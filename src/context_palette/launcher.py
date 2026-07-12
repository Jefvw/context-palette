from __future__ import annotations

from pathlib import Path
import ctypes
import queue
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Callable

from .actions import (
    Action,
    ActionError,
    append_action,
    draft_copy_text_action,
    edited_copy_text_action,
    execute_action,
    expanded_action,
    load_combined_actions,
    load_actions,
    search_actions,
    trusted_action,
    update_action,
)
from .cheatsheets import (
    CheatSheet,
    CheatSheetError,
    CheatSheetItem,
    draft_action_from_cheatsheet_item,
    filter_cheatsheet,
    load_cheatsheets,
)
from .hotkeys import GlobalHotkey, send_copy_shortcut
from .inbox import InboxError, InboxItem, append_inbox_item, create_clipboard_item, load_inbox_items
from .inbox import update_inbox_item_state
from .single_instance import SingleInstanceServer
from .palette_state import (
    PaletteState,
    action_slots,
    load_palette_state,
    save_palette_state,
    toggle_pin,
)
from .window_layouts import (
    WindowLayoutError,
    apply_window_layout,
    browser_windows_without_launch_url,
    capture_window_snapshot,
    describe_window_layout,
    describe_window_snapshot,
    restore_window_snapshot,
    set_snapshot_launch_target,
)


class WidgetTooltip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.window: tk.Toplevel | None = None
        self.after_id: str | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def _schedule(self, _event=None) -> None:
        self.hide()
        self.after_id = self.widget.after(500, self.show)

    def show(self) -> None:
        self.after_id = None
        if not self.widget.winfo_exists():
            return
        window = tk.Toplevel(self.widget)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        label = tk.Label(
            window,
            text=self.text,
            justify=tk.LEFT,
            wraplength=360,
            background="#ffffe0",
            foreground="#202124",
            relief=tk.SOLID,
            borderwidth=1,
            padx=7,
            pady=5,
            font=("Segoe UI", 9),
        )
        label.pack()
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        window.geometry(f"+{x}+{y}")
        self.window = window

    def hide(self, _event=None) -> None:
        if self.after_id is not None:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
        if self.window is not None:
            self.window.destroy()
            self.window = None


