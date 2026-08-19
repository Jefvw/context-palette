from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Generic, TypeVar

from .backup import (
    BackupError,
    BackupOptions,
    BackupResult,
    create_configuration_backup,
)
from .data_catalog import AppDataPaths
from .restore import (
    RestoreArchiveError,
    RestoreCommitError,
    RestoreConfirmation,
    RestoreError,
    RestorePlan,
    RestorePlanStaleError,
    RestoreRecoveryRequiredError,
    RestoreResult,
    commit_restore,
    inspect_restore_archive,
)
from .window_geometry import place_child_window


_T = TypeVar("_T")
_POLL_INTERVAL_MS = 30
_PREVIEW_PATH_LIMIT = 20
_PREVIEW_WARNING_LIMIT = 12


@dataclass(frozen=True, slots=True)
class _WorkerOutcome(Generic[_T]):
    value: _T | None = None
    error: Exception | None = None


class _UiWorker:
    """Run one operation at a time and deliver results only on the Tk thread."""

    def __init__(self, owner: tk.Misc) -> None:
        self._owner = owner
        self._results: queue.Queue[
            tuple[Callable[[_WorkerOutcome[object]], None], _WorkerOutcome[object]]
        ] = queue.Queue(maxsize=1)
        self._busy = False
        self._closed = False
        self._poll_after_id: str | None = None
        self._thread: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        return self._busy

    def start(
        self,
        task: Callable[[], _T],
        callback: Callable[[_WorkerOutcome[_T]], None],
    ) -> bool:
        if self._busy or self._closed:
            return False
        self._busy = True
        self._schedule_poll()

        def run() -> None:
            try:
                outcome: _WorkerOutcome[_T] = _WorkerOutcome(value=task())
            except Exception as exc:
                outcome = _WorkerOutcome(error=exc)
            self._results.put((callback, outcome))

        try:
            self._thread = threading.Thread(
                target=run,
                name="context-palette-backup-restore",
                daemon=False,
            )
            self._thread.start()
        except Exception:
            self._thread = None
            self._busy = False
            self._cancel_poll()
            raise
        return True

    def close(self) -> None:
        self._closed = True
        if not self._busy:
            self._cancel_poll()

    def _schedule_poll(self) -> None:
        if self._closed and not self._busy:
            return
        self._poll_after_id = self._owner.after(
            _POLL_INTERVAL_MS,
            self._poll,
        )

    def _poll(self) -> None:
        self._poll_after_id = None
        try:
            callback, outcome = self._results.get_nowait()
        except queue.Empty:
            self._schedule_poll()
            return
        thread = self._thread
        if thread is not None:
            thread.join()
        self._thread = None
        self._busy = False
        if not self._closed:
            callback(outcome)

    def _cancel_poll(self) -> None:
        if self._poll_after_id is None:
            return
        try:
            self._owner.after_cancel(self._poll_after_id)
        except tk.TclError:
            pass
        self._poll_after_id = None


def format_backup_success(result: BackupResult) -> str:
    """Return a compact success message using only service-safe metadata."""

    lines = [
        f"Backup created:\n{result.destination}",
        f"Included files: {len(result.included_files)}",
    ]
    if result.excluded_categories:
        lines.append(
            "Excluded: "
            + "; ".join(category.value for category in result.excluded_categories)
        )
    if result.snapshot_warnings:
        lines.append("Warnings:")
        lines.extend(
            f"- {issue.summary}"
            for issue in result.snapshot_warnings[:_PREVIEW_WARNING_LIMIT]
        )
        remaining = len(result.snapshot_warnings) - _PREVIEW_WARNING_LIMIT
        if remaining > 0:
            lines.append(f"- {remaining} additional warning(s) omitted here")
    return "\n\n".join(lines[:3]) + (
        "\n" + "\n".join(lines[3:]) if len(lines) > 3 else ""
    )


