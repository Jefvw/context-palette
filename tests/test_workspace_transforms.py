import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.workspace_transforms import (
    WORKSPACE_TRANSFORM_GROUPS,
    WORKSPACE_TRANSFORMS,
)
from context_palette.actions import ActionError, transform_text


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

    def test_parameter_metadata_matches_defaults(self):
        for transform in WORKSPACE_TRANSFORMS.values():
            with self.subTest(operation=transform.operation):
                self.assertLessEqual(
                    len(transform.parameter_defaults),
                    len(transform.parameter_labels),
                )

    def test_new_general_text_operations(self):
        cases = (
            ("collapse_blank_lines", "one\n\n\n\ntwo", (), "one\n\ntwo"),
            ("literal_replace", "red blue red", ("red", ""), " blue "),
            (
                "keep_lines_containing",
                "Invoice 1\nNote\ninvoice 2",
                ("invoice",),
                "Invoice 1\ninvoice 2",
            ),
            (
                "remove_lines_containing",
                "Invoice 1\nNote\ninvoice 2",
                ("invoice",),
                "Note",
            ),
            ("split_delimiter", "red,green,blue", (",",), "red\ngreen\nblue"),
            ("join_delimiter", "red\ngreen\nblue", (" | ",), "red | green | blue"),
            ("comma_list_plain", "red\n2\nblue", (), "red, 2, blue"),
            (
                "comma_list_single_quotes",
                "red\n2\nblue",
                (),
                "'red', 2, 'blue'",
            ),
            (
                "comma_list_double_quotes",
                "red\n2\nblue",
                (),
                '"red", 2, "blue"',
            ),
            ("url_encode", "A value/é", (), "A%20value%2F%C3%A9"),
            ("url_decode", "A%20value%2F%C3%A9", (), "A value/é"),
            ("sql_escape_quotes", "O'Brien", (), "O''Brien"),
        )
        for operation, source, arguments, expected in cases:
            with self.subTest(operation=operation):
                self.assertEqual(
                    transform_text(source, operation, arguments=arguments),
                    expected,
                )

    def test_naming_style_operations(self):
        cases = {
            "camel_case": "customerAccountId",
            "pascal_case": "CustomerAccountId",
            "snake_case": "customer_account_id",
            "screaming_snake_case": "CUSTOMER_ACCOUNT_ID",
            "kebab_case": "customer-account-id",
            "readable_words": "Customer account ID",
        }
        for operation, expected in cases.items():
            with self.subTest(operation=operation):
                self.assertEqual(
                    transform_text("customerAccountID", operation),
                    expected,
                )

    def test_json_operations_and_actionable_error(self):
        source = '{"name":"Jef","items":[1,2]}'
        pretty = transform_text(source, "json_pretty")

        self.assertIn('\n  "name": "Jef"', pretty)
        self.assertEqual(transform_text(pretty, "json_minify"), source)
        with self.assertRaisesRegex(ActionError, "line 1, column 2"):
            transform_text("{broken", "json_pretty")

    def test_windows_path_and_file_uri_round_trip(self):
        uri = transform_text(
            r"C:\Work items\ISS-CAP40.xlsx",
            "path_to_file_uri",
        )

        self.assertEqual(uri, "file:///C:/Work%20items/ISS-CAP40.xlsx")
        self.assertEqual(
            transform_text(uri, "file_uri_to_path"),
            r"C:\Work items\ISS-CAP40.xlsx",
        )

    def test_parameterized_operations_reject_missing_or_empty_input(self):
        with self.assertRaisesRegex(ActionError, "requires 2 parameters"):
            transform_text("text", "literal_replace")
        with self.assertRaisesRegex(ActionError, "Find cannot be empty"):
            transform_text("text", "literal_replace", arguments=("", "new"))
        with self.assertRaisesRegex(ActionError, "Delimiter .*cannot be empty"):
            transform_text("text", "split_delimiter", arguments=("",))


if __name__ == "__main__":
    unittest.main()
