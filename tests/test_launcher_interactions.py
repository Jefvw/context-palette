from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.actions import Action, ActionError
from context_palette.command_surface import CommandItem
from context_palette.contexts import ContextDefinition, ContextError
from context_palette.launcher import (
    LauncherApp,
    bounded_sash_position,
    frequent_credential_actions,
)
from context_palette.palette_state import PaletteState
from context_palette.windows_credentials import CredentialSecret


class FakeVariable:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class FakeButton:
    def __init__(self) -> None:
        self.options: dict[str, str] = {}

    def configure(self, **options: str) -> None:
        self.options.update(options)


class FakeRoot:
    def __init__(self) -> None:
        self.withdraw_calls = 0
        self.after_callbacks: list[object] = []

    def withdraw(self) -> None:
        self.withdraw_calls += 1

    def after(self, _delay: int, callback: object) -> None:
        self.after_callbacks.append(callback)


class LauncherInteractionTests(unittest.TestCase):
    def test_sash_position_protects_both_panes_from_extreme_ratios(self):
        self.assertEqual(bounded_sash_position(800, 0.0, 220, 320), 220)
        self.assertEqual(bounded_sash_position(800, 1.0, 220, 320), 480)
        self.assertEqual(bounded_sash_position(800, 0.33, 220, 320), 264)

    def test_sash_position_scales_minimums_when_window_is_too_small(self):
        self.assertEqual(bounded_sash_position(200, 0.9, 140, 140), 100)

    def test_frequent_credentials_prioritize_trusted_pins_and_limit_to_four(self):
        actions = [
            Action("one", "One", "General", "paste_credential", "one", "Trusted"),
            Action("two", "Two", "General", "paste_credential", "two", "Trusted"),
            Action("draft", "Draft", "General", "paste_credential", "draft", "Draft"),
            Action("copy", "Copy", "General", "copy_text", "text", "Trusted"),
            Action("three", "Three", "General", "paste_credential", "three", "Trusted"),
            Action("four", "Four", "General", "paste_credential", "four", "Trusted"),
            Action("five", "Five", "General", "paste_credential", "five", "Trusted"),
        ]

        selected = frequent_credential_actions(actions, ("three", "two", "draft"))

        self.assertEqual([action.id for action in selected], ["three", "two", "one", "four"])

    def test_password_button_toggles_exact_credential_action_filter(self):
        app = LauncherApp.__new__(LauncherApp)
        app.action_type_filter = None
        app.passwords_button = FakeButton()
        app.action_type_filter_var = FakeVariable()
        app.status_var = FakeVariable()
        refreshes: list[bool] = []
        app._refresh_results = lambda: refreshes.append(True)

        app._toggle_password_actions()

        self.assertEqual(app.action_type_filter, "paste_credential")
        self.assertEqual(app.action_type_filter_var.value, "Paste a Windows credential")
        self.assertEqual(app.passwords_button.options["style"], "Accent.TButton")

        app._toggle_password_actions()

        self.assertIsNone(app.action_type_filter)
        self.assertEqual(app.action_type_filter_var.value, "All types")
        self.assertEqual(app.passwords_button.options["style"], "Compact.TButton")
        self.assertEqual(refreshes, [True, True])

    def test_any_action_type_can_be_selected_as_a_filter(self):
        app = LauncherApp.__new__(LauncherApp)
        app.action_type_filter = None
        app.passwords_button = FakeButton()
        app.action_type_filter_var = FakeVariable()
        refreshes: list[bool] = []
        app._refresh_results = lambda: refreshes.append(True)

        app._select_action_type_filter("open_url")

        self.assertEqual(app.action_type_filter, "open_url")
        self.assertEqual(app.action_type_filter_var.value, "Open a website")
        self.assertEqual(app.passwords_button.options["style"], "Compact.TButton")
        self.assertEqual(refreshes, [True])

    def test_protected_clipboard_is_never_synchronized_into_workspace(self):
        app = LauncherApp.__new__(LauncherApp)
        synchronizations: list[bool] = []
        app._sync_workspace_from_clipboard = lambda: synchronizations.append(True)
        app.protected_clipboard_sequence = 42

        app._sync_workspace_from_clipboard_if_safe()
        self.assertEqual(synchronizations, [])

        app.protected_clipboard_sequence = None
        app._sync_workspace_from_clipboard_if_safe()
        self.assertEqual(synchronizations, [True])

    def test_failed_ordinary_clipboard_write_keeps_protected_marker(self):
        app = LauncherApp.__new__(LauncherApp)
        app.protected_clipboard_sequence = 42
        root = Mock()
        root.clipboard_clear.side_effect = RuntimeError("clipboard busy")
        app.root = root

        with self.assertRaisesRegex(RuntimeError, "clipboard busy"):
            app._set_clipboard("ordinary text")

        self.assertEqual(app.protected_clipboard_sequence, 42)

    def test_external_show_invalidates_captured_credential_destination(self):
        app = LauncherApp.__new__(LauncherApp)
        app.source_foreground_handle = 123
        app.show_window = lambda: None

        app._handle_external_request({"command": "show"})

        self.assertIsNone(app.source_foreground_handle)

    def test_credential_paste_confirms_destination_and_clears_conditionally(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = FakeRoot()
        app.source_foreground_handle = 123
        app.protected_clipboard_sequence = None
        action = Action(
            "credential",
            "Paste login",
            "General",
            "paste_credential",
            "ContextPalette/example-login",
            "Trusted",
        )

        with (
            patch("context_palette.launcher.window_title", return_value="Sign in") as title,
            patch("context_palette.launcher.messagebox.askyesno", return_value=True) as confirm,
            patch(
                "context_palette.launcher.read_windows_credential",
                return_value=CredentialSecret("user", "do-not-show"),
            ),
            patch("context_palette.launcher.set_protected_clipboard_text", return_value=42),
            patch("context_palette.launcher.focus_window", return_value=True),
            patch("context_palette.launcher.send_paste_shortcut") as paste,
            patch(
                "context_palette.launcher.clear_clipboard_if_unchanged",
                return_value=True,
            ) as clear,
        ):
            result = app._paste_credential_action(action)
            first_callback = app.root.after_callbacks.pop(0)
            first_callback()
            clear_callback = app.root.after_callbacks.pop(0)
            clear_callback()

        title.assert_called_once_with(123)
        self.assertNotIn("do-not-show", confirm.call_args.args[1])
        self.assertIn("Sign in", confirm.call_args.args[1])
        self.assertEqual(app.root.withdraw_calls, 1)
        self.assertIsNone(app.source_foreground_handle)
        paste.assert_called_once()
        clear.assert_called_once_with(42)
        self.assertIsNone(app.protected_clipboard_sequence)
        self.assertIn("approved", result)

    def test_credential_paste_requires_fresh_hotkey_destination(self):
        app = LauncherApp.__new__(LauncherApp)
        app.source_foreground_handle = None
        action = Action(
            "credential",
            "Paste login",
            "General",
            "paste_credential",
            "ContextPalette/example-login",
            "Trusted",
        )

        with self.assertRaisesRegex(ActionError, "F9"):
            app._paste_credential_action(action)

    def test_successful_focus_change_persists_before_applying_and_refreshes(self):
        previous = PaletteState(("existing",), "General", {})
        app = LauncherApp.__new__(LauncherApp)
        app.palette_state = previous
        app.context_var = FakeVariable()
        app.context_var.set("Developing")
        app.context_definitions = []
        app.status_var = FakeVariable()
        app.palette_path = Path("palette.json")
        app._configuration_signature = lambda: (("palette.json", 1, 1),)
        refreshes: list[bool] = []
        app._refresh_results = lambda: refreshes.append(True)
        saved_states: list[PaletteState] = []

        def save(_path: Path, state: PaletteState) -> None:
            self.assertIs(app.palette_state, previous)
            saved_states.append(state)

        with patch("context_palette.launcher.save_palette_state", side_effect=save):
            app._change_focus_context()

        self.assertEqual(saved_states[0].focus_context, "Developing")
        self.assertIs(app.palette_state, saved_states[0])
        self.assertEqual(refreshes, [True])
        self.assertEqual(app.status_var.value, "Focus context: Developing")

    def test_successful_pin_change_persists_before_applying_and_refreshes(self):
        previous = PaletteState(("existing",), "General", {})
        action = Action("new", "New action", "General", "copy_text", "Hello")
        app = LauncherApp.__new__(LauncherApp)
        app.palette_state = previous
        app.status_var = FakeVariable()
        app.palette_path = Path("palette.json")
        app._selected_action = lambda: action
        app._configuration_signature = lambda: (("palette.json", 1, 1),)
        refreshes: list[bool] = []
        surface_refreshes: list[bool] = []
        app._refresh_results = lambda: refreshes.append(True)
        app._render_command_surface = lambda: surface_refreshes.append(True)
        saved_states: list[PaletteState] = []

        def save(_path: Path, state: PaletteState) -> None:
            self.assertIs(app.palette_state, previous)
            saved_states.append(state)

        with patch("context_palette.launcher.save_palette_state", side_effect=save):
            app._toggle_selected_pin()

        self.assertEqual(saved_states[0].pinned_action_ids, ("existing", "new"))
        self.assertIs(app.palette_state, saved_states[0])
        self.assertEqual(refreshes, [True])
        self.assertEqual(surface_refreshes, [True])
        self.assertIn("Pinned:", app.status_var.value)

    def test_failed_context_reload_preserves_last_known_good_contexts(self):
        app = LauncherApp.__new__(LauncherApp)
        existing = ContextDefinition("General", "Existing context")
        app.context_definitions = [existing]
        app.contexts_path = Path("contexts.json")
        app.local_contexts_path = Path("local_contexts.json")
        app.status_var = FakeVariable()
        app.root = object()

        with (
            patch(
                "context_palette.launcher.load_combined_contexts",
                side_effect=ContextError("invalid context file"),
            ),
            patch("context_palette.launcher.messagebox.showerror") as showerror,
        ):
            app._load_contexts()

        self.assertEqual(app.context_definitions, [existing])
        self.assertIn("kept 1 previous context", app.status_var.value)
        showerror.assert_called_once()

    def test_failed_focus_save_restores_previous_context(self):
        app = LauncherApp.__new__(LauncherApp)
        app.palette_state = PaletteState(("existing",), "General", {})
        app.context_var = FakeVariable()
        app.context_var.set("Developing")
        app.status_var = FakeVariable()
        app.palette_path = Path("palette.json")

        with (
            patch(
                "context_palette.launcher.save_palette_state",
                side_effect=OSError("file is locked"),
            ),
            patch("context_palette.launcher.messagebox.showerror") as showerror,
        ):
            app._change_focus_context()

        self.assertEqual(app.palette_state.focus_context, "General")
        self.assertEqual(app.context_var.value, "General")
        self.assertIn("not changed", app.status_var.value)
        showerror.assert_called_once()

    def test_failed_pin_save_preserves_previous_pins(self):
        action = Action("new", "New action", "General", "copy_text", "Hello")
        app = LauncherApp.__new__(LauncherApp)
        app.palette_state = PaletteState(("existing",), "General", {})
        app.status_var = FakeVariable()
        app.palette_path = Path("palette.json")
        app._selected_action = lambda: action

        with (
            patch(
                "context_palette.launcher.save_palette_state",
                side_effect=OSError("file is locked"),
            ),
            patch("context_palette.launcher.messagebox.showerror") as showerror,
        ):
            app._toggle_selected_pin()

        self.assertEqual(app.palette_state.pinned_action_ids, ("existing",))
        self.assertIn("not changed", app.status_var.value)
        showerror.assert_called_once()

    def test_failed_action_reload_preserves_last_known_good_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            app = LauncherApp.__new__(LauncherApp)
            existing = Action(
                id="existing",
                title="Existing action",
                context="General",
                type="copy_text",
                value="Hello",
            )
            app.actions = [existing]
            app.local_action_ids = {"existing"}
            app.actions_path = Path(directory) / "actions.json"
            app.actions_path.write_text("not json", encoding="utf-8")
            app.local_actions_path = Path(directory) / "local_actions.json"
            app.status_var = FakeVariable()
            app.root = object()

            with patch("context_palette.launcher.messagebox.showerror"):
                app._load_actions()

            self.assertEqual(app.actions, [existing])
            self.assertEqual(app.local_action_ids, {"existing"})
            self.assertIn("could not be loaded", app.status_var.value)

    def test_successful_action_reload_replaces_previous_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            app = LauncherApp.__new__(LauncherApp)
            app.actions = [
                Action("old", "Old action", "General", "copy_text", "Old")
            ]
            app.local_action_ids = {"old"}
            app.actions_path = Path(directory) / "actions.json"
            app.actions_path.write_text(
                json.dumps(
                    {
                        "actions": [
                            {
                                "id": "new",
                                "title": "New action",
                                "context": "General",
                                "type": "copy_text",
                                "value": "New",
                                "state": "Draft",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            app.local_actions_path = Path(directory) / "local_actions.json"
            app.status_var = FakeVariable()

            app._load_actions()

            self.assertEqual([action.id for action in app.actions], ["new"])
            self.assertEqual(app.local_action_ids, set())
            self.assertEqual(app.status_var.value, "Loaded 1 actions")

    def test_keyboard_quick_action_runs_primary_action(self):
        app = LauncherApp.__new__(LauncherApp)
        action = Action(
            id="open-docs",
            title="Open documentation",
            context="Developing",
            type="open_url",
            value="https://docs.python.org/",
        )
        app.actions = [action]
        executed: list[Action] = []
        app._execute_action = executed.append
        app.status_var = FakeVariable()

        result = app._execute_item_primary(
            CommandItem(
                id="docs",
                label="Docs",
                primary_action_id="open-docs",
                action_ids=("open-docs",),
            )
        )

        self.assertEqual(result, "break")
        self.assertEqual(executed, [action])

    def test_keyboard_quick_action_explains_missing_assignment(self):
        app = LauncherApp.__new__(LauncherApp)
        app.actions = []
        app.status_var = FakeVariable()

        app._execute_item_primary(CommandItem(id="empty", label="Empty"))

        self.assertIn("no available action", app.status_var.value)


if __name__ == "__main__":
    unittest.main()
