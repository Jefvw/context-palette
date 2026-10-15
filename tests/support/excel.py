"""Inert Excel test doubles and synthetic response builders.

These helpers only queue callbacks or construct data; they never start an
engine, access desktop Excel, or create Tk widgets.
"""

from __future__ import annotations

import json
from pathlib import Path

from context_palette.excel_automation import (
    AutomationCallResult,
    ExcelCapability,
    ExcelCapabilityAvailability,
    ExcelCapabilitySupports,
    LiveColumnFormulas,
    LiveColumnPreflightColumn,
    LiveColumnPreflightResult,
    LiveColumnPrecisionRisks,
    LiveDataRows,
    LiveExcelApplication,
    LiveExcelInventoryResult,
    LiveExcelSheet,
    LiveExcelWorkbook,
    LivePreflightWorkbook,
    LivePrecisionRisk,
    LiveUsedRange,
    LiveValueClassifications,
)


class FakeCoordinator:
    """Deliver queued completions only when drained by the test's UI loop."""

    def __init__(self) -> None:
        self.running = False
        self.completion_pending = False
        self.calls: list[dict[str, object]] = []
        self._callback = None
        self._result = None

    def start(
        self,
        launcher_path: Path,
        request: dict[str, object],
        *,
        phase: str,
        timeout_seconds: float,
        on_complete,
    ) -> bool:
        if self.running:
            return False
        self.running = True
        self.calls.append(
            {
                "launcher_path": launcher_path,
                "request": request,
                "phase": phase,
                "timeout_seconds": timeout_seconds,
            }
        )
        self._callback = on_complete
        return True

    def complete(self, result: AutomationCallResult) -> None:
        self._result = result
        self.completion_pending = True

    def drain(self) -> bool:
        if not self.completion_pending:
            return False
        callback = self._callback
        result = self._result
        self.running = False
        self.completion_pending = False
        self._callback = None
        self._result = None
        callback(result)
        return True


def capability(
    operation: str,
    *,
    version: str = "1.0",
    available: bool = True,
) -> ExcelCapability:
    return ExcelCapability(
        operation,
        version,
        operation,
        "Test capability",
        "xlwings",
        "live_excel",
        (),
        0,
        0,
        "live_mutation" if operation.startswith("convert") else "read_only",
        "none",
        ExcelCapabilitySupports(True, True, False, operation.startswith("convert")),
        (
            "plan_live_column_conversion"
            if operation == "convert_live_column_representation"
            else None
        ),
        "1.0" if operation == "convert_live_column_representation" else None,
        True,
        ExcelCapabilityAvailability(
            available,
            None if available else "xlwings is unavailable",
        ),
    )


def conversion_workbook(
    token: str = "live-one",
    *,
    name: str = "Budget.xlsx",
    process_id: int = 42,
    full_path: str | None = r"D:\work\Budget.xlsx",
    active_sheet: str | None = "Données",
    sheets: tuple[LiveExcelSheet, ...] = (
        LiveExcelSheet(1, "Données", "visible"),
        LiveExcelSheet(2, "Archive", "hidden"),
    ),
) -> LiveExcelWorkbook:
    return LiveExcelWorkbook(
        token,
        process_id,
        name,
        full_path,
        True,
        False,
        False,
        active_sheet,
        len(sheets),
        False,
        sheets,
    )


def inventory_result(*books: LiveExcelWorkbook) -> AutomationCallResult:
    return AutomationCallResult(
        "inventory",
        "inventory_succeeded",
        True,
        0,
        result=LiveExcelInventoryResult(
            1,
            False,
            (
                LiveExcelApplication(
                    42,
                    True,
                    True,
                    len(books),
                    False,
                    books,
                ),
            ),
            (),
        ),
    )


def preflight_column(
    index: int,
    letter: str,
    header: object,
    *,
    precision: int = 0,
) -> LiveColumnPreflightColumn:
    risks = (
        (LivePrecisionRisk(2, "live.numeric_precision_may_already_be_lost", 1.23e18),)
        if precision
        else ()
    )
    return LiveColumnPreflightColumn(
        index,
        letter,
        header,  # type: ignore[arg-type]
        2,
        3,
        2,
        LiveValueClassifications(0, 1, 1, 0, 0, 0, 0, 0),
        LiveColumnFormulas(0, (), False),
        LiveColumnPrecisionRisks(precision, risks, False),
    )


def preflight_result(
    *columns: LiveColumnPreflightColumn,
    truncated: bool = False,
    next_offset: int | None = None,
    columns_total: int | None = None,
) -> AutomationCallResult:
    return AutomationCallResult(
        "preflight",
        "preflight_succeeded",
        True,
        0,
        result=LiveColumnPreflightResult(
            LivePreflightWorkbook(
                "live-one",
                42,
                "Budget.xlsx",
                r"D:\work\Budget.xlsx",
                True,
                False,
                False,
            ),
            "Données",
            1,
            LiveUsedRange(1, 3, 1, max((item.column_index for item in columns), default=1)),
            LiveDataRows(2, 3, 2, 2, False),
            columns_total if columns_total is not None else len(columns),
            truncated,
            next_offset,
            columns,
            (),
        ),
    )


def automation_response_envelope(
    operation: str,
    request_id: str,
    result: dict[str, object] | None,
    *,
    status: str = "success",
    error: dict[str, object] | None = None,
    warnings: list[dict[str, object]] | None = None,
) -> bytes:
    return (
        json.dumps(
            {
                "schema_version": "1.0",
                "request_id": request_id,
                "operation": operation,
                "operation_version": "1.0",
                "status": status,
                "duration_ms": 3,
                "paths": {"input": None, "output": None, "backup": None},
                "result": result,
                "warnings": warnings or [],
                "error": error,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        + b"\n"
    )
