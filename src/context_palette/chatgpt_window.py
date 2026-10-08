"""Attended text-chat trial; messages stay in memory and Tk stays on its thread."""
from __future__ import annotations

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

from .actions import ACTIVE_STATE, Action, ActionError
from .action_bound_quick_actions import action_bound_quick_group
from .chatgpt_auth import ChatGPTAuth
from .chatgpt_client import ChatGPTClient, ChatMessage, MAX_MESSAGES
from .chatgpt_http import ChatGPTError
from .style import COLORS, DEFAULT_FONT, HEADING_FONT
from .window_geometry import configure_standard_window, place_child_window


class ChatGPTWindow:
    """One explicit command at a time; provisional answers cannot be placed."""

    def __init__(self, parent, *, settings_path: Path, initial_text: str,
                 expected_workspace: str,
                 apply_text: Callable[[str, Callable[[], bool], str], bool],
                 copy_text: Callable[[str], None], on_close: Callable[[], None],
                 prompt_actions: Callable[[], list[Action]] | None = None,
                 prompt_reader: Callable[[str], tuple[str, str]] | None = None,
                 auth_factory=ChatGPTAuth, client_factory=ChatGPTClient):
        self.apply_text, self.copy_text, self.on_close = apply_text, copy_text, on_close
        self._expected_workspace = expected_workspace
        self.prompt_actions, self.prompt_reader = prompt_actions, prompt_reader
        self._prompt_submenus = []
        self._auth = None
        self._account = None  # Immutable display snapshot; no locked auth reads while busy.
        self._client = client_factory()
        self._history: list[ChatMessage] = []
        self._models = ()
        self._answer = ""
        self._generation = 0
        self._job = None
        self._cancel = threading.Event()
        self._queue = queue.Queue()
        self._closed = False
        self._closing = False
        self._poll_id = None
        self._pending_question = ""
        self._send_key_down = False
        self._needs_sign_in = False
        self.window = tk.Toplevel(parent)
        self.window.title("ChatGPT — Context Palette")
        configure_standard_window(self.window, parent)
        place_child_window(self.window, parent, size=(780, 680))
        self.window.minsize(600, 480)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.bind("<Control-Return>", self._send_key_press)
        self.window.bind("<KeyRelease-Return>", self._send_key_release)
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)
        heading = ttk.Frame(outer)
        heading.grid(row=0, sticky=tk.EW)
        heading.columnconfigure(0, weight=1)
        ttk.Label(heading, text="ChatGPT", style="Title.TLabel").grid(row=0, sticky=tk.W)
        self.connect_button = ttk.Button(heading, text="Continue with ChatGPT", command=self.connect)
        self.connect_button.grid(row=0, column=1, padx=(8, 0))
        self.forget_button = ttk.Button(heading, text="Forget sign-in", command=self.forget)
        self.forget_button.grid(row=0, column=2, padx=(6, 0))
        model_row = ttk.Frame(outer)
        model_row.grid(row=1, sticky=tk.EW, pady=(8, 8))
        model_row.columnconfigure(2, weight=1)
        ttk.Label(model_row, text="Model:").grid(row=0, column=0, padx=(0, 6))
        self.model_var = tk.StringVar()
        self.model_picker = ttk.Combobox(model_row, textvariable=self.model_var, state="disabled", width=26)
        self.model_picker.grid(row=0, column=1, sticky=tk.W)
        self.account_var = tk.StringVar(value="Not signed in")
        ttk.Label(model_row, textvariable=self.account_var, foreground=COLORS["muted_text"],
                  wraplength=290).grid(row=0, column=2, sticky=tk.E, padx=(8, 0))
        transcript_frame = ttk.Frame(outer)
        transcript_frame.grid(row=2, sticky=tk.NSEW)
        self.transcript = self._text_box(transcript_frame, height=10)
        self.transcript.configure(state=tk.DISABLED)
        self.transcript.tag_configure("speaker", font=HEADING_FONT, foreground=COLORS["accent"], spacing1=10, spacing3=4)
        self.transcript.tag_configure("note", foreground=COLORS["muted_text"], spacing1=8)
        self.transcript.tag_configure("heading", font=HEADING_FONT, spacing1=8, spacing3=4)
        self.transcript.tag_configure("bold", font=HEADING_FONT)
        self.transcript.tag_configure("code", font=("Consolas", 10), background=COLORS["row_light"])
        composer_frame = ttk.Frame(outer)
        composer_frame.grid(row=3, sticky=tk.EW, pady=(10, 0))
        composer_heading = ttk.Frame(composer_frame)
        composer_heading.pack(fill=tk.X)
        ttk.Label(composer_heading, text="Your message", style="Heading.TLabel").pack(side=tk.LEFT)
        self.prompts_button = ttk.Menubutton(composer_heading, text="Prompts", takefocus=True)
        self.prompts_button.pack(side=tk.RIGHT)
        self.prompts_menu = tk.Menu(self.prompts_button, tearoff=False, postcommand=self._refresh_prompt_menu)
        self.prompts_button.configure(menu=self.prompts_menu)
        composer_text = ttk.Frame(composer_frame)
        composer_text.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.composer = self._text_box(composer_text, height=5)
        self.composer.insert("1.0", initial_text)
        self.composer.configure(undo=True, autoseparators=True, maxundo=30)
        self.composer.bind("<<Modified>>", self._message_changed)
        self.composer.bind("<Tab>", lambda _event: self._focus_send())
        self.composer.bind("<Shift-Tab>", lambda _event: self._focus_model())
        self.composer.bind("<ISO_Left_Tab>", lambda _event: self._focus_model())
        self.notice_var = tk.StringVar(value="Only the messages in this window are sent. Answers are brief by default.")
        self.notice_label = ttk.Label(outer, textvariable=self.notice_var, wraplength=740,
                                      foreground=COLORS["muted_text"])
        self.notice_label.grid(row=4, sticky=tk.EW, pady=(8, 6))
        commands = ttk.Frame(outer)
        commands.grid(row=5, sticky=tk.EW)
        self.new_button = ttk.Button(commands, text="New chat", command=self.new_chat)
        self.new_button.pack(side=tk.LEFT)
        self.copy_button = ttk.Button(commands, text="Copy answer", command=self.copy_answer)
        self.copy_button.pack(side=tk.LEFT, padx=(6, 0))
        self.use_button = ttk.Button(commands, text="Use answer…", command=self.use_answer)
        self.use_button.pack(side=tk.LEFT, padx=(6, 0))
        self.close_button = ttk.Button(commands, text="Close", command=self.close)
        self.close_button.pack(side=tk.RIGHT)
        self.stop_button = ttk.Button(commands, text="Stop", command=self.cancel)
        self.send_button = ttk.Button(commands, text="Send", style="Accent.TButton", command=self.send)
        self.send_button.pack(side=tk.RIGHT, padx=(6, 6))
        self.window.bind("<Configure>", self._resize_notice)
        try:
            self._auth = auth_factory(settings_path)
        except ChatGPTError as exc:
            self._notice(str(exc), error=True)
        self._refresh_controls()
        self.composer.focus_set()

    @staticmethod
    def _text_box(parent, *, height):
        text = tk.Text(parent, wrap=tk.WORD, height=height, font=DEFAULT_FONT,
                       padx=10, pady=8, background=COLORS["surface"], foreground=COLORS["text"],
                       selectbackground=COLORS["accent"], selectforeground=COLORS["white"],
                       highlightthickness=1, highlightbackground=COLORS["border"],
                       highlightcolor=COLORS["focus"], relief=tk.FLAT, undo=False)
        scroll = ttk.Scrollbar(parent, command=text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text.configure(yscrollcommand=scroll.set)
        return text

    @property
    def busy(self):
        return self._job is not None

    def _resize_notice(self, event):
        if event.widget == self.window:
            self.notice_label.configure(wraplength=max(300, event.width - 32))

    def _message_changed(self, _event=None):
        if self.composer.edit_modified():
            self.composer.edit_modified(False)
            self._refresh_controls()

    def _focus_send(self):
        self.send_button.focus_set()
        return "break"

    def _focus_model(self):
        if self.prompts_button.instate(["!disabled"]):
            self.prompts_button.focus_set()
        else:
            self.model_picker.focus_set()
        return "break"

    def _refresh_prompt_menu(self):
        """Reuse the live automatic hierarchy; menu opening has no remote effects."""
        for submenu in reversed(self._prompt_submenus):
            submenu.destroy()
        self._prompt_submenus.clear()
        self.prompts_menu.delete(0, tk.END)
        if self.busy or self._closed or self._closing:
            self.prompts_menu.add_command(label="Wait for the current request", state=tk.DISABLED)
            return
        if self.prompt_actions is None or self.prompt_reader is None:
            self.prompts_menu.add_command(label="No prompts available", state=tk.DISABLED)
            return
        actions = [action for action in self.prompt_actions()
                   if action.type == "ai_prompt" and action.state == ACTIVE_STATE]
        group = action_bound_quick_group(actions, group_id="prompts", label="Prompts", action_type="ai_prompt")
        by_id = {action.id: action for action in actions}

        def populate(menu, node):
            for action_id in node.action_ids:
                action = by_id.get(action_id)
                if action is not None:
                    menu.add_command(label=action.compact_display_text,
                                     command=lambda selected_id=action_id: self.insert_prompt(selected_id))
            if node.action_ids and node.items:
                menu.add_separator()
            for child in node.items:
                submenu = tk.Menu(menu, tearoff=False)
                self._prompt_submenus.append(submenu)
                populate(submenu, child)
                menu.add_cascade(label=child.label, menu=submenu)
        populate(self.prompts_menu, group)
        if self.prompts_menu.index(tk.END) is None:
            self.prompts_menu.add_command(label="No saved prompts yet", state=tk.DISABLED)

    def insert_prompt(self, action_id):
        """Insert one current prompt as an undoable draft edit, never Send it."""
        if self.busy or self._closed or self._closing or self.prompt_reader is None:
            return
        try:
            title, value = self.prompt_reader(action_id)
        except ActionError as exc:
            self._notice(str(exc), error=True)
            return
        if not isinstance(value, str) or not value.strip():
            self._notice("The prompt produced empty text. Check its value or clipboard input.", error=True)
            return
        position = self.composer.index(tk.INSERT)
        before = self.composer.get("1.0", position)
        after = self.composer.get(position, "end-1c")
        prefix = "\n\n" if before and not before.endswith("\n") else ""
        suffix = "\n\n" if after and not after.startswith("\n") else ""
        self.composer.edit_separator()
        self.composer.insert(position, prefix + value + suffix)
        self.composer.edit_separator()
        self.composer.tag_remove(tk.SEL, "1.0", tk.END)
        self.composer.see(tk.INSERT)
        self.composer.focus_set()
        self._notice(f"Inserted {title}. Edit your message, then choose Send.")
        self._refresh_controls()

    def _send_key_press(self, _event=None):
        if not self._send_key_down:
            self._send_key_down = True
            self.send()
        return "break"

    def _send_key_release(self, _event=None):
        self._send_key_down = False

    def _notice(self, text, *, error=False):
        self.notice_var.set(text)
        self.notice_label.configure(foreground=COLORS["error"] if error else COLORS["muted_text"])

    def _refresh_controls(self):
        idle = not self.busy and not self._closed and not self._closing
        if self._auth is not None and not self.busy:
            self._account = self._auth.account
        account = self._account
        usable = account is not None and account.can_use_plan
        needs_sign_in = self._needs_sign_in or bool(getattr(account, "needs_reauthorization", False))
        self.account_var.set(account.display_label if account is not None else "Not signed in")
        self.connect_button.configure(text="Load models" if usable and not needs_sign_in else "Continue with ChatGPT",
                                      state=tk.NORMAL if idle and self._auth is not None else tk.DISABLED)
        self.forget_button.configure(state=tk.NORMAL if idle and account is not None else tk.DISABLED)
        self.model_picker.configure(state="readonly" if idle and self._models else tk.DISABLED)
        self.prompts_button.configure(state=tk.NORMAL if idle and self.prompt_actions is not None
                                      and self.prompt_reader is not None else tk.DISABLED)
        self.new_button.configure(state=tk.NORMAL if idle else tk.DISABLED)
        self.composer.configure(state=tk.NORMAL if idle else tk.DISABLED)
        self.send_button.configure(state=tk.NORMAL if idle and usable and self._models
                                   and self.composer.get("1.0", "end-1c").strip() else tk.DISABLED)
        answer_state = tk.NORMAL if idle and self._answer else tk.DISABLED
        self.copy_button.configure(state=answer_state)
        self.use_button.configure(state=answer_state)
        if self.busy:
            self.stop_button.pack(side=tk.RIGHT, padx=(6, 0))
            self.stop_button.configure(state=tk.DISABLED if self._cancel.is_set() else tk.NORMAL)
        else:
            self.stop_button.pack_forget()

    def _start(self, kind, work):
        if self.busy or self._closed or self._closing:
            return
        self._generation += 1
        generation = self._generation
        self._cancel = threading.Event()
        cancel = self._cancel

        def worker():
            try:
                result = work(cancel, generation)
                if cancel.is_set():
                    raise ChatGPTError("cancelled", "Stopped. No answer was applied; a sent request may still use your allowance.")
                event = (generation, kind, result, None)
            except ChatGPTError as exc:
                event = (generation, kind, None, exc)
            except Exception:
                # Never surface raw exceptions that may contain tokens or user messages.
                event = (generation, kind, None, "The ChatGPT request could not finish. Nothing was applied. Try again explicitly.")
            self._queue.put(event)

        self._job = threading.Thread(target=worker, daemon=True, name="palette-chatgpt")
        self._job.start()
        self._refresh_controls()
        self._poll_id = self.window.after(40, self._poll)

    def connect(self):
        if self.busy or self._auth is None:
            return
        self._models = ()
        force_sign_in = self._needs_sign_in or bool(getattr(self._account, "needs_reauthorization", False))
        self._notice("Connecting… Complete any sign-in request in your browser. No message is sent.")

        def work(cancel, _generation):
            account = self._auth.account
            if account is None or not account.can_use_plan or force_sign_in:
                self._auth.sign_in(cancel)
            token = self._auth.access_token(cancel)
            return self._client.list_models(token, cancel)
        self._start("connect", work)

    def send(self):
        if self.busy or self._auth is None or not self._models or self._closed:
            return
        question = self.composer.get("1.0", "end-1c")
        if not question.strip():
            return
        if len(self._history) + 2 > MAX_MESSAGES:
            self._notice("This trial chat is full. Choose New chat to start another conversation.", error=True)
            return
        chosen = self.model_picker.current()
        if not 0 <= chosen < len(self._models):
            self._notice("Choose an available model first.", error=True)
            return
        model = self._models[chosen].slug
        messages = tuple(self._history) + (ChatMessage("user", question),)
        self._pending_question = question
        self._answer = ""
        self._append("\nYou\n", "speaker")
        self._append(question + "\n")
        self._append("\nChatGPT\n", "speaker")
        self._stream_start = self.transcript.index("end-1c")
        self._notice("Receiving an answer… Your message and completed conversation history are sent using your ChatGPT plan.")

        def work(cancel, generation):
            token = self._auth.access_token(cancel)
            return self._client.respond(token, model, messages,
                lambda delta: self._queue.put((generation, "delta", delta, None)), cancel)
        self._start("send", work)

    def _append(self, text, tag=None):
        self.transcript.configure(state=tk.NORMAL)
        self.transcript.insert(tk.END, text, tag or ())
        self.transcript.configure(state=tk.DISABLED)
        self.transcript.see(tk.END)

    def _render_completed(self, answer):
        """Readable text formatting only; no HTML, images, links or scripts execute."""
        self.transcript.configure(state=tk.NORMAL)
        self.transcript.delete(self._stream_start, "end-1c")
        code = False
        for line in answer.splitlines(keepends=True):
            if line.lstrip().startswith("```"):
                code = not code
                self.transcript.insert(tk.END, "\n")
            elif code:
                self.transcript.insert(tk.END, line, "code")
            elif line.startswith(("# ", "## ", "### ")):
                self.transcript.insert(tk.END, line.lstrip("# "), "heading")
            else:
                parts = line.split("**")
                for index, part in enumerate(parts):
                    self.transcript.insert(tk.END, part, "bold" if index % 2 else ())
        self.transcript.insert(tk.END, "\n")
        self.transcript.configure(state=tk.DISABLED)
        self.transcript.see(tk.END)

    def _poll(self):
        self._poll_id = None
        if self._closed:
            return
        terminal = False
        while True:
            try:
                generation, kind, value, error = self._queue.get_nowait()
            except queue.Empty:
                break
            if generation != self._generation:
                continue
            if kind == "delta":
                if not self._cancel.is_set() and not self._closing:
                    self._append(value)
                continue
            terminal = True
            self._job = None
            if self._closing:
                self._finish_close()
                return
            if error or self._cancel.is_set():
                if isinstance(error, ChatGPTError) and error.code in {
                    "unauthorized", "invalid_token", "invalid_grant", "invalid_client",
                    "refresh_uncertain", "refresh_token_expired", "refresh_token_invalidated",
                    "refresh_token_reused", "refresh_token_invalid", "session_expired",
                }:
                    self._needs_sign_in = True
                    self._models = ()
                self._notice(str(error) if error else "Stopped. Nothing was applied; a sent request may still use your allowance.", error=True)
                if kind == "send":
                    self._append("\n[Incomplete answer — unavailable for Use answer]\n", "note")
            elif kind == "connect":
                self._needs_sign_in = False
                self._models = value
                self.model_picker.configure(values=tuple(model.display_name for model in value))
                if value:
                    self.model_picker.current(0)
                    self._notice("Ready. Check your message, then choose Send. This chat is separate from your ChatGPT history.")
                else:
                    self._notice("No models are available for this account. Check ChatGPT plan access.", error=True)
            elif kind == "send":
                self._answer = value
                self._history.extend((ChatMessage("user", self._pending_question), ChatMessage("assistant", value)))
                self._render_completed(value)
                self.composer.configure(state=tk.NORMAL)
                self.composer.delete("1.0", tk.END)
                self.composer.focus_set()
                self._notice("Answer complete. Ask a follow-up, copy it, or choose Use answer.")
            self._refresh_controls()
        if self.busy and not terminal:
            self._poll_id = self.window.after(40, self._poll)

    def cancel(self):
        if self.busy:
            self._cancel.set()
            self._notice("Stopping… Waiting for the current request to finish. Nothing will be applied.")
            self._refresh_controls()

    def new_chat(self):
        if self.busy:
            return
        self._history.clear()
        self._answer = ""
        self._generation += 1
        self.transcript.configure(state=tk.NORMAL)
        self.transcript.delete("1.0", tk.END)
        self.transcript.configure(state=tk.DISABLED)
        self._notice("New chat. Only messages you send here are included; nothing is saved as chat history.")
        self._refresh_controls()

    def forget(self):
        if self.busy or self._auth is None:
            return
        try:
            self._auth.sign_out()
        except ChatGPTError as exc:
            self._notice(str(exc), error=True)
            return
        self._models = ()
        self._needs_sign_in = False
        self.model_var.set("")
        self.new_chat()
        self._notice("Local sign-in forgotten. Manage the app's remaining access in ChatGPT settings.")
        self._refresh_controls()

    def copy_answer(self):
        if self._answer and not self.busy:
            self.copy_text(self._answer)
            self._notice("Completed answer copied.")

    def use_answer(self):
        if not self._answer or self.busy:
            return
        answer, generation = self._answer, self._generation
        is_current = lambda: not self._closed and not self.busy and self._generation == generation and self._answer == answer
        if self.apply_text(answer, is_current, self._expected_workspace):
            self._notice("Completed answer placed in Input / Output.")

    def show(self):
        self.window.deiconify()
        self.window.lift()
        self.composer.focus_set()

    def close(self):
        if self._closed:
            return True
        if self.busy:
            self._closing = True
            self.cancel()
            return False
        self._finish_close()
        return True

    def _finish_close(self):
        self._closed = True
        self._history.clear()
        self._answer = ""
        if self._poll_id is not None:
            self.window.after_cancel(self._poll_id)
            self._poll_id = None
        self.window.destroy()
        self.on_close()
