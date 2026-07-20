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
from .action_types import ACTION_TYPES
from .cheat_sheet_window import CheatSheetWindow
from .cheatsheets import CheatSheetError, load_cheatsheets
from .command_surface import (
    CommandGroup,
    CommandItem,
    CommandSurfaceError,
    command_configuration_paths,
    command_item_action_ids,
    load_combined_command_groups,
)
from .configuration_window import ConfigurationWindow
from .focus_model import focus_action_hierarchy, resolve_focus_state
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
from .tooltips import ListboxItemTooltip, TreeviewItemTooltip, WidgetTooltip
from .window_geometry import configure_main_window, configure_standard_window
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
MINIMUM_ACTION_CONSOLE_HEIGHT = 140
MINIMUM_WORKSPACE_HEIGHT = 140
MINIMUM_ACTIONS_WIDTH = 300
MINIMUM_QUICK_ACTIONS_WIDTH = 320
BUILTIN_QUICK_COMMAND_OPEN_SHEETS = "open_sheets"
BUILTIN_QUICK_COMMANDS = frozenset({BUILTIN_QUICK_COMMAND_OPEN_SHEETS})


def bounded_sash_position(
    available_size: int,
    ratio: float,
    first_minimum: int,
    second_minimum: int,
) -> int:
    """Return a sash position that keeps both panes useful when space permits."""
    if available_size <= 1:
        return 0
    combined_minimum = first_minimum + second_minimum
    if available_size < combined_minimum:
        return round(available_size * first_minimum / combined_minimum)
    requested = round(available_size * ratio)
    return max(first_minimum, min(requested, available_size - second_minimum))


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


def execute_builtin_quick_command(command_id: str, *, open_sheets: Callable[[], None]) -> None:
    """Execute one explicitly allow-listed application command."""
    if command_id == BUILTIN_QUICK_COMMAND_OPEN_SHEETS:
        open_sheets()
        return
    raise ValueError(f"Unknown built-in quick command: {command_id}")


