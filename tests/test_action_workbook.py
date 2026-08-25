from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from context_palette.action_types import CREATABLE_ACTION_TYPES
from context_palette.action_workbook import (
    ACTION_HEADERS,
    MAX_ACTION_ROWS,
    ActionWorkbookError,
    read_action_import_workbook,
    workbook_digest,
    write_action_import_template,
)


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _replace_zip_part(path: Path, name: str, payload: bytes) -> None:
    with zipfile.ZipFile(path) as source:
        parts = {item.filename: source.read(item.filename) for item in source.infolist()}
    parts[name] = payload
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for part_name, part_payload in parts.items():
            target.writestr(part_name, part_payload)


def _actions_xml(rows: list[list[tuple[str, str, bool]]]) -> bytes:
    root = ET.Element(f"{{{MAIN_NS}}}worksheet")
    data = ET.SubElement(root, f"{{{MAIN_NS}}}sheetData")
    header = ET.SubElement(data, f"{{{MAIN_NS}}}row", r="1")
    for index, value in enumerate(ACTION_HEADERS, 1):
        cell = ET.SubElement(header, f"{{{MAIN_NS}}}c", r=f"{chr(64 + index)}1", t="inlineStr")
        inline = ET.SubElement(cell, f"{{{MAIN_NS}}}is")
        ET.SubElement(inline, f"{{{MAIN_NS}}}t").text = value
    for row_number, values in enumerate(rows, 2):
        row = ET.SubElement(data, f"{{{MAIN_NS}}}row", r=str(row_number))
        for reference, value, formula in values:
            cell = ET.SubElement(row, f"{{{MAIN_NS}}}c", r=f"{reference}{row_number}", t="inlineStr")
            if formula:
                ET.SubElement(cell, f"{{{MAIN_NS}}}f").text = value
            inline = ET.SubElement(cell, f"{{{MAIN_NS}}}is")
            ET.SubElement(inline, f"{{{MAIN_NS}}}t").text = value
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


class ActionWorkbookTemplateTests(unittest.TestCase):
    def test_template_is_deterministic_valid_and_lists_only_bulk_supported_types(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first.xlsx"
            second = Path(temporary) / "second.XLSX"
            self.assertEqual(write_action_import_template(first), first.resolve())
            write_action_import_template(second)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertIn("xl/worksheets/sheet3.xml", archive.namelist())
                reference = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")
                actions = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")

        expected = set(CREATABLE_ACTION_TYPES) - {
            "sequence",
            "excel_automation",
            "transform_file_text",
        }
        for action_type in expected:
            self.assertIn(f">{action_type}<", reference)
        self.assertNotIn(">sequence<", reference)
        self.assertNotIn(">excel_automation<", reference)
        self.assertNotIn(">transform_file_text<", reference)
        for header in ACTION_HEADERS:
            self.assertIn(f">{header}<", actions)

    def test_template_round_trip_is_empty_and_models_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "actions.xlsx"
            write_action_import_template(path)
            workbook = read_action_import_workbook(path)
            digest = workbook_digest(path)

        self.assertEqual(workbook.path, path.resolve())
        self.assertEqual(workbook.digest, digest)
        self.assertEqual(workbook.rows, ())
        with self.assertRaises(FrozenInstanceError):
            workbook.digest = "changed"  # type: ignore[misc]

    def test_writer_rejects_non_xlsx_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ActionWorkbookError, "xlsx"):
                write_action_import_template(Path(temporary) / "actions.csv")


