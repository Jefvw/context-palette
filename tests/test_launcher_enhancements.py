from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.actions import Action, ActionError
from context_palette.drop_action import DropActionSettings, approve_drop_action
from context_palette.drop_adapter import DropResult, DropWarning
from context_palette.drop_extraction import DropItem
from context_palette.excel_automation import EXCEL_AUTOMATION_ID
from context_palette.launcher import LauncherApp
from context_palette.palette_state import PaletteState


class MemoryWorkspace:
    def __init__(self, value="", placement="replace"):
        self.value = value
        self.placement = placement
        self.text = Mock()
        self.show_file_preview = Mock()
        self.placements = []
        self.outputs = []

    def raw_text(self):
        return self.value

    def set_text(self, value):
        self.outputs.append(value)
        self.value = value

    def apply_incoming_text(self, value, *, source_label):
        self.placements.append(value)
        if self.placement == "append":
            self.value += ("" if self.value.endswith("\n") else "\n\n") + value
        elif self.placement == "replace":
            self.value = value
        return self.placement


class LauncherEnhancementTests(unittest.TestCase):
    def action(self, kind="transform_text", value="uppercase", **kwargs):
        return Action("drop-action", "Example", "General", kind, value, **kwargs)

    def app(self, action=None, *, value="old input", placement="replace"):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.status_var = Mock()
        app.workspace_component = MemoryWorkspace(value, placement)
        app.palette_state = PaletteState(
            drop_settings=approve_drop_action(action) if action else DropActionSettings()
        )
        app.actions = [action] if action else []
        app.source_foreground_handle = 123
        app.captured_selection = "unrelated selection"
        app._reveal_window = Mock(return_value=True)
        app._set_workspace_visible = Mock()
        app._reload_if_changed = Mock()
        app.configuration_signature_cache = (("accepted", 1, 1),)
        app._configuration_signature = Mock(return_value=app.configuration_signature_cache)
        app._get_clipboard_text = Mock(return_value="unrelated clipboard")
        app._set_clipboard = Mock()
        app._workspace_text = lambda: app.workspace_component.raw_text().strip()
        app._set_workspace_text = app.workspace_component.set_text
        app._ask_for_action_input = Mock()
        app._open_action_target = Mock()
        app._run_action_sequence = Mock()
        app._run_excel_automation = Mock(return_value="Export review opened")
        app._paste_credential = Mock()
        app._paste_saved_text_if_destination = Mock()
        app._show_execution_preview = Mock()
        app._selected_work_item = Mock(return_value=None)
        app._selected_action = Mock(return_value=action)
        return app

    def result(self, text="a b"):
        return DropResult(items=(DropItem("text", text),))

    def test_default_drop_reveals_input_without_execution_or_clipboard_capture(self):
        app = self.app()
        app._execute_action = Mock()
        app._accept_drop_result(self.result())
        self.assertEqual(app.workspace_component.value, "a b")
        app._set_workspace_visible.assert_called_once_with(True)
        self.assertFalse(app._reveal_window.call_args.kwargs["sync_workspace"])
        self.assertIsNone(app.captured_selection)
        self.assertIsNone(app.source_foreground_handle)
        app._execute_action.assert_not_called()
        app._get_clipboard_text.assert_not_called()

    def test_drop_transform_runs_directly_and_only_then_publishes_output(self):
        app = self.app(self.action(), placement="append")
        def check_input_is_not_staged(_value):
            self.assertEqual(app.workspace_component.value, "old input")
            app._reveal_window.assert_not_called()
        app._set_clipboard.side_effect = check_input_is_not_staged
        app._accept_drop_result(self.result(" a b "))
        self.assertEqual(app.workspace_component.value, " A B ")
        self.assertEqual(app.workspace_component.placements, [])
        self.assertEqual(app.workspace_component.outputs, [" A B "])
        app._set_workspace_visible.assert_called_once_with(True)
        app._set_clipboard.assert_called_once_with(" A B ")
        app._get_clipboard_text.assert_not_called()
        app._open_action_target.assert_not_called()

    def test_template_drop_uses_snapshot_not_clipboard_or_appended_input(self):
        app = self.app(self.action("workspace_template", "Answer: %CLIPBOARD%"), placement="append")
        app._accept_drop_result(self.result("fresh"))
        self.assertEqual(app.workspace_component.value, "Answer: fresh")
        self.assertEqual(app.workspace_component.placements, [])
        app._set_clipboard.assert_called_once_with("Answer: fresh")
        app._get_clipboard_text.assert_not_called()

    def test_url_drop_opens_only_snapshot_url(self):
        app = self.app(self.action("build_url_selection_open", "https://example.com/{id_url}"))
        app._accept_drop_result(self.result("a b"))
        app._open_action_target.assert_called_once()
        self.assertEqual(app._open_action_target.call_args.args[0].value, "https://example.com/a%20b")
        self.assertEqual(app.workspace_component.value, "old input")
        self.assertEqual(app.workspace_component.placements, [])
        app._reveal_window.assert_not_called()
        app._set_clipboard.assert_called_once_with("https://example.com/a%20b")
        app._get_clipboard_text.assert_not_called()

    def test_copy_drop_bypasses_editor_even_when_placement_would_cancel(self):
        app = self.app(self.action("send_files_to_folder", "C:/Exports"), placement="append")
        app.workspace_component.apply_incoming_text = Mock(side_effect=AssertionError("No placement dialog"))
        app.workspace_component.raw_text = Mock(side_effect=AssertionError("Do not read Input / Output"))
        app._workspace_text = Mock(side_effect=AssertionError("Do not acquire ambient input"))
        app._run_file_transfer_action = Mock(return_value="Preparing to copy files")
        app._accept_drop_result(self.result("C:/Input/new.xlsx"))
        args, kwargs = app._run_file_transfer_action.call_args
        self.assertEqual(args[0].value, "C:/Exports")
        self.assertEqual(args[1], "C:/Input/new.xlsx")
        self.assertEqual(kwargs, {"dropped": True})
        self.assertEqual(app.workspace_component.value, "old input")
        self.assertEqual(app.workspace_component.outputs, [])
        app._reveal_window.assert_not_called()
        app._set_workspace_visible.assert_not_called()
        app._get_clipboard_text.assert_not_called()
        app._set_clipboard.assert_not_called()

    def test_excel_drop_retains_attended_flow_with_exact_dropped_paths(self):
        app = self.app(self.action("excel_automation", EXCEL_AUTOMATION_ID), placement="append")
        app._accept_drop_result(self.result("C:\\work\\one.xlsx"))
        app._run_excel_automation.assert_called_once_with(
            app.actions[0], workspace_snapshot="C:\\work\\one.xlsx"
        )
        self.assertEqual(app.workspace_component.value, "old input")
        self.assertEqual(app.workspace_component.placements, [])
        app._reveal_window.assert_not_called()
        app._set_clipboard.assert_not_called()

    def test_cancel_never_runs(self):
        app = self.app(placement=None)
        app._execute_action = Mock()
        app._accept_drop_result(self.result())
        self.assertEqual(app.workspace_component.value, "old input")
        app._execute_action.assert_not_called()

    def test_action_changed_before_direct_dispatch_is_rechecked(self):
        app = self.app(self.action())
        app._reload_if_changed.side_effect = lambda: setattr(app, "actions", [])
        app._execute_action = Mock()
        app._accept_drop_result(self.result())
        app._reload_if_changed.assert_called_once()
        app._execute_action.assert_not_called()
        self.assertEqual(app.workspace_component.value, "old input")
        self.assertEqual(app.workspace_component.placements, [])

    def test_new_excel_drop_does_not_close_or_retarget_existing_review(self):
        app = self.app(self.action("excel_automation", EXCEL_AUTOMATION_ID))
        app.excel_automation_window = Mock(busy=False)
        with self.assertRaisesRegex(ActionError, "existing review was not changed"):
            LauncherApp._run_excel_automation(
                app, app.actions[0], workspace_snapshot="C:\\work\\two.xlsx"
            )
        app.excel_automation_window.show.assert_called_once()
        app.excel_automation_window.close.assert_not_called()

    def test_failed_action_does_not_publish_partial_output_or_retry(self):
        app = self.app(self.action(), placement="append")
        app._set_clipboard.side_effect = ActionError("Clipboard unavailable")
        with patch("context_palette.launcher.messagebox.showerror") as error:
            app._accept_drop_result(self.result("fresh"))
        error.assert_called_once()
        self.assertEqual(app.workspace_component.value, "old input")
        self.assertEqual(app.workspace_component.outputs, [])
        self.assertEqual(app.workspace_component.placements, [])
        self.assertEqual(app._set_clipboard.call_count, 1)
        self.assertIn("kept in Drop history", app.status_var.set.call_args.args[0])

    def test_changed_missing_and_failed_reload_actions_preserve_editor_and_do_not_run(self):
        for failure in ("changed", "missing", "reload"):
            with self.subTest(failure=failure):
                app = self.app(self.action())
                if failure == "changed":
                    app.actions = [replace(app.actions[0], value="lowercase")]
                elif failure == "missing":
                    app.actions = []
                else:
                    app.configuration_failed_signature_cache = ("bad-file",)
                app._execute_action = Mock()
                app._accept_drop_result(self.result("fresh"))
                self.assertEqual(app.workspace_component.value, "old input")
                self.assertEqual(app.workspace_component.placements, [])
                app._execute_action.assert_not_called()
                self.assertIn("no Action ran", app.status_var.set.call_args.args[0])
                if failure in {"changed", "missing"}:
                    app.drop_target_window = Mock()
                    app._refresh_drop_behavior_label()
                    app.drop_target_window.set_behavior_label.assert_called_once_with(
                        "Action blocked — review Settings"
                    )

    def test_shortcut_warnings_stop_automatic_execution(self):
        app = self.app(self.action())
        app._execute_action = Mock()
        result = replace(self.result(), warnings=(DropWarning("shortcut", "Could not resolve"),))
        app._accept_drop_result(result)
        app._execute_action.assert_not_called()
        self.assertIn("warnings", app.status_var.set.call_args.args[0])

    def test_changing_configuration_refuses_old_authority_without_failed_cache(self):
        app = self.app(self.action())
        # A changed-during-reload failure deliberately clears the failed cache
        # so the next ordinary reload can retry. It does not publish new state.
        app.configuration_failed_signature_cache = None
        app._configuration_signature.return_value = (("changed-during-reload", 2, 2),)
        app._execute_action = Mock()
        app._accept_drop_result(self.result())
        app._execute_action.assert_not_called()
        self.assertEqual(app.workspace_component.value, "old input")
        self.assertIn("no Action ran", app.status_var.set.call_args.args[0])

    def test_history_resend_does_not_repeat_automatic_effect(self):
        app = self.app(self.action())
        app._execute_action = Mock()
        app._show_drop_result(self.result())
        self.assertEqual(app.workspace_component.value, "a b")
        app._execute_action.assert_not_called()

    def test_history_resend_keeps_append_and_cancel_choices(self):
        for placement, expected in (("append", "old input\n\na b"), (None, "old input")):
            with self.subTest(placement=placement):
                app = self.app(self.action(), placement=placement)
                app._execute_action = Mock()
                app._show_drop_result(self.result())
                self.assertEqual(app.workspace_component.value, expected)
                self.assertEqual(app.workspace_component.placements, ["a b"])
                app._execute_action.assert_not_called()

    def test_fresh_show_setting_returns_to_normal_placement(self):
        app = self.app(self.action())
        app._reload_if_changed.side_effect = lambda: setattr(app, "palette_state", PaletteState())
        app._execute_action = Mock()
        app._accept_drop_result(self.result())
        self.assertEqual(app.workspace_component.value, "a b")
        self.assertEqual(app.workspace_component.placements, ["a b"])
        app._execute_action.assert_not_called()

    def test_invalid_drop_never_enters_direct_dispatch(self):
        app = self.app(self.action())
        app._execute_action = Mock()
        app._accept_drop_result(DropResult())
        app._execute_action.assert_not_called()
        app._reload_if_changed.assert_not_called()
        self.assertEqual(app.workspace_component.value, "old input")

    def test_preview_transform_does_not_execute_copy_or_consume_capture(self):
        app = self.app(self.action(), value="preview this")
        app._execute_action = Mock()
        app._preview_selected()
        self.assertIn("PREVIEW THIS", app._show_execution_preview.call_args.args[1].full_text())
        self.assertEqual(app.workspace_component.value, "preview this")
        self.assertEqual(app.source_foreground_handle, 123)
        self.assertEqual(app.captured_selection, "unrelated selection")
        app._execute_action.assert_not_called()
        app._get_clipboard_text.assert_not_called()
        app._set_clipboard.assert_not_called()
        app._open_action_target.assert_not_called()

    def test_preview_template_reads_real_source_without_changing_it(self):
        app = self.app(self.action("workspace_template", "From %CLIPBOARD%"))
        app._preview_selected()
        self.assertIn("From unrelated clipboard", app._show_execution_preview.call_args.args[1].full_text())
        app._get_clipboard_text.assert_called_once()
        app._set_clipboard.assert_not_called()
        self.assertEqual(app.workspace_component.value, "old input")

    def test_preview_literal_transform_token_does_not_read_clipboard(self):
        app = self.app(self.action("transform_text", "literal_replace",
                                   arguments=("%CLIPBOARD%", "replaced")), value="%CLIPBOARD%")
        app._preview_selected()
        app._get_clipboard_text.assert_not_called()
        self.assertIn("replaced", app._show_execution_preview.call_args.args[1].full_text())

    def test_preview_does_not_read_protected_clipboard_or_credentials(self):
        for action in (self.action("workspace_template", "%CLIPBOARD%"), self.action("paste_credential", "ContextPalette:Example")):
            with self.subTest(kind=action.type):
                app = self.app()
                app.actions = [action]
                app._selected_action.return_value = action
                app.protected_clipboard_sequence = 44
                app._preview_selected()
                app._get_clipboard_text.assert_not_called()
                app._paste_credential.assert_not_called()
                app._set_clipboard.assert_not_called()

    def test_context_filter_preserves_drop_approval(self):
        app = self.app(self.action())
        approved = app.palette_state.drop_settings
        app.item_context_filter = "Development"
        app._sync_slot_context_to_filter()
        self.assertEqual(app.palette_state.focus_context, "Development")
        self.assertEqual(app.palette_state.drop_settings, approved)

    def test_saving_drop_preference_merges_fresh_slots_and_rejects_changed_action(self):
        app = self.app(self.action())
        app.palette_path = Path("palette.json")
        app.actions_path = Path("actions.json")
        app.local_actions_path = Path("local_actions.json")
        app._refresh_drop_behavior_label = Mock()
        fresh = PaletteState(context_slots={"General": ("new-slot",)})
        with patch("context_palette.launcher.load_palette_state", return_value=fresh), patch(
            "context_palette.launcher.load_combined_actions", return_value=(app.actions, set())
        ) as load, patch("context_palette.launcher.save_palette_state") as save:
            app._save_drop_settings(app.palette_state.drop_settings)
            self.assertEqual(save.call_args.args[1].context_slots, fresh.context_slots)
            self.assertEqual(save.call_args.args[1].drop_settings, app.palette_state.drop_settings)
            load.return_value = ([replace(app.actions[0], value="lowercase")], set())
            with self.assertRaises(ActionError):
                app._save_drop_settings(app.palette_state.drop_settings)
            self.assertEqual(save.call_count, 1)

    def test_recovery_required_blocks_saving_open_drop_settings_dialog(self):
        app = self.app()
        app._configuration_recovery_required = True
        with patch("context_palette.launcher.save_palette_state") as save:
            with self.assertRaises(ActionError):
                app._save_drop_settings(DropActionSettings())
            save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
