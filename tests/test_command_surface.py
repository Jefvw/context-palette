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
    GROUP_PRESENTATION_NESTED_MENU,
    GROUP_PRESENTATION_ROWS,
    MAX_COMMAND_MENU_LEVELS,
    command_configuration_paths,
    command_group_action_ids,
    command_group_launcher_count,
    command_item_action_ids,
    iter_command_items,
    load_combined_command_groups,
    load_command_groups,
)


class CommandSurfaceTests(unittest.TestCase):
    def test_group_launcher_count_follows_presentation(self):
        items = (
            CommandItem("one", "One"),
            CommandItem("two", "Two"),
        )

        self.assertEqual(
            command_group_launcher_count(
                CommandGroup("rows", "Rows", items)
            ),
            2,
        )
        self.assertEqual(
            command_group_launcher_count(
                CommandGroup(
                    "nested",
                    "Nested",
                    items,
                    presentation=GROUP_PRESENTATION_NESTED_MENU,
                )
            ),
            1,
        )

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

    def test_loads_one_standard_group_with_subject_menus(self):
        groups = load_command_groups(ROOT / "data" / "command_surface.json")

        self.assertEqual([group.id for group in groups], ["standard"])
        self.assertEqual(groups[0].label, "Standard")
        self.assertEqual(
            groups[0].presentation,
            GROUP_PRESENTATION_NESTED_MENU,
        )
        self.assertEqual(
            [item.label for item in groups[0].items],
            [
                "Product systems",
                "Work tools",
                "References",
            ],
        )
        self.assertEqual(
            command_group_action_ids(groups[0]),
            ("general-open-python-docs",),
        )
        self.assertEqual(
            groups[0].items[0].primary_action_id,
            "product-lookup-myproduct-any-id",
        )
        levels = {len(path) for path, _item in iter_command_items(groups[0])}
        self.assertEqual(levels, {1, 2, 3})
        technical_articles = next(
            item
            for _path, item in iter_command_items(groups[0])
            if item.id == "technical-articles"
        )
        self.assertIn(
            "product-lookup-rti",
            technical_articles.action_ids,
        )

    def test_shared_surface_distributes_every_active_builtin_action_once(self):
        groups = load_command_groups(ROOT / "data" / "command_surface.json")
        action_ids = {
            item["id"]
            for item in json.loads((ROOT / "data" / "actions.json").read_text(encoding="utf-8"))["actions"]
            if item.get("state", "Active") != "Archived"
        }
        referenced: list[str] = []
        for group in groups:
            referenced.extend(command_group_action_ids(group))
            for _path, item in iter_command_items(group):
                referenced.extend(command_item_action_ids(item))

        self.assertEqual(set(referenced), action_ids)
        self.assertEqual(len(referenced), len(set(referenced)))

    def test_combined_surface_allows_missing_local_file(self):
        groups = load_combined_command_groups(
            ROOT / "data" / "command_surface.json",
            ROOT / "data" / "missing-command-surface.json",
        )

        self.assertEqual([group.id for group in groups], ["standard"])

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

    def test_group_rejects_more_than_three_submenu_levels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "surface.json"
            nested_item: dict[str, object] = {
                "id": "level-4",
                "label": "Level 4",
                "action_ids": ["one"],
            }
            for level in range(MAX_COMMAND_MENU_LEVELS, 0, -1):
                nested_item = {
                    "id": f"level-{level}",
                    "label": f"Level {level}",
                    "items": [nested_item],
                }
            path.write_text(
                json.dumps(
                    {
                        "groups": [
                            {
                                "id": "group",
                                "label": "Group",
                                "presentation": "nested_menu",
                                "items": [nested_item],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                CommandSurfaceError,
                "maximum of 3 submenu levels",
            ):
                load_command_groups(path)

    def test_group_rejects_unknown_presentation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "surface.json"
            for presentation in ("recursive_magic", []):
                with self.subTest(presentation=presentation):
                    path.write_text(
                        json.dumps(
                            {
                                "groups": [
                                    {
                                        "id": "group",
                                        "label": "Group",
                                        "presentation": presentation,
                                        "items": [],
                                    }
                                ]
                            }
                        ),
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(
                        CommandSurfaceError,
                        "invalid presentation",
                    ):
                        load_command_groups(path)

    def test_group_defaults_to_quick_action_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "surface.json"
            path.write_text(
                json.dumps(
                    {
                        "groups": [
                            {"id": "group", "label": "Group", "items": []}
                        ]
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                load_command_groups(path)[0].presentation,
                GROUP_PRESENTATION_ROWS,
            )


if __name__ == "__main__":
    unittest.main()
