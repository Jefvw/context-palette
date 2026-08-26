from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from context_palette.actions import Action
from context_palette.action_sequences import SequenceStep
from context_palette.action_update_workbook import (
    ACTION_UPDATE_HEADERS,
    ELIGIBLE_ACTION_TYPES,
    MAX_ACTION_ROWS,
    ActionUpdateWorkbookError,
    action_record_fingerprint,
    read_action_update_workbook,
    update_workbook_digest,
    write_action_update_workbook,
)


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _action(
    action_id: str = "one",
    *,
    title: str = "One",
    action_type: str = "copy_text",
    value: str = "Text",
    state: str = "Active",
    arguments: tuple[str, ...] = (),
    working_directory: str | None = None,
    contexts: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    description: str = "",
    quick_action_path: tuple[str, ...] = (),
    sequence_steps: tuple[SequenceStep, ...] = (),
) -> Action:
    return Action(
        id=action_id,
        title=title,
        context=contexts[0] if contexts else "General",
        type=action_type,
        value=value,
        state=state,
        arguments=arguments,
        working_directory=working_directory,
        contexts=contexts,
        tags=tags,
        description=description,
        quick_action_path=quick_action_path,
        sequence_steps=sequence_steps,
    )


def _replace_zip_part(path: Path, name: str, payload: bytes) -> None:
    with zipfile.ZipFile(path) as source:
        parts = {item.filename: source.read(item.filename) for item in source.infolist()}
    parts[name] = payload
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for part_name, part_payload in parts.items():
            target.writestr(part_name, part_payload)


def _change_cell(
    path: Path,
    part: str,
    reference: str,
    *,
    value: str | None = None,
    formula: str | None = None,
) -> None:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read(part))
    cell = next(
        node
        for node in root.iter()
        if node.tag.endswith("}c") and node.attrib.get("r") == reference
    )
    if value is not None:
        text = next(node for node in cell.iter() if node.tag.endswith("}t"))
        text.text = value
    if formula is not None:
        ET.SubElement(cell, f"{{{MAIN_NS}}}f").text = formula
    _replace_zip_part(
        path,
        part,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


def _append_cell(path: Path, reference: str, value: str) -> None:
    part = "xl/worksheets/sheet2.xml"
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read(part))
    row_number = "".join(character for character in reference if character.isdigit())
    row = next(
        node
        for node in root.iter()
        if node.tag.endswith("}row") and node.attrib.get("r") == row_number
    )
    cell = ET.SubElement(
        row,
        f"{{{MAIN_NS}}}c",
        r=reference,
        t="inlineStr",
    )
    inline = ET.SubElement(cell, f"{{{MAIN_NS}}}is")
    ET.SubElement(inline, f"{{{MAIN_NS}}}t").text = value
    _replace_zip_part(
        path,
        part,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


class ActionUpdateWorkbookWriteTests(unittest.TestCase):
    def test_export_uses_default_namespaces_for_strict_xlsx_readers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "updates.xlsx"
            write_action_update_workbook(path, (_action(),))

            with zipfile.ZipFile(path) as archive:
                for part in (
                    "[Content_Types].xml",
                    "_rels/.rels",
                    "xl/workbook.xml",
                    "xl/_rels/workbook.xml.rels",
                    "xl/styles.xml",
                    "xl/worksheets/sheet1.xml",
                ):
                    payload = archive.read(part).decode("utf-8")
                    self.assertIn(' xmlns="', payload, part)
                    self.assertNotIn("<ns0:", payload, part)

    def test_writer_is_deterministic_sorted_and_contains_no_private_duplicate_sheet(self) -> None:
        first_action = _action(
            "first",
            title="Alpha",
            value="private saved text",
        )
        second_action = _action("second", title="Zulu", value="other")
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first.xlsx"
            second = Path(temporary) / "second.XLSX"
            self.assertEqual(
                write_action_update_workbook(first, [second_action, first_action]),
                first.resolve(),
            )
            write_action_update_workbook(second, [first_action, second_action])

            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
                package_text = "\n".join(
                    archive.read(name).decode("utf-8", errors="ignore")
                    for name in archive.namelist()
                )
                self.assertNotIn("xl/worksheets/sheet3.xml", archive.namelist())

            parsed = read_action_update_workbook(first, [first_action, second_action])
            exact_digest = update_workbook_digest(first)

        self.assertIn('name="Instructions"', workbook_xml)
        self.assertIn('name="Actions"', workbook_xml)
        self.assertNotIn("Original Records", workbook_xml)
        self.assertEqual(package_text.count("private saved text"), 1)
        self.assertEqual([row.action_id for row in parsed.rows], ["first", "second"])
        self.assertEqual(parsed.digest, exact_digest)

    def test_writer_exports_only_active_eligible_personal_actions(self) -> None:
        active = _action("active")
        archived = _action("archived", state="Archived")
        sequence = _action(
            "sequence",
            action_type="sequence",
            value="",
            sequence_steps=(
                SequenceStep("action", action_id="active"),
                SequenceStep("action", action_id="active"),
            ),
        )
        excel = _action(
            "excel",
            action_type="excel_automation",
            value="excel.export_workbooks_to_csv",
        )
        file_transform = _action(
            "file-transform",
            action_type="transform_file_text",
            value="C:\\input.txt",
        )
        all_actions = [active, archived, sequence, excel, file_transform]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "updates.xlsx"
            write_action_update_workbook(path, all_actions)
            parsed = read_action_update_workbook(path, all_actions)

        self.assertEqual(tuple(row.action_id for row in parsed.rows), ("active",))
        self.assertIn(active.type, ELIGIBLE_ACTION_TYPES)
        self.assertNotIn("sequence", ELIGIBLE_ACTION_TYPES)
        self.assertNotIn("excel_automation", ELIGIBLE_ACTION_TYPES)
        self.assertNotIn("transform_file_text", ELIGIBLE_ACTION_TYPES)

    def test_writer_rejects_duplicate_ids_limits_bad_targets_and_excel_control_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ActionUpdateWorkbookError, "unique"):
                write_action_update_workbook(
                    root / "duplicates.xlsx",
                    [_action("Same"), _action("same")],
                )
            with self.assertRaisesRegex(ActionUpdateWorkbookError, "at most 1,000"):
                write_action_update_workbook(
                    root / "many.xlsx",
                    (_action(f"action-{index}") for index in range(MAX_ACTION_ROWS + 1)),
                )
            with self.assertRaisesRegex(ActionUpdateWorkbookError, "xlsx"):
                write_action_update_workbook(root / "updates.csv", [])
            with self.assertRaisesRegex(ActionUpdateWorkbookError, "cannot store"):
                write_action_update_workbook(
                    root / "control.xlsx",
                    [_action("control", value="bad\x00text")],
                )


