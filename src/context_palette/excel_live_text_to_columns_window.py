"""Attended native Text to Columns as Text, using the shared live Excel UI."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from uuid import uuid4

from .excel_automation import (
    AutomationCallError,
    AutomationCallResult,
    DescribeCapabilitiesResult,
    ExcelAutomationInputError,
    LiveColumnPreflightInvocation,
    LiveColumnPreflightResult,
    LiveExcelWorkbook,
    LiveTextToColumnsInvocation,
    LiveTextToColumnsResult,
    build_apply_live_text_to_columns_as_text_request,
    build_preflight_live_columns_request,
)
from .excel_live_column_selector import LiveExcelColumnSelector
from .excel_live_text_conversion_window import ExcelLiveTextConversionWindow


_REQUIRED_CAPABILITIES = (
    "inventory_live_excel",
    "preflight_live_columns",
    "apply_live_text_to_columns_as_text",
)
_NO_BACKUP_WARNING = "No backup is created; Excel Undo may be affected."


class ExcelLiveTextToColumnsWindow(ExcelLiveTextConversionWindow):
    """One explicit gesture authorizes one ordered, engine-owned native batch."""

    WINDOW_TITLE = "Text to Columns → Text (fast)"
    INTRO_TEXT = (
        "Changes selected Excel columns to text using Excel’s native Text to Columns "
        "operation. Displayed notation may remain unchanged."
    )

    def __init__(self, *args, **kwargs) -> None:
        self._selected_column_order: tuple[int, ...] = ()
        self._native_invocation: LiveTextToColumnsInvocation | None = None
        self._native_workbook: LiveExcelWorkbook | None = None
        super().__init__(*args, **kwargs)

    def _capabilities_completed(self, call: AutomationCallResult) -> None:
        result = call.result
        if call.classification != "capabilities_succeeded" or not isinstance(
            result, DescribeCapabilitiesResult
        ):
            self._show_unavailable(call, "Python Excel capabilities are unavailable.")
            return
        missing = []
        for operation in _REQUIRED_CAPABILITIES:
            capability = result.find(operation, "1.0")
            if capability is None:
                missing.append(f"{operation} 1.0 is not advertised.")
            elif capability.availability.available is not True:
                missing.append(
                    f"{operation} 1.0 is unavailable: "
                    f"{capability.availability.reason or 'engine backend unavailable'}"
                )
        if missing:
            self.view_state = "capability_unavailable"
            self._clear_content()
            ttk.Label(
                self.content, text="Native Text to Columns unavailable",
                style="Heading.TLabel",
            ).pack(anchor=tk.W)
            self._show_text(missing, height=min(9, max(4, len(missing) + 1)))
            self._change_launcher_button()
            self._set_status(
                "The exact Python Excel 1.0 native Text to Columns capabilities are required.",
                error=True,
            )
            return
        self._start_inventory()

    def _start_first_preflight(self) -> None:
        self._selected_column_order = ()
        super()._start_first_preflight()

    def _start_preflight(self, column_offset: int) -> None:
        if self._closed or self.busy or self.coordinator.completion_pending:
            return
        workbook = self._selected_workbook
        worksheet = self._selected_worksheet
        if workbook is None or worksheet is None:
            self._set_status("Choose an open workbook and worksheet first.", error=True)
            return
        self._selected_column_order = self._selected_columns()
        self._selected_preflight_column_indexes = set(self._selected_column_order)
        try:
            invocation = LiveColumnPreflightInvocation(
                workbook.token, worksheet, column_offset=column_offset,
                headers_only=True,
            )
        except ExcelAutomationInputError as exc:
            self._set_status(str(exc), error=True)
            return
        self.view_state = "preflight"
        self._clear_content()
        self._show_working("Loading physical column headers without changing Excel…")
        self._start_call(
            build_preflight_live_columns_request(str(uuid4()), invocation),
            phase="preflight", timeout_seconds=45.0,
            callback=lambda call: self._preflight_completed(call, invocation),
        )

    def _preflight_matches(
        self, result: LiveColumnPreflightResult,
        invocation: LiveColumnPreflightInvocation,
    ) -> bool:
        return result.headers_only is True and super()._preflight_matches(result, invocation)

    def _show_preflight_selection(self, result: LiveColumnPreflightResult) -> None:
        self.view_state = "select_columns"
        self._clear_content()
        ttk.Label(
            self.content, text="Choose columns to convert to text", style="Heading.TLabel",
        ).pack(anchor=tk.W)
        if self._selected_workbook is not None:
            self._review_label(f"{self._selected_workbook.name} · {result.worksheet}")
            if self._selected_workbook.full_path:
                self._review_label(self._selected_workbook.full_path, muted=True)
        self._review_label(
            "Click columns in the order to convert them. Arrow keys and Space also work. "
            "Header row 1 is never converted.",
            muted=True,
        )
        self.column_selector = LiveExcelColumnSelector(
            self.content, columns=self._preflight_columns,
            selected_columns=self._selected_column_order,
            selection_changed=self._column_selection_changed,
            ordered_selection=True,
        )
        self.column_selector.pack(fill=tk.BOTH, expand=True)
        self.columns_listbox = self.column_selector.listbox
        if self._next_column_offset is not None:
            self._review_label("Load more columns to include later physical columns.", muted=True)
            ttk.Button(
                self.content, text="Load more columns",
                command=lambda: self._start_preflight(self._next_column_offset or 0),
            ).pack(anchor=tk.W, pady=(5, 0))
        self._review_label(_NO_BACKUP_WARNING, muted=True)
        self.primary_button = ttk.Button(
            self.footer, text="Convert", command=self._execute,
            style="Accent.TButton", state=tk.DISABLED,
        )
        self.primary_button.pack(side=tk.RIGHT, padx=(8, 0))
        self._refresh_inventory_button()
        self._render_warnings(result.warnings)
        self._column_selection_changed()

    def _selected_columns(self) -> tuple[int, ...]:
        selector = getattr(self, "column_selector", None)
        if selector is not None:
            try:
                return selector.selected_columns()
            except tk.TclError:
                pass
        return self._selected_column_order

    def _column_selection_changed(self, _event: tk.Event | None = None) -> None:
        self._selected_column_order = self._selected_columns()
        self._selected_preflight_column_indexes = set(self._selected_column_order)
        if self.primary_button is None:
            return
        allowed = bool(self._selected_column_order)
        self.primary_button.configure(state=tk.NORMAL if allowed else tk.DISABLED)
        self._set_status(
            "Choose Convert when ready. Load more only to select later columns."
            if allowed else "Select one or more columns."
        )

    def _execute(self) -> None:
        if (
            self._closed or self.busy or self.coordinator.completion_pending
            or self.view_state != "select_columns"
        ):
            return
        workbook = self._selected_workbook
        worksheet = self._selected_worksheet
        if workbook is None or worksheet is None or not self._selected_columns():
            return
        try:
            invocation = LiveTextToColumnsInvocation(
                workbook.token, worksheet, self._selected_columns(),
            )
        except ExcelAutomationInputError as exc:
            self._set_status(str(exc), error=True)
            return
        ticket = object()
        self._pending_execute_ticket = ticket
        self._native_invocation = invocation
        self._native_workbook = workbook
        self.view_state = "executing"
        self._clear_content()
        self._show_working("Converting selected columns with Excel’s native Text to Columns…")
        self._start_call(
            build_apply_live_text_to_columns_as_text_request(str(uuid4()), invocation),
            phase="native_text", timeout_seconds=180.0,
            callback=lambda call: self._execute_completed(call, ticket, invocation, workbook),
        )

    def _execute_completed(
        self, call: AutomationCallResult, ticket: object,
        invocation: LiveTextToColumnsInvocation, workbook: LiveExcelWorkbook,
    ) -> None:
        if self._closed or ticket is not self._pending_execute_ticket:
            return
        self._pending_execute_ticket = None
        result = call.result
        if call.classification == "start_failed" and not call.process_started:
            self._show_pre_effect_error(AutomationCallError(
                "host.native_start_failed", "host", call.reason or "The engine process could not start.", False, {},
            ))
            return
        if (
            call.phase == "native_text" and call.classification == "native_text_failed"
            and result is None and call.error is not None
        ):
            self._show_pre_effect_error(call.error)
            return
        if (
            not isinstance(result, LiveTextToColumnsResult)
            or call.phase != "native_text"
            or call.classification != f"native_text_{result.state}"
            or not self._execution_matches(result, invocation, workbook)
        ):
            self._show_unknown(call.reason or "The native conversion receipt was missing or mismatched.")
            return
        self._show_execution_result(result)

    @staticmethod
    def _execution_matches(
        result: LiveTextToColumnsResult, invocation: LiveTextToColumnsInvocation,
        workbook: LiveExcelWorkbook,
    ) -> bool:
        # The shared protocol parser validates receipt/range/state consistency.
        # The UI independently binds that receipt to its immutable gesture snapshot.
        target = result.target
        return (
            target.workbook_token == invocation.workbook_token == workbook.token
            and target.process_id == workbook.process_id
            and target.workbook_name == workbook.name
            and target.full_path == workbook.full_path
            and target.worksheet == invocation.worksheet
            and target.header_row == invocation.header_row
            and target.physical_columns == invocation.columns
        )

    def _show_execution_result(self, result: LiveTextToColumnsResult) -> None:
        if result.state == "unknown":
            super()._show_unknown(
                "The current column may already have changed. Inspect Excel before any manual retry.",
                trusted_partial_receipts=True,
            )
        else:
            self.view_state = result.state
            self._clear_content()
            heading, status = {
                "succeeded": ("Native Text to Columns completed", "Selected columns processed. Excel stays open and was not saved."),
                "failed": ("Native Text to Columns stopped before mutation", "No native call began; no workbook mutation was started."),
                "partial_failure": ("Native Text to Columns partly completed", "Earlier completed columns changed; the current column was blocked before its call."),
            }[result.state]
            self._review_label(heading, error=result.state != "succeeded")
            self._set_status(status, error=result.state != "succeeded")
        lines = [
            f"{result.target.workbook_name} · {result.target.worksheet}",
            f"Completed: {_columns_text(result.columns_completed)}",
            f"Skipped because empty: {_columns_text(result.columns_skipped_empty)}",
            f"Current column: {_columns_text(() if result.current_column is None else (result.current_column,))}",
            f"Current range: {result.current_range or 'None'}",
            f"Pending columns: {_columns_text(result.pending_columns)}",
            "Excel remains open and was not saved.",
            f"Unsaved changes reported by Excel before: {_dirty_text(result.workbook_dirty_before)}",
            f"Unsaved changes reported by Excel after: {_dirty_text(result.workbook_dirty)}",
            "Excel’s unsaved-changes flag does not prove whether cells changed.",
            _NO_BACKUP_WARNING,
        ]
        if result.failure is not None:
            lines.append(result.failure.message)
        if result.state == "unknown":
            lines.append("The current column may already have changed. Inspect Excel before any manual retry.")
        self._show_text(lines, height=13)
        self._render_warnings(result.warnings)
        if result.state != "unknown":
            self._return_button()

    def _show_pre_effect_error(self, error: AutomationCallError) -> None:
        self.view_state = "failed_before_effect"
        self._clear_content()
        self._review_label("Native Text to Columns could not start", error=True)
        self._show_text([error.message, "No conversion was started."], height=5)
        self._refresh_inventory_button()
        self._return_button()
        self._set_status("No conversion was started. Refresh the workbook list before a new selection.", error=True)

    def _show_unknown(self, reason: str) -> None:
        if self._native_invocation is None:
            self.view_state = "selection_unavailable"
            self._clear_content()
            self._review_label("Column selection could not be verified", error=True)
            self._show_text([reason, "No conversion request was sent."], height=5)
            self._refresh_inventory_button()
            self._return_button()
            self._set_status("No conversion request was sent. Refresh before choosing columns again.", error=True)
            return
        super()._show_unknown(reason)
        invocation = self._native_invocation
        if invocation is not None:
            self._show_text(
                [f"Possibly changed columns: {_columns_text(invocation.columns)}",
                 "Inspect every requested column before any manual retry."],
                height=5,
            )

    def _refresh_inventory_button(self, *, accent: bool = False, parent=None) -> None:
        if self.view_state != "unknown":
            super()._refresh_inventory_button(accent=accent, parent=parent)

    def _reset_target_state(self) -> None:
        super()._reset_target_state()
        self._selected_column_order = ()
        self._native_invocation = None
        self._native_workbook = None
        self.column_selector = None


def _columns_text(columns: tuple[int, ...]) -> str:
    return ", ".join(_column_letter(column) for column in columns) or "None"


def _column_letter(column: int) -> str:
    letter = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        letter = chr(65 + remainder) + letter
    return letter


def _dirty_text(value: bool | None) -> str:
    return "Unknown" if value is None else ("Yes" if value else "No")
