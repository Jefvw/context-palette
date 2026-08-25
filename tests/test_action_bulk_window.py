from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from context_palette.action_bulk import BulkActionCandidate, BulkActionPlan
from context_palette.action_bulk_window import ActionBulkWindow
from context_palette.action_workbook import ActionWorkbook, ActionWorkbookRow
from context_palette.actions import Action


def action(
    action_id: str,
    title: str = "Open report",
    *,
    action_type: str = "open_file",
    value: str | None = None,
    description: str = "",
    quick_action_path: tuple[str, ...] = (),
    arguments: tuple[str, ...] = (),
    working_directory: str | None = None,
) -> Action:
    return Action(
        action_id,
        title,
        "",
        action_type,
        value or rf"D:\reports\{action_id}.xlsx",
        contexts=("Finance",),
        tags=("monthly",),
        description=description,
        quick_action_path=quick_action_path,
        arguments=arguments,
        working_directory=working_directory,
    )


def row(number: int, *, title: str = "Open report") -> ActionWorkbookRow:
    return ActionWorkbookRow(
        number,
        True,
        title,
        "open_file",
        rf"D:\reports\row-{number}.xlsx",
        ("Finance",),
        ("monthly",),
        "",
        (),
        (),
        "",
    )


def candidate(
    number: int,
    status: str,
    *,
    selected: bool = False,
    with_action: bool = True,
    reviewed_action: Action | None = None,
) -> BulkActionCandidate:
    return BulkActionCandidate(
        number,
        (
            reviewed_action or action(f"action-{number}", f"Action {number}")
            if with_action
            else None
        ),
        status,
        (f"{status} message",),
        selected,
    )


def workbook(path: Path) -> ActionWorkbook:
    return ActionWorkbook(path, "digest", (row(2), row(3), row(4), row(5)))


def plan(path: Path) -> BulkActionPlan:
    return BulkActionPlan(
        path,
        "digest",
        (
            candidate(
                2,
                "Ready",
                selected=True,
                reviewed_action=action(
                    "action-2",
                    "Run report",
                    action_type="launch_app",
                    value=r"D:\tools\report.exe",
                    description="Runs the monthly report.",
                    arguments=("--profile", "monthly"),
                    working_directory=r"D:\tools",
                ),
            ),
            candidate(
                3,
                "Possible duplicate",
                reviewed_action=action(
                    "action-3",
                    "Open reports",
                    action_type="open_folder",
                    value=r"D:\reports",
                    quick_action_path=("Folders", "Reports"),
                ),
            ),
            candidate(4, "Warning"),
            candidate(5, "Error", with_action=False),
        ),
        "existing",
    )


