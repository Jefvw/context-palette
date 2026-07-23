from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.context_deletion import (
    ContextDeletionError,
    delete_context_and_memberships,
    rename_context_and_references,
)
from context_palette.contexts import ContextDefinition
from context_palette.persistence import atomic_write_json


class ContextDeletionTests(unittest.TestCase):
    def test_rename_updates_action_memberships_and_palette_state(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            contexts = root / "contexts.json"
            shared_actions = root / "actions.json"
            local_actions = root / "local_actions.json"
            palette = root / "palette.json"
            self._write(
                contexts,
                {"contexts": [{"name": "Old", "description": "Before"}]},
            )
            self._write(
                shared_actions,
                {
                    "actions": [
                        {
                            "id": "mixed",
                            "title": "Mixed",
                            "context": "Old",
                            "contexts": ["Old", "Keep"],
                            "type": "copy_text",
                            "value": "x",
                            "state": "Active",
                        }
                    ]
                },
            )
            self._write(
                local_actions,
                {
                    "actions": [
                        {
                            "id": "only",
                            "title": "Only",
                            "context": "old",
                            "contexts": ["OLD"],
                            "type": "copy_text",
                            "value": "y",
                            "state": "Active",
                        }
                    ]
                },
            )
            self._write(
                palette,
                {
                    "focus_context": "OLD",
                    "context_slots": {"Old": ["mixed"]},
                },
            )

            report = rename_context_and_references(
                contexts,
                "Old",
                ContextDefinition("New", "After"),
                action_paths=(shared_actions, local_actions),
                palette_path=palette,
            )

            self.assertEqual(report.action_references_updated, 4)
            self.assertEqual(report.palette_references_updated, 2)
            self.assertEqual(
                self._read(contexts),
                {"contexts": [{"name": "New", "description": "After"}]},
            )
            self.assertEqual(
                self._read(shared_actions)["actions"][0]["contexts"],
                ["New", "Keep"],
            )
            self.assertEqual(
                self._read(shared_actions)["actions"][0]["context"],
                "New",
            )
            self.assertEqual(
                self._read(local_actions)["actions"][0]["contexts"],
                ["New"],
            )
            self.assertEqual(
                self._read(local_actions)["actions"][0]["context"],
                "New",
            )
            self.assertEqual(
                self._read(palette),
                {
                    "focus_context": "New",
                    "context_slots": {"New": ["mixed"]},
                },
            )

    def test_interrupted_rename_keeps_both_context_names_defined(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            contexts = root / "contexts.json"
            actions = root / "actions.json"
            palette = root / "palette.json"
            self._write(contexts, {"contexts": [{"name": "Old"}]})
            self._write(
                actions,
                {
                    "actions": [
                        {
                            "id": "one",
                            "title": "One",
                            "context": "Old",
                            "contexts": ["Old"],
                            "type": "copy_text",
                            "value": "x",
                            "state": "Active",
                        }
                    ]
                },
            )
            self._write(palette, {})

            real_writer = atomic_write_json
            write_count = 0

            def fail_second_write(
                path: Path,
                value: object,
                **options: object,
            ) -> None:
                nonlocal write_count
                write_count += 1
                if write_count == 2:
                    raise OSError("locked")
                real_writer(path, value, **options)

            with patch(
                "context_palette.context_deletion.atomic_write_json",
                side_effect=fail_second_write,
            ):
                with self.assertRaises(OSError):
                    rename_context_and_references(
                        contexts,
                        "Old",
                        ContextDefinition("New"),
                        action_paths=(actions,),
                        palette_path=palette,
                    )

            self.assertEqual(
                [item["name"] for item in self._read(contexts)["contexts"]],
                ["Old", "New"],
            )

    def test_successful_rename_backup_contains_pre_rename_definition(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            contexts = root / "contexts.json"
            actions = root / "actions.json"
            palette = root / "palette.json"
            original = {"contexts": [{"name": "Old", "description": "Before"}]}
            self._write(contexts, original)
            self._write(actions, {"actions": []})
            self._write(palette, {})

            rename_context_and_references(
                contexts,
                "Old",
                ContextDefinition("New", "After"),
                action_paths=(actions,),
                palette_path=palette,
            )

            self.assertEqual(
                self._read(contexts.with_name("contexts.json.bak")),
                original,
            )

    def test_delete_removes_action_memberships_and_palette_state(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            contexts = root / "contexts.json"
            shared_actions = root / "actions.json"
            local_actions = root / "local_actions.json"
            palette = root / "palette.json"
            self._write(
                contexts,
                {
                    "contexts": [
                        {"name": "Delete"},
                        {"name": "Keep"},
                    ]
                },
            )
            self._write(
                shared_actions,
                {
                    "actions": [
                        {
                            "id": "mixed",
                            "title": "Mixed",
                            "context": "Delete",
                            "contexts": ["Delete", "Keep"],
                            "type": "copy_text",
                            "value": "x",
                            "state": "Active",
                        }
                    ]
                },
            )
            self._write(
                local_actions,
                {
                    "actions": [
                        {
                            "id": "only",
                            "title": "Only",
                            "context": "Delete",
                            "contexts": [],
                            "type": "copy_text",
                            "value": "y",
                            "state": "Active",
                        }
                    ]
                },
            )
            self._write(
                palette,
                {
                    "focus_context": "Delete",
                    "context_slots": {"Delete": ["mixed"], "Keep": ["mixed"]},
                },
            )

            report = delete_context_and_memberships(
                contexts,
                "delete",
                action_paths=(shared_actions, local_actions),
                palette_path=palette,
            )

            self.assertEqual(report.action_memberships_removed, 2)
            self.assertEqual(report.palette_references_removed, 2)
            self.assertEqual(
                [item["name"] for item in self._read(contexts)["contexts"]],
                ["Keep"],
            )
            mixed = self._read(shared_actions)["actions"][0]
            self.assertEqual(mixed["contexts"], ["Keep"])
            self.assertEqual(mixed["context"], "Keep")
            only = self._read(local_actions)["actions"][0]
            self.assertEqual(only["context"], "General")
            self.assertEqual(
                self._read(palette),
                {
                    "focus_context": "General",
                    "context_slots": {"Keep": ["mixed"]},
                },
            )
            self.assertTrue(contexts.with_name("contexts.json.bak").exists())

    def test_missing_context_does_not_change_files(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            contexts = root / "contexts.json"
            actions = root / "actions.json"
            palette = root / "palette.json"
            original = {"contexts": [{"name": "Keep"}]}
            self._write(contexts, original)
            self._write(actions, {"actions": []})
            self._write(palette, {})

            with self.assertRaises(ContextDeletionError):
                delete_context_and_memberships(
                    contexts,
                    "Missing",
                    action_paths=(actions,),
                    palette_path=palette,
                )

            self.assertEqual(self._read(contexts), original)

    @staticmethod
    def _write(path: Path, value: object) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")

    @staticmethod
    def _read(path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
