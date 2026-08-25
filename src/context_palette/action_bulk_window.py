"""Attended review window for creating personal Actions from one workbook."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Iterable

from .action_bulk import (
    BulkActionCandidate,
    BulkActionError,
    BulkActionPlan,
    commit_bulk_action_create,
    plan_bulk_action_create,
)
from .action_types import ACTION_TYPES
from .action_workbook import (
    ActionWorkbook,
    ActionWorkbookError,
    ActionWorkbookRow,
    read_action_import_workbook,
    write_action_import_template,
)
from .actions import Action
from .window_geometry import configure_standard_window, place_child_window


_ELIGIBLE_STATUSES = frozenset({"Ready", "Possible duplicate", "Warning"})


class ActionBulkWindow:
    """Choose, validate, review, and safely import an Actions workbook."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        actions: Iterable[Action],
        local_context_names: Iterable[str],
        local_actions_path: Path,
        shared_actions_path: Path,
        shared_contexts_path: Path,
        local_contexts_path: Path,
        on_change: Callable[[], None],
    ) -> None:
        # ``actions`` is deliberately every stored Action, Active and Archived.
        # The pure planner needs both states for duplicate and stale-store checks.
        self.actions = tuple(actions)
        self.local_context_names = tuple(local_context_names)
        self.local_actions_path = Path(local_actions_path)
        self.shared_actions_path = Path(shared_actions_path)
        self.shared_contexts_path = Path(shared_contexts_path)
        self.local_contexts_path = Path(local_contexts_path)
        self.on_change = on_change

        self.workbook: ActionWorkbook | None = None
        self.source_path: Path | None = None
        self.plan: BulkActionPlan | None = None
        self.selected_row_numbers: set[int] = set()
        self.created_row_numbers: set[int] = set()
        self.submitting = False
        self._reload_required = False

        self.window = tk.Toplevel(parent)
        self.window.title("Bulk create Actions")
        configure_standard_window(self.window, parent)
        self.window.minsize(760, 540)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.bind("<Control-o>", self._choose_from_key)
        self.window.bind("<F5>", self._reload_from_key)

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        ttk.Label(outer, text="Bulk create Actions", style="Title.TLabel").pack(
            anchor=tk.W
        )
        ttk.Label(
            outer,
            text=(
                "Use one standard Actions workbook to review and create personal Active Actions "
                "in a single write. Nothing runs during import."
            ),
            style="Muted.TLabel",
            wraplength=850,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(2, 10))

        toolbar = ttk.Frame(outer)
        toolbar.pack(fill=tk.X)
        self.choose_button = ttk.Button(
            toolbar, text="Choose Actions workbook…", command=self.choose_workbook
        )
        self.choose_button.pack(side=tk.LEFT)
        self.template_button = ttk.Button(
            toolbar,
            text="Save blank Actions workbook…",
            command=self.save_blank_template,
        )
        self.template_button.pack(side=tk.LEFT, padx=(6, 0))
        self.reload_button = ttk.Button(
            toolbar, text="Reload", command=self.reload_workbook, state=tk.DISABLED
        )
        self.reload_button.pack(side=tk.LEFT, padx=(6, 0))

        self.source_var = tk.StringVar(value="No workbook selected.")
        ttk.Label(
            outer,
            textvariable=self.source_var,
            style="Muted.TLabel",
            wraplength=850,
            justify=tk.LEFT,
        ).pack(fill=tk.X, pady=(6, 8))

        review = ttk.Panedwindow(outer, orient=tk.HORIZONTAL)
        review.pack(fill=tk.BOTH, expand=True)

        table_frame = ttk.Frame(review)
        review.add(table_frame, weight=3)
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL)
        horizontal_scrollbar = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL)
        self.tree = ttk.Treeview(
            table_frame,
            columns=("use", "row", "name", "type", "status"),
            show="headings",
            selectmode="browse",
            yscrollcommand=scrollbar.set,
            xscrollcommand=horizontal_scrollbar.set,
        )
        scrollbar.configure(command=self.tree.yview)
        horizontal_scrollbar.configure(command=self.tree.xview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        horizontal_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for column, label, width, stretch, anchor in (
            ("use", "Use", 48, False, tk.CENTER),
            ("row", "Excel row", 72, False, tk.E),
            ("name", "Name", 190, True, tk.W),
            ("type", "Type", 145, False, tk.W),
            ("status", "Status", 125, False, tk.W),
        ):
            self.tree.heading(column, text=label)
            self.tree.column(
                column, width=width, minwidth=width, stretch=stretch, anchor=anchor
            )
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_detail())
        self.tree.bind("<ButtonRelease-1>", self._tree_clicked)
        self.tree.bind("<space>", self._toggle_from_key)

        detail_frame = ttk.Frame(review, padding=(10, 0, 0, 0))
        review.add(detail_frame, weight=2)
        ttk.Label(detail_frame, text="Selected row", style="Heading.TLabel").pack(
            anchor=tk.W
        )
        detail_scrollbar = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL)
        self.detail = tk.Text(
            detail_frame,
            width=34,
            height=12,
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
            "Choose an Actions workbook. Ready rows are selected automatically; "
            "warnings require an explicit choice."
        )

        self.status_var = tk.StringVar(
            value="Choose an existing .xlsx workbook or save a blank template first."
        )
        ttk.Label(
            outer,
            textvariable=self.status_var,
            style="Status.TLabel",
            wraplength=850,
            justify=tk.LEFT,
        ).pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        footer = ttk.Frame(outer)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        self.create_button = ttk.Button(
            footer,
            text="Create 0 Actions",
            command=self.create_actions,
            state=tk.DISABLED,
            style="Accent.TButton",
        )
        self.create_button.pack(side=tk.LEFT)
        ttk.Button(footer, text="Close", command=self.close).pack(side=tk.RIGHT)

        self.window.transient(parent)
        place_child_window(self.window, parent, size=(900, 650))
        self.window.lift()
        self.window.after_idle(self.choose_button.focus_set)

    def close(self) -> None:
        self.window.destroy()

    def _choose_from_key(self, _event: tk.Event | None = None) -> str:
        if not self.submitting:
            self.choose_workbook()
        return "break"

    def _reload_from_key(self, _event: tk.Event | None = None) -> str:
        if not self.submitting:
            self.reload_workbook()
        return "break"

    def choose_workbook(self) -> None:
        if self.submitting:
            return
        selected = filedialog.askopenfilename(
            parent=self.window,
            title="Choose Actions workbook",
            filetypes=(("Excel workbooks", "*.xlsx"),),
        )
        if selected:
            self._load_workbook(Path(selected))

    def save_blank_template(self) -> None:
        if self.submitting:
            return
        selected = filedialog.asksaveasfilename(
            parent=self.window,
            title="Save blank Actions workbook",
            defaultextension=".xlsx",
            initialfile="Context Palette Actions.xlsx",
            filetypes=(("Excel workbooks", "*.xlsx"),),
        )
        if not selected:
            return
        try:
            saved = write_action_import_template(Path(selected))
        except (ActionWorkbookError, OSError) as exc:
            messagebox.showerror(
                "Actions workbook was not saved", str(exc), parent=self.window
            )
            return
        self.status_var.set(f"Blank Actions workbook saved: {saved}")
        messagebox.showinfo(
            "Actions workbook saved",
            "The blank workbook is ready. Fill its Actions sheet, save it, then choose it here.",
            parent=self.window,
        )

    def reload_workbook(self) -> None:
        if self.submitting or self.source_path is None:
            return
        self._load_workbook(self.source_path)

    def _load_workbook(self, path: Path) -> None:
        self.source_path = Path(path)
        try:
            workbook = read_action_import_workbook(self.source_path)
            plan = plan_bulk_action_create(
                workbook, self.actions, self.local_context_names
            )
        except (ActionWorkbookError, BulkActionError, OSError) as exc:
            self._clear_review_after_load_error()
            messagebox.showerror(
                "Actions workbook could not be reviewed", str(exc), parent=self.window
            )
            self.status_var.set(
                "No Actions were created. Correct this workbook and choose Reload, "
                "or choose another workbook."
            )
            return

        self.workbook = workbook
        self.plan = plan
        self.created_row_numbers.clear()
        self._reload_required = False
        self.selected_row_numbers = {
            candidate.row_number
            for candidate in plan.candidates
            if candidate.status == "Ready" and candidate.selected_by_default
        }
        self.source_var.set(str(workbook.path))
        self.reload_button.configure(state=tk.NORMAL)
        self._render_candidates()
        self.status_var.set(self._plan_summary())
        if self.tree.get_children():
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
            self._show_detail()
            self.tree.focus_set()

    def _clear_review_after_load_error(self) -> None:
        self.workbook = None
        self.plan = None
        self.selected_row_numbers.clear()
        self.created_row_numbers.clear()
        self._reload_required = False
        self.source_var.set(
            str(self.source_path) if self.source_path else "No workbook selected."
        )
        self.reload_button.configure(
            state=tk.NORMAL if self.source_path is not None else tk.DISABLED
        )
        self.tree.delete(*self.tree.get_children())
        self._set_detail(
            "This workbook could not be reviewed. Correct it and choose Reload, "
            "or choose another workbook."
        )
        self._update_create_state()

    def _plan_summary(self) -> str:
        if self.plan is None:
            return "No workbook has been reviewed."
        counts: dict[str, int] = {}
        for candidate in self.plan.candidates:
            counts[candidate.status] = counts.get(candidate.status, 0) + 1
        details = [f"{len(self.plan.candidates)} workbook row(s)"]
        for status in (
            "Ready",
            "Possible duplicate",
            "Warning",
            "Already exists",
            "Error",
            "Not selected",
        ):
            if counts.get(status):
                details.append(f"{counts[status]} {status.casefold()}")
        return " · ".join(details) + ". Review warnings before creating Actions."

    def _candidate_for_iid(self, iid: str) -> BulkActionCandidate | None:
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

    def _row_data(self, row_number: int) -> ActionWorkbookRow | None:
        if self.workbook is None:
            return None
        return next(
            (row for row in self.workbook.rows if row.row_number == row_number), None
        )

    def _candidate_eligible(self, candidate: BulkActionCandidate) -> bool:
        return (
            not self._reload_required
            and candidate.action is not None
            and candidate.status in _ELIGIBLE_STATUSES
        )

    def _render_candidates(self) -> None:
        selected_iids = tuple(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        if self.plan is None:
            self._update_create_state()
            self._set_detail("Choose an Actions workbook to review its rows.")
            return

        for candidate in self.plan.candidates:
            action = candidate.action
            row = self._row_data(candidate.row_number)
            name = action.title if action is not None else (row.name if row else "")
            action_type = action.type if action is not None else (row.action_type if row else "")
            definition = ACTION_TYPES.get(action_type)
            type_label = definition.label if definition is not None else action_type
            if candidate.row_number in self.created_row_numbers:
                marker = "done"
                status = "Created"
            elif self._candidate_eligible(candidate):
                marker = "[x]" if candidate.row_number in self.selected_row_numbers else "[ ]"
                status = candidate.status
            else:
                marker = "-"
                status = candidate.status
            self.tree.insert(
                "",
                tk.END,
                iid=f"row-{candidate.row_number}",
                values=(marker, candidate.row_number, name, type_label, status),
            )

        retained = [iid for iid in selected_iids if self.tree.exists(iid)]
        if retained:
            self.tree.selection_set(retained[0])
            self.tree.focus(retained[0])
        self._update_create_state()
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
        action = candidate.action
        row = self._row_data(candidate.row_number)
        name = action.title if action is not None else (row.name if row else "")
        action_type = action.type if action is not None else (row.action_type if row else "")
        definition = ACTION_TYPES.get(action_type)
        type_label = definition.label if definition is not None else action_type
        value = action.value if action is not None else (row.value if row else "")
        contexts = (
            action.effective_contexts
            if action is not None
            else (row.contexts if row else ())
        )
        tags = (
            action.effective_tags if action is not None else (row.tags if row else ())
        )
        description = (
            action.description if action is not None else (row.description if row else "")
        )
        quick_menu = (
            action.quick_action_path if action is not None else (row.quick_menu if row else ())
        )
        arguments = (
            action.arguments if action is not None else (row.arguments if row else ())
        )
        working_folder = (
            (action.working_directory or "")
            if action is not None
            else (row.working_folder if row else "")
        )
        lines = [
            f"Excel row: {candidate.row_number}",
            f"Status: {candidate.status}",
            "",
            "Name:",
            name or "(none)",
            "",
            "Action type:",
            f"{type_label} ({action_type})" if action_type else "(none)",
            "",
            "Value:",
            value or "(none)",
            "",
            "Description:",
            description or "(none)",
            "",
            "Contexts:",
            ", ".join(contexts) or "General only",
            "",
            "Tags:",
            ", ".join(tags) or "(none)",
            "",
            "Quick menu:",
            " > ".join(quick_menu) or "(none)",
            "",
            "Arguments:",
            "\n".join(arguments) or "(none)",
            "",
            "Working folder:",
            working_folder or "(none)",
        ]
        if candidate.messages:
            lines.extend(("", "Messages:", *candidate.messages))
        self._set_detail("\n".join(lines))

    def _set_detail(self, text: str) -> None:
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        self.detail.insert("1.0", text)
        self.detail.configure(state=tk.DISABLED)

    def _update_create_state(self) -> None:
        count = len(self.selected_row_numbers)
        self.create_button.configure(
            text=f"Create {_action_count(count)}",
            state=tk.NORMAL if count and not self.submitting else tk.DISABLED,
        )

    def create_actions(self) -> None:
        if self.submitting or self.plan is None or not self.selected_row_numbers:
            return
        selected_rows = tuple(sorted(self.selected_row_numbers))
        self.submitting = True
        self._update_create_state()
        try:
            created = commit_bulk_action_create(
                self.plan,
                selected_rows,
                self.local_actions_path,
                self.shared_actions_path,
                self.shared_contexts_path,
                self.local_contexts_path,
            )
        except (BulkActionError, OSError) as exc:
            self.submitting = False
            self._update_create_state()
            messagebox.showerror(
                "Actions were not created", str(exc), parent=self.window
            )
            return

        self.created_row_numbers.update(selected_rows)
        self.actions = (*self.actions, *created)
        self.selected_row_numbers.clear()
        self._reload_required = True
        self.submitting = False
        self._render_candidates()
        self.status_var.set(
            f"Created {_action_count(len(created))} in My configuration. "
            "Reload to review the workbook again."
        )
        self.on_change()
        messagebox.showinfo(
            "Actions created",
            f"Created {_action_count(len(created))} in My configuration.",
            parent=self.window,
        )


def _action_count(count: int) -> str:
    return f"{count} Action" if count == 1 else f"{count} Actions"
