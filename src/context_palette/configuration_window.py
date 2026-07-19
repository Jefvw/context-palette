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
    configured_draft_action,
    edited_configured_action,
    update_action,
)
from .action_types import ACTION_TYPES
from .command_surface import (
    CommandGroup,
    CommandItem,
    CommandSurfaceError,
    command_item_action_ids,
    load_combined_command_groups,
)
from .configuration_data import save_local_command_item, save_local_context
from .contexts import ContextDefinition, ContextError, load_combined_contexts, load_contexts
from .window_geometry import configure_standard_window


ACTION_TYPE_EXAMPLES = {
    "copy_text": "Example: Copy “Kind regards,” to the clipboard.",
    "workspace_template": "Example: Put a reusable meeting-notes outline in Input / Output.",
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


def action_matches_filter(action: Action, query: str, *, personal: bool) -> bool:
    terms = [term.casefold() for term in query.split() if term.strip()]
    if not terms:
        return True
    searchable = " ".join(
        (
            action.title,
            ACTION_TYPES[action.type].label,
            action.context,
            action.technology,
            action.task,
            action.state,
            "Personal" if personal else "Shared read-only",
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
        local_actions_path: Path,
        contexts_path: Path,
        local_contexts_path: Path,
        command_surface_path: Path,
        local_command_surface_path: Path,
        on_change: Callable[[], None],
        initial_tab: str = "actions",
    ) -> None:
        self.actions = actions
        self.local_action_ids = local_action_ids
        self.local_actions_path = local_actions_path
        self.contexts_path = contexts_path
        self.local_contexts_path = local_contexts_path
        self.command_surface_path = command_surface_path
        self.local_command_surface_path = local_command_surface_path
        self.on_change = on_change
        self.contexts: list[ContextDefinition] = []
        self.groups: list[CommandGroup] = []
        self.action_filter_var = tk.StringVar()
        self.action_filter_count_var = tk.StringVar()
        self.initial_tab = initial_tab

        self.window = tk.Toplevel(parent)
        self.window.title("Configure Context Palette")
        configure_standard_window(self.window)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        footer = ttk.Frame(outer)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        self.feedback_var = tk.StringVar(
            value="Shared project examples are visible but read-only."
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
        notebook = ttk.Notebook(outer)
        notebook.pack(fill=tk.BOTH, expand=True)
        self._build_actions_tab(notebook)
        self._build_types_tab(notebook)
        self._build_contexts_tab(notebook)
        self._build_buttons_tab(notebook)
        tab_indexes = {"actions": 0, "types": 1, "contexts": 2, "buttons": 3}
        notebook.select(tab_indexes.get(self.initial_tab, 0))
        self.window.bind("<Control-f>", self._focus_action_filter)
        self._reload()
        self.window.transient(parent)
        self.window.lift()
        if self.initial_tab == "contexts":
            self.window.after_idle(self.context_tree.focus_set)
        else:
            self.window.after_idle(self.action_tree.focus_set)

    def _build_actions_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Actions")
        ttk.Label(
            tab,
            text="Every personal action type is editable. Shared actions remain read-only.",
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
            columns=("type", "context", "source", "state"),
            show="tree headings",
            selectmode="browse",
        )
        for column, label, width in (
            ("#0", "Action", 245),
            ("type", "Built-in type", 150),
            ("context", "Context", 130),
            ("source", "Source", 115),
            ("state", "State", 70),
        ):
            self.action_tree.heading(column, text=label)
            self.action_tree.column(column, width=width, stretch=column in {"#0", "context"})
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
        ttk.Button(controls, text="Edit selected", command=self._edit_action).pack(
            side=tk.LEFT, padx=(6, 0)
        )

    def _build_types_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Built-in action types")
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
            text="Create personal Draft from this type",
            command=self._create_action,
            style="Accent.TButton",
        )
        create_button.pack(side=tk.BOTTOM, anchor=tk.E, pady=(8, 0), before=self.type_detail)
        self.type_list.bind("<<ListboxSelect>>", lambda _event: self._show_type())
        self.type_list.selection_set(0)
        self._show_type()

    def _build_contexts_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Contexts")
        ttk.Label(
            tab,
            text="Choose up to four preferred actions for slots 6–9.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 6))
        self.context_tree = ttk.Treeview(
            tab, columns=("source", "actions"), show="tree headings", selectmode="browse"
        )
        self.context_tree.heading("#0", text="Context")
        self.context_tree.heading("source", text="Source")
        self.context_tree.heading("actions", text="Preferred actions")
        self.context_tree.column("#0", width=180)
        self.context_tree.column("source", width=120, stretch=False)
        self.context_tree.column("actions", width=380)
        self.context_tree.pack(fill=tk.BOTH, expand=True)
        self.context_tree.bind("<Double-1>", lambda _event: self._edit_context())
        self.context_tree.bind("<Return>", lambda _event: self._edit_context())
        controls = ttk.Frame(tab)
        controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0), before=self.context_tree)
        ttk.Button(controls, text="Add personal context", command=self._add_context).pack(side=tk.LEFT)
        ttk.Button(controls, text="Edit selected", command=self._edit_context).pack(side=tk.LEFT, padx=(6, 0))

    def _build_buttons_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Right-side buttons")
        ttk.Label(
            tab,
            text="Buttons safely reference existing actions; they never contain commands.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 6))
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
        self.button_tree.bind("<Double-1>", lambda _event: self._edit_button())
        self.button_tree.bind("<Return>", lambda _event: self._edit_button())
        controls = ttk.Frame(tab)
        controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0), before=self.button_tree)
        ttk.Button(controls, text="Add personal button", command=self._add_button).pack(side=tk.LEFT)
        ttk.Button(controls, text="Edit selected", command=self._edit_button).pack(side=tk.LEFT, padx=(6, 0))

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
            ActionDraftDialog(
                self.window, self.type_ids[selected[0]], self.actions, self._save_action
            )

    def _save_action(self, action: Action) -> bool:
        try:
            append_action(self.local_actions_path, action)
        except ActionError as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.window)
            return False
        self.actions.append(action)
        self.local_action_ids.add(action.id)
        self.on_change()
        if self.action_filter_var.get():
            self.action_filter_var.set("")
        else:
            self._render_actions()
        self.feedback_var.set(f"Created Draft: {action.display_text}")
        self.feedback_label.configure(style="Success.TLabel")
        return True

    def _focus_action_filter(self, _event: tk.Event | None = None) -> str:
        self.action_filter_entry.focus_set()
        self.action_filter_entry.selection_range(0, tk.END)
        return "break"

    def _reload(self) -> None:
        self.window.configure(cursor="wait")
        self.window.update_idletasks()
        try:
            self.contexts = load_combined_contexts(self.contexts_path, self.local_contexts_path)
            self.groups = load_combined_command_groups(
                self.command_surface_path, self.local_command_surface_path
            )
        except (ContextError, CommandSurfaceError) as exc:
            self.feedback_var.set(f"Configuration could not be refreshed: {exc}")
            self.feedback_label.configure(style="Error.TLabel")
            return
        finally:
            self.window.configure(cursor="")
        self._render_actions()
        local_context_names = {
            item.name.casefold()
            for item in (load_contexts(self.local_contexts_path) if self.local_contexts_path.exists() else [])
        }
        self.context_tree.delete(*self.context_tree.get_children())
        for index, context in enumerate(self.contexts):
            local = context.name.casefold() in local_context_names
            self.context_tree.insert(
                "", tk.END, iid=f"context-{index}", text=context.name,
                values=("Personal" if local else "Shared (read-only)",
                        ", ".join(context.preferred_action_ids) or "Automatic"),
                tags=("local",) if local else ("shared",),
            )
        self.context_tree.tag_configure("shared", foreground="#666666")
        select_first_tree_item(self.context_tree)
        self.button_tree.delete(*self.button_tree.get_children())
        for group_index, group in enumerate(self.groups):
            local = bool(
                group.source_path
                and group.source_path.resolve() == self.local_command_surface_path.resolve()
            )
            group_iid = f"group-{group_index}"
            self.button_tree.insert(
                "", tk.END, iid=group_iid, text=group.label,
                values=("Personal" if local else "Shared (read-only)", ""),
                tags=("local",) if local else ("shared",), open=True,
            )
            for item_index, item in enumerate(group.items):
                ids = command_item_action_ids(item)
                self.button_tree.insert(
                    group_iid, tk.END, iid=f"button-{group_index}-{item_index}",
                    text=item.label,
                    values=("Personal" if local else "Shared (read-only)", ", ".join(ids)),
                    tags=("local",) if local else ("shared",),
                )
        self.button_tree.tag_configure("shared", foreground="#666666")
        select_first_tree_item(self.button_tree, descend=True)

    def _render_actions(self) -> None:
        self.action_tree.delete(*self.action_tree.get_children())
        query = self.action_filter_var.get()
        matching_iids: list[str] = []
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
                    action.context,
                    "Personal" if local else "Shared (read-only)",
                    action.state,
                ),
                tags=("local",) if local else ("shared",),
            )
            matching_iids.append(iid)
        self.action_tree.tag_configure("shared", foreground="#666666")
        self.action_filter_count_var.set(
            f"{len(matching_iids)} of {len(self.actions)}"
            if query.strip()
            else f"{len(self.actions)} actions"
        )
        if matching_iids:
            self.action_tree.selection_set(matching_iids[0])
            self.action_tree.focus(matching_iids[0])

    def _edit_action(self) -> None:
        selection = self.action_tree.selection()
        if not selection:
            return
        action = self.actions[int(selection[0].split("-")[1])]
        if action.id not in self.local_action_ids:
            messagebox.showinfo(
                "Context Palette",
                "Shared actions are read-only. Create a personal action instead.",
                parent=self.window,
            )
            return
        ActionDraftDialog(
            self.window,
            action.type,
            self.actions,
            self._save_edited_action,
            action=action,
        )

    def _save_edited_action(self, action: Action) -> bool:
        try:
            update_action(self.local_actions_path, action)
        except ActionError as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.window)
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

    def _add_context(self) -> None:
        ContextDialog(self.window, None, self.actions, self._save_context)

    def _edit_context(self) -> None:
        selection = self.context_tree.selection()
        if not selection:
            return
        if self.context_tree.item(selection[0], "values")[0] != "Personal":
            messagebox.showinfo(
                "Context Palette", "Shared contexts are read-only. Add a personal context instead.",
                parent=self.window,
            )
            return
        context = self.contexts[int(selection[0].split("-")[1])]
        ContextDialog(self.window, context, self.actions, self._save_context)

    def _save_context(self, context: ContextDefinition, original_name: str) -> bool:
        shared_names = {item.name.casefold() for item in load_contexts(self.contexts_path)}
        if context.name.casefold() in shared_names:
            messagebox.showerror(
                "Context Palette", "A shared context already uses that name.", parent=self.window
            )
            return False
        try:
            save_local_context(self.local_contexts_path, context, original_name=original_name)
        except ContextError as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.window)
            return False
        self.on_change()
        self._reload()
        self.feedback_var.set(f"Saved context: {context.name}")
        self.feedback_label.configure(style="Success.TLabel")
        return True

    def _add_button(self) -> None:
        ButtonDialog(self.window, None, None, self.actions, self._save_button)

    def _edit_button(self) -> None:
        selection = self.button_tree.selection()
        if not selection or not selection[0].startswith("button-"):
            messagebox.showinfo("Context Palette", "Select an individual button first.", parent=self.window)
            return
        _, group_index, item_index = selection[0].split("-")
        group = self.groups[int(group_index)]
        if not group.source_path or group.source_path.resolve() != self.local_command_surface_path.resolve():
            messagebox.showinfo(
                "Context Palette", "Shared buttons are read-only. Add a personal button instead.",
                parent=self.window,
            )
            return
        ButtonDialog(
            self.window, group, group.items[int(item_index)], self.actions, self._save_button
        )

    def _save_button(
        self, group_id: str, group_label: str, item: CommandItem,
        original_group_id: str, original_item_id: str,
    ) -> bool:
        shared_group_ids = {
            group.id.casefold()
            for group in load_combined_command_groups(
                self.command_surface_path, Path("__missing_command_surface__")
            )
        }
        if group_id.strip().casefold() in shared_group_ids:
            messagebox.showerror(
                "Context Palette",
                "A shared button group already uses that stable ID.",
                parent=self.window,
            )
            return False
        try:
            save_local_command_item(
                self.local_command_surface_path,
                group_id=group_id, group_label=group_label, item=item,
                original_group_id=original_group_id, original_item_id=original_item_id,
            )
        except CommandSurfaceError as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.window)
            return False
        self.on_change()
        self._reload()
        self.feedback_var.set(f"Saved quick-action button: {item.label}")
        self.feedback_label.configure(style="Success.TLabel")
        return True


