"""Attended Send-to-OneNote UI; source snapshots and receipts stay in memory."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .onenote_integration import (
    OneNoteError, OneNoteSettings, OneNoteSettingsError, load_onenote_settings,
    save_onenote_settings, discover_direct_sibling_python_onenote_launcher,
)
from .onenote_send import (
    OneNoteSendClient, SendError, SendOutcome, load_destination, save_destination,
    canonical_plan, normalize_text, suggested_title,
)
from .onenote_session import capture_session
from .style import CAPTION_FONT, COLORS, DEFAULT_FONT, HEADING_FONT, TITLE_FONT
from .window_geometry import configure_standard_window, place_child_window


class DestinationChoice:
    """Only an explicitly selected row is accepted; labels never identify targets."""
    def __init__(self, parent, title, entries):
        self.entries, self.result = entries, None
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        configure_standard_window(self.window, parent)
        place_child_window(self.window, parent, size=(660, 390))
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)
        self.window.bind("<Escape>", lambda _: self.cancel())
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        ttk.Label(outer, text=f"{len(entries)} choices. Select the exact destination.").pack(anchor=tk.W)
        buttons = ttk.Frame(outer)
        buttons.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        ttk.Button(buttons, text="Choose", command=self.choose).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side=tk.RIGHT)
        self.rows = tk.Listbox(outer, exportselection=False)
        horizontal = ttk.Scrollbar(outer, orient=tk.HORIZONTAL, command=self.rows.xview)
        horizontal.pack(side=tk.BOTTOM, fill=tk.X)
        self.rows.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(outer, command=self.rows.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.rows.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        for entry in entries:
            self.rows.insert(tk.END, entry.label or "(untitled)")
        self.rows.bind("<Return>", lambda _: self.choose())
        self.rows.focus_set()

    def choose(self):
        selected = self.rows.curselection()
        if selected:
            self.result = self.entries[selected[0]]
            self.window.destroy()

    def cancel(self):
        self.window.destroy()

    def show(self):
        self.window.grab_set()
        self.window.wait_window()
        return self.result


class OneNoteSendWindow:
    def __init__(self, parent, *, settings_path, destination_path, source_reader,
                 client_factory=OneNoteSendClient, session_reader=capture_session,
                 application_root=None, clock=None, gesture_clock=None):
        self.settings_path, self.destination_path = Path(settings_path), Path(destination_path)
        self.application_root = Path(application_root) if application_root else Path(__file__).resolve().parents[2]
        self.source_reader = source_reader  # Tk thread only; returns (text, revision).
        self.client_factory, self.session_reader = client_factory, session_reader
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.gesture_clock = gesture_clock or time.monotonic
        self._last_send_gesture = None
        self._send_key_down = False
        self._client = None
        self._engine_key = None
        self._destination = None
        self._job = None
        self._cancel = threading.Event()
        self._queue = queue.Queue()
        self._generation = 0
        self._blocked = False
        self._source_current = True
        self._setting_title = False
        self._receipt_unacknowledged = False
        self._notice = ("Check the title and text, then choose Send to OneNote.", "neutral")
        self._validation_error = None
        self._suggestion = ""
        self.receipts = []  # Transient only. Never persisted or logged.
        self.window = tk.Toplevel(parent)
        self.window.title("Send text to OneNote")
        configure_standard_window(self.window, parent)
        place_child_window(self.window, parent, size=(780, 650))
        self.window.minsize(640, 520)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _: self.close())
        self.window.bind("<Control-Return>", self._send_key_press)
        self.window.bind("<KeyRelease-Return>", self._send_key_release)
        style = ttk.Style(self.window)
        style.configure("OneNoteSend.Accent.TButton", padding=(14, 7))
        style.map("OneNoteSend.Accent.TButton",
                  background=[("disabled", COLORS["topic_header"]), ("active", COLORS["accent_hover"])],
                  foreground=[("disabled", COLORS["muted_text"]), ("!disabled", COLORS["white"])])
        outer = ttk.Frame(self.window, padding=16)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)
        self.title_label = ttk.Label(outer, text="Send text to OneNote", style="Title.TLabel", font=TITLE_FONT)
        self.title_label.grid(row=0, sticky=tk.W, pady=(0, 12))
        destination_frame = ttk.Frame(outer)
        destination_frame.grid(row=1, sticky=tk.EW, pady=(0, 12))
        destination_frame.columnconfigure(0, weight=1)
        ttk.Label(destination_frame, text="Destination", style="Heading.TLabel", font=HEADING_FONT).grid(row=0, sticky=tk.W)
        self.destination_var = tk.StringVar()
        self.destination_label = ttk.Label(destination_frame, textvariable=self.destination_var, wraplength=580)
        self.destination_label.grid(row=1, column=0, sticky=tk.EW, pady=(4, 0))
        self.destination_button = ttk.Button(destination_frame, text="Change…", command=self.choose_destination)
        self.destination_button.grid(row=1, column=1, padx=(12, 0), sticky=tk.NE)
        page = ttk.Frame(outer)
        page.grid(row=2, sticky=tk.EW)
        page.columnconfigure(0, weight=1)
        ttk.Label(page, text="Page title", style="Heading.TLabel", font=HEADING_FONT).grid(row=0, sticky=tk.W)
        self.title_count_var = tk.StringVar()
        ttk.Label(page, textvariable=self.title_count_var, font=CAPTION_FONT,
                  foreground=COLORS["muted_text"]).grid(row=0, column=1, sticky=tk.E)
        self.title_var = tk.StringVar()
        self.title_entry = ttk.Entry(page, textvariable=self.title_var)
        self.title_entry.grid(row=1, columnspan=2, sticky=tk.EW, pady=(4, 4))
        self.final_title_var = tk.StringVar()
        self.title_preview = ttk.Label(page, textvariable=self.final_title_var, wraplength=740,
                                       foreground=COLORS["muted_text"], font=CAPTION_FONT)
        self.title_preview.grid(row=2, columnspan=2, sticky=tk.EW, pady=(0, 4))
        self.title_hint_var = tk.StringVar()
        self.title_hint = ttk.Label(page, textvariable=self.title_hint_var, wraplength=740,
                                    foreground=COLORS["muted_text"], font=CAPTION_FONT)
        self.title_hint.grid(row=3, columnspan=2, sticky=tk.EW, pady=(0, 8))
        self.count_var = tk.StringVar()
        ttk.Label(page, textvariable=self.count_var, style="Heading.TLabel", font=HEADING_FONT).grid(row=4, columnspan=2, sticky=tk.W)
        text_frame = ttk.Frame(outer)
        text_frame.grid(row=3, sticky=tk.NSEW, pady=(4, 12))
        self.body_text = tk.Text(text_frame, wrap=tk.WORD, height=5, font=DEFAULT_FONT,
                                 padx=10, pady=8, state=tk.DISABLED, background=COLORS["surface"],
                                 foreground=COLORS["text"], selectbackground=COLORS["accent"],
                                 selectforeground=COLORS["white"], highlightcolor=COLORS["focus"],
                                 highlightbackground=COLORS["border"], highlightthickness=1, relief=tk.FLAT)
        self.body_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(text_frame, command=self.body_text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.body_text.configure(yscrollcommand=scroll.set)
        self.body_text.bind("<Tab>", lambda _: self._focus_from_body())
        self.body_text.bind("<Shift-Tab>", lambda _: self._focus_from_body(backwards=True))
        self.body_text.bind("<ISO_Left_Tab>", lambda _: self._focus_from_body(backwards=True))
        banner = tk.Frame(outer, background=COLORS["row_light"])
        banner.grid(row=4, sticky=tk.EW, pady=(0, 12))
        banner.columnconfigure(1, weight=1)
        self.status_stripe = tk.Frame(banner, width=4, background=COLORS["accent"])
        self.status_stripe.grid(row=0, column=0, rowspan=2, sticky=tk.NS)
        self.status_var = tk.StringVar()
        self.status_label = tk.Label(banner, textvariable=self.status_var, wraplength=700,
                                     background=COLORS["row_light"], foreground=COLORS["text"],
                                     font=DEFAULT_FONT, anchor=tk.W, justify=tk.LEFT, padx=12, pady=10)
        self.status_label.grid(row=0, column=1, sticky=tk.EW)
        self.banner_commands = ttk.Frame(banner)
        self.banner_commands.grid(row=1, column=1, sticky=tk.W, padx=12, pady=(0, 10))
        self.refresh_button = ttk.Button(self.banner_commands, text="Use current Input / Output", command=self.capture_source)
        self.ack_button = ttk.Button(self.banner_commands, text="I've checked OneNote", command=self.acknowledge)
        commands = ttk.Frame(outer)
        commands.grid(row=5, sticky=tk.EW)
        self.close_button = ttk.Button(commands, text="Close", command=self.close)
        self.close_button.pack(side=tk.LEFT)
        self.send_button = ttk.Button(commands, text="Send to OneNote", style="OneNoteSend.Accent.TButton", command=self.send)
        self.send_button.pack(side=tk.RIGHT)
        self.send_button.bind("<Double-Button-1>", lambda _: "break")
        self.cancel_button = ttk.Button(commands, text="Cancel request", command=self.cancel)
        receipt_controls = ttk.Frame(outer)
        receipt_controls.grid(row=6, sticky=tk.EW, pady=(8, 0))
        self.engine_button = ttk.Button(receipt_controls, text="Change engine…", style="Compact.TButton", command=self.choose_engine)
        self.engine_button.pack(side=tk.LEFT)
        self.details_button = ttk.Button(receipt_controls, text="Result details…", command=self.show_receipts)
        self.title_var.trace_add("write", self._title_changed)
        outer.bind("<Configure>", self._resize)
        try:
            self._destination = load_destination(self.destination_path)
        except (OSError, ValueError):
            self._notice = ("Choose an existing section; the saved Send destination needs reselection.", "warning")
        self._show_destination()
        self._refresh_engine()
        self.capture_source()
        self._sync()
        self.title_entry.focus_set()

    def _resize(self, event):
        width = max(260, event.width - 8)
        for label in (self.title_preview, self.title_hint):
            label.configure(wraplength=width)
        self.status_label.configure(wraplength=max(200, width - 32))
        self.destination_label.configure(wraplength=max(200, width - self.destination_button.winfo_reqwidth() - 12))

    def _set_notice(self, text, tone="neutral"):
        self._notice = (text, tone)
        self._sync()

    @staticmethod
    def _visible(widget, visible, **options):
        if visible:
            if not widget.winfo_manager():
                widget.pack(**options)
        else:
            widget.pack_forget()

    @property
    def busy(self):
        return self._job is not None

    def _sync(self):
        idle = not self.busy and not self._blocked
        valid = self._validate_page()
        for widget, enabled in (
            (self.engine_button, idle), (self.destination_button, idle and self._client is not None),
            (self.refresh_button, idle),
            (self.send_button, idle and valid and self._client is not None and self._destination is not None
                and self._source_current and not self._receipt_unacknowledged),
            (self.cancel_button, self.busy), (self.details_button, bool(self.receipts)),
            (self.ack_button, idle and self._receipt_unacknowledged),
        ):
            widget.configure(state=tk.NORMAL if enabled else tk.DISABLED)
        self.title_entry.configure(state=tk.NORMAL if idle else tk.DISABLED)
        self._visible(self.cancel_button, self.busy, side=tk.RIGHT, padx=(0, 8))
        self._visible(self.details_button, bool(self.receipts), side=tk.RIGHT)
        self._visible(self.ack_button, self._receipt_unacknowledged, side=tk.TOP, anchor=tk.W, pady=(0, 4))
        self._visible(self.refresh_button, not self._source_current, side=tk.TOP, anchor=tk.W)
        if self._receipt_unacknowledged or not self._source_current:
            self.banner_commands.grid()
        else:
            self.banner_commands.grid_remove()
        if self._blocked:
            text, tone = "Process cleanup is unconfirmed. Further requests and closing are blocked.", "error"
            if self.receipts and self.receipts[-1].cleanup_blocked:
                text += " " + self.receipts[-1].message
            elif self._receipt_unacknowledged:
                text += " Earlier Send still needs attention: " + self.receipts[-1].message
        elif self._receipt_unacknowledged:
            text, tone = self.receipts[-1].message, "warning"
            if not self._source_current:
                text += " Input / Output also changed."
        elif self.busy:
            text, tone = self._notice
        elif not self._source_current:
            text, tone = "Input / Output changed. Use its current text before sending.", "warning"
        elif self._client is None:
            text, tone = "Engine needs setup. Choose Change engine… to select its launcher on this PC.", "warning"
        elif self._validation_error:
            text, tone = self._validation_error, "warning"
        elif not self._destination:
            text, tone = "Choose an existing notebook / section using Change… Nothing has been sent.", "neutral"
        else:
            text, tone = self._notice
        self.status_tone = tone
        self.status_var.set(text)
        color = {"neutral": "accent", "success": "success", "warning": "warning", "error": "error"}[tone]
        self.status_stripe.configure(background=COLORS[color])

    def _validate_page(self):
        title = self.title_var.get().strip()
        self.final_title_var.set("Title to send: " + title)
        self.title_count_var.set(f"{len(title)} / 255 characters")
        self.title_hint_var.set("Suggested title — edit it if needed. The complete page text is below."
                                if title == self._suggestion else "Input / Output stays intact; one new plain-text page will be created.")
        try:
            normalize_text(title, getattr(self, "_source", ""))
        except SendError as exc:
            self._validation_error = str(exc)
            return False
        self._validation_error = None
        return True

    def _show_destination(self):
        self.destination_var.set(self._destination.label if self._destination else "Choose an existing notebook / section.")

    def _engine_selection(self):
        settings = load_onenote_settings(self.settings_path)
        launcher = settings.launcher_path
        if launcher is None:
            launcher = discover_direct_sibling_python_onenote_launcher(self.application_root)
        if launcher is None or not launcher.is_file():
            raise SendError("Choose an existing python-onenote.bat. A broken saved engine must be repaired explicitly.")
        return settings.launcher_path, launcher

    def _refresh_engine(self):
        try:
            key = self._engine_selection()
            if key != self._engine_key:
                self._client = self.client_factory(key[1])
                self._engine_key = key
            return True
        except (ValueError, OSError):
            self._client = None
            self._engine_key = None
            return False

    def choose_engine(self):
        if self.busy or self._blocked:
            return
        selected = filedialog.askopenfilename(parent=self.window, title="Choose Python OneNote launcher",
                      filetypes=[("Python OneNote launcher", "python-onenote.bat")])
        if not selected:
            return
        try:
            try:
                settings = load_onenote_settings(self.settings_path)
                notebook = settings.notebook
            except OneNoteSettingsError as exc:
                notebook = exc.notebook
            save_onenote_settings(self.settings_path, OneNoteSettings(Path(selected), notebook))
        except (ValueError, OSError):
            self._set_notice("Choose an existing absolute python-onenote.bat launcher.", "warning")
            return
        self._client = None
        self._engine_key = None
        self._invalidate()
        self._refresh_engine()
        self._set_notice("Engine saved. Check the title and text before choosing Send.")

    def _invalidate(self):
        self._generation += 1
        if self.busy:
            self._cancel.set()

    def _title_changed(self, *_args):
        if self._setting_title:
            return
        self._invalidate()
        self._set_notice("Check the updated title, then choose Send to OneNote." if not self.busy else
                         "Title changed. Cancelling; wait for the result before another send.",
                         "warning" if self.busy else "neutral")

    def source_changed(self):
        self._source_current = False
        self._invalidate()
        self._set_notice("Input / Output changed. Use its current text before sending." if not self.busy else
                         "Source changed. Cancelling; a Send already dispatched may have created a page.", "warning")

    def capture_source(self):
        if self.busy or self._blocked:
            return
        self._invalidate()
        self._source, self._source_revision = self.source_reader()
        self._source_current = True
        self._setting_title = True
        self._suggestion = suggested_title(self._source)
        self.title_var.set(self._suggestion)
        self._setting_title = False
        self._show_body(self._source.replace("\r\n", "\n").replace("\r", "\n"))
        self._set_notice("Check the destination, title and complete text. Send creates one new page.")

    def _show_body(self, body):
        self.body_text.configure(state=tk.NORMAL)
        self.body_text.delete("1.0", tk.END)
        self.body_text.insert("1.0", body)
        self.body_text.configure(state=tk.DISABLED)
        self.count_var.set(f"Page text · {len(body):,} characters")

    def _current_source(self):
        text, revision = self.source_reader()
        if not self._source_current or text != self._source or revision != self._source_revision:
            self.source_changed()
            return False
        return True

    def _start(self, kind, operation):
        if self.busy or self._blocked:
            return
        self._generation += 1
        generation = self._generation
        self._job = kind
        self._cancel = cancel = threading.Event()
        def work():
            try:
                result, error = operation(cancel), None
            except OneNoteError as exc:
                result = SendOutcome("none", cleanup_blocked=True) if exc.code == "transport.cleanup" else None
                error = "The OneNote step could not complete. No execution request was issued. Check setup and select the destination again."
            except SendError as exc:
                result, error = None, str(exc)
            except Exception:
                result, error = None, "The OneNote step could not complete. No execution request was issued."
            self._queue.put((generation, kind, result, error))
        self._sync()
        try:
            threading.Thread(target=work, daemon=True, name="onenote-send").start()
        except Exception:
            self._job = None
            self._set_notice("The request could not start. Choose Send again when ready.", "error")
            return
        self.window.after(40, self._poll)

    def _read_metadata(self, client, notebook, cancel):
        before = client.prepare(self.session_reader, cancel)
        result = client.inventory(notebook, cancel)
        if self.session_reader() != before:
            raise SendError("OneNote changed while listing destinations. Choose the destination again.")
        return result

    def choose_destination(self):
        if self.busy or self._blocked or not self._refresh_engine():
            self._sync()
            return
        self._invalidate()
        client = self._client
        self._notice = ("Listing open notebook names…", "neutral")
        self._start("notebooks", lambda cancel: self._read_metadata(client, None, cancel))

    def _send_key_press(self, _event=None):
        if not self._send_key_down:
            self._send_key_down = True
            self.send()
        return "break"

    def _send_key_release(self, _event=None):
        self._send_key_down = False

    def _focus_from_body(self, *, backwards=False):
        target = self.body_text.tk_focusPrev() if backwards else self.body_text.tk_focusNext()
        if target is not None:
            target.focus_set()
        return "break"

    def _confirmation_current(self, confirmed):
        now = self.clock()
        if not confirmed <= now < confirmed + timedelta(seconds=300):
            raise SendError("Confirmation expired. Check the title and text, then choose Send again.")

    def send(self):
        if self.busy or self._blocked or self._receipt_unacknowledged or not self._destination or not self._current_source():
            return
        old_engine_key = self._engine_key
        if not self._refresh_engine() or self._engine_key != old_engine_key:
            self._set_notice("Engine changed. Check setup and choose Send again.", "warning")
            return
        try:
            title, body = normalize_text(self.title_var.get(), self._source)
        except SendError as exc:
            self._set_notice(str(exc), "warning")
            return
        if title != self.title_var.get() or body != self.body_text.get("1.0", "end-1c"):
            self._setting_title = True
            self.title_var.set(title)
            self._setting_title = False
            self._show_body(body)
            self._set_notice("Title spacing adjusted. Check the displayed title and text, then choose Send.", "warning")
            return
        gesture = self.gesture_clock()
        if self._last_send_gesture is not None and gesture - self._last_send_gesture < 0.5:
            return  # A completed fast request must not turn a double-click into two pages.
        self._last_send_gesture = gesture
        confirmed = self.clock()  # Authority starts at this affirmative click, before planning.
        client, engine_key, destination = self._client, self._engine_key, self._destination
        source, source_revision = self._source, self._source_revision
        expected = canonical_plan(destination.section_id, title, body)
        gate = threading.Event()
        def send_once(cancel):
            before = self.session_reader()
            if not before:
                raise SendError("Open OneNote and the chosen notebook before sending.")
            review = client.plan(destination, title, body, cancel)
            if review.destination != destination or review.document() != expected:
                raise SendError("The engine returned a different plan. Nothing was sent.")
            authorization = review.authorize(confirmed)
            self._confirmation_current(confirmed)
            if cancel.is_set():
                raise SendError("Cancelled before Send. No execution request was issued.")
            if client.prepare(self.session_reader, cancel) != before:
                raise SendError("OneNote session changed. Choose Send again; nothing was sent.")
            choices = client.inventory(destination.path[0], cancel)
            if destination not in choices:
                raise SendError("The exact destination is unavailable or changed. Choose the section again; nothing was sent.")
            # Hand off to Tk for a final source/title/destination check. Never read widgets
            # from the worker. Keep this same worker, cancel token and authority in flight.
            self._queue.put((None, "send_ready", (gate, cancel, destination, engine_key,
                                                  title, body, source, source_revision), None))
            while not gate.wait(0.04):
                if cancel.is_set():
                    raise SendError("Cancelled before Send. No execution request was issued.")
                self._confirmation_current(confirmed)
            if self._engine_selection() != engine_key or self.session_reader() != before:
                raise SendError("Engine or OneNote session changed. Check setup and choose Send again; nothing was sent.")
            if cancel.is_set():
                raise SendError("Cancelled before Send. No execution request was issued.")
            self._confirmation_current(confirmed)
            try:
                return client.execute(review, authorization, cancel)
            except SendError:
                # The client's documented validation errors occur before its
                # transport attempt (changed/expired review or pre-cancel).
                raise
            except Exception as exc:
                return SendOutcome("unknown", cleanup_blocked=getattr(exc, "code", None) == "transport.cleanup")
        self._notice = ("Checking the exact section, then sending one page… Cancellation cannot undo a page already created.", "neutral")
        self._start("send", send_once)

    def _approve_preflight(self, snapshot):
        gate, cancel, destination, engine_key, title, body, source, revision = snapshot
        current_source = None
        try:
            current_source = self.source_reader()
            current_engine = self._engine_selection()
            unchanged = (not cancel.is_set() and self._source_current
                         and current_source == (source, revision)
                         and self._source == source and self._source_revision == revision
                         and self._destination == destination and current_engine == engine_key
                         and self._engine_key == engine_key and self.title_var.get() == title
                         and self.body_text.get("1.0", "end-1c") == body)
            if not unchanged:
                cancel.set()
                self._notice = ("The source or setup changed before sending. Nothing was sent; check it and choose Send again.", "warning")
                if current_source != (source, revision):
                    self._source_current = False
        except Exception:
            cancel.set()  # Fail closed even for an unexpected Tk/source callback failure.
            self._notice = ("The final check could not complete. Nothing was sent.", "error")
        finally:
            gate.set()

    def _poll(self):
        try:
            generation, kind, result, error = self._queue.get_nowait()
        except queue.Empty:
            self.window.after(40, self._poll)
            return
        if kind == "send_ready":
            try:
                self._approve_preflight(result)
                self._sync()
            finally:
                self.window.after(40, self._poll)
            return
        self._job = None
        # Write outcomes never follow the read-generation discard rule.
        if kind == "send":
            receipt = result if isinstance(result, SendOutcome) else SendOutcome("none")
            self.receipts.append(receipt)
            self._blocked |= receipt.cleanup_blocked
            self._receipt_unacknowledged = receipt.state not in {"none", "content_verified"}
            self._notice = (receipt.message if result is not None else error,
                            "success" if receipt.state == "content_verified" else "error" if receipt.state == "none" else "warning")
            self.show()
        elif isinstance(result, SendOutcome) and result.cleanup_blocked:
            self._blocked = True  # Read cleanup uncertainty is not a mutation receipt.
        elif generation != self._generation or self._cancel.is_set():
            self._notice = ("Request cancelled. Nothing was sent.", "neutral")
        elif error:
            self._notice = (error, "error")
        elif kind in {"notebooks", "sections"}:
            if not result:
                self._notice = ("No available destinations returned. Open the intended notebook in OneNote and choose again.", "warning")
            else:
                chosen = DestinationChoice(self.window, "Choose notebook" if kind == "notebooks" else "Choose section", result).show()
                if generation != self._generation:
                    self._notice = ("The choice changed. Choose the destination again.", "warning")
                elif chosen is not None:
                    if kind == "notebooks":
                        client = self._client
                        self._notice = ("Listing sections in the chosen notebook…", "neutral")
                        self._start("sections", lambda cancel: self._read_metadata(client, chosen, cancel))
                    else:
                        try:
                            save_destination(self.destination_path, chosen)
                        except (ValueError, OSError):
                            self._notice = ("Destination could not be saved. Your previous choice is unchanged.", "error")
                        else:
                            self._destination = chosen
                            self._show_destination()
                            self._notice = ("Destination remembered. Check the title and text, then choose Send to OneNote.", "neutral")
                else:
                    self._notice = ("Destination choice cancelled. Check the current page before sending.", "neutral")
        self._sync()

    def cancel(self):
        if self.busy:
            self._invalidate()
            self._notice = ("Cancelling and waiting for process cleanup. A Send already dispatched may have created a page.", "warning")
        else:
            self._notice = ("Nothing further was sent.", "neutral")
        self._sync()

    def acknowledge(self):
        if self.busy or self._blocked:
            return
        self._receipt_unacknowledged = False
        self._set_notice("Warning acknowledged. The recorded result is unchanged; no automatic retry was made.")

    def show_receipts(self):
        if not self.receipts:
            return
        window = tk.Toplevel(self.window)
        window.title("OneNote Send results — this session only")
        configure_standard_window(window, self.window)
        place_child_window(window, self.window, size=(660, 400))
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Button(frame, text="Close", command=window.destroy).pack(side=tk.BOTTOM, pady=(8, 0))
        text = tk.Text(frame, wrap=tk.WORD, padx=8, pady=8)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(frame, command=text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text.configure(yscrollcommand=scroll.set)
        for index, receipt in enumerate(self.receipts, 1):
            text.insert(tk.END, f"Send {index}: {receipt.message}\n")
            if receipt.page_id:
                text.insert(tk.END, f"Created page ID (for deliberate inspection):\n{receipt.page_id}\n")
            text.insert(tk.END, "\n")
        text.configure(state=tk.DISABLED)
        window.bind("<Escape>", lambda _: window.destroy())

    def show(self):
        self.window.deiconify()
        self.window.lift()
        self._sync()

    def close(self):
        if self.busy:
            self.cancel()
            self._set_notice("Wait for the result before closing. Cancellation does not undo a page creation.", "warning")
            return False
        if self._blocked:
            self.show()
            return False
        if self._receipt_unacknowledged:
            self.show()
            if not messagebox.askyesno("OneNote result needs attention",
                    "A page may exist or be incomplete. Inspect OneNote before sending again.\n\n"
                    "Acknowledge this result and close? Result details remain available until you quit Context Palette.", parent=self.window):
                return False
            self.acknowledge()
        # Keep receipts even when hidden. Reopening cannot conceal/retry a send.
        self.window.withdraw()
        return True