class LauncherApp:
    def __init__(
        self,
        root: tk.Tk,
        actions_path: Path,
        local_actions_path: Path,
        palette_path: Path,
        inbox_path: Path,
        cheatsheets_dir: Path,
        instance_port: int,
    ) -> None:
        self.root = root
        self.actions_path = actions_path
        self.local_actions_path = local_actions_path
        self.local_action_ids: set[str] = set()
        self.palette_path = palette_path
        self.inbox_path = inbox_path
        self.cheatsheets_dir = cheatsheets_dir
        self.actions: list[Action] = []
        self.filtered_actions: list[Action] = []
        self.displayed_actions: list[Action] = []
        self.displayed_slots: list[int | None] = []
        self.slot_actions: dict[int, Action] = {}
        self.palette_state = PaletteState()
        self.show_requests: queue.Queue[str] = queue.Queue()
        self.instance_server = SingleInstanceServer(lambda: self.show_requests.put("show"), instance_port)
        self.hotkey = GlobalHotkey(lambda: self.show_requests.put("hotkey"))
        self.captured_selection: str | None = None
        self.source_foreground_handle: int | None = None
        self.hotkey_available = False
        self.hide_after_id: str | None = None
        self.search_entry: ttk.Entry | None = None
        self.search_var = tk.StringVar()
        self.context_var = tk.StringVar(value="General")
        self.preview_tooltip: ttk.Label | None = None
        self.preview_after_id: str | None = None
        self.widget_tooltips: list[WidgetTooltip] = []
        self.preview_var = tk.StringVar(value="Select an action to preview it.")
        self.status_var = tk.StringVar(value="Ready")
        self.search_var.trace_add("write", lambda *_args: self._refresh_results())

        self._build_ui()
        self._load_actions()
        self._load_palette_state()
        self._refresh_results()
        if not self.instance_server.start():
            self.root.after(0, self.root.destroy)
            return
        self.hotkey_available = self.hotkey.start()
        if self.hotkey_available:
            self.status_var.set("Ready. Ctrl+Alt+P shows Context Palette.")
        else:
            self.status_var.set("Ctrl+Alt+P is unavailable. Auto-hide is disabled.")
        self._poll_show_requests()

    def _build_ui(self) -> None:
        self.root.title("Context Palette")
        self.root.geometry("720x620")
        self.root.minsize(560, 460)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        self.root.bind("<FocusOut>", self._schedule_hide_when_inactive)
        self.root.bind("<FocusIn>", self._cancel_scheduled_hide)

        style = ttk.Style(self.root)
        style.configure("Heading.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Muted.TLabel", foreground="#5f6368")
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 6))
        style.configure("Pin.TLabel", background="#e8f0fe", foreground="#174ea6", padding=(7, 3))
        style.configure("Context.TLabel", background="#e6f4ea", foreground="#137333", padding=(7, 3))

        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)

        context_panel = ttk.Frame(outer)
        context_panel.pack(fill=tk.X, pady=(0, 10))
        context_text = ttk.Frame(context_panel)
        context_text.pack(side=tk.LEFT)
        ttk.Label(context_text, text="FOCUS CONTEXT", style="Muted.TLabel").pack(anchor=tk.W)
        ttk.Label(context_text, text="What are you working on?", style="Heading.TLabel").pack(anchor=tk.W)
        self.context_picker = ttk.Combobox(
            context_panel,
            textvariable=self.context_var,
            state="readonly",
            width=32,
            font=("Segoe UI", 10),
        )
        self.context_picker.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(18, 0), ipady=3)
        self.context_picker.bind("<<ComboboxSelected>>", lambda _event: self._change_focus_context())

        ttk.Separator(outer).pack(fill=tk.X, pady=(0, 10))
        ttk.Label(outer, text="Find an action", style="Heading.TLabel").pack(anchor=tk.W)
        ttk.Label(
            outer,
            text="Search by technology, task, context, or action name",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(1, 0))

        search_row = ttk.Frame(outer)
        search_row.pack(fill=tk.X, pady=(6, 7))

        search = ttk.Entry(search_row, textvariable=self.search_var, font=("Segoe UI", 11))
        self.search_entry = search
        search.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
        search.focus_set()
        search.bind("<KeyPress>", self._handle_keypress)
        search.bind("<Return>", lambda _event: self._execute_selected())

        run_button = ttk.Button(
            search_row,
            text="Run selected",
            command=self._execute_selected,
            style="Accent.TButton",
        )
        run_button.pack(side=tk.LEFT, padx=(8, 0))
        self._tooltip(run_button, "Execute the highlighted action. Check its action tooltip for input and effect.")

        slot_legend = ttk.Frame(outer)
        slot_legend.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(slot_legend, text="1–5  PINNED", style="Pin.TLabel").pack(side=tk.LEFT)
        ttk.Label(slot_legend, text="6–9  FOCUS CONTEXT", style="Context.TLabel").pack(
            side=tk.LEFT, padx=(7, 0)
        )
        ttk.Label(slot_legend, text="Double-click or press Enter to run", style="Muted.TLabel").pack(
            side=tk.RIGHT
        )

        results_frame = ttk.Frame(outer)
        results_frame.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.results = tk.Listbox(
            results_frame,
            activestyle="dotbox",
            font=("Segoe UI", 10),
            selectmode=tk.BROWSE,
            yscrollcommand=scrollbar.set,
            borderwidth=1,
            relief=tk.SOLID,
            highlightthickness=0,
        )
        self.results.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.configure(command=self.results.yview)
        self.results.bind("<KeyPress>", self._handle_keypress)
        self.results.bind("<<ListboxSelect>>", lambda _event: self._update_preview())
        self.results.bind("<Double-Button-1>", lambda _event: self._execute_selected())
        self.results.bind("<Return>", lambda _event: self._execute_selected())

        self.root.bind("<KeyPress>", self._handle_keypress)
        self.root.bind("<Escape>", lambda _event: self.hide_window())
        self.root.bind("<Control-l>", lambda _event: self.focus_search())
        self.root.bind("<Control-i>", lambda _event: self._capture_clipboard())

        workspace_panel = ttk.LabelFrame(outer, text=" Input / Output workspace ", padding=8)
        workspace_panel.pack(fill=tk.X, pady=(10, 0))
        workspace_header = ttk.Frame(workspace_panel)
        workspace_header.pack(fill=tk.X)
        ttk.Label(
            workspace_header,
            text="Selection, pasted input, and transformation results",
            style="Muted.TLabel",
        ).pack(side=tk.LEFT)
        paste_button = ttk.Button(workspace_header, text="Paste", command=self._paste_into_workspace)
        paste_button.pack(side=tk.RIGHT, padx=(6, 0))
        self._tooltip(paste_button, "Replace Input / Output with current clipboard text.")
        clear_button = ttk.Button(
            workspace_header, text="Clear", command=lambda: self._set_workspace_text("")
        )
        clear_button.pack(side=tk.RIGHT)
        self._tooltip(clear_button, "Empty the Input / Output workspace. This does not clear the clipboard.")
        self.workspace = tk.Text(
            workspace_panel,
            height=5,
            wrap=tk.WORD,
            undo=True,
            font=("Consolas", 10),
            borderwidth=1,
            relief=tk.SOLID,
            padx=7,
            pady=6,
        )
        self.workspace.pack(fill=tk.X, pady=(6, 0))

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=(10, 0))

        capture_button = ttk.Button(controls, text="Capture", command=self._capture_clipboard)
        capture_button.pack(side=tk.LEFT)
        self._tooltip(capture_button, "Save current clipboard text to Inbox after asking for a title.")
        snapshot_button = ttk.Button(controls, text="Snapshot", command=self._capture_window_snapshot)
        snapshot_button.pack(side=tk.LEFT, padx=(6, 0))
        self._tooltip(snapshot_button, "Capture visible window positions and create a Draft restore action in this context.")
        inbox_button = ttk.Button(controls, text="Inbox", command=self._show_inbox)
        inbox_button.pack(side=tk.LEFT, padx=(6, 0))
        self._tooltip(inbox_button, "Review captures and convert them into structured Draft actions.")
        sheets_button = ttk.Button(controls, text="Sheets", command=self._show_cheatsheets)
        sheets_button.pack(side=tk.LEFT, padx=(6, 0))
        self._tooltip(sheets_button, "Open searchable local cheat sheets and promote useful entries to Draft actions.")
        edit_button = ttk.Button(controls, text="Edit", command=self._edit_selected)
        edit_button.pack(side=tk.LEFT, padx=(6, 0))
        self._tooltip(edit_button, "Edit the selected Draft copy-text action. Other action types are currently read-only.")
        pin_button = ttk.Button(controls, text="Pin", command=self._toggle_selected_pin)
        pin_button.pack(side=tk.LEFT, padx=(6, 0))
        self._tooltip(pin_button, "Pin or unpin the selected action in stable slots 1–5.")
        trust_button = ttk.Button(controls, text="Trust", command=self._mark_selected_trusted)
        trust_button.pack(side=tk.LEFT, padx=(6, 0))
        self._tooltip(trust_button, "Mark the selected reviewed Draft action as Trusted after confirmation.")
        quit_button = ttk.Button(controls, text="Quit", command=self.quit_app)
        quit_button.pack(side=tk.RIGHT)
        self._tooltip(quit_button, "Stop Context Palette completely and release Ctrl+Alt+P.")
        hide_button = ttk.Button(controls, text="Hide", command=self.hide_window)
        hide_button.pack(side=tk.RIGHT, padx=(0, 6))
        self._tooltip(hide_button, "Hide the palette but keep it resident. Reopen with Ctrl+Alt+P.")
        help_button = ttk.Button(controls, text="Help", command=self._show_help)
        help_button.pack(side=tk.RIGHT, padx=(0, 6))
        self._tooltip(help_button, "Open the complete local Context Palette help document.")

        exit_controls = ttk.Frame(outer)
        exit_controls.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(exit_controls, textvariable=self.status_var, style="Muted.TLabel").pack(side=tk.LEFT)

    def _tooltip(self, widget: tk.Widget, text: str) -> None:
        self.widget_tooltips.append(WidgetTooltip(widget, text))

    def show_window(self) -> None:
        self._cancel_scheduled_hide()
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(100, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()
        self.search_var.set("")
        self._reload()
        self.root.after(80, self.focus_search)

    def hide_window(self) -> None:
        self._cancel_scheduled_hide()
        if not self.hotkey_available:
            self.status_var.set("Cannot hide because Ctrl+Alt+P is unavailable.")
            return
        self.status_var.set("Hidden. Use Ctrl+Alt+P to show Context Palette.")
        self.root.withdraw()

    def quit_app(self) -> None:
        self._hide_action_tooltip()
        self.hotkey.stop()
        self.instance_server.stop()
        self.root.destroy()

    def focus_search(self) -> str:
        if self.search_entry is not None:
            self.search_entry.focus_set()
            self.search_entry.selection_range(0, tk.END)
        return "break"

    def _schedule_hide_when_inactive(self, _event: tk.Event) -> None:
        if not self.hotkey_available:
            return
        self._cancel_scheduled_hide()
        self.hide_after_id = self.root.after(200, self._hide_if_inactive)

    def _cancel_scheduled_hide(self, _event: tk.Event | None = None) -> None:
        if self.hide_after_id is not None:
            self.root.after_cancel(self.hide_after_id)
            self.hide_after_id = None

    def _hide_if_inactive(self) -> None:
        self.hide_after_id = None
        focus = self.root.focus_get()
        if focus is None:
            self.root.withdraw()

    def _poll_show_requests(self) -> None:
        while True:
            try:
                request = self.show_requests.get_nowait()
            except queue.Empty:
                break
            if request == "hotkey":
                # Wait for Ctrl+Alt+P to be released, copy while the source app
                # still has focus, then show the palette.
                self.root.after(100, self._capture_selection)
            else:
                self.show_window()
        self.root.after(100, self._poll_show_requests)

    def _capture_selection(self) -> None:
        self.source_foreground_handle = int(ctypes.windll.user32.GetForegroundWindow())
        send_copy_shortcut()
        self.root.after(120, self._finish_selection_capture)

    def _finish_selection_capture(self) -> None:
        try:
            value = self.root.clipboard_get()
            self.captured_selection = value.strip() or None
        except tk.TclError:
            self.captured_selection = None
        self.show_window()
        if self.captured_selection is not None:
            self._set_workspace_text(self.captured_selection)

    def _load_actions(self) -> None:
        try:
            self.actions, self.local_action_ids = load_combined_actions(
                self.actions_path,
                self.local_actions_path,
            )
            self.status_var.set(f"Loaded {len(self.actions)} actions")
        except ActionError as exc:
            self.actions = []
            self.status_var.set("Could not load actions")
            messagebox.showerror("Context Palette", str(exc))

    def _action_storage_path(self, action: Action) -> Path:
        return self.local_actions_path if action.id in self.local_action_ids else self.actions_path

    def _load_palette_state(self) -> None:
        try:
            self.palette_state = load_palette_state(self.palette_path)
        except ActionError as exc:
            self.palette_state = PaletteState()
            messagebox.showerror("Context Palette", str(exc))
        contexts = sorted({action.context for action in self.actions}, key=str.casefold)
        if self.palette_state.focus_context not in contexts and contexts:
            self.palette_state = PaletteState(
                self.palette_state.pinned_action_ids,
                contexts[0],
                self.palette_state.context_slots,
            )
        self.context_picker["values"] = contexts
        self.context_var.set(self.palette_state.focus_context)

    def _change_focus_context(self) -> None:
        context = self.context_var.get().strip() or "General"
        self.palette_state = PaletteState(
            self.palette_state.pinned_action_ids,
            context,
            self.palette_state.context_slots,
        )
        save_palette_state(self.palette_path, self.palette_state)
        self._refresh_results()
        self.status_var.set(f"Focus context: {context}")

    def _refresh_results(self) -> None:
        self.filtered_actions = search_actions(self.actions, self.search_var.get())
        self.slot_actions = action_slots(self.actions, self.palette_state)
        matching_ids = {action.id for action in self.filtered_actions}
        slot_rows = [
            (slot, action)
            for slot, action in sorted(self.slot_actions.items())
            if action.id in matching_ids
        ]
        slot_row_ids = {action.id for _slot, action in slot_rows}
        remaining = [
            action for action in self.filtered_actions if action.id not in slot_row_ids
        ]
        self.displayed_actions = [action for _slot, action in slot_rows] + remaining
        self.displayed_slots = [slot for slot, _action in slot_rows] + [None] * len(remaining)
        self.results.delete(0, tk.END)
        for index, (action, slot) in enumerate(zip(self.displayed_actions, self.displayed_slots)):
            prefix = f"{slot}. " if slot is not None else "   "
            self.results.insert(tk.END, f"{prefix}{action.compact_display_text}")
            if slot is not None and 1 <= slot <= 5:
                self.results.itemconfigure(index, background="#e8f0fe", foreground="#174ea6")
            elif slot is not None and 6 <= slot <= 9:
                self.results.itemconfigure(index, background="#e6f4ea", foreground="#137333")
        if self.displayed_actions:
            self.results.selection_set(0)
            self.results.activate(0)
        self.status_var.set(
            f"{len(self.filtered_actions)} matches. Slots 1-5 pinned; 6-9 {self.palette_state.focus_context}."
        )
        self._update_preview()

    def _reload(self) -> None:
        self._load_actions()
        self._load_palette_state()
        self._refresh_results()

    def _toggle_selected_pin(self) -> None:
        action = self._selected_action()
        if action is None:
            self.status_var.set("No action selected")
            return
        try:
            self.palette_state = toggle_pin(self.palette_state, action.id)
            save_palette_state(self.palette_path, self.palette_state)
            self._refresh_results()
            verb = "Pinned" if action.id in self.palette_state.pinned_action_ids else "Unpinned"
            self.status_var.set(f"{verb}: {action.display_text}")
        except ActionError as exc:
            messagebox.showerror("Context Palette", str(exc))

    def _execute_selected(self) -> None:
        action = self._selected_action()
        if action is None:
            self.status_var.set("No action selected")
            return

        try:
            message = execute_action(
                action,
                clipboard_setter=self._set_clipboard,
                clipboard_getter=self._get_clipboard_text,
                input_provider=self._ask_for_action_input,
                selected_text=self._workspace_text() or self.captured_selection,
                input_text=self._workspace_text(),
                output_setter=self._set_workspace_text,
                window_layout_runner=self._run_window_layout,
                window_snapshot_runner=self._run_window_snapshot,
            )
            self.status_var.set(message)
        except ActionError as exc:
            self.status_var.set("Action failed")
            messagebox.showerror("Context Palette", str(exc))

    def _edit_selected(self) -> None:
        action = self._selected_action()
        if action is None:
            self.status_var.set("No action selected")
            return
        if action.type != "copy_text" or action.state != "Draft":
            messagebox.showinfo(
                "Context Palette",
                "Only draft copy-text actions can be edited right now.",
            )
            return

        DraftActionEditor(self.root, action, self._save_edited_action)

    def _mark_selected_trusted(self) -> None:
        action = self._selected_action()
        if action is None:
            self.status_var.set("No action selected")
            return
        if action.state != "Draft":
            messagebox.showinfo("Context Palette", "Only draft actions can be marked Trusted.")
            return

        if not messagebox.askyesno(
            "Mark Trusted",
            f"Mark this action as Trusted?\n\n{action.display_text}",
            parent=self.root,
        ):
            return

        try:
            updated = trusted_action(action)
            update_action(self._action_storage_path(action), updated)
            self._reload()
            self.status_var.set(f"Marked Trusted: {updated.title}")
        except ActionError as exc:
            messagebox.showerror("Context Palette", str(exc))

    def _execute_slot(self, slot: int, event: tk.Event) -> str | None:
        action = self.slot_actions.get(slot)
        if action is None:
            self.status_var.set(f"No action in slot {slot}")
            return "break"
        try:
            message = execute_action(
                action,
                clipboard_setter=self._set_clipboard,
                clipboard_getter=self._get_clipboard_text,
                input_provider=self._ask_for_action_input,
                selected_text=self._workspace_text() or self.captured_selection,
                input_text=self._workspace_text(),
                output_setter=self._set_workspace_text,
                window_layout_runner=self._run_window_layout,
                window_snapshot_runner=self._run_window_snapshot,
            )
            self.status_var.set(message)
        except ActionError as exc:
            self.status_var.set("Action failed")
            messagebox.showerror("Context Palette", str(exc))
        return "break"

    def _move_selection(self, offset: int, event: tk.Event) -> str:
        if not self.displayed_actions:
            return "break"

        selected = self.results.curselection()
        current = selected[0] if selected else 0
        return self._select_index(current + offset, event)

    def _select_index(self, index: int, _event: tk.Event) -> str:
        if not self.displayed_actions:
            return "break"

        bounded_index = max(0, min(index, len(self.displayed_actions) - 1))
        self.results.selection_clear(0, tk.END)
        self.results.selection_set(bounded_index)
        self.results.activate(bounded_index)
        self.results.see(bounded_index)
        self._update_preview()
        return "break"

    def _selected_action(self) -> Action | None:
        selected = self.results.curselection()
        if not selected:
            return None
        index = selected[0]
        if index >= len(self.displayed_actions):
            return None
        return self.displayed_actions[index]

    def _update_preview(self) -> None:
        action = self._selected_action()
        if action is None:
            self._hide_action_tooltip()
            return
        self._show_action_tooltip(action.display_text, self._preview_text(action))

    def _preview_text(self, action: Action) -> str:
        try:
            action = expanded_action(action, clipboard_getter=self._get_clipboard_text)
        except ActionError:
            pass
        if action.type == "copy_text":
            return action.value
        if action.type == "open_url":
            return f"Open URL:\n{action.value}"
        if action.type == "open_file":
            return f"Open file:\n{action.value}"
        if action.type == "open_folder":
            return f"Open folder:\n{action.value}"
        if action.type == "launch_app":
            lines = [f"Launch app:\n{action.value}"]
            if action.arguments:
                lines.append("Arguments:")
                lines.extend(action.arguments)
            if action.working_directory:
                lines.append(f"Working folder:\n{action.working_directory}")
            return "\n".join(lines)
        if action.type == "build_url_copy":
            return f"Ask for an ID, then copy this URL:\n{action.value}"
        if action.type == "build_url_open":
            return f"Ask for an ID, then open this URL:\n{action.value}"
        if action.type == "build_url_selection_open":
            selected = self._workspace_text() or self.captured_selection or "(no input available)"
            return f"Selected ID: {selected}\nCopy URL and open it:\n{action.value}"
        if action.type == "transform_list_csv":
            mode = "quoted SQL strings" if action.value == "sql_strings" else "comma-separated values"
            return f"Transform Input / Output lines into {mode}.\nThe result replaces the field and is copied."
        if action.type == "workspace_template":
            return "Load this template into Input / Output and copy it:\n" + action.value
        if action.type == "window_layout":
            try:
                return describe_window_layout(self._layout_path(action.value))
            except WindowLayoutError as exc:
                return f"Window layout unavailable:\n{exc}"
        if action.type == "restore_window_snapshot":
            try:
                return describe_window_snapshot(self._layout_path(action.value))
            except WindowLayoutError as exc:
                return f"Window snapshot unavailable:\n{exc}"
        return f"{action.type}:\n{action.value}"

    def _layout_path(self, value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.actions_path.parent.parent / path
        return path

    def _run_window_layout(self, value: str) -> str:
        try:
            return apply_window_layout(
                self._layout_path(value),
                base_directory=self.actions_path.parent.parent,
            )
        except WindowLayoutError as exc:
            raise ActionError(str(exc)) from exc

    def _run_window_snapshot(self, value: str) -> str:
        try:
            return restore_window_snapshot(self._layout_path(value))
        except WindowLayoutError as exc:
            raise ActionError(str(exc)) from exc

    def _capture_window_snapshot(self) -> None:
        name = simpledialog.askstring(
            "Capture Window Snapshot",
            "Name for the current window situation:",
            initialvalue=f"{self.palette_state.focus_context} workspace",
            parent=self.root,
        )
        if name is None:
            return
        try:
            project_root = self.actions_path.parent.parent
            path = capture_window_snapshot(
                project_root / "data" / "layouts" / "snapshots",
                name,
                exclude_handle=self.root.winfo_id(),
                foreground_handle=self.source_foreground_handle,
            )
            for window_index, title in browser_windows_without_launch_url(path):
                url = simpledialog.askstring(
                    "Browser Launch URL",
                    f"Optional URL to reopen this browser window:\n\n{title}",
                    parent=self.root,
                )
                if url:
                    set_snapshot_launch_target(path, window_index, url)
            relative_path = path.relative_to(project_root).as_posix()
            action = Action(
                id=f"snapshot-{path.stem}",
                title=f"Restore {name.strip()}",
                context=self.palette_state.focus_context,
                technology="Windows / Win32",
                task="Restore workspace",
                type="restore_window_snapshot",
                value=relative_path,
                state="Draft",
            )
            append_action(self.local_actions_path, action)
            self._reload()
            self.status_var.set(f"Captured snapshot with action: {action.title}")
        except (WindowLayoutError, ActionError, ValueError) as exc:
            messagebox.showerror("Context Palette", str(exc))

    def _show_action_tooltip(self, title: str, detail: str) -> None:
        self._hide_action_tooltip()
        selected = self.results.curselection()
        if not selected:
            return
        bbox = self.results.bbox(selected[0])
        y = (bbox[1] + bbox[3] + 2) if bbox is not None else 4
        tooltip = ttk.Label(
            self.results,
            text=f"{title}\n{detail}",
            justify=tk.LEFT,
            wraplength=max(260, self.results.winfo_width() - 80),
            padding=8,
            relief=tk.SOLID,
            borderwidth=1,
        )
        tooltip.place(x=38, y=y)
        tooltip.lift()
        self.preview_tooltip = tooltip
        self.preview_after_id = self.root.after(5000, self._hide_action_tooltip)

    def _hide_action_tooltip(self) -> None:
        if self.preview_after_id is not None:
            self.root.after_cancel(self.preview_after_id)
            self.preview_after_id = None
        if self.preview_tooltip is not None:
            self.preview_tooltip.destroy()
            self.preview_tooltip = None

    def _workspace_text(self) -> str:
        return self.workspace.get("1.0", "end-1c").strip()

    def _set_workspace_text(self, value: str) -> None:
        self.workspace.delete("1.0", tk.END)
        self.workspace.insert("1.0", value)

    def _paste_into_workspace(self) -> None:
        try:
            self._set_workspace_text(self.root.clipboard_get())
            self.status_var.set("Pasted clipboard text into Input / Output")
        except tk.TclError:
            messagebox.showerror("Context Palette", "The clipboard does not contain text.")

    def _set_clipboard(self, value: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update()

    def _get_clipboard_text(self) -> str:
        try:
            return self.root.clipboard_get()
        except tk.TclError as exc:
            raise ActionError("The clipboard does not contain text.") from exc

    def _ask_for_action_input(self, prompt: str) -> str | None:
        return simpledialog.askstring("Build URL", prompt, parent=self.root)

    def _save_edited_action(self, action: Action, title: str, context: str, value: str) -> None:
        try:
            updated = edited_copy_text_action(action, title=title, context=context, value=value)
            update_action(self._action_storage_path(action), updated)
            self._reload()
            self.status_var.set(f"Saved draft action: {updated.title}")
        except ActionError as exc:
            messagebox.showerror("Context Palette", str(exc))

    def _capture_clipboard(self) -> None:
        try:
            content = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showerror("Context Palette", "The clipboard does not contain text.")
            return

        title = simpledialog.askstring(
            "Capture Clipboard",
            "Title for this capture:",
            parent=self.root,
        )
        if title is None:
            self.status_var.set("Capture cancelled")
            return

        try:
            item = create_clipboard_item(title=title, content=content)
            append_inbox_item(self.inbox_path, item)
            self.status_var.set(f"Captured to Inbox: {item.title}")
        except InboxError as exc:
            self.status_var.set("Capture failed")
            messagebox.showerror("Context Palette", str(exc))

    def _show_inbox(self) -> None:
        try:
            items = load_inbox_items(self.inbox_path)
        except InboxError as exc:
            messagebox.showerror("Context Palette", str(exc))
            return

        InboxWindow(
            self.root,
            items,
            self.actions,
            self.palette_state.focus_context,
            self.local_actions_path,
            self.inbox_path,
            self._reload,
        )

    def _show_help(self) -> None:
        HelpWindow(self.root, self.actions_path.parent.parent / "docs" / "HELP.md")

    def _show_cheatsheets(self) -> None:
        try:
            sheets = load_cheatsheets(self.cheatsheets_dir)
        except CheatSheetError as exc:
            messagebox.showerror("Context Palette", str(exc))
            return

        CheatSheetWindow(self.root, sheets, self.local_actions_path, self._reload)

    def _handle_keypress(self, event: tk.Event) -> str | None:
        keysym = str(event.keysym)

        navigation = {
            "Up": -1,
            "Down": 1,
            "Prior": -5,
            "Next": 5,
        }
        if keysym in navigation:
            return self._move_selection(navigation[keysym], event)
        if keysym == "Home":
            return self._select_index(0, event)
        if keysym == "End":
            return self._select_index(len(self.displayed_actions) - 1, event)

        slot = self._slot_from_key(event)
        if slot is None:
            return None

        if self._plain_number_from_text_input(event):
            return None
        return self._execute_slot(slot, event)

    def _slot_from_key(self, event: tk.Event) -> int | None:
        keysym = str(event.keysym)
        keycode = int(getattr(event, "keycode", 0) or 0)
        if 97 <= keycode <= 105:
            return keycode - 96

        if keysym.isdigit():
            slot = int(keysym)
            return slot if 1 <= slot <= 9 else None
        if keysym.startswith("KP_"):
            keypad_names = {
                "KP_1": 1,
                "KP_2": 2,
                "KP_3": 3,
                "KP_4": 4,
                "KP_5": 5,
                "KP_6": 6,
                "KP_7": 7,
                "KP_8": 8,
                "KP_9": 9,
                "KP_End": 1,
                "KP_Down": 2,
                "KP_Next": 3,
                "KP_Left": 4,
                "KP_Begin": 5,
                "KP_Right": 6,
                "KP_Home": 7,
                "KP_Up": 8,
                "KP_Prior": 9,
            }
            return keypad_names.get(keysym)
        return None

    def _plain_number_from_text_input(self, event: tk.Event) -> bool:
        keycode = int(getattr(event, "keycode", 0) or 0)
        return (
            event.widget is not None
            and event.widget == self.root.focus_get()
            and isinstance(event.widget, ttk.Entry)
            and str(event.keysym).isdigit()
            and not 97 <= keycode <= 105
        )


class HelpWindow:
    def __init__(self, parent: tk.Tk, help_path: Path) -> None:
        self.window = tk.Toplevel(parent)
        self.window.title("Context Palette Help")
        self.window.geometry("760x680")
        self.window.minsize(520, 420)
        self.search_var = tk.StringVar()

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(header, text="Context Palette Help", style="Heading.TLabel").pack(side=tk.LEFT)
        search = ttk.Entry(header, textvariable=self.search_var, width=28)
        search.pack(side=tk.RIGHT, padx=(6, 0))
        search.bind("<Return>", lambda _event: self._find_next())
        ttk.Button(header, text="Find next", command=self._find_next).pack(side=tk.RIGHT)

        content_frame = ttk.Frame(outer)
        content_frame.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(content_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.content = tk.Text(
            content_frame,
            wrap=tk.WORD,
            font=("Segoe UI", 10),
            padx=10,
            pady=8,
            yscrollcommand=scrollbar.set,
        )
        self.content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.configure(command=self.content.yview)
        self.content.tag_configure("found", background="#fff2a8")

        try:
            text = help_path.read_text(encoding="utf-8")
        except OSError as exc:
            text = f"Help could not be loaded from:\n{help_path}\n\n{exc}"
        self.content.insert("1.0", text)
        self.content.configure(state=tk.DISABLED)

        footer = ttk.Frame(outer)
        footer.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(footer, text=str(help_path), style="Muted.TLabel").pack(side=tk.LEFT)
        ttk.Button(footer, text="Close", command=self.window.destroy).pack(side=tk.RIGHT)
        self.window.transient(parent)
        self.window.lift()
        search.focus_set()

    def _find_next(self) -> None:
        query = self.search_var.get().strip()
        if not query:
            return
        self.content.tag_remove("found", "1.0", tk.END)
        start = self.content.index(f"{self.content.index(tk.INSERT)} +1c")
        position = self.content.search(query, start, stopindex=tk.END, nocase=True)
        if not position:
            position = self.content.search(query, "1.0", stopindex=tk.END, nocase=True)
        if not position:
            return
        end = f"{position}+{len(query)}c"
        self.content.tag_add("found", position, end)
        self.content.see(position)
        self.content.mark_set(tk.INSERT, end)


class InboxWindow:
    def __init__(
        self,
        parent: tk.Tk,
        items: list[InboxItem],
        actions: list[Action],
        focus_context: str,
        actions_path: Path,
        inbox_path: Path,
        on_change: Callable[[], None],
    ) -> None:
        self.items = items
        self.actions = actions
        self.focus_context = focus_context
        self.actions_path = actions_path
        self.inbox_path = inbox_path
        self.on_change = on_change
        self.window = tk.Toplevel(parent)
        self.window.title("Context Palette Inbox")
        self.window.geometry("640x420")
        self.window.minsize(480, 320)

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text=f"Inbox items: {len(items)}").pack(anchor=tk.W)

        self.listbox = tk.Listbox(outer, activestyle="dotbox", height=8)
        self.listbox.pack(fill=tk.BOTH, expand=True, pady=(4, 8))
        self.listbox.bind("<<ListboxSelect>>", lambda _event: self._update_preview())

        ttk.Label(outer, text="Preview").pack(anchor=tk.W)
        self.preview = tk.Text(outer, height=8, wrap=tk.WORD)
        self.preview.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.preview.configure(state=tk.DISABLED)

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(controls, text="Convert to Draft Action", command=self._convert_selected).pack(
            side=tk.LEFT
        )
        ttk.Button(controls, text="Close", command=self.window.destroy).pack(side=tk.RIGHT)

        self._load_items()

    def _load_items(self) -> None:
        self.listbox.delete(0, tk.END)
        for item in self.items:
            self.listbox.insert(tk.END, f"{item.title} ({item.created_at})")
        if self.items:
            self.listbox.selection_set(0)
            self.listbox.activate(0)
        self._update_preview()

    def _update_preview(self) -> None:
        item = self._selected_item()
        if item is None:
            text = "No Inbox items yet."
        else:
            text = (
                f"Title: {item.title}\n"
                f"State: {item.state}\n"
                f"Source: {item.source}\n"
                f"Created: {item.created_at}\n"
                f"Suggested context: {item.suggested_context or '(none)'}\n\n"
                f"{item.content}"
            )

        self.preview.configure(state=tk.NORMAL)
        self.preview.delete("1.0", tk.END)
        self.preview.insert("1.0", text)
        self.preview.configure(state=tk.DISABLED)

    def _selected_item(self) -> InboxItem | None:
        selected = self.listbox.curselection()
        if not selected:
            return None
        index = selected[0]
        if index >= len(self.items):
            return None
        return self.items[index]

    def _convert_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            return

        DraftActionCreator(
            self.window,
            item,
            self.actions,
            item.suggested_context or self.focus_context,
            self._save_created_action,
        )

    def _save_created_action(self, item: InboxItem, action: Action) -> None:
        try:
            append_action(self.actions_path, action)
            update_inbox_item_state(self.inbox_path, item.id, "Draft")
            self.items = load_inbox_items(self.inbox_path)
            self._load_items()
            self.on_change()
        except (ActionError, InboxError) as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.window)


class DraftActionCreator:
    def __init__(
        self,
        parent: tk.Toplevel,
        item: InboxItem,
        actions: list[Action],
        initial_context: str,
        on_save: Callable[[InboxItem, Action], None],
    ) -> None:
        self.item = item
        self.on_save = on_save
        self.window = tk.Toplevel(parent)
        self.window.title("Create Draft Action")
        self.window.geometry("560x520")
        self.window.minsize(480, 440)

        technologies = sorted({action.technology for action in actions if action.technology}, key=str.casefold)
        tasks = sorted({action.task for action in actions if action.task}, key=str.casefold)
        contexts = sorted({action.context for action in actions if action.context}, key=str.casefold)

        self.technology_var = tk.StringVar()
        self.task_var = tk.StringVar()
        self.context_var = tk.StringVar(value=initial_context or "General")
        self.title_var = tk.StringVar(value=item.title)

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        self._field(outer, "Technology", self.technology_var, technologies)
        self._field(outer, "Task", self.task_var, tasks)
        self._field(outer, "Context", self.context_var, contexts)

        ttk.Label(outer, text="Action name").pack(anchor=tk.W, pady=(8, 0))
        title_entry = ttk.Entry(outer, textvariable=self.title_var)
        title_entry.pack(fill=tk.X, pady=(3, 0))

        ttk.Label(outer, text="Action type").pack(anchor=tk.W, pady=(8, 0))
        type_field = ttk.Entry(outer)
        type_field.insert(0, "Copy text")
        type_field.configure(state="readonly")
        type_field.pack(fill=tk.X, pady=(3, 0))

        ttk.Label(outer, text="Input / content").pack(anchor=tk.W, pady=(8, 0))
        self.content = tk.Text(outer, height=10, wrap=tk.WORD, undo=True)
        self.content.pack(fill=tk.BOTH, expand=True, pady=(3, 0))
        self.content.insert("1.0", item.content)

        self.path_var = tk.StringVar()
        ttk.Label(outer, textvariable=self.path_var).pack(anchor=tk.W, pady=(8, 0))
        for variable in (self.technology_var, self.task_var, self.context_var, self.title_var):
            variable.trace_add("write", lambda *_args: self._update_path())

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(controls, text="Create Draft", command=self._save).pack(side=tk.LEFT)
        ttk.Button(controls, text="Cancel", command=self.window.destroy).pack(side=tk.RIGHT)

        self._update_path()
        self.window.transient(parent)
        self.window.grab_set()
        title_entry.focus_set()
        title_entry.selection_range(0, tk.END)

    def _field(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        values: list[str],
    ) -> None:
        ttk.Label(parent, text=label).pack(anchor=tk.W, pady=(8, 0))
        ttk.Combobox(parent, textvariable=variable, values=values).pack(fill=tk.X, pady=(3, 0))

    def _update_path(self) -> None:
        parts = [
            value.strip()
            for value in (
                self.technology_var.get(),
                self.task_var.get(),
                self.context_var.get(),
                self.title_var.get(),
            )
            if value.strip()
        ]
        self.path_var.set("Displayed as: " + " > ".join(parts))

    def _save(self) -> None:
        try:
            action = draft_copy_text_action(
                title=self.title_var.get(),
                technology=self.technology_var.get(),
                task=self.task_var.get(),
                context=self.context_var.get(),
                value=self.content.get("1.0", "end-1c"),
            )
        except ActionError as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.window)
            return
        self.on_save(self.item, action)
        self.window.destroy()


class DraftActionEditor:
    def __init__(
        self,
        parent: tk.Tk,
        action: Action,
        on_save: Callable[[Action, str, str, str], None],
    ) -> None:
        self.action = action
        self.on_save = on_save
        self.window = tk.Toplevel(parent)
        self.window.title("Edit Draft Action")
        self.window.geometry("560x420")
        self.window.minsize(440, 320)

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="Title").pack(anchor=tk.W)
        self.title_var = tk.StringVar(value=action.title)
        ttk.Entry(outer, textvariable=self.title_var).pack(fill=tk.X, pady=(4, 8))

        ttk.Label(outer, text="Context").pack(anchor=tk.W)
        self.context_var = tk.StringVar(value=action.context)
        ttk.Entry(outer, textvariable=self.context_var).pack(fill=tk.X, pady=(4, 8))

        ttk.Label(outer, text="Text").pack(anchor=tk.W)
        self.text = tk.Text(outer, wrap=tk.WORD)
        self.text.pack(fill=tk.BOTH, expand=True, pady=(4, 8))
        self.text.insert("1.0", action.value)

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X)
        ttk.Button(controls, text="Save", command=self._save).pack(side=tk.LEFT)
        ttk.Button(controls, text="Cancel", command=self.window.destroy).pack(side=tk.RIGHT)

    def _save(self) -> None:
        self.on_save(
            self.action,
            self.title_var.get(),
            self.context_var.get(),
            self.text.get("1.0", tk.END),
        )
        self.window.destroy()


