from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk
import unittest

from context_palette.ui_mockups import (
    BASE_TK_SCALING,
    MOCKUP_ACTIONS,
    MOCKUP_DEFINITIONS,
    MOCKUP_KEYS,
    MOCKUP_MAIN,
    MOCKUP_WORK_ITEMS,
    SCALE_PERCENTAGES,
    SIZE_KEYS,
    SIZE_MINIMUM,
    SIZE_NORMAL,
    ConfigureMockup,
    MainPaletteMockup,
    build_mockup,
    tk_scaling_for_percentage,
)


def descendants(widget: tk.Misc) -> tuple[tk.Misc, ...]:
    children: list[tk.Misc] = []
    for child in widget.winfo_children():
        children.append(child)
        children.extend(descendants(child))
    return tuple(children)


@unittest.skipUnless(sys.platform == "win32", "Real-Tk mockups target Windows.")
class UiMockupTkTests(unittest.TestCase):
    def build(
        self,
        screen: str,
        *,
        size: str = SIZE_NORMAL,
        scaling: int = 100,
        scenario: str | None = None,
    ) -> tuple[tk.Tk, MainPaletteMockup | ConfigureMockup]:
        root = tk.Tk()
        root.withdraw()
        definition = MOCKUP_DEFINITIONS[screen]
        view = build_mockup(
            root,
            screen=screen,
            scenario=scenario or definition.scenarios[0][0],
            size=size,
            scaling=scaling,
        )
        width, height = definition.size(size)
        root.geometry(f"{width}x{height}+-32000+-32000")
        root.deiconify()
        root.update()
        return root, view  # type: ignore[return-value]

    def test_all_mockups_fit_supported_size_and_scaling_matrix(self) -> None:
        for screen in MOCKUP_KEYS:
            for size in SIZE_KEYS:
                for scaling in SCALE_PERCENTAGES:
                    for scenario, _label in MOCKUP_DEFINITIONS[screen].scenarios:
                        with self.subTest(
                            screen=screen,
                            size=size,
                            scaling=scaling,
                            scenario=scenario,
                        ):
                            root, view = self.build(
                                screen,
                                size=size,
                                scaling=scaling,
                                scenario=scenario,
                            )
                            try:
                                self.assertEqual(view.layout_issues(), ())
                                for widget in view.critical_widgets:
                                    if not widget.winfo_manager():
                                        continue
                                    if widget.winfo_class() not in {"TButton", "TMenubutton"}:
                                        continue
                                    if (
                                        isinstance(view, MainPaletteMockup)
                                        and widget in view.scope_buttons.values()
                                    ):
                                        continue
                                    text = str(widget.cget("text"))
                                    if text:
                                        self.assertGreaterEqual(
                                            widget.winfo_width() + 1,
                                            widget.winfo_reqwidth(),
                                            f"Clipped {text!r} in {screen}/{size}/{scaling}%",
                                        )
                            finally:
                                root.destroy()

    def test_main_palette_keeps_daily_regions_visible_at_minimum(self) -> None:
        for scaling in SCALE_PERCENTAGES:
            with self.subTest(scaling=scaling):
                root, view = self.build(
                    MOCKUP_MAIN,
                    size=SIZE_MINIMUM,
                    scaling=scaling,
                    scenario="sequence",
                )
                try:
                    self.assertGreaterEqual(view.panes.sashpos(0), 286)
                    self.assertGreaterEqual(
                        view.workspace.winfo_width(),
                        340 if scaling >= 150 else 350,
                    )
                    entry_center = view.find_entry.winfo_y() + view.find_entry.winfo_height() / 2
                    filter_center = view.filter_button.winfo_y() + view.filter_button.winfo_height() / 2
                    self.assertAlmostEqual(entry_center, filter_center, delta=1)
                    row_height = int(ttk.Style(root).lookup("Treeview", "rowheight"))
                    self.assertGreaterEqual(view.results.winfo_height() // row_height, 5)
                    self.assertGreaterEqual(view.text.winfo_width(), 300)
                    self.assertGreaterEqual(view.text.winfo_height(), 180)
                    self.assertEqual(view.primary_button.cget("text"), "Stop remaining")
                    self.assertEqual(view.send_to_button.cget("text"), "Send to…")
                    self.assertTrue(view.send_to_button.winfo_manager())
                    self.assertTrue(view.configure_button.winfo_manager())
                    self.assertTrue(view.quick_canvas.winfo_manager())
                finally:
                    root.destroy()

    def test_main_palette_proposes_accessible_scope_and_aligned_tools(self) -> None:
        for scaling in SCALE_PERCENTAGES:
            with self.subTest(scaling=scaling):
                root, view = self.build(
                    MOCKUP_MAIN,
                    size=SIZE_MINIMUM,
                    scaling=scaling,
                    scenario="selected",
                )
                try:
                    style = ttk.Style(root)
                    selected_scope = "ScopeSelected.TButton"
                    self.assertEqual(
                        style.lookup(selected_scope, "background"),
                        "#d8eeeb",
                    )
                    self.assertEqual(
                        style.lookup(selected_scope, "foreground"),
                        "#1f2933",
                    )
                    self.assertEqual(
                        style.lookup(selected_scope, "foreground", ("active", "pressed")),
                        "#1f2933",
                    )
                    self.assertEqual(
                        style.lookup(selected_scope, "foreground", ("disabled", "active")),
                        "#52616b",
                    )
                    self.assertEqual(
                        style.lookup(selected_scope, "bordercolor", ("focus",)),
                        "#005fcc",
                    )
                    self.assertEqual(view.preview_button.cget("text"), "Preview")
                    self.assertEqual(str(view.preview_button.cget("state")), str(tk.NORMAL))
                    for button in view.scope_buttons.values():
                        self.assertGreaterEqual(button.winfo_width(), button.winfo_reqwidth())
                    self.assertEqual(
                        {button.winfo_height() for button in view.workspace_buttons},
                        {view.send_to_button.winfo_height()},
                    )
                    self.assertEqual(
                        view.preview_button.winfo_height(),
                        view.send_to_button.winfo_height(),
                    )
                    self.assertEqual(
                        style.layout("Toolbar.TMenubutton"),
                        style.layout("TMenubutton"),
                    )
                    self.assertEqual(
                        style.lookup(
                            "ToolbarIcon.TButton",
                            "background",
                            ("active", "pressed"),
                        ),
                        "#d8eeeb",
                    )
                    self.assertEqual(
                        style.lookup(
                            "ToolbarIcon.TButton",
                            "foreground",
                            ("active", "pressed"),
                        ),
                        "#1f2933",
                    )
                    self.assertEqual(
                        style.lookup(
                            "ToolbarIcon.TButton",
                            "foreground",
                            ("disabled", "active"),
                        ),
                        "#52616b",
                    )
                    self.assertEqual(
                        style.lookup(
                            "Primary.TButton",
                            "background",
                            ("disabled", "active", "pressed"),
                        ),
                        "#eef2f4",
                    )
                    self.assertEqual(
                        style.lookup(
                            "Primary.TButton",
                            "foreground",
                            ("disabled", "active", "pressed"),
                        ),
                        "#52616b",
                    )
                    self.assertNotIn("▼", view.send_to_button.cget("text"))
                    self.assertNotIn("▾", view.send_to_button.cget("text"))
                    self.assertEqual(view.text.cget("font"), "Consolas 10")
                    self.assertEqual(view.text.cget("highlightcolor"), "#005fcc")
                    self.assertEqual(view.text.cget("selectbackground"), "#087f78")
                    self.assertEqual(
                        tuple(map(str, root.tk.splitlist(view.new_action_button.cget("image")))),
                        (str(view.icons["create_action"]),),
                    )
                    self.assertEqual(view.new_action_button.cget("text"), "Create Action")
                    self.assertEqual(str(view.new_action_button.cget("compound")), "none")
                    self.assertIn("Create Action", view.new_action_button.mockup_accessible_name)
                finally:
                    root.destroy()

    def test_main_palette_uses_compact_execution_row_for_work_item_open(self) -> None:
        root, view = self.build(
            MOCKUP_MAIN,
            size=SIZE_MINIMUM,
            scaling=150,
            scenario="work-item",
        )
        try:
            self.assertTrue(view.compact_execution_row.winfo_manager())
            self.assertTrue(view.preview_button.winfo_ismapped())
            self.assertTrue(view.primary_button.winfo_ismapped())
            self.assertEqual(
                view.preview_button.grid_info()["in"],
                view.compact_execution_row,
            )
            toolbar_children = view.compact_execution_row.master.winfo_children()
            self.assertLess(
                toolbar_children.index(view.compact_execution_row),
                toolbar_children.index(view.preview_button),
            )
            self.assertLess(
                toolbar_children.index(view.compact_execution_row),
                toolbar_children.index(view.primary_button),
            )
            self.assertGreater(view.preview_button.winfo_y(), view.edit_button.winfo_y())
            self.assertGreater(view.primary_button.winfo_y(), view.edit_button.winfo_y())
            self.assertEqual(view.primary_button.cget("text"), "Open")
            self.assertEqual(view.layout_issues(), ())
            event = type("Event", (), {"widget": view.execution_toolbar, "width": 1000})()
            view._layout_execution_controls(event)
            self.assertEqual(
                view.preview_button.grid_info()["in"],
                view.execution_toolbar,
            )
            event.width = 1
            view._layout_execution_controls(event)
            self.assertEqual(
                view.preview_button.grid_info()["in"],
                view.compact_execution_row,
            )
        finally:
            root.destroy()

    def test_configure_uses_one_mapped_page_without_notebook(self) -> None:
        for screen in (MOCKUP_WORK_ITEMS, MOCKUP_ACTIONS):
            with self.subTest(screen=screen):
                root, view = self.build(screen, size=SIZE_MINIMUM, scaling=150)
                try:
                    self.assertIsInstance(view, ConfigureMockup)
                    self.assertFalse(
                        any(isinstance(widget, ttk.Notebook) for widget in descendants(root))
                    )
                    self.assertEqual(
                        sum(bool(page.winfo_manager()) for page in view.pages.values()),
                        1,
                    )
                    tree = view.work_tree if screen == MOCKUP_WORK_ITEMS else view.actions_tree
                    row_height = int(ttk.Style(root).lookup("Treeview", "rowheight"))
                    useful_height = max(0, tree.winfo_height() - row_height)
                    if screen == MOCKUP_WORK_ITEMS:
                        self.assertGreater(tree.winfo_height(), 1)
                    else:
                        self.assertGreaterEqual(useful_height // row_height, 3)
                    self.assertFalse(
                        any(
                            isinstance(widget, ttk.Scrollbar)
                            and str(widget.cget("orient")) == str(tk.HORIZONTAL)
                            for widget in descendants(root)
                        )
                    )
                finally:
                    root.destroy()

    def test_configure_tables_keep_useful_rows_at_current_minimum(self) -> None:
        for screen in (MOCKUP_WORK_ITEMS, MOCKUP_ACTIONS):
            with self.subTest(screen=screen):
                root, view = self.build(screen, size=SIZE_MINIMUM, scaling=100)
                try:
                    tree = view.work_tree if screen == MOCKUP_WORK_ITEMS else view.actions_tree
                    row_height = int(ttk.Style(root).lookup("Treeview", "rowheight"))
                    useful_height = max(0, tree.winfo_height() - row_height)
                    self.assertGreaterEqual(useful_height // row_height, 4)
                finally:
                    root.destroy()

    def test_context_filter_controls_membership_and_shortcut_slots(self) -> None:
        root, view = self.build(MOCKUP_MAIN, scenario="selected")
        try:
            self.assertIsInstance(view, MainPaletteMockup)
            self.assertFalse(hasattr(view, "focus_only_button"))
            self.assertFalse(hasattr(view, "context_scope_picker"))
            self.assertFalse(hasattr(view, "context_var"))
            self.assertIsNone(view.item_context_filter)
            self.assertTrue(
                any(
                    "context_slot" in view.results.item(item, "tags")
                    for item in view.results.get_children("")
                )
            )
            self.assertIn("cart", view.results.get_children(""))

            view._set_context_filter("Developing")
            root.update_idletasks()
            self.assertEqual(view.item_context_filter, "Developing")
            self.assertIn("Context: Developing", view.filter_chip.cget("text"))
            self.assertEqual(view.filter_button.cget("style"), "RailIconAccent.TButton")
            self.assertTrue(
                all(
                    "Developing" in view.result_items[item].contexts
                    for item in view.results.get_children("")
                )
            )
            self.assertTrue(
                all(
                    "context_slot" in view.results.item(item, "tags")
                    for item in view.results.get_children("")[:5]
                )
            )
            chip_bottom = view.filter_chip.winfo_rooty() + view.filter_chip.winfo_height()
            self.assertLessEqual(chip_bottom, view.results_host.winfo_rooty())

            view._set_context_filter(None)
            self.assertIn("cart", view.results.get_children(""))
            self.assertEqual(view.filter_button.cget("style"), "Icon.TButton")
            self.assertTrue(
                any(
                    "context_slot" in view.results.item(item, "tags")
                    for item in view.results.get_children("")
                )
            )

            view._set_context_filter("Developing")
            view._placeholder_active = False
            view.find_var.set("open")
            view._render_results()
            self.assertFalse(
                any(
                    "context_slot" in view.results.item(item, "tags")
                    for item in view.results.get_children("")
                )
            )
            self.assertEqual(view.item_context_filter, "Developing")
        finally:
            root.destroy()

    def test_mockups_show_current_quick_order_and_work_item_organize(self) -> None:
        root, main = self.build(MOCKUP_MAIN, scenario="no-selection")
        try:
            self.assertIsInstance(main, MainPaletteMockup)
            self.assertEqual(
                main.quick_group_order,
                ("Standard", "My work", "Shared tools", "Passwords", "Folders", "Prompts"),
            )
            self.assertEqual(
                tuple(button.cget("text") for button in main.quick_buttons),
                main.quick_group_order,
            )
        finally:
            root.destroy()

        root, configure = self.build(MOCKUP_WORK_ITEMS, scenario="selected")
        try:
            self.assertIsInstance(configure, ConfigureMockup)
            self.assertEqual(configure.work_organize_button.cget("text"), "Organize")
            self.assertEqual(
                configure.work_organize_menu.entrycget(0, "label"),
                "Edit tags & contexts…",
            )
            self.assertEqual(
                configure.work_organize_menu.entrycget(2, "label"),
                "Forget Palette organization…",
            )
        finally:
            root.destroy()

        root, configure = self.build(MOCKUP_ACTIONS, scenario="active")
        try:
            self.assertIsInstance(configure, ConfigureMockup)
            self.assertFalse(hasattr(configure, "pins_panel"))
            self.assertEqual(
                str(configure.action_delete_button.cget("state")),
                str(tk.NORMAL),
            )
            self.assertEqual(
                str(configure.action_edit_button.cget("state")),
                str(tk.NORMAL),
            )
            self.assertFalse(hasattr(configure, "action_state_var"))
            self.assertFalse(hasattr(configure, "action_lifecycle_button"))
        finally:
            root.destroy()

        root, configure = self.build(MOCKUP_ACTIONS, scenario="legacy-inactive")
        try:
            self.assertIsInstance(configure, ConfigureMockup)
            self.assertEqual(
                str(configure.action_delete_button.cget("state")),
                str(tk.NORMAL),
            )
            self.assertEqual(
                str(configure.action_edit_button.cget("state")),
                str(tk.DISABLED),
            )
            selection = configure.actions_tree.selection()
            self.assertTrue(selection)
            self.assertEqual(
                configure.actions_tree.set(selection[0], "state"),
                "Legacy inactive",
            )
        finally:
            root.destroy()

    def test_main_mockup_send_to_menu_separates_copy_and_vscode_effects(self) -> None:
        root, main = self.build(MOCKUP_MAIN, scenario="no-selection")
        try:
            self.assertIsInstance(main, MainPaletteMockup)
            labels = [
                main.send_to_menu.entrycget(index, "label")
                for index in range(main.send_to_menu.index(tk.END) + 1)
                if main.send_to_menu.type(index) != "separator"
            ]
            self.assertEqual(
                labels,
                [
                    "Finance reports",
                    "Choose another folder…",
                    "Open with:",
                    "Open folder in VS Code",
                ],
            )
        finally:
            root.destroy()


class UiMockupDefinitionTests(unittest.TestCase):
    def test_presets_keep_current_supported_window_boundaries(self) -> None:
        self.assertEqual(MOCKUP_DEFINITIONS[MOCKUP_MAIN].normal_size, (780, 600))
        self.assertEqual(MOCKUP_DEFINITIONS[MOCKUP_MAIN].minimum_size, (700, 480))
        self.assertEqual(MOCKUP_DEFINITIONS[MOCKUP_WORK_ITEMS].normal_size, (960, 680))
        self.assertEqual(MOCKUP_DEFINITIONS[MOCKUP_ACTIONS].minimum_size, (900, 520))

    def test_scaling_presets_match_windows_logical_dpi(self) -> None:
        self.assertAlmostEqual(tk_scaling_for_percentage(100), BASE_TK_SCALING)
        self.assertAlmostEqual(tk_scaling_for_percentage(125), BASE_TK_SCALING * 1.25)
        self.assertAlmostEqual(tk_scaling_for_percentage(150), BASE_TK_SCALING * 1.5)
        with self.assertRaises(ValueError):
            tk_scaling_for_percentage(175)

    def test_scenarios_describe_the_current_retrieval_model(self) -> None:
        main_scenarios = dict(MOCKUP_DEFINITIONS[MOCKUP_MAIN].scenarios)
        self.assertIn("context-slots", main_scenarios)
        self.assertIn("context-filter", main_scenarios)
        self.assertIn("empty-context", main_scenarios)
        self.assertNotIn("pins", dict(MOCKUP_DEFINITIONS[MOCKUP_ACTIONS].scenarios))


if __name__ == "__main__":
    unittest.main()
