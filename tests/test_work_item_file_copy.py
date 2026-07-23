from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.work_item_file_copy import (
    WorkItemFileCopyCoordinator,
    WorkItemFileCopyError,
    copy_file_to_work_item,
    file_path_from_workspace,
)


class WorkItemFileCopyTests(unittest.TestCase):
    def test_quoted_exact_path_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source note.txt"
            source.write_text("content", encoding="utf-8")

            parsed = file_path_from_workspace(f'"{source}"')

            self.assertEqual(parsed, source)

    def test_empty_relative_multiple_missing_and_folder_paths_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for value, message in (
                ("", "does not contain"),
                ("relative.txt", "absolute"),
                ("C:\\missing.txt\nother text", "one exact"),
                (str(Path(directory) / "missing.txt"), "does not exist"),
                (directory, "folder"),
            ):
                with self.subTest(value=value), self.assertRaisesRegex(
                    WorkItemFileCopyError,
                    message,
                ):
                    file_path_from_workspace(value)

    def test_file_is_copied_without_overwriting_existing_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source" / "evidence.txt"
            source.parent.mkdir()
            source.write_bytes(b"new content")
            work_item = root / "ISS-CAP40-example"
            work_item.mkdir()

            result = copy_file_to_work_item(source, work_item)

            self.assertEqual(result.destination_path, work_item / source.name)
            self.assertEqual(result.destination_path.read_bytes(), b"new content")
            self.assertEqual(result.size, len(b"new content"))

            result.destination_path.write_bytes(b"keep existing")
            with self.assertRaisesRegex(WorkItemFileCopyError, "already exists"):
                copy_file_to_work_item(source, work_item)
            self.assertEqual(result.destination_path.read_bytes(), b"keep existing")

    def test_source_already_inside_work_item_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work_item = Path(directory) / "ISS-CAP40-example"
            work_item.mkdir()
            source = work_item / "evidence.txt"
            source.write_text("content", encoding="utf-8")

            with self.assertRaisesRegex(WorkItemFileCopyError, "already in"):
                copy_file_to_work_item(source, work_item)

    def test_failed_copy_removes_only_new_partial_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "evidence.txt"
            source.write_text("content", encoding="utf-8")
            work_item = root / "ISS-CAP40-example"
            work_item.mkdir()

            with (
                patch(
                    "context_palette.work_item_file_copy.shutil.copyfileobj",
                    side_effect=OSError("copy failed"),
                ),
                self.assertRaises(WorkItemFileCopyError),
            ):
                copy_file_to_work_item(source, work_item)

            self.assertFalse((work_item / source.name).exists())
            self.assertFalse(
                any("context-palette-copy" in path.name for path in work_item.iterdir())
            )
            self.assertTrue(source.is_file())

    def test_coordinator_rejects_double_submission_and_delivers_completion(self) -> None:
        coordinator = WorkItemFileCopyCoordinator()
        callback = Mock()
        release = threading.Event()
        result = Mock()

        def copy(*_args):
            release.wait(1)
            return result

        with patch(
            "context_palette.work_item_file_copy.copy_file_to_work_item",
            side_effect=copy,
        ):
            self.assertTrue(
                coordinator.start(
                    Path("C:/source.txt"),
                    Path("C:/work/item"),
                    callback,
                )
            )
            self.assertFalse(
                coordinator.start(
                    Path("C:/other.txt"),
                    Path("C:/work/item"),
                    callback,
                )
            )
            release.set()
            for _ in range(100):
                if coordinator.drain():
                    break
                time.sleep(0.01)

        callback.assert_called_once_with(result, None)
        self.assertFalse(coordinator.running)

    def test_coordinator_converts_unexpected_failure_and_does_not_stay_running(self) -> None:
        coordinator = WorkItemFileCopyCoordinator()
        callback = Mock()

        with patch(
            "context_palette.work_item_file_copy.copy_file_to_work_item",
            side_effect=RuntimeError("private detail"),
        ):
            self.assertTrue(
                coordinator.start(
                    Path("C:/source.txt"),
                    Path("C:/work/item"),
                    callback,
                )
            )
            for _ in range(100):
                if coordinator.drain():
                    break
                time.sleep(0.01)

        result, error = callback.call_args.args
        self.assertIsNone(result)
        self.assertIn("unexpected local error", str(error))
        self.assertNotIn("private detail", str(error))
        self.assertFalse(coordinator.running)


if __name__ == "__main__":
    unittest.main()
