from __future__ import annotations

from pathlib import Path, PurePosixPath
from types import SimpleNamespace
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.backup import BackupExclusion
from context_palette.backup_restore_ui import (
    BackupRestorePanel,
    _UiWorker,
    format_backup_success,
    format_restore_plan,
)
from context_palette.data_catalog import AppDataPaths
from context_palette.restore import (
    RestoreArchiveError,
    RestoreCommitError,
    RestorePlanStaleError,
    RestoreRecoveryRequiredError,
    RestoreSensitiveCategory,
)


SHA = "a" * 64


def restore_file(asset_id: str, relative_path: str) -> SimpleNamespace:
    return SimpleNamespace(
        asset_id=asset_id,
        relative_path=PurePosixPath(relative_path),
    )


def restore_plan(*, built_in: bool = False) -> SimpleNamespace:
    built_in_files = (
        (restore_file("built-in-actions", "data/actions.json"),)
        if built_in
        else ()
    )
    replacement = restore_file("personal-actions", "data/local_actions.json")
    created = restore_file("palette-state", "data/palette.json")
    return SimpleNamespace(
        archive=SimpleNamespace(sha256=SHA),
        live_state_sha256="b" * 64,
        files_to_replace=(replacement,),
        files_to_create=(created,),
        affected_files=(replacement, created),
        preserved_live_files=(
            restore_file("personal-contexts", "data/local_contexts.json"),
        ),
        built_in_files=built_in_files,
        sensitive_categories=(RestoreSensitiveCategory.PRIVATE_PATHS,),
        snapshot_warnings=(
            SimpleNamespace(summary="One machine-local dependency will need review."),
        ),
        compatibility=SimpleNamespace(
            archive_format_version=1,
            data_model_version=1,
            scope="complete configuration",
            legacy_forms_present=True,
            migration_required=False,
        ),
        built_in_acknowledgement_required=built_in,
    )


def backup_result(destination: Path) -> SimpleNamespace:
    return SimpleNamespace(
        destination=destination,
        included_files=(object(), object()),
        excluded_categories=(
            BackupExclusion.MANAGED_CONTENT,
            BackupExclusion.EXTERNAL_RESOURCES,
        ),
        snapshot_warnings=(SimpleNamespace(summary="Review one portable reference."),),
    )