class ActionDraftDialog:
    def __init__(
        self, parent: tk.Toplevel, action_type: str, actions: list[Action],
        on_save: Callable[[Action], bool],
        *,
        action: Action | None = None,
    ) -> None:
        self.action_type = action_type
        self.action = action
        self.on_save = on_save
        definition = ACTION_TYPES[action_type]
        self.window = tk.Toplevel(parent)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.title(
            f"Edit action · {definition.label}" if action else f"Create Draft · {definition.label}"
        )
        configure_standard_window(self.window)
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        controls = ttk.Frame(outer)
        controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        ttk.Button(
            controls,
            text="Save action" if action else "Create Draft",
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
        self.title_var = tk.StringVar(value=action.title if action else "")
        self.context_var = tk.StringVar(value=action.context if action else "General")
        self.technology_var = tk.StringVar(value=action.technology if action else "")
        self.task_var = tk.StringVar(value=action.task if action else "")
        self.arguments_var = tk.StringVar(
            value="\n".join(action.arguments) if action else ""
        )
        self.working_directory_var = tk.StringVar(
            value=action.working_directory or "" if action else ""
        )
        title_entry = _entry(outer, "Action name", self.title_var)
        ttk.Label(outer, text="Context").pack(anchor=tk.W, pady=(7, 0))
        ttk.Combobox(
            outer, textvariable=self.context_var,
            values=sorted({item.context for item in actions if item.context}, key=str.casefold),
        ).pack(fill=tk.X, pady=(2, 0))
        row = ttk.Frame(outer)
        row.pack(fill=tk.X)
        left, right = ttk.Frame(row), ttk.Frame(row)
        left.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        right.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        _entry(left, "Technology (optional)", self.technology_var)
        _entry(right, "Task (optional)", self.task_var)
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
            values = dict(
                title=self.title_var.get(), context=self.context_var.get(),
                action_type=self.action_type, value=self.value.get("1.0", "end-1c"),
                technology=self.technology_var.get(), task=self.task_var.get(),
                arguments=self.arguments_var.get().splitlines(),
                working_directory=self.working_directory_var.get(),
            )
            action = (
                edited_configured_action(self.action, **values)
                if self.action
                else configured_draft_action(**values)
            )
        except ActionError as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.window)
            return
        if self.on_save(action):
            self.window.destroy()


