from __future__ import annotations

from dataclasses import asdict, replace
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
    LiveDataRows,
    LiveExcelWarning,
    LiveTextToColumnsColumnReceipt,
    LiveTextToColumnsColumnScope,
    LiveTextToColumnsFailure,
    LiveTextToColumnsResult,
    LiveTextToColumnsTarget,
    parse_automation_response,
)
from context_palette.excel_live_column_selector import LiveExcelColumnSelector
from context_palette.excel_live_target_selector import LiveExcelTargetSelector
from context_palette.excel_live_text_conversion_window import ExcelLiveTextConversionWindow
from context_palette.excel_live_text_to_columns_window import ExcelLiveTextToColumnsWindow
from context_palette.style import configure_theme
from tests.test_excel_automation import _envelope
from tests.test_excel_live_text_conversion_window import (
    FakeCoordinator,
    capability,
    inventory_result,
    preflight_column,
    preflight_result,
    workbook,
)


REQUIRED = (
    "inventory_live_excel",
    "preflight_live_columns",
    "apply_live_text_to_columns_as_text",
)


def capabilities_result(*, missing=None, mismatch=None, unavailable=None):
    return AutomationCallResult(
        "capabilities", "capabilities_succeeded", True, 0,
        result=DescribeCapabilitiesResult(tuple(
            capability(operation, version="2.0" if operation == mismatch else "1.0",
                       available=operation != unavailable)
            for operation in REQUIRED if operation != missing
        )),
    )


def headers_result(*columns, next_offset=None, headers_only=True):
    call = preflight_result(
        *columns, truncated=next_offset is not None, next_offset=next_offset,
        columns_total=7 if next_offset is not None else len(columns),
    )
    return replace(call, result=replace(
        call.result, headers_only=headers_only,
        data_rows=LiveDataRows(2, 20051, 20050, 0, True),
        columns=tuple(replace(
            column, cells_examined=0,
            classifications=replace(column.classifications, numeric=0, text=0),
        ) for column in call.result.columns),
    ))


def parse_native_result(result):
    document = asdict(replace(result, warnings=()))
    document.pop("warnings")
    warnings = [
        {"code": warning.code, "message": warning.message, "details": dict(warning.details)}
        for warning in result.warnings
    ]
    return parse_automation_response(
        phase="native_text", request_id="synthetic-native", return_code=0,
        stdout=_envelope("apply_live_text_to_columns_as_text", "synthetic-native", document, warnings=warnings),
    )


def native_result(state="succeeded", *, columns=(3, 7, 5), dirty=False, failed_after_empty=False):
    scopes = tuple(LiveTextToColumnsColumnScope(
        column, letter, None if column == 5 else 2,
        None if column == 5 else 20051,
        None if column == 5 else f"${letter}$2:${letter}$20051", column == 5,
    ) for column, letter in ((column, {3: "C", 5: "E", 7: "G"}[column]) for column in columns))
    if state == "succeeded":
        receipt_columns = columns
        current = None
        failure = None
    elif state == "failed":
        receipt_columns = columns[:1] if failed_after_empty else ()
        current = columns[1] if failed_after_empty else columns[0]
        if not failed_after_empty:
            scopes = scopes[:1]
        failure = LiveTextToColumnsFailure(
            "live.formula_scope_blocked", "The selected column contains a formula.",
            "revalidate" if failed_after_empty else "preflight", False, False, False,
            current, next(scope.data_range for scope in scopes if scope.column_index == current),
            None, None, None,
        )
    else:
        receipt_columns = columns[:1]
        current = columns[1]
        failure = LiveTextToColumnsFailure(
            "live.native_call_unknown" if state == "unknown" else "live.application_not_ready",
            "Inspect the current column." if state == "unknown" else "Excel is no longer ready.",
            "text_to_columns" if state == "unknown" else "revalidate",
            False, state == "unknown", state == "unknown", current,
            next(scope.data_range for scope in scopes if scope.column_index == current),
            None, None, None,
        )
    receipts = tuple(LiveTextToColumnsColumnReceipt(
        scope.column_index, scope.column_letter, scope.data_range,
        "skipped_empty" if scope.empty else "completed", not scope.empty,
    ) for scope in scopes if scope.column_index in receipt_columns)
    result = LiveTextToColumnsResult(
        state=state,
        target=LiveTextToColumnsTarget(42, "live-one", "Budget.xlsx", r"D:\work\Budget.xlsx", "Données", 1, columns),
        column_scopes=scopes, column_receipts=receipts,
        columns_completed=tuple(r.column_index for r in receipts if r.state == "completed"),
        columns_skipped_empty=tuple(r.column_index for r in receipts if r.state == "skipped_empty"),
        current_column=current,
        current_range=None if failure is None else failure.data_range,
        pending_columns=tuple(column for column in columns if column not in receipt_columns and column != current),
        mutation_started=any(r.mutation_started for r in receipts) or state == "unknown",
        workbook_dirty_before=True, workbook_dirty=dirty,
        recovery_created=False, save_invoked=False, workbook_saved=False,
        workbook_closed=False, application_closed=False, failure=failure,
        warnings=(LiveExcelWarning("live.no_backup", "No backup is created; Excel Undo may be affected.", {}),),
    )
    return parse_native_result(result)


