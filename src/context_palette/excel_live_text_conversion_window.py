"""Attended live-Excel workflow for reviewed column-to-text conversion."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable
from uuid import uuid4

from .excel_automation import (
    AutomationCallError,
    AutomationCallResult,
    DescribeCapabilitiesResult,
    ExcelAutomationCoordinator,
    ExcelAutomationInputError,
    ExcelAutomationSettings,
    ExcelAutomationSettingsError,
    ExcelCapability,
    LiveColumnConversionInvocation,
    LiveColumnConversionPlanInvocation,
    LiveColumnConversionPlanResult,
    LiveColumnConversionResult,
    LiveColumnPreflightInvocation,
    LiveColumnPreflightResult,
    LiveExcelInventoryResult,
    LiveExcelWorkbook,
    PythonExcelProcessClient,
    build_convert_live_column_representation_request,
    build_describe_capabilities_request,
    build_inventory_live_excel_request,
    build_plan_live_column_conversion_request,
    build_preflight_live_columns_request,
    discover_direct_sibling_python_excel_launcher,
    load_excel_automation_settings,
    save_excel_automation_settings,
)
from .excel_live_target_selector import (
    CapturedExcelSource,
    LiveExcelTargetSelector,
    can_return_to_captured_excel,
    inventory_process_ids,
    visible_inventory_workbooks,
)
from .hotkeys import focus_window
from .window_geometry import configure_standard_window


_POLL_MILLISECONDS = 50
_READ_TIMEOUT_SECONDS = 45.0
_PLAN_TIMEOUT_SECONDS = 90.0
_EXECUTE_TIMEOUT_SECONDS = 180.0
_REQUIRED_CAPABILITIES = (
    "inventory_live_excel",
    "preflight_live_columns",
    "plan_live_column_conversion",
    "convert_live_column_representation",
)
_PRE_EFFECT_CODES = frozenset(
    {
        "conflict.live_workbook_stale",
        "conflict.live_worksheet_stale",
        "conflict.live_conversion_plan_stale",
        "conflict.live_conversion_plan_blocked",
        "conflict.recovery_output_exists",
        "request.precision_risk_acknowledgement_required",
    }
)


class ExcelLiveTextConversionWindow:
    """Review and execute one recovery-backed live column conversion."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        settings_path: Path,
        status_setter: Callable[[str], None],
        source_window_handle: int | None = None,
        source_process_id: int | None = None,
        source_window_title: str = "",
        execution_enabled: bool = False,
        coordinator: ExcelAutomationCoordinator | None = None,
        client: PythonExcelProcessClient | None = None,
        file_opener: Callable[[Path], None] | None = None,
        folder_opener: Callable[[Path], None] | None = None,
        return_to_source: Callable[[int], bool] = focus_window,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        if coordinator is not None and client is not None:
            raise ValueError("Supply either coordinator or client, not both.")
        self.settings_path = Path(settings_path)
        self.status_setter = status_setter
        self.source_window_handle = source_window_handle
        self.source_process_id = source_process_id
        self.source_window_title = source_window_title.strip()
        self._captured_source = CapturedExcelSource(
            source_window_handle,
            source_process_id,
            self.source_window_title,
        )
        self.execution_enabled = bool(execution_enabled)
        self.coordinator = coordinator or ExcelAutomationCoordinator(client)
        self.file_opener = file_opener or (lambda _path: None)
        self.folder_opener = folder_opener or (lambda _path: None)
        self.return_to_source = return_to_source
        self.on_close = on_close or (lambda: None)

        self._launcher_path: Path | None = None
        self._poll_after_id: str | None = None
        self._closed = False
        self._progressbar: ttk.Progressbar | None = None
        self._inventory_process_ids: frozenset[int] = frozenset()
        self._workbooks_by_label: dict[str, LiveExcelWorkbook] = {}
        self._selected_workbook: LiveExcelWorkbook | None = None
        self._selected_worksheet: str | None = None
        self.target_selector: LiveExcelTargetSelector | None = None
        self._preflight_columns: list[object] = []
        self._preflight_column_indexes: set[int] = set()
        self._selected_preflight_column_indexes: set[int] = set()
        self._next_column_offset: int | None = None
        self._preflight_result: LiveColumnPreflightResult | None = None
        self._plan_invocation: LiveColumnConversionPlanInvocation | None = None
        self._plan_result: LiveColumnConversionPlanResult | None = None
        self._plan_correlated = False
        self.view_state = "starting"

        self.window = tk.Toplevel(parent)
        self.window.title("Convert scientific-notation columns")
        configure_standard_window(self.window, parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.transient(parent)

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            outer,
            text="Convert scientific-notation columns",
            style="Title.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            outer,
            text=(
                "Choose exact physical columns in an already-open workbook, "
                "review a zero-write plan, then create a recovery copy before conversion."
            ),
            style="Muted.TLabel",
            wraplength=720,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(2, 7))
        banner_text = (
            "Development/UAT: live text execution is enabled for this app session."
            if self.execution_enabled
            else (
                "Development/UAT: execution is disabled. Planning is available, "
                "but this build cannot change Excel."
            )
        )
        self.uat_banner = ttk.Label(
            outer,
            text=banner_text,
            style="Error.TLabel" if self.execution_enabled else "Muted.TLabel",
            wraplength=720,
            justify=tk.LEFT,
        )
        self.uat_banner.pack(fill=tk.X, pady=(0, 7))

        body = ttk.Frame(outer)
        body.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(body, highlightthickness=0, takefocus=False)
        body_scrollbar = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=body_scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky=tk.NSEW)
        body_scrollbar.grid(row=0, column=1, sticky=tk.NS)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.content = ttk.Frame(self.canvas)
        self._content_window_id = self.canvas.create_window(
            (0, 0), window=self.content, anchor=tk.NW
        )
        self.content.bind("<Configure>", self._content_configured)
        self.canvas.bind("<Configure>", self._canvas_configured)

        footer = ttk.Frame(outer)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        self.status_var = tk.StringVar()
        self.status_label = ttk.Label(
            footer,
            textvariable=self.status_var,
            style="Status.TLabel",
            wraplength=590,
            justify=tk.LEFT,
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.close_button = ttk.Button(footer, text="Close", command=self.close)
        self.close_button.pack(side=tk.RIGHT, padx=(8, 0))

        self.primary_button: ttk.Button | None = None
        self.refresh_button: ttk.Button | None = None
        self.workbook_var = tk.StringVar()
        self.worksheet_var = tk.StringVar()
        self.precision_ack_var = tk.BooleanVar(value=False)
        self.workbook_picker: ttk.Combobox | None = None
        self.worksheet_picker: ttk.Combobox | None = None
        self.columns_listbox: tk.Listbox | None = None
        self.result_text: tk.Text | None = None
        self.show()
        self.window.after_idle(self._load_settings)

    @property
    def busy(self) -> bool:
        return bool(self.coordinator.running)

    def show(self) -> None:
        if not self._closed:
            self.window.deiconify()
            self.window.lift()

    def close(self) -> bool:
        if self._closed:
            return True
        if self.busy or self.coordinator.completion_pending:
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
        if launcher is None:
            launcher = discover_direct_sibling_python_excel_launcher(
                self.settings_path.parent.parent
            )
        if launcher is None:
            self._show_setup(
                "Choose the Python Excel machine launcher on this computer. "
                "Excel features remain optional."
            )
            return
        if not launcher.is_file():
            self._show_setup(
                "The configured Python Excel launcher is unavailable on this computer."
            )
            return
        self._launcher_path = launcher
        self._start_capabilities()

    def _show_setup(self, message: str) -> None:
        self.view_state = "setup"
        self._clear_content()
        ttk.Label(self.content, text="Set up Python Excel", style="Heading.TLabel").pack(
            anchor=tk.W
        )
        ttk.Label(self.content, text=message, wraplength=700, justify=tk.LEFT).pack(
            anchor=tk.W, pady=(5, 10)
        )
        self.primary_button = ttk.Button(
            self.content,
            text="Browse for Python Excel launcher…",
            command=self._browse_launcher,
            style="Accent.TButton",
        )
        self.primary_button.pack(anchor=tk.W)
        self._set_status("Python Excel setup is required before open workbooks can be listed.")

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
            save_excel_automation_settings(
                self.settings_path, ExcelAutomationSettings(launcher)
            )
        except (ExcelAutomationSettingsError, OSError) as exc:
            self._set_status(str(exc), error=True)
            return
        self._launcher_path = launcher
        self.status_setter("Python Excel setup saved for this computer.")
        self._start_capabilities()

    def _start_capabilities(self) -> None:
        self.view_state = "capabilities"
        self._clear_content()
        self._show_working("Checking the exact live Excel capabilities…")
        self._start_call(
            build_describe_capabilities_request(_request_id()),
            phase="capabilities",
            timeout_seconds=_READ_TIMEOUT_SECONDS,
            callback=self._capabilities_completed,
        )

    def _capabilities_completed(self, call: AutomationCallResult) -> None:
        result = call.result
        if call.classification != "capabilities_succeeded" or not isinstance(
            result, DescribeCapabilitiesResult
        ):
            self._show_unavailable(call, "Python Excel capabilities are unavailable.")
            return
        capabilities = {item.operation: item for item in result.capabilities}
        missing: list[str] = []
        for operation in _REQUIRED_CAPABILITIES:
            item = capabilities.get(operation)
            if (
                item is None
                or item.operation_version != "1.0"
                or not item.availability.available
            ):
                missing.append(_capability_issue(operation, item))
        if missing:
            self.view_state = "capability_unavailable"
            self._clear_content()
            ttk.Label(
                self.content,
                text="Live text conversion unavailable",
                style="Heading.TLabel",
            ).pack(anchor=tk.W)
            self._show_text(missing, height=min(9, max(4, len(missing) + 1)))
            self._change_launcher_button()
            self._set_status(
                "The exact Python Excel 1.0 live conversion capabilities are required.",
                error=True,
            )
            return
        self._start_inventory()

    def _start_inventory(self) -> None:
        self.view_state = "inventory"
        self._reset_target_state()
        self._clear_content()
        self._show_working("Looking for already-open Excel workbooks…")
        self._start_call(
            build_inventory_live_excel_request(_request_id()),
            phase="inventory",
            timeout_seconds=_READ_TIMEOUT_SECONDS,
            callback=self._inventory_completed,
        )

    def _inventory_completed(self, call: AutomationCallResult) -> None:
        result = call.result
        if call.classification != "inventory_succeeded" or not isinstance(
            result, LiveExcelInventoryResult
        ):
            self._show_unavailable(call, "Open Excel workbooks are unavailable.")
            return
        self._inventory_process_ids = inventory_process_ids(result)
        workbooks = visible_inventory_workbooks(result)
        if not workbooks:
            self.view_state = "no_workbooks"
            self._clear_content()
            ttk.Label(
                self.content, text="No open Excel workbooks", style="Heading.TLabel"
            ).pack(anchor=tk.W)
            ttk.Label(
                self.content,
                text="Open a saved .xlsx workbook in Excel, then refresh this list.",
                wraplength=700,
                justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=(5, 10))
            self._refresh_inventory_button(accent=True)
            self._render_warnings(result.warnings)
            self._set_status("No visible Excel workbook is available yet.")
            return
        self._show_target_selection(workbooks, result)

    def _show_target_selection(
        self,
        workbooks: tuple[LiveExcelWorkbook, ...],
        inventory: LiveExcelInventoryResult,
    ) -> None:
        self.view_state = "select_target"
        self._clear_content()
        selector = LiveExcelTargetSelector(
            self.content,
            workbooks=workbooks,
            source=self._captured_source,
            refresh_command=self._start_inventory,
            selection_changed=self._target_selection_changed,
        )
        selector.pack(fill=tk.X)
        self.target_selector = selector
        self._workbooks_by_label = selector.workbooks_by_label
        self.workbook_var = selector.workbook_var
        self.worksheet_var = selector.worksheet_var
        self.workbook_picker = selector.workbook_picker
        self.worksheet_picker = selector.worksheet_picker
        self.refresh_button = selector.refresh_button
        self._sync_target_selection()

        ttk.Label(
            self.content,
            text=(
                "Only the selected worksheet and physical columns can be changed. "
                "Header row 1 is never converted."
            ),
            style="Muted.TLabel",
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(10, 0))
        self.primary_button = ttk.Button(
            self.content,
            text="Inspect physical columns",
            command=self._start_first_preflight,
            style="Accent.TButton",
        )
        self.primary_button.pack(anchor=tk.W, pady=(12, 0))
        self._render_warnings(inventory.warnings)
        self._update_inspect_state()

    def _sync_target_selection(self) -> None:
        selector = self.target_selector
        if selector is None:
            return
        self._selected_workbook = selector.selected_workbook
        self._selected_worksheet = selector.selected_worksheet

    def _target_selection_changed(self) -> None:
        self._sync_target_selection()
        self._update_inspect_state()

    def _workbook_changed(self, _event: tk.Event | None = None) -> None:
        if self.target_selector is not None:
            self.target_selector.select_workbook_from_variable(_event)

    def _worksheet_changed(self, _event: tk.Event | None = None) -> None:
        if self.target_selector is not None:
            self.target_selector.select_worksheet_from_variable(_event)

    def _update_inspect_state(self) -> None:
        if self.primary_button is None:
            return
        allowed = self._selected_workbook is not None and self._selected_worksheet is not None
        self.primary_button.configure(state=tk.NORMAL if allowed else tk.DISABLED)
        self._set_status(
            "Choose the exact open workbook and visible worksheet, then inspect columns."
            if allowed
            else "The selected workbook has no visible worksheet.",
            error=not allowed,
        )

    def _start_first_preflight(self) -> None:
        self._preflight_columns.clear()
        self._preflight_column_indexes.clear()
        self._selected_preflight_column_indexes.clear()
        self._next_column_offset = None
        self._start_preflight(0)

    def _start_preflight(self, column_offset: int) -> None:
        workbook = self._selected_workbook
        worksheet = self._selected_worksheet
        if workbook is None or worksheet is None:
            self._set_status("Choose an open workbook and worksheet first.", error=True)
            return
        if self.columns_listbox is not None:
            self._selected_preflight_column_indexes.update(self._selected_columns())
        try:
            invocation = LiveColumnPreflightInvocation(
                workbook.token, worksheet, column_offset=column_offset
            )
        except ExcelAutomationInputError as exc:
            self._set_status(str(exc), error=True)
            return
        self.view_state = "preflight"
        self._clear_content()
        self._show_working("Inspecting bounded physical columns without changing Excel…")
        self._start_call(
            build_preflight_live_columns_request(_request_id(), invocation),
            phase="preflight",
            timeout_seconds=_READ_TIMEOUT_SECONDS,
            callback=lambda call: self._preflight_completed(call, invocation),
        )

    def _preflight_completed(
        self,
        call: AutomationCallResult,
        invocation: LiveColumnPreflightInvocation,
    ) -> None:
        result = call.result
        if call.classification == "outer_error" and call.error is not None:
            self._show_pre_effect_error(call.error)
            return
        if call.classification != "preflight_succeeded" or not isinstance(
            result, LiveColumnPreflightResult
        ):
            self._show_unavailable(call, "Column preflight could not complete.")
            return
        if not self._preflight_matches(result, invocation):
            self._show_unknown("The preflight response did not match the selected target.")
            return
        for column in result.columns:
            if column.column_index not in self._preflight_column_indexes:
                self._preflight_columns.append(column)
                self._preflight_column_indexes.add(column.column_index)
        self._preflight_result = result
        self._next_column_offset = result.next_column_offset
        self._show_preflight_selection(result)

    def _preflight_matches(
        self,
        result: LiveColumnPreflightResult,
        invocation: LiveColumnPreflightInvocation,
    ) -> bool:
        workbook = self._selected_workbook
        if workbook is None:
            return False
        indexes = tuple(column.column_index for column in result.columns)
        return (
            result.workbook.token == invocation.workbook_token == workbook.token
            and result.workbook.process_id == workbook.process_id
            and result.worksheet == invocation.worksheet == self._selected_worksheet
            and result.header_row == 1
            and len(indexes) == len(set(indexes))
            and all(index > invocation.column_offset for index in indexes)
        )

    def _show_preflight_selection(self, result: LiveColumnPreflightResult) -> None:
        self.view_state = "select_columns"
        self._clear_content()
        ttk.Label(
            self.content, text="Choose physical columns", style="Heading.TLabel"
        ).pack(anchor=tk.W)
        ttk.Label(
            self.content,
            text=(
                f"Worksheet: {result.worksheet} · data rows examined: "
                f"{result.data_rows.examined} of {result.data_rows.total}. "
                "Blank and duplicate headers remain separate because column coordinates are authoritative."
            ),
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 7))
        frame = ttk.Frame(self.content)
        frame.pack(fill=tk.BOTH, expand=True)
        self.columns_listbox = tk.Listbox(
            frame,
            selectmode=tk.EXTENDED,
            exportselection=False,
            height=10,
            activestyle="dotbox",
        )
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.columns_listbox.yview)
        self.columns_listbox.configure(yscrollcommand=scrollbar.set)
        self.columns_listbox.grid(row=0, column=0, sticky=tk.NSEW)
        scrollbar.grid(row=0, column=1, sticky=tk.NS)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        for column in self._preflight_columns:
            self.columns_listbox.insert(tk.END, _column_label(column))
        for index, column in enumerate(self._preflight_columns):
            if column.column_index in self._selected_preflight_column_indexes:
                self.columns_listbox.selection_set(index)
        self.columns_listbox.bind("<<ListboxSelect>>", self._column_selection_changed)
        if self._next_column_offset is not None:
            ttk.Label(
                self.content,
                text=(
                    "The column inventory is truncated. Load more to inspect later "
                    "physical columns; already listed columns remain selectable."
                ),
                style="Muted.TLabel",
                wraplength=700,
                justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=(7, 3))
            ttk.Button(
                self.content,
                text="Load more columns",
                command=lambda: self._start_preflight(self._next_column_offset or 0),
            ).pack(anchor=tk.W)
        self.primary_button = ttk.Button(
            self.content,
            text="Review conversion plan",
            command=lambda: self._start_plan(None),
            style="Accent.TButton",
            state=tk.DISABLED,
        )
        self.primary_button.pack(anchor=tk.W, pady=(10, 0))
        self._refresh_inventory_button()
        self._render_warnings(result.warnings)
        self._column_selection_changed()

    def _column_selection_changed(self, _event: tk.Event | None = None) -> None:
        if self.primary_button is None or self.columns_listbox is None:
            return
        selected = bool(self.columns_listbox.curselection())
        self._selected_preflight_column_indexes = set(self._selected_columns())
        preflight_complete = self._next_column_offset is None
        self.primary_button.configure(
            state=tk.NORMAL if selected and preflight_complete else tk.DISABLED
        )
        self._set_status(
            (
                "Load all remaining column pages before reviewing a conversion plan."
                if not preflight_complete
                else (
                    "Review the exact conversion plan for the selected physical columns."
                    if selected
                    else "Select one or more exact physical columns."
                )
            )
        )

    def _selected_columns(self) -> tuple[int, ...]:
        if self.columns_listbox is None:
            return ()
        try:
            selected = self.columns_listbox.curselection()
        except tk.TclError:
            return tuple(sorted(self._selected_preflight_column_indexes))
        return tuple(
            self._preflight_columns[index].column_index
            for index in selected
        )

    def _start_plan(self, recovery_path: str | None) -> None:
        workbook = self._selected_workbook
        worksheet = self._selected_worksheet
        columns = (
            self._plan_invocation.columns
            if recovery_path is not None and self._plan_invocation is not None
            else self._selected_columns()
        )
        if not columns and self._plan_invocation is not None:
            columns = self._plan_invocation.columns
        if workbook is None or worksheet is None or not columns:
            self._set_status("Select one or more physical columns first.", error=True)
            return
        try:
            invocation = LiveColumnConversionPlanInvocation(
                workbook.token,
                worksheet,
                columns,
                recovery_path=recovery_path,
            )
        except ExcelAutomationInputError as exc:
            self._set_status(str(exc), error=True)
            return
        self._plan_invocation = invocation
        self._plan_result = None
        self._plan_correlated = False
        self.view_state = "planning"
        self._clear_content()
        self._show_working("Building an exact zero-write conversion plan…")
        self._start_call(
            build_plan_live_column_conversion_request(_request_id(), invocation),
            phase="conversion_plan",
            timeout_seconds=_PLAN_TIMEOUT_SECONDS,
            callback=lambda call: self._plan_completed(call, invocation),
        )

    def _plan_completed(
        self,
        call: AutomationCallResult,
        invocation: LiveColumnConversionPlanInvocation,
    ) -> None:
        if call.classification == "outer_error" and call.error is not None:
            self._show_pre_effect_error(call.error)
            return
        result = call.result
        if call.classification not in {
            "conversion_plan_ready",
            "conversion_plan_blocked",
        } or not isinstance(result, LiveColumnConversionPlanResult):
            self._show_unavailable(call, "The conversion plan could not be trusted.")
            return
        self._plan_result = result
        self._plan_correlated = self._plan_matches(result, invocation)
        if not self._plan_correlated:
            self._show_unknown("The plan response did not match the reviewed target.")
            return
        self._show_plan(result)

    @staticmethod
    def _plan_matches(
        result: LiveColumnConversionPlanResult,
        invocation: LiveColumnConversionPlanInvocation,
    ) -> bool:
        return (
            result.target.workbook_token == invocation.workbook_token
            and result.target.worksheet == invocation.worksheet
            and result.target.physical_columns == invocation.columns
            and result.effect.target_type == "text"
            and result.target.header_row == 1
            and result.writes_performed == 0
            and (
                invocation.recovery_path is None
                or result.recovery.path == invocation.recovery_path
            )
        )

    def _show_plan(self, result: LiveColumnConversionPlanResult) -> None:
        self.view_state = "plan_ready" if result.can_execute else "plan_blocked"
        self._clear_content()
        ttk.Label(
            self.content,
            text="Review exact conversion plan",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        recovery = result.recovery.path or "Unavailable"
        lines = [
            f"Workbook: {result.target.workbook_name}",
            f"Worksheet: {result.target.worksheet}",
            "Physical columns: "
            + ", ".join(str(value) for value in result.target.physical_columns),
            (
                "Cells: "
                f"{result.effect.eligible} eligible · "
                f"{result.effect.already_compliant} compliant · "
                f"{result.effect.blank} blank · {result.effect.blocked} blocked"
            ),
            (
                f"Blockers in scope: {result.effect.formulas} formula · "
                f"{result.effect.unsupported} unsupported"
            ),
            f"Precision-risk cells: {result.effect.precision_risk_cells}",
            f"Recovery copy: {recovery}",
            f"Can execute: {'Yes' if result.can_execute else 'No'}",
            f"Plan fingerprint: {result.plan_fingerprint}",
            (
                "Fixed bounds: header row 1 · up to 10,000 data rows · "
                "10 samples per column."
            ),
        ]
        for column in result.columns:
            lines.append(
                f"{column.column_index} · {column.column_letter} · "
                f"{_header_text(column.header_value)}"
            )
            counts = column.counts
            lines.append(
                "  "
                f"eligible {counts.eligible}; compliant {counts.already_compliant}; "
                f"blank {counts.blank}; formula {counts.blocked_formula}; "
                f"unsupported {counts.blocked_unsupported}; precision risk {counts.precision_risk_cells}"
            )
            for sample in column.conversion_samples:
                lines.append(
                    f"  row {sample.row}: {sample.input_preview} → {sample.output_text}"
                )
            for risk in column.precision_risks:
                lines.append(
                    f"  precision row {risk.row}: {risk.value_preview} ({risk.code})"
                )
        if result.blockers:
            lines.append("Blockers")
            lines.extend(f"  {item.code}: {item.message}" for item in result.blockers)
        if result.warnings:
            lines.append("Warnings")
            lines.extend(f"  {item.code}: {item.message}" for item in result.warnings)
        self._show_text(lines, height=13)

        controls = ttk.Frame(self.content)
        controls.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(
            controls,
            text="Choose another recovery path…",
            command=self._choose_recovery_path,
        ).pack(side=tk.LEFT)
        if result.effect.precision_risk_cells:
            self.precision_ack_var.set(False)
            acknowledgement = ttk.Checkbutton(
                self.content,
                text=(
                    "I understand Excel may already have discarded digits; conversion "
                    "preserves only Excel's current value and cannot reconstruct lost digits. "
                    "Python Excel will create the reviewed recovery copy first."
                ),
                variable=self.precision_ack_var,
                command=self._update_execute_state,
            )
            acknowledgement.pack(anchor=tk.W, fill=tk.X, pady=(9, 0))
        self.primary_button = ttk.Button(
            self.content,
            text="Execute reviewed text conversion",
            command=self._execute,
            style="Accent.TButton",
        )
        self.primary_button.pack(anchor=tk.W, pady=(10, 0))
        self._refresh_inventory_button()
        self._return_button()
        self._update_execute_state()
        if not self.execution_enabled:
            self._set_status(
                "Execution is disabled by the Development/UAT gate; the reviewed plan remains read-only.",
                error=True,
            )
        elif not result.can_execute:
            self._set_status("The engine plan is blocked. Excel has not changed.", error=True)
        else:
            self._set_status("Review every effect, recovery path, and warning before Execute.")

    def _choose_recovery_path(self) -> None:
        result = self._plan_result
        if result is None:
            return
        initial = Path(result.recovery.path) if result.recovery.path else None
        selected = filedialog.asksaveasfilename(
            parent=self.window,
            title="Choose a future sibling recovery workbook",
            initialdir=str(initial.parent) if initial is not None else None,
            initialfile=initial.name if initial is not None else None,
            defaultextension=".xlsx",
            filetypes=(("Excel workbooks", "*.xlsx"),),
            confirmoverwrite=False,
        )
        if selected:
            self._start_plan(selected)

    def _update_execute_state(self) -> None:
        button = self.primary_button
        result = self._plan_result
        if button is None or result is None:
            return
        precision_ok = (
            result.effect.precision_risk_cells == 0 or self.precision_ack_var.get()
        )
        recovery_ok = bool(result.recovery.path)
        allowed = (
            self.execution_enabled
            and result.can_execute
            and self._plan_correlated
            and precision_ok
            and recovery_ok
        )
        button.configure(state=tk.NORMAL if allowed else tk.DISABLED)

    def _execute(self) -> None:
        result = self._plan_result
        invocation = self._plan_invocation
        if result is None or invocation is None or not self._plan_correlated:
            self._show_unknown("The reviewed plan is no longer available.")
            return
        if not self.execution_enabled or not result.can_execute or not result.recovery.path:
            self._set_status("This reviewed plan cannot be executed.", error=True)
            return
        acknowledgement = bool(
            result.effect.precision_risk_cells and self.precision_ack_var.get()
        )
        if result.effect.precision_risk_cells and not acknowledgement:
            self._set_status("Acknowledge the irreversible precision risk first.", error=True)
            return
        try:
            execute_invocation = LiveColumnConversionInvocation(
                invocation.workbook_token,
                invocation.worksheet,
                invocation.columns,
                result.plan_fingerprint,
                result.recovery.path,
                acknowledge_irreversible_precision_risk=acknowledgement,
            )
        except ExcelAutomationInputError as exc:
            self._set_status(str(exc), error=True)
            return
        self.view_state = "executing"
        self._clear_content()
        self._show_working(
            "Creating and verifying the recovery copy, then converting the reviewed columns…"
        )
        self._start_call(
            build_convert_live_column_representation_request(
                _request_id(), execute_invocation
            ),
            phase="conversion_execute",
            timeout_seconds=_EXECUTE_TIMEOUT_SECONDS,
            callback=lambda call: self._execute_completed(call, execute_invocation),
        )

    def _execute_completed(
        self,
        call: AutomationCallResult,
        invocation: LiveColumnConversionInvocation,
    ) -> None:
        if call.classification == "outer_error" and call.error is not None:
            if call.error.code in _PRE_EFFECT_CODES:
                self._show_pre_effect_error(call.error)
            else:
                self._show_unknown(
                    "Python Excel returned an error without a trustworthy mutation receipt."
                )
            return
        result = call.result
        if call.classification == "conversion_execute_unknown" or not isinstance(
            result, LiveColumnConversionResult
        ):
            self._show_unknown(call.reason or "No trustworthy execution result was received.")
            return
        if not self._execution_matches(result, invocation):
            self._show_unknown("The execution result did not match the reviewed plan.")
            return
        self._show_execution_result(result)

    @staticmethod
    def _execution_matches(
        result: LiveColumnConversionResult,
        invocation: LiveColumnConversionInvocation,
    ) -> bool:
        return (
            result.target.workbook_token == invocation.workbook_token
            and result.target.worksheet == invocation.worksheet
            and result.target.physical_columns == invocation.columns
            and result.reviewed_plan_fingerprint == invocation.expected_plan_fingerprint
            and result.recovery.path == invocation.recovery_path
            and not result.workbook_saved
            and not result.workbook_closed
            and not result.application_closed
            and (
                (result.state == "succeeded" and result.mutation_started)
                or (result.state == "failed" and not result.mutation_started)
                or (result.state == "partial_failure" and result.mutation_started)
            )
        )

    def _show_execution_result(self, result: LiveColumnConversionResult) -> None:
        self.view_state = result.state
        self._clear_content()
        heading = {
            "succeeded": "Excel columns converted to text",
            "failed": "Conversion stopped before workbook mutation",
            "partial_failure": "Excel workbook may be partly converted",
        }[result.state]
        ttk.Label(self.content, text=heading, style="Heading.TLabel").pack(anchor=tk.W)
        lines = [
            f"Workbook: {result.target.workbook_name}",
            f"Worksheet: {result.target.worksheet}",
            f"Changed: {result.changed_cells}",
            f"Already compliant: {result.already_compliant_cells}",
            f"Blank: {result.blank_cells}",
            "Completed columns: "
            + (", ".join(str(value) for value in result.columns_completed) or "None"),
            f"Recovery: {result.recovery.path}",
            f"Recovery verified: {'Yes' if result.recovery.verified else 'No'}",
            f"Workbook remains open and unsaved: {'Yes' if result.workbook_dirty else 'No mutation'}",
        ]
        if result.failure is not None:
            lines.append(f"Failure: {result.failure.code} — {result.failure.message}")
        if result.warnings:
            lines.extend(f"Warning: {item.message}" for item in result.warnings)
        self._show_text(lines, height=10)
        if result.recovery.verified:
            ttk.Button(
                self.content,
                text="Review recovery workbook",
                command=lambda: self._open_recovery(Path(result.recovery.path)),
            ).pack(anchor=tk.W, pady=(9, 0))
            ttk.Button(
                self.content,
                text="Open recovery folder",
                command=lambda: self._open_recovery_folder(Path(result.recovery.path)),
            ).pack(anchor=tk.W, pady=(5, 0))
        self._refresh_inventory_button()
        self._return_button()
        if result.state == "succeeded":
            self._set_status(
                "Conversion succeeded. Excel remains open, dirty, and unsaved; review it before saving."
            )
        elif result.state == "failed":
            self._set_status(
                "No workbook mutation began. Review any verified recovery copy before starting a new workflow.",
                error=True,
            )
        else:
            self._set_status(
                "Possible partial modification. Do not retry automatically; inspect Excel, close without saving, or review recovery.",
                error=True,
            )

    def _show_pre_effect_error(self, error: AutomationCallError) -> None:
        self.view_state = "failed_before_effect"
        self._clear_content()
        ttk.Label(
            self.content,
            text="Excel changed before the reviewed operation",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            self.content,
            text=error.message,
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 8))
        ttk.Label(
            self.content,
            text="No conversion retry is started. Refresh inventory and review a new plan.",
            style="Muted.TLabel",
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W)
        self._refresh_inventory_button(accent=True)
        self._return_button()
        self._set_status("The reviewed target is stale or blocked; refresh before any new plan.", error=True)

    def _show_unknown(self, reason: str) -> None:
        self.view_state = "unknown"
        self._clear_content()
        ttk.Label(
            self.content,
            text="Excel conversion outcome unknown",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            self.content,
            text=(
                "Context Palette did not receive a trustworthy final receipt. The workbook "
                "may have changed. Do not retry automatically; inspect Excel first."
            ),
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 6))
        if reason:
            ttk.Label(
                self.content,
                text=reason,
                style="Muted.TLabel",
                wraplength=700,
                justify=tk.LEFT,
            ).pack(anchor=tk.W)
        recovery_path = (
            self._plan_result.recovery.path
            if self._plan_result is not None
            else None
        )
        if recovery_path:
            ttk.Label(
                self.content,
                text=(
                    "Reviewed recovery location (the file may or may not have "
                    f"been created): {recovery_path}"
                ),
                style="Muted.TLabel",
                wraplength=700,
                justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=(6, 0))
            ttk.Button(
                self.content,
                text="Open reviewed recovery folder",
                command=lambda: self._open_recovery_folder(Path(recovery_path)),
            ).pack(anchor=tk.W, pady=(8, 0))
        self._refresh_inventory_button()
        self._return_button()
        self._set_status("Outcome unknown. Inspect Excel before starting a new workflow.", error=True)

    def _show_unavailable(self, call: AutomationCallResult, fallback: str) -> None:
        self.view_state = "unavailable"
        self._clear_content()
        ttk.Label(
            self.content, text="Python Excel unavailable", style="Heading.TLabel"
        ).pack(anchor=tk.W)
        message = call.error.message if call.error is not None else call.reason
        ttk.Label(
            self.content,
            text=message or fallback,
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 10))
        self._change_launcher_button()
        self._set_status("Only this optional Excel workflow is unavailable.", error=True)

    def _change_launcher_button(self) -> None:
        self.primary_button = ttk.Button(
            self.content,
            text="Change Python Excel launcher…",
            command=self._browse_launcher,
        )
        self.primary_button.pack(anchor=tk.W, pady=(8, 0))

    def _refresh_inventory_button(self, *, accent: bool = False) -> None:
        self.refresh_button = ttk.Button(
            self.content,
            text="Refresh open workbooks",
            command=self._start_inventory,
            style="Accent.TButton" if accent else "TButton",
        )
        self.refresh_button.pack(anchor=tk.W, pady=(8, 0))

    def _return_button(self) -> None:
        if not can_return_to_captured_excel(
            self._captured_source, self._inventory_process_ids
        ):
            return
        ttk.Button(
            self.content,
            text="Return to Excel",
            command=self._return_to_excel,
        ).pack(anchor=tk.W, pady=(8, 0))

    def _return_to_excel(self) -> None:
        handle = self.source_window_handle
        if handle is None or not self.return_to_source(handle):
            self._set_status(
                "The captured Excel window is no longer available; select it manually.",
                error=True,
            )
            return
        self._set_status("Returned to the captured Excel window.")

    def _open_recovery(self, path: Path) -> None:
        try:
            self.file_opener(path)
        except OSError as exc:
            self._set_status(f"Recovery workbook could not be opened: {exc}", error=True)

    def _open_recovery_folder(self, path: Path) -> None:
        try:
            self.folder_opener(path.parent)
        except OSError as exc:
            self._set_status(f"Recovery folder could not be opened: {exc}", error=True)

    def _render_warnings(self, warnings: tuple[object, ...]) -> None:
        if warnings:
            ttk.Label(
                self.content,
                text="Warnings: "
                + " · ".join(getattr(item, "message", "Warning") for item in warnings),
                style="Muted.TLabel",
                wraplength=700,
                justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=(8, 0))

    def _show_text(self, lines: list[str], *, height: int) -> None:
        frame = ttk.Frame(self.content)
        frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        text = tk.Text(frame, height=height, wrap=tk.WORD, takefocus=True, padx=6, pady=6)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.grid(row=0, column=0, sticky=tk.NSEW)
        scrollbar.grid(row=0, column=1, sticky=tk.NS)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        text.insert("1.0", "\n".join(lines))
        text.configure(state=tk.DISABLED)
        self.result_text = text

    def _show_working(self, message: str) -> None:
        ttk.Label(
            self.content, text=message, style="Heading.TLabel", wraplength=700
        ).pack(anchor=tk.W)
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
        if not self.coordinator.start(
            launcher,
            request,
            phase=phase,  # type: ignore[arg-type]
            timeout_seconds=timeout_seconds,
            on_complete=callback,
        ):
            self._show_unknown("Another Excel automation workflow is already running.")
            return
        self.close_button.configure(state=tk.DISABLED)
        self._schedule_poll()

    def _schedule_poll(self) -> None:
        if not self._closed and self._poll_after_id is None:
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

    def _clear_content(self) -> None:
        self._stop_progress()
        for child in self.content.winfo_children():
            child.destroy()
        self.target_selector = None
        self.primary_button = None
        self.refresh_button = None
        self.result_text = None
        self.canvas.yview_moveto(0)

    def _stop_progress(self) -> None:
        if self._progressbar is not None:
            try:
                self._progressbar.stop()
            except tk.TclError:
                pass
        self._progressbar = None

    def _reset_target_state(self) -> None:
        self._workbooks_by_label.clear()
        self._selected_workbook = None
        self._selected_worksheet = None
        self._preflight_columns.clear()
        self._preflight_column_indexes.clear()
        self._selected_preflight_column_indexes.clear()
        self._next_column_offset = None
        self._preflight_result = None
        self._plan_invocation = None
        self._plan_result = None
        self._plan_correlated = False

    def _set_status(self, message: str, *, error: bool = False) -> None:
        self.status_var.set(message)
        self.status_label.configure(style="Error.TLabel" if error else "Status.TLabel")
        self.status_setter(message)

    def _content_configured(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _canvas_configured(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._content_window_id, width=event.width)


def _column_label(column: object) -> str:
    return (
        f"{getattr(column, 'column_index')} · {getattr(column, 'column_letter')} · "
        f"{_header_text(getattr(column, 'header_value'))}"
    )


def _header_text(value: object) -> str:
    if value is None or value == "":
        return "(blank header)"
    return str(value)


def _capability_issue(operation: str, capability: ExcelCapability | None) -> str:
    if capability is None:
        return f"{operation} 1.0 is missing."
    if capability.operation_version != "1.0":
        return f"{operation} requires version 1.0; engine reported {capability.operation_version}."
    reason = capability.availability.reason or "the live backend is unavailable"
    return f"{operation} 1.0 is unavailable: {reason}."


def _request_id() -> str:
    return f"context-palette-{uuid4().hex}"
