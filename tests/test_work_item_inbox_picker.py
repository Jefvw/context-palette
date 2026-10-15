from __future__ import annotations

from dataclasses import replace
import gc
from pathlib import Path
import sys
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from context_palette.launcher import LauncherApp
from context_palette.work_item_refresh import SourceRefreshResult, WorkItemIndex
from context_palette.work_items import DiscoveredWorkItem, WorkItemSource
from tests.support.launcher_ui import disposable_launcher


class WorkItemInboxPickerTests(unittest.TestCase):
    def _item(self, source_id: str = "cap40", *, root: str = "one") -> DiscoveredWorkItem:
        folder = Path(f"D:/synthetic/{root}/ISS-CAP40-report")
        return DiscoveredWorkItem(
            source_id, "Reports", folder.name, folder, "Issue report",
            "ISS", "Issue", "CAP40", "report", (), folder / f"{folder.name}.xlsx",
        )

    def _app(
        self,
        items: tuple[DiscoveredWorkItem, ...],
        *,
        selected: DiscoveredWorkItem | None = None,
        text: str = "  A useful note\nThe full note  ",
    ) -> LauncherApp:
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.send_text_button = Mock()
        app.send_files_button = Mock()
        app.status_var = Mock()
        app.workspace_component = Mock(text_revision=7)
        app.workspace_component.raw_text.return_value = text
        app.workspace_component.get_text.return_value = text.strip()
        app.work_item_index = Mock(items=items)
        app.work_item_inbox = Mock(running=False)
        app.work_item_inbox_picker = None
        app.captured_selection = None
        app.source_foreground_handle = None
        app._selected_work_item = Mock(return_value=selected)
        app._send_workspace_to_work_item_inbox = Mock()
        app._work_item_inbox_source = Mock()
        app._start_work_item_refresh = Mock()
        app._refresh_results = Mock()
        app.item_context_filter = "Unrelated context"
        app.item_scope = "actions"
        app.search_var = Mock()
        app.search_var.get.return_value = "unrelated search"
        return app

    def _open(self, app: LauncherApp) -> tuple[Mock, tuple[str, ...], object]:
        popup = Mock(closed=False)
        with patch("context_palette.launcher.SearchableSelectionPopup", return_value=popup) as factory:
            app._choose_work_item_inbox()
        self.assertIs(factory.call_args.args[0], app.send_text_button)
        self.assertFalse(factory.call_args.kwargs["multiple"])
        self.assertEqual(factory.call_args.kwargs["title"], "Choose Work Item Excel Inbox")
        self.assertEqual(factory.call_args.kwargs["search_label"], "Find Work Item")
        self.assertEqual(factory.call_args.kwargs["item_name"], "Work Item")
        popup.apply_button.configure.assert_called_once_with(text="Append text")
        return popup, tuple(factory.call_args.args[1]), factory.call_args.kwargs["on_select"]

    def test_open_uses_loaded_work_items_and_preselects_exact_main_identity_without_effects(self):
        first = replace(self._item(), matching_workbook_path=None)
        selected = self._item("cap50", root="two")
        selected = replace(selected, matching_workbook_path=selected.folder_path / "Exact workbook.xlsx")
        app = self._app((first, selected), selected=replace(selected, display_name="Old display"))
        with (
            patch("subprocess.Popen", side_effect=AssertionError("No process on open")),
            patch.object(Path, "read_text", side_effect=AssertionError("No read on open")),
            patch.object(Path, "read_bytes", side_effect=AssertionError("No read on open")),
            patch.object(Path, "write_text", side_effect=AssertionError("No write on open")),
            patch.object(Path, "write_bytes", side_effect=AssertionError("No write on open")),
            patch.object(Path, "exists", side_effect=AssertionError("No probe on open")),
            patch.object(Path, "is_file", side_effect=AssertionError("No probe on open")),
            patch.object(Path, "is_dir", side_effect=AssertionError("No scan on open")),
            patch("context_palette.launcher.SearchableSelectionPopup", return_value=Mock(closed=False)) as factory,
        ):
            app._choose_work_item_inbox()
            selection_detail = factory.call_args.kwargs["selection_detail"]
            details = {label: selection_detail(label) for label in factory.call_args.args[1]}
        labels = tuple(factory.call_args.args[1])
        self.assertEqual(len(labels), 2)
        self.assertNotEqual(labels[0], labels[1])
        selected_label = next(label for label in labels if str(selected.folder_path) in label)
        self.assertEqual(tuple(factory.call_args.kwargs["selected"]), (selected_label,))
        for item in (first, selected):
            self.assertTrue(any(item.display_name in label and item.source_name in label
                                and str(item.folder_path) in label for label in labels))
            label = next(label for label in labels if str(item.folder_path) in label)
            workbook = item.matching_workbook_path or item.folder_path / f"{item.folder_path.name}.xlsx"
            self.assertIn(item.source_id, details[label])
            self.assertIn(str(workbook), details[label])
        app._start_work_item_refresh.assert_not_called()
        app._work_item_inbox_source.assert_not_called()
        self._assert_no_send_or_view_change(app)

    def test_duplicate_visible_names_dispatch_exact_source_and_folder(self):
        first, second = self._item(), self._item("cap50", root="two")
        app = self._app((first, second))
        popup, labels, select = self._open(app)
        chosen_label = next(label for label in labels if str(second.folder_path) in label)
        dispatch_order = Mock()
        dispatch_order.attach_mock(popup.close, "close_picker")
        dispatch_order.attach_mock(app._send_workspace_to_work_item_inbox, "send")

        select((chosen_label,))

        app._send_workspace_to_work_item_inbox.assert_called_once_with(second)
        popup.close.assert_called_once_with()
        self.assertEqual([entry[0] for entry in dispatch_order.mock_calls], ["close_picker", "send"])
        self.assertIsNone(app.work_item_inbox_picker)
        self._assert_view_unchanged(app)
        app.workspace_component.selected_or_full_text.assert_not_called()
        app.workspace_component.set_text.assert_not_called()

    def test_identical_label_parts_remain_distinct_by_stable_identity(self):
        first = self._item()
        second = replace(first, source_id="cap50")
        app = self._app((first, second))
        _popup, labels, select = self._open(app)
        self.assertEqual(len(labels), 2)
        self.assertNotEqual(labels[0], labels[1])

        select((labels[1],))

        app._send_workspace_to_work_item_inbox.assert_called_once_with(second)

    def test_cancel_or_unrecognized_selection_never_dispatches(self):
        for values in ((), ("not a listed Work Item",)):
            with self.subTest(values=values):
                app = self._app((self._item(),))
                _popup, _labels, select = self._open(app)
                select(values)
                self._assert_no_send_or_view_change(app)

    def test_cancel_destroy_clears_picker_and_rejects_retained_callback(self):
        app = self._app((self._item(),))
        popup, labels, select = self._open(app)
        destroy = popup.window.bind.call_args.args[1]
        self.assertEqual(popup.window.bind.call_args.args[0], "<Destroy>")
        self.assertEqual(popup.window.bind.call_args.kwargs["add"], "+")

        popup.closed = True
        destroy(SimpleNamespace(widget=popup.window))
        select((labels[0],))

        self.assertIsNone(app.work_item_inbox_picker)
        self._assert_no_send_or_view_change(app)

    def test_child_or_obsolete_popup_destroy_does_not_forget_current_picker(self):
        app = self._app((self._item(),))
        old, _labels, _select = self._open(app)
        old_destroy = old.window.bind.call_args.args[1]
        active, _labels, _select = self._open(app)
        active_destroy = active.window.bind.call_args.args[1]

        active_destroy(SimpleNamespace(widget=Mock()))
        old_destroy(SimpleNamespace(widget=old.window))

        self.assertIs(app.work_item_inbox_picker, active)
        self._assert_no_send_or_view_change(app)

    def test_changed_text_or_changed_revision_rejects_selection(self):
        for change in ("text", "revision", "edit then undo"):
            with self.subTest(change=change):
                app = self._app((self._item(),))
                _popup, labels, select = self._open(app)
                if change == "text":
                    app.workspace_component.raw_text.return_value += " changed"
                else:
                    app.workspace_component.text_revision += 1
                select((labels[0],))
                self._assert_no_send_or_view_change(app)
                app.status_var.set.assert_called()

    def test_changed_captured_source_rejects_selection(self):
        for change in ("selection", "window"):
            with self.subTest(change=change):
                app = self._app((self._item(),))
                app.captured_selection = "Captured note"
                app.source_foreground_handle = 100
                _popup, labels, select = self._open(app)
                if change == "selection":
                    app.captured_selection = "Another captured note"
                else:
                    app.source_foreground_handle = 101
                select((labels[0],))
                self._assert_no_send_or_view_change(app)

    def test_busy_after_open_rejects_selection(self):
        app = self._app((self._item(),))
        _popup, labels, select = self._open(app)
        app.work_item_inbox.running = True

        select((labels[0],))

        self._assert_no_send_or_view_change(app)
        app.status_var.set.assert_called()

    def test_removed_source_is_not_replaced_by_same_visible_name(self):
        first = self._item()
        app = self._app((first,))
        _popup, labels, select = self._open(app)
        app.work_item_index.items = (replace(first, source_id="cap50"),)

        select((labels[0],))

        self._assert_no_send_or_view_change(app)
        app.status_var.set.assert_called()

    def test_changed_destination_paths_reject_selection_even_with_same_identity(self):
        first = self._item()
        replacements = (
            replace(first, folder_path=Path("D:/synthetic/moved/ISS-CAP40-report")),
            replace(first, matching_workbook_path=first.folder_path / "different.xlsx"),
            replace(first, matching_workbook_path=None),
        )
        for moved in replacements:
            with self.subTest(moved=moved):
                app = self._app((first,))
                _popup, labels, select = self._open(app)
                app.work_item_index.items = (moved,)
                select((labels[0],))
                self._assert_no_send_or_view_change(app)

    def test_refresh_preserving_exact_destination_dispatches_current_item(self):
        first = self._item()
        app = self._app((first,))
        _popup, labels, select = self._open(app)
        refreshed = replace(first, display_name="Updated display", project_codes=("CAP50",))
        app.work_item_index.items = (refreshed,)

        select((labels[0],))

        app._send_workspace_to_work_item_inbox.assert_called_once_with(refreshed)

    def test_reopening_closes_previous_picker_and_rejects_its_stale_callback(self):
        app = self._app((self._item(),))
        first_popup, first_labels, first_select = self._open(app)
        second_popup, labels, select = self._open(app)
        first_popup.close.assert_called_once_with()
        self.assertIs(app.work_item_inbox_picker, second_popup)

        first_select((first_labels[0],))
        app._send_workspace_to_work_item_inbox.assert_not_called()
        select((labels[0],))
        select((labels[0],))

        app._send_workspace_to_work_item_inbox.assert_called_once_with(app.work_item_index.items[0])

    def test_blank_busy_or_empty_index_stops_before_opening_picker(self):
        for unavailable in ("blank", "busy", "no Work Items"):
            with self.subTest(unavailable=unavailable):
                app = self._app((self._item(),))
                if unavailable == "blank":
                    app.workspace_component.raw_text.return_value = " \n\t"
                elif unavailable == "busy":
                    app.work_item_inbox.running = True
                else:
                    app.work_item_index.items = ()
                with patch("context_palette.launcher.SearchableSelectionPopup") as factory:
                    app._choose_work_item_inbox()
                factory.assert_not_called()
                self._assert_no_send_or_view_change(app)

    @unittest.skipUnless(sys.platform == "win32", "Requires Windows Tk.")
    def test_real_popup_apply_restores_prior_grab_before_dispatch_and_cancel_clears_owner(self):
        gc.collect()
        with disposable_launcher() as (app, get, clear, append):
            item = self._item()
            source = WorkItemSource(item.source_id, item.source_name, item.folder_path.parent)
            app.work_item_index = WorkItemIndex((SourceRefreshResult(source, (item,)),))
            app._selected_work_item = Mock(return_value=None)
            app.workspace_component.set_text("  Synthetic note\nFull text  ")
            app.root.update_idletasks()
            text = app.workspace_component.raw_text()
            real_toplevel = tk.Toplevel

            def hidden_popup(owner):
                window = real_toplevel(owner)
                window.attributes("-alpha", 0)
                return window

            def dispatched(selected):
                self.assertIs(selected, item)
                self.assertIs(app.root.grab_current(), app.root)
                self.assertIsNone(app.work_item_inbox_picker)

            app._send_workspace_to_work_item_inbox = Mock(side_effect=dispatched)
            app.root.grab_set()
            try:
                with patch("context_palette.searchable_selection.tk.Toplevel", side_effect=hidden_popup):
                    app._choose_work_item_inbox()
                    picker = app.work_item_inbox_picker
                    app.root.update_idletasks()
                    self.assertIs(app.root.grab_current(), picker.window)
                    self.assertIs(picker.previous_grab, app.root)

                    # Actual Popup.apply calls the host consumer, which closes
                    # the popup before dispatch; Apply then closes it again.
                    picker.apply_button.invoke()
                    picker.close()
                    picker.on_select(picker.values[:1])
                    app._send_workspace_to_work_item_inbox.assert_called_once_with(item)
                    self.assertTrue(picker.closed)
                    self.assertIs(app.root.grab_current(), app.root)

                    app._choose_work_item_inbox()
                    cancelled = app.work_item_inbox_picker
                    self.assertIs(app.root.grab_current(), cancelled.window)
                    self.assertEqual(cancelled._close_event(), "break")
                    self.assertTrue(cancelled.closed)
                    self.assertIsNone(app.work_item_inbox_picker)
                    self.assertIs(app.root.grab_current(), app.root)
                    cancelled.on_select(cancelled.values[:1])
                    app._send_workspace_to_work_item_inbox.assert_called_once_with(item)
            finally:
                app.root.grab_release()
            self.assertEqual(app.workspace_component.raw_text(), text)
            get.assert_not_called()
            clear.assert_not_called()
            append.assert_not_called()

    def _assert_no_send_or_view_change(self, app: LauncherApp) -> None:
        app._send_workspace_to_work_item_inbox.assert_not_called()
        app.work_item_inbox.start.assert_not_called()
        app.workspace_component.set_text.assert_not_called()
        app.root.clipboard_get.assert_not_called()
        app.root.clipboard_clear.assert_not_called()
        app.root.clipboard_append.assert_not_called()
        self._assert_view_unchanged(app)

    def _assert_view_unchanged(self, app: LauncherApp) -> None:
        self.assertEqual(app.item_context_filter, "Unrelated context")
        self.assertEqual(app.item_scope, "actions")
        app.search_var.set.assert_not_called()
        app._refresh_results.assert_not_called()


if __name__ == "__main__":
    unittest.main()
