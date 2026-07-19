from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.actions import Action
from context_palette.command_surface import CommandItem
from context_palette.contexts import ContextDefinition, ContextError
from context_palette.launcher import LauncherApp
from context_palette.palette_state import PaletteState


class FakeVariable:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class LauncherInteractionTests(unittest.TestCase):
    def test_failed_context_reload_preserves_last_known_good_contexts(self):
        app = LauncherApp.__new__(LauncherApp)
        existing = ContextDefinition("General", "Existing context")
        app.context_definitions = [existing]
        app.contexts_path = Path("contexts.json")
        app.local_contexts_path = Path("local_contexts.json")
        app.status_var = FakeVariable()
        app.root = object()

        with (
            patch(
                "context_palette.launcher.load_combined_contexts",
                side_effect=ContextError("invalid context file"),
            ),
            patch("context_palette.launcher.messagebox.showerror") as showerror,
        ):
            app._load_contexts()

        self.assertEqual(app.context_definitions, [existing])
        self.assertIn("kept 1 previous context", app.status_var.value)
        showerror.assert_called_once()

    def test_failed_focus_save_restores_previous_context(self):
        app = LauncherApp.__new__(LauncherApp)
        app.palette_state = PaletteState(("existing",), "General", {})
        app.context_var = FakeVariable()
        app.context_var.set("Developing")
        app.status_var = FakeVariable()
        app.palette_path = Path("palette.json")

        with (
            patch(
                "context_palette.launcher.save_palette_state",
                side_effect=OSError("file is locked"),
            ),
            patch("context_palette.launcher.messagebox.showerror") as showerror,
        ):
            app._change_focus_context()

        self.assertEqual(app.palette_state.focus_context, "General")
        self.assertEqual(app.context_var.value, "General")
        self.assertIn("not changed", app.status_var.value)
        showerror.assert_called_once()

    def test_failed_pin_save_preserves_previous_pins(self):
        action = Action("new", "New action", "General", "copy_text", "Hello")
        app = LauncherApp.__new__(LauncherApp)
        app.palette_state = PaletteState(("existing",), "General", {})
        app.status_var = FakeVariable()
        app.palette_path = Path("palette.json")
        app._selected_action = lambda: action

        with (
            patch(
                "context_palette.launcher.save_palette_state",
                side_effect=OSError("file is locked"),
            ),
            patch("context_palette.launcher.messagebox.showerror") as showerror,
        ):
            app._toggle_selected_pin()

        self.assertEqual(app.palette_state.pinned_action_ids, ("existing",))
        self.assertIn("not changed", app.status_var.value)
        showerror.assert_called_once()

    def test_failed_action_reload_preserves_last_known_good_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            app = LauncherApp.__new__(LauncherApp)
            existing = Action(
                id="existing",
                title="Existing action",
                context="General",
                type="copy_text",
                value="Hello",
            )
            app.actions = [existing]
            app.local_action_ids = {"existing"}
            app.actions_path = Path(directory) / "actions.json"
            app.actions_path.write_text("not json", encoding="utf-8")
            app.local_actions_path = Path(directory) / "local_actions.json"
            app.status_var = FakeVariable()
            app.root = object()

            with patch("context_palette.launcher.messagebox.showerror"):
                app._load_actions()

            self.assertEqual(app.actions, [existing])
            self.assertEqual(app.local_action_ids, {"existing"})
            self.assertIn("could not be loaded", app.status_var.value)

    def test_successful_action_reload_replaces_previous_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            app = LauncherApp.__new__(LauncherApp)
            app.actions = [
                Action("old", "Old action", "General", "copy_text", "Old")
            ]
            app.local_action_ids = {"old"}
            app.actions_path = Path(directory) / "actions.json"
            app.actions_path.write_text(
                json.dumps(
                    {
                        "actions": [
                            {
                                "id": "new",
                                "title": "New action",
                                "context": "General",
                                "type": "copy_text",
                                "value": "New",
                                "state": "Draft",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            app.local_actions_path = Path(directory) / "local_actions.json"
            app.status_var = FakeVariable()

            app._load_actions()

            self.assertEqual([action.id for action in app.actions], ["new"])
            self.assertEqual(app.local_action_ids, set())
            self.assertEqual(app.status_var.value, "Loaded 1 actions")

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
