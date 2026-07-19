from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.retired_feature_cleanup import cleanup_retired_local_configuration


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class RetiredFeatureCleanupTests(unittest.TestCase):
    def test_removes_retired_actions_and_every_local_reference_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            write_json(
                data / "local_actions.json",
                {
                    "actions": [
                        {"id": "keep", "type": "copy_text"},
                        {"id": "snapshot", "type": "restore_window_snapshot"},
                    ]
                },
            )
            write_json(
                data / "local_contexts.json",
                {
                    "contexts": [
                        {"name": "Work", "preferred_action_ids": ["snapshot", "keep"]}
                    ]
                },
            )
            write_json(
                data / "local_command_surface.json",
                {
                    "groups": [
                        {
                            "id": "work",
                            "items": [
                                {
                                    "id": "restore",
                                    "primary_action_id": "snapshot",
                                    "action_ids": ["snapshot", "keep"],
                                }
                            ],
                        }
                    ]
                },
            )
            write_json(
                data / "palette.json",
                {
                    "pinned_action_ids": ["developing-arrange-three-explorers", "keep"],
                    "context_slots": {"Work": ["snapshot", "keep"]},
                },
            )

            report = cleanup_retired_local_configuration(root)
            second_report = cleanup_retired_local_configuration(root)

            self.assertEqual(report.actions_removed, 1)
            self.assertEqual(report.references_removed, 5)
            self.assertEqual(report.files_changed, 4)
            self.assertEqual(second_report.files_changed, 0)
            self.assertTrue((data / "local_actions.json.bak").exists())
            self.assertEqual(
                json.loads((data / "local_actions.json").read_text())["actions"],
                [{"id": "keep", "type": "copy_text"}],
            )
            item = json.loads(
                (data / "local_command_surface.json").read_text()
            )["groups"][0]["items"][0]
            self.assertEqual(item["primary_action_id"], "keep")
            self.assertEqual(item["action_ids"], ["keep"])


if __name__ == "__main__":
    unittest.main()
