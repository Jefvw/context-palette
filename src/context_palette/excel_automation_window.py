"""Attended Tk workflow for reviewed Python Excel CSV automation."""

from __future__ import annotations

import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable
from uuid import uuid4

from .excel_automation import (
    AutomationCallResult,
    CsvAutomationInvocation,
    DescribeAutomationsResult,
    EXCEL_AUTOMATION_ID,
    EXCEL_AUTOMATION_VERSION,
    ExcelAutomationCoordinator,
    ExcelAutomationSettings,
    ExcelAutomationSettingsError,
    ExecuteAutomationResult,
    PlanAutomationResult,
    PythonExcelProcessClient,
    build_describe_automations_request,
    build_execute_automation_request,
    build_plan_automation_request,
    csv_invocation,
    load_excel_automation_settings,
    save_excel_automation_settings,
)
from .window_geometry import configure_standard_window


_REQUIRED_PHASES = frozenset({"describe", "plan", "execute"})
_POLL_MILLISECONDS = 50
_DESCRIBE_TIMEOUT_SECONDS = 30.0
_PLAN_TIMEOUT_SECONDS = 180.0
_EXECUTE_TIMEOUT_SECONDS = 300.0


class ExcelAutomationWindow:
    """Guide one reviewed, create-only workbook-to-CSV operation."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        settings_path: Path,
        workbooks: tuple[Path, ...],
        status_setter: Callable[[str], None],
        coordinator: ExcelAutomationCoordinator | None = None,
        client: PythonExcelProcessClient | None = None,
        folder_opener: Callable[[Path], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        if coordinator is not None and client is not None:
            raise ValueError("Supply either coordinator or client, not both.")
        if not workbooks:
            raise ValueError("At least one workbook is required.")

        self.settings_path = Path(settings_path)
        self.workbooks = tuple(Path(path) for path in workbooks)
        self.status_setter = status_setter
        self.coordinator = coordinator or ExcelAutomationCoordinator(client)
        self.folder_opener = folder_opener or _open_folder
        self.on_close = on_close or (lambda: None)

        self._launcher_path: Path | None = None
        self._output_directory: Path | None = None
        self._worksheets: dict[str, str] = {}
        self._current_invocation: CsvAutomationInvocation | None = None
        self._reviewed_invocation: CsvAutomationInvocation | None = None
        self._reviewed_fingerprint: str | None = None
        self._reviewed_warning_count = 0
        self._predicted_output_folder: Path | None = None
        self._predicted_outputs: tuple[Path, ...] = ()
        self._poll_after_id: str | None = None
        self._closed = False
        self.view_state = "starting"

        self.window = tk.Toplevel(parent)
        self.window.title("Export Excel files to CSV")
        configure_standard_window(self.window, parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            outer,
            text="Export Excel files to CSV",
            style="Title.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            outer,
            text=(
                "Review exactly what will be read and created before Python Excel runs. "
                "Your source workbooks are never changed."
            ),
            style="Muted.TLabel",
            wraplength=720,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(2, 10))

        self.content = ttk.Frame(outer)
        self.content.pack(fill=tk.BOTH, expand=True)
        self.status_var = tk.StringVar()
        self.status_label = ttk.Label(
            outer,
            textvariable=self.status_var,
            style="Status.TLabel",
            wraplength=720,
            justify=tk.LEFT,
        )
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        footer = ttk.Frame(outer)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        self.close_button = ttk.Button(footer, text="Close", command=self.close)
        self.close_button.pack(side=tk.RIGHT)

        self.primary_button: ttk.Button | None = None
        self.secondary_button: ttk.Button | None = None
        self.worksheet_variables: dict[str, tk.StringVar] = {}
        self._worksheet_requirements_supported = False
        self.review_text: tk.Text | None = None
        self._progressbar: ttk.Progressbar | None = None

        self.window.transient(parent)
        self.show()
        self.window.after_idle(self._load_settings)

    @property
    def busy(self) -> bool:
        return bool(self.coordinator.running)

    def show(self) -> None:
        if self._closed:
            return
        self.window.deiconify()
        self.window.lift()

    def close(self) -> bool:
        if self._closed:
            return True
        if self.busy:
            self._set_status(
                "Python Excel is still working. This window will remain open until it finishes.",
                error=True,
            )
            return False
        self._closed = True
        if self._poll_after_id is not None:
            try:
                self.window.after_cancel(self._poll_after_id)
            except tk.TclError:
                pass
            self._poll_after_id = None
        self._stop_progress()
        try:
            self.window.destroy()
        finally:
            self.on_close()
        return True

    def _load_settings(self) -> None:
        try:
            settings = load_excel_automation_settings(self.settings_path)
        except ExcelAutomationSettingsError as exc:
            self._show_setup(str(exc))
            return
        launcher = settings.launcher_path
        if launcher is None or not launcher.is_file():
            self._show_setup(
                "Choose the Python Excel machine launcher on this computer. "
                "Excel features remain optional."
            )
            return
        self._launcher_path = launcher
        self._start_describe()

    def _show_setup(self, message: str) -> None:
        self.view_state = "setup"
        self._clear_content()
        ttk.Label(
            self.content,
            text="Set up Python Excel",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            self.content,
            text=message,
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 12))
        ttk.Label(
            self.content,
            text=(
                "Select the absolute .bat launcher supplied by Python Excel. "
                "This setting is stored only on this computer and needs no administrator rights."
            ),
            style="Muted.TLabel",
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 12))
        self.primary_button = ttk.Button(
            self.content,
            text="Browse for Python Excel launcher…",
            command=self._browse_launcher,
            style="Accent.TButton",
        )
        self.primary_button.pack(anchor=tk.W)
        self._set_status("Python Excel setup is required before this export can be planned.")

    def _browse_launcher(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.window,
            title="Choose Python Excel launcher",
            filetypes=(("Batch launchers", "*.bat"), ("All files", "*.*")),
        )
        if not selected:
            return
        launcher = Path(selected)
        try:
            if not launcher.is_file():
                raise ExcelAutomationSettingsError(
                    "The selected Python Excel launcher does not exist."
                )
            settings = ExcelAutomationSettings(launcher)
            save_excel_automation_settings(self.settings_path, settings)
        except (ExcelAutomationSettingsError, OSError) as exc:
            self._set_status(str(exc), error=True)
            return
        self._launcher_path = launcher
        self._output_directory = None
        self._worksheets.clear()
        self._current_invocation = None
        self._clear_review_identity()
        self.status_setter("Python Excel setup saved for this computer.")
        self._start_describe()

    def _start_describe(self) -> None:
        self.view_state = "describing"
        self._clear_content()
        self._show_working("Checking Python Excel capabilities…")
        request = build_describe_automations_request(_request_id())
        self._start_call(
            request,
            phase="describe",
            timeout_seconds=_DESCRIBE_TIMEOUT_SECONDS,
            callback=self._describe_completed,
        )

    def _describe_completed(self, call: AutomationCallResult) -> None:
        if call.classification != "describe_succeeded" or not isinstance(
            call.result, DescribeAutomationsResult
        ):
            self._show_call_failure(
                "Python Excel could not describe its automations.", call
            )
            return
        availability = call.result.csv_automation
        if availability is None:
            self._show_unavailable(
                f"Python Excel does not provide {EXCEL_AUTOMATION_ID} "
                f"version {EXCEL_AUTOMATION_VERSION}."
            )
            return
        missing = _REQUIRED_PHASES.difference(availability.supported_phases)
        if not availability.available or missing:
            reason = availability.reason or availability.code or "The automation is unavailable."
            if missing:
                reason = (
                    f"{reason} Required phases are not all supported: "
                    f"{', '.join(sorted(missing))}."
                )
            self._show_unavailable(reason)
            return
        self._show_output_directory()

    def _show_unavailable(self, message: str) -> None:
        self.view_state = "unavailable"
        self._clear_content()
        ttk.Label(
            self.content,
            text="CSV automation unavailable",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            self.content,
            text=message,
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 0))
        self.secondary_button = ttk.Button(
            self.content,
            text="Change Python Excel launcher…",
            command=self._browse_launcher,
        )
        self.secondary_button.pack(anchor=tk.W, pady=(12, 0))
        self._set_status("Context Palette remains available; only this Excel export is unavailable.", error=True)

    def _show_output_directory(self) -> None:
        self.view_state = "choose_output"
        self._clear_content()
        ttk.Label(
            self.content,
            text="Choose where new CSV files will be created",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            self.content,
            text=(
                f"{len(self.workbooks)} closed .xlsx workbook(s) will be inspected during planning. "
                "The output directory must already exist. Existing files will not be overwritten."
            ),
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 12))
        self.primary_button = ttk.Button(
            self.content,
            text="Choose output directory…",
            command=self._browse_output_directory,
            style="Accent.TButton",
        )
        self.primary_button.pack(anchor=tk.W)
        self._set_status("Choose an existing output directory to begin the read-only plan.")

    def _browse_output_directory(self) -> None:
        selected = filedialog.askdirectory(
            parent=self.window,
            title="Choose output directory",
            mustexist=True,
        )
        if not selected:
            return
        directory = Path(selected)
        if not directory.is_absolute() or not directory.is_dir():
            self._set_status("Choose an existing absolute output directory.", error=True)
            return
        self._output_directory = directory
        self._start_plan()

    def _start_plan(self) -> None:
        if self._output_directory is None:
            self._show_output_directory()
            return
        invocation = csv_invocation(
            self.workbooks,
            output_directory=self._output_directory,
            worksheets=self._worksheets,
        )
        self._current_invocation = invocation
        self._clear_review_identity()
        self.view_state = "planning"
        self._clear_content()
        self._show_working("Inspecting workbooks and preparing a create-only plan…")
        self._start_call(
            build_plan_automation_request(_request_id(), invocation),
            phase="plan",
            timeout_seconds=_PLAN_TIMEOUT_SECONDS,
            callback=self._plan_completed,
        )

    def _plan_completed(self, call: AutomationCallResult) -> None:
        if not isinstance(call.result, PlanAutomationResult):
            self._show_call_failure("Python Excel could not prepare the plan.", call)
            return
        plan = call.result
        if call.classification == "plan_needs_parameters" and plan.state == "needs_parameters":
            self._show_requirements(plan)
            return
        if call.classification == "plan_blocked" and plan.state == "blocked":
            self._show_blocked(plan)
            return
        if call.classification == "plan_ready" and plan.state == "ready":
            self._show_ready(plan)
            return
        self._show_call_failure("Python Excel returned a contradictory planning result.", call)

    def _show_requirements(self, plan: PlanAutomationResult) -> None:
        self.view_state = "needs_parameters"
        self._clear_content()
        self._worksheet_requirements_supported = False
        ttk.Label(
            self.content,
            text="Choose a worksheet for each workbook",
            style="Heading.TLabel",
        ).pack(anchor=tk.W, pady=(0, 8))
        self.worksheet_variables = {}
        self.primary_button = ttk.Button(
            self.content,
            text="Re-plan with these worksheets",
            command=lambda: self._replan_from_requirements(plan),
            style="Accent.TButton",
        )
        self.primary_button.pack(side=tk.BOTTOM, anchor=tk.W, pady=(12, 0))
        choices_host = ttk.Frame(self.content)
        choices_host.pack(fill=tk.BOTH, expand=True)
        choices_canvas = tk.Canvas(
            choices_host,
            borderwidth=0,
            highlightthickness=0,
            background=self.window.cget("background"),
        )
        choices_scrollbar = ttk.Scrollbar(
            choices_host,
            orient=tk.VERTICAL,
            command=choices_canvas.yview,
        )
        choices_canvas.configure(yscrollcommand=choices_scrollbar.set)
        choices_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        choices_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        choices_frame = ttk.Frame(choices_canvas)
        choices_window = choices_canvas.create_window(
            (0, 0),
            window=choices_frame,
            anchor=tk.NW,
        )
        choices_frame.bind(
            "<Configure>",
            lambda _event: choices_canvas.configure(
                scrollregion=choices_canvas.bbox("all")
            ),
        )
        choices_canvas.bind(
            "<Configure>",
            lambda event: choices_canvas.itemconfigure(
                choices_window,
                width=event.width,
            ),
        )
        self.requirements_canvas = choices_canvas
        can_replan = True
        for requirement in plan.requirements:
            if (
                requirement.parameter_id != "worksheet"
                or requirement.input_id is None
                or not requirement.choices
                or requirement.choices_truncated
            ):
                can_replan = False
                ttk.Label(
                    choices_frame,
                    text=f"{requirement.code}: {requirement.message}",
                    wraplength=700,
                    justify=tk.LEFT,
                ).pack(anchor=tk.W, pady=3)
                continue
            row = ttk.Frame(choices_frame)
            row.pack(fill=tk.X, pady=5)
            ttk.Label(
                row,
                text=self._input_label(requirement.input_id),
                wraplength=680,
                justify=tk.LEFT,
            ).pack(fill=tk.X, anchor=tk.W)
            labels = tuple(choice.label for choice in requirement.choices)
            variable = tk.StringVar(value="")
            picker = ttk.Combobox(
                row,
                textvariable=variable,
                values=labels,
                state="readonly",
                width=34,
            )
            picker.pack(fill=tk.X, pady=(2, 0))
            picker._excel_choice_values = {  # type: ignore[attr-defined]
                choice.label: choice.value for choice in requirement.choices
            }
            self.worksheet_variables[requirement.input_id] = variable
            variable.trace_add(
                "write",
                lambda *_args: self._update_requirements_button_state(),
            )
        self._worksheet_requirements_supported = can_replan
        self._update_requirements_button_state()
        self._set_status(
            "Choose a worksheet explicitly for every workbook. Planning has not changed any files."
        )

    def _update_requirements_button_state(self) -> None:
        button = self.primary_button
        if button is None:
            return
        complete = (
            self._worksheet_requirements_supported
            and bool(self.worksheet_variables)
            and all(variable.get().strip() for variable in self.worksheet_variables.values())
        )
        button.configure(state=tk.NORMAL if complete else tk.DISABLED)

    def _replan_from_requirements(self, plan: PlanAutomationResult) -> None:
        for requirement in plan.requirements:
            if requirement.input_id not in self.worksheet_variables:
                continue
            selected_label = self.worksheet_variables[requirement.input_id].get()
            choice = next(
                (item for item in requirement.choices if item.label == selected_label),
                None,
            )
            if choice is None:
                self._set_status("Choose a valid worksheet for every workbook.", error=True)
                return
            self._worksheets[requirement.input_id] = choice.value
        self._start_plan()

    def _show_blocked(self, plan: PlanAutomationResult) -> None:
        self.view_state = "blocked"
        self._clear_content()
        ttk.Label(self.content, text="The export cannot proceed", style="Heading.TLabel").pack(anchor=tk.W)
        lines: list[str] = []
        for blocker in plan.blockers:
            text = f"{blocker.code}: {blocker.message}"
            if blocker.path:
                text += f"\nPath: {blocker.path}"
            lines.append(text)
        self._read_only_text(
            "\n\n".join(lines) or "Python Excel did not provide a blocker description.",
            height=min(14, max(5, len(plan.blockers) * 3)),
            wrap=tk.WORD,
            pady=(6, 8),
        )
        self.primary_button = ttk.Button(
            self.content,
            text="Choose another output folder…",
            command=self._browse_output_directory,
            style="Accent.TButton",
        )
        self.primary_button.pack(anchor=tk.W)
        self._set_status("No output files were created and no source workbook was changed.", error=True)

    def _show_ready(self, plan: PlanAutomationResult) -> None:
        invocation = self._current_invocation
        fingerprint = plan.plan_fingerprint
        if invocation is None or fingerprint is None:
            self._show_unavailable("Python Excel returned an incomplete reviewed plan.")
            return
        validation_error = self._validate_ready_plan(plan, invocation)
        if validation_error is not None:
            self._show_unavailable(
                "Python Excel returned a plan that Context Palette could not "
                f"verify safely: {validation_error}"
            )
            return
        self._reviewed_invocation = invocation
        self._reviewed_fingerprint = fingerprint
        self._predicted_output_folder = self._output_directory
        self._predicted_outputs = tuple(
            Path(item.output_path) for item in plan.inputs
        )
        self.view_state = "ready"
        self._clear_content()
        ttk.Label(self.content, text="Review before export", style="Heading.TLabel").pack(anchor=tk.W)
        ttk.Label(
            self.content,
            text=(
                "CREATE ONLY · Source workbooks unchanged · Existing outputs never overwritten"
            ),
            style="Success.TLabel",
        ).pack(anchor=tk.W, pady=(3, 8))
        ttk.Label(
            self.content,
            text=_csv_format_summary(invocation),
            style="Muted.TLabel",
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 5))
        warning_count = len(plan.warnings)
        ttk.Label(
            self.content,
            text=(
                f"Warnings: {warning_count}"
                if warning_count
                else "Warnings: none"
            ),
            style="Heading.TLabel" if warning_count else "Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 5))
        lines: list[str] = []
        for item in plan.inputs:
            columns = ", ".join(str(column) for column in item.physical_columns)
            lines.extend(
                (
                    f"Source: {item.original_path}",
                    f"  Worksheet: {item.worksheet}",
                    f"  Columns: {columns}",
                    f"  Rows: {item.rows_to_write}",
                    f"  Creates: {item.output_path}",
                    "",
                )
            )
        if plan.warnings:
            lines.append(f"Warnings ({warning_count})")
            lines.extend(f"  {warning.code}: {warning.message}" for warning in plan.warnings)
        self.review_text = self._read_only_text(
            "\n".join(lines).rstrip(),
            height=max(8, min(18, 4 * len(plan.inputs))),
            wrap=tk.NONE,
            pady=(0, 0),
        )
        self._reviewed_warning_count = warning_count
        button_row = ttk.Frame(self.content)
        button_row.pack(fill=tk.X, pady=(10, 0))
        self.primary_button = ttk.Button(
            button_row,
            text=(
                f"Create {len(plan.inputs)} CSV "
                f"file{'s' if len(plan.inputs) != 1 else ''}"
            ),
            command=self._execute_reviewed,
            style="Accent.TButton",
        )
        self.primary_button.pack(side=tk.LEFT)
        self.secondary_button = ttk.Button(
            button_row,
            text="Choose another output folder…",
            command=self._browse_output_directory,
        )
        self.secondary_button.pack(side=tk.LEFT, padx=(8, 0))
        self._set_status("Review every workbook and output, then explicitly execute the reviewed plan.")

    def _execute_reviewed(self) -> None:
        invocation = self._reviewed_invocation
        fingerprint = self._reviewed_fingerprint
        if invocation is None or fingerprint is None:
            self._set_status("The reviewed plan is no longer available. Re-plan first.", error=True)
            return
        self.view_state = "executing"
        self._clear_content()
        self._show_working(
            "Creating the reviewed CSV files… Do not close this window until the result is known."
        )
        self._start_call(
            build_execute_automation_request(_request_id(), invocation, fingerprint),
            phase="execute",
            timeout_seconds=_EXECUTE_TIMEOUT_SECONDS,
            callback=self._execute_completed,
        )

    def _execute_completed(self, call: AutomationCallResult) -> None:
        if call.classification == "start_failed" and not call.process_started:
            self._show_execute_not_started(call)
            return
        if call.classification == "outer_error" and call.error is not None:
            self._show_call_failure(
                "Python Excel rejected the export before any effect.",
                call,
            )
            self._clear_review_identity()
            return
        if call.classification == "execute_unknown":
            self._show_unknown(call)
            return
        if not isinstance(call.result, ExecuteAutomationResult):
            self._show_unknown(call)
            return
        result = call.result
        if not self._execution_result_is_consistent(result):
            self._show_unknown(call)
            return
        if call.classification == "execute_succeeded" and result.state == "succeeded":
            self._show_execution_result("succeeded", result)
        elif (
            call.classification == "execute_failed_before_effect"
            and result.state == "failed_before_effect"
        ):
            self._show_execution_result("failed_before_effect", result)
        elif (
            call.classification == "execute_failed_after_partial_effect"
            and result.state == "failed_after_partial_effect"
        ):
            self._show_execution_result("failed_after_partial_effect", result)
        else:
            self._show_unknown(call)

    def _show_execution_result(self, state: str, result: ExecuteAutomationResult) -> None:
        self.view_state = state
        self._clear_content()
        headings = {
            "succeeded": "CSV export completed",
            "failed_before_effect": "No CSV files were created",
            "failed_after_partial_effect": "CSV export stopped after creating some files",
        }
        ttk.Label(self.content, text=headings[state], style="Heading.TLabel").pack(anchor=tk.W)
        ttk.Label(
            self.content,
            text=f"{result.code}: {result.message}",
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 8))
        if result.outputs_created:
            ttk.Label(
                self.content,
                text="Files created in this attempt:",
                style="Heading.TLabel",
            ).pack(anchor=tk.W)
            self._read_only_text(
                "\n".join(result.outputs_created),
                height=min(12, max(3, len(result.outputs_created))),
                wrap=tk.NONE,
                pady=(3, 8),
            )
        if state == "failed_before_effect" and _is_stale(result.code):
            self.primary_button = ttk.Button(
                self.content,
                text="Re-plan",
                command=self._start_plan,
                style="Accent.TButton",
            )
            self.primary_button.pack(anchor=tk.W)
        elif state in {"succeeded", "failed_after_partial_effect"} and self._output_directory:
            self.primary_button = ttk.Button(
                self.content,
                text="Open output folder",
                command=self._open_output_folder,
            )
            self.primary_button.pack(anchor=tk.W)
        if state == "failed_after_partial_effect":
            self._set_status(
                "Some outputs exist. Automatic retry is disabled; inspect the exact list above.",
                error=True,
            )
        elif state == "failed_before_effect":
            self._set_status("No effects started. Re-plan only when the reviewed plan became stale.", error=True)
        else:
            self._set_status("Export complete. Source workbooks were not changed.")
        self._clear_review_identity()

    def _show_unknown(self, call: AutomationCallResult) -> None:
        self.view_state = "execute_unknown"
        self._clear_content()
        ttk.Label(
            self.content,
            text="Export outcome unknown",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            self.content,
            text=(
                "Context Palette lost a trustworthy execution result. Some predicted outputs may exist. "
                "Do not retry automatically; inspect the output directory first."
            ),
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 8))
        if self._predicted_output_folder is not None:
            ttk.Label(
                self.content,
                text=f"Predicted output folder: {self._predicted_output_folder}",
                wraplength=700,
                justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=(0, 8))
            self.primary_button = ttk.Button(
                self.content,
                text="Open predicted output folder",
                command=self._open_predicted_output_folder,
            )
            self.primary_button.pack(anchor=tk.W)
        if self._predicted_outputs:
            ttk.Label(
                self.content,
                text="Predicted outputs to inspect:",
                style="Heading.TLabel",
            ).pack(anchor=tk.W, pady=(8, 0))
            self._read_only_text(
                "\n".join(str(path) for path in self._predicted_outputs),
                height=min(8, max(2, len(self._predicted_outputs))),
                wrap=tk.NONE,
                pady=(3, 0),
            )
        self._set_status("Outcome unknown. Automatic retry is disabled.", error=True)
        self._clear_review_identity()

    def _show_execute_not_started(self, call: AutomationCallResult) -> None:
        self.view_state = "failed_before_effect"
        self._clear_content()
        ttk.Label(
            self.content,
            text="The Excel export did not start",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            self.content,
            text=call.reason or "Python Excel could not be started.",
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 0))
        self.secondary_button = ttk.Button(
            self.content,
            text="Change Python Excel launcher…",
            command=self._browse_launcher,
        )
        self.secondary_button.pack(anchor=tk.W, pady=(12, 0))
        self._set_status(
            "No output effect started. Check this computer's Python Excel setup.",
            error=True,
        )
        self._clear_review_identity()

    def _show_call_failure(self, heading: str, call: AutomationCallResult) -> None:
        self.view_state = "failed"
        self._clear_content()
        ttk.Label(self.content, text=heading, style="Heading.TLabel").pack(anchor=tk.W)
        message = call.error.message if call.error is not None else call.reason
        ttk.Label(
            self.content,
            text=message or "Python Excel did not return a usable result.",
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 0))
        self.secondary_button = ttk.Button(
            self.content,
            text="Change Python Excel launcher…",
            command=self._browse_launcher,
        )
        self.secondary_button.pack(anchor=tk.W, pady=(12, 0))
        self._set_status("No output effect was started by this attended workflow.", error=True)

    def _show_working(self, message: str) -> None:
        ttk.Label(self.content, text=message, style="Heading.TLabel", wraplength=700).pack(anchor=tk.W)
        progress = ttk.Progressbar(self.content, mode="indeterminate")
        progress.pack(fill=tk.X, pady=(12, 0))
        progress.start(12)
        self._progressbar = progress
        self._set_status("Please wait. Closing is disabled while Python Excel is working.")

    def _start_call(
        self,
        request: dict[str, object],
        *,
        phase: str,
        timeout_seconds: float,
        callback: Callable[[AutomationCallResult], None],
    ) -> None:
        launcher = self._launcher_path
        if launcher is None:
            self._show_setup("The Python Excel launcher is not configured.")
            return
        started = self.coordinator.start(
            launcher,
            request,
            phase=phase,  # type: ignore[arg-type]
            timeout_seconds=timeout_seconds,
            on_complete=callback,
        )
        if not started:
            self._show_unavailable("Another Excel automation workflow is already running.")
            return
        self.close_button.configure(state=tk.DISABLED)
        self._schedule_poll()

    def _schedule_poll(self) -> None:
        if self._closed or self._poll_after_id is not None:
            return
        self._poll_after_id = self.window.after(_POLL_MILLISECONDS, self._poll)

    def _poll(self) -> None:
        self._poll_after_id = None
        if self._closed:
            return
        self.coordinator.drain()
        if self.busy or self.coordinator.completion_pending:
            self._schedule_poll()
        else:
            self.close_button.configure(state=tk.NORMAL)

    def _open_output_folder(self) -> None:
        if self._output_directory is not None:
            self._open_folder_safely(self._output_directory)

    def _open_predicted_output_folder(self) -> None:
        if self._predicted_output_folder is not None:
            self._open_folder_safely(self._predicted_output_folder)

    def _open_folder_safely(self, path: Path) -> None:
        try:
            self.folder_opener(path)
        except (OSError, ValueError) as exc:
            self._set_status(f"The output folder could not be opened: {exc}", error=True)

    def _validate_ready_plan(
        self,
        plan: PlanAutomationResult,
        invocation: CsvAutomationInvocation,
    ) -> str | None:
        effect = plan.effect
        if (
            effect is None
            or effect.mutates_inputs
            or effect.output_policy != "create_only"
        ):
            return "the effect is not create-only and source-preserving"
        if len(plan.inputs) != len(invocation.inputs):
            return "the returned workbook count changed"
        expected_ids = tuple(item.input_id for item in invocation.inputs)
        returned_ids = tuple(item.input_id for item in plan.inputs)
        if returned_ids != expected_ids:
            return "the returned workbook identities or order changed"
        if (
            effect.input_files != len(plan.inputs)
            or effect.output_files != len(plan.inputs)
            or effect.rows_to_write != sum(item.rows_to_write for item in plan.inputs)
        ):
            return "the returned effect totals are inconsistent"
        output_directory = self._output_directory
        if output_directory is None:
            return "the reviewed output directory is missing"
        try:
            expected_output_parent = output_directory.resolve(strict=True)
        except OSError:
            return "the reviewed output directory is unavailable"
        seen_outputs: set[str] = set()
        for expected, returned in zip(invocation.inputs, plan.inputs):
            try:
                original = Path(returned.original_path).resolve(strict=True)
                resolved = Path(returned.resolved_path).resolve(strict=True)
            except OSError:
                return "a returned source path is unavailable"
            if original != expected.path or resolved != expected.path:
                return "a returned source path does not match the request"
            if expected.worksheet is not None and returned.worksheet != expected.worksheet:
                return "a returned worksheet does not match the reviewed choice"
            output = Path(returned.output_path)
            if not output.is_absolute() or output.suffix.casefold() != ".csv":
                return "a returned output is not an absolute CSV path"
            try:
                output_parent = output.parent.resolve(strict=True)
            except OSError:
                return "a returned output directory is unavailable"
            if output_parent != expected_output_parent:
                return "a returned output escaped the chosen directory"
            output_key = os.path.normcase(str(output))
            if output_key in seen_outputs:
                return "the plan returned the same output more than once"
            seen_outputs.add(output_key)
            if output.exists():
                return "an output already exists; re-plan after choosing another folder"
        return None

    def _execution_result_is_consistent(
        self,
        result: ExecuteAutomationResult,
    ) -> bool:
        fingerprint = self._reviewed_fingerprint
        if (
            fingerprint is None
            or result.reviewed_plan_fingerprint != fingerprint
            or result.source_mutates_inputs
            or result.workbooks_saved != 0
            or result.outputs_overwritten != 0
            or (
                result.state in {"succeeded", "failed_after_partial_effect"}
                and result.final_plan_fingerprint != fingerprint
            )
        ):
            return False
        predicted = {
            os.path.normcase(str(path)): path for path in self._predicted_outputs
        }
        created: set[str] = set()
        for raw in result.outputs_created:
            path = Path(raw)
            key = os.path.normcase(str(path))
            if (
                not path.is_absolute()
                or path.suffix.casefold() != ".csv"
                or key in created
                or key not in predicted
            ):
                return False
            created.add(key)
        if result.state == "succeeded":
            return created == set(predicted)
        if result.state == "failed_before_effect":
            return not created
        return bool(created) and created.issubset(predicted)

    def _input_label(self, input_id: str) -> str:
        invocation = self._current_invocation
        if invocation is not None:
            match = next((item for item in invocation.inputs if item.input_id == input_id), None)
            if match is not None:
                return str(match.path)
        return input_id

    def _clear_review_identity(self) -> None:
        self._reviewed_invocation = None
        self._reviewed_fingerprint = None
        self._reviewed_warning_count = 0
        self._predicted_outputs = ()

    def _read_only_text(
        self,
        value: str,
        *,
        height: int,
        wrap: str,
        pady: tuple[int, int],
    ) -> tk.Text:
        host = ttk.Frame(self.content)
        host.pack(fill=tk.BOTH, expand=True, pady=pady)
        host.columnconfigure(0, weight=1)
        host.rowconfigure(0, weight=1)
        text = tk.Text(
            host,
            height=height,
            wrap=wrap,
            relief=tk.SOLID,
            borderwidth=1,
        )
        vertical = ttk.Scrollbar(host, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=vertical.set)
        text.grid(row=0, column=0, sticky=tk.NSEW)
        vertical.grid(row=0, column=1, sticky=tk.NS)
        if wrap == tk.NONE:
            horizontal = ttk.Scrollbar(
                host,
                orient=tk.HORIZONTAL,
                command=text.xview,
            )
            text.configure(xscrollcommand=horizontal.set)
            horizontal.grid(row=1, column=0, sticky=tk.EW)
        text.insert("1.0", value)
        text.configure(state=tk.DISABLED)
        return text

    def _clear_content(self) -> None:
        self._stop_progress()
        for child in self.content.winfo_children():
            child.destroy()
        self.primary_button = None
        self.secondary_button = None
        self.review_text = None
        self._worksheet_requirements_supported = False

    def _stop_progress(self) -> None:
        progress = self._progressbar
        self._progressbar = None
        if progress is not None:
            try:
                progress.stop()
            except tk.TclError:
                pass

    def _set_status(self, message: str, *, error: bool = False) -> None:
        self.status_var.set(message)
        self.status_label.configure(style="Error.TLabel" if error else "Status.TLabel")
        self.status_setter(message)


def _request_id() -> str:
    return uuid4().hex


def _csv_format_summary(invocation: CsvAutomationInvocation) -> str:
    delimiter = (
        "comma (,)"
        if invocation.delimiter == ","
        else repr(invocation.delimiter)
    )
    encoding = (
        "UTF-8 with BOM (utf-8-sig)"
        if invocation.encoding.casefold() == "utf-8-sig"
        else invocation.encoding
    )
    return (
        f"CSV format: {delimiter} delimiter · encoding: {encoding} · "
        f"formula mode: {invocation.formula_mode} · "
        f"Excel-safe escaping: {'on' if invocation.excel_safe else 'off'}"
    )


def _is_stale(code: str) -> bool:
    normalized = code.casefold()
    return "stale" in normalized or "fingerprint" in normalized


def _open_folder(path: Path) -> None:
    os.startfile(str(path))  # type: ignore[attr-defined]