def format_restore_plan(plan: RestorePlan) -> str:
    """Render a privacy-safe restore preview from operational plan metadata."""

    sections = [
        _format_restore_files("Files to replace", plan.files_to_replace),
        _format_restore_files("Files to create", plan.files_to_create),
        _format_restore_files(
            "Omitted live files preserved",
            plan.preserved_live_files,
        ),
        _format_restore_files("Built-in files affected", plan.built_in_files),
    ]
    sensitive = (
        ", ".join(category.value for category in plan.sensitive_categories)
        if plan.sensitive_categories
        else "none"
    )
    compatibility = plan.compatibility
    sections.append(
        "Compatibility\n"
        f"Format {compatibility.archive_format_version}; data model "
        f"{compatibility.data_model_version}; scope {compatibility.scope}.\n"
        f"Legacy forms: {'present and preserved' if compatibility.legacy_forms_present else 'none detected'}.\n"
        f"Migration: {'required' if compatibility.migration_required else 'not required'}."
    )
    sections.append(f"Sensitive categories\n{sensitive}")
    if plan.snapshot_warnings:
        warning_lines = [
            f"- {issue.summary}"
            for issue in plan.snapshot_warnings[:_PREVIEW_WARNING_LIMIT]
        ]
        remaining = len(plan.snapshot_warnings) - _PREVIEW_WARNING_LIMIT
        if remaining > 0:
            warning_lines.append(f"- {remaining} additional warning(s)")
        sections.append("Warnings\n" + "\n".join(warning_lines))
    else:
        sections.append("Warnings\nNone.")
    return "\n\n".join(sections)


def _format_restore_files(label: str, files) -> str:
    values = tuple(item.relative_path.as_posix() for item in files)
    lines = [f"{label}: {len(values)}"]
    lines.extend(f"- {value}" for value in values[:_PREVIEW_PATH_LIMIT])
    remaining = len(values) - _PREVIEW_PATH_LIMIT
    if remaining > 0:
        lines.append(f"- {remaining} additional catalogued file(s)")
    return "\n".join(lines)


