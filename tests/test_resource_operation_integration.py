from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.actions import (
    Action, ActionError, LIVE_FORMAT_PROFILE_AUTOMATION_ID,
    LIVE_TEXT_CONVERSION_AUTOMATION_ID,
)
from context_palette.excel_automation import EXCEL_AUTOMATION_ID
from context_palette.launcher import LauncherApp
from context_palette.resource_operations import CopyFilesRequest, ExcelWorkflowRequest, FolderResource


class ResourceOperationIntegrationTests(unittest.TestCase):
    def app(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.status_var = Mock()
        app.workspace_component = Mock()
        app.file_transfer_window = None
        app.excel_automation_window = None
        app.excel_automation_settings_path = Path("C:/settings.json")
        app.recent_send_destinations = []
        app._workspace_text = Mock(side_effect=AssertionError("No ambient input reread"))
        return app

    def test_saved_copy_and_send_to_share_the_same_engine_snapshot_and_destination(self):
        text = '  "C:/input/one.txt"\nC:/input/two.txt  '
        destination = FolderResource("folder:reports", "Reports", Path("C:/reports"))
        selected = Action("reports", "Reports", "General", "send_files_to_folder", "C:/reports")
        engine_arguments = []
        for route in ("send_to", "saved_action"):
            app = self.app()
            app.workspace_component.raw_text.return_value = text
            workflow = Mock(busy=False)
            with (
                patch("context_palette.launcher.FileTransferWindow", return_value=workflow) as factory,
                patch("context_palette.launcher.resolve_local_folder_path", return_value=destination.folder_path),
            ):
                if route == "send_to":
                    app._open_send_destination(destination)
                    app.workspace_component.raw_text.assert_called_once_with()
                else:
                    app._run_file_transfer_action(selected, text)
                    app.workspace_component.raw_text.assert_not_called()
            kwargs = factory.call_args.kwargs
            engine_arguments.append(tuple(kwargs[key] for key in (
                "workspace_text", "destination_folder", "destination_label",
            )))
            app.workspace_component.set_text.assert_not_called()
            app.root.clipboard_get.assert_not_called()
            app.root.clipboard_clear.assert_not_called()
            self.assertEqual(app.recent_send_destinations, [])
            self.assertIs(app.file_transfer_window, workflow)
            workflow.show.assert_called_once_with()
        self.assertEqual(engine_arguments[0], engine_arguments[1])
        self.assertEqual(engine_arguments[0], (text, destination.folder_path, "Reports"))

    def test_drop_copy_uses_only_explicit_input_not_current_workspace_or_clipboard(self):
        app = self.app()
        app.workspace_component.raw_text.side_effect = AssertionError("Do not read appended workspace")
        selected = Action("reports", "Reports", "General", "send_files_to_folder", "C:/reports")
        with (
            patch("context_palette.launcher.FileTransferWindow") as factory,
            patch("context_palette.launcher.resolve_local_folder_path", return_value=Path("C:/reports")),
        ):
            message = app._run_file_transfer_action(selected, "C:/only-dropped.txt", dropped=True)
        self.assertEqual(factory.call_args.kwargs["workspace_text"], "C:/only-dropped.txt")
        self.assertIn("Preparing", message)
        app.workspace_component.raw_text.assert_not_called()
        app.root.clipboard_get.assert_not_called()
        self.assertEqual(app.recent_send_destinations, [])

    def test_saved_action_execution_preserves_the_same_raw_copy_snapshot_as_send_to(self):
        app = self.app()
        snapshot = '  "C:/input/one.txt"\r\nC:/input/two.txt  '
        app.workspace_component.raw_text.return_value = snapshot
        app._workspace_text = Mock(return_value=snapshot.strip())
        app.source_foreground_handle = None
        app.captured_selection = "old selection"
        app._set_clipboard = Mock()
        app._get_clipboard_text = Mock(side_effect=AssertionError("No clipboard read"))
        app._ask_for_action_input = Mock(side_effect=AssertionError("No prompt"))
        app._set_workspace_text = Mock()
        app._run_file_transfer_action = Mock(return_value="Preparing file copy")
        selected = Action("reports", "Reports", "General", "send_files_to_folder", "C:/reports")
        self.assertTrue(app._execute_action(selected))
        self.assertEqual(app._run_file_transfer_action.call_args.args[1], snapshot)
        self.assertFalse(app._run_file_transfer_action.call_args.kwargs["dropped"])
        app._set_clipboard.assert_not_called()
        app._get_clipboard_text.assert_not_called()
        app._set_workspace_text.assert_not_called()

    def test_saved_copy_preview_never_opens_a_workflow_or_reads_external_content(self):
        app = self.app()
        selected = Action("reports", "Reports", "General", "send_files_to_folder", "C:/reports")
        app._selected_work_item = Mock(return_value=None)
        app._selected_action = Mock(return_value=selected)
        app._workspace_text = Mock(return_value="C:/input.txt")
        app.workspace_component.raw_text.return_value = "C:/input.txt"
        app.captured_selection = "irrelevant selection"
        app.source_foreground_handle = None
        app.actions = [selected]
        app._get_clipboard_text = Mock(side_effect=AssertionError("No clipboard read"))
        app._dispatch_resource_operation = Mock(side_effect=AssertionError("Preview must not dispatch"))
        app._show_execution_preview = Mock()
        with (
            patch("context_palette.launcher.FileTransferWindow") as factory,
            patch.object(Path, "read_bytes", side_effect=AssertionError("No external read")),
        ):
            app._preview_selected()
        factory.assert_not_called()
        app._dispatch_resource_operation.assert_not_called()
        app._get_clipboard_text.assert_not_called()
        report = app._show_execution_preview.call_args.args[1]
        self.assertIn("C:/input.txt", report)
        self.assertIn("C:/reports", report)
        self.assertIn("does not inspect or copy files", report)

    def test_drop_does_not_close_even_an_idle_copy_review(self):
        app = self.app()
        existing = Mock(busy=False)
        existing.window.winfo_exists.return_value = True
        app.file_transfer_window = existing
        request = CopyFilesRequest(FolderResource("folder:r", "Reports", Path("C:/reports")), "C:/input.txt", "drop")
        with patch("context_palette.launcher.FileTransferWindow") as factory:
            with self.assertRaisesRegex(ActionError, "review is already open"):
                app._dispatch_resource_operation(request)
        factory.assert_not_called()
        existing.show.assert_called_once_with()
        existing.close.assert_not_called()
        self.assertIs(app.file_transfer_window, existing)

    def test_copy_handoff_only_records_recent_destination_after_success_callback(self):
        app = self.app()
        destination = FolderResource("folder:r", "Reports", Path("C:/reports"))
        workflow = Mock(busy=False)
        with patch("context_palette.launcher.FileTransferWindow", return_value=workflow) as factory:
            receipt = app._dispatch_resource_operation(CopyFilesRequest(destination, "C:/input.txt"))
        self.assertEqual(receipt.status, "workflow_started")
        self.assertEqual(app.recent_send_destinations, [])
        factory.call_args.kwargs["on_success"](destination.folder_path)
        self.assertEqual(len(app.recent_send_destinations), 1)
        self.assertEqual(app.recent_send_destinations[0].folder_path, destination.folder_path)

    def test_old_copy_close_callback_cannot_clear_a_new_workflow(self):
        app = self.app()
        first = Mock(busy=False)
        newer = Mock(busy=False)
        request = CopyFilesRequest(FolderResource("folder:r", "Reports", Path("C:/reports")), "C:/input.txt")
        with patch("context_palette.launcher.FileTransferWindow", return_value=first) as factory:
            app._dispatch_resource_operation(request)
        app.file_transfer_window = newer
        factory.call_args.kwargs["on_close"]()
        self.assertIs(app.file_transfer_window, newer)

    def test_drop_csv_keeps_exact_snapshot_and_existing_review(self):
        app = self.app()
        selected = Action("csv", "Export CSV", "General", "excel_automation", EXCEL_AUTOMATION_ID)
        with (
            patch("context_palette.launcher.workbook_paths_from_workspace", return_value=(Path("C:/one.xlsx"),)) as parse,
            patch("context_palette.launcher.ExcelAutomationWindow") as factory,
        ):
            message = app._run_excel_automation(selected, workspace_snapshot='"C:/one.xlsx"')
        parse.assert_called_once_with('"C:/one.xlsx"')
        self.assertEqual(factory.call_args.kwargs["workbooks"], (Path("C:/one.xlsx"),))
        self.assertIn("Opened reviewed", message)
        app._workspace_text.assert_not_called()
        old = app.excel_automation_window
        with self.assertRaisesRegex(ActionError, "review is already open"):
            app._run_excel_automation(selected, workspace_snapshot="C:/two.xlsx")
        old.show.assert_called_once_with()
        old.close.assert_not_called()

    def test_live_excel_keeps_captured_metadata_and_host_uat_gate(self):
        for operation, window_name in (
            (LIVE_FORMAT_PROFILE_AUTOMATION_ID, "ExcelLiveFormatWindow"),
            (LIVE_TEXT_CONVERSION_AUTOMATION_ID, "ExcelLiveTextConversionWindow"),
        ):
            for enabled in (False, True):
                with self.subTest(operation=operation, enabled=enabled):
                    app = self.app()
                    app.live_text_conversion_execution_enabled = enabled
                    selected = Action("live", "Live Excel", "General", "excel_automation", operation)
                    with (
                        patch("context_palette.launcher." + window_name) as factory,
                        patch("context_palette.launcher.window_process_id", return_value=7),
                        patch("context_palette.launcher.window_title", return_value="Book.xlsx - Excel"),
                    ):
                        app._run_excel_automation(selected, source_window_handle=123)
                    kwargs = factory.call_args.kwargs
                    self.assertEqual(kwargs["source_window_handle"], 123)
                    self.assertEqual(kwargs["source_process_id"], 7)
                    self.assertEqual(kwargs["source_window_title"], "Book.xlsx - Excel")
                    if operation == LIVE_TEXT_CONVERSION_AUTOMATION_ID:
                        self.assertIs(kwargs["execution_enabled"], enabled)
                        self.assertEqual(kwargs["file_opener"], app._open_excel_recovery_file)
                    app._workspace_text.assert_not_called()

    def test_live_excel_drop_request_cannot_start_a_workflow(self):
        app = self.app()
        selected = Action("live", "Live Excel", "General", "excel_automation", LIVE_FORMAT_PROFILE_AUTOMATION_ID)
        with patch("context_palette.launcher.ExcelLiveFormatWindow") as factory:
            with self.assertRaisesRegex(ActionError, "run them from the Palette"):
                app._dispatch_resource_operation(ExcelWorkflowRequest(selected, invocation="drop"))
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
