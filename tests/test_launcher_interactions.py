from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.actions import Action, ActionError
from context_palette.action_sequences import SequenceStep
from context_palette.action_suggestions import ActionCreationSuggestion
from context_palette.action_types import ACTION_TYPES
from context_palette.action_discovery_panel import (
    ALL_CONTEXTS_FILTER_LABEL,
    ActionDiscoveryPanel,
    DISCOVERY_ALL,
    FOCUS_SLOT_ROW_TAG,
    context_filter_choices,
    context_filter_display_label,
    slot_row_tag,
    visible_result_row_count,
)
from context_palette.command_surface import CommandGroup, CommandItem
from context_palette.contexts import ContextDefinition, ContextError
from context_palette.drop_adapter import DropProblem, DropResult
from context_palette.drop_extraction import DropItem
from context_palette.launcher import (
    LauncherApp,
    _SendDestination,
    bounded_sash_position,
    ordered_configured_quick_groups,
    quick_action_column_count,
    quick_group_top_level_choice_count,
)
from context_palette.ocr import OcrError, OcrResult, OcrSource
from context_palette.palette_state import PaletteState
from context_palette.palette_items import PaletteItemReference
from context_palette.windows_credentials import (
    ClipboardTextSnapshot,
    CredentialSecret,
    ProtectedClipboardTransaction,
)
from context_palette.work_item_file_copy import (
    WorkItemFileCopyError,
    WorkItemFileCopyResult,
)
from context_palette.work_item_inbox import WorkItemInboxError, WorkItemInboxResult
from context_palette.work_item_refresh import SourceRefreshResult, WorkItemIndex
from context_palette.work_items import (
    DiscoveredWorkItem,
    WorkItemReference,
    WorkItemSource,
)
from context_palette.vscode_integration import VsCodeIntegrationError


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


class RecordingMenu:
    """Small menu double that retains commands and cascades for inspection."""

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.entries: list[tuple[str, dict[str, object]]] = []

    def add_command(self, **options: object) -> None:
        self.entries.append(("command", options))

    def add_separator(self) -> None:
        self.entries.append(("separator", {}))

    def add_cascade(self, **options: object) -> None:
        self.entries.append(("cascade", options))

    @property
    def labels(self) -> list[str]:
        return [
            str(options["label"])
            for kind, options in self.entries
            if kind != "separator"
        ]

    def options_for(self, label: str) -> dict[str, object]:
        return next(
            options
            for kind, options in self.entries
            if kind != "separator" and options.get("label") == label
        )