def _warn_if_slow(
    operation: str,
    started_at: float,
    threshold_seconds: float,
    *,
    action_count: int,
    stage_timings_ms: dict[str, float] | None = None,
) -> None:
    elapsed_seconds = time.perf_counter() - started_at
    if elapsed_seconds >= threshold_seconds:
        stage_summary = ""
        if stage_timings_ms:
            stage_summary = " stages_ms=" + ",".join(
                f"{name}:{duration_ms:.1f}"
                for name, duration_ms in stage_timings_ms.items()
            )
        LOGGER.warning(
            "Slow %s: elapsed_ms=%.1f action_count=%d%s",
            operation,
            elapsed_seconds * 1000,
            action_count,
            stage_summary,
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
        self.available_context_names: list[str] = []
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
        self.focus_actions_mode = False
        self.focus_tree_actions: dict[str, Action] = {}
        self.focus_tree_expansion: dict[str, set[tuple[str, ...]]] = {}
        self.focus_tree_context: str | None = None
        self.results_view = "flat"
        self.passwords_button: ttk.Button | None = None
        self.action_type_filter_var = tk.StringVar(value="All types")
        self.configuration_signature_cache: tuple[tuple[str, int, int], ...] = ()
        self.search_var = tk.StringVar()
        self.context_var = tk.StringVar(value="General")
        self.focus_launcher_var = tk.StringVar(value="General ▾")
        self.manage_focus_var = tk.StringVar(value="Manage focus ▾")
        self.actions_heading_var = tk.StringVar(value="Actions")
        self.results_count_var = tk.StringVar(value="0 actions")
        self.surface_count_var = tk.StringVar(value="0 buttons")
        self.widget_tooltips: list[WidgetTooltip] = []
        self.command_surface_tooltips: list[WidgetTooltip] = []
        self.action_info_full = "Select an action to see what it reads and what it will do."
        self.status_var = tk.StringVar(value="Ready")
        self.search_var.trace_add("write", lambda *_args: self._schedule_refresh_results())

        self._build_ui()
        self._load_actions()
        self._load_command_surface(render=False)
        self._load_contexts()
        self._load_palette_state(render=False)
        self._render_command_surface()
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
        configure_main_window(self.root)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        self.root.bind("<FocusOut>", self._schedule_hide_when_inactive)
        self.root.bind("<FocusIn>", self._cancel_scheduled_hide)

        configure_theme(self.root)

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        self._build_header(outer)
        self._bind_main_shortcuts()

        content = ttk.Panedwindow(outer, orient=tk.VERTICAL)
        results_container = ttk.Frame(content)
        workspace_container = ttk.Frame(content)
        content.add(results_container, weight=2)
        content.add(workspace_container, weight=3)
        self._build_results_area(results_container)
        self._build_workspace(workspace_container)
        self._build_footer(outer)
        content.pack(fill=tk.BOTH, expand=True)
        self.main_content = content
        self.results_container = results_container
        self.workspace_container = workspace_container
        self.main_split_ratio = 0.52
        self.main_content.bind("<Configure>", self._resize_main_split)
        self.main_content.bind("<ButtonRelease-1>", self._remember_main_split)
        self.root.after_idle(self._set_initial_main_split)

    def _set_initial_main_split(self) -> None:
        self.root.update_idletasks()
        available_height = self.main_content.winfo_height()
        if available_height <= 1:
            self.root.after(10, self._set_initial_main_split)
            return
        self.main_content.sashpos(
            0,
            bounded_sash_position(
                available_height,
                self.main_split_ratio,
                MINIMUM_ACTION_CONSOLE_HEIGHT,
                MINIMUM_WORKSPACE_HEIGHT,
            ),
        )

    def _resize_main_split(self, event: tk.Event) -> None:
        if event.height > 1:
            self.main_content.sashpos(
                0,
                bounded_sash_position(
                    event.height,
                    self.main_split_ratio,
                    MINIMUM_ACTION_CONSOLE_HEIGHT,
                    MINIMUM_WORKSPACE_HEIGHT,
                ),
            )

    def _remember_main_split(self, _event: tk.Event) -> None:
        available_height = self.main_content.winfo_height()
        if available_height > 1:
            position = bounded_sash_position(
                available_height,
                self.main_content.sashpos(0) / available_height,
                MINIMUM_ACTION_CONSOLE_HEIGHT,
                MINIMUM_WORKSPACE_HEIGHT,
            )
            self.main_content.sashpos(0, position)
            self.main_split_ratio = position / available_height

    def _build_header(self, outer: ttk.Frame) -> None:

        context_panel = ttk.Frame(outer)
        context_panel.pack(fill=tk.X, pady=(0, 8))
        focus_label = ttk.Label(context_panel, text="Focus", style="Heading.TLabel")
        focus_label.pack(side=tk.LEFT)
        self._tooltip(focus_label, "Choose what you are working on. This changes context slots 6–9.")
        self.context_picker = ttk.Menubutton(
            context_panel,
            textvariable=self.focus_launcher_var,
            width=18,
            style="Compact.TButton",
        )
        self.context_picker.pack(side=tk.LEFT, padx=(10, 6))
        self.context_menu = tk.Menu(self.context_picker, tearoff=False)
        self.context_picker.configure(menu=self.context_menu)
        focus_actions_button = ttk.Button(
            context_panel,
            text="Focus actions",
            command=self._activate_focus_actions,
            style="Compact.TButton",
        )
        focus_actions_button.pack(side=tk.LEFT, padx=(0, 6))
        manage_focus = ttk.Menubutton(
            context_panel,
            textvariable=self.manage_focus_var,
            style="Compact.TButton",
        )
        manage_focus.pack(side=tk.LEFT)
        manage_focus_menu = tk.Menu(manage_focus, tearoff=False)
        manage_focus_menu.add_command(
            label="Manage focuses…",
            command=self._show_focus_configuration,
        )
        manage_focus_menu.add_separator()
        manage_focus_menu.add_command(
            label="Configure actions and buttons…",
            command=self._show_configuration,
        )
        manage_focus.configure(menu=manage_focus_menu)
        context_help = ttk.Button(context_panel, text="?", width=3, command=self._show_help)
        context_help.pack(side=tk.RIGHT)
        self._tooltip(
            self.context_picker,
            lambda: f"Active Focus: {self.context_var.get()}. Choose a Focus explicitly.",
        )
        self._tooltip(
            focus_actions_button,
            "Show actions explicitly assigned to the active Focus, grouped by technology and task.",
        )
        self._tooltip(
            manage_focus,
            "Manage focus — Edit focuses or configure actions and buttons.",
        )
        self._tooltip(
            context_help,
            "Focus changes slots 6–9. It does not limit global search. Open Help for context configuration.",
        )
        self.global_help_button = context_help
        self.configure_button = manage_focus
        self.focus_actions_button = focus_actions_button
        self.manage_focus_button = manage_focus
        self.manage_focus_menu = manage_focus_menu

    def _activate_focus_actions(self) -> None:
        self.focus_actions_mode = True
        self._refresh_results()
        self.root.after_idle(self._focus_active_results)

    def _focus_active_results(self) -> None:
        """Move keyboard users into the result view they explicitly opened."""
        if self.results_view == "focus" and self.focus_tree.winfo_manager():
            self.focus_tree.focus_force()

    def _toggle_password_actions(self) -> None:
        selected = (
            None if self.action_type_filter == "paste_credential" else "paste_credential"
        )
        self._select_action_type_filter(selected)

    def _select_action_type_filter(self, action_type: str | None) -> None:
        self.action_type_filter = action_type
        self.action_type_filter_var.set(
            ACTION_TYPES[action_type].label if action_type is not None else "All types"
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
        ttk.Label(
            results_header,
            textvariable=self.actions_heading_var,
            style="PaneHeader.TLabel",
        ).pack(side=tk.LEFT)
        ttk.Label(
            results_header,
            textvariable=self.results_count_var,
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)

        search_row = ttk.Frame(results_frame)
        search_row.pack(fill=tk.X, pady=(0, 5))
        find_label = ttk.Label(search_row, text="Find action", style="Heading.TLabel")
        find_label.pack(anchor=tk.W)
        self._tooltip(find_label, "Type any technology, task, context, action name, type, or content.")
        search = ttk.Entry(search_row, textvariable=self.search_var, font=("Segoe UI", 11))
        self.search_entry = search
        search.pack(fill=tk.X, pady=(3, 0))
        search.focus_set()
        search.bind("<KeyPress>", self._handle_keypress)
        search.bind("<Return>", lambda _event: self._execute_selected())

        results_body = ttk.Frame(results_frame)
        results_body.pack(fill=tk.BOTH, expand=True)

        self.actions_tool_rail = ttk.Frame(results_body, width=88)
        self.actions_tool_rail.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))
        self.actions_tool_rail.pack_propagate(False)
        self.passwords_button = ttk.Button(
            self.actions_tool_rail,
            text="Passwords",
            command=self._toggle_password_actions,
            style="Compact.TButton",
        )
        self.passwords_button.pack(fill=tk.X)
        self._tooltip(
            self.passwords_button,
            "Passwords — Show only protected Windows Credential Manager actions. Activate again to show all actions.",
        )

        type_filter = ttk.Menubutton(
            self.actions_tool_rail,
            text="Types ▾",
            style="Compact.TButton",
        )
        type_filter.pack(fill=tk.X, pady=(5, 0))
        type_menu = tk.Menu(type_filter, tearoff=False)
        type_menu.add_radiobutton(
            label="All types",
            variable=self.action_type_filter_var,
            value="All types",
            command=lambda: self._select_action_type_filter(None),
        )
        type_menu.add_separator()
        for action_type, definition in ACTION_TYPES.items():
            type_menu.add_radiobutton(
                label=definition.label,
                variable=self.action_type_filter_var,
                value=definition.label,
                command=lambda selected=action_type: self._select_action_type_filter(selected),
            )
        type_filter.configure(menu=type_menu)
        self._tooltip(
            type_filter,
            "Types — Filter the action list by any built-in action type, or show all types.",
        )

        run_button = ttk.Button(
            self.actions_tool_rail,
            text="Run",
            command=self._execute_selected,
            style="Accent.TButton",
        )
        run_button.pack(fill=tk.X, pady=(12, 0))
        self._tooltip(run_button, "Execute the highlighted action. Its input and effect appear in Action info below.")
        search_help = ttk.Button(
            self.actions_tool_rail,
            text="?",
            width=3,
            command=self._show_help,
            style="Compact.TButton",
        )
        search_help.pack(fill=tk.X, pady=(5, 0))
        self._tooltip(
            search_help,
            "Search globally across technology, task, context, action name, type, and content.",
        )
        self.type_filter = type_filter
        self.run_button = run_button
        self.action_help_button = search_help

        actions_list_frame = ttk.Frame(results_body)
        actions_list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.actions_list_frame = actions_list_frame
        scrollbar = ttk.Scrollbar(actions_list_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.results_scrollbar = scrollbar
        self.results = tk.Listbox(
            actions_list_frame,
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
        self.focus_tree = ttk.Treeview(
            actions_list_frame,
            show="tree",
            selectmode="browse",
        )
        self.focus_tree.bind("<<TreeviewSelect>>", lambda _event: self._update_preview())
        self.focus_tree.bind("<Double-Button-1>", lambda _event: self._execute_selected())
        self.focus_tree.bind("<Return>", lambda _event: self._execute_selected())
        self.focus_tree_tooltip = TreeviewItemTooltip(
            self.focus_tree,
            self._focus_tree_tooltip_text,
        )

        self.command_surface_panel = ttk.Frame(results_area, padding=(6, 0, 0, 0))
        results_area.add(self.command_surface_panel, weight=2)
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
        self.action_console = results_area
        self.actions_panel = results_frame
        self.action_console_ratio = 0.44
        self.action_console.bind("<Configure>", self._resize_action_console)
        self.action_console.bind("<ButtonRelease-1>", self._remember_action_console_split)
        self.root.after_idle(self._set_initial_action_console_split)

    def _set_initial_action_console_split(self) -> None:
        self.root.update_idletasks()
        available_width = self.action_console.winfo_width()
        if available_width <= 1:
            self.root.after(10, self._set_initial_action_console_split)
            return
        self.action_console.sashpos(
            0,
            bounded_sash_position(
                available_width,
                self.action_console_ratio,
                MINIMUM_ACTIONS_WIDTH,
                MINIMUM_QUICK_ACTIONS_WIDTH,
            ),
        )

    def _resize_action_console(self, event: tk.Event) -> None:
        if event.width > 1:
            self.action_console.sashpos(
                0,
                bounded_sash_position(
                    event.width,
                    self.action_console_ratio,
                    MINIMUM_ACTIONS_WIDTH,
                    MINIMUM_QUICK_ACTIONS_WIDTH,
                ),
            )

    def _remember_action_console_split(self, _event: tk.Event) -> None:
        available_width = self.action_console.winfo_width()
        if available_width > 1:
            position = bounded_sash_position(
                available_width,
                self.action_console.sashpos(0) / available_width,
                MINIMUM_ACTIONS_WIDTH,
                MINIMUM_QUICK_ACTIONS_WIDTH,
            )
            self.action_console.sashpos(0, position)
            self.action_console_ratio = position / available_width

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
        self.workspace_panel.pack(fill=tk.BOTH, expand=True)
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
        workspace_body.pack(fill=tk.BOTH, expand=True)
        self.workspace = tk.Text(
            workspace_body,
            height=8,
            wrap=tk.WORD,
            undo=True,
            font=("Consolas", 10),
            borderwidth=1,
            relief=tk.SOLID,
            padx=7,
            pady=6,
        )
        self.workspace.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
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
        case_menu = tk.Menu(self.workspace_transform_menu, tearoff=False)
        case_menu.add_command(
            label="lowercase", command=lambda: self._transform_workspace("lowercase", "lowercase")
        )
        case_menu.add_command(
            label="UPPERCASE", command=lambda: self._transform_workspace("uppercase", "UPPERCASE")
        )
        case_menu.add_command(
            label="Proper Case",
            command=lambda: self._transform_workspace("proper_case", "Applied Proper Case"),
        )
        case_menu.add_command(
            label="Sentence case",
            command=lambda: self._transform_workspace("sentence_case", "Applied sentence case"),
        )
        case_menu.add_command(
            label="iNVERT cASE",
            command=lambda: self._transform_workspace("invert_case", "Inverted case"),
        )
        self.workspace_transform_menu.add_cascade(label="Case", menu=case_menu)

        whitespace_menu = tk.Menu(self.workspace_transform_menu, tearoff=False)
        whitespace_menu.add_command(
            label="Normalize consecutive spaces",
            command=lambda: self._transform_workspace("normalize_spaces", "Normalized spaces"),
        )
        whitespace_menu.add_command(
            label="Trim every line",
            command=lambda: self._transform_workspace("trim_lines", "Trimmed every line"),
        )
        self.workspace_transform_menu.add_cascade(
            label="Whitespace",
            menu=whitespace_menu,
        )

        lines_menu = tk.Menu(self.workspace_transform_menu, tearoff=False)
        lines_menu.add_command(
            label="Prefix / suffix every line…", command=self._prefix_suffix_workspace
        )
        lines_menu.add_command(
            label="Remove blank lines",
            command=lambda: self._transform_workspace("remove_blank_lines", "Removed blank lines"),
        )
        lines_menu.add_command(
            label="Sort lines A–Z",
            command=lambda: self._transform_workspace("sort_lines_ascending", "Sorted lines A–Z"),
        )
        lines_menu.add_command(
            label="Sort lines Z–A",
            command=lambda: self._transform_workspace("sort_lines_descending", "Sorted lines Z–A"),
        )
        lines_menu.add_command(
            label="Join lines with spaces",
            command=lambda: self._transform_workspace("join_lines", "Joined lines"),
        )
        lines_menu.add_command(
            label="Format as SQL value list",
            command=lambda: self._transform_workspace(
                "sql_values",
                "Formatted SQL value list",
            ),
        )
        lines_menu.add_command(
            label="Remove consecutive duplicate lines",
            command=lambda: self._transform_workspace(
                "remove_consecutive_duplicate_lines",
                "Removed consecutive duplicate lines",
            ),
        )
        lines_menu.add_command(
            label="Remove duplicate lines",
            command=lambda: self._transform_workspace("remove_duplicate_lines", "Removed duplicate lines"),
        )
        self.workspace_transform_menu.add_cascade(label="Lines", menu=lines_menu)
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

        status_label = ttk.Label(
            outer,
            textvariable=self.status_var,
            style="Status.TLabel",
            anchor=tk.W,
        )
        status_label.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0), anchor=tk.W)
        self._tooltip(status_label, self._status_tooltip_text)
        status_label.bind("<Button-1>", lambda _event: self._show_action_info_dialog())

        controls = ttk.Frame(outer)
        controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        for column in range(8):
            controls.columnconfigure(column, weight=1, uniform="controls")

        button_specs = (
            ("+", "Capture — Save current clipboard text to Inbox after asking for a title.", self._capture_clipboard),
            ("▣", "Inbox — Review captures and convert them into structured Draft actions.", self._show_inbox),
            ("✎", "Edit — Edit the selected Draft copy-text action. Other action types are currently read-only.", self._edit_selected),
            ("⌖", "Pin — Pin or unpin the selected action in stable slots 1–5.", self._toggle_selected_pin),
            ("✓", "Trust — Mark the selected reviewed Draft action as Trusted after confirmation.", self._mark_selected_trusted),
            ("?", "Help — Open the complete local Context Palette help document.", self._show_help),
            ("−", "Hide — Hide the palette but keep it resident. Reopen with Ctrl+Alt+P.", self.hide_window),
            ("×", "Quit — Stop Context Palette completely and release Ctrl+Alt+P.", self.quit_app),
        )
        for column, (symbol, tooltip, command) in enumerate(button_specs):
            control = ttk.Button(
                controls,
                text=symbol,
                width=3,
                command=command,
                style="Icon.TButton",
            )
            control.grid(
                row=0,
                column=column,
                sticky=tk.EW,
                padx=(0 if column == 0 else 2, 0 if column == 7 else 2),
            )
            self._tooltip(control, tooltip)

    def _tooltip(self, widget: tk.Widget, text: str | Callable[[], str]) -> None:
        self.widget_tooltips.append(WidgetTooltip(widget, text))

    def _command_surface_tooltip(
        self,
        widget: tk.Widget,
        text: str | Callable[[], str],
    ) -> None:
        self.command_surface_tooltips.append(WidgetTooltip(widget, text))

    def _bind_surface_menu_control(
        self,
        control: tk.Widget,
        *,
        on_click: Callable[[tk.Event], object],
        on_menu: Callable[[tk.Event], object],
        on_keyboard: Callable[[tk.Event], object],
    ) -> None:
        """Apply the shared mouse and keyboard contract for Quick-action menus."""
        control.bind("<Button-1>", on_click, add="+")
        control.bind("<Button-3>", on_menu, add="+")
        control.bind("<Return>", on_keyboard, add="+")
        control.bind("<space>", on_keyboard, add="+")

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
        configure_standard_window(window)
        outer = ttk.Frame(window, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)
        close_button = ttk.Button(outer, text="Close", command=window.destroy)
        close_button.pack(side=tk.BOTTOM, anchor=tk.E, pady=(8, 0))
        text = tk.Text(outer, wrap=tk.WORD, font=("Segoe UI", 10), padx=8, pady=8)
        text.pack(fill=tk.BOTH, expand=True)
        text.insert("1.0", self._status_tooltip_text())
        text.configure(state=tk.DISABLED)
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
            contexts = {
                value.casefold(): value
                for value in self.available_context_names
            }
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
        work_width = values[4] - values[2]
        work_height = values[5] - values[3]
        fitted_width = min(width, work_width)
        fitted_height = min(height, work_height)
        if (fitted_width, fitted_height) != (width, height):
            minimum_width, minimum_height = self.root.minsize()
            self.root.minsize(
                min(minimum_width, fitted_width),
                min(minimum_height, fitted_height),
            )
            self.root.geometry(f"{fitted_width}x{fitted_height}")
            self.root.update_idletasks()
            width, height = fitted_width, fitted_height
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

    def _load_command_surface(self, *, render: bool = True) -> None:
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
        if render:
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
        button_count = 1 + len(credential_actions) + sum(
            len(group.items) for group in self.command_groups
        )
        self.surface_count_var.set(
            f"{button_count} button" if button_count == 1 else f"{button_count} buttons"
        )
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
        self._render_knowledge_quick_action(group_row_offset)
        group_row_offset += 1
        for index, group in enumerate(self.command_groups):
            row, column = divmod(index, 2)
            row += group_row_offset
            area = ttk.LabelFrame(self.command_tiles_frame, text=group.label, padding=4)
            area.grid(row=row, column=column, sticky=tk.NSEW, padx=2, pady=2)
            area.columnconfigure(0, weight=1)
            for item_index, item in enumerate(group.items):
                control = ttk.Label(
                    area,
                    text=item.label,
                    style="SurfaceMenu.TLabel",
                    anchor=tk.W,
                    relief=tk.SOLID,
                    cursor="hand2",
                    takefocus=True,
                )
                control.grid(
                    row=item_index,
                    column=0,
                    sticky=tk.EW,
                    padx=1,
                    pady=1,
                )
                self._command_surface_tooltip(
                    control,
                    "Left-click or Enter runs the primary action. Right-click chooses an action. Shift/Ctrl+click edits configuration.",
                )
                self._bind_surface_menu_control(
                    control,
                    on_click=lambda event, selected_group=group, selected_item=item: self._handle_command_item_left_click(
                        event,
                        selected_group,
                        selected_item,
                    ),
                    on_menu=lambda event, selected_item=item: self._show_item_menu(
                        event, selected_item
                    ),
                    on_keyboard=lambda _event, selected_item=item: self._execute_item_primary(
                        selected_item
                    ),
                )

    def _render_knowledge_quick_action(self, row: int) -> None:
        knowledge_area = ttk.LabelFrame(
            self.command_tiles_frame,
            text="Knowledge",
            padding=4,
        )
        knowledge_area.grid(
            row=row,
            column=0,
            columnspan=2,
            sticky=tk.NSEW,
            padx=2,
            pady=2,
        )
        knowledge_area.columnconfigure(0, weight=1)
        sheets_control = ttk.Label(
            knowledge_area,
            text="Sheets ▾",
            style="SurfaceMenu.TLabel",
            anchor=tk.W,
            relief=tk.SOLID,
            cursor="hand2",
            takefocus=True,
        )
        sheets_control.grid(row=0, column=0, sticky=tk.EW, padx=1, pady=1)
        self._command_surface_tooltip(
            sheets_control,
            "Sheets — Open searchable local cheat sheets. Right-click for the available command.",
        )
        self._bind_surface_menu_control(
            sheets_control,
            on_click=lambda _event: self._execute_builtin_quick_command(
                BUILTIN_QUICK_COMMAND_OPEN_SHEETS
            ),
            on_menu=lambda event: self._show_builtin_quick_menu(
                event,
                BUILTIN_QUICK_COMMAND_OPEN_SHEETS,
            ),
            on_keyboard=lambda _event: self._execute_builtin_quick_command(
                BUILTIN_QUICK_COMMAND_OPEN_SHEETS
            ),
        )

    def _execute_builtin_quick_command(self, command_id: str) -> None:
        execute_builtin_quick_command(command_id, open_sheets=self._show_cheatsheets)

    def _show_builtin_quick_menu(self, event: tk.Event, command_id: str) -> str:
        if command_id not in BUILTIN_QUICK_COMMANDS:
            raise ValueError(f"Unknown built-in quick command: {command_id}")
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(
            label="Open Sheets",
            command=lambda: self._execute_builtin_quick_command(command_id),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

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

    def _load_palette_state(self, *, render: bool = True) -> None:
        try:
            loaded_state = load_palette_state(self.palette_path)
        except ActionError as exc:
            self.status_var.set(
                "Palette settings could not be loaded; kept previous pins, Focus, and slots."
            )
            messagebox.showerror(
                "Palette settings could not be loaded",
                f"{exc}\n\nPrevious pins, Focus, and context slots remain active.",
                parent=self.root,
            )
            LOGGER.exception("Palette configuration failed to load")
        else:
            self.palette_state = loaded_state
        resolved = resolve_focus_state(
            self.actions,
            self.context_definitions,
            self.palette_state,
        )
        self.palette_state = resolved.palette_state
        self.available_context_names = list(resolved.available_names)
        self.context_var.set(self.palette_state.focus_context)
        self._refresh_focus_controls()
        if render:
            self._render_command_surface()

    def _refresh_focus_controls(self) -> None:
        context = self.context_var.get().strip() or "General"
        self.focus_launcher_var.set(f"{context} ▾")
        self.manage_focus_var.set("Manage focus ▾")
        self.context_menu.delete(0, tk.END)
        for name in self.available_context_names:
            self.context_menu.add_radiobutton(
                label=name,
                variable=self.context_var,
                value=name,
                command=self._change_focus_context,
            )
        if self.available_context_names:
            self.context_menu.add_separator()
        self.context_menu.add_command(
            label="Manage focuses…",
            command=self._show_focus_configuration,
        )

    def _change_focus_context(self) -> None:
        context = self.context_var.get().strip() or "General"
        previous_state = self.palette_state
        if getattr(self, "results_view", "flat") == "focus":
            self._remember_focus_tree_expansion(previous_state.focus_context)
        updated_state = PaletteState(
            self.palette_state.pinned_action_ids,
            context,
            self.palette_state.context_slots,
        )
        try:
            save_palette_state(self.palette_path, updated_state)
        except OSError as exc:
            self.context_var.set(previous_state.focus_context)
            if hasattr(self, "context_menu"):
                self._refresh_focus_controls()
            self.status_var.set("Focus context was not changed because it could not be saved.")
            messagebox.showerror(
                "Context Palette",
                f"Could not save the focus context.\n\n{exc}",
            )
            return
        self.palette_state = updated_state
        if hasattr(self, "context_menu"):
            self._refresh_focus_controls()
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
        self.focus_tree_tooltip.hide()
        if (
            self.focus_actions_mode
            and not self.search_var.get().strip()
            and self.action_type_filter is None
        ):
            self._render_focus_actions()
            _warn_if_slow(
                "result refresh",
                started_at,
                SLOW_RESULT_REFRESH_SECONDS,
                action_count=len(self.actions),
            )
            return
        self._show_flat_results()
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
            if self.action_type_filter is not None:
                type_label = ACTION_TYPES[self.action_type_filter].label
                empty_message = (
                    f'No {type_label} actions match “{query}”.\n'
                    "Clear Find or choose another type."
                    if query
                    else f"No {type_label} actions yet.\nUse Configure to create one."
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
            if self.action_type_filter is not None:
                type_label = ACTION_TYPES[self.action_type_filter].label
                self.status_var.set(
                    f"No matching {type_label} action. Clear Find or choose another type."
                )
            else:
                self.status_var.set("No matching action. Clear Find or create one in Configure.")
        else:
            if self.action_type_filter is not None:
                type_label = ACTION_TYPES[self.action_type_filter].label
                label = f"{type_label} action" if count == 1 else f"{type_label} actions"
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

    def _show_flat_results(self) -> None:
        if self.results_view == "flat":
            return
        self._remember_focus_tree_expansion()
        self.focus_tree.pack_forget()
        self.results.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.results_scrollbar.configure(command=self.results.yview)
        self.results_view = "flat"
        self.actions_heading_var.set("Actions")

    def _show_focus_tree(self) -> None:
        if self.results_view == "focus":
            return
        self.results.pack_forget()
        self.focus_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.results_scrollbar.configure(command=self.focus_tree.yview)
        self.focus_tree.configure(yscrollcommand=self.results_scrollbar.set)
        self.results_view = "focus"

    def _remember_focus_tree_expansion(self, context: str | None = None) -> None:
        if self.results_view != "focus":
            return
        expanded: set[tuple[str, ...]] = set()
        for technology_id in self.focus_tree.get_children():
            technology = self.focus_tree.item(technology_id, "text")
            if self.focus_tree.item(technology_id, "open"):
                expanded.add((technology,))
            for task_id in self.focus_tree.get_children(technology_id):
                task = self.focus_tree.item(task_id, "text")
                if self.focus_tree.item(task_id, "open"):
                    expanded.add((technology, task))
        owner = (
            context
            or getattr(self, "focus_tree_context", None)
            or self.palette_state.focus_context
        )
        key = owner.casefold()
        self.focus_tree_expansion[key] = expanded

    def _render_focus_actions(self) -> None:
        if self.results_view == "focus":
            self._remember_focus_tree_expansion(
                getattr(self, "focus_tree_context", None)
            )
        self._show_focus_tree()
        self.focus_tree.delete(*self.focus_tree.get_children())
        self.focus_tree_actions.clear()
        hierarchy = focus_action_hierarchy(
            self.actions,
            self.palette_state.focus_context,
        )
        stored_expansion = self.focus_tree_expansion.get(
            self.palette_state.focus_context.casefold()
        )
        expanded = stored_expansion if stored_expansion is not None else set()
        count = 0
        for technology_index, (technology, tasks) in enumerate(hierarchy):
            technology_id = f"technology:{technology_index}"
            self.focus_tree.insert(
                "",
                tk.END,
                iid=technology_id,
                text=technology,
                open=(technology,) in expanded,
            )
            for task_index, (task, actions) in enumerate(tasks):
                task_id = f"task:{technology_index}:{task_index}"
                self.focus_tree.insert(
                    technology_id,
                    tk.END,
                    iid=task_id,
                    text=task,
                    open=(technology, task) in expanded,
                )
                for action_index, action in enumerate(actions):
                    item_id = f"action:{technology_index}:{task_index}:{action_index}:{action.id}"
                    self.focus_tree.insert(task_id, tk.END, iid=item_id, text=action.title)
                    self.focus_tree_actions[item_id] = action
                    count += 1
        context = self.palette_state.focus_context
        self.focus_tree_context = context
        self.actions_heading_var.set(f"Focus actions — {context}")
        self.results_count_var.set(f"{count} action" if count == 1 else f"{count} actions")
        if count:
            first_technology = self.focus_tree.get_children()[0]
            first_task = self.focus_tree.get_children(first_technology)[0]
            if stored_expansion is None:
                self.focus_tree.item(first_technology, open=True)
                self.focus_tree.item(first_task, open=True)
            initial_item = self._first_visible_focus_tree_item()
            self.focus_tree.selection_set(initial_item)
            self.focus_tree.focus(initial_item)
            self.status_var.set(
                f"{count} actions explicitly assigned to {context}. Find remains global."
            )
        else:
            self.status_var.set(
                f"No actions are explicitly assigned to {context}. Find searches all actions."
            )
        self._update_preview()

    def _first_visible_focus_tree_item(self) -> str:
        """Return a visible leaf, or a visible non-executable branch as fallback."""
        technologies = self.focus_tree.get_children()
        for technology_id in technologies:
            if not self.focus_tree.item(technology_id, "open"):
                continue
            for task_id in self.focus_tree.get_children(technology_id):
                if not self.focus_tree.item(task_id, "open"):
                    continue
                actions = self.focus_tree.get_children(task_id)
                if actions:
                    return actions[0]
        first_technology = technologies[0]
        if self.focus_tree.item(first_technology, "open"):
            tasks = self.focus_tree.get_children(first_technology)
            if tasks:
                return tasks[0]
        return first_technology

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
        stage_timings_ms: dict[str, float] = {}

        def run_stage(name: str, callback: Callable[[], None]) -> None:
            stage_started_at = time.perf_counter()
            callback()
            stage_timings_ms[name] = (
                time.perf_counter() - stage_started_at
            ) * 1000

        self.status_var.set("Refreshing actions, contexts, and buttons…")
        self.root.configure(cursor="wait")
        self.root.update_idletasks()
        try:
            run_stage("actions", self._load_actions)
            run_stage(
                "buttons",
                lambda: self._load_command_surface(render=False),
            )
            run_stage("contexts", self._load_contexts)
            run_stage(
                "palette",
                lambda: self._load_palette_state(render=False),
            )
            run_stage("quick_actions", self._render_command_surface)
            run_stage("results", self._refresh_results)
            run_stage(
                "signature",
                lambda: setattr(
                    self,
                    "configuration_signature_cache",
                    self._configuration_signature(),
                ),
            )
        finally:
            self.root.configure(cursor="")
            _warn_if_slow(
                "configuration reload",
                started_at,
                SLOW_CONFIGURATION_RELOAD_SECONDS,
                action_count=len(self.actions),
                stage_timings_ms=stage_timings_ms,
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
        if self.results_view == "focus":
            selected = self.focus_tree.selection()
            return self.focus_tree_actions.get(selected[0]) if selected else None
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

    def _focus_tree_tooltip_text(self, item_id: str) -> str:
        action = self.focus_tree_actions.get(item_id)
        if action is None:
            return ""
        return (
            f"{action.title}\n"
            f"Context: {action.context or 'General'}\n"
            f"Type: {ACTION_TYPES[action.type].label}\n"
            f"State: {action.state}"
        )

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
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update()
        self.protected_clipboard_sequence = None

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

    def _show_configuration(self, *, initial_tab: str = "actions") -> None:
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
            initial_tab=initial_tab,
        )

    def _show_focus_configuration(self) -> None:
        self._show_configuration(initial_tab="contexts")

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
            if self.results_view == "focus" and event.widget == self.focus_tree:
                return None
            return self._move_selection(navigation[keysym], event)
        if keysym == "Home":
            if self.results_view == "focus" and event.widget == self.focus_tree:
                return None
            return self._select_index(0, event)
        if keysym == "End":
            if self.results_view == "focus" and event.widget == self.focus_tree:
                return None
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
        configure_standard_window(self.window)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(outer)
        controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        self.convert_button = ttk.Button(
            controls,
            text="Convert to Draft Action",
            command=self._convert_selected,
            style="Accent.TButton",
        )
        self.convert_button.pack(side=tk.LEFT)
        self.ai_button = ttk.Button(controls, text="Ask AI", command=self._ask_ai_for_selected)
        self.ai_button.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            controls,
            text="Close",
            command=self.window.destroy,
            style="Compact.TButton",
        ).pack(side=tk.RIGHT)

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
        configure_standard_window(self.window)
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
        configure_standard_window(self.window)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(outer)
        controls.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(controls, text="Save", command=self._save).pack(side=tk.LEFT)
        ttk.Button(controls, text="Cancel", command=self.window.destroy).pack(side=tk.RIGHT)

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

    def _save(self) -> None:
        self.on_save(
            self.action,
            self.title_var.get(),
            self.context_var.get(),
            self.text.get("1.0", tk.END),
        )
        self.window.destroy()


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
