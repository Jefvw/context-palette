from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.actions import Action
from context_palette.contexts import ContextDefinition
from context_palette.focus_model import actions_for_context, resolve_focus_state
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
            ("General", "Database", "Developing"),
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

    def test_resolve_falls_back_to_general_and_matches_focus_case_insensitively(self):
        available = resolve_focus_state(
            [Action("mail", "Mail", "Mail", "copy_text", "1")],
            [ContextDefinition("Developing")],
            PaletteState(focus_context="Missing"),
        )
        matched = resolve_focus_state(
            [Action("mail", "Mail", "Mail", "copy_text", "1")],
            [],
            PaletteState(focus_context="mail"),
        )
        empty = resolve_focus_state(
            [],
            [],
            PaletteState(focus_context="Personal"),
        )

        self.assertEqual(available.palette_state.focus_context, "General")
        self.assertEqual(matched.palette_state.focus_context, "Mail")
        self.assertEqual(empty.available_names, ("General",))
        self.assertEqual(empty.palette_state.focus_context, "General")

    def test_resolve_canonicalizes_saved_context_slot_keys(self):
        resolved = resolve_focus_state(
            [
                Action("mail-one", "Mail one", "Mail", "copy_text", "1"),
                Action("mail-two", "Mail two", "Mail", "copy_text", "2"),
            ],
            [ContextDefinition("Mail", preferred_action_ids=("mail-two",))],
            PaletteState(
                focus_context="MAIL",
                context_slots={
                    "mail": ("mail-one",),
                    "Mail": ("mail-two",),
                    "Removed context": ("mail-two",),
                },
            ),
        )

        self.assertEqual(resolved.palette_state.focus_context, "Mail")
        self.assertEqual(
            resolved.palette_state.context_slots,
            {
                "Mail": ("mail-two",),
                "Removed context": ("mail-two",),
            },
        )

    def test_context_actions_use_membership_and_canonical_order(self):
        actions = [
            Action("one", "First", "General", "copy_text", "1", technology="Text", task="Copy"),
            Action("two", "Second", "Other", "copy_text", "2", technology="Text", task="Copy"),
            Action("three", "Third", "general", "copy_text", "3", technology="", task=""),
            Action("four", "Archived", "General", "copy_text", "4", state="Archived"),
            Action("five", "First", "General", "copy_text", "5", technology="Text", task="Copy"),
        ]

        general = actions_for_context(actions, "GENERAL")
        other = actions_for_context(actions, "Other")

        self.assertEqual(
            [action.id for action in general],
            ["one", "two", "three", "five"],
        )
        self.assertEqual([action.id for action in other], ["two"])


if __name__ == "__main__":
    unittest.main()
