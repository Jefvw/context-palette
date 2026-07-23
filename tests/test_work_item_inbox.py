from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.work_item_inbox import (
    MAX_EXCEL_CELL_CHARS,
    WorkItemInboxCoordinator,
    WorkItemInboxEntry,
    WorkItemInboxError,
    append_work_item_inbox,
    create_work_item_inbox_entry,
    first_http_url,
    send_to_work_item_inbox,
)


class WorkItemInboxTests(unittest.TestCase):
    def test_entry_maps_text_first_link_source_and_timestamp(self) -> None:
        now = datetime(2026, 7, 23, 12, 30, tzinfo=timezone.utc)

        entry = create_work_item_inbox_entry(
            "See https://example.com/first, then https://example.com/second.",
            source="  Browser   title  ",
            now=now,
        )

        self.assertEqual(entry.added, now.isoformat())
        self.assertEqual(
            entry.text,
            "See https://example.com/first, then https://example.com/second.",
        )
        self.assertEqual(entry.link, "https://example.com/first")
        self.assertEqual(entry.source, "Browser title")

    def test_empty_and_oversized_content_are_rejected(self) -> None:
        with self.assertRaisesRegex(WorkItemInboxError, "empty"):
            create_work_item_inbox_entry("  ", source="Clipboard")
        with self.assertRaisesRegex(WorkItemInboxError, "cell limit"):
            create_work_item_inbox_entry(
                "x" * (MAX_EXCEL_CELL_CHARS + 1),
                source="Clipboard",
            )
        with self.assertRaisesRegex(WorkItemInboxError, "cell limit"):
            create_work_item_inbox_entry(
                "😀" * 20_000,
                source="Clipboard",
            )
        with self.assertRaisesRegex(WorkItemInboxError, "control character"):
            create_work_item_inbox_entry("bad\x00text", source="Clipboard")

    def test_unsupported_scheme_is_not_used_as_link(self) -> None:
        self.assertEqual(first_http_url("Open file:///C:/temp or ftp://example.com"), "")

    def test_existing_matching_workbook_is_appended_without_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "ISS-CAP40-example"
            folder.mkdir()
            workbook = folder / "ISS-CAP40-example.xlsx"
            workbook.write_bytes(b"existing")
            entry = WorkItemInboxEntry("now", "text", "", "Input / Output")
            appender = Mock(return_value=(4, False))

            result = send_to_work_item_inbox(
                folder,
                workbook,
                None,
                entry,
                appender=appender,
            )

            self.assertEqual(result.row, 4)
            self.assertFalse(result.created_workbook)
            appender.assert_called_once_with(workbook, entry)

    def test_missing_workbook_is_created_from_template_then_appended(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "ISS-CAP40-example"
            folder.mkdir()
            template = root / "generic.xlsx"
            template.write_bytes(b"template")
            entry = WorkItemInboxEntry("now", "text", "", "Input / Output")
            appender = Mock(return_value=(2, True))

            result = send_to_work_item_inbox(
                folder,
                None,
                template,
                entry,
                appender=appender,
            )

            self.assertTrue(result.created_workbook)
            self.assertTrue(result.created_sheet)
            self.assertEqual(result.workbook_path.read_bytes(), b"template")

    def test_nonmatching_workbook_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "ISS-CAP40-example"
            folder.mkdir()
            other = folder / "other.xlsx"
            other.write_bytes(b"other")

            with self.assertRaisesRegex(WorkItemInboxError, "exactly match"):
                send_to_work_item_inbox(
                    folder,
                    other,
                    None,
                    WorkItemInboxEntry("now", "text", "", "source"),
                )

    def test_excel_script_is_fixed_literal_safe_and_utf8(self) -> None:
        script = (
            ROOT / "integrations" / "Append-WorkItemInbox.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("[Console]::InputEncoding", script)
        self.assertIn('function Resolve-WorkbookPath', script)
        self.assertIn('$candidatePath = Resolve-WorkbookPath([string]$candidate.FullName)', script)
        self.assertIn('if ([string]::IsNullOrWhiteSpace($candidatePath)) {', script)
        self.assertIn('$sheet.Cells.Item($row, 2)', script)
        self.assertIn('$addedCell.NumberFormat = "@"', script)
        self.assertIn('$textCell.NumberFormat = "@"', script)
        self.assertIn('$sourceCell.NumberFormat = "@"', script)
        self.assertIn('$sheet.Range("A$row", "D$row").Clear()', script)
        self.assertIn('$excel.Workbooks.Open($workbookPath, 0, $false)', script)
        self.assertNotIn("Invoke-Expression", script)
        self.assertNotIn("Start-Process", script)
        self.assertNotIn("DownloadString", script)

    def test_powershell_request_uses_stdin_and_parses_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workbook = root / "item.xlsx"
            workbook.write_bytes(b"xlsx")
            script = root / "append.ps1"
            script.write_text("# fixed integration", encoding="utf-8")
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='{"row":3,"created_sheet":true}',
                stderr="",
            )
            entry = WorkItemInboxEntry(
                "2026-07-23T12:00:00+00:00",
                "=not a formula",
                "https://example.com",
                "Browser",
            )

            with (
                patch("context_palette.work_item_inbox.shutil.which", return_value="powershell.exe"),
                patch(
                    "context_palette.work_item_inbox.subprocess.run",
                    return_value=completed,
                ) as run,
            ):
                result = append_work_item_inbox(
                    workbook,
                    entry,
                    script_path=script,
                )

            self.assertEqual(result, (3, True))
            request = json.loads(run.call_args.kwargs["input"])
            self.assertEqual(request["text"], "=not a formula")
            self.assertNotIn("=not a formula", run.call_args.args[0])

    def test_coordinator_rejects_double_submission_and_delivers_completion(self) -> None:
        coordinator = WorkItemInboxCoordinator()
        callback = Mock()
        release = __import__("threading").Event()
        result = Mock()

        def send(*_args):
            release.wait(1)
            return result

        with patch("context_palette.work_item_inbox.send_to_work_item_inbox", side_effect=send):
            self.assertTrue(
                coordinator.start(
                    Path("C:/work/item"),
                    Path("C:/work/item/item.xlsx"),
                    None,
                    WorkItemInboxEntry("now", "text", "", "source"),
                    callback,
                )
            )
            self.assertFalse(
                coordinator.start(
                    Path("C:/work/item"),
                    None,
                    None,
                    WorkItemInboxEntry("now", "text", "", "source"),
                    callback,
                )
            )
            release.set()
            for _ in range(100):
                if coordinator.drain():
                    break
                __import__("time").sleep(0.01)

        callback.assert_called_once_with(result, None)
        self.assertFalse(coordinator.running)

    def test_coordinator_converts_unexpected_failure_and_recovers(self) -> None:
        coordinator = WorkItemInboxCoordinator()
        callback = Mock()

        with self.assertLogs(
            "context_palette.work_item_inbox",
            level="ERROR",
        ) as logs:
            with patch(
                "context_palette.work_item_inbox.send_to_work_item_inbox",
                side_effect=RuntimeError("boom"),
            ):
                self.assertTrue(
                    coordinator.start(
                        Path("C:/work/item"),
                        Path("C:/work/item/item.xlsx"),
                        None,
                        WorkItemInboxEntry("now", "text", "", "source"),
                        callback,
                    )
                )
                for _ in range(100):
                    if coordinator.drain():
                        break
                    __import__("time").sleep(0.01)
                else:
                    self.fail("Unexpected Inbox failure did not reach completion")

        result, error = callback.call_args.args
        self.assertIsNone(result)
        self.assertIsInstance(error, WorkItemInboxError)
        self.assertIn("unexpected local error", str(error))
        self.assertFalse(coordinator.running)
        self.assertIn("Unexpected Work Item Inbox", logs.output[0])


if __name__ == "__main__":
    unittest.main()
