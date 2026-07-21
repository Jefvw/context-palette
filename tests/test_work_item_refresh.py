from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.work_item_refresh import (
    WorkItemIndex,
    WorkItemRefreshCoordinator,
    refresh_work_item_index,
)
from context_palette.work_items import WorkItemSource


class WorkItemRefreshTests(unittest.TestCase):
    def test_refresh_combines_available_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self._source(root, "one", "ISS-CAP40-one")
            second = self._source(root, "two", "TRCK-CAP49-two")

            index = refresh_work_item_index((first, second))

            self.assertEqual([item.display_name for item in index.items], [
                "ISS-CAP40-one",
                "TRCK-CAP49-two",
            ])
            self.assertTrue(all(result.error is None for result in index.sources))
            self.assertGreaterEqual(index.elapsed_seconds, 0.0)

    def test_failed_source_preserves_only_its_last_successful_items(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            available = self._source(root, "available", "ISS-CAP40-current")
            failing = self._source(root, "failing", "QST-CAP49-remembered")
            previous = refresh_work_item_index((available, failing))
            failing.workitems_path.rename(failing.workitems_path.with_name("offline"))
            (available.workitems_path / "TRCK-CAP40-new").mkdir()

            refreshed = refresh_work_item_index((available, failing), previous)

            by_id = {result.source.id: result for result in refreshed.sources}
            self.assertEqual(len(by_id["available"].items), 2)
            self.assertFalse(by_id["available"].using_last_known_good)
            self.assertEqual(
                [item.display_name for item in by_id["failing"].items],
                ["QST-CAP49-remembered"],
            )
            self.assertTrue(by_id["failing"].using_last_known_good)
            self.assertIn("unavailable", by_id["failing"].error or "")

    def test_failed_new_source_is_empty_and_removed_sources_leave_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            retained = self._source(root, "retained", "ISS-CAP40-retained")
            removed = self._source(root, "removed", "ISS-CAP40-removed")
            previous = refresh_work_item_index((retained, removed))
            missing = WorkItemSource("missing", "Missing", root / "missing")

            refreshed = refresh_work_item_index((retained, missing), previous)

            self.assertEqual([result.source.id for result in refreshed.sources], [
                "retained",
                "missing",
            ])
            self.assertEqual(refreshed.sources[1].items, ())
            self.assertFalse(refreshed.sources[1].using_last_known_good)

    def test_background_coordinator_queues_delivery_for_main_thread_drain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = self._source(Path(directory), "one", "ISS-CAP40-one")
            completed: list[tuple[WorkItemIndex, int]] = []
            main_thread = threading.get_ident()
            coordinator = WorkItemRefreshCoordinator()
            self.assertTrue(
                coordinator.start(
                    (source,),
                    None,
                    lambda index: completed.append((index, threading.get_ident())),
                )
            )
            self.assertFalse(coordinator.start((source,), None, lambda _index: None))
            wait = threading.Event()
            for _attempt in range(200):
                if coordinator.completion_pending:
                    break
                wait.wait(0.01)
            else:
                self.fail("Background Work Items refresh did not complete")
            self.assertEqual(completed, [])
            self.assertTrue(coordinator.running)

            self.assertTrue(coordinator.drain())

            self.assertEqual([item.display_name for item in completed[0][0].items], [
                "ISS-CAP40-one"
            ])
            self.assertEqual(completed[0][1], main_thread)
            self.assertFalse(coordinator.running)
            self.assertFalse(coordinator.drain())

    def _source(self, root: Path, source_id: str, folder_name: str) -> WorkItemSource:
        workitems = root / source_id / "workitems"
        (workitems / folder_name).mkdir(parents=True)
        return WorkItemSource(source_id, source_id.title(), workitems)


if __name__ == "__main__":
    unittest.main()
