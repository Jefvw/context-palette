"""Attended Tk workflow for copying Input / Output files to one folder."""

from __future__ import annotations

import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Callable

from .file_transfer import (
    FileTransferCoordinator,
    FileTransferError,
    FileTransferPlan,
    FileTransferResult,
    FileTransferUnexpectedError,
)
from .window_geometry import configure_standard_window


_POLL_MILLISECONDS = 50


class FileTransferWindow:
    """Plan, review when needed, and copy one Input / Output snapshot."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        workspace_text: str,
        destination_folder: Path,
        destination_label: str,
        status_setter: Callable[[str], None],
        coordinator: FileTransferCoordinator | None = None,
        folder_opener: Callable[[Path], None] | None = None,
        on_success: Callable[[Path], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        self.workspace_text = workspace_text
        self.destination_folder = Path(destination_folder)
        self.destination_label = destination_label.strip() or self.destination_folder.name
        self.status_setter = status_setter
        self.coordinator = coordinator or FileTransferCoordinator()
        self.folder_opener = folder_opener or _open_folder
        self.on_success = on_success or (lambda _destination: None)
        self.on_close = on_close or (lambda: None)

        self.allow_overwrite = False
        self.plan: FileTransferPlan | None = None
        self.result: FileTransferResult | None = None
        self.view_state = "starting"
        self._poll_after_id: str | None = None
        self._queued_execute_after_id: str | None = None
        self._execution_queued = False
        self._closed = False
        self._progressbar: ttk.Progressbar | None = None

        self.window = tk.Toplevel(parent)
        self.window.title(f"Send files to {self.destination_label}")
        configure_standard_window(self.window, parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.transient(parent)

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        ttk.Label(outer, text="Send files", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            outer,
            text=(
                f"Copy the supplied file paths to {self.destination_label}. "
                "Source files stay unchanged."
            ),
            style="Muted.TLabel",
            wraplength=720,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(2, 4))
        ttk.Label(
            outer,
            text=f"Destination: {self.destination_folder}",
            style="Muted.TLabel",
            wraplength=720,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 8))

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

        self.footer = ttk.Frame(outer)
        self.footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        self.primary_button = ttk.Button(
            self.footer,
            style="Accent.TButton",
        )
        self.stop_button = ttk.Button(
            self.footer,
            text="Stop remaining",
            command=self._request_stop,
        )
        self.open_folder_button = ttk.Button(
            self.footer,
            text="Open destination folder",
            command=self._open_destination_folder,
        )
        self.close_button = ttk.Button(
            self.footer,
            text="Close",
            command=self.close,
        )
        self.close_button.pack(side=tk.RIGHT)

        self.overwrite_checkbutton: ttk.Checkbutton | None = None
        self.review_text: tk.Text | None = None
        self.result_text: tk.Text | None = None

        self.show()
        self.window.after_idle(self._start_plan)

    @property
    def busy(self) -> bool:
        return bool(self.coordinator.running or self._execution_queued)

    def show(self) -> None:
        if self._closed:
            return
        # Automatic drops may start while the Palette is hidden. Do not tie
        # review/results visibility to a withdrawn owner.
        parent = self.window.master
        self.window.transient(parent if parent.winfo_viewable() else "")
        self.window.deiconify()
        self.window.lift()

    def close(self) -> bool:
        if self._closed:
            return True
        if self.busy:
            self._set_status(
                "The file copy is still working. This window will remain open until its outcome is known.",
                error=True,
            )
            return False
        self._closed = True
        for after_id in (self._poll_after_id, self._queued_execute_after_id):
            if after_id is None:
                continue
            try:
                self.window.after_cancel(after_id)
            except tk.TclError:
                pass
        self._poll_after_id = None
        self._queued_execute_after_id = None
        self._stop_progress()
        try:
            self.window.destroy()
        finally:
            self.on_close()
        return True

    def _start_plan(self) -> None:
        if self._closed:
            return
        self.plan = None
        self.result = None
        self.view_state = "planning"
        self._hide_footer_actions()
        self._clear_content()
        self._show_working(
            "Checking source files and destination names…",
            "Nothing is copied while this check runs.",
        )
        started = self.coordinator.start_plan(
            self.workspace_text,
            self.destination_folder,
            self.allow_overwrite,
            self._plan_completed,
        )
        if not started:
            self._show_pre_effect_error(
                "Another file transfer is already running. No files were copied."
            )
            return
        self.close_button.configure(state=tk.DISABLED)
        self._schedule_poll()

    def _plan_completed(
        self,
        plan: FileTransferPlan | None,
        error: FileTransferError | None,
    ) -> None:
        self._stop_progress()
        if error is not None or plan is None:
            self._show_pre_effect_error(
                str(error) if error is not None else "The file copy could not be prepared."
            )
            return
        self.plan = plan
        if plan.create_count == 0 and plan.replace_count == 0:
            self._show_nothing_to_copy(plan)
            return
        if plan.requires_review:
            self._show_review(plan)
            return

        # Choosing the destination already confirmed a conflict-free transfer.
        # Queue execution so the coordinator can finish delivering the plan first.
        self._execution_queued = True
        self._queued_execute_after_id = self.window.after_idle(
            self._execute_queued_plan
        )

    def _execute_queued_plan(self) -> None:
        self._queued_execute_after_id = None
        self._execution_queued = False
        if not self._closed and self.plan is not None:
            self._start_execute(self.plan)

    def _show_review(self, plan: FileTransferPlan) -> None:
        self.view_state = "review"
        self._clear_content()
        self._hide_footer_actions()
        ttk.Label(
            self.content,
            text="Review destination conflicts",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            self.content,
            text=_plan_summary(plan),
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 5))
        ttk.Label(
            self.content,
            text=(
                "With overwrite off, conflicting names receive (1), (2), … suffixes. "
                "Only an explicit overwrite choice may replace a destination file."
            ),
            style="Muted.TLabel",
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 5))
        self.overwrite_checkbutton = ttk.Checkbutton(
            self.content,
            text="Allow overwrite",
            command=self._overwrite_choice_changed,
        )
        self.overwrite_checkbutton.state(
            ["selected"] if self.allow_overwrite else ["!selected"]
        )
        self.overwrite_checkbutton.pack(anchor=tk.W, pady=(0, 7))
        self.review_text = self._read_only_text(_plan_lines(plan))
        self.primary_button.configure(
            text=_execute_button_label(plan),
            command=self._execute_reviewed,
            state=tk.NORMAL,
        )
        self.primary_button.pack(side=tk.LEFT)
        self.open_folder_button.pack(side=tk.LEFT, padx=(8, 0))
        self.close_button.configure(state=tk.NORMAL)
        self._set_status(
            "Review every source and destination, then choose the effect-labelled copy button."
        )

    def _show_nothing_to_copy(self, plan: FileTransferPlan) -> None:
        self.view_state = "no_effect"
        self._clear_content()
        self._hide_footer_actions()
        ttk.Label(
            self.content,
            text="Nothing to copy",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            self.content,
            text=(
                "Every selected file is already the exact file in this destination. "
                "Context Palette will not overwrite a file with itself."
            ),
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 5))
        self.review_text = self._read_only_text(_plan_lines(plan))
        self.open_folder_button.pack(side=tk.LEFT)
        self.close_button.configure(state=tk.NORMAL)
        self._set_status(
            "No files were copied because they are already in the destination."
        )

    def _overwrite_choice_changed(self) -> None:
        checkbox = self.overwrite_checkbutton
        if checkbox is None or self.busy:
            return
        self.allow_overwrite = checkbox.instate(["selected"])
        self._start_plan()

    def _execute_reviewed(self) -> None:
        plan = self.plan
        if plan is None or self.busy:
            return
        self._start_execute(plan)

    def _start_execute(self, plan: FileTransferPlan) -> None:
        self.view_state = "executing"
        self._clear_content()
        self._hide_footer_actions()
        self._show_working(
            "Copying the reviewed files…",
            "The current file will finish if you choose Stop remaining.",
        )
        self.stop_button.configure(state=tk.NORMAL, text="Stop remaining")
        self.stop_button.pack(side=tk.LEFT)
        started = self.coordinator.start_execute(plan, self._execute_completed)
        if not started:
            self._show_pre_effect_error(
                "The file transfer could not start because another transfer is running. "
                "No files were copied."
            )
            return
        self.close_button.configure(state=tk.DISABLED)
        self._schedule_poll()

    def _request_stop(self) -> None:
        if self.view_state != "executing" or not self.coordinator.running:
            return
        self.coordinator.request_stop()
        self.stop_button.configure(state=tk.DISABLED, text="Stop requested")
        self._set_status(
            "Stop requested. The current file will finish; remaining files will not start."
        )

    def _execute_completed(
        self,
        result: FileTransferResult | None,
        error: FileTransferError | None,
    ) -> None:
        self._stop_progress()
        if result is None:
            message = (
                str(error)
                if error is not None
                else "The file transfer did not return a trustworthy result."
            )
            if isinstance(error, FileTransferUnexpectedError) or error is None:
                self._show_unknown_outcome(message)
            else:
                self._show_pre_effect_error(message)
            return
        self.result = result
        self._show_result(result, error)

    def _show_result(
        self,
        result: FileTransferResult,
        error: FileTransferError | None,
    ) -> None:
        self.view_state = "result"
        self._clear_content()
        self._hide_footer_actions()
        completed_count = len(result.created) + len(result.replaced)
        if result.stopped:
            heading = "File copy stopped"
        elif result.failures or error is not None:
            heading = (
                "File copy stopped after some files"
                if completed_count
                else "No files were copied"
            )
        else:
            heading = "Files copied"
        ttk.Label(self.content, text=heading, style="Heading.TLabel").pack(anchor=tk.W)
        ttk.Label(
            self.content,
            text=_result_summary(result),
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 5))
        self.result_text = self._read_only_text(_result_lines(result, error))
        self.open_folder_button.pack(side=tk.LEFT)
        self.close_button.configure(state=tk.NORMAL)

        if result.stopped:
            self._set_status(
                "Stopped. Completed destination files remain; pending files were not started. "
                "There is no automatic rollback or retry. Sources are unchanged.",
                error=True,
            )
        elif result.failures or error is not None:
            self._set_status(
                "Some outcomes failed. Completed files remain; there is no automatic rollback or retry. Sources are unchanged.",
                error=True,
            )
        else:
            self._set_status("Copy complete. Source files were not changed.")
            try:
                self.on_success(self.destination_folder)
            except Exception:
                self._set_status(
                    "Copy complete, but the recent-destination list could not be updated. Source files were not changed.",
                    error=True,
                )

    def _show_pre_effect_error(self, message: str) -> None:
        self.view_state = "pre_effect_error"
        self._clear_content()
        self._hide_footer_actions()
        ttk.Label(
            self.content,
            text="Files could not be prepared",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            self.content,
            text=message,
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 0))
        self.open_folder_button.pack(side=tk.LEFT)
        self.close_button.configure(state=tk.NORMAL)
        self._set_status("No files were copied.", error=True)

    def _show_unknown_outcome(self, message: str) -> None:
        self.view_state = "unknown"
        self._clear_content()
        self._hide_footer_actions()
        ttk.Label(
            self.content,
            text="File copy outcome unknown",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            self.content,
            text=(
                f"{message}\n\nInspect the destination before doing anything else. "
                "Do not retry automatically; some files may already exist."
            ),
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 0))
        self.open_folder_button.pack(side=tk.LEFT)
        self.close_button.configure(state=tk.NORMAL)
        self._set_status(
            "Outcome unknown. No rollback or automatic retry is claimed. Sources should be inspected only if the local copy process reported an error.",
            error=True,
        )

    def _show_working(self, heading: str, detail: str) -> None:
        ttk.Label(
            self.content,
            text=heading,
            style="Heading.TLabel",
            wraplength=700,
        ).pack(anchor=tk.W)
        ttk.Label(
            self.content,
            text=detail,
            style="Muted.TLabel",
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(5, 0))
        progress = ttk.Progressbar(self.content, mode="indeterminate")
        progress.pack(fill=tk.X, pady=(12, 0))
        progress.start(12)
        self._progressbar = progress
        self._set_status("Please wait. Closing is disabled while the operation is active.")

    def _read_only_text(self, value: str) -> tk.Text:
        frame = ttk.Frame(self.content)
        frame.pack(fill=tk.BOTH, expand=True, pady=(2, 0))
        vertical = ttk.Scrollbar(frame, orient=tk.VERTICAL)
        horizontal = ttk.Scrollbar(frame, orient=tk.HORIZONTAL)
        text = tk.Text(
            frame,
            height=8,
            wrap=tk.NONE,
            padx=8,
            pady=6,
            yscrollcommand=vertical.set,
            xscrollcommand=horizontal.set,
        )
        vertical.configure(command=text.yview)
        horizontal.configure(command=text.xview)
        vertical.pack(side=tk.RIGHT, fill=tk.Y)
        horizontal.pack(side=tk.BOTTOM, fill=tk.X)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text.insert("1.0", value)
        text.configure(state=tk.DISABLED)
        return text

    def _open_destination_folder(self) -> None:
        try:
            self.folder_opener(self.destination_folder)
        except (OSError, ValueError) as exc:
            self._set_status(f"The destination folder could not be opened: {exc}", error=True)

    def _schedule_poll(self) -> None:
        if self._closed or self._poll_after_id is not None:
            return
        self._poll_after_id = self.window.after(_POLL_MILLISECONDS, self._poll)

    def _poll(self) -> None:
        self._poll_after_id = None
        if self._closed:
            return
        self.coordinator.drain()
        if self.coordinator.running:
            self._schedule_poll()
        elif not self._execution_queued:
            self.close_button.configure(state=tk.NORMAL)

    def _clear_content(self) -> None:
        self._stop_progress()
        for child in self.content.winfo_children():
            child.destroy()
        self.overwrite_checkbutton = None
        self.review_text = None
        self.result_text = None

    def _hide_footer_actions(self) -> None:
        for button in (
            self.primary_button,
            self.stop_button,
            self.open_folder_button,
        ):
            button.pack_forget()

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


def _plan_summary(plan: FileTransferPlan) -> str:
    parts = [
        _count_label(plan.create_count, "new file", "new files"),
        _count_label(plan.replace_count, "existing file to replace", "existing files to replace"),
    ]
    if plan.renamed_count:
        parts.append(
            _count_label(plan.renamed_count, "name receives a suffix", "names receive suffixes")
        )
    if plan.skipped_count:
        parts.append(
            _count_label(plan.skipped_count, "file already in place", "files already in place")
        )
    return " · ".join(parts)


def _execute_button_label(plan: FileTransferPlan) -> str:
    creates = plan.create_count
    replaces = plan.replace_count
    skips = plan.skipped_count
    if replaces and creates:
        return f"Replace {replaces} and copy {creates} {_file_word(creates)}"
    if replaces:
        return f"Replace {replaces} {_file_word(replaces)}"
    if creates:
        return f"Copy {creates} {_file_word(creates)}"
    return f"Skip {skips} {_file_word(skips)} already there"


def _plan_lines(plan: FileTransferPlan) -> str:
    lines: list[str] = []
    labels = {
        "create": "Create",
        "replace": "Replace",
        "skip_same": "Already there; skip",
    }
    for item in plan.items:
        lines.append(f"{labels.get(item.disposition, item.disposition)}: {item.source_path}")
        lines.append(f"  → {item.destination_path}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _result_summary(result: FileTransferResult) -> str:
    return " · ".join(
        (
            _count_label(len(result.created), "file created", "files created"),
            _count_label(len(result.replaced), "file replaced", "files replaced"),
            _count_label(len(result.skipped), "file skipped", "files skipped"),
            _count_label(len(result.failures), "failure", "failures"),
        )
    )


def _result_lines(
    result: FileTransferResult,
    error: FileTransferError | None,
) -> str:
    lines: list[str] = []
    for heading, paths in (
        ("Created", result.created),
        ("Replaced", result.replaced),
        ("Skipped", result.skipped),
    ):
        if not paths:
            continue
        lines.append(heading)
        lines.extend(f"  {path}" for path in paths)
        lines.append("")
    if result.failures:
        lines.append("Failed")
        for failure in result.failures:
            lines.append(f"  Source: {failure.source_path}")
            if failure.destination_path is not None:
                lines.append(f"  Destination: {failure.destination_path}")
            lines.append(f"  {failure.message}")
            lines.append("")
    if error is not None:
        lines.extend(("Transfer error", f"  {error}"))
    if not lines:
        lines.append("No destination files were changed.")
    return "\n".join(lines).rstrip()


def _count_label(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _file_word(count: int) -> str:
    return "file" if count == 1 else "files"


def _open_folder(path: Path) -> None:
    os.startfile(str(path))  # type: ignore[attr-defined]
