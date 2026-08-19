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
    FOCUS_SLOT_ROW_TAG,
    PINNED_SLOT_ROW_TAG,
    slot_row_tag,
    visible_result_row_count,
)
from context_palette.command_surface import CommandGroup, CommandItem
from context_palette.contexts import ContextDefinition, ContextError
from context_palette.launcher import (
    LauncherApp,
    bounded_sash_position,
    quick_action_column_count,
)
from context_palette.ocr import OcrResult, OcrSource
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
from context_palette.work_items import DiscoveredWorkItem, WorkItemReference


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
        app._load_actions = Mock()
        app._load_command_surface = Mock()
        app._load_contexts = Mock()
        app._load_work_item_configuration = Mock()
        app._load_palette_state = Mock()
        app._render_command_surface = Mock()
        app._refresh_results = Mock()
        app._start_work_item_refresh = Mock()
        app._configuration_signature = Mock(return_value=(("test", 1, 1),))

        app._reload()

        app._load_actions.assert_called_once_with()
        app._load_command_surface.assert_called_once_with(render=False)
        app._load_contexts.assert_called_once_with()
        app._load_work_item_configuration.assert_called_once_with()
        app._load_palette_state.assert_called_once_with(render=False)
        app._render_command_surface.assert_called_once_with()
        app._refresh_results.assert_called_once_with()
        app._start_work_item_refresh.assert_called_once_with()
        self.assertEqual(app.configuration_signature_cache, (("test", 1, 1),))

    def test_inbox_is_loaded_from_storage_each_time_it_is_opened(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.inbox_path = Path("inbox.json")
        app.actions = []
        app.palette_state = PaletteState()
        app.available_context_names = []
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

    def test_shift_number_executes_slot_for_azerty_find_input(self):
        app = LauncherApp.__new__(LauncherApp)
        app.search_entry = object()
        app.root = Mock()
        app.root.focus_get.return_value = app.search_entry
        app._execute_slot = Mock(return_value="break")
        event = FakeKeyEvent(state=0x0001, keysym="2", keycode=50)

        self.assertEqual(app._handle_keypress(event), "break")
        app._execute_slot.assert_called_once_with(2, event)

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
            ("ampersand", 1),
            ("eacute", 2),
            ("quotedbl", 3),
            ("apostrophe", 4),
            ("parenleft", 5),
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

    def test_visible_result_rows_adapt_to_text_scaling(self):
        self.assertEqual(visible_result_row_count(1.333), 7)
        self.assertEqual(visible_result_row_count(1.667), 6)
        self.assertEqual(visible_result_row_count(2.0), 5)

    def test_slot_row_tags_distinguish_shortcut_groups_without_number_labels(self):
        for slot in range(1, 6):
            self.assertEqual(slot_row_tag(slot), PINNED_SLOT_ROW_TAG)
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

    def test_focus_actions_button_toggles_focus_mode_and_visual_state(self):
        app = LauncherApp.__new__(LauncherApp)
        app.focus_actions_mode = False
        app.focus_actions_button = FakeButton()
        app.root = Mock()
        scope_changes: list[str] = []
        refreshes: list[bool] = []
        app._select_discovery_scope = scope_changes.append
        app._refresh_results = lambda: refreshes.append(True)

        app._activate_focus_actions()

        self.assertTrue(app.focus_actions_mode)
        self.assertEqual(app.focus_actions_button.options["style"], "RailAccent.TButton")

        app._activate_focus_actions()

        self.assertFalse(app.focus_actions_mode)
        self.assertEqual(app.focus_actions_button.options["style"], "Compact.TButton")
        self.assertEqual(scope_changes, ["all", "all"])
        self.assertEqual(refreshes, [True, True])
        self.assertEqual(app.root.after_idle.call_count, 2)

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

    def test_f5_reset_clears_transient_state_but_preserves_palette_state(self):
        app = LauncherApp.__new__(LauncherApp)
        app.focus_actions_mode = True
        app.action_type_filter = "open_url"
        app.action_tag_filter = "database"
        app.work_project_filter = "AB9C"
        app.work_tag_filter = "urgent"
        app.item_tag_filter = "urgent"
        app.item_context_filter = "Database"
        app.action_type_filter_var = FakeVariable()
        app.action_tag_filter_var = FakeVariable()
        app.item_tag_filter_var = FakeVariable()
        app.item_context_filter_var = FakeVariable()
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
        self.assertIsNone(app.work_project_filter)
        self.assertIsNone(app.work_tag_filter)
        self.assertIsNone(app.item_tag_filter)
        self.assertIsNone(app.item_context_filter)
        self.assertEqual(app.action_type_filter_var.value, "All types")
        self.assertEqual(app.action_tag_filter_var.value, "All tags")
        self.assertEqual(app.item_tag_filter_var.value, "All tags")
        self.assertEqual(app.item_context_filter_var.value, "All contexts")
        self.assertEqual(app.passwords_button.options["style"], "RailIcon.TButton")
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
                "Active",
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


if __name__ == "__main__":
    unittest.main()
