from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.action_deletion import (
    delete_action_and_references,
    inspect_action_references,
)


class ActionDeletionTests(unittest.TestCase):
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
                         "type": "copy_text", "value": "x", "state": "Active"},
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

    @staticmethod
    def _write(path: Path, value: object) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")

    @staticmethod
    def _read(path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
