from __future__ import annotations

import json
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from context_palette.excel_automation import (
    AutomationAvailability,
    AutomationCallError,
    AutomationCallResult,
    AutomationWarning,
    DescribeAutomationsResult,
    ExecuteAutomationResult,
    PlanAutomationResult,
    PlanBlocker,
    PlanChoice,
    PlanEffect,
    PlannedWorkbook,
    PlanRequirement,
)
from context_palette.excel_automation_window import ExcelAutomationWindow


FINGERPRINT = "a" * 64


class FakeCoordinator:
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
        result = self._result
        callback = self._callback
        self.completion_pending = False
        self.running = False
        self._result = None
        self._callback = None
        callback(result)
        return True


def describe_success() -> AutomationCallResult:
    return AutomationCallResult(
        "describe",
        "describe_succeeded",
        True,
        0,
        result=DescribeAutomationsResult(
            "1.0",
            (
                AutomationAvailability(
                    "excel.export_workbooks_to_csv",
                    "1.0",
                    True,
                    ("describe", "plan", "execute"),
                    None,
                    None,
                ),
            ),
        ),
    )


def needs_worksheet() -> AutomationCallResult:
    return AutomationCallResult(
        "plan",
        "plan_needs_parameters",
        True,
        0,
        result=PlanAutomationResult(
            state="needs_parameters",
            requirements=(
                PlanRequirement(
                    "worksheet_required",
                    "Choose a worksheet.",
                    "worksheet",
                    "input-1",
                    (PlanChoice("Data", "Data"), PlanChoice("Summary", "Summary")),
                    2,
                    False,
                ),
            ),
            blockers=(),
            inputs=(),
            warnings=(),
            effect=None,
            predicted_artifacts=(),
            plan_fingerprint=None,
            writes_performed=0,
        ),
    )


def ready_plan(source: Path, output: Path) -> AutomationCallResult:
    return AutomationCallResult(
        "plan",
        "plan_ready",
        True,
        0,
        result=PlanAutomationResult(
            state="ready",
            requirements=(),
            blockers=(),
            inputs=(
                PlannedWorkbook(
                    "input-1",
                    str(source),
                    str(source),
                    "Data",
                    (1, 2, 4),
                    27,
                    str(output / "book-Data.csv"),
                ),
            ),
            warnings=(AutomationWarning("formula_text", "Formulas are exported as text.", "input-1"),),
            effect=PlanEffect(False, "create_only", 1, 1, 27),
            predicted_artifacts=(),
            plan_fingerprint=FINGERPRINT,
            writes_performed=0,
        ),
    )


def execution_result(
    state: str,
    *,
    outputs: tuple[str, ...] = (),
    code: str = "ok",
    final_fingerprint: str | None = FINGERPRINT,
) -> AutomationCallResult:
    classifications = {
        "succeeded": "execute_succeeded",
        "failed_before_effect": "execute_failed_before_effect",
        "failed_after_partial_effect": "execute_failed_after_partial_effect",
    }
    effects_started = state != "failed_before_effect"
    result = ExecuteAutomationResult(
        state=state,  # type: ignore[arg-type]
        reviewed_plan_fingerprint=FINGERPRINT,
        final_plan_fingerprint=final_fingerprint,
        effects_started=effects_started,
        writes_performed=len(outputs),
        inputs=(),
        source_mutates_inputs=False,
        workbooks_saved=0,
        outputs_created=outputs,
        outputs_overwritten=0,
        artifacts=(),
        warnings=(),
        code=code,
        message="Result message.",
        retryable=False,
    )
    return AutomationCallResult(
        "execute",
        classifications[state],  # type: ignore[arg-type]
        True,
        0 if state == "succeeded" else 1,
        result=result,
    )


class ExcelAutomationWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.launcher = self.directory / "python-excel.bat"
        self.launcher.write_text("@echo off\n", encoding="utf-8")
        self.workbook = self.directory / "book.xlsx"
        self.workbook.write_bytes(b"test workbook placeholder")
        self.output = self.directory / "csv"
        self.output.mkdir()
        self.settings = self.directory / "local_python_excel.json"
        self.status = Mock()
        self.closed = Mock()
        self.coordinator = FakeCoordinator()

    def _window(self, *, configured: bool = True, opener=None) -> ExcelAutomationWindow:
        if configured:
            self.settings.write_text(
                json.dumps({"launcher_path": str(self.launcher)}),
                encoding="utf-8",
            )
        window = ExcelAutomationWindow(
            self.root,
            settings_path=self.settings,
            workbooks=(self.workbook,),
            status_setter=self.status,
            coordinator=self.coordinator,  # type: ignore[arg-type]
            folder_opener=opener,
            on_close=self.closed,
        )
        self.addCleanup(self._clean_up_window, window)
        self.root.update()
        return window

    def _clean_up_window(self, window: ExcelAutomationWindow) -> None:
        self.coordinator.running = False
        self.coordinator.completion_pending = False
        if not window._closed:
            window.close()

    def _through_describe(self, window: ExcelAutomationWindow) -> None:
        self.assertEqual(self.coordinator.calls[-1]["phase"], "describe")
        self._complete(window, describe_success())
        self.assertEqual(window.view_state, "choose_output")

    def _complete(
        self,
        window: ExcelAutomationWindow,
        result: AutomationCallResult,
    ) -> None:
        self.coordinator.complete(result)
        if window._poll_after_id is not None:
            window.window.after_cancel(window._poll_after_id)
            window._poll_after_id = None
        window._poll()

    def _start_plan(self, window: ExcelAutomationWindow) -> None:
        self._through_describe(window)
        with patch(
            "context_palette.excel_automation_window.filedialog.askdirectory",
            return_value=str(self.output),
        ):
            window._browse_output_directory()
        self.assertEqual(self.coordinator.calls[-1]["phase"], "plan")

    def _through_ready(self, window: ExcelAutomationWindow) -> None:
        self._start_plan(window)
        self._complete(window, ready_plan(self.workbook, self.output))
        self.assertEqual(window.view_state, "ready")

    @staticmethod
    def _descendants(widget: tk.Misc) -> list[tk.Misc]:
        descendants: list[tk.Misc] = []
        pending = list(widget.winfo_children())
        while pending:
            child = pending.pop(0)
            descendants.append(child)
            pending.extend(child.winfo_children())
        return descendants

    def _visible_text(self, window: ExcelAutomationWindow) -> str:
        values: list[str] = []
        for widget in self._descendants(window.content):
            if isinstance(widget, tk.Text):
                values.append(widget.get("1.0", tk.END))
            elif "text" in widget.keys():
                values.append(str(widget.cget("text")))
        return "\n".join(values)

    def _assert_scrollable_text_present(
        self,
        window: ExcelAutomationWindow,
        *,
        horizontal: bool = False,
    ) -> None:
        widgets = self._descendants(window.content)
        self.assertTrue(any(isinstance(widget, tk.Text) for widget in widgets))
        orientations = {
            str(widget.cget("orient"))
            for widget in widgets
            if isinstance(widget, ttk.Scrollbar)
        }
        self.assertIn("vertical", orientations)
        if horizontal:
            self.assertIn("horizontal", orientations)

    def test_missing_setup_is_visible_and_browse_saves_machine_local_launcher(self) -> None:
        window = self._window(configured=False)
        self.assertEqual(window.view_state, "setup")
        self.assertIn("Browse", window.primary_button.cget("text"))

        with patch(
            "context_palette.excel_automation_window.filedialog.askopenfilename",
            return_value=str(self.launcher),
        ):
            window._browse_launcher()

        self.assertEqual(
            json.loads(self.settings.read_text(encoding="utf-8")),
            {"launcher_path": str(self.launcher)},
        )
        self.assertEqual(self.coordinator.calls[-1]["phase"], "describe")
        self.assertEqual(window.view_state, "describing")

    def test_requirements_offer_per_input_worksheet_choices_and_replan_exact_selection(self) -> None:
        window = self._window()
        self._start_plan(window)
        self._complete(window, needs_worksheet())

        self.assertEqual(window.view_state, "needs_parameters")
        self.assertEqual(window.worksheet_variables["input-1"].get(), "")
        self.assertTrue(window.primary_button.instate(["disabled"]))
        self.assertIn(str(self.workbook), self._visible_text(window))
        window.worksheet_variables["input-1"].set("Summary")
        self.root.update()
        self.assertTrue(window.primary_button.instate(["!disabled"]))
        window._replan_from_requirements(needs_worksheet().result)  # type: ignore[arg-type]

        arguments = self.coordinator.calls[-1]["request"]["arguments"]
        self.assertEqual(arguments["inputs"][0]["parameters"]["worksheet"], "Summary")
        self.assertEqual(arguments["parameters"]["output_directory"], str(self.output))

    def test_ready_review_names_every_effect_and_execute_uses_exact_private_fingerprint(self) -> None:
        window = self._window()
        self._through_ready(window)

        review = window.review_text.get("1.0", tk.END)
        self.assertIn(f"Source: {self.workbook}", review)
        self.assertIn("Worksheet: Data", review)
        self.assertIn("Columns: 1, 2, 4", review)
        self.assertIn("Rows: 27", review)
        self.assertIn(str(self.output / "book-Data.csv"), review)
        self.assertNotIn(FINGERPRINT, review)
        visible = self._visible_text(window)
        self.assertIn("Warnings: 1", visible)
        self.assertIn("utf-8-sig", visible)
        self.assertIn("formula mode: formulas", visible)
        self.assertIn("Excel-safe escaping: on", visible)
        self.assertEqual(
            window.secondary_button.cget("text"),
            "Choose another output folder…",
        )
        self.assertEqual(window.primary_button.cget("text"), "Create 1 CSV file")
        self._assert_scrollable_text_present(window, horizontal=True)

        window.primary_button.invoke()

        request = self.coordinator.calls[-1]["request"]
        self.assertEqual(self.coordinator.calls[-1]["phase"], "execute")
        self.assertEqual(request["arguments"]["expected_plan_fingerprint"], FINGERPRINT)
        self.assertEqual(request["arguments"]["inputs"][0]["path"], str(self.workbook))

    def test_stale_before_effect_offers_only_replan(self) -> None:
        window = self._window()
        self._through_ready(window)
        window._execute_reviewed()
        self._complete(
            window,
            execution_result("failed_before_effect", code="stale_plan_fingerprint")
        )

        self.assertEqual(window.view_state, "failed_before_effect")
        self.assertEqual(window.primary_button.cget("text"), "Re-plan")
        self.assertNotIn("retry", window.status_var.get().casefold())

    def test_ready_review_can_choose_another_output_folder_and_replan(self) -> None:
        window = self._window()
        self._through_ready(window)
        alternate = self.directory / "ready-alternate"
        alternate.mkdir()

        with patch(
            "context_palette.excel_automation_window.filedialog.askdirectory",
            return_value=str(alternate),
        ):
            window.secondary_button.invoke()

        self.assertEqual(window.view_state, "planning")
        request = self.coordinator.calls[-1]["request"]
        self.assertEqual(
            request["arguments"]["parameters"]["output_directory"],
            str(alternate),
        )
        self.assertNotIn("expected_plan_fingerprint", request["arguments"])

    def test_partial_effect_lists_exact_outputs_opens_folder_and_has_no_retry(self) -> None:
        opened = Mock()
        window = self._window(opener=opened)
        self._through_ready(window)
        window._execute_reviewed()
        created = str(self.output / "book-Data.csv")
        self._complete(
            window,
            execution_result("failed_after_partial_effect", outputs=(created,), code="write_failed")
        )

        self.assertEqual(window.view_state, "failed_after_partial_effect")
        self.assertEqual(window.primary_button.cget("text"), "Open output folder")
        self.assertIn("Automatic retry is disabled", window.status_var.get())
        self._assert_scrollable_text_present(window, horizontal=True)
        window.primary_button.invoke()
        opened.assert_called_once_with(self.output)

    def test_unknown_outcome_shows_predicted_folder_without_retry(self) -> None:
        opened = Mock()
        window = self._window(opener=opened)
        self._through_ready(window)
        window._execute_reviewed()
        self._complete(
            window,
            AutomationCallResult(
                "execute",
                "execute_unknown",
                True,
                None,
                diagnostic_present=True,
                reason="The process timed out.",
            )
        )

        self.assertEqual(window.view_state, "execute_unknown")
        visible_text = "\n".join(
            str(child.cget("text"))
            for child in window.content.winfo_children()
            if "text" in child.keys()
        )
        self.assertIn(str(self.output), visible_text)
        self.assertIn("disabled", window.status_var.get())
        self.assertNotIn("The process timed out", window.status_var.get())
        self._assert_scrollable_text_present(window, horizontal=True)
        window.primary_button.invoke()
        opened.assert_called_once_with(self.output)

    def test_process_start_failure_is_known_to_have_no_effect(self) -> None:
        window = self._window()
        self._through_ready(window)
        window._execute_reviewed()
        self._complete(
            window,
            AutomationCallResult(
                "execute",
                "start_failed",
                False,
                None,
                reason="The Python Excel process could not start.",
            ),
        )

        self.assertEqual(window.view_state, "failed_before_effect")
        self.assertIn("No output effect started", window.status_var.get())
        self.assertNotIn("unknown", window.status_var.get().casefold())
        self.assertEqual(
            window.secondary_button.cget("text"),
            "Change Python Excel launcher…",
        )

    def test_correlated_engine_rejection_is_known_to_have_no_effect(self) -> None:
        window = self._window()
        self._through_ready(window)
        window._execute_reviewed()
        self._complete(
            window,
            AutomationCallResult(
                "execute",
                "outer_error",
                True,
                2,
                error=AutomationCallError(
                    "request.invalid",
                    "invalid_request",
                    "The reviewed request was rejected.",
                    False,
                    {},
                ),
            ),
        )

        self.assertEqual(window.view_state, "failed")
        self.assertIn("No output effect", window.status_var.get())
        self.assertNotIn("unknown", window.status_var.get().casefold())

    def test_ready_plan_rejects_an_output_outside_the_chosen_directory(self) -> None:
        window = self._window()
        self._start_plan(window)
        escaped = self.directory / "escaped"
        escaped.mkdir()
        call = ready_plan(self.workbook, escaped)

        self._complete(window, call)

        self.assertEqual(window.view_state, "unavailable")
        self.assertIn("escaped", window.content.winfo_children()[1].cget("text"))

    def test_execution_with_unreviewed_output_is_treated_as_unknown(self) -> None:
        window = self._window()
        self._through_ready(window)
        window._execute_reviewed()
        unreviewed = str(self.output / "different.csv")
        self._complete(
            window,
            execution_result("succeeded", outputs=(unreviewed,))
        )

        self.assertEqual(window.view_state, "execute_unknown")
        self.assertIn("Automatic retry is disabled", window.status_var.get())

    def test_succeeded_and_partial_results_require_the_reviewed_final_fingerprint(self) -> None:
        for state in ("succeeded", "failed_after_partial_effect"):
            with self.subTest(state=state):
                window = self._window()
                self._through_ready(window)
                window._execute_reviewed()
                created = str(self.output / "book-Data.csv")
                self._complete(
                    window,
                    execution_result(
                        state,
                        outputs=(created,),
                        final_fingerprint="b" * 64,
                    ),
                )

                self.assertEqual(window.view_state, "execute_unknown")

    def test_blocked_plan_is_scrollable_and_can_choose_another_output_folder(self) -> None:
        window = self._window()
        self._start_plan(window)
        blocked = PlanAutomationResult(
            state="blocked",
            requirements=(),
            blockers=tuple(
                PlanBlocker(
                    "output_exists",
                    f"Output {index} already exists.",
                    f"input-{index}",
                    str(self.output / f"book-{index}.csv"),
                    True,
                )
                for index in range(1, 101)
            ),
            inputs=(),
            warnings=(),
            effect=None,
            predicted_artifacts=(),
            plan_fingerprint=None,
            writes_performed=0,
        )
        self._complete(
            window,
            AutomationCallResult(
                "plan",
                "plan_blocked",
                True,
                0,
                result=blocked,
            ),
        )

        self.assertEqual(window.view_state, "blocked")
        self._assert_scrollable_text_present(window)
        self.assertIn("Output 100 already exists", self._visible_text(window))
        alternate = self.directory / "alternate"
        alternate.mkdir()
        with patch(
            "context_palette.excel_automation_window.filedialog.askdirectory",
            return_value=str(alternate),
        ):
            window.primary_button.invoke()
        request = self.coordinator.calls[-1]["request"]
        self.assertEqual(
            request["arguments"]["parameters"]["output_directory"],
            str(alternate),
        )

    def test_failure_and_unavailable_views_allow_launcher_replacement(self) -> None:
        window = self._window()
        self._complete(
            window,
            AutomationCallResult(
                "describe",
                "describe_failed",
                True,
                1,
                reason="The selected launcher did not return Python Excel JSON.",
            ),
        )
        self.assertEqual(window.view_state, "failed")
        self.assertEqual(
            window.secondary_button.cget("text"),
            "Change Python Excel launcher…",
        )
        replacement = self.directory / "replacement-python-excel.bat"
        replacement.write_text("@echo off\n", encoding="utf-8")
        with patch(
            "context_palette.excel_automation_window.filedialog.askopenfilename",
            return_value=str(replacement),
        ):
            window.secondary_button.invoke()
        self.assertEqual(
            json.loads(self.settings.read_text(encoding="utf-8")),
            {"launcher_path": str(replacement)},
        )
        self.assertEqual(self.coordinator.calls[-1]["phase"], "describe")

        self._complete(window, describe_success())
        window._show_unavailable("The required automation is unavailable.")
        self.assertEqual(
            window.secondary_button.cget("text"),
            "Change Python Excel launcher…",
        )

    def test_many_worksheet_requirements_scroll_without_hiding_replan(self) -> None:
        window = self._window()
        self._start_plan(window)
        requirements = tuple(
            PlanRequirement(
                "worksheet_required",
                "Choose a worksheet.",
                "worksheet",
                f"input-{index}",
                (PlanChoice("Data", "Data"), PlanChoice("Summary", "Summary")),
                2,
                False,
            )
            for index in range(1, 31)
        )
        plan = PlanAutomationResult(
            state="needs_parameters",
            requirements=requirements,
            blockers=(),
            inputs=(),
            warnings=(),
            effect=None,
            predicted_artifacts=(),
            plan_fingerprint=None,
            writes_performed=0,
        )

        self._complete(
            window,
            AutomationCallResult(
                "plan",
                "plan_needs_parameters",
                True,
                0,
                result=plan,
            ),
        )
        self.root.update()

        self.assertLess(window.requirements_canvas.yview()[1], 1.0)
        self.assertTrue(window.primary_button.winfo_ismapped())
        self.assertLessEqual(
            window.primary_button.winfo_rooty()
            + window.primary_button.winfo_height(),
            window.content.winfo_rooty() + window.content.winfo_height(),
        )

    def test_close_is_blocked_while_coordinator_runs(self) -> None:
        window = self._window()
        self.assertTrue(window.busy)

        self.assertFalse(window.close())

        self.assertTrue(window.window.winfo_exists())
        self.assertFalse(self.closed.called)
        self.assertIn("still working", window.status_var.get())


if __name__ == "__main__":
    unittest.main()
