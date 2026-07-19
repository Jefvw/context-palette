from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.actions import Action
from context_palette.command_surface import CommandGroup, CommandItem, CommandSurfaceError
from context_palette.launcher import LauncherApp


class FakeStatusVar:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class FakeEvent:
    def __init__(self, state: int = 0, x_root: int = 10, y_root: int = 20) -> None:
        self.state = state
        self.x_root = x_root
        self.y_root = y_root


class FakeMenu:
    last_instance: "FakeMenu | None" = None

    def __init__(self, _root: object, tearoff: bool = False) -> None:
        self.tearoff = tearoff
        self.labels: list[str] = []
        self.commands: list[object] = []
        self.popup_calls: list[tuple[int, int]] = []
        self.grab_release_calls = 0
        FakeMenu.last_instance = self

    def add_command(self, label: str, command: object | None = None, state: str | None = None) -> None:
        self.labels.append(label)
        self.commands.append(command)

    def index(self, _marker: object) -> int | None:
        return None if not self.labels else len(self.labels) - 1

    def tk_popup(self, x_root: int, y_root: int) -> None:
        self.popup_calls.append((x_root, y_root))

    def grab_release(self) -> None:
        self.grab_release_calls += 1


class LauncherCommandSurfaceTests(unittest.TestCase):
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
        app.root = object()
        app.status_var = FakeStatusVar()
        app.actions = [
            Action(
                id="primary",
                title="Open Primary",
                context="General",
                type="open_url",
                value="https://example.com",
                state="Trusted",
            ),
            Action(
                id="secondary",
                title="Open Secondary",
                context="General",
                type="open_url",
                value="https://example.org",
                state="Trusted",
            ),
        ]
        app.command_groups = []
        app._execute_action_calls = []

        def _execute_action(action: Action) -> None:
            app._execute_action_calls.append(action.id)

        def _open_command_configuration(group: CommandGroup) -> None:
            app._opened_group = group.id

        app._execute_action = _execute_action
        app._open_command_configuration = _open_command_configuration
        return app

    def test_left_click_executes_primary_action(self):
        app = self._app()
        item = CommandItem(
            id="test",
            label="Test",
            primary_action_id="primary",
            action_ids=("secondary",),
        )

        result = app._handle_command_item_left_click(FakeEvent(state=0), CommandGroup("g", "Group"), item)

        self.assertEqual(result, "break")
        self.assertEqual(app._execute_action_calls, ["primary"])

    def test_primary_action_wins_when_listed_after_another_action(self):
        app = self._app()
        item = CommandItem(
            id="test",
            label="Test",
            primary_action_id="primary",
            action_ids=("secondary", "primary"),
        )

        left_click_result = app._handle_command_item_left_click(
            FakeEvent(state=0),
            CommandGroup("g", "Group"),
            item,
        )
        keyboard_result = app._execute_item_primary(item)

        self.assertEqual(left_click_result, "break")
        self.assertEqual(keyboard_result, "break")
        self.assertEqual(app._execute_action_calls, ["primary", "primary"])

    def test_shift_or_ctrl_left_click_opens_configuration(self):
        app = self._app()
        item = CommandItem(id="test", label="Test", primary_action_id="primary")
        group = CommandGroup("group-id", "Group")

        app._handle_command_item_left_click(FakeEvent(state=0x0001), group, item)
        app._handle_command_item_left_click(FakeEvent(state=0x0004), group, item)

        self.assertEqual(app._opened_group, "group-id")
        self.assertEqual(app._execute_action_calls, [])

    def test_item_menu_posts_and_keeps_menu_alive_for_callbacks(self):
        app = self._app()
        item = CommandItem(
            id="test",
            label="Test",
            primary_action_id="primary",
            action_ids=("secondary",),
        )

        with patch("context_palette.launcher.tk.Menu", FakeMenu):
            result = app._show_item_menu(FakeEvent(), item)

        self.assertEqual(result, "break")
        menu = FakeMenu.last_instance
        self.assertIsNotNone(menu)
        self.assertEqual(menu.popup_calls, [(10, 20)])
        self.assertEqual(menu.grab_release_calls, 1)
        self.assertGreaterEqual(len(menu.commands), 2)
        first_callback = menu.commands[0]
        self.assertTrue(callable(first_callback))
        first_callback()
        self.assertEqual(app._execute_action_calls, ["primary"])


if __name__ == "__main__":
    unittest.main()
