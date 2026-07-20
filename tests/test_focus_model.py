from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.actions import Action
from context_palette.contexts import ContextDefinition
from context_palette.focus_model import focus_action_hierarchy, resolve_focus_state
from context_palette.palette_state import PaletteState


class FocusModelTests(unittest.TestCase):
    def test_resolve_discovers_names_seeds_preferences_and_preserves_explicit_slots(self):
        actions = [
            Action("general", "General", "General", "copy_text", "1"),
            Action("database", "Database", "Database", "copy_text", "2"),
        ]
        definitions = [
            ContextDefinition(
                "Developing",
                preferred_action_ids=("database", "missing"),
            ),
            ContextDefinition(
                "General",
                preferred_action_ids=("database",),
            ),
        ]
        state = PaletteState(
            ("general",),
            "Database",
            {"General": ("general",)},
        )

        resolved = resolve_focus_state(actions, definitions, state)

        self.assertEqual(
            resolved.available_names,
            ("Database", "Developing", "General"),
        )
        self.assertEqual(resolved.palette_state.focus_context, "Database")
        self.assertEqual(
            resolved.palette_state.context_slots,
            {
                "General": ("general",),
                "Developing": ("database",),
            },
        )
        self.assertEqual(resolved.palette_state.pinned_action_ids, ("general",))

    def test_resolve_falls_back_to_first_name_but_keeps_focus_when_none_exist(self):
        available = resolve_focus_state(
            [Action("mail", "Mail", "Mail", "copy_text", "1")],
            [ContextDefinition("Developing")],
            PaletteState(focus_context="Missing"),
        )
        empty = resolve_focus_state(
            [],
            [],
            PaletteState(focus_context="Personal"),
        )

        self.assertEqual(available.palette_state.focus_context, "Developing")
        self.assertEqual(empty.available_names, ())
        self.assertEqual(empty.palette_state.focus_context, "Personal")

    def test_hierarchy_uses_explicit_context_and_canonical_order(self):
        actions = [
            Action("one", "First", "General", "copy_text", "1", technology="Text", task="Copy"),
            Action("two", "Second", "Other", "copy_text", "2", technology="Text", task="Copy"),
            Action("three", "Third", "general", "copy_text", "3", technology="", task=""),
            Action("four", "Archived", "General", "copy_text", "4", state="Archived"),
            Action("five", "First", "General", "copy_text", "5", technology="Text", task="Copy"),
        ]

        hierarchy = focus_action_hierarchy(actions, "GENERAL")

        self.assertEqual([technology for technology, _tasks in hierarchy], ["Text", "Other"])
        self.assertEqual(
            [action.id for action in hierarchy[0][1][0][1]],
            ["one", "five"],
        )
        self.assertEqual(hierarchy[1][1][0][0], "Other")
        self.assertEqual(hierarchy[1][1][0][1][0].id, "three")


if __name__ == "__main__":
    unittest.main()
