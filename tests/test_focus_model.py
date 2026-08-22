from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.actions import Action
from context_palette.contexts import ContextDefinition
from context_palette.focus_model import (
    actions_for_context,
    palette_items_for_context,
    resolve_focus_state,
)
from context_palette.palette_state import PaletteState
from context_palette.palette_items import PaletteItemReference
from context_palette.work_items import WorkItemReference


class FocusModelTests(unittest.TestCase):
    def test_resolve_discovers_names_seeds_preferences_and_preserves_legacy_pins(self):
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

    def test_empty_explicit_context_drops_stale_saved_slot_references(self):
        greeting = Action(
            "greeting",
            "Professional greeting",
            "General",
            "copy_text",
            "Hello",
        )
        stale_work_item = WorkItemReference("work", "ISS-old")

        resolved = resolve_focus_state(
            [greeting],
            [ContextDefinition("Empty", action_ids=())],
            PaletteState(
                focus_context="Empty",
                context_slots={"Empty": ("greeting",)},
                context_item_slots={
                    "Empty": (
                        PaletteItemReference(action_id="greeting"),
                        PaletteItemReference(work_item_ref=stale_work_item),
                    )
                },
            ),
        )

        self.assertNotIn("Empty", resolved.palette_state.context_slots)
        self.assertNotIn("Empty", resolved.palette_state.context_item_slots)

    def test_saved_slots_preserve_only_current_explicit_context_members(self):
        actions = [
            Action("kept", "Kept", "General", "copy_text", "1"),
            Action("stale", "Stale", "General", "copy_text", "2"),
        ]

        resolved = resolve_focus_state(
            actions,
            [ContextDefinition("Work", action_ids=("kept",))],
            PaletteState(
                focus_context="Work",
                context_slots={"Work": ("stale", "kept")},
            ),
        )

        self.assertEqual(resolved.palette_state.context_slots["Work"], ("kept",))

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

    def test_context_definition_can_assign_built_in_action_without_editing_it(self):
        actions = [
            Action("built-in", "Built in", "General", "copy_text", "1"),
            Action("local", "Local", "General", "copy_text", "2"),
            Action("other", "Other", "General", "copy_text", "3"),
        ]
        definitions = [
            ContextDefinition(
                "My work",
                preferred_action_ids=("built-in",),
                action_ids=("built-in", "local"),
            )
        ]

        focused = actions_for_context(actions, "My work", definitions)
        resolved = resolve_focus_state(
            actions,
            definitions,
            PaletteState(focus_context="My work"),
        )

        self.assertEqual([action.id for action in focused], ["built-in", "local"])
        self.assertEqual(
            resolved.palette_state.context_slots["My work"],
            ("built-in", "local"),
        )

    def test_context_definition_seeds_all_five_preferred_slots(self):
        actions = [
            Action(str(index), str(index), "Work", "copy_text", str(index))
            for index in range(1, 6)
        ]
        preferred = tuple(action.id for action in actions)

        resolved = resolve_focus_state(
            actions,
            [ContextDefinition("Work", preferred_action_ids=preferred)],
            PaletteState(focus_context="Work"),
        )

        self.assertEqual(
            resolved.palette_state.context_slots["Work"],
            preferred,
        )

    def test_context_definition_seeds_mixed_preferred_item_slots(self):
        work_item = WorkItemReference("customer-work", "CAS-ACME-Review")
        preferred = (
            PaletteItemReference(work_item_ref=work_item),
            PaletteItemReference(action_id="follow-up"),
        )
        resolved = resolve_focus_state(
            [Action("follow-up", "Follow up", "General", "copy_text", "x")],
            [
                ContextDefinition(
                    "Customer",
                    preferred_action_ids=("follow-up",),
                    action_ids=("follow-up",),
                    work_item_refs=(work_item,),
                    preferred_item_refs=preferred,
                )
            ],
            PaletteState(focus_context="Customer"),
        )

        self.assertEqual(
            resolved.palette_state.context_item_slots["Customer"],
            preferred,
        )

    def test_explicit_context_membership_replaces_legacy_action_classification(self):
        actions = [
            Action("kept", "Kept", "My work", "copy_text", "1"),
            Action("removed", "Removed", "My work", "copy_text", "2"),
        ]

        focused = actions_for_context(
            actions,
            "My work",
            [ContextDefinition("My work", action_ids=("kept",))],
        )

        self.assertEqual([action.id for action in focused], ["kept"])

    def test_palette_items_for_context_uses_canonical_mixed_membership(self):
        primary_work_item = WorkItemReference("work", "ISS-primary")
        preferred_work_item = PaletteItemReference(
            work_item_ref=WorkItemReference("work", "ISS-preferred")
        )
        actions = [
            Action("kept", "Kept", "My work", "copy_text", "1"),
            Action("legacy-only", "Legacy", "My work", "copy_text", "2"),
            Action(
                "archived",
                "Archived",
                "My work",
                "copy_text",
                "3",
                state="Archived",
            ),
        ]
        definitions = [
            ContextDefinition(
                "My work",
                action_ids=("kept", "archived"),
                work_item_refs=(primary_work_item,),
                preferred_item_refs=(
                    PaletteItemReference(action_id="kept"),
                    preferred_work_item,
                ),
            )
        ]

        references = palette_items_for_context(actions, "My work", definitions)

        self.assertEqual(
            references,
            (
                PaletteItemReference(action_id="kept"),
                PaletteItemReference(work_item_ref=primary_work_item),
                preferred_work_item,
            ),
        )


if __name__ == "__main__":
    unittest.main()
