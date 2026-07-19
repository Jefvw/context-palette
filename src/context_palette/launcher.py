from __future__ import annotations

from pathlib import Path
import ctypes
import logging
import queue
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Callable

from .actions import (
    Action,
    ActionError,
    append_action,
    append_actions,
    build_url,
    draft_build_url_action,
    draft_copy_text_action,
    edited_copy_text_action,
    execute_action,
    expanded_action,
    load_combined_actions,
    load_actions,
    search_actions,
    transform_text,
    trusted_action,
    update_action,
)
from .ai_guidance_window import AIGuidanceWindow
from .cheatsheets import (
    CheatSheet,
    CheatSheetError,
    CheatSheetItem,
    draft_action_from_cheatsheet_item,
    filter_cheatsheet,
    load_cheatsheets,
)
from .command_surface import (
    CommandGroup,
    CommandItem,
    CommandSurfaceError,
    command_configuration_paths,
    command_item_action_ids,
    load_combined_command_groups,
)
from .configuration_window import ConfigurationWindow
from .hotkeys import (
    GlobalHotkey,
    cursor_location,
    focus_window,
    send_copy_shortcut,
    send_paste_shortcut,
    window_position_near_cursor,
    window_title,
)
from .help_window import HelpWindow
from .contexts import ContextDefinition, ContextError, load_combined_contexts
from .inbox import InboxError, InboxItem, append_inbox_item, create_clipboard_item, load_inbox_items
from .inbox import update_inbox_item_state
from .single_instance import SingleInstanceServer
from .style import COLORS, configure_theme
from .tooltips import ListboxItemTooltip, WidgetTooltip
from .palette_state import (
    PaletteState,
    action_slots,
    load_palette_state,
    save_palette_state,
    toggle_pin,
)
from .windows_credentials import (
    CredentialAccessError,
    clear_clipboard_if_unchanged,
    read_windows_credential,
    set_protected_clipboard_text,
)

LOGGER = logging.getLogger("context_palette.launcher")
LOGGER.addHandler(logging.NullHandler())

SLOW_RESULT_REFRESH_SECONDS = 0.100
SLOW_CONFIGURATION_RELOAD_SECONDS = 0.500


def frequent_credential_actions(
    actions: list[Action],
    pinned_action_ids: tuple[str, ...],
    *,
    limit: int = 4,
) -> list[Action]:
    """Return direct-paste credentials, prioritizing the user's global pin order."""
    eligible = {
        action.id: action
        for action in actions
        if action.type == "paste_credential" and action.state == "Trusted"
    }
    selected = [
        eligible[action_id]
        for action_id in pinned_action_ids
        if action_id in eligible
    ]
    selected_ids = {action.id for action in selected}
    selected.extend(
        action
        for action in actions
        if action.id in eligible and action.id not in selected_ids
    )
    return selected[:limit]


def _warn_if_slow(
    operation: str,
    started_at: float,
    threshold_seconds: float,
    *,
    action_count: int,
) -> None:
    elapsed_seconds = time.perf_counter() - started_at
    if elapsed_seconds >= threshold_seconds:
        LOGGER.warning(
            "Slow %s: elapsed_ms=%.1f action_count=%d",
            operation,
            elapsed_seconds * 1000,
            action_count,
        )


def suggest_url_template(value: str) -> str:
    current = value.strip()
    if not current or "{id}" in current or "{id_url}" in current:
        return current
    if current.startswith(("http://", "https://")):
        separator = "" if current.endswith("/") else "/"
        return current + separator + "{id_url}"
    return current


class PrefixSuffixDialog(simpledialog.Dialog):
    def body(self, master: tk.Misc) -> tk.Widget:
        ttk.Label(master, text="Prefix for every line").grid(row=0, column=0, sticky=tk.W)
        self.prefix_var = tk.StringVar()
        prefix_entry = ttk.Entry(master, textvariable=self.prefix_var, width=42)
        prefix_entry.grid(row=1, column=0, sticky=tk.EW, pady=(3, 9))
        ttk.Label(master, text="Suffix for every line").grid(row=2, column=0, sticky=tk.W)
        self.suffix_var = tk.StringVar()
        ttk.Entry(master, textvariable=self.suffix_var, width=42).grid(
            row=3, column=0, sticky=tk.EW, pady=(3, 0)
        )
        master.columnconfigure(0, weight=1)
        return prefix_entry

    def apply(self) -> None:
        self.result = (self.prefix_var.get(), self.suffix_var.get())