@unittest.skipUnless(sys.platform == "win32", "The Configure UI requires Windows Tk.")
class BackupRestorePanelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.paths = AppDataPaths.from_root(Path(self.temporary.name) / "app")
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self._destroy_root)
        self.restore_complete = Mock()
        self.recovery_required = Mock()
        self.panel = BackupRestorePanel(
            self.root,
            data_paths=self.paths,
            on_restore_complete=self.restore_complete,
            on_recovery_required=self.recovery_required,
        )
        self.panel.pack(fill=tk.BOTH, expand=True)
        self.root.update_idletasks()
        self.panel._show_progress = Mock()
        self.panel._hide_progress = Mock()

    def _destroy_root(self) -> None:
        try:
            self.panel.close()
            self.root.update()
            self.root.destroy()
        except tk.TclError:
            pass

    def _wait(self) -> None:
        deadline = time.monotonic() + 4
        while self.panel.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.root.update()
        self.assertFalse(self.panel.busy, "background UI operation did not finish")

    def test_backup_defaults_and_exclusions_are_visible_and_forwarded(self) -> None:
        destination = Path(self.temporary.name) / "portable.zip"
        service = Mock(return_value=backup_result(destination))
        with (
            patch(
                "context_palette.backup_restore_ui.filedialog.asksaveasfilename",
                return_value=str(destination),
            ),
            patch(
                "context_palette.backup_restore_ui.create_configuration_backup",
                service,
            ),
            patch("context_palette.backup_restore_ui.messagebox.showinfo") as info,
        ):
            self.panel._choose_backup_destination()
            self._wait()

        paths, selected, = service.call_args.args
        options = service.call_args.kwargs["options"]
        self.assertIs(paths, self.paths)
        self.assertEqual(selected, destination)
        self.assertTrue(options.include_inbox)
        self.assertFalse(options.include_managed_content)
        self.assertFalse(options.overwrite)
        self.assertIn("Work Item folders", self._visible_text())
        message = info.call_args.args[1]
        self.assertIn(str(destination), message)
        self.assertIn("Included files: 2", message)
        self.assertIn("optional managed text content", message)

    def test_cancelled_dialogs_do_not_call_services(self) -> None:
        with (
            patch(
                "context_palette.backup_restore_ui.filedialog.asksaveasfilename",
                return_value="",
            ),
            patch(
                "context_palette.backup_restore_ui.filedialog.askopenfilename",
                return_value="",
            ),
            patch(
                "context_palette.backup_restore_ui.create_configuration_backup"
            ) as create,
            patch(
                "context_palette.backup_restore_ui.inspect_restore_archive"
            ) as inspect,
        ):
            self.panel._choose_backup_destination()
            self.panel._choose_restore_archive()

        create.assert_not_called()
        inspect.assert_not_called()

    def test_overwrite_requires_explicit_confirmation(self) -> None:
        destination = Path(self.temporary.name) / "existing.zip"
        destination.write_bytes(b"old")
        with (
            patch(
                "context_palette.backup_restore_ui.filedialog.asksaveasfilename",
                return_value=str(destination),
            ),
            patch(
                "context_palette.backup_restore_ui.messagebox.askyesno",
                return_value=False,
            ),
            patch(
                "context_palette.backup_restore_ui.create_configuration_backup"
            ) as create,
        ):
            self.panel._choose_backup_destination()
        create.assert_not_called()

        service = Mock(return_value=backup_result(destination))
        with (
            patch(
                "context_palette.backup_restore_ui.filedialog.asksaveasfilename",
                return_value=str(destination),
            ),
            patch(
                "context_palette.backup_restore_ui.messagebox.askyesno",
                return_value=True,
            ),
            patch(
                "context_palette.backup_restore_ui.create_configuration_backup",
                service,
            ),
            patch("context_palette.backup_restore_ui.messagebox.showinfo"),
        ):
            self.panel._choose_backup_destination()
            self._wait()
        self.assertTrue(service.call_args.kwargs["options"].overwrite)

    def test_restore_inspection_preview_and_two_stage_commit(self) -> None:
        archive = Path(self.temporary.name) / "selected.zip"
        plan = restore_plan(built_in=True)
        result = SimpleNamespace(recovery_archive=archive.with_name("recovery.zip"))
        order: list[str] = []

        def inspect(paths, selected):
            self.assertIs(paths, self.paths)
            self.assertEqual(selected, archive)
            order.append("inspect")
            return plan

        def commit(paths, selected, used_plan, confirmation, *, recovery_directory):
            self.assertIs(paths, self.paths)
            self.assertEqual(selected, archive)
            self.assertIs(used_plan, plan)
            self.assertTrue(confirmation.confirmed)
            self.assertTrue(confirmation.built_in_acknowledged)
            self.assertEqual(recovery_directory, archive.parent)
            order.append("commit")
            return result

        with (
            patch(
                "context_palette.backup_restore_ui.filedialog.askopenfilename",
                return_value=str(archive),
            ),
            patch(
                "context_palette.backup_restore_ui.inspect_restore_archive",
                side_effect=inspect,
            ),
            patch("context_palette.backup_restore_ui.commit_restore", side_effect=commit),
            patch(
                "context_palette.backup_restore_ui.messagebox.askyesno",
                side_effect=[True, True],
            ) as confirm,
            patch("context_palette.backup_restore_ui.messagebox.showinfo") as info,
        ):
            self.panel._choose_restore_archive()
            self._wait()
            preview = self.panel.preview_text.get("1.0", tk.END)
            self.assertIn("Files to replace: 1", preview)
            self.assertIn("Omitted live files preserved: 1", preview)
            self.assertIn("Built-in files affected: 1", preview)
            self.assertIn("Legacy forms: present and preserved", preview)
            self.assertNotIn(r"C:\Private\Customer", preview)
            self.panel._confirm_restore()
            self._wait()

        self.assertEqual(order, ["inspect", "commit"])
        self.assertEqual(confirm.call_count, 2)
        self.assertIn(str(result.recovery_archive), info.call_args.args[1])
        self.restore_complete.assert_called_once_with()
        self.recovery_required.assert_not_called()

    def test_declining_built_in_acknowledgement_prevents_commit(self) -> None:
        self.panel._selected_archive = Path(self.temporary.name) / "backup.zip"
        self.panel._restore_plan = restore_plan(built_in=True)
        with (
            patch(
                "context_palette.backup_restore_ui.messagebox.askyesno",
                side_effect=[True, False],
            ),
            patch("context_palette.backup_restore_ui.commit_restore") as commit,
        ):
            self.panel._confirm_restore()
        commit.assert_not_called()

    def test_invalid_archive_keeps_commit_disabled_and_live_state_unchanged(self) -> None:
        archive = Path(self.temporary.name) / "invalid.zip"
        with (
            patch(
                "context_palette.backup_restore_ui.filedialog.askopenfilename",
                return_value=str(archive),
            ),
            patch(
                "context_palette.backup_restore_ui.inspect_restore_archive",
                side_effect=RestoreArchiveError("The restore archive is invalid."),
            ),
            patch("context_palette.backup_restore_ui.commit_restore") as commit,
            patch("context_palette.backup_restore_ui.messagebox.showerror") as error,
        ):
            self.panel._choose_restore_archive()
            self._wait()
            self.panel.commit_restore_button.invoke()
        self.assertIsNone(self.panel._restore_plan)
        self.assertIn("disabled", self.panel.commit_restore_button.state())
        commit.assert_not_called()
        self.assertIn("live configuration was unchanged", self.panel.status_var.get())
        self.assertNotIn(r"C:\Private", error.call_args.args[1])

    def test_stale_plan_requires_reinspection(self) -> None:
        self._prepare_commit()
        with (
            patch(
                "context_palette.backup_restore_ui.messagebox.askyesno",
                return_value=True,
            ),
            patch(
                "context_palette.backup_restore_ui.commit_restore",
                side_effect=RestorePlanStaleError("stale"),
            ),
            patch("context_palette.backup_restore_ui.messagebox.showwarning"),
        ):
            self.panel._confirm_restore()
            self._wait()
        self.assertIsNone(self.panel._restore_plan)
        self.assertIn("Inspect the backup again", self.panel.status_var.get())
        self.restore_complete.assert_not_called()

    def test_completed_rollback_keeps_configure_usable(self) -> None:
        self._prepare_commit()
        with (
            patch(
                "context_palette.backup_restore_ui.messagebox.askyesno",
                return_value=True,
            ),
            patch(
                "context_palette.backup_restore_ui.commit_restore",
                side_effect=RestoreCommitError(rollback_completed=True),
            ),
            patch("context_palette.backup_restore_ui.messagebox.showerror"),
        ):
            self.panel._confirm_restore()
            self._wait()
        self.assertIn("previous configuration was restored", self.panel.status_var.get())
        self.recovery_required.assert_not_called()
        with patch(
            "context_palette.backup_restore_ui.filedialog.askopenfilename",
            return_value="",
        ) as dialog:
            self.panel.inspect_restore_button.invoke()
        dialog.assert_called_once()

    def test_incomplete_rollback_and_recovery_requirement_block_mutation(self) -> None:
        for failure in (
            RestoreCommitError(rollback_completed=False),
            RestoreRecoveryRequiredError("recovery required"),
        ):
            with self.subTest(failure=type(failure).__name__):
                self._prepare_commit()
                self.recovery_required.reset_mock()
                with (
                    patch(
                        "context_palette.backup_restore_ui.messagebox.askyesno",
                        return_value=True,
                    ),
                    patch(
                        "context_palette.backup_restore_ui.commit_restore",
                        side_effect=failure,
                    ),
                    patch("context_palette.backup_restore_ui.messagebox.showerror") as error,
                ):
                    self.panel._confirm_restore()
                    self._wait()
                self.recovery_required.assert_called_once_with()
                self.assertIn("Restart", error.call_args.args[0])

    def test_duplicate_operation_is_ignored_and_callback_runs_on_tk_thread(self) -> None:
        destination = Path(self.temporary.name) / "backup.zip"
        release = threading.Event()
        service_thread_ids: list[int] = []
        callback_thread_ids: list[int] = []

        def service(*_args, **_kwargs):
            service_thread_ids.append(threading.get_ident())
            release.wait(2)
            return backup_result(destination)

        main_thread = threading.get_ident()
        with (
            patch(
                "context_palette.backup_restore_ui.filedialog.asksaveasfilename",
                return_value=str(destination),
            ) as dialog,
            patch(
                "context_palette.backup_restore_ui.create_configuration_backup",
                side_effect=service,
            ) as create,
            patch(
                "context_palette.backup_restore_ui.messagebox.showinfo",
                side_effect=lambda *_args, **_kwargs: callback_thread_ids.append(
                    threading.get_ident()
                ),
            ),
        ):
            self.panel._choose_backup_destination()
            self.panel._choose_backup_destination()
            self.assertTrue(self.panel.busy)
            release.set()
            self._wait()

        self.assertEqual(dialog.call_count, 1)
        self.assertEqual(create.call_count, 1)
        self.assertNotEqual(service_thread_ids, [main_thread])
        self.assertEqual(callback_thread_ids, [main_thread])

    def _prepare_commit(self) -> None:
        self.panel._selected_archive = Path(self.temporary.name) / "backup.zip"
        self.panel._restore_plan = restore_plan()
        self.panel.commit_restore_button.state(["!disabled"])

    def _visible_text(self) -> str:
        values: list[str] = []
        pending = list(self.panel.winfo_children())
        while pending:
            widget = pending.pop()
            pending.extend(widget.winfo_children())
            try:
                values.append(str(widget.cget("text")))
            except tk.TclError:
                pass
        return "\n".join(values)


