"""Production presentation checks with fictional data and isolated effects."""
from __future__ import annotations

import gc
import sys
import tkinter as tk
from tkinter import font as tkfont, ttk
import unittest

from context_palette.style import COLORS
import tests.test_launcher_enhancements_ui as fixtures


@unittest.skipUnless(sys.platform == "win32", "Requires Windows Tk.")
class UiPolishTests(unittest.TestCase):
    def setUp(self) -> None:
        gc.collect()
        self.fixture = fixtures.LauncherEnhancementsUiTests()

    def test_scope_transitions_and_combined_states_keep_their_visual_meaning(self):
        with self.fixture.launcher() as (app, *_):
            style = ttk.Style(app.root)
            panel = app.action_discovery_panel
            for selected in ("all", "actions", "work_items", "all"):
                panel.scope_buttons[selected].invoke()
                app.root.update()
                for scope, button in panel.scope_buttons.items():
                    self.assertEqual(
                        button.cget("style"),
                        "ScopeSelected.TButton" if scope == selected else "Scope.TButton",
                    )
                self.assertEqual(app.run_button.cget("style"), "Primary.TButton")
            self.assertEqual(style.lookup("ScopeSelected.TButton", "background"), COLORS["row_aqua"])
            self.assertEqual(style.lookup("Primary.TButton", "background"), COLORS["accent"])
            for name in ("Scope.TButton", "ScopeSelected.TButton", "Toolbar.TButton",
                         "Toolbar.TMenubutton", "ToolbarIcon.TButton", "ToolbarIcon.TMenubutton"):
                with self.subTest(style=name):
                    self.assertEqual(style.lookup(name, "foreground", ("active", "pressed")), COLORS["text"])
                    self.assertEqual(style.lookup(name, "background", ("active", "pressed")), COLORS["row_aqua"])
                    self.assertEqual(style.lookup(name, "foreground", ("disabled", "active", "pressed")), COLORS["muted_text"])
                    self.assertEqual(style.lookup(name, "background", ("disabled", "active", "pressed")), COLORS["background"])
                    self.assertEqual(style.lookup(name, "bordercolor", ("focus",)), COLORS["focus"])
            self.assertEqual(style.lookup("Primary.TButton", "background", ("disabled", "active", "pressed")), COLORS["topic_header"])
            self.assertEqual(style.lookup("Primary.TButton", "foreground", ("disabled", "active", "pressed")), COLORS["muted_text"])
            self.assertEqual(style.lookup("Danger.TButton", "foreground"), COLORS["error"])

    def test_production_tools_and_scope_labels_fit_normal_minimum_scaling_matrix(self):
        for scale in (100, 125, 150):
            for size in ("780x600", "700x480"):
                with self.subTest(scale=scale, size=size), self.fixture.launcher(
                    scaling=4 / 3 * scale / 100, size=size,
                ) as (app, *_):
                    panel = app.workspace_component
                    discovery = app.action_discovery_panel
                    discovery.render_control_state(work_item=True, has_selection=True)
                    app.root.update()
                    controls = (
                        panel.send_to_button, panel.content_back_button,
                        panel.content_forward_button, panel.capture_button,
                        panel.inbox_button, panel.create_action_button,
                        panel.ocr_button, panel.text_tools_button,
                        app.preview_button, discovery.new_action_button, discovery.edit_button,
                        discovery.work_item_folder_button,
                    )
                    self.assertEqual(len({control.winfo_height() for control in controls}), 1)
                    for control in (*controls, app.run_button):
                        self.fixture.assert_control_fits(control, app.root)
                    self.fixture.assert_control_fits(app.scope_options_button, app.root)
                    style = ttk.Style(app.root)
                    for button in discovery.scope_buttons.values():
                        font = tkfont.Font(root=app.root, font=style.lookup(button.cget("style"), "font"))
                        self.assertGreaterEqual(button.winfo_width(), font.measure(button.cget("text")) + 4)
                    self.assertEqual(panel.text.cget("font"), "Consolas 10")
                    self.assertTrue(panel.text.cget("undo"))
                    self.assertFalse(panel.text.cget("exportselection"))
                    self.assertEqual(int(panel.text.cget("borderwidth")), 0)
                    self.assertEqual(panel.text.cget("highlightcolor"), COLORS["focus"])
                    self.assertEqual(panel.text.cget("selectbackground"), COLORS["accent"])
                    self.assertEqual(panel.text.cget("selectforeground"), COLORS["white"])

    def test_compact_execution_controls_remain_above_their_container_after_resize(self):
        with self.fixture.launcher(scaling=2, size="700x480") as (app, *_):
            panel = app.action_discovery_panel
            panel.render_control_state(sequence_running=True, has_selection=True)
            for size in ("700x480", "1400x800", "700x480"):
                app.root.geometry(size + "+-32000+-32000")
                app.root.update()
                if size.startswith("700"):
                    row = app.compact_execution_row
                    siblings = row.master.winfo_children()
                    self.assertTrue(row.winfo_ismapped())
                    for control in (app.preview_button, panel.primary_action_frame):
                        self.assertEqual(str(control.grid_info()["in"]), str(row))
                        self.assertLess(siblings.index(row), siblings.index(control))
                else:
                    self.assertFalse(app.compact_execution_row.winfo_manager())
                self.fixture.assert_control_fits(app.preview_button, app.root)
                self.fixture.assert_control_fits(app.run_button, app.root)
                self.assertEqual(app.run_button.cget("text"), "Stop remaining")

    def test_quick_menu_keeps_one_visible_right_arrow_and_existing_bindings(self):
        with self.fixture.launcher(size="1100x700") as (app, *_):
            for area in app.command_tiles_frame.winfo_children():
                for control in area.winfo_children():
                    self.assertIsInstance(control, ttk.Label)
                    self.assertFalse(control.cget("text").endswith(("▾", "▼")))
                    for event in ("<Button-1>", "<Button-3>", "<Return>", "<space>"):
                        self.assertTrue(control.bind(event), event)
            host = ttk.Frame(app.root)
            host.columnconfigure(0, weight=1)
            label = app._surface_menu_label(host, "A deliberately long fictional Quick-menu title")
            for width in (100, 180):
                host.place(x=0, y=0, width=width, height=40)
                app.root.update()
                indicators = [x for x in range(label.winfo_width())
                              if "indicator" in label.identify(x, label.winfo_height() // 2)]
                self.assertTrue(indicators, "Long menu text must not conceal the arrow")
                self.assertGreater(min(indicators), label.winfo_width() - 35)
                self.assertEqual(indicators, list(range(min(indicators), max(indicators) + 1)))
            host.destroy()


if __name__ == "__main__":
    unittest.main()