class ContextDialog:
    def __init__(
        self, parent: tk.Toplevel, context: ContextDefinition | None,
        actions: list[Action], on_save: Callable[[ContextDefinition, str], bool],
    ) -> None:
        self.original_name = context.name if context else ""
        self.on_save = on_save
        self.window = tk.Toplevel(parent)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.title("Edit personal context" if context else "Add personal context")
        configure_standard_window(self.window)
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        _dialog_buttons(outer, self._save, self.window.destroy)
        self.name = tk.StringVar(value=context.name if context else "")
        self.description = tk.StringVar(value=context.description if context else "")
        self.technology = tk.StringVar(value=context.technology if context else "")
        self.task = tk.StringVar(value=context.task if context else "")
        name_entry = _entry(outer, "Context name", self.name)
        _entry(outer, "Description", self.description)
        _entry(outer, "Technology (optional)", self.technology)
        _entry(outer, "Task (optional)", self.task)
        preferred = context.preferred_action_ids if context else ()
        self.action_choices = _action_choices(actions)
        labels_by_id = {action_id: label for label, action_id in self.action_choices.items()}
        self.slots = [
            tk.StringVar(
                value=labels_by_id.get(preferred[index], "")
                if index < len(preferred)
                else ""
            )
            for index in range(4)
        ]
        values = [""] + list(self.action_choices)
        ttk.Label(outer, text="Preferred actions for slots 6–9").pack(anchor=tk.W, pady=(9, 2))
        for slot, variable in enumerate(self.slots, start=6):
            row = ttk.Frame(outer)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"Slot {slot}", width=8).pack(side=tk.LEFT)
            ttk.Combobox(row, textvariable=variable, values=values, state="readonly").pack(
                side=tk.LEFT, fill=tk.X, expand=True
            )
        self.window.transient(parent)
        self.window.grab_set()
        _focus_entry(self.window, name_entry)

    def _save(self) -> None:
        name = self.name.get().strip()
        if not name:
            messagebox.showerror("Context Palette", "Context name cannot be empty.", parent=self.window)
            return
        saved = self.on_save(
            ContextDefinition(
                name=name, description=self.description.get().strip(),
                technology=self.technology.get().strip(), task=self.task.get().strip(),
                preferred_action_ids=tuple(
                    dict.fromkeys(
                        self.action_choices[item.get()]
                        for item in self.slots
                        if item.get() in self.action_choices
                    )
                ),
            ),
            self.original_name,
        )
        if saved:
            self.window.destroy()


