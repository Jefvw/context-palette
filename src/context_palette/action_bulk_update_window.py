"""Attended review window for updating personal Active Actions from Excel."""

from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Iterable

from .action_bulk_update import (
    BulkActionUpdateCandidate,
    BulkActionUpdateError,
    BulkActionUpdatePlan,
    commit_bulk_action_update,
    eligible_personal_actions_for_update,
    plan_bulk_action_update,
)
from .action_update_workbook import (
    ActionUpdateWorkbook,
    ActionUpdateWorkbookError,
    read_action_update_workbook,
    write_action_update_workbook,
)
from .actions import Action
from .window_geometry import configure_standard_window


_FIELD_LABELS = {
    "title": "Name",
    "name": "Name",
    "value": "Value",
    "contexts": "Contexts",
    "tags": "Tags",
    "description": "Description",
    "quick_action_path": "Quick menu",
    "quick_menu": "Quick menu",
    "arguments": "Arguments",
    "working_directory": "Working folder",
    "working_folder": "Working folder",
    "Name": "Name",
    "Value": "Value",
    "Contexts": "Contexts",
    "Tags": "Tags",
    "Description": "Description",
    "Quick menu": "Quick menu",
    "Arguments": "Arguments",
    "Working folder": "Working folder",
}


class ActionBulkUpdateWindow:
    """Export, review, and atomically update personal Active Actions."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        actions: Iterable[Action],
        local_action_ids: Iterable[str],
        local_context_names: Iterable[str],
        local_actions_path: Path,
        shared_actions_path: Path,
        shared_contexts_path: Path,
        local_contexts_path: Path,
        on_change: Callable[[], None],
        initial_workbook_path: Path | None = None,
    ) -> None:
        # Planning deliberately receives every stored Action (Active and
        # Archived). The explicit ID set is the personal-write boundary.
        self.actions = tuple(actions)
        self.local_action_ids = frozenset(local_action_ids)
        self.local_context_names = tuple(local_context_names)
        self.local_actions_path = Path(local_actions_path)
        self.shared_actions_path = Path(shared_actions_path)
        self.shared_contexts_path = Path(shared_contexts_path)
        self.local_contexts_path = Path(local_contexts_path)
        self.on_change = on_change

        self.workbook: ActionUpdateWorkbook | None = None
        self.source_path: Path | None = None
        self.plan: BulkActionUpdatePlan | None = None
        self.selected_row_numbers: set[int] = set()
        self.applied_row_numbers: set[int] = set()
        self.submitting = False
        self._review_is_stale = False
        self._effects_unknown = False

        self.window = tk.Toplevel(parent)
        self.window.title("Bulk update Actions")
        configure_standard_window(self.window, parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.bind("<Control-e>", self._export_from_key)
        self.window.bind("<Control-o>", self._choose_from_key)
        self.window.bind("<F5>", self._reload_from_key)

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        ttk.Label(outer, text="Bulk update Actions", style="Title.TLabel").pack(
            anchor=tk.W
        )
        self.intro_label = ttk.Label(
            outer,
            text=(
                "Export and update personal Active Actions only. Missing workbook rows "
                "are not deleted, and Action lifecycle remains unchanged. The workbook "
                "may contain private values and paths."
            ),
            style="Muted.TLabel",
            wraplength=740,
            justify=tk.LEFT,
        )
        self.intro_label.pack(anchor=tk.W, fill=tk.X, pady=(2, 8))

        toolbar = ttk.Frame(outer)
        toolbar.pack(fill=tk.X)
        self.export_button = ttk.Button(
            toolbar,
            text="Export fresh workbook…",
            command=self.export_fresh_workbook,
        )
        self.export_button.pack(side=tk.LEFT)
        self.choose_button = ttk.Button(
            toolbar,
            text="Choose updated workbook…",
            command=self.choose_workbook,
        )
        self.choose_button.pack(side=tk.LEFT, padx=(6, 0))
        self.reload_button = ttk.Button(
            toolbar,
            text="Reload",
            command=self.reload_workbook,
            state=tk.DISABLED,
        )
        self.reload_button.pack(side=tk.LEFT, padx=(6, 0))

        self.source_var = tk.StringVar(value="No workbook selected.")
        ttk.Label(
            outer,
            textvariable=self.source_var,
            style="Muted.TLabel",
            wraplength=740,
            justify=tk.LEFT,
        ).pack(fill=tk.X, pady=(5, 7))

        review = ttk.Panedwindow(outer, orient=tk.VERTICAL)
        review.pack(fill=tk.BOTH, expand=True)

        table_frame = ttk.Frame(review)
        review.add(table_frame, weight=3)
        vertical_scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL)
        horizontal_scrollbar = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL)
        self.tree = ttk.Treeview(
            table_frame,
            columns=("use", "row", "action", "changes", "status"),
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
            ("use", "Use", 46, False, tk.CENTER),
            ("row", "Row", 54, False, tk.E),
            ("action", "Action", 210, True, tk.W),
            ("changes", "Changes", 250, True, tk.W),
            ("status", "Status", 100, False, tk.W),
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

        detail_frame = ttk.Frame(review, padding=(0, 8, 0, 0))
        review.add(detail_frame, weight=2)
        ttk.Label(detail_frame, text="Selected change", style="Heading.TLabel").pack(
            anchor=tk.W
        )
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
        self._set_detail(
            "Export a fresh workbook, edit it in Excel, then choose or reload it. "
            "Only changed Ready rows are selected automatically."
        )

        footer = ttk.Frame(outer)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        self.update_button = ttk.Button(
            footer,
            text="Update 0 Actions",
            command=self.update_actions,
            state=tk.DISABLED,
            style="Accent.TButton",
        )
        self.update_button.pack(side=tk.LEFT)
        ttk.Button(footer, text="Close", command=self.close).pack(side=tk.RIGHT)
        self.status_var = tk.StringVar(
            value="Export a fresh workbook before editing personal Actions."
        )
        ttk.Label(
            outer,
            textvariable=self.status_var,
            style="Status.TLabel",
            wraplength=740,
            justify=tk.LEFT,
        ).pack(side=tk.BOTTOM, fill=tk.X, pady=(7, 0))

        self.window.transient(parent)
        self.window.lift()
        self.window.after_idle(self.export_button.focus_set)
        if initial_workbook_path is not None:
            initial_path = Path(initial_workbook_path)
            self.window.after_idle(lambda: self._load_workbook(initial_path))

    def close(self) -> None:
        self.window.destroy()

    def _export_from_key(self, _event: tk.Event | None = None) -> str:
        if not self.submitting and not self._effects_unknown:
            self.export_fresh_workbook()
        return "break"

    def _choose_from_key(self, _event: tk.Event | None = None) -> str:
        if not self.submitting and not self._effects_unknown:
            self.choose_workbook()
        return "break"

    def _reload_from_key(self, _event: tk.Event | None = None) -> str:
        if not self.submitting and not self._effects_unknown:
            self.reload_workbook()
        return "break"

    def _personal_active_actions(self) -> tuple[Action, ...]:
        return tuple(
            eligible_personal_actions_for_update(
                self.actions,
                self.local_action_ids,
            )
        )

    def export_fresh_workbook(self) -> None:
        if self.submitting or self._effects_unknown:
            return
        selected = filedialog.asksaveasfilename(
            parent=self.window,
            title="Export personal Active Actions",
            defaultextension=".xlsx",
            initialfile="Context Palette Action Updates.xlsx",
            filetypes=(("Excel workbooks", "*.xlsx"),),
        )
        if not selected:
            return
        target = Path(selected)
        try:
            saved = write_action_update_workbook(
                target,
                self._personal_active_actions(),
            )
        except (ActionUpdateWorkbookError, OSError) as exc:
            messagebox.showerror(
                "Action update workbook was not exported",
                str(exc),
                parent=self.window,
            )
            return
        self._load_workbook(saved)
        if self.plan is not None:
            self.status_var.set(
                "Fresh workbook exported. Edit and save it in Excel, then choose Reload."
            )

    def choose_workbook(self) -> None:
        if self.submitting or self._effects_unknown:
            return
        selected = filedialog.askopenfilename(
            parent=self.window,
            title="Choose updated Actions workbook",
            filetypes=(("Excel workbooks", "*.xlsx"),),
        )
        if selected:
            self._load_workbook(Path(selected))

    def reload_workbook(self) -> None:
        if self.submitting or self._effects_unknown or self.source_path is None:
            return
        self._load_workbook(self.source_path)

    def _load_workbook(self, path: Path) -> None:
        self.source_path = Path(path)
        try:
            workbook = read_action_update_workbook(
                self.source_path,
                self._personal_active_actions(),
            )
            plan = plan_bulk_action_update(
                workbook,
                self.actions,
                self.local_action_ids,
                self.local_context_names,
            )
        except (ActionUpdateWorkbookError, BulkActionUpdateError, OSError) as exc:
            self._clear_review_after_load_error()
            messagebox.showerror(
                "Action update workbook could not be reviewed",
                str(exc),
                parent=self.window,
            )
            self.status_var.set(
                "No Actions were updated. Correct this workbook and choose Reload, "
                "or export a fresh workbook."
            )
            return

        self.workbook = workbook
        self.plan = plan
        self.applied_row_numbers.clear()
        self._review_is_stale = False
        self.selected_row_numbers = {
            candidate.row_number
            for candidate in plan.candidates
            if candidate.status == "Ready" and candidate.selected_by_default
        }
        self.source_var.set(str(workbook.path))
        self.reload_button.configure(state=tk.NORMAL)
        self._render_candidates()
        self.status_var.set(self._plan_summary())
        children = self.tree.get_children()
        if children:
            first = children[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
            self._show_detail()
            self.tree.focus_set()

    def _clear_review_after_load_error(self) -> None:
        self.workbook = None
        self.plan = None
        self.selected_row_numbers.clear()
        self.applied_row_numbers.clear()
        self._review_is_stale = False
        self.source_var.set(
            str(self.source_path) if self.source_path else "No workbook selected."
        )
        self.reload_button.configure(
            state=tk.NORMAL if self.source_path is not None else tk.DISABLED
        )
        self.tree.delete(*self.tree.get_children())
        self._set_detail(
            "This workbook could not be reviewed. Correct it and choose Reload, "
            "or export a fresh workbook."
        )
        self._update_commit_state()

    def _plan_summary(self) -> str:
        if self.plan is None:
            return "No workbook has been reviewed."
        counts: dict[str, int] = {}
        for candidate in self.plan.candidates:
            counts[candidate.status] = counts.get(candidate.status, 0) + 1
        details = [f"{len(self.plan.candidates)} workbook row(s)"]
        for status in ("Ready", "No changes", "Error"):
            if counts.get(status):
                details.append(f"{counts[status]} {status.casefold()}")
        return " · ".join(details) + ". Review exact changes before updating."

    def _candidate_for_iid(self, iid: str) -> BulkActionUpdateCandidate | None:
        if self.plan is None or not iid.startswith("row-"):
            return None
        try:
            row_number = int(iid[4:])
        except ValueError:
            return None
        return next(
            (
                candidate
                for candidate in self.plan.candidates
                if candidate.row_number == row_number
            ),
            None,
        )

    def _candidate_eligible(self, candidate: BulkActionUpdateCandidate) -> bool:
        return (
            not self._review_is_stale
            and candidate.action is not None
            and candidate.status == "Ready"
        )

    def _render_candidates(self) -> None:
        selected_iids = tuple(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        if self.plan is None:
            self._update_commit_state()
            self._set_detail("Choose an updated workbook to review its rows.")
            return

        for candidate in self.plan.candidates:
            reviewed = candidate.action or candidate.original_action
            title = reviewed.title if reviewed is not None else candidate.action_id
            change_labels = tuple(
                _FIELD_LABELS.get(field, field.replace("_", " ").title())
                for field in candidate.changed_fields
            )
            changes = ", ".join(change_labels) or "None"
            if candidate.row_number in self.applied_row_numbers:
                marker = "done"
                status = "Updated"
            elif self._candidate_eligible(candidate):
                marker = (
                    "[x]"
                    if candidate.row_number in self.selected_row_numbers
                    else "[ ]"
                )
                status = candidate.status
            else:
                marker = "-"
                status = candidate.status
            self.tree.insert(
                "",
                tk.END,
                iid=f"row-{candidate.row_number}",
                values=(
                    marker,
                    candidate.row_number,
                    title,
                    changes,
                    status,
                ),
            )

        retained = [iid for iid in selected_iids if self.tree.exists(iid)]
        if retained:
            self.tree.selection_set(retained[0])
            self.tree.focus(retained[0])
        self._update_commit_state()
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
        changed = False
        for iid in iids:
            candidate = self._candidate_for_iid(iid)
            if candidate is None or not self._candidate_eligible(candidate):
                continue
            if candidate.row_number in self.selected_row_numbers:
                self.selected_row_numbers.remove(candidate.row_number)
            else:
                self.selected_row_numbers.add(candidate.row_number)
            changed = True
        if changed:
            self._render_candidates()

    def _show_detail(self) -> None:
        selected = self.tree.selection()
        candidate = self._candidate_for_iid(selected[0]) if selected else None
        if candidate is None:
            self._set_detail("Select a workbook row to inspect it.")
            return
        lines = [
            f"Row: {candidate.row_number}",
            f"Action ID: {candidate.action_id}",
            f"Status: {candidate.status}",
        ]
        if (
            candidate.changed_fields
            and candidate.original_action is not None
            and candidate.action is not None
        ):
            lines.extend(("", "Exact changes:"))
            for field in candidate.changed_fields:
                label = _FIELD_LABELS.get(
                    field,
                    field.replace("_", " ").title(),
                )
                before = _action_field(candidate.original_action, field)
                after = _action_field(candidate.action, field)
                lines.extend(
                    (
                        "",
                        label,
                        f"Before: {_exact_value(before)}",
                        f"After:  {_exact_value(after)}",
                    )
                )
        else:
            lines.extend(("", "No editable fields changed."))
        if candidate.messages:
            lines.extend(("", "Messages:", *candidate.messages))
        self._set_detail("\n".join(lines))

    def _set_detail(self, text: str) -> None:
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        self.detail.insert("1.0", text)
        self.detail.configure(state=tk.DISABLED)

    def _update_commit_state(self) -> None:
        count = len(self.selected_row_numbers)
        self.update_button.configure(
            text=f"Update {_action_count(count)}",
            state=(
                tk.NORMAL
                if count
                and not self.submitting
                and not self._review_is_stale
                and not self._effects_unknown
                else tk.DISABLED
            ),
        )

    def update_actions(self) -> None:
        if (
            self.submitting
            or self.plan is None
            or not self.selected_row_numbers
            or self._review_is_stale
        ):
            return
        selected_rows = tuple(sorted(self.selected_row_numbers))
        self.submitting = True
        self._update_commit_state()
        try:
            updated = commit_bulk_action_update(
                self.plan,
                selected_rows,
                local_actions_path=self.local_actions_path,
                shared_actions_path=self.shared_actions_path,
                shared_contexts_path=self.shared_contexts_path,
                local_contexts_path=self.local_contexts_path,
            )
        except (BulkActionUpdateError, OSError) as exc:
            self.submitting = False
            self._review_is_stale = True
            self.selected_row_numbers.clear()
            self._render_candidates()
            if (
                isinstance(exc, BulkActionUpdateError)
                and exc.rollback_completed is False
            ):
                self._effects_unknown = True
                self.export_button.configure(state=tk.DISABLED)
                self.choose_button.configure(state=tk.DISABLED)
                self.reload_button.configure(state=tk.DISABLED)
                self._update_commit_state()
                messagebox.showerror(
                    "Actions or Contexts may have changed",
                    str(exc),
                    parent=self.window,
                )
                self.status_var.set(
                    "Actions or Contexts may have changed. Do not retry this "
                    "workbook. Inspect the latest backup and Diagnostics, then "
                    "close this window and verify the saved configuration."
                )
                return
            messagebox.showerror(
                "Actions were not updated",
                str(exc),
                parent=self.window,
            )
            self.status_var.set(
                "No Actions were updated. Reload the workbook and review the "
                "current changes before trying again."
            )
            return

        updated_by_id = {action.id: action for action in updated}
        self.actions = tuple(updated_by_id.get(action.id, action) for action in self.actions)
        self.applied_row_numbers.update(selected_rows)
        self.selected_row_numbers.clear()
        self._review_is_stale = True
        self.submitting = False
        self._render_candidates()
        self.status_var.set(
            f"Updated {_action_count(len(updated))}. Export a fresh workbook before "
            "reviewing more changes."
        )
        self.on_change()


def _action_field(action: Action, field: str) -> object:
    key = field.casefold().replace("_", " ")
    if key in {"title", "name"}:
        return action.title
    if key == "value":
        return action.value
    if key == "contexts":
        return action.effective_contexts
    if key == "tags":
        return action.effective_tags
    if key == "description":
        return action.description
    if key in {"quick action path", "quick menu"}:
        return action.quick_action_path
    if key == "arguments":
        return action.arguments
    if key in {"working directory", "working folder"}:
        return action.working_directory or ""
    return getattr(action, field, "")


def _exact_value(value: object) -> str:
    if isinstance(value, tuple):
        return json.dumps(list(value), ensure_ascii=False)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return '""'
    return json.dumps(value, ensure_ascii=False)


def _action_count(count: int) -> str:
    return f"{count} Action" if count == 1 else f"{count} Actions"
