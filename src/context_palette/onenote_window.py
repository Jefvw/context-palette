"""Transient, attended OneNote search and plain-text review."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable

from .onenote_integration import (
    OneNoteClient, OneNoteError, OneNoteSettings, OneNoteSettingsError,
    discover_direct_sibling_python_onenote_launcher, load_onenote_settings,
    save_onenote_settings,
)
from .onenote_session import SessionError, capture_session
from .tooltips import WidgetTooltip
from .window_geometry import configure_standard_window, place_child_window


class NotebookChoiceDialog:
    """Pick a remembered search scope from explicitly requested metadata."""

    def __init__(self, parent, notebooks, current):
        self.notebooks = notebooks.notebooks
        self.result = (False, None)
        self.window = tk.Toplevel(parent)
        self.window.title("Choose OneNote notebook")
        configure_standard_window(self.window, parent)
        place_child_window(self.window, parent, size=(500, 360))
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)
        self.window.bind("<Escape>", lambda _: self.cancel())
        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Remember where to search on this PC.").pack(anchor=tk.W)
        if notebooks.truncated:
            ttk.Label(frame, text="Only the first 100 open notebooks are listed.").pack(anchor=tk.W)
        buttons = ttk.Frame(frame)
        buttons.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        ttk.Button(buttons, text="Use notebook", command=self.choose).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side=tk.RIGHT)
        self.results = ttk.Treeview(frame, show="tree", selectmode="browse", height=8)
        self.results.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(frame, command=self.results.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.results.configure(yscrollcommand=scroll.set)
        self.results.insert("", tk.END, iid="all", text="All open notebooks")
        selected = "all" if current is None else None
        for index, notebook in enumerate(self.notebooks):
            self.results.insert("", tk.END, iid=str(index), text=notebook.title)
            if current is not None and notebook.object_id == current.object_id:
                selected = str(index)
        if selected is not None:
            self.results.selection_set(selected)
            self.results.see(selected)
        self.results.bind("<Return>", lambda _: self.choose())
        self.results.focus_set()

    def choose(self):
        selection = self.results.selection()
        if selection:
            selected = selection[0]
            self.result = (True, None if selected == "all" else self.notebooks[int(selected)])
            self.window.destroy()

    def cancel(self):
        self.window.destroy()

    def show(self):
        self.window.grab_set()
        self.window.wait_window()
        return self.result


class OneNoteWindow:
    """One request at a time; only the Tk thread can publish current results."""

    def __init__(self, parent, *, settings_path: Path, initial_query: str,
                 apply_text: Callable[[str, Callable[[], bool]], bool],
                 on_close: Callable[[], None], client_factory=OneNoteClient,
                 session_reader=capture_session, application_root: Path | None = None) -> None:
        self.settings_path = settings_path
        # The shipped source layout defines installation location, independently
        # of the process cwd or a separately supplied settings directory.
        self.application_root = (Path(application_root) if application_root is not None
                                 else Path(__file__).resolve().parents[2])
        self.apply_text = apply_text
        self.on_close = on_close
        self.client_factory = client_factory
        self.session_reader = session_reader
        self._client = None
        self._generation = 0
        self._job = None
        self._cancel = threading.Event()
        self._queue = queue.Queue()
        self._ready = frozenset()
        self._session = None
        self._described = False
        self._settings = OneNoteSettings()
        self._pages = ()
        self._preview = None
        self._selected_id = None
        self._closed = False
        self._closing = False
        self._blocked = False
        self._poll_id = None
        self.window = tk.Toplevel(parent)
        self.window.title("Find OneNote notes")
        configure_standard_window(self.window, parent)
        place_child_window(self.window, parent, size=(860, 740))
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        # Reserve footer space before the growing result and preview regions.
        bottom = ttk.Frame(outer)
        bottom.pack(side=tk.BOTTOM, fill=tk.X)
        heading = ttk.Frame(outer)
        heading.pack(fill=tk.X)
        ttk.Label(heading, text="Find OneNote notes", style="Title.TLabel").pack(side=tk.LEFT)
        self.choose_button = ttk.Button(heading, text="Choose engine…", command=self.choose_engine)
        self.choose_button.pack(side=tk.RIGHT)
        self.setup_var = tk.StringVar(value="No sibling engine found. Choose python-onenote.bat on this PC.")
        scope_row = ttk.Frame(outer)
        scope_row.pack(fill=tk.X, pady=(8, 10))
        ttk.Label(scope_row, text="Notebook:").pack(side=tk.LEFT)
        self.notebook_var = tk.StringVar(value="All open notebooks")
        ttk.Label(scope_row, textvariable=self.notebook_var, wraplength=450).pack(side=tk.LEFT, padx=6)
        self.notebook_button = ttk.Button(scope_row, text="Choose notebook…", command=self.choose_notebook)
        self.notebook_button.pack(side=tk.RIGHT)
        query_row = ttk.Frame(outer)
        query_row.pack(fill=tk.X, pady=(4, 4))
        self.find_label = ttk.Label(query_row, text="Find:")
        self.find_label.pack(side=tk.LEFT, padx=(0, 6))
        self.query_var = tk.StringVar(value=initial_query)
        self.query_entry = ttk.Entry(query_row, textvariable=self.query_var)
        self.query_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.query_entry.bind("<Return>", lambda _event: self.search())
        self.search_button = ttk.Button(query_row, text="Search", command=self.search)
        self.search_button.pack(side=tk.RIGHT, padx=(6, 0))
        self.results_var = tk.StringVar(value="Notes")
        ttk.Label(outer, textvariable=self.results_var).pack(anchor=tk.W)
        result_frame = ttk.Frame(outer)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 6))
        self.results = ttk.Treeview(result_frame, columns=("location",), height=3,
                                    selectmode="browse", show="tree headings")
        self.results.heading("#0", text="Note")
        self.results.heading("location", text="Notebook / section")
        self.results.column("#0", width=260, minwidth=120)
        self.results.column("location", width=400, minwidth=120)
        self.results.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(result_frame, command=self.results.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.results.configure(yscrollcommand=scroll.set)
        self.results.bind("<<TreeviewSelect>>", self._selection_changed)
        preview_controls = ttk.Frame(outer)
        preview_controls.pack(fill=tk.X)
        self.preview_button = ttk.Button(preview_controls, text="Preview text", command=self.preview)
        self.preview_button.pack(side=tk.LEFT)
        self.preview_var = tk.StringVar()
        ttk.Label(preview_controls, textvariable=self.preview_var).pack(side=tk.LEFT, padx=8)
        preview_frame = ttk.Frame(outer)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 4))
        self.preview_text = tk.Text(preview_frame, height=4, wrap=tk.WORD, state=tk.DISABLED,
                                    font=("Segoe UI", 10), padx=8, pady=8)
        self.preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        preview_scroll = ttk.Scrollbar(preview_frame, command=self.preview_text.yview)
        preview_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.preview_text.configure(yscrollcommand=preview_scroll.set)
        self.basic_text_warning = ttk.Label(bottom,
            text="Basic text only; formatting, attachments and ink may be absent.",
            wraplength=740, style="Muted.TLabel")
        footer = ttk.Frame(bottom)
        footer.pack(fill=tk.X, pady=(10, 0))
        self.use_button = ttk.Button(footer, text="Use text…", command=self.use_text)
        self.use_button.pack(side=tk.LEFT)
        self.close_button = ttk.Button(footer, text="Close", command=self.close)
        self.close_button.pack(side=tk.RIGHT)
        self.cancel_button = ttk.Button(footer, text="Cancel request", command=self.cancel)
        self.status_var = tk.StringVar(value="Enter a query and choose Search.")
        self.status_label = ttk.Label(bottom, textvariable=self.status_var, wraplength=740,
                                      style="Status.TLabel")
        self.status_label.pack(fill=tk.X, pady=(8, 0))
        self._tooltips = (
            WidgetTooltip(self.search_button,
                "Search connects to the open OneNote app and reads titles and locations in the shown notebook. OneNote stays unchanged. Nothing runs while you type."),
            WidgetTooltip(self.notebook_button,
                "List open notebook names and remember an exact search scope on this PC. This reads notebook names only when requested."),
            WidgetTooltip(self.choose_button, lambda: self.setup_var.get()),
        )
        self.query_var.trace_add("write", self._query_changed)
        try:
            self._settings = load_onenote_settings(settings_path)
            self._show_scope()
            launcher = self._settings.launcher_path
            if launcher is not None:
                self.choose_button.configure(text="Change engine…")
                if launcher.is_file():
                    self._client = client_factory(launcher)
                    self.setup_var.set("Engine remembered on this PC. Search connects automatically.")
                else:
                    self.setup_var.set("Saved engine unavailable. Choose Change engine…; your notebook is remembered.")
            else:
                launcher = discover_direct_sibling_python_onenote_launcher(self.application_root)
                if launcher is not None:
                    self._client = client_factory(launcher)
                    self.choose_button.configure(text="Change engine…")
                    self.setup_var.set("Sibling engine found. Search checks and connects when requested.")
        except OneNoteSettingsError as exc:
            self._settings = OneNoteSettings(notebook=exc.notebook)
            self._show_scope()
            self.choose_button.configure(text="Change engine…")
            self.setup_var.set("Saved engine settings need repair. Choose Change engine….")
        except (OneNoteError, OSError, ValueError):
            self.setup_var.set("Engine unavailable. Choose the launcher again.")
        if self._client is None:
            self.status_var.set(self.setup_var.get())
        self._sync()
        self.show()

    @property
    def busy(self):
        return self._job is not None or self._blocked

    def show(self):
        if not self._closed:
            self.window.deiconify()
            self.window.lift()

    def _sync(self):
        available = not self.busy and not self._closing
        for button, enabled in (
            (self.choose_button, available),
            (self.notebook_button, available and self._client is not None),
            (self.search_button, available and self._client is not None),
            (self.preview_button, available and self._selected_id is not None
             and "preview_desktop_page" in self._ready),
            (self.use_button, available and self._preview is not None and self._preview.can_use),
            (self.cancel_button, self._job is not None and not self._closing),
        ):
            button.configure(state=tk.NORMAL if enabled else tk.DISABLED)
        if self._job is not None and not self._closing:
            self.cancel_button.pack(side=tk.RIGHT, padx=6)
        else:
            self.cancel_button.pack_forget()
        if self._selected_id is not None:
            self.basic_text_warning.pack(anchor=tk.W, before=self.use_button.master)
        else:
            self.basic_text_warning.pack_forget()

    def _clear_preview(self):
        self._preview = None
        self.preview_text.configure(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.configure(state=tk.DISABLED)
        self.preview_var.set("")

    def _clear_results(self):
        self._selected_id = None
        self._pages = ()
        self.results.delete(*self.results.get_children())
        self.results_var.set("Notes")
        self._clear_preview()

    def _invalidate(self):
        self._generation += 1
        if self._job is not None:
            self._cancel.set()
            # Cancellation can interrupt a backend lifecycle check. A late
            # completion must never revive the cancelled readiness session.
            self._ready = frozenset()
            self._session = None

    def _query_changed(self, *_args):
        self._invalidate()
        self._clear_results()
        self.status_var.set("Cancelling the previous request…" if self.busy else
                            self.setup_var.get() if self._client is None else
                            "Choose Search when ready.")
        self._sync()

    def _selection_changed(self, _event=None):
        selected = self.results.selection()
        page_id = self._pages[int(selected[0])].object_id if selected else None
        if page_id == self._selected_id:
            return
        self._invalidate()
        self._selected_id = page_id
        self._clear_preview()
        self.status_var.set("Cancelling the previous request…" if self.busy else
                            "Choose Preview text to read the selected note." if page_id is not None else
                            "Choose a note, then Preview text.")
        self._sync()

    def choose_engine(self):
        if self.busy or self._closing:
            return
        selected = filedialog.askopenfilename(parent=self.window, title="Choose Python OneNote launcher",
                    filetypes=[("Python OneNote launcher", "python-onenote.bat")])
        if not selected:
            return
        self._invalidate()
        self._clear_results()
        self._ready = frozenset()
        self._session = None
        self._described = False
        try:
            # Engine setup must never widen a deliberately chosen notebook.
            # If its identity is stale, scoped search will stop for reselection.
            settings = OneNoteSettings(Path(selected), self._settings.notebook)
            save_onenote_settings(self.settings_path, settings)
            self._client = self.client_factory(settings.launcher_path)
            self._settings = settings
            self._show_scope()
        except (OneNoteError, OSError, ValueError):
            self._client = None
            self.status_var.set("Choose an existing, absolute python-onenote.bat launcher.")
        else:
            self.choose_button.configure(text="Change engine…")
            self.setup_var.set("Engine remembered on this PC. Search connects automatically.")
            self.status_var.set("Engine saved. Choose Search when ready.")
        self._sync()

    def _show_scope(self):
        notebook = self._settings.notebook
        self.notebook_var.set(notebook.title if notebook is not None else "All open notebooks")

    def choose_notebook(self):
        if self.busy or self._client is None or self._closing:
            return
        self._clear_results()
        self._connected_read("notebooks", "inventory_desktop_hierarchy",
                             lambda cancel: self._client.notebooks(cancel_event=cancel))

    def _start(self, kind, operation):
        if self.busy or self._closing or self._closed:
            return
        self._generation += 1
        generation = self._generation
        self._job = (generation, kind)
        self._cancel = threading.Event()
        cancel = self._cancel
        def work():
            try:
                result = operation(cancel)
                outcome = (result, None)
            except OneNoteError as exc:
                outcome = (None, exc)
            except SessionError:
                outcome = (None, OneNoteError("backend.desktop_process_exited"))
            except Exception:
                # Never serialize a backend exception or sensitive request.
                outcome = (None, OneNoteError("internal.host"))
            self._queue.put((generation, kind, *outcome))
        self.status_var.set({"notebooks": "Connecting and listing open notebooks…",
                             "search": "Connecting and searching OneNote…", "preview": "Reading the selected note…"}[kind])
        self._sync()
        try:
            threading.Thread(target=work, daemon=True, name="onenote-read").start()
        except Exception:
            self._job = None
            self._ready = frozenset()
            self._session = None
            self.status_var.set("OneNote request could not start. Try Search again.")
            self._sync()
            return
        self._poll_id = self.window.after(40, self._poll)

    def _connected_read(self, kind, capability, operation):
        # Only explicit Search/Choose notebook reaches this method. Capture UI
        # state before the worker; publish readiness only with a current result.
        client = self._client
        described, ready, session = self._described, self._ready, self._session
        def read(cancel):
            def check_cancel():
                if cancel.is_set():
                    raise OneNoteError("transport.cancelled")
            check_cancel()
            if not described and not client.describe(cancel_event=cancel).can_probe:
                raise OneNoteError("integration.unavailable", "This engine cannot read OneNote on this PC.")
            check_cancel()
            before = self.session_reader()
            if not before:
                raise OneNoteError("backend.desktop_not_running")
            current_ready = ready
            if session != before or capability not in ready:
                current_ready = frozenset(client.probe(cancel_event=cancel).ready_capabilities)
            check_cancel()
            if self.session_reader() != before:
                raise OneNoteError("backend.desktop_process_exited")
            if capability not in current_ready:
                raise OneNoteError("integration.unavailable", "This engine does not support the requested OneNote read.")
            result = operation(cancel)
            check_cancel()
            if self.session_reader() != before:
                raise OneNoteError("backend.desktop_process_exited")
            return result, current_ready, before
        self._start(kind, read)

    def _read(self, operation, cancel):
        expected = self._session
        if not expected or self.session_reader() != expected:
            raise OneNoteError("backend.desktop_process_exited")
        result = operation(cancel)
        if self.session_reader() != expected:
            raise OneNoteError("backend.desktop_process_exited")
        return result

    def search(self):
        if self.busy or self._client is None or self._closing:
            return "break"
        query = self.query_var.get()
        if not query.strip():
            self.status_var.set("Enter some text to find.")
            return "break"
        notebook = self._settings.notebook
        notebook_id = notebook.object_id if notebook is not None else None
        self._clear_results()
        self._connected_read("search", "search_desktop_pages",
            lambda cancel: self._client.search(query, notebook_id=notebook_id, cancel_event=cancel))
        return "break"

    def preview(self):
        if self.busy or self._selected_id is None or "preview_desktop_page" not in self._ready:
            return
        selected = self._selected_id
        self._clear_preview()
        self._start("preview", lambda cancel: self._read(
            lambda event: self._client.preview(selected, cancel_event=event), cancel))

    def _poll(self):
        self._poll_id = None
        try:
            generation, kind, result, error = self._queue.get_nowait()
        except queue.Empty:
            self._poll_id = self.window.after(40, self._poll)
            return
        self._job = None  # Runner has returned only after process cleanup.
        if error is not None and error.code == "transport.cleanup":
            self._blocked = True
            self._ready = frozenset()
            self._session = None
            self.status_var.set("Process cleanup could not be confirmed. Further OneNote requests are blocked; keep this session open for investigation.")
            self._sync()
            return
        if self._closing:
            self._finish_close()
            return
        if generation != self._generation:
            self.status_var.set("Previous request cancelled. Choose Search when ready.")
            self._sync()
            return
        if error is not None:
            if error.invalidates_readiness:
                self._ready = frozenset()
                self._session = None
                self._described = False
            if error.code in {"backend.desktop_busy", "backend.desktop_timeout", "transport.timeout"}:
                self._clear_preview()
            else:
                self._clear_results()
            self.status_var.set(str(error))
            if error.code in {"integration.transport_failed", "integration.protocol_failed",
                              "integration.engine_failed", "integration.unavailable", "transport.launch"}:
                # A failed configured/discovered engine is not permission to try
                # a different installation. Preserve scope and require repair.
                self._client = None
                self.setup_var.set("Engine unavailable or incompatible. Choose Change engine to repair setup.")
                self.status_var.set(self.setup_var.get())
        elif kind in {"notebooks", "search"}:
            result, self._ready, self._session = result
            self._described = True
            if kind == "notebooks":
                choice_generation = self._generation
                accepted, notebook = NotebookChoiceDialog(self.window, result, self._settings.notebook).show()
                if self._closed or self._closing:
                    return
                if choice_generation != self._generation:
                    self.status_var.set("The request changed during the choice. Your notebook is unchanged.")
                    self._sync()
                    return
                if accepted:
                    settings = OneNoteSettings(self._settings.launcher_path, notebook)
                    try:
                        save_onenote_settings(self.settings_path, settings)
                    except (OSError, ValueError):
                        self.status_var.set("The notebook choice could not be saved. Your previous scope is unchanged.")
                    else:
                        self._settings = settings
                        self._show_scope()
                        self.status_var.set("Notebook choice remembered. Enter a query and choose Search.")
                else:
                    self.status_var.set("Notebook choice unchanged.")
                self._sync()
                return
            self._pages = result.pages
            for index, page in enumerate(result.pages):
                self.results.insert("", tk.END, iid=str(index), text=page.title,
                                    values=(" / ".join(page.breadcrumb),))
            count = len(result.pages)
            self.results_var.set(f"Showing {count} of {result.total} matches"
                                 if result.truncated else f"{count} matches returned.")
            self.status_var.set("Choose a note and Preview text, or narrow the query for other matches."
                                if count and result.truncated else
                                "Choose a note, then Preview text." if count else
                                "This response is limited. Narrow the query and search again." if result.truncated else
                                "No matches returned for this query. Search coverage depends on OneNote.")
        elif kind == "preview" and result.object_id == self._selected_id:
            self._preview = result
            self.preview_text.configure(state=tk.NORMAL)
            self.preview_text.insert("1.0", result.text)
            self.preview_text.configure(state=tk.DISABLED)
            self.preview_var.set(f"Limited preview: {result.returned_characters:,} of {result.source_characters:,} characters."
                                 if result.truncated else f"Complete basic text · {result.returned_characters:,} characters")
            self.status_var.set("This note exceeds the 50,000-character limit. Use text is disabled."
                                if result.truncated else "Review the text, then choose Use text… for Replace or Append.")
        self._sync()

    def use_text(self):
        preview = self._preview
        if self.busy or preview is None or not preview.can_use or preview.object_id != self._selected_id:
            return
        generation = self._generation
        is_current = lambda: (not self._closing and not self._closed and
                              self._generation == generation and self._preview is preview)
        if self.apply_text(preview.text, is_current) and is_current():
            self.status_var.set("Reviewed text placed in Input / Output. OneNote was unchanged.")

    def cancel(self):
        self._invalidate()
        self._clear_results()
        self._ready = frozenset()
        self._session = None
        self.status_var.set("Cancelling request and clearing results…" if self.busy else "Cancelled. Choose Search when ready.")
        self._sync()

    def close(self):
        if self._closed:
            return True
        self._closing = True
        self.cancel()
        self.query_var.set("")
        if self.busy:
            self.status_var.set("Closing after process cleanup…" if not self._blocked else "Cleanup is unconfirmed. Further OneNote requests remain blocked.")
            return False
        self._finish_close()
        return True

    def _finish_close(self):
        self._closed = True
        self._client = None
        if self._poll_id is not None:
            self.window.after_cancel(self._poll_id)
        self.window.destroy()
        self.on_close()
