from __future__ import annotations

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
            {1: "A", 2: "B", 3: "C"}.get(index, "Z"),
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

    def _window(self, **kwargs) -> ExcelLiveTextConversionWindow:
        window = ExcelLiveTextConversionWindow(
            self.root,
            settings_path=kwargs.pop("settings_path", self.settings),
            status_setter=self.status,
            coordinator=self.coordinator,  # type: ignore[arg-type]
            file_opener=self.file_opener,
            folder_opener=self.folder_opener,
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
        window.primary_button.invoke()
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
        self.assertFalse(window.primary_button.instate(["disabled"]))

    def test_blocked_plan_disables_execute_and_renders_blocker(self) -> None:
        window = self._window(execution_enabled=True)
        self._plan(window, can_execute=False)

        self.assertEqual(window.view_state, "plan_blocked")
        self.assertTrue(window.primary_button.instate(["disabled"]))
        self.assertIn("formulas", window.result_text.get("1.0", "end-1c"))
        self.assertNotIn("retry", window.primary_button.cget("text").casefold())

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
            self._button(window.content, "Choose another recovery path…").invoke()

        request = self.coordinator.calls[-1]["request"]
        self.assertEqual(request["arguments"]["recovery_path"], alternate)
        self.assertFalse(Path(alternate).exists())

    def test_precision_ack_and_uat_flag_jointly_gate_exact_execution(self) -> None:
        disabled = self._window(execution_enabled=False)
        self._plan(disabled, precision=1)
        disabled.precision_ack_var.set(True)
        disabled._update_execute_state()
        self.assertTrue(disabled.primary_button.instate(["disabled"]))
        self.assertIn("execution is disabled", disabled.uat_banner.cget("text").casefold())
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

        with patch(
            "context_palette.excel_live_text_conversion_window.focus_window",
            return_value=True,
        ) as focus:
            self._button(window.content, "Return to Excel").invoke()
        focus.assert_called_once_with(4321)

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
                self.assertNotIn("Execute reviewed", self._texts(window.content))
                self._close(window)
                self.coordinator = FakeCoordinator()

    def test_outer_stale_and_recovery_collision_are_known_pre_effect_without_retry(self) -> None:
        for code in (
            "conflict.live_conversion_plan_stale",
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
                self.assertNotIn("Execute reviewed", texts)
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
                self.assertNotIn("Execute reviewed", texts)
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