class CheatSheetWindow:
    def __init__(
        self,
        parent: tk.Tk,
        sheets: list[CheatSheet],
        actions_path: Path,
        on_change: Callable[[], None],
    ) -> None:
        self.sheets = sheets
        self.actions_path = actions_path
        self.on_change = on_change
        self.filtered_items: list[tuple[CheatSheet, str, CheatSheetItem]] = []
        self.selected_sheet_index = 0
        self.selected_item_index = 0
        self.search_entry: ttk.Entry | None = None
        self.status_var = tk.StringVar(value="")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_args: self._refresh_items())
        self.window = tk.Toplevel(parent)
        self.window.title("Context Palette Cheat Sheets")
        self.window.geometry("760x520")
        self.window.minsize(560, 360)

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text=f"Cheat sheets: {len(sheets)}").pack(anchor=tk.W)

        self.listbox = tk.Listbox(outer, activestyle="dotbox", height=6, exportselection=False)
        self.listbox.pack(fill=tk.X, pady=(4, 8))
        self.listbox.bind("<<ListboxSelect>>", lambda _event: self._select_sheet())

        ttk.Label(outer, text="Search selected sheet").pack(anchor=tk.W)
        search_row = ttk.Frame(outer)
        search_row.pack(fill=tk.X, pady=(4, 8))

        search = ttk.Entry(search_row, textvariable=self.search_var)
        self.search_entry = search
        search.pack(side=tk.LEFT, fill=tk.X, expand=True)
        search.bind("<Escape>", lambda _event: self.window.destroy())
        ttk.Button(search_row, text="Promote to Draft", command=self._promote_selected).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        self.items = tk.Listbox(outer, activestyle="dotbox", height=8, exportselection=False)
        self.items.pack(fill=tk.BOTH, expand=True)
        self.items.bind("<<ListboxSelect>>", lambda _event: self._select_item())

        self.preview = tk.Text(outer, wrap=tk.WORD)
        self.preview.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.preview.configure(state=tk.DISABLED)

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(controls, textvariable=self.status_var).pack(side=tk.LEFT)
        ttk.Button(controls, text="Close", command=self.window.destroy).pack(side=tk.RIGHT)

        self._load_sheets()
        self.window.transient(parent)
        self.window.lift()
        self.window.after(80, self.focus_search)

    def _load_sheets(self) -> None:
        for sheet in self.sheets:
            self.listbox.insert(tk.END, sheet.title)
        if self.sheets:
            self.listbox.selection_set(0)
            self.listbox.activate(0)
        self._refresh_items()

    def _refresh_items(self) -> None:
        sheet = self._selected_sheet()
        self.filtered_items = []
        self.selected_item_index = 0
        self.items.delete(0, tk.END)

        if sheet is None:
            self._update_preview()
            return

        filtered_sheet = filter_cheatsheet(sheet, self.search_var.get())
        for section in filtered_sheet.sections:
            for item in section.items:
                self.filtered_items.append((sheet, section.title, item))
                self.items.insert(tk.END, f"{section.title} > {item.label}: {item.detail}")

        if self.filtered_items:
            self.items.selection_set(0)
            self.items.activate(0)
            self.status_var.set(f"{len(self.filtered_items)} matching items")
        else:
            self.status_var.set("No matching items")
        self._update_preview()

    def _select_sheet(self) -> None:
        selected = self.listbox.curselection()
        if selected:
            self.selected_sheet_index = selected[0]
        self._refresh_items()

    def _select_item(self) -> None:
        selected = self.items.curselection()
        if selected:
            self.selected_item_index = selected[0]
        self._update_preview()

    def _update_preview(self) -> None:
        selected = self._selected_item()
        if selected is None:
            sheet = self._selected_sheet()
            if sheet is None:
                text = "No cheat sheets available."
            elif self.search_var.get().strip():
                text = f"No matching items for: {self.search_var.get().strip()}"
            else:
                text = "Select a cheat-sheet item."
        else:
            sheet, section_title, item = selected
            text = (
                f"Sheet: {sheet.title}\n"
                f"Section: {section_title}\n"
                f"Item: {item.label}\n\n"
                f"{item.detail}\n\n"
                f"Tags: {', '.join(item.tags) if item.tags else '(none)'}"
            )

        self.preview.configure(state=tk.NORMAL)
        self.preview.delete("1.0", tk.END)
        self.preview.insert("1.0", text)
        self.preview.configure(state=tk.DISABLED)

    def _selected_sheet(self) -> CheatSheet | None:
        if not self.sheets:
            return None
        if self.selected_sheet_index >= len(self.sheets):
            self.selected_sheet_index = 0
        if self.selected_sheet_index < 0:
            return None
        return self.sheets[self.selected_sheet_index]

    def _selected_item(self):
        if not self.filtered_items:
            return None
        if self.selected_item_index >= len(self.filtered_items):
            self.selected_item_index = 0
        if self.selected_item_index < 0:
            return None
        return self.filtered_items[self.selected_item_index]

    def _promote_selected(self) -> None:
        selected = self._selected_item()
        if selected is None:
            self.status_var.set("Select a cheat-sheet item first")
            return

        sheet, _section_title, item = selected
        try:
            action = draft_action_from_cheatsheet_item(sheet, item)
            append_action(self.actions_path, action)
            self.on_change()
            self.status_var.set(f"Promoted: {item.label}")
            messagebox.showinfo(
                "Context Palette",
                f"Created draft action:\n\n{sheet.title} > {item.label}",
                parent=self.window,
            )
        except ActionError as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.window)

    def focus_search(self) -> None:
        if self.search_entry is not None:
            self.search_entry.focus_force()
            self.search_entry.selection_range(0, tk.END)


def run(
    actions_path: Path,
    local_actions_path: Path,
    palette_path: Path,
    inbox_path: Path,
    cheatsheets_dir: Path,
    instance_port: int,
) -> None:
    root = tk.Tk()
    LauncherApp(
        root,
        actions_path,
        local_actions_path,
        palette_path,
        inbox_path,
        cheatsheets_dir,
        instance_port,
    )
    root.mainloop()
