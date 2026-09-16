from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from context_palette.actions import Action, ActionError
from context_palette.launcher import LauncherApp
from context_palette.resource_operations import EdgeScorePdfRequest, dispatch_resource_operation


class EdgeScorePdfIntegrationTests(unittest.TestCase):
    def app(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.status_var = Mock()
        app.workspace_component = Mock()
        app.source_foreground_handle = 123
        app.edge_score_pdf_settings_path = Path("settings.json")
        return app

    def action(self):
        return Action("score", "Save current score as PDF", "Music", "save_edge_score_pdf", str(Path.cwd() / "scores"))

    def test_action_snapshots_source_and_does_not_read_workspace_or_clipboard(self):
        app = self.app()
        app._workspace_text = Mock(side_effect=AssertionError("No editor read"))
        app._get_clipboard_text = Mock(side_effect=AssertionError("No clipboard read"))
        workflow = Mock(busy=False)
        with patch("context_palette.launcher.EdgeScorePdfWindow", return_value=workflow) as factory:
            self.assertTrue(app._execute_action(self.action()))
        self.assertEqual(factory.call_args.kwargs["source_hwnd"], 123)
        self.assertEqual(factory.call_args.kwargs["destination_folder"], Path(self.action().value))
        self.assertIsNone(app.source_foreground_handle)
        app._workspace_text.assert_not_called()
        app._get_clipboard_text.assert_not_called()
        self.assertEqual(app.workspace_component.mock_calls, [])
        self.assertEqual(app.root.mock_calls, [])
        workflow.show.assert_called_once_with()

    def test_no_captured_window_stops_without_opening_workflow(self):
        app = self.app()
        app.source_foreground_handle = None
        with (
            patch("context_palette.launcher.EdgeScorePdfWindow") as factory,
            patch("context_palette.launcher.messagebox.showerror") as error,
        ):
            self.assertFalse(app._execute_action(self.action()))
        factory.assert_not_called()
        self.assertIn("F9", error.call_args.args[1])

    def test_drop_cannot_dispatch_score_action_even_with_a_captured_window(self):
        app = self.app()
        with (
            patch("context_palette.launcher.EdgeScorePdfWindow") as factory,
            patch("context_palette.launcher.messagebox.showerror"),
        ):
            self.assertFalse(app._execute_action(self.action(), input_snapshot="dropped URL"))
        factory.assert_not_called()

    def test_busy_and_recovery_block_before_dispatch(self):
        for state in ("busy", "recovery"):
            with self.subTest(state=state):
                app = self.app()
                if state == "busy":
                    app.edge_score_pdf_window = Mock(busy=True)
                else:
                    app._configuration_recovery_required = True
                with (
                    patch("context_palette.launcher.EdgeScorePdfWindow") as factory,
                    patch("context_palette.launcher.messagebox.showerror"),
                ):
                    self.assertFalse(app._execute_action(self.action()))
                factory.assert_not_called()

    def test_failed_focus_is_reported_before_renderer_can_start(self):
        app = self.app()
        with patch("context_palette.launcher.focus_window", return_value=False):
            with self.assertRaisesRegex(ActionError, "return to Edge"):
                app._return_to_edge_score(123)

    def test_old_close_callback_does_not_forget_new_window(self):
        app = self.app()
        old, new = Mock(busy=False), Mock(busy=False)
        request = EdgeScorePdfRequest(123, Path.cwd())
        with patch("context_palette.launcher.EdgeScorePdfWindow", side_effect=(old, new)) as factory:
            app._start_edge_score_pdf(request)
            old_close = factory.call_args.kwargs["on_close"]
            app._start_edge_score_pdf(request)
            new_close = factory.call_args.kwargs["on_close"]
        old.close.assert_called_once_with()
        old_close()
        self.assertIs(app.edge_score_pdf_window, new)
        new_close()
        self.assertIsNone(app.edge_score_pdf_window)

    def test_score_worker_blocks_quit(self):
        app = self.app()
        app.edge_score_pdf_window = Mock(busy=True)
        app.work_item_file_copy = Mock(running=False)
        app.work_item_inbox = Mock(running=False)
        with patch("context_palette.launcher.messagebox.showwarning") as warning:
            app.quit_app()
        self.assertIn("Edge score", warning.call_args.args[1])
        app.root.destroy.assert_not_called()

    def test_adapter_is_manual_immutable_and_reports_only_handoff(self):
        request = EdgeScorePdfRequest(123, Path.cwd())
        handler = Mock(return_value="Saving the current Edge score as PDF…")
        other = Mock(side_effect=AssertionError("Wrong adapter"))
        receipt = dispatch_resource_operation(
            request, open_target=other, copy_files=other, excel_workflow=other,
            edge_score_pdf=handler,
        )
        handler.assert_called_once_with(request)
        self.assertEqual(receipt.status, "workflow_started")
        with self.assertRaises(FrozenInstanceError):
            request.source_window_handle = 456

    def test_adapter_rejects_drop_invalid_handle_and_relative_folder(self):
        handler = Mock()
        for request in (
            EdgeScorePdfRequest(123, Path.cwd(), "drop"),
            EdgeScorePdfRequest(0, Path.cwd()),
            EdgeScorePdfRequest(True, Path.cwd()),
            EdgeScorePdfRequest(123, Path("relative")),
        ):
            with self.subTest(request=request), self.assertRaises(ActionError):
                dispatch_resource_operation(
                    request, open_target=handler, copy_files=handler,
                    excel_workflow=handler, edge_score_pdf=handler,
                )
        handler.assert_not_called()


if __name__ == "__main__":
    unittest.main()
