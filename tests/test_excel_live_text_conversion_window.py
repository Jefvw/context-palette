from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from context_palette.excel_automation import (
    AutomationCallError,
    AutomationCallResult,
    DescribeCapabilitiesResult,
    ExcelCapability,
    ExcelCapabilityAvailability,
    ExcelCapabilitySupports,
    LiveColumnConversionPlanResult,
    LiveColumnConversionResult,
    LiveColumnFormulas,
    LiveColumnPreflightColumn,
    LiveColumnPreflightResult,
    LiveColumnPrecisionRisks,
    LiveConversionBlocker,
    LiveConversionCounts,
    LiveConversionEffect,
    LiveConversionExecutionRecovery,
    LiveConversionExecutionTarget,
    LiveConversionFailure,
    LiveConversionPlanColumn,
    LiveConversionPlanTarget,
    LiveConversionRecoveryPlan,
    LiveConversionSample,
    LiveDataRows,
    LiveExcelApplication,
    LiveExcelInventoryResult,
    LiveExcelSheet,
    LiveExcelWarning,
    LiveExcelWorkbook,
    LivePreflightWorkbook,
    LivePrecisionRisk,
    LiveUsedRange,
    LiveValueClassifications,
)
from context_palette.excel_live_text_conversion_window import (
    ExcelLiveTextConversionWindow,
)
from context_palette.excel_live_target_selector import LiveExcelTargetSelector
from context_palette.style import configure_theme


FINGERPRINT = "sha256:" + "a" * 64
SCOPE_FINGERPRINT = "sha256:" + "b" * 64
RECOVERY = r"D:\work\Budget.python-excel-recovery.xlsx"
REQUIRED = (
    "inventory_live_excel",
    "preflight_live_columns",
    "plan_live_column_conversion",
    "convert_live_column_representation",
)


class FakeCoordinator:
    def __init__(self) -> None:
        self.running = False
        self.completion_pending = False
        self.calls: list[dict[str, object]] = []
        self._callback = None
        self._result = None

    def start(self, launcher_path, request, *, phase, timeout_seconds, on_complete):
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


def capabilities_result(
    *,
    missing: str | None = None,
    mismatch: str | None = None,
    unavailable: str | None = None,
) -> AutomationCallResult:
    items = tuple(
        capability(
            operation,
            version="2.0" if operation == mismatch else "1.0",
            available=operation != unavailable,
        )
        for operation in REQUIRED
        if operation != missing
    )
    return AutomationCallResult(
        "capabilities",
        "capabilities_succeeded",
        True,
        0,
        result=DescribeCapabilitiesResult(items),
    )


