from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.work_items import (
    WorkItemDiscoveryError,
    WorkItemSource,
    discover_work_items,
    is_marker_folder_name,
    parse_work_item_name,
    work_item_matches,
)


class WorkItemDiscoveryTests(unittest.TestCase):
    def test_parses_known_unknown_and_unstructured_names(self) -> None:
        issue = parse_work_item_name("ISS-CAP40-age-verification")
        unknown = parse_work_item_name("NEW-CAP40-useful-subject")
        unstructured = parse_work_item_name("notes")

        self.assertEqual(
            (issue.kind_code, issue.kind_name, issue.organisation, issue.subject),
            ("ISS", "Issue", "CAP40", "age-verification"),
        )
        self.assertEqual((unknown.kind_code, unknown.kind_name), ("NEW", "NEW"))
        self.assertEqual(
            (unstructured.kind_code, unstructured.organisation, unstructured.subject),
            (None, None, "notes"),
        )

    def test_detects_zero_multiple_and_distinct_project_codes(self) -> None:
        parsed = parse_work_item_name("ISS-CAP40-AB9C-and-xy9z-and-ab9c")

        self.assertEqual(parsed.project_codes, ("AB9C", "XY9Z"))
        self.assertEqual(
            parse_work_item_name("ISS-CAP40-no-project-code").project_codes,
            (),
        )

    def test_project_code_requires_exact_four_character_token(self) -> None:
        parsed = parse_work_item_name("ISS-CAP40-A9BC-ABC9-XAB9C-AB9C1-AB9C")

        self.assertEqual(parsed.project_codes, ("AB9C",))

    def test_marker_requires_at_least_five_trailing_hyphens(self) -> None:
        self.assertTrue(is_marker_folder_name("ISS-CAP40-----"))
        self.assertTrue(is_marker_folder_name("separator----------"))
        self.assertFalse(is_marker_folder_name("ISS-CAP40----"))
        self.assertFalse(is_marker_folder_name("ISS-----CAP40"))

    def test_discovers_only_direct_non_marker_folders(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workitems"
            root.mkdir()
            direct = root / "ISS-CAP40-direct"
            direct.mkdir()
            nested = direct / "details" / "TRCK-CAP40-nested"
            nested.mkdir(parents=True)
            marker = root / "ISS-CAP40----------"
            marker.mkdir()
            (marker / "ISS-CAP40-hidden").mkdir()
            (root / "not-a-folder.txt").write_text("ignored", encoding="utf-8")

            items = discover_work_items(self._source(root))

            self.assertEqual([item.display_name for item in items], [direct.name])

    def test_exact_case_insensitive_xlsx_match_wins_and_other_files_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workitems"
            folder = root / "TRCK-CAP40-data-reservoir"
            folder.mkdir(parents=True)
            exact = folder / "trck-cap40-DATA-reservoir.XLSX"
            exact.write_text("", encoding="utf-8")
            (folder / "other.xlsx").write_text("", encoding="utf-8")
            (folder / f"{folder.name}.xls").write_text("", encoding="utf-8")

            item = discover_work_items(self._source(root))[0]

            self.assertEqual(item.matching_workbook_path, exact)
            self.assertEqual(item.default_open_path, exact)

    def test_missing_exact_workbook_falls_back_to_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workitems"
            folder = root / "QST-CAP40-analysis"
            folder.mkdir(parents=True)
            (folder / "unrelated.xlsx").write_text("", encoding="utf-8")

            item = discover_work_items(self._source(root))[0]

            self.assertIsNone(item.matching_workbook_path)
            self.assertEqual(item.default_open_path, folder)

    def test_unavailable_source_fails_without_creating_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing = Path(temporary_directory) / "missing" / "workitems"
            source = self._source(missing)

            with self.assertRaisesRegex(WorkItemDiscoveryError, "unavailable"):
                discover_work_items(source)

            self.assertFalse(missing.exists())

    def test_search_combines_text_project_code_and_personal_tag_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workitems"
            folder = root / "ISS-CAP40-AB9C-age-verification"
            folder.mkdir(parents=True)
            item = discover_work_items(self._source(root))[0]

            self.assertTrue(work_item_matches(item, "issue verification"))
            self.assertTrue(
                work_item_matches(
                    item,
                    "cap40",
                    tags=("urgent",),
                    project_code="ab9c",
                    tag="URGENT",
                )
            )
            self.assertFalse(work_item_matches(item, "verification", project_code="XY9Z"))
            self.assertFalse(work_item_matches(item, "verification", tags=("urgent",), tag="later"))

    def test_source_requires_stable_id_name_and_absolute_path(self) -> None:
        with self.assertRaises(WorkItemDiscoveryError):
            WorkItemSource("CAP40 Product", "CAP40", Path("C:/workitems"))
        with self.assertRaises(WorkItemDiscoveryError):
            WorkItemSource("cap40-product", " ", Path("C:/workitems"))
        with self.assertRaises(WorkItemDiscoveryError):
            WorkItemSource("cap40-product", "CAP40", Path("relative/workitems"))

    def _source(self, root: Path) -> WorkItemSource:
        return WorkItemSource("cap40-product", "CAP40 Product", root)


if __name__ == "__main__":
    unittest.main()
