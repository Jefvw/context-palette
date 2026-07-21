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
from context_palette.work_items import DiscoveredWorkItem


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


class FakeKeyEvent:
    def __init__(
        self,
        state: int = 0,
        *,
        keysym: str = "",
        keycode: int = 0,
        char: str = "",
        widget: object | None = None,
    ) -> None:
        self.state = state
        self.keysym = keysym
        self.keycode = keycode
        self.char = char
        self.widget = widget


class LauncherInteractionTests(unittest.TestCase):
    def test_markdown_file_action_opens_in_document_viewer(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        with tempfile.TemporaryDirectory() as temporary:
            document = Path(temporary) / "guide.md"
            document.write_text("# Guide", encoding="utf-8")
            action = Action("guide", "Open guide", "General", "open_file", str(document))

            with patch("context_palette.launcher.HelpWindow") as viewer:
                app._open_action_target(action)

            viewer.assert_called_once_with(app.root, document, title="Guide")

    def test_non_markdown_file_action_keeps_standard_opener(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        action = Action("text", "Open text", "General", "open_file", "C:/guide.txt")

        with patch("context_palette.launcher.open_action_target") as opener:
            app._open_action_target(action)

        opener.assert_called_once_with(action)

    def test_missing_work_item_folder_keeps_folder_target_semantics(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.status_var = FakeVariable()
        missing_folder = Path("C:/missing/workitems/ISS-CAP40-example")
        item = DiscoveredWorkItem(
            source_id="cap40",
            source_name="CAP40",
            relative_folder="ISS-CAP40-example",
            folder_path=missing_folder,
            display_name="ISS-CAP40-example",
            kind_code="ISS",
            kind_name="Issue",
            organisation="CAP40",
            subject="example",
            project_codes=(),
            matching_workbook_path=None,
        )

        with patch("context_palette.launcher.open_action_target") as open_target:
            opened = app._open_work_item_target(item, missing_folder)

        self.assertTrue(opened)
        self.assertEqual(open_target.call_args.args[0].type, "open_folder")

    def test_shift_number_executes_slot_for_azerty_find_input(self):
        app = LauncherApp.__new__(LauncherApp)
        app.search_entry = object()
        app.root = Mock()
        app.root.focus_get.return_value = app.search_entry
        app._execute_slot = Mock(return_value="break")
        event = FakeKeyEvent(state=0x0001, keysym="2", keycode=50)

        self.assertEqual(app._handle_keypress(event), "break")
        app._execute_slot.assert_called_once_with(2, event)

    def test_shift_azerty_key_names_execute_slots_without_assumed_keycodes(self):
        app = LauncherApp.__new__(LauncherApp)
        app.search_entry = object()
        app.root = Mock()
        app.root.focus_get.return_value = app.search_entry
        app._execute_slot = Mock(return_value="break")

        for keysym, expected_slot in (
            ("ampersand", 1),
            ("eacute", 2),
            ("quotedbl", 3),
            ("apostrophe", 4),
            ("parenleft", 5),
            ("minus", 6),
            ("egrave", 7),
            ("underscore", 8),
            ("ccedilla", 9),
        ):
            event = FakeKeyEvent(state=0x0001, keysym=keysym)
            with self.subTest(keysym=keysym):
                self.assertEqual(app._handle_keypress(event), "break")
                app._execute_slot.assert_called_with(expected_slot, event)

    def test_plain_number_and_numpad_remain_find_input(self):
        app = LauncherApp.__new__(LauncherApp)
        app._execute_slot = Mock(return_value="break")

        for event in (
            FakeKeyEvent(state=0, keysym="2", keycode=50),
            FakeKeyEvent(state=0, keysym="2", keycode=98),
        ):
            with self.subTest(keycode=event.keycode):
                self.assertIsNone(app._handle_keypress(event))

        app._execute_slot.assert_not_called()

    def test_control_number_does_not_execute_an_action_slot(self):
        app = LauncherApp.__new__(LauncherApp)
        app._execute_slot = Mock(return_value="break")

        result = app._handle_keypress(
            FakeKeyEvent(state=0x0004, keysym="2", keycode=50),
        )

        self.assertIsNone(result)
        app._execute_slot.assert_not_called()

    def test_main_palette_hides_only_for_plain_escape(self):
        app = LauncherApp.__new__(LauncherApp)
        app.hide_window = Mock()

        self.assertEqual(
            app._hide_on_plain_escape(FakeKeyEvent(state=0x0004)),
            "break",
        )
        app.hide_window.assert_not_called()

        self.assertEqual(app._hide_on_plain_escape(FakeKeyEvent()), "break")
        app.hide_window.assert_called_once()

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

    def test_f5_reset_clears_transient_state_but_preserves_palette_state(self):
        app = LauncherApp.__new__(LauncherApp)
        app.focus_actions_mode = True
        app.action_type_filter = "open_url"
        app.action_tag_filter = "database"
        app.action_type_filter_var = FakeVariable()
        app.action_tag_filter_var = FakeVariable()
        app.passwords_button = FakeButton()
        app.captured_selection = "captured"
        app.source_foreground_handle = 123
        app.search_var = FakeVariable()
        app.search_var.value = "query"
        app.status_var = FakeVariable()
        app.palette_state = PaletteState(("pinned",), "Database", {})
        workspace_values: list[str] = []
        reloads: list[bool] = []
        refreshes: list[bool] = []
        focus_requests: list[bool] = []
        app._set_workspace_text = workspace_values.append
        app._reload_if_changed = lambda: reloads.append(True)
        app._refresh_results = lambda: refreshes.append(True)
        app.focus_search = lambda: focus_requests.append(True) or "break"

        result = app._reset_main_window()

        self.assertEqual(result, "break")
        self.assertFalse(app.focus_actions_mode)
        self.assertIsNone(app.action_type_filter)
        self.assertIsNone(app.action_tag_filter)
        self.assertEqual(app.action_type_filter_var.value, "All types")
        self.assertEqual(app.action_tag_filter_var.value, "All tags")
        self.assertEqual(app.passwords_button.options["style"], "Compact.TButton")
        self.assertIsNone(app.captured_selection)
        self.assertIsNone(app.source_foreground_handle)
        self.assertEqual(app.search_var.value, "")
        self.assertEqual(workspace_values, [""])
        self.assertEqual(reloads, [True])
        self.assertEqual(refreshes, [True])
        self.assertEqual(focus_requests, [True])
        self.assertEqual(app.palette_state, PaletteState(("pinned",), "Database", {}))
        self.assertEqual(app.status_var.value, "Reset to the startup view.")

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

    def test_saved_text_pastes_into_fresh_hotkey_destination(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = FakeRoot()
        app.source_foreground_handle = 123

        with (
            patch("context_palette.launcher.focus_window", return_value=True) as focus,
            patch("context_palette.launcher.send_paste_shortcut") as paste,
        ):
            message = app._paste_saved_text_if_destination()
            callback = app.root.after_callbacks.pop()
            with self.assertLogs("context_palette.launcher", level="INFO") as logs:
                callback()

        self.assertIsNone(app.source_foreground_handle)
        self.assertEqual(app.root.withdraw_calls, 1)
        focus.assert_called_once_with(123)
        paste.assert_called_once()
        self.assertIn("returning", message)
        self.assertIn(
            "category=saved_text outcome=success reason=dispatched",
            "\n".join(logs.output),
        )

    def test_saved_text_without_destination_remains_on_clipboard(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = FakeRoot()
        app.source_foreground_handle = None

        with self.assertLogs("context_palette.launcher", level="INFO") as logs:
            message = app._paste_saved_text_if_destination()

        self.assertEqual(app.root.withdraw_calls, 0)
        self.assertEqual(app.root.after_callbacks, [])
        self.assertIn("paste manually", message)
        self.assertIn("reason=no_destination", "\n".join(logs.output))

    def test_unavailable_saved_text_destination_restores_palette(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = FakeRoot()
        app.source_foreground_handle = 123
        app.status_var = FakeVariable()
        app.show_window = Mock()

        with (
            patch("context_palette.launcher.focus_window", return_value=False),
            patch("context_palette.launcher.send_paste_shortcut") as paste,
            patch("context_palette.launcher.messagebox.showerror") as error,
        ):
            app._paste_saved_text_if_destination()
            callback = app.root.after_callbacks.pop()
            with self.assertLogs("context_palette.launcher", level="WARNING") as logs:
                callback()

        app.show_window.assert_called_once()
        paste.assert_not_called()
        self.assertIn("remains on the clipboard", error.call_args.args[1])
        self.assertIn("reason=destination_unavailable", "\n".join(logs.output))

    def test_saved_text_dispatch_failure_restores_palette_and_keeps_clipboard(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = FakeRoot()
        app.source_foreground_handle = 123
        app.status_var = FakeVariable()
        app.show_window = Mock()

        with (
            patch("context_palette.launcher.focus_window", return_value=True),
            patch(
                "context_palette.launcher.send_paste_shortcut",
                side_effect=RuntimeError("Windows input failed"),
            ),
            patch("context_palette.launcher.messagebox.showerror") as error,
        ):
            app._paste_saved_text_if_destination()
            callback = app.root.after_callbacks.pop()
            with self.assertLogs("context_palette.launcher", level="ERROR") as logs:
                callback()

        app.show_window.assert_called_once()
        self.assertIn("remains on the clipboard", error.call_args.args[1])
        self.assertEqual(
            app.status_var.value,
            "Text copied, but automatic paste failed.",
        )
        logged = "\n".join(logs.output)
        self.assertIn("reason=dispatch_error", logged)
        self.assertNotIn("Hello private greeting", logged)

    def test_external_show_invalidates_captured_credential_destination(self):
        app = LauncherApp.__new__(LauncherApp)
        app.source_foreground_handle = 123
        app.show_window = lambda: None

        app._handle_external_request({"command": "show"})

        self.assertIsNone(app.source_foreground_handle)

    def test_every_action_attempt_consumes_captured_destination(self):
        app = LauncherApp.__new__(LauncherApp)
        app.source_foreground_handle = 123
        app.status_var = FakeVariable()
        app.captured_selection = None
        app._workspace_text = lambda: ""
        app._set_clipboard = Mock()
        app._get_clipboard_text = Mock()
        app._ask_for_action_input = Mock()
        app._set_workspace_text = Mock()
        action = Action("website", "Website", "General", "open_url", "https://example.com")

        with patch("context_palette.launcher.execute_action", return_value="Opened"):
            app._execute_action(action)

        self.assertIsNone(app.source_foreground_handle)
        self.assertEqual(app.status_var.value, "Opened")

    def test_failed_action_attempt_also_consumes_captured_destination(self):
        app = LauncherApp.__new__(LauncherApp)
        app.source_foreground_handle = 123
        app.status_var = FakeVariable()
        app.captured_selection = None
        app._workspace_text = lambda: ""
        app._set_clipboard = Mock()
        app._get_clipboard_text = Mock()
        app._ask_for_action_input = Mock()
        app._set_workspace_text = Mock()
        action = Action("broken", "Broken", "General", "open_url", "https://example.com")

        with (
            patch(
                "context_palette.launcher.execute_action",
                side_effect=ActionError("failed"),
            ),
            patch("context_palette.launcher.messagebox.showerror"),
        ):
            app._execute_action(action)

        self.assertIsNone(app.source_foreground_handle)
        self.assertEqual(app.status_var.value, "Action failed")

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
            with self.assertLogs("context_palette.launcher", level="INFO") as logs:
                result = app._paste_credential_action(action)
                clear_callback = app.root.after_callbacks.pop(0)
                paste_callback = app.root.after_callbacks.pop(0)
                paste_callback()
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
        logged = "\n".join(logs.output)
        self.assertIn("category=protected_credential outcome=success", logged)
        self.assertNotIn("do-not-show", logged)
        self.assertNotIn("ContextPalette/example-login", logged)

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

    def test_credential_cleanup_is_armed_before_paste_dispatch(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = FakeRoot()
        app.source_foreground_handle = 123
        app.protected_clipboard_sequence = None
        app.status_var = FakeVariable()
        app.show_window = Mock()
        action = Action(
            "credential",
            "Paste login",
            "General",
            "paste_credential",
            "ContextPalette/example-login",
            "Trusted",
        )

        with (
            patch("context_palette.launcher.window_title", return_value="Sign in"),
            patch("context_palette.launcher.messagebox.askyesno", return_value=True),
            patch(
                "context_palette.launcher.read_windows_credential",
                return_value=CredentialSecret("user", "do-not-show"),
            ),
            patch("context_palette.launcher.set_protected_clipboard_text", return_value=42),
            patch("context_palette.launcher.focus_window", return_value=True),
            patch(
                "context_palette.launcher.send_paste_shortcut",
                side_effect=RuntimeError("Windows input failed"),
            ),
            patch(
                "context_palette.launcher.clear_clipboard_if_unchanged",
                return_value=True,
            ) as clear,
            patch("context_palette.launcher.messagebox.showerror") as error,
        ):
            app._paste_credential_action(action)
            cleanup_callback = app.root.after_callbacks.pop(0)
            paste_callback = app.root.after_callbacks.pop(0)

            paste_callback()
            cleanup_callback()

        clear.assert_called_once_with(42)
        self.assertIsNone(app.protected_clipboard_sequence)
        app.show_window.assert_called_once()
        self.assertIn("was cleared", error.call_args.args[1])
        self.assertNotIn("do-not-show", error.call_args.args[1])
        self.assertEqual(
            app.status_var.value,
            "Protected credential paste was cancelled.",
        )

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

    def test_failed_palette_reload_preserves_last_known_good_state(self):
        previous = PaletteState(
            ("existing",),
            "General",
            {"General": ("existing",)},
        )
        app = LauncherApp.__new__(LauncherApp)
        app.palette_state = previous
        app.palette_path = Path("palette.json")
        app.actions = [
            Action(
                "existing",
                "Existing",
                "General",
                "copy_text",
                "text",
                "Trusted",
            )
        ]
        app.context_definitions = []
        app.context_var = FakeVariable()
        app.status_var = FakeVariable()
        app.root = object()
        app._refresh_focus_controls = lambda: None
        app._render_command_surface = lambda: None

        with (
            patch(
                "context_palette.launcher.load_palette_state",
                side_effect=ActionError("invalid palette"),
            ),
            patch("context_palette.launcher.messagebox.showerror") as showerror,
        ):
            app._load_palette_state()

        self.assertEqual(app.palette_state, previous)
        self.assertIn("kept previous", app.status_var.value)
        showerror.assert_called_once()

    def test_failed_initial_palette_load_keeps_usable_empty_slots(self):
        app = LauncherApp.__new__(LauncherApp)
        app.palette_state = PaletteState()
        app.palette_path = Path("palette.json")
        app.actions = []
        app.context_definitions = []
        app.context_var = FakeVariable()
        app.status_var = FakeVariable()
        app.root = object()
        app._refresh_focus_controls = lambda: None
        app._render_command_surface = lambda: None

        with (
            patch(
                "context_palette.launcher.load_palette_state",
                side_effect=ActionError("invalid palette"),
            ),
            patch("context_palette.launcher.messagebox.showerror"),
        ):
            app._load_palette_state()

        self.assertEqual(app.palette_state.context_slots, {})

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