class ExcelLiveTextToColumnsWindowTests(unittest.TestCase):
    def setUp(self):
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
        self.settings.write_text(json.dumps({"launcher_path": str(self.launcher)}), encoding="utf-8")
        self.coordinator = FakeCoordinator()
        self.status = Mock()
        self.return_to_source = Mock(return_value=True)
        # Even accidental client use must remain synthetic and cannot launch Office.
        self.process_start = patch("context_palette.excel_automation.subprocess.Popen", side_effect=AssertionError("No process is authorized in UI tests"))
        self.process_start.start()
        self.addCleanup(self.process_start.stop)

    def _window(self, **kwargs):
        window = ExcelLiveTextToColumnsWindow(
            self.root, settings_path=kwargs.pop("settings_path", self.settings),
            status_setter=self.status, coordinator=self.coordinator,
            return_to_source=self.return_to_source, **kwargs,
        )
        self.addCleanup(self._close, window)
        self.root.update()
        return window

    @staticmethod
    def _close(window):
        window.coordinator.running = False
        window.coordinator.completion_pending = False
        window.coordinator._callback = None
        window.close()

    def _complete(self, window, result):
        self.coordinator.complete(result)
        if window._poll_after_id is not None:
            window.window.after_cancel(window._poll_after_id)
            window._poll_after_id = None
        window._poll()

    def _inventory(self, window, *books):
        self._complete(window, capabilities_result())
        self.assertEqual(self.coordinator.calls[-1]["phase"], "inventory")
        self._complete(window, inventory_result(*(books or (workbook(),))))

    def _headers(self, window):
        self._inventory(window)
        window.primary_button.invoke()
        self.assertEqual(self.coordinator.calls[-1]["phase"], "preflight")
        self._complete(window, headers_result(
            preflight_column(3, "C", "ID"), preflight_column(5, "E", None), preflight_column(7, "G", "ID"),
        ))

    def _select(self, window, *indices):
        for index in indices:
            window.columns_listbox.selection_set(index)
            window._column_selection_changed()

    def _execute(self, window):
        self._headers(window)
        self._select(window, 0, 2, 1)
        window.primary_button.invoke()
        self.assertEqual(self.coordinator.calls[-1]["phase"], "native_text")

    def test_shared_scaffolding_and_optional_setup(self):
        window = self._window(settings_path=self.data / "missing.json")
        self.assertIsInstance(window, ExcelLiveTextConversionWindow)
        self.assertEqual(window.window.title(), "Text to Columns → Text (fast)")
        self.assertEqual(window.view_state, "setup")
        self.assertIn("Displayed notation may remain unchanged.", self._texts(window.window))
        self.assertEqual(self.coordinator.calls, [])

    def test_every_exact_missing_mismatched_or_unavailable_capability_stops_before_inventory(self):
        for issue in ("missing", "mismatch", "unavailable"):
            for operation in REQUIRED:
                with self.subTest(issue=issue, operation=operation):
                    window = self._window()
                    self._complete(window, capabilities_result(**{issue: operation}))
                    self.assertEqual(window.view_state, "capability_unavailable")
                    self.assertEqual([call["phase"] for call in self.coordinator.calls], ["capabilities"])
                    self.assertNotIn("Convert", self._texts(window.content))
                    self._close(window)
                    self.coordinator = FakeCoordinator()

    def test_exact_capability_lookup_accepts_multiple_versions_without_checked_capabilities(self):
        window = self._window()
        result = capabilities_result().result
        self._complete(window, replace(capabilities_result(), result=replace(
            result, capabilities=(capability(REQUIRED[2], version="2.0"),) + result.capabilities,
        )))
        self.assertEqual(self.coordinator.calls[-1]["phase"], "inventory")

    def test_headers_only_request_and_truncated_zero_counts_do_not_authorize_mutation(self):
        window = self._window()
        self._headers(window)
        arguments = self.coordinator.calls[-1]["request"]["arguments"]
        self.assertIs(arguments["headers_only"], True)
        self.assertEqual(arguments["header_row"], 1)
        self.assertIsNone(arguments["columns"])
        self.assertIsInstance(window.target_selector, type(None))
        self.assertIsInstance(window.column_selector, LiveExcelColumnSelector)
        self.assertIs(window.columns_listbox, window.column_selector.listbox)
        self.assertEqual(window.view_state, "select_columns")
        self.assertTrue(window.primary_button.instate(["disabled"]))
        self._select(window, 0)
        self.assertFalse(window.primary_button.instate(["disabled"]))
        self.assertEqual([call["phase"] for call in self.coordinator.calls], ["capabilities", "inventory", "preflight"])
        text = self._texts(window.content)
        self.assertIn("No backup is created; Excel Undo may be affected.", text)
        self.assertNotIn("data rows examined", text)
        self.assertNotIn("Review", text)
        self.assertNotIn("recovery", text.lower())
        self.assertIsNone(window.review_button)
        self.assertIsNone(window.plan_details_frame)
        self.assertFalse(any(isinstance(widget, ttk.Checkbutton) for widget in window.content.winfo_children()))

    def test_headers_only_mismatch_refuses_conversion_without_claiming_mutation(self):
        for issue in ("echo", "token", "process", "sheet", "header"):
            with self.subTest(issue=issue):
                window = self._window()
                self._inventory(window)
                self.assertIsInstance(window.target_selector, LiveExcelTargetSelector)
                window.primary_button.invoke()
                call = headers_result(preflight_column(3, "C", None))
                result = call.result
                if issue == "echo":
                    result = replace(result, headers_only=False)
                elif issue in {"token", "process"}:
                    result = replace(result, workbook=replace(
                        result.workbook, **({"token": "stale"} if issue == "token" else {"process_id": 999}),
                    ))
                else:
                    result = replace(result, **({"worksheet": "Other"} if issue == "sheet" else {"header_row": 2}))
                self._complete(window, replace(call, result=result))
                self.assertEqual(window.view_state, "selection_unavailable")
                self.assertIsNone(window.primary_button)
                self.assertIn("No conversion request was sent", window.result_text.get("1.0", tk.END))
                self.assertNotIn("Possibly changed columns", window.result_text.get("1.0", tk.END))
                self._close(window)
                self.coordinator = FakeCoordinator()

    def test_convert_does_not_wait_for_unselected_header_pages(self):
        window = self._window()
        self._inventory(window)
        window.primary_button.invoke()
        self._complete(window, headers_result(preflight_column(3, "C", "ID"), next_offset=3))
        self._select(window, 0)
        window.primary_button.invoke()
        self.assertEqual(self.coordinator.calls[-1]["phase"], "native_text")
        self.assertEqual(self.coordinator.calls[-1]["request"]["arguments"]["columns"], [3])

    def test_process_start_failure_is_presented_as_no_conversion_started(self):
        window = self._window()
        self._headers(window)
        self._select(window, 0)
        window.primary_button.invoke()
        self._complete(window, AutomationCallResult("native_text", "start_failed", False, None,
                                                   reason="The engine could not start."))
        self.assertEqual(window.view_state, "failed_before_effect")
        self.assertIn("No conversion was started", window.result_text.get("1.0", tk.END))
        self.assertNotIn("Possibly changed", window.result_text.get("1.0", tk.END))

    def test_paging_and_toggle_preserve_ordered_physical_columns(self):
        window = self._window()
        self._inventory(window)
        window.primary_button.invoke()
        self._complete(window, headers_result(preflight_column(3, "C", "ID"), next_offset=3))
        self._select(window, 0)
        self.assertFalse(window.primary_button.instate(["disabled"]))
        self._button(window.content, "Load more columns").invoke()
        self.assertEqual(self.coordinator.calls[-1]["request"]["arguments"]["column_offset"], 3)
        self._complete(window, headers_result(preflight_column(5, "E", None), preflight_column(7, "G", "ID")))
        self._select(window, 2, 1)
        self.assertEqual(window._selected_columns(), (3, 7, 5))
        window.columns_listbox.selection_clear(2)
        window._column_selection_changed()
        self.assertEqual(window._selected_columns(), (3, 5))
        self._select(window, 2)
        self.assertEqual(window._selected_columns(), (3, 5, 7))
        window.columns_listbox.selection_clear(1)
        window._column_selection_changed()
        self._select(window, 1)
        self.assertEqual(window._selected_columns(), (3, 7, 5))
        window.primary_button.invoke()
        self.assertEqual(self.coordinator.calls[-1]["request"]["arguments"]["columns"], [3, 7, 5])

    def test_one_explicit_convert_sends_exact_single_batch_without_planner_or_lifecycle_ui(self):
        window = self._window()
        with patch.object(ExcelLiveTextConversionWindow, "_start_plan", side_effect=AssertionError("Planner must not run")):
            self._execute(window)
            window._execute()
        call = self.coordinator.calls[-1]
        request = call["request"]
        self.assertEqual(request["schema_version"], "1.0")
        self.assertEqual(request["operation_version"], "1.0")
        self.assertEqual(request["operation"], "apply_live_text_to_columns_as_text")
        self.assertEqual(request["arguments"], {
            "workbook_token": "live-one", "worksheet": "Données", "columns": [3, 7, 5], "header_row": 1,
        })
        self.assertEqual(call["timeout_seconds"], 180.0)
        self.assertEqual([call["phase"] for call in self.coordinator.calls].count("native_text"), 1)
        self.assertFalse(any("conversion" in call["phase"] for call in self.coordinator.calls))
        self.assertIsNone(window._plan_result)
        self.assertIsNone(window._plan_invocation)

    def test_mouse_gestures_preserve_selection_order_with_duplicate_and_blank_headers(self):
        window = self._window()
        self._headers(window)
        window.window.update()
        picker = window.columns_listbox
        self.assertEqual(picker.get(0), "3 · C · ID")
        self.assertEqual(picker.get(1), "5 · E · (blank header)")
        self.assertEqual(picker.get(2), "7 · G · ID")
        for index in (0, 2, 1):
            x, y, _width, height = picker.bbox(index)
            picker.event_generate("<Button-1>", x=x + 3, y=y + height // 2)
            picker.event_generate("<ButtonRelease-1>", x=x + 3, y=y + height // 2)
            window.window.update()
        self.assertEqual(window._selected_columns(), (3, 7, 5))

    def test_success_renders_completed_skipped_empty_lifecycle_and_warnings(self):
        window = self._window(source_window_handle=4321, source_process_id=42)
        self._execute(window)
        self._complete(window, native_result())
        self.assertEqual(window.view_state, "succeeded")
        text = window.result_text.get("1.0", "end-1c")
        for expected in ("Completed: C, G", "Skipped because empty: E", "Pending columns: None",
                         "Excel remains open and was not saved.", "before: Yes", "after: No",
                         "flag does not prove whether cells changed", "No backup is created; Excel Undo may be affected."):
            self.assertIn(expected, text)
        self.assertIsNone(window.primary_button)
        self._button(window.content, "Return to Excel").invoke()
        self.return_to_source.assert_called_once_with(4321)
        self.assertNotIn("Review recovery workbook", self._texts(window.content))

    def test_formula_failure_and_known_outer_ready_failure_claim_no_started_mutation(self):
        cases = (native_result("failed"), AutomationCallResult(
            "native_text", "native_text_failed", True, 4,
            error=AutomationCallError("conflict.live_excel_busy", "conflict", "Excel is busy.", True, {}),
        ))
        for call in cases:
            with self.subTest(call=call):
                window = self._window()
                self._execute(window)
                self._complete(window, call)
                self.assertIn(window.view_state, {"failed", "failed_before_effect"})
                self.assertIn("No", window.status_var.get())
                self.assertNotIn("may already have changed", self._texts(window.content))
                self.assertIsNone(window.primary_button)
                self.assertEqual([call["phase"] for call in self.coordinator.calls].count("native_text"), 1)
                self._close(window)
                self.coordinator = FakeCoordinator()

    def test_all_empty_success_is_a_valid_noop(self):
        window = self._window()
        self._headers(window)
        self._select(window, 1)
        window.primary_button.invoke()
        call = native_result(columns=(5,))
        self.assertFalse(call.result.mutation_started)
        self._complete(window, call)
        self.assertEqual(window.view_state, "succeeded")
        text = window.result_text.get("1.0", "end-1c")
        self.assertIn("Completed: None", text)
        self.assertIn("Skipped because empty: E", text)
        self.assertNotIn("cells changed", window.status_var.get())

    def test_revalidation_after_skipped_empty_can_fail_without_mutation(self):
        window = self._window()
        self._headers(window)
        self._select(window, 1, 2)
        window.primary_button.invoke()
        self._complete(window, native_result("failed", columns=(5, 7), failed_after_empty=True))
        self.assertEqual(window.view_state, "failed")
        self.assertIn("Skipped because empty: E", window.result_text.get("1.0", "end-1c"))
        self.assertIn("No native call began", window.status_var.get())

    def test_partial_and_valid_unknown_preserve_earlier_current_and_pending_distinctions(self):
        for state in ("partial_failure", "unknown"):
            with self.subTest(state=state):
                window = self._window(source_window_handle=4321, source_process_id=42)
                self._execute(window)
                self._complete(window, native_result(state))
                self.assertEqual(window.view_state, state)
                text = window.result_text.get("1.0", "end-1c")
                for expected in ("Completed: C", "Current column: G", "Current range: $G$2:$G$20051", "Pending columns: E"):
                    self.assertIn(expected, text)
                self.assertNotIn("No mutation", text)
                self.assertIsNone(window.primary_button)
                if state == "unknown":
                    self.assertIn("current column may already have changed", text)
                    self.assertNotIn("Possibly changed columns: C, G, E", text)
                    self.assertNotIn("Refresh open workbooks", self._texts(window.content))
                    self.assertEqual(self._button_labels(window.content), ["Return to Excel"])
                self._close(window)
                self.coordinator = FakeCoordinator()

    def test_transport_timeout_loss_and_untrusted_receipts_require_inspection_of_all_columns(self):
        success = native_result()
        target = success.result.target
        mismatches = (
            replace(target, process_id=999), replace(target, workbook_token="other"),
            replace(target, workbook_name="Other.xlsx"), replace(target, full_path=r"D:\other.xlsx"),
            replace(target, worksheet="Other"), replace(target, header_row=2),
            replace(target, physical_columns=(3, 5, 7)),
        )
        cases = [AutomationCallResult("native_text", "native_text_unknown", True, None, reason=reason)
                 for reason in ("Timeout", "Process lost", "Malformed response", "Missing result")]
        cases.extend(replace(success, result=replace(success.result, target=other)) for other in mismatches)
        cases.extend((replace(success, phase="conversion_execute"), replace(success, classification="native_text_failed")))
        cases.extend((
            parse_native_result(replace(success.result, column_receipts=())),
            parse_native_result(replace(success.result, workbook_saved=True)),
            parse_native_result(replace(success.result, columns_completed=(3,))),
        ))
        for call in cases:
            with self.subTest(call=call):
                window = self._window(source_window_handle=4321, source_process_id=42)
                self._execute(window)
                self._complete(window, call)
                self.assertEqual(window.view_state, "unknown")
                text = window.result_text.get("1.0", "end-1c")
                self.assertIn("Possibly changed columns: C, G, E", text)
                self.assertNotIn("Completed:", text)
                self.assertEqual(self._button_labels(window.content), ["Return to Excel"])
                window._execute()
                self.assertEqual([call["phase"] for call in self.coordinator.calls].count("native_text"), 1)
                self._close(window)
                self.coordinator = FakeCoordinator()

    def test_obsolete_callbacks_cannot_replace_current_ticket_or_closed_view(self):
        window = self._window()
        self._execute(window)
        callback = self.coordinator._callback
        window._pending_execute_ticket = object()
        callback(native_result())
        self.assertEqual(window.view_state, "executing")
        self._close(window)
        callback(native_result())
        self.assertTrue(window._closed)

    def test_busy_and_pending_completion_refuse_close_and_return_requires_captured_pid(self):
        window = self._window(source_window_handle=99, source_process_id=999)
        self.assertFalse(window.close())
        self.coordinator.running = False
        self.coordinator.completion_pending = True
        self.assertFalse(window.close())
        self.coordinator.completion_pending = False
        self.coordinator.running = True
        self._execute(window)
        self._complete(window, native_result())
        self.assertNotIn("Return to Excel", self._texts(window.content))
        self.return_to_source.assert_not_called()
        self.assertTrue(window.close())

    def test_dpi_simulation_keeps_footer_convert_and_close_visible_and_restores_scale(self):
        configure_theme(self.root)
        window = self._window()
        self._headers(window)
        self._select(window, 0)
        original_scaling = float(self.root.tk.call("tk", "scaling"))
        try:
            for percent in (1.0, 1.25, 1.5):
                self.root.tk.call("tk", "scaling", original_scaling * percent)
                window.window.geometry("700x480")
                window.window.update()
                self.assertIs(window.primary_button.master, window.footer)
                for button in (window.primary_button, window.close_button):
                    self.assertTrue(button.winfo_ismapped())
                    self.assertGreaterEqual(button.winfo_rooty(), window.window.winfo_rooty())
                    self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), window.window.winfo_rooty() + window.window.winfo_height())
                    self.assertGreaterEqual(button.winfo_rootx(), window.window.winfo_rootx())
                    self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), window.window.winfo_rootx() + window.window.winfo_width())
        finally:
            self.root.tk.call("tk", "scaling", original_scaling)
        self.assertAlmostEqual(float(self.root.tk.call("tk", "scaling")), original_scaling, places=2)

    @staticmethod
    def _texts(widget):
        values = []
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
    def _button(widget, label):
        pending = list(widget.winfo_children())
        while pending:
            child = pending.pop()
            pending.extend(child.winfo_children())
            if isinstance(child, ttk.Button) and child.cget("text") == label:
                return child
        raise AssertionError(f"Button not found: {label}")

    @staticmethod
    def _button_labels(widget):
        pending = list(widget.winfo_children())
        labels = []
        while pending:
            child = pending.pop()
            pending.extend(child.winfo_children())
            if isinstance(child, ttk.Button):
                labels.append(str(child.cget("text")))
        return labels


if __name__ == "__main__":
    unittest.main()
