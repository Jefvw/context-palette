from __future__ import annotations

from pathlib import Path
import ctypes
import logging
import queue
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

from .actions import (
    ACTION_BOUND_QUICK_MENU_SPECS,
    Action,
    ActionError,
    action_search_rank,
    execute_action,
    load_combined_actions,
    load_actions,
    open_action_target,
    search_actions,
)
from .action_preview import (
    build_action_preview,
    compact_preview_value,
    format_preview_summary,
)
from .action_bound_quick_actions import action_bound_quick_groups
from .action_discovery_panel import (
    ActionDiscoveryPanel,
    DISCOVERY_ACTIONS,
    DISCOVERY_ALL,
    DISCOVERY_SCOPES,
    DISCOVERY_WORK_ITEMS,
    CONTEXT_SCOPE_EVERYWHERE,
    CONTEXT_SCOPE_THIS,
    FOCUS_GROUP_ROW_TAG,
    FOCUS_SLOT_ROW_TAG,
    slot_row_tag,
)
from .action_types import ACTION_TYPES
from .action_suggestions import (
    ActionCreationSuggestion,
    suggest_action_from_text,
)
from .action_sequences import (
    ActionSequenceError,
    ResolvedActionStep,
    ResolvedWaitStep,
    SequenceRunPlan,
    resolve_sequence_steps,
)
from .cheat_sheet_window import CheatSheetWindow
from .cheatsheets import CheatSheetError, load_cheatsheets
from .command_surface import (
    CommandGroup,
    CommandItem,
    CommandTarget,
    CommandSurfaceError,
    GROUP_PRESENTATION_NESTED_MENU,
    MAX_COMMAND_MENU_LEVELS,
    command_group_action_ids,
    command_group_launcher_count,
    command_item_at_path,
    command_item_id_path,
    command_item_targets,
    load_combined_command_groups,
)
from .configuration_window import ConfigurationWindow
from .context_membership import (
    actions_with_canonical_contexts,
    migrate_legacy_action_contexts,
)
from .focus_model import resolve_focus_state
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
from .harvest_window import HarvestWindow
from .contexts import ContextDefinition, ContextError, load_combined_contexts
from .data_catalog import AppDataPaths
from .drop_adapter import DropResult
from .drop_target_window import DropTargetWindow
from .inbox import InboxError, append_inbox_item, create_clipboard_item, load_inbox_items
from .inbox_window import ActionCreator, InboxWindow, suggest_url_template
from .ocr import (
    OcrCoordinator,
    OcrError,
    OcrResult,
    OcrSourceError,
    OcrUnavailableError,
    clipboard_image_source,
    image_source_from_path,
    image_source_from_text,
)
from .single_instance import SingleInstanceServer
from .style import COLORS, configure_theme
from .tooltips import WidgetTooltip
from .window_geometry import configure_main_window, configure_standard_window
from .palette_state import (
    PaletteState,
    action_slots,
    load_palette_state,
    palette_item_slots,
    save_palette_state,
    slot_display_number,
)
from .palette_items import PaletteItemReference
from .windows_credentials import (
    ClipboardTextSnapshot,
    CredentialAccessError,
    begin_protected_clipboard_transaction,
    read_windows_credential,
    restore_clipboard_text_if_unchanged,
)
from .workspace_panel import WorkspacePanel
from .work_item_refresh import WorkItemIndex, WorkItemRefreshCoordinator
from .work_item_file_copy import (
    WorkItemFileCopyCoordinator,
    WorkItemFileCopyError,
    WorkItemFileCopyResult,
    file_path_from_workspace,
)
from .work_item_inbox import (
    WorkItemInboxCoordinator,
    WorkItemInboxError,
    WorkItemInboxResult,
    create_work_item_inbox_entry,
)
from .work_item_storage import (
    WorkItemMetadata,
    WorkItemStorageError,
    load_work_item_creation_settings,
    load_work_item_metadata,
    load_work_item_sources,
    work_item_metadata_key,
)
from .work_items import (
    DiscoveredWorkItem,
    WorkItemReference,
    WorkItemSource,
    work_item_matches,
    work_item_search_rank,
)

LOGGER = logging.getLogger("context_palette.launcher")
LOGGER.addHandler(logging.NullHandler())
DOCUMENTATION_DIR = Path(__file__).resolve().parents[2] / "docs"


def _log_automatic_paste(
    category: str,
    outcome: str,
    reason: str,
    *,
    level: int = logging.INFO,
) -> None:
    """Record paste control flow without action, clipboard, or window content."""
    LOGGER.log(
        level,
        "Automatic paste: category=%s outcome=%s reason=%s",
        category,
        outcome,
        reason,
    )

SLOW_RESULT_REFRESH_SECONDS = 0.100
SLOW_CONFIGURATION_RELOAD_SECONDS = 0.500
MINIMUM_COMMAND_CONSOLE_WIDTH = 280
MINIMUM_WORKSPACE_WIDTH = 350
TWO_COLUMN_QUICK_ACTIONS_WIDTH = 250
STANDARD_QUICK_GROUP_ID = "standard"
ACTION_BOUND_QUICK_ADD_LABELS = {
    "paste_credential": "Add credential shortcut…",
    "open_folder": "Add folder shortcut…",
    "ai_prompt": "Add prompt…",
}
ACTION_BOUND_QUICK_NOUNS = {
    "paste_credential": "credential",
    "open_folder": "folder",
    "ai_prompt": "prompt",
}


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


def quick_action_column_count(available_width: int) -> int:
    """Use two Quick-action columns only when both remain comfortably readable."""

    return 2 if available_width >= TWO_COLUMN_QUICK_ACTIONS_WIDTH else 1


def ordered_configured_quick_groups(
    groups: list[CommandGroup],
    local_command_surface_path: Path,
) -> list[CommandGroup]:
    """Put personal configured menus before shared configured menus.

    The loader records each group's owning file in ``source_path``.  Partitioning
    by that existing ownership keeps the configured order within each file,
    requires no persisted setting, and leaves groups without source metadata in
    the shared/system partition.
    """

    local_path = local_command_surface_path.resolve()
    personal: list[CommandGroup] = []
    shared: list[CommandGroup] = []
    for group in groups:
        if group.source_path is not None and group.source_path.resolve() == local_path:
            personal.append(group)
        else:
            shared.append(group)
    return [*personal, *shared]


