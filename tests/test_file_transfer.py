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

from context_palette.file_transfer import (
    FileTransferCoordinator,
    FileTransferError,
    FileTransferStaleError,
    FileTransferUnexpectedError,
    execute_file_transfer_plan,
    parse_workspace_file_paths,
    plan_file_transfer,
)


class FileTransferParsingTests(unittest.TestCase):
    def test_parses_quoted_and_unquoted_absolute_files_in_stable_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first note.txt"
            second = root / "second.txt"
            first.write_text("first", encoding="utf-8")
            second.write_text("second", encoding="utf-8")

            result = parse_workspace_file_paths(
                f'  "{first}"  \n\n{second}\n'
            )

            self.assertEqual(result, (first.resolve(), second.resolve()))

    def test_rejects_invalid_lines_duplicates_and_more_than_one_hundred(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.txt"
            source.write_text("content", encoding="utf-8")
            folder = root / "folder"
            folder.mkdir()
            cases = (
                ("", "does not contain"),
                ("relative.txt", "absolute"),
                (str(root / "missing.txt"), "does not exist"),
                (str(folder), "folder"),
                (f'"{source}', "unmatched"),
                (f"{source}\n{source}", "more than once"),
                ("https://example.test/file.txt", "absolute"),
            )
            for value, message in cases:
                with self.subTest(value=value), self.assertRaisesRegex(
                    FileTransferError,
                    message,
                ):
                    parse_workspace_file_paths(value)

            many = "\n".join(str(source) for _ in range(101))
            with self.assertRaisesRegex(FileTransferError, "at most 100"):
                parse_workspace_file_paths(many)


class FileTransferPlanningTests(unittest.TestCase):
    def test_clean_plan_is_deterministic_pure_and_reports_exact_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source" / "report.csv"
            source.parent.mkdir()
            source.write_bytes(b"a,b\n1,2\n")
            destination = root / "destination"
            destination.mkdir()

            first = plan_file_transfer(str(source), destination)
            second = plan_file_transfer(str(source), destination)

            self.assertEqual(first, second)
            self.assertEqual(first.create_count, 1)
            self.assertEqual(first.replace_count, 0)
            self.assertEqual(first.renamed_count, 0)
            self.assertEqual(first.skipped_count, 0)
            self.assertEqual(first.bytes_total, source.stat().st_size)
            self.assertFalse(first.requires_review)
            self.assertEqual(first.items[0].destination_path, destination / source.name)
            self.assertEqual(first.items[0].disposition, "create")
            self.assertEqual(len(first.fingerprint), 64)
            self.assertEqual(list(destination.iterdir()), [])

    def test_default_suffixes_existing_and_batch_collisions_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources: list[Path] = []
            for index, content in enumerate((b"first", b"second"), start=1):
                source = root / f"source-{index}" / "report.csv"
                source.parent.mkdir()
                source.write_bytes(content)
                sources.append(source)
            destination = root / "destination"
            destination.mkdir()
            (destination / "report.csv").write_bytes(b"existing")
            (destination / "report(1).csv").write_bytes(b"existing suffix")

            plan = plan_file_transfer(
                "\n".join(str(path) for path in sources),
                destination,
            )

            self.assertEqual(
                [item.destination_path.name for item in plan.items],
                ["report(2).csv", "report(3).csv"],
            )
            self.assertEqual(plan.create_count, 2)
            self.assertEqual(plan.replace_count, 0)
            self.assertEqual(plan.renamed_count, 2)
            self.assertTrue(plan.requires_review)
            self.assertTrue(all(item.original_conflict for item in plan.items))

    def test_explicit_overwrite_replaces_unsuffixed_but_never_reuses_batch_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first" / "report.csv"
            second = root / "second" / "report.csv"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            destination = root / "destination"
            destination.mkdir()
            (destination / "report.csv").write_bytes(b"existing")

            plan = plan_file_transfer(
                f"{first}\n{second}",
                destination,
                allow_overwrite=True,
            )

            self.assertEqual(
                [(item.destination_path.name, item.disposition) for item in plan.items],
                [("report.csv", "replace"), ("report(1).csv", "create")],
            )
            self.assertEqual(plan.replace_count, 1)
            self.assertEqual(plan.create_count, 1)
            self.assertTrue(plan.requires_review)

    def test_same_source_and_destination_is_an_explicit_skip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "already-here.txt"
            source.write_text("keep", encoding="utf-8")

            plan = plan_file_transfer(str(source), folder)

            self.assertEqual(plan.skipped_count, 1)
            self.assertEqual(plan.create_count, 0)
            self.assertEqual(plan.items[0].disposition, "skip_same")
            self.assertTrue(plan.requires_review)

    def test_destination_must_be_an_existing_absolute_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.txt"
            source.write_text("content", encoding="utf-8")
            for destination, message in (
                (Path("relative"), "absolute"),
                (Path(directory) / "missing", "unavailable"),
                (source, "unavailable"),
            ):
                with self.subTest(destination=destination), self.assertRaisesRegex(
                    FileTransferError,
                    message,
                ):
                    plan_file_transfer(str(source), destination)


class FileTransferExecutionTests(unittest.TestCase):
    def test_executes_create_and_reviewed_replace_without_changing_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_source = root / "source-a" / "new.txt"
            replace_source = root / "source-b" / "existing.txt"
            create_source.parent.mkdir()
            replace_source.parent.mkdir()
            create_source.write_bytes(b"new bytes")
            replace_source.write_bytes(b"replacement")
            destination = root / "destination"
            destination.mkdir()
            (destination / "existing.txt").write_bytes(b"old")
            original_sources = {
                create_source: create_source.read_bytes(),
                replace_source: replace_source.read_bytes(),
            }
            plan = plan_file_transfer(
                f"{create_source}\n{replace_source}",
                destination,
                allow_overwrite=True,
            )

            result = execute_file_transfer_plan(plan)

            self.assertEqual(result.created, (destination / "new.txt",))
            self.assertEqual(result.replaced, (destination / "existing.txt",))
            self.assertEqual(result.failures, ())
            self.assertFalse(result.stopped)
            self.assertEqual((destination / "new.txt").read_bytes(), b"new bytes")
            self.assertEqual(
                (destination / "existing.txt").read_bytes(),
                b"replacement",
            )
            self.assertEqual(
                result.bytes_copied,
                len(b"new bytes") + len(b"replacement"),
            )
            for source, content in original_sources.items():
                self.assertEqual(source.read_bytes(), content)
            self.assertFalse(
                any("context-palette" in path.name for path in destination.iterdir())
            )

    def test_stale_source_or_destination_is_rejected_before_any_effect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source" / "report.txt"
            source.parent.mkdir()
            source.write_text("reviewed", encoding="utf-8")
            destination = root / "destination"
            destination.mkdir()
            existing = destination / "report.txt"
            existing.write_text("old", encoding="utf-8")

            source_plan = plan_file_transfer(
                str(source), destination, allow_overwrite=True
            )
            source.write_text("changed source", encoding="utf-8")
            with self.assertRaisesRegex(FileTransferStaleError, "changed"):
                execute_file_transfer_plan(source_plan)
            self.assertEqual(existing.read_text(encoding="utf-8"), "old")

            source.write_text("reviewed again", encoding="utf-8")
            destination_plan = plan_file_transfer(
                str(source), destination, allow_overwrite=True
            )
            existing.write_text("changed destination", encoding="utf-8")
            with self.assertRaisesRegex(FileTransferStaleError, "changed"):
                execute_file_transfer_plan(destination_plan)
            self.assertEqual(
                existing.read_text(encoding="utf-8"),
                "changed destination",
            )

    def test_destination_created_during_staging_is_not_clobbered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source" / "report.txt"
            source.parent.mkdir()
            source.write_text("source", encoding="utf-8")
            destination = root / "destination"
            destination.mkdir()
            plan = plan_file_transfer(str(source), destination)
            original_stage = __import__(
                "context_palette.file_transfer",
                fromlist=["_stage_copy"],
            )._stage_copy

            def stage_then_race(item, temporary):
                original_stage(item, temporary)
                item.destination_path.write_text("racer", encoding="utf-8")

            with (
                patch(
                    "context_palette.file_transfer._stage_copy",
                    side_effect=stage_then_race,
                ),
                self.assertRaisesRegex(FileTransferStaleError, "destination"),
            ):
                execute_file_transfer_plan(plan)

            self.assertEqual(
                (destination / "report.txt").read_text(encoding="utf-8"),
                "racer",
            )
            self.assertFalse(
                any("context-palette" in path.name for path in destination.iterdir())
            )

    def test_publication_failure_reports_exact_partial_effect_and_cleans_temps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "source" / "first.txt"
            second = root / "source" / "second.txt"
            first.parent.mkdir()
            first.write_text("first", encoding="utf-8")
            second.write_text("second", encoding="utf-8")
            destination = root / "destination"
            destination.mkdir()
            plan = plan_file_transfer(f"{first}\n{second}", destination)
            module = __import__(
                "context_palette.file_transfer",
                fromlist=["_publish_item"],
            )
            original_publish = module._publish_item
            calls = 0

            def publish_once(item, temporary):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("private failure detail")
                original_publish(item, temporary)

            with patch(
                "context_palette.file_transfer._publish_item",
                side_effect=publish_once,
            ):
                result = execute_file_transfer_plan(plan)

            self.assertEqual(result.created, (destination / "first.txt",))
            self.assertEqual(result.replaced, ())
            self.assertEqual(len(result.failures), 1)
            self.assertNotIn("private failure detail", result.failures[0].message)
            self.assertTrue((destination / "first.txt").is_file())
            self.assertFalse((destination / "second.txt").exists())
            self.assertFalse(
                any("context-palette" in path.name for path in destination.iterdir())
            )

    def test_stop_before_first_file_has_no_effect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.txt"
            source.write_text("source", encoding="utf-8")
            destination = root / "destination"
            destination.mkdir()
            plan = plan_file_transfer(str(source), destination)

            result = execute_file_transfer_plan(plan, stop_requested=lambda: True)

            self.assertTrue(result.stopped)
            self.assertEqual(result.created, ())
            self.assertFalse((destination / source.name).exists())


class FileTransferCoordinatorTests(unittest.TestCase):
    def test_single_flight_drains_on_caller_and_can_chain_from_callback(self) -> None:
        coordinator = FileTransferCoordinator()
        release = threading.Event()
        planned = Mock()
        first_callback = Mock()

        def plan(*_args, **_kwargs):
            release.wait(1)
            return planned

        with patch(
            "context_palette.file_transfer.plan_file_transfer",
            side_effect=plan,
        ):
            self.assertTrue(
                coordinator.start_plan(
                    "C:/source.txt",
                    Path("C:/destination"),
                    False,
                    first_callback,
                )
            )
            self.assertEqual(coordinator.phase, "planning")
            self.assertFalse(
                coordinator.start_plan(
                    "C:/other.txt",
                    Path("C:/destination"),
                    False,
                    Mock(),
                )
            )
            release.set()
            for _ in range(100):
                if coordinator.drain():
                    break
                time.sleep(0.01)

        first_callback.assert_called_once_with(planned, None)
        self.assertFalse(coordinator.running)
        self.assertIsNone(coordinator.phase)

    def test_unexpected_worker_failure_is_sanitized(self) -> None:
        coordinator = FileTransferCoordinator()
        callback = Mock()
        with patch(
            "context_palette.file_transfer.plan_file_transfer",
            side_effect=RuntimeError("private path and detail"),
        ):
            self.assertTrue(
                coordinator.start_plan(
                    "C:/source.txt",
                    Path("C:/destination"),
                    False,
                    callback,
                )
            )
            for _ in range(100):
                if coordinator.drain():
                    break
                time.sleep(0.01)

        result, error = callback.call_args.args
        self.assertIsNone(result)
        self.assertIsInstance(error, FileTransferUnexpectedError)
        self.assertIn("unexpected local error", str(error))
        self.assertNotIn("private", str(error))
        self.assertFalse(coordinator.running)

    def test_expected_worker_failure_keeps_its_known_error_type(self) -> None:
        coordinator = FileTransferCoordinator()
        callback = Mock()
        expected = FileTransferStaleError("Review Send to again.")
        with patch(
            "context_palette.file_transfer.plan_file_transfer",
            side_effect=expected,
        ):
            self.assertTrue(
                coordinator.start_plan(
                    "C:/source.txt",
                    Path("C:/destination"),
                    False,
                    callback,
                )
            )
            for _ in range(100):
                if coordinator.drain():
                    break
                time.sleep(0.01)

        result, error = callback.call_args.args
        self.assertIsNone(result)
        self.assertIs(error, expected)
        self.assertNotIsInstance(error, FileTransferUnexpectedError)


if __name__ == "__main__":
    unittest.main()
