"""Bounded, dependency-free XLSX exchange for bulk Action updates.

The workbook is a reviewed round-trip boundary, not a general spreadsheet
reader.  It exports personal Active Actions from the eligible generic types,
with four verified identity columns that users are instructed not to edit. The reader never starts Office,
evaluates formulas, follows links, or accepts a workbook whose identity no
longer matches the current personal Actions supplied by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
import csv
from hashlib import sha256
from io import BytesIO
from io import StringIO
import json
from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET
import zipfile

from .actions import ACTIVE_STATE, Action
from .action_types import CREATABLE_ACTION_TYPES
from .action_sequences import sequence_steps_to_data
from .action_workbook import (
    MAX_ACTION_ROWS,
    MAX_CELL_CHARACTERS,
    ActionWorkbookError,
    _CONTENT_TYPES_NS,
    _MAIN_NS,
    _PACKAGE_REL_NS,
    _REL_NS,
    _app_properties_xml,
    _cell,
    _package_relationships_xml,
    _read_shared_strings,
    _read_sheet_cells,
    _read_workbook_payload,
    _styles_xml,
    _validate_archive,
    _worksheet_parts,
    _worksheet_root,
    _write_part,
    _xml_bytes,
)
from .persistence import atomic_replace_bytes


WORKBOOK_TITLE = "Context Palette Action Update"
WORKBOOK_VERSION = "1"
ACTION_UPDATE_HEADERS = (
    "Action ID",
    "State",
    "Action type",
    "Original fingerprint",
    "Name",
    "Value",
    "Contexts",
    "Tags",
    "Description",
    "Quick menu",
    "Arguments (JSON)",
    "Working folder",
)
ELIGIBLE_ACTION_TYPES = frozenset(CREATABLE_ACTION_TYPES) - {
    "sequence",
    "excel_automation",
    "transform_file_text",
}
_EXPECTED_SHEETS = frozenset({"instructions", "actions"})
_IDENTITY_PREFIX = "sha256:"


class ActionUpdateWorkbookError(ActionWorkbookError):
    """Raised when an Action update workbook violates its safe contract."""


@dataclass(frozen=True, slots=True)
class ActionUpdateWorkbookRow:
    row_number: int
    action_id: str
    state: str
    action_type: str
    original_fingerprint: str
    name: str
    value: str
    contexts: tuple[str, ...]
    tags: tuple[str, ...]
    description: str
    quick_menu: tuple[str, ...]
    arguments: tuple[str, ...]
    working_folder: str


@dataclass(frozen=True, slots=True)
class ActionUpdateWorkbook:
    path: Path
    digest: str
    export_fingerprint: str
    rows: tuple[ActionUpdateWorkbookRow, ...]


def action_record_fingerprint(action: Action) -> str:
    """Return the stable semantic fingerprint used to guard one update."""

    return _fingerprint_record(_canonical_action_record(action))


def update_workbook_digest(path: Path) -> str:
    """Return the SHA-256 digest of one bounded exact update workbook."""

    try:
        _resolved, payload = _read_workbook_payload(path)
    except ActionWorkbookError as exc:
        raise ActionUpdateWorkbookError(str(exc)) from exc
    return sha256(payload).hexdigest()


def write_action_update_workbook(
    path: Path,
    personal_actions: Iterable[Action],
) -> Path:
    """Atomically export up to 1,000 eligible personal Active Actions."""

    target = _validate_xlsx_target(path)
    actions = sorted(
        (
            action
            for action in personal_actions
            if action.state == ACTIVE_STATE and action.type in ELIGIBLE_ACTION_TYPES
        ),
        key=lambda item: (item.title.casefold(), item.id.casefold(), item.id),
    )
    if len(actions) > MAX_ACTION_ROWS:
        raise ActionUpdateWorkbookError(
            f"An update workbook supports at most {MAX_ACTION_ROWS:,} Actions."
        )

    seen_ids: dict[str, str] = {}
    records: list[tuple[Action, str]] = []
    for action in actions:
        action_id = _identity_text(action.id, field="Action ID")
        key = action_id.casefold()
        if key in seen_ids:
            raise ActionUpdateWorkbookError(
                "Personal Action IDs must be unique: "
                f"{seen_ids[key]} and {action_id}."
            )
        seen_ids[key] = action_id
        _identity_text(action.state, field=f'Action "{action_id}" state')
        _identity_text(action.type, field=f'Action "{action_id}" type')
        record = _canonical_action_record(action)
        fingerprint = _fingerprint_record(record)
        records.append((action, fingerprint))

    export_fingerprint = _export_fingerprint(
        (action.id, action.state, action.type, fingerprint)
        for action, fingerprint in records
    )
    output = BytesIO()
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        _write_part(archive, "[Content_Types].xml", _content_types_xml())
        _write_part(archive, "_rels/.rels", _package_relationships_xml())
        _write_part(archive, "docProps/core.xml", _core_properties_xml())
        _write_part(archive, "docProps/app.xml", _app_properties_xml())
        _write_part(archive, "xl/workbook.xml", _workbook_xml())
        _write_part(
            archive,
            "xl/_rels/workbook.xml.rels",
            _workbook_relationships_xml(),
        )
        _write_part(archive, "xl/styles.xml", _styles_xml())
        _write_part(
            archive,
            "xl/worksheets/sheet1.xml",
            _instructions_sheet_xml(export_fingerprint),
        )
        _write_part(
            archive,
            "xl/worksheets/sheet2.xml",
            _actions_sheet_xml(records),
        )
    atomic_replace_bytes(target, output.getvalue())
    return target


def read_action_update_workbook(
    path: Path,
    personal_actions: Iterable[Action],
) -> ActionUpdateWorkbook:
    """Read and verify one exact version-1 Action update workbook."""

    try:
        return _read_action_update_workbook(path, personal_actions)
    except ActionUpdateWorkbookError:
        raise
    except ActionWorkbookError as exc:
        raise ActionUpdateWorkbookError(str(exc)) from exc


def _read_action_update_workbook(
    path: Path,
    personal_actions: Iterable[Action],
) -> ActionUpdateWorkbook:
    resolved, payload = _read_workbook_payload(path)
    digest = sha256(payload).hexdigest()
    try:
        archive = zipfile.ZipFile(BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ActionUpdateWorkbookError(
            "The selected file is not a valid XLSX workbook."
        ) from exc

    with archive:
        _validate_archive(archive)
        shared_strings = _read_shared_strings(archive)
        sheets = _worksheet_parts(archive)
        if set(sheets) != _EXPECTED_SHEETS:
            raise ActionUpdateWorkbookError(
                'The update workbook must contain only "Instructions" and "Actions" sheets.'
            )

        instruction_rows = _read_sheet_cells(
            archive,
            sheets["instructions"],
            shared_strings,
            max_rows=50,
        )
        if any(
            cell.has_formula
            for row in instruction_rows.values()
            for cell in row.values()
        ):
            raise ActionUpdateWorkbookError(
                "The Instructions sheet cannot contain formulas. Export a fresh workbook."
            )
        identity_cells = tuple(
            _cell(instruction_rows, row, column)
            for row, column in ((1, 1), (2, 1), (2, 2), (3, 1), (3, 2))
        )
        if identity_cells[0].value != WORKBOOK_TITLE:
            raise ActionUpdateWorkbookError(
                "This is not a Context Palette Action Update workbook."
            )
        if (
            identity_cells[1].value != "Contract version"
            or identity_cells[2].value != WORKBOOK_VERSION
        ):
            raise ActionUpdateWorkbookError(
                f"Unsupported Action update workbook version. Version {WORKBOOK_VERSION} is required."
            )
        if identity_cells[3].value != "Export fingerprint":
            raise ActionUpdateWorkbookError(
                "The workbook export identity was changed. Export a fresh workbook."
            )
        declared_export_fingerprint = _validated_fingerprint(
            identity_cells[4].value,
            field="export fingerprint",
        )

        eligible_actions = tuple(
            action
            for action in personal_actions
            if action.state == ACTIVE_STATE and action.type in ELIGIBLE_ACTION_TYPES
        )
        originals: dict[str, tuple[str, str, str, str]] = {}
        for action in eligible_actions:
            action_id = _identity_text(action.id, field="Current personal Action ID")
            key = action_id.casefold()
            if key in originals:
                raise ActionUpdateWorkbookError(
                    f"Current personal Actions contain duplicate Action ID: {action_id}."
                )
            originals[key] = (
                action_id,
                action.state,
                action.type,
                action_record_fingerprint(action),
            )
        calculated_export_fingerprint = _export_fingerprint(originals.values())
        if declared_export_fingerprint != calculated_export_fingerprint:
            raise ActionUpdateWorkbookError(
                "The workbook no longer matches the current personal Actions. Export a fresh workbook."
            )

        action_rows = _read_sheet_cells(
            archive,
            sheets["actions"],
            shared_strings,
            max_rows=MAX_ACTION_ROWS + 1,
        )
        headers = tuple(
            _cell(action_rows, 1, column).value
            for column in range(1, len(ACTION_UPDATE_HEADERS) + 1)
        )
        if headers != ACTION_UPDATE_HEADERS or any(
            _cell(action_rows, 1, column).has_formula
            for column in range(1, len(ACTION_UPDATE_HEADERS) + 1)
        ):
            raise ActionUpdateWorkbookError(
                "The Actions sheet headers were changed. Export a fresh workbook and keep row 1 unchanged."
            )

        parsed: list[ActionUpdateWorkbookRow] = []
        visible_ids: dict[str, str] = {}
        for row_number in sorted(number for number in action_rows if number >= 2):
            cells = action_rows[row_number]
            populated = any(cell.value != "" or cell.has_formula for cell in cells.values())
            if not populated:
                continue
            if any(cell.has_formula for cell in cells.values()):
                raise ActionUpdateWorkbookError(
                    f"Actions row {row_number} contains a formula. Replace formulas with reviewed text values."
                )
            if any(
                column > len(ACTION_UPDATE_HEADERS) and cell.value != ""
                for column, cell in cells.items()
            ):
                raise ActionUpdateWorkbookError(
                    f"Actions row {row_number} contains data outside the supported columns A-L."
                )
            values = tuple(
                _cell(action_rows, row_number, column).value
                for column in range(1, len(ACTION_UPDATE_HEADERS) + 1)
            )
            row = _parse_update_row(row_number, values)
            key = row.action_id.casefold()
            if key in visible_ids:
                raise ActionUpdateWorkbookError(
                    f"Actions rows contain duplicate Action ID: {visible_ids[key]} and {row.action_id}."
                )
            visible_ids[key] = row.action_id
            original = originals.get(key)
            if original is None:
                raise ActionUpdateWorkbookError(
                    f'Actions row {row_number} has unknown, changed, or no-longer-current Action ID "{row.action_id}".'
                )
            expected_id, expected_state, expected_type, expected_fingerprint = original
            if row.action_id != expected_id:
                raise ActionUpdateWorkbookError(
                    f"Actions row {row_number} Action ID was changed. Export a fresh workbook."
                )
            if row.state != expected_state:
                raise ActionUpdateWorkbookError(
                    f"Actions row {row_number} State was changed. State is not editable in this workbook."
                )
            if row.action_type != expected_type:
                raise ActionUpdateWorkbookError(
                    f"Actions row {row_number} Action type was changed. Type is not editable in this workbook."
                )
            if row.original_fingerprint != expected_fingerprint:
                raise ActionUpdateWorkbookError(
                    f"Actions row {row_number} original fingerprint was changed. Export a fresh workbook."
                )
            parsed.append(row)

    return ActionUpdateWorkbook(
        resolved,
        digest,
        declared_export_fingerprint,
        tuple(parsed),
    )


def _parse_update_row(
    row_number: int,
    values: tuple[str, ...],
) -> ActionUpdateWorkbookRow:
    action_id = _identity_text(values[0], field=f"Actions row {row_number} Action ID")
    state = _identity_text(values[1], field=f"Actions row {row_number} State")
    action_type = _identity_text(
        values[2],
        field=f"Actions row {row_number} Action type",
    )
    original_fingerprint = _validated_fingerprint(
        values[3],
        field=f"Actions row {row_number} original fingerprint",
    )
    name = _single_line_preserving(values[4], row_number=row_number, field="Name")
    working_folder = _single_line_preserving(
        values[11],
        row_number=row_number,
        field="Working folder",
    )
    arguments = _arguments_from_json(values[10], row_number=row_number)
    return ActionUpdateWorkbookRow(
        row_number=row_number,
        action_id=action_id,
        state=state,
        action_type=action_type,
        original_fingerprint=original_fingerprint,
        name=name,
        value=_normalized_newlines(values[5]),
        contexts=_split_semicolon_values(
            values[6],
            row_number=row_number,
            field="Contexts",
        ),
        tags=_split_semicolon_values(
            values[7],
            row_number=row_number,
            field="Tags",
        ),
        description=_normalized_newlines(values[8]),
        quick_menu=_split_quick_menu(values[9]),
        arguments=arguments,
        working_folder=working_folder,
    )


def _arguments_from_json(value: str, *, row_number: int) -> tuple[str, ...]:
    if value == "":
        return ()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ActionUpdateWorkbookError(
            f"Actions row {row_number} Arguments must be a JSON array of text values."
        ) from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ActionUpdateWorkbookError(
            f"Actions row {row_number} Arguments must be a JSON array containing only text values."
        )
    return tuple(parsed)


def _canonical_action_record(action: Action) -> dict[str, object]:
    record: dict[str, object] = {
        "id": action.id,
        "title": action.title,
        "type": action.type,
        "value": action.value,
        "state": action.state,
    }
    if action.arguments:
        record["arguments"] = list(action.arguments)
    if action.working_directory:
        record["working_directory"] = action.working_directory
    if action.effective_contexts:
        record["contexts"] = list(action.effective_contexts)
    if action.effective_tags:
        record["tags"] = list(action.effective_tags)
    if action.description:
        record["description"] = action.description
    if action.quick_action_path:
        record["quick_action_path"] = list(action.quick_action_path)
    if action.type == "sequence":
        record["steps"] = sequence_steps_to_data(action.sequence_steps)
    return record


def _fingerprint_record(record: dict[str, object]) -> str:
    payload = _canonical_json(record).encode("utf-8")
    return _IDENTITY_PREFIX + sha256(payload).hexdigest()


def _export_fingerprint(records: Iterable[tuple[str, str, str, str]]) -> str:
    ordered = sorted(
        (
            (action_id, state, action_type, fingerprint)
            for action_id, state, action_type, fingerprint in records
        ),
        key=lambda item: (item[0].casefold(), item[0]),
    )
    return _IDENTITY_PREFIX + sha256(_canonical_json(ordered).encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _validated_fingerprint(value: str, *, field: str) -> str:
    if (
        len(value) != len(_IDENTITY_PREFIX) + 64
        or not value.startswith(_IDENTITY_PREFIX)
        or any(character not in "0123456789abcdef" for character in value[len(_IDENTITY_PREFIX):])
    ):
        raise ActionUpdateWorkbookError(f"The {field} is invalid or was changed.")
    return value


def _identity_text(value: str, *, field: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value:
        raise ActionUpdateWorkbookError(
            f"{field} must be non-empty single-line text without surrounding whitespace."
        )
    _validate_excel_text(value, field=field)
    return value


def _single_line_preserving(value: str, *, row_number: int, field: str) -> str:
    if "\n" in value or "\r" in value:
        raise ActionUpdateWorkbookError(
            f'Actions row {row_number} field "{field}" must contain one line.'
        )
    return value


def _normalized_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _split_semicolon_values(
    value: str,
    *,
    row_number: int,
    field: str,
) -> tuple[str, ...]:
    if not value:
        return ()
    try:
        parsed = next(
            csv.reader(
                (value,),
                delimiter=";",
                quotechar='"',
                skipinitialspace=True,
                strict=True,
            )
        )
    except csv.Error as exc:
        raise ActionUpdateWorkbookError(
            f'Actions row {row_number} field "{field}" has invalid semicolon-separated text.'
        ) from exc
    return tuple(item.strip() for item in parsed if item.strip())


def _join_semicolon_values(values: Iterable[str]) -> str:
    output = StringIO(newline="")
    csv.writer(
        output,
        delimiter=";",
        quotechar='"',
        lineterminator="",
        quoting=csv.QUOTE_MINIMAL,
    ).writerow(tuple(values))
    return output.getvalue()


def _split_quick_menu(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(">") if item.strip())


def _validate_xlsx_target(path: Path) -> Path:
    target = Path(path).expanduser()
    if target.suffix.casefold() != ".xlsx":
        raise ActionUpdateWorkbookError("Choose one file with the .xlsx extension.")
    try:
        return target.resolve(strict=False)
    except OSError as exc:
        raise ActionUpdateWorkbookError("The workbook path is not usable.") from exc


def _validate_excel_text(value: str, *, field: str) -> None:
    if len(value) > MAX_CELL_CHARACTERS:
        raise ActionUpdateWorkbookError(
            f"{field} exceeds Excel's {MAX_CELL_CHARACTERS:,}-character cell limit."
        )
    for character in value:
        codepoint = ord(character)
        if character in "\t\n\r":
            continue
        if not (
            0x20 <= codepoint <= 0xD7FF
            or 0xE000 <= codepoint <= 0xFFFD
            or 0x10000 <= codepoint <= 0x10FFFF
        ):
            raise ActionUpdateWorkbookError(
                f"{field} contains a character Excel cannot store safely."
            )


def _core_properties_xml() -> bytes:
    core_ns = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
    dc_ns = "http://purl.org/dc/elements/1.1/"
    dcterms_ns = "http://purl.org/dc/terms/"
    xsi_ns = "http://www.w3.org/2001/XMLSchema-instance"
    ET.register_namespace("cp", core_ns)
    ET.register_namespace("dc", dc_ns)
    ET.register_namespace("dcterms", dcterms_ns)
    ET.register_namespace("xsi", xsi_ns)
    root = ET.Element(f"{{{core_ns}}}coreProperties")
    ET.SubElement(root, f"{{{dc_ns}}}title").text = WORKBOOK_TITLE
    ET.SubElement(root, f"{{{dc_ns}}}creator").text = "Context Palette"
    ET.SubElement(root, f"{{{core_ns}}}lastModifiedBy").text = "Context Palette"
    for name in ("created", "modified"):
        node = ET.SubElement(
            root,
            f"{{{dcterms_ns}}}{name}",
            attrib={f"{{{xsi_ns}}}type": "dcterms:W3CDTF"},
        )
        node.text = "2020-01-01T00:00:00Z"
    return _xml_bytes(root)


def _content_types_xml() -> bytes:
    root = ET.Element(f"{{{_CONTENT_TYPES_NS}}}Types")
    for extension, content_type in (
        ("rels", "application/vnd.openxmlformats-package.relationships+xml"),
        ("xml", "application/xml"),
    ):
        ET.SubElement(
            root,
            f"{{{_CONTENT_TYPES_NS}}}Default",
            Extension=extension,
            ContentType=content_type,
        )
    overrides = (
        ("/xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"),
        ("/xl/worksheets/sheet1.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"),
        ("/xl/worksheets/sheet2.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"),
        ("/xl/styles.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"),
        ("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
        ("/docProps/app.xml", "application/vnd.openxmlformats-officedocument.extended-properties+xml"),
    )
    for part_name, content_type in overrides:
        ET.SubElement(
            root,
            f"{{{_CONTENT_TYPES_NS}}}Override",
            PartName=part_name,
            ContentType=content_type,
        )
    return _xml_bytes(root)


def _workbook_xml() -> bytes:
    ET.register_namespace("r", _REL_NS)
    root = ET.Element(f"{{{_MAIN_NS}}}workbook")
    ET.SubElement(root, f"{{{_MAIN_NS}}}workbookPr", date1904="0")
    views = ET.SubElement(root, f"{{{_MAIN_NS}}}bookViews")
    ET.SubElement(views, f"{{{_MAIN_NS}}}workbookView", activeTab="1")
    sheets = ET.SubElement(root, f"{{{_MAIN_NS}}}sheets")
    for index, name in enumerate(("Instructions", "Actions"), 1):
        attributes = {
            "name": name,
            "sheetId": str(index),
            f"{{{_REL_NS}}}id": f"rId{index}",
        }
        ET.SubElement(sheets, f"{{{_MAIN_NS}}}sheet", attrib=attributes)
    return _xml_bytes(root)


def _workbook_relationships_xml() -> bytes:
    root = ET.Element(f"{{{_PACKAGE_REL_NS}}}Relationships")
    for index in range(1, 3):
        ET.SubElement(
            root,
            f"{{{_PACKAGE_REL_NS}}}Relationship",
            Id=f"rId{index}",
            Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
            Target=f"worksheets/sheet{index}.xml",
        )
    ET.SubElement(
        root,
        f"{{{_PACKAGE_REL_NS}}}Relationship",
        Id="rId3",
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles",
        Target="styles.xml",
    )
    return _xml_bytes(root)


def _instructions_sheet_xml(export_fingerprint: str) -> bytes:
    rows = (
        (WORKBOOK_TITLE,),
        ("Contract version", WORKBOOK_VERSION),
        ("Export fingerprint", export_fingerprint),
        (),
        ("How to use",),
        ("1. Edit only Name through Working folder on the Actions sheet.",),
        ("2. Action ID, State, Action type, and Original fingerprint identify the saved Action; do not edit them.",),
        ('3. Separate Contexts and Tags with semicolons; quote a value containing ; with "double quotes". Use > for Quick menu levels.',),
        ('4. Arguments must be a JSON array, for example ["--safe"," value "].',),
        ("5. Deleting a row does not delete its Action; only reviewed changed rows can be updated.",),
        ("6. Formulas are rejected and never evaluated.",),
    )
    root = _worksheet_root(widths=(34, 90), frozen=False)
    data = ET.SubElement(root, f"{{{_MAIN_NS}}}sheetData")
    for row_number, values in enumerate(rows, 1):
        if values:
            _append_values(data, row_number, values, style=2 if row_number in {1, 5} else 0)
    return _xml_bytes(root)


def _actions_sheet_xml(
    records: list[tuple[Action, str]],
) -> bytes:
    widths = (24, 14, 28, 76, 30, 55, 28, 28, 48, 30, 55, 45)
    root = _worksheet_root(widths=widths, frozen=True)
    data = ET.SubElement(root, f"{{{_MAIN_NS}}}sheetData")
    _append_values(data, 1, ACTION_UPDATE_HEADERS, style=1)
    for row_number, (action, fingerprint) in enumerate(records, 2):
        values = (
            action.id,
            action.state,
            action.type,
            fingerprint,
            action.title,
            action.value,
            _join_semicolon_values(action.effective_contexts),
            _join_semicolon_values(action.effective_tags),
            action.description,
            " > ".join(action.quick_action_path),
            _canonical_json(list(action.arguments)),
            action.working_directory or "",
        )
        for column, value in enumerate(values, 1):
            _validate_excel_text(value, field=f"Actions row {row_number} column {column}")
        _append_values(data, row_number, values, style=3)
    last_row = max(1, len(records) + 1)
    ET.SubElement(root, f"{{{_MAIN_NS}}}autoFilter", ref=f"A1:L{last_row}")
    return _xml_bytes(root)


def _append_values(
    sheet_data: ET.Element,
    row_number: int,
    values: Iterable[str],
    *,
    style: int,
) -> None:
    row = ET.SubElement(sheet_data, f"{{{_MAIN_NS}}}row", r=str(row_number))
    if style in {1, 2}:
        row.set("ht", "24" if style == 1 else "28")
        row.set("customHeight", "1")
    for column, value in enumerate(values, 1):
        cell = ET.SubElement(
            row,
            f"{{{_MAIN_NS}}}c",
            r=f"{_column_label(column)}{row_number}",
            t="inlineStr",
            s=str(style),
        )
        inline = ET.SubElement(cell, f"{{{_MAIN_NS}}}is")
        text = ET.SubElement(inline, f"{{{_MAIN_NS}}}t")
        text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        text.text = value


def _column_label(number: int) -> str:
    output = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        output = chr(ord("A") + remainder) + output
    return output