class LauncherApp:
    def __init__(
        self,
        root: tk.Tk,
        actions_path: Path,
        local_actions_path: Path,
        contexts_path: Path,
        local_contexts_path: Path,
        command_surface_path: Path,
        local_command_surface_path: Path,
        palette_path: Path,
        inbox_path: Path,
        cheatsheets_dir: Path,
        instance_port: int,
        initial_request: dict[str, str] | None = None,
    ) -> None:
        self.root = root
        self.actions_path = actions_path
        self.local_actions_path = local_actions_path
        self.local_action_ids: set[str] = set()
        self.contexts_path = contexts_path
        self.local_contexts_path = local_contexts_path
        self.context_definitions: list[ContextDefinition] = []
        self.command_surface_path = command_surface_path
        self.local_command_surface_path = local_command_surface_path
        self.command_groups: list[CommandGroup] = []
        self.palette_path = palette_path
        self.inbox_path = inbox_path
        self.cheatsheets_dir = cheatsheets_dir
        self.actions: list[Action] = []
        self.filtered_actions: list[Action] = []
        self.displayed_actions: list[Action] = []
        self.displayed_slots: list[int | None] = []
        self.slot_actions: dict[int, Action] = {}
        self.palette_state = PaletteState()
        self.show_requests: queue.Queue[dict[str, str]] = queue.Queue()
        self.instance_server = SingleInstanceServer(self.show_requests.put, instance_port)
        self.hotkey = GlobalHotkey(self._queue_hotkey_request)
        self.captured_selection: str | None = None
        self.source_foreground_handle: int | None = None
        self.protected_clipboard_sequence: int | None = None
        self.hotkey_available = False
        self.hide_after_id: str | None = None
        self.search_entry: ttk.Entry | None = None
        self.search_refresh_after_id: str | None = None
        self.action_type_filter: str | None = None
        self.passwords_button: ttk.Button | None = None
        self.configuration_signature_cache: tuple[tuple[str, int, int], ...] = ()
        self.search_var = tk.StringVar()
        self.context_var = tk.StringVar(value="General")
        self.results_count_var = tk.StringVar(value="0 actions")
        self.surface_count_var = tk.StringVar(value="0 buttons")
        self.widget_tooltips: list[WidgetTooltip] = []
        self.command_surface_tooltips: list[WidgetTooltip] = []
        self.action_info_full = "Select an action to see what it reads and what it will do."
        self.status_var = tk.StringVar(value="Ready")
        self.search_var.trace_add("write", lambda *_args: self._schedule_refresh_results())

        self._build_ui()
        self._load_actions()
        self._load_command_surface()
        self._load_contexts()
        self._load_palette_state()
        self._refresh_results()
        self.configuration_signature_cache = self._configuration_signature()
        if not self.instance_server.start():
            self.root.after(0, self.root.destroy)
            return
        self.hotkey_available = self.hotkey.start()
        if self.hotkey_available:
            shortcuts = " or ".join(reversed(self.hotkey.available_shortcuts))
            self.status_var.set(f"Ready. {shortcuts} shows Context Palette.")
        else:
            self.status_var.set("F9 and Ctrl+Alt+P are unavailable. Auto-hide is disabled.")
            LOGGER.warning("Global hotkeys unavailable; automatic hiding is disabled")
        if initial_request:
            self.show_requests.put(initial_request)
        self._poll_show_requests()
        self._audit_tooltips()

    def _build_ui(self) -> None:
        self.root.title("Context Palette")
        self.root.geometry("780x600")
        self.root.minsize(700, 480)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        self.root.bind("<FocusOut>", self._schedule_hide_when_inactive)
        self.root.bind("<FocusIn>", self._cancel_scheduled_hide)

        configure_theme(self.root)

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        self._build_header(outer)
        self._build_results_area(outer)
        self._bind_main_shortcuts()
        self._build_workspace(outer)
        self._build_footer(outer)

    def _build_header(self, outer: ttk.Frame) -> None:

        context_panel = ttk.Frame(outer)
        context_panel.pack(fill=tk.X, pady=(0, 8))
        focus_label = ttk.Label(context_panel, text="Focus", style="Heading.TLabel")
        focus_label.pack(side=tk.LEFT)
        self._tooltip(focus_label, "Choose what you are working on. This changes context slots 6–9.")
        self.context_picker = ttk.Combobox(
            context_panel,
            textvariable=self.context_var,
            state="readonly",
            width=36,
            font=("Segoe UI", 10),
        )
        self.context_picker.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 6))
        self.context_picker.bind("<<ComboboxSelected>>", lambda _event: self._change_focus_context())
        context_help = ttk.Button(context_panel, text="?", width=3, command=self._show_help)
        context_help.pack(side=tk.RIGHT)
        configure_button = ttk.Button(
            context_panel,
            text="Configure…",
            command=self._show_configuration,
            style="Compact.TButton",
        )
        configure_button.pack(side=tk.RIGHT, padx=(0, 6))
        self._tooltip(
            configure_button,
            "Create personal actions from built-in types and configure contexts and right-side buttons.",
        )
        self._tooltip(
            context_help,
            "Focus changes slots 6–9. It does not limit global search. Open Help for context configuration.",
        )

        search_row = ttk.Frame(outer)
        search_row.pack(fill=tk.X, pady=(0, 8))
        find_label = ttk.Label(search_row, text="Find action", style="Heading.TLabel")
        find_label.pack(side=tk.LEFT)
        self._tooltip(find_label, "Type any technology, task, context, action name, type, or content.")

        search = ttk.Entry(search_row, textvariable=self.search_var, font=("Segoe UI", 11))
        self.search_entry = search
        search.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 6))
        search.focus_set()
        search.bind("<KeyPress>", self._handle_keypress)
        search.bind("<Return>", lambda _event: self._execute_selected())

        self.passwords_button = ttk.Button(
            search_row,
            text="Passwords",
            command=self._toggle_password_actions,
            style="Compact.TButton",
        )
        self.passwords_button.pack(side=tk.LEFT, padx=(0, 6))
        self._tooltip(
            self.passwords_button,
            "Show only protected Windows Credential Manager actions. Activate again to show all actions.",
        )

        run_button = ttk.Button(
            search_row,
            text="Run",
            command=self._execute_selected,
            style="Accent.TButton",
        )
        run_button.pack(side=tk.LEFT, padx=(8, 0))
        self._tooltip(run_button, "Execute the highlighted action. Its input and effect appear in Action info below.")
        search_help = ttk.Button(
            search_row,
            text="?",
            width=3,
            command=self._show_help,
            style="Compact.TButton",
        )
        search_help.pack(side=tk.LEFT, padx=(6, 0))
        self._tooltip(
            search_help,
            "Search globally across technology, task, context, action name, type, and content.",
        )

    def _toggle_password_actions(self) -> None:
        self.action_type_filter = (
            None if self.action_type_filter == "paste_credential" else "paste_credential"
        )
        if self.passwords_button is not None:
            self.passwords_button.configure(
                style=(
                    "Accent.TButton"
                    if self.action_type_filter == "paste_credential"
                    else "Compact.TButton"
                )
            )
        self._refresh_results()

    def _build_results_area(self, outer: ttk.Frame) -> None:

        results_area = ttk.Panedwindow(outer, orient=tk.HORIZONTAL)
        results_area.pack(fill=tk.BOTH, expand=True)
        results_frame = ttk.Frame(results_area)
        results_area.add(results_frame, weight=1)
        results_header = ttk.Frame(results_frame)
        results_header.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(results_header, text="Actions", style="PaneHeader.TLabel").pack(side=tk.LEFT)
        ttk.Label(
            results_header,
            textvariable=self.results_count_var,
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)
        results_body = ttk.Frame(results_frame)
        results_body.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(results_body, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.results = tk.Listbox(
            results_body,
            activestyle="dotbox",
            font=("Segoe UI", 10),
            selectmode=tk.BROWSE,
            yscrollcommand=scrollbar.set,
            borderwidth=1,
            relief=tk.SOLID,
            highlightthickness=1,
            highlightcolor=COLORS["focus"],
            highlightbackground=COLORS["border"],
        )
        self.results.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.configure(command=self.results.yview)
        self.results.bind("<KeyPress>", self._handle_keypress)
        self.results.bind("<<ListboxSelect>>", lambda _event: self._update_preview())
        self.results.bind("<Double-Button-1>", lambda _event: self._execute_selected())
        self.results.bind("<Return>", lambda _event: self._execute_selected())
        self.results_tooltip = ListboxItemTooltip(self.results, self._result_tooltip_text)

        self.command_surface_panel = ttk.Frame(results_area, padding=(8, 0, 0, 0))
        results_area.add(self.command_surface_panel, weight=1)
        surface_header = ttk.Frame(self.command_surface_panel)
        surface_header.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(surface_header, text="Quick actions", style="PaneHeader.TLabel").pack(
            side=tk.LEFT
        )
        ttk.Label(
            surface_header,
            textvariable=self.surface_count_var,
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)
        surface_body = ttk.Frame(self.command_surface_panel)
        surface_body.pack(fill=tk.BOTH, expand=True)
        surface_scrollbar = ttk.Scrollbar(surface_body, orient=tk.VERTICAL)
        surface_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.command_surface_canvas = tk.Canvas(
            surface_body,
            highlightthickness=0,
            borderwidth=0,
            yscrollcommand=surface_scrollbar.set,
        )
        self.command_surface_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        surface_scrollbar.configure(command=self.command_surface_canvas.yview)
        self.command_tiles_frame = ttk.Frame(self.command_surface_canvas)
        self.command_tiles_window = self.command_surface_canvas.create_window(
            (0, 0), window=self.command_tiles_frame, anchor=tk.NW
        )
        self.command_tiles_frame.bind(
            "<Configure>",
            lambda _event: self.command_surface_canvas.configure(
                scrollregion=self.command_surface_canvas.bbox("all")
            ),
        )
        self.command_surface_canvas.bind(
            "<Configure>",
            lambda event: self.command_surface_canvas.itemconfigure(
                self.command_tiles_window, width=event.width
            ),
        )

    def _bind_main_shortcuts(self) -> None:

        self.root.bind("<KeyPress>", self._handle_keypress)
        self.root.bind("<Escape>", lambda _event: self.hide_window())
        self.root.bind("<Control-l>", lambda _event: self.focus_search())
        self.root.bind("<Control-k>", lambda _event: self.focus_search())
        self.root.bind("<Control-i>", lambda _event: self._capture_clipboard())
        self.root.bind("<Control-comma>", lambda _event: self._show_configuration())
        self.root.bind("<F1>", lambda _event: self._show_help())

    def _build_workspace(self, outer: ttk.Frame) -> None:

        self.workspace_panel = ttk.Frame(outer)
        workspace_header = ttk.Frame(self.workspace_panel)
        workspace_header.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(
            workspace_header,
            text="Input / Output",
            style="PaneHeader.TLabel",
        ).pack(side=tk.LEFT)
        ttk.Label(
            workspace_header,
            text="Selection, clipboard, and transformation workspace",
            style="Muted.TLabel",
        ).pack(side=tk.LEFT, padx=(8, 0))
        workspace_body = ttk.Frame(self.workspace_panel)
        workspace_body.pack(fill=tk.X)
        self.workspace = tk.Text(
            workspace_body,
            height=4,
            wrap=tk.WORD,
            undo=True,
            font=("Consolas", 10),
            borderwidth=1,
            relief=tk.SOLID,
            padx=7,
            pady=6,
        )
        self.workspace.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.workspace.bind("<Control-a>", self._select_all_workspace)
        self.workspace.bind("<Control-A>", self._select_all_workspace)
        self.workspace.bind("<Button-3>", self._show_workspace_menu)
        self.workspace_menu = tk.Menu(self.workspace, tearoff=False)
        self.workspace_menu.add_command(label="Undo", command=lambda: self.workspace.event_generate("<<Undo>>"))
        self.workspace_menu.add_command(label="Redo", command=lambda: self.workspace.event_generate("<<Redo>>"))
        self.workspace_menu.add_separator()
        self.workspace_menu.add_command(label="Cut", command=lambda: self.workspace.event_generate("<<Cut>>"))
        self.workspace_menu.add_command(label="Copy", command=lambda: self.workspace.event_generate("<<Copy>>"))
        self.workspace_menu.add_command(label="Paste", command=lambda: self.workspace.event_generate("<<Paste>>"))
        self.workspace_menu.add_command(label="Select all", command=self._select_all_workspace)
        self.workspace_menu.add_separator()
        self.workspace_menu.add_command(label="Copy all", command=self._copy_workspace_to_clipboard)
        self.workspace_menu.add_command(label="Replace with clipboard", command=self._paste_into_workspace)
        self.workspace_menu.add_command(label="Clear", command=lambda: self._set_workspace_text(""))
        self.workspace_transform_menu = tk.Menu(self.workspace_menu, tearoff=False)
        self.workspace_transform_menu.add_command(
            label="lowercase", command=lambda: self._transform_workspace("lowercase", "lowercase")
        )
        self.workspace_transform_menu.add_command(
            label="UPPERCASE", command=lambda: self._transform_workspace("uppercase", "UPPERCASE")
        )
        self.workspace_transform_menu.add_command(
            label="Normalize consecutive spaces",
            command=lambda: self._transform_workspace("normalize_spaces", "Normalized spaces"),
        )
        self.workspace_transform_menu.add_command(
            label="Prefix / suffix every line…", command=self._prefix_suffix_workspace
        )
        self.workspace_transform_menu.add_command(
            label="Remove duplicate lines",
            command=lambda: self._transform_workspace("remove_duplicate_lines", "Removed duplicate lines"),
        )
        self.workspace_menu.add_cascade(label="Transform", menu=self.workspace_transform_menu)
        self.workspace_transform_button = ttk.Button(
            workspace_body,
            text="⋮",
            width=3,
            command=self._show_workspace_transform_button_menu,
            style="Compact.TButton",
        )
        self.workspace_transform_button.pack(side=tk.RIGHT, anchor=tk.N, padx=(5, 0))
        self._tooltip(
            self.workspace_transform_button,
            "Transform selected text, or the complete field when nothing is selected. Results are copied.",
        )

    def _build_footer(self, outer: ttk.Frame) -> None:

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=(8, 0))
        for column in range(5):
            controls.columnconfigure(column, weight=1, uniform="controls")

        capture_button = ttk.Button(controls, text="Capture", command=self._capture_clipboard)
        capture_button.grid(row=0, column=0, sticky=tk.EW, padx=(0, 3), pady=(0, 3))
        self._tooltip(capture_button, "Save current clipboard text to Inbox after asking for a title.")
        inbox_button = ttk.Button(controls, text="Inbox", command=self._show_inbox)
        inbox_button.grid(row=0, column=1, sticky=tk.EW, padx=3, pady=(0, 3))
        self._tooltip(inbox_button, "Review captures and convert them into structured Draft actions.")
        sheets_button = ttk.Button(controls, text="Sheets", command=self._show_cheatsheets)
        sheets_button.grid(row=0, column=2, sticky=tk.EW, padx=3, pady=(0, 3))
        self._tooltip(sheets_button, "Open searchable local cheat sheets and promote useful entries to Draft actions.")
        edit_button = ttk.Button(controls, text="Edit", command=self._edit_selected)
        edit_button.grid(row=0, column=3, sticky=tk.EW, padx=3, pady=(0, 3))
        self._tooltip(edit_button, "Edit the selected Draft copy-text action. Other action types are currently read-only.")
        pin_button = ttk.Button(controls, text="Pin", command=self._toggle_selected_pin)
        pin_button.grid(row=1, column=0, sticky=tk.EW, padx=(0, 3))
        self._tooltip(pin_button, "Pin or unpin the selected action in stable slots 1–5.")
        trust_button = ttk.Button(controls, text="Trust", command=self._mark_selected_trusted)
        trust_button.grid(row=1, column=1, sticky=tk.EW, padx=3)
        self._tooltip(trust_button, "Mark the selected reviewed Draft action as Trusted after confirmation.")
        help_button = ttk.Button(controls, text="Help", command=self._show_help)
        help_button.grid(row=1, column=2, sticky=tk.EW, padx=3)
        self._tooltip(help_button, "Open the complete local Context Palette help document.")
        hide_button = ttk.Button(controls, text="Hide", command=self.hide_window)
        hide_button.grid(row=1, column=3, sticky=tk.EW, padx=3)
        self._tooltip(hide_button, "Hide the palette but keep it resident. Reopen with Ctrl+Alt+P.")
        quit_button = ttk.Button(controls, text="Quit", command=self.quit_app)
        quit_button.grid(row=1, column=4, sticky=tk.EW, padx=(3, 0))
        self._tooltip(quit_button, "Stop Context Palette completely and release Ctrl+Alt+P.")

        for child in controls.winfo_children():
            try:
                child.configure(style="Compact.TButton")
            except tk.TclError:
                pass

        self.workspace_panel.pack(fill=tk.X, pady=(8, 0))

        status_label = ttk.Label(
            outer,
            textvariable=self.status_var,
            style="Status.TLabel",
            anchor=tk.W,
        )
        status_label.pack(fill=tk.X, pady=(4, 0), anchor=tk.W)
        self._tooltip(status_label, self._status_tooltip_text)
        status_label.bind("<Button-1>", lambda _event: self._show_action_info_dialog())

    def _tooltip(self, widget: tk.Widget, text: str | Callable[[], str]) -> None:
        self.widget_tooltips.append(WidgetTooltip(widget, text))

    def _command_surface_tooltip(
        self,
        widget: tk.Widget,
        text: str | Callable[[], str],
    ) -> None:
        self.command_surface_tooltips.append(WidgetTooltip(widget, text))

    def _result_tooltip_text(self, index: int) -> str:
        if index < 0 or index >= len(self.displayed_actions):
            return ""
        action = self.displayed_actions[index]
        lines = [f"Context: {action.context or 'General'}"]
        if action.technology:
            lines.append(f"Technology: {action.technology}")
        if action.task:
            lines.append(f"Task: {action.task}")
        lines.append(f"Action: {action.title}")
        return "\n".join(lines)

    def _select_all_workspace(self, _event=None) -> str:
        self.workspace.tag_add(tk.SEL, "1.0", "end-1c")
        self.workspace.mark_set(tk.INSERT, "1.0")
        self.workspace.see(tk.INSERT)
        return "break"

    def _show_workspace_menu(self, event: tk.Event) -> str:
        self.workspace.focus_set()
        try:
            self.workspace_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.workspace_menu.grab_release()
        return "break"

    def _show_workspace_transform_button_menu(self) -> None:
        self.workspace.focus_set()
        try:
            self.workspace_transform_menu.tk_popup(
                self.workspace_transform_button.winfo_rootx(),
                self.workspace_transform_button.winfo_rooty()
                + self.workspace_transform_button.winfo_height(),
            )
        finally:
            self.workspace_transform_menu.grab_release()

    def _workspace_transform_range(self) -> tuple[str, str, bool]:
        try:
            return self.workspace.index(tk.SEL_FIRST), self.workspace.index(tk.SEL_LAST), True
        except tk.TclError:
            return "1.0", "end-1c", False

    def _transform_workspace(
        self,
        operation: str,
        description: str,
        *,
        prefix: str = "",
        suffix: str = "",
    ) -> None:
        start, end, had_selection = self._workspace_transform_range()
        source = self.workspace.get(start, end)
        if not source:
            self.status_var.set("Input / Output is empty; nothing was transformed.")
            return
        try:
            result = transform_text(source, operation, prefix=prefix, suffix=suffix)
        except ActionError as exc:
            messagebox.showerror("Context Palette", str(exc))
            return
        self.workspace.edit_separator()
        self.workspace.replace(start, end, result)
        self.workspace.edit_separator()
        result_end = self.workspace.index(f"{start}+{len(result)}c")
        self.workspace.mark_set(tk.INSERT, result_end)
        if had_selection:
            self.workspace.tag_add(tk.SEL, start, result_end)
        self._set_clipboard(result)
        scope = "selection" if had_selection else "complete field"
        self.status_var.set(f"{description} in {scope}; result copied to clipboard.")

    def _prefix_suffix_workspace(self) -> None:
        dialog = PrefixSuffixDialog(self.root, title="Prefix / suffix every line")
        if dialog.result is None:
            return
        prefix, suffix = dialog.result
        self._transform_workspace(
            "prefix_suffix_lines",
            "Added line prefix / suffix",
            prefix=prefix,
            suffix=suffix,
        )

    def _status_tooltip_text(self) -> str:
        current = self.status_var.get().strip()
        if self.action_info_full and self.action_info_full != current:
            return f"{self.action_info_full}\n\nCurrent message: {current}"
        return current or "No current message."

    def _show_action_info_dialog(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Context Palette information")
        window.geometry("620x300")
        window.minsize(440, 220)
        outer = ttk.Frame(window, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)
        text = tk.Text(outer, wrap=tk.WORD, font=("Segoe UI", 10), padx=8, pady=8)
        text.pack(fill=tk.BOTH, expand=True)
        text.insert("1.0", self._status_tooltip_text())
        text.configure(state=tk.DISABLED)
        close_button = ttk.Button(outer, text="Close", command=window.destroy)
        close_button.pack(anchor=tk.E, pady=(8, 0))
        window.transient(self.root)
        window.lift()

    def _audit_tooltips(self) -> None:
        descriptions = {
            "1–5  PINNED": "Global shortcuts that stay in slots 1–5 in every context.",
            "6–9  FOCUS CONTEXT": "The four preferred actions for the current Focus context.",
            "Selection, pasted input, and transformation results": (
                "This editable text is read by input-aware actions and may contain clipboard or action output."
            ),
        }

        def visit(widget: tk.Widget) -> None:
            if getattr(widget, "_context_palette_tooltip_window", False):
                return
            if isinstance(widget, (ttk.Label, ttk.LabelFrame, ttk.Button, tk.Label, tk.Button)) and not getattr(
                widget, "_context_palette_has_tooltip", False
            ):
                try:
                    text = str(widget.cget("text")).strip()
                except tk.TclError:
                    text = ""
                if text:
                    explanation = descriptions.get(text, f"{text}: hover guidance for this control.")
                else:
                    explanation = "Shows contextual information for this field."
                self._tooltip(widget, explanation)
            for child in widget.winfo_children():
                visit(child)

        visit(self.root)

    def _queue_hotkey_request(self) -> None:
        request = {"command": "hotkey"}
        try:
            x, y, left, top, right, bottom = cursor_location()
            request.update(
                {
                    "cursor_x": str(x),
                    "cursor_y": str(y),
                    "work_left": str(left),
                    "work_top": str(top),
                    "work_right": str(right),
                    "work_bottom": str(bottom),
                }
            )
        except OSError:
            pass
        self.show_requests.put(request)

    def show_window(self) -> None:
        self._cancel_scheduled_hide()
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(100, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()
        self.search_var.set("")
        self._reload_if_changed()
        self._sync_workspace_from_clipboard_if_safe()
        self.root.after(80, self.focus_search)

    def hide_window(self) -> None:
        self._cancel_scheduled_hide()
        if not self.hotkey_available:
            self.status_var.set("Cannot hide because no global shortcut is available.")
            return
        self.status_var.set("Hidden. Use F9 or Ctrl+Alt+P to show Context Palette.")
        self.root.withdraw()

    def quit_app(self) -> None:
        self._clear_protected_clipboard()
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
            if request.get("command") == "hotkey":
                # Wait for Ctrl+Alt+P to be released, copy while the source app
                # still has focus, then show the palette.
                self.root.after(100, lambda value=request: self._capture_selection(value))
            else:
                self._handle_external_request(request)
        self.root.after(100, self._poll_show_requests)

    def _handle_external_request(self, request: dict[str, str]) -> None:
        self.source_foreground_handle = None
        self.show_window()
        requested_context = request.get("context", "").strip()
        if requested_context:
            contexts = {value.casefold(): value for value in self.context_picker.cget("values")}
            matched_context = contexts.get(requested_context.casefold())
            if matched_context:
                self.context_var.set(matched_context)
                self._change_focus_context()
            else:
                self.status_var.set(f"Unknown integration context: {requested_context}")
        search = request.get("search", "").strip()
        if search:
            self.search_var.set(search)
            self.root.after(80, self.focus_search)

    def _capture_selection(self, request: dict[str, str]) -> None:
        self._clear_protected_clipboard()
        self.source_foreground_handle = int(ctypes.windll.user32.GetForegroundWindow())
        send_copy_shortcut()
        self.root.after(120, lambda: self._finish_selection_capture(request))

    def _finish_selection_capture(self, request: dict[str, str]) -> None:
        try:
            value = self.root.clipboard_get()
            self.captured_selection = value.strip() or None
        except tk.TclError:
            self.captured_selection = None
        self.show_window()
        self._position_for_hotkey(request)
        if self.captured_selection is not None:
            self._set_workspace_text(self.captured_selection)

    def _position_for_hotkey(self, request: dict[str, str]) -> None:
        keys = ("cursor_x", "cursor_y", "work_left", "work_top", "work_right", "work_bottom")
        if not all(key in request for key in keys):
            return
        try:
            values = [int(request[key]) for key in keys]
        except ValueError:
            return
        self.root.update_idletasks()
        width = max(self.root.winfo_width(), self.root.winfo_reqwidth())
        height = max(self.root.winfo_height(), self.root.winfo_reqheight())
        x, y = window_position_near_cursor(
            (values[0], values[1]),
            (width, height),
            (values[2], values[3], values[4], values[5]),
        )
        self.root.geometry(f"+{x}+{y}")

    def _load_actions(self) -> None:
        try:
            self.actions, self.local_action_ids = load_combined_actions(
                self.actions_path,
                self.local_actions_path,
            )
            self.status_var.set(f"Loaded {len(self.actions)} actions")
        except ActionError as exc:
            self.status_var.set(
                f"Actions could not be loaded; kept {len(self.actions)} previous action(s)."
            )
            messagebox.showerror(
                "Actions could not be loaded",
                f"{exc}\n\nNo actions were changed. Correct the action file and choose Configure or restart.",
                parent=self.root,
            )
            LOGGER.exception("Action configuration failed to load")

    def _load_command_surface(self) -> None:
        try:
            self.command_groups = load_combined_command_groups(
                self.command_surface_path,
                self.local_command_surface_path,
            )
        except CommandSurfaceError as exc:
            button_count = sum(len(group.items) for group in self.command_groups)
            self.status_var.set(
                f"Quick actions could not be loaded; kept {button_count} previous button(s)."
            )
            messagebox.showerror(
                "Quick actions could not be loaded",
                f"{exc}\n\nNo buttons were changed. Correct the button configuration and reload.",
                parent=self.root,
            )
            LOGGER.exception("Quick-action configuration failed to load")
        self._render_command_surface()

    def _render_command_surface(self) -> None:
        for tooltip in self.command_surface_tooltips:
            tooltip.hide()
        self.command_surface_tooltips.clear()
        for child in self.command_tiles_frame.winfo_children():
            child.destroy()
        credential_actions = frequent_credential_actions(
            self.actions,
            self.palette_state.pinned_action_ids,
        )
        button_count = len(credential_actions) + sum(
            len(group.items) for group in self.command_groups
        )
        self.surface_count_var.set(
            f"{button_count} button" if button_count == 1 else f"{button_count} buttons"
        )
        if not self.command_groups and not credential_actions:
            empty = ttk.Label(
                self.command_tiles_frame,
                text="No quick actions yet.\nUse Configure → Right-side buttons to add one.",
                style="Muted.TLabel",
                wraplength=260,
                justify=tk.LEFT,
            )
            empty.pack(fill=tk.X, padx=8, pady=12)
            self._command_surface_tooltip(
                empty,
                "Create a personal quick-action button from Configure.",
            )
            return

        for column in range(2):
            self.command_tiles_frame.columnconfigure(column, weight=1, uniform="surface")
        group_row_offset = 0
        if credential_actions:
            password_area = ttk.LabelFrame(
                self.command_tiles_frame,
                text="Frequent passwords",
                padding=4,
            )
            password_area.grid(
                row=0,
                column=0,
                columnspan=2,
                sticky=tk.NSEW,
                padx=2,
                pady=2,
            )
            for column in range(4):
                password_area.columnconfigure(column, weight=1, uniform="passwords")
            for column, action in enumerate(credential_actions):
                control = ttk.Button(
                    password_area,
                    text=action.title,
                    command=lambda selected_action=action: self._execute_action(selected_action),
                    style="Compact.TButton",
                )
                control.grid(
                    row=0,
                    column=column,
                    sticky=tk.EW,
                    padx=1,
                    pady=1,
                )
                self._command_surface_tooltip(
                    control,
                    "Paste this credential directly. The destination confirmation remains required.",
                )
            group_row_offset = 1
        for index, group in enumerate(self.command_groups):
            row, column = divmod(index, 2)
            row += group_row_offset
            area = ttk.LabelFrame(self.command_tiles_frame, text=group.label, padding=4)
            area.grid(row=row, column=column, sticky=tk.NSEW, padx=2, pady=2)
            for button_column in range(3):
                area.columnconfigure(button_column, weight=1, uniform=f"group-{group.id}")
            for item_index, item in enumerate(group.items):
                item_row, item_column = divmod(item_index, 3)
                control = ttk.Label(
                    area,
                    text=item.label,
                    style="Surface.TLabel",
                    anchor=tk.CENTER,
                    relief=tk.SOLID,
                    padding=(3, 2),
                    cursor="hand2",
                    takefocus=True,
                )
                control.grid(
                    row=item_row,
                    column=item_column,
                    sticky=tk.EW,
                    padx=1,
                    pady=1,
                )
                self._command_surface_tooltip(
                    control,
                    "Left-click or Enter runs the primary action. Right-click chooses an action. Shift/Ctrl+click edits configuration.",
                )
                control.bind(
                    "<Button-1>",
                    lambda event, selected_group=group, selected_item=item: self._handle_command_item_left_click(
                        event,
                        selected_group,
                        selected_item,
                    ),
                    add="+",
                )
                control.bind(
                    "<Button-3>",
                    lambda event, selected_item=item: self._show_item_menu(event, selected_item),
                    add="+",
                )
                control.bind(
                    "<Return>",
                    lambda _event, selected_item=item: self._execute_item_primary(selected_item),
                    add="+",
                )
                control.bind(
                    "<space>",
                    lambda _event, selected_item=item: self._execute_item_primary(selected_item),
                    add="+",
                )

    def _execute_item_primary(self, item: CommandItem) -> str:
        action = self._primary_action_for_item(item)
        if action is None:
            self.status_var.set(f"{item.label} has no available action. Open Configure to assign one.")
            return "break"
        self._execute_action(action)
        return "break"

    def _handle_command_item_left_click(
        self,
        event: tk.Event,
        group: CommandGroup,
        item: CommandItem,
    ) -> str:
        # Shift/Ctrl click preserves the direct path to menu and action JSON configuration.
        if event.state & (0x0001 | 0x0004):
            self._open_command_configuration(group)
            return "break"
        action = self._primary_action_for_item(item)
        if action is None:
            self.status_var.set(f"No available actions configured for {item.label}.")
            return "break"
        self._execute_action(action)
        return "break"

    def _primary_action_for_item(self, item: CommandItem) -> Action | None:
        actions_by_id = {action.id: action for action in self.actions}
        for action_id in command_item_action_ids(item):
            action = actions_by_id.get(action_id)
            if action is not None:
                return action
        return None

    def _open_command_configuration(self, group: CommandGroup) -> None:
        surface_path, actions_path = command_configuration_paths(
            group,
            self.command_surface_path,
            self.local_command_surface_path,
            self.actions_path,
            self.local_actions_path,
        )
        for path, title in (
            (surface_path, "Edit command-surface menus"),
            (actions_path, "Edit command-surface actions"),
        ):
            self._execute_action(
                Action(
                    id=f"configure-{path.stem}",
                    title=title,
                    context="Configuration",
                    type="open_file",
                    value=str(path.resolve()),
                    state="Trusted",
                    technology="JSON",
                    task="Configure quick actions",
                )
            )
        self.status_var.set(f"Opened menu and action configuration for {group.label}.")

    def _show_item_menu(self, event: tk.Event, item: CommandItem) -> str:
        actions_by_id = {action.id: action for action in self.actions}
        menu = tk.Menu(self.root, tearoff=False)
        for action_id in command_item_action_ids(item):
            action = actions_by_id.get(action_id)
            if action is None:
                continue
            menu.add_command(
                label=action.compact_display_text,
                command=lambda selected_action=action: self._execute_action(selected_action),
            )
        if menu.index(tk.END) is None:
            menu.add_command(label="No available actions", state=tk.DISABLED)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _action_storage_path(self, action: Action) -> Path:
        return self.local_actions_path if action.id in self.local_action_ids else self.actions_path

    def _load_contexts(self) -> None:
        try:
            self.context_definitions = load_combined_contexts(
                self.contexts_path,
                self.local_contexts_path,
            )
        except ContextError as exc:
            self.status_var.set(
                f"Contexts could not be loaded; kept {len(self.context_definitions)} previous context(s)."
            )
            messagebox.showerror(
                "Contexts could not be loaded",
                f"{exc}\n\nNo contexts were changed. Correct the context configuration and reload.",
                parent=self.root,
            )
            LOGGER.exception("Context configuration failed to load")

    def _load_palette_state(self) -> None:
        try:
            self.palette_state = load_palette_state(self.palette_path)
        except ActionError as exc:
            self.palette_state = PaletteState()
            messagebox.showerror("Context Palette", str(exc))
        configured_names = {context.name for context in self.context_definitions}
        contexts = sorted(configured_names | {action.context for action in self.actions}, key=str.casefold)
        configured_slots = dict(self.palette_state.context_slots)
        known_action_ids = {action.id for action in self.actions}
        for definition in self.context_definitions:
            if definition.name not in configured_slots and definition.preferred_action_ids:
                configured_slots[definition.name] = tuple(
                    action_id
                    for action_id in definition.preferred_action_ids
                    if action_id in known_action_ids
                )
        self.palette_state = PaletteState(
            self.palette_state.pinned_action_ids,
            self.palette_state.focus_context,
            configured_slots,
        )
        if self.palette_state.focus_context not in contexts and contexts:
            self.palette_state = PaletteState(
                self.palette_state.pinned_action_ids,
                contexts[0],
                self.palette_state.context_slots,
            )
        self.context_picker["values"] = contexts
        self.context_var.set(self.palette_state.focus_context)
        self._render_command_surface()

    def _change_focus_context(self) -> None:
        context = self.context_var.get().strip() or "General"
        previous_state = self.palette_state
        updated_state = PaletteState(
            self.palette_state.pinned_action_ids,
            context,
            self.palette_state.context_slots,
        )
        try:
            save_palette_state(self.palette_path, updated_state)
        except OSError as exc:
            self.context_var.set(previous_state.focus_context)
            self.status_var.set("Focus context was not changed because it could not be saved.")
            messagebox.showerror(
                "Context Palette",
                f"Could not save the focus context.\n\n{exc}",
            )
            return
        self.palette_state = updated_state
        self.configuration_signature_cache = self._configuration_signature()
        self._refresh_results()
        self.status_var.set(f"Focus context: {context}")
        definition = next(
            (item for item in self.context_definitions if item.name.casefold() == context.casefold()),
            None,
        )
        if definition and definition.description:
            self.status_var.set(f"{context}: {definition.description}")

    def _refresh_results(self) -> None:
        started_at = time.perf_counter()
        if self.search_refresh_after_id is not None:
            try:
                self.root.after_cancel(self.search_refresh_after_id)
            except tk.TclError:
                pass
            self.search_refresh_after_id = None
        self.results_tooltip.hide()
        self.filtered_actions = search_actions(self.actions, self.search_var.get())
        if self.action_type_filter is not None:
            self.filtered_actions = [
                action
                for action in self.filtered_actions
                if action.type == self.action_type_filter
            ]
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
                self.results.itemconfigure(
                    index,
                    background=COLORS["row_light"],
                    foreground=COLORS["text"],
                )
            elif slot is not None and 6 <= slot <= 9:
                self.results.itemconfigure(
                    index,
                    background=COLORS["row_aqua"],
                    foreground=COLORS["text"],
                )
        if self.displayed_actions:
            self.results.selection_set(0)
            self.results.activate(0)
        count = len(self.filtered_actions)
        self.results_count_var.set(f"{count} action" if count == 1 else f"{count} actions")
        if not self.displayed_actions:
            query = self.search_var.get().strip()
            if self.action_type_filter == "paste_credential":
                empty_message = (
                    f'No password actions match “{query}”.\nClear Find or create one in Configure.'
                    if query
                    else "No password actions yet.\nUse Configure to create one."
                )
            else:
                empty_message = (
                    f'No actions match “{query}”.\nClear Find or use Configure to create one.'
                    if query
                    else "No actions are available.\nUse Configure to create your first personal action."
                )
            self.results.insert(tk.END, empty_message)
            self.results.itemconfigure(
                0,
                foreground=COLORS["muted_text"],
                background=COLORS["surface"],
            )
            if self.action_type_filter == "paste_credential":
                self.status_var.set("No matching password action. Clear Find or create one.")
            else:
                self.status_var.set("No matching action. Clear Find or create one in Configure.")
        else:
            if self.action_type_filter == "paste_credential":
                label = "password action" if count == 1 else "password actions"
                self.status_var.set(f"{count} {label}")
            else:
                self.status_var.set(
                    f"{count} matches · slots 1–5 pinned · slots 6–9 {self.palette_state.focus_context}"
                )
        self._update_preview()
        _warn_if_slow(
            "result refresh",
            started_at,
            SLOW_RESULT_REFRESH_SECONDS,
            action_count=len(self.actions),
        )

    def _schedule_refresh_results(self) -> None:
        if self.search_refresh_after_id is not None:
            self.root.after_cancel(self.search_refresh_after_id)
        self.search_refresh_after_id = self.root.after(40, self._run_scheduled_refresh)

    def _run_scheduled_refresh(self) -> None:
        self.search_refresh_after_id = None
        self._refresh_results()

    def _configuration_signature(self) -> tuple[tuple[str, int, int], ...]:
        paths = (
            self.actions_path,
            self.local_actions_path,
            self.contexts_path,
            self.local_contexts_path,
            self.command_surface_path,
            self.local_command_surface_path,
            self.palette_path,
        )
        signature = []
        for path in paths:
            try:
                stat = path.stat()
                signature.append((str(path), stat.st_mtime_ns, stat.st_size))
            except OSError:
                signature.append((str(path), -1, -1))
        return tuple(signature)

    def _reload_if_changed(self) -> None:
        if self._configuration_signature() == self.configuration_signature_cache:
            LOGGER.debug("Configuration unchanged; skipped full reload")
            return
        self._reload()

    def _reload(self) -> None:
        started_at = time.perf_counter()
        self.status_var.set("Refreshing actions, contexts, and buttons…")
        self.root.configure(cursor="wait")
        self.root.update_idletasks()
        try:
            self._load_actions()
            self._load_command_surface()
            self._load_contexts()
            self._load_palette_state()
            self._refresh_results()
            self.configuration_signature_cache = self._configuration_signature()
        finally:
            self.root.configure(cursor="")
            _warn_if_slow(
                "configuration reload",
                started_at,
                SLOW_CONFIGURATION_RELOAD_SECONDS,
                action_count=len(self.actions),
            )

    def _toggle_selected_pin(self) -> None:
        action = self._selected_action()
        if action is None:
            self.status_var.set("No action selected")
            return
        try:
            updated_state = toggle_pin(self.palette_state, action.id)
        except ActionError as exc:
            messagebox.showerror("Context Palette", str(exc))
            return
        try:
            save_palette_state(self.palette_path, updated_state)
        except OSError as exc:
            self.status_var.set("Pin was not changed because it could not be saved.")
            messagebox.showerror(
                "Context Palette",
                f"Could not save the pin change.\n\n{exc}",
            )
            return
        self.palette_state = updated_state
        self.configuration_signature_cache = self._configuration_signature()
        self._refresh_results()
        self._render_command_surface()
        verb = "Pinned" if action.id in self.palette_state.pinned_action_ids else "Unpinned"
        self.status_var.set(f"{verb}: {action.display_text}")

    def _execute_selected(self) -> None:
        action = self._selected_action()
        if action is None:
            self.status_var.set("No action selected")
            return

        self._execute_action(action)

    def _execute_action(self, action: Action) -> None:
        try:
            message = execute_action(
                action,
                clipboard_setter=self._set_clipboard,
                clipboard_getter=self._get_clipboard_text,
                input_provider=self._ask_for_action_input,
                selected_text=self._workspace_text() or self.captured_selection,
                input_text=self._workspace_text(),
                output_setter=self._set_workspace_text,
                credential_paster=self._paste_credential_action,
            )
            self.status_var.set(message)
        except ActionError as exc:
            self.status_var.set("Action failed")
            messagebox.showerror("Context Palette", str(exc))
            LOGGER.exception("Action failed: id=%s type=%s", action.id, action.type)

    def _paste_credential_action(self, action: Action) -> str:
        destination = self.source_foreground_handle
        if destination is None:
            raise ActionError(
                "Open Context Palette with F9 or Ctrl+Alt+P from the destination password field."
            )
        destination_title = " ".join(window_title(destination).split())
        destination_title = destination_title[:160] or "the captured application"
        if not messagebox.askyesno(
            "Paste protected credential",
            (
                f"Paste credential target:\n{action.value}\n\n"
                f"Destination:\n{destination_title}\n\n"
                "The password will not be shown or added to clipboard history."
            ),
            parent=self.root,
        ):
            return "Credential paste cancelled."
        try:
            secret = read_windows_credential(action.value)
            sequence = set_protected_clipboard_text(secret.password)
        except CredentialAccessError as exc:
            raise ActionError(str(exc)) from exc
        self.source_foreground_handle = None
        self.protected_clipboard_sequence = sequence
        self.root.withdraw()

        def paste_into_destination() -> None:
            if not focus_window(destination):
                self._clear_protected_clipboard(sequence)
                self.show_window()
                messagebox.showerror(
                    "Credential paste cancelled",
                    "The captured destination window is no longer available.",
                    parent=self.root,
                )
                return
            send_paste_shortcut()
            self.root.after(
                15_000,
                lambda: self._clear_protected_clipboard(sequence),
            )

        self.root.after(120, paste_into_destination)
        return "Protected credential paste approved; returning to the destination."

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
        self._execute_action(action)
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
            self.action_info_full = "Select an action to see what it reads and what it will do."
            self.status_var.set("Select an action to see what it reads and what it will do.")
            return
        detail = self._preview_text(action)
        lines = detail.splitlines()
        if len(lines) > 5:
            detail = "\n".join(lines[:5]) + "\n…"
        if len(detail) > 520:
            detail = detail[:517].rstrip() + "…"
        compact_detail = " · ".join(line.strip() for line in detail.splitlines() if line.strip())
        self.action_info_full = f"{action.display_text}\n\n{self._preview_text(action)}"
        message = f"{action.display_text} — {compact_detail}"
        self.status_var.set(message[:217].rstrip() + "…" if len(message) > 220 else message)

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
        if action.type == "paste_credential":
            return (
                "Paste a protected Windows credential.\n"
                f"Credential target: {action.value}\n"
                "Requires Trusted state and a fresh hotkey invocation from the destination field."
            )
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
        return f"{action.type}:\n{action.value}"

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

    def _sync_workspace_from_clipboard(self) -> None:
        try:
            value = self.root.clipboard_get()
        except tk.TclError:
            return
        self._set_workspace_text(value)

    def _sync_workspace_from_clipboard_if_safe(self) -> None:
        if self.protected_clipboard_sequence is None:
            self._sync_workspace_from_clipboard()

    def _copy_workspace_to_clipboard(self) -> None:
        value = self._workspace_text()
        if not value:
            self.status_var.set("Input / Output is empty; nothing was copied.")
            return
        self._set_clipboard(value)
        self.status_var.set("Copied Input / Output to the clipboard.")

    def _set_clipboard(self, value: str) -> None:
        self.protected_clipboard_sequence = None
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update()

    def _clear_protected_clipboard(self, sequence: int | None = None) -> None:
        current = self.protected_clipboard_sequence
        target = sequence if sequence is not None else current
        if target is None:
            return
        clear_clipboard_if_unchanged(target)
        if self.protected_clipboard_sequence == target:
            self.protected_clipboard_sequence = None

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

    def _show_configuration(self) -> None:
        ConfigurationWindow(
            self.root,
            actions=self.actions,
            local_action_ids=self.local_action_ids,
            local_actions_path=self.local_actions_path,
            contexts_path=self.contexts_path,
            local_contexts_path=self.local_contexts_path,
            command_surface_path=self.command_surface_path,
            local_command_surface_path=self.local_command_surface_path,
            on_change=self._reload,
        )

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
        focused_widget = self.root.focus_get()
        return focused_widget is not self.search_entry


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
        self.window.bind("<Escape>", lambda _event: self.window.destroy())

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="Capture Inbox", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            outer,
            text=f"{len(items)} captured item{'s' if len(items) != 1 else ''} · turn useful material into a Draft action",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(2, 8))

        self.listbox = tk.Listbox(outer, activestyle="dotbox", height=8)
        self.listbox.pack(fill=tk.BOTH, expand=True, pady=(4, 8))
        self.listbox.bind("<<ListboxSelect>>", lambda _event: self._update_preview())

        ttk.Label(outer, text="Preview").pack(anchor=tk.W)
        self.preview = tk.Text(outer, height=8, wrap=tk.WORD)
        self.preview.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.preview.configure(state=tk.DISABLED)

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=(8, 0))
        self.convert_button = ttk.Button(
            controls,
            text="Convert to Draft Action",
            command=self._convert_selected,
            style="Accent.TButton",
        )
        self.convert_button.pack(side=tk.LEFT)
        self.ai_button = ttk.Button(controls, text="Ask AI", command=self._ask_ai_for_selected)
        self.ai_button.pack(
            side=tk.LEFT, padx=(6, 0)
        )
        ttk.Button(
            controls,
            text="Close",
            command=self.window.destroy,
            style="Compact.TButton",
        ).pack(side=tk.RIGHT)

        self._load_items()

    def _load_items(self) -> None:
        self.listbox.delete(0, tk.END)
        for item in self.items:
            self.listbox.insert(tk.END, f"{item.title} ({item.created_at})")
        if self.items:
            self.listbox.selection_set(0)
            self.listbox.activate(0)
            self.convert_button.configure(state=tk.NORMAL)
            self.ai_button.configure(state=tk.NORMAL)
        else:
            self.listbox.insert(
                tk.END,
                "Inbox is empty — use Capture in the main palette to save clipboard text.",
            )
            self.listbox.itemconfigure(0, foreground=COLORS["muted_text"])
            self.convert_button.configure(state=tk.DISABLED)
            self.ai_button.configure(state=tk.DISABLED)
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

    def _ask_ai_for_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        contexts = {action.context for action in self.actions if action.context}
        contexts.update((self.focus_context, item.suggested_context, "General"))
        AIGuidanceWindow(
            self.window,
            item,
            contexts,
            self._save_ai_actions,
        )

    def _save_ai_actions(self, item: InboxItem, actions: list[Action]) -> None:
        try:
            append_actions(self.actions_path, actions)
            update_inbox_item_state(self.inbox_path, item.id, "Draft")
            self.items = load_inbox_items(self.inbox_path)
            self._load_items()
            self.on_change()
            messagebox.showinfo(
                "Context Palette",
                f"Created {len(actions)} local Draft action(s).",
                parent=self.window,
            )
        except (ActionError, InboxError) as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.window)

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
    ACTION_TYPES = {
        "Copy captured text": "copy_text",
        "Build URL — open from selected or copied ID": "build_url_selection_open",
        "Build URL — copy only and ask for input": "build_url_copy",
        "Build URL — open only and ask for input": "build_url_open",
    }

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
        self.window.geometry("680x620")
        self.window.minsize(520, 440)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())

        technologies = sorted({action.technology for action in actions if action.technology}, key=str.casefold)
        tasks = sorted({action.task for action in actions if action.task}, key=str.casefold)
        contexts = sorted({action.context for action in actions if action.context}, key=str.casefold)

        self.technology_var = tk.StringVar()
        self.task_var = tk.StringVar()
        self.context_var = tk.StringVar(value=initial_context or "General")
        self.title_var = tk.StringVar(value=item.title)
        self.action_type_var = tk.StringVar(value="Copy captured text")
        self.guidance_var = tk.StringVar()
        self.example_var = tk.StringVar()

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(outer)
        controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        ttk.Button(controls, text="Create Draft", command=self._save).pack(side=tk.LEFT)
        ttk.Button(controls, text="Cancel", command=self.window.destroy).pack(side=tk.RIGHT)

        form = ttk.Frame(outer)
        form.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        ttk.Label(
            form,
            text="What should this action do?",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            form,
            text="Choose the result first; the fields below adapt to that choice.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(1, 6))
        type_field = ttk.Combobox(
            form,
            textvariable=self.action_type_var,
            values=list(self.ACTION_TYPES),
            state="readonly",
        )
        type_field.pack(fill=tk.X)
        type_field.bind("<<ComboboxSelected>>", lambda _event: self._action_type_changed())

        metadata = ttk.Frame(form)
        metadata.pack(fill=tk.X, pady=(6, 0))
        left = ttk.Frame(metadata)
        left.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        right = ttk.Frame(metadata)
        right.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._field(left, "Technology", self.technology_var, technologies)
        self._field(right, "Task", self.task_var, tasks)
        self._field(left, "Context", self.context_var, contexts)

        ttk.Label(right, text="Action name").pack(anchor=tk.W, pady=(8, 0))
        title_entry = ttk.Entry(right, textvariable=self.title_var)
        title_entry.pack(fill=tk.X, pady=(3, 0))

        self.content_label = ttk.Label(form, text="Captured text to copy")
        self.content_label.pack(anchor=tk.W, pady=(8, 0))
        self.content = tk.Text(form, height=7, wrap=tk.WORD, undo=True)
        self.content.pack(fill=tk.BOTH, expand=True, pady=(3, 0))
        self.content.insert("1.0", item.content)
        self.content.bind("<KeyRelease>", lambda _event: self._update_example())

        ttk.Label(form, textvariable=self.guidance_var, style="Muted.TLabel", wraplength=620).pack(
            anchor=tk.W, pady=(6, 0)
        )
        ttk.Label(form, textvariable=self.example_var, wraplength=620).pack(anchor=tk.W, pady=(4, 0))

        self.path_var = tk.StringVar()
        ttk.Label(form, textvariable=self.path_var).pack(anchor=tk.W, pady=(6, 0))
        for variable in (self.technology_var, self.task_var, self.context_var, self.title_var):
            variable.trace_add("write", lambda *_args: self._update_path())

        self._update_path()
        self._action_type_changed()
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

    def _action_type_changed(self) -> None:
        action_type = self.ACTION_TYPES[self.action_type_var.get()]
        if action_type == "copy_text":
            self.content_label.configure(text="Captured text to copy")
            self.guidance_var.set("The Inbox capture becomes the reusable text produced by this action.")
        else:
            self.content_label.configure(text="URL template")
            self.guidance_var.set(
                "Keep the stable base URL from Inbox and put {id_url} where the runtime ID belongs. "
                "This action reads the selected text first, then falls back to copied text. "
                "Example: https://domain-product.atlassian.net/browse/{id_url}"
            )
            current = self.content.get("1.0", "end-1c")
            suggested = suggest_url_template(current)
            if suggested != current.strip():
                self.content.delete("1.0", tk.END)
                self.content.insert("1.0", suggested)
        self._update_example()

    def _update_example(self) -> None:
        action_type = self.ACTION_TYPES[self.action_type_var.get()]
        if action_type == "copy_text":
            self.example_var.set("Result: copies the text above.")
            return
        template = self.content.get("1.0", "end-1c").strip()
        try:
            example = build_url(template, "ABC 123")
            effect = "copy and open" if action_type == "build_url_selection_open" else (
                "copy" if action_type == "build_url_copy" else "open"
            )
            self.example_var.set(f"Example input: ABC 123  →  {example}\nEffect: {effect}")
        except ActionError as exc:
            self.example_var.set(f"Template needs attention: {exc}")

    def _save(self) -> None:
        try:
            action_type = self.ACTION_TYPES[self.action_type_var.get()]
            common = {
                "title": self.title_var.get(),
                "technology": self.technology_var.get(),
                "task": self.task_var.get(),
                "context": self.context_var.get(),
            }
            if action_type == "copy_text":
                action = draft_copy_text_action(
                    **common,
                    value=self.content.get("1.0", "end-1c"),
                )
            else:
                action = draft_build_url_action(
                    **common,
                    template=self.content.get("1.0", "end-1c"),
                    action_type=action_type,
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
        self.window.bind("<Escape>", lambda _event: self.window.destroy())

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
        self.window.bind("<Escape>", lambda _event: self.window.destroy())

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="Cheat sheets", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            outer,
            text=f"{len(sheets)} local reference sheet{'s' if len(sheets) != 1 else ''}",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(2, 8))

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
        ttk.Label(controls, textvariable=self.status_var, style="Status.TLabel").pack(side=tk.LEFT)
        ttk.Button(
            controls,
            text="Close",
            command=self.window.destroy,
            style="Compact.TButton",
        ).pack(side=tk.RIGHT)

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
            self.items.insert(
                tk.END,
                "No cheat sheets are available. Add a local sheet or check configuration.",
            )
            self.items.itemconfigure(0, foreground=COLORS["muted_text"])
            self.status_var.set("No cheat sheets available")
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
            query = self.search_var.get().strip()
            self.items.insert(
                tk.END,
                f'No entries match “{query}”. Clear search to show all entries.'
                if query
                else "This sheet has no entries.",
            )
            self.items.itemconfigure(0, foreground=COLORS["muted_text"])
            self.status_var.set("No matching entries")
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
    contexts_path: Path,
    local_contexts_path: Path,
    command_surface_path: Path,
    local_command_surface_path: Path,
    palette_path: Path,
    inbox_path: Path,
    cheatsheets_dir: Path,
    instance_port: int,
    initial_request: dict[str, str] | None = None,
) -> None:
    root = tk.Tk()
    LauncherApp(
        root,
        actions_path,
        local_actions_path,
        contexts_path,
        local_contexts_path,
        command_surface_path,
        local_command_surface_path,
        palette_path,
        inbox_path,
        cheatsheets_dir,
        instance_port,
        initial_request,
    )
    root.mainloop()
