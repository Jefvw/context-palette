from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.action_bulk_lifecycle import (
    BulkActionLifecycleError,
    BulkActionLifecyclePaths,
    commit_bulk_action_deletion,
    eligible_personal_actions_for_deletion,
    plan_bulk_action_deletion,
)
from context_palette.action_deletion import ActionDeletionReport
from context_palette.actions import Action, load_stored_actions


class BulkActionLifecycleTests(unittest.TestCase):
    def test_eligibility_includes_active_and_legacy_inactive_personal_actions(self) -> None:
        active = Action("active", "Active", "General", "copy_text", "one")
        archived = Action(
            "archived",
            "Archived",
            "General",
            "copy_text",
            "two",
            state="Archived",
        )
        built_in = Action("built", "Built in", "General", "copy_text", "three")

        self.assertEqual(
            eligible_personal_actions_for_deletion(
                (active, archived, built_in),
                ("active", "archived"),
            ),
            (active, archived),
        )

    def test_plan_and_commit_delete_mixed_states_in_one_transaction(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._paths(root)
            self._write_fixture(
                paths,
                local_actions=(
                    self._action("active"),
                    self._action("legacy", state="Archived"),
                ),
                local_contexts=(
                    {"name": "Work", "action_ids": ["active", "legacy"]},
                ),
                local_groups=(
                    {
                        "id": "tools",
                        "items": [
                            {
                                "id": "only",
                                "targets": [
                                    {"type": "action", "action_id": "active"},
                                    {"type": "action", "action_id": "legacy"},
                                ],
                            }
                        ],
                    },
                ),
                palette={"pinned_action_ids": ["active", "legacy"]},
            )

            plan = plan_bulk_action_deletion(
                ("active", "legacy"),
                paths=paths,
            )

            self.assertTrue(plan.can_commit)
            self.assertEqual(
                tuple(candidate.status for candidate in plan.candidates),
                ("Ready", "Ready"),
            )
            self.assertEqual(plan.impact.references_removed, 6)
            self.assertEqual(plan.impact.buttons_removed, 1)
            self.assertEqual(plan.impact.files_changed, 4)
            self.assertEqual(commit_bulk_action_deletion(plan), plan.impact)
            self.assertEqual(
                load_stored_actions(
                    paths.local_actions_path,
                    inspect_external_paths=False,
                ),
                [],
            )
            self.assertEqual(
                json.loads(paths.local_contexts_path.read_text(encoding="utf-8"))[
                    "contexts"
                ][0]["action_ids"],
                [],
            )

    def test_unselected_active_and_legacy_sequences_both_block_deletion(self) -> None:
        with TemporaryDirectory() as directory:
            paths = self._paths(Path(directory))
            self._write_fixture(
                paths,
                local_actions=(
                    self._action(
                        "target",
                        action_type="open_url",
                        value="https://target.example",
                    ),
                    self._action(
                        "other",
                        action_type="open_url",
                        value="https://other.example",
                    ),
                    self._sequence("active-sequence", "target", "other"),
                    self._sequence(
                        "legacy-sequence",
                        "target",
                        "other",
                        state="Archived",
                    ),
                ),
            )

            plan = plan_bulk_action_deletion(("target",), paths=paths)

            self.assertFalse(plan.can_commit)
            self.assertEqual(
                plan.candidates[0].blocking_sequence_ids,
                ("active-sequence", "legacy-sequence"),
            )
            with self.assertRaisesRegex(
                BulkActionLifecycleError,
                "sequence dependencies",
            ):
                commit_bulk_action_deletion(plan)

    def test_selected_dependent_sequences_can_be_deleted_with_target(self) -> None:
        with TemporaryDirectory() as directory:
            paths = self._paths(Path(directory))
            self._write_fixture(
                paths,
                local_actions=(
                    self._action(
                        "target",
                        action_type="open_url",
                        value="https://target.example",
                    ),
                    self._action(
                        "other",
                        action_type="open_url",
                        value="https://other.example",
                    ),
                    self._sequence("sequence", "target", "other"),
                ),
            )

            plan = plan_bulk_action_deletion(
                ("target", "sequence"),
                paths=paths,
            )

            self.assertTrue(plan.can_commit)
            commit_bulk_action_deletion(plan)
            self.assertEqual(
                [
                    action.id
                    for action in load_stored_actions(
                        paths.local_actions_path,
                        inspect_external_paths=False,
                    )
                ],
                ["other"],
            )

    def test_every_participant_change_makes_review_stale(self) -> None:
        participant_names = (
            "shared_actions_path",
            "local_actions_path",
            "shared_contexts_path",
            "local_contexts_path",
            "shared_command_surface_path",
            "local_command_surface_path",
            "palette_path",
        )
        for participant_name in participant_names:
            with (
                self.subTest(participant=participant_name),
                TemporaryDirectory() as directory,
            ):
                paths = self._paths(Path(directory))
                self._write_fixture(paths, local_actions=(self._action("one"),))
                plan = plan_bulk_action_deletion(("one",), paths=paths)
                participant = getattr(paths, participant_name)
                data = json.loads(participant.read_text(encoding="utf-8"))
                data["external_change"] = participant_name
                self._write(participant, data)

                with self.assertRaisesRegex(
                    BulkActionLifecycleError,
                    "changed after review",
                ):
                    commit_bulk_action_deletion(plan)

                self.assertEqual(
                    [
                        action.id
                        for action in load_stored_actions(
                            paths.local_actions_path,
                            inspect_external_paths=False,
                        )
                    ],
                    ["one"],
                )

    def test_injected_aggregate_mismatch_is_rejected_before_any_write(self) -> None:
        with TemporaryDirectory() as directory:
            paths = self._paths(Path(directory))
            self._write_fixture(
                paths,
                local_actions=(self._action("one"),),
                local_contexts=(
                    {"name": "Work", "action_ids": ["one"]},
                ),
                palette={"pinned_action_ids": ["one"]},
            )
            plan = plan_bulk_action_deletion(("one",), paths=paths)
            injected = replace(
                plan,
                impact=ActionDeletionReport(999, 999, 999),
            )
            participants = tuple(
                participant
                for path in paths.participant_paths
                for participant in (path, path.with_name(path.name + ".bak"))
            )
            before = {
                path: path.read_bytes() if path.exists() else None
                for path in participants
            }

            with (
                patch(
                    "context_palette.action_bulk_lifecycle.plan_bulk_action_deletion",
                    return_value=injected,
                ),
                self.assertRaisesRegex(
                    BulkActionLifecycleError,
                    "does not match the reviewed deletion impact",
                ),
            ):
                commit_bulk_action_deletion(plan)

            self.assertEqual(
                {
                    path: path.read_bytes() if path.exists() else None
                    for path in participants
                },
                before,
            )

    def test_tampered_reviewed_impact_is_rejected_before_any_write(self) -> None:
        with TemporaryDirectory() as directory:
            paths = self._paths(Path(directory))
            self._write_fixture(
                paths,
                local_actions=(self._action("one"),),
                local_contexts=(
                    {"name": "Work", "action_ids": ["one"]},
                ),
            )
            plan = plan_bulk_action_deletion(("one",), paths=paths)
            tampered = replace(
                plan,
                impact=ActionDeletionReport(999, 999, 999),
            )
            participants = tuple(
                participant
                for path in paths.participant_paths
                for participant in (path, path.with_name(path.name + ".bak"))
            )
            before = {
                path: path.read_bytes() if path.exists() else None
                for path in participants
            }

            with self.assertRaisesRegex(
                BulkActionLifecycleError,
                "does not match the reviewed deletion impact",
            ):
                commit_bulk_action_deletion(tampered)

            self.assertEqual(
                {
                    path: path.read_bytes() if path.exists() else None
                    for path in participants
                },
                before,
            )

    def test_invalid_identity_or_owner_requests_write_nothing(self) -> None:
        with TemporaryDirectory() as directory:
            paths = self._paths(Path(directory))
            self._write_fixture(
                paths,
                shared_actions=(self._action("built"),),
                local_actions=(
                    self._action("active"),
                    self._action("legacy", state="Archived"),
                ),
            )
            participants = paths.participant_paths
            before = {path: path.read_bytes() for path in participants}
            invalid_requests = (
                (),
                ("active", "ACTIVE"),
                ("missing",),
                ("built",),
            )

            for action_ids in invalid_requests:
                with self.subTest(action_ids=action_ids):
                    with self.assertRaises(BulkActionLifecycleError):
                        plan_bulk_action_deletion(action_ids, paths=paths)

            valid_mixed = plan_bulk_action_deletion(
                ("active", "legacy"),
                paths=paths,
            )
            self.assertTrue(valid_mixed.can_commit)
            self.assertEqual(
                {path: path.read_bytes() for path in participants},
                before,
            )
            self.assertFalse(
                any(
                    path.with_name(path.name + ".bak").exists()
                    for path in participants
                )
            )

    @staticmethod
    def _paths(root: Path) -> BulkActionLifecyclePaths:
        return BulkActionLifecyclePaths(
            shared_actions_path=root / "actions.json",
            local_actions_path=root / "local_actions.json",
            shared_contexts_path=root / "contexts.json",
            local_contexts_path=root / "local_contexts.json",
            shared_command_surface_path=root / "command_surface.json",
            local_command_surface_path=root / "local_command_surface.json",
            palette_path=root / "palette.json",
        )

    def _write_fixture(
        self,
        paths: BulkActionLifecyclePaths,
        *,
        shared_actions: tuple[dict[str, object], ...] = (),
        local_actions: tuple[dict[str, object], ...] = (),
        shared_contexts: tuple[dict[str, object], ...] = (),
        local_contexts: tuple[dict[str, object], ...] = (),
        shared_groups: tuple[dict[str, object], ...] = (),
        local_groups: tuple[dict[str, object], ...] = (),
        palette: dict[str, object] | None = None,
    ) -> None:
        self._write(paths.shared_actions_path, {"actions": list(shared_actions)})
        self._write(paths.local_actions_path, {"actions": list(local_actions)})
        self._write(paths.shared_contexts_path, {"contexts": list(shared_contexts)})
        self._write(paths.local_contexts_path, {"contexts": list(local_contexts)})
        self._write(
            paths.shared_command_surface_path,
            {"groups": list(shared_groups)},
        )
        self._write(
            paths.local_command_surface_path,
            {"groups": list(local_groups)},
        )
        self._write(paths.palette_path, palette or {"pinned_action_ids": []})

    @staticmethod
    def _action(
        action_id: str,
        *,
        state: str = "Active",
        action_type: str = "copy_text",
        value: str | None = None,
    ) -> dict[str, object]:
        return {
            "id": action_id,
            "title": action_id.title(),
            "context": "General",
            "type": action_type,
            "value": value if value is not None else action_id,
            "state": state,
        }

    @staticmethod
    def _sequence(
        action_id: str,
        target_id: str,
        other_id: str,
        *,
        state: str = "Active",
    ) -> dict[str, object]:
        return {
            "id": action_id,
            "title": action_id.title(),
            "context": "General",
            "type": "sequence",
            "value": "sequence-v1",
            "state": state,
            "steps": [
                {"kind": "action", "action_id": target_id},
                {"kind": "action", "action_id": other_id},
            ],
        }

    @staticmethod
    def _write(path: Path, value: object) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
