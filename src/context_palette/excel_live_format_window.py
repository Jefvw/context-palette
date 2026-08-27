"""Fast attended Tk workflow for applying one live Excel format template."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable
from uuid import uuid4

from .excel_automation import (
    AutomationCallResult,
    ExcelAutomationCoordinator,
    ExcelAutomationSettings,
    ExcelAutomationSettingsError,
    LiveExcelInventoryResult,
    LiveExcelWorkbook,
    LiveFormatProfileInvocation,
    LiveFormatProfileResult,
    PythonExcelProcessClient,
    build_apply_live_format_profile_request,
    build_inventory_live_excel_request,
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
_INVENTORY_TIMEOUT_SECONDS = 30.0
_APPLY_TIMEOUT_SECONDS = 120.0
_STALE_CODES = frozenset(
    {"conflict.live_workbook_stale", "conflict.live_worksheet_stale"}
)
_KNOWN_PRE_EFFECT_CODES = _STALE_CODES | {
    "conflict.live_autosave_enabled",
    "conflict.live_worksheet_not_visible",
    "conflict.live_no_visible_worksheets",
}


class ExcelLiveFormatWindow:
    """Choose an open workbook and apply the fixed format profile once."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        settings_path: Path,
        status_setter: Callable[[str], None],
        source_window_handle: int | None = None,
        source_process_id: int | None = None,
        source_window_title: str = "",
        coordinator: ExcelAutomationCoordinator | None = None,
        client: PythonExcelProcessClient | None = None,
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
        self.coordinator = coordinator or ExcelAutomationCoordinator(client)
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
        self._selected_scope = "worksheet"
        self.target_selector: LiveExcelTargetSelector | None = None
        self.view_state = "starting"

        self.window = tk.Toplevel(parent)
        self.window.title("Apply Excel format template")
        configure_standard_window(self.window, parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.transient(parent)

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            outer, text="Apply Excel format template", style="Title.TLabel"
        ).pack(anchor=tk.W)
        ttk.Label(
            outer,
            text="Choose an already-open workbook. Context Palette never saves or closes Excel.",
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
        self.refresh_button: ttk.Button | None = None
        self.workbook_var = tk.StringVar()
        self.scope_var = tk.StringVar(value="worksheet")
        self.worksheet_var = tk.StringVar()
        self.workbook_picker: ttk.Combobox | None = None
        self.worksheet_picker: ttk.Combobox | None = None
        self.result_text: tk.Text | None = None
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
        self._start_inventory()

    def _show_setup(self, message: str) -> None:
        self.view_state = "setup"
        self._clear_content()
        ttk.Label(self.content, text="Set up Python Excel", style="Heading.TLabel").pack(
            anchor=tk.W
        )
        ttk.Label(
            self.content, text=message, wraplength=700, justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(5, 10))
        ttk.Label(
            self.content,
            text=(
                "Select the absolute .bat launcher supplied by Python Excel. "
                "This machine-local setting needs no administrator rights."
            ),
            style="Muted.TLabel",
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 10))
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
        self._start_inventory()

    def _start_inventory(self) -> None:
        self.view_state = "inventory"
        self._clear_content()
        self._show_working("Looking for already-open Excel workbooks…")
        self._start_call(
            build_inventory_live_excel_request(_request_id()),
            phase="inventory",
            timeout_seconds=_INVENTORY_TIMEOUT_SECONDS,
            callback=self._inventory_completed,
        )

    def _inventory_completed(self, call: AutomationCallResult) -> None:
        if call.classification != "inventory_succeeded" or not isinstance(
            call.result, LiveExcelInventoryResult
        ):
            self._show_inventory_failure(call)
            return
        self._inventory_process_ids = inventory_process_ids(call.result)
        workbooks = visible_inventory_workbooks(call.result)
        if not workbooks:
            self._show_no_workbooks(call.result)
            return
        self._show_selection(workbooks, call.result)

    def _show_no_workbooks(self, result: LiveExcelInventoryResult) -> None:
        self.view_state = "no_workbooks"
        self._clear_content()
        ttk.Label(
            self.content, text="No open Excel workbooks", style="Heading.TLabel"
        ).pack(anchor=tk.W)
        ttk.Label(
            self.content,
            text="Open the workbook in Excel, then refresh this list.",
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 10))
        self.refresh_button = ttk.Button(
            self.content,
            text="Refresh open workbooks",
            command=self._start_inventory,
            style="Accent.TButton",
        )
        self.refresh_button.pack(anchor=tk.W)
        self._render_warnings(result.warnings)
        self._set_status("No visible Excel workbook is available yet.")

    def _show_selection(
        self,
        workbooks: tuple[LiveExcelWorkbook, ...],
        inventory: LiveExcelInventoryResult,
    ) -> None:
        self.view_state = "select"
        self._clear_content()
        selector = LiveExcelTargetSelector(
            self.content,
            workbooks=workbooks,
            source=self._captured_source,
            refresh_command=self._start_inventory,
            selection_changed=self._target_selection_changed,
            allow_all_visible_worksheets=True,
        )
        selector.pack(fill=tk.X)
        self.target_selector = selector
        self._workbooks_by_label = selector.workbooks_by_label
        self.workbook_var = selector.workbook_var
        self.scope_var = selector.scope_var
        self.worksheet_var = selector.worksheet_var
        self.workbook_picker = selector.workbook_picker
        self.worksheet_picker = selector.worksheet_picker
        self.refresh_button = selector.refresh_button
        self._sync_target_selection()

        ttk.Separator(self.content).pack(fill=tk.X, pady=12)
        ttk.Label(self.content, text="What Apply does", style="Heading.TLabel").pack(
            anchor=tk.W
        )
        ttk.Label(
            self.content,
            text=(
                "Uses Aptos 11 in the used range, styles row 1, freezes the top row, "
                "and adds a filter only when one is absent. Existing filters remain. "
                "Hidden worksheets are skipped for all-visible scope."
            ),
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(3, 3))
        self.limitation_label = ttk.Label(
            self.content,
            text=(
                "Changes the open workbook now. Excel Undo may be cleared. There is no backup "
                "or rollback. Enabled AutoSave is rejected; Context Palette never saves or closes Excel."
            ),
            style="Muted.TLabel",
            wraplength=700,
            justify=tk.LEFT,
        )
        self.limitation_label.pack(anchor=tk.W)
        self.primary_button = ttk.Button(
            self.content,
            text="Apply template",
            command=self._apply,
            style="Accent.TButton",
        )
        self.primary_button.pack(anchor=tk.W, pady=(12, 0))
        self._set_status("Choose the target, then Apply template. The workbook will not be saved or closed.")
        self._render_warnings(inventory.warnings)
        self._update_apply_state()

    def _sync_target_selection(self) -> None:
        selector = self.target_selector
        if selector is None:
            return
        self._selected_workbook = selector.selected_workbook
        self._selected_worksheet = selector.selected_worksheet
        self._selected_scope = selector.selected_scope

    def _target_selection_changed(self) -> None:
        self._sync_target_selection()
        self._update_apply_state()

    def _workbook_changed(self, _event: tk.Event | None = None) -> None:
        if self.target_selector is not None:
            self.target_selector.select_workbook_from_variable(_event)

    def _worksheet_changed(self, _event: tk.Event | None = None) -> None:
        if self.target_selector is not None:
            self.target_selector.select_worksheet_from_variable(_event)

    def _scope_changed(self) -> None:
        if self.target_selector is not None:
            self.target_selector.select_scope_from_variable()

    def _update_apply_state(self) -> None:
        button = self.primary_button
        workbook = self._selected_workbook
        if button is None or workbook is None:
            return
        has_visible_sheet = any(sheet.state == "visible" for sheet in workbook.sheets)
        worksheet_ok = (
            self._selected_scope == "workbook"
            or self._selected_worksheet is not None
        )
        autosave_blocked = workbook.autosave_enabled is True
        allowed = has_visible_sheet and worksheet_ok and not autosave_blocked
        button.configure(state=tk.NORMAL if allowed else tk.DISABLED)
        if autosave_blocked:
            self._set_status("AutoSave is enabled for this workbook. Turn it off in Excel, then Refresh.", error=True)
        elif not has_visible_sheet:
            self._set_status("This workbook has no visible worksheet to format.", error=True)
        else:
            self._set_status(
                "Choose the target, then Apply template. The workbook will not "
                "be saved or closed."
            )

    def _apply(self) -> None:
        workbook = self._selected_workbook
        if workbook is None:
            self._set_status("Choose an open workbook first.", error=True)
            return
        worksheet = self._selected_worksheet if self._selected_scope == "worksheet" else None
        try:
            invocation = LiveFormatProfileInvocation(
                workbook.token,
                scope=self._selected_scope,  # type: ignore[arg-type]
                worksheet=worksheet,
            )
        except ValueError as exc:
            self._set_status(str(exc), error=True)
            return
        self.view_state = "applying"
        self._clear_content()
        self._show_working("Applying the Excel format template…")
        self._start_call(
            build_apply_live_format_profile_request(_request_id(), invocation),
            phase="apply",
            timeout_seconds=_APPLY_TIMEOUT_SECONDS,
            callback=lambda call: self._apply_completed(call, invocation),
        )

    def _apply_completed(
        self,
        call: AutomationCallResult,
        invocation: LiveFormatProfileInvocation,
    ) -> None:
        if call.classification == "apply_unknown":
            self._show_unknown(call)
            return
        if call.classification == "outer_error" and call.error is not None:
            if call.error.code in _STALE_CODES:
                self._show_stale(call.error.message)
            elif call.error.code == "conflict.live_autosave_enabled":
                self._show_autosave_blocked(call.error.message)
            elif call.error.code in _KNOWN_PRE_EFFECT_CODES:
                self._show_reselect(call.error.message)
            else:
                self._show_unknown(call)
            return
        if not isinstance(call.result, LiveFormatProfileResult):
            self._show_unknown(call)
            return
        result = call.result
        if not self._result_matches_invocation(result, invocation):
            self._show_unknown(call)
            return
        self._show_result(result)

    @staticmethod
    def _result_matches_invocation(
        result: LiveFormatProfileResult,
        invocation: LiveFormatProfileInvocation,
    ) -> bool:
        return (
            result.workbook_token == invocation.workbook_token
            and result.scope == invocation.scope
            and result.profile_id == invocation.profile_id
            and result.profile_version == invocation.profile_version
            and not result.workbook_saved
            and not result.workbook_closed
            and not result.application_closed
        )

    def _show_result(self, result: LiveFormatProfileResult) -> None:
        self.view_state = result.state
        self._clear_content()
        headings = {
            "succeeded": "Excel format template applied",
            "failed": "Excel format template could not complete",
            "partial_failure": "Excel format template partly applied",
        }
        ttk.Label(self.content, text=headings[result.state], style="Heading.TLabel").pack(
            anchor=tk.W
        )
        ttk.Label(
            self.content,
            text=f"Workbook: {result.workbook_name}",
            style="Muted.TLabel",
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(3, 8))
        result_lines: list[str] = []
        self._append_result_lines(result_lines, "Formatted", result.formatted_sheets)
        self._append_result_lines(
            result_lines,
            "Hidden sheets skipped",
            result.skipped_hidden_sheets,
        )
        self._append_result_lines(
            result_lines,
            "Filter added",
            result.filter_added_sheets,
        )
        self._append_result_lines(
            result_lines,
            "Existing filter preserved",
            result.existing_filter_sheets,
        )
        if result.failures:
            self._append_result_lines(
                result_lines,
                "Worksheet failures",
                tuple(
                    f"{item.worksheet}: {item.code} — {item.message}"
                    for item in result.failures
                ),
            )
        if result.warnings:
            self._append_result_lines(
                result_lines,
                "Warnings",
                tuple(item.message for item in result.warnings),
            )
        self._show_result_text(result_lines)
        if result.state == "succeeded":
            self._set_status(
                "Template applied. Context Palette did not save or close Excel; "
                "review the workbook and save it yourself if wanted."
            )
        else:
            self._set_status(
                "Review Excel before retrying; this fast workflow does not roll back worksheet changes.",
                error=True,
            )
        self._return_button()

    def _show_stale(self, message: str) -> None:
        self.view_state = "stale"
        self._clear_content()
        ttk.Label(self.content, text="Excel selection changed", style="Heading.TLabel").pack(
            anchor=tk.W
        )
        ttk.Label(self.content, text=message, wraplength=700, justify=tk.LEFT).pack(
            anchor=tk.W, pady=(5, 10)
        )
        self.primary_button = ttk.Button(
            self.content,
            text="Refresh open workbooks",
            command=self._start_inventory,
            style="Accent.TButton",
        )
        self.primary_button.pack(anchor=tk.W)
        self._return_button()
        self._set_status("Refresh and choose the workbook or worksheet again. No format was started.", error=True)

    def _show_autosave_blocked(self, message: str) -> None:
        self.view_state = "autosave_blocked"
        self._clear_content()
        ttk.Label(self.content, text="Turn off AutoSave first", style="Heading.TLabel").pack(
            anchor=tk.W
        )
        ttk.Label(self.content, text=message, wraplength=700, justify=tk.LEFT).pack(
            anchor=tk.W, pady=(5, 10)
        )
        self.primary_button = ttk.Button(
            self.content,
            text="Refresh open workbooks",
            command=self._start_inventory,
            style="Accent.TButton",
        )
        self.primary_button.pack(anchor=tk.W)
        self._return_button()
        self._set_status("AutoSave blocked the format before it began.", error=True)

    def _show_reselect(self, message: str) -> None:
        self.view_state = "reselect"
        self._clear_content()
        ttk.Label(self.content, text="Excel target unavailable", style="Heading.TLabel").pack(
            anchor=tk.W
        )
        ttk.Label(self.content, text=message, wraplength=700, justify=tk.LEFT).pack(
            anchor=tk.W, pady=(5, 10)
        )
        self.primary_button = ttk.Button(
            self.content,
            text="Refresh open workbooks",
            command=self._start_inventory,
            style="Accent.TButton",
        )
        self.primary_button.pack(anchor=tk.W)
        self._return_button()
        self._set_status("Choose a visible worksheet before applying the template.", error=True)

    def _show_unknown(self, call: AutomationCallResult) -> None:
        self.view_state = "unknown"
        self._clear_content()
        ttk.Label(self.content, text="Excel format outcome unknown", style="Heading.TLabel").pack(
            anchor=tk.W
        )
        ttk.Label(
            self.content,
            text=(
                "Context Palette did not receive a trustworthy final result. The workbook may have "
                "changed. Do not apply the template again automatically; inspect Excel first."
            ),
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 8))
        if call.reason:
            ttk.Label(self.content, text=call.reason, style="Muted.TLabel", wraplength=700).pack(
                anchor=tk.W
            )
        self._return_button()
        self._set_status("Outcome unknown. Inspect Excel before any retry.", error=True)

    def _show_inventory_failure(self, call: AutomationCallResult) -> None:
        self.view_state = "unavailable"
        self._clear_content()
        ttk.Label(self.content, text="Open Excel workbooks unavailable", style="Heading.TLabel").pack(
            anchor=tk.W
        )
        message = call.error.message if call.error is not None else call.reason
        ttk.Label(
            self.content,
            text=message or "Python Excel could not list open workbooks.",
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 10))
        self.primary_button = ttk.Button(
            self.content,
            text="Change Python Excel launcher…",
            command=self._browse_launcher,
        )
        self.primary_button.pack(anchor=tk.W)
        self._set_status("Context Palette remains available; only the live Excel template is unavailable.", error=True)

    def _return_button(self) -> None:
        if not can_return_to_captured_excel(
            self._captured_source, self._inventory_process_ids
        ):
            return
        button = ttk.Button(self.content, text="Return to Excel", command=self._return_to_excel)
        button.pack(anchor=tk.W, pady=(12, 0))

    def _return_to_excel(self) -> None:
        handle = self.source_window_handle
        if handle is None or not self.return_to_source(handle):
            self._set_status(
                "The captured Excel window is no longer available; select it manually.",
                error=True,
            )
            return
        self._set_status("Returned to the captured Excel window.")

    @staticmethod
    def _append_result_lines(
        lines: list[str],
        label: str,
        values: tuple[str, ...],
    ) -> None:
        if values:
            lines.append(label)
            lines.extend(f"  {value}" for value in values)

    def _show_result_text(self, lines: list[str]) -> None:
        frame = ttk.Frame(self.content)
        frame.pack(fill=tk.BOTH, expand=True)
        text = tk.Text(
            frame,
            height=12,
            wrap=tk.WORD,
            takefocus=True,
            padx=6,
            pady=6,
        )
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.grid(row=0, column=0, sticky=tk.NSEW)
        scrollbar.grid(row=0, column=1, sticky=tk.NS)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        text.insert("1.0", "\n".join(lines) or "No worksheet effects were reported.")
        text.configure(state=tk.DISABLED)
        self.result_text = text

    def _render_warnings(self, warnings: tuple[object, ...]) -> None:
        if not warnings:
            return
        messages = tuple(getattr(item, "message", "Warning") for item in warnings)
        ttk.Label(
            self.content,
            text="Warnings: " + " · ".join(messages),
            style="Muted.TLabel",
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(8, 0))

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
        if not self.coordinator.start(
            launcher,
            request,
            phase=phase,  # type: ignore[arg-type]
            timeout_seconds=timeout_seconds,
            on_complete=callback,
        ):
            self._show_inventory_failure(
                AutomationCallResult("inventory", "inventory_failed", False, None, reason="Another Excel automation workflow is already running.")
            )
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

    def _stop_progress(self) -> None:
        if self._progressbar is not None:
            try:
                self._progressbar.stop()
            except tk.TclError:
                pass
        self._progressbar = None

    def _set_status(self, message: str, *, error: bool = False) -> None:
        self.status_var.set(message)
        self.status_label.configure(style="Error.TLabel" if error else "Status.TLabel")
        self.status_setter(message)


def _request_id() -> str:
    return f"live-format-{uuid4().hex}"