def descendants(widget: tk.Misc):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class ActionBulkWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.geometry("1x1+0+0")
        self.root.update_idletasks()
        self.addCleanup(self.root.destroy)
        self.source = Path(r"D:\imports\Actions.xlsx")
        self.workbook = workbook(self.source)
        self.plan = plan(self.source)
        self.on_change = Mock()
        with patch(
            "context_palette.action_bulk_window.place_child_window",
            return_value=(900, 650, 10, 10),
        ) as place:
            self.window = ActionBulkWindow(
                self.root,
                actions=(),
                local_context_names=("Finance",),
                local_actions_path=Path("local_actions.json"),
                shared_actions_path=Path("actions.json"),
                shared_contexts_path=Path("contexts.json"),
                local_contexts_path=Path("local_contexts.json"),
                on_change=self.on_change,
            )
        place.assert_called_once_with(self.window.window, self.root, size=(900, 650))
        self.addCleanup(self._close_window)
        self.root.update()

    def _close_window(self) -> None:
        if self.window.window.winfo_exists():
            self.window.close()

    def _load(self) -> None:
        with patch(
            "context_palette.action_bulk_window.read_action_import_workbook",
            return_value=self.workbook,
        ) as read, patch(
            "context_palette.action_bulk_window.plan_bulk_action_create",
            return_value=self.plan,
        ) as make_plan:
            self.window._load_workbook(self.source)
        read.assert_called_once_with(self.source)
        make_plan.assert_called_once_with(
            self.workbook, self.window.actions, self.window.local_context_names
        )

    def test_review_defaults_only_ready_rows_and_exposes_effect_label(self) -> None:
        self._load()

        self.assertEqual(self.window.selected_row_numbers, {2})
        self.assertEqual(self.window.create_button.cget("text"), "Create 1 Action")
        self.assertFalse(self.window.create_button.instate(["disabled"]))
        self.assertEqual(self.window.tree.set("row-2", "use"), "[x]")
        self.assertEqual(self.window.tree.set("row-3", "use"), "[ ]")
        self.assertEqual(self.window.tree.set("row-4", "use"), "[ ]")
        self.assertEqual(self.window.tree.set("row-5", "use"), "-")
        detail = self.window.detail.get("1.0", "end-1c")
        self.assertIn("Value:", detail)
        self.assertIn("Contexts:", detail)
        self.assertIn("Tags:", detail)
        self.assertIn("Messages:", detail)
        self.assertIn("Runs the monthly report.", detail)
        self.assertIn("--profile\nmonthly", detail)
        self.assertIn(r"D:\tools", detail)

        self.window.tree.selection_set("row-3")
        self.window._show_detail()
        self.assertIn("Folders > Reports", self.window.detail.get("1.0", "end-1c"))

    def test_invalid_new_workbook_clears_the_previous_executable_plan(self) -> None:
        self._load()
        invalid = Path(r"D:\imports\invalid.xlsx")
        from context_palette.action_workbook import ActionWorkbookError

        with patch(
            "context_palette.action_bulk_window.read_action_import_workbook",
            side_effect=ActionWorkbookError("bad workbook"),
        ), patch("context_palette.action_bulk_window.messagebox.showerror"):
            self.window._load_workbook(invalid)

        self.assertIsNone(self.window.workbook)
        self.assertIsNone(self.window.plan)
        self.assertEqual(self.window.selected_row_numbers, set())
        self.assertEqual(self.window.tree.get_children(), ())
        self.assertTrue(self.window.create_button.instate(["disabled"]))
        self.assertFalse(self.window.reload_button.instate(["disabled"]))
        self.assertEqual(self.window.source_path, invalid)

    def test_space_can_select_warning_but_not_error(self) -> None:
        self._load()
        self.window.tree.selection_set("row-4")
        self.window.tree.focus("row-4")

        self.assertEqual(self.window._toggle_from_key(), "break")
        self.assertEqual(self.window.selected_row_numbers, {2, 4})

        self.window.tree.selection_set("row-5")
        self.window.tree.focus("row-5")
        self.window._toggle_from_key()
        self.assertEqual(self.window.selected_row_numbers, {2, 4})

    def test_create_commits_once_without_a_second_confirmation(self) -> None:
        self._load()
        created = (action("created"),)
        with patch(
            "context_palette.action_bulk_window.commit_bulk_action_create",
            return_value=created,
        ) as commit, patch(
            "context_palette.action_bulk_window.messagebox.showinfo"
        ) as info, patch(
            "context_palette.action_bulk_window.messagebox.askyesno",
            create=True,
        ) as ask:
            self.window.create_actions()

        commit.assert_called_once_with(
            self.plan,
            (2,),
            self.window.local_actions_path,
            self.window.shared_actions_path,
            self.window.shared_contexts_path,
            self.window.local_contexts_path,
        )
        ask.assert_not_called()
        info.assert_called_once()
        self.on_change.assert_called_once_with()
        self.assertEqual(self.window.tree.set("row-2", "status"), "Created")
        self.assertTrue(self.window.create_button.instate(["disabled"]))

    def test_double_submission_is_ignored(self) -> None:
        self._load()
        self.window.submitting = True
        with patch(
            "context_palette.action_bulk_window.commit_bulk_action_create"
        ) as commit:
            self.window.create_actions()
        commit.assert_not_called()
        self.on_change.assert_not_called()

    def test_reload_after_create_plans_against_the_newly_created_actions(self) -> None:
        self._load()
        created = (action("created"),)
        with patch(
            "context_palette.action_bulk_window.commit_bulk_action_create",
            return_value=created,
        ), patch("context_palette.action_bulk_window.messagebox.showinfo"):
            self.window.create_actions()

        updated_plan = plan(self.source)
        with patch(
            "context_palette.action_bulk_window.read_action_import_workbook",
            return_value=self.workbook,
        ), patch(
            "context_palette.action_bulk_window.plan_bulk_action_create",
            return_value=updated_plan,
        ) as make_plan:
            self.window.reload_workbook()

        make_plan.assert_called_once_with(
            self.workbook, created, self.window.local_context_names
        )

    def test_save_blank_template_uses_standard_writer(self) -> None:
        target = Path(r"D:\imports\Context Palette Actions.xlsx")
        with patch(
            "context_palette.action_bulk_window.filedialog.asksaveasfilename",
            return_value=str(target),
        ), patch(
            "context_palette.action_bulk_window.write_action_import_template",
            return_value=target,
        ) as write, patch(
            "context_palette.action_bulk_window.messagebox.showinfo"
        ) as info:
            self.window.save_blank_template()

        write.assert_called_once_with(target)
        info.assert_called_once()
        self.assertIn(str(target), self.window.status_var.get())

    def test_reload_reuses_the_selected_workbook(self) -> None:
        self._load()
        with patch.object(self.window, "_load_workbook") as load:
            self.window.reload_workbook()
        load.assert_called_once_with(self.source)

    def test_window_has_review_controls_and_keyboard_routes(self) -> None:
        labels = {
            str(widget.cget("text"))
            for widget in descendants(self.window.window)
            if isinstance(widget, ttk.Button)
        }
        self.assertIn("Choose Actions workbook…", labels)
        self.assertIn("Save blank Actions workbook…", labels)
        self.assertIn("Reload", labels)
        self.assertIn("Create 0 Actions", labels)
        self.assertTrue(self.window.window.bind("<Control-o>"))
        self.assertTrue(self.window.window.bind("<F5>"))
        self.assertTrue(self.window.tree.bind("<space>"))
        self.assertTrue(self.window.tree.cget("xscrollcommand"))


if __name__ == "__main__":
    unittest.main()
