from __future__ import annotations

from dataclasses import FrozenInstanceError
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
from context_palette.resource_operations import (
    CopyFilesRequest, ExcelWorkflowRequest, FolderResource, OpenTargetRequest,
    dispatch_resource_operation,
)


def action(kind: str, value: str) -> Action:
    return Action("operation-test", "Operation test", "General", kind, value)


class ResourceOperationTests(unittest.TestCase):
    def setUp(self):
        self.destination = FolderResource("folder:reports", "Reports", Path("C:/reports"))
        self.open = Mock()
        self.copy = Mock(return_value="Preparing the file copy")
        self.excel = Mock(return_value="Opened the Excel review")

    def dispatch(self, request):
        return dispatch_resource_operation(
            request, open_target=self.open, copy_files=self.copy,
            excel_workflow=self.excel,
        )

    def test_open_routes_the_same_expanded_action_without_reexpanding(self):
        selected = action("open_url", "https://example.com/%CLIPBOARD%")
        with patch("context_palette.actions.expanded_action", side_effect=AssertionError("Do not expand twice")):
            result = self.dispatch(OpenTargetRequest(selected))
        self.open.assert_called_once_with(selected)
        self.assertIs(self.open.call_args.args[0], selected)
        self.copy.assert_not_called()
        self.excel.assert_not_called()
        self.assertEqual(result.status, "opened")
        self.assertIn("handler", result.message)

    def test_copy_preserves_exact_snapshot_and_returns_handoff_not_completion(self):
        snapshot = '  "C:\\input\\one.txt"\r\nC:\\input\\two.txt  '
        request = CopyFilesRequest(self.destination, snapshot, "drop")
        result = self.dispatch(request)
        self.copy.assert_called_once_with(request)
        self.assertIs(self.copy.call_args.args[0], request)
        self.assertEqual(self.copy.call_args.args[0].input_text, snapshot)
        self.open.assert_not_called()
        self.excel.assert_not_called()
        self.assertEqual(result.status, "workflow_started")
        self.assertEqual(result.message, "Preparing the file copy")

    def test_csv_preserves_exact_request_without_reading_a_workbook(self):
        request = ExcelWorkflowRequest(
            action("excel_automation", EXCEL_AUTOMATION_ID),
            '"C:/input/book.xlsx"', "drop",
        )
        with patch.object(Path, "read_bytes", side_effect=AssertionError("No file read")):
            result = self.dispatch(request)
        self.excel.assert_called_once_with(request)
        self.open.assert_not_called()
        self.copy.assert_not_called()
        self.assertEqual(result.status, "workflow_started")

    def test_live_excel_passes_only_host_supplied_window_reference(self):
        for operation in (LIVE_FORMAT_PROFILE_AUTOMATION_ID, LIVE_TEXT_CONVERSION_AUTOMATION_ID):
            with self.subTest(operation=operation):
                self.excel.reset_mock()
                request = ExcelWorkflowRequest(
                    action("excel_automation", operation), source_window_handle=812,
                )
                result = self.dispatch(request)
                self.excel.assert_called_once_with(request)
                self.assertIsNone(request.input_text)
                self.assertEqual(request.source_window_handle, 812)
                self.assertEqual(result.status, "workflow_started")

    def test_malformed_combinations_fail_before_any_effect_callback(self):
        csv = action("excel_automation", EXCEL_AUTOMATION_ID)
        live = action("excel_automation", LIVE_FORMAT_PROFILE_AUTOMATION_ID)
        cases = (
            object(),
            OpenTargetRequest(action("copy_text", "not an open operation")),
            CopyFilesRequest(self.destination, ""),
            CopyFilesRequest(self.destination, " \n\t"),
            CopyFilesRequest(self.destination, None),
            CopyFilesRequest(self.destination, "C:/input.txt", "other"),
            ExcelWorkflowRequest(action("open_url", "https://example.com")),
            ExcelWorkflowRequest(action("excel_automation", "unknown.operation")),
            ExcelWorkflowRequest(csv),
            ExcelWorkflowRequest(csv, "C:/book.xlsx", "other"),
            ExcelWorkflowRequest(csv, "C:/book.xlsx", "drop", 123),
            ExcelWorkflowRequest(live, "C:/book.xlsx"),
            ExcelWorkflowRequest(live, invocation="drop"),
        )
        for request in cases:
            with self.subTest(request=request), self.assertRaises(ActionError):
                self.dispatch(request)
        self.open.assert_not_called()
        self.copy.assert_not_called()
        self.excel.assert_not_called()

    def test_adapter_failure_propagates_once_without_retry_or_success_receipt(self):
        self.copy.side_effect = ActionError("Existing copy review is still open")
        with self.assertRaisesRegex(ActionError, "review"):
            self.dispatch(CopyFilesRequest(self.destination, "C:/input.txt", "drop"))
        self.copy.assert_called_once()
        self.open.assert_not_called()
        self.excel.assert_not_called()

    def test_requests_and_destination_are_immutable(self):
        request = CopyFilesRequest(self.destination, "C:/input.txt")
        with self.assertRaises(FrozenInstanceError):
            request.input_text = "C:/different.txt"
        with self.assertRaises(FrozenInstanceError):
            request.destination.folder_path = Path("C:/different")


if __name__ == "__main__":
    unittest.main()
