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
    archive_action_and_references,
    delete_action_and_references,
    inspect_action_references,
    restore_action,
)
from context_palette.persistence import atomic_write_json as real_atomic_write_json


class ActionDeletionTests(unittest.TestCase):
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
