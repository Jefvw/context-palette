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
    CommandTarget,
    CommandSurfaceError,
    GROUP_PRESENTATION_NESTED_MENU,
    GROUP_PRESENTATION_ROWS,
    MAX_COMMAND_MENU_LEVELS,
    command_configuration_paths,
    command_group_action_ids,
    command_group_launcher_count,
    command_item_action_ids,
    command_item_targets,
    iter_command_items,
    load_combined_command_groups,
    load_command_groups,
)
from context_palette.work_items import WorkItemReference


class CommandSurfaceTests(unittest.TestCase):
    def test_mixed_targets_preserve_action_and_work_item_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local.json"
            path.write_text(
                json.dumps(
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
                                            {"type": "action", "action_id": "open-docs"},
                                            {
                                                "type": "work_item",
                                                "source_id": "product-work",
                                                "relative_folder": "ISS-ABC-example",
                                            },
                                            {
                                                "type": "work_item",
                                                "source_id": "product-work",
                                                "relative_folder": "PRJ-ABC-roadmap",
                                            },
                                            {"type": "action", "action_id": "copy-link"},
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            item = load_command_groups(path)[0].items[0]

        self.assertEqual(
            command_item_targets(item),
            (
                CommandTarget(action_id="open-docs"),
                CommandTarget(
                    work_item_ref=WorkItemReference(
                        "product-work",
                        "ISS-ABC-example",
                    )
                ),
                CommandTarget(
                    work_item_ref=WorkItemReference(
                        "product-work",
                        "PRJ-ABC-roadmap",
                    )
                ),
                CommandTarget(action_id="copy-link"),
            ),
        )
        self.assertEqual(command_item_action_ids(item), ("open-docs", "copy-link"))

    def test_local_quick_action_loads_stable_work_item_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local.json"
            path.write_text(
                json.dumps(
                    {
                        "groups": [
                            {
                                "id": "work",
                                "label": "Work",
                                "items": [
                                    {
                                        "id": "current",
                                        "label": "Current item",
                                        "work_item_ref": {
                                            "source_id": "product-work",
                                            "relative_folder": "ISS-ABC-example",
                                        },
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            item = load_command_groups(path)[0].items[0]

        self.assertEqual(
            item.work_item_ref,
            WorkItemReference("product-work", "ISS-ABC-example"),
        )
        self.assertEqual(command_item_action_ids(item), ())

    def test_quick_action_rejects_mixed_action_and_work_item_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mixed.json"
            path.write_text(
                json.dumps(
                    {
                        "groups": [
                            {
                                "id": "work",
                                "label": "Work",
                                "items": [
                                    {
                                        "id": "mixed",
                                        "label": "Mixed",
                                        "action_ids": ["open"],
                                        "work_item_ref": {
                                            "source_id": "product-work",
                                            "relative_folder": "ISS-ABC-example",
                                        },
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(CommandSurfaceError, "both actions and a Work Item"):
                load_command_groups(path)

    def test_combined_surface_rejects_work_item_reference_in_built_in_file(self):
        with tempfile.TemporaryDirectory() as directory:
            shared = Path(directory) / "shared.json"
            local = Path(directory) / "local.json"
            shared.write_text(
                json.dumps(
                    {
                        "groups": [
                            {
                                "id": "work",
                                "label": "Work",
                                "items": [
                                    {
                                        "id": "private",
                                        "label": "Private",
                                        "work_item_ref": {
                                            "source_id": "product-work",
                                            "relative_folder": "ISS-ABC-example",
                                        },
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            local.write_text('{"groups": []}', encoding="utf-8")

            with self.assertRaisesRegex(CommandSurfaceError, "Built-in Quick actions"):
                load_combined_command_groups(shared, local)

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
        product_systems = groups[0].items[0]
        self.assertEqual(product_systems.primary_action_id, "")
        self.assertEqual(product_systems.action_ids, ())
        self.assertEqual([item.id for item in product_systems.items], ["shopping"])
        shopping = product_systems.items[0]
        self.assertEqual(shopping.primary_action_id, "colruyt-open-product")
        self.assertEqual(
            shopping.action_ids,
            ("colruyt-open-product", "product-lookup-bioplanet"),
        )
        levels = {len(path) for path, _item in iter_command_items(groups[0])}
        self.assertEqual(levels, {1, 2, 3})

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
