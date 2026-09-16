from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.actions import ActionError
from context_palette.launcher import LauncherApp
from context_palette.resource_operations import WebpagePdfRequest, dispatch_resource_operation


class WebpagePdfIntegrationTests(unittest.TestCase):
    def app(self, text="https://example.com/article?q=one&two=2#section"):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.status_var = Mock()
        app.workspace_component = Mock()
        app.workspace_component.raw_text.return_value = text
        app.webpage_pdf_window = None
        return app

    def test_url_menu_offers_pdf_without_mislabeling_url_as_a_file(self):
        app = self.app("  HTTPS://example.com/article  ")
        menu = Mock()
        app._save_workspace_webpage_as_pdf = Mock()
        app._populate_send_to_menu(menu)
        menu.add_command.assert_called_once_with(
            label="Save webpage as PDF…", command=app._save_workspace_webpage_as_pdf
        )
        app._save_workspace_webpage_as_pdf.assert_not_called()
        app.root.clipboard_get.assert_not_called()

    def test_picker_uses_original_complete_url_and_never_changes_workspace_or_clipboard(self):
        url = "https://example.com/one?q=1&x=2#part"
        app = self.app(" \n" + url + "\n ")
        destination = ROOT / "chosen.pdf"
        window = Mock(busy=True)

        def choose(**_kwargs):
            app.workspace_component.raw_text.return_value = "https://example.com/changed"
            return str(destination)

        with (
            patch("context_palette.launcher.filedialog.asksaveasfilename", side_effect=choose) as picker,
            patch("context_palette.launcher.WebpagePdfWindow", return_value=window) as factory,
        ):
            app._save_workspace_webpage_as_pdf()
        self.assertEqual(factory.call_args.kwargs["url"], url)
        self.assertEqual(factory.call_args.kwargs["destination"], destination)
        self.assertFalse(picker.call_args.kwargs["confirmoverwrite"])
        window.show.assert_called_once_with()
        self.assertIs(app.webpage_pdf_window, window)
        self.assertEqual([call[0] for call in app.workspace_component.mock_calls], ["raw_text"])
        self.assertEqual(app.root.mock_calls, [])
        app.status_var.set.assert_called_with("Creating webpage PDF…")

    def test_invalid_input_stops_before_picker_or_render(self):
        for text in ("", "relative/address", "file:///C:/secret.txt", "https://one.test\nhttps://two.test"):
            with self.subTest(text=text):
                app = self.app(text)
                with (
                    patch("context_palette.launcher.filedialog.asksaveasfilename") as picker,
                    patch("context_palette.launcher.WebpagePdfWindow") as factory,
                    patch("context_palette.launcher.messagebox.showerror") as error,
                ):
                    app._save_workspace_webpage_as_pdf()
                picker.assert_not_called()
                factory.assert_not_called()
                error.assert_called_once()

    def test_cancel_picker_performs_no_dispatch(self):
        app = self.app()
        app._dispatch_resource_operation = Mock()
        with patch("context_palette.launcher.filedialog.asksaveasfilename", return_value=""):
            app._save_workspace_webpage_as_pdf()
        app._dispatch_resource_operation.assert_not_called()
        app.status_var.set.assert_not_called()

    def test_busy_window_rejects_new_input_before_read_or_picker(self):
        app = self.app()
        current = Mock(busy=True)
        app.webpage_pdf_window = current
        with (
            patch("context_palette.launcher.filedialog.asksaveasfilename") as picker,
            patch("context_palette.launcher.messagebox.showerror"),
        ):
            app._save_workspace_webpage_as_pdf()
        current.show.assert_called_once_with()
        current.close.assert_not_called()
        app.workspace_component.raw_text.assert_not_called()
        picker.assert_not_called()

    def test_old_window_callback_cannot_forget_replacement(self):
        app = self.app()
        first, second = Mock(busy=False), Mock(busy=False)
        request = WebpagePdfRequest("https://example.com", ROOT / "chosen.pdf")
        with patch("context_palette.launcher.WebpagePdfWindow", side_effect=(first, second)) as factory:
            app._dispatch_resource_operation(request)
            first_close = factory.call_args.kwargs["on_close"]
            app._dispatch_resource_operation(request)
            second_close = factory.call_args.kwargs["on_close"]
        first.close.assert_called_once_with()
        first_close()
        self.assertIs(app.webpage_pdf_window, second)
        second_close()
        self.assertIsNone(app.webpage_pdf_window)

    def test_pdf_worker_blocks_quit_until_completion(self):
        app = self.app()
        app.webpage_pdf_window = Mock(busy=True)
        app.work_item_file_copy = Mock(running=False)
        app.work_item_inbox = Mock(running=False)
        app._finish_protected_clipboard = Mock()
        with patch("context_palette.launcher.messagebox.showwarning") as warning:
            app.quit_app()
        self.assertIn("webpage PDF", warning.call_args.args[1])
        app.root.destroy.assert_not_called()
        app._finish_protected_clipboard.assert_not_called()
        app.webpage_pdf_window.busy = False
        self.assertEqual(app._active_webpage_pdf_operations(), ())

    def test_adapter_preserves_snapshot_and_returns_only_handoff(self):
        request = WebpagePdfRequest("https://example.com/?x=1&y=2", ROOT / "chosen.pdf")
        handler = Mock(return_value="Creating webpage PDF…")
        other = Mock(side_effect=AssertionError("Wrong operation"))
        receipt = dispatch_resource_operation(
            request, open_target=other, copy_files=other, excel_workflow=other, webpage_pdf=handler
        )
        handler.assert_called_once_with(request)
        self.assertIs(handler.call_args.args[0], request)
        self.assertEqual(receipt.status, "workflow_started")
        self.assertNotIn("saved", receipt.message.casefold())
        with self.assertRaises(FrozenInstanceError):
            request.input_text = "changed"

    def test_adapter_rejects_drop_invalid_input_and_missing_handler_without_effects(self):
        handler = Mock()
        for request in (
            WebpagePdfRequest("https://example.com", ROOT / "chosen.pdf", "drop"),
            WebpagePdfRequest("file:///C:/secret.txt", ROOT / "chosen.pdf"),
        ):
            with self.subTest(request=request), self.assertRaises(ActionError):
                dispatch_resource_operation(
                    request, open_target=handler, copy_files=handler,
                    excel_workflow=handler, webpage_pdf=handler,
                )
        with self.assertRaisesRegex(ActionError, "unavailable"):
            dispatch_resource_operation(
                WebpagePdfRequest("https://example.com", ROOT / "chosen.pdf"),
                open_target=handler, copy_files=handler, excel_workflow=handler,
            )
        handler.assert_not_called()


if __name__ == "__main__":
    unittest.main()