@unittest.skipUnless(sys.platform == "win32", "The UI worker requires Windows Tk.")
class UiWorkerTests(unittest.TestCase):
    def test_worker_delivers_success_and_failure_on_tk_thread(self) -> None:
        root = tk.Tk()
        root.withdraw()
        worker = _UiWorker(root)
        outcomes = []
        threads = []
        main_thread = threading.get_ident()
        try:
            self.assertTrue(
                worker.start(
                    lambda: 7,
                    lambda outcome: (outcomes.append(outcome), threads.append(threading.get_ident())),
                )
            )
            deadline = time.monotonic() + 3
            while worker.busy and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
            self.assertEqual(outcomes[0].value, 7)
            self.assertEqual(threads, [main_thread])

            self.assertTrue(
                worker.start(
                    lambda: (_ for _ in ()).throw(ValueError("safe failure")),
                    lambda outcome: outcomes.append(outcome),
                )
            )
            while worker.busy and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
            self.assertIsInstance(outcomes[1].error, ValueError)
        finally:
            worker.close()
            root.destroy()


class BackupRestoreFormattingTests(unittest.TestCase):
    def test_summaries_use_only_safe_service_metadata(self) -> None:
        destination = Path("backup.zip")
        backup = format_backup_success(backup_result(destination))
        restore = format_restore_plan(restore_plan(built_in=True))

        self.assertIn("Included files: 2", backup)
        self.assertIn("data/actions.json", restore)
        for private in (
            "PRIVATE ACTION VALUE",
            "PRIVATE INBOX CONTENT",
            r"C:\Private\Customer",
            "credential-target-name",
        ):
            self.assertNotIn(private, backup)
            self.assertNotIn(private, restore)
