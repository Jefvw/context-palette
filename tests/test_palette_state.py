import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.actions import Action, ActionError
from context_palette.palette_state import (
    PaletteState,
    action_slots,
    load_palette_state,
    save_palette_state,
    toggle_pin,
)
from context_palette.focus_model import resolve_focus_state
from context_palette.contexts import ContextDefinition


class PaletteStateTests(unittest.TestCase):
    def setUp(self):
        self.actions = [
            Action("a", "A", "Mail", "copy_text", "a"),
            Action("b", "B", "Mail", "copy_text", "b"),
            Action("c", "C", "General", "copy_text", "c"),
        ]

    def test_pins_use_1_to_5_and_context_uses_6_to_9_with_duplicates(self):
        state = PaletteState(("a", "c"), "Mail", {"Mail": ("a", "b")})

        slots = action_slots(self.actions, state)

        self.assertEqual(slots[1].id, "a")
        self.assertEqual(slots[2].id, "c")
        self.assertEqual(slots[6].id, "a")
        self.assertEqual(slots[7].id, "b")

    def test_toggle_pin_limits_pins_to_five(self):
        state = PaletteState(("1", "2", "3", "4", "5"), "General", {})
        with self.assertRaises(ActionError):
            toggle_pin(state, "6")
        self.assertEqual(toggle_pin(state, "3").pinned_action_ids, ("1", "2", "4", "5"))

    def test_state_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "palette.json"
            state = PaletteState(("a",), "Mail", {"Mail": ("a", "b")})
            save_palette_state(path, state)
            loaded = load_palette_state(path)
        self.assertEqual(loaded, state)

    def test_read_failure_is_reported_as_an_action_error(self):
        path = Path("palette.json")

        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", side_effect=OSError("file is locked")),
        ):
            with self.assertRaisesRegex(
                ActionError,
                r"Palette configuration could not be read: palette\.json",
            ):
                load_palette_state(path)

    def test_context_slots_are_filled_with_general_fallbacks(self):
        slots = action_slots(self.actions, PaletteState((), "Mail", {}))

        self.assertEqual(slots[6].id, "a")
        self.assertEqual(slots[7].id, "b")
        self.assertEqual(slots[8].id, "c")

    def test_preferred_slots_fill_with_context_members_before_global_actions(self):
        actions = [
            Action("preferred", "Preferred", "Mail", "copy_text", "a"),
            Action("unrelated", "Unrelated", "Database", "copy_text", "b"),
            Action(
                "member",
                "Also useful for mail",
                "Mail",
                "copy_text",
                "c",
                contexts=("Mail", "Customer support"),
            ),
        ]

        slots = action_slots(
            actions,
            PaletteState((), "Mail", {"Mail": ("preferred",)}),
        )

        self.assertEqual(
            [slots[number].id for number in (6, 7, 8)],
            ["preferred", "member", "unrelated"],
        )

    def test_resolved_mixed_case_slot_key_is_used_by_action_slots(self):
        state = resolve_focus_state(
            self.actions,
            [ContextDefinition("Mail")],
            PaletteState((), "MAIL", {"mail": ("b", "a")}),
        ).palette_state

        slots = action_slots(self.actions, state)

        self.assertEqual(state.focus_context, "Mail")
        self.assertEqual([slots[6].id, slots[7].id], ["b", "a"])


if __name__ == "__main__":
    unittest.main()
