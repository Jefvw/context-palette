from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.command_surface import CommandItem, load_command_groups
from context_palette.actions import Action
from context_palette.configuration_data import save_local_command_item, save_local_context
from context_palette.contexts import ContextDefinition, load_contexts
from context_palette.configuration_window import ACTION_TYPE_EXAMPLES, _action_choices, _stable_id
from context_palette.action_types import ACTION_TYPES


class ConfigurationDataTests(unittest.TestCase):
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
            {"Open documentation · Developing": "internal-open-docs"},
        )

    def test_adds_and_updates_personal_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local_contexts.json"

            save_local_context(
                path,
                ContextDefinition(
                    name="Research",
                    description="Find supporting material",
                    preferred_action_ids=("open-docs",),
                ),
            )
            save_local_context(
                path,
                ContextDefinition(
                    name="Research and writing",
                    description="Find and draft",
                    preferred_action_ids=("open-docs", "copy-outline"),
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
                    )
                ],
            )

    def test_adds_and_updates_personal_button(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local_command_surface.json"

            save_local_command_item(
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
            save_local_command_item(
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


if __name__ == "__main__":
    unittest.main()
