import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.cheatsheets import (
    draft_action_from_cheatsheet_item,
    filter_cheatsheet,
    load_cheatsheet,
    load_cheatsheets,
)


class CheatSheetTests(unittest.TestCase):
    def test_shared_powertoys_sheet_loads_and_includes_command_palette_shortcut(self):
        sheets = load_cheatsheets(ROOT / "data" / "cheatsheets")
        sheet = next(sheet for sheet in sheets if sheet.id == "powertoys-feature-shortcuts")

        filtered = filter_cheatsheet(sheet, "command palette")

        self.assertEqual(filtered.sections[0].items[0].detail, "Win + Alt + Space")

    def test_shared_company_reference_sheet_loads_and_finds_servicenow_prefix(self):
        sheets = load_cheatsheets(ROOT / "data" / "cheatsheets")
        sheet = next(sheet for sheet in sheets if sheet.id == "company-reference-prefixes")

        filtered = filter_cheatsheet(sheet, "SCTASK")

        self.assertEqual(filtered.sections[0].items[0].label, "SCTASK — Service Catalog tasks")

    def test_load_cheatsheet(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "win11.json"
            path.write_text(
                json.dumps(
                    {
                        "id": "win11",
                        "title": "Windows 11",
                        "kind": "application",
                        "aliases": ["windows"],
                        "summary": "Useful Windows shortcuts.",
                        "updated_at": "2026-07-11",
                        "sections": [
                            {
                                "title": "Productivity",
                                "items": [
                                    {
                                        "label": "Clipboard history",
                                        "detail": "Win + V",
                                        "tags": ["clipboard"],
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            sheet = load_cheatsheet(path)

        self.assertEqual(sheet.id, "win11")
        self.assertEqual(sheet.sections[0].items[0].label, "Clipboard history")

    def test_load_cheatsheets_returns_empty_list_when_directory_is_missing(self):
        sheets = load_cheatsheets(Path("missing-cheatsheets-folder"))

        self.assertEqual(sheets, [])

    def test_filter_cheatsheet_matches_items(self):
        sheet = load_cheatsheet(self._write_sheet())

        filtered = filter_cheatsheet(sheet, "clipboard")

        self.assertEqual(len(filtered.sections), 1)
        self.assertEqual(filtered.sections[0].items[0].label, "Clipboard history")

    def test_filter_cheatsheet_returns_no_sections_without_match(self):
        sheet = load_cheatsheet(self._write_sheet())

        filtered = filter_cheatsheet(sheet, "missing")

        self.assertEqual(filtered.sections, ())

    def test_draft_action_from_cheatsheet_item(self):
        sheet = load_cheatsheet(self._write_sheet())
        item = sheet.sections[0].items[0]

        action = draft_action_from_cheatsheet_item(sheet, item)

        self.assertEqual(action.title, "Clipboard history")
        self.assertEqual(action.context, "Windows 11")
        self.assertEqual(action.value, "Clipboard history: Win + V")
        self.assertEqual(action.state, "Draft")

    def _write_sheet(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "win11.json"
        path.write_text(
            json.dumps(
                {
                    "id": "win11",
                    "title": "Windows 11",
                    "kind": "application",
                    "aliases": ["windows"],
                    "summary": "Useful Windows shortcuts.",
                    "updated_at": "2026-07-11",
                    "sections": [
                        {
                            "title": "Productivity",
                            "items": [
                                {
                                    "label": "Clipboard history",
                                    "detail": "Win + V",
                                    "tags": ["clipboard"],
                                },
                                {
                                    "label": "Open Settings",
                                    "detail": "Win + I",
                                    "tags": ["system"],
                                },
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return path


if __name__ == "__main__":
    unittest.main()