def workbook(
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


def plan_result(
    *,
    columns: tuple[int, ...] = (1,),
    can_execute: bool = True,
    precision: int = 0,
    recovery: str = RECOVERY,
) -> AutomationCallResult:
    blockers = () if can_execute else (
        LiveConversionBlocker(
            "input.formulas_in_conversion_scope",
            "The selected scope contains formulas.",
            {},
        ),
    )
    plan_columns = tuple(
        LiveConversionPlanColumn(
            index,
            {1: "A", 2: "B", 3: "C", 4: "D", 6: "F"}.get(index, "Z"),
            "Identifier",
            LiveConversionCounts(2, 0, 1, 1, 0, 0, precision),
            (LiveConversionSample(2, "1.2E+5", "120000"),),
            False,
            (
                (LivePrecisionRisk(2, "live.numeric_precision_may_already_be_lost", 1.2e18),)
                if precision
                else ()
            ),
            False,
        )
        for index in columns
    )
    result = LiveColumnConversionPlanResult(
        can_execute,
        0,
        SCOPE_FINGERPRINT,
        FINGERPRINT,
        LiveConversionPlanTarget(
            42,
            "live-one",
            "Budget.xlsx",
            r"D:\work\Budget.xlsx",
            True,
            False,
            False,
            False,
            "Données",
            False,
            columns,
            1,
            LiveUsedRange(1, 3, 1, max(columns)),
            2,
            3,
            2,
            2,
            False,
        ),
        LiveConversionEffect(
            "text",
            2 * len(columns),
            len(columns),
            len(columns),
            0,
            0 if can_execute else 1,
            0 if can_execute else 1,
            0,
            precision,
        ),
        LiveConversionRecoveryPlan(True, "save_copy_as", recovery, False),
        plan_columns,
        blockers,
        (
            (
                LiveExcelWarning(
                    "live.numeric_precision_may_already_be_lost",
                    "Excel precision may already be lost.",
                    {},
                ),
            )
            if precision
            else ()
        ),
    )
    return AutomationCallResult(
        "conversion_plan",
        "conversion_plan_ready" if can_execute else "conversion_plan_blocked",
        True,
        0,
        result=result,
    )


def execution_result(
    state: str = "succeeded",
    *,
    token: str = "live-one",
    recovery_verified: bool = True,
) -> AutomationCallResult:
    mutation_started = state != "failed"
    failure = None
    if state != "succeeded":
        failure = LiveConversionFailure(
            "operation.live_text_conversion_failed",
            "Excel rejected one range write.",
            "write" if mutation_started else "recovery",
            1 if mutation_started else None,
            "RuntimeError",
            None,
        )
    result = LiveColumnConversionResult(
        state,  # type: ignore[arg-type]
        LiveConversionExecutionTarget(
            42,
            token,
            "Budget.xlsx",
            r"D:\work\Budget.xlsx",
            "Données",
            (1,),
            2,
            3,
        ),
        FINGERPRINT,
        1 if mutation_started else 0,
        1 if mutation_started else 0,
        0,
        (1,) if mutation_started else (),
        LiveConversionExecutionRecovery(RECOVERY, recovery_verified),
        mutation_started,
        mutation_started,
        False,
        False,
        False,
        failure,
        (),
    )
    classification = {
        "succeeded": "conversion_execute_succeeded",
        "failed": "conversion_execute_failed",
        "partial_failure": "conversion_execute_partial_failure",
    }[state]
    return AutomationCallResult(
        "conversion_execute",
        classification,  # type: ignore[arg-type]
        True,
        0,
        result=result,
    )


class ExcelLiveTextConversionWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "context-palette" / "data"
        self.data.mkdir(parents=True)
        self.launcher = Path(self.temp.name) / "python-excel.bat"
        self.launcher.write_text("@echo off\n", encoding="utf-8")
        self.settings = self.data / "local_excel_automation_settings.json"
        self.settings.write_text(
            json.dumps({"launcher_path": str(self.launcher)}), encoding="utf-8"
        )
        self.coordinator = FakeCoordinator()
        self.status = Mock()
        self.file_opener = Mock()
        self.folder_opener = Mock()
        self.return_to_source = Mock(return_value=True)

    def _window(self, **kwargs) -> ExcelLiveTextConversionWindow:
        window = ExcelLiveTextConversionWindow(
            self.root,
            settings_path=kwargs.pop("settings_path", self.settings),
            status_setter=self.status,
            coordinator=self.coordinator,  # type: ignore[arg-type]
            file_opener=self.file_opener,
            folder_opener=self.folder_opener,
            return_to_source=self.return_to_source,
            **kwargs,
        )
        self.addCleanup(self._close, window)
        self.root.update()
        return window

    def _close(self, window: ExcelLiveTextConversionWindow) -> None:
        self.coordinator.running = False
        self.coordinator.completion_pending = False
        self.coordinator._callback = None
        if not window._closed:
            window.close()

    def _complete(
        self,
        window: ExcelLiveTextConversionWindow,
        result: AutomationCallResult,
    ) -> None:
        self.coordinator.complete(result)
        if window._poll_after_id is not None:
            window.window.after_cancel(window._poll_after_id)
            window._poll_after_id = None
        window._poll()

    def _inventory(self, window: ExcelLiveTextConversionWindow, *books) -> None:
        self.assertEqual(self.coordinator.calls[-1]["phase"], "capabilities")
        self._complete(window, capabilities_result())
        self.assertEqual(self.coordinator.calls[-1]["phase"], "inventory")
        self._complete(window, inventory_result(*books))

    def _preflight(
        self,
        window: ExcelLiveTextConversionWindow,
        *columns: LiveColumnPreflightColumn,
    ) -> None:
        self._inventory(window, workbook())
        window.primary_button.invoke()
        self.assertEqual(self.coordinator.calls[-1]["phase"], "preflight")
        self._complete(window, preflight_result(*columns))

    def _plan(
        self,
        window: ExcelLiveTextConversionWindow,
        *,
        precision: int = 0,
        can_execute: bool = True,
    ) -> None:
        self._preflight(window, preflight_column(1, "A", "Identifier"))
        window.columns_listbox.selection_set(0)
        window._column_selection_changed()
        window.review_button.invoke()
        self.assertEqual(self.coordinator.calls[-1]["phase"], "conversion_plan")
        self._complete(
            window,
            plan_result(precision=precision, can_execute=can_execute),
        )

    def test_missing_settings_shows_optional_setup(self) -> None:
        window = self._window(settings_path=self.data / "missing.json")

        self.assertEqual(window.view_state, "setup")
        self.assertIn("Browse for Python Excel launcher", self._texts(window.content))
        self.assertEqual(self.coordinator.calls, [])

    def test_capability_version_mismatch_and_unavailable_stop_before_inventory(self) -> None:
        for result in (
            capabilities_result(mismatch="preflight_live_columns"),
            capabilities_result(unavailable="convert_live_column_representation"),
        ):
            with self.subTest(result=result):
                window = self._window()
                self._complete(window, result)
                self.assertEqual(window.view_state, "capability_unavailable")
                self.assertEqual(
                    [call["phase"] for call in self.coordinator.calls],
                    ["capabilities"],
                )
                self._close(window)
                self.coordinator = FakeCoordinator()

    def test_zero_workbooks_and_duplicate_unicode_labels_are_unambiguous(self) -> None:
        empty = self._window()
        self._inventory(empty)
        self.assertEqual(empty.view_state, "no_workbooks")
        self._close(empty)
        self.coordinator = FakeCoordinator()

        window = self._window(
            source_process_id=42,
            source_window_title="Büdget.xlsx - Excel",
        )
        first = workbook("one", name="Büdget.xlsx")
        second = workbook("two", name="Büdget.xlsx")
        self._inventory(window, first, second)

        labels = tuple(window._workbooks_by_label)
        self.assertEqual(len(labels), 2)
        self.assertNotEqual(labels[0], labels[1])
        self.assertEqual(window.worksheet_var.get(), "Données")
        self.assertIsInstance(window.target_selector, LiveExcelTargetSelector)
        self.assertIs(window.workbook_picker.master, window.target_selector)
        self.assertIs(window.worksheet_picker.master, window.target_selector)
        self.assertIs(window.refresh_button.master, window.target_selector)

    def test_blank_duplicate_headers_and_load_more_preserve_physical_selection(self) -> None:
        window = self._window()
        self._inventory(window, workbook())
        window.primary_button.invoke()
        self._complete(
            window,
            preflight_result(
                preflight_column(1, "A", None),
                preflight_column(2, "B", "ID"),
                truncated=True,
                next_offset=2,
                columns_total=3,
            ),
        )
        labels = window.columns_listbox.get(0, tk.END)
        self.assertIn("1 · A · (blank header)", labels)
        self.assertIn("2 · B · ID", labels)
        window.columns_listbox.selection_set(1)
        window._column_selection_changed()
        self.assertTrue(window.primary_button.instate(["disabled"]))
        self.assertIn("Load all remaining", window.status_var.get())

        self._button(window.content, "Load more columns").invoke()
        request = self.coordinator.calls[-1]["request"]
        self.assertEqual(request["arguments"]["column_offset"], 2)
        self._complete(
            window,
            preflight_result(
                preflight_column(3, "C", "ID"),
                columns_total=3,
            ),
        )

        self.assertEqual(window.columns_listbox.get(0, tk.END)[1:], ("2 · B · ID", "3 · C · ID"))
        self.assertEqual(window._selected_columns(), (2,))
        self.assertFalse(window.review_button.instate(["disabled"]))
        self.assertTrue(window.primary_button.instate(["disabled"]))

    def test_blocked_plan_disables_execute_and_renders_blocker(self) -> None:
        window = self._window(execution_enabled=True)
        self._plan(window, can_execute=False)

        self.assertEqual(window.view_state, "plan_blocked")
        self.assertTrue(window.primary_button.instate(["disabled"]))
        self.assertIn("formulas", window.result_text.get("1.0", "end-1c"))
        self.assertNotIn("retry", window.primary_button.cget("text").casefold())

    def test_direct_convert_plans_then_executes_exact_selection_once_without_review(self) -> None:
        window = self._window(execution_enabled=True)
        self._preflight(window, preflight_column(2, "B", "ID"), preflight_column(4, "D", "ID"), preflight_column(6, "F", "ID"))
        window.columns_listbox.selection_set(0, 2)
        window._column_selection_changed()
        self.assertEqual(window.primary_button.cget("text"), "Convert")
        self.assertIn("One backup", self._texts(window.content))
        self.assertIn("Excel Undo history may be cleared", self._texts(window.content))
        window.primary_button.invoke()
        plan_callback = self.coordinator._callback
        call_count = len(self.coordinator.calls)
        window._start_plan(None, execute_when_ready=True)
        self.assertEqual(len(self.coordinator.calls), call_count)
        self.assertEqual(self.coordinator.calls[-1]["phase"], "conversion_plan")
        plan = plan_result(columns=(2, 4, 6))
        self._complete(window, plan)
        self.assertEqual(window.view_state, "executing")
        self.assertIsNone(window.result_text)
        request = self.coordinator.calls[-1]["request"]["arguments"]
        self.assertEqual(request["columns"], [2, 4, 6])
        self.assertEqual(request["workbook_token"], "live-one")
        self.assertEqual(request["worksheet"], "Données")
        self.assertEqual(request["expected_plan_fingerprint"], FINGERPRINT)
        self.assertEqual(request["recovery_path"], RECOVERY)
        self.assertIs(request["acknowledge_irreversible_precision_risk"], False)
        self.assertFalse(window._plan_correlated)
        execute_callback = self.coordinator._callback
        plan_callback(plan)
        window._execute()
        self.assertEqual([call["phase"] for call in self.coordinator.calls].count("conversion_execute"), 1)
        receipt = execution_result()
        receipt = replace(receipt, result=replace(
            receipt.result,
            target=replace(receipt.result.target, physical_columns=(2, 4, 6)),
            columns_completed=(2, 4, 6), changed_cells=3, already_compliant_cells=3,
        ))
        self._complete(window, receipt)
        self.assertEqual(window.view_state, "succeeded")
        plan_callback(plan)
        execute_callback(execution_result("partial_failure"))
        window._execute()
        self.assertEqual(window.view_state, "succeeded")
        self.assertEqual([call["phase"] for call in self.coordinator.calls].count("conversion_execute"), 1)

    def test_optional_review_does_not_authorize_execution(self) -> None:
        window = self._window(execution_enabled=True)
        self._plan(window)
        self.assertEqual(window.view_state, "plan_ready")
        self.assertNotIn("conversion_execute", [call["phase"] for call in self.coordinator.calls])
        window.plan_details_button.invoke()
        self.assertNotIn("conversion_execute", [call["phase"] for call in self.coordinator.calls])
        window.primary_button.invoke()
        self.assertEqual(self.coordinator.calls[-1]["phase"], "conversion_execute")

    def test_direct_precision_warning_is_short_and_requires_a_new_explicit_convert(self) -> None:
        window = self._window(execution_enabled=True)
        self._preflight(window, preflight_column(1, "A", "ID"))
        window.columns_listbox.selection_set(0)
        window._column_selection_changed()
        window.primary_button.invoke()
        self._complete(window, plan_result(precision=1))
        self.assertEqual(window.view_state, "precision_confirmation")
        self.assertNotIn("Before → After", self._texts(window.content))
        self.assertIn("cannot recover lost digits", self._texts(window.content))
        self.assertIn("Review changes (optional)", self._texts(window.content))
        self.assertTrue(window.primary_button.instate(["disabled"]))
        window.primary_button.invoke()
        self.assertNotIn("conversion_execute", [call["phase"] for call in self.coordinator.calls])
        window.precision_ack_var.set(True)
        window._update_execute_state()
        self.assertNotIn("conversion_execute", [call["phase"] for call in self.coordinator.calls])
        window.primary_button.invoke()
        self.assertIs(self.coordinator.calls[-1]["request"]["arguments"]["acknowledge_irreversible_precision_risk"], True)

    def test_direct_convert_respects_gate_blocked_plan_and_mismatched_response(self) -> None:
        for kind in ("disabled", "disabled_during_plan", "blocked", "mismatch", "no_recovery"):
            with self.subTest(kind=kind):
                window = self._window(execution_enabled=kind != "disabled")
                self._preflight(window, preflight_column(1, "A", "ID"))
                window.columns_listbox.selection_set(0)
                window._column_selection_changed()
                call_count = len(self.coordinator.calls)
                if kind == "disabled":
                    window._start_plan(None, execute_when_ready=True)
                    self.assertEqual(len(self.coordinator.calls), call_count)
                    self.assertFalse(window.review_button.instate(["disabled"]))
                    window.review_button.invoke()
                else:
                    window.primary_button.invoke()
                if kind == "disabled_during_plan":
                    window.execution_enabled = False
                call = plan_result(can_execute=kind != "blocked")
                if kind == "mismatch":
                    call = replace(call, result=replace(call.result, target=replace(call.result.target, workbook_token="different")))
                if kind == "no_recovery":
                    call = replace(call, result=replace(call.result, recovery=replace(call.result.recovery, path=None)))
                self._complete(window, call)
                self.assertNotIn("conversion_execute", [item["phase"] for item in self.coordinator.calls])
                self.assertIn(window.view_state, {"plan_ready", "plan_blocked", "unknown"})
                self._close(window)
                self.coordinator = FakeCoordinator()

    def test_obsolete_plan_callback_cannot_replace_current_conversion_intent(self) -> None:
        window = self._window(execution_enabled=True)
        self._preflight(window, preflight_column(1, "A", "ID"), preflight_column(2, "B", "ID"))
        window.columns_listbox.selection_set(0)
        window._column_selection_changed()
        window.review_button.invoke()
        old_callback = self.coordinator._callback
        self._complete(window, plan_result())
        window._change_columns()
        window.columns_listbox.selection_clear(0, tk.END)
        window.columns_listbox.selection_set(1)
        window._column_selection_changed()
        window.primary_button.invoke()
        old_callback(plan_result())
        self.assertEqual(window.view_state, "planning")
        self.assertNotIn("conversion_execute", [call["phase"] for call in self.coordinator.calls])
        self._complete(window, plan_result(columns=(2,)))
        self.assertEqual(self.coordinator.calls[-1]["request"]["arguments"]["columns"], [2])
        self.assertEqual([call["phase"] for call in self.coordinator.calls].count("conversion_execute"), 1)

    def test_closed_window_revokes_pending_direct_conversion(self) -> None:
        window = self._window(execution_enabled=True)
        self._preflight(window, preflight_column(1, "A", "ID"))
        window.columns_listbox.selection_set(0)
        window._column_selection_changed()
        window.primary_button.invoke()
        old_callback = self.coordinator._callback
        self.assertFalse(window.close())
        self._close(window)
        old_callback(plan_result())
        self.assertNotIn("conversion_execute", [call["phase"] for call in self.coordinator.calls])

    def test_existing_backup_blocks_direct_conversion_without_host_replacement(self) -> None:
        backup = Path(self.temp.name) / "Budget.python-excel-recovery.xlsx"
        backup.write_bytes(b"existing recovery evidence")
        window = self._window(execution_enabled=True)
        self._preflight(window, preflight_column(1, "A", "ID"))
        window.columns_listbox.selection_set(0)
        window._column_selection_changed()
        window.primary_button.invoke()
        call = plan_result(can_execute=False, recovery=str(backup))
        call = replace(call, result=replace(call.result, blockers=(
            LiveConversionBlocker("conflict.recovery_output_exists", "The backup already exists.", {}),
        )))
        self._complete(window, call)
        self.assertEqual(window.view_state, "plan_blocked")
        self.assertIn("backup already exists", self._texts(window.content))
        self.assertEqual(backup.read_bytes(), b"existing recovery evidence")
        self.assertNotIn("conversion_execute", [item["phase"] for item in self.coordinator.calls])
        self.assertEqual([item["phase"] for item in self.coordinator.calls].count("conversion_plan"), 1)

    def test_default_recovery_is_reviewed_and_override_replans_without_creating(self) -> None:
        window = self._window(execution_enabled=True)
        self._plan(window)
        first_request = self.coordinator.calls[-1]["request"]
        self.assertIsNone(first_request["arguments"]["recovery_path"])
        self.assertIn(RECOVERY, window.result_text.get("1.0", "end-1c"))
        alternate = r"D:\work\alternate-recovery.xlsx"

        with patch(
            "context_palette.excel_live_text_conversion_window.filedialog.asksaveasfilename",
            return_value=alternate,
        ):
            self._button(window.content, "Change…").invoke()

        request = self.coordinator.calls[-1]["request"]
        self.assertEqual(request["arguments"]["recovery_path"], alternate)
        self.assertFalse(Path(alternate).exists())

    def test_recovery_picker_normalizes_separators_without_accepting_a_different_file(self) -> None:
        window = self._window(execution_enabled=True)
        self._plan(window)
        alternate = Path(self.temp.name) / "Données recovery copy.xlsx"

        with patch(
            "context_palette.excel_live_text_conversion_window.filedialog.asksaveasfilename",
            return_value=alternate.as_posix(),
        ):
            self._button(window.content, "Change…").invoke()

        request = self.coordinator.calls[-1]["request"]
        self.assertEqual(request["arguments"]["recovery_path"], str(alternate))
        self._complete(window, plan_result(recovery=str(alternate)))
        self.assertEqual(window.view_state, "plan_ready")
        self.assertFalse(alternate.exists())
        self.assertNotIn("conversion_execute", [call["phase"] for call in self.coordinator.calls])

        with patch(
            "context_palette.excel_live_text_conversion_window.filedialog.asksaveasfilename",
            return_value=alternate.as_posix(),
        ):
            self._button(window.content, "Change…").invoke()
        self._complete(window, plan_result(recovery=str(alternate.with_name("different.xlsx"))))
        self.assertEqual(window.view_state, "unknown")
        self.assertIsNone(window.primary_button)

    def test_plan_always_displays_undo_warning_without_engine_warnings(self) -> None:
        window = self._window(execution_enabled=True)
        self._plan(window)
        self.assertFalse(window._plan_result.warnings)
        self.assertIn("Excel Undo history may be cleared", self._texts(window.content))
        self.assertNotIn("conversion_execute", [call["phase"] for call in self.coordinator.calls])

    def test_single_clicks_toggle_disjoint_physical_columns(self) -> None:
        window = self._window()
        self._preflight(window, *(
            preflight_column(index, letter, "ID")
            for index, letter in enumerate("ABCDEF", 1)
        ))
        window.window.update_idletasks()
        picker = window.columns_listbox
        for index in (1, 3, 5):
            x, y, width, height = picker.bbox(index)
            picker.event_generate("<Button-1>", x=x + 3, y=y + height // 2)
            picker.event_generate("<ButtonRelease-1>", x=x + 3, y=y + height // 2)
        self.assertEqual(window._selected_columns(), (2, 4, 6))
        x, y, width, height = picker.bbox(3)
        picker.event_generate("<Button-1>", x=x + 3, y=y + height // 2)
        self.assertEqual(window._selected_columns(), (2, 6))
        window.review_button.invoke()
        self.assertEqual(self.coordinator.calls[-1]["request"]["arguments"]["columns"], [2, 6])

    def test_compact_review_shows_human_effects_and_hides_technical_details(self) -> None:
        window = self._window(execution_enabled=True)
        self._plan(window, precision=1)
        call = plan_result(precision=1)
        result = replace(
            call.result,
            target=replace(call.result.target, full_path=r"D:\Données\Budget.xlsx"),
            warnings=call.result.warnings + (LiveExcelWarning("live.other", "Check the displayed values.", {}),),
        )
        window._show_plan(result)
        text = self._texts(window.content)
        self.assertIn("1 cell to convert to text", text)
        self.assertIn("Budget.xlsx · Données · Column A", text)
        self.assertIn(r"D:\Données\Budget.xlsx", text)
        self.assertIn("1 already text · 0 empty · 0 blocked · 1 precision risks", text)
        self.assertIn("A2: 1.2E+5 → 120000", text)
        self.assertIn("Check the displayed values.", text)
        self.assertNotIn(FINGERPRINT, text)
        self.assertNotIn("Fixed bounds", text)
        self.assertEqual(window.recovery_var.get(), RECOVERY)
        self.assertEqual(window.plan_details_frame.winfo_manager(), "")
        self.assertIn(FINGERPRINT, window.result_text.get("1.0", "end-1c"))
        self.assertEqual(window.primary_button.cget("text"), "Convert 1 cell to text")
        self.assertIs(window.primary_button.master, window.footer)

    def test_details_disclosure_keeps_acknowledgement_and_sends_no_engine_request(self) -> None:
        window = self._window(execution_enabled=True)
        self._plan(window, precision=1)
        window.precision_ack_var.set(True)
        window._update_execute_state()
        count = len(self.coordinator.calls)
        plan = window._plan_result
        for showing in (True, False, True, False):
            window.plan_details_button.invoke()
            self.assertEqual(bool(window.plan_details_frame.winfo_manager()), showing)
            self.assertEqual(len(self.coordinator.calls), count)
            self.assertIs(window._plan_result, plan)
            self.assertTrue(window.precision_ack_var.get())
            self.assertFalse(window.primary_button.instate(["disabled"]))
        window.primary_button.invoke()
        self.assertEqual(
            self.coordinator.calls[-1]["request"]["arguments"]["expected_plan_fingerprint"], FINGERPRINT,
        )

    def test_change_columns_reuses_inspection_and_requires_a_fresh_plan(self) -> None:
        window = self._window(execution_enabled=True)
        self._preflight(window, preflight_column(1, "A", "ID"), preflight_column(2, "B", "ID"))
        window.columns_listbox.selection_set(0)
        window._column_selection_changed()
        window.primary_button.invoke()
        self._complete(window, plan_result(precision=1))
        window.precision_ack_var.set(True)
        window._update_execute_state()
        count = len(self.coordinator.calls)
        self._button(window.content, "Change columns").invoke()
        self.assertEqual(window.view_state, "select_columns")
        self.assertEqual(len(self.coordinator.calls), count)
        self.assertFalse(window._plan_correlated)
        self.assertIsNone(window._plan_result)
        self.assertFalse(window.precision_ack_var.get())
        self.assertEqual(window._selected_columns(), (1,))
        window.columns_listbox.selection_clear(0)
        window.columns_listbox.selection_set(1)
        window._column_selection_changed()
        window.primary_button.invoke()
        self.assertEqual(self.coordinator.calls[-1]["phase"], "conversion_plan")
        self.assertEqual(self.coordinator.calls[-1]["request"]["arguments"]["columns"], [2])
        self._complete(window, plan_result(columns=(2,), precision=1))
        self.assertTrue(window.primary_button.instate(["disabled"]))

    def test_conversion_button_stays_visible_with_details_and_recovery_replanning_resets_ack(self) -> None:
        window = self._window(execution_enabled=True)
        self._plan(window, precision=1)
        window.precision_ack_var.set(True)
        window._update_execute_state()
        window.plan_details_button.invoke()
        window.window.geometry("700x480")
        window.window.update_idletasks()
        window.canvas.yview_moveto(1)
        window.window.update_idletasks()
        button = window.primary_button
        self.assertTrue(button.winfo_ismapped())
        self.assertGreaterEqual(button.winfo_rooty(), window.window.winfo_rooty())
        self.assertLessEqual(
            button.winfo_rooty() + button.winfo_height(),
            window.window.winfo_rooty() + window.window.winfo_height(),
        )
        self.assertGreaterEqual(button.winfo_rootx(), window.window.winfo_rootx())
        self.assertLessEqual(
            button.winfo_rootx() + button.winfo_width(),
            window.window.winfo_rootx() + window.window.winfo_width(),
        )
        alternate = r"D:\work\Données recovery.xlsx"
        with patch(
            "context_palette.excel_live_text_conversion_window.filedialog.asksaveasfilename",
            return_value=alternate,
        ):
            self._button(window.content, "Change…").invoke()
        self.assertIsNone(window.primary_button)
        self._complete(window, plan_result(precision=1, recovery=alternate))
        self.assertFalse(window.precision_ack_var.get())
        self.assertTrue(window.primary_button.instate(["disabled"]))
        self.assertEqual(window.recovery_var.get(), alternate)
        self.assertEqual(window.plan_details_frame.winfo_manager(), "")

    def test_long_exact_paths_wrap_at_minimum_width_with_shared_theme(self) -> None:
        configure_theme(self.root)
        window = self._window(execution_enabled=True)
        self._plan(window, precision=1)
        long_path = "D:\\" + "Données avec un nom long\\" * 7 + "Budget.xlsx"
        result = replace(
            window._plan_result,
            target=replace(window._plan_result.target, full_path=long_path),
            recovery=replace(window._plan_result.recovery, path=long_path.replace(".xlsx", ".recovery.xlsx")),
            effect=replace(window._plan_result.effect, eligible=1_000_000),
        )
        window._show_plan(result)
        for width in (700, 1000, 700):
            window.window.geometry(f"{width}x480")
            window.window.update_idletasks()
            for label in window._responsive_review_labels:
                self.assertLessEqual(label.winfo_reqwidth(), label.winfo_width())
                self.assertLessEqual(int(label.cget("wraplength")), window.canvas.winfo_width() - 12)
            self.assertIn(long_path, self._texts(window.content))
            self.assertEqual(window.recovery_var.get(), result.recovery.path)
            button = window.primary_button
            self.assertGreaterEqual(button.winfo_rootx(), window.window.winfo_rootx())
            self.assertLessEqual(
                button.winfo_rootx() + button.winfo_width(),
                window.window.winfo_rootx() + window.window.winfo_width(),
            )

    def test_precision_ack_and_uat_flag_jointly_gate_exact_execution(self) -> None:
        disabled = self._window(execution_enabled=False)
        self._plan(disabled, precision=1)
        disabled.precision_ack_var.set(True)
        disabled._update_execute_state()
        self.assertTrue(disabled.primary_button.instate(["disabled"]))
        self.assertIn("Conversion is not enabled in this build", disabled.status_var.get())
        self.assertNotIn("UAT", disabled.status_var.get())
        self._close(disabled)
        self.coordinator = FakeCoordinator()

        window = self._window(execution_enabled=True)
        self._plan(window, precision=1)
        self.assertTrue(window.primary_button.instate(["disabled"]))
        window.precision_ack_var.set(True)
        window._update_execute_state()
        self.assertFalse(window.primary_button.instate(["disabled"]))
        window.primary_button.invoke()

        request = self.coordinator.calls[-1]["request"]
        self.assertEqual(request["operation"], "convert_live_column_representation")
        self.assertEqual(request["arguments"]["expected_plan_fingerprint"], FINGERPRINT)
        self.assertEqual(request["arguments"]["workbook_token"], "live-one")
        self.assertEqual(request["arguments"]["worksheet"], "Données")
        self.assertEqual(request["arguments"]["columns"], [1])
        self.assertEqual(request["arguments"]["recovery_path"], RECOVERY)
        self.assertIs(request["arguments"]["acknowledge_irreversible_precision_risk"], True)

    def test_success_is_verified_and_offers_recovery_and_return_to_excel(self) -> None:
        window = self._window(
            execution_enabled=True,
            source_window_handle=4321,
            source_process_id=42,
        )
        self._plan(window)
        window.primary_button.invoke()
        self._complete(window, execution_result())

        self.assertEqual(window.view_state, "succeeded")
        self.assertIn("Changed: 1", window.result_text.get("1.0", "end-1c"))
        self.assertIn("Review recovery workbook", self._texts(window.content))
        self.assertIn("Return to Excel", self._texts(window.content))
        self._button(window.content, "Review recovery workbook").invoke()
        self.file_opener.assert_called_once_with(Path(RECOVERY))

        self._button(window.content, "Return to Excel").invoke()
        self.return_to_source.assert_called_once_with(4321)

    def test_clean_failure_and_partial_failure_have_distinct_recovery_guidance(self) -> None:
        for state, expected in (
            ("failed", "No workbook mutation began"),
            ("partial_failure", "Possible partial modification"),
        ):
            with self.subTest(state=state):
                window = self._window(execution_enabled=True)
                self._plan(window)
                window.primary_button.invoke()
                self._complete(window, execution_result(state))
                self.assertEqual(window.view_state, state)
                self.assertIn(expected, window.status_var.get())
                self.assertIn("Review recovery workbook", self._texts(window.content))
                self.assertIsNone(window.primary_button)
                self._close(window)
                self.coordinator = FakeCoordinator()

    def test_partial_failure_with_clean_workbook_never_claims_no_mutation(self) -> None:
        window = self._window(execution_enabled=True)
        self._plan(window)
        window.primary_button.invoke()
        call = execution_result("partial_failure")
        assert isinstance(call.result, LiveColumnConversionResult)
        result = replace(
            call.result, workbook_dirty=False, changed_cells=0,
            already_compliant_cells=0, blank_cells=0, columns_completed=(),
        )
        self._complete(window, replace(call, result=result))
        self.assertEqual(window.view_state, "partial_failure")
        text = window.result_text.get("1.0", "end-1c")
        self.assertIn("Unsaved changes reported by Excel: No", text)
        self.assertNotIn("No mutation", text)
        self.assertIn("Possible partial modification", window.status_var.get())
        self.assertIsNone(window.primary_button)
        self.assertEqual(
            [call["phase"] for call in self.coordinator.calls].count("conversion_execute"), 1,
        )

    def test_outer_stale_and_recovery_collision_are_known_pre_effect_without_retry(self) -> None:
        for code in (
            "conflict.live_conversion_plan_stale",
            "conflict.live_conversion_scope_stale",
            "conflict.recovery_output_exists",
        ):
            with self.subTest(code=code):
                window = self._window(execution_enabled=True)
                self._plan(window)
                window.primary_button.invoke()
                self._complete(
                    window,
                    AutomationCallResult(
                        "conversion_execute",
                        "outer_error",
                        True,
                        2,
                        error=AutomationCallError(
                            code,
                            "conflict",
                            "The reviewed state changed.",
                            True,
                            {},
                        ),
                    ),
                )
                self.assertEqual(window.view_state, "failed_before_effect")
                texts = self._texts(window.content)
                self.assertIn("Refresh open workbooks", texts)
                self.assertIsNone(window.primary_button)
                self._close(window)
                self.coordinator = FakeCoordinator()

    def test_unknown_and_mismatched_receipt_never_offer_automatic_retry(self) -> None:
        cases = (
            AutomationCallResult(
                "conversion_execute",
                "conversion_execute_unknown",
                True,
                None,
                reason="The process timed out.",
            ),
            execution_result(token="different"),
        )
        for result in cases:
            with self.subTest(result=result):
                window = self._window(execution_enabled=True)
                self._plan(window)
                window.primary_button.invoke()
                self._complete(window, result)
                self.assertEqual(window.view_state, "unknown")
                texts = self._texts(window.content)
                self.assertIn("inspect Excel", texts)
                self.assertIn("Reviewed recovery location", texts)
                self.assertIn(RECOVERY, texts)
                self.assertIsNone(window.primary_button)
                self._close(window)
                self.coordinator = FakeCoordinator()

    def test_busy_or_pending_completion_blocks_close(self) -> None:
        closed = Mock()
        window = self._window(on_close=closed)
        self.assertTrue(window.busy)
        self.assertFalse(window.close())
        closed.assert_not_called()

        self.coordinator.running = False
        self.coordinator.completion_pending = True
        self.assertFalse(window.close())
        closed.assert_not_called()

    def test_return_button_requires_matching_inventory_process_and_footer_stays_fixed(self) -> None:
        window = self._window(source_window_handle=99, source_process_id=999)
        self._inventory(window, workbook())
        self.assertNotIn("Return to Excel", self._texts(window.content))
        self.assertIs(window.close_button.master, window.status_label.master)
        self.assertIsNot(window.close_button.master, window.content)
        original_scaling = float(self.root.tk.call("tk", "scaling"))
        try:
            for scaling in (1.0, 1.25, 1.5):
                self.root.tk.call("tk", "scaling", scaling)
                window.window.update_idletasks()
                self.assertGreater(window.close_button.winfo_reqheight(), 0)
                self.assertLessEqual(
                    window.window.winfo_height(),
                    window.window.winfo_screenheight(),
                )
        finally:
            self.root.tk.call("tk", "scaling", original_scaling)

    @staticmethod
    def _texts(widget: tk.Misc) -> str:
        values: list[str] = []
        pending = list(widget.winfo_children())
        while pending:
            child = pending.pop()
            pending.extend(child.winfo_children())
            try:
                text = child.cget("text")
            except tk.TclError:
                continue
            if text:
                values.append(str(text))
        return "\n".join(values)

    @staticmethod
    def _button(widget: tk.Misc, text: str) -> ttk.Button:
        pending = list(widget.winfo_children())
        while pending:
            child = pending.pop()
            pending.extend(child.winfo_children())
            if isinstance(child, ttk.Button) and child.cget("text") == text:
                return child
        raise AssertionError(f"Button not found: {text}")


if __name__ == "__main__":
    unittest.main()
