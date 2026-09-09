"""Real result widgets, fictional records, and no external execution."""
from dataclasses import replace
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk
import unittest

from context_palette.action_discovery_panel import FOCUS_SLOT_ROW_TAG
from context_palette.actions import Action
from context_palette.style import COLORS
from context_palette.work_item_refresh import SourceRefreshResult, WorkItemIndex
from context_palette.work_items import DiscoveredWorkItem, WorkItemSource
import tests.test_launcher_enhancements_ui as fixtures


def populate_results(app):
    """Shared by tests and the owned-window visual evidence harness."""
    definitions = (
        ("copy_text", "Current date and time", "{date}"),
        ("copy_text", "Professional greeting", "Hello"),
        ("open_url", "Python documentation", "https://example.invalid"),
        ("open_folder", "Project folder", "D:/Example"),
        ("open_file", "Reference notes", "D:/Example/notes.txt"),
        ("copy_text", "Basic SELECT template", "SELECT"),
        ("copy_text", "Basic CTE template", "WITH"),
        ("copy_text", "Follow-up template", "Following up"),
        ("copy_text", "Standard signature", "Regards"),
        ("open_url", "Team handbook", "https://example.invalid/handbook"),
        ("open_folder", "Downloads", "D:/Example/Downloads"),
    )
    app.actions = [Action(f"example-{i}", title, "General", kind, value)
                   for i, (kind, title, value) in enumerate(definitions)]
    app.palette_state = replace(
        app.palette_state, focus_context="General", context_item_slots={},
        context_slots={"General": tuple(action.id for action in app.actions[:5])},
    )
    items = tuple(DiscoveredWorkItem(
        "example", "Example", f"CAS-Example-{i}", Path(f"D:/Example/{i}"),
        f"Case {i}", "CAS", "Case", "Example", f"case-{i}", (), None,
    ) for i in range(3))
    source = WorkItemSource("example", "Example", Path("D:/Example"))
    app.work_item_index = WorkItemIndex((SourceRefreshResult(source, items),))
    app.item_context_filter = None
    app._refresh_results()


@unittest.skipUnless(sys.platform == "win32", "Requires Windows Tk.")
class ResultRowStylingTests(unittest.TestCase):
    def test_action_bands_preserve_labels_shortcuts_separator_and_search(self):
        with fixtures.LauncherEnhancementsUiTests().launcher() as (app, *_):
            populate_results(app)
            app.discovery_scope = "actions"
            app._refresh_results()
            self.assertEqual(list(app.slot_actions), [6, 7, 8, 9, 10])
            self.assertEqual(app.results.itemcget(0, "background"), COLORS["slot_focus"])
            self.assertEqual(app.results.itemcget(1, "background"), COLORS["slot_focus_alternate"])
            self.assertEqual(app.displayed_action_rows[5], (None, None))
            self.assertEqual(app.results.itemcget(5, "foreground"), COLORS["muted_text"])
            self.assertEqual(app.results.itemcget(6, "background"), COLORS["surface"])
            self.assertEqual(app.results.itemcget(7, "background"), COLORS["result_alternate"])
            for index, (action, _) in enumerate(app.displayed_action_rows):
                if action is not None:
                    self.assertEqual(app.results.get(index), app._aligned_action_display_text(action))
            self.assertEqual(app.results.cget("selectbackground"), COLORS["accent"])
            self.assertEqual(app.results.cget("selectforeground"), COLORS["white"])
            slots = dict(app.slot_items)
            app.search_var.set("template")
            app._refresh_results()
            self.assertEqual(app.slot_items, slots)
            self.assertTrue(all(slot is None for _, slot in app.displayed_action_rows))
            self.assertEqual([action for action, _ in app.displayed_action_rows], app.filtered_actions)
            self.assertEqual(app.results.itemcget(0, "background"), COLORS["surface"])
            self.assertEqual(app.results.itemcget(1, "background"), COLORS["result_alternate"])

    def test_mixed_tree_uses_one_paint_tag_and_preserves_shortcut_identity(self):
        with fixtures.LauncherEnhancementsUiTests().launcher() as (app, *_):
            populate_results(app)
            tree = app.focus_tree
            rows = tree.get_children()
            self.assertEqual(len(rows), len(app.actions) + 3)
            expected = ("slot_focus", "slot_focus_alternate", "slot_focus",
                        "slot_focus_alternate", "slot_focus", "result_alternate", "surface")
            for index, color_key in enumerate(expected):
                tags = tree.item(rows[index], "tags")
                paints = [tag for tag in tags if tree.tag_configure(tag, "background")]
                self.assertEqual(paints, ["result_" + color_key])
                self.assertEqual(str(tree.tag_configure(paints[0], "background")), COLORS[color_key])
                self.assertEqual(FOCUS_SLOT_ROW_TAG in tags, index < 5)
                self.assertIn(rows[index], app.focus_tree_items)
            style = ttk.Style(app.root)
            self.assertEqual(style.lookup("Flat.Treeview", "background", ("selected",)), COLORS["accent"])
            self.assertEqual(style.lookup("Flat.Treeview", "foreground", ("selected",)), COLORS["white"])
            for index in (0, 1, 5, 6):
                tree.selection_set(rows[index])
                tree.focus(rows[index])
                app._update_preview()
                self.assertEqual(tree.selection(), (rows[index],))
            app.search_var.set("template")
            app._refresh_results()
            for row in tree.get_children():
                self.assertNotIn(FOCUS_SLOT_ROW_TAG, tree.item(row, "tags"))

    def test_work_item_bands_and_empty_state_do_not_retain_shortcut_paint(self):
        with fixtures.LauncherEnhancementsUiTests().launcher() as (app, *_):
            populate_results(app)
            app.discovery_scope = "actions"
            app._refresh_results()
            app.discovery_scope = "work_items"
            app._refresh_results()
            self.assertEqual(len(app.displayed_work_items), 3)
            self.assertEqual(app.results.itemcget(0, "background"), COLORS["surface"])
            self.assertEqual(app.results.itemcget(1, "background"), COLORS["result_alternate"])
            self.assertEqual(app.results.get(0), "Case → Example case 0")
            app.search_var.set("no-such-item")
            app._refresh_results()
            self.assertEqual(app.displayed_work_items, [])
            self.assertEqual(app.results.itemcget(0, "foreground"), COLORS["muted_text"])
            self.assertEqual(app.results.itemcget(0, "background"), "")


if __name__ == "__main__":
    unittest.main()
