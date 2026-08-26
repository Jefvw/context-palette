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
    archive_action_and_references,
    archive_actions_and_references,
    delete_action_and_references,
    delete_actions_and_references,
    inspect_action_references,
    inspect_action_references_many,
    restore_action,
)
from context_palette.persistence import atomic_write_json as real_atomic_write_json


class ActionDeletionTests(unittest.TestCase):
    def test_plural_reviewed_impact_mismatch_is_a_known_no_write_outcome(self) -> None:
        operations = (
            ("archive", "Active", archive_actions_and_references),
            ("delete", "Archived", delete_actions_and_references),
        )
        for label, state, operation in operations:
            with self.subTest(operation=label), TemporaryDirectory() as directory:
                root = Path(directory)
                actions = root / "actions.json"
                contexts = root / "contexts.json"
                palette = root / "palette.json"
                self._write(
                    actions,
                    {"actions": [{"id": "one", "state": state}]},
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
                    patch(
                        "context_palette.action_deletion.atomic_write_json"
                    ) as writer,
                    self.assertRaisesRegex(
                        ActionDeletionError,
                        "does not match the reviewed lifecycle impact",
                    ),
                ):
                    operation(
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

    def test_plural_archive_counts_combined_cleanup_and_writes_each_file_once(self) -> None:
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
                        {"id": "two", "state": "Active"},
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
                report = archive_actions_and_references(
                    actions,
                    ("one", "two"),
                    context_paths=(contexts,),
                    command_surface_paths=(commands,),
                    palette_path=palette,
                )

            self.assertEqual(impact.references_removed, 6)
            self.assertEqual(impact.buttons_removed, 1)
            self.assertEqual(impact.files_changed, 3)
            self.assertEqual(report.references_removed, 6)
            self.assertEqual(report.buttons_removed, 1)
            self.assertEqual(report.files_changed, 4)
            self.assertEqual(
                writes,
                [contexts, commands, palette, actions],
            )
            self.assertEqual(
                [item["state"] for item in self._read(actions)["actions"]],
                ["Archived", "Archived"],
            )
            self.assertEqual(self._read(commands)["groups"][0]["items"], [])

    def test_plural_cleanup_does_not_count_a_promoted_selected_primary_twice(self) -> None:
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
            report = archive_actions_and_references(
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

    def test_selected_dependent_sequence_can_be_archived_and_deleted_with_target(self) -> None:
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

            archive_actions_and_references(
                actions,
                ("target", "sequence"),
                context_paths=(),
                command_surface_paths=(),
                palette_path=palette,
                sequence_paths=(actions,),
            )
            self.assertEqual(
                [item["state"] for item in self._read(actions)["actions"]],
                ["Archived", "Archived"],
            )

            delete_actions_and_references(
                actions,
                ("target", "sequence"),
                context_paths=(),
                command_surface_paths=(),
                palette_path=palette,
                sequence_paths=(actions,),
            )
            self.assertEqual(self._read(actions)["actions"], [])

    def test_plural_failure_restores_exact_primary_and_backup_bytes(self) -> None:
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
            context_backup = contexts.with_name(contexts.name + ".bak")
            context_backup.write_bytes(b"previous context backup\r\n")
            participating = (
                actions,
                actions.with_name(actions.name + ".bak"),
                contexts,
                context_backup,
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
                archive_actions_and_references(
                    actions,
                    ("one",),
                    context_paths=(contexts,),
                    command_surface_paths=(),
                    palette_path=palette,
                )

            after = {
                path: path.read_bytes() if path.exists() else None
                for path in participating
            }
            self.assertEqual(after, before)

    def test_referenced_action_cannot_be_archived_or_deleted_behind_sequence(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actions = root / "actions.json"
            palette = root / "palette.json"
            self._write(
                actions,
                {
                    "actions": [
                        {"id": "target", "title": "Target", "state": "Active"},
                        {
                            "id": "sequence",
                            "title": "Morning setup",
                            "type": "sequence",
                            "value": "sequence-v1",
                            "state": "Active",
                            "steps": [
                                {"kind": "action", "action_id": "target"},
                                {"kind": "action", "action_id": "other"},
                            ],
                        },
                    ]
                },
            )
            self._write(palette, {"pinned_action_ids": []})

            with self.assertRaisesRegex(ActionDeletionError, "Morning setup"):
                archive_action_and_references(
                    actions,
                    "target",
                    context_paths=(),
                    command_surface_paths=(),
                    palette_path=palette,
                    sequence_paths=(actions,),
                )

            data = self._read(actions)
            data["actions"][0]["state"] = "Archived"
            self._write(actions, data)
            with self.assertRaisesRegex(ActionDeletionError, "Morning setup"):
                delete_action_and_references(
                    actions,
                    "target",
                    context_paths=(),
                    command_surface_paths=(),
                    palette_path=palette,
                    sequence_paths=(actions,),
                )

    def test_archived_sequence_blocks_delete_but_not_archive(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actions = root / "actions.json"
            palette = root / "palette.json"
            self._write(
                actions,
                {
                    "actions": [
                        {"id": "target", "title": "Target", "state": "Active"},
                        {
                            "id": "history",
                            "title": "Archived history",
                            "type": "sequence",
                            "state": "Archived",
                            "steps": [{"kind": "action", "action_id": "target"}],
                        },
                    ]
                },
            )
            self._write(palette, {"pinned_action_ids": []})

            archive_action_and_references(
                actions,
                "target",
                context_paths=(),
                command_surface_paths=(),
                palette_path=palette,
                sequence_paths=(actions,),
            )
            with self.assertRaisesRegex(ActionDeletionError, "Archived history"):
                delete_action_and_references(
                    actions,
                    "target",
                    context_paths=(),
                    command_surface_paths=(),
                    palette_path=palette,
                    sequence_paths=(actions,),
                )

    def test_archive_reference_write_failure_rolls_back_every_attempted_file(self) -> None:
        for failure_index in (0, 1):
            with self.subTest(failure_index=failure_index), TemporaryDirectory() as directory:
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
                        {"contexts": [{"name": path.stem, "action_ids": ["keep-me"]}]},
                    )
                self._write(palette, {"pinned_action_ids": []})
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
                    archive_action_and_references(
                        actions,
                        "keep-me",
                        context_paths=context_paths,
                        command_surface_paths=(),
                        palette_path=palette,
                    )

                self.assertEqual(
                    self._read(actions)["actions"][0]["state"],
                    "Active",
                )
                self.assertEqual(
                    self._read(context_paths[0])["contexts"][0]["action_ids"],
                    ["keep-me"],
                )
                self.assertEqual(
                    self._read(context_paths[1])["contexts"][0]["action_ids"],
                    ["keep-me"],
                )

    def test_lifecycle_rejects_invalid_state_transitions(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            active = root / "active.json"
            archived = root / "archived.json"
            palette = root / "palette.json"
            self._write(active, {"actions": [{"id": "active", "state": "Active"}]})
            self._write(
                archived,
                {"actions": [{"id": "archived", "state": "Archived"}]},
            )
            self._write(palette, {"pinned_action_ids": []})

            with self.assertRaisesRegex(ActionDeletionError, "already archived"):
                archive_action_and_references(
                    archived,
                    "archived",
                    context_paths=(),
                    command_surface_paths=(),
                    palette_path=palette,
                )
            with self.assertRaisesRegex(ActionDeletionError, "not archived"):
                restore_action(active, "active")

    def test_permanent_deletion_rejects_active_action_without_changing_references(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actions = root / "actions.json"
            contexts = root / "contexts.json"
            palette = root / "palette.json"
            self._write(
                actions,
                {"actions": [{"id": "active", "state": "Active"}]},
            )
            self._write(
                contexts,
                {"contexts": [{"name": "Work", "action_ids": ["active"]}]},
            )
            self._write(palette, {"pinned_action_ids": ["active"]})

            with self.assertRaisesRegex(
                ActionDeletionError,
                "must be Archived before permanent deletion",
            ):
                delete_action_and_references(
                    actions,
                    "active",
                    context_paths=(contexts,),
                    command_surface_paths=(),
                    palette_path=palette,
                )

            self.assertEqual(
                self._read(actions),
                {"actions": [{"id": "active", "state": "Active"}]},
            )
            self.assertEqual(
                self._read(contexts),
                {"contexts": [{"name": "Work", "action_ids": ["active"]}]},
            )
            self.assertEqual(
                self._read(palette),
                {"pinned_action_ids": ["active"]},
            )

    def test_restore_write_failure_preserves_archived_record(self) -> None:
        with TemporaryDirectory() as directory:
            actions = Path(directory) / "actions.json"
            self._write(
                actions,
                {"actions": [{"id": "archived", "state": "Archived"}]},
            )

            with (
                patch(
                    "context_palette.action_deletion.atomic_write_json",
                    side_effect=OSError("locked"),
                ),
                self.assertRaises(OSError),
            ):
                restore_action(actions, "archived")

            self.assertEqual(
                self._read(actions)["actions"][0]["state"],
                "Archived",
            )

    def test_archive_action_write_failure_restores_reference_placements(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actions = root / "actions.json"
            contexts = root / "contexts.json"
            palette = root / "palette.json"
            self._write(
                actions,
                {"actions": [{"id": "keep-me", "state": "Active"}]},
            )
            self._write(
                contexts,
                {"contexts": [{"name": "Work", "action_ids": ["keep-me"]}]},
            )
            self._write(palette, {"pinned_action_ids": []})

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
                archive_action_and_references(
                    actions,
                    "keep-me",
                    context_paths=(contexts,),
                    command_surface_paths=(),
                    palette_path=palette,
                )

            self.assertEqual(
                self._read(actions)["actions"][0]["state"],
                "Active",
            )
            self.assertEqual(
                self._read(contexts)["contexts"][0]["action_ids"],
                ["keep-me"],
            )

    def test_permanent_delete_write_failure_restores_action_and_references(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actions = root / "actions.json"
            contexts = root / "contexts.json"
            palette = root / "palette.json"
            self._write(
                actions,
                {"actions": [{"id": "keep-me", "state": "Archived"}]},
            )
            self._write(
                contexts,
                {"contexts": [{"name": "Work", "action_ids": ["keep-me"]}]},
            )
            self._write(palette, {"pinned_action_ids": ["keep-me"]})
            before = {
                path: path.read_bytes()
                for path in (actions, contexts, palette)
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
                delete_action_and_references(
                    actions,
                    "keep-me",
                    context_paths=(contexts,),
                    command_surface_paths=(),
                    palette_path=palette,
                )

            self.assertEqual(
                self._read(actions),
                {"actions": [{"id": "keep-me", "state": "Archived"}]},
            )
            self.assertEqual(
                self._read(contexts)["contexts"][0]["action_ids"],
                ["keep-me"],
            )
            self.assertEqual(
                self._read(palette)["pinned_action_ids"],
                ["keep-me"],
            )
            self.assertEqual(
                {path: path.read_bytes() for path in before},
                before,
            )

    def test_archive_retains_record_removes_references_and_restore_is_unassigned(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            actions = root / "actions.json"
            contexts = root / "contexts.json"
            commands = root / "commands.json"
            palette = root / "palette.json"
            original = {
                "id": "keep-me",
                "title": "Keep",
                "type": "copy_text",
                "value": "unchanged",
                "state": "Active",
                "description": "Retained metadata",
            }
            self._write(actions, {"actions": [original]})
            self._write(
                contexts,
                {"contexts": [{"name": "Work", "action_ids": ["keep-me"]}]},
            )
            self._write(
                commands,
                {
                    "groups": [
                        {
                            "id": "tools",
                            "label": "Tools",
                            "items": [
                                {
                                    "id": "only",
                                    "label": "Only",
                                    "targets": [
                                        {"type": "action", "action_id": "keep-me"}
                                    ],
                                }
                            ],
                        }
                    ]
                },
            )
            self._write(
                palette,
                {
                    "pinned_action_ids": ["keep-me"],
                    "context_slots": {"Work": ["keep-me"]},
                },
            )

            report = archive_action_and_references(
                actions,
                "keep-me",
                context_paths=(contexts,),
                command_surface_paths=(commands,),
                palette_path=palette,
            )

            archived = self._read(actions)["actions"][0]
            self.assertEqual(archived, {**original, "state": "Archived"})
            self.assertEqual(report.references_removed, 4)
            self.assertEqual(report.buttons_removed, 1)
            self.assertEqual(self._read(contexts)["contexts"][0]["action_ids"], [])
            self.assertEqual(
                self._read(commands)["groups"],
                [{"id": "tools", "label": "Tools", "items": []}],
            )
            self.assertEqual(self._read(palette)["pinned_action_ids"], [])
            self.assertEqual(self._read(palette)["context_slots"], {"Work": []})

            restore_action(actions, "keep-me")

            self.assertEqual(self._read(actions)["actions"][0], original)
            self.assertEqual(self._read(contexts)["contexts"][0]["action_ids"], [])
            self.assertEqual(
                self._read(commands)["groups"],
                [{"id": "tools", "label": "Tools", "items": []}],
            )
            self.assertEqual(self._read(palette)["pinned_action_ids"], [])

    def test_deletion_preserves_neighboring_work_item_in_mixed_targets(self) -> None:
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
                        {
                            "id": "delete-me",
                            "title": "Delete",
                            "type": "copy_text",
                            "value": "x",
                            "state": "Archived",
                        }
                    ]
                },
            )
            self._write(contexts, {"contexts": []})
            self._write(palette, {"pinned_action_ids": []})
            work_item_target = {
                "type": "work_item",
                "source_id": "product-work",
                "relative_folder": "ISS-ABC-example",
            }
            self._write(
                commands,
                {
                    "groups": [
                        {
                            "id": "work",
                            "label": "Work",
                            "items": [
                                {
                                    "id": "mixed",
                                    "label": "Mixed",
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

    def test_deletion_removes_action_and_all_saved_references(self) -> None:
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
                        {"id": "delete-me", "title": "Delete", "context": "General",
                         "type": "copy_text", "value": "x", "state": "Archived"},
                        {"id": "keep", "title": "Keep", "context": "General",
                         "type": "copy_text", "value": "y", "state": "Active"},
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
                            "label": "Tools",
                            "items": [
                                {
                                    "id": "mixed",
                                    "label": "Mixed",
                                    "primary_action_id": "delete-me",
                                    "action_ids": ["delete-me", "keep"],
                                },
                                {
                                    "id": "only",
                                    "label": "Only",
                                    "primary_action_id": "delete-me",
                                    "action_ids": ["delete-me"],
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
            )

            self.assertEqual(usage.references_removed, 8)
            self.assertEqual(usage.buttons_removed, 1)
            self.assertEqual(report.references_removed, 8)
            self.assertEqual(
                [item["id"] for item in self._read(actions)["actions"]],
                ["keep"],
            )
            self.assertEqual(
                self._read(contexts)["contexts"][0]["preferred_action_ids"],
                ["keep"],
            )
            self.assertEqual(
                self._read(contexts)["contexts"][0]["action_ids"],
                ["keep"],
            )
            command_items = self._read(commands)["groups"][0]["items"]
            self.assertEqual([item["id"] for item in command_items], ["mixed"])
            self.assertEqual(command_items[0]["primary_action_id"], "keep")
            self.assertEqual(command_items[0]["action_ids"], ["keep"])
            self.assertEqual(
                self._read(palette),
                {
                    "pinned_action_ids": ["keep"],
                    "context_slots": {"Work": ["keep"]},
                },
            )

    def test_deletion_cleans_group_actions_and_nested_empty_levels(self) -> None:
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
                        {
                            "id": "delete-me",
                            "title": "Delete",
                            "context": "General",
                            "type": "copy_text",
                            "value": "x",
                            "state": "Archived",
                        },
                        {
                            "id": "keep",
                            "title": "Keep",
                            "context": "General",
                            "type": "copy_text",
                            "value": "y",
                            "state": "Active",
                        },
                    ]
                },
            )
            self._write(contexts, {"contexts": []})
            self._write(palette, {"pinned_action_ids": []})
            self._write(
                commands,
                {
                    "groups": [
                        {
                            "id": "nested",
                            "label": "Nested",
                            "presentation": "nested_menu",
                            "primary_action_id": "delete-me",
                            "action_ids": ["delete-me", "keep"],
                            "items": [
                                {
                                    "id": "parent",
                                    "label": "Parent",
                                    "items": [
                                        {
                                            "id": "leaf",
                                            "label": "Leaf",
                                            "primary_action_id": "delete-me",
                                            "action_ids": ["delete-me"],
                                        }
                                    ],
                                },
                                {
                                    "id": "empty-sibling",
                                    "label": "Empty sibling",
                                    "items": [],
                                },
                            ],
                        },
                        {
                            "id": "empty-menu",
                            "label": "Intentionally empty",
                            "items": [],
                        },
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

            self.assertEqual(report.references_removed, 4)
            self.assertEqual(report.buttons_removed, 2)
            saved_groups = self._read(commands)["groups"]
            self.assertEqual(
                [group["id"] for group in saved_groups],
                ["nested", "empty-menu"],
            )
            group = saved_groups[0]
            self.assertEqual(group["primary_action_id"], "keep")
            self.assertEqual(group["action_ids"], ["keep"])
            self.assertEqual(
                [item["id"] for item in group["items"]],
                ["empty-sibling"],
            )

    @staticmethod
    def _write(path: Path, value: object) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")

    @staticmethod
    def _read(path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
