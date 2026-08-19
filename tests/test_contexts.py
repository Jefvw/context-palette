import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.contexts import (
    ContextDefinition,
    ContextError,
    load_combined_contexts,
    load_contexts,
    update_work_item_context_memberships,
)
from context_palette.palette_items import PaletteItemReference
from context_palette.work_items import WorkItemReference


class ContextTests(unittest.TestCase):
    def test_work_item_memberships_can_be_replaced_across_personal_contexts(self):
        reference = WorkItemReference("work", "ISS-example")
        other = WorkItemReference("work", "ISS-other")
        contexts = [
            ContextDefinition(
                "Current",
                work_item_refs=(reference, other),
                preferred_item_refs=(
                    PaletteItemReference(work_item_ref=reference),
                    PaletteItemReference(work_item_ref=other),
                ),
            ),
            ContextDefinition("New"),
        ]

        updated = update_work_item_context_memberships(
            contexts,
            reference,
            ("New",),
        )

        self.assertEqual(updated[0].work_item_refs, (other,))
        self.assertEqual(
            updated[0].preferred_item_refs,
            (PaletteItemReference(work_item_ref=other),),
        )
        self.assertEqual(updated[1].work_item_refs, (reference,))

    def test_work_item_membership_rejects_unknown_personal_context(self):
        with self.assertRaisesRegex(ContextError, "existing My configuration"):
            update_work_item_context_memberships(
                [ContextDefinition("Known")],
                WorkItemReference("work", "ISS-example"),
                ("Missing",),
            )

    def test_only_shipped_specific_context_is_developing_context_palette(self):
        contexts = load_contexts(ROOT / "data" / "contexts.json")
        action_ids = {
            item["id"]
            for item in json.loads((ROOT / "data" / "actions.json").read_text(encoding="utf-8"))["actions"]
        }

        self.assertEqual(
            [context.name for context in contexts],
            ["Developing Context Palette"],
        )
        context = contexts[0]
        self.assertEqual(len(context.preferred_action_ids), 2)
        self.assertTrue(set(context.preferred_action_ids) <= action_ids)
        self.assertTrue(set(context.action_ids) <= action_ids)

    def test_loads_context_with_members_and_preferred_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contexts.json"
            path.write_text(
                json.dumps(
                    {
                        "contexts": [
                            {
                                "name": "Archives",
                                "description": "Archive lookup",
                                "preferred_action_ids": ["open-archive"],
                                "action_ids": ["open-archive", "copy-archive", "open-archive"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            context = load_contexts(path)[0]
        self.assertEqual(context.name, "Archives")
        self.assertEqual(context.preferred_action_ids, ("open-archive",))
        self.assertEqual(context.action_ids, ("open-archive", "copy-archive"))

    def test_missing_and_empty_action_ids_have_distinct_meanings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contexts.json"
            path.write_text(
                json.dumps(
                    {
                        "contexts": [
                            {"name": "Legacy"},
                            {"name": "Explicitly empty", "action_ids": []},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            legacy, empty = load_contexts(path)

        self.assertIsNone(legacy.action_ids)
        self.assertEqual(empty.action_ids, ())

    def test_accepts_five_and_rejects_more_preferred_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contexts.json"
            path.write_text(
                json.dumps({"contexts": [{"name": "Five", "preferred_action_ids": list("12345") }]}),
                encoding="utf-8",
            )
            self.assertEqual(
                load_contexts(path)[0].preferred_action_ids,
                tuple("12345"),
            )
            path.write_text(
                json.dumps({"contexts": [{"name": "Too many", "preferred_action_ids": list("123456") }]}),
                encoding="utf-8",
            )
            with self.assertRaises(ContextError):
                load_contexts(path)

    def test_combined_contexts_allow_missing_local_file(self):
        with tempfile.TemporaryDirectory() as directory:
            shared = Path(directory) / "contexts.json"
            shared.write_text(json.dumps({"contexts": [{"name": "General"}]}), encoding="utf-8")
            contexts = load_combined_contexts(shared, Path(directory) / "local_contexts.json")
        self.assertEqual([context.name for context in contexts], ["General"])

    def test_combined_contexts_reject_case_insensitive_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            shared = Path(directory) / "contexts.json"
            local = Path(directory) / "local_contexts.json"
            shared.write_text(json.dumps({"contexts": [{"name": "Archives"}]}), encoding="utf-8")
            local.write_text(json.dumps({"contexts": [{"name": "archives"}]}), encoding="utf-8")
            with self.assertRaises(ContextError):
                load_combined_contexts(shared, local)

    def test_personal_context_loads_work_items_and_mixed_preferred_slots(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contexts.json"
            path.write_text(
                json.dumps(
                    {
                        "contexts": [
                            {
                                "name": "Customer",
                                "action_ids": ["open-crm"],
                                "work_item_refs": [
                                    {
                                        "source_id": "customer-work",
                                        "relative_folder": "CAS-ACME-Review",
                                    }
                                ],
                                "preferred_items": [
                                    {
                                        "type": "work_item",
                                        "source_id": "customer-work",
                                        "relative_folder": "CAS-ACME-Review",
                                    },
                                    {"type": "action", "action_id": "open-crm"},
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            context = load_contexts(path)[0]

        reference = WorkItemReference("customer-work", "CAS-ACME-Review")
        self.assertEqual(context.work_item_refs, (reference,))
        self.assertEqual(
            context.preferred_items,
            (
                PaletteItemReference(work_item_ref=reference),
                PaletteItemReference(action_id="open-crm"),
            ),
        )
        self.assertEqual(context.preferred_action_ids, ("open-crm",))

    def test_built_in_context_rejects_work_item_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            shared = Path(directory) / "contexts.json"
            shared.write_text(
                json.dumps(
                    {
                        "contexts": [
                            {
                                "name": "Invalid",
                                "work_item_refs": [
                                    {
                                        "source_id": "personal",
                                        "relative_folder": "PRJ-ACME-Test",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ContextError,
                "Built-in contexts cannot reference personal Work Items",
            ):
                load_combined_contexts(
                    shared,
                    Path(directory) / "local_contexts.json",
                )


if __name__ == "__main__":
    unittest.main()
