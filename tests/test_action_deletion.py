from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.action_deletion import (
    ActionDeletionError,
    ActionDeletionReport,
    commit_action_deletion,
    delete_action_and_references,
    delete_actions_and_references,
    inspect_action_references,
    inspect_action_references_many,
    plan_action_deletion,
)
from context_palette.persistence import atomic_write_json as real_atomic_write_json


class ActionDeletionTests(unittest.TestCase):
    def test_singular_wrapper_forwards_reviewed_impact(self) -> None:
        expected = ActionDeletionReport(3, 1, 2)
        common = {
            "context_paths": (Path("contexts.json"),),
            "command_surface_paths": (Path("commands.json"),),
            "palette_path": Path("palette.json"),
            "sequence_paths": (Path("actions.json"),),
            "expected_report": expected,
        }

        with patch(
            "context_palette.action_deletion.delete_actions_and_references",
            return_value=expected,
        ) as delete_many:
            self.assertEqual(
                delete_action_and_references(
                    Path("actions.json"),
                    "one",
                    **common,
                ),
                expected,
            )

        delete_many.assert_called_once_with(
            Path("actions.json"),
            ("one",),
            expected_configuration_fingerprint=None,
            **common,
        )

    def test_reviewed_delete_rejects_same_count_action_change_before_writing(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actions = root / "actions.json"
            contexts = root / "contexts.json"
            palette = root / "palette.json"
            self._write(
                actions,
                {
                    "actions": [
                        {
                            "id": "one",
                            "title": "Reviewed title",
                            "state": "Active",
                        }
                    ]
                },
            )
            self._write(
                contexts,
                {"contexts": [{"name": "Work", "action_ids": ["one"]}]},
            )
            self._write(palette, {"pinned_action_ids": []})
            plan = plan_action_deletion(
                actions,
                "one",
                context_paths=(contexts,),
                command_surface_paths=(),
                palette_path=palette,
                sequence_paths=(actions,),
            )
            changed = self._read(actions)
            changed["actions"][0]["title"] = "Changed after review"
            self._write(actions, changed)

            with (
                patch("context_palette.action_deletion.atomic_write_json") as writer,
                self.assertRaisesRegex(
                    ActionDeletionError,
                    "changed after review",
                ),
            ):
                commit_action_deletion(plan)

            writer.assert_not_called()
            self.assertEqual(self._read(actions), changed)
            self.assertEqual(
                self._read(contexts)["contexts"][0]["action_ids"],
                ["one"],
            )

    def test_mixed_case_request_uses_canonical_id_for_reference_cleanup(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actions = root / "actions.json"
            contexts = root / "contexts.json"
            commands = root / "commands.json"
            palette = root / "palette.json"
            self._write(
                actions,
                {"actions": [{"id": "Mixed-ID", "state": "Active"}]},
            )
            self._write(
                contexts,
                {
                    "contexts": [
                        {"name": "Work", "action_ids": ["Mixed-ID"]}
                    ]
                },
            )
            self._write(
                commands,
                {
                    "groups": [
                        {
                            "id": "tools",
                            "items": [
                                {"id": "one", "action_ids": ["Mixed-ID"]}
                            ],
                        }
                    ]
                },
            )
            self._write(
                palette,
                {
                    "pinned_action_ids": ["Mixed-ID"],
                    "context_slots": {"Work": ["Mixed-ID"]},
                },
            )

            report = delete_action_and_references(
                actions,
                "MIXED-ID",
                context_paths=(contexts,),
                command_surface_paths=(commands,),
                palette_path=palette,
            )

            self.assertEqual(report.references_removed, 4)
            self.assertEqual(self._read(actions), {"actions": []})
            self.assertEqual(
                self._read(contexts)["contexts"][0]["action_ids"],
                [],
            )
            self.assertEqual(
                self._read(commands)["groups"][0]["items"],
                [],
            )
            self.assertEqual(self._read(palette)["pinned_action_ids"], [])
            self.assertEqual(self._read(palette)["context_slots"], {"Work": []})

    def test_case_colliding_stored_ids_are_rejected_without_writes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actions = root / "actions.json"
            palette = root / "palette.json"
            original = {
                "actions": [
                    {"id": "Duplicate", "state": "Active"},
                    {"id": "duplicate", "state": "Active"},
                ]
            }
            self._write(actions, original)
            self._write(palette, {"pinned_action_ids": []})

            with (
                patch("context_palette.action_deletion.atomic_write_json") as writer,
                self.assertRaisesRegex(ActionDeletionError, "duplicate Action IDs"),
            ):
                delete_action_and_references(
                    actions,
                    "Duplicate",
                    context_paths=(),
                    command_surface_paths=(),
                    palette_path=palette,
                )

            writer.assert_not_called()
            self.assertEqual(self._read(actions), original)

    def test_invalid_utf8_participant_is_reported_as_deletion_error(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actions = root / "actions.json"
            contexts = root / "contexts.json"
            palette = root / "palette.json"
            self._write(actions, {"actions": [{"id": "one"}]})
            contexts.write_bytes(b"\xff\xfe")
            self._write(palette, {"pinned_action_ids": []})

            with self.assertRaisesRegex(
                ActionDeletionError,
                "could not be read as valid JSON",
            ):
                plan_action_deletion(
                    actions,
                    "one",
                    context_paths=(contexts,),
                    command_surface_paths=(),
                    palette_path=palette,
                )

    def test_direct_delete_accepts_active_and_legacy_archived_records(self) -> None:
        for state in ("Active", "Archived"):
            with self.subTest(state=state), TemporaryDirectory() as directory:
                root = Path(directory)
                actions = root / "actions.json"
                palette = root / "palette.json"
                self._write(
                    actions,
                    {"actions": [{"id": "delete-me", "state": state}]},
                )
                self._write(palette, {"pinned_action_ids": []})

                report = delete_action_and_references(
                    actions,
                    "delete-me",
                    context_paths=(),
                    command_surface_paths=(),
                    palette_path=palette,
                )

                self.assertEqual(report, ActionDeletionReport(0, 0, 1))
                self.assertEqual(self._read(actions), {"actions": []})

    def test_reviewed_impact_mismatch_is_a_known_no_write_outcome(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actions = root / "actions.json"
            contexts = root / "contexts.json"
            palette = root / "palette.json"
            self._write(
                actions,
                {"actions": [{"id": "one", "state": "Active"}]},
            )
            self._write(
                contexts,
                {"contexts": [{"name": "Work", "action_ids": ["one"]}]},
            )
            self._write(palette, {"pinned_action_ids": ["one"]})
            actions.with_name(actions.name + ".bak").write_bytes(
                b"action backup\r\n"
            )
            participants = tuple(
                participant
                for path in (actions, contexts, palette)
                for participant in (path, path.with_name(path.name + ".bak"))
            )
            before = {
                path: path.read_bytes() if path.exists() else None
                for path in participants
            }

            with (
                patch("context_palette.action_deletion.atomic_write_json") as writer,
                self.assertRaisesRegex(
                    ActionDeletionError,
                    "does not match the reviewed deletion impact",
                ),
            ):
                delete_actions_and_references(
                    actions,
                    ("one",),
                    context_paths=(contexts,),
                    command_surface_paths=(),
                    palette_path=palette,
                    expected_report=ActionDeletionReport(999, 999, 999),
                )

            writer.assert_not_called()
            self.assertEqual(
                {
                    path: path.read_bytes() if path.exists() else None
                    for path in participants
                },
                before,
            )

    def test_batch_counts_combined_cleanup_and_writes_each_file_once(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actions = root / "actions.json"
            contexts = root / "contexts.json"
            commands = root / "commands.json"
            palette = root / "palette.json"
            self._write(
                actions,
                {
                    "actions": [
                        {"id": "one", "state": "Active"},
                        {"id": "two", "state": "Archived"},
                    ]
                },
            )
            self._write(
                contexts,
                {"contexts": [{"name": "Work", "action_ids": ["one", "two"]}]},
            )
            self._write(
                commands,
                {
                    "groups": [
                        {
                            "id": "root",
                            "items": [
                                {
                                    "id": "combined",
                                    "targets": [
                                        {"type": "action", "action_id": "one"},
                                        {"type": "action", "action_id": "two"},
                                    ],
                                }
                            ],
                        }
                    ]
                },
            )
            self._write(palette, {"pinned_action_ids": ["one", "two"]})

            impact = inspect_action_references_many(
                ("one", "two"),
                context_paths=(contexts,),
                command_surface_paths=(commands,),
                palette_path=palette,
            )
            writes: list[Path] = []

            def record_write(path: Path, data: object) -> None:
                writes.append(path)
                real_atomic_write_json(path, data)

            with patch(
                "context_palette.action_deletion.atomic_write_json",
                side_effect=record_write,
            ):
                report = delete_actions_and_references(
                    actions,
                    ("one", "two"),
                    context_paths=(contexts,),
                    command_surface_paths=(commands,),
                    palette_path=palette,
                    expected_report=ActionDeletionReport(6, 1, 4),
                )

            self.assertEqual(impact, ActionDeletionReport(6, 1, 3))
            self.assertEqual(report, ActionDeletionReport(6, 1, 4))
            self.assertEqual(writes, [contexts, commands, palette, actions])
            self.assertEqual(self._read(actions), {"actions": []})
            self.assertEqual(self._read(commands)["groups"][0]["items"], [])

    def test_batch_cleanup_does_not_count_selected_primary_twice(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actions = root / "actions.json"
            commands = root / "commands.json"
            palette = root / "palette.json"
            self._write(
                actions,
                {
                    "actions": [
                        {"id": "one", "state": "Active"},
                        {"id": "two", "state": "Active"},
                    ]
                },
            )
            self._write(
                commands,
                {
                    "groups": [
                        {
                            "id": "root",
                            "primary_action_id": "one",
                            "action_ids": ["one", "two"],
                            "items": [],
                        }
                    ]
                },
            )
            self._write(palette, {"pinned_action_ids": []})

            impact = inspect_action_references_many(
                ("one", "two"),
                context_paths=(),
                command_surface_paths=(commands,),
                palette_path=palette,
            )
            report = delete_actions_and_references(
                actions,
                ("one", "two"),
                context_paths=(),
                command_surface_paths=(commands,),
                palette_path=palette,
            )

            self.assertEqual(impact.references_removed, 3)
            self.assertEqual(report.references_removed, 3)
            group = self._read(commands)["groups"][0]
            self.assertEqual(group["primary_action_id"], "")
            self.assertEqual(group["action_ids"], [])

    def test_selected_dependent_sequence_and_target_delete_together(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actions = root / "actions.json"
            palette = root / "palette.json"
            self._write(
                actions,
                {
                    "actions": [
                        {"id": "target", "state": "Active"},
                        {
                            "id": "sequence",
                            "title": "Dependent sequence",
                            "type": "sequence",
                            "state": "Active",
                            "steps": [
                                {"kind": "action", "action_id": "target"}
                            ],
                        },
                    ]
                },
            )
            self._write(palette, {"pinned_action_ids": []})

            delete_actions_and_references(
                actions,
                ("target", "sequence"),
                context_paths=(),
                command_surface_paths=(),
                palette_path=palette,
                sequence_paths=(actions,),
            )

            self.assertEqual(self._read(actions), {"actions": []})

    def test_unselected_active_or_legacy_inactive_sequence_blocks_delete(self) -> None:
        for sequence_state in ("Active", "Archived"):
            with (
                self.subTest(sequence_state=sequence_state),
                TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                actions = root / "actions.json"
                palette = root / "palette.json"
                sequence_title = f"{sequence_state} dependent sequence"
                original = {
                    "actions": [
                        {"id": "target", "title": "Target", "state": "Active"},
                        {
                            "id": "sequence",
                            "title": sequence_title,
                            "type": "sequence",
                            "state": sequence_state,
                            "steps": [
                                {"kind": "action", "action_id": "target"}
                            ],
                        },
                    ]
                }
                self._write(actions, original)
                self._write(palette, {"pinned_action_ids": []})

                with self.assertRaisesRegex(ActionDeletionError, sequence_title):
                    delete_action_and_references(
                        actions,
                        "target",
                        context_paths=(),
                        command_surface_paths=(),
                        palette_path=palette,
                        sequence_paths=(actions,),
                    )

                self.assertEqual(self._read(actions), original)

    def test_failed_late_write_restores_exact_primary_and_backup_bytes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actions = root / "actions.json"
            contexts = root / "contexts.json"
            palette = root / "palette.json"
            self._write(
                actions,
                {"actions": [{"id": "one", "state": "Active"}]},
            )
            self._write(
                contexts,
                {"contexts": [{"name": "Work", "action_ids": ["one"]}]},
            )
            self._write(palette, {"pinned_action_ids": []})
            actions.with_name(actions.name + ".bak").write_bytes(
                b"previous action backup\r\n"
            )
            contexts.with_name(contexts.name + ".bak").write_bytes(
                b"previous context backup\r\n"
            )
            participating = tuple(
                participant
                for path in (actions, contexts)
                for participant in (path, path.with_name(path.name + ".bak"))
            )
            before = {
                path: path.read_bytes() if path.exists() else None
                for path in participating
            }

            def fail_action_write(path: Path, data: object) -> None:
                if path == actions:
                    raise OSError("locked")
                real_atomic_write_json(path, data)

            with (
                patch(
                    "context_palette.action_deletion.atomic_write_json",
                    side_effect=fail_action_write,
                ),
                self.assertRaisesRegex(
                    ActionDeletionError,
                    "all attempted configuration changes were restored",
                ),
            ):
                delete_actions_and_references(
                    actions,
                    ("one",),
                    context_paths=(contexts,),
                    command_surface_paths=(),
                    palette_path=palette,
                )

            self.assertEqual(
                {
                    path: path.read_bytes() if path.exists() else None
                    for path in participating
                },
                before,
            )

    def test_failed_early_reference_write_leaves_every_file_unchanged(self) -> None:
        for failure_index in (0, 1):
            with (
                self.subTest(failure_index=failure_index),
                TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                actions = root / "actions.json"
                context_paths = (root / "first.json", root / "second.json")
                palette = root / "palette.json"
                self._write(
                    actions,
                    {"actions": [{"id": "keep-me", "state": "Active"}]},
                )
                for path in context_paths:
                    self._write(
                        path,
                        {
                            "contexts": [
                                {"name": path.stem, "action_ids": ["keep-me"]}
                            ]
                        },
                    )
                self._write(palette, {"pinned_action_ids": []})
                before = {
                    path: path.read_bytes()
                    for path in (actions, *context_paths, palette)
                }
                failing_path = context_paths[failure_index]

                def fail_selected_write(path: Path, data: object) -> None:
                    if path == failing_path:
                        raise OSError("locked")
                    real_atomic_write_json(path, data)

                with (
                    patch(
                        "context_palette.action_deletion.atomic_write_json",
                        side_effect=fail_selected_write,
                    ),
                    self.assertRaises(ActionDeletionError),
                ):
                    delete_action_and_references(
                        actions,
                        "keep-me",
                        context_paths=context_paths,
                        command_surface_paths=(),
                        palette_path=palette,
                    )

                self.assertEqual(
                    {path: path.read_bytes() for path in before},
                    before,
                )

    def test_deletion_removes_all_internal_references_and_empty_item(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actions = root / "actions.json"
            contexts = root / "contexts.json"
            commands = root / "commands.json"
            palette = root / "palette.json"
            work_item = {
                "type": "work_item",
                "source_id": "product-work",
                "relative_folder": "ISS-ABC-example",
            }
            self._write(
                actions,
                {
                    "actions": [
                        {"id": "delete-me", "state": "Active"},
                        {"id": "keep", "state": "Active"},
                    ]
                },
            )
            self._write(
                contexts,
                {
                    "contexts": [
                        {
                            "name": "Work",
                            "preferred_action_ids": ["delete-me", "keep"],
                            "action_ids": ["delete-me", "keep"],
                            "preferred_items": [
                                {"type": "action", "action_id": "delete-me"},
                                work_item,
                            ],
                        }
                    ]
                },
            )
            self._write(
                commands,
                {
                    "groups": [
                        {
                            "id": "tools",
                            "items": [
                                {
                                    "id": "mixed",
                                    "primary_action_id": "delete-me",
                                    "action_ids": ["delete-me", "keep"],
                                    "targets": [
                                        {"type": "action", "action_id": "delete-me"},
                                        work_item,
                                    ],
                                },
                                {
                                    "id": "only",
                                    "targets": [
                                        {"type": "action", "action_id": "delete-me"}
                                    ],
                                },
                            ],
                        }
                    ]
                },
            )
            self._write(
                palette,
                {
                    "pinned_action_ids": ["delete-me", "keep"],
                    "context_slots": {"Work": ["delete-me", "keep"]},
                    "context_item_slots": {
                        "Work": [
                            {"type": "action", "action_id": "delete-me"},
                            work_item,
                        ]
                    },
                },
            )

            usage = inspect_action_references(
                "delete-me",
                context_paths=(contexts,),
                command_surface_paths=(commands,),
                palette_path=palette,
            )
            report = delete_action_and_references(
                actions,
                "delete-me",
                context_paths=(contexts,),
                command_surface_paths=(commands,),
                palette_path=palette,
                expected_report=ActionDeletionReport(10, 1, 4),
            )

            self.assertEqual(usage, ActionDeletionReport(10, 1, 3))
            self.assertEqual(report, ActionDeletionReport(10, 1, 4))
            self.assertEqual(
                [item["id"] for item in self._read(actions)["actions"]],
                ["keep"],
            )
            context = self._read(contexts)["contexts"][0]
            self.assertEqual(context["preferred_action_ids"], ["keep"])
            self.assertEqual(context["action_ids"], ["keep"])
            self.assertEqual(context["preferred_items"], [work_item])
            command_items = self._read(commands)["groups"][0]["items"]
            self.assertEqual([item["id"] for item in command_items], ["mixed"])
            self.assertEqual(command_items[0]["primary_action_id"], "keep")
            self.assertEqual(command_items[0]["action_ids"], ["keep"])
            self.assertEqual(command_items[0]["targets"], [work_item])
            saved_palette = self._read(palette)
            self.assertEqual(saved_palette["pinned_action_ids"], ["keep"])
            self.assertEqual(saved_palette["context_slots"], {"Work": ["keep"]})
            self.assertEqual(
                saved_palette["context_item_slots"],
                {"Work": [work_item]},
            )

    def test_deletion_preserves_neighboring_work_item_in_mixed_targets(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actions = root / "actions.json"
            contexts = root / "contexts.json"
            commands = root / "commands.json"
            palette = root / "palette.json"
            work_item_target = {
                "type": "work_item",
                "source_id": "product-work",
                "relative_folder": "ISS-ABC-example",
            }
            self._write(
                actions,
                {"actions": [{"id": "delete-me", "state": "Archived"}]},
            )
            self._write(contexts, {"contexts": []})
            self._write(palette, {"pinned_action_ids": []})
            self._write(
                commands,
                {
                    "groups": [
                        {
                            "id": "work",
                            "items": [
                                {
                                    "id": "mixed",
                                    "targets": [
                                        {"type": "action", "action_id": "delete-me"},
                                        work_item_target,
                                    ],
                                }
                            ],
                        }
                    ]
                },
            )

            report = delete_action_and_references(
                actions,
                "delete-me",
                context_paths=(contexts,),
                command_surface_paths=(commands,),
                palette_path=palette,
            )

            self.assertEqual(report.references_removed, 1)
            self.assertEqual(report.buttons_removed, 0)
            self.assertEqual(
                self._read(commands)["groups"][0]["items"][0]["targets"],
                [work_item_target],
            )

    @staticmethod
    def _write(path: Path, value: object) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")

    @staticmethod
    def _read(path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
