from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from context_palette.webpage_pdf_window import WebpagePdfWindow
from context_palette.style import configure_theme


class WebpagePdfWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.geometry("1x1+0+0")
        self.root.update_idletasks()
        self.addCleanup(self.root.destroy)
        self.destination = Path("C:/temporary/output.pdf")
        self.statuses: list[tuple[int, str]] = []
        self.on_close = Mock()
        self.windows: list[WebpagePdfWindow] = []

    def _window(
        self,
        renderer,
        *,
        url="https://example.com/report?month=9",
        destination: Path | None = None,
        **kwargs,
    ) -> WebpagePdfWindow:
        window = WebpagePdfWindow(
            self.root,
            url=url,
            destination=destination or self.destination,
            status_setter=lambda message: self.statuses.append(
                (threading.get_ident(), message)
            ),
            on_close=self.on_close,
            renderer=renderer,
            **kwargs,
        )
        self.windows.append(window)
        self.addCleanup(self._close, window)
        return window

    def _close(self, window: WebpagePdfWindow) -> None:
        if not window._closed and window.window.winfo_exists():
            window.close()
            self._wait_until(lambda: window._closed, timeout=1)

    def _wait_until(self, predicate, *, timeout: float = 2) -> None:
        deadline = time.monotonic() + timeout
        while not predicate():
            self.root.update()
            if time.monotonic() >= deadline:
                self.fail("Timed out waiting for the webpage PDF window")
            time.sleep(0.005)
        self.root.update()

    def test_show_starts_one_worker_and_success_exposes_exact_result_actions(self) -> None:
        calls: list[tuple[str, Path, threading.Event]] = []
        file_opener = Mock()
        folder_opener = Mock()

        def renderer(url, destination, *, cancel_event):
            calls.append((url, destination, cancel_event))
            return destination

        window = self._window(
            renderer, file_opener=file_opener, folder_opener=folder_opener
        )
        window.show()
        self.assertTrue(window.busy)
        window.show()
        self._wait_until(lambda: window.saved_path is not None)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "https://example.com/report?month=9")
        self.assertEqual(calls[0][1], self.destination)
        self.assertEqual(window.saved_path, self.destination)
        self.assertTrue(window.open_pdf_button.winfo_ismapped())
        self.assertTrue(window.open_folder_button.winfo_ismapped())
        self.assertIn(str(self.destination), window.status_var.get())

        window.open_pdf_button.invoke()
        window.open_folder_button.invoke()
        file_opener.assert_called_once_with(self.destination)
        folder_opener.assert_called_once_with(self.destination.parent)

    def test_worker_never_calls_tk_or_status_and_busy_covers_scheduled_start(self) -> None:
        worker_ids: list[int] = []

        def renderer(_url, destination, *, cancel_event):
            worker_ids.append(threading.get_ident())
            return destination

        window = self._window(renderer)
        window.show()
        self.assertTrue(window.busy)
        self._wait_until(lambda: window.saved_path is not None)

        self.assertEqual(len(worker_ids), 1)
        self.assertNotEqual(worker_ids[0], threading.get_ident())
        self.assertTrue(self.statuses)
        self.assertEqual({thread_id for thread_id, _message in self.statuses}, {threading.get_ident()})

    def test_close_during_scheduled_start_cancels_without_launching_renderer(self) -> None:
        renderer = Mock(return_value=self.destination)
        window = self._window(renderer)
        window.show()
        self.assertTrue(window.busy)

        self.assertFalse(window.close())
        self.assertTrue(window._cancel_event.is_set())
        self._wait_until(lambda: window._closed)

        renderer.assert_not_called()
        self.on_close.assert_called_once_with()
        self.assertIn("cancelled", self.statuses[-1][1].casefold())

    def test_close_requests_cancel_but_truthfully_reports_a_success_race(self) -> None:
        started = threading.Event()
        release = threading.Event()

        def renderer(_url, destination, *, cancel_event):
            started.set()
            release.wait(1)
            # Simulates a renderer that completed just after cancellation.
            return destination

        window = self._window(renderer)
        window.show()
        self._wait_until(started.is_set)

        self.assertFalse(window.close())
        self.assertTrue(window._cancel_event.is_set())
        self.assertTrue(window.window.winfo_exists())
        release.set()
        self._wait_until(lambda: window._closed)

        self.assertTrue(any("Saved webpage as PDF" in message for _, message in self.statuses))
        self.assertFalse(any("was cancelled" in message for _, message in self.statuses[-1:]))
        self.on_close.assert_called_once_with()

    def test_cancel_keeps_a_cancelled_outcome_visible_until_close(self) -> None:
        started = threading.Event()

        def renderer(_url, _destination, *, cancel_event):
            started.set()
            self.assertTrue(cancel_event.wait(1))
            raise RuntimeError("renderer cancelled")

        window = self._window(renderer)
        window.show()
        self._wait_until(started.is_set)
        window.cancel_button.invoke()
        self._wait_until(lambda: not window.busy)

        self.assertFalse(window._closed)
        self.assertTrue(window.window.winfo_exists())
        self.assertIn("cancelled", window.status_var.get().casefold())
        self.assertIn("Saving cancelled", " ".join(_widget_texts(window.content)))
        self.assertTrue(window.close_button.instate(["!disabled"]))

    def test_thread_start_failure_clears_busy_and_reports_error(self) -> None:
        window = self._window(lambda _url, destination, *, cancel_event: destination)
        with patch("context_palette.webpage_pdf_window.threading.Thread") as thread:
            thread.return_value.start.side_effect = RuntimeError("Cannot start worker")
            window.show()
            self._wait_until(lambda: not window.busy)

        self.assertIn("Cannot start worker", window.status_var.get())
        self.assertFalse(window.open_pdf_button.winfo_ismapped())
        self.assertTrue(window.close_button.instate(["!disabled"]))

    def test_error_clears_busy_and_keeps_an_honest_error_state(self) -> None:
        def renderer(_url, _destination, *, cancel_event):
            raise RuntimeError("Browser renderer exited without a PDF.")

        window = self._window(renderer)
        window.show()
        self._wait_until(lambda: not window.busy)

        self.assertIsNone(window.saved_path)
        self.assertTrue(window.close_button.instate(["!disabled"]))
        self.assertFalse(window.open_pdf_button.winfo_ismapped())
        self.assertIn("failed", window.status_var.get().casefold())
        content = " ".join(_widget_texts(window.content))
        self.assertIn("PDF was not saved", content)
        self.assertIn("Browser renderer exited", content)

    def test_open_failures_leave_the_saved_receipt_visible(self) -> None:
        file_opener = Mock(side_effect=OSError("No PDF association"))
        folder_opener = Mock(side_effect=OSError("Explorer unavailable"))
        window = self._window(
            lambda _url, destination, *, cancel_event: destination,
            file_opener=file_opener,
            folder_opener=folder_opener,
        )
        window.show()
        self._wait_until(lambda: window.saved_path is not None)

        window.open_pdf_button.invoke()
        self.assertEqual(window.saved_path, self.destination)
        self.assertIn(str(self.destination), window.status_var.get())
        self.assertTrue(window.open_pdf_button.winfo_ismapped())

        window.open_folder_button.invoke()
        self.assertEqual(window.saved_path, self.destination)
        self.assertIn("Could not open the PDF folder", window.status_var.get())
        self.assertTrue(window.open_folder_button.winfo_ismapped())

    def test_long_url_reflows_at_minimum_width_without_hiding_result_controls(self) -> None:
        url = "https://example.com/report?" + "filter=important-value&" * 280
        calls: list[str] = []

        def renderer(render_url, destination, *, cancel_event):
            calls.append(render_url)
            return destination

        configure_theme(self.root)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / ("webpage-report-" + "x" * 120 + ".pdf")
            window = self._window(renderer, url=url, destination=destination)
            window.window.geometry("520x480+20+20")
            window.show()
            self._wait_until(lambda: window.saved_path is not None)
            self.root.update()

            shown_url = next(
                label.cget("text") for label in window._wrapping_labels
                if label.winfo_exists() and "[display shortened]" in str(label.cget("text"))
            )
            self.assertIn("[display shortened]", shown_url)
            self.assertEqual(len(shown_url), 200)
            self.assertEqual(calls, [url])
            self.assertEqual(window.saved_path, destination)
            bottom = window.window.winfo_rooty() + window.window.winfo_height()
            for button in (window.open_pdf_button, window.open_folder_button, window.close_button):
                self.assertTrue(button.winfo_ismapped())
                self.assertGreaterEqual(button.winfo_height(), button.winfo_reqheight())
                self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), bottom)

    def test_close_callback_runs_once_after_a_normal_result(self) -> None:
        window = self._window(lambda _url, destination, *, cancel_event: destination)
        window.show()
        self._wait_until(lambda: window.saved_path is not None)

        self.assertTrue(window.close())
        self.assertTrue(window.close())
        self.on_close.assert_called_once_with()


def _widget_texts(widget: tk.Misc) -> list[str]:
    values: list[str] = []
    for child in widget.winfo_children():
        try:
            value = child.cget("text")
        except tk.TclError:
            value = ""
        if value:
            values.append(str(value))
        values.extend(_widget_texts(child))
    return values


if __name__ == "__main__":
    unittest.main()
