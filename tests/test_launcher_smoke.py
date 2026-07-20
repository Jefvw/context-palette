from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.launcher import (
    MINIMUM_ACTION_CONSOLE_HEIGHT,
    MINIMUM_ACTIONS_WIDTH,
    MINIMUM_QUICK_ACTIONS_WIDTH,
    MINIMUM_WORKSPACE_HEIGHT,
    LauncherApp,
)
from context_palette.workspace_transforms import WORKSPACE_TRANSFORM_GROUPS


@unittest.skipUnless(sys.platform == "win32", "The launcher smoke test requires Windows Tk.")
class LauncherSmokeTests(unittest.TestCase):
    def test_complete_launcher_constructs_and_closes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            data = Path(temporary_directory)
            actions_path = self._write_json(
                data / "actions.json",
                {
                    "actions": [
                        {
                            "id": "general-first",
                            "title": "General first",
                            "context": "General",
                            "technology": "Text",
                            "task": "Reusable text",
                            "type": "copy_text",
                            "value": "First",
                            "state": "Trusted",
                        },
                        {
                            "id": "database-only",
                            "title": "Database only",
                            "context": "Database",
                            "technology": "Database",
                            "task": "Lookup",
                            "type": "copy_text",
                            "value": "Database",
                            "state": "Trusted",
                        },
                        {
                            "id": "general-second",
                            "title": "General second",
                            "context": "General",
                            "technology": "",
                            "task": "",
                            "type": "copy_text",
                            "value": "Second",
                            "state": "Draft",
                        },
                    ]
                },
            )
            contexts_path = self._write_json(data / "contexts.json", {"contexts": []})
            command_surface_path = self._write_json(
                data / "command_surface.json",
                {"groups": []},
            )
            palette_path = self._write_json(data / "palette.json", {})
            inbox_path = self._write_json(data / "inbox.json", {"items": []})
            cheatsheets_dir = data / "cheatsheets"
            cheatsheets_dir.mkdir()

            root = tk.Tk()
            root_destroyed = False
            try:
                with (
                    patch(
                        "context_palette.launcher.SingleInstanceServer.start",
                        return_value=True,
                    ) as start_server,
                    patch(
                        "context_palette.launcher.SingleInstanceServer.stop"
                    ) as stop_server,
                    patch(
                        "context_palette.launcher.GlobalHotkey.start",
                        return_value=False,
                    ) as start_hotkey,
                    patch("context_palette.launcher.GlobalHotkey.stop") as stop_hotkey,
                ):
                    app = LauncherApp(
                        root,
                        actions_path,
                        data / "local_actions.json",
                        contexts_path,
                        data / "local_contexts.json",
                        command_surface_path,
                        data / "local_command_surface.json",
                        palette_path,
                        inbox_path,
                        cheatsheets_dir,
                        instance_port=0,
                    )

                    root.update()
                    app._set_initial_main_split()
                    root.update_idletasks()

                    self.assertEqual(root.title(), "Context Palette")
                    self.assertTrue(root.winfo_exists())
                    self.assertIsNotNone(app.search_entry)
                    self.assertEqual(root.winfo_width(), 780)
                    self._assert_balanced_panes(app)
                    self.assertIs(app.passwords_button.master, app.actions_tool_rail)
                    self.assertIs(app.type_filter.master, app.actions_tool_rail)
                    self.assertIs(app.tag_filter.master, app.actions_tool_rail)
                    self.assertIs(app.run_button.master, app.actions_tool_rail)
                    self.assertIs(app.action_help_button.master, app.actions_tool_rail)
                    self.assertEqual(app.actions_tool_rail.winfo_width(), 88)
                    self.assertGreaterEqual(app.results.winfo_width(), 220)
                    self.assertEqual(app.passwords_button.cget("text"), "Passwords")
                    self.assertEqual(app.tag_filter.cget("text"), "Tags ▾")
                    self.assertEqual(app.type_filter.cget("text"), "Types ▾")
                    self.assertEqual(app.run_button.cget("text"), "Run")
                    self.assertEqual(app.action_help_button.cget("text"), "?")
                    self.assertIs(app.search_entry.tk_focusNext(), app.passwords_button)
                    self.assertIs(app.passwords_button.tk_focusNext(), app.type_filter)
                    self.assertIs(app.type_filter.tk_focusNext(), app.tag_filter)
                    self.assertIs(app.tag_filter.tk_focusNext(), app.run_button)
                    self.assertIs(app.run_button.tk_focusNext(), app.action_help_button)
                    self.assertIs(app.action_help_button.tk_focusNext(), app.results)

                    app.passwords_button.invoke()
                    self.assertEqual(app.action_type_filter, "paste_credential")
                    self.assertEqual(app.passwords_button.cget("style"), "Accent.TButton")
                    app.passwords_button.invoke()
                    self.assertIsNone(app.action_type_filter)

                    type_menu = root.nametowidget(app.type_filter.cget("menu"))
                    open_url_index = next(
                        index
                        for index in range(type_menu.index(tk.END) + 1)
                        if type_menu.type(index) == "radiobutton"
                        and type_menu.entrycget(index, "label") == "Open a website"
                    )
                    type_menu.invoke(open_url_index)
                    self.assertEqual(app.action_type_filter, "open_url")
                    type_menu.invoke(0)
                    self.assertIsNone(app.action_type_filter)

                    tag_menu = root.nametowidget(app.tag_filter.cget("menu"))
                    database_tag_index = next(
                        index
                        for index in range(tag_menu.index(tk.END) + 1)
                        if tag_menu.type(index) == "radiobutton"
                        and tag_menu.entrycget(index, "label") == "database"
                    )
                    tag_menu.invoke(database_tag_index)
                    self.assertEqual(app.action_tag_filter, "database")
                    self.assertEqual(
                        [action.id for action in app.filtered_actions],
                        ["database-only"],
                    )
                    tag_menu.invoke(0)
                    self.assertIsNone(app.action_tag_filter)

                    app._activate_focus_actions()
                    root.update()
                    self.assertEqual(app.results_view, "focus")
                    self.assertIs(root.focus_get(), app.focus_tree)
                    self.assertEqual(
                        {action.id for action in app.focus_tree_actions.values()},
                        {"general-first", "general-second", "database-only"},
                    )
                    app._show_flat_results()
                    app._render_focus_actions()
                    self.assertEqual(app._selected_action().id, "general-first")
                    app.context_var.set("Database")
                    app._change_focus_context()
                    app.context_var.set("General")
                    app._change_focus_context()

                    app.search_var.set("Database only")
                    self._wait_for_search_refresh(root)
                    self.assertEqual(app.results_view, "flat")
                    self.assertEqual(
                        [action.id for action in app.displayed_actions],
                        ["database-only"],
                    )

                    app.context_var.set("Database")
                    app._change_focus_context()
                    self.assertEqual(app.results_view, "flat")
                    self.assertEqual(
                        [action.id for action in app.displayed_actions],
                        ["database-only"],
                    )

                    app.search_var.set("")
                    self._wait_for_search_refresh(root)
                    self.assertEqual(app.results_view, "focus")
                    self.assertEqual(
                        {action.id for action in app.focus_tree_actions.values()},
                        {"database-only"},
                    )

                    app.focus_actions_mode = False
                    app._refresh_results()
                    action_share = (
                        app.actions_panel.winfo_width()
                        / app.action_console.winfo_width()
                    )
                    self.assertGreaterEqual(action_share, 0.42)
                    self.assertLessEqual(action_share, 0.46)

                    group_areas = [
                        child
                        for child in app.command_tiles_frame.winfo_children()
                        if isinstance(child, ttk.LabelFrame)
                        and child.cget("text") != "Frequent passwords"
                    ]
                    self.assertEqual(
                        [area.cget("text") for area in group_areas],
                        ["Knowledge"] + [group.label for group in app.command_groups],
                    )
                    password_row_count = 1 if any(
                        isinstance(child, ttk.LabelFrame)
                        and child.cget("text") == "Frequent passwords"
                        for child in app.command_tiles_frame.winfo_children()
                    ) else 0
                    knowledge_area = group_areas[0]
                    self.assertEqual(int(knowledge_area.grid_info()["row"]), password_row_count)
                    self.assertEqual(int(knowledge_area.grid_info()["column"]), 0)
                    self.assertEqual(int(knowledge_area.grid_info()["columnspan"]), 2)
                    group_row_offset = password_row_count + 1
                    for index, (area, group) in enumerate(
                        zip(group_areas[1:], app.command_groups)
                    ):
                        expected_row, expected_column = divmod(index, 2)
                        self.assertEqual(
                            int(area.grid_info()["row"]),
                            expected_row + group_row_offset,
                        )
                        self.assertEqual(
                            int(area.grid_info()["column"]),
                            expected_column,
                        )
                        menu_launchers = [
                            child
                            for child in area.winfo_children()
                            if isinstance(child, ttk.Label)
                            and child.cget("style") == "SurfaceMenu.TLabel"
                        ]
                        self.assertEqual(
                            [control.cget("text") for control in menu_launchers],
                            [item.label for item in group.items],
                        )
                        for row, control in enumerate(menu_launchers):
                            self.assertEqual(int(control.grid_info()["row"]), row)
                            self.assertEqual(int(control.grid_info()["column"]), 0)
                            self.assertEqual(control.cget("anchor"), "w")
                            self.assertTrue(control.cget("takefocus"))
                            for sequence in (
                                "<Button-1>",
                                "<Button-3>",
                                "<Return>",
                                "<space>",
                            ):
                                self.assertTrue(control.bind(sequence))
                    start_server.assert_called_once_with()
                    start_hotkey.assert_called_once_with()

                    root.geometry("780x600")
                    root.update()
                    self._assert_balanced_panes(app)
                    self.assertGreater(app.results_container.winfo_height(), 150)
                    self.assertGreater(app.workspace_container.winfo_height(), 130)
                    root_bottom = root.winfo_rooty() + root.winfo_height()
                    visible_buttons = [
                        widget
                        for widget in self._descendants(root)
                        if isinstance(widget, ttk.Button) and widget.winfo_ismapped()
                    ]
                    self.assertTrue(visible_buttons)
                    for button in visible_buttons:
                        self.assertLessEqual(
                            button.winfo_rooty() + button.winfo_height(),
                            root_bottom,
                            f"{button}: {button.cget('text')}",
                        )
                    icon_buttons = [
                        button
                        for button in visible_buttons
                        if button.cget("style") == "Icon.TButton"
                    ]
                    self.assertEqual(
                        [button.cget("text") for button in icon_buttons],
                        ["+", "▣", "✎", "⌖", "✓", "?", "−", "×"],
                    )
                    tooltips = {
                        tooltip.widget: tooltip.text
                        for tooltip in app.widget_tooltips
                        if isinstance(tooltip.text, str)
                    }
                    expected_names = (
                        "Capture",
                        "Inbox",
                        "Edit",
                        "Pin",
                        "Trust",
                        "Help",
                        "Hide",
                        "Quit",
                    )
                    for button, name in zip(icon_buttons, expected_names):
                        self.assertTrue(tooltips[button].startswith(f"{name} —"))

                    transform_groups = [
                        app.workspace_transform_menu.entrycget(index, "label")
                        for index in range(len(WORKSPACE_TRANSFORM_GROUPS))
                    ]
                    self.assertEqual(
                        transform_groups,
                        [group.label for group in WORKSPACE_TRANSFORM_GROUPS],
                    )
                    transform_commands: list[str] = []
                    for index in range(len(WORKSPACE_TRANSFORM_GROUPS)):
                        submenu = root.nametowidget(
                            app.workspace_transform_menu.entrycget(index, "menu")
                        )
                        transform_commands.extend(
                            submenu.entrycget(command_index, "label")
                            for command_index in range(submenu.index(tk.END) + 1)
                        )
                    self.assertEqual(
                        transform_commands,
                        [
                            transform.label
                            for group in WORKSPACE_TRANSFORM_GROUPS
                            for transform in group.transforms
                        ],
                    )

                    copied: list[str] = []
                    case_menu = root.nametowidget(
                        app.workspace_transform_menu.entrycget(0, "menu")
                    )
                    proper_case_index = next(
                        index
                        for index in range(case_menu.index(tk.END) + 1)
                        if case_menu.entrycget(index, "label") == "Proper Case"
                    )
                    app._set_workspace_text("hELLO wORLD")
                    with patch.object(app, "_set_clipboard", copied.append):
                        case_menu.invoke(proper_case_index)
                    self.assertEqual(app._workspace_text(), "Hello World")
                    self.assertEqual(copied, ["Hello World"])

                    lines_menu = root.nametowidget(
                        app.workspace_transform_menu.entrycget(2, "menu")
                    )
                    sql_index = next(
                        index
                        for index in range(lines_menu.index(tk.END) + 1)
                        if lines_menu.entrycget(index, "label")
                        == "Format as SQL value list"
                    )
                    app._set_workspace_text("1\nO'Brien")
                    with patch.object(app, "_set_clipboard", copied.append):
                        lines_menu.invoke(sql_index)
                    self.assertEqual(app._workspace_text(), "(1, 'O''Brien')")
                    self.assertEqual(copied[-1], "(1, 'O''Brien')")

                    app._set_workspace_text("One TWO\nThree")
                    app.workspace.tag_add(tk.SEL, "1.4", "1.7")
                    with patch.object(app, "_set_clipboard", copied.append):
                        app._transform_workspace("lowercase", "lowercase")
                    self.assertEqual(app._workspace_text(), "One two\nThree")
                    self.assertEqual(copied[-1], "two")
                    self.assertIn("selection", app.status_var.get())

                    app.workspace.tag_remove(tk.SEL, "1.0", tk.END)
                    with patch.object(app, "_set_clipboard", copied.append):
                        app._transform_workspace("uppercase", "UPPERCASE")
                    self.assertEqual(app._workspace_text(), "ONE TWO\nTHREE")
                    self.assertEqual(copied[-1], "ONE TWO\nTHREE")
                    self.assertIn("complete field", app.status_var.get())

                    with (
                        patch.object(root, "clipboard_get", return_value="Captured selection"),
                        patch.object(app, "show_window"),
                    ):
                        app._finish_selection_capture({})
                    self.assertEqual(app.captured_selection, "Captured selection")
                    self.assertEqual(app._workspace_text(), "Captured selection")

                    root.geometry("780x1000")
                    root.update()
                    self._assert_balanced_panes(app)

                    pane_height = app.main_content.winfo_height()
                    app.main_content.sashpos(0, int(pane_height * 0.60))
                    app._remember_main_split(None)  # type: ignore[arg-type]
                    self.assertAlmostEqual(app.main_split_ratio, 0.60, places=2)
                    app.main_content.sashpos(0, int(pane_height * 0.45))
                    app._remember_main_split(None)  # type: ignore[arg-type]
                    self.assertAlmostEqual(app.main_split_ratio, 0.45, places=2)
                    app.main_content.sashpos(0, 0)
                    app._remember_main_split(None)  # type: ignore[arg-type]
                    self.assertGreaterEqual(
                        app.results_container.winfo_height(),
                        MINIMUM_ACTION_CONSOLE_HEIGHT,
                    )
                    app.main_content.sashpos(0, pane_height)
                    app._remember_main_split(None)  # type: ignore[arg-type]
                    self.assertGreaterEqual(
                        app.workspace_container.winfo_height(),
                        MINIMUM_WORKSPACE_HEIGHT,
                    )
                    app.main_split_ratio = 0.52
                    app._set_initial_main_split()

                    console_width = app.action_console.winfo_width()
                    app.action_console.sashpos(0, 0)
                    app._remember_action_console_split(None)  # type: ignore[arg-type]
                    self.assertGreaterEqual(
                        app.actions_panel.winfo_width(),
                        MINIMUM_ACTIONS_WIDTH,
                    )
                    app.action_console.sashpos(0, console_width)
                    app._remember_action_console_split(None)  # type: ignore[arg-type]
                    self.assertGreaterEqual(
                        app.command_surface_panel.winfo_width(),
                        MINIMUM_QUICK_ACTIONS_WIDTH,
                    )
                    app.action_console_ratio = 0.44
                    app._set_initial_action_console_split()

                    stable_tooltip_count = len(app.widget_tooltips)
                    surface_tooltip_count = len(app.command_surface_tooltips)
                    for _index in range(5):
                        app._render_command_surface()
                    root.update_idletasks()
                    self.assertEqual(len(app.widget_tooltips), stable_tooltip_count)
                    self.assertEqual(
                        len(app.command_surface_tooltips),
                        surface_tooltip_count,
                    )

                    self.assertEqual(
                        [
                            app.manage_focus_menu.entrycget(index, "label")
                            for index in (0, 2)
                        ],
                        ["Manage focuses…", "Configure actions and buttons…"],
                    )
                    self.assertEqual(app.manage_focus_menu.type(1), "separator")

                    for menu_index, expected_tab in ((0, "Contexts"), (2, "Actions")):
                        app.manage_focus_menu.invoke(menu_index)
                        root.update()
                        configuration_windows = [
                            child
                            for child in root.winfo_children()
                            if isinstance(child, tk.Toplevel)
                            and child.title() == "Configure Context Palette"
                        ]
                        self.assertEqual(len(configuration_windows), 1)
                        notebook = next(
                            child
                            for child in self._descendants(configuration_windows[0])
                            if isinstance(child, ttk.Notebook)
                        )
                        self.assertEqual(
                            notebook.tab(notebook.select(), "text"),
                            expected_tab,
                        )
                        configuration_windows[0].destroy()
                        root.update()

                    for help_button in (
                        app.global_help_button,
                        app.action_help_button,
                    ):
                        help_button.invoke()
                        root.update()
                        help_windows = [
                            child
                            for child in root.winfo_children()
                            if isinstance(child, tk.Toplevel)
                            and child.title() == "Context Palette Help"
                        ]
                        self.assertEqual(len(help_windows), 1)
                        help_windows[0].destroy()
                        root.update()

                    app._show_cheatsheets()
                    root.update()
                    sheet_windows = [
                        child
                        for child in root.winfo_children()
                        if isinstance(child, tk.Toplevel)
                        and child.title() == "Context Palette Cheat Sheets"
                    ]
                    self.assertEqual(len(sheet_windows), 1)
                    sheet_windows[0].destroy()
                    root.update()

                    app.quit_app()
                    root_destroyed = True

                    stop_hotkey.assert_called_once_with()
                    stop_server.assert_called_once_with()
            finally:
                if not root_destroyed:
                    root.destroy()

    def _write_json(self, path: Path, value: object) -> Path:
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def _wait_for_search_refresh(self, root: tk.Tk) -> None:
        root.after(60, root.quit)
        root.mainloop()

    def _descendants(self, widget: tk.Misc) -> list[tk.Misc]:
        descendants: list[tk.Misc] = []
        for child in widget.winfo_children():
            descendants.append(child)
            descendants.extend(self._descendants(child))
        return descendants

    def _assert_balanced_panes(self, app: LauncherApp) -> None:
        action_height = app.results_container.winfo_height()
        workspace_height = app.workspace_container.winfo_height()
        action_share = action_height / (action_height + workspace_height)
        self.assertGreaterEqual(action_share, 0.50)
        self.assertLessEqual(action_share, 0.55)


if __name__ == "__main__":
    unittest.main()
