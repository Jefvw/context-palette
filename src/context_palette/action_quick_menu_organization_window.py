"""Reviewed Tk UI for organizing automatic Quick-menu Action placements."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from .action_quick_menu_organization import (
    ASSIGN_OPERATION,
    MOVE_BRANCH_OPERATION,
    QuickMenuOrganizationError,
    QuickMenuOrganizationPlan,
    QuickMenuOrganizationResult,
    commit_quick_menu_organization,
    plan_quick_menu_assignment,
    plan_quick_menu_branch_move,
)
from .actions import ACTIVE_STATE, MAX_QUICK_ACTION_PATH_LEVELS, Action
from .quick_menu_path_dialog import (
    QuickMenuPathDialog,
    QuickMenuSubmenuNameDialog,
    quick_menu_root_label,
)
from .window_geometry import configure_standard_window


MOVE_ACTIONS_INTENT = "move_actions"
REMOVE_ACTIONS_INTENT = "remove_actions"
CREATE_SUBMENU_INTENT = "create_submenu"
RENAME_SUBMENU_INTENT = "rename_submenu"
MOVE_SUBMENU_INTENT = "move_submenu"
REMOVE_SUBMENU_INTENT = "remove_submenu"


class ActionQuickMenuOrganizationWindow:
    """Search, review, and commit automatic Quick-menu placement changes."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        group_label: str,
        action_type: str,
        actions: Iterable[Action],
        local_action_ids: Iterable[str],
        current_path: Iterable[str],
        shared_actions_path: Path,
        local_actions_path: Path,
        on_change: Callable[[], None],
        on_refresh: Callable[[], None],
    ) -> None:
        self.parent = parent
        self.action_type = action_type
        self.root_label = group_label.strip() or quick_menu_root_label(action_type)
        self.actions = tuple(actions)
        self.local_action_ids = frozenset(
            action_id.casefold() for action_id in local_action_ids
        )
        self.current_path = tuple(current_path)
        self.shared_actions_path = Path(shared_actions_path)
        self.local_actions_path = Path(local_actions_path)
        self.on_change = on_change
        self.on_refresh = on_refresh

        self.candidates = tuple(
            action
            for action in self.actions
            if action.type == self.action_type and action.state == ACTIVE_STATE
        )
        self.action_by_id = {action.id: action for action in self.candidates}
        self.action_id_by_iid: dict[str, str] = {}
        self.selected_action_ids: set[str] = set()
        self.visible_action_ids: tuple[str, ...] = ()
        self.destination_path: tuple[str, ...] | None = None
        self.plan: QuickMenuOrganizationPlan | None = None
        self.review_intent = MOVE_ACTIONS_INTENT
        self.submitting = False
        self.review_stale = False
        self.effects_unknown = False

        self.window = tk.Toplevel(parent)
        self.window.title(f"Manage {self.root_label} menu")
        configure_standard_window(self.window, parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.bind("<Control-f>", self._focus_search)

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(5, weight=1)

        ttk.Label(
            outer,
            text=f"Manage {self.root_label} menu",
            style="Title.TLabel",
        ).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            outer,
            text=(
                "Create, rename, move, or remove derived submenus by changing stored "
                "Action placements. No Action or external target is deleted. Empty "
                "submenus are not stored independently."
            ),
            style="Muted.TLabel",
            wraplength=740,
            justify=tk.LEFT,
        ).grid(row=1, column=0, sticky=tk.EW, pady=(2, 7))

        branch_row = ttk.Frame(outer)
        branch_row.grid(row=2, column=0, sticky=tk.EW, pady=(0, 7))
        branch_row.columnconfigure(0, weight=1)
        self.branch_var = tk.StringVar(value=self._current_branch_text())
        ttk.Label(
            branch_row,
            textvariable=self.branch_var,
            style="Heading.TLabel",
            wraplength=510,
            justify=tk.LEFT,
        ).grid(row=0, column=0, sticky=tk.W)
        self.submenu_tasks_button = ttk.Menubutton(
            branch_row,
            text="Submenu tasks",
        )
        self.submenu_tasks_menu = tk.Menu(
            self.submenu_tasks_button,
            tearoff=False,
        )
        self.submenu_tasks_button.configure(menu=self.submenu_tasks_menu)
        self.submenu_tasks_button.grid(row=0, column=1, sticky=tk.E)
        self.branch_button: ttk.Menubutton | None = (
            self.submenu_tasks_button if self.current_path else None
        )
        self._rebuild_submenu_tasks_menu()

        search_row = ttk.Frame(outer)
        search_row.grid(row=3, column=0, sticky=tk.EW, pady=(0, 6))
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="Find Action").grid(row=0, column=0, sticky=tk.W)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        self.search_entry.grid(row=0, column=1, sticky=tk.EW, padx=(6, 8))
        self.count_var = tk.StringVar()
        ttk.Label(
            search_row,
            textvariable=self.count_var,
            style="Muted.TLabel",
        ).grid(row=0, column=2, sticky=tk.E)

        selection_row = ttk.Frame(outer)
        selection_row.grid(row=4, column=0, sticky=tk.EW, pady=(0, 6))
        selection_commands = ttk.Frame(selection_row)
        selection_commands.pack(fill=tk.X)
        self.select_all_button = ttk.Button(
            selection_commands,
            text="Select all shown",
            command=self.select_all_shown,
        )
        self.select_all_button.pack(side=tk.LEFT)
        self.clear_button = ttk.Button(
            selection_commands,
            text="Clear selection",
            command=self.clear_selection,
        )
        self.clear_button.pack(side=tk.LEFT, padx=(6, 0))
        self.placement_commands = ttk.Frame(selection_row)
        self.placement_commands.pack(fill=tk.X, pady=(6, 0))
        self.destination_button = ttk.Button(
            self.placement_commands,
            text="Move selected…",
            command=self.choose_assignment_destination,
        )
        self.destination_button.pack(side=tk.LEFT)
        self.remove_selected_button = ttk.Button(
            self.placement_commands,
            text="Remove selected from this submenu",
            command=self.remove_selected_from_current_submenu,
        )
        self.destination_var = tk.StringVar(value="Destination: Not chosen")
        self.destination_label = ttk.Label(
            self.placement_commands,
            textvariable=self.destination_var,
            style="Muted.TLabel",
        )
        self.destination_label.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=(8, 0),
        )
        self._sync_remove_selected_button()

        review = ttk.Panedwindow(outer, orient=tk.VERTICAL)
        review.grid(row=5, column=0, sticky=tk.NSEW)

        table_frame = ttk.Frame(review)
        review.add(table_frame, weight=3)
        vertical = ttk.Scrollbar(table_frame, orient=tk.VERTICAL)
        horizontal = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL)
        self.tree = ttk.Treeview(
            table_frame,
            columns=("use", "action", "state", "storage", "placement"),
            show="headings",
            selectmode="browse",
            yscrollcommand=vertical.set,
            xscrollcommand=horizontal.set,
        )
        vertical.configure(command=self.tree.yview)
        horizontal.configure(command=self.tree.xview)
        vertical.pack(side=tk.RIGHT, fill=tk.Y)
        horizontal.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for column, label, width, stretch, anchor in (
            ("use", "Select", 54, False, tk.CENTER),
            ("action", "Action", 220, True, tk.W),
            ("state", "State", 84, False, tk.W),
            ("storage", "Storage", 130, False, tk.W),
            ("placement", "Current placement", 270, True, tk.W),
        ):
            self.tree.heading(column, text=label)
            self.tree.column(
                column,
                width=width,
                minwidth=width,
                stretch=stretch,
                anchor=anchor,
            )
        self.tree.bind("<ButtonRelease-1>", self._tree_clicked)
        self.tree.bind("<space>", self._toggle_from_key)
        self.tree.bind("<Return>", self._toggle_from_key)
        # Deliberately scope Select All to the review surface. The Find Entry
        # retains Tk's normal text-selection behavior.
        self.tree.bind("<Control-a>", self._select_all_from_key)

        detail_frame = ttk.Frame(review, padding=(0, 8, 0, 0))
        review.add(detail_frame, weight=2)
        ttk.Label(
            detail_frame,
            text="Reviewed effect",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        detail_scrollbar = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL)
        self.detail = tk.Text(
            detail_frame,
            height=7,
            wrap=tk.WORD,
            padx=8,
            pady=6,
            yscrollcommand=detail_scrollbar.set,
        )
        detail_scrollbar.configure(command=self.detail.yview)
        detail_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(4, 0))
        self.detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(4, 0))
        self.detail.configure(state=tk.DISABLED)

        self.status_var = tk.StringVar(
            value=(
                "Select Actions, then move them elsewhere or remove direct members "
                "from this submenu."
                if self.current_path
                else "Select Actions, then move them into a submenu. Active Actions "
                f"of this type cannot be removed from {self.root_label} while "
                "they remain Active."
            )
        )
        self.status_label = ttk.Label(
            outer,
            textvariable=self.status_var,
            style="Status.TLabel",
            wraplength=740,
            justify=tk.LEFT,
        )
        self.status_label.grid(row=6, column=0, sticky=tk.EW, pady=(7, 0))

        self.footer = ttk.Frame(outer)
        self.footer.grid(row=7, column=0, sticky=tk.EW, pady=(8, 0))
        self.move_button = ttk.Button(
            self.footer,
            text="Move 0 Actions",
            command=self.commit_reviewed_plan,
            state=tk.DISABLED,
            style="Accent.TButton",
        )
        self.move_button.pack(side=tk.LEFT)
        ttk.Button(self.footer, text="Close", command=self.close).pack(side=tk.RIGHT)

        self.search_var.trace_add("write", lambda *_args: self._render_actions())
        self._render_actions()
        self._render_review()
        self.window.transient(parent.winfo_toplevel())
        self.window.lift()
        self.window.after_idle(self.search_entry.focus_set)

    def close(self) -> None:
        self.window.destroy()

    def _focus_search(self, _event: tk.Event | None = None) -> str:
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, tk.END)
        return "break"

    def _current_branch_text(self) -> str:
        return "Current branch: " + self._display_path(self.current_path)

    def _display_path(self, path: tuple[str, ...]) -> str:
        if not path:
            return f"{self.root_label} menu root"
        return " > ".join((self.root_label, *path))

    def _rebuild_submenu_tasks_menu(self) -> None:
        self.submenu_tasks_menu.delete(0, tk.END)
        self.submenu_tasks_menu.add_command(
            label=(
                "New submenu here…"
                if self.current_path
                else "New submenu…"
            ),
            command=self.create_submenu,
        )
        if self.current_path:
            self.submenu_tasks_menu.add_separator()
            self.submenu_tasks_menu.add_command(
                label="Rename this submenu…",
                command=self.rename_submenu,
            )
            self.submenu_tasks_menu.add_command(
                label="Move this submenu…",
                command=self.move_submenu,
            )
            self.submenu_tasks_menu.add_command(
                label="Remove this submenu…",
                command=self.remove_submenu,
            )
        self._update_submenu_task_state()

    def _update_submenu_task_state(self) -> None:
        disabled = self.submitting or self.review_stale or self.effects_unknown
        state = tk.DISABLED if disabled else tk.NORMAL
        try:
            end = self.submenu_tasks_menu.index(tk.END)
            if end is not None:
                for index in range(end + 1):
                    if self.submenu_tasks_menu.type(index) != "separator":
                        self.submenu_tasks_menu.entryconfigure(index, state=state)
            if len(self.current_path) >= MAX_QUICK_ACTION_PATH_LEVELS:
                self.submenu_tasks_menu.entryconfigure(0, state=tk.DISABLED)
        except tk.TclError:
            pass
        self.submenu_tasks_button.configure(state=state)

    def _sync_remove_selected_button(self) -> None:
        self.remove_selected_button.pack_forget()
        if self.current_path:
            self.remove_selected_button.pack(
                side=tk.LEFT,
                padx=(6, 0),
                before=self.destination_label,
            )

    def _active_selected_action_ids(self) -> tuple[str, ...]:
        return tuple(
            action.id
            for action in self.candidates
            if action.id in self.selected_action_ids
            and action.state == ACTIVE_STATE
        )

    def create_submenu(self) -> None:
        if self.submitting or self.review_stale or self.effects_unknown:
            return
        if len(self.current_path) >= MAX_QUICK_ACTION_PATH_LEVELS:
            messagebox.showinfo(
                "Maximum menu depth",
                f"Automatic Quick menus support at most "
                f"{MAX_QUICK_ACTION_PATH_LEVELS} submenu levels.",
                parent=self.window,
            )
            return
        if not self._active_selected_action_ids():
            messagebox.showinfo(
                "Select an Active Action",
                "Select at least one Active Action first. An automatic submenu "
                "exists only while an Active Action is placed in it.",
                parent=self.window,
            )
            self.status_var.set(
                "Select at least one Active Action, then choose Submenu tasks → "
                "New submenu."
            )
            self.tree.focus_set()
            return
        QuickMenuSubmenuNameDialog(
            self.window,
            root_label=self.root_label,
            parent_path=self.current_path,
            on_submit=self._new_submenu_named,
            title="New automatic submenu",
            submit_label="Review new submenu",
            context_label="Create under",
        )

    def _new_submenu_named(self, name: str) -> None:
        destination = (*self.current_path, name)
        if self._active_branch_exists(destination):
            messagebox.showinfo(
                "Submenu already exists",
                f'"{self._display_path(destination)}" already exists. Use '
                "Choose destination to place Actions there.",
                parent=self.window,
            )
            return
        self.review_intent = CREATE_SUBMENU_INTENT
        self._assignment_destination_chosen(destination)

    def _active_branch_exists(self, path: tuple[str, ...]) -> bool:
        keys = tuple(level.casefold() for level in path)
        return any(
            action.state == ACTIVE_STATE
            and len(action.quick_action_path) >= len(path)
            and tuple(
                level.casefold()
                for level in action.quick_action_path[: len(path)]
            )
            == keys
            for action in self.candidates
        )

    def rename_submenu(self) -> None:
        if (
            not self.current_path
            or self.submitting
            or self.review_stale
            or self.effects_unknown
        ):
            return
        QuickMenuSubmenuNameDialog(
            self.window,
            root_label=self.root_label,
            parent_path=self.current_path[:-1],
            on_submit=self._submenu_renamed,
            title="Rename automatic submenu",
            submit_label="Review rename",
            context_label="Rename in",
            initial_name=self.current_path[-1],
        )

    def _submenu_renamed(self, name: str) -> None:
        self._plan_branch_change(
            (*self.current_path[:-1], name),
            intent=RENAME_SUBMENU_INTENT,
        )

    def move_submenu(self) -> None:
        if (
            not self.current_path
            or self.submitting
            or self.review_stale
            or self.effects_unknown
        ):
            return
        QuickMenuPathDialog(
            self.window,
            action_type=self.action_type,
            actions=self.actions,
            current_path=self.current_path[:-1],
            on_select=self._submenu_parent_chosen,
            dialog_title=f"Move {self.current_path[-1]}",
            instructions=(
                f'Choose the new parent for "{self.current_path[-1]}". Its name, '
                "nested submenus, and Action placements are preserved."
            ),
            use_label="Use this parent",
        )

    def _submenu_parent_chosen(self, parent_path: tuple[str, ...]) -> None:
        self._plan_branch_change(
            (*parent_path, self.current_path[-1]),
            intent=MOVE_SUBMENU_INTENT,
        )

    def remove_submenu(self) -> None:
        if (
            not self.current_path
            or self.submitting
            or self.review_stale
            or self.effects_unknown
        ):
            return
        self._plan_branch_change(
            self.current_path[:-1],
            intent=REMOVE_SUBMENU_INTENT,
        )

    def _storage_label(self, action_id: str) -> str:
        return (
            "My configuration"
            if action_id.casefold() in self.local_action_ids
            else "Built-in"
        )

    def _matches_search(self, action: Action, terms: tuple[str, ...]) -> bool:
        searchable = " ".join(
            (
                action.title,
                action.id,
                action.value,
                action.state,
                self._storage_label(action.id),
                self._display_path(action.quick_action_path),
            )
        ).casefold()
        return all(term in searchable for term in terms)

    def _render_actions(self) -> None:
        focused_id = self.action_id_by_iid.get(self.tree.focus())
        terms = tuple(
            part.casefold() for part in self.search_var.get().split() if part.strip()
        )
        shown = tuple(
            action for action in self.candidates if self._matches_search(action, terms)
        )
        self.visible_action_ids = tuple(action.id for action in shown)
        self.tree.delete(*self.tree.get_children())
        self.action_id_by_iid.clear()
        focus_iid = ""
        for index, action in enumerate(shown):
            iid = f"action-{index}"
            self.action_id_by_iid[iid] = action.id
            self.tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    "[x]" if action.id in self.selected_action_ids else "[ ]",
                    f"{action.title} [{action.id}]",
                    action.state,
                    self._storage_label(action.id),
                    self._display_path(action.quick_action_path),
                ),
            )
            if action.id == focused_id:
                focus_iid = iid
        if focus_iid:
            self.tree.focus(focus_iid)
            self.tree.selection_set(focus_iid)
        shown_count = len(shown)
        selected_count = len(self.selected_action_ids)
        self.count_var.set(f"{shown_count} shown · {selected_count} selected")
        self._update_commit_state()

    def _tree_clicked(self, event: tk.Event) -> None:
        if self.submitting or self.review_stale or self.effects_unknown:
            return
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        iid = self.tree.identify_row(event.y)
        if iid and self.tree.identify_column(event.x) == "#1":
            self._toggle_action_id(self.action_id_by_iid[iid])

    def _toggle_from_key(self, _event: tk.Event | None = None) -> str:
        if self.submitting or self.review_stale or self.effects_unknown:
            return "break"
        action_id = self.action_id_by_iid.get(self.tree.focus())
        if action_id:
            self._toggle_action_id(action_id)
        return "break"

    def _toggle_action_id(self, action_id: str) -> None:
        if action_id not in self.action_by_id:
            return
        if action_id in self.selected_action_ids:
            self.selected_action_ids.remove(action_id)
        else:
            self.selected_action_ids.add(action_id)
        self._selection_changed()

    def _select_all_from_key(self, _event: tk.Event | None = None) -> str:
        self.select_all_shown()
        return "break"

    def select_all_shown(self) -> None:
        if self.submitting or self.review_stale or self.effects_unknown:
            return
        self.selected_action_ids.update(self.visible_action_ids)
        self._selection_changed()

    def clear_selection(self) -> None:
        if self.submitting or self.review_stale or self.effects_unknown:
            return
        self.selected_action_ids.clear()
        self._selection_changed()

    def _selection_changed(self) -> None:
        if self.plan is not None and self.plan.operation == MOVE_BRANCH_OPERATION:
            self.destination_path = None
            self.review_intent = MOVE_ACTIONS_INTENT
        self.plan = None
        self._render_actions()
        self._plan_assignment_if_ready()

    def choose_assignment_destination(self) -> None:
        if self.submitting or self.review_stale or self.effects_unknown:
            return
        self.review_intent = MOVE_ACTIONS_INTENT
        QuickMenuPathDialog(
            self.window,
            action_type=self.action_type,
            actions=self.actions,
            current_path=self.destination_path or self.current_path,
            on_select=self._assignment_destination_chosen,
        )

    def review_action_removal(self, action_id: str) -> None:
        """Preselect one exact direct Action and review promotion to its parent."""

        action = self.action_by_id.get(action_id)
        if action is None or action.state != ACTIVE_STATE:
            messagebox.showerror(
                "Action placement changed",
                "That Active Action is no longer available in this automatic menu.",
                parent=self.window,
            )
            self.on_refresh()
            return
        if not self.current_path or not _same_path(
            action.quick_action_path,
            self.current_path,
        ):
            messagebox.showerror(
                "Action placement changed",
                "That Action is no longer directly in this submenu. Close and "
                "reopen the current menu before changing it.",
                parent=self.window,
            )
            self.on_refresh()
            return
        self.selected_action_ids = {action.id}
        self._render_actions()
        self.remove_selected_from_current_submenu()

    def remove_selected_from_current_submenu(self) -> None:
        """Review moving selected direct members exactly one level upward."""

        if self.submitting or self.review_stale or self.effects_unknown:
            return
        if not self.current_path:
            messagebox.showinfo(
                f"{self.root_label} menu root is required",
                f"Every Active {self.root_label} Action appears in this automatic "
                "menu. Move it into a submenu, or delete the Action to remove it "
                "from runtime.",
                parent=self.window,
            )
            return
        if not self.selected_action_ids:
            messagebox.showinfo(
                "Select an Action",
                "Select one or more Actions directly in this submenu first.",
                parent=self.window,
            )
            self.tree.focus_set()
            return
        selected = tuple(
            action
            for action in self.candidates
            if action.id in self.selected_action_ids
        )
        indirect = tuple(
            action
            for action in selected
            if not _same_path(action.quick_action_path, self.current_path)
        )
        if indirect:
            messagebox.showinfo(
                "Select direct submenu members",
                "Remove from this submenu moves Actions exactly one level up. "
                "Clear the selection, then select only Actions whose current "
                f"placement is {self._display_path(self.current_path)}.",
                parent=self.window,
            )
            self.status_var.set(
                "No change was applied. Select only direct members of the current "
                "submenu."
            )
            return
        self.review_intent = REMOVE_ACTIONS_INTENT
        self._assignment_destination_chosen(self.current_path[:-1])

    def _assignment_destination_chosen(self, path: tuple[str, ...]) -> None:
        self.destination_path = tuple(path)
        self.destination_var.set(f"Destination: {self._display_path(self.destination_path)}")
        self.plan = None
        self._plan_assignment_if_ready()

    def _plan_assignment_if_ready(self) -> None:
        if not self.selected_action_ids or self.destination_path is None:
            self._render_review()
            return
        ordered_ids = tuple(
            action.id
            for action in self.candidates
            if action.id in self.selected_action_ids
        )
        if self.review_intent == REMOVE_ACTIONS_INTENT:
            indirect = tuple(
                action
                for action in self.candidates
                if action.id in self.selected_action_ids
                and not _same_path(action.quick_action_path, self.current_path)
            )
            if indirect:
                self.plan = None
                self.status_var.set(
                    "Remove from this submenu accepts only its direct members. "
                    "Clear the other selections or choose Move selected instead."
                )
                self._render_review()
                return
        try:
            reviewed = plan_quick_menu_assignment(
                ordered_ids,
                self.destination_path,
                shared_actions_path=self.shared_actions_path,
                local_actions_path=self.local_actions_path,
            )
            self._accept_plan_type(reviewed)
            if self.review_intent == REMOVE_ACTIONS_INTENT:
                self._accept_remove_plan(reviewed, ordered_ids)
            self.plan = reviewed
        except (QuickMenuOrganizationError, OSError) as exc:
            self.plan = None
            messagebox.showerror(
                "Quick-menu move could not be reviewed",
                str(exc),
                parent=self.window,
            )
            self.status_var.set(
                (
                    "Stored Actions changed. Close and reopen this organizer to "
                    "build a current review."
                    if self.review_stale
                    else "No change was applied. Correct the selection or "
                    "destination and review again."
                )
            )
        self._render_review()

    def choose_branch_destination(self) -> None:
        """Compatibility route for the former combined branch command."""

        self.move_submenu()

    def _branch_destination_chosen(self, parent_path: tuple[str, ...]) -> None:
        """Compatibility callback retaining the submenu name during a move."""

        self._submenu_parent_chosen(parent_path)

    def _plan_branch_change(
        self,
        destination_path: tuple[str, ...],
        *,
        intent: str,
    ) -> None:
        self.review_intent = intent
        self.destination_path = tuple(destination_path)
        self.destination_var.set(f"Destination: {self._display_path(self.destination_path)}")
        self.selected_action_ids.clear()
        self._render_actions()
        try:
            self.plan = plan_quick_menu_branch_move(
                self.action_type,
                self.current_path,
                self.destination_path,
                shared_actions_path=self.shared_actions_path,
                local_actions_path=self.local_actions_path,
            )
        except (QuickMenuOrganizationError, OSError) as exc:
            self.plan = None
            messagebox.showerror(
                "Quick-menu branch move could not be reviewed",
                str(exc),
                parent=self.window,
            )
            self.status_var.set(
                "No change was applied. Choose a different branch destination and review again."
            )
        self._render_review()

    def _accept_plan_type(self, plan: QuickMenuOrganizationPlan) -> None:
        if plan.action_type == self.action_type:
            return
        self.review_stale = True
        self.selected_action_ids.clear()
        self._disable_mutation_controls()
        self.on_refresh()
        raise QuickMenuOrganizationError(
            "An Action changed automatic-menu type while this organizer was open."
        )

    def _accept_remove_plan(
        self,
        plan: QuickMenuOrganizationPlan,
        expected_action_ids: tuple[str, ...],
    ) -> None:
        """Require the fresh plan to preserve the reviewed one-level meaning."""

        expected_keys = tuple(action_id.casefold() for action_id in expected_action_ids)
        matched_keys = tuple(action_id.casefold() for action_id in plan.matched_action_ids)
        change_keys = tuple(change.action_id.casefold() for change in plan.changes)
        expected_by_key = {
            action_id.casefold(): self.action_by_id[action_id]
            for action_id in expected_action_ids
        }
        valid = (
            plan.operation == ASSIGN_OPERATION
            and matched_keys == expected_keys
            and change_keys == expected_keys
            and _same_path(plan.destination_path, self.current_path[:-1])
            and all(
                change.action_type == self.action_type
                and change.state == expected_by_key[change.action_id.casefold()].state
                and _same_path(change.before_path, self.current_path)
                and _same_path(change.after_path, self.current_path[:-1])
                for change in plan.changes
            )
        )
        if valid:
            return
        self.review_stale = True
        self.selected_action_ids.clear()
        self._disable_mutation_controls()
        self.on_refresh()
        raise QuickMenuOrganizationError(
            "An Action moved or changed lifecycle state while this submenu "
            "removal was being reviewed. Close and reopen the organizer."
        )

    def _render_review(self) -> None:
        plan = self.plan
        if self.effects_unknown:
            text = (
                "The saved Action-file effects are unknown. Do not retry from this "
                "window; inspect the latest backup and Diagnostics first."
            )
        elif self.review_stale:
            text = (
                "Stored Actions changed after this organizer opened. Close it and "
                "open it again to build a current review."
            )
        elif plan is None:
            if not self.selected_action_ids:
                text = "No Actions selected. Select one or more Actions to move."
            elif self.destination_path is None:
                text = "Choose a destination to calculate the exact effect."
            else:
                text = "The Quick-menu move has not been reviewed."
        else:
            lines = self._review_lines(plan)
            text = "\n".join(lines)
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        self.detail.insert("1.0", text)
        self.detail.configure(state=tk.DISABLED)
        self._update_commit_state()

    def _review_lines(self, plan: QuickMenuOrganizationPlan) -> list[str]:
        affected = len(plan.affected_action_ids)
        if plan.operation == MOVE_BRANCH_OPERATION:
            if self.review_intent == REMOVE_SUBMENU_INTENT:
                child_names = {
                    change.before_path[len(plan.source_prefix)]
                    for change in plan.changes
                    if len(change.before_path) > len(plan.source_prefix)
                }
                lines = [
                    f"Remove submenu: {self._display_path(plan.source_prefix)}",
                    f"Promote contents to: {self._display_path(plan.destination_path)}",
                    (
                        f"{_action_count(affected)} will keep their saved records and "
                        "move up one level."
                    ),
                    (
                        f"{len(child_names)} child submenu"
                        f"{'s' if len(child_names) != 1 else ''} will move up "
                        + (
                            "and matching destination branches will merge."
                            if plan.destination_merged
                            else "intact."
                        )
                    ),
                ]
            elif self.review_intent == RENAME_SUBMENU_INTENT:
                lines = [
                    f"Rename submenu: {self._display_path(plan.source_prefix)}",
                    f"New name and path: {self._display_path(plan.destination_path)}",
                    (
                        f"{_action_count(affected)} will retain their relative nested "
                        "locations."
                    ),
                ]
            else:
                lines = [
                    f"Move submenu: {self._display_path(plan.source_prefix)}",
                    f"New path: {self._display_path(plan.destination_path)}",
                    (
                        f"{_action_count(affected)} will retain their relative nested "
                        "locations."
                    ),
                ]
        else:
            already_there = len(plan.matched_action_ids) - affected
            if self.review_intent == REMOVE_ACTIONS_INTENT:
                lines = [
                    f"Remove from submenu: {self._display_path(self.current_path)}",
                    f"Move to parent: {self._display_path(plan.destination_path)}",
                    (
                        f"{_action_count(affected)} will remain saved with their "
                        "external targets unchanged."
                    ),
                    (
                        f"Every selected Action still appears in {self.root_label} "
                        "while it remains saved."
                    ),
                ]
            elif self.review_intent == CREATE_SUBMENU_INTENT:
                lines = [
                    f"Create submenu: {self._display_path(plan.destination_path)}",
                    (
                        f"{_action_count(affected)} will move into it; "
                        f"{_action_count(already_there)} already use that path."
                    ),
                    (
                        "The submenu is derived from Active Action placements; it is "
                        "not an independent empty menu record."
                    ),
                ]
            else:
                lines = [
                    f"Destination: {self._display_path(plan.destination_path)}",
                    (
                        f"{_action_count(affected)} will move; "
                        f"{_action_count(already_there)} already at the destination."
                    ),
                ]
        lines.extend(
            (
                (
                    "Exact impact: "
                    f"Built-in {plan.shared_action_count} · "
                    f"My configuration {plan.local_action_count} · "
                    f"Active {plan.active_action_count}"
                ),
                f"Action files to write: {plan.files_to_write}",
            )
        )
        if plan.shared_action_count:
            lines.append(
                "Built-in changes are tracked by Git and can reach other computers "
                "after commit, push, and pull."
            )
        if plan.destination_merged:
            lines.append("The destination already exists; placements will merge there.")
        if plan.canonicalization_applied:
            lines.append("Existing branch capitalization was retained where it matched.")
        if plan.changes:
            lines.extend(("", "Placement changes:"))
            for change in plan.changes:
                storage = (
                    "My configuration"
                    if change.storage == "local"
                    else "Built-in"
                )
                lines.append(
                    f"{change.action.title} [{change.action_id}; "
                    f"{change.state}, {storage}]: "
                    f"{self._display_path(change.before_path)} → "
                    f"{self._display_path(change.after_path)}"
                )
        else:
            lines.extend(("", "Nothing will change; every placement already matches."))
        lines.extend(
            (
                "",
                "No Action, folder, password, prompt, or other external target is "
                "deleted. Automatic submenus are derived from these placements, so "
                "an empty source submenu disappears automatically.",
            )
        )
        return lines

    def _update_commit_state(self) -> None:
        count = len(self.plan.affected_action_ids) if self.plan is not None else 0
        labels = {
            REMOVE_ACTIONS_INTENT: f"Remove {_action_count(count)} from submenu",
            CREATE_SUBMENU_INTENT: f"Create submenu with {_action_count(count)}",
            RENAME_SUBMENU_INTENT: f"Rename submenu for {_action_count(count)}",
            MOVE_SUBMENU_INTENT: f"Move submenu with {_action_count(count)}",
            REMOVE_SUBMENU_INTENT: f"Remove submenu; keep {_action_count(count)}",
        }
        self.move_button.configure(
            text=labels.get(self.review_intent, f"Move {_action_count(count)}"),
            state=(
                tk.NORMAL
                if count
                and not self.submitting
                and not self.review_stale
                and not self.effects_unknown
                else tk.DISABLED
            ),
        )
        self.remove_selected_button.configure(
            state=(
                tk.NORMAL
                if self.current_path
                and not self.submitting
                and not self.review_stale
                and not self.effects_unknown
                else tk.DISABLED
            )
        )
        self._update_submenu_task_state()

    def commit_reviewed_plan(self) -> None:
        if (
            self.submitting
            or self.plan is None
            or not self.plan.affected_action_ids
            or self.review_stale
            or self.effects_unknown
        ):
            return
        reviewed = self.plan
        self.submitting = True
        self._update_commit_state()
        try:
            result = commit_quick_menu_organization(reviewed)
        except (QuickMenuOrganizationError, OSError) as exc:
            self.submitting = False
            self._handle_commit_error(exc)
            return

        self.submitting = False
        self._apply_success(reviewed, result)

    def _handle_commit_error(self, exc: Exception) -> None:
        rollback_completed = (
            exc.rollback_completed
            if isinstance(exc, QuickMenuOrganizationError)
            else None
        )
        self.plan = None
        if rollback_completed is False:
            self.effects_unknown = True
            self.selected_action_ids.clear()
            self._disable_mutation_controls()
            self.on_refresh()
            messagebox.showerror(
                "Actions may have changed",
                str(exc),
                parent=self.window,
            )
            self.status_var.set(
                "Actions may have changed. Do not retry here. Inspect the latest "
                "backup and Diagnostics, then close and reopen this organizer after "
                "verifying the saved configuration."
            )
        elif rollback_completed is True:
            self.destination_path = None
            self.destination_var.set("Destination: Not chosen")
            messagebox.showerror(
                "Actions were not moved",
                str(exc),
                parent=self.window,
            )
            self.status_var.set(
                "No Actions were moved; the attempted Action-file changes were "
                "restored. Choose a destination and review again."
            )
        else:
            self.review_stale = True
            self.selected_action_ids.clear()
            self._disable_mutation_controls()
            messagebox.showerror(
                "Quick-menu review is out of date",
                str(exc),
                parent=self.window,
            )
            self.status_var.set(
                "Stored Actions changed after review. Close and reopen this organizer "
                "to build a current review before moving anything."
            )
            self.on_refresh()
        self._render_actions()
        self._render_review()

    def _disable_mutation_controls(self) -> None:
        for button in (
            self.select_all_button,
            self.clear_button,
            self.destination_button,
            self.remove_selected_button,
            self.submenu_tasks_button,
            self.branch_button,
            self.move_button,
        ):
            if button is not None:
                button.configure(state=tk.DISABLED)

    def _apply_success(
        self,
        plan: QuickMenuOrganizationPlan,
        result: QuickMenuOrganizationResult,
    ) -> None:
        updated_by_id = {action.id: action for action in result.updated_actions}
        self.actions = tuple(
            updated_by_id.get(action.id, action) for action in self.actions
        )
        self.candidates = tuple(
            action
            for action in self.actions
            if action.type == self.action_type and action.state == ACTIVE_STATE
        )
        self.action_by_id = {action.id: action for action in self.candidates}
        applied_intent = self.review_intent
        previous_path = self.current_path
        if (
            plan.operation == MOVE_BRANCH_OPERATION
            or applied_intent == CREATE_SUBMENU_INTENT
        ):
            self.current_path = plan.destination_path
        elif self.current_path and not self._active_branch_exists(self.current_path):
            while self.current_path and not self._active_branch_exists(
                self.current_path
            ):
                self.current_path = self.current_path[:-1]
        branch_changed = self.current_path != previous_path
        if branch_changed or plan.operation == MOVE_BRANCH_OPERATION:
            self.branch_var.set(self._current_branch_text())
            self.branch_button = (
                self.submenu_tasks_button if self.current_path else None
            )
            self._rebuild_submenu_tasks_menu()
            self._sync_remove_selected_button()
        self.selected_action_ids.clear()
        self.destination_path = None
        self.destination_var.set("Destination: Not chosen")
        self.plan = None
        self.review_intent = MOVE_ACTIONS_INTENT
        self._render_actions()
        self._render_review()
        outcome = {
            REMOVE_ACTIONS_INTENT: "Removed from the submenu and kept",
            CREATE_SUBMENU_INTENT: "Created the submenu by moving",
            RENAME_SUBMENU_INTENT: "Renamed the submenu for",
            MOVE_SUBMENU_INTENT: "Moved the submenu with",
            REMOVE_SUBMENU_INTENT: "Removed the submenu and kept",
        }.get(applied_intent, "Moved")
        self.status_var.set(
            f"{outcome} {_action_count(len(result.affected_action_ids))}: "
            f"Built-in {result.shared_action_count} · "
            f"My configuration {result.local_action_count} · "
            f"Active {result.active_action_count}. "
            f"Wrote {_file_count(result.files_written)}. Empty derived submenus "
            "disappeared automatically."
        )
        if (
            branch_changed
            and plan.operation == ASSIGN_OPERATION
            and applied_intent != CREATE_SUBMENU_INTENT
        ):
            self.status_var.set(
                self.status_var.get()
                + f" Showing {self._display_path(self.current_path)} because the "
                "previous branch no longer has an Active Action."
            )
        self.on_change()


def _action_count(count: int) -> str:
    return f"{count} Action{'s' if count != 1 else ''}"


def _file_count(count: int) -> str:
    return f"{count} Action file{'s' if count != 1 else ''}"


def _same_path(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    return tuple(value.casefold() for value in left) == tuple(
        value.casefold() for value in right
    )
