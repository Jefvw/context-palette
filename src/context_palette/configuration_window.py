from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path
import re
from typing import Callable

from .actions import (
    Action,
    ActionError,
    append_action,
    configured_action,
    edited_configured_action,
    load_combined_actions,
    update_action,
    validate_context_memberships,
)
from .action_deletion import (
    ActionDeletionError,
    delete_action_and_references,
    inspect_action_references,
)
from .action_types import ACTION_TYPES
from .command_surface import (
    CommandGroup,
    CommandItem,
    CommandSurfaceError,
    command_item_action_ids,
    load_combined_command_groups,
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
from .context_deletion import (
    ContextDeletionError,
    delete_context_and_memberships,
    rename_context_and_references,
)
from .diagnostics import render_safe_diagnostics, summarize_diagnostics
from .harvest_window import HarvestWindow
from .context_membership_field import (
    ContextMembershipField,
    TagSelectionField,
    specific_context_names,
)
from .window_geometry import configure_standard_window
from .work_item_configuration import WorkItemsConfigurationPanel
from .work_item_refresh import WorkItemIndex
from .work_items import WorkItemSource
from .work_item_storage import WorkItemMetadata


ACTION_TYPE_EXAMPLES = {
    "copy_text": "Example: Paste “Kind regards,” into the application you came from.",
    "workspace_template": "Example: Put a reusable meeting-notes outline in Input / Output.",
    "ai_prompt": "Example: Load a stored review prompt into Input / Output before using it with an AI assistant.",
    "open_url": "Example: Open https://docs.python.org/ in the default browser.",
    "open_file": r"Example: Open %PROJECT_ROOT%\README.md in its associated application.",
    "open_folder": r"Example: Open %PROJECT_ROOT%\docs in File Explorer.",
    "launch_app": r"Example: Start C:\Tools\Example\Example.exe with reviewed arguments.",
    "paste_credential": "Example: Paste the Windows or generic credential target oracle-pc17.",
    "build_url_copy": "Example: Ask for ABC 123 and copy https://example.com/items/ABC%20123.",
    "build_url_open": "Example: Ask for ABC 123 and open its generated website address.",
    "build_url_selection_open": "Example: Use selected text ABC 123, copy its URL, and open it.",
    "transform_list_csv": "Example: Convert three input lines into red, green, blue.",
}

LOCAL_DESTINATION = "My configuration"
PROJECT_DESTINATION = "Built-in"


def action_matches_filter(action: Action, query: str, *, personal: bool) -> bool:
    terms = [term.casefold() for term in query.split() if term.strip()]
    if not terms:
        return True
    searchable = " ".join(
        (
            action.title,
            action.description,
            ACTION_TYPES[action.type].label,
            *action.effective_contexts,
            *action.effective_tags,
            action.state,
            f"{LOCAL_DESTINATION} local personal"
            if personal
            else f"{PROJECT_DESTINATION} project shared",
        )
    ).casefold()
    return all(term in searchable for term in terms)


def context_membership_count(
    context: ContextDefinition,
    actions: list[Action],
) -> int:
    """Count the actions that will lose membership when a context is deleted."""
    if context.action_ids is not None:
        return len(
            {
                action_id
                for action_id in (
                    *context.action_ids,
                    *context.preferred_action_ids,
                )
                if action_id
            }
        )
    member_ids = {
        action.id
        for action in actions
        if action.belongs_to_context(context.name)
    }
    member_ids.update(context.preferred_action_ids)
    return len(member_ids)


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


def context_action_summary(
    context: ContextDefinition,
    actions: list[Action],
) -> str:
    preferred = action_reference_labels(context.preferred_action_ids, actions)
    preferred_text = ", ".join(preferred) if preferred else "automatic"
    return (
        f"{context_membership_count(context, actions)} member(s) | "
        f"Preferred: {preferred_text}"
    )


def context_matches_filter(
    context: ContextDefinition,
    query: str,
    *,
    actions: list[Action],
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
    searchable = " ".join(
        (
            context.name,
            context.description,
            *labels,
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
) -> bool:
    terms = [term.casefold() for term in query.split() if term.strip()]
    if not terms:
        return True
    labels = (
        action_reference_labels(command_item_action_ids(item), actions)
        if item is not None
        else ()
    )
    searchable = " ".join(
        (
            group.label,
            item.label if item is not None else "",
            *labels,
            f"{LOCAL_DESTINATION} local personal"
            if personal
            else f"{PROJECT_DESTINATION} project shared",
        )
    ).casefold()
    return all(term in searchable for term in terms)


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
        initial_tab: str = "actions",
        initial_action_id: str | None = None,
        initial_work_item_key: str | None = None,
        start_work_item_creation: bool = False,
    ) -> None:
        self.actions = actions
        self.local_action_ids = local_action_ids
        self.shared_actions_path = shared_actions_path
        self.local_actions_path = local_actions_path
        self.contexts_path = contexts_path
        self.local_contexts_path = local_contexts_path
        self.command_surface_path = command_surface_path
        self.local_command_surface_path = local_command_surface_path
        self.palette_path = palette_path
        self.work_item_sources_path = work_item_sources_path
        self.work_item_metadata_path = work_item_metadata_path
        self.work_item_settings_path = work_item_settings_path
        self.on_change = on_change
        self.focus_context = focus_context
        self.contexts: list[ContextDefinition] = []
        self.groups: list[CommandGroup] = []
        self.action_filter_var = tk.StringVar()
        self.action_filter_count_var = tk.StringVar()
        self.context_filter_var = tk.StringVar()
        self.context_filter_count_var = tk.StringVar()
        self.button_filter_var = tk.StringVar()
        self.button_filter_count_var = tk.StringVar()
        self.initial_tab = initial_tab
        self.initial_action_id = initial_action_id
        self.initial_work_item_key = initial_work_item_key
        self.start_work_item_creation = start_work_item_creation

        self.window = tk.Toplevel(parent)
        self.window.title("Configure Context Palette")
        configure_standard_window(self.window)
        self.window.bind("<Escape>", self._close_on_plain_escape)
        self.window.bind("<KeyPress>", self._handle_configure_keypress, add="+")
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        footer = ttk.Frame(outer)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        self.feedback_var = tk.StringVar(
            value="Everything shown here is editable; project changes travel through Git."
        )
        self.feedback_label = ttk.Label(
            footer,
            textvariable=self.feedback_var,
            style="Status.TLabel",
        )
        self.feedback_label.pack(side=tk.LEFT)
        ttk.Button(
            footer,
            text="Close",
            command=self.window.destroy,
            style="Compact.TButton",
        ).pack(side=tk.RIGHT)
        ttk.Label(outer, text="Configure Context Palette", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            outer,
            text="Create repeated actions, organize them by context, then place them in slots or quick-action buttons.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(2, 10))
        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.notebook.enable_traversal()
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
        self._build_diagnostics_tab(self.notebook)
        tab_indexes = {
            "actions": 0,
            "types": 1,
            "contexts": 2,
            "buttons": 3,
            "work_items": 4,
            "diagnostics": 5,
        }
        self.notebook.select(tab_indexes.get(self.initial_tab, 0))
        self.notebook.bind("<<NotebookTabChanged>>", self._focus_selected_tab)
        self.window.bind("<Control-f>", self._focus_current_filter)
        self._reload()
        if self.initial_work_item_key:
            self.work_items_panel.select_item(self.initial_work_item_key)
        self.window.transient(parent)
        self.window.lift()
        self.window.after_idle(self._focus_current_tab)
        if self.start_work_item_creation:
            self.window.after_idle(self._start_work_item_creation)

    def _start_work_item_creation(self) -> None:
        self.work_items_panel.create_work_item()

    def _close_on_plain_escape(self, event: tk.Event) -> str:
        if int(event.state) & 0x0004:
            return "break"
        self.window.destroy()
        return "break"

    def _handle_configure_keypress(self, event: tk.Event) -> str | None:
        state = int(getattr(event, "state", 0) or 0)
        if not state & 0x20000:
            return None
        tab_index = {
            "a": 0,
            "t": 1,
            "c": 2,
            "q": 3,
            "w": 4,
            "d": 5,
        }.get(str(getattr(event, "keysym", "")).casefold())
        if tab_index is None:
            return None
        self.notebook.select(tab_index)
        return "break"

    def _build_actions_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Actions", underline=0)
        ttk.Label(
            tab,
            text=(
                "All action types are editable. Built-in changes alter the "
                "starter configuration shipped through Git."
            ),
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 6))
        filter_row = ttk.Frame(tab)
        filter_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(filter_row, text="Find actions").pack(side=tk.LEFT)
        self.action_filter_entry = ttk.Entry(
            filter_row,
            textvariable=self.action_filter_var,
        )
        self.action_filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 8))
        ttk.Label(
            filter_row,
            textvariable=self.action_filter_count_var,
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)
        self.action_tree = ttk.Treeview(
            tab,
            columns=("type", "contexts", "tags", "source", "state"),
            show="tree headings",
            selectmode="browse",
        )
        for column, label, width in (
            ("#0", "Action", 245),
            ("type", "Built-in type", 150),
            ("contexts", "Contexts", 145),
            ("tags", "Tags", 150),
            ("source", "Source", 115),
            ("state", "State", 70),
        ):
            self.action_tree.heading(column, text=label)
            self.action_tree.column(
                column,
                width=width,
                stretch=column in {"#0", "contexts", "tags"},
            )
        self.action_tree.pack(fill=tk.BOTH, expand=True)
        self.action_tree.bind("<Double-1>", lambda _event: self._edit_action())
        self.action_tree.bind("<Return>", lambda _event: self._edit_action())
        self.action_filter_var.trace_add("write", lambda *_args: self._render_actions())
        controls = ttk.Frame(tab)
        controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0), before=self.action_tree)
        ttk.Button(
            controls,
            text="Create from built-in type",
            command=lambda: notebook.select(1),
            style="Accent.TButton",
        ).pack(side=tk.LEFT)
        ttk.Button(
            controls,
            text="Harvest documents…",
            command=self._show_harvest,
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(controls, text="Edit selected", command=self._edit_action).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        ttk.Button(controls, text="Delete selected", command=self._delete_action).pack(
            side=tk.LEFT, padx=(6, 0)
        )

    def _show_harvest(self) -> None:
        HarvestWindow(
            self.window,
            actions=self.actions,
            context_names=[context.name for context in self.contexts],
            focus_context=self.focus_context,
            actions_path=self.local_actions_path,
            on_change=self._harvest_changed,
        )

    def _harvest_changed(self) -> None:
        try:
            self.actions, self.local_action_ids = load_combined_actions(
                self.shared_actions_path,
                self.local_actions_path,
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

    def _build_types_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Built-in action types", underline=16)
        panes = ttk.Panedwindow(tab, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True)
        self.type_ids = list(ACTION_TYPES)
        self.type_list = tk.Listbox(panes, exportselection=False, width=30)
        for definition in ACTION_TYPES.values():
            self.type_list.insert(tk.END, definition.label)
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
            text="Create action from this type",
            command=self._create_action,
            style="Accent.TButton",
        )
        create_button.pack(side=tk.BOTTOM, anchor=tk.E, pady=(8, 0), before=self.type_detail)
        self.type_list.bind("<<ListboxSelect>>", lambda _event: self._show_type())
        self.type_list.selection_set(0)
        self._show_type()

    def _build_contexts_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Contexts", underline=0)
        ttk.Label(
            tab,
            text=(
                "Choose every action in the context, then up to four preferred "
                "actions for slots 6–9."
            ),
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 6))
        filter_row = ttk.Frame(tab)
        filter_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(filter_row, text="Find contexts").pack(side=tk.LEFT)
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
        self.context_tree = ttk.Treeview(
            tab, columns=("source", "actions"), show="tree headings", selectmode="browse"
        )
        self.context_tree.heading("#0", text="Context")
        self.context_tree.heading("source", text="Source")
        self.context_tree.heading("actions", text="Members / preferred actions")
        self.context_tree.column("#0", width=180)
        self.context_tree.column("source", width=120, stretch=False)
        self.context_tree.column("actions", width=380)
        self.context_tree.pack(fill=tk.BOTH, expand=True)
        self.context_tree.bind("<Double-1>", lambda _event: self._edit_context())
        self.context_tree.bind("<Return>", lambda _event: self._edit_context())
        self.context_filter_var.trace_add(
            "write",
            lambda *_args: self._render_contexts(),
        )
        controls = ttk.Frame(tab)
        controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0), before=self.context_tree)
        ttk.Button(controls, text="Add context", command=self._add_context).pack(side=tk.LEFT)
        ttk.Button(controls, text="Edit selected", command=self._edit_context).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(controls, text="Delete selected", command=self._delete_context).pack(
            side=tk.LEFT, padx=(6, 0)
        )

    def _build_buttons_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Quick actions", underline=0)
        ttk.Label(
            tab,
            text="Buttons safely reference existing actions; they never contain commands.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 6))
        filter_row = ttk.Frame(tab)
        filter_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(filter_row, text="Find Quick actions").pack(side=tk.LEFT)
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
        self.button_tree = ttk.Treeview(
            tab, columns=("source", "actions"), show="tree headings", selectmode="browse"
        )
        self.button_tree.heading("#0", text="Group / button")
        self.button_tree.heading("source", text="Source")
        self.button_tree.heading("actions", text="Assigned actions")
        self.button_tree.column("#0", width=220)
        self.button_tree.column("source", width=120, stretch=False)
        self.button_tree.column("actions", width=340)
        self.button_tree.pack(fill=tk.BOTH, expand=True)
        self.button_preview_var = tk.StringVar(
            value="Select a group or Quick action to see how it behaves."
        )
        ttk.Label(
            tab,
            textvariable=self.button_preview_var,
            style="Muted.TLabel",
            wraplength=720,
        ).pack(fill=tk.X, pady=(6, 0))
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
        controls = ttk.Frame(tab)
        controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0), before=self.button_tree)
        ttk.Button(controls, text="Add group", command=self._add_group).pack(side=tk.LEFT)
        ttk.Button(controls, text="Add Quick action", command=self._add_button).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        ttk.Button(controls, text="Edit selected", command=self._edit_button).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(controls, text="Delete selected", command=self._delete_button).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        ttk.Button(
            controls,
            text="Up",
            width=5,
            command=lambda: self._move_button(-1),
        ).pack(side=tk.RIGHT, padx=(3, 0))
        ttk.Button(
            controls,
            text="Down",
            width=6,
            command=lambda: self._move_button(1),
        ).pack(side=tk.RIGHT)

    def _build_diagnostics_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Diagnostics", underline=0)
        ttk.Label(
            tab,
            text="Safe summary only. Use Ctrl+Tab to move between Configure tabs.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 6))
        self.diagnostics_text = tk.Text(
            tab,
            wrap=tk.WORD,
            height=18,
            padx=8,
            pady=8,
            takefocus=True,
        )
        self.diagnostics_text.pack(fill=tk.BOTH, expand=True)
        self.diagnostics_text.configure(state=tk.DISABLED)
        controls = ttk.Frame(tab)
        controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0), before=self.diagnostics_text)
        ttk.Button(
            controls,
            text="Refresh",
            command=self._refresh_diagnostics,
            style="Accent.TButton",
        ).pack(side=tk.LEFT)
        ttk.Button(
            controls,
            text="Copy safe summary",
            command=self._copy_diagnostics,
        ).pack(side=tk.LEFT, padx=(6, 0))

    def _build_work_items_tab(
        self,
        notebook: ttk.Notebook,
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
            on_change=self.on_change,
            feedback=self._set_feedback,
        )

    def _set_feedback(self, message: str, success: bool) -> None:
        self.feedback_var.set(message)
        self.feedback_label.configure(style="Success.TLabel" if success else "Error.TLabel")

    def _show_diagnostics_tab(self, _event: tk.Event | None = None) -> str:
        return self._show_config_tab(5)

    def _show_config_tab(self, tab_index: int) -> str:
        self.notebook.select(tab_index)
        self.window.after_idle(self._focus_current_tab)
        return "break"

    def _focus_selected_tab(self, _event: tk.Event | None = None) -> None:
        self.window.after_idle(self._focus_current_tab)

    def _focus_current_tab(self) -> None:
        selected = self.notebook.index(self.notebook.select())
        targets = (
            self.action_tree,
            self.type_list,
            self.context_tree,
            self.button_tree,
            self.work_items_panel,
            self.diagnostics_text,
        )
        if selected == 4:
            self.work_items_panel.focus()
        else:
            targets[selected].focus_set()

    def _show_type(self) -> None:
        selected = self.type_list.curselection()
        if not selected:
            return
        definition = ACTION_TYPES[self.type_ids[selected[0]]]
        self.type_title.set(definition.label)
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
            ActionDialog(
                self.window,
                self.type_ids[selected[0]],
                self.actions,
                self._save_action,
                context_names=[context.name for context in self.contexts],
                choose_destination=True,
            )

    def _save_action(
        self,
        action: Action,
        destination: str = LOCAL_DESTINATION,
    ) -> bool:
        local = destination != PROJECT_DESTINATION
        target_path = self.local_actions_path if local else self.shared_actions_path
        try:
            append_action(target_path, action)
        except (ActionError, OSError) as exc:
            messagebox.showerror(
                "Action was not created",
                f"Context Palette could not create this action.\n\n{exc}",
                parent=self.window,
            )
            return False
        self.actions.append(action)
        if local:
            self.local_action_ids.add(action.id)
        self.on_change()
        if self.action_filter_var.get():
            self.action_filter_var.set("")
        else:
            self._render_actions()
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
        entry = {
            0: self.action_filter_entry,
            2: self.context_filter_entry,
            3: self.button_filter_entry,
        }.get(selected)
        if entry is None:
            self.notebook.select(0)
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
            )
            self.contexts = load_combined_contexts(self.contexts_path, self.local_contexts_path)
            self.groups = load_combined_command_groups(
                self.command_surface_path, self.local_command_surface_path
            )
        except (ActionError, ContextError, CommandSurfaceError) as exc:
            self.feedback_var.set(f"Configuration could not be refreshed: {exc}")
            self.feedback_label.configure(style="Error.TLabel")
            return
        finally:
            self.window.configure(cursor="")
        self._render_actions()
        self.local_context_names = {
            item.name.casefold()
            for item in (load_contexts(self.local_contexts_path) if self.local_contexts_path.exists() else [])
        }
        self._render_contexts()
        self._render_buttons()
        self._refresh_diagnostics()

    def _render_contexts(self) -> None:
        self.context_tree.delete(*self.context_tree.get_children())
        query = self.context_filter_var.get()
        matches = 0
        for index, context in enumerate(self.contexts):
            local = context.name.casefold() in self.local_context_names
            if not context_matches_filter(
                context,
                query,
                actions=self.actions,
                personal=local,
            ):
                continue
            matches += 1
            self.context_tree.insert(
                "", tk.END, iid=f"context-{index}", text=context.name,
                values=(
                    LOCAL_DESTINATION if local else PROJECT_DESTINATION,
                    context_action_summary(context, self.actions),
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

    def _render_buttons(self) -> None:
        self.button_tree.delete(*self.button_tree.get_children())
        query = self.button_filter_var.get()
        total_items = sum(len(group.items) for group in self.groups)
        matching_items = 0
        for group_index, group in enumerate(self.groups):
            local = bool(
                group.source_path
                and group.source_path.resolve() == self.local_command_surface_path.resolve()
            )
            visible_items = [
                (item_index, item)
                for item_index, item in enumerate(group.items)
                if quick_action_matches_filter(
                    group,
                    item,
                    query,
                    actions=self.actions,
                    personal=local,
                )
            ]
            group_matches = quick_action_matches_filter(
                group,
                None,
                query,
                actions=self.actions,
                personal=local,
            )
            if not visible_items and not group_matches:
                continue
            if group_matches and not visible_items:
                visible_items = list(enumerate(group.items))
            matching_items += len(visible_items)
            group_iid = f"group-{group_index}"
            self.button_tree.insert(
                "", tk.END, iid=group_iid, text=group.label,
                values=(LOCAL_DESTINATION if local else PROJECT_DESTINATION, ""),
                tags=("local",) if local else ("shared",), open=True,
            )
            for item_index, item in visible_items:
                ids = command_item_action_ids(item)
                self.button_tree.insert(
                    group_iid, tk.END, iid=f"button-{group_index}-{item_index}",
                    text=item.label,
                    values=(
                        LOCAL_DESTINATION if local else PROJECT_DESTINATION,
                        ", ".join(action_reference_labels(ids, self.actions)),
                    ),
                    tags=("local",) if local else ("shared",),
                )
        self.button_tree.tag_configure("shared", foreground="#666666")
        select_first_tree_item(self.button_tree, descend=True)
        self.button_filter_count_var.set(
            f"{matching_items} of {total_items}"
            if query.strip()
            else f"{total_items} Quick actions"
        )
        self._update_button_preview()

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
        matching_iids: list[str] = []
        requested_iid: str | None = None
        for index, action in enumerate(self.actions):
            local = action.id in self.local_action_ids
            if not action_matches_filter(action, query, personal=local):
                continue
            iid = f"action-{index}"
            self.action_tree.insert(
                "",
                tk.END,
                iid=iid,
                text=action.title,
                values=(
                    ACTION_TYPES[action.type].label,
                    ", ".join(action.effective_contexts) or "General only",
                    ", ".join(action.effective_tags),
                    LOCAL_DESTINATION if local else PROJECT_DESTINATION,
                    action.state,
                ),
                tags=("local",) if local else ("shared",),
            )
            matching_iids.append(iid)
            if (
                self.initial_action_id is not None
                and action.id.casefold() == self.initial_action_id.casefold()
            ):
                requested_iid = iid
        self.action_tree.tag_configure("shared", foreground="#666666")
        self.action_filter_count_var.set(
            f"{len(matching_iids)} of {len(self.actions)}"
            if query.strip()
            else f"{len(self.actions)} actions"
        )
        if matching_iids:
            selected_iid = requested_iid or matching_iids[0]
            self.action_tree.selection_set(selected_iid)
            self.action_tree.focus(selected_iid)
            self.action_tree.see(selected_iid)

    def _edit_action(self) -> None:
        selection = self.action_tree.selection()
        if not selection:
            return
        action = self.actions[int(selection[0].split("-")[1])]
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
        ActionDialog(
            self.window,
            action.type,
            self.actions,
            lambda edited: self._save_edited_action(edited, target_path),
            action=action,
            context_names=[context.name for context in self.contexts],
        )

    def _save_edited_action(self, action: Action, target_path: Path) -> bool:
        try:
            update_action(target_path, action)
        except (ActionError, OSError) as exc:
            messagebox.showerror(
                "Action was not saved",
                f"Context Palette could not save this action.\n\n{exc}\n\n"
                "The existing action file was left unchanged. Close any program "
                "that may be locking the file, check that its folder is available, "
                "and try again.",
                parent=self.window,
            )
            return False
        self.actions[:] = [
            action if existing.id == action.id else existing for existing in self.actions
        ]
        self.on_change()
        if self.action_filter_var.get():
            self.action_filter_var.set("")
        else:
            self._render_actions()
        self.feedback_var.set(f"Saved action: {action.display_text}")
        self.feedback_label.configure(style="Success.TLabel")
        return True

    def _delete_action(self) -> None:
        selection = self.action_tree.selection()
        if not selection:
            return
        action = self.actions[int(selection[0].split("-")[1])]
        local = action.id in self.local_action_ids
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
            "Delete action?",
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
            )
        except (ActionDeletionError, OSError) as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.window)
            return
        self.actions[:] = [existing for existing in self.actions if existing.id != action.id]
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
            choose_destination=True,
        )

    def _edit_context(self) -> None:
        selection = self.context_tree.selection()
        if not selection:
            return
        context = self.contexts[int(selection[0].split("-")[1])]
        local = (
            self.context_tree.item(selection[0], "values")[0]
            == LOCAL_DESTINATION
        )
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
        if built_in and local_references:
            messagebox.showerror(
                "Context was not saved",
                "Built-in contexts can use only built-in actions. Remove the "
                "My configuration action assignment and try again.",
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
        selection = self.context_tree.selection()
        if not selection:
            return
        context = self.contexts[int(selection[0].split("-")[1])]
        local = (
            self.context_tree.item(selection[0], "values")[0]
            == LOCAL_DESTINATION
        )
        destination = self.local_contexts_path if local else self.contexts_path
        membership_count = context_membership_count(context, self.actions)
        if not messagebox.askyesno(
            "Delete context?",
            f'Delete "{context.name}" permanently?\n\n'
            f"{membership_count} action(s) will be moved to General if they have "
            "no other specific context. Saved Focus slots for this context will "
            "also be removed.\n\n"
            f"Storage: {LOCAL_DESTINATION if local else PROJECT_DESTINATION}",
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
            )
        except ActionError as exc:
            messagebox.showerror(
                "Context deleted; reload needed",
                f"The context was deleted, but actions could not be reloaded.\n\n{exc}",
                parent=self.window,
            )
        self._reload()
        self.feedback_var.set(
            f"Deleted context: {context.name}. Removed its assignment from "
            f"{membership_count} action(s)."
        )
        self.feedback_label.configure(style="Success.TLabel")

    def _add_group(self) -> None:
        GroupDialog(
            self.window,
            None,
            self._save_group,
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
        other_path = (
            self.local_command_surface_path
            if target_path.resolve() == self.command_surface_path.resolve()
            else self.command_surface_path
        )
        try:
            other_ids = {
                item.id.casefold()
                for item in (
                    load_combined_command_groups(
                        other_path,
                        Path("__missing_command_surface__"),
                    )
                    if other_path.exists()
                    else []
                )
            }
            if group.id.casefold() in other_ids:
                raise CommandSurfaceError(
                    "A Quick-action group in the other storage location already "
                    f'uses the name "{group.label}".'
                )
            save_command_group(
                target_path,
                group,
                original_group_id=original_group_id,
            )
        except (CommandSurfaceError, OSError) as exc:
            messagebox.showerror(
                "Quick-action group was not saved",
                f"Context Palette could not save this group.\n\n{exc}",
                parent=self.window,
            )
            return False
        self.on_change()
        self._reload()
        self.feedback_var.set(f"Saved Quick-action group: {group.label}")
        self.feedback_label.configure(style="Success.TLabel")
        return True

    def _selected_button_parts(
        self,
    ) -> tuple[CommandGroup, CommandItem | None] | None:
        selection = self.button_tree.selection()
        if not selection:
            return None
        parts = selection[0].split("-")
        if parts[0] == "group" and len(parts) == 2:
            return self.groups[int(parts[1])], None
        if parts[0] == "button" and len(parts) == 3:
            group = self.groups[int(parts[1])]
            return group, group.items[int(parts[2])]
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

    def _add_button(self) -> None:
        selected = self._selected_button_parts()
        if selected is None:
            messagebox.showinfo(
                "Select a group",
                "Select the group that should contain the new Quick action, "
                "or create a group first.",
                parent=self.window,
            )
            return
        group, _item = selected
        target_path = self._group_target_path(group)
        project = target_path.resolve() == self.command_surface_path.resolve()
        if project and not messagebox.askokcancel(
            "Add built-in Quick action?",
            "This Quick action will become part of the built-in starter "
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
            lambda *args: self._save_button(*args, target_path=target_path),
            shared=project,
        )

    def _edit_button(self) -> None:
        selected = self._selected_button_parts()
        if selected is None:
            return
        group, item = selected
        target_path = self._group_target_path(group)
        local = target_path.resolve() == self.local_command_surface_path.resolve()
        if not local and not messagebox.askokcancel(
                "Edit built-in Quick actions?",
                "This group is part of the built-in starter configuration tracked "
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
        )

    def _save_button(
        self, group_id: str, group_label: str, item: CommandItem,
        original_group_id: str, original_item_id: str,
        *,
        target_path: Path | None = None,
    ) -> bool:
        destination = target_path or self.local_command_surface_path
        project = destination.resolve() == self.command_surface_path.resolve()
        local_references = [
            action_id
            for action_id in command_item_action_ids(item)
            if action_id in getattr(self, "local_action_ids", set())
        ]
        if project and local_references:
            messagebox.showerror(
                "Quick action was not saved",
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
                    load_combined_command_groups(
                        other_path,
                        Path("__missing_command_surface__"),
                    )
                    if other_path.exists()
                    else []
                )
            }
            if group_id.strip().casefold() in other_group_ids:
                messagebox.showerror(
                    "Context Palette",
                    "A button group in the other configuration file already uses that stable ID.",
                    parent=self.window,
                )
                return False
            save_command_item(
                destination,
                group_id=group_id, group_label=group_label, item=item,
                original_group_id=original_group_id, original_item_id=original_item_id,
            )
        except (CommandSurfaceError, OSError) as exc:
            messagebox.showerror(
                "Quick action was not saved",
                f"Context Palette could not save this Quick action.\n\n{exc}\n\n"
                "The existing Quick-action file was left unchanged. Close any program "
                "that may be locking the file, check that its folder is available, "
                "and try again.",
                parent=self.window,
            )
            return False
        self.on_change()
        self._reload()
        self.feedback_var.set(f"Saved quick-action button: {item.label}")
        self.feedback_label.configure(style="Success.TLabel")
        return True

    def _delete_button(self) -> None:
        selected = self._selected_button_parts()
        if selected is None:
            return
        group, item = selected
        target_path = self._group_target_path(group)
        noun = "group" if item is None else "Quick action"
        label = group.label if item is None else item.label
        detail = (
            f"All {len(group.items)} Quick action(s) in this group will be removed."
            if item is None and group.items
            else "Its assigned actions remain available elsewhere."
        )
        if not messagebox.askyesno(
            f"Delete {noun}?",
            f'Delete "{label}" permanently?\n\n{detail}\n\n'
            f"Storage: "
            f"{LOCAL_DESTINATION if target_path.resolve() == self.local_command_surface_path.resolve() else PROJECT_DESTINATION}",
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
        selected = self._selected_button_parts()
        if selected is None:
            return
        group, item = selected
        target_path = self._group_target_path(group)
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

    def _update_button_preview(self) -> None:
        selected = self._selected_button_parts()
        if selected is None:
            self.button_preview_var.set(
                "Select a group or Quick action to see how it behaves."
            )
            return
        group, item = selected
        destination = (
            LOCAL_DESTINATION
            if self._group_target_path(group).resolve()
            == self.local_command_surface_path.resolve()
            else PROJECT_DESTINATION
        )
        if item is None:
            self.button_preview_var.set(
                f'Group "{group.label}" | {len(group.items)} Quick action(s) | '
                f"{destination}"
            )
            return
        labels = action_reference_labels(
            command_item_action_ids(item),
            self.actions,
        )
        self.button_preview_var.set(
            f"Left click: {labels[0] if labels else 'No action'} | "
            f"Right-click menu: {', '.join(labels) if labels else 'empty'} | "
            f"{destination}"
        )


class ActionDialog:
    def __init__(
        self, parent: tk.Toplevel, action_type: str, actions: list[Action],
        on_save: Callable[..., bool],
        *,
        action: Action | None = None,
        context_names: list[str] | None = None,
        choose_destination: bool = False,
    ) -> None:
        self.action_type = action_type
        self.action = action
        self.on_save = on_save
        self.choose_destination = choose_destination
        self.context_names = tuple(context_names or ())
        definition = ACTION_TYPES[action_type]
        self.window = tk.Toplevel(parent)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.title(
            f"Edit action · {definition.label}" if action else f"Create action · {definition.label}"
        )
        configure_standard_window(self.window)
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        controls = ttk.Frame(outer)
        controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        ttk.Button(
            controls,
            text="Save action" if action else "Create action",
            command=self._save,
            style="Accent.TButton",
        ).pack(side=tk.LEFT)
        ttk.Button(controls, text="Cancel", command=self.window.destroy).pack(side=tk.RIGHT)
        ttk.Label(outer, text=definition.label, style="Heading.TLabel").pack(anchor=tk.W)
        ttk.Label(
            outer,
            text=(
                f"{definition.description}\n{definition.output_description}\n"
                f"{ACTION_TYPE_EXAMPLES[action_type]}"
            ),
            style="Muted.TLabel", wraplength=610,
        ).pack(anchor=tk.W, pady=(2, 6))
        self.destination_var = tk.StringVar(value=LOCAL_DESTINATION)
        if choose_destination:
            _destination_field(outer, self.destination_var)
        self.title_var = tk.StringVar(value=action.title if action else "")
        self.description_var = tk.StringVar(
            value=action.description if action else ""
        )
        self.contexts_var = tk.StringVar(
            value=", ".join(action.effective_contexts) if action else ""
        )
        self.tags_var = tk.StringVar(
            value=", ".join(action.effective_tags) if action else ""
        )
        self.arguments_var = tk.StringVar(
            value="\n".join(action.arguments) if action else ""
        )
        self.working_directory_var = tk.StringVar(
            value=action.working_directory or "" if action else ""
        )
        title_entry = _entry(
            outer,
            "Short name (shown in action lists)",
            self.title_var,
        )
        _entry(
            outer,
            "Description (optional; searchable, shown in Action info)",
            self.description_var,
        )
        self.context_field = ContextMembershipField(
            outer,
            self.contexts_var,
            self.context_names,
            label="Specific contexts (optional; General always includes it)",
        )
        known_contexts = specific_context_names(self.context_names)
        if known_contexts:
            ttk.Label(
                outer,
                text="Choose one or more defined contexts, or type their names separated by commas.",
                style="Muted.TLabel",
                wraplength=610,
            ).pack(anchor=tk.W, pady=(2, 0))
        known_tags = sorted(
            {tag for item in actions for tag in item.effective_tags},
            key=str.casefold,
        )
        self.tag_field = TagSelectionField(
            outer,
            self.tags_var,
            known_tags,
        )
        if known_tags:
            ttk.Label(
                outer,
                text="Choose tags already in use, or type new tags separated by commas.",
                style="Muted.TLabel",
                wraplength=610,
            ).pack(anchor=tk.W, pady=(2, 0))
        label = {
            "open_url": "Complete website address", "open_file": "File path",
            "open_folder": "Folder path", "launch_app": "Application .exe path",
            "paste_credential": "Exact Windows or generic credential target name",
            "transform_list_csv": "Conversion mode: csv or sql_strings",
        }.get(action_type, "Saved text or URL template")
        ttk.Label(outer, text=label).pack(anchor=tk.W, pady=(8, 0))
        self.value = tk.Text(outer, height=7, wrap=tk.WORD, undo=True)
        self.value.pack(fill=tk.BOTH, expand=True, pady=(2, 0))
        if action:
            self.value.insert("1.0", action.value)
        elif action_type == "transform_list_csv":
            self.value.insert("1.0", "csv")
        elif action_type in {"build_url_copy", "build_url_open", "build_url_selection_open"}:
            self.value.insert("1.0", "https://example.com/items/{id_url}")
        if action_type == "launch_app":
            _entry(outer, "Arguments, one per line (optional)", self.arguments_var)
            _entry(outer, "Working folder (optional)", self.working_directory_var)
        self.window.transient(parent)
        self.window.grab_set()
        _focus_entry(self.window, title_entry)

    def _save(self) -> None:
        try:
            contexts = validate_context_memberships(
                _comma_separated(self.contexts_var.get()),
                self.context_names,
            )
            values = dict(
                title=self.title_var.get(),
                description=self.description_var.get(),
                context="General",
                contexts=contexts,
                tags=_comma_separated(self.tags_var.get()),
                action_type=self.action_type, value=self.value.get("1.0", "end-1c"),
                arguments=self.arguments_var.get().splitlines(),
                working_directory=self.working_directory_var.get(),
            )
            action = (
                edited_configured_action(self.action, **values)
                if self.action
                else configured_action(**values)
            )
        except ActionError as exc:
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
            else "Add context"
        )
        configure_standard_window(self.window)
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        _dialog_buttons(outer, self._save, self.window.destroy)
        self.name = tk.StringVar(value=context.name if context else "")
        self.description = tk.StringVar(value=context.description if context else "")
        name_entry = _entry(outer, "Context name", self.name)
        _entry(outer, "Description", self.description)
        self.destination_var = tk.StringVar(value=LOCAL_DESTINATION)
        if choose_destination:
            _destination_field(outer, self.destination_var)
        preferred = context.preferred_action_ids if context else ()
        self.action_choices = _action_choices(actions)
        labels_by_id = {action_id: label for label, action_id in self.action_choices.items()}
        self.labels_by_action_id = labels_by_id
        self.member_action_ids = list(
            dict.fromkeys(
                (
                    *(
                        context.action_ids
                        if context and context.action_ids is not None
                        else (
                            tuple(
                                action.id
                                for action in actions
                                if context
                                and action.belongs_to_context(context.name)
                            )
                        )
                    ),
                    *preferred,
                )
            )
        )
        ttk.Label(
            outer,
            text=(
                "Actions in this context. My configuration contexts may contain "
                "both built-in actions and your own actions."
            ),
            wraplength=610,
        ).pack(anchor=tk.W, pady=(9, 2))
        member_chooser = ttk.Frame(outer)
        member_chooser.pack(fill=tk.X)
        self.member_choice_var = tk.StringVar()
        self.member_choice = ttk.Combobox(
            member_chooser,
            textvariable=self.member_choice_var,
            values=list(self.action_choices),
            state="readonly",
        )
        self.member_choice.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            member_chooser,
            text="Add",
            command=self._add_member_action,
        ).pack(side=tk.LEFT, padx=(6, 0))
        member_area = ttk.Frame(outer)
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
            outer,
            text="Remove selected action",
            command=self._remove_member_action,
        ).pack(anchor=tk.W, pady=(5, 0))
        self.slots = [
            tk.StringVar(
                value=labels_by_id.get(preferred[index], "")
                if index < len(preferred)
                else ""
            )
            for index in range(4)
        ]
        self.slot_choices: list[ttk.Combobox] = []
        ttk.Label(outer, text="Preferred actions for slots 6–9").pack(anchor=tk.W, pady=(9, 2))
        for slot, variable in enumerate(self.slots, start=6):
            row = ttk.Frame(outer)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"Slot {slot}", width=8).pack(side=tk.LEFT)
            chooser = ttk.Combobox(
                row,
                textvariable=variable,
                state="readonly",
            )
            chooser.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.slot_choices.append(chooser)
        self._refresh_member_actions()
        self.window.transient(parent)
        self.window.grab_set()
        _focus_entry(self.window, name_entry)

    def _add_member_action(self) -> None:
        action_id = self.action_choices.get(self.member_choice_var.get())
        if not action_id or action_id in self.member_action_ids:
            return
        self.member_action_ids.append(action_id)
        self._refresh_member_actions(select=len(self.member_action_ids) - 1)

    def _remove_member_action(self) -> None:
        selection = self.member_list.curselection()
        if not selection:
            return
        removed_id = self.member_action_ids.pop(selection[0])
        removed_label = self.labels_by_action_id.get(removed_id, "")
        for slot in self.slots:
            if slot.get() == removed_label:
                slot.set("")
        self._refresh_member_actions(
            select=min(selection[0], len(self.member_action_ids) - 1)
        )

    def _refresh_member_actions(self, *, select: int = -1) -> None:
        self.member_list.delete(0, tk.END)
        labels = [
            self.labels_by_action_id.get(
                action_id,
                f"Unavailable action: {action_id}",
            )
            for action_id in self.member_action_ids
        ]
        for label in labels:
            self.member_list.insert(tk.END, label)
        if 0 <= select < len(labels):
            self.member_list.selection_set(select)
            self.member_list.see(select)
        values = ["", *labels]
        for chooser in self.slot_choices:
            chooser.configure(values=values)

    def _save(self) -> None:
        name = self.name.get().strip()
        if not name:
            messagebox.showerror("Context Palette", "Context name cannot be empty.", parent=self.window)
            return
        context = ContextDefinition(
            name=name, description=self.description.get().strip(),
            preferred_action_ids=tuple(
                dict.fromkeys(
                    self.action_choices[item.get()]
                    for item in self.slots
                    if item.get() in self.action_choices
                )
            ),
            action_ids=tuple(
                dict.fromkeys(getattr(self, "member_action_ids", ()))
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
        choose_destination: bool = False,
        destination: str = LOCAL_DESTINATION,
    ) -> None:
        self.group = group
        self.original_group_id = group.id if group else ""
        self.on_save = on_save
        self.window = tk.Toplevel(parent)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.title(
            "Edit Quick-action group" if group else "Add Quick-action group"
        )
        configure_standard_window(self.window)
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        _dialog_buttons(outer, self._save, self.window.destroy)
        ttk.Label(
            outer,
            text=(
                "A group is a visible heading containing one or more Quick actions."
            ),
            style="Muted.TLabel",
            wraplength=560,
        ).pack(anchor=tk.W)
        self.label_var = tk.StringVar(value=group.label if group else "")
        self.id_var = tk.StringVar(value=group.id if group else "")
        name_entry = _entry(outer, "Group heading", self.label_var)
        self.destination_var = tk.StringVar(value=destination)
        if choose_destination:
            _destination_field(outer, self.destination_var)
        else:
            ttk.Label(
                outer,
                text=f"Storage: {destination}",
                style="Muted.TLabel",
            ).pack(anchor=tk.W, pady=(8, 0))
        self.window.transient(parent)
        self.window.grab_set()
        _focus_entry(self.window, name_entry)

    def _save(self) -> None:
        label = self.label_var.get().strip()
        group_id = self.id_var.get().strip() or _stable_id(label)
        if not label or not group_id:
            messagebox.showerror(
                "Context Palette",
                "A Quick-action group needs a visible name.",
                parent=self.window,
            )
            return
        group = CommandGroup(
            group_id,
            label,
            self.group.items if self.group else (),
        )
        if self.on_save(
            group,
            self.original_group_id,
            self.destination_var.get(),
        ):
            self.window.destroy()


class ButtonDialog:
    def __init__(
        self, parent: tk.Toplevel, group: CommandGroup | None, item: CommandItem | None,
        actions: list[Action],
        on_save: Callable[[str, str, CommandItem, str, str], bool],
        *,
        shared: bool = False,
    ) -> None:
        self.original_group_id = group.id if group else ""
        self.original_item_id = item.id if item else ""
        self.project_storage = shared
        self.on_save = on_save
        self.window = tk.Toplevel(parent)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.title(
            "Edit built-in Quick action"
            if item and shared
            else "Edit Quick action"
            if item
            else "Add Quick action"
        )
        configure_standard_window(self.window)
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        _dialog_buttons(outer, self._save, self.window.destroy)
        self.group_id = tk.StringVar(value=group.id if group else "")
        self.group_label = tk.StringVar(value=group.label if group else "")
        self.item_id = tk.StringVar(value=item.id if item else "")
        self.item_label = tk.StringVar(value=item.label if item else "")
        ttk.Label(
            outer,
            text=f"Group: {group.label if group else 'None'}",
            style="Muted.TLabel",
        ).pack(anchor=tk.W)
        item_entry = _entry(outer, "Quick-action name", self.item_label)
        ids = command_item_action_ids(item) if item else ()
        self.action_choices = _action_choices(actions)
        labels_by_id = {action_id: label for label, action_id in self.action_choices.items()}
        self.labels_by_id = labels_by_id
        self.assigned_action_ids = list(ids)
        ttk.Label(
            outer,
            text=(
                "Assigned actions: the first action runs on left-click; "
                "right-click shows the complete ordered list."
            ),
            wraplength=610,
        ).pack(anchor=tk.W, pady=(9, 2))
        chooser = ttk.Frame(outer)
        chooser.pack(fill=tk.X)
        self.action_choice_var = tk.StringVar()
        self.action_choice = ttk.Combobox(
            chooser,
            textvariable=self.action_choice_var,
            values=list(self.action_choices),
            state="readonly",
        )
        self.action_choice.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            chooser,
            text="Add",
            command=self._add_assigned_action,
        ).pack(side=tk.LEFT, padx=(6, 0))
        assigned = ttk.Frame(outer)
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
        assignment_controls = ttk.Frame(outer)
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
        ttk.Button(
            assignment_controls,
            text="Move down",
            command=lambda: self._move_assigned_action(1),
        ).pack(side=tk.LEFT, padx=(6, 0))
        self.assignment_preview_var = tk.StringVar()
        ttk.Label(
            outer,
            textvariable=self.assignment_preview_var,
            style="Muted.TLabel",
            wraplength=610,
        ).pack(fill=tk.X, pady=(8, 0))
        self._refresh_assignment_list()
        self.window.transient(parent)
        self.window.grab_set()
        _focus_entry(self.window, item_entry)

    def _add_assigned_action(self) -> None:
        action_id = self.action_choices.get(self.action_choice_var.get())
        if not action_id or action_id in self.assigned_action_ids:
            return
        self.assigned_action_ids.append(action_id)
        self._refresh_assignment_list(select=len(self.assigned_action_ids) - 1)

    def _remove_assigned_action(self) -> None:
        selection = self.assignment_list.curselection()
        if not selection:
            return
        del self.assigned_action_ids[selection[0]]
        self._refresh_assignment_list(
            select=min(selection[0], len(self.assigned_action_ids) - 1)
        )

    def _move_assigned_action(self, offset: int) -> None:
        selection = self.assignment_list.curselection()
        if not selection:
            return
        index = selection[0]
        target = index + offset
        if target < 0 or target >= len(self.assigned_action_ids):
            return
        self.assigned_action_ids[index], self.assigned_action_ids[target] = (
            self.assigned_action_ids[target],
            self.assigned_action_ids[index],
        )
        self._refresh_assignment_list(select=target)

    def _refresh_assignment_list(self, *, select: int = -1) -> None:
        self.assignment_list.delete(0, tk.END)
        for index, action_id in enumerate(self.assigned_action_ids):
            label = self.labels_by_id.get(action_id, f"Missing action: {action_id}")
            prefix = "Default: " if index == 0 else f"Menu {index + 1}: "
            self.assignment_list.insert(tk.END, prefix + label)
        if 0 <= select < len(self.assigned_action_ids):
            self.assignment_list.selection_set(select)
            self.assignment_list.see(select)
        self.assignment_preview_var.set(
            (
                f"Left click runs: "
                f"{self.labels_by_id.get(self.assigned_action_ids[0], self.assigned_action_ids[0])}. "
                f"Right-click shows {len(self.assigned_action_ids)} action(s)."
            )
            if self.assigned_action_ids
            else "Add at least one action."
        )

    def _save(self) -> None:
        if hasattr(self, "assigned_action_ids"):
            ids = tuple(dict.fromkeys(self.assigned_action_ids))
        else:
            # Compatibility for lightweight non-Tk tests.
            ids = tuple(
                dict.fromkeys(
                    self.action_choices[value.get()]
                    for value in self.action_ids
                    if value.get() in self.action_choices
                )
            )
        if not ids:
            messagebox.showerror(
                "Context Palette",
                "Assign at least one action, or delete this Quick action.",
                parent=self.window,
            )
            return
        available_ids = set(getattr(self, "labels_by_id", {}))
        if not available_ids:
            available_ids = set(self.action_choices.values())
        unavailable_ids = [action_id for action_id in ids if action_id not in available_ids]
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
                primary_action_id=ids[0] if ids else "", action_ids=ids,
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
    def apply_focus() -> None:
        entry.focus_set()
        entry.selection_range(0, tk.END)

    window.after_idle(apply_focus)


def _stable_id(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.strip().casefold()).strip("-")


def _comma_separated(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _action_choices(actions: list[Action]) -> dict[str, str]:
    choices: dict[str, str] = {}
    for action in sorted(
        actions,
        key=lambda item: (item.title.casefold(), item.effective_contexts),
    ):
        context_label = ", ".join(action.effective_contexts) or "General"
        label = f"{action.title} · {context_label}"
        if label in choices:
            label = f"{label} · {ACTION_TYPES[action.type].label}"
        choices[label] = action.id
    return choices


def _dialog_buttons(
    parent: ttk.Frame, save: Callable[[], None], cancel: Callable[[], None]
) -> None:
    controls = ttk.Frame(parent)
    controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
    ttk.Button(controls, text="Save", command=save, style="Accent.TButton").pack(side=tk.LEFT)
    ttk.Button(controls, text="Cancel", command=cancel).pack(side=tk.RIGHT)
