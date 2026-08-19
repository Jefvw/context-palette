import json
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.action_types import ACTION_TYPES
from context_palette.configuration_window import CONFIGURATION_NAVIGATION
from context_palette.data_catalog import DATA_ASSET_CATALOG


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _table_rows(section: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in section.splitlines():
        if not line.startswith("|") or line.startswith("| ---"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 2:
            rows[cells[0].replace("`", "").strip()] = cells[1]
    return rows


class DocumentationSemanticsTests(unittest.TestCase):
    def test_current_policy_uses_active_archived_lifecycle(self):
        contributing = _read("CONTRIBUTING.md")
        self.assertIn("Active/Archived Action lifecycle", contributing)
        current_guides = [ROOT / "README.md", ROOT / "CONTRIBUTING.md"]
        current_guides.extend(
            path
            for path in (ROOT / "docs").glob("*.md")
            if path.name != "DECISIONS.md"
        )
        current_guides.extend((ROOT / "integrations").glob("*.md"))
        retired_policy = re.compile(
            r"Capture\s*(?:→|->)\s*Draft\s*(?:→|->)\s*Test\s*"
            r"(?:→|->)\s*Refine\s*(?:→|->)\s*Trusted|"
            r"\brequires? Trusted state\b|\btrust promotion\b",
            re.IGNORECASE,
        )

        for path in current_guides:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIsNone(retired_policy.search(path.read_text(encoding="utf-8")))

    def test_data_model_asset_table_matches_executable_catalogue(self):
        data_model = _read("docs/DATA_MODEL.md")
        marker = "| Storage or constrained pattern | Stable asset ID |"
        self.assertIn(marker, data_model)
        table = data_model.split(marker, 1)[1].split("\n\n", 1)[0]

        documented: dict[str, tuple[str, int | None]] = {}
        for line in table.splitlines():
            if not line.startswith("|") or line.startswith("| ---"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) != 7:
                continue
            location = cells[0].strip("` ")
            asset_id = cells[1].strip("` ")
            schema_text = cells[6].strip("` ")
            schema = None if schema_text in {"None", "—", "N/A"} else int(schema_text)
            documented[asset_id] = (location, schema)

        expected = {
            spec.asset_id: (
                str(spec.relative_path)
                if spec.relative_path is not None
                else str(spec.relative_pattern),
                spec.schema_version,
            )
            for spec in DATA_ASSET_CATALOG
        }
        self.assertEqual(documented, expected)

    def test_mvp_action_type_count_matches_catalogue(self):
        mvp = _read("docs/MVP.md")
        match = re.search(
            r"\| Explicit action execution \| Implemented \| (\d+) allow-listed types\b",
            mvp,
        )

        self.assertIsNotNone(match)
        self.assertEqual(int(match.group(1)), len(ACTION_TYPES))

    def test_configure_shortcuts_name_every_current_destination(self):
        shortcuts = _read("docs/SHORTCUTS.md")
        configure_section = shortcuts.split("## Configure", 1)[1].split("\n## ", 1)[0]
        documented = _table_rows(configure_section)
        destinations = dict(CONFIGURATION_NAVIGATION)
        expected = {
            "Alt+A": destinations["actions"],
            "Alt+T": destinations["types"],
            "Alt+C": destinations["contexts"],
            "Alt+Q": destinations["buttons"],
            "Alt+W": destinations["work_items"],
            "Alt+B": destinations["backup_restore"],
            "Alt+D": destinations["diagnostics"],
        }

        for shortcut, destination in expected.items():
            with self.subTest(shortcut=shortcut):
                result = documented[shortcut].replace("&", "and").casefold()
                label = destination.replace("&", "and").casefold()
                self.assertIn(label, result)
        self.assertIn("section", documented["Ctrl+Tab"].casefold())
        self.assertIn("section", documented["Ctrl+Shift+Tab"].casefold())

    def test_shortcuts_describe_mixed_action_and_work_item_dispatch(self):
        shortcuts = _read("docs/SHORTCUTS.md")
        main_palette = shortcuts.split("## Main palette", 1)[1].split("\n## ", 1)[0]
        documented = _table_rows(main_palette)

        self.assertIn("selected Action", documented["Enter"])
        self.assertIn("selected Work Item", documented["Enter"])
        self.assertIn("folder", documented["Shift+Enter with a Work Item selected"])

    def test_current_ui_guides_omit_retired_rail_language(self):
        retired = re.compile(
            r"\bcommand[- ]rail\b|\brail[- ]controls?\b|\brail order\b|"
            r"\bcompact rail\b|\btighter rail\b|\brail symbols?\b|"
            r"\bAction tools\b|\bWork tools\b|\bright-side button\b|"
            r"\bwider right side\b",
            re.IGNORECASE,
        )
        for relative_path in (
            "README.md",
            "docs/HELP.md",
            "docs/README.md",
            "docs/SHORTCUTS.md",
            "docs/TESTING.md",
        ):
            with self.subTest(path=relative_path):
                self.assertIsNone(retired.search(_read(relative_path)))

    def test_file_configuration_uses_current_membership_and_target_formats(self):
        guide = _read("docs/CONFIGURE_WITH_FILES.md")
        json_blocks = re.findall(r"```json\n(.*?)\n```", guide, flags=re.DOTALL)

        self.assertGreaterEqual(len(json_blocks), 4)
        for index, block in enumerate(json_blocks):
            with self.subTest(block=index):
                json.loads(block)
        self.assertNotIn('"contexts": ["Database"]', guide)
        self.assertNotIn('"primary_action_id"', guide)
        self.assertIn('"targets"', guide)
        self.assertIn("Slots `6-0`", guide)

    def test_ocr_guide_names_the_actual_result_choices(self):
        ocr_setup = _read("docs/OCR_SETUP.md")

        self.assertIn("**Replace**, **Append**, or", ocr_setup)
        self.assertNotIn("**Yes** to replace", ocr_setup)
        self.assertNotIn("**No** to append", ocr_setup)

    def test_architecture_mentions_every_production_module(self):
        architecture = _read("docs/ARCHITECTURE.md")
        module_names = {
            path.name
            for path in (ROOT / "src" / "context_palette").glob("*.py")
            if path.name != "__init__.py"
        }

        missing = sorted(name for name in module_names if name not in architecture)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
