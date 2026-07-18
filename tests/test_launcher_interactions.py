from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.actions import Action
from context_palette.command_surface import CommandItem
from context_palette.launcher import LauncherApp


class FakeVariable:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class LauncherInteractionTests(unittest.TestCase):
    def test_keyboard_quick_action_runs_primary_action(self):
        app = LauncherApp.__new__(LauncherApp)
        action = Action(
            id="open-docs",
            title="Open documentation",
            context="Developing",
            type="open_url",
            value="https://docs.python.org/",
        )
        app.actions = [action]
        executed: list[Action] = []
        app._execute_action = executed.append
        app.status_var = FakeVariable()

        result = app._execute_item_primary(
            CommandItem(
                id="docs",
                label="Docs",
                primary_action_id="open-docs",
                action_ids=("open-docs",),
            )
        )

        self.assertEqual(result, "break")
        self.assertEqual(executed, [action])

    def test_keyboard_quick_action_explains_missing_assignment(self):
        app = LauncherApp.__new__(LauncherApp)
        app.actions = []
        app.status_var = FakeVariable()

        app._execute_item_primary(CommandItem(id="empty", label="Empty"))

        self.assertIn("no available action", app.status_var.value)


if __name__ == "__main__":
    unittest.main()
