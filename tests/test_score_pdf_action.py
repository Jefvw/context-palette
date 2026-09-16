from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from context_palette.actions import (
    ActionError, configured_action, execute_action, load_actions, append_action,
)
from context_palette.action_preview import build_action_preview, build_execution_preview
from context_palette.action_sequences import ALLOWED_ACTION_TYPES
from context_palette.action_bulk import EXCLUDED_BULK_TYPES
from context_palette.action_update_workbook import ELIGIBLE_ACTION_TYPES
from context_palette.configuration_window import ActionDialog
from context_palette.drop_action import drop_action_eligibility
from context_palette.launcher import LauncherApp
from context_palette.palette_items import PaletteItemReference


class ScoreActionTests(unittest.TestCase):
    def action(self, **changes):
        fields = dict(title="Save current score as PDF", context="General", action_type="save_edge_score_pdf", value="C:/Music/Scores")
        fields.update(changes)
        return configured_action(**fields)

    def test_literal_folder_accepts_unavailable_drive_and_unc_without_probing(self):
        for value in ("Z:/Offline Scores", r"\\server\share\Scores", "C:/Music/Été"):
            with self.subTest(value=value), patch.object(Path, "exists", side_effect=AssertionError("No probe")):
                self.assertEqual(self.action(value=value).value, value)

    def test_invalid_folder_and_execution_configuration_are_rejected(self):
        for value in ("", "relative", "C:relative", "https://example.test", "C:/%CLIPBOARD%", "C:/x\nscore", "C:/x:stream", r"\\?\C:\Scores", "C:/Music/../Scores"):
            with self.subTest(value=value), self.assertRaises(ActionError):
                self.action(value=value)
        for changes in (dict(arguments=("--print",)), dict(working_directory="C:/Music")):
            with self.subTest(changes=changes), self.assertRaises(ActionError):
                self.action(**changes)

    def test_save_load_round_trip_is_data_only_and_retains_the_exact_folder(self):
        action = self.action()
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "actions.json"
            append_action(path, action)
            self.assertEqual(load_actions(path), [action])

    def test_runner_is_required_and_is_the_only_execution_effect(self):
        action = self.action()
        forbidden = Mock(side_effect=AssertionError("Unexpected input/effect"))
        runner = Mock(return_value="Saving…")
        self.assertEqual(execute_action(action, edge_score_pdf_runner=runner,
            clipboard_getter=forbidden, clipboard_setter=forbidden,
            output_setter=forbidden, opener=forbidden, input_provider=forbidden), "Saving…")
        runner.assert_called_once_with(action)
        forbidden.assert_not_called()
        with self.assertRaises(ActionError):
            execute_action(action)
        with self.assertRaises(ActionError):
            execute_action(replace(action, arguments=("bad",)), edge_score_pdf_runner=runner)
        self.assertEqual(runner.call_count, 1)

    def test_preview_explains_browser_and_folder_without_external_access(self):
        with patch.object(Path, "exists", side_effect=AssertionError("No filesystem access")):
            preview = build_execution_preview(self.action(), workspace_text="unrelated", destination_available=True)
        self.assertEqual(preview.resolved_target, "C:/Music/Scores")
        self.assertIsNone(preview.input_value)
        self.assertIsNone(preview.output_text)
        self.assertIn("Edge", preview.input_source)
        self.assertIn("Official score or Guitar Pro tab", preview.full_text())
        self.assertIn("Existing PDFs", preview.recovery_text)
        self.assertNotIn("unrelated", preview.full_text())
        missing = build_action_preview(self.action(), destination_available=False)
        self.assertIn("F9", missing.input_text)

    def test_manual_only_but_data_exchange_is_available(self):
        action = self.action()
        self.assertFalse(drop_action_eligibility(action).eligible)
        self.assertNotIn(action.type, ALLOWED_ACTION_TYPES)
        self.assertNotIn(action.type, EXCLUDED_BULK_TYPES)
        self.assertIn(action.type, ELIGIBLE_ACTION_TYPES)

    def test_reserved_music_slot_uses_normal_action_route_and_requires_find_focus(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.search_entry = Mock()
        app.root.focus_get.return_value = app.search_entry
        app.slot_items = {6: PaletteItemReference(action_id=self.action().id)}
        app._execute_palette_item = Mock()
        event = SimpleNamespace(keysym="asciicircum", char="^", keycode=54, state=1, widget=app.search_entry)
        self.assertEqual(app._handle_keypress(event), "break")
        app._execute_palette_item.assert_called_once_with(app.slot_items[6])
        app.root.focus_get.return_value = Mock()
        app._handle_keypress(event)
        self.assertEqual(app._execute_palette_item.call_count, 1)

    def test_folder_editor_chooses_and_saves_without_starting_a_workflow(self):
        root = tk.Tk()
        root.withdraw()
        saved = []
        dialog = None
        try:
            dialog = ActionDialog(root, "save_edge_score_pdf", [], lambda action: saved.append(action) or True,
                initial_title="Save current score as PDF", initial_value="C:/Music/Scores")
            with patch("context_palette.configuration_window.filedialog.askdirectory", return_value="D:/Scores"):
                dialog.score_pdf_folder_button.invoke()
            self.assertEqual(dialog.score_pdf_folder_var.get(), "D:/Scores")
            dialog._save()
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].value, "D:/Scores")
            self.assertFalse(saved[0].arguments)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