class ButtonDialog:
    def __init__(
        self, parent: tk.Toplevel, group: CommandGroup | None, item: CommandItem | None,
        actions: list[Action],
        on_save: Callable[[str, str, CommandItem, str, str], bool],
    ) -> None:
        self.original_group_id = group.id if group else ""
        self.original_item_id = item.id if item else ""
        self.on_save = on_save
        self.window = tk.Toplevel(parent)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.title("Edit personal button" if item else "Add personal button")
        configure_standard_window(self.window)
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        _dialog_buttons(outer, self._save, self.window.destroy)
        self.group_id = tk.StringVar(value=group.id if group else "")
        self.group_label = tk.StringVar(value=group.label if group else "")
        self.item_id = tk.StringVar(value=item.id if item else "")
        self.item_label = tk.StringVar(value=item.label if item else "")
        group_entry = _entry(outer, "Group heading", self.group_label)
        _entry(outer, "Button label", self.item_label)
        ids = command_item_action_ids(item) if item else ()
        self.action_choices = _action_choices(actions)
        labels_by_id = {action_id: label for label, action_id in self.action_choices.items()}
        self.action_ids = [
            tk.StringVar(value=labels_by_id.get(ids[index], "") if index < len(ids) else "")
            for index in range(4)
        ]
        values = [""] + list(self.action_choices)
        ttk.Label(outer, text="Actions shown by this button").pack(anchor=tk.W, pady=(9, 2))
        for index, variable in enumerate(self.action_ids, start=1):
            row = ttk.Frame(outer)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=str(index), width=4).pack(side=tk.LEFT)
            ttk.Combobox(row, textvariable=variable, values=values, state="readonly").pack(
                side=tk.LEFT, fill=tk.X, expand=True
            )
        self.window.transient(parent)
        self.window.grab_set()
        _focus_entry(self.window, group_entry)

    def _save(self) -> None:
        ids = tuple(
            dict.fromkeys(
                self.action_choices[value.get()]
                for value in self.action_ids
                if value.get() in self.action_choices
            )
        )
        group_id = self.group_id.get().strip() or _stable_id(self.group_label.get())
        item_id = self.item_id.get().strip() or _stable_id(self.item_label.get())
        saved = self.on_save(
            group_id, self.group_label.get(),
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


def _focus_entry(window: tk.Toplevel, entry: ttk.Entry) -> None:
    def apply_focus() -> None:
        entry.focus_set()
        entry.selection_range(0, tk.END)

    window.after_idle(apply_focus)


def _stable_id(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.strip().casefold()).strip("-")


def _action_choices(actions: list[Action]) -> dict[str, str]:
    choices: dict[str, str] = {}
    for action in sorted(actions, key=lambda item: (item.title.casefold(), item.context.casefold())):
        label = f"{action.title} · {action.context}"
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
