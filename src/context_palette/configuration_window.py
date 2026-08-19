from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable

from .actions import (
    ACTION_BOUND_QUICK_MENU_SPECS,
    ACTION_BOUND_QUICK_TYPES,
    Action,
    ActionError,
    action_matches_search,
    action_search_text,
    configured_action,
    edited_configured_action,
    ensure_default_text_action_file,
    load_combined_actions,
    load_combined_stored_actions,
    validate_context_memberships,
)
from .action_deletion import (
    ActionDeletionError,
    archive_action_and_references,
    delete_action_and_references,
    inspect_action_references,
    restore_action,
)
from .action_types import ACTION_TYPES, CREATABLE_ACTION_TYPES
from .action_sequences import (
    ALLOWED_ACTION_TYPES,
    ActionSequenceError,
    SequenceStep,
    dependent_sequences,
    resolve_sequence_steps,
    sequence_reference_ids,
)
from .action_suggestions import ActionCreationSuggestion
from .action_type_picker import ActionTypePickerDialog, ActionTypePickerOption
from .action_bound_quick_actions import action_bound_quick_groups
from .action_picker import ActionPickerField, ActionPickerOption
from .backup_restore_ui import BackupRestorePanel
from .command_surface import (
    CommandGroup,
    CommandItem,
    CommandTarget,
    CommandSurfaceError,
    GROUP_PRESENTATION_NESTED_MENU,
    MAX_COMMAND_MENU_LEVELS,
    command_group_action_ids,
    command_group_all_action_ids,
    command_item_at_path,
    command_item_count,
    command_item_id_path,
    command_item_action_ids,
    command_item_targets,
    command_item_work_item_references,
    iter_command_items,
    load_combined_command_groups,
    load_command_groups,
)
from .configuration_data import save_command_item, save_context
from .configuration_data import (
    delete_command_group,
    delete_command_item,
    move_command_group,
    move_command_item,
    save_command_group,
)
from .contexts import ContextDefinition, ContextError, load_combined_contexts, load_contexts
from .data_catalog import AppDataPaths
from .context_membership import (
    actions_with_canonical_contexts,
    append_actions_with_context_memberships,
    update_action_with_context_memberships,
)
from .context_deletion import (
    ContextDeletionError,
    delete_context_and_memberships,
    rename_context_and_references,
)
from .diagnostics import render_safe_diagnostics, summarize_diagnostics
from .harvest_window import HarvestWindow
from .palette_state import (
    CONTEXT_SLOT_NUMBERS,
    MAX_CONTEXT_SLOT_ACTIONS,
    PaletteState,
    load_palette_state,
    save_palette_state,
    slot_display_number,
)
from .context_membership_field import (
    ContextMembershipField,
    TagSelectionField,
)
from .treeview_utils import scrollable_tree
from .tooltips import WidgetTooltip
from .window_geometry import configure_standard_window, place_child_window
from .work_item_configuration import WorkItemsConfigurationPanel
from .work_item_refresh import WorkItemIndex
from .work_items import DiscoveredWorkItem, WorkItemReference, WorkItemSource
from .work_item_storage import WorkItemMetadata
from .workspace_transforms import WORKSPACE_TRANSFORM_GROUPS, WORKSPACE_TRANSFORMS


ACTION_TYPE_EXAMPLES = {
    "copy_text": "Example: Paste “Kind regards,” into the application you came from.",
    "workspace_template": "Example: Put a reusable meeting-notes outline in Input / Output.",
    "ai_prompt": "Example: Load a stored review prompt into Input / Output before using it with an AI assistant.",
    "open_url": "Example: Open https://docs.python.org/ in the default browser.",
    "open_windows_target": (
        r"Example: Open vscode://file/c:/work/project/, shell:AppsFolder, "
        r"or C:\Tools\script.cmd through Windows."
    ),
    "open_file": r"Example: Open %PROJECT_ROOT%\README.md in its associated application.",
    "open_folder": r"Example: Open %PROJECT_ROOT%\docs in File Explorer.",
    "launch_app": r"Example: Start C:\Tools\Example\Example.exe with reviewed arguments.",
    "sequence": "Example: Start an import Action, wait briefly, then open its results folder.",
    "paste_credential": "Example: Paste the Windows or generic credential target oracle-pc17.",
    "build_url_open": "Example: Ask for ABC 123, then copy and open its generated website address.",
    "build_url_selection_open": "Example: Use selected text ABC 123, copy its URL, and open it.",
    "transform_file_text": "Example: Reformat a recurring UTF-8 JSON or text export and review it before replacing the file.",
    "transform_list_csv": "Example: Convert three input lines into red, green, blue.",
    "transform_text": "Example: Keep only lines containing invoice, format JSON, or convert names to snake_case.",
    "transform_slashes": r"Example: Convert C:/work/project into C:\work\project.",
}

LOCAL_DESTINATION = "My configuration"
PROJECT_DESTINATION = "Built-in"
EMPTY_PIN_LABEL = "Not assigned"
DEFAULT_TEXT_ACTION_FILENAME = "local_text_action_source.txt"
ACTION_DIALOG_SIZE = (700, 520)
ACTION_DIALOG_MINIMUM_SIZE = (620, 420)
ACTION_DIALOG_LABEL_WIDTH = 14
BUILT_IN_ACTION_SCOPE_NOTE = (
    "Built-in configuration lists Built-in actions only. To use a My "
    "configuration action, add or edit a My configuration context or "
    "Quick-action group."
)
CONFIGURATION_TAB_INDEXES = {
    "start": 0,
    "actions": 1,
    "types": 2,
    "contexts": 3,
    "buttons": 4,
    "work_items": 5,
    "backup_restore": 6,
    "diagnostics": 7,
}
CONFIGURATION_NAVIGATION_GROUPS = (
    (
        "SET UP",
        (
            ("start", "Start"),
            ("actions", "Actions"),
            ("types", "Action types"),
            ("contexts", "Contexts"),
            ("buttons", "Quick actions"),
            ("work_items", "Work Items"),
        ),
    ),
    (
        "SUPPORT",
        (
            ("backup_restore", "Backup & restore"),
            ("diagnostics", "Diagnostics"),
        ),
    ),
)
CONFIGURATION_NAVIGATION = tuple(
    destination
    for _group_label, destinations in CONFIGURATION_NAVIGATION_GROUPS
    for destination in destinations
)
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


