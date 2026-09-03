from __future__ import annotations

from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.actions import Action
from context_palette.action_configured_placement import (
    ConfiguredPlacementKey,
    ConfiguredPlacementLocation,
)
from context_palette.quick_menu_path_dialog import (
    QuickMenuPathDialog,
    QuickMenuPathNode,
    QuickMenuPlacementSelection,
    QuickMenuSubmenuNameDialog,
    quick_menu_path_tree,
    quick_menu_root_label,
)


def _action(
    action_id: str,
    action_type: str,
    path: tuple[str, ...] = (),
    *,
    state: str = "Active",
) -> Action:
    value = {
        "open_folder": str(ROOT),
        "paste_credential": "Example credential",
        "ai_prompt": "Summarize this text",
    }[action_type]
    return Action(
        action_id,
        action_id.replace("-", " ").title(),
        "General",
        action_type,
        value,
        state=state,
        quick_action_path=path,
    )


def _nodes_by_path(root: QuickMenuPathNode) -> dict[tuple[str, ...], QuickMenuPathNode]:
    nodes: dict[tuple[str, ...], QuickMenuPathNode] = {}

    def visit(node: QuickMenuPathNode) -> None:
        nodes[node.path] = node
        for child in node.children:
            visit(child)

    visit(root)
    return nodes


def _descendants(widget: tk.Misc) -> list[tk.Misc]:
    descendants: list[tk.Misc] = []
    for child in widget.winfo_children():
        descendants.append(child)
        descendants.extend(_descendants(child))
    return descendants


def _configured_location(
    storage: str,
    group_id: str,
    menu_path: tuple[str, ...],
    *,
    item_id_path: tuple[str, ...] = (),
    assigned: bool = False,
    assignable: bool = True,
    unavailable_reason: str = "",
) -> ConfiguredPlacementLocation:
    return ConfiguredPlacementLocation(
        key=ConfiguredPlacementKey(storage, group_id, item_id_path),
        menu_path=menu_path,
        assigned=assigned,
        assignable=assignable,
        unavailable_reason=unavailable_reason,
        action_target_count=1 if assigned else 0,
        work_item_target_count=0,
        child_menu_count=0,
        reference_mode="actions" if assigned else "empty",
    )


class QuickMenuPathModelTests(unittest.TestCase):
    def test_fixed_root_labels_are_derived_from_action_type(self) -> None:
        self.assertEqual(quick_menu_root_label("paste_credential"), "Passwords")
        self.assertEqual(quick_menu_root_label("open_folder"), "Folders")
        self.assertEqual(quick_menu_root_label("ai_prompt"), "Prompts")
        with self.assertRaisesRegex(ValueError, "Unsupported automatic"):
            quick_menu_root_label("copy_text")

    def test_tree_counts_only_active_same_type_actions_and_preserves_order(self) -> None:
        tree = quick_menu_path_tree(
            (
                _action("root", "open_folder"),
                _action("reports-one", "open_folder", ("Work", "Reports")),
                _action("reports-two", "open_folder", ("work", "reports")),
                _action("monthly", "open_folder", ("Work", "Monthly")),
                _action(
                    "archived",
                    "open_folder",
                    ("Archive",),
                    state="Archived",
                ),
                _action("prompt", "ai_prompt", ("Work",)),
            ),
            action_type="open_folder",
        )

        nodes = _nodes_by_path(tree)
        self.assertEqual(tree.label, "Folders")
        self.assertEqual(tree.direct_action_count, 1)
        self.assertEqual(tree.total_action_count, 4)
        self.assertEqual([child.label for child in tree.children], ["Work"])
        self.assertEqual(nodes[("Work",)].total_action_count, 3)
        self.assertEqual(nodes[("Work", "Reports")].direct_action_count, 2)
        self.assertEqual(nodes[("Work", "Monthly")].direct_action_count, 1)
        self.assertNotIn(("Archive",), nodes)

    def test_current_path_is_retained_and_uses_existing_canonical_casing(self) -> None:
        tree = quick_menu_path_tree(
            (_action("reports", "open_folder", ("Work", "Reports")),),
            action_type="open_folder",
            current_path=("work", "New location"),
        )

        nodes = _nodes_by_path(tree)
        self.assertIn(("Work", "New location"), nodes)
        self.assertTrue(nodes[("Work", "New location")].current)
        self.assertEqual(nodes[("Work", "New location")].total_action_count, 0)
        self.assertNotIn(("work", "New location"), nodes)


class QuickMenuPathDialogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()
        self.root.destroy()

    def _dialog(
        self,
        *,
        actions: tuple[Action, ...] = (),
        current_path: tuple[str, ...] = (),
        selected: list[tuple[str, ...]] | None = None,
    ) -> QuickMenuPathDialog:
        output = selected if selected is not None else []
        dialog = QuickMenuPathDialog(
            self.root,
            action_type="open_folder",
            actions=actions,
            current_path=current_path,
            on_select=output.append,
        )
        self.root.update()
        return dialog

    def _placement_dialog(
        self,
        *,
        actions: tuple[Action, ...] = (),
        current_path: tuple[str, ...] = (),
        configured_locations: tuple[ConfiguredPlacementLocation, ...] = (),
        selected_configured_location_keys: (
            tuple[ConfiguredPlacementKey, ...] | None
        ) = None,
        selected: list[QuickMenuPlacementSelection] | None = None,
    ) -> QuickMenuPathDialog:
        output = selected if selected is not None else []
        dialog = QuickMenuPathDialog(
            self.root,
            action_type="open_folder",
            actions=actions,
            current_path=current_path,
            configured_locations=configured_locations,
            selected_configured_location_keys=selected_configured_location_keys,
            on_select_placements=output.append,
        )
        self.root.update()
        return dialog

    def test_dialog_shows_full_root_current_path_counts_and_fixed_footer(self) -> None:
        dialog = self._dialog(
            actions=(
                _action("root", "open_folder"),
                _action("reports", "open_folder", ("Work", "Reports")),
            ),
            current_path=("Work", "Reports"),
        )

        self.assertEqual(dialog.window.title(), "Choose location in Folders")
        self.assertEqual(dialog.controls_frame.pack_info()["side"], "bottom")
        self.assertEqual(dialog.count_var.get(), "3 locations")
        self.assertEqual(dialog.selected_path(), ("Work", "Reports"))
        root_iid = dialog.iid_by_path[()]
        self.assertEqual(dialog.tree.item(root_iid, "text"), "Folders — menu root")
        self.assertEqual(dialog.tree.item(root_iid, "values"), ("1 here · 2 in branch",))
        self.assertIn(
            "Folders > Work > Reports",
            dialog.selection_var.get(),
        )

    def test_search_keeps_ancestors_and_selectable_root(self) -> None:
        dialog = self._dialog(
            actions=(
                _action("reports", "open_folder", ("Work", "Reports")),
                _action("monthly", "open_folder", ("Work", "Monthly")),
                _action("personal", "open_folder", ("Personal",)),
            ),
        )

        dialog.search_var.set("monthly")
        self.root.update_idletasks()

        self.assertEqual(
            set(dialog.iid_by_path),
            {(), ("Work",), ("Work", "Monthly")},
        )
        self.assertIn((), dialog.iid_by_path)
        self.assertEqual(dialog.count_var.get(), "3 locations")

    def test_using_root_returns_empty_path_and_closes(self) -> None:
        selected: list[tuple[str, ...]] = []
        dialog = self._dialog(
            actions=(_action("reports", "open_folder", ("Work",)),),
            current_path=("Work",),
            selected=selected,
        )
        dialog.tree.selection_set(dialog.iid_by_path[()])
        dialog._update_selection()

        dialog.use_selected()

        self.assertEqual(selected, [()])
        self.assertTrue(dialog.closed)

    def test_new_submenu_normalizes_name_and_reuses_canonical_sibling(self) -> None:
        dialog = self._dialog(
            actions=(
                _action("reports", "open_folder", ("Work", "Reports")),
            ),
        )

        dialog._accept_new_submenu(("Work",), "  reports  ")
        self.root.update_idletasks()
        self.assertEqual(dialog.selected_path(), ("Work", "Reports"))
        self.assertEqual(
            [path for path in dialog.iid_by_path if path == ("Work", "Reports")],
            [("Work", "Reports")],
        )

        dialog._accept_new_submenu(("Work",), "  Monthly   Sales  ")
        self.root.update_idletasks()
        self.assertEqual(dialog.selected_path(), ("Work", "Monthly Sales"))
        self.assertIn(("Work", "Monthly Sales"), dialog.iid_by_path)

    def test_new_submenu_is_disabled_at_three_levels(self) -> None:
        dialog = self._dialog(current_path=("One", "Two", "Three"))

        self.assertEqual(dialog.selected_path(), ("One", "Two", "Three"))
        self.assertEqual(str(dialog.new_submenu_button["state"]), "disabled")

    def test_archived_only_current_location_is_not_described_as_unsaved(self) -> None:
        dialog = self._dialog(
            actions=(
                _action(
                    "archived",
                    "open_folder",
                    ("Archive",),
                    state="Archived",
                ),
            ),
            current_path=("Archive",),
        )

        archived_iid = dialog.iid_by_path[("Archive",)]
        self.assertEqual(
            dialog.tree.item(archived_iid, "values"),
            ("No Active Actions here",),
        )

    def test_combined_dialog_visibly_distinguishes_automatic_and_other_menus(
        self,
    ) -> None:
        locations = (
            _configured_location("local", "apps", ("Apps",)),
            _configured_location(
                "shared",
                "standard",
                ("Standard", "Work tools"),
                item_id_path=("work-tools",),
            ),
        )
        dialog = self._placement_dialog(
            actions=(_action("reports", "open_folder", ("Work",)),),
            current_path=("Work",),
            configured_locations=locations,
            selected_configured_location_keys=(),
        )

        label_texts = {
            child.cget("text")
            for child in _descendants(dialog.window)
            if isinstance(child, (tk.Label, ttk.Label))
        }
        self.assertEqual(dialog.window.title(), "Choose menu locations")
        self.assertEqual(dialog.use_button.cget("text"), "Use these placements")
        self.assertIn("In Folders (automatic)", label_texts)
        self.assertIn("Also show in these menus (optional)", label_texts)
        self.assertEqual(dialog.count_var.get(), "2 automatic · 2 other")
        values = {
            dialog.configured_tree.item(iid, "values")[1]
            for iid in dialog.configured_tree.get_children("")
        }
        self.assertEqual(values, {"Apps", "Standard > Work tools"})

    def test_combined_result_returns_automatic_path_and_stable_keys_in_inventory_order(
        self,
    ) -> None:
        apps = _configured_location("local", "apps", ("Apps",))
        standard = _configured_location(
            "shared",
            "standard",
            ("Standard", "Development"),
            item_id_path=("development",),
        )
        selected: list[QuickMenuPlacementSelection] = []
        dialog = self._placement_dialog(
            actions=(_action("work", "open_folder", ("Work",)),),
            current_path=("Work",),
            configured_locations=(apps, standard),
            selected_configured_location_keys=(standard.key, apps.key),
            selected=selected,
        )

        dialog.use_selected()

        self.assertEqual(
            selected,
            [QuickMenuPlacementSelection(("Work",), (apps.key, standard.key))],
        )
        self.assertTrue(dialog.closed)

    def test_unavailable_location_cannot_be_added_but_existing_one_can_be_removed(
        self,
    ) -> None:
        reason = "Built-in menus require a Built-in Action."
        unavailable = _configured_location(
            "shared",
            "standard",
            ("Standard",),
            assignable=False,
            unavailable_reason=reason,
        )
        retained = _configured_location(
            "shared",
            "legacy",
            ("Legacy",),
            assigned=True,
            assignable=False,
            unavailable_reason=reason,
        )
        dialog = self._placement_dialog(
            configured_locations=(unavailable, retained),
        )

        unavailable_iid = dialog.configured_iid_by_key[unavailable.key]
        dialog.configured_tree.selection_set(unavailable_iid)
        dialog.toggle_selected_configured_location()
        self.assertNotIn(
            unavailable.key,
            dialog.selected_configured_location_keys,
        )
        self.assertEqual(
            dialog.configured_tree.item(unavailable_iid, "values"),
            ("—", "Standard", "Built-in", reason),
        )

        retained_iid = dialog.configured_iid_by_key[retained.key]
        self.assertEqual(
            dialog.configured_tree.item(retained_iid, "values")[3],
            "Assigned · removal allowed",
        )
        dialog.configured_tree.selection_set(retained_iid)
        dialog.toggle_selected_configured_location()
        self.assertNotIn(retained.key, dialog.selected_configured_location_keys)

    def test_combined_search_filters_both_location_lists(self) -> None:
        dialog = self._placement_dialog(
            actions=(
                _action("reports", "open_folder", ("Work", "Reports")),
            ),
            configured_locations=(
                _configured_location("local", "apps", ("Apps",)),
                _configured_location(
                    "shared",
                    "standard",
                    ("Standard", "Reports"),
                    item_id_path=("reports",),
                ),
            ),
        )

        dialog.search_var.set("reports")
        self.root.update_idletasks()

        self.assertEqual(
            set(dialog.iid_by_path),
            {(), ("Work",), ("Work", "Reports")},
        )
        self.assertEqual(len(dialog.configured_tree.get_children("")), 1)
        self.assertEqual(dialog.count_var.get(), "3 automatic · 1 other")

    def test_configured_only_search_preserves_staged_automatic_path(self) -> None:
        selected: list[QuickMenuPlacementSelection] = []
        standard = _configured_location(
            "shared",
            "standard",
            ("Standard", "Development"),
            item_id_path=("development",),
        )
        dialog = self._placement_dialog(
            actions=(
                _action("reports", "open_folder", ("Work", "Reports")),
            ),
            current_path=("Work", "Reports"),
            configured_locations=(standard,),
            selected=selected,
        )

        dialog.search_var.set("standard")
        self.root.update_idletasks()

        self.assertEqual(dialog.selected_path(), ("Work", "Reports"))
        self.assertIn(("Work", "Reports"), dialog.iid_by_path)
        dialog.use_selected()
        self.assertEqual(
            selected,
            [QuickMenuPlacementSelection(("Work", "Reports"), ())],
        )

    def test_requires_exactly_one_result_callback(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one"):
            QuickMenuPathDialog(
                self.root,
                action_type="open_folder",
                actions=(),
            )
        with self.assertRaisesRegex(ValueError, "exactly one"):
            QuickMenuPathDialog(
                self.root,
                action_type="open_folder",
                actions=(),
                on_select=lambda _path: None,
                on_select_placements=lambda _selection: None,
            )

    def test_submenu_name_validation_uses_operation_neutral_error_title(self) -> None:
        dialog = QuickMenuSubmenuNameDialog(
            self.root,
            root_label="Folders",
            parent_path=("Work",),
            on_submit=lambda _name: None,
            title="Rename automatic submenu",
            submit_label="Review rename",
            context_label="Rename in",
        )
        self.root.update()
        dialog.name_var.set("")

        with patch(
            "context_palette.quick_menu_path_dialog.messagebox.showerror"
        ) as show_error:
            dialog.submit()

        self.assertEqual(show_error.call_args.args[0], "Submenu name is invalid")
        self.assertFalse(dialog.closed)


if __name__ == "__main__":
    unittest.main()
