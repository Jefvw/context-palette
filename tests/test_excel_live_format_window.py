from __future__ import annotations

import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock

from context_palette.excel_automation import (
    AutomationCallError,
    AutomationCallResult,
    LiveExcelApplication,
    LiveExcelInventoryResult,
    LiveExcelSheet,
    LiveExcelWarning,
    LiveExcelWorkbook,
    LiveFormatFailure,
    LiveFormatProfileResult,
)
from context_palette.excel_live_format_window import ExcelLiveFormatWindow


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


def workbook(
    token: str = "live-one",
    *,
    name: str = "Budget.xlsx",
    process_id: int = 42,
    active_sheet: str | None = "Data",
    autosave_enabled: bool | None = False,
    sheets: tuple[LiveExcelSheet, ...] = (
        LiveExcelSheet(1, "Data", "visible"),
        LiveExcelSheet(2, "Archive", "hidden"),
    ),
) -> LiveExcelWorkbook:
    return LiveExcelWorkbook(
        token,
        process_id,
        name,
        rf"D:\work\{name}",
        True,
        False,
        autosave_enabled,
        active_sheet,
        len(sheets),
        False,
        sheets,
    )


def inventory(*books: LiveExcelWorkbook) -> AutomationCallResult:
    return AutomationCallResult(
        "inventory",
        "inventory_succeeded",
        True,
        0,
        result=LiveExcelInventoryResult(
            1,
            False,
            (LiveExcelApplication(42, True, True, len(books), False, books),),
            (),
        ),
    )


def format_result(
    state: str = "succeeded", *, token: str = "live-one"
) -> AutomationCallResult:
    failures = ()
    formatted = ("Data",)
    if state == "failed":
        formatted = ()
        failures = (LiveFormatFailure("Data", "conflict.live_worksheet_protected", "Protected"),)
    elif state == "partial_failure":
        failures = (LiveFormatFailure("Summary", "operation.live_format_failed", "Failed"),)
    return AutomationCallResult(
        "apply",
        {"succeeded": "apply_succeeded", "failed": "apply_failed", "partial_failure": "apply_partial_failure"}[state],
        True,
        0,
        result=LiveFormatProfileResult(
            state,  # type: ignore[arg-type]
            token,
            "Budget.xlsx",
            "worksheet",
            "standard_data",
            "1.0",
            formatted,
            (),
            ("Data",) if formatted else (),
            (),
            failures,
            False,
            False,
            False,
            (),
        ),
    )


