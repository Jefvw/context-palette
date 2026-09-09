from __future__ import annotations

from contextlib import contextmanager, ExitStack
from dataclasses import replace
import gc
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from context_palette.actions import Action, execute_action
from context_palette.drop_action import DropActionSettings, approve_drop_action
from context_palette.drop_adapter import DropItem, DropResult
from context_palette.drop_configuration_window import DropConfigurationWindow
from context_palette.drop_target_window import DropTargetWindow
from context_palette.launcher import LauncherApp
from context_palette.work_item_refresh import SourceRefreshResult, WorkItemIndex
from context_palette.work_items import DiscoveredWorkItem, WorkItemSource


@unittest.skipUnless(sys.platform == "win32", "Requires Windows Tk.")
class LauncherEnhancementsUiTests(unittest.TestCase):
    """Real widgets with synthetic data and all external execution isolated."""

    def setUp(self) -> None:
        gc.collect()

    @contextmanager
    def launcher(self, *, scaling: float = 4 / 3, size: str = "780x600"):
        with tempfile.TemporaryDirectory() as temporary_directory, ExitStack() as stack:
            data = Path(temporary_directory)
            payloads = {
                "actions.json": {"actions": [
                    {"id": "sample", "title": "Sample text", "context": "",
                     "type": "copy_text", "value": "Sample result"},
                ]},
                "contexts.json": {"contexts": []},
                "command_surface.json": {"groups": []},
            }
            for filename, payload in payloads.items():
                (data / filename).write_text(json.dumps(payload), encoding="utf-8")
            (data / "cheatsheets").mkdir()
            root = tk.Tk()
            root.withdraw()
            root.tk.call("tk", "scaling", scaling)
            clipboard_get = stack.enter_context(patch.object(root, "clipboard_get", return_value="Clipboard fixture"))
            clipboard_clear = stack.enter_context(patch.object(root, "clipboard_clear"))
            clipboard_append = stack.enter_context(patch.object(root, "clipboard_append"))
            for target, options in (
                ("SingleInstanceServer.start", {"return_value": True}),
                ("SingleInstanceServer.stop", {}),
                ("GlobalHotkey.start", {"return_value": False}),
                ("GlobalHotkey.stop", {}),
                ("DropTargetWindow.start", {"return_value": True}),
                ("LauncherApp._start_work_item_refresh", {}),
                ("open_action_target", {"side_effect": AssertionError("UI smoke must not open targets")}),
                ("execute_action", {"side_effect": AssertionError("UI smoke must not execute Actions")}),
            ):
                stack.enter_context(patch(f"context_palette.launcher.{target}", **options))
            try:
                app = LauncherApp(
                    root, data / "actions.json", data / "local_actions.json",
                    data / "contexts.json", data / "local_contexts.json",
                    data / "command_surface.json", data / "local_command_surface.json",
                    data / "palette.json", data / "inbox.json", data / "cheatsheets",
                    instance_port=0,
                )
                root.geometry(f"{size}+-32000+-32000")
                root.deiconify()
                root.update()
                app._set_initial_main_split()
                root.update_idletasks()
                yield app, clipboard_get, clipboard_clear, clipboard_append
            finally:
                # Polling and tooltip timers are intentionally owned by this
                # interpreter only, never by the user's resident application.
                for callback in root.tk.splitlist(root.tk.call("after", "info")):
                    root.tk.call("after", "cancel", callback)
                root.destroy()

    @staticmethod
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from LauncherEnhancementsUiTests.descendants(child)

    def assert_control_fits(self, control, container) -> None:
        self.assertTrue(control.winfo_ismapped(), str(control))
        self.assertGreaterEqual(control.winfo_width() + 1, control.winfo_reqwidth(), str(control))
        self.assertGreaterEqual(control.winfo_height() + 1, control.winfo_reqheight(), str(control))
        self.assertGreaterEqual(control.winfo_rootx(), container.winfo_rootx(), str(control))
        self.assertGreaterEqual(control.winfo_rooty(), container.winfo_rooty(), str(control))
        self.assertLessEqual(
            control.winfo_rootx() + control.winfo_width(),
            container.winfo_rootx() + container.winfo_width(), str(control),
        )
        self.assertLessEqual(
            control.winfo_rooty() + control.winfo_height(),
            container.winfo_rooty() + container.winfo_height(), str(control),
        )

    def test_create_action_toolbar_control_keeps_its_callback_and_accessible_name(self):
        with self.launcher() as (app, *_):
            button = app.new_action_button
            expected_call = Mock()
            app._show_configuration = expected_call

            self.assertEqual(button.cget("text"), "Create Action")
            self.assertEqual(str(button.cget("compound")), "none")
            self.assertEqual(button.cget("style"), "ToolbarIcon.TButton")
            self.assertEqual(
                tuple(map(str, app.root.tk.splitlist(button.cget("image")))),
                (str(app.action_discovery_panel.ui_icons["create_action"]),),
            )
            self.assertTrue(button.cget("takefocus"))
            tooltips = {
                tooltip.widget: tooltip.text
                for tooltip in app.widget_tooltips
                if isinstance(tooltip.text, str)
            }
            self.assertTrue(tooltips[button].startswith("Create Action —"))

            button.invoke()

            expected_call.assert_called_once_with(
                initial_tab="actions",
                start_action_creation=True,
            )

    def test_direct_copy_drop_leaves_hidden_editor_selection_and_undo_untouched(self):
        with self.launcher(size="1100x700") as (app, _get, clear, append):
            panel = app.workspace_component
            panel.set_text("first state")
            panel.set_text("second state")
            panel.text.tag_add(tk.SEL, "1.0", "1.6")
            selected = tuple(map(str, panel.text.tag_ranges(tk.SEL)))
            history = list(panel._content_history)
            history_index = panel._content_history_index
            action = Action("drop-copy", "Copy dropped files", "General", "send_files_to_folder", "C:/Exports")
            app.actions = [action]
            app.palette_state = replace(app.palette_state, drop_settings=approve_drop_action(action))
            app._reload_if_changed = Mock()
            app.configuration_signature_cache = (("accepted", 1, 1),)
            app._configuration_signature = Mock(return_value=app.configuration_signature_cache)
            app._run_file_transfer_action = Mock(return_value="Preparing to copy files")
            app.root.withdraw()
            app.root.update()
            clear.reset_mock()
            append.reset_mock()
            with patch.object(panel, "apply_incoming_text", side_effect=AssertionError("No placement")), \
                    patch.object(app, "_get_clipboard_text", side_effect=AssertionError("No clipboard read")), \
                    patch("context_palette.launcher.execute_action", side_effect=execute_action):
                app._accept_drop_result(DropResult(items=(DropItem("path", "C:/Input/new.txt"),)))
            self.assertEqual(app.root.state(), "withdrawn")
            self.assertEqual(panel.raw_text(), "second state")
            self.assertEqual(tuple(map(str, panel.text.tag_ranges(tk.SEL))), selected)
            self.assertEqual(panel._content_history, history)
            self.assertEqual(panel._content_history_index, history_index)
            app._run_file_transfer_action.assert_called_once_with(action, "C:/Input/new.txt", dropped=True)
            clear.assert_not_called()
            append.assert_not_called()
            panel.text.edit_undo()
            self.assertEqual(panel.raw_text(), "first state")

    def test_hide_show_keeps_text_selection_history_undo_and_custom_sash(self):
        with self.launcher(size="1100x700") as (app, _get, clear, append):
            root = app.root
            panel = app.workspace_component
            editor = panel.text
            self.assertTrue(app.workspace_visible)
            self.assertTrue(editor.winfo_ismapped())
            self.assertTrue(app.workspace_visibility_var.get())
            panel.set_text("first state")
            panel.set_text("second state")
            root.update()
            editor.tag_add(tk.SEL, "1.0", "1.6")
            selected = tuple(map(str, editor.tag_ranges(tk.SEL)))
            history = list(panel._content_history)
            history_index = panel._content_history_index
            app.main_content.sashpos(0, 440)
            app._remember_main_split(None)
            sash = app.main_content.sashpos(0)

            app.workspace_visibility_button.invoke()
            root.update()
            self.assertFalse(app.workspace_visible)
            self.assertFalse(editor.winfo_ismapped())
            self.assertTrue(editor.winfo_exists())
            self.assertEqual(len(app.main_content.panes()), 1)
            self.assertIn("•", app.workspace_visibility_button.cget("text"))
            self.assertTrue(app.collapsed_workspace_status.winfo_ismapped())
            self.assertEqual(tuple(map(str, editor.tag_ranges(tk.SEL))), selected)
            self.assertEqual(panel._content_history, history)
            self.assertEqual(panel._content_history_index, history_index)

            app.workspace_visibility_button.invoke()
            root.update()
            self.assertIs(panel.text, editor)
            self.assertTrue(editor.winfo_ismapped())
            self.assertEqual(panel.raw_text(), "second state")
            self.assertEqual(tuple(map(str, editor.tag_ranges(tk.SEL))), selected)
            self.assertEqual(app.main_content.sashpos(0), sash)
            self.assertFalse(app.collapsed_workspace_status.winfo_ismapped())
            editor.edit_undo()
            root.update()
            self.assertEqual(panel.raw_text(), "first state")
            editor.edit_redo()
            root.update()
            self.assertEqual(panel.raw_text(), "second state")
            clear.assert_not_called()
            append.assert_not_called()

    def test_hidden_workspace_keeps_clipboard_sync_and_default_drop_reveals_it(self):
        with self.launcher() as (app, get, clear, append):
            app.workspace_visibility_button.invoke()
            app.show_window()
            app.root.update()
            self.assertFalse(app.workspace_visible)
            self.assertEqual(app.workspace_component.raw_text(), "Clipboard fixture")
            self.assertIn("•", app.workspace_visibility_button.cget("text"))
            get.assert_called_once_with()

            # Clear the fixture so no incoming-text choice dialog is required.
            app.workspace_component.set_text("")
            app.root.update()
            self.assertNotIn("•", app.workspace_visibility_button.cget("text"))
            get.reset_mock()
            app.captured_selection = "old selection"
            app._accept_drop_result(DropResult(items=(DropItem("text", "Dropped fixture"),)))
            app.root.update()
            self.assertTrue(app.workspace_visible)
            self.assertTrue(app.workspace_component.text.winfo_ismapped())
            self.assertEqual(app.workspace_component.raw_text(), "Dropped fixture")
            self.assertIsNone(app.captured_selection)
            get.assert_not_called()
            clear.assert_not_called()
            append.assert_not_called()

    def test_preview_button_selection_states_and_dialog_do_not_run(self):
        with self.launcher() as (app, _get, clear, append):
            root = app.root
            panel = app.workspace_component
            panel.set_text("Preserved input")
            app._update_preview()
            self.assertEqual(str(app.preview_button.cget("state")), "normal")
            with patch.object(app, "_execute_action") as execute, patch.object(app, "_open_work_item_target") as open_item:
                app.preview_button.invoke()
                root.update()
                window = app.execution_preview_window
                window.geometry("700x480+-32000+-32000")
                root.update()
                text = next(widget for widget in self.descendants(window) if isinstance(widget, tk.Text))
                self.assertIn("Sample result", text.get("1.0", "end-1c"))
                self.assertEqual(str(text.cget("state")), "disabled")
                close = next(widget for widget in self.descendants(window) if isinstance(widget, ttk.Button) and widget.cget("text") == "Close")
                self.assert_control_fits(close, window)
                self.assertFalse(any(isinstance(widget, ttk.Button) and widget.cget("text") in {"Run", "Open"} for widget in self.descendants(window)))
                close.invoke()
                self.assertFalse(window.winfo_exists())
                execute.assert_not_called()
                open_item.assert_not_called()

            app.focus_tree.selection_remove(*app.focus_tree.selection())
            app._update_preview()
            self.assertEqual(str(app.preview_button.cget("state")), "disabled")
            source = WorkItemSource("fixture", "Fixture source", app.actions_path.parent)
            item = DiscoveredWorkItem("fixture", source.name, "PRJ-TEST-sample", source.workitems_path / "PRJ-TEST-sample", "Sample Work Item", "PRJ", "Project", "TEST", "sample", (), None)
            app.work_item_sources = (source,)
            app.work_item_index = WorkItemIndex((SourceRefreshResult(source, (item,)),))
            app._select_discovery_scope("work_items")
            root.update()
            self.assertEqual(str(app.preview_button.cget("state")), "normal")
            with patch.object(app, "_execute_action") as execute, patch.object(app, "_open_work_item_target") as open_item:
                app.preview_button.invoke()
                root.update()
                window = app.execution_preview_window
                text = next(widget for widget in self.descendants(window) if isinstance(widget, tk.Text))
                self.assertIn(str(item.default_open_path), text.get("1.0", "end-1c"))
                execute.assert_not_called()
                open_item.assert_not_called()
            self.assertEqual(panel.raw_text(), "Preserved input")
            clear.assert_not_called()
            append.assert_not_called()

    def test_new_controls_fit_small_window_at_supported_scaling(self):
        for percentage, scaling in ((100, 4 / 3), (125, 5 / 3), (150, 2.0)):
            with self.subTest(percentage=percentage), self.launcher(scaling=scaling, size="700x480") as (app, *_):
                for control in (app.preview_button, app.run_button, app.workspace_visibility_button):
                    self.assert_control_fits(control, app.command_console)
                app.workspace_component.set_text("Hidden input")
                app.workspace_visibility_button.invoke()
                app.root.update()
                self.assert_control_fits(app.workspace_visibility_button, app.command_console)
                self.assert_control_fits(app.collapsed_workspace_status, app.command_console)

    def test_drop_settings_controls_fit_and_selection_explains_effect(self):
        for percentage, scaling in ((100, 4 / 3), (125, 5 / 3), (150, 2.0)):
            with self.subTest(percentage=percentage), self.launcher(scaling=scaling) as (app, *_):
                save = Mock()
                action = Action("upper", "Uppercase dropped text", "", "transform_text", "uppercase")
                unsupported = Action("password", "Protected credential", "", "paste_credential", "Fixture")
                dialog = DropConfigurationWindow(app.root, actions=(action, unsupported), settings=DropActionSettings(), on_save=save)
                dialog.window.geometry("700x480+-32000+-32000")
                app.root.update()
                self.assertEqual(dialog.mode_var.get(), "show")
                self.assertEqual(str(dialog.action_picker.choose_button.cget("state")), "disabled")
                dialog.action_radio.invoke()
                self.assertEqual(str(dialog.save_button.cget("state")), "disabled")
                dialog.action_var.set(next(iter(dialog.actions_by_label)))
                app.root.update()
                self.assertEqual(str(dialog.save_button.cget("state")), "normal")
                self.assertTrue(dialog.effect_var.get())
                for control in (dialog.show_radio, dialog.action_radio, dialog.action_picker.choose_button, dialog.save_button):
                    self.assert_control_fits(control, dialog.window)
                cancel = next(widget for widget in self.descendants(dialog.window) if isinstance(widget, ttk.Button) and widget.cget("text") == "Cancel")
                self.assert_control_fits(cancel, dialog.window)
                self.assertEqual(len(dialog.unavailable.get_children()), 1)
                cancel.invoke()
                save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