class ActionWorkbookReadTests(unittest.TestCase):
    def _template(self, temporary: str) -> Path:
        path = Path(temporary) / "actions.xlsx"
        write_action_import_template(path)
        return path

    def test_reads_inline_rows_and_normalizes_structured_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self._template(temporary)
            _replace_zip_part(
                path,
                "xl/worksheets/sheet2.xml",
                _actions_xml(
                    [
                        [
                            ("B", "  Open   guide  ", False),
                            ("C", " open_url ", False),
                            ("D", " https://example.test/guide ", False),
                            ("E", " Work ; Research ", False),
                            ("F", " Docs ; Important ", False),
                            ("G", "  Helpful guide  ", False),
                            ("H", " Work > Guides ", False),
                            ("I", "--new-window\n--safe", False),
                            ("J", " C:\\My  Folder ", False),
                        ],
                        [("A", "No", False), ("B", "Skip me", False)],
                    ]
                ),
            )

            workbook = read_action_import_workbook(path)

        self.assertEqual(len(workbook.rows), 2)
        row = workbook.rows[0]
        self.assertEqual(row.row_number, 2)
        self.assertTrue(row.include)
        self.assertEqual(row.name, "Open   guide")
        self.assertEqual(row.action_type, "open_url")
        self.assertEqual(row.value, "https://example.test/guide")
        self.assertEqual(row.contexts, ("Work", "Research"))
        self.assertEqual(row.tags, ("Docs", "Important"))
        self.assertEqual(row.quick_menu, ("Work", "Guides"))
        self.assertEqual(row.arguments, ("--new-window", "--safe"))
        self.assertEqual(row.working_folder, "C:\\My  Folder")
        self.assertFalse(workbook.rows[1].include)
        with self.assertRaises(FrozenInstanceError):
            row.name = "Changed"  # type: ignore[misc]

    def test_supports_shared_string_cells(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self._template(temporary)
            with zipfile.ZipFile(path) as source:
                parts = {item.filename: source.read(item.filename) for item in source.infolist()}
            shared = [*ACTION_HEADERS, "Yes", "Shared action", "open_url", "https://example.test"]
            shared_xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                f'<sst xmlns="{MAIN_NS}" count="{len(shared)}" uniqueCount="{len(shared)}">'
                + "".join(f"<si><t>{value}</t></si>" for value in shared)
                + "</sst>"
            ).encode()
            cells = "".join(
                f'<c r="{chr(65 + index)}1" t="s"><v>{index}</v></c>'
                for index in range(len(ACTION_HEADERS))
            )
            cells += '<c r="A2" t="s"><v>10</v></c><c r="B2" t="s"><v>11</v></c><c r="C2" t="s"><v>12</v></c><c r="D2" t="s"><v>13</v></c>'
            parts["xl/sharedStrings.xml"] = shared_xml
            parts["xl/worksheets/sheet2.xml"] = (
                f'<?xml version="1.0"?><worksheet xmlns="{MAIN_NS}"><sheetData><row r="1">{cells[:cells.index("<c r=\"A2\"")]}</row><row r="2">{cells[cells.index("<c r=\"A2\""):]}</row></sheetData></worksheet>'
            ).encode()
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as target:
                for name, payload in parts.items():
                    target.writestr(name, payload)

            workbook = read_action_import_workbook(path)

        self.assertEqual(workbook.rows[0].name, "Shared action")
        self.assertEqual(workbook.rows[0].value, "https://example.test")

    def test_rejects_formula_in_populated_or_excluded_row(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self._template(temporary)
            _replace_zip_part(
                path,
                "xl/worksheets/sheet2.xml",
                _actions_xml([[("A", "No", False), ("B", 'CONCAT("unsafe")', True)]]),
            )
            with self.assertRaisesRegex(ActionWorkbookError, "row 2.*formula"):
                read_action_import_workbook(path)

    def test_rejects_changed_headers_identity_and_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self._template(temporary)
            _replace_zip_part(path, "xl/worksheets/sheet2.xml", _actions_xml([]).replace(b">Name<", b">Title<"))
            with self.assertRaisesRegex(ActionWorkbookError, "headers"):
                read_action_import_workbook(path)

            path = self._template(temporary)
            with zipfile.ZipFile(path) as archive:
                instructions = archive.read("xl/worksheets/sheet1.xml")
            _replace_zip_part(path, "xl/worksheets/sheet1.xml", instructions.replace(b">1<", b">2<", 1))
            with self.assertRaisesRegex(ActionWorkbookError, "version"):
                read_action_import_workbook(path)

    def test_rejects_invalid_import_marker_and_non_xlsx(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self._template(temporary)
            _replace_zip_part(path, "xl/worksheets/sheet2.xml", _actions_xml([[("A", "Maybe", False), ("B", "Action", False)]]))
            with self.assertRaisesRegex(ActionWorkbookError, "invalid Import"):
                read_action_import_workbook(path)
            with self.assertRaisesRegex(ActionWorkbookError, "xlsx"):
                read_action_import_workbook(path.with_suffix(".xls"))

    def test_rejects_multiline_name_and_working_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self._template(temporary)
            _replace_zip_part(
                path,
                "xl/worksheets/sheet2.xml",
                _actions_xml([[('B', 'Two\nlines', False), ('C', 'copy_text', False), ('D', 'text', False)]]),
            )
            with self.assertRaisesRegex(ActionWorkbookError, 'field "Name"'):
                read_action_import_workbook(path)

            path = self._template(temporary)
            _replace_zip_part(
                path,
                "xl/worksheets/sheet2.xml",
                _actions_xml([[('B', 'Target', False), ('C', 'open_windows_target', False), ('D', 'vscode:', False), ('J', 'C:\\one\ntwo', False)]]),
            )
            with self.assertRaisesRegex(ActionWorkbookError, 'field "Working folder"'):
                read_action_import_workbook(path)

    def test_rejects_rows_over_limit_and_data_after_column_j(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self._template(temporary)
            worksheet_root = ET.fromstring(_actions_xml([]))
            sheet_data = next(
                node for node in worksheet_root if node.tag.endswith("}sheetData")
            )
            row_number = MAX_ACTION_ROWS + 2
            row = ET.SubElement(sheet_data, f"{{{MAIN_NS}}}row", r=str(row_number))
            cell = ET.SubElement(
                row,
                f"{{{MAIN_NS}}}c",
                r=f"B{row_number}",
                t="inlineStr",
            )
            inline = ET.SubElement(cell, f"{{{MAIN_NS}}}is")
            ET.SubElement(inline, f"{{{MAIN_NS}}}t").text = "Too far"
            _replace_zip_part(
                path,
                "xl/worksheets/sheet2.xml",
                ET.tostring(worksheet_root, encoding="utf-8", xml_declaration=True),
            )
            with self.assertRaisesRegex(ActionWorkbookError, "at most 1,000"):
                read_action_import_workbook(path)

            path = self._template(temporary)
            _replace_zip_part(path, "xl/worksheets/sheet2.xml", _actions_xml([[("B", "Action", False), ("K", "extra", False)]]))
            with self.assertRaisesRegex(ActionWorkbookError, "outside"):
                read_action_import_workbook(path)

    def test_rejects_corrupt_encrypted_or_unsafe_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            corrupt = root / "bad.xlsx"
            corrupt.write_bytes(b"not a zip")
            with self.assertRaisesRegex(ActionWorkbookError, "valid XLSX"):
                read_action_import_workbook(corrupt)

            encrypted = root / "encrypted.xlsx"
            encrypted.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest")
            with self.assertRaisesRegex(ActionWorkbookError, "Encrypted"):
                read_action_import_workbook(encrypted)

            unsafe = self._template(temporary)
            with zipfile.ZipFile(unsafe, "a") as archive:
                archive.writestr("../outside.xml", "unsafe")
            with self.assertRaisesRegex(ActionWorkbookError, "unsafe"):
                read_action_import_workbook(unsafe)


if __name__ == "__main__":
    unittest.main()