class FakeRoot:
    def __init__(self) -> None:
        self.withdraw_calls = 0
        self.deiconify_calls = 0
        self.lift_calls = 0
        self.attributes_calls: list[tuple[object, ...]] = []
        self.after_callbacks: list[object] = []
        self.cancelled_after_ids: list[object] = []

    def withdraw(self) -> None:
        self.withdraw_calls += 1

    def deiconify(self) -> None:
        self.deiconify_calls += 1

    def lift(self) -> None:
        self.lift_calls += 1

    def attributes(self, *values: object) -> None:
        self.attributes_calls.append(values)

    def after(self, _delay: int, callback: object) -> str:
        self.after_callbacks.append(callback)
        return f"after#{len(self.after_callbacks)}"

    def after_cancel(self, callback_id: object) -> None:
        self.cancelled_after_ids.append(callback_id)


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
    def test_hotkey_centers_palette_in_the_cursor_monitor_work_area(self) -> None:
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.root.winfo_width.return_value = 780
        app.root.winfo_reqwidth.return_value = 780
        app.root.winfo_height.return_value = 600
        app.root.winfo_reqheight.return_value = 600

        app._position_for_hotkey(
            {
                "cursor_x": "-100",
                "cursor_y": "900",
                "work_left": "-1920",
                "work_top": "40",
                "work_right": "0",
                "work_bottom": "1040",
            }
        )

        app.root.geometry.assert_called_once_with("-1350+240")

    def test_ocr_request_uses_clipboard_image_and_places_background_result(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.status_var = FakeVariable()
        app.workspace_component = Mock()
        app.workspace_component.raw_text.return_value = "Existing notes"
        app.workspace_component.apply_ocr_text.return_value = "append"
        app.ocr = Mock()
        app.ocr.running = False
        app.ocr.start.return_value = True
        source = OcrSource("clipboard", "clipboard image", b"png")

        with (
            patch("context_palette.launcher.image_source_from_text", return_value=None),
            patch("context_palette.launcher.clipboard_image_source", return_value=source),
        ):
            app._extract_text_from_image("Existing notes")

        app.workspace_component.set_ocr_running.assert_called_once_with(True)
        self.assertIn("clipboard image", app.status_var.value)
        callback = app.ocr.start.call_args.args[1]
        callback(OcrResult("Found text", 1, 0.4, "Fake OCR", 0.9), None)

        app.workspace_component.apply_ocr_text.assert_called_once_with(
            "Found text",
            source_label="clipboard image",
            expected_text="Existing notes",
        )
        app.workspace_component.set_ocr_running.assert_called_with(False)
        self.assertIn("Appended", app.status_var.value)

    def test_broken_optional_image_source_is_contained_without_workspace_changes(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.status_var = FakeVariable()
        app.workspace_component = Mock()
        app.ocr = Mock(running=False)
        app._show_ocr_error = Mock()

        with (
            patch("context_palette.launcher.image_source_from_text", return_value=None),
            patch(
                "context_palette.launcher.clipboard_image_source",
                side_effect=RuntimeError("broken optional image library"),
            ),
            patch("context_palette.launcher.LOGGER.exception") as log_error,
        ):
            app._extract_text_from_image("Existing notes")

        log_error.assert_called_once()
        error = app._show_ocr_error.call_args.args[0]
        self.assertIsInstance(error, OcrError)
        self.assertNotIn("broken optional image library", str(error))
        app.ocr.start.assert_not_called()
        app.workspace_component.raw_text.assert_not_called()
        app.workspace_component.apply_ocr_text.assert_not_called()
        app.workspace_component.set_ocr_running.assert_not_called()

    def test_ocr_failure_reenables_control_and_preserves_workspace(self):
        app = LauncherApp.__new__(LauncherApp)
        app.workspace_component = Mock()
        app._show_ocr_error = Mock()
        error = OcrError("Image text extraction failed safely.")

        app._accept_ocr_result("clipboard image", "Existing notes", None, error)

        app.workspace_component.set_ocr_running.assert_called_once_with(False)
        app.workspace_component.apply_ocr_text.assert_not_called()
        app._show_ocr_error.assert_called_once_with(error)

    def test_sequence_confirms_and_dispatches_resolved_actions_in_order(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = FakeRoot()
        app.run_button = FakeButton()
        app.action_discovery_panel = Mock()
        app.status_var = FakeVariable()
        app.sequence_run_plan = None
        first = Action("first", "First", "General", "open_url", "https://example.com")
        second = Action("second", "Second", "General", "open_folder", r"C:\work")
        sequence = Action(
            "sequence",
            "Morning",
            "General",
            "sequence",
            "sequence-v1",
            sequence_steps=(
                SequenceStep("action", action_id="first"),
                SequenceStep("wait", milliseconds=200),
                SequenceStep("action", action_id="second"),
            ),
        )
        app.actions = [first, second, sequence]
        app._open_action_target = Mock()

        with patch("context_palette.launcher.messagebox.askyesno", return_value=True) as confirm:
            message = app._run_action_sequence(sequence)
        app.root.after_callbacks.pop(0)()
        app.root.after_callbacks.pop(0)()
        self.assertIn("step 2/3", app.status_var.value.casefold())
        self.assertIn("waiting 0.2 seconds", app.status_var.value.casefold())
        self.assertIn("Stop remaining", app.status_var.value)
        app.root.after_callbacks.pop(0)()
        app.root.after_callbacks.pop(0)()

        self.assertIn("starting", message)
        self.assertIn("Wait 200 ms", confirm.call_args.args[1])
        self.assertEqual(
            [call.args[0].id for call in app._open_action_target.call_args_list],
            ["first", "second"],
        )
        self.assertIsNone(app.sequence_run_plan)
        self.assertIn("finished dispatching 2", app.status_var.value)
        self.assertIn(("-topmost", True), app.root.attributes_calls)
        self.assertEqual(app.root.attributes_calls[-1], ("-topmost", False))
        self.assertEqual(
            app.action_discovery_panel.render_control_state.call_args_list,
            [call(sequence_running=True), call(sequence_running=False)],
        )

    def test_sequence_stop_cancels_only_remaining_steps(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = FakeRoot()
        app.run_button = FakeButton()
        app.action_discovery_panel = Mock()
        app.status_var = FakeVariable()
        app.sequence_run_plan = None
        first = Action("first", "First", "General", "open_url", "https://example.com")
        second = Action("second", "Second", "General", "open_folder", r"C:\work")
        sequence = Action(
            "sequence",
            "Morning",
            "General",
            "sequence",
            "sequence-v1",
            sequence_steps=(
                SequenceStep("action", action_id="first"),
                SequenceStep("wait", milliseconds=500),
                SequenceStep("action", action_id="second"),
            ),
        )
        app.actions = [first, second, sequence]
        app._open_action_target = Mock()

        with patch("context_palette.launcher.messagebox.askyesno", return_value=True):
            app._run_action_sequence(sequence)
        app.root.after_callbacks.pop(0)()
        app.root.after_callbacks.pop(0)()
        stopped = app._stop_action_sequence()

        self.assertTrue(stopped)
        self.assertEqual(app._open_action_target.call_args.args[0].id, "first")
        self.assertIsNone(app.sequence_run_plan)
        self.assertTrue(app.root.cancelled_after_ids)
        self.assertIn("remaining steps were skipped", app.status_var.value)
        self.assertEqual(
            app.action_discovery_panel.render_control_state.call_args_list,
            [call(sequence_running=True), call(sequence_running=False)],
        )

    def test_active_sequence_suspends_focus_loss_auto_hide(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.root.focus_get.return_value = None
        app.hotkey_available = True
        app.hide_after_id = None
        app.sequence_run_plan = Mock()

        app._schedule_hide_when_inactive(Mock())
        app._hide_if_inactive()

        app.root.after.assert_not_called()
        app.root.withdraw.assert_not_called()

    def test_manual_hide_is_blocked_while_sequence_stop_is_attended(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.status_var = FakeVariable()
        app.hide_after_id = None
        app.sequence_run_plan = Mock()

        app.hide_window()

        app.root.withdraw.assert_not_called()
        app.root.attributes.assert_called_with("-topmost", True)
        self.assertIn("Stop remaining", app.status_var.value)

    def test_incomplete_restore_recovery_hides_launcher_and_requests_exit(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.status_var = FakeVariable()
        app._active_work_item_writes = Mock(return_value=())
        app.quit_app = Mock()

        app._require_restore_recovery_restart()

        self.assertTrue(app._configuration_recovery_required)
        app.root.withdraw.assert_called_once_with()
        app.quit_app.assert_called_once_with()

    def test_incomplete_restore_exits_after_active_work_item_write_finishes(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app._configuration_recovery_required = True
        app.work_item_file_copy = Mock(running=False)
        app.work_item_inbox = Mock(running=True)
        app.quit_app = Mock()

        def finish_write() -> None:
            app.work_item_inbox.running = False

        app.work_item_inbox.drain.side_effect = finish_write

        app._poll_work_item_inbox()

        app.quit_app.assert_called_once_with()
        app.root.after.assert_not_called()

    def test_configure_is_blocked_after_incomplete_restore_recovery(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app._configuration_recovery_required = True

        with (
            patch("context_palette.launcher.ConfigurationWindow") as window,
            patch("context_palette.launcher.messagebox.showerror") as error,
        ):
            app._show_configuration()

        window.assert_not_called()
        self.assertIn("restart", error.call_args.args[1].casefold())

    def test_restore_reload_refreshes_every_cached_launcher_projection(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.status_var = FakeVariable()
        app.actions = []
        generation = object()
        app._stage_runtime_configuration = Mock(return_value=generation)
        app._publish_runtime_configuration = Mock()
        app._render_command_surface = Mock()
        app._refresh_results = Mock()
        app._start_work_item_refresh = Mock()
        app._configuration_signature = Mock(return_value=(("test", 1, 1),))
        app.configuration_signature_cache = (("old", 1, 1),)
        app.configuration_failed_signature_cache = (("failed", 1, 1),)

        result = app._reload()

        self.assertTrue(result)
        app._stage_runtime_configuration.assert_called_once()
        app._publish_runtime_configuration.assert_called_once_with(generation)
        app._render_command_surface.assert_called_once_with()
        app._refresh_results.assert_called_once_with()
        app._start_work_item_refresh.assert_called_once_with()
        self.assertEqual(app.configuration_signature_cache, (("test", 1, 1),))
        self.assertIsNone(app.configuration_failed_signature_cache)

    def test_failed_late_stage_reload_preserves_complete_runtime_generation(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.status_var = FakeVariable()
        app.actions_path = Path("actions.json")
        app.local_actions_path = Path("local_actions.json")
        app.command_surface_path = Path("command_surface.json")
        app.local_command_surface_path = Path("local_command_surface.json")
        app.contexts_path = Path("contexts.json")
        app.local_contexts_path = Path("missing_local_contexts.json")
        app.palette_path = Path("palette.json")
        app.local_work_item_sources_path = Path("local_work_item_sources.json")
        app.local_work_item_metadata_path = Path("local_work_item_metadata.json")
        app.local_work_item_settings_path = Path("local_work_item_settings.json")

        old_actions = [Mock(name="old_action")]
        old_local_ids = {"old-action"}
        old_groups = [Mock(name="old_group")]
        old_contexts = [Mock(name="old_context")]
        old_local_names = {"old": "Old"}
        old_palette = PaletteState(focus_context="Old")
        old_available_names = ["General", "Old"]
        old_sources = (Mock(name="old_source"),)
        old_metadata = {"old/item": Mock(name="old_metadata")}
        old_index = Mock(name="old_index")
        app.actions = old_actions
        app.local_action_ids = old_local_ids
        app.command_groups = old_groups
        app.context_definitions = old_contexts
        app.local_context_names = old_local_names
        app.palette_state = old_palette
        app.available_context_names = old_available_names
        app.work_item_sources = old_sources
        app.work_item_metadata = old_metadata
        app.work_item_index = old_index
        app._render_command_surface = Mock()
        app._refresh_results = Mock()
        app._start_work_item_refresh = Mock()
        old_signature = (("accepted", 1, 1),)
        attempted_signature = (("attempted", 2, 2),)
        app.configuration_signature_cache = old_signature
        app.configuration_failed_signature_cache = None
        app._configuration_signature = Mock(return_value=attempted_signature)

        with (
            patch(
                "context_palette.launcher.load_combined_actions",
                return_value=([Mock(name="new_action")], {"new-action"}),
            ),
            patch(
                "context_palette.launcher.load_combined_command_groups",
                return_value=[Mock(name="new_group")],
            ),
            patch(
                "context_palette.launcher.load_combined_contexts",
                return_value=[Mock(name="new_context")],
            ),
            patch(
                "context_palette.launcher.actions_with_canonical_contexts",
                return_value=[Mock(name="canonical_new_action")],
            ),
            patch(
                "context_palette.launcher.load_work_item_sources",
                return_value=(Mock(name="new_source"),),
            ),
            patch(
                "context_palette.launcher.load_work_item_metadata",
                return_value={"new/item": Mock(name="new_metadata")},
            ),
            patch("context_palette.launcher.load_work_item_creation_settings"),
            patch(
                "context_palette.launcher.load_palette_state",
                side_effect=ActionError("palette is invalid"),
            ),
            patch("context_palette.launcher.messagebox.showerror") as showerror,
        ):
            result = app._reload()

        self.assertFalse(result)
        self.assertIs(app.actions, old_actions)
        self.assertIs(app.local_action_ids, old_local_ids)
        self.assertIs(app.command_groups, old_groups)
        self.assertIs(app.context_definitions, old_contexts)
        self.assertIs(app.local_context_names, old_local_names)
        self.assertIs(app.palette_state, old_palette)
        self.assertIs(app.available_context_names, old_available_names)
        self.assertIs(app.work_item_sources, old_sources)
        self.assertIs(app.work_item_metadata, old_metadata)
        self.assertIs(app.work_item_index, old_index)
        app._render_command_surface.assert_not_called()
        app._refresh_results.assert_not_called()
        app._start_work_item_refresh.assert_not_called()
        self.assertEqual(app.configuration_signature_cache, old_signature)
        self.assertEqual(
            app.configuration_failed_signature_cache,
            attempted_signature,
        )
        showerror.assert_called_once()
        self.assertIn("No configuration was changed", showerror.call_args.args[1])

    def test_failed_bootstrap_signature_remains_available_for_f5_retry(self):
        app = LauncherApp.__new__(LauncherApp)
        invalid_signature = (("invalid", 2, 2),)
        app._configuration_signature = Mock(return_value=invalid_signature)
        app.configuration_signature_cache = (("old", 1, 1),)
        app.configuration_failed_signature_cache = None

        app._record_bootstrap_configuration_signature(
            (True, True, False, True, True),
            expected_signature=invalid_signature,
        )

        self.assertEqual(app.configuration_signature_cache, ())
        self.assertEqual(
            app.configuration_failed_signature_cache,
            invalid_signature,
        )

    def test_changed_bootstrap_signature_is_not_accepted_or_suppressed(self):
        app = LauncherApp.__new__(LauncherApp)
        before_signature = (("changing", 1, 1),)
        after_signature = (("changing", 2, 2),)
        app._configuration_signature = Mock(return_value=after_signature)
        app.configuration_signature_cache = (("old", 0, 0),)
        app.configuration_failed_signature_cache = (("failed", 0, 0),)

        app._record_bootstrap_configuration_signature(
            (True, True, True, True, True),
            expected_signature=before_signature,
        )

        self.assertEqual(app.configuration_signature_cache, ())
        self.assertIsNone(app.configuration_failed_signature_cache)

    def test_files_changed_during_staging_are_not_published(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.status_var = FakeVariable()
        app.actions = [Mock(name="accepted_action")]
        generation = object()
        app._stage_runtime_configuration = Mock(return_value=generation)
        app._publish_runtime_configuration = Mock()
        app._render_command_surface = Mock()
        app._refresh_results = Mock()
        app._start_work_item_refresh = Mock()
        accepted_signature = (("accepted", 1, 1),)
        before_signature = (("changing", 2, 2),)
        after_signature = (("changing", 3, 3),)
        app.configuration_signature_cache = accepted_signature
        app.configuration_failed_signature_cache = None
        app._configuration_signature = Mock(
            side_effect=[before_signature, after_signature]
        )

        with patch(
            "context_palette.launcher.messagebox.showwarning"
        ) as showwarning:
            result = app._reload()

        self.assertFalse(result)
        app._publish_runtime_configuration.assert_not_called()
        app._render_command_surface.assert_not_called()
        app._refresh_results.assert_not_called()
        app._start_work_item_refresh.assert_not_called()
        self.assertEqual(app.configuration_signature_cache, accepted_signature)
        self.assertIsNone(app.configuration_failed_signature_cache)
        showwarning.assert_called_once()
        self.assertIn(
            "No configuration was changed",
            showwarning.call_args.args[1],
        )

    def test_inbox_is_loaded_from_storage_each_time_it_is_opened(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.inbox_path = Path("inbox.json")
        app.actions = []
        app.palette_state = PaletteState()
        app.available_context_names = []
        app.local_context_names = {}
        app.local_actions_path = Path("local_actions.json")
        app.contexts_path = Path("contexts.json")
        app.local_contexts_path = Path("local_contexts.json")
        app._reload_after_external_action_change = Mock()
        app._show_harvest = Mock()

        first = (Mock(),)
        restored = (Mock(), Mock())
        with (
            patch(
                "context_palette.launcher.load_inbox_items",
                side_effect=[first, restored],
            ) as load,
            patch("context_palette.launcher.InboxWindow") as window,
        ):
            app._show_inbox()
            app._show_inbox()

        self.assertEqual(load.call_count, 2)
        self.assertIs(window.call_args_list[0].args[1], first)
        self.assertIs(window.call_args_list[1].args[1], restored)

    def test_personal_context_is_the_only_non_general_authoring_default(self):
        app = LauncherApp.__new__(LauncherApp)
        app.local_context_names = {"review": "Review"}

        app.palette_state = PaletteState(focus_context="Review")
        self.assertEqual(app._active_authoring_context(), "Review")

        app.palette_state = PaletteState(focus_context="Built-in project")
        self.assertEqual(app._active_authoring_context(), "General")

    def test_quit_is_blocked_while_each_work_item_write_is_running(self):
        for file_copy_running, inbox_running, expected in (
            (True, False, "file copy"),
            (False, True, "Excel Inbox update"),
            (True, True, "file copy and an Excel Inbox update"),
        ):
            with self.subTest(
                file_copy_running=file_copy_running,
                inbox_running=inbox_running,
            ):
                app = LauncherApp.__new__(LauncherApp)
                app.root = Mock()
                app.hotkey = Mock()
                app.instance_server = Mock()
                app.work_item_file_copy = Mock(running=file_copy_running)
                app.work_item_inbox = Mock(running=inbox_running)
                app.status_var = FakeVariable()
                app._finish_protected_clipboard = Mock()

                with patch(
                    "context_palette.launcher.messagebox.showwarning"
                ) as warning:
                    app.quit_app()

                self.assertIn(expected, warning.call_args.args[1])
                self.assertIn("Quit blocked", app.status_var.value)
                app._finish_protected_clipboard.assert_not_called()
                app.hotkey.stop.assert_not_called()
                app.instance_server.stop.assert_not_called()
                app.root.destroy.assert_not_called()

    def test_quit_still_stops_cleanly_when_no_work_item_write_is_running(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.hotkey = Mock()
        app.instance_server = Mock()
        app.work_item_file_copy = Mock(running=False)
        app.work_item_inbox = Mock(running=False)
        app.status_var = FakeVariable()
        app._finish_protected_clipboard = Mock()
        app._cancel_pending_tk_callbacks = Mock()

        app.quit_app()

        app._finish_protected_clipboard.assert_called_once_with()
        app.hotkey.stop.assert_called_once_with()
        app.instance_server.stop.assert_called_once_with()
        app._cancel_pending_tk_callbacks.assert_called_once_with()
        app.root.destroy.assert_called_once_with()

    def test_quit_is_blocked_while_local_ocr_is_running(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.hotkey = Mock()
        app.instance_server = Mock()
        app.work_item_file_copy = Mock(running=False)
        app.work_item_inbox = Mock(running=False)
        app.ocr = Mock(running=True)
        app.status_var = FakeVariable()
        app._finish_protected_clipboard = Mock()

        with patch("context_palette.launcher.messagebox.showwarning") as warning:
            app.quit_app()

        self.assertIn("image text extraction", warning.call_args.args[1])
        app._finish_protected_clipboard.assert_not_called()
        app.root.destroy.assert_not_called()

    def test_quit_is_blocked_while_excel_automation_is_running(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.hotkey = Mock()
        app.instance_server = Mock()
        app.work_item_file_copy = Mock(running=False)
        app.work_item_inbox = Mock(running=False)
        app.excel_automation_window = Mock(busy=True)
        app.status_var = FakeVariable()
        app._finish_protected_clipboard = Mock()

        with patch("context_palette.launcher.messagebox.showwarning") as warning:
            app.quit_app()

        self.assertIn("Excel automation", warning.call_args.args[1])
        app._finish_protected_clipboard.assert_not_called()
        app.root.destroy.assert_not_called()

    def test_quit_is_blocked_while_protected_clipboard_cleanup_is_pending(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.hotkey = Mock()
        app.instance_server = Mock()
        app.work_item_file_copy = Mock(running=False)
        app.work_item_inbox = Mock(running=False)
        app.status_var = FakeVariable()
        app.protected_clipboard_sequence = 42
        app._finish_protected_clipboard = Mock(return_value=False)
        app._cancel_pending_tk_callbacks = Mock()

        with patch("context_palette.launcher.messagebox.showwarning") as warning:
            app.quit_app()

        self.assertIn("cannot quit", warning.call_args.args[1])
        self.assertIn("Quit blocked", app.status_var.value)
        app.hotkey.stop.assert_not_called()
        app.instance_server.stop.assert_not_called()
        app.root.destroy.assert_not_called()

    def test_cancel_pending_tk_callbacks_cancels_every_interpreter_callback(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.root.tk.call.return_value = ("after#1", "after#2", "after#3")
        app.root.tk.splitlist.return_value = ("after#1", "after#2", "after#3")

        app._cancel_pending_tk_callbacks()

        self.assertEqual(
            app.root.tk.call.call_args_list,
            [
                unittest.mock.call("after", "info"),
                unittest.mock.call("after", "cancel", "after#1"),
                unittest.mock.call("after", "cancel", "after#2"),
                unittest.mock.call("after", "cancel", "after#3"),
            ],
        )
        app.root.after_cancel.assert_not_called()

    def test_quit_is_blocked_while_backup_or_restore_worker_is_running(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.hotkey = Mock()
        app.instance_server = Mock()
        app.work_item_file_copy = Mock(running=False)
        app.work_item_inbox = Mock(running=False)
        app.status_var = FakeVariable()
        app._finish_protected_clipboard = Mock()
        app._cancel_pending_tk_callbacks = Mock()
        app.configuration_window = Mock()
        app.configuration_window.window.winfo_exists.return_value = True
        app.configuration_window.backup_restore_panel.busy = True

        with patch("context_palette.launcher.messagebox.showwarning") as warning:
            app.quit_app()

        self.assertIn("configuration backup or restore", warning.call_args.args[1])
        self.assertIn("Quit blocked", app.status_var.value)
        app._cancel_pending_tk_callbacks.assert_not_called()
        app.root.destroy.assert_not_called()

    def test_workspace_file_copy_starts_for_selected_work_item(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.txt"
            source.write_text("content", encoding="utf-8")
            folder = root / "ISS-CAP40-example"
            folder.mkdir()
            item = DiscoveredWorkItem(
                "cap40", "CAP40", folder.name, folder, folder.name,
                "ISS", "Issue", "CAP40", "example", (), None,
            )
            app = LauncherApp.__new__(LauncherApp)
            app.work_item_file_copy = Mock(running=False)
            app.work_item_file_copy.start.return_value = True
            app._selected_work_item = Mock(return_value=item)
            app._workspace_text = Mock(return_value=f'"{source}"')
            app.copy_file_to_work_item_button = Mock()
            app.status_var = FakeVariable()

            app._copy_workspace_file_to_work_item()

            app.work_item_file_copy.start.assert_called_once()
            self.assertEqual(app.work_item_file_copy.start.call_args.args[0], source)
            self.assertEqual(app.work_item_file_copy.start.call_args.args[1], folder)
            self.assertIn(source.name, app.status_var.value)

    def test_invalid_workspace_file_path_shows_actionable_error(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.work_item_file_copy = Mock(running=False)
        app._selected_work_item = Mock(return_value=Mock())
        app._workspace_text = Mock(return_value="not-a-full-path")
        app.status_var = FakeVariable()

        with patch("context_palette.launcher.messagebox.showerror") as showerror:
            app._copy_workspace_file_to_work_item()

        self.assertIn("absolute", showerror.call_args.args[1])
        app.work_item_file_copy.start.assert_not_called()

    def test_file_copy_completion_reports_destination_without_source_content(self):
        app = LauncherApp.__new__(LauncherApp)
        app.copy_file_to_work_item_button = Mock()
        app.status_var = FakeVariable()
        item = Mock(display_name="ISS-CAP40-example")
        result = WorkItemFileCopyResult(
            Path("C:/source/report.txt"),
            Path("C:/work/item/report.txt"),
            12,
        )

        app._complete_work_item_file_copy(item, result, None)

        self.assertEqual(
            app.status_var.value,
            "Copied report.txt to ISS-CAP40-example.",
        )

    def test_file_copy_completion_shows_collision_error(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.copy_file_to_work_item_button = Mock()
        app.status_var = FakeVariable()

        with patch("context_palette.launcher.messagebox.showerror") as showerror:
            app._complete_work_item_file_copy(
                Mock(),
                None,
                WorkItemFileCopyError("A file already exists; nothing was overwritten."),
            )

        self.assertIn("nothing was overwritten", showerror.call_args.args[1])

    def test_existing_workbook_inbox_send_starts_without_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "ISS-CAP40-example"
            folder.mkdir()
            workbook = folder / "ISS-CAP40-example.xlsx"
            workbook.write_bytes(b"xlsx")
            item = DiscoveredWorkItem(
                "cap40", "CAP40", folder.name, folder, folder.name,
                "ISS", "Issue", "CAP40", "example", (), workbook,
            )
            app = LauncherApp.__new__(LauncherApp)
            app.work_item_inbox = Mock(running=False)
            app.work_item_inbox.start.return_value = True
            app._selected_work_item = Mock(return_value=item)
            app._workspace_text = Mock(return_value="See https://example.com")
            app._work_item_inbox_source = Mock(return_value="Input / Output")
            app.send_work_item_inbox_button = Mock()
            app.status_var = FakeVariable()

            with patch("context_palette.launcher.messagebox.askyesno") as confirm:
                app._send_workspace_to_work_item_inbox()

            confirm.assert_not_called()
            app.work_item_inbox.start.assert_called_once()
            self.assertEqual(
                app.work_item_inbox.start.call_args.args[3].link,
                "https://example.com",
            )

    def test_missing_workbook_offers_template_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "ISS-CAP40-example"
            folder.mkdir()
            template = root / "generic.xlsx"
            template.write_bytes(b"template")
            item = DiscoveredWorkItem(
                "cap40", "CAP40", folder.name, folder, folder.name,
                "ISS", "Issue", "CAP40", "example", (), None,
            )
            app = LauncherApp.__new__(LauncherApp)
            app.root = Mock()
            app.local_work_item_settings_path = root / "settings.json"
            app.work_item_inbox = Mock(running=False)
            app.work_item_inbox.start.return_value = True
            app._workspace_text = Mock(return_value="note")
            app._work_item_inbox_source = Mock(return_value="Input / Output")
            app.send_work_item_inbox_button = Mock()
            app.status_var = FakeVariable()

            with (
                patch(
                    "context_palette.launcher.load_work_item_creation_settings",
                    return_value=Mock(template_path=template),
                ),
                patch(
                    "context_palette.launcher.messagebox.askyesno",
                    return_value=True,
                ) as confirm,
            ):
                app._send_workspace_to_work_item_inbox(item)

            confirm.assert_called_once()
            self.assertIsNone(app.work_item_inbox.start.call_args.args[1])
            self.assertEqual(app.work_item_inbox.start.call_args.args[2], template)

    def test_inbox_completion_reports_row_without_content(self):
        app = LauncherApp.__new__(LauncherApp)
        app.send_work_item_inbox_button = Mock()
        app.status_var = FakeVariable()
        app._start_work_item_refresh = Mock()
        item = Mock(display_name="ISS-CAP40-example")
        result = WorkItemInboxResult(
            Path("C:/work/item/item.xlsx"),
            7,
            True,
            False,
        )

        app._complete_work_item_inbox_send(item, result, None, False)

        self.assertIn("Inbox row 7", app.status_var.value)
        self.assertNotIn("secret", app.status_var.value)
        app._start_work_item_refresh.assert_not_called()

    def test_inbox_completion_shows_actionable_error(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.send_work_item_inbox_button = Mock()
        app.status_var = FakeVariable()
        app._start_work_item_refresh = Mock()

        with patch("context_palette.launcher.messagebox.showerror") as showerror:
            app._complete_work_item_inbox_send(
                Mock(),
                None,
                WorkItemInboxError("Workbook is read-only."),
                False,
            )

        self.assertIn("read-only", showerror.call_args.args[1])

    def test_new_work_item_route_opens_existing_creation_flow(self):
        app = LauncherApp.__new__(LauncherApp)
        app._show_configuration = Mock()

        app._show_work_item_creation()

        app._show_configuration.assert_called_once_with(
            initial_tab="work_items",
            start_work_item_creation=True,
        )

    def test_new_action_route_opens_quick_creation_in_configure(self):
        app = LauncherApp.__new__(LauncherApp)
        app._show_configuration = Mock()

        self.assertEqual(app._show_action_creation(), "break")

        app._show_configuration.assert_called_once_with(
            initial_tab="actions",
            start_action_creation=True,
        )

    def test_workspace_url_opens_prefilled_existing_action_flow(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app._show_configuration = Mock()

        app._create_action_from_workspace("https://example.com/report")

        app._show_configuration.assert_called_once_with(
            initial_tab="actions",
            initial_action_suggestion=ActionCreationSuggestion(
                "open_url",
                "Open example.com",
                "https://example.com/report",
            ),
        )

    def test_ambiguous_workspace_text_explains_without_opening_configure(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app._show_configuration = Mock()

        with patch("context_palette.launcher.messagebox.showinfo") as showinfo:
            app._create_action_from_workspace(
                "See https://example.com and https://openai.com"
            )

        app._show_configuration.assert_not_called()
        self.assertIn("could not confidently identify", showinfo.call_args.args[1])

    def test_edit_selected_action_requests_its_editor_directly(self):
        app = LauncherApp.__new__(LauncherApp)
        action = Action("edit-me", "Edit me", "General", "copy_text", "one")
        app._selected_action = Mock(return_value=action)
        app._selected_work_item = Mock()
        app._show_configuration = Mock()

        app._edit_selected()

        app._show_configuration.assert_called_once_with(
            initial_action_id="edit-me",
            start_action_edit=True,
        )
        app._selected_work_item.assert_not_called()

    def test_action_row_navigation_keeps_configure_selection_without_direct_edit(self):
        app = LauncherApp.__new__(LauncherApp)
        action = Action("show-me", "Show me", "General", "copy_text", "one")
        app._show_configuration = Mock()

        app._show_action_configuration(action)

        app._show_configuration.assert_called_once_with(
            initial_tab="actions",
            initial_action_id="show-me",
        )

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

    def test_retired_shift_one_through_five_remain_find_input(self):
        app = LauncherApp.__new__(LauncherApp)
        app.search_entry = object()
        app.root = Mock()
        app.root.focus_get.return_value = app.search_entry
        app._execute_slot = Mock(return_value="break")
        event = FakeKeyEvent(state=0x0001, keysym="2", keycode=50)

        self.assertIsNone(app._handle_keypress(event))
        app._execute_slot.assert_not_called()

    def test_focus_slot_dispatches_work_item_reference(self):
        app = LauncherApp.__new__(LauncherApp)
        reference = PaletteItemReference(
            work_item_ref=WorkItemReference(
                "product-work",
                "ISS-ABC-example",
            )
        )
        app.slot_items = {6: reference}
        app.status_var = FakeVariable()
        app._execute_palette_item = Mock(return_value=True)

        result = app._execute_slot(6, FakeKeyEvent())

        self.assertEqual(result, "break")
        app._execute_palette_item.assert_called_once_with(reference)

    def test_shift_azerty_key_names_execute_slots_without_assumed_keycodes(self):
        app = LauncherApp.__new__(LauncherApp)
        app.search_entry = object()
        app.root = Mock()
        app.root.focus_get.return_value = app.search_entry
        app._execute_slot = Mock(return_value="break")

        for keysym, expected_slot in (
            ("minus", 6),
            ("egrave", 7),
            ("underscore", 8),
            ("ccedilla", 9),
            ("agrave", 10),
            ("parenright", 10),
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

    def test_shift_zero_executes_slot_10_but_numpad_zero_remains_input(self):
        app = LauncherApp.__new__(LauncherApp)
        app.search_entry = object()
        app.root = Mock()
        app.root.focus_get.return_value = app.search_entry
        app._execute_slot = Mock(return_value="break")
        top_row = FakeKeyEvent(state=0x0001, keysym="0", keycode=48, char="0")
        numpad = FakeKeyEvent(state=0x0001, keysym="kp_0", keycode=96, char="0")

        self.assertEqual(app._handle_keypress(top_row), "break")
        app._execute_slot.assert_called_once_with(10, top_row)
        app._execute_slot.reset_mock()
        self.assertIsNone(app._handle_keypress(numpad))
        app._execute_slot.assert_not_called()

    def test_keyboard_navigation_skips_action_list_separator(self):
        app = LauncherApp.__new__(LauncherApp)
        first = Action("first", "First", "General", "copy_text", "1")
        second = Action("second", "Second", "General", "copy_text", "2")
        app.work_items_mode = False
        app.displayed_action_rows = [(first, 6), (None, None), (second, None)]
        app.results = Mock()
        app.results.curselection.return_value = (0,)
        app._update_preview = Mock()

        app._select_index(1, Mock())

        app.results.selection_set.assert_called_once_with(2)
        app.results.activate.assert_called_once_with(2)

    def test_mouse_click_on_action_list_separator_clears_selection(self):
        app = LauncherApp.__new__(LauncherApp)
        app.work_items_mode = False
        app.results_view = "flat"
        app.displayed_action_rows = [(None, None)]
        app.results = Mock()
        app.results.nearest.return_value = 0
        app.results.bbox.return_value = (0, 10, 100, 20)
        app._update_preview = Mock()
        event = Mock(y=15)

        result = app._guard_action_separator_click(event)

        self.assertEqual(result, "break")
        app.results.selection_clear.assert_called_once()
        app._update_preview.assert_called_once_with()

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

    def test_quick_action_grid_uses_one_column_until_both_are_readable(self):
        self.assertEqual(quick_action_column_count(200), 1)
        self.assertEqual(quick_action_column_count(249), 1)
        self.assertEqual(quick_action_column_count(250), 2)
        self.assertEqual(quick_action_column_count(900), 2)

    def test_filter_indicator_exposes_saved_filters_from_other_scopes(self):
        app = LauncherApp.__new__(LauncherApp)
        app.action_discovery_panel = Mock()
        app.discovery_scope = DISCOVERY_ALL
        app.action_type_filter = "open_url"
        app.work_project_filter = "AB9C"
        app.item_tag_filter = "urgent"
        app.item_context_filter = "Database"

        app._sync_filter_indicators()

        app.action_discovery_panel.set_filter_indicators.assert_called_once_with(
            scope=DISCOVERY_ALL,
            primary_value=None,
            context_value="Database",
            tag_value="urgent",
            saved_values=(
                f"Actions: {ACTION_TYPES['open_url'].display_label}",
                "Work Items: AB9C",
            ),
        )

    def test_quick_action_order_prioritizes_personal_configured_menus(self):
        with tempfile.TemporaryDirectory() as directory:
            local_path = Path(directory) / "local_command_surface.json"
            shared_path = Path(directory) / "command_surface.json"
            groups = [
                CommandGroup("shared-one", "Shared one", source_path=shared_path),
                CommandGroup("personal-one", "Personal one", source_path=local_path),
                CommandGroup("unknown", "Unknown"),
                CommandGroup("personal-two", "Personal two", source_path=local_path),
                CommandGroup("shared-two", "Shared two", source_path=shared_path),
            ]

            ordered = ordered_configured_quick_groups(groups, local_path)

            self.assertEqual(
                [group.id for group in ordered],
                [
                    "personal-one",
                    "personal-two",
                    "shared-one",
                    "unknown",
                    "shared-two",
                ],
            )

    def test_quick_action_tooltip_count_describes_root_choices(self):
        group = CommandGroup(
            "tools",
            "Tools",
            items=(
                CommandItem("first", "First"),
                CommandItem("second", "Second"),
            ),
            primary_action_id="open-tools",
            action_ids=("open-tools", "copy-tools"),
        )

        self.assertEqual(quick_group_top_level_choice_count(group), 4)

    def test_configured_quick_action_tooltip_explains_browse_count(self):
        app = LauncherApp.__new__(LauncherApp)
        area = Mock()
        control = Mock()
        app.command_tiles_frame = Mock()
        app._surface_menu_label = Mock(return_value=control)
        app._command_surface_tooltip = Mock()
        app._bind_surface_menu_control = Mock()
        group = CommandGroup(
            "tools",
            "Tools",
            items=(
                CommandItem("first", "First"),
                CommandItem("second", "Second"),
            ),
        )

        with patch("context_palette.launcher.ttk.Frame", return_value=area):
            app._render_configured_quick_group(group, row=1, column=0)

        tooltip = app._command_surface_tooltip.call_args.args[1]
        self.assertIn("browse Tools (2 configured top-level choices)", tooltip)
        self.assertIn("Right-click: add or organize", tooltip)

    def test_automatic_quick_action_tooltip_reports_live_action_count(self):
        app = LauncherApp.__new__(LauncherApp)
        area = Mock()
        control = Mock()
        app.command_tiles_frame = Mock()
        app._surface_menu_label = Mock(return_value=control)
        app._command_surface_tooltip = Mock()
        app._bind_surface_menu_control = Mock()
        app.actions = [
            Action("folder", "Folder", "General", "open_folder", r"C:\work"),
            Action(
                "old-folder",
                "Old folder",
                "General",
                "open_folder",
                r"C:\old",
                state="Archived",
            ),
        ]
        group = CommandGroup("action-bound-folders", "Folders")

        with patch("context_palette.launcher.ttk.Frame", return_value=area):
            app._render_action_bound_quick_group(group, row=1, column=1)

        tooltip = app._command_surface_tooltip.call_args.args[1]
        self.assertIn("browse Folders (1 active Action)", tooltip)
        self.assertIn("Matching Actions appear automatically", tooltip)

    def test_visible_result_rows_adapt_to_text_scaling(self):
        self.assertEqual(visible_result_row_count(1.333), 7)
        self.assertEqual(visible_result_row_count(1.667), 6)
        self.assertEqual(visible_result_row_count(2.0), 5)

    def test_slot_row_tags_identify_only_context_shortcuts(self):
        for slot in range(1, 6):
            self.assertIsNone(slot_row_tag(slot))
        for slot in range(6, 11):
            self.assertEqual(slot_row_tag(slot), FOCUS_SLOT_ROW_TAG)
        self.assertIsNone(slot_row_tag(None))

    def test_result_label_uses_measured_icon_column_without_dash(self):
        app = LauncherApp.__new__(LauncherApp)
        icon = ACTION_TYPES["copy_text"].icon
        app.item_icon_padding = {icon: "\u200a\u200a"}
        action = Action("copy", "Copy title", "General", "copy_text", "value")

        label = app._aligned_action_display_text(action)

        self.assertEqual(label, f"{icon}\u200a\u200a {action.compact_title}")
        self.assertNotIn(" - ", label)

    def test_sash_position_scales_minimums_when_window_is_too_small(self):
        self.assertEqual(bounded_sash_position(200, 0.9, 140, 140), 100)

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
        self.assertEqual(
            app.action_type_filter_var.value,
            ACTION_TYPES["paste_credential"].display_label,
        )
        self.assertEqual(app.passwords_button.options["style"], "RailIconAccent.TButton")

        app._toggle_password_actions()

        self.assertIsNone(app.action_type_filter)
        self.assertEqual(app.action_type_filter_var.value, "All types")
        self.assertEqual(app.passwords_button.options["style"], "RailIcon.TButton")
        self.assertEqual(refreshes, [True, True])

    def test_context_filter_selects_the_matching_shortcut_bank(self):
        app = LauncherApp.__new__(LauncherApp)
        app.item_context_filter = None
        app.item_context_filter_var = FakeVariable()
        app.palette_state = PaletteState((), "Developing", {})
        app.root = Mock()
        refreshes: list[bool] = []
        synchronizations: list[bool] = []
        app._sync_filter_indicators = lambda: synchronizations.append(True)
        app._refresh_results = lambda: refreshes.append(True)
        app._focus_active_results = Mock()

        app._select_item_context_filter("Database")

        self.assertEqual(app.item_context_filter, "Database")
        self.assertEqual(app.item_context_filter_var.value, "Database")
        self.assertEqual(app.palette_state.focus_context, "Database")

        app._select_item_context_filter(None)

        self.assertIsNone(app.item_context_filter)
        self.assertEqual(app.item_context_filter_var.value, "All contexts")
        self.assertEqual(app.palette_state.focus_context, "General")
        self.assertEqual(synchronizations, [True, True])
        self.assertEqual(refreshes, [True, True])
        self.assertEqual(app.root.after_idle.call_count, 2)

    def test_context_filter_disambiguates_a_context_named_all_contexts(self):
        contexts = ("General", "All contexts", "All contexts — Context")

        choices, values_by_display, _displays_by_value = context_filter_choices(
            contexts
        )

        self.assertEqual(
            choices,
            ("All contexts — Context", "All contexts — Context — Context"),
        )
        self.assertEqual(
            values_by_display["all contexts — context"],
            "All contexts",
        )
        self.assertEqual(
            context_filter_display_label(contexts, "All contexts"),
            "All contexts — Context",
        )
        self.assertEqual(context_filter_display_label(contexts, None), "All contexts")

        panel = ActionDiscoveryPanel.__new__(ActionDiscoveryPanel)
        panel._context_values_by_display = values_by_display
        panel.select_context_filter = Mock()
        panel._select_context_from_picker(("All contexts — Context",))
        panel.select_context_filter.assert_called_once_with("All contexts")
        panel.select_context_filter.reset_mock()
        panel._select_context_from_picker((ALL_CONTEXTS_FILTER_LABEL,))
        panel.select_context_filter.assert_called_once_with(None)

    def test_any_action_type_can_be_selected_as_a_filter(self):
        app = LauncherApp.__new__(LauncherApp)
        app.action_type_filter = None
        app.passwords_button = FakeButton()
        app.action_type_filter_var = FakeVariable()
        refreshes: list[bool] = []
        app._refresh_results = lambda: refreshes.append(True)

        app._select_action_type_filter("open_url")

        self.assertEqual(app.action_type_filter, "open_url")
        self.assertEqual(
            app.action_type_filter_var.value,
            ACTION_TYPES["open_url"].display_label,
        )
        self.assertEqual(app.passwords_button.options["style"], "RailIcon.TButton")
        self.assertEqual(refreshes, [True])

    def test_context_filter_includes_a_preferred_only_work_item(self):
        reference = WorkItemReference("cap40", "QST-CAP40-question")
        item = DiscoveredWorkItem(
            "cap40",
            "CAP40",
            reference.relative_folder,
            Path("C:/workitems/QST-CAP40-question"),
            reference.relative_folder,
            "QST",
            "Question",
            "CAP40",
            "question",
            (),
            None,
        )
        app = LauncherApp.__new__(LauncherApp)
        app.context_definitions = [
            ContextDefinition(
                "Database",
                preferred_item_refs=(
                    PaletteItemReference(work_item_ref=reference),
                ),
            )
        ]

        self.assertTrue(app._work_item_belongs_to_context(item, "Database"))
        self.assertFalse(app._work_item_belongs_to_context(item, "Other"))

    def test_work_item_refresh_rejects_old_source_with_reused_id(self):
        old_source = WorkItemSource("cap40", "CAP40", Path("C:/old/workitems"))
        current_source = WorkItemSource(
            "cap40",
            "CAP40",
            Path("C:/current/workitems"),
        )
        app = LauncherApp.__new__(LauncherApp)
        app.work_item_sources = (current_source,)
        app.work_item_metadata = {}
        app.actions = []
        app.work_project_filter = None
        app.item_tag_filter = None
        app.discovery_scope = "test-only"
        app.work_item_refresh_pending = False

        app._accept_work_item_index(
            WorkItemIndex((SourceRefreshResult(old_source, ()),), 1.0)
        )

        self.assertEqual(app.work_item_index.sources, ())

    def test_f5_reset_clears_transient_state_but_preserves_palette_state(self):
        app = LauncherApp.__new__(LauncherApp)
        app.item_context_filter = "Database"
        app.item_context_filter_var = FakeVariable()
        app.action_type_filter = "open_url"
        app.action_tag_filter = "database"
        app.work_project_filter = "AB9C"
        app.work_tag_filter = "urgent"
        app.item_tag_filter = "urgent"
        app.action_type_filter_var = FakeVariable()
        app.action_tag_filter_var = FakeVariable()
        app.item_tag_filter_var = FakeVariable()
        app.passwords_button = FakeButton()
        app.captured_selection = "captured"
        app.source_foreground_handle = 123
        app.search_var = FakeVariable()
        app.search_var.value = "query"
        app.status_var = FakeVariable()
        app.configuration_failed_signature_cache = (("failed", 1, 1),)
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
        self.assertIsNone(app.item_context_filter)
        self.assertEqual(app.item_context_filter_var.value, "All contexts")
        self.assertIsNone(app.action_type_filter)
        self.assertIsNone(app.action_tag_filter)
        self.assertIsNone(app.work_project_filter)
        self.assertIsNone(app.work_tag_filter)
        self.assertIsNone(app.item_tag_filter)
        self.assertEqual(app.action_type_filter_var.value, "All types")
        self.assertEqual(app.action_tag_filter_var.value, "All tags")
        self.assertEqual(app.item_tag_filter_var.value, "All tags")
        self.assertEqual(app.passwords_button.options["style"], "RailIcon.TButton")
        self.assertIsNone(app.captured_selection)
        self.assertIsNone(app.source_foreground_handle)
        self.assertEqual(app.search_var.value, "")
        self.assertEqual(workspace_values, [""])
        self.assertEqual(reloads, [True])
        self.assertIsNone(app.configuration_failed_signature_cache)
        self.assertEqual(refreshes, [True])
        self.assertEqual(focus_requests, [True])
        self.assertEqual(app.palette_state, PaletteState(("pinned",), "General", {}))
        self.assertEqual(app.status_var.value, "Reset to the startup view.")

    def test_protected_clipboard_is_never_synchronized_into_workspace(self):
        app = LauncherApp.__new__(LauncherApp)
        synchronizations: list[bool] = []
        app._sync_workspace_from_clipboard = lambda: synchronizations.append(True)
        app._finish_protected_clipboard = Mock()
        app.protected_clipboard_sequence = 42

        app._sync_workspace_from_clipboard_if_safe()
        self.assertEqual(synchronizations, [])
        app._finish_protected_clipboard.assert_called_once_with()

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

    def test_busy_clipboard_keeps_protected_transaction_tracked(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = FakeRoot()
        app.protected_clipboard_sequence = 42
        app.protected_clipboard_snapshot = ClipboardTextSnapshot("previous")

        with patch(
            "context_palette.launcher.restore_clipboard_text_if_unchanged",
            return_value=None,
        ):
            restored = app._finish_protected_clipboard(42)

        self.assertFalse(restored)
        self.assertEqual(app.protected_clipboard_sequence, 42)
        self.assertEqual(
            app.protected_clipboard_snapshot,
            ClipboardTextSnapshot("previous"),
        )
        self.assertEqual(len(app.root.after_callbacks), 1)

        with patch(
            "context_palette.launcher.restore_clipboard_text_if_unchanged",
            return_value=True,
        ) as restore:
            app.root.after_callbacks.pop()()

        restore.assert_called_once_with(42, ClipboardTextSnapshot("previous"))
        self.assertIsNone(app.protected_clipboard_sequence)
        self.assertIsNone(app.protected_clipboard_snapshot)

    def test_newer_clipboard_content_ends_obsolete_protected_transaction(self):
        app = LauncherApp.__new__(LauncherApp)
        app.protected_clipboard_sequence = 42
        app.protected_clipboard_snapshot = ClipboardTextSnapshot("previous")

        with patch(
            "context_palette.launcher.restore_clipboard_text_if_unchanged",
            return_value=False,
        ):
            restored = app._finish_protected_clipboard(42)

        self.assertFalse(restored)
        self.assertIsNone(app.protected_clipboard_sequence)
        self.assertIsNone(app.protected_clipboard_snapshot)

    def test_exhausted_clipboard_retries_keep_tracking_and_warn(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = FakeRoot()
        app.status_var = FakeVariable()
        app.protected_clipboard_sequence = 42
        app.protected_clipboard_snapshot = ClipboardTextSnapshot("previous")

        with (
            patch(
                "context_palette.launcher.restore_clipboard_text_if_unchanged",
                return_value=None,
            ),
            patch("context_palette.launcher.messagebox.showwarning") as warning,
        ):
            restored = app._finish_protected_clipboard(42, retry_count=5)

        self.assertFalse(restored)
        self.assertEqual(app.protected_clipboard_sequence, 42)
        self.assertEqual(app.root.after_callbacks, [])
        self.assertIn("needs attention", app.status_var.value)
        self.assertIn("Copy harmless text", warning.call_args.args[1])

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

    def test_external_context_request_selects_filter_bank_or_general(self):
        app = LauncherApp.__new__(LauncherApp)
        app.source_foreground_handle = 123
        app.show_window = Mock()
        app.available_context_names = ["General", "Database"]
        app._select_item_context_filter = Mock()
        app.status_var = FakeVariable()
        app.search_var = FakeVariable()
        app.root = Mock()
        app.focus_search = Mock()

        app._handle_external_request({"command": "show", "context": "database"})
        app._select_item_context_filter.assert_called_once_with("Database")

        app._select_item_context_filter.reset_mock()
        app._handle_external_request({"command": "show", "context": "General"})
        app._select_item_context_filter.assert_called_once_with(None)

        app._select_item_context_filter.reset_mock()
        app._handle_external_request({"command": "show", "context": "missing"})
        app._select_item_context_filter.assert_not_called()
        self.assertEqual(app.status_var.value, "Unknown integration context: missing")

    def test_drop_reveal_never_synchronizes_clipboard(self):
        app = LauncherApp.__new__(LauncherApp)
        app._configuration_recovery_required = False
        app.root = Mock()
        app.search_var = FakeVariable()
        app._cancel_scheduled_hide = Mock()
        app._reload_if_changed = Mock()
        app._sync_workspace_from_clipboard_if_safe = Mock()
        app.focus_search = Mock()

        self.assertTrue(
            app._reveal_window(
                sync_workspace=False,
                focus_search=False,
                temporary_attention=False,
            )
        )

        app._sync_workspace_from_clipboard_if_safe.assert_not_called()
        app.root.attributes.assert_called_once_with("-topmost", False)
        app.root.after.assert_not_called()

    def test_drop_result_clears_stale_capture_and_places_exact_order(self):
        app = LauncherApp.__new__(LauncherApp)
        app.captured_selection = "stale selection"
        app.source_foreground_handle = 123
        app.status_var = FakeVariable()
        app.root = Mock()
        app._reveal_window = Mock(return_value=True)
        app.workspace_component = Mock()
        app.workspace_component.apply_incoming_text.return_value = "replace"
        result = DropResult(
            items=(
                DropItem("path", r"C:\First File.txt"),
                DropItem("url", "https://example.test/second"),
            )
        )

        app._accept_drop_result(result)

        self.assertIsNone(app.captured_selection)
        self.assertIsNone(app.source_foreground_handle)
        app._reveal_window.assert_called_once_with(
            sync_workspace=False,
            focus_search=False,
            temporary_attention=False,
        )
        app.workspace_component.apply_incoming_text.assert_called_once_with(
            "C:\\First File.txt\nhttps://example.test/second",
            source_label="the drop target",
        )
        self.assertIn("2 dropped item(s)", app.status_var.value)

    def test_failed_drop_does_not_reveal_or_replace_workspace(self):
        app = LauncherApp.__new__(LauncherApp)
        app.captured_selection = "still valid"
        app.source_foreground_handle = 123
        app.status_var = FakeVariable()
        app._reveal_window = Mock()
        app.workspace_component = Mock()

        app._accept_drop_result(
            DropResult(error=DropProblem("payload", "Drop could not be decoded."))
        )

        app._reveal_window.assert_not_called()
        app.workspace_component.apply_incoming_text.assert_not_called()
        self.assertEqual(app.captured_selection, "still valid")
        self.assertEqual(app.source_foreground_handle, 123)

    def test_drop_target_start_failure_sets_actionable_status(self) -> None:
        app = LauncherApp.__new__(LauncherApp)
        app.status_var = FakeVariable()
        app.drop_target_window = Mock()
        app.drop_target_window.start.return_value = False

        with self.assertLogs("context_palette.launcher", level="WARNING"):
            app._start_drop_target()

        self.assertIn("Drop target unavailable", app.status_var.value)
        self.assertIn("More", app.status_var.value)
        app.drop_target_window.start.assert_called_once_with()

    def test_show_unavailable_drop_target_explains_setup_and_restart(self) -> None:
        app = LauncherApp.__new__(LauncherApp)
        app.root = object()
        app.status_var = FakeVariable()
        app.drop_target_window = Mock()
        app.drop_target_window.show.return_value = False
        app.drop_target_window.unavailable_reason = (
            "The drop target window could not be initialized."
        )

        with patch("context_palette.launcher.messagebox.showwarning") as warning:
            app._show_drop_target()

        self.assertIn("remains usable", app.status_var.value)
        message = warning.call_args.args[1]
        self.assertIn("could not be initialized", message)
        self.assertIn("Stop Context Palette", message)
        self.assertIn("setup-context-palette.bat", message)
        self.assertIn("restart", message.casefold())
        self.assertIn("All other Context Palette features", message)
        self.assertIs(warning.call_args.kwargs["parent"], app.root)

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

    def test_excel_action_opens_attended_workflow_for_exact_workspace_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "one.xlsx"
            second = root / "two.xlsx"
            first.write_bytes(b"one")
            second.write_bytes(b"two")
            app = LauncherApp.__new__(LauncherApp)
            app.root = Mock()
            app.status_var = FakeVariable()
            app.excel_automation_settings_path = root / "settings.json"
            app.excel_automation_window = None
            app._workspace_text = Mock(return_value=f'"{first}"\n{second}')
            app._open_excel_output_folder = Mock()
            app._excel_automation_closed = Mock()
            workflow = Mock(busy=False)

            with patch(
                "context_palette.launcher.ExcelAutomationWindow",
                return_value=workflow,
            ) as window:
                message = app._run_excel_automation(
                    Action(
                        "excel-export",
                        "Export Excel files to CSV",
                        "General",
                        "excel_automation",
                        "excel.export_workbooks_to_csv",
                    )
                )

            self.assertEqual(
                window.call_args.kwargs["workbooks"],
                (first.resolve(), second.resolve()),
            )
            self.assertEqual(
                window.call_args.kwargs["settings_path"],
                app.excel_automation_settings_path,
            )
            self.assertIs(app.excel_automation_window, workflow)
            self.assertIn("2 workbook(s)", message)

    def test_live_excel_action_uses_open_workbooks_without_workspace_input(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.status_var = FakeVariable()
        app.excel_automation_settings_path = Path("C:/settings.json")
        app.excel_automation_window = None
        app._workspace_text = Mock(return_value="not workbook input")
        app._excel_automation_closed = Mock()
        workflow = Mock(busy=False)

        with (
            patch(
                "context_palette.launcher.ExcelLiveFormatWindow",
                return_value=workflow,
            ) as window,
            patch("context_palette.launcher.window_process_id", return_value=55),
            patch(
                "context_palette.launcher.window_title",
                return_value="Budget.xlsx - Excel",
            ),
        ):
            message = app._run_excel_automation(
                Action(
                    "excel-live-format",
                    "Apply Excel format template",
                    "General",
                    "excel_automation",
                    "excel.apply_live_format_profile",
                ),
                source_window_handle=123,
            )

        app._workspace_text.assert_not_called()
        self.assertEqual(window.call_args.kwargs["source_window_handle"], 123)
        self.assertEqual(window.call_args.kwargs["source_process_id"], 55)
        self.assertEqual(
            window.call_args.kwargs["source_window_title"],
            "Budget.xlsx - Excel",
        )
        self.assertIs(app.excel_automation_window, workflow)
        self.assertIn("live Excel format", message)

    def test_live_text_conversion_uses_open_workbooks_and_startup_uat_gate(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.status_var = FakeVariable()
        app.excel_automation_settings_path = Path("C:/settings.json")
        app.excel_automation_window = None
        app.live_text_conversion_execution_enabled = True
        app._workspace_text = Mock(return_value="not workbook input")
        app._excel_automation_closed = Mock()
        app._open_excel_recovery_file = Mock()
        app._open_excel_output_folder = Mock()
        workflow = Mock(busy=False)

        with (
            patch(
                "context_palette.launcher.ExcelLiveTextConversionWindow",
                return_value=workflow,
            ) as window,
            patch("context_palette.launcher.window_process_id", return_value=55),
            patch(
                "context_palette.launcher.window_title",
                return_value="Budget.xlsx - Excel",
            ),
        ):
            message = app._run_excel_automation(
                Action(
                    "excel-live-text",
                    "UAT: Convert scientific-notation columns",
                    "General",
                    "excel_automation",
                    "excel.convert_live_column_representation",
                ),
                source_window_handle=123,
            )

        app._workspace_text.assert_not_called()
        self.assertEqual(window.call_args.kwargs["source_window_handle"], 123)
        self.assertEqual(window.call_args.kwargs["source_process_id"], 55)
        self.assertEqual(
            window.call_args.kwargs["source_window_title"],
            "Budget.xlsx - Excel",
        )
        self.assertTrue(window.call_args.kwargs["execution_enabled"])
        self.assertIs(
            window.call_args.kwargs["file_opener"],
            app._open_excel_recovery_file,
        )
        self.assertIs(app.excel_automation_window, workflow)
        self.assertIn("text-conversion", message)

    def test_excel_runner_receives_and_consumes_the_captured_window(self):
        app = LauncherApp.__new__(LauncherApp)
        app.source_foreground_handle = 123
        app.status_var = FakeVariable()
        app.captured_selection = None
        app._workspace_text = Mock(return_value="")
        app._set_clipboard = Mock()
        app._get_clipboard_text = Mock()
        app._ask_for_action_input = Mock()
        app._set_workspace_text = Mock()
        app._run_excel_automation = Mock(return_value="Opened live Excel format")
        action = Action(
            "excel-live-format",
            "Apply Excel format template",
            "General",
            "excel_automation",
            "excel.apply_live_format_profile",
        )

        def execute_with_runner(selected, **kwargs):
            return kwargs["excel_automation_runner"](selected)

        with patch(
            "context_palette.launcher.execute_action",
            side_effect=execute_with_runner,
        ):
            app._execute_action(action)

        app._run_excel_automation.assert_called_once_with(
            action,
            source_window_handle=123,
        )
        self.assertIsNone(app.source_foreground_handle)
        self.assertEqual(app.status_var.value, "Opened live Excel format")

    def test_excel_action_rejects_mixed_workspace_without_opening_workflow(self):
        app = LauncherApp.__new__(LauncherApp)
        app._workspace_text = Mock(return_value="notes and not a workbook")
        app.excel_automation_window = None

        with (
            patch("context_palette.launcher.ExcelAutomationWindow") as window,
            self.assertRaises(ActionError),
        ):
            app._run_excel_automation(
                Action(
                    "excel-export",
                    "Export Excel files to CSV",
                    "General",
                    "excel_automation",
                    "excel.export_workbooks_to_csv",
                )
            )

        window.assert_not_called()

    def test_excel_action_lifts_existing_busy_workflow(self):
        app = LauncherApp.__new__(LauncherApp)
        app._workspace_text = Mock()
        existing = Mock(busy=True)
        app.excel_automation_window = existing

        with patch(
            "context_palette.launcher.workbook_paths_from_workspace",
            return_value=(Path("C:/book.xlsx"),),
        ), self.assertRaises(ActionError):
            app._run_excel_automation(
                Action(
                    "excel-export",
                    "Export Excel files to CSV",
                    "General",
                    "excel_automation",
                    "excel.export_workbooks_to_csv",
                )
            )

        existing.show.assert_called_once_with()
        existing.close.assert_not_called()

    def test_credential_paste_confirms_destination_and_clears_conditionally(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = FakeRoot()
        app.source_foreground_handle = 123
        app.protected_clipboard_sequence = None
        app.protected_clipboard_snapshot = None
        action = Action(
            "credential",
            "Paste login",
            "General",
            "paste_credential",
            "ContextPalette/example-login",
            "Active",
        )

        with (
            patch("context_palette.launcher.window_title", return_value="Sign in") as title,
            patch("context_palette.launcher.messagebox.askyesno", return_value=True) as confirm,
            patch(
                "context_palette.launcher.read_windows_credential",
                return_value=CredentialSecret("user", "do-not-show"),
            ),
            patch(
                "context_palette.launcher.begin_protected_clipboard_transaction",
                return_value=ProtectedClipboardTransaction(
                    42,
                    ClipboardTextSnapshot("previous clipboard text"),
                ),
            ),
            patch("context_palette.launcher.focus_window", return_value=True),
            patch("context_palette.launcher.send_paste_shortcut") as paste,
            patch(
                "context_palette.launcher.restore_clipboard_text_if_unchanged",
                return_value=True,
            ) as restore,
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
        restore.assert_called_once_with(
            42,
            ClipboardTextSnapshot("previous clipboard text"),
        )
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
            "Active",
        )

        with self.assertRaisesRegex(ActionError, "F9"):
            app._paste_credential_action(action)

    def test_credential_cleanup_is_armed_before_paste_dispatch(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = FakeRoot()
        app.source_foreground_handle = 123
        app.protected_clipboard_sequence = None
        app.protected_clipboard_snapshot = None
        app.status_var = FakeVariable()
        app.show_window = Mock()
        action = Action(
            "credential",
            "Paste login",
            "General",
            "paste_credential",
            "ContextPalette/example-login",
            "Active",
        )

        with (
            patch("context_palette.launcher.window_title", return_value="Sign in"),
            patch("context_palette.launcher.messagebox.askyesno", return_value=True),
            patch(
                "context_palette.launcher.read_windows_credential",
                return_value=CredentialSecret("user", "do-not-show"),
            ),
            patch(
                "context_palette.launcher.begin_protected_clipboard_transaction",
                return_value=ProtectedClipboardTransaction(
                    42,
                    ClipboardTextSnapshot("previous clipboard text"),
                ),
            ),
            patch("context_palette.launcher.focus_window", return_value=True),
            patch(
                "context_palette.launcher.send_paste_shortcut",
                side_effect=RuntimeError("Windows input failed"),
            ),
            patch(
                "context_palette.launcher.restore_clipboard_text_if_unchanged",
                return_value=True,
            ) as restore,
            patch("context_palette.launcher.messagebox.showerror") as error,
        ):
            app._paste_credential_action(action)
            cleanup_callback = app.root.after_callbacks.pop(0)
            paste_callback = app.root.after_callbacks.pop(0)

            paste_callback()
            cleanup_callback()

        restore.assert_called_once_with(
            42,
            ClipboardTextSnapshot("previous clipboard text"),
        )
        self.assertIsNone(app.protected_clipboard_sequence)
        app.show_window.assert_called_once()
        self.assertIn("restored the previous clipboard text", error.call_args.args[1])
        self.assertNotIn("do-not-show", error.call_args.args[1])
        self.assertEqual(
            app.status_var.value,
            "Protected credential paste was cancelled.",
        )

    def test_failed_context_reload_preserves_last_known_good_contexts(self):
        app = LauncherApp.__new__(LauncherApp)
        existing = ContextDefinition(
            "Database",
            "Existing context",
            action_ids=("existing",),
        )
        app.context_definitions = [existing]
        app.actions = [
            Action(
                "existing",
                "Existing",
                "General",
                "copy_text",
                "text",
                "Active",
            )
        ]
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
        self.assertEqual(app.actions[0].effective_contexts, ("Database",))
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
                "Active",
            )
        ]
        app.context_definitions = []
        app.item_context_filter = None
        app.status_var = FakeVariable()
        app.root = object()
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
        self.assertIn("kept the current Context filter", app.status_var.value)
        showerror.assert_called_once()

    def test_palette_reload_canonicalizes_or_clears_context_filter(self):
        app = LauncherApp.__new__(LauncherApp)
        state = PaletteState((), "General", {})
        app.palette_state = state
        app.palette_path = Path("palette.json")
        app.actions = [
            Action("database", "Database", "General", "copy_text", "text")
        ]
        app.context_definitions = [
            ContextDefinition("Database", action_ids=("database",))
        ]
        app.item_context_filter = "database"
        app.item_context_filter_var = FakeVariable()
        app.action_type_filter = None
        app.work_project_filter = None
        app.item_tag_filter = None
        app.action_discovery_panel = Mock()
        app._render_command_surface = Mock()

        with patch(
            "context_palette.launcher.load_palette_state",
            return_value=state,
        ):
            app._load_palette_state(render=False)

        self.assertEqual(app.item_context_filter, "Database")
        self.assertEqual(app.item_context_filter_var.value, "Database")
        self.assertEqual(app.palette_state.focus_context, "Database")
        app.action_discovery_panel.set_contexts.assert_called_with(
            ("General", "Database")
        )
        self.assertEqual(
            app.action_discovery_panel.set_filter_indicators.call_args.kwargs[
                "context_value"
            ],
            "Database",
        )

        app.context_definitions = []
        app.action_discovery_panel.reset_mock()
        with patch(
            "context_palette.launcher.load_palette_state",
            return_value=state,
        ):
            app._load_palette_state(render=False)

        self.assertIsNone(app.item_context_filter)
        self.assertEqual(app.item_context_filter_var.value, "All contexts")
        self.assertEqual(app.palette_state.focus_context, "General")
        app.action_discovery_panel.set_contexts.assert_called_with(("General",))
        self.assertIsNone(
            app.action_discovery_panel.set_filter_indicators.call_args.kwargs[
                "context_value"
            ]
        )

    def test_failed_initial_palette_load_keeps_usable_empty_slots(self):
        app = LauncherApp.__new__(LauncherApp)
        app.palette_state = PaletteState()
        app.palette_path = Path("palette.json")
        app.actions = []
        app.context_definitions = []
        app.item_context_filter = None
        app.status_var = FakeVariable()
        app.root = object()
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
                                "state": "Active",
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

    def test_external_action_change_refreshes_open_configuration(self):
        app = LauncherApp.__new__(LauncherApp)
        app._reload = Mock()
        app.configuration_window = Mock()
        app.configuration_window.window.winfo_exists.return_value = True

        app._reload_after_external_action_change()

        app._reload.assert_called_once_with()
        app.configuration_window.refresh_from_storage.assert_called_once_with()

    def test_keyboard_quick_action_opens_its_menu_without_running(self):
        app = LauncherApp.__new__(LauncherApp)
        app._post_group_menu = Mock(return_value="break")
        control = Mock()
        control.winfo_rootx.return_value = 12
        control.winfo_rooty.return_value = 20
        control.winfo_height.return_value = 30
        group = CommandGroup(
            "docs",
            "Docs",
            (CommandItem("python", "Python", primary_action_id="open-docs"),),
        )

        result = app._show_group_menu_at_control(control, group)

        self.assertEqual(result, "break")
        app._post_group_menu.assert_called_once_with(group, 12, 50)

    def test_keyboard_empty_quick_action_still_opens_disabled_menu(self):
        app = LauncherApp.__new__(LauncherApp)
        app._post_group_menu = Mock(return_value="break")
        control = Mock()
        control.winfo_rootx.return_value = 4
        control.winfo_rooty.return_value = 5
        control.winfo_height.return_value = 6
        group = CommandGroup("empty", "Empty")

        result = app._show_group_menu_at_control(control, group)

        self.assertEqual(result, "break")
        app._post_group_menu.assert_called_once_with(group, 4, 11)

    def test_send_to_menu_guides_empty_input(self):
        app = LauncherApp.__new__(LauncherApp)
        app.workspace_component = Mock()
        app.workspace_component.raw_text.return_value = " \n\t"
        menu = RecordingMenu()

        app._populate_send_to_menu(menu)

        self.assertEqual(
            menu.labels,
            ["Paste or drop one or more file paths first"],
        )
        self.assertEqual(
            menu.options_for(menu.labels[0])["state"],
            "disabled",
        )

    def test_send_to_menu_prioritizes_selected_work_item_and_context_folders(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work_item_folder = root / "ISS-CAP40-report"
            finance_folder = root / "finance"
            other_folder = root / "other"
            work_item_folder.mkdir()
            finance_folder.mkdir()
            other_folder.mkdir()
            selected_item = DiscoveredWorkItem(
                "cap40",
                "CAP40",
                work_item_folder.name,
                work_item_folder,
                work_item_folder.name,
                "ISS",
                "Issue",
                "CAP40",
                "report",
                ("CAP40",),
                None,
            )
            finance_action = Action(
                "finance-folder",
                "Finance reports",
                "Finance",
                "open_folder",
                str(finance_folder),
                contexts=("Finance",),
                quick_action_path=("Reports",),
            )
            other_action = Action(
                "other-folder",
                "Other reports",
                "Other",
                "open_folder",
                str(other_folder),
                contexts=("Other",),
            )
            app = LauncherApp.__new__(LauncherApp)
            app.workspace_component = Mock()
            app.workspace_component.raw_text.return_value = (
                f'"{root / "first.txt"}"\n"{root / "second.txt"}"'
            )
            app._selected_work_item = Mock(return_value=selected_item)
            app.actions = [
                finance_action,
                other_action,
                Action(
                    "archived",
                    "Archived folder",
                    "Finance",
                    "open_folder",
                    str(root / "archived"),
                    state="Archived",
                ),
                Action(
                    "not-folder",
                    "Not a folder",
                    "Finance",
                    "copy_text",
                    "text",
                ),
            ]
            app.context_definitions = []
            app.item_context_filter = "Finance"
            app.recent_send_destinations = []
            app._open_send_destination = Mock()
            menu = RecordingMenu()

            with patch(
                "context_palette.launcher.tk.Menu",
                side_effect=lambda *_args, **_kwargs: RecordingMenu(),
            ):
                app._populate_send_to_menu(menu)

            self.assertEqual(menu.labels[0], "Copy 2 file paths to:")
            self.assertIn(
                f"Selected Work Item — {selected_item.display_name}",
                menu.labels,
            )
            self.assertIn("Context: Finance", menu.labels)
            self.assertIn("Finance reports", menu.labels)
            self.assertNotIn("Other reports", menu.labels)
            self.assertIn("All Folder Actions", menu.labels)
            all_menu = menu.options_for("All Folder Actions")["menu"]
            self.assertIsInstance(all_menu, RecordingMenu)
            self.assertIn("Other reports", all_menu.labels)
            self.assertIn("Reports", all_menu.labels)
            reports_menu = all_menu.options_for("Reports")["menu"]
            self.assertIsInstance(reports_menu, RecordingMenu)
            self.assertIn("Finance reports", reports_menu.labels)

            selected_command = menu.options_for(
                f"Selected Work Item — {selected_item.display_name}"
            )["command"]
            self.assertTrue(callable(selected_command))
            selected_command()
            destination = app._open_send_destination.call_args.args[0]
            self.assertEqual(destination.folder_path, work_item_folder)
            self.assertIn("Work Item", destination.label)

    def test_send_to_folder_actions_use_normal_relative_and_file_uri_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative_folder = root / "relative destination"
            uri_folder = root / "URI destination"
            relative_folder.mkdir()
            uri_folder.mkdir()
            app = LauncherApp.__new__(LauncherApp)
            app.actions = [
                Action(
                    "relative-folder",
                    "Relative folder",
                    "General",
                    "open_folder",
                    "relative destination",
                ),
                Action(
                    "uri-folder",
                    "URI folder",
                    "General",
                    "open_folder",
                    uri_folder.as_uri(),
                ),
            ]

            with patch(
                "context_palette.actions.Path.cwd",
                return_value=root,
            ):
                destinations = app._folder_send_destinations()

        self.assertEqual(
            {destination.key: destination.folder_path for destination in destinations},
            {
                "action:relative-folder": relative_folder,
                "action:uri-folder": uri_folder,
            },
        )
        self.assertTrue(
            all(destination.folder_path.is_absolute() for destination in destinations)
        )

    def test_send_to_excludes_clipboard_folder_without_starting_a_copy(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.workspace_component = Mock()
        app.workspace_component.raw_text.return_value = r"C:\source\report.txt"
        app.actions = [
            Action(
                "customer-folder",
                "Current customer",
                "General",
                "open_folder",
                r"D:\customers\%CLIPBOARD%",
            )
        ]
        app.item_context_filter = None
        app.recent_send_destinations = []
        app.work_item_index = Mock(items=())
        app.send_to_destination_picker = None
        app.send_to_button = Mock()
        app.status_var = FakeVariable()
        app._selected_work_item = Mock(return_value=None)
        app._open_send_destination = Mock()
        menu = RecordingMenu()

        with (
            patch(
                "context_palette.launcher.tk.Menu",
                side_effect=lambda *_args, **_kwargs: RecordingMenu(),
            ),
            patch("context_palette.launcher.FileTransferWindow") as transfer_window,
            patch(
                "context_palette.launcher.SearchableSelectionPopup"
            ) as destination_picker,
        ):
            app._populate_send_to_menu(menu)
            menu.options_for("Find destination…")["command"]()

        self.assertNotIn("Current customer", menu.labels)
        self.assertIn(
            "1 clipboard-based Folder Action unavailable here — run normally",
            menu.labels,
        )
        self.assertIn("cannot receive Send-to files", app.status_var.value)
        app._open_send_destination.assert_not_called()
        destination_picker.assert_not_called()
        transfer_window.assert_not_called()
        app.root.clipboard_get.assert_not_called()

    def test_send_to_menu_exposes_search_one_off_and_management_routes(self):
        app = LauncherApp.__new__(LauncherApp)
        app.workspace_component = Mock()
        app.workspace_component.raw_text.return_value = r"C:\source\report.txt"
        app._selected_work_item = Mock(return_value=None)
        app.actions = []
        app.context_definitions = []
        app.item_context_filter = None
        app.recent_send_destinations = []
        app._show_send_destination_picker = Mock()
        app._choose_send_destination_folder = Mock()
        app._find_automatic_quick_actions = Mock()
        app._open_workspace_folder_in_vscode = Mock()
        menu = RecordingMenu()

        app._populate_send_to_menu(menu)

        for label in (
            "Find destination…",
            "Choose another folder…",
            "Manage Folder Actions…",
            "Open folder in VS Code",
        ):
            command = menu.options_for(label)["command"]
            self.assertTrue(callable(command))
            command()
        app._show_send_destination_picker.assert_called_once_with()
        app._choose_send_destination_folder.assert_called_once_with()
        app._find_automatic_quick_actions.assert_called_once_with(
            "Folders",
            "open_folder",
        )
        app._open_workspace_folder_in_vscode.assert_called_once_with()

    def test_send_to_vscode_uses_one_workspace_path_without_changing_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "project"
            folder.mkdir()
            source = folder / "app.py"
            source.write_text("print('hello')", encoding="utf-8")
            app = LauncherApp.__new__(LauncherApp)
            app.root = Mock()
            app.workspace_component = Mock()
            app.workspace_component.raw_text.return_value = f'"{source}"'
            app.status_var = FakeVariable()

            with patch(
                "context_palette.launcher.open_workspace_path_in_vscode",
                return_value=folder,
            ) as opener:
                app._open_workspace_folder_in_vscode()

        opener.assert_called_once_with(f'"{source}"')
        app.workspace_component.set_text.assert_not_called()
        app.root.clipboard_get.assert_not_called()
        app.root.clipboard_clear.assert_not_called()
        app.root.clipboard_append.assert_not_called()
        self.assertIn("project", app.status_var.value)

    def test_send_to_vscode_shows_an_actionable_path_error(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.workspace_component = Mock()
        app.workspace_component.raw_text.return_value = "two\npaths"
        app.status_var = FakeVariable()

        with (
            patch(
                "context_palette.launcher.open_workspace_path_in_vscode",
                side_effect=VsCodeIntegrationError("Choose exactly one path."),
            ),
            patch("context_palette.launcher.messagebox.showerror") as showerror,
        ):
            app._open_workspace_folder_in_vscode()

        self.assertIn("exactly one", showerror.call_args.args[1])
        self.assertEqual(app.status_var.value, "VS Code could not be opened.")

    def test_send_to_search_and_one_off_folder_open_the_selected_destination(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.send_to_destination_picker = None
        app.send_to_button = Mock()
        app.status_var = FakeVariable()
        app._open_send_destination = Mock()
        destination = _SendDestination(
            "action:reports",
            "Reports",
            Path(r"C:\destination\reports"),
            search_text="Reports Finance monthly",
        )
        app._all_send_destinations = Mock(return_value=[destination])

        with patch("context_palette.launcher.SearchableSelectionPopup") as popup:
            app._show_send_destination_picker()

        labels = popup.call_args.args[1]
        self.assertEqual(len(labels), 1)
        self.assertIn("Finance monthly", labels[0])
        self.assertEqual(popup.call_args.kwargs["title"], "Find copy destination")
        popup.call_args.kwargs["on_select"]((labels[0],))
        app._open_send_destination.assert_called_once_with(destination)

        app._open_send_destination.reset_mock()
        with patch(
            "context_palette.launcher.filedialog.askdirectory",
            return_value=r"C:\destination\one-off",
        ):
            app._choose_send_destination_folder()
        one_off = app._open_send_destination.call_args.args[0]
        self.assertEqual(one_off.folder_path, Path(r"C:\destination\one-off"))
        self.assertTrue(one_off.key.startswith("folder:"))

    def test_send_to_uses_one_workspace_snapshot_without_clipboard_or_text_changes(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.workspace_component = Mock()
        snapshot = '  "C:\\source\\one.txt"\nC:\\source\\two.txt  '
        app.workspace_component.raw_text.return_value = snapshot
        app.file_transfer_window = None
        app.status_var = FakeVariable()
        app.recent_send_destinations = []
        destination = _SendDestination(
            "action:reports",
            "Reports",
            Path(r"C:\destination\reports"),
        )
        workflow = Mock(busy=False)

        with patch(
            "context_palette.launcher.FileTransferWindow",
            return_value=workflow,
        ) as window:
            app._open_send_destination(destination)

        self.assertEqual(window.call_args.kwargs["workspace_text"], snapshot)
        self.assertEqual(
            window.call_args.kwargs["destination_folder"],
            destination.folder_path,
        )
        app.workspace_component.set_text.assert_not_called()
        app.workspace_component.get_text.assert_not_called()
        app.root.clipboard_get.assert_not_called()
        app.root.clipboard_clear.assert_not_called()
        app.root.clipboard_append.assert_not_called()
        self.assertEqual(app.recent_send_destinations, [])
        workflow.show.assert_called_once_with()

        window.call_args.kwargs["on_success"](destination.folder_path)
        self.assertEqual(
            [item.folder_path for item in app.recent_send_destinations],
            [destination.folder_path],
        )

    def test_send_to_recent_destinations_are_deduped_bounded_and_runtime_only(self):
        app = LauncherApp.__new__(LauncherApp)
        app.recent_send_destinations = []
        destinations = [
            _SendDestination(
                f"folder:{index}",
                f"Folder {index}",
                Path(f"C:/destinations/{index}"),
            )
            for index in range(12)
        ]

        with patch.object(
            Path,
            "write_text",
            side_effect=AssertionError("recent destinations must not be persisted"),
        ):
            for destination in destinations:
                app._remember_send_destination(
                    destination,
                    destination.folder_path,
                )
            renamed = _SendDestination(
                "folder:renamed",
                "Most recent name",
                destinations[-3].folder_path,
            )
            app._remember_send_destination(renamed, renamed.folder_path)

        self.assertEqual(len(app.recent_send_destinations), 10)
        self.assertEqual(
            app.recent_send_destinations[0].label,
            "Most recent name",
        )
        self.assertEqual(
            sum(
                item.folder_path == renamed.folder_path
                for item in app.recent_send_destinations
            ),
            1,
        )

    def test_send_to_single_flight_reuses_busy_workflow(self):
        app = LauncherApp.__new__(LauncherApp)
        app.workspace_component = Mock()
        app.status_var = FakeVariable()
        current = Mock(busy=True)
        current.window.winfo_exists.return_value = True
        app.file_transfer_window = current
        destination = _SendDestination(
            "action:reports",
            "Reports",
            Path(r"C:\destination\reports"),
        )

        with patch("context_palette.launcher.FileTransferWindow") as window:
            app._open_send_destination(destination)

        window.assert_not_called()
        current.show.assert_called_once_with()
        app.workspace_component.raw_text.assert_not_called()
        self.assertIn("already running", app.status_var.value)

    def test_quit_is_blocked_while_send_to_copy_is_running(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.hotkey = Mock()
        app.instance_server = Mock()
        app.work_item_file_copy = Mock(running=False)
        app.work_item_inbox = Mock(running=False)
        app.file_transfer_window = Mock(busy=True)
        app.status_var = FakeVariable()
        app._finish_protected_clipboard = Mock()

        with patch("context_palette.launcher.messagebox.showwarning") as warning:
            app.quit_app()

        self.assertIn("Send-to file copy", warning.call_args.args[1])
        self.assertIn("Quit blocked", app.status_var.value)
        app._finish_protected_clipboard.assert_not_called()
        app.root.destroy.assert_not_called()

    def test_folder_action_still_opens_normally_outside_send_to(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        action = Action(
            "reports",
            "Reports",
            "General",
            "open_folder",
            r"C:\destination\reports",
        )

        with patch("context_palette.launcher.open_action_target") as opener:
            app._open_action_target(action)

        opener.assert_called_once_with(action)


if __name__ == "__main__":
    unittest.main()
