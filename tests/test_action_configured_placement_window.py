from __future__ import annotations

from pathlib import Path
from dataclasses import replace
import sys
import tkinter as tk
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.action_configured_placement import (
    ConfiguredActionPlacementInventory,
    ConfiguredActionPlacementPlan,
    ConfiguredActionPlacementResult,
    ConfiguredPlacementError,
    ConfiguredPlacementKey,
    ConfiguredPlacementLocation,
)
from context_palette.action_configured_placement_window import (
    ActionConfiguredPlacementWindow,
    automatic_quick_menu_placement,
)
from context_palette.actions import Action


SHARED_ACTIONS = Path("shared-actions.json")
LOCAL_ACTIONS = Path("local-actions.json")
SHARED_MENUS = Path("shared-menus.json")
LOCAL_MENUS = Path("local-menus.json")

LOCAL_ROOT = ConfiguredPlacementKey("local", "personal")
LOCAL_BRANCH = ConfiguredPlacementKey("local", "personal", ("reports",))
SHARED_ROOT = ConfiguredPlacementKey("shared", "standard")
LOCAL_ONLY_REASON = (
    "A My configuration Action cannot be placed in Built-in Quick actions. "
    "Choose a My configuration menu instead."
)


def _folder_action() -> Action:
    return Action(
        "folder-action",
        "Reports folder",
        "General",
        "open_folder",
        str(ROOT),
        quick_action_path=("Work", "Reports"),
    )


def _location(
    key: ConfiguredPlacementKey,
    path: tuple[str, ...],
    *,
    assigned: bool = False,
    assignable: bool = True,
    unavailable_reason: str = "",
    action_targets: int = 0,
    work_items: int = 0,
    children: int = 0,
) -> ConfiguredPlacementLocation:
    return ConfiguredPlacementLocation(
        key=key,
        menu_path=path,
        assigned=assigned,
        assignable=assignable,
        unavailable_reason=unavailable_reason,
        action_target_count=action_targets,
        work_item_target_count=work_items,
        child_menu_count=children,
        reference_mode="mixed" if work_items else "actions" if action_targets else "empty",
    )


def _inventory(
    current: tuple[ConfiguredPlacementKey, ...] = (LOCAL_ROOT,),
) -> ConfiguredActionPlacementInventory:
    return ConfiguredActionPlacementInventory(
        action_id="folder-action",
        action_title="Reports folder",
        action_state="Active",
        action_storage="local",
        locations=(
            _location(
                LOCAL_ROOT,
                ("Personal tools",),
                assigned=LOCAL_ROOT in current,
                action_targets=1 if LOCAL_ROOT in current else 0,
                children=1,
            ),
            _location(
                LOCAL_BRANCH,
                ("Personal tools", "Reports"),
                assigned=LOCAL_BRANCH in current,
                action_targets=1 if LOCAL_BRANCH in current else 0,
                work_items=1,
            ),
            _location(
                SHARED_ROOT,
                ("Standard",),
                assignable=False,
                unavailable_reason=LOCAL_ONLY_REASON,
                action_targets=4,
                children=3,
            ),
        ),
        current_locations=current,
    )


def _plan(
    desired: tuple[ConfiguredPlacementKey, ...],
    *,
    current: tuple[ConfiguredPlacementKey, ...] = (LOCAL_ROOT,),
) -> ConfiguredActionPlacementPlan:
    inventory = _inventory(current)
    additions = tuple(key for key in desired if key not in current)
    removals = tuple(key for key in current if key not in desired)
    return ConfiguredActionPlacementPlan(
        action_id="folder-action",
        action_title="Reports folder",
        action_storage="local",
        shared_actions_path=SHARED_ACTIONS,
        local_actions_path=LOCAL_ACTIONS,
        shared_command_surface_path=SHARED_MENUS,
        local_command_surface_path=LOCAL_MENUS,
        requested_desired_locations=desired,
        desired_locations=desired,
        current_locations=current,
        locations=inventory.locations,
        additions=additions,
        removals=removals,
        items_pruned=1 if removals else 0,
        shared_reference_changes=0,
        local_reference_changes=len(additions) + len(removals),
        shared_items_pruned=0,
        local_items_pruned=1 if removals else 0,
        files_to_write=1 if additions or removals else 0,
        fingerprint="reviewed",
    )


class AutomaticPlacementSummaryTests(unittest.TestCase):
    def test_summary_uses_fixed_root_and_action_relative_path(self) -> None:
        self.assertEqual(
            automatic_quick_menu_placement(_folder_action()),
            "Folders > Work > Reports",
        )
        prompt = Action("prompt", "Prompt", "General", "ai_prompt", "Explain")
        self.assertEqual(
            automatic_quick_menu_placement(prompt),
            "Prompts > Menu root",
        )
        ordinary = Action("copy", "Copy", "General", "copy_text", "Text")
        self.assertEqual(
            automatic_quick_menu_placement(ordinary),
            "None for this Action type",
        )


class ConfiguredPlacementWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.on_change = Mock()
        self.on_refresh = Mock()

    def tearDown(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()
        self.root.destroy()

    def _window(
        self,
        inventory_mock: Mock,
        plan_mock: Mock,
    ) -> ActionConfiguredPlacementWindow:
        window = ActionConfiguredPlacementWindow(
            self.root,
            action=_folder_action(),
            shared_actions_path=SHARED_ACTIONS,
            local_actions_path=LOCAL_ACTIONS,
            shared_command_surface_path=SHARED_MENUS,
            local_command_surface_path=LOCAL_MENUS,
            on_change=self.on_change,
            on_refresh=self.on_refresh,
        )
        self.root.update()
        return window

    def test_window_lists_every_location_and_blocks_built_in_for_personal_action(
        self,
    ) -> None:
        inventory = _inventory()
        with (
            patch(
                "context_palette.action_configured_placement_window."
                "configured_action_placement_inventory",
                return_value=inventory,
            ) as inventory_call,
            patch(
                "context_palette.action_configured_placement_window."
                "plan_configured_action_placements",
                side_effect=lambda _action_id, desired, **_kwargs: _plan(tuple(desired)),
            ) as plan_call,
        ):
            window = self._window(inventory_call, plan_call)

        self.assertEqual(window.automatic_placement_var.get(), "Folders > Work > Reports")
        self.assertEqual(window.action_storage_var.get(), "My configuration")
        self.assertEqual(window.count_var.get(), "3 of 3 locations")
        self.assertEqual(window.footer.grid_info()["row"], 7)
        self.assertEqual(window.status_label.grid_info()["row"], 6)
        shared_values = window.tree.item(window.iid_by_key[SHARED_ROOT], "values")
        self.assertEqual(shared_values[0], "—")
        self.assertIn("My configuration Action", shared_values[3])
        inventory_call.assert_called_once_with(
            "folder-action",
            shared_actions_path=SHARED_ACTIONS,
            local_actions_path=LOCAL_ACTIONS,
            shared_command_surface_path=SHARED_MENUS,
            local_command_surface_path=LOCAL_MENUS,
        )
        self.assertEqual(plan_call.call_args.args[1], (LOCAL_ROOT,))

        window.search_var.set("built-in")
        self.root.update_idletasks()
        self.assertEqual(set(window.iid_by_key), {SHARED_ROOT})

    def test_toggles_review_add_remove_pruning_and_effect_label(self) -> None:
        inventory = _inventory()
        with (
            patch(
                "context_palette.action_configured_placement_window."
                "configured_action_placement_inventory",
                return_value=inventory,
            ),
            patch(
                "context_palette.action_configured_placement_window."
                "plan_configured_action_placements",
                side_effect=lambda _action_id, desired, **_kwargs: _plan(tuple(desired)),
            ) as plan_call,
        ):
            window = self._window(Mock(), plan_call)
            window.tree.selection_set(window.iid_by_key[LOCAL_ROOT])
            window.toggle_selected()
            window.tree.selection_set(window.iid_by_key[LOCAL_BRANCH])
            window.toggle_selected()

            self.assertEqual(
                str(window.apply_button["text"]),
                "Apply 2 placement changes",
            )
            self.assertEqual(str(window.apply_button["state"]), "normal")
            detail = window.detail.get("1.0", "end-1c")
            self.assertIn("Add (1):", detail)
            self.assertIn("Personal tools > Reports", detail)
            self.assertIn("Remove (1):", detail)
            self.assertIn("Empty Quick-action items/branches pruned: 1", detail)
            self.assertIn("Configuration files to write: 1", detail)

            calls_before = plan_call.call_count
            window.tree.selection_set(window.iid_by_key[SHARED_ROOT])
            window.toggle_selected()
            self.assertEqual(plan_call.call_count, calls_before)
            self.assertIn("cannot be placed", window.status_var.get())

    def test_success_applies_without_second_confirmation_and_refreshes_inventory(
        self,
    ) -> None:
        initial = _inventory()
        refreshed = _inventory((LOCAL_ROOT, LOCAL_BRANCH))
        with (
            patch(
                "context_palette.action_configured_placement_window."
                "configured_action_placement_inventory",
                side_effect=(initial, refreshed),
            ),
            patch(
                "context_palette.action_configured_placement_window."
                "plan_configured_action_placements",
                side_effect=lambda _action_id, desired, **_kwargs: _plan(
                    tuple(desired),
                    current=(
                        (LOCAL_ROOT, LOCAL_BRANCH)
                        if desired == (LOCAL_ROOT, LOCAL_BRANCH)
                        and self.on_change.called
                        else (LOCAL_ROOT,)
                    ),
                ),
            ),
            patch(
                "context_palette.action_configured_placement_window."
                "commit_configured_action_placements",
                return_value=ConfiguredActionPlacementResult(
                    action_id="folder-action",
                    current_locations=(LOCAL_ROOT, LOCAL_BRANCH),
                    additions=(LOCAL_BRANCH,),
                    removals=(),
                    items_pruned=0,
                    files_written=1,
                ),
            ) as commit,
        ):
            window = self._window(Mock(), Mock())
            window.tree.selection_set(window.iid_by_key[LOCAL_BRANCH])
            window.toggle_selected()
            reviewed = window.plan

            window.apply_changes()

        commit.assert_called_once_with(reviewed)
        self.on_change.assert_called_once_with()
        self.on_refresh.assert_not_called()
        self.assertIn("Applied 1 configured placement change", window.status_var.get())
        self.assertEqual(str(window.apply_button["text"]), "No changes")
        self.assertEqual(str(window.apply_button["state"]), "disabled")

    def test_review_warns_when_built_in_quick_actions_will_change(self) -> None:
        inventory = _inventory()
        shared_plan = replace(
            _plan((LOCAL_ROOT,)),
            shared_reference_changes=1,
            files_to_write=1,
        )
        with (
            patch(
                "context_palette.action_configured_placement_window."
                "configured_action_placement_inventory",
                return_value=inventory,
            ),
            patch(
                "context_palette.action_configured_placement_window."
                "plan_configured_action_placements",
                return_value=shared_plan,
            ),
        ):
            window = self._window(Mock(), Mock())

        detail = window.detail.get("1.0", "end-1c")
        self.assertIn("Built-in Quick-action changes are Git-tracked", detail)
        self.assertIn("other computers after commit and pull", detail)

    def test_stale_or_rollback_unknown_locks_review_and_requests_refresh(self) -> None:
        for rollback_completed in (None, False):
            with self.subTest(rollback_completed=rollback_completed):
                self.on_refresh.reset_mock()
                with (
                    patch(
                        "context_palette.action_configured_placement_window."
                        "configured_action_placement_inventory",
                        return_value=_inventory(),
                    ),
                    patch(
                        "context_palette.action_configured_placement_window."
                        "plan_configured_action_placements",
                        side_effect=lambda _action_id, desired, **_kwargs: _plan(
                            tuple(desired)
                        ),
                    ),
                    patch(
                        "context_palette.action_configured_placement_window."
                        "commit_configured_action_placements",
                        side_effect=ConfiguredPlacementError(
                            "Configuration changed after review.",
                            rollback_completed=rollback_completed,
                        ),
                    ),
                    patch(
                        "context_palette.action_configured_placement_window."
                        "messagebox.showerror"
                    ),
                ):
                    window = self._window(Mock(), Mock())
                    window.tree.selection_set(window.iid_by_key[LOCAL_BRANCH])
                    window.toggle_selected()
                    window.apply_changes()

                self.assertTrue(window.review_locked)
                self.assertIsNone(window.plan)
                self.assertEqual(str(window.apply_button["state"]), "disabled")
                self.assertIn("close and reopen", window.status_var.get())
                self.on_refresh.assert_called_once_with()
                window.close()

    def test_replan_locks_when_the_visible_inventory_changed_elsewhere(self) -> None:
        initial = _inventory()
        drifted_plan = _plan(
            (LOCAL_ROOT, LOCAL_BRANCH),
            current=(LOCAL_BRANCH,),
        )
        with (
            patch(
                "context_palette.action_configured_placement_window."
                "configured_action_placement_inventory",
                return_value=initial,
            ),
            patch(
                "context_palette.action_configured_placement_window."
                "plan_configured_action_placements",
                side_effect=(
                    _plan((LOCAL_ROOT,)),
                    drifted_plan,
                ),
            ),
        ):
            window = self._window(Mock(), Mock())
            window.tree.selection_set(window.iid_by_key[LOCAL_BRANCH])
            window.toggle_selected()

        self.assertTrue(window.review_locked)
        self.assertIsNone(window.plan)
        self.assertEqual(str(window.apply_button["state"]), "disabled")
        self.assertIn("changed while this window was open", window.status_var.get())
        self.on_refresh.assert_called_once_with()

    def test_fixed_status_and_footer_fit_at_supported_scaling(self) -> None:
        original_scaling = float(self.root.tk.call("tk", "scaling"))
        try:
            self.root.geometry("320x240+0+0")
            self.root.deiconify()
            for scaling in (1.0, 1.25, 1.5):
                with self.subTest(scaling=scaling):
                    self.root.tk.call("tk", "scaling", scaling)
                    with (
                        patch(
                            "context_palette.action_configured_placement_window."
                            "configured_action_placement_inventory",
                            return_value=_inventory(),
                        ),
                        patch(
                            "context_palette.action_configured_placement_window."
                            "plan_configured_action_placements",
                            side_effect=lambda _action_id, desired, **_kwargs: _plan(
                                tuple(desired)
                            ),
                        ),
                    ):
                        window = self._window(Mock(), Mock())
                    window.window.geometry("700x480+20+20")
                    self.root.update()

                    bottom = window.window.winfo_rooty() + window.window.winfo_height()
                    for widget in (
                        window.status_label,
                        window.footer,
                        window.apply_button,
                    ):
                        self.assertTrue(widget.winfo_ismapped())
                        self.assertLessEqual(
                            widget.winfo_rooty() + widget.winfo_height(),
                            bottom,
                        )
                    window.close()
        finally:
            self.root.tk.call("tk", "scaling", original_scaling)


if __name__ == "__main__":
    unittest.main()
