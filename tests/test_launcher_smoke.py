from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.launcher import (
    MINIMUM_COMMAND_CONSOLE_WIDTH,
    MINIMUM_WORKSPACE_WIDTH,
    LauncherApp,
)
from context_palette.actions import Action, transform_text_file
from context_palette.action_discovery_panel import (
    FOCUS_GROUP_ROW_TAG,
    FOCUS_SLOT_ROW_TAG,
    PINNED_SLOT_ROW_TAG,
)
from context_palette.action_types import ACTION_TYPES, CREATABLE_ACTION_TYPES
from context_palette.command_surface import (
    CommandGroup,
    CommandItem,
    GROUP_PRESENTATION_NESTED_MENU,
)
from context_palette.configuration_window import (
    ConfigurationWindow,
    LOCAL_DESTINATION,
)
from context_palette.contexts import ContextDefinition
from context_palette.data_catalog import AppDataPaths
from context_palette.focus_model import palette_items_for_context
from context_palette.palette_state import PaletteState
from context_palette.workspace_transforms import WORKSPACE_TRANSFORM_GROUPS
from context_palette.workspace_panel import WorkspacePanel


@unittest.skipUnless(sys.platform == "win32", "The launcher smoke test requires Windows Tk.")
class LauncherSmokeTests(unittest.TestCase):
    def test_workspace_create_action_uses_selection_then_full_text_without_clipboard(self):
        root = tk.Tk()
        root.withdraw()
        host = ttk.Frame(root)
        host.pack(fill=tk.BOTH, expand=True)
        sources: list[str] = []
        clipboard_getter = Mock(side_effect=AssertionError("clipboard must not be read"))
        panel = WorkspacePanel(
            host,
            clipboard_getter=clipboard_getter,
            clipboard_setter=lambda _value: None,
            status_setter=lambda _value: None,
            tooltip_adder=lambda _widget, _text: None,
            create_action=sources.append,
        )
        try:
            self.assertEqual(str(panel.create_action_button.cget("state")), "disabled")
            panel.set_text("Notes before https://example.com/report after")
            root.update()
            start = panel.text.search("https://", "1.0")
            end = panel.text.index(f"{start}+26c")
            panel.text.tag_add(tk.SEL, start, end)

            panel.create_action_button.invoke()
            self.assertEqual(sources, ["https://example.com/report"])

            panel.text.tag_remove(tk.SEL, "1.0", tk.END)
            panel.create_action_button.invoke()
            self.assertEqual(
                sources[-1],
                "Notes before https://example.com/report after",
            )
            clipboard_getter.assert_not_called()
        finally:
            root.destroy()

    def test_file_transform_preview_exposes_guarded_replace_and_clears_on_new_input(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source.txt"
            source.write_text("Alpha\r\n", encoding="utf-8", newline="")
            preview = transform_text_file(str(source), ("uppercase",))
            root = tk.Tk()
            root.withdraw()
            host = ttk.Frame(root)
            host.pack(fill=tk.BOTH, expand=True)
            statuses: list[str] = []
            panel = WorkspacePanel(
                host,
                clipboard_getter=lambda: "",
                clipboard_setter=lambda _value: None,
                status_setter=statuses.append,
                tooltip_adder=lambda _widget, _text: None,
            )
            try:
                panel.show_file_preview(preview)
                root.update_idletasks()

                self.assertTrue(panel.file_preview_frame.winfo_manager())
                self.assertEqual(panel.raw_text(), "ALPHA\r\n")
                self.assertIn(str(source), panel.file_preview_path_var.get())
                with patch(
                    "context_palette.workspace_panel.messagebox.askyesno",
                    return_value=True,
                ):
                    panel.replace_preview_source()
                with source.open(encoding="utf-8", newline="") as stream:
                    self.assertEqual(stream.read(), "ALPHA\r\n")
                self.assertIn("Replaced original text file", statuses[-1])

                panel.set_text("Unrelated workspace text")
                self.assertIsNone(panel.file_preview)
                self.assertFalse(panel.file_preview_frame.winfo_manager())
            finally:
                root.destroy()

    def test_clean_pc_loads_built_in_configuration_without_creating_local_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            data = Path(temporary_directory)
            for filename in ("actions.json", "contexts.json", "command_surface.json"):
                (data / filename).write_bytes((ROOT / "data" / filename).read_bytes())
            built_in_action_count = len(
                json.loads((data / "actions.json").read_text(encoding="utf-8"))[
                    "actions"
                ]
            )
            built_in_group_count = len(
                json.loads(
                    (data / "command_surface.json").read_text(encoding="utf-8")
                )["groups"]
            )
            cheatsheets_dir = data / "cheatsheets"
            cheatsheets_dir.mkdir()
            local_paths = tuple(
                data / filename
                for filename in (
                    "local_actions.json",
                    "local_contexts.json",
                    "local_command_surface.json",
                    "palette.json",
                    "inbox.json",
                    "local_work_item_sources.json",
                    "local_work_item_metadata.json",
                    "local_work_item_settings.json",
                )
            )
            self.assertFalse(any(path.exists() for path in local_paths))

            root = tk.Tk()
            root_destroyed = False
            try:
                with (
                    patch(
                        "context_palette.launcher.SingleInstanceServer.start",
                        return_value=True,
                    ),
                    patch("context_palette.launcher.SingleInstanceServer.stop"),
                    patch(
                        "context_palette.launcher.GlobalHotkey.start",
                        return_value=False,
                    ),
                    patch("context_palette.launcher.GlobalHotkey.stop"),
                    patch(
                        "context_palette.launcher.messagebox.showerror"
                    ) as error,
                ):
                    app = LauncherApp(
                        root,
                        data / "actions.json",
                        data / "local_actions.json",
                        data / "contexts.json",
                        data / "local_contexts.json",
                        data / "command_surface.json",
                        data / "local_command_surface.json",
                        data / "palette.json",
                        data / "inbox.json",
                        cheatsheets_dir,
                        instance_port=0,
                    )
                    root.update()

                    self.assertEqual(len(app.actions), built_in_action_count)
                    action_rows = tuple(
                        app.focus_tree.item(item_id, "text")
                        for item_id in app.focus_tree.get_children()
                    )
                    number_prefixes = tuple(f"{number}. " for number in "1234567890")
                    self.assertFalse(
                        any(row.startswith(number_prefixes) for row in action_rows)
                    )
                    self.assertTrue(
                        any(
                            FOCUS_SLOT_ROW_TAG
                            in app.focus_tree.item(item_id, "tags")
                            for item_id in app.focus_tree.get_children()
                        )
                    )
                    self.assertTrue(
                        all(
                            " - " not in row
                            for row in action_rows
                            if row.strip()
                        )
                    )
                    self.assertEqual(app.discovery_scope, "all")
                    self.assertEqual(app.actions_heading_var.get(), "All items")
                    self.assertEqual(app.local_action_ids, set())
                    self.assertEqual(
                        [context.name for context in app.context_definitions],
                        ["Developing Context Palette"],
                    )
                    self.assertEqual(len(app.command_groups), built_in_group_count)
                    self.assertEqual(app.palette_state.focus_context, "General")
                    self.assertEqual(app.work_item_sources, ())
                    self.assertEqual(
                        app.data_paths,
                        AppDataPaths.from_data_directory(data),
                    )
                    self.assertEqual(
                        app.local_work_item_sources_path,
                        app.data_paths.work_item_sources_file,
                    )
                    self.assertEqual(
                        app.local_work_item_metadata_path,
                        app.data_paths.work_item_metadata_file,
                    )
                    self.assertEqual(
                        app.local_work_item_settings_path,
                        app.data_paths.work_item_settings_file,
                    )
                    self.assertFalse(any(path.exists() for path in local_paths))

                    app._show_configuration()
                    root.update()
                    configure_windows = [
                        child
                        for child in root.winfo_children()
                        if isinstance(child, tk.Toplevel)
                        and child.title() == "Configure Context Palette"
                    ]
                    self.assertEqual(len(configure_windows), 1)
                    trees_by_heading = {
                        tree.heading("#0", "text"): tree
                        for tree in self._descendants(configure_windows[0])
                        if isinstance(tree, ttk.Treeview)
                    }
                    self.assertEqual(
                        len(trees_by_heading["Action"].get_children()),
                        len(app.actions),
                    )
                    self.assertEqual(
                        len(trees_by_heading["Context"].get_children()),
                        1,
                    )
                    self.assertEqual(
                        len(
                            trees_by_heading[
                                "Group / menu level"
                            ].get_children()
                        ),
                        len(app.command_groups) + 3,
                    )
                    configure_windows[0].geometry("700x480")
                    root.update()
                    configure_notebook = next(
                        child
                        for child in self._descendants(configure_windows[0])
                        if isinstance(child, ttk.Notebook)
                    )
                    for tab_index, heading, last_column in (
                        (1, "Action", "state"),
                        (3, "Context", "actions"),
                        (4, "Group / menu level", "actions"),
                    ):
                        configure_notebook.select(tab_index)
                        root.update()
                        tree = trees_by_heading[heading]
                        self.assertTrue(
                            any(
                                isinstance(child, ttk.Scrollbar)
                                for child in tree.master.winfo_children()
                            ),
                            f"{heading} list has no visible scrollbar",
                        )
                        first_item = tree.get_children()[0]
                        bounds = tree.bbox(first_item, last_column)
                        self.assertTrue(bounds)
                        self.assertLessEqual(
                            bounds[0] + bounds[2],
                            tree.winfo_width(),
                            f"{heading} list clips its final column",
                        )
                    error.assert_not_called()
                    self.assertFalse(any(path.exists() for path in local_paths))

                    configure_windows[0].destroy()
                    app.quit_app()
                    root_destroyed = True
            finally:
                if not root_destroyed:
                    root.destroy()

    def test_clean_pc_creates_first_personal_records_and_reloads_them(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            data = Path(temporary_directory)
            for filename in ("actions.json", "contexts.json", "command_surface.json"):
                (data / filename).write_bytes((ROOT / "data" / filename).read_bytes())
            cheatsheets_dir = data / "cheatsheets"
            cheatsheets_dir.mkdir()
            local_actions = data / "local_actions.json"
            local_contexts = data / "local_contexts.json"
            local_surface = data / "local_command_surface.json"
            unrelated_private_paths = tuple(
                data / filename
                for filename in (
                    "palette.json",
                    "inbox.json",
                    "local_work_item_sources.json",
                    "local_work_item_metadata.json",
                    "local_work_item_settings.json",
                )
            )

            root = tk.Tk()
            first_root_destroyed = False
            try:
                with (
                    patch(
                        "context_palette.launcher.SingleInstanceServer.start",
                        return_value=True,
                    ),
                    patch("context_palette.launcher.SingleInstanceServer.stop"),
                    patch(
                        "context_palette.launcher.GlobalHotkey.start",
                        return_value=False,
                    ),
                    patch("context_palette.launcher.GlobalHotkey.stop"),
                    patch(
                        "context_palette.configuration_window.messagebox.showerror"
                    ) as error,
                ):
                    app = LauncherApp(
                        root,
                        data / "actions.json",
                        local_actions,
                        data / "contexts.json",
                        local_contexts,
                        data / "command_surface.json",
                        local_surface,
                        data / "palette.json",
                        data / "inbox.json",
                        cheatsheets_dir,
                        instance_port=0,
                    )
                    configuration = ConfigurationWindow(
                        root,
                        actions=app.actions,
                        local_action_ids=app.local_action_ids,
                        shared_actions_path=data / "actions.json",
                        local_actions_path=local_actions,
                        contexts_path=data / "contexts.json",
                        local_contexts_path=local_contexts,
                        command_surface_path=data / "command_surface.json",
                        local_command_surface_path=local_surface,
                        palette_path=data / "palette.json",
                        work_item_sources_path=data / "local_work_item_sources.json",
                        work_item_metadata_path=data / "local_work_item_metadata.json",
                        work_item_settings_path=data / "local_work_item_settings.json",
                        work_item_sources=app.work_item_sources,
                        work_item_metadata=app.work_item_metadata,
                        work_item_index=app.work_item_index,
                        on_change=app._reload,
                        initial_tab="actions",
                    )
                    personal_action = Action(
                        "personal-first",
                        "Personal first action",
                        "General",
                        "copy_text",
                        "Hello",
                    )
                    personal_context = ContextDefinition(
                        "Personal focus",
                        preferred_action_ids=(personal_action.id,),
                        action_ids=(personal_action.id,),
                    )
                    personal_group = CommandGroup(
                        "personal-tools",
                        "Personal tools",
                        (
                            CommandItem(
                                "personal-first-button",
                                "Personal first",
                                action_ids=(personal_action.id,),
                            ),
                        ),
                    )

                    self.assertTrue(
                        configuration._save_action(
                            personal_action,
                            LOCAL_DESTINATION,
                        )
                    )
                    self.assertTrue(
                        configuration._save_context(
                            personal_context,
                            "",
                            target_path=local_contexts,
                        )
                    )
                    self.assertTrue(
                        configuration._save_group(
                            personal_group,
                            "",
                            LOCAL_DESTINATION,
                        )
                    )
                    root.update()

                    self.assertEqual(len(configuration.pin_comboboxes), 5)
                    self.assertTrue(configuration.save_pins_button.winfo_ismapped())
                    self.assertLessEqual(
                        configuration.pins_frame.winfo_reqwidth(),
                        configuration.window.winfo_width(),
                    )
                    for index, definition in enumerate(CREATABLE_ACTION_TYPES.values()):
                        self.assertTrue(
                            configuration.type_list.get(index).startswith(
                                f"{definition.icon} "
                            )
                        )
                    self.assertTrue(local_actions.exists())
                    self.assertTrue(local_contexts.exists())
                    self.assertTrue(local_surface.exists())
                    self.assertFalse(
                        any(path.exists() for path in unrelated_private_paths)
                    )
                    error.assert_not_called()

                    configuration.window.destroy()
                    app.quit_app()
                    first_root_destroyed = True
            finally:
                if not first_root_destroyed:
                    root.destroy()

            restarted_root = tk.Tk()
            restarted_root_destroyed = False
            try:
                with (
                    patch(
                        "context_palette.launcher.SingleInstanceServer.start",
                        return_value=True,
                    ),
                    patch("context_palette.launcher.SingleInstanceServer.stop"),
                    patch(
                        "context_palette.launcher.GlobalHotkey.start",
                        return_value=False,
                    ),
                    patch("context_palette.launcher.GlobalHotkey.stop"),
                    patch(
                        "context_palette.launcher.messagebox.showerror"
                    ) as restart_error,
                ):
                    restarted = LauncherApp(
                        restarted_root,
                        data / "actions.json",
                        local_actions,
                        data / "contexts.json",
                        local_contexts,
                        data / "command_surface.json",
                        local_surface,
                        data / "palette.json",
                        data / "inbox.json",
                        cheatsheets_dir,
                        instance_port=0,
                    )
                    restarted_root.update()

                    self.assertIn(
                        personal_action.id,
                        {action.id for action in restarted.actions},
                    )
                    self.assertEqual(
                        restarted.local_action_ids,
                        {personal_action.id},
                    )
                    self.assertIn(
                        personal_context.name,
                        {context.name for context in restarted.context_definitions},
                    )
                    reloaded_group = next(
                        group
                        for group in restarted.command_groups
                        if group.id == personal_group.id
                    )
                    self.assertEqual(
                        reloaded_group.items[0].action_ids,
                        (personal_action.id,),
                    )
                    self.assertFalse(
                        any(path.exists() for path in unrelated_private_paths)
                    )
                    restart_error.assert_not_called()

                    restarted.quit_app()
                    restarted_root_destroyed = True
            finally:
                if not restarted_root_destroyed:
                    restarted_root.destroy()

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
                            "state": "Active",
                        },
                        {
                            "id": "database-only",
                            "title": "Database only",
                            "context": "Database",
                            "technology": "Database",
                            "task": "Lookup",
                            "type": "copy_text",
                            "value": "Database",
                            "state": "Active",
                        },
                        {
                            "id": "general-second",
                            "title": "General second",
                            "context": "General",
                            "technology": "",
                            "task": "",
                            "type": "copy_text",
                            "value": "Second",
                            "state": "Active",
                        },
                    ]
                },
            )
            contexts_path = self._write_json(data / "contexts.json", {"contexts": []})
            self._write_json(
                data / "local_contexts.json",
                {
                    "contexts": [
                        {
                            "name": "Review",
                            "action_ids": ["general-first"],
                            "work_item_refs": [
                                {
                                    "source_id": "cap40",
                                    "relative_folder": (
                                        "ISS-CAP40-AB9C-age-verification"
                                    ),
                                }
                            ],
                        },
                        {
                            "name": "Database",
                            "action_ids": ["database-only"],
                            "work_item_refs": [
                                {
                                    "source_id": "cap40",
                                    "relative_folder": "QST-CAP40-question",
                                }
                            ],
                        }
                    ]
                },
            )
            command_surface_path = self._write_json(
                data / "command_surface.json",
                {"groups": []},
            )
            local_command_surface_path = self._write_json(
                data / "local_command_surface.json",
                {
                    "groups": [
                        {
                            "id": "single-row",
                            "label": "Single-row group",
                            "items": [
                                {
                                    "id": "single-row-action",
                                    "label": "Single row",
                                    "primary_action_id": "general-first",
                                }
                            ],
                        },
                        {
                            "id": "multiple-rows",
                            "label": "Multiple-row group",
                            "items": [
                                {
                                    "id": "first-row",
                                    "label": "First row",
                                    "primary_action_id": "general-first",
                                },
                                {
                                    "id": "second-row",
                                    "label": "Second row",
                                    "primary_action_id": "general-second",
                                },
                            ],
                        },
                    ]
                },
            )
            palette_path = self._write_json(data / "palette.json", {})
            inbox_path = self._write_json(data / "inbox.json", {"items": []})
            cheatsheets_dir = data / "cheatsheets"
            cheatsheets_dir.mkdir()
            workitems = data / "work-source" / "workitems"
            exact_folder = workitems / "ISS-CAP40-AB9C-age-verification"
            exact_folder.mkdir(parents=True)
            exact_workbook = exact_folder / f"{exact_folder.name}.xlsx"
            exact_workbook.write_text("", encoding="utf-8")
            (workitems / "QST-CAP40-question").mkdir()
            self._write_json(
                data / "local_work_item_sources.json",
                {
                    "sources": [
                        {
                            "id": "cap40",
                            "name": "CAP40 Product",
                            "workitems_path": str(workitems),
                        }
                    ]
                },
            )
            self._write_json(
                data / "local_work_item_metadata.json",
                {
                    "work_items": {
                        "cap40/ISS-CAP40-AB9C-age-verification": {
                            "tags": ["urgent", "database"]
                        }
                    }
                },
            )

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
                    patch("context_palette.launcher.open_action_target") as open_target,
                ):
                    app = LauncherApp(
                        root,
                        actions_path,
                        data / "local_actions.json",
                        contexts_path,
                        data / "local_contexts.json",
                        command_surface_path,
                        local_command_surface_path,
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
                    self.assertEqual(root.winfo_height(), 600)
                    self._assert_input_first_layout(app)
                    self.assertEqual(
                        app.main_content.master.winfo_children(),
                        [app.main_content],
                    )
                    self.assertIs(app.passwords_button.master, app.actions_tool_rail)
                    self.assertIs(app.new_work_item_button.master, app.actions_tool_rail)
                    self.assertIs(app.send_work_item_inbox_button.master, app.actions_tool_rail)
                    self.assertIs(app.copy_file_to_work_item_button.master, app.actions_tool_rail)
                    self.assertIs(app.type_filter.master, app.actions_tool_rail)
                    self.assertIs(app.tag_filter.master, app.actions_tool_rail)
                    self.assertIs(
                        app.run_button.master,
                        app.action_discovery_panel.primary_action_frame,
                    )
                    self.assertIs(
                        app.action_discovery_panel.primary_action_frame.master,
                        app.actions_tool_rail,
                    )
                    self.assertIs(
                        app.work_item_folder_button.master,
                        app.action_discovery_panel.primary_action_frame,
                    )
                    self.assertIs(app.action_help_button.master, app.app_controls)
                    self.assertIs(app.configure_button.master, app.app_controls)
                    self.assertIs(app.more_button.master, app.app_controls)
                    self.assertGreaterEqual(
                        app.actions_tool_rail.winfo_width(),
                        app.results.winfo_width() - 12,
                    )
                    initial_toolbar_width = app.actions_tool_rail.winfo_width()
                    initial_common_positions = {
                        widget: (widget.winfo_x(), widget.winfo_y())
                        for widget in (
                            app.new_action_button,
                            app.action_discovery_panel.edit_button,
                            app.action_discovery_panel.pin_button,
                            app.action_discovery_panel.primary_action_frame,
                        )
                    }
                    for scope_button in (
                        app.all_items_button,
                        app.actions_button,
                        app.work_items_button,
                    ):
                        self.assertGreaterEqual(
                            scope_button.winfo_width(),
                            scope_button.winfo_reqwidth(),
                        )
                    self.assertGreaterEqual(app.focus_tree.winfo_width(), 180)
                    self.assertEqual(app.focus_tree.cget("style"), "Flat.Treeview")
                    self.assertEqual(
                        app.passwords_button.cget("text"),
                        ACTION_TYPES["paste_credential"].icon,
                    )
                    self.assertEqual(app.new_work_item_button.cget("text"), "+W")
                    self.assertFalse(app.new_work_item_button.winfo_manager())
                    self.assertFalse(app.send_work_item_inbox_button.winfo_manager())
                    self.assertFalse(app.copy_file_to_work_item_button.winfo_manager())
                    self.assertEqual(app.tag_filter.cget("text"), "#")
                    self.assertFalse(app.type_filter.winfo_manager())
                    self.assertEqual(app.run_button.cget("text"), "Run")
                    self.assertFalse(app.work_item_folder_button.winfo_manager())
                    self.assertTrue(app.action_help_button.cget("image"))
                    self.assertTrue(app.scope_options_button.cget("image"))
                    self.assertIs(
                        app.scope_options_button.master,
                        app.search_entry.master,
                    )
                    self.assertFalse(
                        app.action_discovery_panel.find_label.winfo_manager()
                    )
                    self.assertTrue(root.bind("<F5>"))
                    self.assertTrue(root.bind("<Control-Shift-D>"))
                    focus_chain = (
                        app.context_picker,
                        app.focus_actions_button,
                        app.all_items_button,
                        app.actions_button,
                        app.work_items_button,
                    )
                    for current, following in zip(focus_chain, focus_chain[1:]):
                        self.assertIs(current.tk_focusNext(), following)

                    deadline = time.monotonic() + 2.0
                    while not app.work_item_index.items and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.01)
                    self.assertEqual(len(app.work_item_index.items), 2)
                    self.assertEqual(app.results_count_var.get(), "5 items")
                    self.assertEqual(
                        sum(
                            bool(reference.action_id)
                            for reference in app.focus_tree_items.values()
                        ),
                        3,
                    )
                    self.assertEqual(
                        sum(
                            reference.work_item_ref is not None
                            for reference in app.focus_tree_items.values()
                        ),
                        2,
                    )
                    app.palette_state = PaletteState(focus_context="Database")
                    database_work_item = next(
                        item
                        for item in app.work_item_index.items
                        if item.relative_folder == "QST-CAP40-question"
                    )
                    self.assertTrue(
                        app._work_item_belongs_to_context(
                            database_work_item,
                            "Database",
                        )
                    )
                    focus_members = palette_items_for_context(
                        app.actions,
                        "Database",
                        app.context_definitions,
                    )
                    self.assertEqual(
                        [
                            reference.action_id
                            or reference.work_item_ref.relative_folder
                            for reference in focus_members
                        ],
                        ["database-only", "QST-CAP40-question"],
                    )
                    app._refresh_results()
                    grouped_rows = list(app.focus_tree.get_children())
                    divider_row = next(
                        item_id
                        for item_id in grouped_rows
                        if FOCUS_GROUP_ROW_TAG
                        in app.focus_tree.item(item_id, "tags")
                    )
                    divider_index = grouped_rows.index(divider_row)
                    self.assertEqual(app.actions_heading_var.get(), "All items · Focus first")
                    self.assertEqual(app.results_count_var.get(), "5 items")
                    self.assertNotIn(divider_row, app.focus_tree_items)
                    self.assertEqual(divider_index, 4)
                    self.assertEqual(
                        [
                            reference.action_id
                            or reference.work_item_ref.relative_folder
                            for reference in app.focus_tree_items.values()
                        ][:4],
                        [
                            "database-only",
                            "general-first",
                            "general-second",
                            "QST-CAP40-question",
                        ],
                    )

                    last_focus_row = grouped_rows[divider_index - 1]
                    first_other_row = grouped_rows[divider_index + 1]
                    app.focus_tree.selection_set(last_focus_row)
                    app.focus_tree.focus(last_focus_row)
                    app.focus_tree.focus_force()
                    app.focus_tree.event_generate("<Down>")
                    root.update()
                    self.assertEqual(app.focus_tree.selection(), (first_other_row,))

                    app.focus_tree.selection_set(first_other_row)
                    app.focus_tree.focus(first_other_row)
                    divider_bounds = app.focus_tree.bbox(divider_row)
                    self.assertTrue(divider_bounds)
                    app.focus_tree.event_generate(
                        "<Button-1>",
                        x=divider_bounds[0] + 3,
                        y=divider_bounds[1] + 3,
                    )
                    root.update()
                    self.assertEqual(app.focus_tree.selection(), (first_other_row,))
                    with patch.object(app, "_execute_palette_item") as execute_item:
                        app.focus_tree.selection_set(divider_row)
                        app.focus_tree.focus(divider_row)
                        app.focus_tree.event_generate("<Return>")
                        root.update()
                        app._activate_mixed_tree_from_event(
                            type(
                                "PointerEvent",
                                (),
                                {
                                    "keysym": "",
                                    "y": divider_bounds[1] + 3,
                                },
                            )()
                        )
                    execute_item.assert_not_called()

                    app.search_var.set("question")
                    self._wait_for_search_refresh(root)
                    self.assertEqual(app.results_count_var.get(), "1 item")
                    self.assertEqual(
                        app.actions_heading_var.get(),
                        "All items · Focus first",
                    )
                    self.assertFalse(
                        any(
                            FOCUS_GROUP_ROW_TAG
                            in app.focus_tree.item(item_id, "tags")
                            for item_id in app.focus_tree.get_children()
                        )
                    )

                    app.search_var.set("age verification")
                    self._wait_for_search_refresh(root)
                    self.assertEqual(app.results_count_var.get(), "1 item")
                    self.assertEqual(app.actions_heading_var.get(), "All items")
                    self.assertEqual(
                        [
                            reference.work_item_ref.relative_folder
                            for reference in app.focus_tree_items.values()
                            if reference.work_item_ref is not None
                        ],
                        ["ISS-CAP40-AB9C-age-verification"],
                    )

                    app.search_var.set("")
                    self._wait_for_search_refresh(root)
                    app._select_item_context_filter("Review")
                    self.assertEqual(app.actions_heading_var.get(), "All items")
                    self.assertFalse(
                        any(
                            FOCUS_GROUP_ROW_TAG
                            in app.focus_tree.item(item_id, "tags")
                            for item_id in app.focus_tree.get_children()
                        )
                    )
                    app._select_item_context_filter(None)
                    self.assertEqual(
                        app.actions_heading_var.get(),
                        "All items · Focus first",
                    )

                    app.palette_state = PaletteState(
                        ("general-first",),
                        "General",
                        {"General": ("database-only",)},
                    )
                    app._refresh_results()
                    pinned_row = next(
                        item_id
                        for item_id, reference in app.focus_tree_items.items()
                        if reference.action_id == "general-first"
                        and PINNED_SLOT_ROW_TAG in app.focus_tree.item(item_id, "tags")
                    )
                    focus_row = next(
                        item_id
                        for item_id, reference in app.focus_tree_items.items()
                        if reference.action_id == "database-only"
                    )
                    self.assertFalse(app.focus_tree.item(pinned_row, "text").startswith("1. "))
                    self.assertFalse(app.focus_tree.item(focus_row, "text").startswith("6. "))
                    self.assertIn(
                        PINNED_SLOT_ROW_TAG,
                        app.focus_tree.item(pinned_row, "tags"),
                    )
                    self.assertIn(
                        FOCUS_SLOT_ROW_TAG,
                        app.focus_tree.item(focus_row, "tags"),
                    )
                    self.assertIn(
                        "Shortcut: Shift+1",
                        app._focus_tree_tooltip_text(pinned_row),
                    )
                    self.assertIn(
                        "Shortcut: Shift+6",
                        app._focus_tree_tooltip_text(focus_row),
                    )
                    app.palette_state = PaletteState()
                    app._refresh_results()
                    work_item_row = next(
                        item_id
                        for item_id, reference in app.focus_tree_items.items()
                        if reference.work_item_ref is not None
                    )
                    app.focus_tree.selection_set(work_item_row)
                    app.focus_tree.focus(work_item_row)
                    app._update_preview()
                    self.assertEqual(app.run_button.cget("text"), "Open")
                    self.assertEqual(str(app.run_button.cget("state")), "normal")
                    self.assertEqual(str(app.action_discovery_panel.edit_button.cget("state")), "normal")
                    self.assertEqual(str(app.action_discovery_panel.pin_button.cget("state")), "disabled")
                    self.assertTrue(app.work_item_folder_button.winfo_manager())
                    self.assertTrue(app.status_var.get().startswith("Input: none → Effect: open "))
                    self.assertIn("\n\nInput\nNo runtime input.", app.action_info_full)
                    self.assertIn("\n\nEffect\nOpen ", app.action_info_full)
                    folder_only_row = next(
                        item_id
                        for item_id, reference in app.focus_tree_items.items()
                        if reference.work_item_ref is not None
                        and reference.work_item_ref.relative_folder
                        == "QST-CAP40-question"
                    )
                    app.focus_tree.selection_set(folder_only_row)
                    app.focus_tree.focus(folder_only_row)
                    app._update_preview()
                    self.assertEqual(
                        app.status_var.get(),
                        "Input: none → Effect: open the Work Item folder",
                    )
                    action_row = next(
                        item_id
                        for item_id, reference in app.focus_tree_items.items()
                        if reference.action_id
                    )
                    app.focus_tree.selection_set(action_row)
                    app.focus_tree.focus(action_row)
                    app._update_preview()
                    self.assertEqual(app.run_button.cget("text"), "Run")
                    self.assertFalse(app.work_item_folder_button.winfo_manager())
                    self.assertEqual(
                        app.status_var.get(),
                        "Input: saved text → Effect: copy to the clipboard for manual paste",
                    )
                    self.assertIn("\n\nType\n⧉ Paste saved text", app.action_info_full)
                    self.assertIn("\n\nEffect\n", app.action_info_full)
                    app.status_var.set("Completed an unrelated operation.")
                    app._update_preview()
                    self.assertTrue(app.status_var.get().startswith("Input: saved text → Effect:"))
                    app.status_var.set("Completed an unrelated operation.")
                    app._set_workspace_text("Current working text")
                    root.update()
                    self.assertTrue(app.status_var.get().startswith("Input: saved text → Effect:"))

                    app._select_item_context_filter("Review")
                    self.assertEqual(app.results_count_var.get(), "2 items")
                    self.assertEqual(
                        {
                            "action" if reference.action_id else "work_item"
                            for reference in app.focus_tree_items.values()
                        },
                        {"action", "work_item"},
                    )
                    app._select_item_context_filter(None)
                    app._select_item_tag_filter("database")
                    self.assertEqual(app.results_count_var.get(), "2 items")
                    self.assertEqual(
                        {
                            "action" if reference.action_id else "work_item"
                            for reference in app.focus_tree_items.values()
                        },
                        {"action", "work_item"},
                    )
                    app._select_item_tag_filter(None)

                    app.work_items_button.invoke()
                    root.update()
                    self.assertTrue(app.work_items_mode)
                    self.assertEqual(app.actions_heading_var.get(), "Work Items")
                    self.assertEqual(app.action_discovery_panel.find_label.cget("text"), "Find Work Item")
                    self.assertEqual(app.results_count_var.get(), "2 work items")
                    self.assertIn("Issue", app.results.get(0))
                    self.assertEqual(app.type_filter.cget("text"), "Proj ▾")
                    self.assertEqual(app.run_button.cget("text"), "Open")
                    self.assertTrue(app.work_item_folder_button.winfo_manager())
                    self.assertTrue(app.work_item_folder_button.cget("takefocus"))
                    self.assertFalse(app.passwords_button.winfo_manager())
                    self.assertFalse(app.new_work_item_button.winfo_manager())
                    self.assertFalse(app.send_work_item_inbox_button.winfo_manager())
                    self.assertFalse(app.copy_file_to_work_item_button.winfo_manager())
                    self.assertTrue(app.scope_options_button.cget("image"))
                    work_tools_menu = root.nametowidget(
                        app.scope_options_button.cget("menu")
                    )
                    self.assertEqual(
                        [
                            work_tools_menu.entrycget(index, "label")
                            for index in range(work_tools_menu.index(tk.END) + 1)
                            if work_tools_menu.type(index) != "separator"
                        ],
                        [
                            "New Work Item…",
                            "Send Input / Output to Inbox",
                            "Copy file into Work Item",
                            "Filter by project",
                            "Filter by context…",
                            "Filter by tag…",
                        ],
                    )
                    context_filter_index = next(
                        index
                        for index in range(work_tools_menu.index(tk.END) + 1)
                        if work_tools_menu.type(index) != "separator"
                        if work_tools_menu.entrycget(index, "label")
                        == "Filter by context…"
                    )
                    self.assertEqual(
                        work_tools_menu.type(context_filter_index),
                        "command",
                    )
                    work_tools_menu.invoke(context_filter_index)
                    root.update()
                    context_popup = app.action_discovery_panel.context_picker_popup
                    review_index = context_popup.visible_values.index("Review")
                    context_popup.listbox.selection_clear(0, tk.END)
                    context_popup.listbox.selection_set(review_index)
                    context_popup._selection_changed()
                    context_popup.apply()
                    self.assertEqual(app.item_context_filter, "Review")
                    work_tools_menu.invoke(context_filter_index)
                    root.update()
                    context_popup = app.action_discovery_panel.context_picker_popup
                    all_contexts_index = context_popup.visible_values.index(
                        "All contexts"
                    )
                    context_popup.listbox.selection_clear(0, tk.END)
                    context_popup.listbox.selection_set(all_contexts_index)
                    context_popup._selection_changed()
                    context_popup.apply()
                    self.assertIsNone(app.item_context_filter)
                    self.assertEqual(
                        {
                            widget: (widget.winfo_x(), widget.winfo_y())
                            for widget in initial_common_positions
                        },
                        initial_common_positions,
                    )
                    self.assertTrue(app.action_help_button.winfo_ismapped())
                    self._assert_input_first_layout(app)
                    self.assertEqual(app.work_project_filter_var.get(), "All project codes")

                    app._select_work_project_filter("AB9C")
                    self.assertEqual(app.results_count_var.get(), "1 work item")
                    self.assertEqual(app.type_filter.cget("text"), "Proj ✓")
                    self.assertEqual(app.type_filter.cget("style"), "RailAccent.TButton")
                    app._select_work_tag_filter("urgent")
                    self.assertEqual(app.results_count_var.get(), "1 work item")
                    self.assertEqual(app.tag_filter.cget("text"), "#✓")
                    self.assertEqual(app.tag_filter.cget("style"), "RailIconAccent.TButton")
                    app._execute_selected()
                    self.assertEqual(open_target.call_args.args[0].value, str(exact_workbook))
                    app._execute_selected(open_folder=True)
                    self.assertEqual(open_target.call_args.args[0].value, str(exact_folder))
                    app.work_item_folder_button.invoke()
                    self.assertEqual(open_target.call_args.args[0].value, str(exact_folder))

                    app.actions_button.invoke()
                    root.update()
                    self.assertEqual(
                        app.actions_tool_rail.winfo_width(),
                        initial_toolbar_width,
                    )
                    for scope_button in (
                        app.all_items_button,
                        app.actions_button,
                        app.work_items_button,
                    ):
                        self.assertGreaterEqual(
                            scope_button.winfo_width(),
                            scope_button.winfo_reqwidth(),
                        )
                    self.assertFalse(app.work_items_mode)
                    self.assertEqual(app.actions_heading_var.get(), "Actions")
                    self.assertEqual(app.action_discovery_panel.find_label.cget("text"), "Find action")
                    self.assertEqual(app.type_filter.cget("text"), "Types ▾")
                    self.assertEqual(app.run_button.cget("text"), "Run")
                    self.assertFalse(app.work_item_folder_button.winfo_manager())
                    self.assertFalse(app.passwords_button.winfo_manager())
                    self.assertFalse(app.new_work_item_button.winfo_manager())
                    self.assertFalse(app.send_work_item_inbox_button.winfo_manager())
                    self.assertFalse(app.copy_file_to_work_item_button.winfo_manager())
                    self.assertTrue(app.scope_options_button.cget("image"))
                    self.assertEqual(
                        {
                            widget: (widget.winfo_x(), widget.winfo_y())
                            for widget in initial_common_positions
                        },
                        initial_common_positions,
                    )
                    self._assert_input_first_layout(app)
                    self.assertEqual(app.item_tag_filter, "urgent")
                    self.assertEqual(app.results_count_var.get(), "0 actions")
                    self.assertEqual(str(app.run_button.cget("state")), "disabled")
                    self.assertEqual(str(app.action_discovery_panel.edit_button.cget("state")), "disabled")
                    self.assertEqual(str(app.action_discovery_panel.pin_button.cget("state")), "disabled")
                    app._select_item_tag_filter(None)
                    self.assertEqual(str(app.run_button.cget("state")), "normal")
                    self.assertEqual(str(app.action_discovery_panel.edit_button.cget("state")), "normal")
                    self.assertEqual(str(app.action_discovery_panel.pin_button.cget("state")), "normal")

                    opened_action_ids: list[str] = []
                    original_show_configuration = app._show_configuration
                    app._show_configuration = lambda **options: opened_action_ids.append(
                        options["initial_action_id"]
                    )
                    flat_index = 1
                    expected_flat_action = app.displayed_actions[flat_index].id
                    flat_bounds = app.results.bbox(flat_index)
                    self.assertIsNotNone(flat_bounds)
                    app.results.event_generate(
                        "<Button-3>",
                        x=flat_bounds[0] + 3,
                        y=flat_bounds[1] + 3,
                    )
                    root.update()
                    self.assertEqual(opened_action_ids, [expected_flat_action])
                    self.assertEqual(app.results.curselection(), (flat_index,))

                    action_tools_menu = root.nametowidget(
                        app.scope_options_button.cget("menu")
                    )
                    self.assertEqual(
                        [
                            action_tools_menu.entrycget(index, "label")
                            for index in range(action_tools_menu.index(tk.END) + 1)
                            if action_tools_menu.type(index) != "separator"
                        ],
                        ["Filter by type", "Filter by context…", "Filter by tag…"],
                    )

                    type_menu = root.nametowidget(app.type_filter.cget("menu"))
                    open_url_index = next(
                        index
                        for index in range(type_menu.index(tk.END) + 1)
                        if type_menu.type(index) == "radiobutton"
                        and type_menu.entrycget(index, "label")
                        == ACTION_TYPES["open_url"].display_label
                    )
                    type_menu.invoke(open_url_index)
                    self.assertEqual(app.action_type_filter, "open_url")
                    self.assertEqual(app.type_filter.cget("text"), "Types ✓")
                    self.assertEqual(app.type_filter.cget("style"), "RailAccent.TButton")
                    type_menu.invoke(0)
                    self.assertIsNone(app.action_type_filter)
                    self.assertEqual(app.type_filter.cget("text"), "Types ▾")
                    self.assertEqual(app.type_filter.cget("style"), "Compact.TButton")

                    app.tag_filter.invoke()
                    root.update()
                    database_tag_index = app.action_discovery_panel.tag_picker_popup.visible_values.index("database")
                    app.action_discovery_panel.tag_picker_popup.listbox.selection_clear(0, tk.END)
                    app.action_discovery_panel.tag_picker_popup.listbox.selection_set(database_tag_index)
                    app.action_discovery_panel.tag_picker_popup._selection_changed()
                    app.action_discovery_panel.tag_picker_popup.apply()
                    self.assertEqual(app.action_tag_filter, "database")
                    self.assertEqual(app.tag_filter.cget("text"), "#✓")
                    self.assertEqual(app.tag_filter.cget("style"), "RailIconAccent.TButton")
                    self.assertEqual(
                        [action.id for action in app.filtered_actions],
                        ["database-only"],
                    )
                    app.tag_filter.invoke()
                    root.update()
                    all_tags_index = app.action_discovery_panel.tag_picker_popup.visible_values.index("All tags")
                    app.action_discovery_panel.tag_picker_popup.listbox.selection_set(all_tags_index)
                    app.action_discovery_panel.tag_picker_popup._selection_changed()
                    app.action_discovery_panel.tag_picker_popup.apply()
                    self.assertIsNone(app.action_tag_filter)
                    self.assertEqual(app.tag_filter.cget("text"), "#")
                    self.assertEqual(app.tag_filter.cget("style"), "RailIcon.TButton")

                    app.search_var.set("definitely-no-match")
                    app.all_items_button.invoke()
                    root.update()
                    empty_rows = app.focus_tree.get_children()
                    self.assertEqual(empty_rows, ("empty:all",))
                    self.assertIn("No items match", app.focus_tree.item("empty:all", "text"))
                    self.assertEqual(str(app.run_button.cget("state")), "disabled")
                    self.assertTrue(app.status_var.get().startswith("No Actions or Work Items"))
                    app.search_var.set("")
                    root.update()

                    app._activate_focus_actions()
                    root.update()
                    self.assertEqual(app.results_view, "focus")
                    self.assertEqual(
                        app.focus_actions_button.cget("style"),
                        "RailAccent.TButton",
                    )
                    self.assertIs(root.focus_get(), app.focus_tree)
                    self.assertEqual(
                        {action.id for action in app.focus_tree_actions.values()},
                        {"general-first", "general-second", "database-only"},
                    )
                    focus_item = app.focus_tree.get_children()[1]
                    expected_focus_action = app.focus_tree_actions[focus_item].id
                    focus_bounds = app.focus_tree.bbox(focus_item)
                    self.assertTrue(focus_bounds)
                    app.focus_tree.event_generate(
                        "<Button-3>",
                        x=focus_bounds[0] + 3,
                        y=focus_bounds[1] + 3,
                    )
                    root.update()
                    self.assertEqual(
                        opened_action_ids,
                        [expected_flat_action, expected_focus_action],
                    )
                    self.assertEqual(app.focus_tree.selection(), (focus_item,))
                    app._show_configuration = original_show_configuration
                    app._show_flat_results()
                    app._render_focus_actions()
                    self.assertEqual(app._selected_action().id, "general-first")
                    app.context_var.set("Database")
                    app._change_focus_context()
                    app.context_var.set("General")
                    app._change_focus_context()

                    app.search_var.set("Database only")
                    self._wait_for_search_refresh(root)
                    self.assertEqual(app.results_view, "all")
                    self.assertEqual(
                        [action.id for action in app.displayed_actions],
                        ["database-only"],
                    )

                    app.context_var.set("Database")
                    app._change_focus_context()
                    self.assertEqual(app.results_view, "all")
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

                    app._activate_focus_actions()
                    root.update()
                    self.assertFalse(app.focus_actions_mode)
                    self.assertEqual(app.results_view, "all")
                    self.assertEqual(
                        app.focus_actions_button.cget("style"),
                        "Compact.TButton",
                    )
                    self._assert_input_first_layout(app)

                    surface_areas = app.command_tiles_frame.winfo_children()
                    self.assertEqual(
                        len(surface_areas),
                        4
                        + len(
                            [
                                group
                                for group in app.command_groups
                                if group.id.casefold() != "standard"
                            ]
                        ),
                    )
                    for position, (area, label) in enumerate(zip(
                        surface_areas[:4],
                        (
                            "Standard ▾",
                            "Passwords ▾",
                            "Folders ▾",
                            "Prompts ▾",
                        ),
                    )):
                        expected_row, expected_column = divmod(
                            position,
                            app.command_surface_columns,
                        )
                        self.assertIsInstance(area, ttk.Frame)
                        self.assertNotIsInstance(area, ttk.LabelFrame)
                        self.assertEqual(int(area.grid_info()["row"]), expected_row)
                        self.assertEqual(int(area.grid_info()["column"]), expected_column)
                        self.assertEqual(
                            [child.cget("text") for child in area.winfo_children()],
                            [label],
                        )
                    configurable_groups = [
                        group
                        for group in app.command_groups
                        if group.id.casefold() != "standard"
                    ]
                    for index, (area, group) in enumerate(
                        zip(surface_areas[4:], configurable_groups)
                    ):
                        expected_row, expected_column = divmod(
                            index + 4,
                            app.command_surface_columns,
                        )
                        self.assertEqual(
                            int(area.grid_info()["row"]),
                            expected_row,
                        )
                        self.assertEqual(
                            int(area.grid_info()["column"]),
                            expected_column,
                        )
                        if (
                            group.presentation == GROUP_PRESENTATION_NESTED_MENU
                            or len(group.items) == 1
                        ):
                            self.assertIsInstance(area, ttk.Frame)
                            self.assertNotIsInstance(area, ttk.LabelFrame)
                        else:
                            self.assertIsInstance(area, ttk.LabelFrame)
                            self.assertEqual(area.cget("text"), group.label)
                        menu_launchers = [
                            child
                            for child in area.winfo_children()
                            if isinstance(child, ttk.Label)
                            and child.cget("style") == "SurfaceMenu.TLabel"
                        ]
                        expected_launcher_labels = (
                            [f"{group.label} ▾"]
                            if group.presentation
                            == GROUP_PRESENTATION_NESTED_MENU
                            else [item.label for item in group.items]
                        )
                        self.assertEqual(
                            [control.cget("text") for control in menu_launchers],
                            expected_launcher_labels,
                        )
                        for row, control in enumerate(menu_launchers):
                            self.assertEqual(int(control.grid_info()["row"]), row)
                            self.assertEqual(int(control.grid_info()["column"]), 0)
                            self.assertEqual(str(control.cget("anchor")), "w")
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
                    self._assert_input_first_layout(app)
                    self.assertGreater(app.results_container.winfo_height(), 400)
                    self.assertGreater(app.workspace_container.winfo_height(), 400)
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
                    self.assertEqual(app.command_surface_columns, 2)
                    surface_right = (
                        app.command_surface_canvas.winfo_rootx()
                        + app.command_surface_canvas.winfo_width()
                    )
                    surface_controls = [
                        widget
                        for widget in self._descendants(app.command_tiles_frame)
                        if isinstance(widget, ttk.Label)
                        and widget.cget("style") == "SurfaceMenu.TLabel"
                        and widget.winfo_ismapped()
                    ]
                    self.assertTrue(surface_controls)
                    for control in surface_controls:
                        self.assertLessEqual(
                            control.winfo_rootx() + control.winfo_width(),
                            surface_right,
                            control.cget("text"),
                        )
                    self.assertLessEqual(
                        app.command_tiles_frame.winfo_reqheight(),
                        app.command_surface_canvas.winfo_height(),
                        "All Quick actions should fit at the default window size.",
                    )
                    self.assertLessEqual(
                        app.command_surface_canvas.winfo_height(),
                        app.command_tiles_frame.winfo_reqheight() + 2,
                        "Quick actions should not retain blank canvas below its rows.",
                    )
                    self.assertGreater(
                        app.actions_list_frame.winfo_height(),
                        app.actions_list_frame.winfo_reqheight(),
                        "Recovered Quick-action space should expand the results list.",
                    )
                    self.assertTrue(
                        all(button.cget("image") for button in app.footer_action_buttons)
                    )
                    self.assertTrue(app.more_button.cget("image"))
                    self.assertEqual(
                        [
                            app.more_menu.entrycget(index, "label")
                            for index in (0, 2, 3)
                        ],
                        ["Keyboard shortcuts", "Hide", "Quit"],
                    )
                    tooltips = {
                        tooltip.widget: tooltip.text
                        for tooltip in app.widget_tooltips
                        if isinstance(tooltip.text, str)
                    }
                    for button, name in zip(
                        app.footer_action_buttons,
                        ("Capture", "Inbox", "Edit item", "Pin"),
                    ):
                        self.assertTrue(tooltips[button].startswith(f"{name} —"))
                    self.assertTrue(tooltips[app.more_button].startswith("More —"))
                    self.assertTrue(app.text_tools_button.cget("image"))
                    workspace_header = app.workspace_component.frame.winfo_children()[0]
                    self.assertFalse(
                        any(
                            isinstance(widget, ttk.Label)
                            for widget in workspace_header.winfo_children()
                        )
                    )

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

                    lists_menu = root.nametowidget(
                        app.workspace_transform_menu.entrycget(
                            transform_groups.index("Lists"),
                            "menu",
                        )
                    )
                    self.assertEqual(
                        [
                            lists_menu.entrycget(index, "label")
                            for index in range(lists_menu.index(tk.END) + 1)
                        ],
                        [
                            "Comma list: no quotes",
                            "Comma list: single-quoted text",
                            "Comma list: double-quoted text",
                            "Parenthesized SQL value list",
                        ],
                    )
                    sql_index = next(
                        index
                        for index in range(lists_menu.index(tk.END) + 1)
                        if lists_menu.entrycget(index, "label")
                        == "Parenthesized SQL value list"
                    )
                    app._set_workspace_text("1\nO'Brien")
                    with patch.object(app, "_set_clipboard", copied.append):
                        lists_menu.invoke(sql_index)
                    self.assertEqual(app._workspace_text(), "(1, 'O''Brien')")
                    self.assertEqual(copied[-1], "(1, 'O''Brien')")

                    paths_menu = root.nametowidget(
                        app.workspace_transform_menu.entrycget(
                            transform_groups.index("Paths"),
                            "menu",
                        )
                    )
                    slash_index = next(
                        index
                        for index in range(paths_menu.index(tk.END) + 1)
                        if paths_menu.entrycget(index, "label").startswith(
                            "Forward slashes"
                        )
                    )
                    app._set_workspace_text("C:/work/project")
                    with patch.object(app, "_set_clipboard", copied.append):
                        paths_menu.invoke(slash_index)
                    self.assertEqual(app._workspace_text(), "C:\\work\\project")
                    self.assertEqual(copied[-1], "C:\\work\\project")

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
                    self._assert_input_first_layout(app)
                    self.assertAlmostEqual(
                        app.workspace_container.winfo_height(),
                        app.results_container.winfo_height(),
                        delta=4,
                    )

                    pane_width = app.main_content.winfo_width()
                    app.main_content.sashpos(0, int(pane_width * 0.50))
                    app._remember_main_split(None)  # type: ignore[arg-type]
                    self.assertAlmostEqual(app.main_split_ratio, 0.50, places=2)
                    app.main_content.sashpos(0, int(pane_width * 0.45))
                    app._remember_main_split(None)  # type: ignore[arg-type]
                    self.assertAlmostEqual(app.main_split_ratio, 0.45, places=2)
                    app.main_content.sashpos(0, 0)
                    app._remember_main_split(None)  # type: ignore[arg-type]
                    self.assertGreaterEqual(
                        app.results_container.winfo_width(),
                        MINIMUM_COMMAND_CONSOLE_WIDTH,
                    )
                    app.main_content.sashpos(0, pane_width)
                    app._remember_main_split(None)  # type: ignore[arg-type]
                    self.assertGreaterEqual(
                        app.workspace_container.winfo_width(),
                        MINIMUM_WORKSPACE_WIDTH,
                    )
                    app.main_split_ratio = 0.40
                    app._set_initial_main_split()
                    root.update_idletasks()
                    self._assert_input_first_layout(app)

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

                    self.assertTrue(app.configure_button.cget("image"))

                    root.focus_force()
                    root.event_generate("<Control-Shift-KeyPress-d>")
                    root.update()
                    diagnostic_windows = [
                        child
                        for child in root.winfo_children()
                        if isinstance(child, tk.Toplevel)
                        and child.title() == "Configure Context Palette"
                    ]
                    self.assertEqual(len(diagnostic_windows), 1)
                    diagnostic_window = diagnostic_windows[0]
                    diagnostic_notebook = next(
                        child
                        for child in self._descendants(diagnostic_window)
                        if isinstance(child, ttk.Notebook)
                    )
                    self.assertEqual(
                        diagnostic_notebook.tab(
                            diagnostic_notebook.select(),
                            "text",
                        ),
                        "Diagnostics",
                    )
                    diagnostic_text = next(
                        child
                        for child in self._descendants(diagnostic_window)
                        if isinstance(child, tk.Text)
                        and "Context Palette diagnostics"
                        in child.get("1.0", tk.END)
                    )
                    self.assertIs(diagnostic_window.focus_get(), diagnostic_text)

                    diagnostic_text.event_generate("<Control-KeyPress-Escape>")
                    root.update()
                    self.assertTrue(diagnostic_window.winfo_exists())

                    for keysym, expected_tab in (
                        ("a", "Actions"),
                        ("t", "Create action"),
                        ("c", "Contexts"),
                        ("q", "Quick actions"),
                        ("d", "Diagnostics"),
                        ("b", "Backup and restore"),
                    ):
                        diagnostic_window.event_generate(
                            "<KeyPress>",
                            state=0x20000,
                            keysym=keysym,
                        )
                        root.update()
                        self.assertTrue(diagnostic_window.winfo_exists())
                        self.assertEqual(
                            diagnostic_notebook.tab(
                                diagnostic_notebook.select(),
                                "text",
                            ),
                            expected_tab,
                        )

                    diagnostic_text.event_generate("<Control-KeyPress-Tab>")
                    root.update()
                    self.assertEqual(
                        diagnostic_notebook.tab(
                            diagnostic_notebook.select(),
                            "text",
                        ),
                        "Start",
                    )

                    diagnostic_window.destroy()
                    root.update()

                    configuration_routes = (
                        (
                            lambda: app.context_menu.invoke(
                                app.context_menu.index("end")
                            ),
                            "Contexts",
                        ),
                        (app.configure_button.invoke, "Start"),
                    )
                    reused_configuration_window = None
                    for open_configuration, expected_tab in configuration_routes:
                        open_configuration()
                        root.update()
                        configuration_windows = [
                            child
                            for child in root.winfo_children()
                            if isinstance(child, tk.Toplevel)
                            and child.title() == "Configure Context Palette"
                        ]
                        self.assertEqual(len(configuration_windows), 1)
                        if reused_configuration_window is None:
                            reused_configuration_window = configuration_windows[0]
                        else:
                            self.assertIs(
                                configuration_windows[0],
                                reused_configuration_window,
                            )
                        notebook = next(
                            child
                            for child in self._descendants(configuration_windows[0])
                            if isinstance(child, ttk.Notebook)
                        )
                        self.assertEqual(
                            notebook.tab(notebook.select(), "text"),
                            expected_tab,
                        )
                        tab_names = [
                            notebook.tab(tab_id, "text")
                            for tab_id in notebook.tabs()
                        ]
                        self.assertEqual(tab_names[0], "Start")
                        self.assertIn("Diagnostics", tab_names)
                        start_tab = notebook.nametowidget(notebook.tabs()[0])
                        start_buttons = {
                            child.cget("text"): child
                            for child in self._descendants(start_tab)
                            if isinstance(child, ttk.Button)
                        }
                        self.assertTrue(
                            {
                                "Create an Action...",
                                "Find or edit Actions",
                                "Organize Focuses",
                                "Arrange Quick actions",
                                "Set up Work Items",
                                "Back up or restore",
                            }
                            <= set(start_buttons)
                        )
                        if expected_tab == "Start":
                            start_buttons["Arrange Quick actions"].invoke()
                            root.update()
                            self.assertEqual(
                                notebook.tab(notebook.select(), "text"),
                                "Quick actions",
                            )
                            notebook.select(0)
                            root.update()
                        diagnostics_tab_id = notebook.tabs()[
                            tab_names.index("Diagnostics")
                        ]
                        diagnostics_tab = notebook.nametowidget(diagnostics_tab_id)
                        diagnostics_widgets = self._descendants(diagnostics_tab)
                        diagnostics_text = next(
                            child
                            for child in diagnostics_widgets
                            if isinstance(child, tk.Text)
                        )
                        self.assertEqual(
                            str(diagnostics_text.cget("state")),
                            str(tk.DISABLED),
                        )
                        self.assertTrue(bool(diagnostics_text.cget("takefocus")))
                        self.assertIn(
                            "Configuration loaded",
                            diagnostics_text.get("1.0", tk.END),
                        )
                        diagnostic_button_labels = {
                            child.cget("text")
                            for child in diagnostics_widgets
                            if isinstance(child, ttk.Button)
                        }
                        self.assertTrue(
                            {"Refresh", "Copy safe summary"}
                            <= diagnostic_button_labels
                        )
                    self.assertIsNotNone(reused_configuration_window)
                    self.assertIs(
                        app.configuration_window.data_paths,
                        app.data_paths,
                    )
                    self.assertIs(
                        app.configuration_window.backup_restore_panel.data_paths,
                        app.data_paths,
                    )
                    self.assertEqual(
                        app.configuration_window._launcher_restore_complete,
                        app._reload,
                    )
                    reused_configuration_window.geometry("700x480")
                    app.configuration_window.notebook.select(5)
                    root.update()
                    work_item_trees = {
                        tree.heading("#0", "text"): tree
                        for tree in self._descendants(
                            app.configuration_window.work_items_panel.parent
                        )
                        if isinstance(tree, ttk.Treeview)
                    }
                    for heading, last_column in (
                        ("Source", "state"),
                        ("Work Item", "opens"),
                    ):
                        tree = work_item_trees[heading]
                        self.assertTrue(
                            any(
                                isinstance(child, ttk.Scrollbar)
                                for child in tree.master.winfo_children()
                            ),
                            f"{heading} list has no visible scrollbar",
                        )
                        first_item = tree.get_children()[0]
                        bounds = tree.bbox(first_item, last_column)
                        self.assertTrue(bounds)
                        self.assertLessEqual(
                            bounds[0] + bounds[2],
                            tree.winfo_width(),
                            f"{heading} list clips its final column",
                        )
                    requested_action = app.actions[-1]
                    app.configuration_window.action_filter_var.set(
                        "query that hides every action"
                    )
                    app._show_configuration(
                        initial_tab="actions",
                        initial_action_id=requested_action.id,
                    )
                    root.update()
                    self.assertIs(
                        app.configuration_window.window,
                        reused_configuration_window,
                    )
                    self.assertEqual(
                        app.configuration_window.action_filter_var.get(),
                        "",
                    )
                    selected_action_iid = (
                        app.configuration_window.action_tree.selection()[0]
                    )
                    selected_action_index = int(
                        selected_action_iid.removeprefix("action-")
                    )
                    self.assertEqual(
                        app.configuration_window.actions[selected_action_index].id,
                        requested_action.id,
                    )
                    reused_configuration_window.destroy()
                    root.update()
                    previous_configuration = app.configuration_window
                    app.configure_button.invoke()
                    root.update()
                    self.assertIsNot(
                        app.configuration_window,
                        previous_configuration,
                    )
                    app.configuration_window.window.destroy()
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
                        self.assertEqual(
                            [
                                child.cget("text")
                                for child in self._descendants(help_windows[0])
                                if isinstance(child, ttk.Button)
                                and child.cget("text") == "Cheat sheets"
                            ],
                            ["Cheat sheets"],
                        )
                        help_windows[0].destroy()
                        root.update()

                    app._show_shortcuts()
                    root.update()
                    shortcut_windows = [
                        child
                        for child in root.winfo_children()
                        if isinstance(child, tk.Toplevel)
                        and child.title() == "Context Palette Keyboard Shortcuts"
                    ]
                    self.assertEqual(len(shortcut_windows), 1)
                    shortcut_document = next(
                        child
                        for child in self._descendants(shortcut_windows[0])
                        if callable(getattr(child, "get_page_text", None))
                    )
                    self.assertIn("Alt+A", shortcut_document.get_page_text())
                    shortcut_windows[0].destroy()
                    root.update()

                    callbacks_before_sheet = set(
                        root.tk.splitlist(root.tk.call("after", "info"))
                    )
                    app._show_cheatsheets()
                    sheet_callback_ids = set(
                        root.tk.splitlist(root.tk.call("after", "info"))
                    ) - callbacks_before_sheet
                    self.assertTrue(sheet_callback_ids)
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
                    remaining_callback_ids = set(
                        root.tk.splitlist(root.tk.call("after", "info"))
                    )
                    self.assertTrue(
                        sheet_callback_ids.isdisjoint(remaining_callback_ids)
                    )

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

    def _descendants(
        self,
        widget: tk.Misc,
        seen: set[str] | None = None,
    ) -> list[tk.Misc]:
        seen = seen or set()
        descendants: list[tk.Misc] = []
        for child in widget.winfo_children():
            identity = str(child)
            if identity in seen:
                continue
            seen.add(identity)
            descendants.append(child)
            descendants.extend(self._descendants(child, seen))
        return descendants

    def _assert_input_first_layout(self, app: LauncherApp) -> None:
        total_width = app.main_content.winfo_width()
        self.assertGreater(total_width, 1)
        self.assertEqual(str(app.main_content.cget("orient")), "horizontal")
        self.assertGreaterEqual(
            app.workspace_container.winfo_width(),
            total_width * 0.50,
        )
        self.assertAlmostEqual(
            app.workspace_container.winfo_height(),
            app.command_console.winfo_height(),
            delta=4,
        )
        self.assertGreaterEqual(int(app.results.cget("height")), 7)
        self.assertLessEqual(int(app.results.cget("height")), 10)
        self.assertLessEqual(
            app.search_entry.winfo_width(),
            app.actions_list_frame.winfo_width(),
        )
        self.assertIs(app.command_surface_panel.master, app.command_console)
        self.assertIs(app.workspace_panel.master, app.workspace_container)
        self.assertIs(app.status_label.master, app.workspace_container)
        self.assertGreaterEqual(
            app.workspace_panel.winfo_height(),
            app.workspace_container.winfo_height() - 40,
        )


if __name__ == "__main__":
    unittest.main()
