from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, call, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.actions import Action
from context_palette.action_bound_quick_actions import action_bound_quick_groups
from context_palette.command_surface import (
    CommandGroup,
    CommandItem,
    CommandTarget,
    CommandSurfaceError,
    GROUP_PRESENTATION_NESTED_MENU,
)
from context_palette.launcher import LauncherApp
from context_palette.work_item_refresh import SourceRefreshResult, WorkItemIndex
from context_palette.work_items import (
    DiscoveredWorkItem,
    WorkItemReference,
    WorkItemSource,
)


class FakeStatusVar:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class FakeRoot:
    def after_idle(self, callback: object) -> str:
        callback()
        return "after-idle"


class FakeEvent:
    def __init__(
        self,
        state: int = 0,
        x_root: int = 10,
        y_root: int = 20,
        y: int = 0,
    ) -> None:
        self.state = state
        self.x_root = x_root
        self.y_root = y_root
        self.y = y


class FakeMenu:
    last_instance: "FakeMenu | None" = None
    instances: list["FakeMenu"] = []

    def __init__(self, _root: object, tearoff: bool = False) -> None:
        self.tearoff = tearoff
        self.labels: list[str] = []
        self.commands: list[object] = []
        self.states: list[str | None] = []
        self.cascades: list["FakeMenu"] = []
        self.popup_calls: list[tuple[int, int]] = []
        self.grab_release_calls = 0
        self.unpost_calls = 0
        self.bindings: dict[str, object] = {}
        FakeMenu.last_instance = self
        FakeMenu.instances.append(self)

    def add_command(
        self,
        label: str,
        command: object | None = None,
        state: str | None = None,
    ) -> None:
        self.labels.append(label)
        self.commands.append(command)
        self.states.append(state)

    def add_separator(self) -> None:
        self.labels.append("---")
        self.commands.append(None)
        self.states.append(None)

    def add_cascade(self, label: str, menu: "FakeMenu") -> None:
        self.labels.append(label)
        self.commands.append(menu)
        self.states.append(None)
        self.cascades.append(menu)

    def index(self, marker: object) -> int | None:
        if not self.labels:
            return None
        if isinstance(marker, str) and marker.startswith("@"):
            try:
                candidate = int(marker[1:])
            except ValueError:
                return None
            return candidate if 0 <= candidate < len(self.labels) else None
        return len(self.labels) - 1

    def bind(self, sequence: str, callback: object, add: str | None = None) -> None:
        self.bindings[sequence] = callback

    def tk_popup(self, x_root: int, y_root: int) -> None:
        self.popup_calls.append((x_root, y_root))

    def unpost(self) -> None:
        self.unpost_calls += 1

    def grab_release(self) -> None:
        self.grab_release_calls += 1

    def right_click(self, index: int) -> str:
        callback = self.bindings["<Button-3>"]
        return callback(FakeEvent(x_root=30, y_root=40, y=index))


class LauncherCommandSurfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeMenu.last_instance = None
        FakeMenu.instances = []

    def test_action_bound_groups_put_blank_paths_at_menu_root(self):
        actions = [
            Action("password", "Database", "General", "paste_credential", "database"),
            Action(
                "folder",
                "Reports",
                "General",
                "open_folder",
                ".",
                quick_action_path=("Work", "Reports"),
            ),
            Action("one", "First prompt", "General", "ai_prompt", "Review this"),
            Action("template", "Not a prompt", "General", "workspace_template", "text"),
            Action("old", "Archived", "General", "ai_prompt", "old", "Archived"),
        ]

        passwords, folders, prompts = action_bound_quick_groups(actions)

        self.assertEqual(
            [group.label for group in (passwords, folders, prompts)],
            ["Passwords", "Folders", "Prompts"],
        )
        self.assertEqual(passwords.action_ids, ("password",))
        self.assertEqual(passwords.items, ())
        self.assertEqual(folders.items[0].label, "Work")
        self.assertEqual(folders.items[0].items[0].label, "Reports")
        self.assertEqual(folders.items[0].items[0].action_ids, ("folder",))
        self.assertEqual(prompts.action_ids, ("one",))

    def test_failed_reload_preserves_last_known_good_buttons(self):
        app = self._app()
        existing = CommandGroup(
            "existing",
            "Existing",
            (CommandItem("button", "Button", primary_action_id="primary"),),
        )
        app.command_groups = [existing]
        app.command_surface_path = Path("command_surface.json")
        app.local_command_surface_path = Path("local_command_surface.json")
        renders: list[bool] = []
        app._render_command_surface = lambda: renders.append(True)

        with (
            patch(
                "context_palette.launcher.load_combined_command_groups",
                side_effect=CommandSurfaceError("invalid button file"),
            ),
            patch("context_palette.launcher.messagebox.showerror") as showerror,
        ):
            app._load_command_surface()

        self.assertEqual(app.command_groups, [existing])
        self.assertIn("kept 1 previous button", app.status_var.value)
        self.assertEqual(renders, [True])
        showerror.assert_called_once()

    def _app(self) -> LauncherApp:
        app = LauncherApp.__new__(LauncherApp)
        app.root = FakeRoot()
        app.status_var = FakeStatusVar()
        app.actions = [
            Action(
                id="primary",
                title="Open Primary",
                context="General",
                type="open_url",
                value="https://example.com",
                state="Active",
            ),
            Action(
                id="secondary",
                title="Open Secondary",
                context="General",
                type="open_url",
                value="https://example.org",
                state="Active",
            ),
        ]
        app.command_groups = []
        source = WorkItemSource("product-work", "Product work", ROOT)
        app._test_work_item = DiscoveredWorkItem(
            source_id=source.id,
            source_name=source.name,
            relative_folder="ISS-ABC-example",
            folder_path=ROOT / "ISS-ABC-example",
            display_name="ISS-ABC-example",
            kind_code="ISS",
            kind_name="Issue",
            organisation="ABC",
            subject="example",
            project_codes=(),
            matching_workbook_path=ROOT / "ISS-ABC-example" / "ISS-ABC-example.xlsx",
        )
        app.work_item_index = WorkItemIndex(
            (SourceRefreshResult(source, (app._test_work_item,)),)
        )
        app._execute_action_calls = []
        app._opened_work_items = []
        app._configuration_requests = []

        app._execute_action = lambda action: app._execute_action_calls.append(action.id)
        app._open_work_item_target = (
            lambda item, target: app._opened_work_items.append((item, target)) or True
        )
        app._show_configuration = (
            lambda **kwargs: app._configuration_requests.append(kwargs)
        )
        return app

    def test_group_left_click_browses_without_executing(self):
        app = self._app()
        group = CommandGroup(
            "writing",
            "Writing",
            (
                CommandItem(
                    "greeting",
                    "Greetings",
                    primary_action_id="primary",
                    action_ids=("secondary",),
                ),
            ),
        )

        with patch("context_palette.launcher.tk.Menu", FakeMenu):
            result = app._show_group_menu(FakeEvent(), group)

        self.assertEqual(result, "break")
        self.assertEqual(app._execute_action_calls, [])
        self.assertEqual(app._active_command_menu.labels, ["Greetings"])
        self.assertEqual(app._active_command_menu.popup_calls, [(10, 20)])
        self.assertEqual(
            app._active_command_submenus[0].labels,
            ["↗ - Primary", "↗ - Secondary"],
        )

    def test_legacy_primary_only_controls_menu_order(self):
        app = self._app()
        group = CommandGroup(
            "writing",
            "Writing",
            (
                CommandItem(
                    "greeting",
                    "Greetings",
                    primary_action_id="primary",
                    action_ids=("secondary", "primary"),
                ),
            ),
        )

        with patch("context_palette.launcher.tk.Menu", FakeMenu):
            app._show_group_menu(FakeEvent(), group)

        self.assertEqual(
            app._active_command_submenus[0].labels,
            ["↗ - Primary", "↗ - Secondary"],
        )
        self.assertEqual(app._execute_action_calls, [])

    def test_action_entry_left_click_executes_only_selected_action(self):
        app = self._app()
        group = CommandGroup(
            "standard",
            "Standard",
            presentation=GROUP_PRESENTATION_NESTED_MENU,
            action_ids=("primary", "secondary"),
        )

        with patch("context_palette.launcher.tk.Menu", FakeMenu):
            app._show_group_menu(FakeEvent(), group)

        app._active_command_menu.commands[1]()
        self.assertEqual(app._execute_action_calls, ["secondary"])

    def test_action_entry_right_click_edits_exact_action_without_running(self):
        app = self._app()
        group = CommandGroup(
            "standard",
            "Standard",
            presentation=GROUP_PRESENTATION_NESTED_MENU,
            action_ids=("primary",),
        )

        with patch("context_palette.launcher.tk.Menu", FakeMenu):
            app._show_group_menu(FakeEvent(), group)
            result = app._active_command_menu.right_click(0)

        self.assertEqual(result, "break")
        self.assertEqual(app._execute_action_calls, [])
        self.assertEqual(
            app._configuration_requests,
            [
                {
                    "initial_tab": "actions",
                    "initial_action_id": "primary",
                    "start_action_edit": True,
                }
            ],
        )
        self.assertEqual(app._active_command_menu.unpost_calls, 1)

    def test_work_item_entry_left_opens_and_right_selects_for_management(self):
        app = self._app()
        reference = WorkItemReference("product-work", "ISS-ABC-example")
        group = CommandGroup(
            "work",
            "Work",
            (CommandItem("current", "Current item", work_item_ref=reference),),
        )

        with patch("context_palette.launcher.tk.Menu", FakeMenu):
            app._show_group_menu(FakeEvent(), group)
            item_menu = app._active_command_submenus[0]
            item_menu.commands[0]()
            item_menu.right_click(0)

        self.assertEqual(
            app._opened_work_items,
            [(app._test_work_item, app._test_work_item.matching_workbook_path)],
        )
        self.assertEqual(
            app._configuration_requests[-1],
            {
                "initial_tab": "work_items",
                "initial_work_item_key": "product-work/ISS-ABC-example",
            },
        )

    def test_unavailable_work_item_stays_visible_and_disabled(self):
        app = self._app()
        group = CommandGroup(
            "work",
            "Work",
            (
                CommandItem(
                    "missing",
                    "Missing item",
                    work_item_ref=WorkItemReference(
                        "product-work",
                        "ISS-ABC-missing",
                    ),
                ),
            ),
        )

        with patch("context_palette.launcher.tk.Menu", FakeMenu):
            app._show_group_menu(FakeEvent(), group)

        missing_menu = app._active_command_submenus[0]
        self.assertEqual(
            missing_menu.labels,
            ["Unavailable Work Item - ISS-ABC-missing"],
        )
        self.assertEqual(missing_menu.states, ["disabled"])

    def test_mixed_quick_action_menu_preserves_target_order(self):
        app = self._app()
        group = CommandGroup(
            "mixed",
            "Mixed",
            (
                CommandItem(
                    "mixed",
                    "Mixed targets",
                    targets=(
                        CommandTarget(action_id="primary"),
                        CommandTarget(
                            work_item_ref=WorkItemReference(
                                "product-work",
                                "ISS-ABC-example",
                            )
                        ),
                        CommandTarget(action_id="secondary"),
                    ),
                ),
            ),
        )

        with patch("context_palette.launcher.tk.Menu", FakeMenu):
            app._show_group_menu(FakeEvent(), group)

        self.assertEqual(
            app._active_command_submenus[0].labels,
            [
                app.actions[0].compact_display_text,
                "▣ - ISS-ABC-example",
                app.actions[1].compact_display_text,
            ],
        )

    def test_configured_launcher_right_click_offers_add_and_organize(self):
        app = self._app()
        group = CommandGroup("writing", "Writing")
        app._open_configured_quick_manager = Mock()

        with patch("context_palette.launcher.tk.Menu", FakeMenu):
            result = app._show_configured_group_management(FakeEvent(), group)

        self.assertEqual(result, "break")
        self.assertEqual(
            app._active_quick_management_menu.labels,
            ["Add Quick action to Writing…", "---", "Organize Writing…"],
        )
        app._active_quick_management_menu.commands[0]()
        app._active_quick_management_menu.commands[2]()
        self.assertEqual(
            app._open_configured_quick_manager.call_args_list,
            [
                call("writing", (), start_add=True),
                call("writing", ()),
            ],
        )
        self.assertEqual(app._execute_action_calls, [])

    def test_automatic_launcher_right_click_offers_typed_add_and_management(self):
        app = self._app()
        group = CommandGroup("action-bound-folders", "Folders")
        app._open_automatic_quick_creator = Mock()
        app._open_automatic_quick_manager = Mock()
        app._find_automatic_quick_actions = Mock()

        with patch("context_palette.launcher.tk.Menu", FakeMenu):
            result = app._show_action_bound_group_management(
                FakeEvent(),
                group,
                "open_folder",
            )

        self.assertEqual(result, "break")
        self.assertEqual(
            app._active_quick_management_menu.labels,
            [
                "Add folder shortcut…",
                "---",
                "Organize Folders…",
                "Find matching Actions…",
            ],
        )
        for index in (0, 2, 3):
            app._active_quick_management_menu.commands[index]()
        app._open_automatic_quick_creator.assert_called_once_with(
            "open_folder",
            (),
        )
        app._open_automatic_quick_manager.assert_called_once_with(
            "open_folder",
            (),
        )
        app._find_automatic_quick_actions.assert_called_once_with(
            "Folders",
            "open_folder",
            (),
        )

    def test_branch_right_click_offers_related_branch_commands(self):
        app = self._app()
        app._open_automatic_quick_creator = Mock()
        app._open_automatic_quick_manager = Mock()
        app._find_automatic_quick_actions = Mock()
        group = CommandGroup(
            "action-bound-folders",
            "Folders",
            (CommandItem("work", "Work", action_ids=("primary",)),),
            presentation=GROUP_PRESENTATION_NESTED_MENU,
        )

        with patch("context_palette.launcher.tk.Menu", FakeMenu):
            app._post_group_menu(
                group,
                10,
                20,
                automatic_action_type="open_folder",
            )
            app._active_command_menu.right_click(0)

        self.assertEqual(
            app._active_quick_management_menu.labels,
            [
                "Add folder here…",
                "---",
                "Organize Folders > Work…",
                "Find matching Actions…",
            ],
        )
        for index in (0, 2, 3):
            app._active_quick_management_menu.commands[index]()
        app._open_automatic_quick_creator.assert_called_once_with(
            "open_folder",
            ("Work",),
        )
        app._open_automatic_quick_manager.assert_called_once_with(
            "open_folder",
            ("Work",),
        )

    def test_configured_branch_uses_submenu_language_and_hides_add_at_max_depth(self):
        app = self._app()
        app._open_configured_quick_manager = Mock()
        group = CommandGroup(
            "tools",
            "Tools",
            (
                CommandItem(
                    "one",
                    "One",
                    items=(
                        CommandItem(
                            "two",
                            "Two",
                            items=(CommandItem("three", "Three"),),
                        ),
                    ),
                ),
            ),
            presentation=GROUP_PRESENTATION_NESTED_MENU,
        )

        with patch("context_palette.launcher.tk.Menu", FakeMenu):
            app._post_configured_quick_management(group, (0,), 10, 20)
            self.assertEqual(
                app._active_quick_management_menu.labels,
                ["New submenu here…", "---", "Organize One…"],
            )
            app._post_configured_quick_management(group, (0, 0, 0), 10, 20)

        self.assertEqual(
            app._active_quick_management_menu.labels,
            ["Organize Three…"],
        )
        app._active_quick_management_menu.commands[0]()
        app._open_configured_quick_manager.assert_called_once_with(
            "tools",
            ("one", "two", "three"),
        )

    def test_nested_group_menu_keeps_root_actions_and_subject_tree(self):
        app = self._app()
        group = CommandGroup(
            "standard",
            "Standard",
            (
                CommandItem(
                    "lookup",
                    "Lookup",
                    items=(
                        CommandItem(
                            "details",
                            "Details",
                            items=(
                                CommandItem(
                                    "deep",
                                    "Deep",
                                    primary_action_id="secondary",
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            presentation=GROUP_PRESENTATION_NESTED_MENU,
            primary_action_id="primary",
            action_ids=("primary",),
        )

        with patch("context_palette.launcher.tk.Menu", FakeMenu):
            result = app._show_group_menu(FakeEvent(), group)

        self.assertEqual(result, "break")
        root_menu = app._active_command_menu
        lookup_menu, details_menu, deep_menu = app._active_command_submenus
        self.assertEqual(root_menu.labels, ["↗ - Primary", "---", "Lookup"])
        self.assertEqual(lookup_menu.labels, ["Details"])
        self.assertEqual(details_menu.labels, ["Deep"])
        self.assertEqual(deep_menu.labels, ["↗ - Secondary"])
        deep_menu.commands[0]()
        self.assertEqual(app._execute_action_calls, ["secondary"])


if __name__ == "__main__":
    unittest.main()
