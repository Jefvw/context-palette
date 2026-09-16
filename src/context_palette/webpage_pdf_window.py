"""Attended window for saving one public webpage URL as a PDF."""

from __future__ import annotations

from pathlib import Path
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

from .window_geometry import configure_standard_window


_POLL_MILLISECONDS = 50
_MAX_DISPLAY_URL = 200

Renderer = Callable[..., Path]
PathOpener = Callable[[Path], None]


class WebpagePdfWindow:
    """Run one attended webpage-to-PDF render without touching the workspace."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        url: str,
        destination: Path,
        status_setter: Callable[[str], None],
        on_close: Callable[[], None],
        renderer: Renderer | None = None,
        file_opener: PathOpener | None = None,
        folder_opener: PathOpener | None = None,
    ) -> None:
        self.url = url
        self.destination = Path(destination)
        self.status_setter = status_setter
        self.on_close = on_close
        self.renderer = renderer or _default_renderer
        self.file_opener = file_opener or _open_path
        self.folder_opener = folder_opener or _open_path

        self._results: queue.Queue[tuple[str, object]] = queue.Queue()
        self._cancel_event = threading.Event()
        self._started = False
        self._start_queued = False
        self._worker_running = False
        self._cancel_requested = False
        self._close_requested = False
        self._closed = False
        self._poll_after_id: str | None = None
        self._start_after_id: str | None = None
        self.saved_path: Path | None = None
        self._wrapping_labels: list[ttk.Label] = []

        self.window = tk.Toplevel(parent)
        self.window.title("Save webpage as PDF")
        configure_standard_window(self.window, parent)
        self.window.minsize(520, 480)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.bind("<Configure>", self._update_wraplength)
        self.window.transient(parent)

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        ttk.Label(outer, text="Save webpage as PDF", style="Title.TLabel").pack(
            anchor=tk.W
        )
        self._wrapped_label(
            outer,
            text=(
                "Uses Microsoft Edge or Chrome in a temporary browser session. Best "
                "for webpages that open without signing in."
            ),
            style="Muted.TLabel",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(2, 8))
        ttk.Label(outer, text="Webpage", style="Heading.TLabel").pack(anchor=tk.W)
        self._wrapped_label(
            outer, text=_display_url(self.url), justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(1, 7))
        ttk.Label(outer, text="PDF file", style="Heading.TLabel").pack(anchor=tk.W)
        self._wrapped_label(
            outer, text=str(self.destination), justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(1, 8))

        self.content = ttk.Frame(outer)
        self.status_var = tk.StringVar(value="Ready to save the webpage as a PDF.")
        self.status_label = self._wrapped_label(
            outer,
            textvariable=self.status_var,
            style="Status.TLabel",
            justify=tk.LEFT,
        )
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        self.footer = ttk.Frame(outer)
        self.footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        self.cancel_button = ttk.Button(
            self.footer, text="Cancel", command=self._request_cancel
        )
        self.open_pdf_button = ttk.Button(
            self.footer, text="Open PDF", command=self._open_pdf
        )
        self.open_folder_button = ttk.Button(
            self.footer, text="Open folder", command=self._open_folder
        )
        self.close_button = ttk.Button(self.footer, text="Close", command=self.close)
        self.close_button.pack(side=tk.RIGHT)
        self.progress = ttk.Progressbar(self.content, mode="indeterminate")
        # Pack expandable content after the fixed status/footer so a narrow window
        # preserves complete button rows instead of allocating their height away.
        self.content.pack(fill=tk.BOTH, expand=True)

    @property
    def busy(self) -> bool:
        """Include scheduled work so application Quit guards cannot race startup."""

        return self._start_queued or self._worker_running

    def show(self) -> None:
        """Show the attended window and begin its one permitted render."""

        if self._closed:
            return
        parent = self.window.master
        self.window.transient(parent if parent.winfo_viewable() else "")
        self.window.deiconify()
        self.window.lift()
        if self._started:
            return
        self._started = True
        self._start_queued = True
        self._show_working("Preparing the webpage render…")
        self._start_after_id = self.window.after_idle(self._start_worker)

    def close(self) -> bool:
        """Close immediately when idle, otherwise request cancellation and wait."""

        if self._closed:
            return True
        if self.busy:
            self._close_requested = True
            self._request_cancel()
            return False
        self._closed = True
        for after_id in (self._start_after_id, self._poll_after_id):
            if after_id is None:
                continue
            try:
                self.window.after_cancel(after_id)
            except tk.TclError:
                pass
        self._start_after_id = None
        self._poll_after_id = None
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
            self._show_cancelled("Saving the webpage as PDF was cancelled before it started.")
            if self._close_requested:
                self.close()
            return
        self._worker_running = True
        worker = threading.Thread(target=self._render_worker, daemon=True)
        try:
            worker.start()
        except RuntimeError as exc:
            self._worker_running = False
            self.progress.stop()
            self._show_error(exc)
            if self._close_requested:
                self.close()
            return
        self._schedule_poll()

    def _render_worker(self) -> None:
        """Call the blocking renderer without making Tk calls from this thread."""

        try:
            saved = self.renderer(
                self.url, self.destination, cancel_event=self._cancel_event
            )
        except BaseException as exc:  # Convert every worker failure into UI state.
            self._results.put(("error", exc))
        else:
            self._results.put(("success", Path(saved)))

    def _schedule_poll(self) -> None:
        if not self._closed and self._poll_after_id is None:
            self._poll_after_id = self.window.after(_POLL_MILLISECONDS, self._poll)

    def _poll(self) -> None:
        self._poll_after_id = None
        if self._closed:
            return
        try:
            kind, value = self._results.get_nowait()
        except queue.Empty:
            if self._worker_running:
                self._schedule_poll()
            return
        self._worker_running = False
        self.progress.stop()
        if kind == "success":
            self._show_success(Path(value))
        else:
            assert isinstance(value, BaseException)
            self._show_error(value)
        if self._close_requested:
            self.close()

    def _request_cancel(self) -> None:
        if not self.busy:
            return
        if self._cancel_requested:
            return
        self._cancel_requested = True
        self._cancel_event.set()
        self.cancel_button.configure(state=tk.DISABLED)
        self._set_status(
            "Cancellation requested. This window stays open until browser cleanup finishes."
        )

    def _show_working(self, message: str) -> None:
        self._clear_content()
        ttk.Label(
            self.content,
            text="Saving the webpage…",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        self._wrapped_label(
            self.content,
            text="The PDF is saved only after the renderer completes. Closing now requests cancellation.",
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

    def _show_success(self, saved: Path) -> None:
        self.saved_path = saved
        self._clear_content()
        ttk.Label(self.content, text="PDF saved", style="Heading.TLabel").pack(anchor=tk.W)
        self._wrapped_label(
            self.content,
            text=(
                "Open and check the PDF. Page print layout, cookie notices, or "
                "missing content can differ from the webpage."
            ),
            style="Muted.TLabel",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))
        self._hide_result_buttons()
        self.open_pdf_button.pack(side=tk.LEFT)
        self.open_folder_button.pack(side=tk.LEFT, padx=(8, 0))
        self.close_button.configure(state=tk.NORMAL)
        self._set_status(f"Saved webpage as PDF: {saved}")

    def _show_error(self, error: BaseException) -> None:
        self._clear_content()
        cancelled = self._cancel_requested and "cancel" in str(error).casefold()
        if cancelled:
            self._show_cancelled(
                "The renderer finished cancellation. No successful PDF path was reported."
            )
            return
        heading = "PDF was not saved"
        ttk.Label(self.content, text=heading, style="Heading.TLabel").pack(anchor=tk.W)
        detail = str(error) or error.__class__.__name__
        self._wrapped_label(
            self.content, text=detail, justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(4, 0))
        self._hide_result_buttons()
        self.close_button.configure(state=tk.NORMAL)
        self._set_status(f"Saving webpage as PDF failed: {detail}")

    def _show_cancelled(self, detail: str) -> None:
        self._clear_content()
        ttk.Label(
            self.content, text="Saving cancelled", style="Heading.TLabel"
        ).pack(anchor=tk.W)
        self._wrapped_label(
            self.content, text=detail, justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(4, 0))
        self._hide_result_buttons()
        self.close_button.configure(state=tk.NORMAL)
        self._set_status("Saving webpage as PDF was cancelled.")

    def _hide_result_buttons(self) -> None:
        for button in (self.cancel_button, self.open_pdf_button, self.open_folder_button):
            button.pack_forget()

    def _clear_content(self) -> None:
        self.progress.stop()
        self.progress.pack_forget()
        for child in self.content.winfo_children():
            if child is self.progress:
                continue
            child.destroy()

    def _wrapped_label(self, parent: tk.Misc, **kwargs) -> ttk.Label:
        """Make long URLs, paths, and status text reflow inside the current window."""

        label = ttk.Label(parent, wraplength=self._wraplength(), **kwargs)
        self._wrapping_labels.append(label)
        return label

    def _wraplength(self) -> int:
        return max(320, self.window.winfo_width() - 48, 472)

    def _update_wraplength(self, _event: tk.Event | None = None) -> None:
        wraplength = self._wraplength()
        live: list[ttk.Label] = []
        for label in self._wrapping_labels:
            try:
                if label.winfo_exists():
                    label.configure(wraplength=wraplength)
                    live.append(label)
            except tk.TclError:
                continue
        self._wrapping_labels = live

    def _open_pdf(self) -> None:
        if self.saved_path is not None:
            try:
                self.file_opener(self.saved_path)
            except OSError as exc:
                self._set_status(
                    f"Could not open the PDF. It remains saved at {self.saved_path}: {exc}"
                )

    def _open_folder(self) -> None:
        if self.saved_path is not None:
            try:
                self.folder_opener(self.saved_path.parent)
            except OSError as exc:
                self._set_status(
                    "Could not open the PDF folder. The PDF remains saved at "
                    f"{self.saved_path}: {exc}"
                )

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)
        self.status_setter(message)


def _default_renderer(
    url: str,
    destination: Path,
    *,
    cancel_event: threading.Event,
) -> Path:
    # Import lazily so this presentation module remains independently testable.
    from .webpage_pdf import render_webpage_pdf

    return render_webpage_pdf(url, destination, cancel_event=cancel_event)


def _open_path(path: Path) -> None:
    os.startfile(str(path))  # type: ignore[attr-defined]


def _display_url(url: str) -> str:
    if len(url) <= _MAX_DISPLAY_URL:
        return url
    suffix = "… [display shortened]"
    return url[: _MAX_DISPLAY_URL - len(suffix)] + suffix