def quick_group_top_level_choice_count(group: CommandGroup) -> int:
    """Return the persisted choices presented at the root of one menu."""

    return len(command_group_action_ids(group)) + len(group.items)


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
        *,
        data_paths: AppDataPaths | None = None,
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
        self.data_paths = data_paths or AppDataPaths.from_data_directory(
            actions_path.parent
        )
        self._configuration_recovery_required = False
        self.local_work_item_sources_path = self.data_paths.work_item_sources_file
        self.local_work_item_metadata_path = self.data_paths.work_item_metadata_file
        self.local_work_item_settings_path = self.data_paths.work_item_settings_file
        self.work_item_sources: tuple[WorkItemSource, ...] = ()
        self.work_item_metadata: dict[str, WorkItemMetadata] = {}
        self.work_item_index = WorkItemIndex()
        self.work_item_refresh = WorkItemRefreshCoordinator()
        self.work_item_file_copy = WorkItemFileCopyCoordinator()
        self.work_item_inbox = WorkItemInboxCoordinator()
        self.ocr = OcrCoordinator()
        self.ocr_after_id: str | None = None
        self.work_item_refresh_pending = False
        self.discovery_scope = DISCOVERY_ALL
        self.work_items_mode = False
        self.displayed_work_items: list[DiscoveredWorkItem] = []
        self.work_project_filter: str | None = None
        self.work_tag_filter: str | None = None
        self.actions: list[Action] = []
        self.filtered_actions: list[Action] = []
        self.displayed_actions: list[Action] = []
        self.displayed_slots: list[int | None] = []
        self.displayed_action_rows: list[tuple[Action | None, int | None]] = []
        self.slot_actions: dict[int, Action] = {}
        self.slot_items: dict[int, PaletteItemReference] = {}
        self.palette_state = PaletteState()
        self.show_requests: queue.Queue[dict[str, str]] = queue.Queue()
        self.instance_server = SingleInstanceServer(self.show_requests.put, instance_port)
        self.hotkey = GlobalHotkey(self._queue_hotkey_request)
        self.captured_selection: str | None = None
        self.source_foreground_handle: int | None = None
        self.protected_clipboard_sequence: int | None = None
        self.protected_clipboard_snapshot: ClipboardTextSnapshot | None = None
        self.sequence_run_plan: SequenceRunPlan | None = None
        self.sequence_run_index = 0
        self.sequence_started_actions = 0
        self.sequence_after_id: str | None = None
        self.hotkey_available = False
        self.hide_after_id: str | None = None
        self.search_entry: ttk.Entry | None = None
        self.search_refresh_after_id: str | None = None
        self.action_type_filter: str | None = None
        self.action_tag_filter: str | None = None
        self.work_items_mode = False
        self.work_project_filter = None
        self.work_tag_filter = None
        self.item_tag_filter: str | None = None
        self.context_scope = CONTEXT_SCOPE_EVERYWHERE
        self.focus_tree_actions: dict[str, Action] = {}
        self.focus_tree_items: dict[str, PaletteItemReference] = {}
        self.focus_tree_context: str | None = None
        self.results_view = "flat"
        self.passwords_button: ttk.Button | None = None
        self.action_type_filter_var = tk.StringVar(value="All types")
        self.action_tag_filter_var = tk.StringVar(value="All tags")
        self.item_tag_filter_var = tk.StringVar(value="All tags")
        self.context_scope_var = tk.StringVar(value="Everywhere")
        self.work_project_filter_var = tk.StringVar(value="All project codes")
        self.work_tag_filter_var = tk.StringVar(value="All work tags")
        self.configuration_signature_cache: tuple[tuple[str, int, int], ...] = ()
        self.search_var = tk.StringVar()
        self.context_var = tk.StringVar(value="General")
        self.focus_launcher_var = tk.StringVar(value="Context: All contexts")
        self.actions_heading_var = tk.StringVar(value="Actions")
        self.results_count_var = tk.StringVar(value="0 actions")
        self.surface_count_var = tk.StringVar(value="0 buttons")
        self.widget_tooltips: list[WidgetTooltip] = []
        self.command_surface_tooltips: list[WidgetTooltip] = []
        self.command_surface_columns = 1
        self.configuration_window: ConfigurationWindow | None = None
        self.drop_target_window: DropTargetWindow | None = None
        self.action_info_full = (
            "Select an Action or Work Item to see what it will do."
        )
        self.status_var = tk.StringVar(value="Ready")
        self.search_var.trace_add("write", lambda *_args: self._schedule_refresh_results())

        self._build_ui()
        self._migrate_context_memberships()
        self._load_actions()
        self._load_command_surface(render=False)
        self._load_contexts()
        self._load_palette_state(render=False)
        self._load_work_item_configuration()
        self._render_command_surface()
        self._refresh_results()
        self.configuration_signature_cache = self._configuration_signature()
        if not self.instance_server.start():
            self.root.after(0, self.root.destroy)
            return
        self.drop_target_window = DropTargetWindow(
            self.root,
            self._accept_drop_result,
        )
        self.root.after_idle(self._start_drop_target)
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
        self._poll_work_item_refresh()
        self._poll_work_item_file_copy()
        self._poll_work_item_inbox()
        self._start_work_item_refresh()
        self._audit_tooltips()

    def _migrate_context_memberships(self) -> None:
        try:
            report = migrate_legacy_action_contexts(
                shared_actions_path=self.actions_path,
                local_actions_path=self.local_actions_path,
                shared_contexts_path=self.contexts_path,
                local_contexts_path=self.local_contexts_path,
                palette_path=self.palette_path,
            )
        except (ActionError, ContextError, OSError) as exc:
            LOGGER.exception("Context membership migration failed")
            messagebox.showwarning(
                "Context memberships could not be synchronized",
                "Context Palette could not complete the one-time context "
                "membership migration. Existing files were kept or restored.\n\n"
                f"{exc}",
                parent=self.root,
            )
            return
        if report.incompatible_memberships_skipped:
            messagebox.showwarning(
                "Some context memberships need attention",
                f"{report.incompatible_memberships_skipped} personal action "
                "membership(s) pointed to a Built-in context and could not be "
                "copied into the tracked configuration. Assign those actions "
                "to a My configuration context in Configure.",
                parent=self.root,
            )

    def _build_ui(self) -> None:
        self.root.title("Context Palette")
        configure_main_window(self.root)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        self.root.bind("<FocusOut>", self._schedule_hide_when_inactive)
        self.root.bind("<FocusIn>", self._cancel_scheduled_hide)

        configure_theme(self.root)

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        self._bind_main_shortcuts()

        content = ttk.Panedwindow(outer, orient=tk.HORIZONTAL)
        command_console = ttk.Frame(content, padding=(0, 0, 6, 0))
        workspace_container = ttk.Frame(content, padding=(6, 0, 0, 0))
        content.add(command_console, weight=2)
        content.add(workspace_container, weight=3)
        self._build_results_area(command_console)
        self._build_workspace(workspace_container)
        content.pack(fill=tk.BOTH, expand=True)
        self.main_content = content
        self.command_console = command_console
        self.results_container = command_console
        self.workspace_container = workspace_container
        self.main_split_ratio = 0.40
        self.main_split_customized = False
        self.main_content.bind("<Configure>", self._resize_main_split)
        self.main_content.bind("<ButtonRelease-1>", self._remember_main_split)
        self.root.after_idle(self._set_initial_main_split)

    def _set_initial_main_split(self) -> None:
        self.root.update_idletasks()
        available_width = self.main_content.winfo_width()
        if available_width <= 1:
            return
        self.main_split_customized = False
        self._sync_main_split(available_width)

    def _resize_main_split(self, event: tk.Event) -> None:
        if event.width > 1:
            self._sync_main_split(event.width)

    def _sync_main_split(self, available_width: int | None = None) -> None:
        width = available_width or self.main_content.winfo_width()
        if width <= 1:
            return
        self.main_content.sashpos(
            0,
            bounded_sash_position(
                width,
                self.main_split_ratio,
                MINIMUM_COMMAND_CONSOLE_WIDTH,
                MINIMUM_WORKSPACE_WIDTH,
            ),
        )

    def _remember_main_split(self, _event: tk.Event) -> None:
        available_width = self.main_content.winfo_width()
        if available_width > 1:
            position = bounded_sash_position(
                available_width,
                self.main_content.sashpos(0) / available_width,
                MINIMUM_COMMAND_CONSOLE_WIDTH,
                MINIMUM_WORKSPACE_WIDTH,
            )
            self.main_content.sashpos(0, position)
            self.main_split_ratio = position / available_width
            self.main_split_customized = True

    def _select_context_scope(self, scope: str) -> None:
        if scope not in {CONTEXT_SCOPE_EVERYWHERE, CONTEXT_SCOPE_THIS}:
            raise ValueError(f"Unsupported context scope: {scope}")
        if (
            scope == CONTEXT_SCOPE_THIS
            and self.palette_state.focus_context.casefold() == "general"
        ):
            scope = CONTEXT_SCOPE_EVERYWHERE
            self.status_var.set(
                "Choose a specific Working context before limiting results to it."
            )
        self.context_scope = scope
        self._sync_context_scope_control()
        self._refresh_results()
        self.root.after_idle(self._focus_active_results)

    def _selected_result_context(self) -> str | None:
        if self.context_scope != CONTEXT_SCOPE_THIS:
            return None
        context = self.palette_state.focus_context
        return None if context.casefold() == "general" else context

    def _sync_context_scope_control(self) -> None:
        specific = self.palette_state.focus_context.casefold() != "general"
        if not specific and self.context_scope == CONTEXT_SCOPE_THIS:
            self.context_scope = CONTEXT_SCOPE_EVERYWHERE
        self.context_scope_var.set(
            "This context"
            if self.context_scope == CONTEXT_SCOPE_THIS
            else "Everywhere"
        )
        panel = getattr(self, "action_discovery_panel", None)
        if panel is None:
            return
        panel.context_scope_picker.configure(
            style=(
                "RailAccent.TButton"
                if self.context_scope == CONTEXT_SCOPE_THIS
                else "Compact.TButton"
            )
        )
        panel.context_scope_menu.entryconfigure(
            1,
            state=tk.NORMAL if specific else tk.DISABLED,
        )

    def _focus_active_results(self) -> None:
        """Move keyboard users into the result view they explicitly opened."""
        if self.results_view != "flat" and self.focus_tree.winfo_manager():
            self.focus_tree.focus_force()
        elif self.discovery_scope == DISCOVERY_WORK_ITEMS:
            self.results.focus_force()

    def _toggle_password_actions(self) -> None:
        if getattr(self, "discovery_scope", DISCOVERY_ACTIONS) != DISCOVERY_ACTIONS:
            self._select_discovery_scope(DISCOVERY_ACTIONS)
        selected = (
            None if self.action_type_filter == "paste_credential" else "paste_credential"
        )
        self._select_action_type_filter(selected)

    def _select_action_type_filter(self, action_type: str | None) -> None:
        self.action_type_filter = action_type
        self.action_type_filter_var.set(
            ACTION_TYPES[action_type].display_label
            if action_type is not None
            else "All types"
        )
        if self.passwords_button is not None:
            self.passwords_button.configure(
                style=(
                    "RailIconAccent.TButton"
                    if self.action_type_filter == "paste_credential"
                    else "RailIcon.TButton"
                )
            )
        self._sync_filter_indicators()
        self._refresh_results()

    def _select_tag_filter(self, tag: str | None) -> None:
        self._select_item_tag_filter(tag)

    def _select_item_tag_filter(self, tag: str | None) -> None:
        self.item_tag_filter = tag
        self.action_tag_filter = tag
        self.work_tag_filter = tag
        self.item_tag_filter_var.set(tag or "All tags")
        self.action_tag_filter_var.set(tag or "All tags")
        self.work_tag_filter_var.set(tag or "All work tags")
        self._sync_filter_indicators()
        self._refresh_results()

    def _toggle_work_items(self) -> None:
        self._select_discovery_scope(
            DISCOVERY_ACTIONS
            if self.discovery_scope == DISCOVERY_WORK_ITEMS
            else DISCOVERY_WORK_ITEMS
        )

    def _set_work_items_mode(self, enabled: bool) -> None:
        """Compatibility adapter for callers that still express a boolean mode."""

        self._select_discovery_scope(
            DISCOVERY_WORK_ITEMS if enabled else DISCOVERY_ACTIONS
        )

    def _select_discovery_scope(self, scope: str) -> None:
        if scope not in DISCOVERY_SCOPES:
            raise ValueError(f"Unsupported discovery scope: {scope}")
        self.discovery_scope = scope
        self.work_items_mode = scope == DISCOVERY_WORK_ITEMS
        if scope in {DISCOVERY_ALL, DISCOVERY_WORK_ITEMS}:
            work_item_sources = getattr(self, "work_item_sources", ())
            work_item_refresh = getattr(self, "work_item_refresh", None)
            if (
                work_item_sources
                and work_item_refresh is not None
                and not work_item_refresh.running
            ):
                self._start_work_item_refresh()
        self.action_discovery_panel.set_discovery_scope(
            scope,
            project_codes=self._available_work_project_codes(),
            tags=self._available_item_tags(),
        )
        self.action_discovery_panel.render_control_state(
            work_item=None,
            has_selection=False,
            sequence_running=getattr(self, "sequence_run_plan", None) is not None,
        )
        if not self.main_split_customized:
            self.root.after_idle(self._sync_main_split)
        self._sync_filter_indicators()
        self._refresh_results()
        self.root.after_idle(self._focus_active_results)

    def _select_work_project_filter(self, project_code: str | None) -> None:
        self.work_project_filter = project_code
        self.work_project_filter_var.set(project_code or "All project codes")
        self._sync_filter_indicators()
        self._refresh_results()

    def _select_work_tag_filter(self, tag: str | None) -> None:
        self._select_item_tag_filter(tag)

    def _sync_filter_indicators(self) -> None:
        panel = getattr(self, "action_discovery_panel", None)
        if panel is None:
            return
        scope = getattr(self, "discovery_scope", DISCOVERY_ACTIONS)
        action_type = self.action_type_filter
        action_type_label = (
            ACTION_TYPES[action_type].display_label
            if action_type is not None
            else None
        )
        saved_values: list[str] = []
        if scope != DISCOVERY_ACTIONS and action_type_label:
            saved_values.append(f"Actions: {action_type_label}")
        if scope != DISCOVERY_WORK_ITEMS and self.work_project_filter:
            saved_values.append(f"Work Items: {self.work_project_filter}")
        panel.set_filter_indicators(
            scope=scope,
            primary_value=(
                self.work_project_filter
                if scope == DISCOVERY_WORK_ITEMS
                else action_type_label
                if scope == DISCOVERY_ACTIONS
                else None
            ),
            tag_value=self.item_tag_filter,
            saved_values=tuple(saved_values),
        )

    def _build_results_area(self, outer: ttk.Frame) -> None:
        self.action_discovery_panel = ActionDiscoveryPanel(
            outer,
            heading_var=self.actions_heading_var,
            count_var=self.results_count_var,
            search_var=self.search_var,
            action_type_filter_var=self.action_type_filter_var,
            tag_filter_var=self.item_tag_filter_var,
            project_filter_var=self.work_project_filter_var,
            focus_launcher_var=self.focus_launcher_var,
            context_scope_var=self.context_scope_var,
            tooltip_adder=self._tooltip,
            keypress_handler=self._handle_keypress,
            execute_selected=self._execute_selected,
            update_preview=self._update_preview,
            toggle_password_actions=self._toggle_password_actions,
            select_context_scope=self._select_context_scope,
            select_scope=self._select_discovery_scope,
            create_action=self._show_action_creation,
            create_work_item=self._show_work_item_creation,
            send_work_item_inbox=self._send_workspace_to_work_item_inbox,
            copy_file_to_work_item=self._copy_workspace_file_to_work_item,
            select_action_type_filter=self._select_action_type_filter,
            select_tag_filter=self._select_item_tag_filter,
            select_project_filter=self._select_work_project_filter,
            capture=self._capture_clipboard,
            show_inbox=self._show_inbox,
            edit_item=self._edit_selected,
            configure=self._show_configuration,
            show_help=self._show_help,
            show_shortcuts=self._show_shortcuts,
            hide_window=self.hide_window,
            quit_app=self.quit_app,
            result_tooltip_text=self._result_tooltip_text,
            focus_tree_tooltip_text=self._focus_tree_tooltip_text,
            configure_flat_action=self._configure_flat_action_from_event,
            configure_focus_action=self._configure_focus_action_from_event,
        )
        discovery = self.action_discovery_panel
        self.search_entry = discovery.search_entry
        self.actions_tool_rail = discovery.tool_rail
        self.passwords_button = discovery.passwords_button
        self.all_items_button = discovery.all_items_button
        self.actions_button = discovery.actions_button
        self.work_items_button = discovery.work_items_button
        self.scope_options_button = discovery.scope_options_button
        self.new_work_item_button = discovery.new_work_item_button
        self.send_work_item_inbox_button = discovery.send_work_item_inbox_button
        self.copy_file_to_work_item_button = discovery.copy_file_to_work_item_button
        self.type_filter = discovery.type_filter
        self.tag_filter = discovery.tag_filter
        self.run_button = discovery.run_button
        self.work_item_folder_button = discovery.work_item_folder_button
        self.action_help_button = discovery.help_button
        self.context_picker = discovery.context_picker
        self.context_menu = discovery.focus_menu
        self.context_scope_picker = discovery.context_scope_picker
        self.new_action_button = discovery.new_action_button
        self.configure_button = discovery.configure_button
        self.global_help_button = discovery.help_button
        self.footer_action_buttons = [
            discovery.capture_button,
            discovery.inbox_button,
            discovery.edit_button,
        ]
        self.more_menu = discovery.more_menu
        self.more_menu.insert_command(
            1,
            label="Show drop target",
            command=self._show_drop_target,
        )
        self.more_button = discovery.more_button
        self.actions_list_frame = discovery.list_frame
        self.results_scrollbar = discovery.scrollbar
        self.results = discovery.results
        self._prepare_action_icon_alignment()
        self.results.bind("<Button-1>", self._guard_action_separator_click, add="+")
        self.results_tooltip = discovery.results_tooltip
        self.focus_tree = discovery.focus_tree
        self.focus_tree.bind(
            "<Button-1>",
            self._guard_mixed_group_click,
            add="+",
        )
        self.focus_tree.bind(
            "<Double-Button-1>",
            self._activate_mixed_tree_from_event,
        )
        self.focus_tree.bind(
            "<Return>",
            self._activate_mixed_tree_from_event,
        )
        self.focus_tree.bind(
            "<KeyPress>",
            self._navigate_mixed_tree_groups,
            add="+",
        )
        self.focus_tree_tooltip = discovery.focus_tree_tooltip
        discovery.set_discovery_scope(DISCOVERY_ALL)

        self.command_surface_panel = ttk.Frame(outer, padding=(0, 4, 0, 0))
        self.command_surface_panel.pack(fill=tk.X)
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
            self._sync_command_surface_height,
        )
        self.command_surface_canvas.bind(
            "<Configure>",
            self._resize_command_surface,
        )
        # Reserve the compact application controls before letting the Quick
        # action surface consume the remaining vertical space.
        surface_body.pack_forget()
        self.app_controls = ttk.Frame(self.command_surface_panel)
        self.app_controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))
        discovery.configure_button = ttk.Button(
            self.app_controls,
            image=discovery.ui_icons["configure"],
            command=self._show_configuration,
            style="Icon.TButton",
        )
        discovery.configure_button.pack(side=tk.LEFT)
        discovery.help_button = ttk.Button(
            self.app_controls,
            image=discovery.ui_icons["help"],
            command=self._show_help,
            style="Icon.TButton",
        )
        discovery.help_button.pack(side=tk.LEFT, padx=(4, 0))
        discovery.more_button = ttk.Menubutton(
            self.app_controls,
            image=discovery.ui_icons["more"],
            menu=discovery.more_menu,
            style="Icon.TButton",
            takefocus=True,
        )
        discovery.more_button.pack(side=tk.LEFT, padx=(4, 0))
        self._tooltip(
            discovery.configure_button,
            "Configure — Manage Actions, Contexts, Quick actions, Work Items, and diagnostics.",
        )
        self._tooltip(discovery.help_button, lambda: discovery.mode_help_text)
        self._tooltip(
            discovery.more_button,
            "More — Show the drop target, open keyboard shortcuts, hide Context Palette, or quit.",
        )
        surface_body.pack(fill=tk.X)
        self.configure_button = discovery.configure_button
        self.action_help_button = discovery.help_button
        self.global_help_button = discovery.help_button
        self.more_button = discovery.more_button
        self.action_console = outer
        self.actions_panel = discovery.frame

    def _resize_command_surface(self, event: tk.Event) -> None:
        """Fill the canvas and adapt the Quick-action grid without clipping."""

        width = max(1, int(event.width))
        self.command_surface_canvas.itemconfigure(
            self.command_tiles_window,
            width=width,
        )
        columns = quick_action_column_count(width)
        if columns == self.command_surface_columns:
            return
        self.command_surface_columns = columns
        self.root.after_idle(self._render_command_surface)

    def _sync_command_surface_height(self, event: tk.Event) -> None:
        """Shrink Quick actions to its real rows so discovery gets the rest."""

        self.command_surface_canvas.configure(
            scrollregion=self.command_surface_canvas.bbox("all"),
            height=max(1, int(event.height)),
        )

    def _bind_main_shortcuts(self) -> None:

        self.root.bind("<KeyPress>", self._handle_keypress)
        self.root.bind("<Escape>", self._hide_on_plain_escape)
        self.root.bind("<Control-l>", lambda _event: self.focus_search())
        self.root.bind("<Control-k>", lambda _event: self.focus_search())
        self.root.bind("<Control-i>", lambda _event: self._capture_clipboard())
        self.root.bind("<Control-n>", lambda _event: self._show_action_creation())
        self.root.bind("<Control-comma>", lambda _event: self._show_configuration())
        self.root.bind(
            "<Control-Shift-D>",
            lambda _event: self._show_configuration(initial_tab="diagnostics"),
        )
        self.root.bind("<F1>", lambda _event: self._show_help())
        self.root.bind("<F5>", self._reset_main_window)

    def _reset_main_window(self, _event: tk.Event | None = None) -> str:
        """Restore the transient main-window state used by a fresh startup."""
        self.context_scope = CONTEXT_SCOPE_EVERYWHERE
        self._sync_context_scope_control()
        self.action_type_filter = None
        self.action_tag_filter = None
        self.work_project_filter = None
        self.work_tag_filter = None
        self.item_tag_filter = None
        self.action_type_filter_var.set("All types")
        self.action_tag_filter_var.set("All tags")
        if hasattr(self, "item_tag_filter_var"):
            self.item_tag_filter_var.set("All tags")
        if hasattr(self, "work_project_filter_var"):
            self.work_project_filter_var.set("All project codes")
        if hasattr(self, "work_tag_filter_var"):
            self.work_tag_filter_var.set("All work tags")
        if self.passwords_button is not None:
            self.passwords_button.configure(style="RailIcon.TButton")
        if hasattr(self, "action_discovery_panel"):
            self.discovery_scope = DISCOVERY_ALL
            self.work_items_mode = False
            self.action_discovery_panel.set_discovery_scope(
                DISCOVERY_ALL,
                tags=self._available_item_tags(),
            )
            if not self.main_split_customized:
                self.root.after_idle(self._sync_main_split)
            self._sync_filter_indicators()
        self.captured_selection = None
        self.source_foreground_handle = None
        self._set_workspace_text("")
        self.search_var.set("")
        self._reload_if_changed()
        self._refresh_results()
        self.focus_search()
        self.status_var.set("Reset to the startup view.")
        return "break"

    def _hide_on_plain_escape(self, event: tk.Event) -> str:
        if int(event.state) & 0x0004:
            return "break"
        self.hide_window()
        return "break"

    def _build_workspace(self, outer: ttk.Frame) -> None:
        status_label = ttk.Label(
            outer,
            textvariable=self.status_var,
            style="Status.TLabel",
            anchor=tk.W,
        )
        status_label.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))
        self._tooltip(status_label, self._status_tooltip_text)
        status_label.bind("<Button-1>", lambda _event: self._show_action_info_dialog())
        self.status_label = status_label
        self.workspace_component = WorkspacePanel(
            outer,
            clipboard_getter=self.root.clipboard_get,
            clipboard_setter=lambda value: self._set_clipboard(value),
            status_setter=self.status_var.set,
            tooltip_adder=self._tooltip,
            create_action=self._create_action_from_workspace,
            extract_text=self._extract_text_from_image,
            capture=self._capture_clipboard,
            show_inbox=self._show_inbox,
            text_change_callback=self._update_preview,
        )
        # Compatibility aliases keep launcher orchestration and integrations
        # independent while callers migrate to the focused component.
        self.workspace_panel = self.workspace_component.frame
        self.workspace = self.workspace_component.text
        self.workspace_menu = self.workspace_component.context_menu
        self.workspace_transform_menu = self.workspace_component.transform_menu
        self.workspace_transform_button = self.workspace_component.transform_button
        self.text_tools_button = self.workspace_component.text_tools_button
        self.create_action_button = self.workspace_component.create_action_button
        self.ocr_button = self.workspace_component.ocr_button
        self.capture_button = self.workspace_component.capture_button
        self.inbox_button = self.workspace_component.inbox_button
        self.footer_action_buttons = [
            self.workspace_component.capture_button,
            self.workspace_component.inbox_button,
            self.action_discovery_panel.edit_button,
        ]

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

    def _prepare_action_icon_alignment(self) -> None:
        try:
            result_font = tkfont.nametofont(
                str(self.results.cget("font")),
                root=self.root,
            )
        except tk.TclError:
            result_font = tkfont.Font(
                root=self.root,
                font=self.results.cget("font"),
            )
        icons = {definition.icon for definition in ACTION_TYPES.values()} | {"▣"}
        icon_widths = {icon: result_font.measure(icon) for icon in icons}
        target_width = max(icon_widths.values(), default=0)
        spacer = "\u200a"
        spacer_width = result_font.measure(spacer)
        if spacer_width <= 0:
            spacer = " "
            spacer_width = max(1, result_font.measure(spacer))
        self.item_icon_padding: dict[str, str] = {}
        for icon in icons:
            padding = ""
            while (
                result_font.measure(icon + padding + spacer)
                <= target_width
            ):
                padding += spacer
            self.item_icon_padding[icon] = padding

    def _aligned_item_display_text(self, icon: str, title: str) -> str:
        padding = getattr(self, "item_icon_padding", {}).get(icon, "")
        return f"{icon}{padding} {title}"

    def _aligned_action_display_text(self, action: Action) -> str:
        icon = ACTION_TYPES[action.type].icon
        return self._aligned_item_display_text(icon, action.compact_title)

    def _result_tooltip_text(self, index: int) -> str:
        if self.work_items_mode:
            if index < 0 or index >= len(self.displayed_work_items):
                return ""
            item = self.displayed_work_items[index]
            tags = self._work_item_tags(item)
            workbook = (
                item.matching_workbook_path.name
                if item.matching_workbook_path is not None
                else "No exact workbook; opens folder"
            )
            return (
                f"{item.display_name}\n"
                f"{item.kind_name or 'Work item'} · {item.organisation or 'Unparsed'} · {item.source_name}\n"
                f"Project codes: {', '.join(item.project_codes) or '(none)'}\n"
                f"Tags: {', '.join(tags) or '(none)'}\n"
                f"Workbook: {workbook}"
            )
        if index < 0 or index >= len(self.displayed_action_rows):
            return ""
        action, slot = self.displayed_action_rows[index]
        if action is None:
            return ""
        lines = []
        if slot is not None:
            lines.append(f"Shortcut: Shift+{slot_display_number(slot)}")
        lines.append(
            "Contexts: "
            + (", ".join(action.effective_contexts) or "General only")
        )
        if action.effective_tags:
            lines.append(f"Tags: {', '.join(action.effective_tags)}")
        lines.append(f"Action: {action.title}")
        if action.description:
            lines.append(f"Description: {action.description}")
        lines.append(f"Type: {ACTION_TYPES[action.type].display_label}")
        return "\n".join(lines)

    def _transform_workspace(
        self,
        operation: str,
        description: str,
        *,
        prefix: str = "",
        suffix: str = "",
    ) -> None:
        self.workspace_component.transform(
            operation,
            description,
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
        configure_standard_window(window, self.root)
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
            "6–0  WORKING CONTEXT": "The five preferred Actions or Work Items for the current Working context.",
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
        self._reveal_window(
            sync_workspace=True,
            focus_search=True,
            temporary_attention=True,
        )

    def _reveal_window(
        self,
        *,
        sync_workspace: bool,
        focus_search: bool,
        temporary_attention: bool,
    ) -> bool:
        if getattr(self, "_configuration_recovery_required", False):
            messagebox.showerror(
                "Restart required for recovery",
                (
                    "Context Palette must restart so startup recovery can finish "
                    "before configuration is used or changed."
                ),
                parent=self.root,
            )
            return False
        self._cancel_scheduled_hide()
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        if temporary_attention:
            self.root.attributes("-topmost", True)
            self.root.after(100, lambda: self.root.attributes("-topmost", False))
        else:
            self.root.attributes("-topmost", False)
        self.root.focus_force()
        self.search_var.set("")
        self._reload_if_changed()
        if sync_workspace:
            self._sync_workspace_from_clipboard_if_safe()
        if focus_search:
            self.root.after(80, self.focus_search)
        return True

    def _start_drop_target(self) -> None:
        target = getattr(self, "drop_target_window", None)
        if target is not None and not target.start():
            LOGGER.warning("Always-on-top drop target is unavailable")

    def _show_drop_target(self) -> None:
        target = getattr(self, "drop_target_window", None)
        if target is not None and target.show():
            self.status_var.set("Drop target is ready for files, links, or text.")
            return
        self.status_var.set("Drop target is unavailable; Context Palette remains usable.")
        messagebox.showwarning(
            "Drop target unavailable",
            "The optional Windows drag-and-drop component could not be loaded. "
            "Run setup-context-palette.bat to repair the local environment. "
            "All other Context Palette features remain available.",
            parent=self.root,
        )

    def _accept_drop_result(self, result: DropResult) -> None:
        if result.error is not None:
            self.status_var.set(
                f"Drop was not accepted: {result.error.message}"
            )
            return
        if not result.items:
            self.status_var.set("Drop contained no supported content.")
            return

        value = "\n".join(item.value for item in result.items)
        # A drop is a new explicit intake event, never material captured for an
        # earlier window. Invalidate both sources before showing the palette.
        self.captured_selection = None
        self.source_foreground_handle = None
        if not self._reveal_window(
            sync_workspace=False,
            focus_search=False,
            temporary_attention=False,
        ):
            return
        placement = self.workspace_component.apply_incoming_text(
            value,
            source_label="the drop target",
        )
        if placement is None:
            self.status_var.set(
                "Dropped content was not placed; Input / Output was unchanged."
            )
            return
        verb = "Replaced" if placement == "replace" else "Appended to"
        warning_note = (
            f" {len(result.warnings)} shortcut warning(s); unresolved paths were kept."
            if result.warnings
            else ""
        )
        self.status_var.set(
            f"{verb} Input / Output with {len(result.items)} dropped item(s)."
            f"{warning_note}"
        )
        self.root.after_idle(self.workspace_component.text.focus_set)

    def hide_window(self) -> None:
        self._cancel_scheduled_hide()
        if getattr(self, "sequence_run_plan", None) is not None:
            self.status_var.set(
                "A sequence is running. Choose Stop remaining before hiding."
            )
            self._set_sequence_attention(True)
            return
        if not self.hotkey_available:
            self.status_var.set("Cannot hide because no global shortcut is available.")
            return
        self.status_var.set("Hidden. Use F9 or Ctrl+Alt+P to show Context Palette.")
        self.root.withdraw()

    def quit_app(self) -> None:
        ocr = getattr(self, "ocr", None)
        ocr_operations = (
            ("image text extraction",)
            if ocr is not None and ocr.running
            else ()
        )
        active_operations = (
            self._active_work_item_writes()
            + self._active_configuration_operations()
            + ocr_operations
        )
        if active_operations:
            operation_text = " and ".join(active_operations)
            message = (
                f"Context Palette cannot quit while {operation_text} is still running.\n\n"
                "Wait for its success or error message. You may hide the palette "
                "while the operation finishes."
            )
            self.status_var.set(f"Quit blocked: {operation_text} is still running.")
            messagebox.showwarning(
                "Operation still running",
                message,
                parent=self.root,
            )
            return
        self._stop_action_sequence()
        self._finish_protected_clipboard()
        if getattr(self, "protected_clipboard_sequence", None) is not None:
            self.status_var.set("Quit blocked: protected clipboard cleanup is pending.")
            messagebox.showwarning(
                "Protected clipboard cleanup pending",
                "Context Palette cannot quit while Windows is keeping the protected "
                "clipboard busy. Keep the app open; cleanup will retry automatically.",
                parent=self.root,
            )
            return
        self.hotkey.stop()
        self.instance_server.stop()
        self._cancel_pending_tk_callbacks()
        self.root.destroy()

    def _cancel_pending_tk_callbacks(self) -> None:
        """Cancel interpreter callbacks before destroying the Tk application."""

        try:
            callback_ids = self.root.tk.splitlist(
                self.root.tk.call("after", "info")
            )
        except (AttributeError, tk.TclError):
            return
        for callback_id in callback_ids:
            try:
                # Cancel the Tcl timer without asking a possibly different
                # widget to delete its registered Python command. Widget
                # destruction retains ownership of that command bookkeeping.
                self.root.tk.call("after", "cancel", callback_id)
            except tk.TclError:
                pass

    def _active_work_item_writes(self) -> tuple[str, ...]:
        active: list[str] = []
        if self.work_item_file_copy.running:
            active.append("a Work Item file copy")
        if self.work_item_inbox.running:
            active.append("an Excel Inbox update")
        return tuple(active)

    def _active_configuration_operations(self) -> tuple[str, ...]:
        configuration = getattr(self, "configuration_window", None)
        if configuration is None:
            return ()
        try:
            exists = bool(configuration.window.winfo_exists())
        except tk.TclError:
            exists = False
        panel = getattr(configuration, "backup_restore_panel", None)
        if exists and panel is not None and panel.busy:
            return ("a configuration backup or restore",)
        return ()

    def _quit_for_restore_recovery_when_safe(self) -> bool:
        if not getattr(self, "_configuration_recovery_required", False):
            return False
        if self._active_work_item_writes():
            return False
        self.quit_app()
        return True

    def focus_search(self) -> str:
        if self.search_entry is not None:
            self.search_entry.focus_set()
            self.search_entry.selection_range(0, tk.END)
        return "break"

    def _schedule_hide_when_inactive(self, _event: tk.Event) -> None:
        if (
            not self.hotkey_available
            or getattr(self, "sequence_run_plan", None) is not None
        ):
            return
        self._cancel_scheduled_hide()
        self.hide_after_id = self.root.after(200, self._hide_if_inactive)

    def _cancel_scheduled_hide(self, _event: tk.Event | None = None) -> None:
        hide_after_id = getattr(self, "hide_after_id", None)
        if hide_after_id is not None:
            self.root.after_cancel(hide_after_id)
            self.hide_after_id = None

    def _hide_if_inactive(self) -> None:
        self.hide_after_id = None
        if getattr(self, "sequence_run_plan", None) is not None:
            self._set_sequence_attention(True)
            return
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
        self._finish_protected_clipboard()
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
                inspect_external_paths=False,
            )
            available_tags = self._available_item_tags()
            if hasattr(self, "action_discovery_panel"):
                self.action_discovery_panel.set_tags(self._available_item_tags())
            if (
                getattr(self, "item_tag_filter", None) is not None
                and self.item_tag_filter.casefold()
                not in {tag.casefold() for tag in available_tags}
            ):
                self.item_tag_filter = None
                self.action_tag_filter = None
                self.work_tag_filter = None
                self.item_tag_filter_var.set("All tags")
                self.action_tag_filter_var.set("All tags")
                self.work_tag_filter_var.set("All work tags")
            self._sync_filter_indicators()
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

    def _load_work_item_configuration(self) -> None:
        try:
            sources = load_work_item_sources(
                self.local_work_item_sources_path
            )
            metadata = load_work_item_metadata(
                self.local_work_item_metadata_path
            )
        except WorkItemStorageError as exc:
            self.status_var.set("Work Items configuration could not be loaded.")
            messagebox.showerror(
                "Work Items configuration could not be loaded",
                f"{exc}\n\nExisting in-memory Work Items results were kept.",
                parent=self.root,
            )
            LOGGER.exception("Work Items local configuration failed to load")
            return
        self.work_item_sources = sources
        self.work_item_metadata = metadata
        if not sources:
            self.work_item_index = WorkItemIndex()

    def _start_work_item_refresh(self) -> None:
        if not self.work_item_sources:
            if self.work_item_refresh.running:
                self.work_item_refresh_pending = True
            else:
                self._accept_work_item_index(WorkItemIndex())
            return
        if self.work_item_refresh.start(
            self.work_item_sources,
            self.work_item_index,
            self._accept_work_item_index,
        ):
            if self.discovery_scope in {DISCOVERY_ALL, DISCOVERY_WORK_ITEMS}:
                self.status_var.set("Refreshing Work Items…")
        else:
            self.work_item_refresh_pending = True

    def _poll_work_item_refresh(self) -> None:
        try:
            self.work_item_refresh.drain()
            self.root.after(100, self._poll_work_item_refresh)
        except tk.TclError:
            return

    def _poll_work_item_inbox(self) -> None:
        try:
            self.work_item_inbox.drain()
            if self._quit_for_restore_recovery_when_safe():
                return
            self.root.after(100, self._poll_work_item_inbox)
        except tk.TclError:
            return

    def _poll_work_item_file_copy(self) -> None:
        try:
            self.work_item_file_copy.drain()
            if self._quit_for_restore_recovery_when_safe():
                return
            self.root.after(100, self._poll_work_item_file_copy)
        except tk.TclError:
            return

    def _poll_ocr(self) -> None:
        self.ocr_after_id = None
        try:
            self.ocr.drain()
            if self.ocr.running:
                self.ocr_after_id = self.root.after(100, self._poll_ocr)
        except tk.TclError:
            return

    def _accept_work_item_index(self, index: WorkItemIndex) -> None:
        configured_source_ids = {
            source.id.casefold() for source in self.work_item_sources
        }
        self.work_item_index = WorkItemIndex(
            tuple(
                result
                for result in index.sources
                if result.source.id.casefold() in configured_source_ids
            ),
            index.elapsed_seconds,
        )
        project_codes = self._available_work_project_codes()
        work_tags = self._available_work_tags()
        if (
            self.work_project_filter is not None
            and self.work_project_filter.casefold()
            not in {code.casefold() for code in project_codes}
        ):
            self.work_project_filter = None
            self.work_project_filter_var.set("All project codes")
        item_tags = self._available_item_tags()
        if (
            self.item_tag_filter is not None
            and self.item_tag_filter.casefold()
            not in {tag.casefold() for tag in item_tags}
        ):
            self.item_tag_filter = None
            self.action_tag_filter = None
            self.work_tag_filter = None
            self.item_tag_filter_var.set("All tags")
            self.action_tag_filter_var.set("All tags")
            self.work_tag_filter_var.set("All work tags")
        if self.discovery_scope in {DISCOVERY_ALL, DISCOVERY_WORK_ITEMS}:
            self.action_discovery_panel.set_discovery_scope(
                self.discovery_scope,
                project_codes=project_codes,
                tags=item_tags,
            )
            self._sync_filter_indicators()
            self._refresh_results()
        if getattr(self, "work_item_refresh_pending", False):
            self.work_item_refresh_pending = False
            self.root.after_idle(self._start_work_item_refresh)

    def _work_item_tags(self, item: DiscoveredWorkItem) -> tuple[str, ...]:
        key = work_item_metadata_key(item.source_id, item.relative_folder)
        metadata = self.work_item_metadata.get(key)
        return metadata.tags if metadata is not None else ()

    def _available_work_project_codes(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {code for item in self.work_item_index.items for code in item.project_codes},
                key=str.casefold,
            )
        )

    def _available_work_tags(self) -> tuple[str, ...]:
        work_item_index = getattr(self, "work_item_index", None)
        return tuple(
            sorted(
                {
                    tag
                    for item in (work_item_index.items if work_item_index else ())
                    for tag in self._work_item_tags(item)
                },
                key=str.casefold,
            )
        )

    def _available_item_tags(self) -> tuple[str, ...]:
        tags = {
            tag
            for action in self.actions
            for tag in action.effective_tags
        }
        tags.update(self._available_work_tags())
        return tuple(sorted(tags, key=str.casefold))

    def _load_command_surface(self, *, render: bool = True) -> None:
        try:
            self.command_groups = load_combined_command_groups(
                self.command_surface_path,
                self.local_command_surface_path,
            )
        except CommandSurfaceError as exc:
            button_count = sum(
                command_group_launcher_count(group)
                for group in self.command_groups
            )
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
        standard_group = next(
            (
                group
                for group in self.command_groups
                if group.id.casefold() == STANDARD_QUICK_GROUP_ID
            ),
            CommandGroup(
                id=STANDARD_QUICK_GROUP_ID,
                label="Standard",
                presentation=GROUP_PRESENTATION_NESTED_MENU,
            ),
        )
        configured_groups = [
            group
            for group in self.command_groups
            if group.id.casefold() != STANDARD_QUICK_GROUP_ID
        ]
        configured_groups = ordered_configured_quick_groups(
            configured_groups,
            self.local_command_surface_path,
        )
        bound_groups = action_bound_quick_groups(self.actions)
        button_count = 1 + len(bound_groups) + sum(
            command_group_launcher_count(group)
            for group in configured_groups
        )
        self.surface_count_var.set(
            f"{button_count} button" if button_count == 1 else f"{button_count} buttons"
        )
        column_count = self.command_surface_columns
        for column in range(2):
            enabled = column < column_count
            self.command_tiles_frame.columnconfigure(
                column,
                weight=1 if enabled else 0,
                uniform="surface" if enabled else "",
                minsize=0,
            )
        position = 0
        row, column = divmod(position, column_count)
        self._render_configured_quick_group(standard_group, row=row, column=column)
        position += 1
        for group in configured_groups:
            row, column = divmod(position, column_count)
            self._render_configured_quick_group(
                group,
                row=row,
                column=column,
            )
            position += 1
        for group in bound_groups:
            row, column = divmod(position, column_count)
            self._render_action_bound_quick_group(group, row=row, column=column)
            position += 1

    def _render_configured_quick_group(
        self,
        group: CommandGroup,
        *,
        row: int,
        column: int,
    ) -> None:
        area = ttk.Frame(self.command_tiles_frame, padding=4)
        area.grid(row=row, column=column, sticky=tk.NSEW, padx=2, pady=2)
        area.columnconfigure(0, weight=1)
        control = self._surface_menu_label(area, group.label)
        choice_count = quick_group_top_level_choice_count(group)
        choice_label = "choice" if choice_count == 1 else "choices"
        self._command_surface_tooltip(
            control,
            f"Left-click: browse {group.label} ({choice_count} configured top-level {choice_label}). "
            "Right-click: add or organize.",
        )
        self._bind_surface_menu_control(
            control,
            on_click=lambda event: self._show_group_menu(event, group),
            on_menu=lambda event: self._show_configured_group_management(
                event,
                group,
            ),
            on_keyboard=lambda _event: self._show_group_menu_at_control(
                control,
                group,
            ),
        )

    def _render_action_bound_quick_group(
        self,
        group: CommandGroup,
        *,
        row: int,
        column: int,
    ) -> None:
        area = ttk.Frame(self.command_tiles_frame, padding=4)
        area.grid(row=row, column=column, sticky=tk.NSEW, padx=2, pady=2)
        area.columnconfigure(0, weight=1)
        control = self._surface_menu_label(area, group.label)
        action_type = self._action_bound_type_for_group(group)
        action_count = sum(
            1
            for action in self.actions
            if action.type == action_type and action.state != "Archived"
        )
        action_label = "Action" if action_count == 1 else "Actions"
        self._command_surface_tooltip(
            control,
            f"Left-click: browse {group.label} ({action_count} active {action_label}). "
            "Right-click: add or organize. Matching Actions appear automatically.",
        )
        self._bind_surface_menu_control(
            control,
            on_click=lambda event: self._show_action_bound_group_menu(
                event,
                group,
                action_type,
            ),
            on_menu=lambda event: self._show_action_bound_group_management(
                event,
                group,
                action_type,
            ),
            on_keyboard=lambda _event: self._post_group_menu(
                group,
                control.winfo_rootx(),
                control.winfo_rooty() + control.winfo_height(),
                automatic_action_type=action_type,
            ),
        )

    def _surface_menu_label(
        self,
        parent: ttk.Frame,
        label: str,
        *,
        row: int = 0,
        dropdown: bool = True,
    ) -> ttk.Label:
        control = ttk.Label(
            parent,
            text=f"{label} ▾" if dropdown else label,
            style="SurfaceMenu.TLabel",
            anchor=tk.W,
            relief=tk.SOLID,
            cursor="hand2",
            takefocus=True,
        )
        control.grid(row=row, column=0, sticky=tk.EW, padx=1, pady=1)
        return control

    def _show_action_bound_group_menu(
        self,
        event: tk.Event,
        group: CommandGroup,
        action_type: str,
    ) -> str:
        return self._post_group_menu(
            group,
            event.x_root,
            event.y_root,
            automatic_action_type=action_type,
        )

    def _work_item_for_reference(
        self,
        reference: WorkItemReference,
    ) -> DiscoveredWorkItem | None:
        source_key = reference.source_id.casefold()
        folder_key = reference.relative_folder.casefold()
        return next(
            (
                item
                for item in self.work_item_index.items
                if item.source_id.casefold() == source_key
                and item.relative_folder.casefold() == folder_key
            ),
            None,
        )

    def _execute_work_item_reference(
        self,
        label: str,
        reference: WorkItemReference,
    ) -> bool:
        item = self._work_item_for_reference(reference)
        if item is None:
            self.status_var.set(f"Work Item unavailable: {label}")
            messagebox.showerror(
                "Work Item unavailable",
                f'“{label}” is not in the current Work Item index.\n\n'
                "Refresh Work Items or check its personal source configuration. "
                "The Quick action has been kept and will recover when the source returns.",
                parent=self.root,
            )
            return False
        target = item.default_open_path
        if not self._open_work_item_target(item, target):
            return False
        self.status_var.set(
            f"Opened workbook: {target.name}"
            if item.matching_workbook_path is not None
            and target == item.matching_workbook_path
            else f"Opened folder: {item.display_name}"
        )
        return True

    def _action_bound_type_for_group(self, group: CommandGroup) -> str:
        for group_id, _label, action_type in ACTION_BOUND_QUICK_MENU_SPECS:
            if group.id.casefold() == f"action-bound-{group_id}".casefold():
                return action_type
        raise ValueError(f"Unknown automatic Quick-action group: {group.id}")

    def _show_configured_group_management(
        self,
        event: tk.Event,
        group: CommandGroup,
    ) -> str:
        return self._post_configured_quick_management(
            group,
            (),
            event.x_root,
            event.y_root,
        )

    def _show_action_bound_group_management(
        self,
        event: tk.Event,
        group: CommandGroup,
        action_type: str,
    ) -> str:
        return self._post_action_bound_quick_management(
            group,
            action_type,
            (),
            event.x_root,
            event.y_root,
        )

    def _post_configured_quick_management(
        self,
        group: CommandGroup,
        item_path: tuple[int, ...],
        x_root: int,
        y_root: int,
    ) -> str:
        item_ids = command_item_id_path(group, item_path) if item_path else ()
        label = (
            command_item_at_path(group, item_path).label
            if item_path
            else group.label
        )
        commands: list[tuple[str, Callable[[], None]] | None] = []
        if len(item_path) < MAX_COMMAND_MENU_LEVELS:
            add_label = (
                "New submenu here…"
                if item_path
                else f"Add Quick action to {group.label}…"
            )
            commands.extend(
                (
                    (
                        add_label,
                        lambda: self._open_configured_quick_manager(
                            group.id,
                            item_ids,
                            start_add=True,
                        ),
                    ),
                    None,
                )
            )
        commands.append(
            (
                f"Organize {label}…",
                lambda: self._open_configured_quick_manager(
                    group.id,
                    item_ids,
                ),
            )
        )
        return self._post_quick_management_menu(
            tuple(commands),
            x_root,
            y_root,
        )

    def _post_action_bound_quick_management(
        self,
        group: CommandGroup,
        action_type: str,
        path: tuple[str, ...],
        x_root: int,
        y_root: int,
    ) -> str:
        noun = ACTION_BOUND_QUICK_NOUNS[action_type]
        add_label = (
            f"Add {noun} here…"
            if path
            else ACTION_BOUND_QUICK_ADD_LABELS[action_type]
        )
        selection_label = " > ".join((group.label, *path))
        return self._post_quick_management_menu(
            (
                (
                    add_label,
                    lambda: self._open_automatic_quick_creator(
                        action_type,
                        path,
                    ),
                ),
                None,
                (
                    f"Organize {selection_label}…",
                    lambda: self._open_automatic_quick_manager(
                        action_type,
                        path,
                    ),
                ),
                (
                    "Find matching Actions…",
                    lambda: self._find_automatic_quick_actions(
                        group.label,
                        action_type,
                        path,
                    ),
                ),
            ),
            x_root,
            y_root,
        )

    def _post_quick_management_menu(
        self,
        commands: tuple[tuple[str, Callable[[], None]] | None, ...],
        x_root: int,
        y_root: int,
    ) -> str:
        menu = tk.Menu(self.root, tearoff=False)
        for command in commands:
            if command is None:
                menu.add_separator()
                continue
            label, callback = command
            menu.add_command(label=label, command=callback)
        self._active_quick_management_menu = menu
        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()
        return "break"

    def _open_configured_quick_manager(
        self,
        group_id: str,
        item_ids: tuple[str, ...] = (),
        *,
        start_add: bool = False,
    ) -> None:
        self._show_configuration(initial_tab="buttons")
        workspace = getattr(self, "configuration_window", None)
        if workspace is None:
            return
        if workspace.select_configured_quick_action(group_id, item_ids) and start_add:
            workspace.add_quick_action_to_selection()

    def _open_automatic_quick_manager(
        self,
        action_type: str,
        path: tuple[str, ...] = (),
    ) -> None:
        self._show_configuration(initial_tab="buttons")
        workspace = getattr(self, "configuration_window", None)
        if workspace is not None:
            workspace.select_automatic_quick_action(action_type, path)

    def _open_automatic_quick_creator(
        self,
        action_type: str,
        path: tuple[str, ...] = (),
    ) -> None:
        self._show_configuration(initial_tab="buttons")
        workspace = getattr(self, "configuration_window", None)
        if workspace is None:
            return
        workspace.select_automatic_quick_action(action_type, path)
        workspace.create_action_for_automatic_menu(action_type, path)

    def _find_automatic_quick_actions(
        self,
        group_label: str,
        action_type: str,
        path: tuple[str, ...] = (),
    ) -> None:
        self._show_configuration(initial_tab="buttons")
        workspace = getattr(self, "configuration_window", None)
        if workspace is not None:
            workspace.show_automatic_quick_actions(
                group_label,
                action_type,
                path,
            )

    def _edit_action_from_quick_menu(self, action_id: str) -> None:
        self._show_configuration(
            initial_tab="actions",
            initial_action_id=action_id,
            start_action_edit=True,
        )

    def _manage_work_item_from_quick_menu(
        self,
        reference: WorkItemReference,
    ) -> None:
        self._show_configuration(
            initial_tab="work_items",
            initial_work_item_key=work_item_metadata_key(
                reference.source_id,
                reference.relative_folder,
            ),
        )

    def _show_item_menu(self, event: tk.Event, item: CommandItem) -> str:
        return self._post_item_menu(item, event.x_root, event.y_root)

    def _post_item_menu(
        self,
        item: CommandItem,
        x_root: int,
        y_root: int,
    ) -> str:
        menu = tk.Menu(self.root, tearoff=False)
        submenus: list[tk.Menu] = []
        self._populate_menu_node(
            menu,
            command_item_targets(item),
            item.items,
            submenus,
        )
        self._active_command_menu = menu
        self._active_command_submenus = tuple(submenus)
        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()
        return "break"

    def _populate_menu_node(
        self,
        menu: tk.Menu,
        targets: tuple[CommandTarget, ...],
        child_items: tuple[CommandItem, ...],
        submenus: list[tk.Menu],
        *,
        item_path: tuple[int, ...] = (),
        label_path: tuple[str, ...] = (),
        manage_branch: Callable[
            [CommandItem, tuple[int, ...], tuple[str, ...], int, int],
            None,
        ]
        | None = None,
    ) -> None:
        actions_by_id = {action.id: action for action in self.actions}
        entry_managers: dict[int, Callable[[int, int], None]] = {}
        added_targets = False
        for target in targets:
            if target.action_id:
                action = actions_by_id.get(target.action_id)
                if action is None:
                    continue
                menu.add_command(
                    label=action.compact_display_text,
                    command=lambda selected_action=action: self._execute_action(selected_action),
                )
                entry_index = menu.index(tk.END)
                if entry_index is not None:
                    entry_managers[int(entry_index)] = (
                        lambda _x, _y, action_id=action.id: self._edit_action_from_quick_menu(
                            action_id
                        )
                    )
                added_targets = True
                continue
            work_item_ref = target.work_item_ref
            if work_item_ref is None:
                continue
            work_item = self._work_item_for_reference(work_item_ref)
            if work_item is None:
                menu.add_command(
                    label=f"Unavailable Work Item - {work_item_ref.relative_folder}",
                    state=tk.DISABLED,
                )
            else:
                menu.add_command(
                    label=f"▣ - {work_item.display_name}",
                    command=lambda selected_item=work_item: self._execute_work_item_reference(
                        selected_item.display_name,
                        WorkItemReference(selected_item.source_id, selected_item.relative_folder),
                    ),
                )
                entry_index = menu.index(tk.END)
                if entry_index is not None:
                    entry_managers[int(entry_index)] = (
                        lambda _x, _y, reference=work_item_ref: self._manage_work_item_from_quick_menu(
                            reference
                        )
                    )
            added_targets = True
        if added_targets and child_items:
            menu.add_separator()
        for child_index, child in enumerate(child_items):
            child_item_path = (*item_path, child_index)
            child_label_path = (*label_path, child.label)
            submenu = tk.Menu(menu, tearoff=False)
            submenus.append(submenu)
            self._populate_menu_node(
                submenu,
                command_item_targets(child),
                child.items,
                submenus,
                item_path=child_item_path,
                label_path=child_label_path,
                manage_branch=manage_branch,
            )
            menu.add_cascade(label=child.label, menu=submenu)
            entry_index = menu.index(tk.END)
            if entry_index is not None and manage_branch is not None:
                entry_managers[int(entry_index)] = (
                    lambda x, y, selected_item=child, selected_path=child_item_path,
                    selected_labels=child_label_path: manage_branch(
                        selected_item,
                        selected_path,
                        selected_labels,
                        x,
                        y,
                    )
                )
        if menu.index(tk.END) is None:
            menu.add_command(label="No available actions", state=tk.DISABLED)
        self._bind_command_menu_management(menu, entry_managers)

    def _bind_command_menu_management(
        self,
        menu: tk.Menu,
        entry_managers: dict[int, Callable[[int, int], None]],
    ) -> None:
        if not entry_managers:
            return
        menu._context_palette_entry_managers = entry_managers  # type: ignore[attr-defined]
        menu.bind(
            "<Button-3>",
            lambda event: self._handle_command_menu_right_click(
                menu,
                entry_managers,
                event,
            ),
            add="+",
        )

    def _handle_command_menu_right_click(
        self,
        menu: tk.Menu,
        entry_managers: dict[int, Callable[[int, int], None]],
        event: tk.Event,
    ) -> str:
        try:
            entry_index = menu.index(f"@{event.y}")
        except tk.TclError:
            entry_index = None
        callback = (
            entry_managers.get(int(entry_index))
            if entry_index is not None
            else None
        )
        if callback is None:
            return "break"
        x_root = int(getattr(event, "x_root", 0))
        y_root = int(getattr(event, "y_root", 0))
        self._dismiss_active_command_menu()
        self.root.after_idle(
            lambda: callback(x_root, y_root)
        )
        return "break"

    def _dismiss_active_command_menu(self) -> None:
        menu = getattr(self, "_active_command_menu", None)
        if menu is None:
            return
        try:
            menu.unpost()
        except tk.TclError:
            pass
        try:
            menu.grab_release()
        except tk.TclError:
            pass

    def _show_group_menu(self, event: tk.Event, group: CommandGroup) -> str:
        return self._post_group_menu(group, event.x_root, event.y_root)

    def _show_group_menu_at_control(
        self,
        control: tk.Widget,
        group: CommandGroup,
    ) -> str:
        return self._post_group_menu(
            group,
            control.winfo_rootx(),
            control.winfo_rooty() + control.winfo_height(),
        )

    def _post_group_menu(
        self,
        group: CommandGroup,
        x_root: int,
        y_root: int,
        *,
        automatic_action_type: str | None = None,
    ) -> str:
        menu = tk.Menu(self.root, tearoff=False)
        submenus: list[tk.Menu] = []
        manage_branch = (
            (
                lambda _item, path, _labels, x, y: self._post_configured_quick_management(
                    group,
                    path,
                    x,
                    y,
                )
            )
            if automatic_action_type is None
            else (
                lambda _item, _path, labels, x, y: self._post_action_bound_quick_management(
                    group,
                    automatic_action_type,
                    labels,
                    x,
                    y,
                )
            )
        )
        self._populate_menu_node(
            menu,
            tuple(
                CommandTarget(action_id=action_id)
                for action_id in command_group_action_ids(group)
            ),
            group.items,
            submenus,
            manage_branch=manage_branch,
        )
        self._active_command_menu = menu
        self._active_command_submenus = tuple(submenus)
        try:
            menu.tk_popup(x_root, y_root)
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
            self.actions = actions_with_canonical_contexts(
                self.actions,
                self.context_definitions,
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
                "Palette settings could not be loaded; kept previous Working context and slots."
            )
            messagebox.showerror(
                "Palette settings could not be loaded",
                f"{exc}\n\nThe previous Working context and context slots remain active.",
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
        self.focus_launcher_var.set(
            "Context: All contexts"
            if context.casefold() == "general"
            else f"Context: {context}"
        )
        self.context_menu.delete(0, tk.END)
        for name in self.available_context_names:
            self.context_menu.add_radiobutton(
                label="All contexts" if name.casefold() == "general" else name,
                variable=self.context_var,
                value=name,
                command=self._change_focus_context,
            )
        if self.available_context_names:
            self.context_menu.add_separator()
        self.context_menu.add_command(
            label="Manage contexts…",
            command=self._show_focus_configuration,
        )
        self._sync_context_scope_control()

    def _change_focus_context(self) -> None:
        context = self.context_var.get().strip() or "General"
        previous_state = self.palette_state
        updated_state = PaletteState(
            self.palette_state.pinned_action_ids,
            context,
            self.palette_state.context_slots,
            self.palette_state.context_membership_version,
            self.palette_state.context_item_slots,
        )
        try:
            save_palette_state(self.palette_path, updated_state)
        except OSError as exc:
            self.context_var.set(previous_state.focus_context)
            if hasattr(self, "context_menu"):
                self._refresh_focus_controls()
            self.status_var.set("Working context was not changed because it could not be saved.")
            messagebox.showerror(
                "Context Palette",
                f"Could not save the Working context.\n\n{exc}",
            )
            return
        self.palette_state = updated_state
        if hasattr(self, "context_menu"):
            self._refresh_focus_controls()
        self.configuration_signature_cache = self._configuration_signature()
        self._refresh_results()
        self.status_var.set(
            "Searching all contexts."
            if context.casefold() == "general"
            else f"Working context: {context}"
        )
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
        self.slot_items = palette_item_slots(self.actions, self.palette_state)
        self.slot_actions = action_slots(self.actions, self.palette_state)
        if self.discovery_scope == DISCOVERY_WORK_ITEMS:
            self._render_work_items()
            return
        if self.discovery_scope == DISCOVERY_ALL:
            self._render_all_items()
            _warn_if_slow(
                "result refresh",
                started_at,
                SLOW_RESULT_REFRESH_SECONDS,
                action_count=len(self.actions),
            )
            return
        self._show_flat_results()
        self.filtered_actions = search_actions(self.actions, self.search_var.get())
        selected_context = self._selected_result_context()
        if selected_context is not None:
            self.filtered_actions = [
                action
                for action in self.filtered_actions
                if self._action_belongs_to_context(
                    action,
                    selected_context,
                )
            ]
        if self.action_type_filter is not None:
            self.filtered_actions = [
                action
                for action in self.filtered_actions
                if action.type == self.action_type_filter
            ]
        if self.item_tag_filter is not None:
            selected_tag = self.item_tag_filter.casefold()
            self.filtered_actions = [
                action
                for action in self.filtered_actions
                if selected_tag in {
                    tag.casefold() for tag in action.effective_tags
                }
            ]
        matching_ids = {action.id for action in self.filtered_actions}
        slot_rows = (
            []
            if self.search_var.get().strip()
            else [
                (slot, action)
                for slot, action in sorted(self.slot_actions.items())
                if action.id in matching_ids
            ]
        )
        slot_row_ids = {action.id for _slot, action in slot_rows}
        remaining = [
            action for action in self.filtered_actions if action.id not in slot_row_ids
        ]
        self.displayed_actions = [action for _slot, action in slot_rows] + remaining
        self.displayed_slots = [slot for slot, _action in slot_rows] + [None] * len(remaining)
        self.displayed_action_rows = [
            (action, slot) for slot, action in slot_rows
        ]
        if slot_rows and remaining:
            self.displayed_action_rows.append((None, None))
        self.displayed_action_rows.extend((action, None) for action in remaining)
        self.results.delete(0, tk.END)
        for index, (action, slot) in enumerate(self.displayed_action_rows):
            if action is None:
                self.results.insert(tk.END, "   " + "─" * 28)
                self.results.itemconfigure(
                    index,
                    background=COLORS["surface"],
                    foreground=COLORS["muted_text"],
                    selectbackground=COLORS["surface"],
                    selectforeground=COLORS["muted_text"],
                )
                continue
            self.results.insert(
                tk.END,
                self._aligned_action_display_text(action),
            )
            row_tag = slot_row_tag(slot)
            if row_tag == FOCUS_SLOT_ROW_TAG:
                self.results.itemconfigure(
                    index,
                    background=COLORS["slot_focus"],
                    foreground=COLORS["text"],
                )
        if self.displayed_actions:
            self.results.selection_set(0)
            self.results.activate(0)
        count = len(self.filtered_actions)
        self.results_count_var.set(f"{count} action" if count == 1 else f"{count} actions")
        if not self.displayed_actions:
            query = self.search_var.get().strip()
            if (
                self.action_type_filter is not None
                and self.item_tag_filter is not None
            ):
                type_label = ACTION_TYPES[self.action_type_filter].display_label
                empty_message = (
                    f'No {type_label} actions tagged “{self.item_tag_filter}” '
                    f'match “{query}”.\nClear Find or choose another filter.'
                    if query
                    else f'No {type_label} actions use the tag '
                    f'“{self.item_tag_filter}”.\nChoose another type or tag.'
                )
            elif self.item_tag_filter is not None:
                empty_message = (
                    f'No actions tagged “{self.item_tag_filter}” match “{query}”.\n'
                    "Clear Find or choose another tag."
                    if query
                    else f'No actions use the tag “{self.item_tag_filter}”.\n'
                    "Choose another tag or add it in Configure."
                )
            elif self.action_type_filter is not None:
                type_label = ACTION_TYPES[self.action_type_filter].display_label
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
            if (
                self.action_type_filter is not None
                and self.item_tag_filter is not None
            ):
                type_label = ACTION_TYPES[self.action_type_filter].display_label
                self.status_var.set(
                    f"No matching actions · type: {type_label} · "
                    f"tag: {self.item_tag_filter}"
                )
            elif self.item_tag_filter is not None:
                self.status_var.set(
                    f"No matching action tagged {self.item_tag_filter}."
                )
            elif self.action_type_filter is not None:
                type_label = ACTION_TYPES[self.action_type_filter].display_label
                self.status_var.set(
                    f"No matching {type_label} action. Clear Find or choose another type."
                )
            else:
                self.status_var.set("No matching action. Clear Find or create one in Configure.")
        else:
            if (
                self.action_type_filter is not None
                and self.item_tag_filter is not None
            ):
                type_label = ACTION_TYPES[self.action_type_filter].display_label
                self.status_var.set(
                    f"{count} action{'s' if count != 1 else ''} · "
                    f"type: {type_label} · tag: {self.item_tag_filter}"
                )
            elif self.item_tag_filter is not None:
                self.status_var.set(
                    f"{count} action{'s' if count != 1 else ''} tagged "
                    f"{self.item_tag_filter}"
                )
            elif self.action_type_filter is not None:
                type_label = ACTION_TYPES[self.action_type_filter].display_label
                label = f"{type_label} action" if count == 1 else f"{type_label} actions"
                self.status_var.set(f"{count} {label}")
            else:
                self.status_var.set(
                    f"{count} matches · context slots 6–0: {self.palette_state.focus_context}"
                )
        self._update_preview()
        _warn_if_slow(
            "result refresh",
            started_at,
            SLOW_RESULT_REFRESH_SECONDS,
            action_count=len(self.actions),
        )

    def _work_item_belongs_to_context(
        self,
        item: DiscoveredWorkItem,
        context: str | None,
    ) -> bool:
        if context is None or context.casefold() == "general":
            return True
        reference = WorkItemReference(item.source_id, item.relative_folder)
        palette_reference = PaletteItemReference(work_item_ref=reference)
        return any(
            palette_reference in definition.member_items
            for definition in self.context_definitions
            if definition.name.casefold() == context.casefold()
        )

    def _action_belongs_to_context(
        self,
        action: Action,
        context: str | None,
    ) -> bool:
        if context is None or context.casefold() == "general":
            return True
        if action.belongs_to_context(context):
            return True
        reference = PaletteItemReference(action_id=action.id)
        return any(
            reference in definition.member_items
            for definition in self.context_definitions
            if definition.name.casefold() == context.casefold()
        )

    def _render_all_items(self) -> None:
        self._show_mixed_results("all")
        self.actions_heading_var.set("All items")
        query = self.search_var.get()
        actions = search_actions(self.actions, query)
        selected_context = self._selected_result_context()
        if selected_context is not None:
            actions = [
                action
                for action in actions
                if self._action_belongs_to_context(
                    action,
                    selected_context,
                )
            ]
        if self.item_tag_filter is not None:
            selected_tag = self.item_tag_filter.casefold()
            actions = [
                action
                for action in actions
                if selected_tag in {
                    tag.casefold() for tag in action.effective_tags
                }
            ]
        work_items = [
            item
            for item in self.work_item_index.items
            if work_item_matches(
                item,
                query,
                tags=self._work_item_tags(item),
                tag=self.item_tag_filter,
            )
            and self._work_item_belongs_to_context(
                item,
                selected_context,
            )
        ]
        if query.strip():
            work_items.sort(
                key=lambda item: (
                    work_item_search_rank(item, query),
                    item.display_name.casefold(),
                    f"{item.source_id}/{item.relative_folder}".casefold(),
                )
            )
        self.filtered_actions = actions
        self.displayed_actions = actions
        self.displayed_work_items = work_items
        actions_by_id = {action.id: action for action in actions}
        work_items_by_reference = {
            WorkItemReference(item.source_id, item.relative_folder): item
            for item in work_items
        }
        matching_references = {
            *(PaletteItemReference(action_id=action.id) for action in actions),
            *(
                PaletteItemReference(work_item_ref=reference)
                for reference in work_items_by_reference
            ),
        }
        slotted = (
            []
            if query.strip()
            else [
                (slot, reference)
                for slot, reference in sorted(self.slot_items.items())
                if reference in matching_references
            ]
        )
        slotted_references = {reference for _slot, reference in slotted}
        remaining = [
            *(PaletteItemReference(action_id=action.id) for action in actions),
            *(
                PaletteItemReference(work_item_ref=reference)
                for reference in work_items_by_reference
            ),
        ]
        remaining = [
            reference
            for reference in remaining
            if reference not in slotted_references
        ]
        def display_key(reference: PaletteItemReference) -> tuple[str, str]:
            return (
                actions_by_id[reference.action_id].compact_title.casefold()
                if reference.action_id
                else work_items_by_reference[
                    reference.work_item_ref
                ].display_name.casefold(),
                reference.stable_key,
            )

        def result_key(reference: PaletteItemReference) -> tuple[int, str, str]:
            if reference.action_id:
                rank = action_search_rank(actions_by_id[reference.action_id], query)
            else:
                assert reference.work_item_ref is not None
                rank = work_item_search_rank(
                    work_items_by_reference[reference.work_item_ref],
                    query,
                )
            visible, stable = display_key(reference)
            return rank, visible, stable

        ordinary_remaining = sorted(remaining, key=result_key)
        rows: list[tuple[int | None, PaletteItemReference | None]] = [
            *slotted,
            *((None, reference) for reference in ordinary_remaining),
        ]

        self.focus_tree.delete(*self.focus_tree.get_children())
        self.focus_tree_actions.clear()
        self.focus_tree_items.clear()
        for index, (slot, reference) in enumerate(rows):
            assert reference is not None
            if reference.action_id:
                action = actions_by_id[reference.action_id]
                label = self._aligned_action_display_text(action)
                item_id = f"all-action:{index}:{action.id}"
                self.focus_tree_actions[item_id] = action
            else:
                assert reference.work_item_ref is not None
                item = work_items_by_reference[reference.work_item_ref]
                label = self._aligned_item_display_text("▣", item.display_name)
                item_id = f"all-work-item:{index}:{reference.stable_key}"
            row_tag = slot_row_tag(slot)
            self.focus_tree.insert(
                "",
                tk.END,
                iid=item_id,
                text=label,
                tags=(row_tag,) if row_tag else (),
            )
            self.focus_tree_items[item_id] = reference

        match_count = len(actions) + len(work_items)
        self.results_count_var.set(
            f"{match_count} item" if match_count == 1 else f"{match_count} items"
        )
        if rows:
            first = next(
                item_id
                for item_id in self.focus_tree.get_children()
                if item_id in self.focus_tree_items
            )
            self.focus_tree.selection_set(first)
            self.focus_tree.focus(first)
            self.status_var.set(
                f"{len(actions)} Actions · {len(work_items)} Work Items"
            )
        else:
            has_filter = bool(
                query.strip()
                or selected_context is not None
                or self.item_tag_filter is not None
            )
            self.focus_tree.insert(
                "",
                tk.END,
                iid="empty:all",
                text=(
                    "No items match Find or the selected filters."
                    if has_filter
                    else "No items are available. Use +A to create an Action."
                ),
                tags=(FOCUS_GROUP_ROW_TAG,),
            )
            self.status_var.set("No Actions or Work Items match the current filters.")
        self._update_preview()

    def _guard_mixed_group_click(self, event: tk.Event) -> str | None:
        item_id = self.focus_tree.identify_row(event.y)
        if item_id and item_id not in self.focus_tree_items:
            return "break"
        return None

    def _activate_mixed_tree_from_event(self, event: tk.Event) -> str:
        if str(getattr(event, "keysym", "")) == "Return":
            selected = self.focus_tree.selection()
            item_id = selected[0] if selected else ""
        else:
            item_id = self.focus_tree.identify_row(event.y)
        if item_id not in self.focus_tree_items:
            return "break"
        self.focus_tree.selection_set(item_id)
        self.focus_tree.focus(item_id)
        self._update_preview()
        self._execute_selected()
        return "break"

    def _navigate_mixed_tree_groups(self, event: tk.Event) -> str | None:
        keysym = str(getattr(event, "keysym", ""))
        if keysym not in {"Up", "Down", "Prior", "Next", "Home", "End"}:
            return None
        children = list(self.focus_tree.get_children())
        selectable = [
            item_id for item_id in children if item_id in self.focus_tree_items
        ]
        if len(selectable) == len(children) or not selectable:
            return None
        selected = self.focus_tree.selection()
        current = selected[0] if selected and selected[0] in selectable else None
        if keysym == "Home":
            target_index = 0
        elif keysym == "End":
            target_index = len(selectable) - 1
        elif current is None:
            target_index = 0 if keysym in {"Down", "Next"} else len(selectable) - 1
        else:
            offset = {"Up": -1, "Down": 1, "Prior": -5, "Next": 5}[keysym]
            target_index = max(
                0,
                min(len(selectable) - 1, selectable.index(current) + offset),
            )
        target = selectable[target_index]
        self.focus_tree.selection_set(target)
        self.focus_tree.focus(target)
        self.focus_tree.see(target)
        self._update_preview()
        return "break"

    def _render_work_items(self) -> None:
        self._show_flat_results()
        self.actions_heading_var.set("Work Items")
        self.results.delete(0, tk.END)
        self.displayed_actions = []
        self.displayed_slots = []
        self.displayed_action_rows = []
        selected_context = self._selected_result_context()
        query = self.search_var.get()
        self.displayed_work_items = [
            item
            for item in self.work_item_index.items
            if work_item_matches(
                item,
                query,
                tags=self._work_item_tags(item),
                project_code=self.work_project_filter,
                tag=self.item_tag_filter,
            )
            and self._work_item_belongs_to_context(
                item,
                selected_context,
            )
        ]
        if query.strip():
            self.displayed_work_items.sort(
                key=lambda item: (
                    work_item_search_rank(item, query),
                    item.display_name.casefold(),
                    f"{item.source_id}/{item.relative_folder}".casefold(),
                )
            )
        for item in self.displayed_work_items:
            kind = item.kind_name or "Work item"
            subject = item.subject.replace("-", " ")
            organisation = f"{item.organisation} " if item.organisation else ""
            self.results.insert(tk.END, f"{kind} → {organisation}{subject}")
        count = len(self.displayed_work_items)
        self.results_count_var.set(
            f"{count} work item" if count == 1 else f"{count} work items"
        )
        if count:
            self.results.selection_set(0)
            self.results.activate(0)
            stale_count = sum(
                1 for source in self.work_item_index.sources if source.using_last_known_good
            )
            suffix = f" · {stale_count} source stale" if stale_count else ""
            self.status_var.set(f"{count} Work Items match{suffix}.")
        else:
            if not self.work_item_sources:
                message = "No Work Item sources configured yet."
                status = "No Work Item sources are configured."
            elif self.work_item_refresh.running and not self.work_item_index.sources:
                message = "Refreshing Work Items…"
                status = message
            elif any(source.error for source in self.work_item_index.sources):
                message = "No available Work Items.\nOne or more source folders are unavailable."
                status = "Work Item sources are unavailable."
            else:
                message = "No Work Items match Find and the selected filters."
                details: list[str] = []
                if self.work_project_filter is not None:
                    details.append(f"project: {self.work_project_filter}")
                if self.item_tag_filter is not None:
                    details.append(f"tag: {self.item_tag_filter}")
                suffix = f" · {' · '.join(details)}" if details else ""
                status = f"No Work Items match{suffix}."
            self.results.insert(tk.END, message)
            self.results.itemconfigure(0, foreground=COLORS["muted_text"])
            self.status_var.set(status)
        self._update_preview()

    def _show_flat_results(self) -> None:
        self.actions_heading_var.set(
            "Work Items"
            if self.discovery_scope == DISCOVERY_WORK_ITEMS
            else "Actions"
        )
        if self.results_view == "flat":
            return
        self.focus_tree.pack_forget()
        self.results.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.results_scrollbar.configure(command=self.results.yview)
        self.results_view = "flat"

    def _show_mixed_results(self, view: str) -> None:
        if self.results_view == view:
            return
        self.results.pack_forget()
        self.focus_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.results_scrollbar.configure(command=self.focus_tree.yview)
        self.focus_tree.configure(yscrollcommand=self.results_scrollbar.set)
        self.results_view = view

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
            self.local_work_item_sources_path,
            self.local_work_item_metadata_path,
            self.local_work_item_settings_path,
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
            run_stage("work_items", self._load_work_item_configuration)
            run_stage(
                "palette",
                lambda: self._load_palette_state(render=False),
            )
            run_stage("quick_actions", self._render_command_surface)
            run_stage("results", self._refresh_results)
            self._start_work_item_refresh()
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

    def _reload_after_external_action_change(self) -> None:
        """Reload the launcher and any Configure workspace open beside it."""

        self._reload()
        configuration = getattr(self, "configuration_window", None)
        if configuration is None:
            return
        try:
            exists = bool(configuration.window.winfo_exists())
        except tk.TclError:
            exists = False
        if exists:
            configuration.refresh_from_storage()

    def _execute_selected(self, *, open_folder: bool = False) -> None:
        if self._stop_action_sequence():
            return
        if self.results_view != "flat":
            selected = self.focus_tree.selection()
            reference = (
                self.focus_tree_items.get(selected[0]) if selected else None
            )
            if reference is None:
                self.status_var.set("No Palette item selected")
                return
            self._execute_palette_item(reference, open_folder=open_folder)
            return
        if self.work_items_mode:
            item = self._selected_work_item()
            if item is None:
                self.status_var.set("No Work Item selected")
                return
            target = item.folder_path if open_folder else item.default_open_path
            if not self._open_work_item_target(item, target):
                return
            self.status_var.set(
                f"Opened folder: {item.display_name}"
                if target != item.matching_workbook_path
                else f"Opened workbook: {item.matching_workbook_path.name}"
            )
            return
        action = self._selected_action()
        if action is None:
            self.status_var.set("No action selected")
            return

        self._execute_action(action)

    def _execute_palette_item(
        self,
        reference: PaletteItemReference,
        *,
        open_folder: bool = False,
    ) -> bool:
        if reference.action_id:
            action = next(
                (item for item in self.actions if item.id == reference.action_id),
                None,
            )
            if action is None:
                self.status_var.set(f"Action unavailable: {reference.action_id}")
                return False
            self._execute_action(action)
            return True
        assert reference.work_item_ref is not None
        item = self._work_item_for_reference(reference.work_item_ref)
        if item is None:
            return self._execute_work_item_reference(
                reference.work_item_ref.relative_folder,
                reference.work_item_ref,
            )
        if open_folder:
            if not self._open_work_item_target(item, item.folder_path):
                return False
            self.status_var.set(f"Opened folder: {item.display_name}")
            return True
        return self._execute_work_item_reference(
            item.display_name,
            reference.work_item_ref,
        )

    def _execute_action(self, action: Action) -> None:
        if getattr(self, "sequence_run_plan", None) is not None:
            self.status_var.set("A sequence is running; stop it before another Action.")
            return
        destination = self.source_foreground_handle
        self.source_foreground_handle = None
        workspace_component = getattr(self, "workspace_component", None)
        try:
            message = execute_action(
                action,
                clipboard_setter=self._set_clipboard,
                clipboard_getter=self._get_clipboard_text,
                input_provider=self._ask_for_action_input,
                selected_text=self._workspace_text() or self.captured_selection,
                input_text=self._workspace_text(),
                output_setter=self._set_workspace_text,
                file_preview_setter=(
                    workspace_component.show_file_preview
                    if workspace_component is not None
                    else None
                ),
                credential_paster=lambda selected: self._paste_credential_action(
                    selected,
                    destination,
                ),
                opener=self._open_action_target,
                sequence_runner=self._run_action_sequence,
            )
            if action.type == "copy_text":
                message = self._paste_saved_text_if_destination(destination)
            self.status_var.set(message)
        except ActionError as exc:
            self.status_var.set("Action failed")
            messagebox.showerror("Context Palette", str(exc))
            LOGGER.exception("Action failed: id=%s type=%s", action.id, action.type)

    def _run_action_sequence(self, action: Action) -> str:
        if getattr(self, "sequence_run_plan", None) is not None:
            raise ActionError("Another Action sequence is already running.")
        try:
            plan = resolve_sequence_steps(
                action.sequence_steps,
                self.actions,
                sequence_id=action.id,
            )
        except ActionSequenceError as exc:
            raise ActionError(str(exc)) from exc
        confirmation = (
            f'Run sequence "{action.title}"?\n\n'
            + "\n".join(plan.preview_lines)
            + "\n\nOpened targets and started scripts cannot be undone. "
            "Waits are delays, not completion checks. Stop prevents only "
            "steps that have not started."
        )
        if not messagebox.askyesno(
            "Run Action sequence?",
            confirmation,
            icon=messagebox.WARNING,
            parent=self.root,
        ):
            return "Action sequence cancelled."
        self.sequence_run_plan = plan
        self.sequence_run_index = 0
        self.sequence_started_actions = 0
        self._cancel_scheduled_hide()
        self._set_sequence_attention(True)
        panel = getattr(self, "action_discovery_panel", None)
        if panel is not None:
            panel.render_control_state(sequence_running=True)
        elif hasattr(self, "run_button"):
            self.run_button.configure(text="Stop remaining", style="Accent.TButton")
        self.sequence_after_id = self.root.after(0, self._run_next_sequence_step)
        return "Action sequence approved; starting step 1."

    def _run_next_sequence_step(self) -> None:
        self.sequence_after_id = None
        plan = self.sequence_run_plan
        if plan is None:
            return
        if self.sequence_run_index >= len(plan.steps):
            started = self.sequence_started_actions
            self._finish_action_sequence(
                f"Sequence finished dispatching {started} Action(s)."
            )
            return
        step_number = self.sequence_run_index + 1
        step = plan.steps[self.sequence_run_index]
        self.sequence_run_index += 1
        if isinstance(step, ResolvedWaitStep):
            seconds = step.milliseconds / 1000
            self.status_var.set(
                f"Sequence step {step_number}/{len(plan.steps)}: waiting "
                f"{seconds:g} seconds. Choose Stop remaining to cancel pending steps."
            )
            self.sequence_after_id = self.root.after(
                step.milliseconds,
                self._run_next_sequence_step,
            )
            return
        assert isinstance(step, ResolvedActionStep)
        selected = Action(
            id=step.action_id,
            title=step.title,
            context="General",
            type=step.action_type,
            value=step.value,
            arguments=step.arguments,
            working_directory=step.working_directory,
        )
        try:
            execute_action(selected, opener=self._open_action_target)
        except ActionError as exc:
            self._finish_action_sequence(
                f"Sequence stopped at step {step_number}: {exc}",
                error=True,
            )
            return
        self.sequence_started_actions += 1
        self._set_sequence_attention(True)
        self.status_var.set(
            f'Sequence step {step_number}/{len(plan.steps)}: dispatched "{step.title}".'
        )
        self.sequence_after_id = self.root.after(0, self._run_next_sequence_step)

    def _stop_action_sequence(self) -> bool:
        if getattr(self, "sequence_run_plan", None) is None:
            return False
        if self.sequence_after_id is not None:
            try:
                self.root.after_cancel(self.sequence_after_id)
            except tk.TclError:
                pass
        started = self.sequence_started_actions
        self._finish_action_sequence(
            f"Sequence stopped. Started {started} Action(s); remaining steps were skipped."
        )
        return True

    def _finish_action_sequence(self, message: str, *, error: bool = False) -> None:
        self.sequence_run_plan = None
        self.sequence_after_id = None
        self.sequence_run_index = 0
        self._set_sequence_attention(False)
        panel = getattr(self, "action_discovery_panel", None)
        if panel is not None:
            panel.render_control_state(sequence_running=False)
        elif hasattr(self, "run_button"):
            self.run_button.configure(text="Run", style="Accent.TButton")
        self.status_var.set(message)
        if error:
            messagebox.showerror("Action sequence stopped", message, parent=self.root)

    def _set_sequence_attention(self, active: bool) -> None:
        """Keep an attended sequence and its Stop control visible."""

        try:
            if active:
                self.root.deiconify()
                self.root.lift()
            self.root.attributes("-topmost", active)
        except (AttributeError, tk.TclError):
            pass

    def _open_action_target(self, action: Action) -> None:
        """Open Markdown actions in-app and delegate every other safe target."""
        if action.type == "open_file":
            target = Path(action.value).expanduser()
            if not target.is_absolute():
                target = Path.cwd() / target
            if target.suffix.casefold() == ".md":
                if not target.is_file():
                    raise ActionError(f"File does not exist: {target}")
                HelpWindow(
                    self.root,
                    target,
                    title=target.stem.replace("_", " ").title(),
                )
                return
        open_action_target(action)

    def _paste_saved_text_if_destination(
        self,
        destination: int | None = None,
    ) -> str:
        if destination is None:
            destination = self.source_foreground_handle
        self.source_foreground_handle = None
        if destination is None:
            _log_automatic_paste("saved_text", "clipboard_only", "no_destination")
            return "Copied text. No fresh destination was captured; paste manually with Ctrl+V."
        self.root.withdraw()

        def paste_into_destination() -> None:
            if not focus_window(destination):
                _log_automatic_paste(
                    "saved_text",
                    "failed",
                    "destination_unavailable",
                    level=logging.WARNING,
                )
                self.show_window()
                self.status_var.set("Text copied, but automatic paste failed.")
                messagebox.showerror(
                    "Text copied, but not pasted",
                    "The captured destination window is no longer available. "
                    "The text remains on the clipboard; paste it manually with Ctrl+V.",
                    parent=self.root,
                )
                return
            try:
                send_paste_shortcut()
            except Exception as exc:
                LOGGER.exception(
                    "Automatic paste: category=saved_text outcome=failed "
                    "reason=dispatch_error",
                )
                self.show_window()
                self.status_var.set("Text copied, but automatic paste failed.")
                messagebox.showerror(
                    "Text copied, but not pasted",
                    "Windows could not send the paste command. The text remains "
                    "on the clipboard; paste it manually with Ctrl+V.\n\n"
                    f"Technical detail: {exc}",
                    parent=self.root,
                )
                return
            _log_automatic_paste("saved_text", "success", "dispatched")

        self.root.after(120, paste_into_destination)
        return "Text copied; returning to the captured destination to paste it."

    def _paste_credential_action(
        self,
        action: Action,
        destination: int | None = None,
    ) -> str:
        if destination is None:
            destination = self.source_foreground_handle
        self.source_foreground_handle = None
        if destination is None:
            _log_automatic_paste(
                "protected_credential",
                "failed",
                "no_destination",
                level=logging.WARNING,
            )
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
                "The password will not be shown or added to clipboard history. "
                "After 15 seconds, Context Palette will restore the previous "
                "plain-text clipboard value unless something newer was copied."
            ),
            parent=self.root,
        ):
            _log_automatic_paste(
                "protected_credential",
                "cancelled",
                "user_cancelled",
            )
            return "Credential paste cancelled."
        try:
            self._finish_protected_clipboard()
            if self.protected_clipboard_sequence is not None:
                raise CredentialAccessError(
                    "Windows could not finish the previous protected clipboard operation. "
                    "Try again."
                )
            secret = read_windows_credential(action.value)
            transaction = begin_protected_clipboard_transaction(secret.password)
        except CredentialAccessError as exc:
            raise ActionError(str(exc)) from exc
        sequence = transaction.sequence_number
        previous_clipboard = transaction.snapshot
        self.protected_clipboard_sequence = transaction.sequence_number
        self.protected_clipboard_snapshot = transaction.snapshot
        self.root.withdraw()

        def paste_into_destination() -> None:
            if not focus_window(destination):
                _log_automatic_paste(
                    "protected_credential",
                    "failed",
                    "destination_unavailable",
                    level=logging.WARNING,
                )
                self._finish_protected_clipboard(sequence)
                self.show_window()
                messagebox.showerror(
                    "Credential paste cancelled",
                    "The captured destination window is no longer available.",
                    parent=self.root,
                )
                return
            try:
                send_paste_shortcut()
            except Exception as exc:
                LOGGER.exception(
                    "Automatic paste: category=protected_credential outcome=failed "
                    "reason=dispatch_error",
                )
                restored = self._finish_protected_clipboard(sequence)
                recovery_pending = self.protected_clipboard_sequence == sequence
                self.show_window()
                self.status_var.set("Protected credential paste was cancelled.")
                messagebox.showerror(
                    "Credential paste cancelled",
                    "Windows could not send the paste command. Context Palette "
                    + (
                        "restored the previous clipboard text.\n\n"
                        if restored and previous_clipboard.text is not None
                        else (
                            "could not access the protected clipboard yet; "
                            "cleanup will retry.\n\n"
                            if recovery_pending
                            else "removed the protected clipboard item or left "
                            "newer clipboard content untouched.\n\n"
                        )
                    )
                    + f"Technical detail: {exc}",
                    parent=self.root,
                )
                return
            _log_automatic_paste(
                "protected_credential",
                "success",
                "dispatched",
            )

        self.root.after(
            15_000,
            lambda: self._finish_protected_clipboard(sequence),
        )
        self.root.after(120, paste_into_destination)
        return "Protected credential paste approved; returning to the destination."

    def _edit_selected(self) -> None:
        action = self._selected_action()
        if action is not None:
            self._show_configuration(
                initial_action_id=action.id,
                start_action_edit=True,
            )
            return
        item = self._selected_work_item()
        if item is None:
            self.status_var.set("No item selected")
            return
        self._show_configuration(
            initial_tab="work_items",
            initial_work_item_key=work_item_metadata_key(
                item.source_id,
                item.relative_folder,
            ),
        )

    def _execute_slot(self, slot: int, event: tk.Event) -> str | None:
        reference = self.slot_items.get(slot)
        if reference is None:
            self.status_var.set(f"No item in slot {slot_display_number(slot)}")
            return "break"
        self._execute_palette_item(reference)
        return "break"

    def _move_selection(self, offset: int, event: tk.Event) -> str:
        result_count = (
            len(self.displayed_work_items)
            if self.work_items_mode
            else len(self.displayed_action_rows)
        )
        if not result_count:
            return "break"

        selected = self.results.curselection()
        current = selected[0] if selected else 0
        return self._select_index(current + offset, event)

    def _select_index(self, index: int, _event: tk.Event) -> str:
        result_count = (
            len(self.displayed_work_items)
            if self.work_items_mode
            else len(self.displayed_action_rows)
        )
        if not result_count:
            return "break"

        bounded_index = max(0, min(index, result_count - 1))
        if (
            not self.work_items_mode
            and self.displayed_action_rows[bounded_index][0] is None
        ):
            selected = self.results.curselection()
            current = selected[0] if selected else 0
            direction = -1 if index < current else 1
            candidate = bounded_index + direction
            if not 0 <= candidate < result_count:
                candidate = bounded_index - direction
            if not 0 <= candidate < result_count:
                return "break"
            bounded_index = candidate
        self.results.selection_clear(0, tk.END)
        self.results.selection_set(bounded_index)
        self.results.activate(bounded_index)
        self.results.see(bounded_index)
        self._update_preview()
        return "break"

    def _selected_action(self) -> Action | None:
        if self.results_view != "flat":
            selected = self.focus_tree.selection()
            return self.focus_tree_actions.get(selected[0]) if selected else None
        if self.work_items_mode:
            return None
        selected = self.results.curselection()
        if not selected:
            return None
        index = selected[0]
        if index >= len(self.displayed_action_rows):
            return None
        action, _slot = self.displayed_action_rows[index]
        return action

    def _selected_focus_item(self) -> PaletteItemReference | None:
        if self.results_view == "flat":
            return None
        selected = self.focus_tree.selection()
        return self.focus_tree_items.get(selected[0]) if selected else None

    def _selected_work_item(self) -> DiscoveredWorkItem | None:
        if self.results_view != "flat":
            reference = self._selected_focus_item()
            return (
                self._work_item_for_reference(reference.work_item_ref)
                if reference is not None and reference.work_item_ref is not None
                else None
            )
        if not self.work_items_mode:
            return None
        selected = self.results.curselection()
        if not selected or selected[0] >= len(self.displayed_work_items):
            return None
        return self.displayed_work_items[selected[0]]

    def _update_preview(self) -> None:
        selected_reference = self._selected_focus_item()
        panel = getattr(self, "action_discovery_panel", None)
        if panel is not None:
            selected_work_item = self._selected_work_item()
            selected_action = self._selected_action()
            panel.render_control_state(
                work_item=(
                    True
                    if selected_work_item is not None
                    else False
                    if selected_action is not None
                    else None
                ),
                has_selection=(
                    selected_work_item is not None or selected_action is not None
                ),
                sequence_running=getattr(self, "sequence_run_plan", None) is not None,
            )
        if self.work_items_mode and self.results_view == "flat":
            item = self._selected_work_item()
            if item is None:
                self.action_info_full = (
                    "Select a Work Item to see its source and open target."
                )
                self.status_var.set(
                    "Select an Action or Work Item to see Input → Effect before Run or Open."
                )
                return
            self.action_info_full, summary = self._work_item_preview(item)
            self.status_var.set(summary)
            return
        focus_reference = self._selected_focus_item()
        if focus_reference is not None and focus_reference.work_item_ref is not None:
            item = self._work_item_for_reference(focus_reference.work_item_ref)
            if item is None:
                self.action_info_full = (
                    "Unavailable Work Item: "
                    f"{focus_reference.work_item_ref.relative_folder}\n"
                    "Refresh Work Items or repair its personal source configuration."
                )
                self.status_var.set(
                    "Input: needed—Work Item source unavailable → "
                    "Effect: Run will stop without changes"
                )
                return
            self.action_info_full, summary = self._work_item_preview(item)
            self.status_var.set(summary)
            return
        action = self._selected_action()
        if action is None:
            self.action_info_full = (
                "Select an Action or Work Item to see what it will do."
            )
            if self.results_count_var.get().startswith("0 "):
                return
            self.status_var.set(
                "Select an Action or Work Item to see Input → Effect before Run or Open."
            )
            return
        preview = build_action_preview(
            action,
            workspace_has_text=bool(self._workspace_text()),
            captured_selection_available=bool(self.captured_selection),
            destination_available=self.source_foreground_handle is not None,
            available_actions=self.actions,
        )
        self.action_info_full = preview.full_text(action)
        message = preview.summary
        self.status_var.set(message[:217].rstrip() + "…" if len(message) > 220 else message)

    def _work_item_preview(self, item: DiscoveredWorkItem) -> tuple[str, str]:
        tags = self._work_item_tags(item)
        if item.matching_workbook_path is not None:
            effect = f"open workbook: {item.matching_workbook_path.name}"
            compact_effect = (
                "open workbook: "
                f"{compact_preview_value(item.matching_workbook_path.name)}"
            )
            recovery = "The adjacent folder command can open the Work Item folder instead."
        else:
            effect = "open the Work Item folder"
            compact_effect = effect
            recovery = "No exact matching workbook is currently available."
        full_effect = effect[0].upper() + effect[1:]
        detail = (
            f"{item.display_name}\n\n"
            "Type\nWork Item\n\n"
            "Input\nNo runtime input.\n\n"
            f"Effect\n{full_effect}.\n\n"
            f"Source\n{item.source_name}\n\n"
            f"Kind / organisation\n"
            f"{item.kind_name or 'Work item'} · {item.organisation or 'Unparsed'}\n\n"
            f"Project codes\n{', '.join(item.project_codes) or '(none)'}\n\n"
            f"Tags\n{', '.join(tags) or '(none)'}\n\n"
            f"Recovery / limitations\n{recovery}"
        )
        return detail, format_preview_summary("none", compact_effect)

    def _focus_tree_tooltip_text(self, item_id: str) -> str:
        reference = self.focus_tree_items.get(item_id)
        slot = next(
            (
                number
                for number, candidate in self.slot_items.items()
                if candidate == reference
            ),
            None,
        )
        shortcut = (
            f"Shortcut: Shift+{slot_display_number(slot)}\n"
            if slot is not None
            else ""
        )
        action = self.focus_tree_actions.get(item_id)
        if action is None:
            if reference is None or reference.work_item_ref is None:
                return ""
            item = self._work_item_for_reference(reference.work_item_ref)
            if item is None:
                return (
                    f"Unavailable Work Item: {reference.work_item_ref.relative_folder}\n"
                    f"{shortcut}Source: {reference.work_item_ref.source_id}"
                )
            return (
                f"{item.display_name}\n"
                f"{shortcut}"
                f"Source: {item.source_name}\n"
                f"Tags: {', '.join(self._work_item_tags(item)) or '(none)'}\n"
                "Type: Work Item"
            )
        return (
            f"{action.title}\n"
            f"{shortcut}"
            + (
                f"Description: {action.description}\n"
                if action.description
                else ""
            )
            + f"Contexts: {', '.join(action.effective_contexts) or 'General only'}\n"
            f"Tags: {', '.join(action.effective_tags) or '(none)'}\n"
            f"Type: {ACTION_TYPES[action.type].display_label}\n"
            f"State: {action.state}"
        )

    def _workspace_text(self) -> str:
        return self.workspace_component.get_text()

    def _set_workspace_text(self, value: str) -> None:
        self.workspace_component.set_text(value)

    def _paste_into_workspace(self) -> None:
        self.workspace_component.replace_with_clipboard()

    def _sync_workspace_from_clipboard(self) -> None:
        self.workspace_component.sync_from_clipboard()

    def _sync_workspace_from_clipboard_if_safe(self) -> None:
        if self.protected_clipboard_sequence is not None:
            self._finish_protected_clipboard()
        if self.protected_clipboard_sequence is None:
            self._sync_workspace_from_clipboard()

    def _copy_workspace_to_clipboard(self) -> None:
        self.workspace_component.copy_all()

    def _extract_text_from_image(self, candidate: str) -> None:
        if self.ocr.running:
            self.status_var.set("Image text extraction is already running.")
            return

        try:
            source = image_source_from_text(candidate)
            if source is None:
                source = clipboard_image_source()
        except OcrError as exc:
            self._show_ocr_error(exc)
            return
        except Exception:
            LOGGER.exception("Unexpected local OCR source-acquisition failure")
            self._show_ocr_error(
                OcrError(
                    "The optional image component could not read the selected source. "
                    "Nothing was changed."
                )
            )
            return

        if source is None:
            selected = filedialog.askopenfilename(
                parent=self.root,
                title="Choose an image to extract text from",
                filetypes=(
                    ("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp"),
                    ("All files", "*.*"),
                ),
            )
            if not selected:
                self.status_var.set("Image text extraction cancelled.")
                return
            try:
                source = image_source_from_path(Path(selected))
            except OcrSourceError as exc:
                self._show_ocr_error(exc)
                return

        expected_text = self.workspace_component.raw_text()
        started = self.ocr.start(
            source,
            lambda result, error: self._accept_ocr_result(
                source.label,
                expected_text,
                result,
                error,
            ),
        )
        if not started:
            self.status_var.set("Image text extraction is already running.")
            return
        self.workspace_component.set_ocr_running(True)
        self.status_var.set(f"Extracting text from {source.label}…")
        if getattr(self, "ocr_after_id", None) is None:
            self.ocr_after_id = self.root.after(100, self._poll_ocr)

    def _accept_ocr_result(
        self,
        source_label: str,
        expected_text: str,
        result: OcrResult | None,
        error: OcrError | None,
    ) -> None:
        self.workspace_component.set_ocr_running(False)
        if error is not None:
            self._show_ocr_error(error)
            return
        if result is None or not result.text.strip():
            self.status_var.set("No readable text was found; Input / Output was unchanged.")
            messagebox.showinfo(
                "No text found",
                "Context Palette did not find readable text in the image.\n\n"
                "Input / Output and the clipboard were left unchanged.",
                parent=self.root,
            )
            return
        placement = self.workspace_component.apply_ocr_text(
            result.text,
            source_label=source_label,
            expected_text=expected_text,
        )
        if placement is None:
            self.status_var.set("Extracted text was not placed; Input / Output was unchanged.")
            return
        verb = "Replaced" if placement == "replace" else "Appended to"
        self.status_var.set(
            f"{verb} Input / Output with {result.line_count} extracted line(s) "
            f"in {result.elapsed_seconds:.1f} seconds."
        )

    def _show_ocr_error(self, error: OcrError) -> None:
        message = str(error)
        if isinstance(error, OcrUnavailableError):
            message += (
                "\n\nOCR is an optional local component. Run "
                "setup-ocr-context-palette.bat from the Context Palette folder. "
                "It installs only into that folder and does not require administrator rights."
            )
        self.status_var.set("Image text extraction could not start.")
        messagebox.showerror(
            "Could not extract text",
            message,
            parent=self.root,
        )

    def _set_clipboard(self, value: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update()
        self.protected_clipboard_sequence = None
        self.protected_clipboard_snapshot = None

    def _finish_protected_clipboard(
        self,
        sequence: int | None = None,
        retry_count: int = 0,
    ) -> bool:
        current = self.protected_clipboard_sequence
        if sequence is not None and current != sequence:
            return False
        target = sequence if sequence is not None else current
        if target is None:
            return False
        snapshot = (
            getattr(self, "protected_clipboard_snapshot", None)
            or ClipboardTextSnapshot()
        )
        result = restore_clipboard_text_if_unchanged(target, snapshot)
        if result is None and retry_count < 5:
            try:
                self.root.after(
                    1_000,
                    lambda: self._finish_protected_clipboard(target, retry_count + 1),
                )
            except (AttributeError, tk.TclError):
                pass
        elif result is None:
            try:
                self.status_var.set("Protected clipboard cleanup still needs attention.")
                messagebox.showwarning(
                    "Protected clipboard cleanup needs attention",
                    "Windows kept the clipboard busy, so Context Palette could not "
                    "finish cleanup. Copy harmless text, reopen Context Palette, "
                    "and do not quit until this warning no longer appears.",
                    parent=self.root,
                )
            except (AttributeError, tk.TclError):
                pass
        if result is not None and self.protected_clipboard_sequence == target:
            self.protected_clipboard_sequence = None
            self.protected_clipboard_snapshot = None
        return result is True

    def _get_clipboard_text(self) -> str:
        try:
            return self.root.clipboard_get()
        except tk.TclError as exc:
            raise ActionError("The clipboard does not contain text.") from exc

    def _ask_for_action_input(self, prompt: str) -> str | None:
        return simpledialog.askstring("Build URL", prompt, parent=self.root)

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
            self.available_context_names,
            self.local_actions_path,
            self.inbox_path,
            self._reload_after_external_action_change,
            self._show_harvest,
            shared_contexts_path=self.contexts_path,
            local_contexts_path=self.local_contexts_path,
        )

    def _show_harvest(self) -> None:
        HarvestWindow(
            self.root,
            actions=self.actions,
            context_names=self.available_context_names,
            focus_context=self.palette_state.focus_context,
            actions_path=self.local_actions_path,
            shared_contexts_path=self.contexts_path,
            local_contexts_path=self.local_contexts_path,
            on_change=self._reload_after_external_action_change,
        )

    def _show_help(self) -> None:
        HelpWindow(
            self.root,
            DOCUMENTATION_DIR / "HELP.md",
            related_actions=(("Cheat sheets", self._show_cheatsheets),),
        )

    def _show_shortcuts(self) -> None:
        HelpWindow(
            self.root,
            DOCUMENTATION_DIR / "SHORTCUTS.md",
            title="Context Palette Keyboard Shortcuts",
        )

    def _show_configuration(
        self,
        *,
        initial_tab: str = "start",
        initial_action_id: str | None = None,
        initial_work_item_key: str | None = None,
        start_work_item_creation: bool = False,
        start_action_creation: bool = False,
        initial_action_suggestion: ActionCreationSuggestion | None = None,
        start_action_edit: bool = False,
    ) -> None:
        if getattr(self, "_configuration_recovery_required", False):
            messagebox.showerror(
                "Restart required for recovery",
                (
                    "Configure is unavailable until Context Palette restarts and "
                    "startup recovery finishes."
                ),
                parent=self.root,
            )
            return
        existing = getattr(self, "configuration_window", None)
        if existing is not None:
            try:
                exists = bool(existing.window.winfo_exists())
            except tk.TclError:
                exists = False
            if exists:
                existing.show(
                    initial_tab=initial_tab,
                    initial_action_id=initial_action_id,
                    initial_work_item_key=initial_work_item_key,
                    start_work_item_creation=start_work_item_creation,
                    start_action_creation=start_action_creation,
                    initial_action_suggestion=initial_action_suggestion,
                    start_action_edit=start_action_edit,
                )
                return
        self.configuration_window = ConfigurationWindow(
            self.root,
            actions=self.actions,
            local_action_ids=self.local_action_ids,
            shared_actions_path=self.actions_path,
            local_actions_path=self.local_actions_path,
            contexts_path=self.contexts_path,
            local_contexts_path=self.local_contexts_path,
            command_surface_path=self.command_surface_path,
            local_command_surface_path=self.local_command_surface_path,
            palette_path=self.palette_path,
            work_item_sources_path=self.local_work_item_sources_path,
            work_item_metadata_path=self.local_work_item_metadata_path,
            work_item_settings_path=self.local_work_item_settings_path,
            work_item_sources=self.work_item_sources,
            work_item_metadata=self.work_item_metadata,
            work_item_index=self.work_item_index,
            on_change=self._reload,
            focus_context=self.palette_state.focus_context,
            initial_tab=initial_tab,
            initial_action_id=initial_action_id,
            initial_work_item_key=initial_work_item_key,
            start_work_item_creation=start_work_item_creation,
            start_action_creation=start_action_creation,
            initial_action_suggestion=initial_action_suggestion,
            start_action_edit=start_action_edit,
            data_paths=self.data_paths,
            on_restore_complete=self._reload,
            on_restore_recovery_required=self._require_restore_recovery_restart,
        )

    def _require_restore_recovery_restart(self) -> None:
        """Block further interaction after an incomplete restore rollback."""

        self._configuration_recovery_required = True
        self.status_var.set("Restart required so restore recovery can finish.")
        self.root.withdraw()
        if not self._active_work_item_writes():
            self.quit_app()

    def _show_work_item_creation(self) -> None:
        self._show_configuration(
            initial_tab="work_items",
            start_work_item_creation=True,
        )

    def _show_action_creation(self) -> str:
        self._show_configuration(
            initial_tab="actions",
            start_action_creation=True,
        )
        return "break"

    def _create_action_from_workspace(self, source_text: str) -> None:
        suggestion = suggest_action_from_text(source_text)
        if suggestion is None:
            messagebox.showinfo(
                "No obvious Action found",
                (
                    "Context Palette could not confidently identify one clear "
                    "website, file, folder, or application in Input / Output.\n\n"
                    "Select one complete target and try again. Use + Action when "
                    "you want to choose the Action type yourself."
                ),
                parent=self.root,
            )
            return
        self._show_configuration(
            initial_tab="actions",
            initial_action_suggestion=suggestion,
        )

    def _send_workspace_to_work_item_inbox(
        self,
        item: DiscoveredWorkItem | None = None,
    ) -> None:
        selected = item or self._selected_work_item()
        if selected is None:
            self.status_var.set("Select a Work Item before sending to Inbox.")
            return
        if self.work_item_inbox.running:
            self.status_var.set("An Inbox update is already running.")
            return
        text = self._workspace_text()
        try:
            entry = create_work_item_inbox_entry(
                text,
                source=self._work_item_inbox_source(text),
            )
        except WorkItemInboxError as exc:
            self.status_var.set(str(exc))
            return

        expected_workbook = (
            selected.folder_path / f"{selected.folder_path.name}.xlsx"
        )
        workbook = selected.matching_workbook_path
        if workbook is not None and not workbook.is_file():
            workbook = None
        if workbook is None and expected_workbook.is_file():
            workbook = expected_workbook

        template: Path | None = None
        missing_workbook = workbook is None
        if missing_workbook:
            try:
                settings = load_work_item_creation_settings(
                    self.local_work_item_settings_path
                )
            except WorkItemStorageError as exc:
                messagebox.showerror(
                    "Work Item Inbox",
                    f"The generic template setting could not be loaded.\n\n{exc}",
                    parent=self.root,
                )
                return
            template = settings.template_path
            if template is None or not template.is_file():
                if messagebox.askyesno(
                    "Generic template required",
                    "This Work Item has no matching workbook, and no available "
                    "generic Excel template is configured.\n\n"
                    "Open Work Items configuration now?",
                    parent=self.root,
                ):
                    self._show_configuration(initial_tab="work_items")
                return
            if not messagebox.askyesno(
                "Create matching workbook?",
                "This Work Item has no matching workbook.\n\n"
                f"Create {expected_workbook.name} from the generic template "
                "and send Input / Output to its Inbox?",
                parent=self.root,
            ):
                self.status_var.set("Inbox send cancelled; no workbook was created.")
                return

        self.send_work_item_inbox_button.configure(state=tk.DISABLED)
        started = self.work_item_inbox.start(
            selected.folder_path,
            workbook,
            template,
            entry,
            lambda result, error: self._complete_work_item_inbox_send(
                selected,
                result,
                error,
                missing_workbook,
            ),
        )
        if not started:
            self.send_work_item_inbox_button.configure(state=tk.NORMAL)
            self.status_var.set("An Inbox update is already running.")
            return
        self.status_var.set(f"Sending Input / Output to {selected.display_name}…")

    def _work_item_inbox_source(self, text: str) -> str:
        if self.captured_selection == text and self.source_foreground_handle:
            title = " ".join(window_title(self.source_foreground_handle).split())
            if title:
                return title
            return "Clipboard"
        return "Input / Output"

    def _copy_workspace_file_to_work_item(
        self,
        item: DiscoveredWorkItem | None = None,
    ) -> None:
        selected = item or self._selected_work_item()
        if selected is None:
            self.status_var.set("Select a Work Item before copying a file.")
            return
        if self.work_item_file_copy.running:
            self.status_var.set("A Work Item file copy is already running.")
            return
        try:
            source = file_path_from_workspace(self._workspace_text())
        except WorkItemFileCopyError as exc:
            self.status_var.set(str(exc))
            messagebox.showerror(
                "File could not be copied",
                str(exc),
                parent=self.root,
            )
            return

        self.copy_file_to_work_item_button.configure(state=tk.DISABLED)
        started = self.work_item_file_copy.start(
            source,
            selected.folder_path,
            lambda result, error: self._complete_work_item_file_copy(
                selected,
                result,
                error,
            ),
        )
        if not started:
            self.copy_file_to_work_item_button.configure(state=tk.NORMAL)
            self.status_var.set("A Work Item file copy is already running.")
            return
        self.status_var.set(
            f"Copying {source.name} to {selected.display_name}…"
        )

    def _complete_work_item_file_copy(
        self,
        item: DiscoveredWorkItem,
        result: WorkItemFileCopyResult | None,
        error: WorkItemFileCopyError | None,
    ) -> None:
        self.copy_file_to_work_item_button.configure(state=tk.NORMAL)
        if error is not None:
            self.status_var.set("The file could not be copied to the Work Item.")
            messagebox.showerror(
                "File could not be copied",
                str(error),
                parent=self.root,
            )
            return
        if result is None:
            self.status_var.set("The Work Item file copy returned no result.")
            return
        self.status_var.set(
            f"Copied {result.destination_path.name} to {item.display_name}."
        )

    def _complete_work_item_inbox_send(
        self,
        item: DiscoveredWorkItem,
        result: WorkItemInboxResult | None,
        error: WorkItemInboxError | None,
        refresh_work_items: bool,
    ) -> None:
        self.send_work_item_inbox_button.configure(state=tk.NORMAL)
        if error is not None:
            self.status_var.set("The Work Item Inbox could not be updated.")
            messagebox.showerror(
                "Work Item Inbox could not be updated",
                str(error),
                parent=self.root,
            )
            if refresh_work_items:
                self._start_work_item_refresh()
            return
        if result is None:
            self.status_var.set("The Work Item Inbox returned no result.")
            return
        sheet_note = " A new Inbox sheet was created." if result.created_sheet else ""
        self.status_var.set(
            f"Sent Input / Output to {item.display_name}, Inbox row {result.row}."
            f"{sheet_note}"
        )
        if result.created_workbook or refresh_work_items:
            self._start_work_item_refresh()

    def _show_action_configuration(self, action: Action) -> None:
        self._show_configuration(
            initial_tab="actions",
            initial_action_id=action.id,
        )

    def _guard_action_separator_click(self, event: tk.Event) -> str | None:
        if self.work_items_mode or self.results_view != "flat":
            return None
        index = self.results.nearest(event.y)
        bounds = self.results.bbox(index)
        if (
            bounds is not None
            and bounds[1] <= event.y < bounds[1] + bounds[3]
            and index < len(self.displayed_action_rows)
            and self.displayed_action_rows[index][0] is None
        ):
            self.results.selection_clear(0, tk.END)
            self._update_preview()
            return "break"
        return None

    def _configure_flat_action_from_event(self, event: tk.Event) -> str:
        index = self.results.nearest(event.y)
        bounds = self.results.bbox(index)
        result_count = (
            len(self.displayed_work_items)
            if self.work_items_mode
            else len(self.displayed_action_rows)
        )
        if (
            bounds is None
            or not (bounds[1] <= event.y < bounds[1] + bounds[3])
            or index >= result_count
        ):
            return "break"
        self.results.selection_clear(0, tk.END)
        self.results.selection_set(index)
        self.results.activate(index)
        self._update_preview()
        if self.work_items_mode:
            self._show_work_item_menu(event, self.displayed_work_items[index])
            return "break"
        action, _slot = self.displayed_action_rows[index]
        if action is None:
            return "break"
        self._show_action_configuration(action)
        return "break"

    def _show_work_item_menu(
        self,
        event: tk.Event,
        item: DiscoveredWorkItem,
    ) -> None:
        menu = tk.Menu(self.root, tearoff=False)
        if item.matching_workbook_path is not None:
            menu.add_command(
                label="Open workbook",
                command=lambda: self._open_work_item_target(
                    item,
                    item.matching_workbook_path,
                ),
            )
        menu.add_command(
            label="Open work-item folder",
            command=lambda: self._open_work_item_target(item, item.folder_path),
        )
        source = next(
            (source for source in self.work_item_sources if source.id == item.source_id),
            None,
        )
        if source is not None:
            menu.add_command(
                label="Open source folder",
                command=lambda: self._open_work_item_target(item, source.workitems_path),
            )
        menu.add_separator()
        menu.add_command(
            label="Send Input / Output to Inbox",
            command=lambda: self._send_workspace_to_work_item_inbox(item),
        )
        menu.add_command(
            label="Copy file from Input / Output",
            command=lambda: self._copy_workspace_file_to_work_item(item),
        )
        menu.add_separator()
        menu.add_command(
            label="Edit tags & contexts…",
            command=lambda: self._show_configuration(
                initial_tab="work_items",
                initial_work_item_key=work_item_metadata_key(
                    item.source_id,
                    item.relative_folder,
                ),
            ),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_work_item_target(self, item: DiscoveredWorkItem, target: Path) -> bool:
        action_type = (
            "open_file"
            if item.matching_workbook_path is not None
            and target == item.matching_workbook_path
            else "open_folder"
        )
        try:
            open_action_target(
                Action(
                    f"work-item:{item.source_id}:{item.relative_folder}",
                    item.display_name,
                    "General",
                    action_type,
                    str(target),
                    "Active",
                )
            )
        except ActionError as exc:
            self.status_var.set("Work Item target could not be opened.")
            messagebox.showerror("Work Item could not be opened", str(exc), parent=self.root)
            return False
        self.status_var.set(f"Opened: {target.name}")
        return True

    def _configure_focus_action_from_event(self, event: tk.Event) -> str:
        item_id = self.focus_tree.identify_row(event.y)
        action = self.focus_tree_actions.get(item_id)
        reference = self.focus_tree_items.get(item_id)
        if action is None and (reference is None or reference.work_item_ref is None):
            return "break"
        self.focus_tree.selection_set(item_id)
        self.focus_tree.focus(item_id)
        self._update_preview()
        if action is not None:
            self._show_action_configuration(action)
        else:
            assert reference is not None and reference.work_item_ref is not None
            item = self._work_item_for_reference(reference.work_item_ref)
            if item is not None:
                self._show_work_item_menu(event, item)
            else:
                self._show_configuration(
                    initial_tab="work_items",
                    initial_work_item_key=work_item_metadata_key(
                        reference.work_item_ref.source_id,
                        reference.work_item_ref.relative_folder,
                    ),
                )
        return "break"

    def _show_focus_configuration(self) -> None:
        self._show_configuration(initial_tab="contexts")

    def _show_cheatsheets(self) -> None:
        try:
            sheets = load_cheatsheets(self.cheatsheets_dir)
        except CheatSheetError as exc:
            messagebox.showerror("Context Palette", str(exc))
            return

        CheatSheetWindow(
            self.root,
            sheets,
            self.local_actions_path,
            self._reload_after_external_action_change,
            shared_contexts_path=self.contexts_path,
            local_contexts_path=self.local_contexts_path,
        )

    def _handle_keypress(self, event: tk.Event) -> str | None:
        keysym = str(event.keysym)

        navigation = {
            "Up": -1,
            "Down": 1,
            "Prior": -5,
            "Next": 5,
        }
        if keysym in navigation:
            if self.results_view != "flat" and event.widget == self.focus_tree:
                return None
            return self._move_selection(navigation[keysym], event)
        if keysym == "Home":
            if self.results_view != "flat" and event.widget == self.focus_tree:
                return None
            return self._select_index(0, event)
        if keysym == "End":
            if self.results_view != "flat" and event.widget == self.focus_tree:
                return None
            result_count = (
                len(self.displayed_work_items)
                if self.work_items_mode
                else len(self.displayed_action_rows)
            )
            return self._select_index(result_count - 1, event)

        slot = self._slot_from_key(event)
        if slot is None:
            return None

        if self._plain_number_from_text_input(event):
            return None
        return self._execute_slot(slot, event)

    def _slot_from_key(self, event: tk.Event) -> int | None:
        state = int(getattr(event, "state", 0) or 0)
        if not state & 0x0001 or state & (0x0004 | 0x20000):
            return None

        # Tk's Windows event fields vary with keyboard layout and driver. Try
        # the produced digit first, then the AZERTY key name, then the common
        # Windows virtual-key code. Numpad input remains Find text.
        keycode = int(getattr(event, "keycode", 0) or 0)
        if 96 <= keycode <= 105:
            return None
        keysym = str(getattr(event, "keysym", "")).casefold()
        character = str(getattr(event, "char", ""))
        for candidate in (character, keysym):
            if candidate.isdigit():
                digit = int(candidate)
                if 6 <= digit <= 9:
                    return digit
                if digit == 0:
                    return 10
        azerty_slots = {
            "minus": 6,
            "egrave": 7,
            "underscore": 8,
            "ccedilla": 9,
            "agrave": 10,
            "parenright": 10,
        }
        if keysym in azerty_slots:
            return azerty_slots[keysym]
        if 54 <= keycode <= 57:
            return keycode - 48
        if keycode == 48:
            return 10
        return None

    def _plain_number_from_text_input(self, event: tk.Event) -> bool:
        focused_widget = self.root.focus_get()
        return focused_widget is not self.search_entry



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
    *,
    data_paths: AppDataPaths | None = None,
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
        data_paths=data_paths,
    )
    root.mainloop()
