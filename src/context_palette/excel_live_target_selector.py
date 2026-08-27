"""Shared workbook and worksheet selection for attended live-Excel workflows."""

from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk
from typing import Callable, Literal

from .excel_automation import LiveExcelInventoryResult, LiveExcelWorkbook


LiveExcelTargetScope = Literal["worksheet", "workbook"]


@dataclass(frozen=True, slots=True)
class CapturedExcelSource:
    """The window that was active when Context Palette was requested."""

    window_handle: int | None
    process_id: int | None
    window_title: str = ""


def workbook_labels(
    workbooks: tuple[LiveExcelWorkbook, ...],
) -> dict[str, LiveExcelWorkbook]:
    """Return stable, disambiguated labels for already-open workbooks."""

    labels: dict[str, LiveExcelWorkbook] = {}
    for workbook in workbooks:
        location = workbook.full_path or "Unsaved workbook"
        base = f"{workbook.name} — {location} — Excel {workbook.process_id}"
        label = base
        suffix = 2
        while label in labels:
            label = f"{base} ({suffix})"
            suffix += 1
        labels[label] = workbook
    return labels


def preferred_workbook(
    workbooks: tuple[LiveExcelWorkbook, ...],
    source: CapturedExcelSource,
) -> LiveExcelWorkbook:
    """Prefer the unambiguous workbook captured by F9, then a stable fallback."""

    if not workbooks:
        raise ValueError("At least one open workbook is required.")
    title = source.window_title.strip().casefold()
    same_process = tuple(
        item
        for item in workbooks
        if source.process_id is not None and item.process_id == source.process_id
    )
    title_matches = tuple(
        item
        for item in same_process
        if _title_starts_with_workbook_name(title, item.name.casefold())
    )
    if len(title_matches) == 1:
        return title_matches[0]
    if len(same_process) == 1:
        return same_process[0]
    return workbooks[0]


def visible_worksheet_names(workbook: LiveExcelWorkbook) -> tuple[str, ...]:
    """Return visible worksheet names in Excel order."""

    return tuple(sheet.name for sheet in workbook.sheets if sheet.state == "visible")


def preferred_visible_worksheet(workbook: LiveExcelWorkbook) -> str | None:
    """Prefer Excel's active visible worksheet, then the first visible sheet."""

    visible = visible_worksheet_names(workbook)
    if workbook.active_sheet in visible:
        return workbook.active_sheet
    return visible[0] if visible else None


def can_return_to_captured_excel(
    source: CapturedExcelSource,
    inventory_process_ids: frozenset[int],
) -> bool:
    """Return whether the captured source was an inventoried Excel process."""

    return (
        source.window_handle is not None
        and source.process_id is not None
        and source.process_id in inventory_process_ids
    )


def inventory_process_ids(inventory: LiveExcelInventoryResult) -> frozenset[int]:
    """Return every Excel process represented by the latest inventory."""

    return frozenset(application.process_id for application in inventory.applications)


def visible_inventory_workbooks(
    inventory: LiveExcelInventoryResult,
) -> tuple[LiveExcelWorkbook, ...]:
    """Flatten workbooks from visible Excel application instances."""

    return tuple(
        workbook
        for application in inventory.applications
        if application.visible
        for workbook in application.workbooks
    )


