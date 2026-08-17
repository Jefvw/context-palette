from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.action_sequences import (
    ActionSequenceError,
    ResolvedActionStep,
    SequenceRunPlan,
    SequenceStep,
    parse_sequence_steps,
    resolve_sequence_steps,
    sequence_reference_ids,
    sequence_steps_to_data,
)


@dataclass(frozen=True)
class FakeAction:
    id: str
    title: str
    type: str
    value: str
    state: str = "Active"
    arguments: tuple[str, ...] = ()
    working_directory: str | None = None


class ActionSequenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.actions = (
            FakeAction("docs", "Documentation", "open_url", "https://example.com"),
            FakeAction("folder", "Project folder", "open_folder", r"C:\work"),
            FakeAction("app", "Editor", "launch_app", r"C:\editor.exe", arguments=("--new",)),
        )

    def test_resolves_a_bounded_reference_plan_and_renders_live_details(self) -> None:
        plan = resolve_sequence_steps(
            (SequenceStep("action", "DOCS"), SequenceStep("wait", milliseconds=250), SequenceStep("action", "app")),
            self.actions,
        )

        self.assertEqual(plan.steps[0], ResolvedActionStep("docs", "Documentation", "open_url", "https://example.com", ()))
        self.assertEqual(
            plan.preview_lines,
            (
                "1. Open website: Documentation | Target: https://example.com",
                "2. Wait 250 ms",
                "3. Launch application: Editor | Target: C:\\editor.exe | Arguments: '--new'",
            ),
        )

    def test_rejects_sequence_shape_and_wait_bounds(self) -> None:
        cases = (
            ((SequenceStep("action", "docs"),), "2 to 12"),
            ((SequenceStep("wait", milliseconds=100), SequenceStep("action", "docs")), "leading"),
            ((SequenceStep("action", "docs"), SequenceStep("wait", milliseconds=100)), "trailing"),
            ((SequenceStep("action", "docs"), SequenceStep("wait", milliseconds=100), SequenceStep("wait", milliseconds=100), SequenceStep("action", "app")), "adjacent"),
            ((SequenceStep("action", "docs"), SequenceStep("wait", milliseconds=99), SequenceStep("action", "app")), "100 to 10000"),
            ((SequenceStep("action", "docs"), SequenceStep("wait", milliseconds=10_001), SequenceStep("action", "app")), "100 to 10000"),
        )
        for sequence, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ActionSequenceError, message):
                resolve_sequence_steps(sequence, self.actions)

    def test_rejects_too_many_steps_and_total_wait(self) -> None:
        too_many = tuple(SequenceStep("action", "docs") for _ in range(13))
        with self.assertRaisesRegex(ActionSequenceError, "2 to 12"):
            resolve_sequence_steps(too_many, self.actions)
        long_waits = (
            SequenceStep("action", "docs"), SequenceStep("wait", milliseconds=10_000), SequenceStep("action", "app"),
            SequenceStep("wait", milliseconds=10_000), SequenceStep("action", "folder"), SequenceStep("wait", milliseconds=10_000), SequenceStep("action", "docs"),
            SequenceStep("wait", milliseconds=100), SequenceStep("action", "app"),
        )
        with self.assertRaisesRegex(ActionSequenceError, "Total wait"):
            resolve_sequence_steps(long_waits, self.actions)

    def test_rejects_missing_archived_unsupported_nested_and_self_references(self) -> None:
        cases = (
            ((FakeAction("old", "Old", "open_url", "https://old", "Archived"),), "Archived"),
            ((FakeAction("copy", "Copy", "copy_text", "text"),), "unsupported"),
            ((FakeAction("nested", "Nested", "sequence", ""),), "another sequence"),
        )
        for actions, message in cases:
            sequence = (SequenceStep("action", actions[0].id), SequenceStep("action", actions[0].id))
            with self.subTest(message=message), self.assertRaisesRegex(ActionSequenceError, message):
                resolve_sequence_steps(sequence, actions)
        with self.assertRaisesRegex(ActionSequenceError, "missing"):
            resolve_sequence_steps(
                (SequenceStep("action", "missing"), SequenceStep("action", "docs")),
                self.actions,
            )
        with self.assertRaisesRegex(ActionSequenceError, "itself"):
            resolve_sequence_steps(
                (SequenceStep("action", "owner"), SequenceStep("action", "docs")),
                (*self.actions, FakeAction("owner", "Owner", "open_url", "https://owner")),
                sequence_id="OWNER",
            )

    def test_rejects_blank_references_and_duplicate_live_ids(self) -> None:
        with self.assertRaisesRegex(ActionSequenceError, "nonblank"):
            resolve_sequence_steps(
                (SequenceStep("action", " "), SequenceStep("action", "docs")),
                self.actions,
            )
        with self.assertRaisesRegex(ActionSequenceError, "Duplicate"):
            resolve_sequence_steps(
                (SequenceStep("action", "docs"), SequenceStep("action", "folder")),
                (*self.actions, FakeAction("DOCS", "Duplicate", "open_url", "https://two")),
            )

    def test_rejects_referenced_action_that_needs_clipboard_input(self) -> None:
        clipboard_action = FakeAction(
            "clipboard-url",
            "Clipboard URL",
            "open_url",
            "https://example.com/%CLIPBOARD_URL%",
        )

        with self.assertRaisesRegex(ActionSequenceError, "clipboard input"):
            resolve_sequence_steps(
                (
                    SequenceStep("action", "clipboard-url"),
                    SequenceStep("action", "docs"),
                ),
                (*self.actions, clipboard_action),
            )

    def test_resolved_plan_is_immutable_and_does_not_execute_actions(self) -> None:
        plan = resolve_sequence_steps(
            (SequenceStep("action", "docs"), SequenceStep("action", "folder")),
            self.actions,
        )
        self.assertIsInstance(plan, SequenceRunPlan)
        with self.assertRaises(AttributeError):
            plan.steps = ()  # type: ignore[misc]

    def test_parse_serialize_and_reference_ids_are_structured_and_side_effect_free(self) -> None:
        steps = parse_sequence_steps([
            {"kind": "action", "action_id": "docs"},
            {"kind": "wait", "milliseconds": 120},
            {"kind": "action", "action_id": "app"},
        ])
        self.assertEqual(sequence_reference_ids(steps), ("docs", "app"))
        self.assertEqual(sequence_steps_to_data(steps), [
            {"kind": "action", "action_id": "docs"},
            {"kind": "wait", "milliseconds": 120},
            {"kind": "action", "action_id": "app"},
        ])
        with self.assertRaisesRegex(ActionSequenceError, "unsupported fields"):
            parse_sequence_steps([{"kind": "action", "action_id": "docs", "command": "x"}])


if __name__ == "__main__":
    unittest.main()
