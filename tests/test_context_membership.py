from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from context_palette.actions import Action, load_stored_actions
from context_palette.configuration_data import save_contexts
from context_palette.context_membership import (
    CONTEXT_MEMBERSHIP_VERSION,
    actions_with_canonical_contexts,
    append_actions_with_context_memberships,
    migrate_legacy_action_contexts,
    update_action_with_context_memberships,
)
from context_palette.contexts import ContextDefinition, ContextError, load_contexts
from context_palette.palette_state import load_palette_state


def write_actions(path: Path, actions: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps({"actions": actions}, indent=2) + "\n",
        encoding="utf-8",
    )


class CanonicalContextProjectionTests(unittest.TestCase):
    def test_context_definitions_override_stale_action_memberships(self) -> None:
        actions = [
            Action("one", "One", "Legacy", "copy_text", "one"),
            Action("two", "Two", "General", "copy_text", "two"),
        ]
        definitions = [
            ContextDefinition("Legacy", action_ids=()),
            ContextDefinition("Current", action_ids=("one",)),
            ContextDefinition(
                "Preferred",
                preferred_action_ids=("two",),
                action_ids=(),
            ),
        ]

        projected = actions_with_canonical_contexts(actions, definitions)

        self.assertEqual(projected[0].effective_contexts, ("Current",))
        self.assertEqual(projected[1].effective_contexts, ("Preferred",))

    def test_legacy_membership_remains_readable_until_a_context_is_explicit(self) -> None:
        action = Action("one", "One", "Legacy", "copy_text", "one")

        projected = actions_with_canonical_contexts(
            [action],
            [ContextDefinition("Legacy")],
        )

        self.assertEqual(projected[0].effective_contexts, ("Legacy",))


class ContextMembershipPersistenceTests(unittest.TestCase):
    def test_append_stores_membership_only_in_context_definition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actions_path = root / "local_actions.json"
            shared_contexts_path = root / "contexts.json"
            local_contexts_path = root / "local_contexts.json"
            save_contexts(shared_contexts_path, [])
            save_contexts(
                local_contexts_path,
                [ContextDefinition("Personal", action_ids=())],
            )
            action = Action(
                "new",
                "New",
                "Personal",
                "copy_text",
                "value",
                contexts=("Personal",),
            )

            append_actions_with_context_memberships(
                actions_path,
                [action],
                actions_are_local=True,
                shared_contexts_path=shared_contexts_path,
                local_contexts_path=local_contexts_path,
            )

            raw = json.loads(actions_path.read_text(encoding="utf-8"))
            self.assertNotIn("contexts", raw["actions"][0])
            self.assertEqual(
                load_contexts(local_contexts_path)[0].action_ids,
                ("new",),
            )
            projected = actions_with_canonical_contexts(
                load_stored_actions(actions_path),
                load_contexts(local_contexts_path),
            )
            self.assertEqual(projected[0].effective_contexts, ("Personal",))

    def test_local_action_cannot_leak_into_built_in_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actions_path = root / "local_actions.json"
            shared_contexts_path = root / "contexts.json"
            local_contexts_path = root / "local_contexts.json"
            save_contexts(
                shared_contexts_path,
                [ContextDefinition("Built in", action_ids=())],
            )
            action = Action(
                "private",
                "Private",
                "Built in",
                "copy_text",
                "secret",
            )

            with self.assertRaisesRegex(
                ContextError,
                "cannot be assigned to Built-in context",
            ):
                append_actions_with_context_memberships(
                    actions_path,
                    [action],
                    actions_are_local=True,
                    shared_contexts_path=shared_contexts_path,
                    local_contexts_path=local_contexts_path,
                )

            self.assertFalse(actions_path.exists())
            self.assertEqual(load_contexts(shared_contexts_path)[0].action_ids, ())

    def test_explicit_personal_import_route_can_create_missing_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actions_path = root / "local_actions.json"
            shared_contexts_path = root / "contexts.json"
            local_contexts_path = root / "local_contexts.json"
            save_contexts(shared_contexts_path, [])
            action = Action(
                "imported",
                "Imported",
                "Reference sheet",
                "copy_text",
                "value",
            )

            append_actions_with_context_memberships(
                actions_path,
                [action],
                actions_are_local=True,
                shared_contexts_path=shared_contexts_path,
                local_contexts_path=local_contexts_path,
                create_missing_local_contexts=True,
            )

            created = load_contexts(local_contexts_path)
            self.assertEqual(len(created), 1)
            self.assertEqual(created[0].name, "Reference sheet")
            self.assertEqual(created[0].action_ids, ("imported",))

    def test_edit_moves_membership_and_removes_obsolete_preference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actions_path = root / "local_actions.json"
            shared_contexts_path = root / "contexts.json"
            local_contexts_path = root / "local_contexts.json"
            write_actions(
                actions_path,
                [
                    {
                        "id": "move",
                        "title": "Before",
                        "type": "copy_text",
                        "value": "before",
                        "state": "Active",
                    }
                ],
            )
            save_contexts(shared_contexts_path, [])
            save_contexts(
                local_contexts_path,
                [
                    ContextDefinition(
                        "Before",
                        preferred_action_ids=("move",),
                        action_ids=("move",),
                    ),
                    ContextDefinition("After", action_ids=()),
                ],
            )
            previous = Action(
                "move",
                "Before",
                "Before",
                "copy_text",
                "before",
            )
            updated = Action(
                "move",
                "After",
                "After",
                "copy_text",
                "after",
            )

            update_action_with_context_memberships(
                actions_path,
                updated,
                previous,
                action_is_local=True,
                shared_contexts_path=shared_contexts_path,
                local_contexts_path=local_contexts_path,
            )

            definitions = {
                context.name: context
                for context in load_contexts(local_contexts_path)
            }
            self.assertEqual(definitions["Before"].action_ids, ())
            self.assertEqual(definitions["Before"].preferred_action_ids, ())
            self.assertEqual(definitions["After"].action_ids, ("move",))
            stored = load_stored_actions(actions_path)[0]
            self.assertEqual(stored.title, "After")
            self.assertEqual(stored.effective_contexts, ())

    def test_context_write_failure_rolls_back_new_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actions_path = root / "local_actions.json"
            shared_contexts_path = root / "contexts.json"
            local_contexts_path = root / "local_contexts.json"
            save_contexts(shared_contexts_path, [])
            save_contexts(
                local_contexts_path,
                [ContextDefinition("Personal", action_ids=())],
            )
            action = Action(
                "new",
                "New",
                "Personal",
                "copy_text",
                "value",
            )

            with patch(
                "context_palette.context_membership.save_contexts",
                side_effect=ContextError("locked"),
            ):
                with self.assertRaisesRegex(ContextError, "locked"):
                    append_actions_with_context_memberships(
                        actions_path,
                        [action],
                        actions_are_local=True,
                        shared_contexts_path=shared_contexts_path,
                        local_contexts_path=local_contexts_path,
                    )

            self.assertEqual(load_stored_actions(actions_path), [])