class BackupRestorePanel(ttk.Frame):
    """Thin Configure UI over the Phase 3 and Phase 4 service boundaries."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        data_paths: AppDataPaths,
        on_restore_complete: Callable[[], None],
        on_recovery_required: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.data_paths = data_paths
        self.on_restore_complete = on_restore_complete
        self.on_recovery_required = on_recovery_required
        self.owner = parent.winfo_toplevel()
        self._worker = _UiWorker(self.owner)
        self._progress_window: tk.Toplevel | None = None
        self._selected_archive: Path | None = None
        self._restore_plan: RestorePlan | None = None

        self.include_inbox_var = tk.BooleanVar(value=True)
        self.include_managed_content_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready to create or inspect a backup.")

        self._build_widgets()

    @property
    def busy(self) -> bool:
        return self._worker.busy

    def focus_primary(self) -> None:
        self.create_backup_button.focus_set()

    def close(self) -> None:
        self._worker.close()

    def _build_widgets(self) -> None:
        backup = ttk.LabelFrame(self, text="Create backup", padding=8)
        backup.pack(fill=tk.X, pady=(0, 8))
        ttk.Checkbutton(
            backup,
            text="Include captured Inbox content",
            variable=self.include_inbox_var,
        ).pack(anchor=tk.W)
        ttk.Checkbutton(
            backup,
            text="Include optional managed text content",
            variable=self.include_managed_content_var,
        ).pack(anchor=tk.W, pady=(2, 0))
        ttk.Label(
            backup,
            text=(
                "Configured references and settings are included. Referenced files, "
                "folders, Work Item roots/workbooks, and templates themselves are not "
                "copied. Credential secrets, logs, caches, environments, and unknown "
                "files are also excluded."
            ),
            style="Muted.TLabel",
            wraplength=700,
        ).pack(anchor=tk.W, pady=(6, 6))
        self.create_backup_button = ttk.Button(
            backup,
            text="Create backup…",
            command=self._choose_backup_destination,
            style="Accent.TButton",
        )
        self.create_backup_button.pack(anchor=tk.W)

        restore = ttk.LabelFrame(self, text="Inspect and restore", padding=8)
        restore.pack(fill=tk.BOTH, expand=True)
        controls = ttk.Frame(restore)
        controls.pack(fill=tk.X, pady=(0, 6))
        self.inspect_restore_button = ttk.Button(
            controls,
            text="Choose backup to inspect…",
            command=self._choose_restore_archive,
        )
        self.inspect_restore_button.pack(side=tk.LEFT)
        self.commit_restore_button = ttk.Button(
            controls,
            text="Apply inspected changes…",
            command=self._confirm_restore,
            style="Danger.TButton",
        )
        self.commit_restore_button.pack(side=tk.LEFT, padx=(6, 0))
        self.commit_restore_button.state(["disabled"])

        preview_frame = ttk.Frame(restore)
        preview_frame.pack(fill=tk.BOTH, expand=True)
        self.preview_text = tk.Text(
            preview_frame,
            wrap=tk.WORD,
            height=14,
            padx=7,
            pady=7,
            takefocus=True,
        )
        scrollbar = ttk.Scrollbar(
            preview_frame,
            orient=tk.VERTICAL,
            command=self.preview_text.yview,
        )
        self.preview_text.configure(yscrollcommand=scrollbar.set)
        self.preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._set_preview(
            "Choose a backup to inspect. Nothing is changed during inspection."
        )

        ttk.Label(
            self,
            textvariable=self.status_var,
            style="Status.TLabel",
            wraplength=720,
        ).pack(fill=tk.X, pady=(8, 0))

    def _choose_backup_destination(self) -> None:
        if self.busy:
            return
        selected = filedialog.asksaveasfilename(
            parent=self.owner,
            title="Create Context Palette backup",
            defaultextension=".zip",
            filetypes=(("ZIP backup", "*.zip"), ("All files", "*.*")),
            confirmoverwrite=False,
        )
        if not selected:
            return
        destination = Path(selected)
        overwrite = destination.exists()
        if overwrite and not messagebox.askyesno(
            "Replace existing backup?",
            "A file already exists at the selected location. Replace it with this backup?",
            parent=self.owner,
        ):
            return
        options = BackupOptions(
            include_inbox=bool(self.include_inbox_var.get()),
            include_managed_content=bool(self.include_managed_content_var.get()),
            overwrite=overwrite,
        )
        self._start_operation(
            "Creating a validated configuration backup...",
            lambda: create_configuration_backup(
                self.data_paths,
                destination,
                options=options,
            ),
            self._backup_finished,
        )

    def _backup_finished(self, outcome: _WorkerOutcome[BackupResult]) -> None:
        if outcome.error is not None:
            message = (
                str(outcome.error)
                if isinstance(outcome.error, BackupError)
                else "The backup could not be created safely."
            )
            self.status_var.set("Backup was not created.")
            messagebox.showerror("Backup was not created", message, parent=self.owner)
            return
        result = outcome.value
        if result is None:
            return
        self.status_var.set(f"Backup created with {len(result.included_files)} file(s).")
        messagebox.showinfo(
            "Backup created",
            format_backup_success(result),
            parent=self.owner,
        )

    def _choose_restore_archive(self) -> None:
        if self.busy:
            return
        selected = filedialog.askopenfilename(
            parent=self.owner,
            title="Inspect Context Palette backup",
            filetypes=(("ZIP backup", "*.zip"), ("All files", "*.*")),
        )
        if not selected:
            return
        archive = Path(selected)
        self._clear_restore_plan()
        self._start_operation(
            "Inspecting and validating the selected backup...",
            lambda: inspect_restore_archive(self.data_paths, archive),
            lambda outcome: self._inspection_finished(archive, outcome),
        )

    def _inspection_finished(
        self,
        archive: Path,
        outcome: _WorkerOutcome[RestorePlan],
    ) -> None:
        if outcome.error is not None:
            message = (
                str(outcome.error)
                if isinstance(outcome.error, RestoreError)
                else "The selected backup could not be inspected safely."
            )
            self.status_var.set("Restore inspection failed; live configuration was unchanged.")
            self._set_preview(
                "Inspection failed. No restore is available and live configuration was unchanged."
            )
            messagebox.showerror("Backup is not restorable", message, parent=self.owner)
            return
        plan = outcome.value
        if plan is None:
            return
        self._selected_archive = archive
        self._restore_plan = plan
        self._set_preview(format_restore_plan(plan))
        self.commit_restore_button.state(["!disabled"])
        self.status_var.set(
            "Inspection succeeded. Review the summary before applying the restore."
        )

    def _confirm_restore(self) -> None:
        if self.busy or self._restore_plan is None or self._selected_archive is None:
            return
        plan = self._restore_plan
        affected_count = len(plan.affected_files)
        if not messagebox.askyesno(
            "Restore inspected backup?",
            (
                f"Restore {affected_count} catalogued file(s)?\n\n"
                "Context Palette will create and retain a recovery archive first. "
                "Once this starts it cannot be cancelled."
            ),
            parent=self.owner,
        ):
            return
        built_in_acknowledged = False
        if plan.built_in_acknowledgement_required:
            built_in_acknowledged = messagebox.askyesno(
                "Replace Built-in configuration?",
                (
                    f"This restore replaces {len(plan.built_in_files)} Built-in file(s). "
                    "Built-in changes can affect Git-tracked starter configuration.\n\n"
                    "Continue with Built-in replacement?"
                ),
                parent=self.owner,
            )
            if not built_in_acknowledged:
                return
        confirmation = RestoreConfirmation.for_plan(
            plan,
            built_in_acknowledged=built_in_acknowledged,
        )
        archive = self._selected_archive
        self._start_operation(
            "Creating recovery state and applying the confirmed restore...",
            lambda: commit_restore(
                self.data_paths,
                archive,
                plan,
                confirmation,
                recovery_directory=archive.parent,
            ),
            self._commit_finished,
        )

    def _commit_finished(self, outcome: _WorkerOutcome[RestoreResult]) -> None:
        if outcome.error is None:
            result = outcome.value
            if result is None:
                return
            messagebox.showinfo(
                "Restore complete",
                (
                    "Configuration was restored and will now be reloaded.\n\n"
                    f"Recovery archive retained at:\n{result.recovery_archive}"
                ),
                parent=self.owner,
            )
            self.status_var.set("Restore complete. Reloading Context Palette...")
            self.on_restore_complete()
            return

        error = outcome.error
        self._clear_restore_plan()
        if isinstance(error, RestoreCommitError):
            if error.rollback_completed:
                self.status_var.set(
                    "Restore failed; the previous configuration was restored."
                )
                messagebox.showerror(
                    "Restore failed and was rolled back",
                    (
                        "The restore could not be completed. The previous "
                        "configuration was restored and Configure remains usable."
                    ),
                    parent=self.owner,
                )
                return
            self._require_restart_after_recovery_failure()
            return
        if isinstance(error, RestoreRecoveryRequiredError):
            self._require_restart_after_recovery_failure()
            return
        if isinstance(error, (RestorePlanStaleError, RestoreArchiveError)):
            self.status_var.set(
                "The archive or configuration changed. Inspect the backup again."
            )
            messagebox.showwarning(
                "Restore plan changed",
                (
                    "The inspected archive or relevant live configuration changed. "
                    "Nothing was restored. Inspect the backup again before continuing."
                ),
                parent=self.owner,
            )
            return
        message = (
            str(error)
            if isinstance(error, RestoreError)
            else "The restore could not be completed safely."
        )
        self.status_var.set("Restore was not completed.")
        messagebox.showerror("Restore was not completed", message, parent=self.owner)

    def _require_restart_after_recovery_failure(self) -> None:
        self.status_var.set("Recovery is incomplete. Restart is required.")
        messagebox.showerror(
            "Restart required for recovery",
            (
                "Automatic rollback is incomplete. Configure will close and further "
                "configuration changes are blocked. Restart Context Palette so startup "
                "recovery can finish before editing configuration."
            ),
            parent=self.owner,
        )
        self.on_recovery_required()

    def _start_operation(
        self,
        status: str,
        task: Callable[[], _T],
        callback: Callable[[_WorkerOutcome[_T]], None],
    ) -> None:
        if self.busy:
            return
        self.status_var.set(status)
        self._show_progress(status)

        def finished(outcome: _WorkerOutcome[_T]) -> None:
            self._hide_progress()
            callback(outcome)

        try:
            started = self._worker.start(task, finished)
        except Exception:
            self._hide_progress()
            self.status_var.set("The background operation could not start.")
            messagebox.showerror(
                "Operation could not start",
                "Context Palette could not start the background operation.",
                parent=self.owner,
            )
            return
        if not started:
            self._hide_progress()

    def _show_progress(self, status: str) -> None:
        progress = tk.Toplevel(self.owner)
        self._progress_window = progress
        progress.title("Context Palette")
        progress.transient(self.owner)
        progress.resizable(False, False)
        progress.protocol("WM_DELETE_WINDOW", lambda: None)
        frame = ttk.Frame(progress, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=status, wraplength=430).pack(anchor=tk.W)
        ttk.Label(
            frame,
            text="Please wait. This operation cannot overlap Configure changes.",
            style="Muted.TLabel",
            wraplength=430,
        ).pack(anchor=tk.W, pady=(8, 0))
        place_child_window(progress, self.owner, size=(480, 130))
        progress.grab_set()
        progress.focus_set()

    def _hide_progress(self) -> None:
        progress = self._progress_window
        self._progress_window = None
        if progress is None:
            return
        try:
            if progress.grab_current() == progress:
                progress.grab_release()
            progress.destroy()
        except tk.TclError:
            pass

    def _clear_restore_plan(self) -> None:
        self._selected_archive = None
        self._restore_plan = None
        self.commit_restore_button.state(["disabled"])

    def _set_preview(self, text: str) -> None:
        self.preview_text.configure(state=tk.NORMAL)
        self.preview_text.replace("1.0", tk.END, text)
        self.preview_text.configure(state=tk.DISABLED)