class LiveExcelTargetSelector(ttk.Frame):
    """Render the shared open-workbook and visible-worksheet chooser."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        workbooks: tuple[LiveExcelWorkbook, ...],
        source: CapturedExcelSource,
        refresh_command: Callable[[], None],
        selection_changed: Callable[[], None],
        allow_all_visible_worksheets: bool = False,
    ) -> None:
        if not workbooks:
            raise ValueError("At least one open workbook is required.")
        super().__init__(parent)
        self._selection_changed = selection_changed
        self._allow_all_visible_worksheets = allow_all_visible_worksheets
        self.workbooks_by_label = workbook_labels(workbooks)
        initial = preferred_workbook(workbooks, source)

        self.workbook_var = tk.StringVar(master=self)
        self.scope_var = tk.StringVar(master=self, value="worksheet")
        self.worksheet_var = tk.StringVar(master=self)
        self._selected_workbook = initial
        self._selected_worksheet: str | None = None
        self._selected_scope: LiveExcelTargetScope = "worksheet"

        initial_label = next(
            label
            for label, workbook in self.workbooks_by_label.items()
            if workbook == initial
        )
        self.workbook_var.set(initial_label)

        ttk.Label(self, text="Workbook", style="Heading.TLabel").grid(
            row=0, column=0, sticky=tk.W, padx=(0, 8), pady=(0, 6)
        )
        self.workbook_picker = ttk.Combobox(
            self,
            textvariable=self.workbook_var,
            values=tuple(self.workbooks_by_label),
            state="readonly",
            width=68,
        )
        self.workbook_picker.grid(row=0, column=1, sticky=tk.EW, pady=(0, 6))
        self.workbook_picker.bind(
            "<<ComboboxSelected>>", self.select_workbook_from_variable
        )
        self.refresh_button = ttk.Button(
            self,
            text="Refresh",
            command=refresh_command,
            style="Compact.TButton",
        )
        self.refresh_button.grid(
            row=0, column=2, sticky=tk.E, padx=(8, 0), pady=(0, 6)
        )

        worksheet_row = 1
        if allow_all_visible_worksheets:
            ttk.Label(self, text="Apply to", style="Heading.TLabel").grid(
                row=1, column=0, sticky=tk.NW, padx=(0, 8), pady=(4, 0)
            )
            scope = ttk.Frame(self)
            scope.grid(row=1, column=1, columnspan=2, sticky=tk.W, pady=(4, 0))
            ttk.Radiobutton(
                scope,
                text="One worksheet",
                variable=self.scope_var,
                value="worksheet",
                command=self.select_scope_from_variable,
            ).pack(side=tk.LEFT)
            ttk.Radiobutton(
                scope,
                text="All visible worksheets",
                variable=self.scope_var,
                value="workbook",
                command=self.select_scope_from_variable,
            ).pack(side=tk.LEFT, padx=(12, 0))
            worksheet_row = 2

        ttk.Label(self, text="Worksheet", style="Heading.TLabel").grid(
            row=worksheet_row,
            column=0,
            sticky=tk.W,
            padx=(0, 8),
            pady=(6 if allow_all_visible_worksheets else 0, 0),
        )
        self.worksheet_picker = ttk.Combobox(
            self,
            textvariable=self.worksheet_var,
            state="readonly",
            width=50,
        )
        self.worksheet_picker.grid(
            row=worksheet_row,
            column=1,
            columnspan=2,
            sticky=tk.EW,
            pady=(6 if allow_all_visible_worksheets else 0, 0),
        )
        self.worksheet_picker.bind(
            "<<ComboboxSelected>>", self.select_worksheet_from_variable
        )
        self.columnconfigure(1, weight=1)
        self._populate_worksheets(initial)

    @property
    def selected_workbook(self) -> LiveExcelWorkbook:
        return self._selected_workbook

    @property
    def selected_worksheet(self) -> str | None:
        return self._selected_worksheet

    @property
    def selected_scope(self) -> LiveExcelTargetScope:
        return self._selected_scope

    def select_workbook_from_variable(self, _event: tk.Event | None = None) -> None:
        workbook = self.workbooks_by_label.get(self.workbook_var.get())
        if workbook is None:
            return
        self._selected_workbook = workbook
        self._populate_worksheets(workbook)
        self._selection_changed()

    def select_worksheet_from_variable(self, _event: tk.Event | None = None) -> None:
        value = self.worksheet_var.get()
        self._selected_worksheet = value or None
        self._selection_changed()

    def select_scope_from_variable(self) -> None:
        if not self._allow_all_visible_worksheets:
            self.scope_var.set("worksheet")
        self._selected_scope = (
            "workbook" if self.scope_var.get() == "workbook" else "worksheet"
        )
        self.worksheet_picker.configure(
            state=("readonly" if self._selected_scope == "worksheet" else tk.DISABLED)
        )
        self._selection_changed()

    def _populate_worksheets(self, workbook: LiveExcelWorkbook) -> None:
        visible = visible_worksheet_names(workbook)
        selected = preferred_visible_worksheet(workbook)
        self.worksheet_var.set(selected or "")
        self._selected_worksheet = selected
        self.worksheet_picker.configure(values=visible)
        self.worksheet_picker.configure(
            state=("readonly" if self._selected_scope == "worksheet" else tk.DISABLED)
        )


def _title_starts_with_workbook_name(title: str, workbook_name: str) -> bool:
    if not title.startswith(workbook_name):
        return False
    remainder = title[len(workbook_name) :]
    return not remainder or remainder[0].isspace() or remainder[0] in "-—"
