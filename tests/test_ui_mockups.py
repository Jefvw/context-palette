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
                    with self.subTest(screen=screen, size=size, scaling=scaling):
                        root, view = self.build(screen, size=size, scaling=scaling)
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
                    self.assertGreaterEqual(view.workspace.winfo_width(), 350)
                    entry_center = view.find_entry.winfo_y() + view.find_entry.winfo_height() / 2
                    filter_center = view.filter_button.winfo_y() + view.filter_button.winfo_height() / 2
                    self.assertAlmostEqual(entry_center, filter_center, delta=1)
                    row_height = int(ttk.Style(root).lookup("Treeview", "rowheight"))
                    self.assertGreaterEqual(view.results.winfo_height() // row_height, 5)
                    self.assertGreaterEqual(view.text.winfo_width(), 300)
                    self.assertGreaterEqual(view.text.winfo_height(), 180)
                    self.assertEqual(view.primary_button.cget("text"), "Stop remaining")
                    self.assertTrue(view.configure_button.winfo_manager())
                    self.assertTrue(view.quick_canvas.winfo_manager())
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

    def test_focus_and_context_filter_remain_independent_and_truthful(self) -> None:
        root, view = self.build(MOCKUP_MAIN, scenario="selected")
        try:
            self.assertIsInstance(view, MainPaletteMockup)
            view._set_context_filter("Developing")
            view._set_focus("Empty UAT")
            self.assertEqual(view.context_filter, "Developing")
            self.assertEqual(view.current_focus, "Empty UAT")
            self.assertTrue(view.results.get_children(""))
            self.assertFalse(
                any(
                    "focus" in view.results.item(item, "tags")
                    for item in view.results.get_children("")
                )
            )
            view._set_context_filter(None)
            view._toggle_focus_only()
            self.assertFalse(view.results.get_children(""))
            self.assertTrue(view.empty_state.winfo_manager())
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


if __name__ == "__main__":
    unittest.main()