class ExcelLiveFormatWindowTests(unittest.TestCase):
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
        self.settings.write_text(json.dumps({"launcher_path": str(self.launcher)}), encoding="utf-8")
        self.coordinator = FakeCoordinator()
        self.status = Mock()
        self.return_to_source = Mock(return_value=True)

    def _window(self, **kwargs) -> ExcelLiveFormatWindow:
        window = ExcelLiveFormatWindow(
            self.root,
            settings_path=self.settings,
            status_setter=self.status,
            coordinator=self.coordinator,  # type: ignore[arg-type]
            return_to_source=self.return_to_source,
            **kwargs,
        )
        self.addCleanup(self._close, window)
        self.root.update()
        return window

    def _close(self, window: ExcelLiveFormatWindow) -> None:
        self.coordinator.running = False
        self.coordinator.completion_pending = False
        self.coordinator._callback = None
        if not window._closed:
            window.close()

    def _complete(self, window: ExcelLiveFormatWindow, result: AutomationCallResult) -> None:
        self.coordinator.complete(result)
        if window._poll_after_id is not None:
            window.window.after_cancel(window._poll_after_id)
            window._poll_after_id = None
        window._poll()

    def _selection(self, window: ExcelLiveFormatWindow, *books: LiveExcelWorkbook) -> None:
        self.assertEqual(self.coordinator.calls[-1]["phase"], "inventory")
        self._complete(window, inventory(*books))
        self.assertEqual(window.view_state, "select")

    def test_inventory_starts_automatically_and_preselects_captured_book_and_sheet(self) -> None:
        other = workbook("live-other", name="Other.xlsx", process_id=42, active_sheet="Data")
        selected = workbook("live-budget", name="Budget.xlsx", process_id=42, active_sheet="Data")
        window = self._window(
            source_window_handle=99,
            source_process_id=42,
            source_window_title="Budget.xlsx - Excel",
        )

        self._selection(window, other, selected)

        self.assertEqual(window._selected_workbook, selected)
        self.assertEqual(window.worksheet_var.get(), "Data")
        self.assertEqual(str(window.workbook_picker.cget("state")), "readonly")

    def test_apply_uses_one_worksheet_request_without_a_planner(self) -> None:
        window = self._window()
        self._selection(window, workbook())

        window._apply()

        self.assertEqual(self.coordinator.calls[-1]["phase"], "apply")
        request = self.coordinator.calls[-1]["request"]
        self.assertEqual(request["operation"], "apply_live_format_profile")
        self.assertEqual(request["arguments"]["scope"], "worksheet")
        self.assertEqual(request["arguments"]["worksheet"], "Data")

    def test_workbook_scope_uses_null_worksheet(self) -> None:
        window = self._window()
        self._selection(window, workbook())
        window.scope_var.set("workbook")
        window._scope_changed()

        self.assertEqual(str(window.worksheet_picker.cget("state")), "disabled")

        window.scope_var.set("worksheet")
        window._scope_changed()
        self.assertEqual(str(window.worksheet_picker.cget("state")), "readonly")

        window.scope_var.set("workbook")
        window._scope_changed()

        window._apply()

        request = self.coordinator.calls[-1]["request"]
        self.assertEqual(request["arguments"]["scope"], "workbook")
        self.assertIsNone(request["arguments"]["worksheet"])

    def test_autosave_disables_apply_until_inventory_is_refreshed(self) -> None:
        window = self._window(source_window_handle=77, source_process_id=42)
        self._selection(window, workbook(autosave_enabled=True))

        self.assertEqual(window.primary_button.instate(["disabled"]), True)
        self.assertIn("AutoSave", window.status_var.get())

    def test_success_renders_effect_and_returns_to_captured_excel(self) -> None:
        window = self._window(source_window_handle=4321, source_process_id=42)
        self._selection(window, workbook())
        window._apply()
        self._complete(window, format_result())

        self.assertEqual(window.view_state, "succeeded")
        window._return_to_excel()
        self.return_to_source.assert_called_once_with(4321)

    def test_stale_token_requires_inventory_refresh(self) -> None:
        window = self._window()
        self._selection(window, workbook())
        window._apply()
        self._complete(
            window,
            AutomationCallResult(
                "apply",
                "outer_error",
                True,
                1,
                error=AutomationCallError(
                    "conflict.live_workbook_stale", "conflict", "Workbook changed", True, {}
                ),
            ),
        )

        self.assertEqual(window.view_state, "stale")
        window.primary_button.invoke()
        self.assertEqual(self.coordinator.calls[-1]["phase"], "inventory")

    def test_unknown_apply_never_offers_an_automatic_retry(self) -> None:
        window = self._window(source_window_handle=77, source_process_id=42)
        self._selection(window, workbook())
        window._apply()
        self._complete(
            window,
            AutomationCallResult("apply", "apply_unknown", True, None, reason="timed out"),
        )

        self.assertEqual(window.view_state, "unknown")
        self.assertNotIn("Apply template", self._texts(window.content))
        self.assertIn("Return to Excel", self._texts(window.content))

    def test_partial_failure_is_reported_without_claiming_rollback(self) -> None:
        window = self._window()
        self._selection(window, workbook())
        window._apply()
        self._complete(window, format_result("partial_failure"))

        self.assertEqual(window.view_state, "partial_failure")
        self.assertIn("Worksheet failures", window.result_text.get("1.0", "end-1c"))
        self.assertTrue(window.result_text.cget("yscrollcommand"))
        self.assertIn("does not roll back", window.status_var.get())

    def test_non_excel_source_has_no_return_button_and_valid_switch_clears_error(self) -> None:
        blocked = workbook("blocked", name="Blocked.xlsx", autosave_enabled=True)
        valid = workbook("valid", name="Valid.xlsx", autosave_enabled=False)
        window = self._window(source_window_handle=77, source_process_id=999)
        self._selection(window, blocked, valid)

        self.assertNotIn("Return to Excel", self._texts(window.content))
        self.assertIn("AutoSave", window.status_var.get())

        valid_label = next(
            label
            for label, selected in window._workbooks_by_label.items()
            if selected == valid
        )
        window.workbook_var.set(valid_label)
        window._workbook_changed()

        self.assertFalse(window.primary_button.instate(["disabled"]))
        self.assertNotIn("AutoSave", window.status_var.get())

    def test_similar_workbook_names_do_not_use_a_substring_title_match(self) -> None:
        book1 = workbook("book-1", name="Book1.xlsx", process_id=42)
        book10 = workbook("book-10", name="Book10.xlsx", process_id=42)
        window = self._window(
            source_process_id=42,
            source_window_title="Book10.xlsx - Excel",
        )

        self._selection(window, book1, book10)

        self.assertEqual(window._selected_workbook, book10)

    @staticmethod
    def _texts(widget: tk.Misc) -> str:
        values: list[str] = []
        pending = list(widget.winfo_children())
        while pending:
            child = pending.pop()
            pending.extend(child.winfo_children())
            if "text" in child.keys():
                values.append(str(child.cget("text")))
        return "\n".join(values)


if __name__ == "__main__":
    unittest.main()
