"""Attended one-stage deletion workflow for personal Actions.

The window reviews exact Action records, saved-reference cleanup, and sequence
dependencies before one effect-labelled deletion. External targets are never
changed and no Action is executed.
"""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Iterable

from .action_bulk_lifecycle import (
    BulkActionLifecycleCandidate,
    BulkActionLifecycleError,
    BulkActionLifecyclePaths,
    BulkActionLifecyclePlan,
    commit_bulk_action_deletion,
    eligible_personal_actions_for_deletion,
    plan_bulk_action_deletion,
)
from .action_deletion import ActionDeletionReport
from .action_types import ACTION_TYPES
from .actions import Action, ActionError, action_matches_search, load_combined_stored_actions
from .window_geometry import configure_standard_window


class ActionBulkLifecycleWindow:
    """Review and permanently delete one or more personal Actions."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        actions: Iterable[Action],
        local_action_ids: Iterable[str],
        local_actions_path: Path,
        shared_actions_path: Path,
        shared_contexts_path: Path,
        local_contexts_path: Path,
        shared_command_surface_path: Path,
        local_command_surface_path: Path,
        palette_path: Path,
        on_change: Callable[[], None],
    ) -> None:
        self.actions = tuple(actions)
        self.local_action_ids = frozenset(local_action_ids)
        self.paths = BulkActionLifecyclePaths(
            shared_actions_path=Path(shared_actions_path),
            local_actions_path=Path(local_actions_path),
            shared_contexts_path=Path(shared_contexts_path),
            local_contexts_path=Path(local_contexts_path),
            shared_command_surface_path=Path(shared_command_surface_path),
            local_command_surface_path=Path(local_command_surface_path),
            palette_path=Path(palette_path),
        )
        self.on_change = on_change
        self.eligible_actions = self._eligible()
        self.selected_action_ids: set[str] = set()
        self.plan: BulkActionLifecyclePlan | None = None
        self.submitting = False
        self._transition_message = ""

        self.window = tk.Toplevel(parent)
        self.window.title("Delete personal Actions")
        configure_standard_window(self.window, parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.bind("<Control-f>", self._focus_find)
        self.window.bind("<Control-a>", self._select_all_from_key)
        self.window.bind("<F5>", self._refresh_from_key)

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        ttk.Label(outer, text="Delete personal Actions", style="Title.TLabel").grid(
            row=0,
            column=0,
            sticky=tk.W,
        )
        self.intro_label = ttk.Label(
            outer,
            text=(
                "Select personal Actions and review exactly what will be removed. "
                "Deletion removes the saved Action records and their placements. "
                "External targets are never changed."
            ),
            style="Muted.TLabel",
            wraplength=740,
            justify=tk.LEFT,
        )
        self.intro_label.grid(row=1, column=0, sticky=tk.EW, pady=(2, 8))

        filter_row = ttk.Frame(outer)
        filter_row.grid(row=2, column=0, sticky=tk.EW, pady=(0, 7))
        ttk.Label(filter_row, text="Find").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        self.filter_entry = ttk.Entry(filter_row, textvariable=self.filter_var)
        self.filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 8))
        self.select_all_button = ttk.Button(
            filter_row,
            text="Select all shown",
            command=self.select_all_shown,
            style="Compact.TButton",
        )
        self.select_all_button.pack(side=tk.LEFT)
        self.clear_button = ttk.Button(
            filter_row,
            text="Clear selection",
            command=self.clear_selection,
            style="Compact.TButton",
        )
        self.clear_button.pack(side=tk.LEFT, padx=(6, 0))
        self.shown_var = tk.StringVar()
        ttk.Label(
            filter_row,
            textvariable=self.shown_var,
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT, padx=(8, 0))

        review = ttk.Panedwindow(outer, orient=tk.VERTICAL)
        review.grid(row=3, column=0, sticky=tk.NSEW)

        table_frame = ttk.Frame(review)
        review.add(table_frame, weight=3)
        vertical_scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL)
        horizontal_scrollbar = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL)
        self.tree = ttk.Treeview(
            table_frame,
            columns=(
                "use",
                "action",
                "type",
                "availability",
                "dependencies",
                "status",
            ),
            show="headings",
            selectmode="browse",
            yscrollcommand=vertical_scrollbar.set,
            xscrollcommand=horizontal_scrollbar.set,
        )
        vertical_scrollbar.configure(command=self.tree.yview)
        horizontal_scrollbar.configure(command=self.tree.xview)
        vertical_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        horizontal_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for column, label, width, stretch, anchor in (
            ("use", "Delete", 62, False, tk.CENTER),
            ("action", "Action", 190, True, tk.W),
            ("type", "Type", 125, False, tk.W),
            ("availability", "Availability", 110, False, tk.W),
            ("dependencies", "Dependencies", 195, True, tk.W),
            ("status", "Status", 92, False, tk.W),
        ):
            self.tree.heading(column, text=label)
            self.tree.column(
                column,
                width=width,
                minwidth=width,
                stretch=stretch,
                anchor=anchor,
            )
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_detail())
        self.tree.bind("<ButtonRelease-1>", self._tree_clicked)
        self.tree.bind("<space>", self._toggle_from_key)

        detail_frame = ttk.Frame(review, padding=(0, 7, 0, 0))
        review.add(detail_frame, weight=2)
        ttk.Label(
            detail_frame,
            text="Selected Action and deletion impact",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        detail_scrollbar = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL)
        self.detail = tk.Text(
            detail_frame,
            height=6,
            wrap=tk.WORD,
            padx=8,
            pady=6,
            yscrollcommand=detail_scrollbar.set,
        )
        detail_scrollbar.configure(command=self.detail.yview)
        detail_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(4, 0))
        self.detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(4, 0))
        self.detail.configure(state=tk.DISABLED)

        self.status_var = tk.StringVar()
        ttk.Label(
            outer,
            textvariable=self.status_var,
            style="Status.TLabel",
            wraplength=740,
            justify=tk.LEFT,
        ).grid(row=4, column=0, sticky=tk.EW, pady=(7, 0))

        footer = ttk.Frame(outer)
        footer.grid(row=5, column=0, sticky=tk.EW, pady=(8, 0))
        self.delete_button = ttk.Button(
            footer,
            command=self.commit_selected,
            state=tk.DISABLED,
            style="Danger.TButton",
        )
        self.delete_button.pack(side=tk.LEFT)
        self.close_button = ttk.Button(footer, text="Close", command=self.close)
        self.close_button.pack(side=tk.RIGHT)

        self.filter_var.trace_add("write", lambda *_args: self._render())
        self._render()
        self.window.transient(parent)
        self.window.lift()
        self.window.after_idle(self.filter_entry.focus_set)

    @property
    def commit_button(self) -> ttk.Button:
        """Return the window's single effect-labelled deletion button."""

        return self.delete_button

    def close(self) -> None:
        self.window.destroy()

    def _eligible(self) -> tuple[Action, ...]:
        return eligible_personal_actions_for_deletion(
            self.actions,
            self.local_action_ids,
        )

    def _load_current_actions(self) -> None:
        actions, local_ids = load_combined_stored_actions(
            self.paths.shared_actions_path,
            self.paths.local_actions_path,
            inspect_external_paths=False,
        )
        self.actions = tuple(actions)
        self.local_action_ids = frozenset(local_ids)
        self.eligible_actions = self._eligible()

    def _focus_find(self, _event: tk.Event | None = None) -> str:
        self.filter_entry.focus_set()
        self.filter_entry.selection_range(0, tk.END)
        return "break"

    def _select_all_from_key(self, event: tk.Event | None = None) -> str | None:
        source = getattr(event, "widget", None)
        if source is None:
            source = self.window.focus_get()
        if source is not self.tree:
            return None
        self.select_all_shown()
        return "break"

    def _refresh_from_key(self, _event: tk.Event | None = None) -> str:
        self.refresh_review()
        return "break"

    def _visible_actions(self) -> tuple[Action, ...]:
        query = self.filter_var.get()
        return tuple(
            action
            for action in self.eligible_actions
            if action_matches_search(action, query)
        )

    def _candidate_by_id(self) -> dict[str, BulkActionLifecycleCandidate]:
        if self.plan is None:
            return {}
        return {candidate.action_id: candidate for candidate in self.plan.candidates}

    def _candidate_for_iid(self, iid: str) -> BulkActionLifecycleCandidate | None:
        if not iid.startswith("action-"):
            return None
        return self._candidate_by_id().get(iid[7:])

    def _action_for_iid(self, iid: str) -> Action | None:
        if not iid.startswith("action-"):
            return None
        action_id = iid[7:]
        return next(
            (action for action in self.eligible_actions if action.id == action_id),
            None,
        )

    def _render(self) -> None:
        selected_iids = tuple(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        candidates = self._candidate_by_id()
        visible = self._visible_actions()
        selected_hidden = len(
            self.selected_action_ids - {item.id for item in visible}
        )
        self.shown_var.set(
            f"{len(visible)} shown"
            + (f" · {selected_hidden} selected hidden" if selected_hidden else "")
        )

        for action in visible:
            candidate = candidates.get(action.id)
            selected = action.id in self.selected_action_ids
            marker = "[x]" if selected else "[ ]"
            if candidate is not None:
                status = candidate.status
                dependencies = " ".join(candidate.messages) or "None"
            elif selected:
                status = "Review error"
                dependencies = "Refresh the review before continuing."
            else:
                status = "Not selected"
                dependencies = "Select to check"
            definition = ACTION_TYPES.get(action.type)
            type_label = definition.label if definition is not None else action.type
            self.tree.insert(
                "",
                tk.END,
                iid=f"action-{action.id}",
                values=(
                    marker,
                    action.title,
                    type_label,
                    _availability_label(action),
                    dependencies,
                    status,
                ),
            )

        retained = [iid for iid in selected_iids if self.tree.exists(iid)]
        if retained:
            self.tree.selection_set(retained[0])
            self.tree.focus(retained[0])
        elif self.tree.get_children():
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
        self._update_controls()
        self._show_detail()

    def _tree_clicked(self, event: tk.Event) -> str | None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return None
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        if self.tree.identify_column(event.x) == "#1":
            self._toggle_iids((iid,))
            return "break"
        self._show_detail()
        return None

    def _toggle_from_key(self, _event: tk.Event | None = None) -> str:
        selected = self.tree.selection()
        if not selected:
            focused = self.tree.focus()
            selected = (focused,) if focused else ()
        self._toggle_iids(selected)
        return "break"

    def _toggle_iids(self, iids: Iterable[str]) -> None:
        if self.submitting:
            return
        changed = False
        for iid in iids:
            action = self._action_for_iid(iid)
            if action is None:
                continue
            if action.id in self.selected_action_ids:
                self.selected_action_ids.remove(action.id)
            else:
                self.selected_action_ids.add(action.id)
            changed = True
        if changed:
            self._transition_message = ""
            self._replan()

    def select_all_shown(self) -> None:
        if self.submitting:
            return
        self.selected_action_ids.update(action.id for action in self._visible_actions())
        self._transition_message = ""
        self._replan()

    def clear_selection(self) -> None:
        if self.submitting:
            return
        self.selected_action_ids.clear()
        self.plan = None
        self._transition_message = ""
        self._render()

    def refresh_review(self) -> None:
        if self.submitting:
            return
        self._transition_message = ""
        try:
            self._load_current_actions()
        except (ActionError, OSError) as exc:
            messagebox.showerror(
                "Actions could not be refreshed",
                str(exc),
                parent=self.window,
            )
            return
        eligible_ids = {action.id for action in self.eligible_actions}
        self.selected_action_ids.intersection_update(eligible_ids)
        self._replan(show_error=False)

    def _replan(self, *, show_error: bool = True) -> str | None:
        if not self.selected_action_ids:
            self.plan = None
            self._render()
            return None
        review_error: str | None = None
        try:
            self.plan = plan_bulk_action_deletion(
                tuple(sorted(self.selected_action_ids)),
                paths=self.paths,
            )
        except (BulkActionLifecycleError, OSError) as exc:
            self.plan = None
            review_error = str(exc)
            if show_error:
                messagebox.showerror(
                    "Action deletion could not be reviewed",
                    review_error,
                    parent=self.window,
                )
        self._render()
        return review_error

    def _update_controls(self) -> None:
        count = len(self.selected_action_ids)
        can_commit = bool(
            count
            and self.plan is not None
            and self.plan.can_commit
            and not self.submitting
        )
        self.delete_button.configure(
            text=f"Delete {_action_count(count)} permanently",
            state=tk.NORMAL if can_commit else tk.DISABLED,
        )
        self.select_all_button.configure(
            state=(
                tk.DISABLED
                if self.submitting or not self._visible_actions()
                else tk.NORMAL
            )
        )
        self.clear_button.configure(
            state=tk.DISABLED if self.submitting or not count else tk.NORMAL
        )

        if self._transition_message:
            self.status_var.set(self._transition_message)
        elif not self.eligible_actions:
            self.status_var.set("No personal Actions are available to delete.")
        elif not count:
            self.status_var.set(
                f"{len(self.eligible_actions)} personal Action(s) available. "
                "Select the Actions to review."
            )
        elif self.plan is None:
            self.status_var.set("The selected Actions could not be reviewed.")
        elif self.plan.can_commit:
            self.status_var.set(
                f"{count} selected and ready. Review the exact impact before deleting."
            )
        else:
            blocked = sum(
                candidate.status == "Blocked" for candidate in self.plan.candidates
            )
            self.status_var.set(
                f"{count} selected · {blocked} blocked. "
                "Delete the dependent sequences too, or edit them first."
            )

    def _show_detail(self) -> None:
        selected = self.tree.selection()
        action = self._action_for_iid(selected[0]) if selected else None
        candidate = self._candidate_for_iid(selected[0]) if selected else None
        if action is None:
            self._set_detail(
                "Select an Action to inspect it. Use the checkbox column or Space "
                "to include it in the reviewed deletion."
            )
            return

        lines = [
            f"Action: {action.title}",
            f"Action ID: {action.id}",
            f"Availability: {_availability_label(action)}",
        ]
        if candidate is None:
            lines.extend(("", "Select this Action to review its exact effects."))
        else:
            lines.extend(("", f"Status: {candidate.status}"))
            if candidate.messages:
                lines.extend(candidate.messages)
            if candidate.blocking_sequence_ids:
                lines.extend(
                    (
                        "",
                        "Blocking sequence IDs: "
                        + ", ".join(candidate.blocking_sequence_ids),
                    )
                )

        if self.plan is not None:
            lines.extend(("", "Selected batch impact:"))
            lines.extend(_impact_lines(self.plan.impact))
        lines.extend(("", "External targets: not deleted or changed."))
        self._set_detail("\n".join(lines))

    def _set_detail(self, text: str) -> None:
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        self.detail.insert("1.0", text)
        self.detail.configure(state=tk.DISABLED)

    def commit_selected(self) -> None:
        if (
            self.submitting
            or self.plan is None
            or not self.selected_action_ids
            or not self.plan.can_commit
        ):
            return
        selected_count = len(self.selected_action_ids)
        self.submitting = True
        self._transition_message = ""
        self._update_controls()
        try:
            report = commit_bulk_action_deletion(self.plan)
        except (BulkActionLifecycleError, OSError) as exc:
            self.submitting = False
            try:
                self._load_current_actions()
                eligible_ids = {action.id for action in self.eligible_actions}
                self.selected_action_ids.intersection_update(eligible_ids)
                self._replan(show_error=False)
            except (ActionError, OSError):
                self.plan = None
                self._render()
            messagebox.showerror(
                "Action deletion did not complete as reviewed",
                str(exc),
                parent=self.window,
            )
            return

        self.submitting = False
        self.on_change()
        try:
            self._load_current_actions()
        except (ActionError, OSError) as exc:
            self.plan = None
            self.selected_action_ids.clear()
            self._render()
            messagebox.showerror(
                "Actions changed but the review could not refresh",
                str(exc),
                parent=self.window,
            )
            return

        self.selected_action_ids.clear()
        self.plan = None
        self._transition_message = (
            f"Deleted {_action_count(selected_count)} permanently. Removed "
            f"{report.references_removed} saved reference(s). External targets "
            "were unchanged."
        )
        self._render()


def _availability_label(action: Action) -> str:
    return "Legacy inactive" if action.state == "Archived" else "Active"


def _impact_lines(report: ActionDeletionReport) -> tuple[str, ...]:
    return (
        "Action records: deleted permanently.",
        f"Saved references removed: {report.references_removed}",
        f"Empty Quick-action items removed: {report.buttons_removed}",
        f"Configuration files changed: {report.files_changed}",
    )


def _action_count(count: int) -> str:
    return f"{count} Action" if count == 1 else f"{count} Actions"
