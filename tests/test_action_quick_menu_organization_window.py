from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from context_palette.action_quick_menu_organization import (
    ASSIGN_OPERATION,
    MOVE_BRANCH_OPERATION,
    QuickMenuOrganizationChange,
    QuickMenuOrganizationError,
    QuickMenuOrganizationPlan,
    QuickMenuOrganizationResult,
)
from context_palette.action_quick_menu_organization_window import (
    ActionQuickMenuOrganizationWindow,
)
from context_palette.actions import ACTIVE_STATE, ARCHIVED_STATE, Action


def action(
    action_id: str,
    title: str,
    *,
    action_type: str = "open_folder",
    state: str = ACTIVE_STATE,
    path: tuple[str, ...] = (),
) -> Action:
    value = (
        rf"D:\targets\{action_id}"
        if action_type == "open_folder"
        else "Summarize this text"
    )
    return Action(
        action_id,
        title,
        "General",
        action_type,
        value,
        state=state,
        quick_action_path=path,
    )


def organization_plan(
    changes: tuple[QuickMenuOrganizationChange, ...],
    *,
    operation: str = ASSIGN_OPERATION,
    requested_ids: tuple[str, ...] = (),
    source: tuple[str, ...] = (),
    destination: tuple[str, ...] = ("Archive",),
    matched_ids: tuple[str, ...] | None = None,
    destination_merged: bool = False,
) -> QuickMenuOrganizationPlan:
    affected = tuple(change.action_id for change in changes)
    matched = affected if matched_ids is None else matched_ids
    return QuickMenuOrganizationPlan(
        operation=operation,
        action_type="open_folder",
        shared_actions_path=Path("actions.json"),
        local_actions_path=Path("local_actions.json"),
        requested_action_ids=requested_ids,
        requested_source_prefix=source,
        source_prefix=source,
        requested_destination_path=destination,
        destination_path=destination,
        matched_action_ids=matched,
        changes=changes,
        affected_action_ids=affected,
        shared_action_count=sum(change.storage == "shared" for change in changes),
        local_action_count=sum(change.storage == "local" for change in changes),
        active_action_count=sum(change.state == ACTIVE_STATE for change in changes),
        files_to_write=len({change.storage for change in changes}),
        destination_merged=destination_merged,
        canonicalization_applied=False,
        fingerprint="sha256:reviewed",
    )


def change(
    source: Action,
    destination: tuple[str, ...],
    *,
    storage: str,
) -> QuickMenuOrganizationChange:
    return QuickMenuOrganizationChange(
        action_id=source.id,
        action_type=source.type,
        state=source.state,
        storage=storage,
        before_path=source.quick_action_path,
        after_path=destination,
        action=replace(source, quick_action_path=destination),
    )


class ActionQuickMenuOrganizationWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.geometry("1x1+0+0")
        self.root.update_idletasks()
        self.addCleanup(self.root.destroy)
        self.shared = action("shared-report", "Shared report", path=("Work",))
        self.local_archived = action(
            "local-archive",
            "Local folder",
            path=("Old",),
        )
        self.legacy_inactive = action(
            "legacy-inactive",
            "Legacy inactive",
            state=ARCHIVED_STATE,
            path=("Old",),
        )
        self.prompt = action(
            "prompt",
            "Prompt",
            action_type="ai_prompt",
            path=("Work",),
        )
        self.actions = (
            self.shared,
            self.local_archived,
            self.legacy_inactive,
            self.prompt,
        )
        self.on_change = Mock()
        self.on_refresh = Mock()
        self.windows: list[ActionQuickMenuOrganizationWindow] = []

    def tearDown(self) -> None:
        for organizer in reversed(self.windows):
            if organizer.window.winfo_exists():
                organizer.close()

    def organizer(
        self,
        *,
        current_path: tuple[str, ...] = (),
    ) -> ActionQuickMenuOrganizationWindow:
        with patch(
            "context_palette.action_quick_menu_organization_window."
            "configure_standard_window"
        ) as configure:
            organizer = ActionQuickMenuOrganizationWindow(
                self.root,
                group_label="Folders",
                action_type="open_folder",
                actions=self.actions,
                local_action_ids=(self.local_archived.id, self.legacy_inactive.id),
                current_path=current_path,
                shared_actions_path=Path("actions.json"),
                local_actions_path=Path("local_actions.json"),
                on_change=self.on_change,
                on_refresh=self.on_refresh,
            )
        configure.assert_called_once_with(organizer.window, self.root)
        self.windows.append(organizer)
        self.root.update()
        return organizer

    @staticmethod
    def iid_for(
        organizer: ActionQuickMenuOrganizationWindow,
        action_id: str,
    ) -> str:
        return next(
            iid
            for iid, candidate_id in organizer.action_id_by_iid.items()
            if candidate_id == action_id
        )

    def test_starts_unselected_and_shows_state_storage_placement_and_fixed_footer(
        self,
    ) -> None:
        organizer = self.organizer(current_path=("Work",))

        self.assertEqual(organizer.selected_action_ids, set())
        self.assertEqual(set(organizer.action_by_id), {"shared-report", "local-archive"})
        self.assertNotIn("legacy-inactive", organizer.action_by_id)
        shared_iid = self.iid_for(organizer, "shared-report")
        local_iid = self.iid_for(organizer, "local-archive")
        self.assertEqual(organizer.tree.set(shared_iid, "state"), ACTIVE_STATE)
        self.assertEqual(organizer.tree.set(shared_iid, "storage"), "Built-in")
        self.assertEqual(
            organizer.tree.set(shared_iid, "placement"),
            "Folders > Work",
        )
        self.assertEqual(
            organizer.tree.set(shared_iid, "action"),
            "Shared report [shared-report]",
        )
        self.assertEqual(organizer.tree.set(local_iid, "state"), ACTIVE_STATE)
        self.assertEqual(
            organizer.tree.set(local_iid, "storage"),
            "My configuration",
        )
        self.assertEqual(organizer.footer.grid_info()["row"], 7)
        self.assertEqual(
            organizer.branch_var.get(),
            "Current branch: Folders > Work",
        )
        self.assertIsNotNone(organizer.branch_button)
        self.assertIn(
            "No Action or external target is deleted",
            organizer.window.winfo_children()[0].winfo_children()[1].cget("text"),
        )

    def test_ctrl_a_is_scoped_to_table_and_find_keeps_text_select_all(self) -> None:
        organizer = self.organizer()
        organizer.search_var.set("report")
        self.root.update()

        self.assertEqual(organizer.window.bind("<Control-a>"), "")
        self.assertTrue(organizer.tree.bind("<Control-a>"))
        organizer.search_entry.focus_force()
        organizer.search_entry.selection_clear()
        organizer.search_entry.event_generate("<Control-a>")
        self.root.update()
        self.assertEqual(organizer.selected_action_ids, set())
        self.assertTrue(organizer.search_entry.selection_present())

        organizer.tree.focus_force()
        organizer.tree.event_generate("<Control-a>")
        self.root.update()
        self.assertEqual(organizer.selected_action_ids, {"shared-report"})

    def test_submenu_tasks_are_explicit_for_root_branch_and_depth_limit(self) -> None:
        root = self.organizer()
        root_labels = [
            root.submenu_tasks_menu.entrycget(index, "label")
            for index in range(root.submenu_tasks_menu.index(tk.END) + 1)
            if root.submenu_tasks_menu.type(index) != "separator"
        ]
        self.assertEqual(root_labels, ["New submenu…"])
        self.assertIsNone(root.branch_button)

        branch = self.organizer(current_path=("Work",))
        branch_labels = [
            branch.submenu_tasks_menu.entrycget(index, "label")
            for index in range(branch.submenu_tasks_menu.index(tk.END) + 1)
            if branch.submenu_tasks_menu.type(index) != "separator"
        ]
        self.assertEqual(
            branch_labels,
            [
                "New submenu here…",
                "Rename this submenu…",
                "Move this submenu…",
                "Remove this submenu…",
            ],
        )
        self.assertIs(branch.branch_button, branch.submenu_tasks_button)

        deepest = self.organizer(current_path=("One", "Two", "Three"))
        self.assertEqual(
            deepest.submenu_tasks_menu.entrycget(0, "state"),
            tk.DISABLED,
        )

    def test_submenu_tasks_status_and_footer_fit_at_150_percent(self) -> None:
        original_scaling = float(self.root.tk.call("tk", "scaling"))
        try:
            self.root.tk.call("tk", "scaling", original_scaling * 1.5)
            organizer = self.organizer(current_path=("Work",))
            organizer.window.geometry("700x480+0+0")
            self.root.update()

            window_right = (
                organizer.window.winfo_rootx() + organizer.window.winfo_width()
            )
            window_bottom = (
                organizer.window.winfo_rooty() + organizer.window.winfo_height()
            )
            self.assertLessEqual(
                organizer.submenu_tasks_button.winfo_rootx()
                + organizer.submenu_tasks_button.winfo_width(),
                window_right,
            )
            self.assertLessEqual(
                organizer.status_label.winfo_rooty()
                + organizer.status_label.winfo_height(),
                window_bottom,
            )
            self.assertLessEqual(
                organizer.footer.winfo_rooty() + organizer.footer.winfo_height(),
                window_bottom,
            )
        finally:
            self.root.tk.call("tk", "scaling", original_scaling)

    def test_create_submenu_requires_active_selection_and_reviews_assignment(self) -> None:
        organizer = self.organizer(current_path=("Work",))
        with patch(
            "context_palette.action_quick_menu_organization_window.messagebox.showinfo"
        ) as show_info, patch(
            "context_palette.action_quick_menu_organization_window."
            "QuickMenuSubmenuNameDialog"
        ) as name_dialog:
            organizer.create_submenu()
        show_info.assert_called_once()
        name_dialog.assert_not_called()

        organizer._toggle_action_id("local-archive")
        organizer._toggle_action_id("shared-report")
        planned_change = change(
            self.shared,
            ("Work", "Reports"),
            storage="shared",
        )
        plan = organization_plan(
            (planned_change,),
            requested_ids=("shared-report", "local-archive"),
            destination=("Work", "Reports"),
            matched_ids=("shared-report", "local-archive"),
        )
        captured: dict[str, object] = {}

        def open_name_dialog(_parent: tk.Misc, **kwargs: object) -> None:
            captured.update(kwargs)

        with patch(
            "context_palette.action_quick_menu_organization_window."
            "QuickMenuSubmenuNameDialog",
            side_effect=open_name_dialog,
        ), patch(
            "context_palette.action_quick_menu_organization_window."
            "plan_quick_menu_assignment",
            return_value=plan,
        ) as planner:
            organizer.create_submenu()
            captured["on_submit"]("Reports")  # type: ignore[operator]

        planner.assert_called_once_with(
            ("shared-report", "local-archive"),
            ("Work", "Reports"),
            shared_actions_path=Path("actions.json"),
            local_actions_path=Path("local_actions.json"),
        )
        self.assertEqual(organizer.review_intent, "create_submenu")
        self.assertEqual(
            organizer.move_button.cget("text"),
            "Create submenu with 1 Action",
        )
        detail = organizer.detail.get("1.0", "end-1c")
        self.assertIn("Create submenu: Folders > Work > Reports", detail)
        self.assertIn("not an independent empty menu record", detail)

    def test_remove_selected_direct_actions_reviews_one_level_promotion(self) -> None:
        organizer = self.organizer(current_path=("Work",))
        organizer._toggle_action_id("shared-report")
        planned_change = change(self.shared, (), storage="shared")
        plan = organization_plan(
            (planned_change,),
            requested_ids=("shared-report",),
            destination=(),
            matched_ids=("shared-report",),
        )

        with patch(
            "context_palette.action_quick_menu_organization_window."
            "plan_quick_menu_assignment",
            return_value=plan,
        ) as planner:
            organizer.remove_selected_from_current_submenu()

        planner.assert_called_once_with(
            ("shared-report",),
            (),
            shared_actions_path=Path("actions.json"),
            local_actions_path=Path("local_actions.json"),
        )
        self.assertEqual(organizer.review_intent, "remove_actions")
        self.assertEqual(
            organizer.move_button.cget("text"),
            "Remove 1 Action from submenu",
        )
        detail = organizer.detail.get("1.0", "end-1c")
        self.assertIn("Remove from submenu: Folders > Work", detail)
        self.assertIn("Move to parent: Folders menu root", detail)
        self.assertIn("external targets unchanged", detail)
        self.assertIn("Shared report [shared-report; Active, Built-in]", detail)

    def test_remove_selected_rejects_fresh_plan_from_another_submenu(self) -> None:
        organizer = self.organizer(current_path=("Work",))
        organizer._toggle_action_id("shared-report")
        moved_elsewhere = replace(
            self.shared,
            quick_action_path=("Elsewhere",),
        )
        stale_plan = organization_plan(
            (change(moved_elsewhere, (), storage="shared"),),
            requested_ids=("shared-report",),
            destination=(),
            matched_ids=("shared-report",),
        )

        with patch(
            "context_palette.action_quick_menu_organization_window."
            "plan_quick_menu_assignment",
            return_value=stale_plan,
        ), patch(
            "context_palette.action_quick_menu_organization_window.messagebox.showerror"
        ) as show_error:
            organizer.remove_selected_from_current_submenu()

        self.assertIsNone(organizer.plan)
        self.assertTrue(organizer.review_stale)
        self.assertEqual(organizer.selected_action_ids, set())
        self.assertTrue(organizer.move_button.instate(["disabled"]))
        self.assertIn("Close and reopen", organizer.status_var.get())
        self.on_refresh.assert_called_once_with()
        self.on_change.assert_not_called()
        show_error.assert_called_once()

    def test_remove_selected_rejects_actions_outside_current_submenu(self) -> None:
        organizer = self.organizer(current_path=("Work",))
        organizer._toggle_action_id("local-archive")

        with patch(
            "context_palette.action_quick_menu_organization_window.messagebox.showinfo"
        ) as show_info, patch(
            "context_palette.action_quick_menu_organization_window."
            "plan_quick_menu_assignment"
        ) as planner:
            organizer.remove_selected_from_current_submenu()

        show_info.assert_called_once()
        planner.assert_not_called()
        self.assertIn("direct members", organizer.status_var.get())

    def test_exact_action_id_is_preselected_for_leaf_removal(self) -> None:
        duplicate = replace(
            self.shared,
            id="shared-report-duplicate",
            title=self.shared.title,
        )
        organizer = self.organizer(current_path=("Work",))
        organizer.actions = (self.shared, duplicate, self.local_archived, self.prompt)
        organizer.candidates = (self.shared, duplicate, self.local_archived)
        organizer.action_by_id = {
            action.id: action for action in organizer.candidates
        }

        with patch.object(
            organizer,
            "remove_selected_from_current_submenu",
        ) as remove:
            organizer.review_action_removal(duplicate.id)

        self.assertEqual(organizer.selected_action_ids, {duplicate.id})
        remove.assert_called_once_with()

    def test_rename_and_remove_submenu_build_distinct_reviewed_effects(self) -> None:
        organizer = self.organizer(current_path=("Work",))
        rename_change = change(self.shared, ("Archive",), storage="shared")
        rename_plan = organization_plan(
            (rename_change,),
            operation=MOVE_BRANCH_OPERATION,
            source=("Work",),
            destination=("Archive",),
            matched_ids=("shared-report",),
        )
        captured: dict[str, object] = {}

        def open_name_dialog(_parent: tk.Misc, **kwargs: object) -> None:
            captured.update(kwargs)

        with patch(
            "context_palette.action_quick_menu_organization_window."
            "QuickMenuSubmenuNameDialog",
            side_effect=open_name_dialog,
        ), patch(
            "context_palette.action_quick_menu_organization_window."
            "plan_quick_menu_branch_move",
            return_value=rename_plan,
        ) as planner:
            organizer.rename_submenu()
            captured["on_submit"]("Archive")  # type: ignore[operator]

        planner.assert_called_once_with(
            "open_folder",
            ("Work",),
            ("Archive",),
            shared_actions_path=Path("actions.json"),
            local_actions_path=Path("local_actions.json"),
        )
        self.assertEqual(
            organizer.move_button.cget("text"),
            "Rename submenu for 1 Action",
        )
        self.assertIn(
            "Rename submenu: Folders > Work",
            organizer.detail.get("1.0", "end-1c"),
        )

        remove_plan = organization_plan(
            (change(self.shared, (), storage="shared"),),
            operation=MOVE_BRANCH_OPERATION,
            source=("Work",),
            destination=(),
            matched_ids=("shared-report",),
        )
        with patch(
            "context_palette.action_quick_menu_organization_window."
            "plan_quick_menu_branch_move",
            return_value=remove_plan,
        ) as planner:
            organizer.remove_submenu()

        planner.assert_called_once_with(
            "open_folder",
            ("Work",),
            (),
            shared_actions_path=Path("actions.json"),
            local_actions_path=Path("local_actions.json"),
        )
        self.assertEqual(
            organizer.move_button.cget("text"),
            "Remove submenu; keep 1 Action",
        )
        detail = organizer.detail.get("1.0", "end-1c")
        self.assertIn("Remove submenu: Folders > Work", detail)
        self.assertIn("Promote contents to: Folders menu root", detail)

        merged_remove = replace(remove_plan, destination_merged=True)
        organizer.plan = merged_remove
        organizer.review_intent = "remove_submenu"
        organizer._render_review()
        self.assertIn(
            "matching destination branches will merge",
            organizer.detail.get("1.0", "end-1c"),
        )

    def test_destination_chooser_builds_exact_assignment_review(self) -> None:
        organizer = self.organizer()
        organizer._toggle_action_id("shared-report")
        organizer._toggle_action_id("local-archive")
        changes = (
            change(self.shared, ("Archive",), storage="shared"),
            change(self.local_archived, ("Archive",), storage="local"),
        )
        plan = organization_plan(
            changes,
            requested_ids=("shared-report", "local-archive"),
        )

        chooser_args: dict[str, object] = {}

        def open_chooser(parent: tk.Misc, **kwargs: object) -> None:
            chooser_args["parent"] = parent
            chooser_args.update(kwargs)

        with patch(
            "context_palette.action_quick_menu_organization_window."
            "QuickMenuPathDialog",
            side_effect=open_chooser,
        ) as chooser, patch(
            "context_palette.action_quick_menu_organization_window."
            "plan_quick_menu_assignment",
            return_value=plan,
        ) as planner:
            organizer.choose_assignment_destination()
            chooser_args["on_select"](("Archive",))  # type: ignore[operator]

        chooser.assert_called_once()
        self.assertIs(chooser_args["parent"], organizer.window)
        self.assertEqual(chooser_args["action_type"], "open_folder")
        self.assertEqual(chooser_args["actions"], organizer.actions)
        planner.assert_called_once_with(
            ("shared-report", "local-archive"),
            ("Archive",),
            shared_actions_path=Path("actions.json"),
            local_actions_path=Path("local_actions.json"),
        )
        self.assertEqual(organizer.move_button.cget("text"), "Move 2 Actions")
        self.assertFalse(organizer.move_button.instate(["disabled"]))
        detail = organizer.detail.get("1.0", "end-1c")
        self.assertIn(
            "Built-in 1 · My configuration 1 · Active 2",
            detail,
        )
        self.assertIn("tracked by Git", detail)
        self.assertIn("No Action, folder, password, prompt", detail)

    def test_assignment_rejects_action_that_changed_automatic_menu_type(self) -> None:
        organizer = self.organizer()
        organizer._toggle_action_id("shared-report")
        mismatched = replace(
            organization_plan(
                (change(self.shared, ("Archive",), storage="shared"),),
                requested_ids=("shared-report",),
            ),
            action_type="ai_prompt",
        )

        with patch(
            "context_palette.action_quick_menu_organization_window."
            "plan_quick_menu_assignment",
            return_value=mismatched,
        ), patch(
            "context_palette.action_quick_menu_organization_window.messagebox.showerror"
        ) as show_error:
            organizer._assignment_destination_chosen(("Archive",))

        self.assertIsNone(organizer.plan)
        self.assertTrue(organizer.review_stale)
        self.assertTrue(organizer.move_button.instate(["disabled"]))
        self.assertIn("Close and reopen", organizer.status_var.get())
        self.on_refresh.assert_called_once_with()
        self.on_change.assert_not_called()
        show_error.assert_called_once()

    def test_no_effect_review_is_explicit_and_cannot_commit(self) -> None:
        organizer = self.organizer()
        organizer._toggle_action_id("shared-report")
        no_effect = organization_plan(
            (),
            requested_ids=("shared-report",),
            destination=("Work",),
            matched_ids=("shared-report",),
        )
        with patch(
            "context_palette.action_quick_menu_organization_window."
            "plan_quick_menu_assignment",
            return_value=no_effect,
        ):
            organizer._assignment_destination_chosen(("Work",))

        self.assertEqual(organizer.move_button.cget("text"), "Move 0 Actions")
        self.assertTrue(organizer.move_button.instate(["disabled"]))
        self.assertIn(
            "Nothing will change",
            organizer.detail.get("1.0", "end-1c"),
        )
        with patch(
            "context_palette.action_quick_menu_organization_window."
            "commit_quick_menu_organization"
        ) as commit:
            organizer.commit_reviewed_plan()
        commit.assert_not_called()

    def test_branch_move_reviews_active_descendants_and_leaves_legacy_inactive_alone(self) -> None:
        organizer = self.organizer(current_path=("Work",))
        local_in_branch = replace(
            self.local_archived,
            quick_action_path=("Work", "Old"),
        )
        legacy_in_branch = replace(
            self.legacy_inactive,
            quick_action_path=("Work", "Legacy"),
        )
        organizer.actions = (self.shared, local_in_branch, legacy_in_branch, self.prompt)
        organizer.candidates = (self.shared, local_in_branch)
        changes = (
            change(self.shared, ("Archive", "Work"), storage="shared"),
            change(
                local_in_branch,
                ("Archive", "Work", "Old"),
                storage="local",
            ),
        )
        plan = organization_plan(
            changes,
            operation=MOVE_BRANCH_OPERATION,
            source=("Work",),
            destination=("Archive", "Work"),
            matched_ids=("shared-report", "local-archive"),
        )
        result = QuickMenuOrganizationResult(
            affected_action_ids=plan.affected_action_ids,
            shared_action_count=1,
            local_action_count=1,
            active_action_count=2,
            files_written=2,
            updated_actions=tuple(item.action for item in changes),
        )
        chooser_callback: list[object] = []
        chooser_options: list[dict[str, object]] = []

        def open_chooser(_parent: tk.Misc, **kwargs: object) -> None:
            chooser_options.append(kwargs)
            chooser_callback.append(kwargs["on_select"])

        with patch(
            "context_palette.action_quick_menu_organization_window."
            "QuickMenuPathDialog",
            side_effect=open_chooser,
        ), patch(
            "context_palette.action_quick_menu_organization_window."
            "plan_quick_menu_branch_move",
            return_value=plan,
        ) as planner:
            organizer.choose_branch_destination()
            chooser_callback[0](("Archive",))  # type: ignore[operator]

        planner.assert_called_once_with(
            "open_folder",
            ("Work",),
            ("Archive", "Work"),
            shared_actions_path=Path("actions.json"),
            local_actions_path=Path("local_actions.json"),
        )
        self.assertEqual(chooser_options[0]["current_path"], ())
        self.assertEqual(chooser_options[0]["use_label"], "Use this parent")
        self.assertEqual(chooser_options[0]["dialog_title"], "Move Work")
        detail = organizer.detail.get("1.0", "end-1c")
        self.assertNotIn("Archived descendants", detail)
        self.assertIn("No Action, folder, password, prompt", detail)

        with patch(
            "context_palette.action_quick_menu_organization_window."
            "commit_quick_menu_organization",
            return_value=result,
        ) as commit, patch(
            "context_palette.action_quick_menu_organization_window.messagebox.askyesno",
            create=True,
        ) as confirmation:
            organizer.commit_reviewed_plan()

        commit.assert_called_once_with(plan)
        confirmation.assert_not_called()
        self.on_change.assert_called_once_with()
        self.assertEqual(
            organizer.branch_var.get(),
            "Current branch: Folders > Archive > Work",
        )
        self.assertIn(
            "Built-in 1 · My configuration 1 · Active 2",
            organizer.status_var.get(),
        )
        self.assertTrue(organizer.window.winfo_exists())

    def test_stale_commit_keeps_window_open_and_requires_fresh_organizer(self) -> None:
        organizer = self.organizer()
        organizer.plan = organization_plan(
            (change(self.shared, ("Archive",), storage="shared"),),
            requested_ids=("shared-report",),
        )
        organizer.selected_action_ids.add("shared-report")
        organizer._render_actions()
        organizer._render_review()
        failure = QuickMenuOrganizationError("Actions changed after review")

        with patch(
            "context_palette.action_quick_menu_organization_window."
            "commit_quick_menu_organization",
            side_effect=failure,
        ), patch(
            "context_palette.action_quick_menu_organization_window.messagebox.showerror"
        ) as show_error:
            organizer.commit_reviewed_plan()

        self.assertTrue(organizer.window.winfo_exists())
        self.assertTrue(organizer.review_stale)
        self.assertFalse(organizer.effects_unknown)
        self.assertTrue(organizer.destination_button.instate(["disabled"]))
        self.assertIn("Close and reopen", organizer.status_var.get())
        show_error.assert_called_once()
        self.on_refresh.assert_called_once_with()
        self.on_change.assert_not_called()

    def test_rollback_outcomes_are_distinct_and_keep_dialog_open(self) -> None:
        organizer = self.organizer()
        organizer.plan = organization_plan(
            (change(self.shared, ("Archive",), storage="shared"),),
            requested_ids=("shared-report",),
        )
        organizer.selected_action_ids.add("shared-report")
        organizer.destination_path = ("Archive",)
        organizer._render_review()
        restored = QuickMenuOrganizationError(
            "all attempted Action-file changes were restored",
            rollback_completed=True,
        )
        with patch(
            "context_palette.action_quick_menu_organization_window."
            "commit_quick_menu_organization",
            side_effect=restored,
        ), patch(
            "context_palette.action_quick_menu_organization_window.messagebox.showerror"
        ):
            organizer.commit_reviewed_plan()

        self.assertTrue(organizer.window.winfo_exists())
        self.assertFalse(organizer.review_stale)
        self.assertFalse(organizer.effects_unknown)
        self.assertFalse(organizer.destination_button.instate(["disabled"]))
        self.assertIn("No Actions were moved", organizer.status_var.get())

        organizer.plan = organization_plan(
            (change(self.shared, ("Archive",), storage="shared"),),
            requested_ids=("shared-report",),
        )
        organizer._render_review()
        unknown = QuickMenuOrganizationError(
            "rollback was incomplete",
            rollback_completed=False,
        )
        with patch(
            "context_palette.action_quick_menu_organization_window."
            "commit_quick_menu_organization",
            side_effect=unknown,
        ), patch(
            "context_palette.action_quick_menu_organization_window.messagebox.showerror"
        ):
            organizer.commit_reviewed_plan()

        self.assertTrue(organizer.window.winfo_exists())
        self.assertTrue(organizer.effects_unknown)
        self.assertTrue(organizer.move_button.instate(["disabled"]))
        self.assertIn("backup", organizer.status_var.get())
        self.assertIn("Diagnostics", organizer.status_var.get())
        self.on_refresh.assert_called_once_with()

    def test_moving_branch_to_menu_root_removes_branch_command(self) -> None:
        organizer = self.organizer(current_path=("Work",))
        planned_change = change(self.shared, (), storage="shared")
        plan = organization_plan(
            (planned_change,),
            operation=MOVE_BRANCH_OPERATION,
            source=("Work",),
            destination=(),
            matched_ids=("shared-report",),
        )
        result = QuickMenuOrganizationResult(
            affected_action_ids=("shared-report",),
            shared_action_count=1,
            local_action_count=0,
            active_action_count=1,
            files_written=1,
            updated_actions=(planned_change.action,),
        )
        organizer.plan = plan

        with patch(
            "context_palette.action_quick_menu_organization_window."
            "commit_quick_menu_organization",
            return_value=result,
        ):
            organizer.commit_reviewed_plan()

        self.assertEqual(organizer.current_path, ())
        self.assertEqual(
            organizer.branch_var.get(),
            "Current branch: Folders menu root",
        )
        self.assertIsNone(organizer.branch_button)

    def test_moving_last_active_action_out_resets_missing_current_branch(self) -> None:
        organizer = self.organizer(current_path=("Work",))
        planned_change = change(self.shared, ("Archive",), storage="shared")
        plan = organization_plan(
            (planned_change,),
            requested_ids=("shared-report",),
            destination=("Archive",),
            matched_ids=("shared-report",),
        )
        result = QuickMenuOrganizationResult(
            affected_action_ids=("shared-report",),
            shared_action_count=1,
            local_action_count=0,
            active_action_count=1,
            files_written=1,
            updated_actions=(planned_change.action,),
        )
        organizer.plan = plan

        with patch(
            "context_palette.action_quick_menu_organization_window."
            "commit_quick_menu_organization",
            return_value=result,
        ):
            organizer.commit_reviewed_plan()

        self.assertEqual(organizer.current_path, ())
        self.assertEqual(
            organizer.branch_var.get(),
            "Current branch: Folders menu root",
        )
        self.assertIsNone(organizer.branch_button)
        self.assertIn("previous branch no longer has an Active Action", organizer.status_var.get())


if __name__ == "__main__":
    unittest.main()
