"""Attended window for saving the captured Ultimate Guitar Edge score."""

from __future__ import annotations

from pathlib import Path
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

from .edge_score_pdf import EdgeScorePdfManualSave
from .window_geometry import configure_standard_window


_POLL_MILLISECONDS = 50
Renderer = Callable[..., object]
PathOpener = Callable[[Path], None]


class EdgeScorePdfWindow:
    """Present one visible, attended Edge score export without driving Edge here."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        source_hwnd: int,
        destination_folder: Path,
        status_setter: Callable[[str], None],
        on_close: Callable[[], None],
        on_start: Callable[[], None] | None = None,
        renderer: Renderer | None = None,
        file_opener: PathOpener | None = None,
        folder_opener: PathOpener | None = None,
    ) -> None:
        self.source_hwnd = source_hwnd
        self.destination_folder = Path(destination_folder)
        self.status_setter = status_setter
        self.on_close = on_close
        self.on_start = on_start
        self.renderer = renderer or _default_renderer
        self.file_opener = file_opener or _open_path
        self.folder_opener = folder_opener or _open_path
        self._results: queue.Queue[tuple[str, object]] = queue.Queue()
        self._cancel_event = threading.Event()
        self._started = self._start_queued = self._starting_worker = False
        self._worker_running = self._cancel_requested = self._close_requested = False
        self._closed = False
        self._poll_after_id: str | None = None
        self._start_after_id: str | None = None
        self.saved_path: Path | None = None
        self._wrapping_labels: list[ttk.Label] = []

        self.window = tk.Toplevel(parent)
        self.window.title("Save Edge score as PDF")
        configure_standard_window(self.window, parent)
        self.window.minsize(520, 480)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.bind("<Configure>", self._update_wraplength)
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        ttk.Label(outer, text="Save Edge score as PDF", style="Title.TLabel").pack(
            anchor=tk.W
        )
        self._wrapped_label(
            outer,
            text=(
                "Prints the current Official score or Guitar Pro tab in Microsoft Edge. "
                "If Save As stays open, choose your folder and filename and save in Edge."
            ),
            style="Muted.TLabel",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(2, 8))
        ttk.Label(outer, text="PDF folder", style="Heading.TLabel").pack(anchor=tk.W)
        self._wrapped_label(outer, text=str(self.destination_folder), justify=tk.LEFT).pack(anchor=tk.W, pady=(1, 8))
        self.content = ttk.Frame(outer)
        self.status_var = tk.StringVar(value="Preparing to save the current Edge score as a PDF.")
        self.status_label = self._wrapped_label(
            outer, textvariable=self.status_var, style="Status.TLabel", justify=tk.LEFT
        )
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        self.footer = ttk.Frame(outer)
        self.footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        self.cancel_button = ttk.Button(self.footer, text="Cancel", command=self._request_cancel)
        self.open_pdf_button = ttk.Button(self.footer, text="Open PDF", command=self._open_pdf)
        self.open_folder_button = ttk.Button(self.footer, text="Open folder", command=self._open_folder)
        self.close_button = ttk.Button(self.footer, text="Close", command=self.close)
        self.close_button.pack(side=tk.RIGHT)
        self.progress = ttk.Progressbar(self.content, mode="indeterminate")
        self.content.pack(fill=tk.BOTH, expand=True)

    @property
    def busy(self) -> bool:
        return self._start_queued or self._starting_worker or self._worker_running

    def show(self) -> None:
        if self._closed:
            return
        if self._started:
            return
        self._started = self._start_queued = True
        self._show_working("Preparing the Edge score export…")
        self._start_after_id = self.window.after_idle(self._start_worker)

    def close(self) -> bool:
        if self._closed:
            return True
        if self.busy:
            self._close_requested = True
            self._request_cancel()
            return False
        self._closed = True
        for after_id in (self._start_after_id, self._poll_after_id):
            if after_id:
                try:
                    self.window.after_cancel(after_id)
                except tk.TclError:
                    pass
        try:
            self.window.destroy()
        finally:
            self.on_close()
        return True

    def _start_worker(self) -> None:
        self._start_after_id = None
        self._start_queued = False
        if self._closed:
            return
        if self._cancel_event.is_set():
            self._show_cancelled("Saving was cancelled before the Edge score export started.")
            if self._close_requested:
                self.close()
            return
        self._starting_worker = True
        start_failed = False
        try:
            if self.on_start is not None:
                self.on_start()
            worker = threading.Thread(target=self._render_worker, daemon=True)
            self._worker_running = True
            worker.start()
        except BaseException as exc:
            self._worker_running = False
            start_failed = True
            self._show_error(exc)
        else:
            self._schedule_poll()
        finally:
            self._starting_worker = False
            if start_failed and self._close_requested:
                self.close()

    def _render_worker(self) -> None:
        try:
            result = self.renderer(
                self.source_hwnd,
                self.destination_folder,
                cancel_event=self._cancel_event,
                progress=self._progress,
            )
        except EdgeScorePdfManualSave as exc:
            self._results.put(("manual_save", exc))
        except BaseException as exc:
            self._results.put(("error", exc))
        else:
            self._results.put(("success", result))

    def _progress(self, message: str) -> None:
        self._results.put(("progress", str(message)))

    def _schedule_poll(self) -> None:
        if not self._closed and self._poll_after_id is None:
            self._poll_after_id = self.window.after(_POLL_MILLISECONDS, self._poll)

    def _poll(self) -> None:
        self._poll_after_id = None
        if self._closed:
            return
        completed = False
        while True:
            try:
                kind, value = self._results.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                self._set_status(str(value))
            else:
                completed = True
                self._worker_running = False
                self.progress.stop()
                if kind == "success":
                    self._show_success(value)
                elif kind == "manual_save":
                    # Cleanup has finished. Leave Edge's Save As in front;
                    # neither a failure popup nor a saved-PDF claim is needed.
                    self._set_status(str(value))
                    self.close()
                else:
                    self._show_error(value if isinstance(value, BaseException) else RuntimeError(str(value)))
                break
        if completed:
            if self._close_requested:
                self.close()
        elif self._worker_running:
            self._schedule_poll()

    def _request_cancel(self) -> None:
        if not self.busy or self._cancel_requested:
            return
        self._cancel_requested = True
        self._cancel_event.set()
        self.cancel_button.configure(state=tk.DISABLED)
        self._set_status("Cancellation requested. This window stays open until Edge export cleanup finishes.")

    def _show_working(self, message: str) -> None:
        self._clear_content()
        ttk.Label(self.content, text="Saving the Edge score…", style="Heading.TLabel").pack(
            anchor=tk.W
        )
        self._wrapped_label(
            self.content,
            text=(
                "Keep Edge in front and wait for PDF saved. Cancel stops automation; "
                "a print dialog may remain open."
            ),
            style="Muted.TLabel",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 4))
        self.progress.pack(fill=tk.X, pady=(6, 0))
        self.progress.start(12)
        self._hide_result_buttons()
        self.cancel_button.configure(state=tk.NORMAL)
        self.cancel_button.pack(side=tk.LEFT)
        self.close_button.configure(state=tk.DISABLED)
        self._set_status(message)

    def _show_success(self, result: object) -> None:
        try:
            path = Path(getattr(result, "destination_path"))
        except (AttributeError, TypeError) as exc:
            self._show_error(RuntimeError("Edge returned an invalid score PDF result."))
            return
        title = str(getattr(result, "title", "Ultimate Guitar score"))
        self.saved_path = path
        self._clear_content()
        ttk.Label(self.content, text="PDF saved", style="Heading.TLabel").pack(anchor=tk.W)
        self._wrapped_label(
            self.content, text=f"Saved {title} as a PDF.", style="Muted.TLabel", justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(4, 0))
        self._wrapped_label(self.content, text=str(path), justify=tk.LEFT).pack(
            anchor=tk.W, pady=(4, 0)
        )
        self._hide_result_buttons()
        self.open_pdf_button.pack(side=tk.LEFT)
        self.open_folder_button.pack(side=tk.LEFT, padx=(8, 0))
        self.close_button.configure(state=tk.NORMAL)
        self._set_status(f"Saved Edge score as PDF: {path}")
        self.window.deiconify()
        self.window.lift()

    def _show_error(self, error: BaseException) -> None:
        self._clear_content()
        detail = str(error) or error.__class__.__name__
        if self._cancel_requested and "cancel" in detail.casefold():
            self._show_cancelled(detail)
            return
        ttk.Label(self.content, text="PDF was not verified", style="Heading.TLabel").pack(anchor=tk.W)
        self._wrapped_label(self.content, text=detail, justify=tk.LEFT).pack(
            anchor=tk.W, pady=(4, 0)
        )
        self._wrapped_label(
            self.content,
            text=(
                "The renderer did not return a verified PDF path. Check the destination "
                "folder if its message indicates a partial or unknown outcome."
            ),
            style="Muted.TLabel",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))
        self._hide_result_buttons()
        self.close_button.configure(state=tk.NORMAL)
        self._set_status(f"Saving Edge score as PDF failed: {detail}")
        self.window.deiconify()
        self.window.lift()

    def _show_cancelled(self, detail: str) -> None:
        self._clear_content()
        ttk.Label(self.content, text="Saving cancelled", style="Heading.TLabel").pack(anchor=tk.W)
        self._wrapped_label(self.content, text=detail, justify=tk.LEFT).pack(
            anchor=tk.W, pady=(4, 0)
        )
        self._hide_result_buttons()
        self.close_button.configure(state=tk.NORMAL)
        self._set_status("Saving Edge score as PDF was cancelled.")

    def _hide_result_buttons(self) -> None:
        for button in (self.cancel_button, self.open_pdf_button, self.open_folder_button):
            button.pack_forget()

    def _clear_content(self) -> None:
        self.progress.stop()
        self.progress.pack_forget()
        for child in self.content.winfo_children():
            if child is not self.progress:
                child.destroy()

    def _wrapped_label(self, parent: tk.Misc, **kwargs) -> ttk.Label:
        label = ttk.Label(parent, wraplength=self._wraplength(), **kwargs)
        self._wrapping_labels.append(label)
        return label

    def _wraplength(self) -> int:
        return max(320, self.window.winfo_width() - 48, 472)

    def _update_wraplength(self, _event: tk.Event | None = None) -> None:
        live: list[ttk.Label] = []
        for label in self._wrapping_labels:
            try:
                if label.winfo_exists():
                    label.configure(wraplength=self._wraplength())
                    live.append(label)
            except tk.TclError:
                pass
        self._wrapping_labels = live

    def _open_pdf(self) -> None:
        if self.saved_path is not None:
            try:
                self.file_opener(self.saved_path)
            except OSError as exc:
                self._set_status(f"Could not open the PDF. It remains saved at {self.saved_path}: {exc}")

    def _open_folder(self) -> None:
        if self.saved_path is not None:
            try:
                self.folder_opener(self.saved_path.parent)
            except OSError as exc:
                self._set_status(f"Could not open the PDF folder. The PDF remains saved at {self.saved_path}: {exc}")

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)
        self.status_setter(message)


def _default_renderer(
    source_hwnd: int,
    destination_folder: Path,
    *,
    cancel_event: threading.Event,
    progress: Callable[[str], None],
) -> object:
    from .edge_score_pdf import save_edge_score_pdf
    return save_edge_score_pdf(source_hwnd, destination_folder, cancel_event=cancel_event, progress=progress)


def _open_path(path: Path) -> None:
    os.startfile(str(path))  # type: ignore[attr-defined]