class ContextMembershipMigrationTests(unittest.TestCase):
    def test_migration_unions_legacy_membership_and_marks_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared_actions_path = root / "actions.json"
            local_actions_path = root / "local_actions.json"
            shared_contexts_path = root / "contexts.json"
            local_contexts_path = root / "local_contexts.json"
            palette_path = root / "palette.json"
            write_actions(
                shared_actions_path,
                [
                    {
                        "id": "shared",
                        "title": "Shared",
                        "type": "copy_text",
                        "value": "shared",
                        "state": "Active",
                        "contexts": ["Built in", "New personal context"],
                    }
                ],
            )
            write_actions(
                local_actions_path,
                [
                    {
                        "id": "local",
                        "title": "Local",
                        "type": "copy_text",
                        "value": "local",
                        "state": "Archived",
                        "contexts": ["Personal", "Built in"],
                    }
                ],
            )
            save_contexts(
                shared_contexts_path,
                [ContextDefinition("Built in", action_ids=())],
            )
            save_contexts(
                local_contexts_path,
                [ContextDefinition("Personal", action_ids=())],
            )
            palette_path.write_text(
                json.dumps(
                    {
                        "pinned_action_ids": ["shared"],
                        "focus_context": "General",
                        "context_slots": {},
                    }
                ),
                encoding="utf-8",
            )

            report = migrate_legacy_action_contexts(
                shared_actions_path=shared_actions_path,
                local_actions_path=local_actions_path,
                shared_contexts_path=shared_contexts_path,
                local_contexts_path=local_contexts_path,
                palette_path=palette_path,
            )

            self.assertEqual(report.memberships_migrated, 3)
            self.assertEqual(report.contexts_created, 1)
            self.assertEqual(report.incompatible_memberships_skipped, 1)
            shared_context = load_contexts(shared_contexts_path)[0]
            self.assertEqual(shared_context.action_ids, ("shared",))
            local_contexts = {
                context.name: context
                for context in load_contexts(local_contexts_path)
            }
            self.assertEqual(local_contexts["Personal"].action_ids, ("local",))
            self.assertEqual(
                local_contexts["New personal context"].action_ids,
                ("shared",),
            )
            self.assertEqual(
                load_palette_state(palette_path).context_membership_version,
                CONTEXT_MEMBERSHIP_VERSION,
            )
            self.assertEqual(
                load_palette_state(palette_path).pinned_action_ids,
                ("shared",),
            )

            repeated = migrate_legacy_action_contexts(
                shared_actions_path=shared_actions_path,
                local_actions_path=local_actions_path,
                shared_contexts_path=shared_contexts_path,
                local_contexts_path=local_contexts_path,
                palette_path=palette_path,
            )

            self.assertTrue(repeated.already_current)

    def test_clean_explicit_configuration_does_not_create_local_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared_actions_path = root / "actions.json"
            shared_contexts_path = root / "contexts.json"
            palette_path = root / "palette.json"
            write_actions(
                shared_actions_path,
                [
                    {
                        "id": "shared",
                        "title": "Shared",
                        "type": "copy_text",
                        "value": "shared",
                        "state": "Active",
                    }
                ],
            )
            save_contexts(
                shared_contexts_path,
                [ContextDefinition("Built in", action_ids=("shared",))],
            )

            report = migrate_legacy_action_contexts(
                shared_actions_path=shared_actions_path,
                local_actions_path=root / "local_actions.json",
                shared_contexts_path=shared_contexts_path,
                local_contexts_path=root / "local_contexts.json",
                palette_path=palette_path,
            )

            self.assertEqual(report.files_changed, 0)
            self.assertFalse(palette_path.exists())


if __name__ == "__main__":
    unittest.main()
