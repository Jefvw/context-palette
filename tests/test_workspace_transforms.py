import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.workspace_transforms import WORKSPACE_TRANSFORM_GROUPS
from context_palette.actions import transform_text


class WorkspaceTransformCatalogueTests(unittest.TestCase):
    def test_groups_operations_and_labels_are_unique(self):
        group_labels = [group.label for group in WORKSPACE_TRANSFORM_GROUPS]
        transforms = [
            transform
            for group in WORKSPACE_TRANSFORM_GROUPS
            for transform in group.transforms
        ]

        self.assertEqual(len(group_labels), len(set(group_labels)))
        self.assertTrue(all(group.transforms for group in WORKSPACE_TRANSFORM_GROUPS))
        self.assertEqual(
            len(transforms),
            len({transform.operation for transform in transforms}),
        )
        self.assertEqual(
            len(transforms),
            len({transform.label for transform in transforms}),
        )
        self.assertTrue(all(transform.success_message for transform in transforms))

    def test_only_affix_operation_requires_additional_input(self):
        prompting_operations = {
            transform.operation
            for group in WORKSPACE_TRANSFORM_GROUPS
            for transform in group.transforms
            if transform.prompts_for_affixes
        }

        self.assertEqual(prompting_operations, {"prefix_suffix_lines"})

    def test_every_non_prompting_operation_is_implemented(self):
        for group in WORKSPACE_TRANSFORM_GROUPS:
            for transform in group.transforms:
                if not transform.prompts_for_affixes:
                    with self.subTest(operation=transform.operation):
                        transform_text("2\nO'Brien", transform.operation)


if __name__ == "__main__":
    unittest.main()
