import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.command_surface import (
    CommandGroup,
    CommandItem,
    CommandSurfaceError,
    command_item_action_ids,
    command_configuration_paths,
    load_combined_command_groups,
    load_command_groups,
)


class CommandSurfaceTests(unittest.TestCase):
    def test_item_action_ids_are_primary_first_and_unique(self):
        item = CommandItem(
            id="lookup",
            label="Lookup",
            primary_action_id="primary",
            action_ids=("secondary", "primary", "secondary"),
        )

        self.assertEqual(
            command_item_action_ids(item),
            ("primary", "secondary"),
        )

    def test_configuration_paths_follow_group_source(self):
        shared_surface = Path("shared-surface.json")
        local_surface = Path("local-surface.json")
        shared_actions = Path("shared-actions.json")
        local_actions = Path("local-actions.json")

        self.assertEqual(
            command_configuration_paths(
                CommandGroup("shared", "Shared", source_path=shared_surface),
                shared_surface,
                local_surface,
                shared_actions,
                local_actions,
            ),
            (shared_surface, shared_actions),
        )
        self.assertEqual(
            command_configuration_paths(
                CommandGroup("local", "Local", source_path=local_surface),
                shared_surface,
                local_surface,
                shared_actions,
                local_actions,
            ),
            (local_surface, local_actions),
        )

    def test_loads_groups_with_multiple_items(self):
        groups = load_command_groups(ROOT / "data" / "command_surface.json")

        self.assertEqual(groups[0].label, "Product systems")
        self.assertGreaterEqual(len(groups[0].items), 4)
        self.assertEqual(groups[0].items[0].primary_action_id, "colruyt-open-product")
        self.assertIn("product-lookup-rti", groups[0].items[2].action_ids)

    def test_shared_surface_references_existing_actions(self):
        groups = load_command_groups(ROOT / "data" / "command_surface.json")
        action_ids = {
            item["id"]
            for item in json.loads((ROOT / "data" / "actions.json").read_text(encoding="utf-8"))["actions"]
        }
        referenced = {
            action_id
            for group in groups
            for item in group.items
            for action_id in (item.primary_action_id, *item.action_ids)
            if action_id
        }

        self.assertTrue(referenced <= action_ids)

    def test_combined_surface_allows_missing_local_file(self):
        groups = load_combined_command_groups(
            ROOT / "data" / "command_surface.json",
            ROOT / "data" / "missing-command-surface.json",
        )

        self.assertGreaterEqual(len(groups), 4)

    def test_combined_surface_rejects_duplicate_group_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            shared = Path(directory) / "shared.json"
            local = Path(directory) / "local.json"
            payload = {"groups": [{"id": "same", "label": "Shared", "items": []}]}
            shared.write_text(json.dumps(payload), encoding="utf-8")
            local.write_text(
                json.dumps({"groups": [{"id": "SAME", "label": "Local", "items": []}]}),
                encoding="utf-8",
            )

            with self.assertRaises(CommandSurfaceError):
                load_combined_command_groups(shared, local)

    def test_group_rejects_duplicate_item_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "surface.json"
            path.write_text(
                json.dumps(
                    {
                        "groups": [
                            {
                                "id": "group",
                                "label": "Group",
                                "items": [
                                    {"id": "same", "label": "One"},
                                    {"id": "SAME", "label": "Two"},
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(CommandSurfaceError):
                load_command_groups(path)


if __name__ == "__main__":
    unittest.main()
