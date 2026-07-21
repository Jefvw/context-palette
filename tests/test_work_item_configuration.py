from __future__ import annotations

from pathlib import Path
import gc
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import weakref


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.work_item_configuration import (
    WorkItemsConfigurationPanel,
    _stable_source_id,
)
from context_palette.work_item_refresh import WorkItemIndex
from context_palette.work_item_storage import (
    WorkItemMetadata,
    load_work_item_metadata,
    load_work_item_sources,
    save_work_item_metadata,
    save_work_item_sources,
)
from context_palette.work_items import WorkItemSource


class WorkItemConfigurationTests(unittest.TestCase):
    def test_stable_source_id_is_generated_from_friendly_name(self) -> None:
        self.assertEqual(_stable_source_id(" CAP40 Product & Support "), "cap40-product-support")

    def test_new_source_is_saved_locally_and_refreshes_panel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workitems = root / "workitems"
            workitems.mkdir()
            panel = WorkItemsConfigurationPanel.__new__(WorkItemsConfigurationPanel)
            panel.sources = []
            panel.metadata = {}
            panel.index = WorkItemIndex()
            panel.sources_path = root / "sources.json"
            panel.metadata_path = root / "metadata.json"
            panel.on_change = Mock()
            panel.feedback = Mock()
            panel.render = Mock()
            panel._start_refresh = Mock()

            saved = panel._save_source(
                WorkItemSource("cap40-product", "CAP40 Product", workitems),
                original_id=None,
            )

            self.assertTrue(saved)
            self.assertEqual(load_work_item_sources(panel.sources_path), tuple(panel.sources))
            panel.on_change.assert_called_once_with()
            panel.render.assert_called_once_with()
            panel._start_refresh.assert_called_once_with()

    def test_duplicate_source_id_is_rejected_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workitems = root / "workitems"
            workitems.mkdir()
            existing = WorkItemSource("cap40", "CAP40", workitems)
            panel = WorkItemsConfigurationPanel.__new__(WorkItemsConfigurationPanel)
            panel.sources = [existing]
            panel.parent = None
            panel.metadata = {}
            panel.index = WorkItemIndex()
            panel.sources_path = root / "sources.json"
            panel.metadata_path = root / "metadata.json"
            panel.on_change = Mock()
            panel.feedback = Mock()
            panel.render = Mock()
            panel._start_refresh = Mock()

            with patch("context_palette.work_item_configuration.messagebox.showerror") as error:
                saved = panel._save_source(
                    WorkItemSource("cap40", "Duplicate", workitems),
                    original_id=None,
                )

            self.assertFalse(saved)
            error.assert_called_once()
            self.assertFalse(panel.sources_path.exists())

    def test_personal_tags_are_saved_and_can_be_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.json"
            panel = WorkItemsConfigurationPanel.__new__(WorkItemsConfigurationPanel)
            panel.metadata = {}
            panel.metadata_path = path
            panel.on_change = Mock()
            panel.feedback = Mock()
            panel.render = Mock()
            panel._start_refresh = Mock()
            key = "cap40/ISS-CAP40-example"

            self.assertTrue(panel._save_tags(key, ("urgent", "waiting")))
            self.assertEqual(
                load_work_item_metadata(path)[key],
                WorkItemMetadata(("urgent", "waiting")),
            )
            self.assertTrue(panel._save_tags(key, ()))
            self.assertEqual(load_work_item_metadata(path), {})

    def test_removing_source_is_one_write_and_retains_private_tags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workitems = root / "workitems"
            workitems.mkdir()
            source = WorkItemSource("cap40", "CAP40", workitems)
            sources_path = root / "sources.json"
            metadata_path = root / "metadata.json"
            key = "cap40/ISS-CAP40-example"
            metadata = {key: WorkItemMetadata(("urgent",))}
            save_work_item_sources(sources_path, (source,))
            save_work_item_metadata(metadata_path, metadata)

            panel = WorkItemsConfigurationPanel.__new__(WorkItemsConfigurationPanel)
            panel.parent = None
            panel.sources = [source]
            panel.metadata = metadata
            panel.index = WorkItemIndex()
            panel.sources_path = sources_path
            panel.metadata_path = metadata_path
            panel.source_tree = Mock()
            panel.source_tree.selection.return_value = (source.id,)
            panel.on_change = Mock()
            panel.feedback = Mock()
            panel.render = Mock()
            panel._start_refresh = Mock()

            with patch(
                "context_palette.work_item_configuration.messagebox.askyesno",
                return_value=True,
            ):
                panel.remove_source()

            self.assertEqual(load_work_item_sources(sources_path), ())
            self.assertEqual(load_work_item_metadata(metadata_path), metadata)
            self.assertTrue(workitems.is_dir())
            panel.on_change.assert_called_once_with()
            panel.feedback.assert_called_once()
            panel._start_refresh.assert_called_once_with()

    def test_explicit_refresh_delegates_without_scanning_inline(self) -> None:
        panel = WorkItemsConfigurationPanel.__new__(WorkItemsConfigurationPanel)
        panel.on_change = Mock()
        panel._start_refresh = Mock()

        panel.refresh()

        panel.on_change.assert_called_once_with()
        panel._start_refresh.assert_called_once_with()

    def test_refresh_queues_latest_configuration_when_scan_is_running(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workitems = Path(directory) / "workitems"
            workitems.mkdir()
            panel = WorkItemsConfigurationPanel.__new__(WorkItemsConfigurationPanel)
            panel.sources = [WorkItemSource("cap40", "CAP40", workitems)]
            panel.index = WorkItemIndex()
            panel.refresh_coordinator = Mock()
            panel.refresh_coordinator.start.return_value = False
            panel.refresh_pending = False
            panel.feedback = Mock()

            panel._start_refresh()

            self.assertTrue(panel.refresh_pending)
            panel.feedback.assert_called_once()

    def test_completed_old_refresh_schedules_queued_latest_refresh(self) -> None:
        panel = WorkItemsConfigurationPanel.__new__(WorkItemsConfigurationPanel)
        panel.sources = []
        panel.index = WorkItemIndex()
        panel.refresh_pending = True
        panel.parent = Mock()
        panel.render = Mock()
        panel._start_refresh = Mock()

        panel._accept_refresh(WorkItemIndex())

        self.assertFalse(panel.refresh_pending)
        panel.render.assert_called_once_with()
        panel.parent.after_idle.assert_called_once_with(panel._start_refresh)

    def test_failed_source_write_keeps_live_sources_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workitems = Path(directory) / "workitems"
            workitems.mkdir()
            existing = WorkItemSource("cap40", "CAP40", workitems)
            replacement = WorkItemSource("cap40", "Renamed", workitems)
            panel = WorkItemsConfigurationPanel.__new__(WorkItemsConfigurationPanel)
            panel.parent = None
            panel.sources = [existing]
            panel.index = WorkItemIndex()
            panel.sources_path = Path(directory) / "sources.json"
            panel.on_change = Mock()
            panel.feedback = Mock()
            panel.render = Mock()
            panel._start_refresh = Mock()

            with (
                patch(
                    "context_palette.work_item_configuration.save_work_item_sources",
                    side_effect=PermissionError("denied"),
                ),
                patch("context_palette.work_item_configuration.messagebox.showerror") as error,
            ):
                saved = panel._save_source(replacement, original_id=existing.id)

            self.assertFalse(saved)
            self.assertEqual(panel.sources, [existing])
            error.assert_called_once()
            panel.on_change.assert_not_called()
            panel._start_refresh.assert_not_called()

    def test_failed_tag_write_keeps_live_metadata_unchanged(self) -> None:
        panel = WorkItemsConfigurationPanel.__new__(WorkItemsConfigurationPanel)
        panel.parent = None
        key = "cap40/ISS-CAP40-example"
        original = {key: WorkItemMetadata(("urgent",))}
        panel.metadata = original
        panel.metadata_path = Path("metadata.json")
        panel.on_change = Mock()
        panel.feedback = Mock()
        panel.render = Mock()

        with (
            patch(
                "context_palette.work_item_configuration.save_work_item_metadata",
                side_effect=PermissionError("denied"),
            ),
            patch("context_palette.work_item_configuration.messagebox.showerror") as error,
        ):
            saved = panel._save_tags(key, ("changed",))

        self.assertFalse(saved)
        self.assertIs(panel.metadata, original)
        error.assert_called_once()
        panel.on_change.assert_not_called()

    def test_closed_panel_ignores_late_refresh_without_being_retained(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workitems = Path(directory) / "workitems"
            workitems.mkdir()
            coordinator = Mock()
            coordinator.start.return_value = True
            parent = Mock()
            panel = WorkItemsConfigurationPanel.__new__(WorkItemsConfigurationPanel)
            panel.parent = parent
            panel.sources = [WorkItemSource("cap40", "CAP40", workitems)]
            panel.index = WorkItemIndex()
            panel.refresh_coordinator = coordinator
            panel.refresh_pending = False
            panel.disposed = False
            panel.feedback = Mock()
            panel._accept_refresh = Mock()

            panel._start_refresh()
            completion = coordinator.start.call_args.args[2]
            panel.disposed = True
            completion(WorkItemIndex())

            panel._accept_refresh.assert_not_called()
            parent.reset_mock()
            reference = weakref.ref(panel)
            del panel
            gc.collect()
            self.assertIsNone(reference())


if __name__ == "__main__":
    unittest.main()