class ActionUpdateWorkbookReadTests(unittest.TestCase):
    def _workbook(self, temporary: str, actions: list[Action]) -> Path:
        path = Path(temporary) / "updates.xlsx"
        write_action_update_workbook(path, actions)
        return path

    def test_round_trip_preserves_meaningful_whitespace_and_json_arguments(self) -> None:
        action = _action(
            "application",
            title="  Keep title spacing  ",
            action_type="launch_app",
            value="  C:\\Tools\\app.exe  ",
            arguments=("", "  padded  ", "line\nvalue", "\t"),
            working_directory="  C:\\Work folder  ",
            contexts=("My  Context", "Client; Europe"),
            tags=("tag one", "semi;colon"),
            description="  First line\nSecond line  ",
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = self._workbook(temporary, [action])
            parsed = read_action_update_workbook(path, [action])

        row = parsed.rows[0]
        self.assertEqual(row.name, action.title)
        self.assertEqual(row.value, action.value)
        self.assertEqual(row.description, action.description)
        self.assertEqual(row.arguments, action.arguments)
        self.assertEqual(row.working_folder, action.working_directory)
        self.assertEqual(row.contexts, action.contexts)
        self.assertEqual(row.tags, action.tags)
        with self.assertRaises(FrozenInstanceError):
            row.name = "Changed"  # type: ignore[misc]

    def test_round_trip_preserves_quick_menu_and_empty_arguments(self) -> None:
        action = _action(
            "prompt",
            action_type="ai_prompt",
            value="Review this",
            quick_action_path=("Work", "Review"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = self._workbook(temporary, [action])
            parsed = read_action_update_workbook(path, [action])

        self.assertEqual(parsed.rows[0].quick_menu, ("Work", "Review"))
        self.assertEqual(parsed.rows[0].arguments, ())

    def test_reader_returns_reviewed_editable_values_without_changing_identity(self) -> None:
        action = _action("editable", title="Before", value="Before")
        with tempfile.TemporaryDirectory() as temporary:
            path = self._workbook(temporary, [action])
            changes = {
                "E2": "  After  ",
                "F2": "  line one\nline two  ",
                "G2": " Work ; Research ",
                "H2": " Tag One ; tag-two ",
                "I2": "  Description  ",
                "J2": "Team > Reports",
                "K2": '["", "  exact  ", "line\\nvalue"]',
                "L2": "  C:\\Working  ",
            }
            for reference, value in changes.items():
                _change_cell(
                    path,
                    "xl/worksheets/sheet2.xml",
                    reference,
                    value=value,
                )
            parsed = read_action_update_workbook(path, [action])

        row = parsed.rows[0]
        self.assertEqual(row.action_id, action.id)
        self.assertEqual(row.name, "  After  ")
        self.assertEqual(row.value, "  line one\nline two  ")
        self.assertEqual(row.contexts, ("Work", "Research"))
        self.assertEqual(row.tags, ("Tag One", "tag-two"))
        self.assertEqual(row.description, "  Description  ")
        self.assertEqual(row.quick_menu, ("Team", "Reports"))
        self.assertEqual(row.arguments, ("", "  exact  ", "line\nvalue"))
        self.assertEqual(row.working_folder, "  C:\\Working  ")

    def test_reader_rejects_each_changed_identity_column(self) -> None:
        action = _action("identity")
        cases = (
            ("A2", "changed", "unknown, changed"),
            ("B2", "Archived", "State was changed"),
            ("C2", "open_url", "Action type was changed"),
            ("D2", "sha256:" + "0" * 64, "original fingerprint was changed"),
        )
        for reference, replacement_value, expected in cases:
            with self.subTest(reference=reference), tempfile.TemporaryDirectory() as temporary:
                path = self._workbook(temporary, [action])
                _change_cell(
                    path,
                    "xl/worksheets/sheet2.xml",
                    reference,
                    value=replacement_value,
                )
                with self.assertRaisesRegex(ActionUpdateWorkbookError, expected):
                    read_action_update_workbook(path, [action])

    def test_reader_rejects_stale_current_actions_and_changed_export_identity(self) -> None:
        action = _action("stale", value="before")
        with tempfile.TemporaryDirectory() as temporary:
            path = self._workbook(temporary, [action])
            with self.assertRaisesRegex(ActionUpdateWorkbookError, "no longer matches"):
                read_action_update_workbook(path, [replace(action, value="after")])

            _change_cell(
                path,
                "xl/worksheets/sheet1.xml",
                "B3",
                value="sha256:" + "0" * 64,
            )
            with self.assertRaisesRegex(ActionUpdateWorkbookError, "no longer matches"):
                read_action_update_workbook(path, [action])

    def test_reader_rejects_formula_changed_headers_and_extra_columns(self) -> None:
        action = _action("one")
        with tempfile.TemporaryDirectory() as temporary:
            path = self._workbook(temporary, [action])
            _change_cell(
                path,
                "xl/worksheets/sheet2.xml",
                "E2",
                formula="1+1",
            )
            with self.assertRaisesRegex(ActionUpdateWorkbookError, "row 2.*formula"):
                read_action_update_workbook(path, [action])

            path = self._workbook(temporary, [action])
            _change_cell(
                path,
                "xl/worksheets/sheet2.xml",
                "E1",
                value="Title",
            )
            with self.assertRaisesRegex(ActionUpdateWorkbookError, "headers"):
                read_action_update_workbook(path, [action])

            path = self._workbook(temporary, [action])
            _append_cell(path, "M2", "unsupported")
            with self.assertRaisesRegex(ActionUpdateWorkbookError, "outside"):
                read_action_update_workbook(path, [action])

            path = self._workbook(temporary, [action])
            _change_cell(
                path,
                "xl/worksheets/sheet1.xml",
                "A6",
                formula="1+1",
            )
            with self.assertRaisesRegex(ActionUpdateWorkbookError, "Instructions.*formula"):
                read_action_update_workbook(path, [action])

    def test_reader_rejects_invalid_argument_json_and_multiline_single_line_fields(self) -> None:
        action = _action("one")
        with tempfile.TemporaryDirectory() as temporary:
            path = self._workbook(temporary, [action])
            _change_cell(
                path,
                "xl/worksheets/sheet2.xml",
                "K2",
                value='["valid", 2]',
            )
            with self.assertRaisesRegex(ActionUpdateWorkbookError, "only text"):
                read_action_update_workbook(path, [action])

            path = self._workbook(temporary, [action])
            _change_cell(
                path,
                "xl/worksheets/sheet2.xml",
                "L2",
                value="C:\\one\ntwo",
            )
            with self.assertRaisesRegex(ActionUpdateWorkbookError, "Working folder"):
                read_action_update_workbook(path, [action])

    def test_reader_allows_rows_to_be_removed_without_treating_that_as_deletion(self) -> None:
        first = _action("first", title="First")
        second = _action("second", title="Second")
        with tempfile.TemporaryDirectory() as temporary:
            path = self._workbook(temporary, [first, second])
            with zipfile.ZipFile(path) as archive:
                root = ET.fromstring(archive.read("xl/worksheets/sheet2.xml"))
            data = next(node for node in root if node.tag.endswith("}sheetData"))
            row = next(
                node
                for node in data
                if node.tag.endswith("}row") and node.attrib.get("r") == "3"
            )
            data.remove(row)
            _replace_zip_part(
                path,
                "xl/worksheets/sheet2.xml",
                ET.tostring(root, encoding="utf-8", xml_declaration=True),
            )
            parsed = read_action_update_workbook(path, [first, second])

        self.assertEqual(tuple(row.action_id for row in parsed.rows), ("first",))

    def test_reader_rejects_non_xlsx_and_changed_sheet_contract(self) -> None:
        action = _action("one")
        with tempfile.TemporaryDirectory() as temporary:
            path = self._workbook(temporary, [action])
            with self.assertRaisesRegex(ActionUpdateWorkbookError, "xlsx"):
                read_action_update_workbook(path.with_suffix(".xls"), [action])

            with zipfile.ZipFile(path) as archive:
                workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            sheet = next(
                node
                for node in workbook.iter()
                if node.tag.endswith("}sheet") and node.attrib.get("name") == "Actions"
            )
            sheet.set("name", "Changed")
            _replace_zip_part(
                path,
                "xl/workbook.xml",
                ET.tostring(workbook, encoding="utf-8", xml_declaration=True),
            )
            with self.assertRaisesRegex(ActionUpdateWorkbookError, "only"):
                read_action_update_workbook(path, [action])


class ActionUpdateFingerprintTests(unittest.TestCase):
    def test_fingerprint_is_stable_and_covers_every_persisted_semantic_field(self) -> None:
        base = _action(
            "fingerprint",
            title="Title",
            value="Value",
            arguments=("one", " two "),
            working_directory="C:\\Work",
            contexts=("Work",),
            tags=("tag",),
            description="Description",
        )
        self.assertEqual(action_record_fingerprint(base), action_record_fingerprint(base))
        variants = (
            replace(base, title="Changed"),
            replace(base, value="Changed"),
            replace(base, state="Archived"),
            replace(base, arguments=("different",)),
            replace(base, working_directory="C:\\Other"),
            replace(base, contexts=("Other",), context="Other"),
            replace(base, tags=("other",)),
            replace(base, description="Other"),
        )
        self.assertTrue(
            all(
                action_record_fingerprint(variant) != action_record_fingerprint(base)
                for variant in variants
            )
        )
        self.assertRegex(action_record_fingerprint(base), r"^sha256:[0-9a-f]{64}$")

    def test_headers_describe_four_read_only_identity_and_eight_editable_columns(self) -> None:
        self.assertEqual(
            ACTION_UPDATE_HEADERS[:4],
            ("Action ID", "State", "Action type", "Original fingerprint"),
        )
        self.assertEqual(
            ACTION_UPDATE_HEADERS[4:],
            (
                "Name",
                "Value",
                "Contexts",
                "Tags",
                "Description",
                "Quick menu",
                "Arguments (JSON)",
                "Working folder",
            ),
        )


if __name__ == "__main__":
    unittest.main()
