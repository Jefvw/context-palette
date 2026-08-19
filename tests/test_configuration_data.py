from __future__ import annotations

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
    load_command_groups,
)
from context_palette.actions import Action
from context_palette.configuration_data import (
    delete_command_group,
    delete_command_item,
    move_command_group,
    move_command_item,
    save_command_group,
    save_command_item,
    save_context,
)
from context_palette.contexts import ContextDefinition, load_contexts
from context_palette.configuration_window import ACTION_TYPE_EXAMPLES, _action_choices, _stable_id
from context_palette.action_types import ACTION_TYPES
from context_palette.work_items import WorkItemReference


class ConfigurationDataTests(unittest.TestCase):
    def test_rejects_legacy_action_and_work_item_combination_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local_command_surface.json"
            reference = WorkItemReference("product-work", "ISS-ABC-example")

            with self.assertRaisesRegex(
                CommandSurfaceError,
                "cannot combine an Action with a legacy Work Item",
            ):
                save_command_item(
                    path,
                    group_id="work",
                    group_label="Work",
                    item=CommandItem(
                        "invalid",
                        "Invalid",
                        primary_action_id="open-docs",
                        action_ids=("open-docs",),
                        work_item_ref=reference,
                    ),
                )

            self.assertFalse(path.exists())

    def test_work_item_quick_action_round_trips_without_file_or_folder_action(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local_command_surface.json"
            reference = WorkItemReference(
                "product-work",
                "ISS-ABC-example",
            )

            save_command_item(
                path,
                group_id="work",
                group_label="Work",
                item=CommandItem(
                    "current",
                    "Current item",
                    targets=(
                        CommandTarget(action_id="open-docs"),
                        CommandTarget(work_item_ref=reference),
                    ),
                ),
            )

            saved = load_command_groups(path)[0].items[0]
            raw = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(
            saved.targets,
            (
                CommandTarget(action_id="open-docs"),
                CommandTarget(work_item_ref=reference),
            ),
        )
        self.assertEqual(saved.action_ids, ())
        self.assertEqual(
            raw["groups"][0]["items"][0]["targets"],
            [
                {"type": "action", "action_id": "open-docs"},
                {
                    "type": "work_item",
                    "source_id": "product-work",
                    "relative_folder": "ISS-ABC-example",
                },
            ],
        )
    def test_save_context_preserves_explicit_empty_membership(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contexts.json"

            save_context(path, ContextDefinition("Empty", action_ids=()))

            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["contexts"][0]["action_ids"], [])
            self.assertEqual(load_contexts(path)[0].action_ids, ())

    def test_personal_context_round_trips_work_item_membership_and_slot_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contexts.json"
            reference = WorkItemReference("product-work", "ISS-ABC-example")
            context = ContextDefinition(
                "Product",
                preferred_action_ids=("open-docs",),
                action_ids=("open-docs",),
                work_item_refs=(reference,),
                preferred_item_refs=(
                    CommandTarget(work_item_ref=reference),
                    CommandTarget(action_id="open-docs"),
                ),
            )

            save_context(path, context)
            loaded = load_contexts(path)[0]
            raw = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(loaded, context)
        self.assertEqual(
            raw["contexts"][0]["preferred_items"],
            [
                {
                    "type": "work_item",
                    "source_id": "product-work",
                    "relative_folder": "ISS-ABC-example",
                },
                {"type": "action", "action_id": "open-docs"},
            ],
        )

    def test_every_built_in_action_type_has_an_example(self):
        self.assertEqual(set(ACTION_TYPE_EXAMPLES), set(ACTION_TYPES))
        self.assertTrue(all(value.startswith("Example:") for value in ACTION_TYPE_EXAMPLES.values()))

    def test_visible_button_name_generates_stable_id(self):
        self.assertEqual(_stable_id("My useful tools"), "my-useful-tools")

    def test_action_choices_show_names_and_contexts_instead_of_ids(self):
        choices = _action_choices(
            [
                Action(
                    id="internal-open-docs",
                    title="Open documentation",
                    context="Developing",
                    type="open_url",
                    value="https://docs.python.org/",
                )
            ]
        )

        self.assertEqual(
            choices,
            {
                f"{ACTION_TYPES['open_url'].icon} "
                "Open documentation · Developing": "internal-open-docs"
            },
        )

    def test_adds_and_updates_personal_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local_contexts.json"

            save_context(
                path,
                ContextDefinition(
                    name="Research",
                    description="Find supporting material",
                    preferred_action_ids=("open-docs",),
                    action_ids=("open-docs", "copy-outline"),
                ),
            )
            save_context(
                path,
                ContextDefinition(
                    name="Research and writing",
                    description="Find and draft",
                    preferred_action_ids=("open-docs", "copy-outline"),
                    action_ids=("open-docs", "copy-outline", "open-notes"),
                ),
                original_name="Research",
            )

            self.assertEqual(
                load_contexts(path),
                [
                    ContextDefinition(
                        name="Research and writing",
                        description="Find and draft",
                        preferred_action_ids=("open-docs", "copy-outline"),
                        action_ids=("open-docs", "copy-outline", "open-notes"),
                    )
                ],
            )

    def test_adds_and_updates_personal_button(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local_command_surface.json"

            save_command_item(
                path,
                group_id="personal",
                group_label="Personal",
                item=CommandItem(
                    id="docs",
                    label="Documentation",
                    primary_action_id="open-docs",
                    action_ids=("open-docs",),
                ),
            )
            save_command_item(
                path,
                group_id="personal",
                group_label="My tools",
                item=CommandItem(
                    id="reference",
                    label="Reference",
                    primary_action_id="open-docs",
                    action_ids=("open-docs", "copy-outline"),
                ),
                original_group_id="personal",
                original_item_id="docs",
            )

            groups = load_command_groups(path)
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0].label, "My tools")
            self.assertEqual(groups[0].items[0].id, "reference")
            self.assertEqual(
                groups[0].items[0].action_ids,
                ("open-docs", "copy-outline"),
            )
            self.assertTrue(json.loads(path.read_text(encoding="utf-8"))["groups"])

    def test_editing_button_preserves_position_and_unlimited_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "commands.json"
            save_command_group(
                path,
                CommandGroup(
                    "tools",
                    "Tools",
                    (
                        CommandItem("first", "First", action_ids=("one",)),
                        CommandItem("second", "Second", action_ids=("two",)),
                    ),
                    presentation=GROUP_PRESENTATION_NESTED_MENU,
                ),
            )

            save_command_item(
                path,
                group_id="tools",
                group_label="Tools",
                item=CommandItem(
                    "first",
                    "Updated",
                    primary_action_id="one",
                    action_ids=("one", "two", "three", "four", "five", "six"),
                ),
                original_group_id="tools",
                original_item_id="first",
            )

            group = load_command_groups(path)[0]
            self.assertEqual([item.id for item in group.items], ["first", "second"])
            self.assertEqual(
                group.items[0].action_ids,
                ("one", "two", "three", "four", "five", "six"),
            )
            self.assertEqual(
                group.presentation,
                GROUP_PRESENTATION_NESTED_MENU,
            )
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["groups"][0][
                    "presentation"
                ],
                GROUP_PRESENTATION_NESTED_MENU,
            )

    def test_group_and_item_delete_and_reorder_operations(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "commands.json"
            save_command_group(
                path,
                CommandGroup(
                    "first",
                    "First",
                    (
                        CommandItem("one", "One", action_ids=("a",)),
                        CommandItem("two", "Two", action_ids=("b",)),
                    ),
                ),
            )
            save_command_group(path, CommandGroup("second", "Second"))

            self.assertTrue(move_command_item(path, "first", "two", -1))
            self.assertEqual(
                [item.id for item in load_command_groups(path)[0].items],
                ["two", "one"],
            )
            self.assertTrue(move_command_group(path, "second", -1))
            self.assertEqual(
                [group.id for group in load_command_groups(path)],
                ["second", "first"],
            )
            delete_command_item(path, "first", "one")
            self.assertEqual(
                [item.id for item in load_command_groups(path)[1].items],
                ["two"],
            )
            delete_command_group(path, "second")
            self.assertEqual(
                [group.id for group in load_command_groups(path)],
                ["first"],
            )

    def test_nested_items_and_direct_group_actions_survive_guided_operations(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested.json"
            save_command_group(
                path,
                CommandGroup(
                    "nested",
                    "Nested",
                    (
                        CommandItem(
                            "level-1",
                            "Level 1",
                            items=(
                                CommandItem(
                                    "level-2",
                                    "Level 2",
                                    items=(
                                        CommandItem(
                                            "first",
                                            "First",
                                            action_ids=("one",),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                    presentation=GROUP_PRESENTATION_NESTED_MENU,
                    primary_action_id="root",
                    action_ids=("root",),
                ),
            )

            save_command_item(
                path,
                group_id="nested",
                group_label="Nested",
                item=CommandItem(
                    "second",
                    "Second",
                    action_ids=("two",),
                ),
                parent_item_ids=("level-1", "level-2"),
            )
            self.assertTrue(
                move_command_item(path, "nested", "second", -1)
            )
            save_command_item(
                path,
                group_id="nested",
                group_label="Nested",
                item=CommandItem(
                    "renamed",
                    "Renamed",
                    action_ids=("two",),
                ),
                original_item_id="second",
            )

            group = load_command_groups(path)[0]
            level_2 = group.items[0].items[0]
            self.assertEqual(
                [item.id for item in level_2.items],
                ["renamed", "first"],
            )
            self.assertEqual(group.action_ids, ("root",))
            delete_command_item(path, "nested", "level-2")
            group = load_command_groups(path)[0]
            self.assertEqual(group.items[0].items, ())
            self.assertEqual(group.action_ids, ("root",))


if __name__ == "__main__":
    unittest.main()
