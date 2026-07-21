from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.work_item_storage import (
    WorkItemMetadata,
    WorkItemCreationSettings,
    WorkItemStorageError,
    load_work_item_metadata,
    load_work_item_creation_settings,
    load_work_item_sources,
    save_work_item_metadata,
    save_work_item_creation_settings,
    save_work_item_sources,
    work_item_metadata_key,
)
from context_palette.work_items import WorkItemSource


class WorkItemStorageTests(unittest.TestCase):
    def test_missing_local_files_load_as_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            self.assertEqual(load_work_item_sources(root / "sources.json"), ())
            self.assertEqual(load_work_item_metadata(root / "metadata.json"), {})
            self.assertEqual(
                load_work_item_creation_settings(root / "settings.json"),
                WorkItemCreationSettings(),
            )

    def test_creation_settings_round_trip_machine_local_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "local_work_item_settings.json"
            settings = WorkItemCreationSettings(root / "templates" / "generic.xlsx")

            save_work_item_creation_settings(path, settings)

            self.assertEqual(load_work_item_creation_settings(path), settings)

    def test_sources_round_trip_and_atomic_replacement_preserves_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "local_work_item_sources.json"
            first = WorkItemSource("cap40", "CAP40", root / "cap40" / "workitems")
            second = WorkItemSource("cap49", "CAP49", root / "cap49" / "workitems")

            save_work_item_sources(path, (first,))
            save_work_item_sources(path, (first, second))

            self.assertEqual(load_work_item_sources(path), (first, second))
            backup = json.loads(path.with_suffix(".json.bak").read_text(encoding="utf-8"))
            self.assertEqual([item["id"] for item in backup["sources"]], ["cap40"])

    def test_duplicate_or_malformed_sources_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "sources.json"
            absolute = str(root / "workitems")
            path.write_text(
                json.dumps(
                    {
                        "sources": [
                            {"id": "cap40", "name": "One", "workitems_path": absolute},
                            {"id": "cap40", "name": "Two", "workitems_path": absolute},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(WorkItemStorageError, "Duplicate"):
                load_work_item_sources(path)

            path.write_text("not json", encoding="utf-8")
            with self.assertRaisesRegex(WorkItemStorageError, "could not be read"):
                load_work_item_sources(path)

    def test_metadata_round_trip_normalizes_tags_and_uses_stable_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local_work_item_metadata.json"
            key = work_item_metadata_key("cap40", "ISS-CAP40-age-verification")

            save_work_item_metadata(
                path,
                {key: WorkItemMetadata((" Urgent ", "data   quality", "urgent"))},
            )

            self.assertEqual(
                load_work_item_metadata(path),
                {key: WorkItemMetadata(("urgent", "data quality"))},
            )
            self.assertNotIn(str(Path(directory)), path.read_text(encoding="utf-8"))

    def test_metadata_rejects_absolute_or_nested_identity_and_non_text_tags(self) -> None:
        with self.assertRaises(WorkItemStorageError):
            work_item_metadata_key("cap40", "nested/folder")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.json"
            path.write_text(
                json.dumps({"work_items": {"cap40/item": {"tags": [42]}}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(WorkItemStorageError, "tags must be text"):
                load_work_item_metadata(path)

    def test_local_work_item_files_are_ignored_by_git(self) -> None:
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("/data/local_work_item_sources.json", gitignore)
        self.assertIn("/data/local_work_item_metadata.json", gitignore)
        self.assertIn("/data/local_work_item_settings.json", gitignore)


if __name__ == "__main__":
    unittest.main()