class ConfigurationPageStack(ttk.Frame):
    """A tab-compatible internal page host with no visible tab strip."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._pages: list[tuple[tk.Widget, str, int | None]] = []
        self._selected_index = 0

    def add(
        self,
        child: tk.Widget,
        *,
        text: str,
        underline: int | None = None,
    ) -> None:
        self._pages.append((child, text, underline))
        child.grid(row=0, column=0, sticky=tk.NSEW)
        if len(self._pages) == 1:
            child.tkraise()
        else:
            child.grid_remove()

    def tabs(self) -> tuple[str, ...]:
        return tuple(str(page) for page, _text, _underline in self._pages)

    def tab(self, page: object, option: str | None = None) -> object:
        index = self.index(page)
        _widget, text, underline = self._pages[index]
        values = {"text": text, "underline": underline}
        return values.get(option) if option is not None else values

    def index(self, page: object) -> int:
        if page == "end":
            return len(self._pages)
        if isinstance(page, int):
            if 0 <= page < len(self._pages):
                return page
            raise tk.TclError(f"page index {page} is out of range")
        page_name = str(page)
        for index, (widget, _text, _underline) in enumerate(self._pages):
            if page is widget or page_name == str(widget):
                return index
        raise tk.TclError(f'unknown Configure page "{page_name}"')

    def select(self, page: object | None = None) -> str:
        if not self._pages:
            return ""
        if page is None:
            return str(self._pages[self._selected_index][0])
        index = self.index(page)
        if index == self._selected_index:
            return str(self._pages[index][0])
        current = self._pages[self._selected_index][0]
        current.grid_remove()
        self._selected_index = index
        selected = self._pages[index][0]
        selected.grid()
        selected.tkraise()
        self.event_generate("<<NotebookTabChanged>>")
        return str(selected)

    def enable_traversal(self) -> None:
        owner = self.winfo_toplevel()
        owner.bind("<Control-Tab>", self._next_page, add="+")
        owner.bind("<Control-Shift-Tab>", self._previous_page, add="+")

    def _next_page(self, _event: tk.Event | None = None) -> str:
        if self._pages:
            self.select((self._selected_index + 1) % len(self._pages))
        return "break"

    def _previous_page(self, _event: tk.Event | None = None) -> str:
        if self._pages:
            self.select((self._selected_index - 1) % len(self._pages))
        return "break"


@dataclass(frozen=True)
class ActionBoundQuickSelection:
    group_label: str
    action_type: str
    path: tuple[str, ...] = ()
    action_id: str = ""


def compact_selection_title(value: str, *, limit: int = 88) -> str:
    """Keep an arbitrary record title from displacing selection commands."""

    clean = " ".join(value.split())
    if len(clean) <= limit:
        return clean
    return f"{clean[: limit - 1].rstrip()}…"


def compact_selection_summary(value: str, *, limit: int = 180) -> str:
    """Bound selection-card detail so arbitrary data cannot erase its table."""

    clean = " ".join(value.split())
    if len(clean) <= limit:
        return clean
    return f"{clean[: limit - 1].rstrip()}…"


def action_matches_filter(action: Action, query: str, *, personal: bool) -> bool:
    return action_matches_search(
        action,
        query,
        extra_terms=(
            f"{LOCAL_DESTINATION} local personal"
            if personal
            else f"{PROJECT_DESTINATION} project shared",
        ),
    )


def context_membership_count(
    context: ContextDefinition,
    actions: list[Action],
) -> int:
    """Count Palette items that will lose membership when a context is deleted."""
    if context.action_ids is not None:
        return len(context.member_items)
    member_ids = {
        action.id
        for action in actions
        if action.belongs_to_context(context.name)
    }
    member_ids.update(context.preferred_action_ids)
    return len(member_ids) + len(context.work_item_refs)


def action_reference_labels(
    action_ids: tuple[str, ...],
    actions: list[Action],
) -> tuple[str, ...]:
    """Resolve stable action references into names suitable for the UI."""
    actions_by_id = {action.id: action for action in actions}
    return tuple(
        (
            actions_by_id[action_id].title
            if action_id in actions_by_id
            else f"Missing action: {action_id}"
        )
        for action_id in action_ids
    )


def work_item_reference_label(
    reference: WorkItemReference,
    work_items: tuple[DiscoveredWorkItem, ...],
) -> str:
    """Resolve a stable Work Item reference without discarding unavailable entries."""
    source_key = reference.source_id.casefold()
    folder_key = reference.relative_folder.casefold()
    item = next(
        (
            candidate
            for candidate in work_items
            if candidate.source_id.casefold() == source_key
            and candidate.relative_folder.casefold() == folder_key
        ),
        None,
    )
    if item is None:
        return (
            f"Unavailable Work Item: {reference.relative_folder} "
            f"[{reference.source_id}]"
        )
    return f"Work Item: {item.display_name} · {item.source_name}"


def _work_item_reference_search_terms(
    reference: WorkItemReference,
    work_items: tuple[DiscoveredWorkItem, ...],
) -> tuple[str, ...]:
    source_key = reference.source_id.casefold()
    folder_key = reference.relative_folder.casefold()
    item = next(
        (
            candidate
            for candidate in work_items
            if candidate.source_id.casefold() == source_key
            and candidate.relative_folder.casefold() == folder_key
        ),
        None,
    )
    if item is None:
        return (reference.source_id, reference.relative_folder)
    return (
        reference.source_id,
        reference.relative_folder,
        item.display_name,
        item.source_name,
        item.kind_code or "",
        item.kind_name or "",
        item.organisation or "",
        item.subject,
        *item.project_codes,
    )


def _work_item_choices(
    work_items: tuple[DiscoveredWorkItem, ...],
) -> dict[str, WorkItemReference]:
    return {
        f"▣ {item.display_name} · {item.source_name} [{item.source_id}]": (
            WorkItemReference(item.source_id, item.relative_folder)
        )
        for item in sorted(
            work_items,
            key=lambda candidate: (
                candidate.display_name.casefold(),
                candidate.source_name.casefold(),
            ),
        )
    }


def _work_item_picker_options(
    work_items: tuple[DiscoveredWorkItem, ...],
    choices: dict[str, WorkItemReference],
) -> tuple[ActionPickerOption, ...]:
    items_by_reference = {
        WorkItemReference(item.source_id, item.relative_folder): item
        for item in work_items
    }
    return tuple(
        ActionPickerOption(
            action_id=f"{reference.source_id}/{reference.relative_folder}",
            label=label,
            search_text=" ".join(
                (
                    reference.source_id,
                    reference.relative_folder,
                    items_by_reference[reference].source_name,
                    items_by_reference[reference].display_name,
                    items_by_reference[reference].kind_code or "",
                    items_by_reference[reference].kind_name or "",
                    items_by_reference[reference].organisation or "",
                    items_by_reference[reference].subject,
                    *items_by_reference[reference].project_codes,
                )
            ),
        )
        for label, reference in choices.items()
    )


def quick_action_target_labels(
    item: CommandItem,
    actions: list[Action],
    work_items: tuple[DiscoveredWorkItem, ...],
) -> tuple[str, ...]:
    actions_by_id = {action.id: action for action in actions}
    labels: list[str] = []
    for target in command_item_targets(item):
        if target.action_id:
            action = actions_by_id.get(target.action_id)
            labels.append(
                action.title
                if action is not None
                else f"Missing action: {target.action_id}"
            )
        elif target.work_item_ref is not None:
            labels.append(
                work_item_reference_label(target.work_item_ref, work_items)
            )
    return tuple(labels)


def context_action_summary(
    context: ContextDefinition,
    actions: list[Action],
    work_items: tuple[DiscoveredWorkItem, ...] = (),
) -> str:
    actions_by_id = {action.id: action for action in actions}
    preferred = tuple(
        (
            actions_by_id[reference.action_id].title
            if reference.action_id in actions_by_id
            else f"Missing action: {reference.action_id}"
        )
        if reference.action_id
        else work_item_reference_label(reference.work_item_ref, work_items)
        for reference in context.preferred_items
    )
    preferred_text = ", ".join(preferred) if preferred else "automatic"
    return (
        f"{context_membership_count(context, actions)} member(s) · "
        f"Focus shortcuts: {preferred_text}"
    )


def context_matches_filter(
    context: ContextDefinition,
    query: str,
    *,
    actions: list[Action],
    work_items: tuple[DiscoveredWorkItem, ...] = (),
    personal: bool,
) -> bool:
    terms = [term.casefold() for term in query.split() if term.strip()]
    if not terms:
        return True
    member_ids = (
        context.action_ids
        if context.action_ids is not None
        else tuple(
            action.id
            for action in actions
            if action.belongs_to_context(context.name)
        )
    )
    labels = action_reference_labels(
        tuple(dict.fromkeys((*member_ids, *context.preferred_action_ids))),
        actions,
    )
    work_item_labels = tuple(
        work_item_reference_label(reference, work_items)
        for reference in context.work_item_refs
    )
    searchable = " ".join(
        (
            context.name,
            context.description,
            *labels,
            *work_item_labels,
            f"{LOCAL_DESTINATION} local personal"
            if personal
            else f"{PROJECT_DESTINATION} project shared",
        )
    ).casefold()
    return all(term in searchable for term in terms)


def quick_action_matches_filter(
    group: CommandGroup,
    item: CommandItem | None,
    query: str,
    *,
    actions: list[Action],
    personal: bool,
    work_items: tuple[DiscoveredWorkItem, ...] = (),
) -> bool:
    terms = [term.casefold() for term in query.split() if term.strip()]
    if not terms:
        return True
    labels = (
        action_reference_labels(command_item_action_ids(item), actions)
        if item is not None
        else action_reference_labels(command_group_action_ids(group), actions)
    )
    work_item_terms = tuple(
        term
        for reference in (
            command_item_work_item_references(item)
            if item is not None
            else ()
        )
        for term in (
            work_item_reference_label(reference, work_items),
            *_work_item_reference_search_terms(reference, work_items),
        )
    )
    searchable = " ".join(
        (
            group.label,
            item.label if item is not None else "",
            *labels,
            *work_item_terms,
            f"{LOCAL_DESTINATION} local personal"
            if personal
            else f"{PROJECT_DESTINATION} project shared",
        )
    ).casefold()
    return all(term in searchable for term in terms)


def command_item_subtree_count(item: CommandItem) -> int:
    return 1 + sum(
        command_item_subtree_count(child)
        for child in item.items
    )


def select_first_tree_item(tree: ttk.Treeview, *, descend: bool = False) -> None:
    roots = tree.get_children()
    if not roots:
        return
    target = roots[0]
    if descend:
        children = tree.get_children(target)
        if children:
            target = children[0]
    tree.selection_set(target)
    tree.focus(target)


def resolve_pinned_action_ids(
    selected_labels: list[str],
    action_choices: dict[str, str],
) -> tuple[str, ...]:
    action_ids: list[str] = []
    for label in selected_labels:
        if not label or label == EMPTY_PIN_LABEL:
            continue
        action_id = action_choices.get(label)
        if action_id is None:
            raise ActionError(f'Pinned action "{label}" is no longer available.')
        if action_id in action_ids:
            raise ActionError("Each action can occupy only one pinned slot.")
        action_ids.append(action_id)
    return tuple(action_ids)


class ConfigurationWindow:
    def __init__(
        self,
        parent: tk.Tk,
        *,
        actions: list[Action],
        local_action_ids: set[str],
        shared_actions_path: Path,
        local_actions_path: Path,
        contexts_path: Path,
        local_contexts_path: Path,
        command_surface_path: Path,
        local_command_surface_path: Path,
        palette_path: Path,
        work_item_sources_path: Path,
        work_item_metadata_path: Path,
        work_item_settings_path: Path,
        work_item_sources: tuple[WorkItemSource, ...],
        work_item_metadata: dict[str, WorkItemMetadata],
        work_item_index: WorkItemIndex,
        on_change: Callable[[], None],
        focus_context: str = "General",
        initial_tab: str = "start",
        initial_action_id: str | None = None,
        initial_work_item_key: str | None = None,
        start_work_item_creation: bool = False,
        start_action_creation: bool = False,
        initial_action_suggestion: ActionCreationSuggestion | None = None,
        start_action_edit: bool = False,
        data_paths: AppDataPaths | None = None,
        on_restore_complete: Callable[[], None] | None = None,
        on_restore_recovery_required: Callable[[], None] | None = None,
    ) -> None:
        self.actions = actions
        self.stored_actions = list(actions)
        self.local_action_ids = local_action_ids
        self.shared_actions_path = shared_actions_path
        self.local_actions_path = local_actions_path
        self.contexts_path = contexts_path
        self.local_contexts_path = local_contexts_path
        self.command_surface_path = command_surface_path
        self.local_command_surface_path = local_command_surface_path
        self.palette_path = palette_path
        self.palette_state = PaletteState()
        self.work_item_sources_path = work_item_sources_path
        self.work_item_metadata_path = work_item_metadata_path
        self.work_item_settings_path = work_item_settings_path
        self.work_item_index = work_item_index
        self.local_contexts: list[ContextDefinition] = []
        self.on_change = on_change
        self.focus_context = focus_context
        self.contexts: list[ContextDefinition] = []
        self.groups: list[CommandGroup] = []
        self.action_filter_var = tk.StringVar()
        self.action_filter_count_var = tk.StringVar()
        self.action_state_filter_var = tk.StringVar(value="Active")
        self.action_state_help_var = tk.StringVar()
        self.context_filter_var = tk.StringVar()
        self.context_filter_count_var = tk.StringVar()
        self.button_filter_var = tk.StringVar()
        self.button_filter_count_var = tk.StringVar()
        self.initial_tab = initial_tab
        self.initial_action_id = initial_action_id
        self.initial_work_item_key = initial_work_item_key
        self.start_work_item_creation = start_work_item_creation
        self.start_action_creation = start_action_creation
        self.initial_action_suggestion = initial_action_suggestion
        self.action_type_picker: ActionTypePickerDialog | None = None
        self.action_creation_dialog: ActionDialog | None = None
        self.action_edit_dialog: ActionDialog | None = None
        self._pending_action_edit_id: str | None = None
        self._pending_action_edit_after_id: str | None = None
        self._pending_action_suggestion: ActionCreationSuggestion | None = None
        self._pending_action_suggestion_after_id: str | None = None
        self.data_paths = data_paths or AppDataPaths.from_data_directory(
            shared_actions_path.parent
        )
        self._launcher_restore_complete = on_restore_complete or on_change
        self._launcher_recovery_required = (
            on_restore_recovery_required or (lambda: None)
        )

        self.window = tk.Toplevel(parent)
        self.window.title("Configure Context Palette")
        configure_standard_window(self.window, parent)
        configured_width, configured_height, _x, _y = place_child_window(
            self.window,
            parent,
            size=(960, 680),
        )
        self.window.minsize(
            min(900, configured_width),
            min(520, configured_height),
        )
        self.window.protocol("WM_DELETE_WINDOW", self._request_close)
        self.window.bind("<Escape>", self._close_on_plain_escape)
        self.window.bind("<KeyPress>", self._handle_configure_keypress, add="+")
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        footer = ttk.Frame(outer)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        self.feedback_var = tk.StringVar(
            value="Changes save immediately."
        )
        self.feedback_label = ttk.Label(
            footer,
            textvariable=self.feedback_var,
            style="Status.TLabel",
        )
        self.feedback_label.pack(side=tk.LEFT)
        self.close_button = ttk.Button(
            footer,
            text="Close",
            command=self._request_close,
            style="Compact.TButton",
        )
        self.close_button.pack(side=tk.RIGHT)
        body = ttk.Frame(outer)
        body.pack(fill=tk.BOTH, expand=True)
        self.configuration_navigation = ttk.Frame(body, padding=(0, 0, 10, 0))
        self.configuration_navigation.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Separator(body, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y)
        self.notebook = ConfigurationPageStack(body)
        self.notebook.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        self.notebook.enable_traversal()
        self._build_start_tab(self.notebook)
        self._build_actions_tab(self.notebook)
        self._build_types_tab(self.notebook)
        self._build_contexts_tab(self.notebook)
        self._build_buttons_tab(self.notebook)
        self._build_work_items_tab(
            self.notebook,
            work_item_sources,
            work_item_metadata,
            work_item_index,
        )
        self._build_backup_restore_tab(self.notebook)
        self._build_diagnostics_tab(self.notebook)
        self._build_configuration_navigation()
        self.notebook.select(CONFIGURATION_TAB_INDEXES.get(self.initial_tab, 0))
        self.notebook.bind("<<NotebookTabChanged>>", self._focus_selected_tab)
        self._sync_configuration_navigation()
        self.window.bind("<Control-f>", self._focus_current_filter)
        self._reload()
        if self.initial_work_item_key:
            self.work_items_panel.select_item(self.initial_work_item_key)
        self.window.transient(parent)
        self.window.lift()
        self.window.after_idle(self._focus_current_tab)
        if self.start_work_item_creation:
            self.window.after_idle(self._start_work_item_creation)
        if self.start_action_creation:
            self.window.after_idle(self._start_action_creation)
        if self.initial_action_suggestion is not None:
            self._schedule_action_suggestion(self.initial_action_suggestion)
        if start_action_edit and self.initial_action_id:
            self._schedule_action_edit(self.initial_action_id)

    def show(
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
        """Refresh, navigate, and raise an already-open Configure workspace."""
        pin_draft = (
            tuple(variable.get() for variable in self.pin_vars)
            if getattr(self, "_pins_dirty", False)
            else None
        )
        self.initial_action_id = initial_action_id
        if initial_action_id and self.action_filter_var.get():
            self.action_filter_var.set("")
        if initial_action_id and self.action_state_filter_var.get() != "Active":
            self.action_state_filter_var.set("Active")
        self._reload()
        if pin_draft is not None:
            self._pins_rendering = True
            try:
                for variable, value in zip(self.pin_vars, pin_draft):
                    variable.set(value)
            finally:
                self._pins_rendering = False
            self._pins_dirty = True
            self._update_pin_summary()
        self.notebook.select(CONFIGURATION_TAB_INDEXES.get(initial_tab, 0))
        if initial_work_item_key:
            self.work_items_panel.select_item(initial_work_item_key)
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()
        self.window.after_idle(self._focus_current_tab)
        if start_work_item_creation:
            self.window.after_idle(self._start_work_item_creation)
        if start_action_creation:
            self.window.after_idle(self._start_action_creation)
        if initial_action_suggestion is not None:
            self._schedule_action_suggestion(initial_action_suggestion)
        if start_action_edit and initial_action_id:
            self._schedule_action_edit(initial_action_id)

    def refresh_from_storage(self) -> None:
        """Refresh an already-open workspace after another window changes data."""

        self._reload()

    def select_configured_quick_action(
        self,
        group_id: str,
        item_ids: tuple[str, ...] = (),
    ) -> bool:
        """Show one configured menu or submenu by stable persisted IDs."""

        self.notebook.select(CONFIGURATION_TAB_INDEXES["buttons"])
        if self.button_filter_var.get():
            self.button_filter_var.set("")
        group_index = next(
            (
                index
                for index, group in enumerate(self.groups)
                if group.id.casefold() == group_id.casefold()
            ),
            None,
        )
        if group_index is None:
            self.feedback_var.set("That Quick-action menu is no longer available.")
            return False
        group = self.groups[group_index]
        path: list[int] = []
        items = group.items
        for item_id in item_ids:
            item_index = next(
                (
                    index
                    for index, item in enumerate(items)
                    if item.id.casefold() == item_id.casefold()
                ),
                None,
            )
            if item_index is None:
                self.feedback_var.set(
                    "That Quick-action submenu is no longer available."
                )
                return False
            path.append(item_index)
            items = items[item_index].items
        iid = (
            f"button-{group_index}-"
            + ".".join(str(index) for index in path)
            if path
            else f"group-{group_index}"
        )
        if not self.button_tree.exists(iid):
            self._render_buttons()
        if not self.button_tree.exists(iid):
            self.feedback_var.set("That Quick-action item is no longer available.")
            return False
        self.button_tree.selection_set(iid)
        self.button_tree.focus(iid)
        self.button_tree.see(iid)
        self._update_button_preview()
        self.button_tree.focus_set()
        return True

    def select_automatic_quick_action(
        self,
        action_type: str,
        path: tuple[str, ...] = (),
        action_id: str = "",
    ) -> bool:
        """Show an automatic menu branch or Action without an approximate search."""

        self.notebook.select(CONFIGURATION_TAB_INDEXES["buttons"])
        if self.button_filter_var.get():
            self.button_filter_var.set("")
        expected_path = tuple(part.casefold() for part in path)
        iid = next(
            (
                record_iid
                for record_iid, selection in self.action_bound_button_records.items()
                if selection.action_type == action_type
                and tuple(part.casefold() for part in selection.path) == expected_path
                and selection.action_id.casefold() == action_id.casefold()
            ),
            None,
        )
        if iid is None:
            self.feedback_var.set(
                "That automatic Quick-action selection is no longer available."
            )
            return False
        self.button_tree.selection_set(iid)
        self.button_tree.focus(iid)
        self.button_tree.see(iid)
        self._update_button_preview()
        self.button_tree.focus_set()
        return True

    def add_quick_action_to_selection(self) -> None:
        """Start the normal guided add flow for the selected configured menu."""

        self._add_button()

    def create_action_for_automatic_menu(
        self,
        action_type: str,
        path: tuple[str, ...] = (),
    ) -> None:
        """Create one normal reviewed Action pre-organized in a live menu."""

        if action_type not in ACTION_BOUND_QUICK_TYPES:
            return
        if self._raise_existing_action_creation_dialog():
            return
        self._create_action_for_type(
            action_type,
            initial_quick_action_path=path,
        )

    def show_automatic_quick_actions(
        self,
        group_label: str,
        action_type: str,
        path: tuple[str, ...] = (),
    ) -> None:
        """Open the existing Actions view for one automatic menu selection."""

        self._manage_action_bound_quick_selection(
            ActionBoundQuickSelection(group_label, action_type, path)
        )

    def _start_work_item_creation(self) -> None:
        self.work_items_panel.create_work_item()

    def _start_action_creation(self) -> None:
        """Open one small type chooser before the existing full Action form."""
        panel = getattr(self, "backup_restore_panel", None)
        if panel is not None and panel.busy:
            self._set_feedback(
                "Wait for the backup or restore operation to finish before creating an Action.",
                False,
            )
            return
        if self._raise_existing_action_creation_dialog():
            return
        picker = self.action_type_picker
        if picker is not None:
            try:
                if picker.window.winfo_exists():
                    picker.window.lift()
                    picker.window.focus_force()
                    return
            except tk.TclError:
                pass
        self.action_type_picker = ActionTypePickerDialog(
            self.window,
            options=tuple(
                ActionTypePickerOption(
                    action_type,
                    definition.display_label,
                    definition.family,
                    definition.description,
                )
                for action_type, definition in CREATABLE_ACTION_TYPES.items()
            ),
            on_select=self._create_action_for_type,
            on_close=lambda: setattr(self, "action_type_picker", None),
        )

    def _raise_existing_action_creation_dialog(self) -> bool:
        dialog = self.action_creation_dialog
        if dialog is not None:
            try:
                if dialog.window.winfo_exists():
                    dialog.window.lift()
                    dialog.window.focus_force()
                    return True
            except tk.TclError:
                pass
            self.action_creation_dialog = None
        return False

    def _start_action_suggestion(
        self,
        suggestion: ActionCreationSuggestion,
    ) -> None:
        panel = getattr(self, "backup_restore_panel", None)
        if panel is not None and panel.busy:
            self._set_feedback(
                "Wait for the backup or restore operation to finish before creating an Action.",
                False,
            )
            return
        if self._raise_existing_action_creation_dialog():
            return
        picker = self.action_type_picker
        if picker is not None:
            try:
                if picker.window.winfo_exists():
                    picker.window.lift()
                    picker.window.focus_force()
                    self._set_feedback(
                        "Finish or close the open Action type chooser, then try Create Action again.",
                        False,
                    )
                    return
            except tk.TclError:
                pass
            self.action_type_picker = None
        self._create_action_for_type(
            suggestion.action_type,
            suggestion=suggestion,
        )

    def _schedule_action_suggestion(
        self,
        suggestion: ActionCreationSuggestion,
    ) -> None:
        self._pending_action_suggestion = suggestion
        if self._pending_action_suggestion_after_id is not None:
            return
        self._pending_action_suggestion_after_id = self.window.after_idle(
            self._open_pending_action_suggestion
        )

    def _open_pending_action_suggestion(self) -> None:
        self._pending_action_suggestion_after_id = None
        suggestion = self._pending_action_suggestion
        self._pending_action_suggestion = None
        if suggestion is not None:
            self._start_action_suggestion(suggestion)

    def _cancel_pending_action_suggestion(self) -> None:
        after_id = getattr(self, "_pending_action_suggestion_after_id", None)
        if after_id is not None:
            try:
                self.window.after_cancel(after_id)
            except tk.TclError:
                pass
        self._pending_action_suggestion_after_id = None
        self._pending_action_suggestion = None

    def _close_on_plain_escape(self, event: tk.Event) -> str:
        if int(event.state) & 0x0004:
            return "break"
        self._request_close()
        return "break"

    def _handle_configure_keypress(self, event: tk.Event) -> str | None:
        state = int(getattr(event, "state", 0) or 0)
        if state & 0x0004 and str(getattr(event, "keysym", "")).casefold() == "n":
            self._start_action_creation()
            return "break"
        if not state & 0x20000:
            return None
        tab_index = {
            "a": CONFIGURATION_TAB_INDEXES["actions"],
            "t": CONFIGURATION_TAB_INDEXES["types"],
            "c": CONFIGURATION_TAB_INDEXES["contexts"],
            "q": CONFIGURATION_TAB_INDEXES["buttons"],
            "w": CONFIGURATION_TAB_INDEXES["work_items"],
            "d": CONFIGURATION_TAB_INDEXES["diagnostics"],
            "b": CONFIGURATION_TAB_INDEXES["backup_restore"],
        }.get(str(getattr(event, "keysym", "")).casefold())
        if tab_index is None:
            return None
        self.notebook.select(tab_index)
        return "break"

    def _build_configuration_navigation(self) -> None:
        self.configuration_navigation_buttons: dict[int, ttk.Button] = {}
        self.configuration_navigation_groups: dict[str, ttk.Frame] = {}
        self.configuration_navigation_group_labels: dict[str, ttk.Label] = {}
        for group_index, (group_label, destinations) in enumerate(
            CONFIGURATION_NAVIGATION_GROUPS
        ):
            group = ttk.Frame(self.configuration_navigation)
            group.pack(
                side=tk.BOTTOM if group_index else tk.TOP,
                fill=tk.X,
            )
            heading = ttk.Label(
                group,
                text=group_label,
                style="ConfigureNavGroup.TLabel",
            )
            heading.pack(fill=tk.X, pady=(0, 2))
            self.configuration_navigation_groups[group_label] = group
            self.configuration_navigation_group_labels[group_label] = heading
            for section, label in destinations:
                index = CONFIGURATION_TAB_INDEXES[section]
                button = ttk.Button(
                    group,
                    text=label,
                    width=20,
                    style="ConfigureNav.TButton",
                    command=lambda tab_index=index: self._show_config_tab(tab_index),
                )
                button.pack(fill=tk.X, pady=(0, 2))
                self.configuration_navigation_buttons[index] = button

    def _sync_configuration_navigation(self) -> None:
        if not hasattr(self, "configuration_navigation_buttons"):
            return
        selected = self.notebook.index(self.notebook.select())
        for index, button in self.configuration_navigation_buttons.items():
            button.configure(
                style=(
                    "ConfigureNavSelected.TButton"
                    if index == selected
                    else "ConfigureNav.TButton"
                )
            )

    def _build_start_tab(self, notebook: ConfigurationPageStack) -> None:
        tab = ttk.Frame(notebook, padding=14)
        notebook.add(tab, text="Start", underline=0)
        ttk.Label(
            tab,
            text="Choose a setup task",
            style="Heading.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W)
        ttk.Label(
            tab,
            text=(
                "Choose a task. Context Palette will take you to the existing "
                "editor where the change is made."
            ),
            style="Muted.TLabel",
            wraplength=620,
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(3, 12))
        tasks = (
            (
                "Create an Action...",
                "Choose a reusable effect, then review and create the Action.",
                self._start_action_creation,
            ),
            (
                "Find or edit Actions",
                "Manage saved Actions, pinned slots, and Active or Archived state.",
                lambda: self._show_config_named_tab("actions"),
            ),
            (
                "Organize Focuses",
                "Create Contexts, choose their members, and arrange Focus slots.",
                lambda: self._show_config_named_tab("contexts"),
            ),
            (
                "Arrange Quick actions",
                "Change the buttons and menus shown in the main palette.",
                lambda: self._show_config_named_tab("buttons"),
            ),
            (
                "Set up Work Items",
                "Manage folders, templates, personal tags, and discovered work.",
                lambda: self._show_config_named_tab("work_items"),
            ),
            (
                "Back up or restore",
                "Protect this configuration or review a backup before restoring it.",
                lambda: self._show_config_named_tab("backup_restore"),
            ),
        )
        for index, (label, description, command) in enumerate(tasks):
            row = 2 + index // 2
            column = index % 2
            card = ttk.Frame(tab, padding=(0, 0, 12, 10))
            card.grid(row=row, column=column, sticky=tk.NSEW)
            button = ttk.Button(
                card,
                text=label,
                command=command,
                style="Accent.TButton" if index == 0 else "TButton",
            )
            button.pack(fill=tk.X)
            ttk.Label(
                card,
                text=description,
                style="Muted.TLabel",
                wraplength=270,
                justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=(4, 0))
            if index == 0:
                self.start_primary_button = button
        advanced = ttk.Frame(tab)
        advanced.grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(4, 0))
        ttk.Label(advanced, text="More:", style="Muted.TLabel").pack(side=tk.LEFT)
        ttk.Button(
            advanced,
            text="Browse Action types",
            command=lambda: self._show_config_named_tab("types"),
            style="Compact.TButton",
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            advanced,
            text="View diagnostics",
            command=lambda: self._show_config_named_tab("diagnostics"),
            style="Compact.TButton",
        ).pack(side=tk.LEFT, padx=(6, 0))
        tab.columnconfigure(0, weight=1, uniform="tasks")
        tab.columnconfigure(1, weight=1, uniform="tasks")

    def _show_config_named_tab(self, name: str) -> str:
        return self._show_config_tab(CONFIGURATION_TAB_INDEXES[name])

    def _build_actions_tab(self, notebook: ConfigurationPageStack) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Actions", underline=0)

        header = ttk.Frame(tab)
        header.pack(fill=tk.X, pady=(0, 8))
        heading = ttk.Frame(header)
        heading.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            heading,
            text="Manage Actions",
            style="Title.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            heading,
            text="Create, find, edit, archive, and restore saved Actions.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))
        header_commands = ttk.Frame(header)
        header_commands.pack(side=tk.RIGHT, padx=(10, 0))
        self.other_action_creation_button = ttk.Menubutton(
            header_commands,
            text="Other ways to create",
        )
        self.other_action_creation_menu = tk.Menu(
            self.other_action_creation_button,
            tearoff=False,
        )
        self.other_action_creation_menu.add_command(
            label="Browse Action types…",
            command=lambda: self._show_config_named_tab("types"),
        )
        self.other_action_creation_menu.add_command(
            label="Harvest documents…",
            command=self._show_harvest,
        )
        self.other_action_creation_button.configure(
            menu=self.other_action_creation_menu
        )
        self.other_action_creation_button.pack(side=tk.LEFT)
        self.new_action_button = ttk.Button(
            header_commands,
            text="New Action…",
            command=self._start_action_creation,
            style="Accent.TButton",
        )
        self.new_action_button.pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(
            tab,
            text=(
                "My configuration stays on this computer. Built-in changes alter "
                "the starter configuration tracked through Git."
            ),
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 7))

        pins = ttk.Frame(
            tab,
            style="Card.TFrame",
            padding=(8, 5),
        )
        self.pins_frame = pins
        pins.pack(fill=tk.X, pady=(0, 8))
        pins.columnconfigure(1, weight=1)
        ttk.Label(
            pins,
            text="Pinned slots 1–5",
            style="Card.TLabel",
            font=("Segoe UI Semibold", 10),
        ).grid(row=0, column=0, sticky=tk.W)
        self.pin_summary_var = tk.StringVar(value="0 assigned on this computer")
        ttk.Label(
            pins,
            textvariable=self.pin_summary_var,
            style="CardMuted.TLabel",
        ).grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        self.toggle_pins_button = ttk.Button(
            pins,
            text="Show pins",
            command=self._toggle_pins,
            style="Compact.TButton",
        )
        self.toggle_pins_button.grid(row=0, column=2, sticky=tk.E)
        self.pins_body = ttk.Frame(pins, style="Card.TFrame")
        self.pins_body.columnconfigure(1, weight=1)
        self._pins_rendering = False
        self._pins_dirty = False
        self.pin_vars: list[tk.StringVar] = []
        self.pin_choices: dict[str, str] = {}
        self.pin_pickers: list[ActionPickerField] = []
        for row in range(5):
            ttk.Label(
                self.pins_body,
                text=f"Slot {row + 1}",
                style="CardMuted.TLabel",
                width=7,
            ).grid(row=row, column=0, sticky=tk.W, pady=(3, 0))
            variable = tk.StringVar(value=EMPTY_PIN_LABEL)
            picker = ActionPickerField(
                self.pins_body,
                variable=variable,
                empty_label=EMPTY_PIN_LABEL,
                title=f"Choose action for slot {row + 1}",
                button_text="Choose…",
            )
            picker.configure(style="Card.TFrame")
            picker.grid(
                row=row,
                column=1,
                sticky=tk.EW,
                padx=(8, 0),
                pady=(3, 0),
            )
            self.pin_vars.append(variable)
            self.pin_pickers.append(picker)
            variable.trace_add(
                "write",
                lambda *_args: self._mark_pins_dirty(),
            )
        self.pin_comboboxes = self.pin_pickers
        self.save_pins_button = ttk.Button(
            self.pins_body,
            text="Save pins",
            command=self._save_pinned_slots,
        )
        self.save_pins_button.grid(row=5, column=1, sticky=tk.E, pady=(7, 0))

        filter_row = ttk.Frame(tab)
        filter_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(filter_row, text="Find").pack(side=tk.LEFT)
        self.action_filter_entry = ttk.Entry(
            filter_row,
            textvariable=self.action_filter_var,
        )
        self.action_filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 8))
        ttk.Label(filter_row, text="Show").pack(side=tk.LEFT)
        self.action_state_filter = ttk.Combobox(
            filter_row,
            textvariable=self.action_state_filter_var,
            values=("Active", "Archived", "All"),
            state="readonly",
            width=10,
        )
        self.action_state_filter.pack(side=tk.LEFT, padx=(6, 8))
        ttk.Label(
            filter_row,
            textvariable=self.action_filter_count_var,
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)
        ttk.Label(
            tab,
            textvariable=self.action_state_help_var,
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 5))
        self.action_tree_frame, self.action_tree = scrollable_tree(
            tab,
            ("type", "contexts", "source", "state"),
        )
        for column, label, width in (
            ("#0", "Action", 250),
            ("type", "Type", 145),
            ("contexts", "Contexts", 125),
            ("source", "Source", 125),
            ("state", "State", 70),
        ):
            self.action_tree.heading(column, text=label)
            self.action_tree.column(
                column,
                width=width,
                minwidth=90 if column != "#0" else 180,
                stretch=column == "#0",
            )
        self.action_tree_frame.pack(fill=tk.BOTH, expand=True)
        self.action_tree.bind("<Double-1>", lambda _event: self._edit_action())
        self.action_tree.bind("<Return>", lambda _event: self._edit_action())
        self.action_tree.bind(
            "<<TreeviewSelect>>", lambda _event: self._update_action_controls()
        )
        self.action_filter_var.trace_add("write", lambda *_args: self._render_actions())
        self.action_state_filter_var.trace_add(
            "write", lambda *_args: self._render_actions()
        )

        selection = ttk.Frame(
            tab,
            style="Card.TFrame",
            padding=(10, 8),
        )
        self.action_selection_frame = selection
        selection.pack(
            side=tk.BOTTOM,
            fill=tk.X,
            pady=(8, 0),
            before=self.action_tree_frame,
        )
        selection.columnconfigure(0, weight=1)
        self.action_detail_title_var = tk.StringVar(value="Select an Action")
        self.action_detail_title_label = ttk.Label(
            selection,
            textvariable=self.action_detail_title_var,
            style="Card.TLabel",
            font=("Segoe UI Semibold", 10),
            justify=tk.LEFT,
        )
        self.action_detail_title_label.grid(row=0, column=0, sticky=tk.EW)
        self.action_detail_summary_var = tk.StringVar(
            value="Contexts, tags, ownership, and lifecycle appear here."
        )
        self.action_detail_summary_label = ttk.Label(
            selection,
            textvariable=self.action_detail_summary_var,
            style="CardMuted.TLabel",
            justify=tk.LEFT,
        )
        self.action_detail_summary_label.grid(
            row=1,
            column=0,
            sticky=tk.EW,
            pady=(4, 0),
        )
        self.action_commands_frame = ttk.Frame(selection, style="Card.TFrame")
        self.action_commands_frame.grid(row=0, column=1, rowspan=2, sticky=tk.E)
        self.action_edit_button = ttk.Button(
            self.action_commands_frame,
            text="Edit…",
            command=self._edit_action,
            state=tk.DISABLED,
        )
        self.action_edit_button.pack(side=tk.LEFT)
        self.action_lifecycle_button = ttk.Button(
            self.action_commands_frame,
            text="Archive…",
            command=self._change_action_state,
            state=tk.DISABLED,
        )
        self.action_lifecycle_button.pack(side=tk.LEFT, padx=(6, 0))
        self.delete_action_button = ttk.Button(
            self.action_commands_frame,
            text="Delete permanently…",
            command=self._delete_action,
            state=tk.DISABLED,
            style="Danger.TButton",
        )
        self.delete_action_button.pack(side=tk.LEFT, padx=(6, 0))
        selection.bind("<Configure>", self._resize_action_summary, add="+")

    def _toggle_pins(self) -> None:
        if self.pins_body.winfo_manager():
            self.pins_body.grid_remove()
            self.toggle_pins_button.configure(text="Show pins")
            self.toggle_pins_button.focus_set()
            return
        self.pins_body.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky=tk.EW,
            pady=(7, 0),
        )
        self.toggle_pins_button.configure(text="Hide pins")

    def _mark_pins_dirty(self) -> None:
        if self._pins_rendering:
            return
        self._pins_dirty = True
        self._update_pin_summary()

    def _update_pin_summary(self) -> None:
        assigned = len(self.palette_state.pinned_action_ids[:5])
        self.pin_summary_var.set(
            f"{assigned} saved · unsaved changes"
            if self._pins_dirty
            else f"{assigned} assigned on this computer"
        )

    def _resize_action_summary(self, event: tk.Event) -> None:
        command_width = self.action_commands_frame.winfo_reqwidth()
        text_width = max(120, int(event.width) - command_width - 34)
        self.action_detail_title_label.configure(wraplength=text_width)
        self.action_detail_summary_label.configure(
            wraplength=text_width
        )

    def _resize_context_summary(self, event: tk.Event) -> None:
        command_width = self.context_commands_frame.winfo_reqwidth()
        text_width = max(120, int(event.width) - command_width - 34)
        self.context_detail_title_label.configure(wraplength=text_width)
        self.context_detail_summary_label.configure(wraplength=text_width)

    def _resize_button_summary(self, event: tk.Event) -> None:
        command_width = self.button_commands_frame.winfo_reqwidth()
        text_width = max(120, int(event.width) - command_width - 34)
        self.button_detail_title_label.configure(wraplength=text_width)
        self.button_preview_label.configure(wraplength=text_width)

    def _show_harvest(self) -> None:
        HarvestWindow(
            self.window,
            actions=self.actions,
            context_names=[context.name for context in self.contexts],
            focus_context=self.focus_context,
            actions_path=self.local_actions_path,
            shared_contexts_path=self.contexts_path,
            local_contexts_path=self.local_contexts_path,
            on_change=self._harvest_changed,
        )

    def _harvest_changed(self) -> None:
        try:
            self.actions, self.local_action_ids = load_combined_actions(
                self.shared_actions_path,
                self.local_actions_path,
                inspect_external_paths=False,
            )
        except ActionError as exc:
            messagebox.showerror(
                "Context Palette",
                f"The harvested actions were saved, but Configure could not reload them.\n\n{exc}",
                parent=self.window,
            )
            self.on_change()
            return
        self._reload()
        self.on_change()

    def _build_types_tab(self, notebook: ConfigurationPageStack) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Action types", underline=0)
        panes = ttk.Panedwindow(tab, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True)
        self.type_ids = list(CREATABLE_ACTION_TYPES)
        self.type_list = tk.Listbox(panes, exportselection=False, width=30)
        for definition in CREATABLE_ACTION_TYPES.values():
            self.type_list.insert(tk.END, definition.display_label)
        panes.add(self.type_list, weight=1)
        detail = ttk.Frame(panes, padding=(12, 0, 0, 0))
        panes.add(detail, weight=2)
        self.type_title = tk.StringVar()
        self.type_family = tk.StringVar()
        ttk.Label(detail, textvariable=self.type_title, style="Heading.TLabel").pack(anchor=tk.W)
        ttk.Label(detail, textvariable=self.type_family, style="Muted.TLabel").pack(anchor=tk.W, pady=(2, 8))
        self.type_detail = tk.Text(detail, wrap=tk.WORD, height=14)
        self.type_detail.pack(fill=tk.BOTH, expand=True)
        self.type_detail.configure(state=tk.DISABLED)
        create_button = ttk.Button(
            detail,
            text="Create this action",
            command=self._create_action,
            style="Accent.TButton",
        )
        create_button.pack(side=tk.BOTTOM, anchor=tk.E, pady=(8, 0), before=self.type_detail)
        self.type_list.bind("<<ListboxSelect>>", lambda _event: self._show_type())
        self.type_list.selection_set(0)
        self._show_type()

    def _build_contexts_tab(self, notebook: ConfigurationPageStack) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Contexts", underline=0)

        header = ttk.Frame(tab)
        header.pack(fill=tk.X, pady=(0, 8))
        heading = ttk.Frame(header)
        heading.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            heading,
            text="Manage Contexts",
            style="Title.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            heading,
            text=(
                "A Context organizes items; Focus is the Context currently "
                "highlighted in the palette."
            ),
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))
        self.new_context_button = ttk.Button(
            header,
            text="New Context…",
            command=self._add_context,
            style="Accent.TButton",
        )
        self.new_context_button.pack(side=tk.RIGHT, padx=(10, 0))

        filter_row = ttk.Frame(tab)
        filter_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(filter_row, text="Find").pack(side=tk.LEFT)
        self.context_filter_entry = ttk.Entry(
            filter_row,
            textvariable=self.context_filter_var,
        )
        self.context_filter_entry.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=(6, 8),
        )
        ttk.Label(
            filter_row,
            textvariable=self.context_filter_count_var,
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)
        self.context_tree_frame, self.context_tree = scrollable_tree(
            tab,
            ("source", "actions"),
        )
        self.context_tree.heading("#0", text="Context")
        self.context_tree.heading("source", text="Source")
        self.context_tree.heading("actions", text="Members / Focus shortcuts")
        self.context_tree.column("#0", width=170, minwidth=140)
        self.context_tree.column("source", width=105, minwidth=100, stretch=False)
        self.context_tree.column("actions", width=300, minwidth=190)
        self.context_tree_frame.pack(fill=tk.BOTH, expand=True)
        self.context_tree.bind("<Double-1>", lambda _event: self._edit_context())
        self.context_tree.bind("<Return>", lambda _event: self._edit_context())
        self.context_tree.bind(
            "<<TreeviewSelect>>",
            lambda _event: self._update_context_controls(),
        )
        self.context_filter_var.trace_add(
            "write",
            lambda *_args: self._render_contexts(),
        )

        selection = ttk.Frame(
            tab,
            style="Card.TFrame",
            padding=(10, 8),
        )
        self.context_selection_frame = selection
        selection.pack(
            side=tk.BOTTOM,
            fill=tk.X,
            pady=(8, 0),
            before=self.context_tree_frame,
        )
        selection.columnconfigure(0, weight=1)
        self.context_detail_title_var = tk.StringVar(value="Select a Context")
        self.context_detail_title_label = ttk.Label(
            selection,
            textvariable=self.context_detail_title_var,
            style="Card.TLabel",
            font=("Segoe UI Semibold", 10),
            justify=tk.LEFT,
        )
        self.context_detail_title_label.grid(row=0, column=0, sticky=tk.EW)
        self.context_detail_summary_var = tk.StringVar(
            value="Choose a Context to review its members and Focus shortcuts."
        )
        self.context_detail_summary_label = ttk.Label(
            selection,
            textvariable=self.context_detail_summary_var,
            style="CardMuted.TLabel",
            justify=tk.LEFT,
            wraplength=430,
        )
        self.context_detail_summary_label.grid(
            row=1,
            column=0,
            sticky=tk.EW,
            pady=(3, 0),
        )
        context_commands = ttk.Frame(selection, style="Card.TFrame")
        self.context_commands_frame = context_commands
        context_commands.grid(row=0, column=1, rowspan=2, sticky=tk.E, padx=(10, 0))
        self.context_edit_button = ttk.Button(
            context_commands,
            text="Edit…",
            command=self._edit_context,
            state=tk.DISABLED,
        )
        self.context_edit_button.pack(side=tk.LEFT)
        self.context_delete_button = ttk.Button(
            context_commands,
            text="Delete permanently…",
            command=self._delete_context,
            state=tk.DISABLED,
            style="Danger.TButton",
        )
        self.context_delete_button.pack(side=tk.LEFT, padx=(6, 0))
        selection.bind("<Configure>", self._resize_context_summary, add="+")

    def _build_buttons_tab(self, notebook: ConfigurationPageStack) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Quick actions", underline=0)

        header = ttk.Frame(tab)
        header.pack(fill=tk.X, pady=(0, 8))
        heading = ttk.Frame(header)
        heading.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            heading,
            text="Manage Quick actions",
            style="Title.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            heading,
            text=(
                "Arrange custom shortcut menus; Passwords, Folders, and Prompts "
                "are generated from Actions."
            ),
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))
        self.new_quick_menu_button = ttk.Button(
            header,
            text="New menu…",
            command=self._add_group,
            style="Accent.TButton",
        )
        self.new_quick_menu_button.pack(side=tk.RIGHT, padx=(10, 0))

        filter_row = ttk.Frame(tab)
        filter_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(filter_row, text="Find").pack(side=tk.LEFT)
        self.button_filter_entry = ttk.Entry(
            filter_row,
            textvariable=self.button_filter_var,
        )
        self.button_filter_entry.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=(6, 8),
        )
        ttk.Label(
            filter_row,
            textvariable=self.button_filter_count_var,
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)
        self.button_tree_frame, self.button_tree = scrollable_tree(
            tab,
            ("source", "actions"),
        )
        self.button_tree.heading("#0", text="Menu / item")
        self.button_tree.heading("source", text="Managed by")
        self.button_tree.heading("actions", text="Targets / contents")
        self.button_tree.column("#0", width=180, minwidth=150)
        self.button_tree.column("source", width=105, minwidth=100, stretch=False)
        self.button_tree.column("actions", width=290, minwidth=190)
        self.button_tree_frame.pack(fill=tk.BOTH, expand=True)
        self.button_preview_var = tk.StringVar(
            value="Choose a custom or automatic item to review how it behaves."
        )
        self.button_detail_title_var = tk.StringVar(value="Select a Quick action")
        selection = ttk.Frame(
            tab,
            style="Card.TFrame",
            padding=(10, 8),
        )
        self.button_selection_frame = selection
        selection.pack(
            side=tk.BOTTOM,
            fill=tk.X,
            pady=(8, 0),
            before=self.button_tree_frame,
        )
        selection.columnconfigure(0, weight=1)
        self.button_detail_title_label = ttk.Label(
            selection,
            textvariable=self.button_detail_title_var,
            style="Card.TLabel",
            font=("Segoe UI Semibold", 10),
            justify=tk.LEFT,
        )
        self.button_detail_title_label.grid(row=0, column=0, sticky=tk.EW)
        self.button_preview_label = ttk.Label(
            selection,
            textvariable=self.button_preview_var,
            style="CardMuted.TLabel",
            justify=tk.LEFT,
            wraplength=380,
        )
        self.button_preview_label.grid(
            row=1,
            column=0,
            sticky=tk.EW,
            pady=(3, 0),
        )
        button_commands = ttk.Frame(selection, style="Card.TFrame")
        self.button_commands_frame = button_commands
        button_commands.grid(row=0, column=1, rowspan=2, sticky=tk.E, padx=(10, 0))
        self.new_quick_item_button = ttk.Button(
            button_commands,
            text="New Quick action…",
            command=self._add_button,
            state=tk.DISABLED,
        )
        self.new_quick_item_button.pack(side=tk.LEFT)
        self.quick_item_edit_button = ttk.Button(
            button_commands,
            text="Edit…",
            command=self._edit_button,
            state=tk.DISABLED,
        )
        self.quick_item_edit_button.pack(side=tk.LEFT, padx=(6, 0))
        self.quick_item_move_button = ttk.Menubutton(
            button_commands,
            text="Move",
            state=tk.DISABLED,
        )
        self.quick_item_move_menu = tk.Menu(
            self.quick_item_move_button,
            tearoff=False,
        )
        self.quick_item_move_menu.add_command(
            label="Move up",
            command=lambda: self._move_button(-1),
        )
        self.quick_item_move_menu.add_command(
            label="Move down",
            command=lambda: self._move_button(1),
        )
        self.quick_item_move_button.configure(menu=self.quick_item_move_menu)
        self.quick_item_move_button.pack(side=tk.LEFT, padx=(6, 0))
        self.quick_item_delete_button = ttk.Button(
            button_commands,
            text="Delete permanently…",
            command=self._delete_button,
            state=tk.DISABLED,
            style="Danger.TButton",
        )
        self.quick_item_delete_button.pack(side=tk.LEFT, padx=(6, 0))
        self.button_tree.bind("<Double-1>", lambda _event: self._edit_button())
        self.button_tree.bind("<Return>", lambda _event: self._edit_button())
        self.button_tree.bind(
            "<<TreeviewSelect>>",
            lambda _event: self._update_button_preview(),
        )
        self.button_filter_var.trace_add(
            "write",
            lambda *_args: self._render_buttons(),
        )
        selection.bind("<Configure>", self._resize_button_summary, add="+")

    def _build_diagnostics_tab(self, notebook: ConfigurationPageStack) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Diagnostics", underline=0)
        ttk.Label(
            tab,
            text="Diagnostics",
            style="Title.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            tab,
            text="Review and copy a privacy-safe summary for troubleshooting.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(2, 8))
        diagnostics_frame = ttk.Frame(tab)
        diagnostics_frame.pack(fill=tk.BOTH, expand=True)
        self.diagnostics_text = tk.Text(
            diagnostics_frame,
            wrap=tk.WORD,
            height=18,
            padx=8,
            pady=8,
            takefocus=True,
        )
        diagnostics_scrollbar = ttk.Scrollbar(
            diagnostics_frame,
            orient=tk.VERTICAL,
            command=self.diagnostics_text.yview,
        )
        self.diagnostics_text.configure(yscrollcommand=diagnostics_scrollbar.set)
        self.diagnostics_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        diagnostics_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.diagnostics_scrollbar = diagnostics_scrollbar
        self.diagnostics_text.configure(state=tk.DISABLED)
        controls = ttk.Frame(tab)
        controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0), before=diagnostics_frame)
        self.refresh_diagnostics_button = ttk.Button(
            controls,
            text="Refresh",
            command=self._refresh_diagnostics,
        )
        self.refresh_diagnostics_button.pack(side=tk.LEFT)
        self.copy_diagnostics_button = ttk.Button(
            controls,
            text="Copy safe summary",
            command=self._copy_diagnostics,
            style="Accent.TButton",
        )
        self.copy_diagnostics_button.pack(side=tk.LEFT, padx=(6, 0))

    def _build_backup_restore_tab(self, notebook: ConfigurationPageStack) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Backup and restore", underline=0)
        ttk.Label(
            tab,
            text="Backup & restore",
            style="Title.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            tab,
            text="Create a portable backup or inspect one safely before restoring.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(2, 8))
        self.backup_restore_panel = BackupRestorePanel(
            tab,
            data_paths=self.data_paths,
            on_restore_complete=self._restore_completed,
            on_recovery_required=self._restore_recovery_required,
        )
        self.backup_restore_panel.pack(fill=tk.BOTH, expand=True)

    def _request_close(self) -> None:
        panel = getattr(self, "backup_restore_panel", None)
        if panel is not None and panel.busy:
            self._set_feedback(
                "Wait for the backup or restore operation to finish before closing.",
                False,
            )
            return
        if panel is not None:
            panel.close()
        self._cancel_pending_action_edit()
        self._cancel_pending_action_suggestion()
        self.window.destroy()

    def _restore_completed(self) -> None:
        self.backup_restore_panel.close()
        self._cancel_pending_action_edit()
        self._cancel_pending_action_suggestion()
        self.window.destroy()
        self._launcher_restore_complete()

    def _restore_recovery_required(self) -> None:
        self.backup_restore_panel.close()
        self._cancel_pending_action_edit()
        self._cancel_pending_action_suggestion()
        self.window.destroy()
        self._launcher_recovery_required()

    def _build_work_items_tab(
        self,
        notebook: ConfigurationPageStack,
        sources: tuple[WorkItemSource, ...],
        metadata: dict[str, WorkItemMetadata],
        index: WorkItemIndex,
    ) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Work Items", underline=0)
        self.work_items_panel = WorkItemsConfigurationPanel(
            tab,
            sources=sources,
            metadata=metadata,
            index=index,
            sources_path=self.work_item_sources_path,
            metadata_path=self.work_item_metadata_path,
            settings_path=self.work_item_settings_path,
            contexts_path=self.local_contexts_path,
            on_change=self.on_change,
            feedback=self._set_feedback,
            refresh_configuration=self._reload,
        )

    def _set_feedback(self, message: str, success: bool) -> None:
        self.feedback_var.set(message)
        self.feedback_label.configure(style="Success.TLabel" if success else "Error.TLabel")

    def _show_diagnostics_tab(self, _event: tk.Event | None = None) -> str:
        return self._show_config_named_tab("diagnostics")

    def _show_config_tab(self, tab_index: int) -> str:
        self.notebook.select(tab_index)
        self.window.after_idle(self._focus_current_tab)
        return "break"

    def _focus_selected_tab(self, _event: tk.Event | None = None) -> None:
        self._sync_configuration_navigation()
        self.window.after_idle(self._focus_current_tab)

    def _focus_current_tab(self) -> None:
        selected = self.notebook.index(self.notebook.select())
        if selected == CONFIGURATION_TAB_INDEXES["start"]:
            self.start_primary_button.focus_set()
        elif selected == CONFIGURATION_TAB_INDEXES["work_items"]:
            self.work_items_panel.focus()
        elif selected == CONFIGURATION_TAB_INDEXES["backup_restore"]:
            self.backup_restore_panel.focus_primary()
        else:
            {
                CONFIGURATION_TAB_INDEXES["actions"]: self.action_tree,
                CONFIGURATION_TAB_INDEXES["types"]: self.type_list,
                CONFIGURATION_TAB_INDEXES["contexts"]: self.context_tree,
                CONFIGURATION_TAB_INDEXES["buttons"]: self.button_tree,
                CONFIGURATION_TAB_INDEXES["diagnostics"]: self.diagnostics_text,
            }[selected].focus_set()

    def _show_type(self) -> None:
        selected = self.type_list.curselection()
        if not selected:
            return
        definition = ACTION_TYPES[self.type_ids[selected[0]]]
        self.type_title.set(definition.display_label)
        self.type_family.set(f"{definition.family} · {definition.id}")
        detail = (
            f"{definition.description}\n\nInput\n{definition.input_description}\n\n"
            f"Output\n{definition.output_description}\n\n"
            f"{ACTION_TYPE_EXAMPLES[definition.id]}\n\n"
            f"Portability\n{definition.portability}"
        )
        self.type_detail.configure(state=tk.NORMAL)
        self.type_detail.replace("1.0", tk.END, detail)
        self.type_detail.configure(state=tk.DISABLED)

    def _create_action(self) -> None:
        selected = self.type_list.curselection()
        if selected:
            self._create_action_for_type(self.type_ids[selected[0]])

    def _create_action_for_type(
        self,
        action_type: str,
        *,
        suggestion: ActionCreationSuggestion | None = None,
        initial_quick_action_path: tuple[str, ...] = (),
    ) -> None:
        """Use the one Action form and save path for catalogue and quick creation."""
        if action_type not in CREATABLE_ACTION_TYPES:
            return
        default_text_file_path: Path | None = None
        if action_type == "transform_file_text":
            try:
                default_text_file_path = ensure_default_text_action_file(
                    self.local_actions_path.with_name(DEFAULT_TEXT_ACTION_FILENAME)
                )
            except ActionError as exc:
                messagebox.showerror(
                    "Could not prepare the default text file",
                    str(exc),
                    parent=self.window,
                )
                return
        initial_contexts = (
            () if self.focus_context.casefold() == "general" else (self.focus_context,)
        )
        dialog = ActionDialog(
            self.window,
            action_type,
            self.actions,
            self._save_action,
            context_names=[context.name for context in self.contexts],
            choose_destination=True,
            default_text_file_path=default_text_file_path,
            initial_contexts=initial_contexts,
            initial_title=suggestion.title if suggestion is not None else "",
            initial_value=suggestion.value if suggestion is not None else "",
            suggested_from_workspace=suggestion is not None,
            initial_quick_action_path=initial_quick_action_path,
        )
        self.action_creation_dialog = dialog
        dialog.window.bind(
            "<Destroy>",
            lambda event, created=dialog: self._clear_action_creation_dialog(
                event, created
            ),
            add="+",
        )

    def _clear_action_creation_dialog(
        self,
        event: tk.Event,
        dialog: ActionDialog,
    ) -> None:
        if event.widget is dialog.window and self.action_creation_dialog is dialog:
            self.action_creation_dialog = None

    def _save_action(
        self,
        action: Action,
        destination: str = LOCAL_DESTINATION,
    ) -> bool:
        local = destination != PROJECT_DESTINATION
        if (
            action.type == "sequence"
            and not local
            and set(sequence_reference_ids(action.sequence_steps))
            & self.local_action_ids
        ):
            messagebox.showerror(
                "Action was not created",
                "A Built-in sequence can reference Built-in Actions only. "
                "Choose My configuration or remove personal Action steps.",
                parent=self.window,
            )
            return False
        target_path = self.local_actions_path if local else self.shared_actions_path
        try:
            append_actions_with_context_memberships(
                target_path,
                [action],
                actions_are_local=local,
                shared_contexts_path=self.contexts_path,
                local_contexts_path=self.local_contexts_path,
            )
        except (ActionError, ContextError, OSError) as exc:
            messagebox.showerror(
                "Action was not created",
                f"Context Palette could not create this action.\n\n{exc}",
                parent=self.window,
            )
            return False
        self.on_change()
        self.initial_action_id = action.id
        if self.action_filter_var.get():
            self.action_filter_var.set("")
        self._reload()
        self.feedback_var.set(
            f"Created {destination.lower()} action: {action.display_text}"
        )
        self.feedback_label.configure(style="Success.TLabel")
        return True

    def _focus_action_filter(self, _event: tk.Event | None = None) -> str:
        self.action_filter_entry.focus_set()
        self.action_filter_entry.selection_range(0, tk.END)
        return "break"

    def _focus_current_filter(self, _event: tk.Event | None = None) -> str:
        selected = self.notebook.index(self.notebook.select())
        work_item_search = getattr(
            getattr(self, "work_items_panel", None),
            "search_entry",
            None,
        )
        entry = {
            CONFIGURATION_TAB_INDEXES["actions"]: self.action_filter_entry,
            CONFIGURATION_TAB_INDEXES["contexts"]: self.context_filter_entry,
            CONFIGURATION_TAB_INDEXES["buttons"]: self.button_filter_entry,
            CONFIGURATION_TAB_INDEXES["work_items"]: work_item_search,
        }.get(selected)
        if entry is None:
            self.notebook.select(CONFIGURATION_TAB_INDEXES["actions"])
            entry = self.action_filter_entry
        entry.focus_set()
        entry.selection_range(0, tk.END)
        return "break"

    def _reload(self) -> None:
        self.window.configure(cursor="wait")
        self.window.update_idletasks()
        try:
            self.actions, self.local_action_ids = load_combined_actions(
                self.shared_actions_path,
                self.local_actions_path,
                inspect_external_paths=False,
            )
            self.stored_actions, stored_local_ids = load_combined_stored_actions(
                self.shared_actions_path,
                self.local_actions_path,
                inspect_external_paths=False,
            )
            self.local_action_ids = stored_local_ids
            self.palette_state = load_palette_state(self.palette_path)
            local_contexts = (
                load_contexts(self.local_contexts_path)
                if self.local_contexts_path.exists()
                else []
            )
            self.contexts = load_combined_contexts(self.contexts_path, self.local_contexts_path)
            self.actions = actions_with_canonical_contexts(
                self.actions,
                self.contexts,
            )
            self.stored_actions = actions_with_canonical_contexts(
                self.stored_actions,
                self.contexts,
            )
            self.groups = load_combined_command_groups(
                self.command_surface_path, self.local_command_surface_path
            )
        except (ActionError, ContextError, CommandSurfaceError) as exc:
            self.feedback_var.set(f"Configuration could not be refreshed: {exc}")
            self.feedback_label.configure(style="Error.TLabel")
            return
        finally:
            self.window.configure(cursor="")
        self.local_contexts = local_contexts
        self.local_context_names = {
            item.name.casefold() for item in self.local_contexts
        }
        if hasattr(self, "work_items_panel"):
            self.work_items_panel.set_contexts(tuple(self.local_contexts))
        self._refresh_action_views()

    def _refresh_action_views(self) -> None:
        """Refresh every Configure view derived from the current action list."""

        self._render_actions()
        self._render_pinned_slots()
        self._render_contexts()
        self._render_buttons()
        self._refresh_diagnostics()

    def _render_pinned_slots(self) -> None:
        self.pin_choices = _action_choices(self.actions)
        labels_by_id = {
            action_id: label for label, action_id in self.pin_choices.items()
        }
        for action_id in self.palette_state.pinned_action_ids:
            if action_id not in labels_by_id:
                label = f"Missing action: {action_id}"
                self.pin_choices[label] = action_id
                labels_by_id[action_id] = label
        picker_options = _action_picker_options(
            self.actions,
            choices=self.pin_choices,
        )
        for picker in self.pin_pickers:
            picker.set_options(
                picker_options,
                empty_label=EMPTY_PIN_LABEL,
            )
        self._pins_rendering = True
        try:
            for index, variable in enumerate(self.pin_vars):
                label = EMPTY_PIN_LABEL
                if index < len(self.palette_state.pinned_action_ids):
                    action_id = self.palette_state.pinned_action_ids[index]
                    label = labels_by_id.get(action_id, f"Missing action: {action_id}")
                variable.set(label)
        finally:
            self._pins_rendering = False
        self._pins_dirty = False
        self._update_pin_summary()

    def _save_pinned_slots(self) -> None:
        try:
            action_ids = resolve_pinned_action_ids(
                [variable.get() for variable in self.pin_vars],
                self.pin_choices,
            )
            updated = PaletteState(
                action_ids,
                self.palette_state.focus_context,
                self.palette_state.context_slots,
                self.palette_state.context_membership_version,
                self.palette_state.context_item_slots,
            )
            save_palette_state(self.palette_path, updated)
        except (ActionError, OSError) as exc:
            messagebox.showerror(
                "Pinned slots were not saved",
                f"Context Palette could not save slots 1–5.\n\n{exc}",
                parent=self.window,
            )
            return
        self.palette_state = updated
        self.on_change()
        self._render_pinned_slots()
        self.feedback_var.set(
            f"Saved {len(action_ids)} pinned action(s) in slots 1–5."
        )
        self.feedback_label.configure(style="Success.TLabel")

    def _render_contexts(self) -> None:
        self.context_tree.delete(*self.context_tree.get_children())
        query = self.context_filter_var.get()
        matches = 0
        work_items = self._available_work_items()
        for index, context in enumerate(self.contexts):
            local = context.name.casefold() in self.local_context_names
            if not context_matches_filter(
                context,
                query,
                actions=self.actions,
                work_items=work_items,
                personal=local,
            ):
                continue
            matches += 1
            self.context_tree.insert(
                "", tk.END, iid=f"context-{index}", text=context.name,
                values=(
                    LOCAL_DESTINATION if local else PROJECT_DESTINATION,
                    context_action_summary(context, self.actions, work_items),
                ),
                tags=("local",) if local else ("shared",),
            )
        self.context_tree.tag_configure("shared", foreground="#666666")
        select_first_tree_item(self.context_tree)
        self.context_filter_count_var.set(
            f"{matches} of {len(self.contexts)}"
            if query.strip()
            else f"{len(self.contexts)} contexts"
        )
        self._update_context_controls()

    def _render_buttons(self) -> None:
        self.button_tree.delete(*self.button_tree.get_children())
        self.button_tree_records: dict[
            str,
            tuple[int, tuple[int, ...]],
        ] = {}
        self.action_bound_button_records: dict[
            str,
            ActionBoundQuickSelection,
        ] = {}
        query = self.button_filter_var.get()
        work_items = self._available_work_items()
        action_bound_groups = action_bound_quick_groups(self.actions)
        total_items = (
            sum(command_item_count(group) for group in self.groups)
            + sum(
                command_item_count(group)
                + len(command_group_all_action_ids(group))
                for group in action_bound_groups
            )
        )
        matching_items = self._render_action_bound_button_groups(
            action_bound_groups,
            query,
        )
        for group_index, group in enumerate(self.groups):
            local = bool(
                group.source_path
                and group.source_path.resolve() == self.local_command_surface_path.resolve()
            )

            def item_or_descendant_matches(item: CommandItem) -> bool:
                return quick_action_matches_filter(
                    group,
                    item,
                    query,
                    actions=self.actions,
                    personal=local,
                    work_items=work_items,
                ) or any(
                    item_or_descendant_matches(child)
                    for child in item.items
                )

            group_matches = quick_action_matches_filter(
                group,
                None,
                query,
                actions=self.actions,
                personal=local,
                work_items=work_items,
            )
            if (
                not group_matches
                and not any(
                    item_or_descendant_matches(item)
                    for item in group.items
                )
            ):
                continue
            group_iid = f"group-{group_index}"
            group_action_labels = action_reference_labels(
                command_group_action_ids(group),
                self.actions,
            )
            self.button_tree.insert(
                "", tk.END, iid=group_iid, text=group.label,
                values=(
                    LOCAL_DESTINATION if local else PROJECT_DESTINATION,
                    f"Browse menu · {command_item_count(group)} item(s)"
                    + (
                        f" · At menu root: {', '.join(group_action_labels)}"
                        if group_action_labels
                        else ""
                    ),
                ),
                tags=("local",) if local else ("shared",), open=True,
            )

            def insert_items(
                parent_iid: str,
                items: tuple[CommandItem, ...],
                parent_path: tuple[int, ...],
            ) -> None:
                nonlocal matching_items
                for item_index, item in enumerate(items):
                    if query.strip() and not item_or_descendant_matches(item):
                        continue
                    path = (*parent_path, item_index)
                    iid = (
                        f"button-{group_index}-"
                        + ".".join(str(index) for index in path)
                    )
                    self.button_tree_records[iid] = (group_index, path)
                    labels = quick_action_target_labels(
                        item,
                        self.actions,
                        work_items,
                    )
                    summary = ", ".join(labels)
                    if item.items:
                        child_summary = f"{len(item.items)} submenu(s)"
                        summary = (
                            f"{summary} · {child_summary}"
                            if summary
                            else child_summary
                        )
                    self.button_tree.insert(
                        parent_iid,
                        tk.END,
                        iid=iid,
                        text=item.label,
                        values=(
                            LOCAL_DESTINATION if local else PROJECT_DESTINATION,
                            summary,
                        ),
                        tags=("local",) if local else ("shared",),
                        open=True,
                    )
                    matching_items += 1
                    insert_items(iid, item.items, path)

            insert_items(group_iid, group.items, ())
        self.button_tree.tag_configure("shared", foreground="#666666")
        select_first_tree_item(self.button_tree, descend=True)
        self.button_filter_count_var.set(
            f"{matching_items} of {total_items}"
            if query.strip()
            else f"{total_items} items"
        )
        self._update_button_preview()

    def _render_action_bound_button_groups(
        self,
        groups: tuple[CommandGroup, ...],
        query: str,
    ) -> int:
        actions_by_id = {action.id: action for action in self.actions}
        terms = [term.casefold() for term in query.split() if term.strip()]
        matching_items = 0
        action_counter = 0

        for (_group_id, _label, action_type), group in zip(
            ACTION_BOUND_QUICK_MENU_SPECS,
            groups,
        ):
            eligible_actions = [
                action
                for action in self.actions
                if action.type == action_type and action.state != "Archived"
            ]
            group_searchable = f"{group.label} automatic action-bound".casefold()
            group_matches = bool(terms) and all(
                term in group_searchable for term in terms
            )
            visible_action_ids = {
                action.id
                for action in eligible_actions
                if not terms
                or group_matches
                or (
                    not action.quick_action_path
                    and all(term in "menu root" for term in terms)
                )
                or action_matches_filter(
                    action,
                    query,
                    personal=action.id in self.local_action_ids,
                )
            }
            if terms and not group_matches and not visible_action_ids:
                continue

            group_iid = f"automatic-group-{action_type}"
            self.action_bound_button_records[group_iid] = ActionBoundQuickSelection(
                group.label,
                action_type,
            )
            self.button_tree.insert(
                "",
                tk.END,
                iid=group_iid,
                text=group.label,
                values=(
                    "Automatic",
                    f"{len(eligible_actions)} Active action(s) · edit actions to organize",
                ),
                tags=("automatic",),
                open=True,
            )

            root_action_ids = tuple(
                action_id
                for action_id in command_group_action_ids(group)
                if action_id in visible_action_ids
            )
            for action_id in root_action_ids:
                action = actions_by_id[action_id]
                action_counter += 1
                action_iid = f"automatic-action-{action_type}-{action_counter}"
                self.action_bound_button_records[action_iid] = (
                    ActionBoundQuickSelection(
                        group.label,
                        action_type,
                        (),
                        action.id,
                    )
                )
                self.button_tree.insert(
                    group_iid,
                    tk.END,
                    iid=action_iid,
                    text=action.compact_display_text,
                    values=(
                        LOCAL_DESTINATION
                        if action.id in self.local_action_ids
                        else PROJECT_DESTINATION,
                        "At menu root · edit Action to organize",
                    ),
                    tags=(
                        "local"
                        if action.id in self.local_action_ids
                        else "shared",
                    ),
                )
                matching_items += 1

            def item_has_visible_action(item: CommandItem) -> bool:
                return any(
                    action_id in visible_action_ids
                    for action_id in command_item_action_ids(item)
                ) or any(item_has_visible_action(child) for child in item.items)

            def insert_items(
                parent_iid: str,
                items: tuple[CommandItem, ...],
                parent_path: tuple[str, ...],
            ) -> None:
                nonlocal matching_items, action_counter
                for item_index, item in enumerate(items):
                    if not item_has_visible_action(item):
                        continue
                    path = (*parent_path, item.label)
                    item_iid = (
                        f"automatic-level-{action_type}-{matching_items}-{item_index}"
                    )
                    self.action_bound_button_records[item_iid] = (
                        ActionBoundQuickSelection(group.label, action_type, path)
                    )
                    direct_action_ids = tuple(
                        action_id
                        for action_id in command_item_action_ids(item)
                        if action_id in visible_action_ids
                    )
                    self.button_tree.insert(
                        parent_iid,
                        tk.END,
                        iid=item_iid,
                        text=item.label,
                        values=(
                            "Automatic",
                            f"{len(direct_action_ids)} action(s)"
                            + (f" · {len(item.items)} submenu(s)" if item.items else ""),
                        ),
                        tags=("automatic",),
                        open=True,
                    )
                    matching_items += 1
                    for action_id in direct_action_ids:
                        action = actions_by_id[action_id]
                        action_counter += 1
                        action_iid = f"automatic-action-{action_type}-{action_counter}"
                        self.action_bound_button_records[action_iid] = (
                            ActionBoundQuickSelection(
                                group.label,
                                action_type,
                                path,
                                action.id,
                            )
                        )
                        self.button_tree.insert(
                            item_iid,
                            tk.END,
                            iid=action_iid,
                            text=action.compact_display_text,
                            values=(
                                LOCAL_DESTINATION
                                if action.id in self.local_action_ids
                                else PROJECT_DESTINATION,
                                "Edit action to change its Quick menu path",
                            ),
                            tags=(
                                "local"
                                if action.id in self.local_action_ids
                                else "shared",
                            ),
                        )
                        matching_items += 1
                    insert_items(item_iid, item.items, path)

            insert_items(group_iid, group.items, ())

        return matching_items

    def _refresh_diagnostics(self) -> None:
        summary = summarize_diagnostics(
            self.shared_actions_path.parent / "context-palette.log"
        )
        self.diagnostics_summary = render_safe_diagnostics(
            summary,
            action_count=len(self.actions),
            personal_action_count=len(self.local_action_ids),
            context_count=len(self.contexts),
            button_group_count=len(self.groups),
        )
        self.diagnostics_text.configure(state=tk.NORMAL)
        self.diagnostics_text.replace("1.0", tk.END, self.diagnostics_summary)
        self.diagnostics_text.configure(state=tk.DISABLED)

    def _copy_diagnostics(self) -> None:
        try:
            self.window.clipboard_clear()
            self.window.clipboard_append(self.diagnostics_summary)
            self.window.update()
        except tk.TclError as exc:
            messagebox.showerror(
                "Context Palette",
                f"The safe diagnostics summary could not be copied.\n\n{exc}",
                parent=self.window,
            )
            return
        self.feedback_var.set("Copied the safe diagnostics summary.")
        self.feedback_label.configure(style="Success.TLabel")

    def _render_actions(self) -> None:
        self.action_tree.delete(*self.action_tree.get_children())
        query = self.action_filter_var.get()
        state_filter_var = getattr(self, "action_state_filter_var", None)
        state_filter = state_filter_var.get() if state_filter_var is not None else "Active"
        stored_actions = getattr(self, "stored_actions", self.actions)
        state_actions = [
            action
            for action in stored_actions
            if state_filter == "All" or action.state == state_filter
        ]
        matching_iids: list[str] = []
        requested_iid: str | None = None
        for index, action in enumerate(stored_actions):
            local = action.id in self.local_action_ids
            if action not in state_actions:
                continue
            if not action_matches_filter(action, query, personal=local):
                continue
            iid = f"action-{index}"
            self.action_tree.insert(
                "",
                tk.END,
                iid=iid,
                text=action.title,
                values=(
                    ACTION_TYPES[action.type].display_label,
                    ", ".join(action.effective_contexts) or "General only",
                    LOCAL_DESTINATION if local else PROJECT_DESTINATION,
                    action.state,
                ),
                tags=(
                    "archived",
                    "local" if local else "shared",
                )
                if action.state == "Archived"
                else (("local",) if local else ("shared",)),
            )
            matching_iids.append(iid)
            if (
                self.initial_action_id is not None
                and action.id.casefold() == self.initial_action_id.casefold()
            ):
                requested_iid = iid
        self.action_tree.tag_configure("shared", foreground="#666666")
        self.action_tree.tag_configure("archived", foreground="#777777")
        self.action_tree.configure(
            displaycolumns=(
                ("type", "contexts", "source", "state")
                if state_filter == "All"
                else ("type", "contexts", "source")
            )
        )
        self.action_filter_count_var.set(
            f"{len(matching_iids)} of {len(state_actions)}"
            if query.strip()
            else (
                f"{len(state_actions)} {state_filter.lower()}"
                if state_filter != "All"
                else f"{len(state_actions)} actions"
            )
        )
        if hasattr(self, "action_state_help_var"):
            guidance = {
                "Active": "Active actions appear in the launcher and can be run.",
                "Archived": (
                    "Archived actions are kept for review or restore and do not "
                    "appear in the launcher."
                ),
                "All": "Archived actions are kept but cannot run until restored.",
            }[state_filter]
            if not state_actions:
                guidance = (
                    "No Archived actions. Archive an Action when you may want it later."
                    if state_filter == "Archived"
                    else "No Active actions. Switch Show to Archived to restore one."
                    if state_filter == "Active"
                    else "No actions have been configured yet."
                )
            self.action_state_help_var.set(guidance)
        if matching_iids:
            selected_iid = requested_iid or matching_iids[0]
            self.action_tree.selection_set(selected_iid)
            self.action_tree.focus(selected_iid)
            self.action_tree.see(selected_iid)
        self._update_action_controls()

    def _selected_stored_action(self) -> Action | None:
        selection = self.action_tree.selection()
        if not selection:
            return None
        stored_actions = getattr(self, "stored_actions", self.actions)
        return stored_actions[int(selection[0].split("-")[1])]

    def _update_action_controls(self) -> None:
        if not hasattr(self, "action_lifecycle_button"):
            return
        action = self._selected_stored_action()
        if action is None:
            self.action_detail_title_var.set("Select an Action")
            self.action_detail_summary_var.set(
                "Contexts, tags, ownership, and lifecycle appear here."
            )
            self.action_edit_button.configure(state=tk.DISABLED)
            self.action_lifecycle_button.configure(state=tk.DISABLED)
            self.delete_action_button.configure(state=tk.DISABLED)
            return
        archived = action.state == "Archived"
        local = action.id in self.local_action_ids
        self.action_detail_title_var.set(compact_selection_title(action.title))
        self.action_detail_summary_var.set(
            (
                f"{ACTION_TYPES[action.type].display_label} · {action.state} · "
                f"{LOCAL_DESTINATION if local else PROJECT_DESTINATION}\n"
                f"Contexts: {', '.join(action.effective_contexts) or 'General only'}   "
                f"Tags: {', '.join(action.effective_tags) or '—'}"
            )
        )
        self.action_edit_button.configure(state=tk.NORMAL)
        self.action_lifecycle_button.configure(
            text="Restore…" if archived else "Archive…",
            state=tk.NORMAL,
        )
        self.delete_action_button.configure(
            state=tk.NORMAL if archived else tk.DISABLED
        )

    def _selected_context_record(
        self,
    ) -> tuple[ContextDefinition, str] | None:
        selection = self.context_tree.selection()
        if not selection:
            return None
        context = self.contexts[int(selection[0].split("-")[1])]
        values = self.context_tree.item(selection[0], "values")
        source = values[0] if values else PROJECT_DESTINATION
        return context, source

    def _update_context_controls(self) -> None:
        if not hasattr(self, "context_edit_button"):
            return
        selected = self._selected_context_record()
        if selected is None:
            self.context_detail_title_var.set("Select a Context")
            self.context_detail_summary_var.set(
                "Choose a Context to review its members and Focus shortcuts."
            )
            self.context_edit_button.configure(state=tk.DISABLED)
            self.context_delete_button.configure(state=tk.DISABLED)
            return
        context, source = selected
        member_count = context_membership_count(context, self.actions)
        preferred_count = len(context.preferred_items)
        description = " ".join(context.description.split()) or "No description"
        self.context_detail_title_var.set(
            compact_selection_title(context.name)
        )
        self.context_detail_summary_var.set(
            compact_selection_summary(
                f"{source} · {member_count} member(s) · "
                f"{preferred_count} Focus shortcut(s) · {description}"
            )
        )
        self.context_edit_button.configure(state=tk.NORMAL)
        self.context_delete_button.configure(state=tk.NORMAL)

    def _edit_action(self) -> None:
        action = self._selected_stored_action()
        if action is None:
            return
        self._edit_action_record(action)

    def _edit_action_by_id(self, action_id: str) -> None:
        action = next(
            (
                candidate
                for candidate in self.actions
                if candidate.id.casefold() == action_id.casefold()
            ),
            None,
        )
        if action is None:
            self.feedback_var.set(
                "That Action is no longer available. Configure was refreshed."
            )
            self.feedback_label.configure(style="Error.TLabel")
            return
        self._edit_action_record(action)

    def _schedule_action_edit(self, action_id: str) -> None:
        self._pending_action_edit_id = action_id
        if self._pending_action_edit_after_id is not None:
            return
        self._pending_action_edit_after_id = self.window.after_idle(
            self._open_pending_action_edit
        )

    def _open_pending_action_edit(self) -> None:
        self._pending_action_edit_after_id = None
        action_id = self._pending_action_edit_id
        self._pending_action_edit_id = None
        if action_id is not None:
            self._edit_action_by_id(action_id)

    def _cancel_pending_action_edit(self) -> None:
        after_id = getattr(self, "_pending_action_edit_after_id", None)
        if after_id is not None:
            try:
                self.window.after_cancel(after_id)
            except tk.TclError:
                pass
        self._pending_action_edit_after_id = None
        self._pending_action_edit_id = None

    def _edit_action_record(self, action: Action) -> None:
        existing_dialog = getattr(self, "action_edit_dialog", None)
        if existing_dialog is not None:
            try:
                if existing_dialog.window.winfo_exists():
                    existing_dialog.window.lift()
                    existing_dialog.window.focus_force()
                    return
            except tk.TclError:
                pass
            self.action_edit_dialog = None
        local = action.id in self.local_action_ids
        if not local and not messagebox.askokcancel(
                "Edit built-in action?",
                "This action is part of Context Palette's built-in starter "
                "configuration and is tracked by Git.\n\nChanging it affects the "
                "defaults delivered after commit, push, and pull. Do not put "
                "personal paths, secrets, or private work details in a built-in "
                "action.\n\nContinue editing this built-in action?",
                parent=self.window,
            ):
            return
        target_path = self.local_actions_path if local else self.shared_actions_path
        dialog = ActionDialog(
            self.window,
            action.type,
            getattr(self, "stored_actions", self.actions),
            lambda edited: self._save_edited_action(edited, target_path),
            action=action,
            context_names=[context.name for context in self.contexts],
            default_text_file_path=(
                self.local_actions_path.with_name(DEFAULT_TEXT_ACTION_FILENAME)
                if action.type == "transform_file_text"
                else None
            ),
        )
        self.action_edit_dialog = dialog
        dialog.window.bind(
            "<Destroy>",
            lambda event, opened=dialog: self._clear_action_edit_dialog(
                event, opened
            ),
            add="+",
        )

    def _clear_action_edit_dialog(
        self,
        event: tk.Event,
        dialog: ActionDialog,
    ) -> None:
        if event.widget is dialog.window and self.action_edit_dialog is dialog:
            self.action_edit_dialog = None

    def _save_edited_action(self, action: Action, target_path: Path) -> bool:
        if action.state == "Archived" and action.effective_contexts:
            messagebox.showerror(
                "Action was not saved",
                "An Archived Action cannot be assigned to a Context. Restore it "
                "first, then add the wanted Context membership.",
                parent=self.window,
            )
            return False
        previous_action = next(
            (
                existing
                for existing in getattr(self, "stored_actions", self.actions)
                if existing.id == action.id
            ),
            None,
        )
        if previous_action is None:
            messagebox.showerror(
                "Action was not saved",
                f"Action was not found: {action.id}",
                parent=self.window,
            )
            return False
        local = target_path == self.local_actions_path
        if (
            action.type == "sequence"
            and not local
            and set(sequence_reference_ids(action.sequence_steps))
            & self.local_action_ids
        ):
            messagebox.showerror(
                "Action was not saved",
                "A Built-in sequence can reference Built-in Actions only.",
                parent=self.window,
            )
            return False
        try:
            update_action_with_context_memberships(
                target_path,
                action,
                previous_action,
                action_is_local=local,
                shared_contexts_path=self.contexts_path,
                local_contexts_path=self.local_contexts_path,
            )
        except (ActionError, ContextError, OSError) as exc:
            messagebox.showerror(
                "Action was not saved",
                f"Context Palette could not save this action.\n\n{exc}\n\n"
                "The existing action file was left unchanged. Close any program "
                "that may be locking the file, check that its folder is available, "
                "and try again.",
                parent=self.window,
            )
            return False
        self.on_change()
        if self.action_filter_var.get():
            self.action_filter_var.set("")
        self._reload()
        self.feedback_var.set(f"Saved action: {action.display_text}")
        self.feedback_label.configure(style="Success.TLabel")
        return True

    def _change_action_state(self) -> None:
        action = self._selected_stored_action()
        if action is None:
            return
        local = action.id in self.local_action_ids
        action_path = self.local_actions_path if local else self.shared_actions_path
        shared_warning = ""
        if not local:
            shared_warning = (
                "\n\nThis changes Built-in starter configuration tracked through "
                "Git and can affect other computers after commit, push, and pull."
            )

        if action.state == "Archived":
            if action.type == "sequence":
                try:
                    resolve_sequence_steps(
                        action.sequence_steps,
                        self.actions,
                        sequence_id=action.id,
                    )
                except ActionSequenceError as exc:
                    messagebox.showerror(
                        "Action was not restored",
                        f"Repair its sequence steps first.\n\n{exc}",
                        parent=self.window,
                    )
                    return
            if not messagebox.askyesno(
                "Restore action?",
                f'Restore "{action.title}" as Active?\n\nIt will return to normal '
                "launcher search. Previous pins, Context membership, Focus slots, "
                f"and configured Quick actions will not be recreated.{shared_warning}",
                parent=self.window,
            ):
                return
            try:
                restore_action(action_path, action.id)
            except (ActionDeletionError, OSError) as exc:
                messagebox.showerror(
                    "Action was not restored", str(exc), parent=self.window
                )
                return
            self.action_state_filter_var.set("Active")
            self.initial_action_id = action.id
            self.on_change()
            self._reload()
            owner = LOCAL_DESTINATION.lower() if local else "built-in"
            self.feedback_var.set(
                f"Restored {owner} action: {action.title}. "
                "Reassign saved placements as needed."
            )
            self.feedback_label.configure(style="Success.TLabel")
            return

        blockers = dependent_sequences(
            self.stored_actions,
            action.id,
            include_archived=False,
        )
        if blockers:
            messagebox.showerror(
                "Action was not archived",
                "Archive or edit these active sequences first:\n\n"
                + "\n".join(sequence.title for sequence in blockers),
                parent=self.window,
            )
            return
        try:
            usage = inspect_action_references(
                action.id,
                context_paths=(self.contexts_path, self.local_contexts_path),
                command_surface_paths=(
                    self.command_surface_path,
                    self.local_command_surface_path,
                ),
                palette_path=self.palette_path,
            )
        except (ActionDeletionError, OSError) as exc:
            messagebox.showerror("Action was not archived", str(exc), parent=self.window)
            return
        impact = (
            f"{usage.references_removed} saved reference(s) will be removed."
            if usage.references_removed
            else "It has no saved pins, Focus slots, Contexts, or Quick actions."
        )
        if usage.buttons_removed:
            impact += (
                f"\n{usage.buttons_removed} empty Quick-action button(s) will also "
                "be removed."
            )
        if not messagebox.askyesno(
            "Archive action?",
            f'Archive "{action.title}"?\n\nIt will disappear from normal '
            f"discovery and saved placements. {impact}\n\nThe Action remains "
            "editable under Show: Archived and can be restored later. Restoring "
            f"does not recreate removed assignments.{shared_warning}",
            icon=messagebox.WARNING,
            parent=self.window,
        ):
            return
        try:
            report = archive_action_and_references(
                action_path,
                action.id,
                context_paths=(self.contexts_path, self.local_contexts_path),
                command_surface_paths=(
                    self.command_surface_path,
                    self.local_command_surface_path,
                ),
                palette_path=self.palette_path,
                sequence_paths=(self.shared_actions_path, self.local_actions_path),
            )
        except (ActionDeletionError, OSError) as exc:
            # Reference cleanup intentionally precedes the state write. A
            # failure can therefore leave a valid Active action with fewer
            # placements; reload every view before explaining that outcome.
            self.on_change()
            self._reload()
            messagebox.showerror("Action was not archived", str(exc), parent=self.window)
            return
        self.initial_action_id = None
        self.on_change()
        self._reload()
        self.feedback_var.set(
            f"Archived action: {action.title}. Removed "
            f"{report.references_removed} saved reference(s)."
        )
        self.feedback_label.configure(style="Success.TLabel")

    def _delete_action(self) -> None:
        action = self._selected_stored_action()
        if action is None or action.state != "Archived":
            return
        local = action.id in self.local_action_ids
        blockers = dependent_sequences(
            self.stored_actions,
            action.id,
            include_archived=True,
        )
        if blockers:
            messagebox.showerror(
                "Action was not deleted",
                "Edit or delete these sequences first:\n\n"
                + "\n".join(sequence.title for sequence in blockers),
                parent=self.window,
            )
            return
        try:
            usage = inspect_action_references(
                action.id,
                context_paths=(self.contexts_path, self.local_contexts_path),
                command_surface_paths=(
                    self.command_surface_path,
                    self.local_command_surface_path,
                ),
                palette_path=self.palette_path,
            )
        except (ActionDeletionError, OSError) as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.window)
            return

        impact = (
            f"{usage.references_removed} saved reference(s) will also be removed."
            if usage.references_removed
            else "No saved pins, Focus slots, contexts, or quick buttons reference it."
        )
        if usage.buttons_removed:
            impact += (
                f"\n{usage.buttons_removed} quick button(s) with no remaining "
                "action will be removed."
            )
        shared_warning = ""
        if not local:
            shared_warning = (
                "\n\nThis is a built-in action. Its deletion and reference changes "
                "alter the starter configuration tracked through Git."
            )
        if not messagebox.askyesno(
            "Delete archived action permanently?",
            f'Delete “{action.title}”?\n\n{impact}{shared_warning}\n\n'
            "This cannot be undone inside Context Palette.",
            icon=messagebox.WARNING,
            parent=self.window,
        ):
            return

        action_path = self.local_actions_path if local else self.shared_actions_path
        try:
            report = delete_action_and_references(
                action_path,
                action.id,
                context_paths=(self.contexts_path, self.local_contexts_path),
                command_surface_paths=(
                    self.command_surface_path,
                    self.local_command_surface_path,
                ),
                palette_path=self.palette_path,
                sequence_paths=(self.shared_actions_path, self.local_actions_path),
            )
        except (ActionDeletionError, OSError) as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.window)
            return
        self.stored_actions[:] = [
            existing for existing in self.stored_actions if existing.id != action.id
        ]
        self.local_action_ids.discard(action.id)
        self.initial_action_id = None
        self.on_change()
        self._reload()
        self.feedback_var.set(
            f"Deleted action: {action.title}. "
            f"Removed {report.references_removed} saved reference(s)."
        )
        self.feedback_label.configure(style="Success.TLabel")

    def _add_context(self) -> None:
        ContextDialog(
            self.window,
            None,
            self.actions,
            lambda context, original, destination: self._save_context(
                context,
                original,
                target_path=(
                    self.contexts_path
                    if destination == PROJECT_DESTINATION
                    else self.local_contexts_path
                ),
            ),
            work_items=self._available_work_items(),
            choose_destination=True,
        )

    def _edit_context(self) -> None:
        selected = self._selected_context_record()
        if selected is None:
            return
        context, source = selected
        local = source == LOCAL_DESTINATION
        if not local and not messagebox.askokcancel(
                "Edit built-in context?",
                "This context is part of the built-in starter configuration tracked "
                "by Git.\n\nChanging it alters the defaults delivered after commit, "
                "push, and pull. "
                "Context Palette will save the change permanently and keep a backup.\n\n"
                "Continue editing this built-in context?",
                parent=self.window,
            ):
            return
        target_path = self.local_contexts_path if local else self.contexts_path
        ContextDialog(
            self.window,
            context,
            self._actions_for_quick_action_storage(project=not local),
            lambda edited, original: self._save_context(
                edited,
                original,
                target_path=target_path,
            ),
            work_items=(self._available_work_items() if local else ()),
            shared=not local,
        )

    def _save_context(
        self,
        context: ContextDefinition,
        original_name: str,
        *,
        target_path: Path | None = None,
    ) -> bool:
        destination = target_path or self.local_contexts_path
        built_in = destination.resolve() == self.contexts_path.resolve()
        local_references = [
            action_id
            for action_id in dict.fromkeys(
                (
                    *(context.action_ids or ()),
                    *context.preferred_action_ids,
                )
            )
            if action_id in getattr(self, "local_action_ids", set())
        ]
        work_item_references = tuple(
            dict.fromkeys(
                (
                    *context.work_item_refs,
                    *(
                        reference.work_item_ref
                        for reference in context.preferred_items
                        if reference.work_item_ref is not None
                    ),
                )
            )
        )
        if built_in and (local_references or work_item_references):
            messagebox.showerror(
                "Context was not saved",
                "Built-in contexts can use only built-in actions. Remove My "
                "configuration Actions and Work Items, then try again.",
                parent=self.window,
            )
            return False
        other_path = (
            self.contexts_path
            if destination.resolve() == self.local_contexts_path.resolve()
            else self.local_contexts_path
        )
        try:
            other_names = {
                item.name.casefold()
                for item in (load_contexts(other_path) if other_path.exists() else [])
            }
            if context.name.casefold() in other_names:
                messagebox.showerror(
                    "Context Palette",
                    "A context in the other configuration file already uses that name.",
                    parent=self.window,
                )
                return False
            if original_name and original_name != context.name:
                rename_context_and_references(
                    destination,
                    original_name,
                    context,
                    action_paths=(self.shared_actions_path, self.local_actions_path),
                    palette_path=self.palette_path,
                )
            else:
                save_context(destination, context, original_name=original_name)
        except (ContextError, OSError) as exc:
            recovery = (
                "\n\nA rename is performed through a safe intermediate state. If "
                "both the old and new names now appear, no action membership was "
                "orphaned; close and reopen Configure, then retry the rename."
                if original_name and original_name != context.name
                else "\n\nThe existing context file was left unchanged."
            )
            messagebox.showerror(
                "Context was not saved",
                f"Context Palette could not save this context.\n\n{exc}"
                f"{recovery}\n\nClose any program "
                "that may be locking the file, check that its folder is available, "
                "and try again.",
                parent=self.window,
            )
            return False
        self.on_change()
        self._reload()
        self.feedback_var.set(f"Saved context: {context.name}")
        self.feedback_label.configure(style="Success.TLabel")
        return True

    def _delete_context(self) -> None:
        selected = self._selected_context_record()
        if selected is None:
            return
        context, source = selected
        local = source == LOCAL_DESTINATION
        destination = self.local_contexts_path if local else self.contexts_path
        membership_count = context_membership_count(context, self.actions)
        membership_label = (
            "Palette item(s)"
            if context.work_item_refs
            or any(
                reference.work_item_ref is not None
                for reference in context.preferred_items
            )
            else "action(s)"
        )
        shared_warning = (
            "\n\nThis changes the built-in starter configuration tracked by "
            "Git and affects other computers after commit, push, and pull."
            if not local
            else ""
        )
        if not messagebox.askyesno(
            "Delete context?",
            f'Delete "{context.name}" permanently?\n\n'
            f"{membership_count} {membership_label} will be moved to General if they have "
            "no other specific context. Saved Focus slots for this context will "
            "also be removed.\n\n"
            f"Storage: {LOCAL_DESTINATION if local else PROJECT_DESTINATION}"
            f"{shared_warning}",
            icon=messagebox.WARNING,
            parent=self.window,
        ):
            return
        try:
            delete_context_and_memberships(
                destination,
                context.name,
                action_paths=(self.shared_actions_path, self.local_actions_path),
                palette_path=self.palette_path,
            )
        except (ContextDeletionError, OSError) as exc:
            messagebox.showerror(
                "Context was not deleted",
                f"Context Palette could not delete this context.\n\n{exc}",
                parent=self.window,
            )
            return
        self.on_change()
        try:
            self.actions, self.local_action_ids = load_combined_actions(
                self.shared_actions_path,
                self.local_actions_path,
                inspect_external_paths=False,
            )
        except (ActionError, ActionSequenceError) as exc:
            messagebox.showerror(
                "Context deleted; reload needed",
                f"The context was deleted, but actions could not be reloaded.\n\n{exc}",
                parent=self.window,
            )
        self._reload()
        self.feedback_var.set(
            f"Deleted context: {context.name}. Removed its assignment from "
            f"{membership_count} {membership_label}."
        )
        self.feedback_label.configure(style="Success.TLabel")

    def _add_group(self) -> None:
        GroupDialog(
            self.window,
            None,
            self._save_group,
            actions=self.actions,
            choose_destination=True,
        )

    def _save_group(
        self,
        group: CommandGroup,
        original_group_id: str,
        destination: str,
    ) -> bool:
        target_path = (
            self.command_surface_path
            if destination == PROJECT_DESTINATION
            else self.local_command_surface_path
        )
        local_references = [
            action_id
            for action_id in command_group_all_action_ids(group)
            if action_id in getattr(self, "local_action_ids", set())
        ]
        if (
            destination == PROJECT_DESTINATION
            and local_references
        ):
            messagebox.showerror(
                "Quick-action menu was not saved",
                "Built-in Quick actions can use only Built-in Actions. Remove "
                "the My configuration action assignment and try again.",
                parent=self.window,
            )
            return False
        other_path = (
            self.local_command_surface_path
            if target_path.resolve() == self.command_surface_path.resolve()
            else self.command_surface_path
        )
        try:
            other_ids = {
                item.id.casefold()
                for item in (
                    load_command_groups(other_path)
                    if other_path.exists()
                    else []
                )
            }
            if group.id.casefold() in other_ids:
                raise CommandSurfaceError(
                    "A Quick-action menu in the other storage location already "
                    f'uses the name "{group.label}".'
                )
            save_command_group(
                target_path,
                group,
                original_group_id=original_group_id,
            )
        except (CommandSurfaceError, OSError) as exc:
            messagebox.showerror(
                "Quick-action menu was not saved",
                f"Context Palette could not save this menu.\n\n{exc}",
                parent=self.window,
            )
            return False
        self.on_change()
        self._reload()
        self.feedback_var.set(f"Saved Quick-action menu: {group.label}")
        self.feedback_label.configure(style="Success.TLabel")
        return True

    def _selected_button_parts(
        self,
    ) -> tuple[CommandGroup, CommandItem | None] | None:
        record = self._selected_button_record()
        if record is None:
            return None
        group, item, _path = record
        return group, item

    def _selected_action_bound_button_record(
        self,
    ) -> ActionBoundQuickSelection | None:
        selection = self.button_tree.selection()
        if not selection:
            return None
        return getattr(self, "action_bound_button_records", {}).get(selection[0])

    def _selected_button_record(
        self,
    ) -> tuple[CommandGroup, CommandItem | None, tuple[int, ...]] | None:
        selection = self.button_tree.selection()
        if not selection:
            return None
        iid = selection[0]
        parts = iid.split("-")
        if parts[0] == "group" and len(parts) == 2:
            return self.groups[int(parts[1])], None, ()
        if parts[0] == "button" and len(parts) == 3:
            record = getattr(self, "button_tree_records", {}).get(iid)
            if record is not None:
                group_index, path = record
            else:
                group_index = int(parts[1])
                path = tuple(int(index) for index in parts[2].split("."))
            group = self.groups[group_index]
            return group, command_item_at_path(group, path), path
        return None

    def _group_target_path(self, group: CommandGroup) -> Path:
        if (
            group.source_path
            and group.source_path.resolve()
            == self.local_command_surface_path.resolve()
        ):
            return self.local_command_surface_path
        return self.command_surface_path

    def _actions_for_quick_action_storage(self, *, project: bool) -> list[Action]:
        if not project:
            return self.actions
        return [
            action
            for action in self.actions
            if action.id not in self.local_action_ids
        ]

    def _available_work_items(self) -> tuple[DiscoveredWorkItem, ...]:
        panel = getattr(self, "work_items_panel", None)
        index = getattr(panel, "index", None)
        if index is not None:
            return index.items
        return getattr(self, "work_item_index", WorkItemIndex()).items

    def _add_button(self) -> None:
        action_bound = self._selected_action_bound_button_record()
        if action_bound is not None:
            if action_bound.action_id:
                return
            self.create_action_for_automatic_menu(
                action_bound.action_type,
                action_bound.path,
            )
            return
        selected = self._selected_button_record()
        if selected is None:
            messagebox.showinfo(
                "Select a group",
                "Select the group that should contain the new Quick action, "
                "or create a group first.",
                parent=self.window,
            )
            return
        group, item, path = selected
        if len(path) >= MAX_COMMAND_MENU_LEVELS:
            messagebox.showinfo(
                "Maximum menu depth",
                f"Quick-action menus support {MAX_COMMAND_MENU_LEVELS} levels "
                "below the group. Select the group or a higher level.",
                parent=self.window,
            )
            return
        parent_item_ids = (
            command_item_id_path(group, path)
            if item is not None
            else ()
        )
        target_path = self._group_target_path(group)
        project = target_path.resolve() == self.command_surface_path.resolve()
        if project and not messagebox.askokcancel(
            "Add built-in submenu?" if item is not None else "Add built-in Quick action?",
            ("This submenu" if item is not None else "This Quick action")
            + " will become part of the built-in starter "
            "configuration tracked by Git and delivered after commit, push, "
            "and pull.\n\nContinue?",
            parent=self.window,
        ):
            return
        ButtonDialog(
            self.window,
            group,
            None,
            self._actions_for_quick_action_storage(project=project),
            lambda *args: self._save_button(
                *args,
                target_path=target_path,
                parent_item_ids=parent_item_ids,
            ),
            shared=project,
            work_items=() if project else self._available_work_items(),
            creating_submenu=item is not None,
        )

    def _edit_button(self) -> None:
        action_bound = self._selected_action_bound_button_record()
        if action_bound is not None:
            if action_bound.action_id:
                action = next(
                    (
                        candidate
                        for candidate in self.actions
                        if candidate.id == action_bound.action_id
                    ),
                    None,
                )
                if action is not None:
                    self._edit_action_record(action)
                else:
                    self.feedback_var.set(
                        "That automatic Quick-action entry is no longer available."
                    )
                    self._reload()
                return
            self._manage_action_bound_quick_selection(action_bound)
            return
        selected = self._selected_button_record()
        if selected is None:
            return
        group, item, _path = selected
        target_path = self._group_target_path(group)
        local = target_path.resolve() == self.local_command_surface_path.resolve()
        if not local and not messagebox.askokcancel(
                "Edit built-in Quick actions?",
                "This menu is part of the built-in starter configuration tracked "
                "by Git.\n\nChanging it alters the defaults delivered after commit, "
                "push, and pull. "
                "Context Palette will save the change permanently and keep a backup.\n\n"
                "Continue editing this built-in configuration?",
                parent=self.window,
            ):
            return
        if item is None:
            GroupDialog(
                self.window,
                group,
                self._save_group,
                actions=self._actions_for_quick_action_storage(
                    project=not local
                ),
                destination=(
                    LOCAL_DESTINATION if local else PROJECT_DESTINATION
                ),
            )
            return
        ButtonDialog(
            self.window,
            group,
            item,
            self._actions_for_quick_action_storage(project=not local),
            lambda *args: self._save_button(*args, target_path=target_path),
            shared=not local,
            work_items=() if not local else self._available_work_items(),
        )

    def _manage_action_bound_quick_selection(
        self,
        selection: ActionBoundQuickSelection,
    ) -> None:
        query_parts = [ACTION_TYPES[selection.action_type].label]
        if selection.path:
            query_parts.extend(selection.path)
        self.notebook.select(CONFIGURATION_TAB_INDEXES["actions"])
        self.action_state_filter_var.set("Active")
        self.action_filter_var.set(" ".join(query_parts))
        self.action_filter_entry.focus_set()
        self.action_filter_entry.selection_range(0, tk.END)
        self.feedback_var.set(
            f"Edit a {selection.group_label} action and change Quick menu to reorganize it."
        )
        self.feedback_label.configure(style="Success.TLabel")

    def _show_action_bound_quick_guidance(
        self,
        selection: ActionBoundQuickSelection,
    ) -> None:
        messagebox.showinfo(
            "Automatic Quick-action menu",
            f"{selection.group_label} is generated from Active "
            f"{ACTION_TYPES[selection.action_type].display_label} actions.\n\n"
            "Choose Edit selected, then edit an action's Quick menu field to "
            "create, rename, or move nested levels. Create another matching "
            "action to add it automatically.",
            parent=self.window,
        )

    def _save_button(
        self, group_id: str, group_label: str, item: CommandItem,
        original_group_id: str, original_item_id: str,
        *,
        target_path: Path | None = None,
        parent_item_ids: tuple[str, ...] = (),
    ) -> bool:
        destination = target_path or self.local_command_surface_path
        project = destination.resolve() == self.command_surface_path.resolve()
        if project and command_item_work_item_references(item):
            messagebox.showerror(
                "Quick-action item was not saved",
                "Work Items are personal and can be assigned only to My "
                "configuration Quick actions.",
                parent=self.window,
            )
            return False
        local_references = [
            action_id
            for action_id in command_item_action_ids(item)
            if action_id in getattr(self, "local_action_ids", set())
        ]
        if project and local_references:
            messagebox.showerror(
                "Quick-action item was not saved",
                "Built-in Quick actions can use only built-in actions. Remove "
                "the My configuration action assignment and try again.",
                parent=self.window,
            )
            return False
        other_path = (
            self.command_surface_path
            if destination.resolve() == self.local_command_surface_path.resolve()
            else self.local_command_surface_path
        )
        try:
            other_group_ids = {
                group.id.casefold()
                for group in (
                    load_command_groups(other_path)
                    if other_path.exists()
                    else []
                )
            }
            if group_id.strip().casefold() in other_group_ids:
                messagebox.showerror(
                    "Context Palette",
                    "A Quick-action menu in the other configuration file already uses that stable ID.",
                    parent=self.window,
                )
                return False
            nesting_options = (
                {"parent_item_ids": parent_item_ids}
                if parent_item_ids
                else {}
            )
            save_command_item(
                destination,
                group_id=group_id, group_label=group_label, item=item,
                original_group_id=original_group_id, original_item_id=original_item_id,
                **nesting_options,
            )
        except (CommandSurfaceError, OSError) as exc:
            messagebox.showerror(
                "Quick-action item was not saved",
                f"Context Palette could not save this Quick-action item.\n\n{exc}\n\n"
                "The existing Quick-action file was left unchanged. Close any program "
                "that may be locking the file, check that its folder is available, "
                "and try again.",
                parent=self.window,
            )
            return False
        self.on_change()
        self._reload()
        self.feedback_var.set(f"Saved Quick-action item: {item.label}")
        self.feedback_label.configure(style="Success.TLabel")
        return True

    def _delete_button(self) -> None:
        action_bound = self._selected_action_bound_button_record()
        if action_bound is not None:
            self._show_action_bound_quick_guidance(action_bound)
            return
        selected = self._selected_button_record()
        if selected is None:
            return
        group, item, _path = selected
        target_path = self._group_target_path(group)
        project = target_path.resolve() == self.command_surface_path.resolve()
        noun = "menu" if item is None else "Quick-action item"
        label = group.label if item is None else item.label
        detail = (
            f"All {command_item_count(group)} item(s) in this menu will be removed."
            if item is None and group.items
            else (
                f"This level and its {command_item_subtree_count(item) - 1} "
                "nested level(s) will be removed. Assigned actions remain "
                "available elsewhere."
            )
            if item is not None and item.items
            else "Its assigned actions remain available elsewhere."
        )
        shared_warning = (
            "\n\nThis changes the built-in starter configuration tracked by "
            "Git and affects other computers after commit, push, and pull."
            if project
            else ""
        )
        if not messagebox.askyesno(
            f"Delete {noun}?",
            f'Delete "{label}" permanently?\n\n{detail}\n\n'
            f"Storage: "
            f"{PROJECT_DESTINATION if project else LOCAL_DESTINATION}"
            f"{shared_warning}",
            icon=messagebox.WARNING,
            parent=self.window,
        ):
            return
        try:
            if item is None:
                delete_command_group(target_path, group.id)
            else:
                delete_command_item(target_path, group.id, item.id)
        except (CommandSurfaceError, OSError) as exc:
            messagebox.showerror(
                f"{noun.title()} was not deleted",
                f"Context Palette could not delete it.\n\n{exc}",
                parent=self.window,
            )
            return
        self.on_change()
        self._reload()
        self.feedback_var.set(f"Deleted {noun}: {label}")
        self.feedback_label.configure(style="Success.TLabel")

    def _move_button(self, offset: int) -> None:
        action_bound = self._selected_action_bound_button_record()
        if action_bound is not None:
            self._show_action_bound_quick_guidance(action_bound)
            return
        selected = self._selected_button_record()
        if selected is None:
            return
        group, item, _path = selected
        target_path = self._group_target_path(group)
        project = target_path.resolve() == self.command_surface_path.resolve()
        if project and not messagebox.askokcancel(
            "Move built-in Quick action?",
            "This changes the order in the built-in starter configuration "
            "tracked by Git and affects other computers after commit, push, "
            "and pull.\n\nContinue?",
            parent=self.window,
        ):
            return
        try:
            moved = (
                move_command_group(target_path, group.id, offset)
                if item is None
                else move_command_item(target_path, group.id, item.id, offset)
            )
        except (CommandSurfaceError, OSError) as exc:
            messagebox.showerror(
                "Quick actions were not reordered",
                f"Context Palette could not change the order.\n\n{exc}",
                parent=self.window,
            )
            return
        if not moved:
            self.feedback_var.set("The selected item is already at that edge.")
            return
        self.on_change()
        self._reload()
        self.feedback_var.set("Updated Quick-action order.")
        self.feedback_label.configure(style="Success.TLabel")

    def _button_move_availability(
        self,
        group: CommandGroup,
        item: CommandItem | None,
        path: tuple[int, ...],
    ) -> tuple[bool, bool]:
        if item is None:
            target = self._group_target_path(group).resolve()
            siblings = [
                candidate
                for candidate in self.groups
                if self._group_target_path(candidate).resolve() == target
            ]
            index = next(
                position
                for position, candidate in enumerate(siblings)
                if candidate.id.casefold() == group.id.casefold()
            )
        else:
            if len(path) == 1:
                siblings = list(group.items)
            else:
                parent = command_item_at_path(group, path[:-1])
                siblings = list(parent.items)
            index = path[-1]
        return index > 0, index < len(siblings) - 1

    def _set_button_selection_state(
        self,
        *,
        edit_label: str,
        edit_enabled: bool,
        new_label: str,
        new_enabled: bool,
        move_up: bool,
        move_down: bool,
        delete_enabled: bool,
    ) -> None:
        if not hasattr(self, "quick_item_edit_button"):
            return
        self.quick_item_edit_button.configure(
            text=edit_label,
            state=tk.NORMAL if edit_enabled else tk.DISABLED,
        )
        self.new_quick_item_button.configure(
            text=new_label,
            state=tk.NORMAL if new_enabled else tk.DISABLED,
        )
        self.quick_item_move_menu.entryconfigure(
            0,
            state=tk.NORMAL if move_up else tk.DISABLED,
        )
        self.quick_item_move_menu.entryconfigure(
            1,
            state=tk.NORMAL if move_down else tk.DISABLED,
        )
        self.quick_item_move_button.configure(
            state=tk.NORMAL if move_up or move_down else tk.DISABLED,
        )
        self.quick_item_delete_button.configure(
            state=tk.NORMAL if delete_enabled else tk.DISABLED,
        )
        commands = (
            (self.new_quick_item_button, new_enabled),
            (self.quick_item_edit_button, edit_enabled),
            (self.quick_item_move_button, move_up or move_down),
            (self.quick_item_delete_button, delete_enabled),
        )
        for command, _visible in commands:
            command.pack_forget()
        first = True
        for command, visible in commands:
            if not visible:
                continue
            command.pack(
                side=tk.LEFT,
                padx=(0, 0) if first else (6, 0),
            )
            first = False

    def _update_button_preview(self) -> None:
        action_bound = self._selected_action_bound_button_record()
        if action_bound is not None:
            path = " > ".join(
                (action_bound.group_label, *action_bound.path)
            )
            if action_bound.action_id:
                action = next(
                    (
                        candidate
                        for candidate in self.actions
                        if candidate.id == action_bound.action_id
                    ),
                    None,
                )
                if hasattr(self, "button_detail_title_var"):
                    self.button_detail_title_var.set(
                        compact_selection_title(
                            action.title if action is not None else path
                        )
                    )
                self.button_preview_var.set(
                    compact_selection_summary(
                        f"Automatic menu: {path} · Action: "
                        f"{action.title if action is not None else 'Unavailable'} · "
                        "Edit the Action to change its Quick menu path."
                    )
                )
                self._set_button_selection_state(
                    edit_label="Edit Action…",
                    edit_enabled=True,
                    new_label="New submenu…",
                    new_enabled=False,
                    move_up=False,
                    move_down=False,
                    delete_enabled=False,
                )
            else:
                if hasattr(self, "button_detail_title_var"):
                    self.button_detail_title_var.set(
                        compact_selection_title(path)
                    )
                self.button_preview_var.set(
                    compact_selection_summary(
                        f"Automatic menu: {path} · Membership follows Active "
                        f"{ACTION_TYPES[action_bound.action_type].display_label} actions. "
                        "View Actions opens the matching list."
                    )
                )
                self._set_button_selection_state(
                    edit_label=(
                        "Find matching Actions…"
                        if action_bound.path
                        else "Find all Actions…"
                    ),
                    edit_enabled=True,
                    new_label=(
                        f"Add {ACTION_BOUND_QUICK_NOUNS[action_bound.action_type]} here…"
                        if action_bound.path
                        else ACTION_BOUND_QUICK_ADD_LABELS[action_bound.action_type]
                    ),
                    new_enabled=True,
                    move_up=False,
                    move_down=False,
                    delete_enabled=False,
                )
            return
        selected = self._selected_button_record()
        if selected is None:
            if hasattr(self, "button_detail_title_var"):
                self.button_detail_title_var.set("Select a Quick action")
            self.button_preview_var.set(
                "Choose a custom or automatic item to review how it behaves."
            )
            self._set_button_selection_state(
                edit_label="Edit…",
                edit_enabled=False,
                new_label="New Quick action…",
                new_enabled=False,
                move_up=False,
                move_down=False,
                delete_enabled=False,
            )
            return
        group, item, path = selected
        destination = (
            LOCAL_DESTINATION
            if self._group_target_path(group).resolve()
            == self.local_command_surface_path.resolve()
            else PROJECT_DESTINATION
        )
        move_up, move_down = self._button_move_availability(
            group,
            item,
            path,
        )
        self._set_button_selection_state(
            edit_label="Edit…",
            edit_enabled=True,
            new_label=(
                "New Quick action…" if item is None else "New submenu…"
            ),
            new_enabled=len(path) < MAX_COMMAND_MENU_LEVELS,
            move_up=move_up,
            move_down=move_down,
            delete_enabled=True,
        )
        if item is None:
            root_labels = action_reference_labels(
                command_group_action_ids(group),
                self.actions,
            )
            if hasattr(self, "button_detail_title_var"):
                self.button_detail_title_var.set(
                    compact_selection_title(group.label)
                )
            self.button_preview_var.set(
                compact_selection_summary(
                    f"Browse menu · {command_item_count(group)} item(s) · "
                    f"Actions at menu root: "
                    f"{', '.join(root_labels) if root_labels else 'none'} · "
                    f"{destination}"
                )
            )
            return
        labels = quick_action_target_labels(
            item,
            self.actions,
            self._available_work_items(),
        )
        menu_path = [group.label]
        current_items = group.items
        for item_index in path:
            current = current_items[item_index]
            menu_path.append(current.label)
            current_items = current.items
        if hasattr(self, "button_detail_title_var"):
            self.button_detail_title_var.set(
                compact_selection_title(" > ".join(menu_path))
            )
        self.button_preview_var.set(
            compact_selection_summary(
                f"Targets in menu order: "
                f"{', '.join(labels) if labels else 'empty'} · "
                f"Child menus: {len(item.items)} · "
                f"{destination}"
            )
        )


class ActionDialog:
    def __init__(
        self, parent: tk.Toplevel, action_type: str, actions: list[Action],
        on_save: Callable[..., bool],
        *,
        action: Action | None = None,
        context_names: list[str] | None = None,
        choose_destination: bool = False,
        default_text_file_path: Path | None = None,
        initial_contexts: tuple[str, ...] = (),
        initial_title: str = "",
        initial_value: str = "",
        suggested_from_workspace: bool = False,
        initial_quick_action_path: tuple[str, ...] = (),
    ) -> None:
        self.action_type = action_type
        self.action = action
        self.available_actions = list(actions)
        self.on_save = on_save
        self.choose_destination = choose_destination
        self.default_text_file_path = default_text_file_path
        self.context_names = tuple(context_names or ())
        definition = ACTION_TYPES[action_type]
        self.window = tk.Toplevel(parent)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.title(
            f"Edit action · {definition.display_label}"
            if action
            else f"Create action · {definition.display_label}"
        )
        width, height, _x, _y = place_child_window(
            self.window,
            parent,
            size=ACTION_DIALOG_SIZE,
        )
        self.window.minsize(
            min(ACTION_DIALOG_MINIMUM_SIZE[0], width),
            min(ACTION_DIALOG_MINIMUM_SIZE[1], height),
        )
        self.tooltips: list[WidgetTooltip] = []
        self.action_guidance = (
            f"{definition.description}\n"
            f"{definition.output_description}\n"
            f"{ACTION_TYPE_EXAMPLES[action_type]}"
        )
        outer = ttk.Frame(self.window, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)
        self.controls_frame = ttk.Frame(outer)
        self.controls_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(7, 0))
        ttk.Button(
            self.controls_frame,
            text="Save action" if action else "Create action",
            command=self._save,
            style="Accent.TButton",
        ).pack(side=tk.LEFT)
        ttk.Button(
            self.controls_frame,
            text="Cancel",
            command=self.window.destroy,
        ).pack(side=tk.RIGHT)

        form_host = ttk.Frame(outer)
        form_host.pack(fill=tk.BOTH, expand=True)
        self.form_canvas = tk.Canvas(
            form_host,
            borderwidth=0,
            highlightthickness=0,
            background=self.window.cget("background"),
            takefocus=False,
        )
        self.form_scrollbar = ttk.Scrollbar(
            form_host,
            orient=tk.VERTICAL,
            command=self.form_canvas.yview,
        )
        self.form_canvas.configure(yscrollcommand=self.form_scrollbar.set)
        self.form_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.form_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.form_frame = ttk.Frame(self.form_canvas)
        self.form_window_id = self.form_canvas.create_window(
            (0, 0),
            window=self.form_frame,
            anchor=tk.NW,
        )
        self.form_frame.bind("<Configure>", self._update_form_scrollregion)
        self.form_canvas.bind("<Configure>", self._resize_form_width)
        self.window.bind("<MouseWheel>", self._scroll_form, add="+")
        self.window.bind("<FocusIn>", self._keep_focused_field_visible, add="+")
        form = self.form_frame
        header = ttk.Frame(form)
        header.pack(fill=tk.X, pady=(0, 3))
        action_type_label = ttk.Label(
            header,
            text=definition.display_label,
            style="Heading.TLabel",
        )
        action_type_label.pack(side=tk.LEFT, anchor=tk.W)
        action_help = ttk.Button(
            header,
            text="?",
            width=3,
            command=self._show_action_type_help,
            style="Compact.TButton",
        )
        action_help.pack(side=tk.RIGHT)
        self._tooltip(action_type_label, self.action_guidance)
        self._tooltip(
            action_help,
            "Show what this action reads, changes, and an example.",
        )
        self.suggestion_notice: ttk.Label | None = None
        if suggested_from_workspace and action is None:
            self.suggestion_notice = ttk.Label(
                form,
                text=(
                    "Prefilled from Input / Output - review the name, target, "
                    "and effect before creating this Action."
                ),
                style="Status.TLabel",
                wraplength=610,
            )
            self.suggestion_notice.pack(fill=tk.X, pady=(2, 5))
        self.destination_var = tk.StringVar(value=LOCAL_DESTINATION)
        if choose_destination:
            self.destination_field = self._compact_combobox(
                form,
                "Storage",
                self.destination_var,
                (LOCAL_DESTINATION, PROJECT_DESTINATION),
                help_text=(
                    "My configuration stays on this PC. Built-in changes the "
                    "starter configuration tracked through Git and is intended "
                    "for developers."
                ),
            )
        self.title_var = tk.StringVar(
            value=action.title if action else initial_title
        )
        self.description_var = tk.StringVar(
            value=action.description if action else ""
        )
        self.contexts_var = tk.StringVar(
            value=(
                ", ".join(action.effective_contexts)
                if action
                else ", ".join(initial_contexts)
            )
        )
        self.tags_var = tk.StringVar(
            value=", ".join(action.effective_tags) if action else ""
        )
        self.quick_action_path_var = tk.StringVar(
            value=(
                " > ".join(action.quick_action_path)
                if action
                else " > ".join(initial_quick_action_path)
            )
        )
        self.arguments_var = tk.StringVar(
            value="\n".join(action.arguments) if action else ""
        )
        self.arguments_text: tk.Text | None = None
        self.working_directory_var = tk.StringVar(
            value=action.working_directory or "" if action else ""
        )
        title_entry = self._compact_entry(
            form,
            "Name",
            self.title_var,
            help_text="Short name shown in action lists and search results.",
        )
        self._compact_entry(
            form,
            "Description",
            self.description_var,
            help_text="Optional searchable explanation shown in Action info.",
        )
        self.context_field = ContextMembershipField(
            form,
            self.contexts_var,
            self.context_names,
            label="Contexts",
            inline=True,
            label_width=ACTION_DIALOG_LABEL_WIDTH,
        )
        self._tooltip(
            self.context_field.entry,
            (
                "Optional. Choose defined contexts or type comma-separated "
                "names. General always includes the action."
            ),
        )
        self._tooltip(
            self.context_field.picker,
            "Choose one or more defined contexts.",
        )
        known_tags = sorted(
            {tag for item in actions for tag in item.effective_tags},
            key=str.casefold,
        )
        self.tag_field = TagSelectionField(
            form,
            self.tags_var,
            known_tags,
            label="Tags",
            inline=True,
            label_width=ACTION_DIALOG_LABEL_WIDTH,
        )
        self._tooltip(
            self.tag_field.entry,
            (
                "Optional. Type new comma-separated tags or choose tags "
                "already in use."
            ),
        )
        self._tooltip(
            self.tag_field.picker,
            "Search and choose tags already in use.",
        )
        if action_type in ACTION_BOUND_QUICK_TYPES:
            self._compact_entry(
                form,
                "Quick menu",
                self.quick_action_path_var,
                help_text=(
                    "Optional nested placement in the fixed Quick-action menu. "
                    "Separate up to three levels with >. Leave blank to show "
                    "the Action at the menu root."
                ),
            )
        label = {
            "open_url": "Website",
            "open_windows_target": "Windows target",
            "open_file": "File",
            "open_folder": "Folder",
            "launch_app": "Application",
            "paste_credential": "Credential",
            "transform_file_text": "Text file",
            "transform_list_csv": "Mode",
            "transform_text": "Operation",
            "transform_slashes": "Mode",
        }.get(action_type, "Text")
        self.transform_operation_choices: dict[str, str] = {}
        self.transform_parameter_vars: list[tk.StringVar] = []
        self.transform_parameters_frame: ttk.Frame | None = None
        self.value: tk.Text | None = None
        if action_type == "sequence":
            self.sequence_steps = list(action.sequence_steps if action else ())
            self._build_sequence_fields(form)
        elif action_type in {"transform_text", "transform_file_text"}:
            self._build_transform_fields(
                form,
                action,
                file_source=action_type == "transform_file_text",
            )
        else:
            value_height = (
                5
                if action_type in {"copy_text", "workspace_template", "ai_prompt"}
                else 2
            )
            self.value = self._compact_text(
                form,
                label,
                height=value_height,
                help_text=self.action_guidance,
            )
            if action:
                self.value.insert("1.0", action.value)
            elif initial_value:
                self.value.insert("1.0", initial_value)
            elif action_type == "transform_list_csv":
                self.value.insert("1.0", "csv")
            elif action_type == "transform_slashes":
                self.value.insert("1.0", "forward_to_back")
            elif action_type == "open_windows_target":
                self.value.insert("1.0", "vscode:")
            elif action_type in {"build_url_open", "build_url_selection_open"}:
                self.value.insert("1.0", "https://example.com/items/{id_url}")
        if action_type in {"launch_app", "open_windows_target"}:
            self.arguments_text = self._compact_text(
                form,
                "Arguments",
                height=3,
                help_text=(
                    "Optional. Enter one argument per line; press Enter to "
                    "start the next argument."
                ),
            )
            self.arguments_text.insert("1.0", self.arguments_var.get())
            self._compact_entry(
                form,
                "Working folder",
                self.working_directory_var,
                help_text="Optional working folder used when the action starts.",
            )
        self.window.transient(parent)
        self.window.grab_set()
        _focus_entry(self.window, title_entry)

    def _tooltip(self, widget: tk.Widget, text: str) -> None:
        self.tooltips.append(WidgetTooltip(widget, text))

    def _compact_row(
        self,
        parent: ttk.Frame,
        label: str,
    ) -> tuple[ttk.Frame, ttk.Label]:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=(5, 0))
        label_widget = ttk.Label(
            row,
            text=label,
            width=ACTION_DIALOG_LABEL_WIDTH,
        )
        label_widget.pack(side=tk.LEFT, anchor=tk.W, padx=(0, 8))
        return row, label_widget

    def _compact_entry(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        *,
        help_text: str,
    ) -> ttk.Entry:
        row, label_widget = self._compact_row(parent, label)
        entry = ttk.Entry(row, textvariable=variable)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._tooltip(label_widget, help_text)
        self._tooltip(entry, help_text)
        return entry

    def _compact_combobox(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
        *,
        help_text: str,
    ) -> ttk.Combobox:
        row, label_widget = self._compact_row(parent, label)
        chooser = ttk.Combobox(
            row,
            textvariable=variable,
            values=values,
            state="readonly",
        )
        chooser.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._tooltip(label_widget, help_text)
        self._tooltip(chooser, help_text)
        return chooser

    def _compact_text(
        self,
        parent: ttk.Frame,
        label: str,
        *,
        height: int,
        help_text: str,
    ) -> tk.Text:
        row, label_widget = self._compact_row(parent, label)
        text = tk.Text(row, height=height, wrap=tk.WORD, undo=True)
        text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._tooltip(label_widget, help_text)
        self._tooltip(text, help_text)
        return text

    def _show_action_type_help(self) -> None:
        messagebox.showinfo(
            ACTION_TYPES[self.action_type].display_label,
            self.action_guidance,
            parent=self.window,
        )

    def _build_sequence_fields(self, parent: ttk.Frame) -> None:
        eligible = [
            action
            for action in self.available_actions
            if action.state == "Active"
            and action.type in ALLOWED_ACTION_TYPES
            and (self.action is None or action.id != self.action.id)
        ]
        self.sequence_action_choices = _action_choices(eligible)
        chooser_row = ttk.Frame(parent)
        chooser_row.pack(fill=tk.X, pady=(7, 0))
        ttk.Label(
            chooser_row,
            text="Add Action",
            width=ACTION_DIALOG_LABEL_WIDTH,
        ).pack(side=tk.LEFT, padx=(0, 8))
        self.sequence_action_var = tk.StringVar()
        self.sequence_action_picker = ActionPickerField(
            chooser_row,
            variable=self.sequence_action_var,
            options=_action_picker_options(
                eligible,
                choices=self.sequence_action_choices,
            ),
            title="Choose Action for sequence",
            scope_note=(
                "Sequences may start reviewed websites, files, folders, "
                "applications, and Windows targets."
            ),
        )
        self.sequence_action_picker.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            chooser_row,
            text="Add",
            command=self._add_sequence_action,
        ).pack(side=tk.LEFT, padx=(6, 0))
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(7, 0))
        self.sequence_list = tk.Listbox(list_frame, exportselection=False, height=8)
        self.sequence_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(
            list_frame,
            orient=tk.VERTICAL,
            command=self.sequence_list.yview,
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.sequence_list.configure(yscrollcommand=scrollbar.set)
        controls = ttk.Frame(parent)
        controls.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(
            controls,
            text="Add wait…",
            command=self._add_sequence_wait,
        ).pack(side=tk.LEFT)
        ttk.Button(
            controls,
            text="Remove",
            command=self._remove_sequence_step,
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            controls,
            text="Move up",
            command=lambda: self._move_sequence_step(-1),
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            controls,
            text="Move down",
            command=lambda: self._move_sequence_step(1),
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(
            parent,
            text=(
                "2–12 steps. Waits are 100–10,000 ms, cannot touch each "
                "other or the ends, and never prove that a program finished."
            ),
            style="Muted.TLabel",
            wraplength=610,
        ).pack(anchor=tk.W, pady=(5, 0))
        self._refresh_sequence_steps()

    def _add_sequence_action(self) -> None:
        action_id = self.sequence_action_choices.get(self.sequence_action_var.get())
        if not action_id:
            return
        self.sequence_steps.append(SequenceStep("action", action_id=action_id))
        self._refresh_sequence_steps(select=len(self.sequence_steps) - 1)

    def _add_sequence_wait(self) -> None:
        milliseconds = simpledialog.askinteger(
            "Add wait",
            "Wait how many milliseconds? (100 to 10,000)",
            parent=self.window,
            minvalue=100,
            maxvalue=10_000,
            initialvalue=500,
        )
        if milliseconds is None:
            return
        self.sequence_steps.append(SequenceStep("wait", milliseconds=milliseconds))
        self._refresh_sequence_steps(select=len(self.sequence_steps) - 1)

    def _remove_sequence_step(self) -> None:
        selection = self.sequence_list.curselection()
        if not selection:
            return
        index = selection[0]
        del self.sequence_steps[index]
        self._refresh_sequence_steps(select=min(index, len(self.sequence_steps) - 1))

    def _move_sequence_step(self, offset: int) -> None:
        selection = self.sequence_list.curselection()
        if not selection:
            return
        index = selection[0]
        target = index + offset
        if target < 0 or target >= len(self.sequence_steps):
            return
        self.sequence_steps[index], self.sequence_steps[target] = (
            self.sequence_steps[target],
            self.sequence_steps[index],
        )
        self._refresh_sequence_steps(select=target)

    def _refresh_sequence_steps(self, *, select: int | None = None) -> None:
        actions_by_id = {action.id: action for action in self.available_actions}
        self.sequence_list.delete(0, tk.END)
        for number, step in enumerate(self.sequence_steps, start=1):
            if step.kind == "wait":
                label = f"{number}. Wait {step.milliseconds} ms"
            else:
                action = actions_by_id.get(step.action_id)
                label = (
                    f"{number}. {action.title} · {ACTION_TYPES[action.type].label}"
                    if action is not None
                    else f"{number}. Unavailable Action"
                )
            self.sequence_list.insert(tk.END, label)
        if select is not None and self.sequence_steps:
            self.sequence_list.selection_set(select)
            self.sequence_list.see(select)

    def _update_form_scrollregion(self, _event: tk.Event | None = None) -> None:
        bounds = self.form_canvas.bbox("all")
        if bounds is not None:
            self.form_canvas.configure(scrollregion=bounds)

    def _resize_form_width(self, event: tk.Event) -> None:
        self.form_canvas.itemconfigure(
            self.form_window_id,
            width=max(1, int(event.width)),
        )

    def _scroll_form(self, event: tk.Event) -> str | None:
        if isinstance(event.widget, (tk.Text, tk.Listbox, ttk.Combobox)):
            return None
        first, last = self.form_canvas.yview()
        if first <= 0.0 and last >= 1.0:
            return None
        direction = -1 if int(event.delta) > 0 else 1
        visible_fraction = max(0.0, last - first)
        maximum_start = max(0.0, 1.0 - visible_fraction)
        self.form_canvas.yview_moveto(
            max(0.0, min(first + direction * 0.08, maximum_start))
        )
        return "break"

    def _keep_focused_field_visible(self, event: tk.Event) -> None:
        widget = event.widget
        if not self._is_form_widget(widget):
            return
        self.window.after_idle(
            lambda focused=widget: self._show_form_widget(focused)
        )

    def _is_form_widget(self, widget: tk.Misc) -> bool:
        current: tk.Misc | None = widget
        while current is not None:
            if current is self.form_frame:
                return True
            if current is self.window:
                return False
            current = getattr(current, "master", None)
        return False

    def _show_form_widget(self, widget: tk.Misc) -> None:
        try:
            if not widget.winfo_exists() or not self._is_form_widget(widget):
                return
            self.form_canvas.update_idletasks()
            viewport_height = self.form_canvas.winfo_height()
            content_bounds = self.form_canvas.bbox("all")
            if viewport_height <= 1 or content_bounds is None:
                return
            content_height = max(1, content_bounds[3] - content_bounds[1])
            widget_top = widget.winfo_rooty() - self.form_frame.winfo_rooty()
            widget_bottom = widget_top + widget.winfo_height()
            viewport_top = self.form_canvas.canvasy(0)
            viewport_bottom = viewport_top + viewport_height
            padding = 8
            target_top: float | None = None
            if widget_top < viewport_top + padding:
                target_top = widget_top - padding
            elif widget_bottom > viewport_bottom - padding:
                target_top = widget_bottom - viewport_height + padding
            if target_top is not None:
                maximum_top = max(0, content_height - viewport_height)
                self.form_canvas.yview_moveto(
                    max(0.0, min(float(target_top), maximum_top))
                    / content_height
                )
        except tk.TclError:
            return

    def _build_transform_fields(
        self,
        parent: ttk.Frame,
        action: Action | None,
        *,
        file_source: bool = False,
    ) -> None:
        self.transform_file_path_var: tk.StringVar | None = None
        if file_source:
            default_path = (
                action.value
                if action
                else str(self.default_text_file_path or "")
            )
            self.transform_file_path_var = tk.StringVar(value=default_path)
            path_row, path_label = self._compact_row(parent, "Text file")
            path_entry = ttk.Entry(
                path_row,
                textvariable=self.transform_file_path_var,
            )
            path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Button(
                path_row,
                text="Browse…",
                command=self._choose_transform_file,
            ).pack(side=tk.RIGHT, padx=(6, 0))
            file_help = (
                "Choose an existing text file. Running the action reads it "
                "again and shows a reviewable result without changing it."
            )
            self._tooltip(path_label, file_help)
            self._tooltip(path_entry, file_help)
        for group in WORKSPACE_TRANSFORM_GROUPS:
            for transform in group.transforms:
                self.transform_operation_choices[
                    f"{group.label} · {transform.label.rstrip('…')}"
                ] = transform.operation
        labels_by_operation = {
            operation: label
            for label, operation in self.transform_operation_choices.items()
        }
        operation = (
            action.arguments[0]
            if file_source
            and action
            and action.arguments
            and action.arguments[0] in WORKSPACE_TRANSFORMS
            else action.value
            if not file_source and action and action.value in WORKSPACE_TRANSFORMS
            else "literal_replace"
        )
        self.transform_operation_var = tk.StringVar(
            value=labels_by_operation[operation]
        )
        operation_row, operation_label = self._compact_row(parent, "Operation")
        chooser = ttk.Combobox(
            operation_row,
            textvariable=self.transform_operation_var,
            values=tuple(self.transform_operation_choices),
            state="readonly",
        )
        chooser.pack(side=tk.LEFT, fill=tk.X, expand=True)
        operation_help = "Choose the text operation to apply."
        self._tooltip(operation_label, operation_help)
        self._tooltip(chooser, operation_help)
        self.transform_parameters_frame = ttk.Frame(parent)
        self.transform_parameters_frame.pack(fill=tk.X)
        chooser.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._render_transform_parameters(),
        )
        self._render_transform_parameters(
            tuple(action.arguments[1:])
            if file_source and action
            else tuple(action.arguments)
            if action
            else (),
        )

    def _choose_transform_file(self) -> None:
        assert self.transform_file_path_var is not None
        current = Path(self.transform_file_path_var.get()).expanduser()
        selected = filedialog.askopenfilename(
            parent=self.window,
            title="Choose source text file",
            initialdir=str(
                current.parent
                if current.parent.is_dir()
                else Path.home()
            ),
            initialfile=current.name if current.name else "",
            filetypes=(
                ("Text files", "*.txt *.csv *.tsv *.json *.md *.xml *.sql *.log"),
                ("All files", "*.*"),
            ),
        )
        if selected:
            self.transform_file_path_var.set(selected)

    def _selected_transform_operation(self) -> str:
        return self.transform_operation_choices[self.transform_operation_var.get()]

    def _render_transform_parameters(
        self,
        initial_values: tuple[str, ...] = (),
    ) -> None:
        assert self.transform_parameters_frame is not None
        for child in self.transform_parameters_frame.winfo_children():
            child.destroy()
        definition = WORKSPACE_TRANSFORMS[self._selected_transform_operation()]
        self.transform_parameter_vars = []
        for index, label in enumerate(definition.parameter_labels):
            default = (
                initial_values[index]
                if index < len(initial_values)
                else definition.parameter_defaults[index]
                if index < len(definition.parameter_defaults)
                else ""
            )
            variable = tk.StringVar(value=default)
            self._compact_entry(
                self.transform_parameters_frame,
                label,
                variable,
                help_text=f"Value used for {label.casefold()}.",
            )
            self.transform_parameter_vars.append(variable)
        if not definition.parameter_labels:
            ttk.Label(
                self.transform_parameters_frame,
                text="This operation needs no additional settings.",
                style="Muted.TLabel",
            ).pack(anchor=tk.W, pady=(4, 0))

    def _save(self) -> None:
        try:
            contexts = validate_context_memberships(
                _comma_separated(self.contexts_var.get()),
                self.context_names,
            )
            sequence_steps: tuple[SequenceStep, ...] = ()
            if self.action_type == "sequence":
                value = "sequence-v1"
                arguments = []
                sequence_steps = tuple(self.sequence_steps)
                resolve_sequence_steps(
                    sequence_steps,
                    self.available_actions,
                    sequence_id=self.action.id if self.action else "",
                )
            elif self.action_type in {"transform_text", "transform_file_text"}:
                operation = self._selected_transform_operation()
                parameters = [
                    variable.get() for variable in self.transform_parameter_vars
                ]
                if self.action_type == "transform_file_text":
                    assert self.transform_file_path_var is not None
                    value = self.transform_file_path_var.get()
                    arguments = [operation, *parameters]
                else:
                    value = operation
                    arguments = parameters
            else:
                assert self.value is not None
                value = self.value.get("1.0", "end-1c")
                arguments_text = getattr(self, "arguments_text", None)
                arguments = (
                    arguments_text.get("1.0", "end-1c").splitlines()
                    if arguments_text is not None
                    else self.arguments_var.get().splitlines()
                )
            quick_action_path_var = getattr(self, "quick_action_path_var", None)
            values = dict(
                title=self.title_var.get(),
                description=self.description_var.get(),
                context="General",
                contexts=contexts,
                tags=_comma_separated(self.tags_var.get()),
                action_type=self.action_type,
                value=value,
                arguments=arguments,
                working_directory=self.working_directory_var.get(),
                quick_action_path=_quick_action_path(
                    quick_action_path_var.get()
                    if quick_action_path_var is not None
                    else ""
                ),
                sequence_steps=sequence_steps,
                available_actions=getattr(self, "available_actions", ()),
            )
            action = (
                edited_configured_action(self.action, **values)
                if self.action
                else configured_action(**values)
            )
        except (ActionError, ActionSequenceError) as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.window)
            return
        saved = (
            self.on_save(action, self.destination_var.get())
            if getattr(self, "choose_destination", False)
            else self.on_save(action)
        )
        if saved:
            self.window.destroy()


class ContextDialog:
    def __init__(
        self, parent: tk.Toplevel, context: ContextDefinition | None,
        actions: list[Action], on_save: Callable[..., bool],
        *,
        work_items: tuple[DiscoveredWorkItem, ...] = (),
        shared: bool = False,
        choose_destination: bool = False,
    ) -> None:
        self.original_name = context.name if context else ""
        self.on_save = on_save
        self.choose_destination = choose_destination
        self.window = tk.Toplevel(parent)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.title(
            "Edit built-in context"
            if context and shared
            else "Edit context"
            if context
            else "New context"
        )
        configure_standard_window(self.window, parent)
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        self.controls_frame = _dialog_buttons(
            outer,
            self._save,
            self.window.destroy,
        )
        self.form_view = _ScrollableDialogBody(self.window, outer)
        form = self.form_view.content
        self.name = tk.StringVar(value=context.name if context else "")
        self.description = tk.StringVar(value=context.description if context else "")
        name_entry = _entry(form, "Context name", self.name)
        _entry(form, "Description", self.description)
        self.destination_var = tk.StringVar(value=LOCAL_DESTINATION)
        if choose_destination:
            _destination_field(form, self.destination_var)
        preferred = context.preferred_action_ids if context else ()
        self.action_choices = _action_choices(actions)
        self.action_picker_options = _action_picker_options(
            actions,
            choices=self.action_choices,
        )
        self.action_picker_options_by_id = {
            option.action_id: option for option in self.action_picker_options
        }
        labels_by_id = {action_id: label for label, action_id in self.action_choices.items()}
        self.labels_by_action_id = labels_by_id
        self.work_items = work_items
        self.work_item_choices = _work_item_choices(work_items)
        self.work_item_labels_by_ref = {
            reference: label
            for label, reference in self.work_item_choices.items()
        }
        legacy_members = (
            context.action_ids
            if context and context.action_ids is not None
            else tuple(
                action.id
                for action in actions
                if context and action.belongs_to_context(context.name)
            )
        )
        member_targets = [
            CommandTarget(action_id=action_id)
            for action_id in dict.fromkeys((*legacy_members, *preferred))
        ]
        if context:
            member_targets.extend(
                CommandTarget(work_item_ref=reference)
                for reference in context.work_item_refs
            )
            for reference in context.preferred_items:
                if reference not in member_targets:
                    member_targets.append(reference)
        self.member_targets = list(dict.fromkeys(member_targets))
        self.member_action_ids = [
            reference.action_id
            for reference in self.member_targets
            if reference.action_id
        ]
        ttk.Label(
            form,
            text="Members",
            style="Heading.TLabel",
        ).pack(anchor=tk.W, pady=(9, 0))
        ttk.Label(
            form,
            text=(
                "Actions in this Built-in context. Only Built-in actions are "
                "available."
                if shared
                else
                "Palette items in this context. My configuration contexts may "
                "contain built-in Actions, your Actions, and Work Items."
            ),
            style="Muted.TLabel",
            wraplength=610,
        ).pack(anchor=tk.W, pady=(2, 2))
        member_chooser = ttk.Frame(form)
        member_chooser.pack(fill=tk.X)
        self.member_choice_var = tk.StringVar()
        self.member_choice = ActionPickerField(
            member_chooser,
            variable=self.member_choice_var,
            options=self.action_picker_options,
            title="Choose action to add to context",
            scope_note=BUILT_IN_ACTION_SCOPE_NOTE if shared else None,
        )
        self.member_choice.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            member_chooser,
            text="Add Action",
            command=self._add_member_action,
        ).pack(side=tk.LEFT, padx=(6, 0))
        if not shared:
            work_item_chooser = ttk.Frame(form)
            work_item_chooser.pack(fill=tk.X, pady=(5, 0))
            self.member_work_item_var = tk.StringVar()
            self.member_work_item_choice = ActionPickerField(
                work_item_chooser,
                variable=self.member_work_item_var,
                options=_work_item_picker_options(
                    work_items,
                    self.work_item_choices,
                ),
                title="Choose Work Item to add to context",
                item_name="Work Item",
                item_plural="Work Items",
                search_help=(
                    "Searches Work Item name, source, kind, organisation, "
                    "project code, and stable folder identity."
                ),
            )
            self.member_work_item_choice.pack(
                side=tk.LEFT,
                fill=tk.X,
                expand=True,
            )
            ttk.Button(
                work_item_chooser,
                text="Add Work Item",
                command=self._add_member_work_item,
            ).pack(side=tk.LEFT, padx=(6, 0))
        member_area = ttk.Frame(form)
        member_area.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.member_list = tk.Listbox(
            member_area,
            exportselection=False,
            height=5,
        )
        self.member_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        member_scrollbar = ttk.Scrollbar(
            member_area,
            orient=tk.VERTICAL,
            command=self.member_list.yview,
        )
        member_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.member_list.configure(yscrollcommand=member_scrollbar.set)
        ttk.Button(
            form,
            text="Remove from Context",
            command=self._remove_member_item,
        ).pack(anchor=tk.W, pady=(5, 0))
        self.item_choices: dict[str, CommandTarget] = {
            label: CommandTarget(action_id=action_id)
            for label, action_id in self.action_choices.items()
        }
        self.item_choices.update(
            {
                label: CommandTarget(work_item_ref=reference)
                for label, reference in self.work_item_choices.items()
            }
        )
        preferred_items = context.preferred_items if context else ()
        self.slots = []
        for index in range(MAX_CONTEXT_SLOT_ACTIONS):
            label = EMPTY_PIN_LABEL
            if index < len(preferred_items):
                label = self._item_label(preferred_items[index])
            self.slots.append(tk.StringVar(value=label))
        self.slot_choices: list[ActionPickerField] = []
        ttk.Label(
            form,
            text="Focus shortcuts 6–0 (optional)",
            style="Heading.TLabel",
        ).pack(anchor=tk.W, pady=(9, 0))
        ttk.Label(
            form,
            text=(
                "Choose up to five Context members for the numbered shortcuts "
                "shown when this Context is the current Focus."
            ),
            style="Muted.TLabel",
            wraplength=610,
        ).pack(anchor=tk.W, pady=(2, 2))
        for slot, variable in zip(CONTEXT_SLOT_NUMBERS, self.slots):
            slot_label = slot_display_number(slot)
            row = ttk.Frame(form)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"Slot {slot_label}", width=8).pack(side=tk.LEFT)
            chooser = ActionPickerField(
                row,
                variable=variable,
                empty_label=EMPTY_PIN_LABEL,
                title=f"Choose preferred item for slot {slot_label}",
                item_name="Palette item",
                item_plural="Palette items",
            )
            chooser.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.slot_choices.append(chooser)
        self._refresh_member_actions()
        self.window.transient(parent)
        self.window.grab_set()
        _focus_entry(self.window, name_entry)

    def _add_member_action(self) -> None:
        action_id = self.action_choices.get(self.member_choice_var.get())
        target = CommandTarget(action_id=action_id) if action_id else None
        if target is None or target in self.member_targets:
            return
        self.member_targets.append(target)
        self.member_action_ids.append(action_id)
        self._refresh_member_actions(select=len(self.member_targets) - 1)

    def _add_member_work_item(self) -> None:
        reference = self.work_item_choices.get(self.member_work_item_var.get())
        target = CommandTarget(work_item_ref=reference) if reference else None
        if target is None or target in self.member_targets:
            return
        self.member_targets.append(target)
        self._refresh_member_actions(select=len(self.member_targets) - 1)

    def _remove_member_item(self) -> None:
        selection = self.member_list.curselection()
        if not selection:
            return
        removed = self.member_targets.pop(selection[0])
        if removed.action_id and removed.action_id in self.member_action_ids:
            self.member_action_ids.remove(removed.action_id)
        removed_label = self._item_label(removed)
        for slot in self.slots:
            if slot.get() == removed_label:
                slot.set(EMPTY_PIN_LABEL)
        self._refresh_member_actions(
            select=min(selection[0], len(self.member_targets) - 1)
        )

    _remove_member_action = _remove_member_item

    def _item_label(self, reference: CommandTarget) -> str:
        if reference.action_id:
            return self.labels_by_action_id.get(
                reference.action_id,
                f"Unavailable action: {reference.action_id}",
            )
        assert reference.work_item_ref is not None
        return self.work_item_labels_by_ref.get(
            reference.work_item_ref,
            work_item_reference_label(reference.work_item_ref, ()),
        )

    def _refresh_member_actions(self, *, select: int = -1) -> None:
        self.member_list.delete(0, tk.END)
        labels = [self._item_label(reference) for reference in self.member_targets]
        for label in labels:
            self.member_list.insert(tk.END, label)
        if 0 <= select < len(labels):
            self.member_list.selection_set(select)
            self.member_list.see(select)
        options = tuple(
            ActionPickerOption(
                reference.stable_key,
                self._item_label(reference),
                self._item_label(reference),
            )
            for reference in self.member_targets
        )
        for chooser in self.slot_choices:
            chooser.set_options(options, empty_label=EMPTY_PIN_LABEL)

    def _save(self) -> None:
        name = self.name.get().strip()
        if not name:
            messagebox.showerror("Context Palette", "Context name cannot be empty.", parent=self.window)
            return
        member_targets = tuple(
            dict.fromkeys(
                getattr(
                    self,
                    "member_targets",
                    tuple(
                        CommandTarget(action_id=action_id)
                        for action_id in getattr(self, "member_action_ids", ())
                    ),
                )
            )
        )
        item_choices = getattr(
            self,
            "item_choices",
            {
                label: CommandTarget(action_id=action_id)
                for label, action_id in self.action_choices.items()
            },
        )
        preferred_items = tuple(
            dict.fromkeys(
                item_choices[item.get()]
                for item in self.slots
                if item.get() in item_choices
            )
        )
        context = ContextDefinition(
            name=name, description=self.description.get().strip(),
            preferred_action_ids=tuple(
                reference.action_id
                for reference in preferred_items
                if reference.action_id
            ),
            action_ids=tuple(
                reference.action_id
                for reference in member_targets
                if reference.action_id
            ),
            work_item_refs=tuple(
                reference.work_item_ref
                for reference in member_targets
                if reference.work_item_ref is not None
            ),
            preferred_item_refs=(
                preferred_items
                if any(
                    reference.work_item_ref is not None
                    for reference in preferred_items
                )
                else ()
            ),
        )
        saved = (
            self.on_save(
                context,
                self.original_name,
                self.destination_var.get(),
            )
            if getattr(self, "choose_destination", False)
            else self.on_save(context, self.original_name)
        )
        if saved:
            self.window.destroy()


class GroupDialog:
    def __init__(
        self,
        parent: tk.Toplevel,
        group: CommandGroup | None,
        on_save: Callable[[CommandGroup, str, str], bool],
        *,
        actions: list[Action] | None = None,
        choose_destination: bool = False,
        destination: str = LOCAL_DESTINATION,
    ) -> None:
        self.group = group
        self.original_group_id = group.id if group else ""
        self.on_save = on_save
        self.window = tk.Toplevel(parent)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.title(
            "Edit Quick-action menu" if group else "New Quick-action menu"
        )
        configure_standard_window(self.window, parent)
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        self.controls_frame = _dialog_buttons(
            outer,
            self._save,
            self.window.destroy,
        )
        self.form_view = _ScrollableDialogBody(self.window, outer)
        form = self.form_view.content
        ttk.Label(
            form,
            text=(
                "A menu is one visible launcher containing ordered Actions and submenus."
            ),
            style="Muted.TLabel",
            wraplength=560,
        ).pack(anchor=tk.W)
        self.label_var = tk.StringVar(value=group.label if group else "")
        self.id_var = tk.StringVar(value=group.id if group else "")
        name_entry = _entry(form, "Menu name", self.label_var)
        ttk.Label(
            form,
            text=(
                "Left-click browses this menu. Right-click opens its Add and "
                "Organize commands."
            ),
            style="Muted.TLabel",
            wraplength=560,
        ).pack(anchor=tk.W, pady=(2, 0))
        self.destination_var = tk.StringVar(value=destination)
        if choose_destination:
            _destination_field(form, self.destination_var)
        else:
            ttk.Label(
                form,
                text=f"Storage: {destination}",
                style="Muted.TLabel",
            ).pack(anchor=tk.W, pady=(8, 0))
        available_actions = actions or []
        self.direct_action_choices = _action_choices(available_actions)
        self.direct_picker_options = _action_picker_options(
            available_actions,
            choices=self.direct_action_choices,
        )
        self.direct_labels_by_id = {
            action_id: label
            for label, action_id in self.direct_action_choices.items()
        }
        self.direct_action_ids = list(
            command_group_action_ids(group)
            if group is not None
            else ()
        )
        ttk.Label(
            form,
            text="Actions at menu root (optional)",
        ).pack(anchor=tk.W, pady=(9, 2))
        direct_chooser = ttk.Frame(form)
        direct_chooser.pack(fill=tk.X)
        self.direct_action_var = tk.StringVar()
        self.direct_action_choice = ActionPickerField(
            direct_chooser,
            variable=self.direct_action_var,
            options=self.direct_picker_options,
            title="Choose Action at menu root",
            scope_note=(
                BUILT_IN_ACTION_SCOPE_NOTE
                if destination == PROJECT_DESTINATION and not choose_destination
                else None
            ),
        )
        self.direct_action_choice.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
        )
        ttk.Button(
            direct_chooser,
            text="Add",
            command=self._add_direct_action,
        ).pack(side=tk.LEFT, padx=(6, 0))
        direct_list_frame = ttk.Frame(form)
        direct_list_frame.pack(fill=tk.X, pady=(6, 0))
        self.direct_action_list = tk.Listbox(
            direct_list_frame,
            exportselection=False,
            height=4,
        )
        self.direct_action_list.pack(side=tk.LEFT, fill=tk.X, expand=True)
        direct_scrollbar = ttk.Scrollbar(
            direct_list_frame,
            orient=tk.VERTICAL,
            command=self.direct_action_list.yview,
        )
        direct_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.direct_action_list.configure(
            yscrollcommand=direct_scrollbar.set
        )
        direct_controls = ttk.Frame(form)
        direct_controls.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(
            direct_controls,
            text="Remove",
            command=self._remove_direct_action,
        ).pack(side=tk.LEFT)
        ttk.Button(
            direct_controls,
            text="Move up",
            command=lambda: self._move_direct_action(-1),
        ).pack(side=tk.LEFT, padx=(6, 0))
        self.direct_move_down_button = ttk.Button(
            direct_controls,
            text="Move down",
            command=lambda: self._move_direct_action(1),
        )
        self.direct_move_down_button.pack(side=tk.LEFT, padx=(6, 0))
        self._refresh_direct_actions()
        self.window.transient(parent)
        self.window.grab_set()
        _focus_entry(self.window, name_entry)

    def _save(self) -> None:
        label = self.label_var.get().strip()
        group_id = self.id_var.get().strip() or _stable_id(label)
        if not label or not group_id:
            messagebox.showerror(
                "Context Palette",
                "A Quick-action menu needs a visible name.",
                parent=self.window,
            )
            return
        direct_action_ids = tuple(
            dict.fromkeys(getattr(self, "direct_action_ids", ()))
        )
        presentation = (
            self.group.presentation
            if self.group is not None
            else GROUP_PRESENTATION_NESTED_MENU
        )
        if direct_action_ids:
            presentation = GROUP_PRESENTATION_NESTED_MENU
        group = CommandGroup(
            group_id,
            label,
            self.group.items if self.group else (),
            presentation=presentation,
            primary_action_id="",
            action_ids=direct_action_ids,
        )
        if self.on_save(
            group,
            self.original_group_id,
            self.destination_var.get(),
        ):
            self.window.destroy()

    def _add_direct_action(self) -> None:
        action_id = self.direct_action_choices.get(
            self.direct_action_var.get()
        )
        if not action_id or action_id in self.direct_action_ids:
            return
        self.direct_action_ids.append(action_id)
        self._refresh_direct_actions(
            select=len(self.direct_action_ids) - 1
        )

    def _remove_direct_action(self) -> None:
        selection = self.direct_action_list.curselection()
        if not selection:
            return
        del self.direct_action_ids[selection[0]]
        self._refresh_direct_actions(
            select=min(
                selection[0],
                len(self.direct_action_ids) - 1,
            )
        )

    def _move_direct_action(self, offset: int) -> None:
        selection = self.direct_action_list.curselection()
        if not selection:
            return
        index = selection[0]
        target = index + offset
        if target < 0 or target >= len(self.direct_action_ids):
            return
        self.direct_action_ids[index], self.direct_action_ids[target] = (
            self.direct_action_ids[target],
            self.direct_action_ids[index],
        )
        self._refresh_direct_actions(select=target)

    def _refresh_direct_actions(self, *, select: int = -1) -> None:
        self.direct_action_list.delete(0, tk.END)
        for action_id in self.direct_action_ids:
            self.direct_action_list.insert(
                tk.END,
                self.direct_labels_by_id.get(
                    action_id,
                    f"Missing action: {action_id}",
                ),
            )
        if 0 <= select < len(self.direct_action_ids):
            self.direct_action_list.selection_set(select)
            self.direct_action_list.see(select)


class ButtonDialog:
    def __init__(
        self, parent: tk.Toplevel, group: CommandGroup | None, item: CommandItem | None,
        actions: list[Action],
        on_save: Callable[[str, str, CommandItem, str, str], bool],
        *,
        shared: bool = False,
        work_items: tuple[DiscoveredWorkItem, ...] = (),
        creating_submenu: bool = False,
    ) -> None:
        self.original_group_id = group.id if group else ""
        self.original_item_id = item.id if item else ""
        self.child_items = item.items if item else ()
        self.project_storage = shared
        self.on_save = on_save
        self.window = tk.Toplevel(parent)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.title(
            "Edit built-in Quick-action item"
            if item and shared
            else "Edit Quick-action item"
            if item
            else "New submenu"
            if creating_submenu
            else "New Quick action"
        )
        configure_standard_window(self.window, parent)
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        self.controls_frame = _dialog_buttons(
            outer,
            self._save,
            self.window.destroy,
        )
        self.form_view = _ScrollableDialogBody(self.window, outer)
        form = self.form_view.content
        self.group_id = tk.StringVar(value=group.id if group else "")
        self.group_label = tk.StringVar(value=group.label if group else "")
        self.item_id = tk.StringVar(value=item.id if item else "")
        self.item_label = tk.StringVar(value=item.label if item else "")
        ttk.Label(
            form,
            text=f"Menu: {group.label if group else 'None'}",
            style="Muted.TLabel",
        ).pack(anchor=tk.W)
        item_entry = _entry(
            form,
            "Submenu name" if creating_submenu else "Quick-action name",
            self.item_label,
        )
        self.assigned_targets = list(command_item_targets(item)) if item else []
        self.action_choices = _action_choices(actions)
        self.action_picker_options = _action_picker_options(
            actions,
            choices=self.action_choices,
        )
        labels_by_id = {action_id: label for label, action_id in self.action_choices.items()}
        self.labels_by_id = labels_by_id
        self.assigned_action_ids = [
            target.action_id
            for target in self.assigned_targets
            if target.action_id
        ]
        self.work_item_choices = _work_item_choices(work_items)
        self.work_item_labels_by_ref = {
            reference: label
            for label, reference in self.work_item_choices.items()
        }
        ttk.Label(
            form,
            text=(
                "Targets appear in this order when the menu opens. Actions and "
                "Work Items can be mixed."
            ),
            wraplength=610,
        ).pack(anchor=tk.W, pady=(9, 2))
        chooser = ttk.Frame(form)
        chooser.pack(fill=tk.X)
        self.action_choice_var = tk.StringVar()
        self.action_choice = ActionPickerField(
            chooser,
            variable=self.action_choice_var,
            options=self.action_picker_options,
            title="Choose Quick action assignment",
            scope_note=BUILT_IN_ACTION_SCOPE_NOTE if shared else None,
        )
        self.action_choice.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            chooser,
            text="Add",
            command=self._add_assigned_action,
        ).pack(side=tk.LEFT, padx=(6, 0))
        if not shared:
            ttk.Label(
                form,
                text="Add a Work Item target",
            ).pack(anchor=tk.W, pady=(9, 2))
            work_item_chooser = ttk.Frame(form)
            work_item_chooser.pack(fill=tk.X)
            self.work_item_choice_var = tk.StringVar(
                value=""
            )
            self.work_item_choice = ActionPickerField(
                work_item_chooser,
                variable=self.work_item_choice_var,
                options=_work_item_picker_options(
                    work_items,
                    self.work_item_choices,
                ),
                title="Choose Work Item for Quick action",
                item_name="Work Item",
                item_plural="Work Items",
                search_help=(
                    "Searches Work Item name, source, kind, organisation, "
                    "project code, and stable folder identity. Use Down Arrow, "
                    "Enter, or double-click."
                ),
            )
            self.work_item_choice.pack(
                side=tk.LEFT,
                fill=tk.X,
                expand=True,
            )
            ttk.Button(
                work_item_chooser,
                text="Add Work Item",
                command=self._use_work_item,
            ).pack(side=tk.LEFT, padx=(6, 0))
        assigned = ttk.Frame(form)
        assigned.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.assignment_list = tk.Listbox(
            assigned,
            exportselection=False,
            height=8,
        )
        self.assignment_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(
            assigned,
            orient=tk.VERTICAL,
            command=self.assignment_list.yview,
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.assignment_list.configure(yscrollcommand=scrollbar.set)
        assignment_controls = ttk.Frame(form)
        assignment_controls.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(
            assignment_controls,
            text="Remove",
            command=self._remove_assigned_action,
        ).pack(side=tk.LEFT)
        ttk.Button(
            assignment_controls,
            text="Move up",
            command=lambda: self._move_assigned_action(-1),
        ).pack(side=tk.LEFT, padx=(6, 0))
        self.assignment_move_down_button = ttk.Button(
            assignment_controls,
            text="Move down",
            command=lambda: self._move_assigned_action(1),
        )
        self.assignment_move_down_button.pack(side=tk.LEFT, padx=(6, 0))
        self.assignment_preview_var = tk.StringVar()
        self.assignment_preview_label = ttk.Label(
            form,
            textvariable=self.assignment_preview_var,
            style="Muted.TLabel",
            wraplength=610,
        )
        self.assignment_preview_label.pack(fill=tk.X, pady=(8, 0))
        self._refresh_assignment_list()
        self.window.transient(parent)
        self.window.grab_set()
        _focus_entry(self.window, item_entry)

    def _add_assigned_action(self) -> None:
        action_id = self.action_choices.get(self.action_choice_var.get())
        target = CommandTarget(action_id=action_id) if action_id else None
        if target is None or target in self.assigned_targets:
            return
        self.assigned_targets.append(target)
        self._sync_assigned_action_ids()
        self._refresh_assignment_list(select=len(self.assigned_targets) - 1)

    def _use_work_item(self) -> None:
        reference = self.work_item_choices.get(self.work_item_choice_var.get())
        if reference is None:
            return
        target = CommandTarget(work_item_ref=reference)
        if target in self.assigned_targets:
            return
        self.assigned_targets.append(target)
        if not self.item_label.get().strip():
            self.item_label.set(reference.relative_folder)
        self._sync_assigned_action_ids()
        self._refresh_assignment_list(select=len(self.assigned_targets) - 1)

    def _sync_assigned_action_ids(self) -> None:
        self.assigned_action_ids = [
            target.action_id
            for target in self.assigned_targets
            if target.action_id
        ]

    def _remove_assigned_action(self) -> None:
        selection = self.assignment_list.curselection()
        if not selection:
            return
        del self.assigned_targets[selection[0]]
        self._sync_assigned_action_ids()
        self._refresh_assignment_list(
            select=min(selection[0], len(self.assigned_targets) - 1)
        )

    def _move_assigned_action(self, offset: int) -> None:
        selection = self.assignment_list.curselection()
        if not selection:
            return
        index = selection[0]
        target = index + offset
        if target < 0 or target >= len(self.assigned_targets):
            return
        self.assigned_targets[index], self.assigned_targets[target] = (
            self.assigned_targets[target],
            self.assigned_targets[index],
        )
        self._sync_assigned_action_ids()
        self._refresh_assignment_list(select=target)

    def _refresh_assignment_list(self, *, select: int = -1) -> None:
        self.assignment_list.delete(0, tk.END)
        for index, target in enumerate(self.assigned_targets):
            if target.action_id:
                label = self.labels_by_id.get(
                    target.action_id,
                    f"Missing action: {target.action_id}",
                )
            else:
                label = self.work_item_labels_by_ref.get(
                    target.work_item_ref,
                    work_item_reference_label(target.work_item_ref, ()),
                )
            prefix = f"Target {index + 1}: "
            self.assignment_list.insert(tk.END, prefix + label)
        if 0 <= select < len(self.assigned_targets):
            self.assignment_list.selection_set(select)
            self.assignment_list.see(select)
        self.assignment_preview_var.set(
            (
                f"The menu shows {len(self.assigned_targets)} target(s) in this order."
            )
            if self.assigned_targets
            else "Add at least one action or Work Item."
        )

    def _save(self) -> None:
        if hasattr(self, "assigned_targets"):
            targets = tuple(dict.fromkeys(self.assigned_targets))
        else:
            # Compatibility for lightweight non-Tk tests.
            targets = tuple(
                CommandTarget(action_id=action_id)
                for action_id in dict.fromkeys(
                    self.action_choices[value.get()]
                    for value in self.action_ids
                    if value.get() in self.action_choices
                )
            )
        if not targets:
            messagebox.showerror(
                "Context Palette",
                "Assign at least one action or Work Item, or delete this Quick action.",
                parent=self.window,
            )
            return
        available_ids = set(getattr(self, "labels_by_id", {}))
        if not available_ids:
            available_ids = set(self.action_choices.values())
        unavailable_ids = [
            target.action_id
            for target in targets
            if target.action_id and target.action_id not in available_ids
        ]
        if unavailable_ids:
            messagebox.showerror(
                "Context Palette",
                (
                    "Built-in Quick actions can use only built-in actions. Remove "
                    "the unavailable My configuration action(s) before saving."
                    if getattr(self, "project_storage", False)
                    else "Remove unavailable actions before saving this Quick action."
                ),
                parent=self.window,
            )
            return
        group_id = self.group_id.get().strip() or _stable_id(self.group_label.get())
        item_id = self.item_id.get().strip() or _stable_id(self.item_label.get())
        saved = self.on_save(
            group_id,
            self.group_label.get(),
            CommandItem(
                id=item_id, label=self.item_label.get().strip(),
                primary_action_id="",
                action_ids=(),
                items=getattr(self, "child_items", ()),
                targets=targets,
            ),
            self.original_group_id, self.original_item_id,
        )
        if saved:
            self.window.destroy()


def _entry(parent: ttk.Frame, label: str, variable: tk.StringVar) -> ttk.Entry:
    ttk.Label(parent, text=label).pack(anchor=tk.W, pady=(7, 0))
    entry = ttk.Entry(parent, textvariable=variable)
    entry.pack(fill=tk.X, pady=(2, 0))
    return entry


def _destination_field(parent: ttk.Frame, variable: tk.StringVar) -> None:
    ttk.Label(parent, text="Storage").pack(anchor=tk.W, pady=(7, 0))
    ttk.Combobox(
        parent,
        textvariable=variable,
        values=(LOCAL_DESTINATION, PROJECT_DESTINATION),
        state="readonly",
    ).pack(fill=tk.X, pady=(2, 0))
    ttk.Label(
        parent,
        text=(
            "My configuration stays on this PC. Built-in changes the starter "
            "configuration tracked through Git and is intended for developers."
        ),
        style="Muted.TLabel",
        wraplength=610,
    ).pack(anchor=tk.W, pady=(2, 0))


def _focus_entry(window: tk.Toplevel, entry: ttk.Entry) -> None:
    after_id: str | None = None

    def apply_focus() -> None:
        nonlocal after_id
        after_id = None
        entry.focus_set()
        entry.selection_range(0, tk.END)

    def cancel_focus(event: tk.Event) -> None:
        nonlocal after_id
        if event.widget is not window or after_id is None:
            return
        try:
            window.after_cancel(after_id)
        except tk.TclError:
            pass
        after_id = None

    after_id = window.after_idle(apply_focus)
    window.bind("<Destroy>", cancel_focus, add="+")


def _stable_id(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.strip().casefold()).strip("-")


def _comma_separated(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _quick_action_path(value: str) -> tuple[str, ...]:
    clean = value.strip()
    if not clean:
        return ()
    parts = tuple(part.strip() for part in clean.split(">"))
    if any(not part for part in parts):
        raise ActionError(
            "Quick menu paths cannot contain an empty level between > separators."
        )
    return parts


def _action_choices(actions: list[Action]) -> dict[str, str]:
    choices: dict[str, str] = {}
    for action in sorted(
        actions,
        key=lambda item: (item.title.casefold(), item.effective_contexts),
    ):
        context_label = ", ".join(action.effective_contexts) or "General"
        definition = ACTION_TYPES[action.type]
        label = f"{definition.icon} {action.title} · {context_label}"
        if label in choices:
            label = f"{label} · {definition.label}"
        if label in choices:
            label = f"{label} · {action.id}"
        choices[label] = action.id
    return choices


def _action_picker_options(
    actions: list[Action],
    *,
    choices: dict[str, str] | None = None,
) -> tuple[ActionPickerOption, ...]:
    action_choices = choices if choices is not None else _action_choices(actions)
    actions_by_id = {action.id: action for action in actions}
    options: list[ActionPickerOption] = []
    for label, action_id in action_choices.items():
        action = actions_by_id.get(action_id)
        if action is None:
            options.append(ActionPickerOption(action_id, label, label))
            continue
        options.append(
            ActionPickerOption(
                action_id,
                label,
                action_search_text(action),
            )
        )
    return tuple(options)


class _ScrollableDialogBody:
    """A monitor-safe dialog body with a fixed footer outside its viewport."""

    def __init__(self, window: tk.Toplevel, parent: ttk.Frame) -> None:
        self.window = window
        self.host = ttk.Frame(parent)
        self.host.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(
            self.host,
            borderwidth=0,
            highlightthickness=0,
            background=window.cget("background"),
            takefocus=False,
        )
        self.scrollbar = ttk.Scrollbar(
            self.host,
            orient=tk.VERTICAL,
            command=self.canvas.yview,
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.content = ttk.Frame(self.canvas)
        self.content_window_id = self.canvas.create_window(
            (0, 0),
            window=self.content,
            anchor=tk.NW,
        )
        self.content.bind("<Configure>", self._update_scrollregion, add="+")
        self.canvas.bind("<Configure>", self._resize_content, add="+")
        window.bind("<MouseWheel>", self._on_mousewheel, add="+")
        window.bind("<FocusIn>", self._on_focus_in, add="+")

    def _update_scrollregion(self, _event: tk.Event | None = None) -> None:
        bounds = self.canvas.bbox("all")
        self.canvas.configure(scrollregion=bounds or (0, 0, 0, 0))

    def _resize_content(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(
            self.content_window_id,
            width=max(1, int(event.width)),
        )

    def _pointer_is_over_canvas(self) -> bool:
        x, y = self.window.winfo_pointerxy()
        left = self.canvas.winfo_rootx()
        top = self.canvas.winfo_rooty()
        return (
            left <= x < left + self.canvas.winfo_width()
            and top <= y < top + self.canvas.winfo_height()
        )

    def _on_mousewheel(self, event: tk.Event) -> str | None:
        if isinstance(event.widget, (tk.Text, tk.Listbox, ttk.Combobox)):
            return None
        if not self._pointer_is_over_canvas():
            return None
        delta = int(getattr(event, "delta", 0) or 0)
        if delta:
            self.canvas.yview_scroll(-1 if delta > 0 else 1, "units")
            return "break"
        return None

    def _on_focus_in(self, event: tk.Event) -> None:
        self.ensure_visible(event.widget)

    def ensure_visible(self, widget: tk.Misc) -> None:
        current: tk.Misc | None = widget
        while current is not None and current is not self.content:
            parent_name = current.winfo_parent()
            if not parent_name:
                current = None
                break
            current = current.nametowidget(parent_name)
        if current is not self.content:
            return
        self.window.update_idletasks()
        content_height = max(1, self.content.winfo_reqheight())
        viewport_top = float(self.canvas.canvasy(0))
        viewport_bottom = viewport_top + self.canvas.winfo_height()
        widget_top = widget.winfo_rooty() - self.content.winfo_rooty()
        widget_bottom = widget_top + widget.winfo_height()
        margin = 6
        if widget_top < viewport_top:
            self.canvas.yview_moveto(max(0.0, (widget_top - margin) / content_height))
        elif widget_bottom > viewport_bottom:
            self.canvas.yview_moveto(
                min(
                    1.0,
                    (widget_bottom + margin - self.canvas.winfo_height())
                    / content_height,
                )
            )


def _dialog_buttons(
    parent: ttk.Frame, save: Callable[[], None], cancel: Callable[[], None]
) -> ttk.Frame:
    controls = ttk.Frame(parent)
    controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
    ttk.Button(controls, text="Save", command=save, style="Accent.TButton").pack(side=tk.LEFT)
    ttk.Button(controls, text="Cancel", command=cancel).pack(side=tk.RIGHT)
    return controls
