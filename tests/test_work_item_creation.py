from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.work_item_creation import (
    WorkItemCreationError,
    create_work_item_from_template,
    suggest_work_item_name,
    validate_work_item_name,
)
from context_palette.work_items import WorkItemSource


class WorkItemCreationTests(unittest.TestCase):
    def test_suggestion_uses_optional_project_code_without_enforcing_name(self) -> None:
        self.assertEqual(
            suggest_work_item_name("iss", "cap40", "Age verification", "ab9c"),
            "ISS-CAP40-Age-verification-AB9C",
        )
        self.assertEqual(
            suggest_work_item_name("iss", "cap40", "Age verification"),
            "ISS-CAP40-Age-verification",
        )
        self.assertEqual(validate_work_item_name("My own chosen name"), "My own chosen name")

    def test_invalid_windows_and_marker_names_are_rejected(self) -> None:
        for name in ("", "CON", "bad:name", "item.", "ISS-CAP40-----"):
            with self.subTest(name=name), self.assertRaises(WorkItemCreationError):
                validate_work_item_name(name)

    def test_template_is_copied_to_exact_matching_workbook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workitems = root / "workitems"
            workitems.mkdir()
            template = root / "generic.xlsx"
            template.write_bytes(b"xlsx-template-content")
            source = WorkItemSource("cap40", "CAP40", workitems)

            created = create_work_item_from_template(source, "ISS-CAP40-example", template)

            self.assertEqual(created.folder_path.name, "ISS-CAP40-example")
            self.assertEqual(created.workbook_path.name, "ISS-CAP40-example.xlsx")
            self.assertEqual(created.workbook_path.read_bytes(), template.read_bytes())

            with self.assertRaisesRegex(WorkItemCreationError, "already exists"):
                create_work_item_from_template(source, "ISS-CAP40-example", template)

    def test_failed_template_copy_removes_only_new_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workitems = root / "workitems"
            workitems.mkdir()
            template = root / "generic.xlsx"
            template.write_bytes(b"template")
            existing = workitems / "existing"
            existing.mkdir()
            source = WorkItemSource("cap40", "CAP40", workitems)

            with (
                patch("context_palette.work_item_creation.shutil.copy2", side_effect=OSError("failed")),
                self.assertRaises(WorkItemCreationError),
            ):
                create_work_item_from_template(source, "new-item", template)

            self.assertFalse((workitems / "new-item").exists())
            self.assertTrue(existing.is_dir())


if __name__ == "__main__":
    unittest.main()
