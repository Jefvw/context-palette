from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from context_palette.action_bulk_update import BulkActionUpdateError
from context_palette.action_bulk_update_window import ActionBulkUpdateWindow
from context_palette.actions import ACTIVE_STATE, ARCHIVED_STATE, Action


def action(
    action_id: str,
    title: str,
    *,
    value: str | None = None,
    state: str = ACTIVE_STATE,
    contexts: tuple[str, ...] = ("Finance",),
    tags: tuple[str, ...] = ("monthly",),
    arguments: tuple[str, ...] = (),
    working_directory: str | None = None,
) -> Action:
    return Action(
        action_id,
        title,
        "",
        "open_windows_target",
        value or rf"D:\reports\{action_id}.xlsx",
        state=state,
        contexts=contexts,
        tags=tags,
        arguments=arguments,
        working_directory=working_directory,
    )


def candidate(
    row_number: int,
    status: str,
    before: Action,
    after: Action | None,
    *,
    changed_fields: tuple[str, ...] = (),
    selected_by_default: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        row_number=row_number,
        action_id=before.id,
        original_action=before,
        action=after,
        changed_fields=changed_fields,
        status=status,
        messages=(f"{status} message",),
        selected_by_default=selected_by_default,
    )


def descendants(widget: tk.Misc):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class ActionBulkUpdateWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.geometry("1x1+0+0")
        self.root.update_idletasks()
        self.addCleanup(self.root.destroy)

        before_ready = action(
            "personal-ready",
            "Old report",
            arguments=("--profile", " old value "),
            working_directory=r"D:\old",
        )
        after_ready = action(
            "personal-ready",
            "New report",
            contexts=("Finance", "Quarter close"),
            arguments=("--profile", " new value "),
            working_directory=r"D:\new",
        )
        before_unchanged = action("personal-unchanged", "Unchanged")
        before_error = action("personal-error", "Invalid edit")
        self.actions = (
            before_ready,
            before_unchanged,
            before_error,
            action("personal-archived", "Archived", state=ARCHIVED_STATE),
            action("shared-action", "Built-in"),
        )
        self.source = Path(r"D:\imports\Action updates.xlsx")
        self.workbook = SimpleNamespace(path=self.source, digest="digest")
        self.plan = SimpleNamespace(
            candidates=(
                candidate(
                    2,
                    "Ready",
                    before_ready,
                    after_ready,
                    changed_fields=("Name", "Contexts", "Arguments", "Working folder"),
                    selected_by_default=True,
                ),
                candidate(
                    3,
                    "No changes",
                    before_unchanged,
                    before_unchanged,
                ),
                candidate(4, "Error", before_error, None),
            )
        )
        self.on_change = Mock()
        with patch(
            "context_palette.action_bulk_update_window.configure_standard_window"
        ) as configure:
            self.window = ActionBulkUpdateWindow(
                self.root,
                actions=self.actions,
                local_action_ids=(
                    "personal-ready",
                    "personal-unchanged",
                    "personal-error",
                    "personal-archived",
                ),
                local_context_names=("Finance", "Quarter close"),
                local_actions_path=Path("local_actions.json"),
                shared_actions_path=Path("actions.json"),
                shared_contexts_path=Path("contexts.json"),
                local_contexts_path=Path("local_contexts.json"),
                on_change=self.on_change,
            )
        configure.assert_called_once_with(self.window.window, self.root)
        self.addCleanup(self._close_window)
        self.root.update()

    def _close_window(self) -> None:
        if self.window.window.winfo_exists():
            self.window.close()

    def _load(self) -> None:
        with patch(
            "context_palette.action_bulk_update_window.read_action_update_workbook",
            return_value=self.workbook,
        ) as read, patch(
            "context_palette.action_bulk_update_window.plan_bulk_action_update",
            return_value=self.plan,
        ) as make_plan:
            self.window._load_workbook(self.source)
        read.assert_called_once_with(
            self.source,
            self.window._personal_active_actions(),
        )
        make_plan.assert_called_once_with(
            self.workbook,
            self.window.actions,
            self.window.local_action_ids,
            self.window.local_context_names,
        )

    def test_compact_review_defaults_ready_only_and_shows_exact_changes(self) -> None:
        self._load()

        self.assertEqual(self.window.selected_row_numbers, {2})
        self.assertEqual(self.window.update_button.cget("text"), "Update 1 Action")
        self.assertFalse(self.window.update_button.instate(["disabled"]))
        self.assertEqual(self.window.tree.set("row-2", "use"), "[x]")
        self.assertEqual(self.window.tree.set("row-3", "use"), "-")
        self.assertEqual(self.window.tree.set("row-4", "use"), "-")
        self.assertEqual(
            self.window.tree.set("row-2", "changes"),
            "Name, Contexts, Arguments, Working folder",
        )
        detail = self.window.detail.get("1.0", "end-1c")
        self.assertIn('Before: "Old report"', detail)
        self.assertIn('After:  "New report"', detail)
        self.assertIn('["Finance", "Quarter close"]', detail)
        self.assertIn('["--profile", " new value "]', detail)
        self.assertIn(r'After:  "D:\\new"', detail)
        self.assertIn("Ready message", detail)

    def test_failed_load_clears_the_previous_review_and_commit_state(self) -> None:
        self._load()
        invalid = Path(r"D:\imports\invalid.xlsx")
        from context_palette.action_update_workbook import ActionUpdateWorkbookError

        with patch(
            "context_palette.action_bulk_update_window.read_action_update_workbook",
            side_effect=ActionUpdateWorkbookError("bad workbook"),
        ), patch("context_palette.action_bulk_update_window.messagebox.showerror"):
            self.window._load_workbook(invalid)

        self.assertIsNone(self.window.workbook)
        self.assertIsNone(self.window.plan)
        self.assertEqual(self.window.selected_row_numbers, set())
        self.assertEqual(self.window.tree.get_children(), ())
        self.assertTrue(self.window.update_button.instate(["disabled"]))
        self.assertFalse(self.window.reload_button.instate(["disabled"]))
        self.assertEqual(self.window.source_path, invalid)

    def test_space_toggles_ready_but_not_unchanged_or_error(self) -> None:
        self._load()
        self.window.tree.selection_set("row-2")
        self.window.tree.focus("row-2")

        self.assertEqual(self.window._toggle_from_key(), "break")
        self.assertEqual(self.window.selected_row_numbers, set())

        for iid in ("row-3", "row-4"):
            self.window.tree.selection_set(iid)
            self.window.tree.focus(iid)
            self.window._toggle_from_key()
        self.assertEqual(self.window.selected_row_numbers, set())

    def test_update_commits_once_without_confirmation_and_stales_plan(self) -> None:
        self._load()
        updated = self.plan.candidates[0].action
        assert updated is not None
        with patch(
            "context_palette.action_bulk_update_window.commit_bulk_action_update",
            return_value=(updated,),
        ) as commit, patch(
            "context_palette.action_bulk_update_window.messagebox.askyesno",
            create=True,
        ) as ask, patch(
            "context_palette.action_bulk_update_window.messagebox.showinfo",
            create=True,
        ) as info:
            self.window.update_actions()

        commit.assert_called_once_with(
            self.plan,
            (2,),
            local_actions_path=self.window.local_actions_path,
            shared_actions_path=self.window.shared_actions_path,
            shared_contexts_path=self.window.shared_contexts_path,
            local_contexts_path=self.window.local_contexts_path,
        )
        ask.assert_not_called()
        info.assert_not_called()
        self.on_change.assert_called_once_with()
        self.assertEqual(self.window.tree.set("row-2", "status"), "Updated")
        self.assertTrue(self.window.update_button.instate(["disabled"]))
        self.assertTrue(self.window._review_is_stale)
        self.assertIn("Export a fresh workbook", self.window.status_var.get())

        with patch(
            "context_palette.action_bulk_update_window.commit_bulk_action_update"
        ) as second_commit:
            self.window.update_actions()
        second_commit.assert_not_called()

    def test_failed_commit_stales_review_and_requires_reload(self) -> None:
        self._load()
        with (
            patch(
                "context_palette.action_bulk_update_window.commit_bulk_action_update",
                side_effect=BulkActionUpdateError("saved Actions changed"),
            ) as commit,
            patch(
                "context_palette.action_bulk_update_window.messagebox.showerror"
            ),
        ):
            self.window.update_actions()

        commit.assert_called_once()
        self.assertTrue(self.window._review_is_stale)
        self.assertEqual(self.window.selected_row_numbers, set())
        self.assertTrue(self.window.update_button.instate(["disabled"]))
        self.assertIn("Reload the workbook", self.window.status_var.get())

        with patch(
            "context_palette.action_bulk_update_window.commit_bulk_action_update"
        ) as second_commit:
            self.window.update_actions()
        second_commit.assert_not_called()

    def test_incomplete_rollback_reports_unknown_effects_and_blocks_retry(self) -> None:
        self._load()
        failure = BulkActionUpdateError(
            "Saved Actions or Contexts may have changed. Inspect the latest "
            "backup and Diagnostics.",
            rollback_completed=False,
        )
        with (
            patch(
                "context_palette.action_bulk_update_window.commit_bulk_action_update",
                side_effect=failure,
            ) as commit,
            patch(
                "context_palette.action_bulk_update_window.messagebox.showerror"
            ) as show_error,
        ):
            self.window.update_actions()

        commit.assert_called_once()
        self.assertTrue(self.window._effects_unknown)
        self.assertTrue(self.window._review_is_stale)
        self.assertEqual(self.window.selected_row_numbers, set())
        for button in (
            self.window.export_button,
            self.window.choose_button,
            self.window.reload_button,
            self.window.update_button,
        ):
            self.assertTrue(button.instate(["disabled"]))
        title, message = show_error.call_args.args
        self.assertEqual(title, "Actions or Contexts may have changed")
        self.assertIn("may have changed", message)
        status = self.window.status_var.get()
        self.assertNotIn("No Actions were updated", status)
        self.assertIn("Do not retry", status)
        self.assertIn("backup", status)
        self.assertIn("Diagnostics", status)

        with (
            patch.object(self.window, "_load_workbook") as load,
            patch(
                "context_palette.action_bulk_update_window.filedialog.asksaveasfilename"
            ) as save_dialog,
            patch(
                "context_palette.action_bulk_update_window.filedialog.askopenfilename"
            ) as open_dialog,
        ):
            self.window.reload_workbook()
            self.window.export_fresh_workbook()
            self.window.choose_workbook()
            self.window._reload_from_key()
            self.window._export_from_key()
            self.window._choose_from_key()
        load.assert_not_called()
        save_dialog.assert_not_called()
        open_dialog.assert_not_called()

    def test_export_contains_only_personal_active_actions_and_loads_result(self) -> None:
        target = Path(r"D:\imports\Context Palette Action Updates.xlsx")
        with patch(
            "context_palette.action_bulk_update_window.filedialog.asksaveasfilename",
            return_value=str(target),
        ), patch(
            "context_palette.action_bulk_update_window.write_action_update_workbook",
            return_value=target,
        ) as write, patch.object(self.window, "_load_workbook") as load:
            self.window.export_fresh_workbook()

        write.assert_called_once_with(
            target,
            self.actions[:3],
        )
        load.assert_called_once_with(target)

    def test_reload_and_keyboard_routes_are_visible(self) -> None:
        self._load()
        with patch.object(self.window, "_load_workbook") as load:
            self.window.reload_workbook()
        load.assert_called_once_with(self.source)

        labels = {
            str(widget.cget("text"))
            for widget in descendants(self.window.window)
            if isinstance(widget, ttk.Button)
        }
        self.assertIn("Export fresh workbook…", labels)
        self.assertIn("Choose updated workbook…", labels)
        self.assertIn("Reload", labels)
        self.assertIn("Update 1 Action", labels)
        self.assertIn("personal Active Actions only", self.window.intro_label.cget("text"))
        self.assertIn("Missing workbook rows are not deleted", self.window.intro_label.cget("text"))
        self.assertIn("lifecycle remains unchanged", self.window.intro_label.cget("text"))
        self.assertIn("private values and paths", self.window.intro_label.cget("text"))
        self.assertTrue(self.window.window.bind("<Control-e>"))
        self.assertTrue(self.window.window.bind("<Control-o>"))
        self.assertTrue(self.window.window.bind("<F5>"))
        self.assertTrue(self.window.window.bind("<Escape>"))
        self.assertTrue(self.window.tree.bind("<space>"))
        self.assertTrue(self.window.tree.cget("xscrollcommand"))


if __name__ == "__main__":
    unittest.main()
