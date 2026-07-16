from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.configuration_check import validate_project_configuration


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def valid_project(root: Path) -> None:
    write_json(
        root / "data" / "actions.json",
        {
            "actions": [
                {
                    "id": "copy-one",
                    "title": "Copy one",
                    "context": "General",
                    "type": "copy_text",
                    "value": "one",
                    "state": "Draft",
                }
            ]
        },
    )
    write_json(
        root / "data" / "contexts.json",
        {"contexts": [{"name": "General", "preferred_action_ids": ["copy-one"]}]},
    )
    write_json(
        root / "data" / "command_surface.json",
        {
            "groups": [
                {
                    "id": "general",
                    "label": "General",
                    "items": [
                        {
                            "id": "copy",
                            "label": "Copy",
                            "primary_action_id": "copy-one",
                            "action_ids": ["copy-one"],
                        }
                    ],
                }
            ]
        },
    )
    (root / "data" / "cheatsheets").mkdir(parents=True)
    (root / "data" / "layouts").mkdir(parents=True)


class ConfigurationCheckTests(unittest.TestCase):
    def test_valid_configuration_reports_loaded_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid_project(root)

            report = validate_project_configuration(root)

        self.assertTrue(report.ok)
        self.assertEqual(report.errors, ())
        self.assertEqual(report.counts["actions"], 1)
        self.assertEqual(report.counts["contexts"], 1)
        self.assertEqual(report.counts["command_groups"], 1)

    def test_missing_action_references_are_reported_with_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid_project(root)
            write_json(
                root / "data" / "contexts.json",
                {"contexts": [{"name": "Email", "preferred_action_ids": ["missing"]}]},
            )
            write_json(
                root / "data" / "palette.json",
                {
                    "pinned_action_ids": ["also-missing"],
                    "focus_context": "General",
                    "context_slots": {},
                },
            )

            report = validate_project_configuration(root)

        self.assertFalse(report.ok)
        self.assertTrue(any("Context 'Email'" in error and "missing" in error for error in report.errors))
        self.assertTrue(any("Pinned action" in error and "also-missing" in error for error in report.errors))

    def test_invalid_file_is_reported_without_stopping_other_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid_project(root)
            (root / "data" / "actions.json").write_text("not json", encoding="utf-8")

            report = validate_project_configuration(root)

        self.assertFalse(report.ok)
        self.assertTrue(any("Actions:" in error and "valid JSON" in error for error in report.errors))
        self.assertEqual(report.counts["contexts"], 1)


if __name__ == "__main__":
    unittest.main()
