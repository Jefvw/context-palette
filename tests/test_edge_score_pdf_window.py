from __future__ import annotations

from pathlib import Path
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from context_palette.edge_score_pdf import EdgeScorePdfError, EdgeScorePdfManualSave
from context_palette.edge_score_pdf_window import EdgeScorePdfWindow
from context_palette.style import configure_theme


class _Result:
    def __init__(self, path: Path, title: str = "A score") -> None:
        self.destination_path = path
        self.url = "https://tabs.ultimate-guitar.com/tab/example"
        self.title = title


class EdgeScorePdfWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def _wait(self, predicate, timeout: float = 2.0) -> None:
        end = time.monotonic() + timeout
        while not predicate() and time.monotonic() < end:
            self.root.update()
            time.sleep(.01)
        self.root.update()
        self.assertTrue(predicate())

    def test_starts_once_focuses_before_renderer_and_reports_success(self) -> None:
        events: list[str] = []
        statuses: list[str] = []
        def renderer(hwnd, folder, *, cancel_event, progress):
            events.append(f"render:{hwnd}:{folder.name}")
            progress("Edge print preview is ready")
            return _Result(folder / "A score.pdf")
        view = EdgeScorePdfWindow(self.root, source_hwnd=9, destination_folder=Path("C:/scores"), status_setter=statuses.append, on_close=lambda: events.append("close"), on_start=lambda: events.append("focus"), renderer=renderer)
        view.show()
        self._wait(lambda: view.saved_path is not None)
        view.show()
        self.root.update()
        self.assertEqual(events[:2], ["focus", "render:9:scores"])
        self.assertEqual(view.saved_path, Path("C:/scores/A score.pdf"))
        self.assertIn("Saved Edge score as PDF", statuses[-1])
        self.assertTrue(view.open_pdf_button.winfo_ismapped())

    def test_progress_is_delivered_on_tk_thread(self) -> None:
        seen: list[tuple[str, int]] = []
        main = threading.get_ident()
        def renderer(hwnd, folder, *, cancel_event, progress):
            progress("Opening Edge print preview")
            return _Result(folder / "score.pdf")
        view = EdgeScorePdfWindow(self.root, source_hwnd=3, destination_folder=Path("C:/scores"), status_setter=lambda message: seen.append((message, threading.get_ident())), on_close=lambda: None, renderer=renderer)
        view.show()
        self._wait(lambda: view.saved_path is not None)
        self.assertIn(("Opening Edge print preview", main), seen)

    def test_cancel_leaves_truthful_outcome_visible_and_success_wins_race(self) -> None:
        release = threading.Event()
        renderer_started = threading.Event()
        def renderer(hwnd, folder, *, cancel_event, progress):
            renderer_started.set()
            release.wait(1)
            return _Result(folder / "done.pdf")
        view = EdgeScorePdfWindow(self.root, source_hwnd=3, destination_folder=Path("C:/scores"), status_setter=lambda _m: None, on_close=lambda: None, renderer=renderer)
        view.show()
        self._wait(renderer_started.is_set)
        view._request_cancel()
        release.set()
        self._wait(lambda: view.saved_path is not None)
        self.assertIn("Saved Edge score as PDF", view.status_var.get())
        self.assertTrue(view.close_button.instate(("!disabled",)))

    def test_close_waits_for_cleanup_then_calls_on_close_once(self) -> None:
        release = threading.Event()
        closed: list[bool] = []
        def renderer(hwnd, folder, *, cancel_event, progress):
            release.wait(1)
            raise RuntimeError("cleanup complete")
        view = EdgeScorePdfWindow(self.root, source_hwnd=3, destination_folder=Path("C:/scores"), status_setter=lambda _m: None, on_close=lambda: closed.append(True), renderer=renderer)
        view.show()
        self._wait(lambda: view.busy)
        self.assertFalse(view.close())
        self.assertEqual(closed, [])
        release.set()
        self._wait(lambda: closed == [True])

    def test_error_does_not_offer_open_buttons_and_start_failure_clears_busy(self) -> None:
        statuses: list[str] = []
        view = EdgeScorePdfWindow(self.root, source_hwnd=3, destination_folder=Path("C:/scores"), status_setter=statuses.append, on_close=lambda: None, on_start=lambda: (_ for _ in ()).throw(RuntimeError("could not focus Edge")), renderer=lambda *a, **k: None)
        view.show()
        self._wait(lambda: not view.busy)
        self.assertIn("could not focus Edge", statuses[-1])
        self.assertFalse(view.open_pdf_button.winfo_ismapped())

    def test_manual_handoff_closes_without_a_result_popup_or_saved_claim(self) -> None:
        statuses: list[str] = []
        closed: list[bool] = []
        cleaned = threading.Event()
        def renderer(*_args, **_kwargs):
            try:
                raise EdgeScorePdfManualSave("Finish saving in Edge: choose a folder and filename, then select Save.")
            finally:
                cleaned.set()
        view = EdgeScorePdfWindow(self.root, source_hwnd=3, destination_folder=Path("C:/scores"), status_setter=statuses.append, on_close=lambda: closed.append(cleaned.is_set()), renderer=renderer)
        with patch.object(view.window, "deiconify") as show, patch.object(view.window, "lift") as lift:
            view.show()
            self._wait(lambda: view._closed)
        show.assert_not_called()
        lift.assert_not_called()
        self.assertEqual(closed, [True])
        self.assertFalse(view.busy)
        self.assertIsNone(view.saved_path)
        self.assertFalse(view.window.winfo_exists())
        self.assertEqual(statuses[-1], "Finish saving in Edge: choose a folder and filename, then select Save.")
        view.close()
        self.assertEqual(closed, [True])

    def test_ordinary_worker_failure_still_shows_result_window(self) -> None:
        def renderer(*_args, **_kwargs):
            raise EdgeScorePdfError("Could not find the score's PRINT button.")
        view = EdgeScorePdfWindow(self.root, source_hwnd=3, destination_folder=Path("C:/scores"), status_setter=lambda _m: None, on_close=lambda: None, renderer=renderer)
        view.show()
        self._wait(lambda: not view.busy)
        self.assertFalse(view._closed)
        self.assertIn("failed", view.status_var.get())
        self.assertTrue(view.window.winfo_ismapped())
        self.assertFalse(view.open_pdf_button.winfo_ismapped())

    def test_minimum_window_keeps_themed_result_controls_visible_with_long_text(self) -> None:
        configure_theme(self.root)
        folder = Path("C:/scores") / ("very-long-folder-name-" * 16)
        view = EdgeScorePdfWindow(
            self.root,
            source_hwnd=3,
            destination_folder=folder,
            status_setter=lambda _m: None,
            on_close=lambda: None,
            renderer=lambda *_args, **_kwargs: _Result(folder / ("long-score-name-" * 12 + ".pdf")),
        )
        view.window.geometry("520x480+20+20")
        view.show()
        self._wait(lambda: view.saved_path is not None)
        bottom = view.window.winfo_rooty() + view.window.winfo_height()
        for button in (view.open_pdf_button, view.open_folder_button, view.close_button):
            self.assertTrue(button.winfo_ismapped())
            self.assertGreaterEqual(button.winfo_height(), button.winfo_reqheight())
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), bottom)


if __name__ == "__main__":
    unittest.main()
