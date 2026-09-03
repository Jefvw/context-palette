from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from context_palette.action_bulk_lifecycle import (
    BulkActionLifecycleCandidate,
    BulkActionLifecycleError,
    BulkActionLifecyclePlan,
)
from context_palette.action_bulk_lifecycle_window import ActionBulkLifecycleWindow
from context_palette.action_deletion import ActionDeletionReport
from context_palette.actions import ACTIVE_STATE, ARCHIVED_STATE, Action


def action(
    action_id: str,
    title: str,
    *,
    state: str = ACTIVE_STATE,
) -> Action:
    return Action(
        action_id,
        title,
        "General",
        "open_url",
        f"https://example.test/{action_id}",
        state=state,
    )


def descendants(widget: tk.Misc):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class ActionBulkLifecycleWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.geometry("1x1+0+0")
        self.root.update_idletasks()
        self.addCleanup(self.root.destroy)

        self.active_one = action("active-one", "Active one")
        self.active_two = action("active-two", "Active two")
        self.legacy = action(
            "legacy-one",
            "Legacy one",
            state=ARCHIVED_STATE,
        )
        self.shared = action("shared", "Built-in")
        self.actions = (
            self.active_one,
            self.active_two,
            self.legacy,
            self.shared,
        )
        self.on_change = Mock()
        with patch(
            "context_palette.action_bulk_lifecycle_window.configure_standard_window"
        ) as configure:
            self.window = self._make_window(self.actions)
        configure.assert_called_once_with(self.window.window, self.root)
        self.addCleanup(self._close_window)
        self.root.update()

    def _make_window(
        self,
        actions: tuple[Action, ...],
        *,
        local_ids: tuple[str, ...] = (
            "active-one",
            "active-two",
            "legacy-one",
        ),
    ) -> ActionBulkLifecycleWindow:
        return ActionBulkLifecycleWindow(
            self.root,
            actions=actions,
            local_action_ids=local_ids,
            local_actions_path=Path("local_actions.json"),
            shared_actions_path=Path("actions.json"),
            shared_contexts_path=Path("contexts.json"),
            local_contexts_path=Path("local_contexts.json"),
            shared_command_surface_path=Path("command_surface.json"),
            local_command_surface_path=Path("local_command_surface.json"),
            palette_path=Path("palette.json"),
            on_change=self.on_change,
        )

    def _close_window(self) -> None:
        if self.window.window.winfo_exists():
            self.window.close()

    def _plan(
        self,
        selected: tuple[Action, ...],
        *,
        blocked_ids: tuple[str, ...] = (),
    ) -> BulkActionLifecyclePlan:
        candidates = tuple(
            BulkActionLifecycleCandidate(
                item,
                "Blocked" if item.id in blocked_ids else "Ready",
                (
                    ("Also select dependent sequence: Monthly sequence",)
                    if item.id in blocked_ids
                    else ()
                ),
                (("sequence-monthly",) if item.id in blocked_ids else ()),
            )
            for item in selected
        )
        return BulkActionLifecyclePlan(
            action_ids=tuple(item.id for item in selected),
            candidates=candidates,
            impact=ActionDeletionReport(3, 1, 4),
            configuration_fingerprint="reviewed",
            paths=self.window.paths,
        )

    def test_starts_with_all_personal_states_and_one_delete_action(self) -> None:
        self.assertEqual(
            self.window.tree.get_children(),
            ("action-active-one", "action-active-two", "action-legacy-one"),
        )
        self.assertEqual(
            self.window.tree.set("action-active-one", "availability"),
            "Active",
        )
        self.assertEqual(
            self.window.tree.set("action-legacy-one", "availability"),
            "Legacy inactive",
        )
        self.assertEqual(
            self.window.commit_button.cget("text"),
            "Delete 0 Actions permanently",
        )
        self.assertTrue(self.window.commit_button.instate(["disabled"]))

        labels = {
            str(widget.cget("text"))
            for widget in descendants(self.window.window)
            if isinstance(widget, ttk.Button)
        }
        self.assertIn("Select all shown", labels)
        self.assertIn("Clear selection", labels)
        self.assertIn("Close", labels)
        self.assertNotIn("Prepare 0 Actions for deletion", labels)
        self.assertFalse(any(label.startswith("Show prepared") for label in labels))
        self.assertIn(
            "External targets are never changed",
            self.window.intro_label.cget("text"),
        )
        self.assertEqual(self.window.tree.heading("use")["text"], "Delete")
        self.assertTrue(self.window.window.bind("<Control-f>"))
        self.assertTrue(self.window.window.bind("<Control-a>"))
        self.assertTrue(self.window.window.bind("<F5>"))
        self.assertTrue(self.window.window.bind("<Escape>"))
        self.assertTrue(self.window.tree.bind("<space>"))
        self.assertTrue(self.window.tree.cget("xscrollcommand"))

    def test_footer_and_review_remain_visible_at_150_percent_scaling(self) -> None:
        self._close_window()
        original_scaling = float(self.root.tk.call("tk", "scaling"))
        try:
            self.root.tk.call("tk", "scaling", 2.0)
            self.window = self._make_window(self.actions)
            self.root.update()

            window = self.window.window
            client_width = window.winfo_width()
            client_height = window.winfo_height()
            for widget in (
                self.window.intro_label,
                self.window.tree,
                self.window.detail,
                self.window.commit_button,
            ):
                self.assertTrue(widget.winfo_ismapped())
                left = widget.winfo_rootx() - window.winfo_rootx()
                top = widget.winfo_rooty() - window.winfo_rooty()
                self.assertGreaterEqual(left, 0)
                self.assertGreaterEqual(top, 0)
                self.assertLessEqual(left + widget.winfo_width(), client_width)
                self.assertLessEqual(top + widget.winfo_height(), client_height)
            self.assertGreater(self.window.tree.winfo_height(), 40)
            self.assertGreater(self.window.detail.winfo_height(), 40)
        finally:
            self.root.tk.call("tk", "scaling", original_scaling)

    def test_selection_plans_exact_batch_and_space_toggles(self) -> None:
        reviewed = self._plan((self.active_one,))
        with patch(
            "context_palette.action_bulk_lifecycle_window.plan_bulk_action_deletion",
            return_value=reviewed,
        ) as planner:
            self.window.tree.selection_set("action-active-one")
            self.window.tree.focus("action-active-one")
            self.assertEqual(self.window._toggle_from_key(), "break")

        planner.assert_called_once_with(("active-one",), paths=self.window.paths)
        self.assertEqual(self.window.selected_action_ids, {"active-one"})
        self.assertEqual(self.window.tree.set("action-active-one", "use"), "[x]")
        self.assertEqual(
            self.window.commit_button.cget("text"),
            "Delete 1 Action permanently",
        )
        self.assertFalse(self.window.commit_button.instate(["disabled"]))
        detail = self.window.detail.get("1.0", "end-1c")
        self.assertIn("Action records: deleted permanently.", detail)
        self.assertIn("Saved references removed: 3", detail)
        self.assertIn("Empty Quick-action items removed: 1", detail)
        self.assertIn("Configuration files changed: 4", detail)
        self.assertIn("External targets: not deleted or changed.", detail)

    def test_ctrl_a_selects_shown_actions_only_when_table_has_focus(self) -> None:
        self.window.filter_var.set("Active")
        self.window.filter_entry.focus_force()
        self.window.filter_entry.icursor(2)
        self.window.filter_entry.selection_clear()
        self.root.update()

        self.window.filter_entry.event_generate("<Control-KeyPress-a>")
        self.root.update()

        self.assertEqual(self.window.selected_action_ids, set())
        self.assertTrue(self.window.filter_entry.selection_present())

        reviewed = self._plan((self.active_one, self.active_two))
        with patch(
            "context_palette.action_bulk_lifecycle_window.plan_bulk_action_deletion",
            return_value=reviewed,
        ):
            self.window.tree.focus_force()
            self.root.update()
            self.window.tree.event_generate("<Control-KeyPress-a>")
            self.root.update()

        self.assertEqual(
            self.window.selected_action_ids,
            {"active-one", "active-two"},
        )

    def test_blocked_selection_stays_visible_and_disables_delete(self) -> None:
        blocked = self._plan(
            (self.active_one,),
            blocked_ids=("active-one",),
        )
        with patch(
            "context_palette.action_bulk_lifecycle_window.plan_bulk_action_deletion",
            return_value=blocked,
        ):
            self.window._toggle_iids(("action-active-one",))

        self.assertEqual(self.window.tree.set("action-active-one", "status"), "Blocked")
        self.assertTrue(self.window.commit_button.instate(["disabled"]))
        self.assertIn("1 blocked", self.window.status_var.get())
        detail = self.window.detail.get("1.0", "end-1c")
        self.assertIn("Monthly sequence", detail)
        self.assertIn("sequence-monthly", detail)

    def test_delete_commits_without_another_dialog_and_clears_selection(self) -> None:
        deletion_plan = self._plan((self.active_one, self.legacy))
        with (
            patch(
                "context_palette.action_bulk_lifecycle_window.plan_bulk_action_deletion",
                return_value=deletion_plan,
            ),
            patch(
                "context_palette.action_bulk_lifecycle_window.commit_bulk_action_deletion",
                return_value=deletion_plan.impact,
            ) as commit,
            patch(
                "context_palette.action_bulk_lifecycle_window.load_combined_stored_actions",
                return_value=([self.active_two, self.shared], {self.active_two.id}),
            ),
            patch(
                "context_palette.action_bulk_lifecycle_window.messagebox.askyesno",
                create=True,
            ) as confirmation,
        ):
            self.window.selected_action_ids = {self.active_one.id, self.legacy.id}
            self.window.plan = deletion_plan
            self.window._render()
            self.window.commit_selected()

        commit.assert_called_once_with(deletion_plan)
        confirmation.assert_not_called()
        self.on_change.assert_called_once_with()
        self.assertEqual(self.window.selected_action_ids, set())
        self.assertEqual(self.window.tree.get_children(), ("action-active-two",))
        self.assertIn("Deleted 2 Actions permanently", self.window.status_var.get())
        self.assertIn("External targets were unchanged", self.window.status_var.get())

    def test_filter_select_all_and_clear_keep_hidden_selection_explicit(self) -> None:
        first_plan = self._plan((self.active_one,))
        all_plan = self._plan((self.active_one, self.active_two, self.legacy))
        with patch(
            "context_palette.action_bulk_lifecycle_window.plan_bulk_action_deletion",
            side_effect=(first_plan, all_plan),
        ):
            self.window.filter_var.set("Active one")
            self.window.select_all_shown()
            self.window.filter_var.set("")
            self.window.select_all_shown()

        self.assertEqual(
            self.window.selected_action_ids,
            {"active-one", "active-two", "legacy-one"},
        )
        self.window.filter_var.set("Active one")
        self.assertIn("2 selected hidden", self.window.shown_var.get())
        self.window.clear_selection()
        self.assertEqual(self.window.selected_action_ids, set())
        self.assertTrue(self.window.commit_button.instate(["disabled"]))

    def test_failed_commit_refreshes_review_without_claiming_no_effect(self) -> None:
        plan = self._plan((self.active_one,))
        with (
            patch(
                "context_palette.action_bulk_lifecycle_window.plan_bulk_action_deletion",
                return_value=plan,
            ),
            patch(
                "context_palette.action_bulk_lifecycle_window.commit_bulk_action_deletion",
                side_effect=BulkActionLifecycleError("saved Actions changed"),
            ),
            patch(
                "context_palette.action_bulk_lifecycle_window.load_combined_stored_actions",
                return_value=(
                    list(self.actions),
                    {"active-one", "active-two", "legacy-one"},
                ),
            ),
            patch(
                "context_palette.action_bulk_lifecycle_window.messagebox.showerror"
            ) as error,
        ):
            self.window._toggle_iids(("action-active-one",))
            self.window.commit_selected()

        self.assertFalse(self.window.submitting)
        error.assert_called_once()
        self.assertEqual(
            error.call_args.args[0],
            "Action deletion did not complete as reviewed",
        )


if __name__ == "__main__":
    unittest.main()
