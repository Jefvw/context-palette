"""Bounded, dependency-free XLSX exchange for bulk Action creation.

The workbook is deliberately a narrow import format rather than a general
spreadsheet reader.  It never starts Excel, evaluates formulas, follows links,
or reads any file other than the exact ``.xlsx`` path supplied by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
import posixpath
import re
from typing import Iterable
import xml.etree.ElementTree as ET
import zipfile

from .action_types import ACTION_TYPES, CREATABLE_ACTION_TYPES
from .persistence import atomic_replace_bytes


WORKBOOK_TITLE = "Context Palette Action Import"
WORKBOOK_VERSION = "1"
ACTION_HEADERS = (
    "Import",
    "Name",
    "Action type",
    "Value",
    "Contexts",
    "Tags",
    "Description",
    "Quick menu",
    "Arguments",
    "Working folder",
)

MAX_ACTION_ROWS = 1_000
MAX_WORKBOOK_BYTES = 25 * 1024 * 1024
MAX_ZIP_ENTRIES = 200
MAX_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_XML_PART_BYTES = 32 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_SHARED_STRINGS = 20_000
MAX_CELL_CHARACTERS = 32_767
MAX_INSPECTED_CELLS = 20_000

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_EXTENDED_PROPERTIES_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
)
_DEFAULT_XML_NAMESPACES = frozenset(
    {
        _MAIN_NS,
        _PACKAGE_REL_NS,
        _CONTENT_TYPES_NS,
        _EXTENDED_PROPERTIES_NS,
    }
)
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_CELL_REFERENCE = re.compile(r"^([A-Z]{1,3})([1-9][0-9]*)$", re.IGNORECASE)
_INCLUDE_MARKERS = frozenset({"", "yes", "y", "true", "1"})
_EXCLUDE_MARKERS = frozenset({"no", "n", "false", "0"})
_FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)


class ActionWorkbookError(ValueError):
    """Raised when an Action import workbook is unsafe or violates its contract."""


@dataclass(frozen=True, slots=True)
class ActionWorkbookRow:
    row_number: int
    include: bool
    name: str
    action_type: str
    value: str
    contexts: tuple[str, ...]
    tags: tuple[str, ...]
    description: str
    quick_menu: tuple[str, ...]
    arguments: tuple[str, ...]
    working_folder: str


@dataclass(frozen=True, slots=True)
class ActionWorkbook:
    path: Path
    digest: str
    rows: tuple[ActionWorkbookRow, ...]


@dataclass(frozen=True, slots=True)
class _CellValue:
    value: str
    has_formula: bool


def workbook_digest(path: Path) -> str:
    """Return the SHA-256 digest of one bounded exact XLSX file."""

    _resolved, payload = _read_workbook_payload(path)
    return sha256(payload).hexdigest()


def write_action_import_template(path: Path) -> Path:
    """Atomically write a blank version-1 Action import workbook."""

    target = _validate_xlsx_target(path)
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
        _write_part(archive, "xl/_rels/workbook.xml.rels", _workbook_relationships_xml())
        _write_part(archive, "xl/styles.xml", _styles_xml())
        _write_part(archive, "xl/worksheets/sheet1.xml", _instructions_sheet_xml())
        _write_part(archive, "xl/worksheets/sheet2.xml", _actions_sheet_xml())
        _write_part(archive, "xl/worksheets/sheet3.xml", _reference_sheet_xml())
    atomic_replace_bytes(target, output.getvalue())
    return target


def read_action_import_workbook(path: Path) -> ActionWorkbook:
    """Read one exact version-1 Action workbook without evaluating formulas."""

    resolved, payload = _read_workbook_payload(path)
    digest = sha256(payload).hexdigest()
    try:
        archive = zipfile.ZipFile(BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ActionWorkbookError("The selected file is not a valid XLSX workbook.") from exc

    with archive:
        _validate_archive(archive)
        shared_strings = _read_shared_strings(archive)
        sheets = _worksheet_parts(archive)
        instructions_part = sheets.get("instructions")
        actions_part = sheets.get("actions")
        if instructions_part is None or actions_part is None:
            raise ActionWorkbookError(
                'The workbook must contain sheets named "Instructions" and "Actions".'
            )

        instruction_rows = _read_sheet_cells(
            archive,
            instructions_part,
            shared_strings,
            max_rows=50,
        )
        marker = _cell(instruction_rows, 1, 1)
        version_label = _cell(instruction_rows, 2, 1)
        version = _cell(instruction_rows, 2, 2)
        if marker.has_formula or version_label.has_formula or version.has_formula:
            raise ActionWorkbookError("Workbook identity cells cannot contain formulas.")
        if marker.value.strip() != WORKBOOK_TITLE:
            raise ActionWorkbookError(
                "This is not a Context Palette Action Import workbook. "
                "Download a fresh template and copy your rows into it."
            )
        if version_label.value.strip() != "Contract version" or version.value.strip() != WORKBOOK_VERSION:
            raise ActionWorkbookError(
                f"Unsupported Action import workbook version. Version {WORKBOOK_VERSION} is required."
            )

        action_rows = _read_sheet_cells(
            archive,
            actions_part,
            shared_strings,
            max_rows=MAX_ACTION_ROWS + 1,
        )
        headers = tuple(_cell(action_rows, 1, column).value.strip() for column in range(1, 11))
        if headers != ACTION_HEADERS or any(
            _cell(action_rows, 1, column).has_formula for column in range(1, 11)
        ):
            raise ActionWorkbookError(
                "The Actions sheet headers were changed. Download a fresh template and keep the first row unchanged."
            )

        rows: list[ActionWorkbookRow] = []
        for row_number in sorted(number for number in action_rows if number >= 2):
            cells = action_rows[row_number]
            populated = any(cell.value.strip() or cell.has_formula for cell in cells.values())
            if not populated:
                continue
            if any(cell.has_formula for cell in cells.values()):
                raise ActionWorkbookError(
                    f"Actions row {row_number} contains a formula. Replace formulas with reviewed text values."
                )
            if any(column > len(ACTION_HEADERS) and cell.value.strip() for column, cell in cells.items()):
                raise ActionWorkbookError(
                    f"Actions row {row_number} contains data outside the supported columns A-J."
                )
            values = tuple(_cell(action_rows, row_number, column).value for column in range(1, 11))
            rows.append(_parse_action_row(row_number, values))
        return ActionWorkbook(resolved, digest, tuple(rows))


def _validate_xlsx_target(path: Path) -> Path:
    target = Path(path).expanduser()
    if target.suffix.casefold() != ".xlsx":
        raise ActionWorkbookError("Choose one file with the .xlsx extension.")
    try:
        return target.resolve(strict=False)
    except OSError as exc:
        raise ActionWorkbookError("The workbook path is not usable.") from exc


def _read_workbook_payload(path: Path) -> tuple[Path, bytes]:
    candidate = Path(path).expanduser()
    if candidate.suffix.casefold() != ".xlsx":
        raise ActionWorkbookError("Choose one exact .xlsx workbook.")
    try:
        resolved = candidate.resolve(strict=True)
        if not resolved.is_file():
            raise ActionWorkbookError("Choose one exact .xlsx workbook file.")
        with resolved.open("rb") as stream:
            payload = stream.read(MAX_WORKBOOK_BYTES + 1)
    except ActionWorkbookError:
        raise
    except OSError as exc:
        raise ActionWorkbookError("The selected workbook could not be read.") from exc
    if len(payload) > MAX_WORKBOOK_BYTES:
        raise ActionWorkbookError(
            f"The workbook exceeds the {MAX_WORKBOOK_BYTES // (1024 * 1024)} MiB import limit."
        )
    if payload.startswith(_OLE_SIGNATURE):
        raise ActionWorkbookError("Encrypted and legacy Excel workbooks are not supported.")
    return resolved, payload


def _validate_archive(archive: zipfile.ZipFile) -> None:
    entries = archive.infolist()
    if len(entries) > MAX_ZIP_ENTRIES:
        raise ActionWorkbookError(
            f"The workbook contains more than {MAX_ZIP_ENTRIES} package entries."
        )
    expanded = 0
    names: set[str] = set()
    for entry in entries:
        normalized = entry.filename.replace("\\", "/")
        normalized_key = normalized.casefold()
        parts = PurePosixPath(normalized).parts
        if (
            not normalized
            or normalized.startswith("/")
            or ".." in parts
            or normalized_key in names
        ):
            raise ActionWorkbookError("The workbook contains an unsafe or duplicate package path.")
        names.add(normalized_key)
        if normalized_key.endswith("vbaproject.bin"):
            raise ActionWorkbookError("Macro-bearing Excel workbooks are not supported.")
        if normalized_key.startswith("xl/externallinks/"):
            raise ActionWorkbookError("External workbook links are not supported.")
        if entry.flag_bits & 0x1:
            raise ActionWorkbookError("Encrypted Excel workbooks are not supported.")
        expanded += entry.file_size
        if normalized_key.endswith((".xml", ".rels")) and entry.file_size > MAX_XML_PART_BYTES:
            raise ActionWorkbookError("A workbook XML part exceeds the safe import limit.")
        if entry.file_size and (
            entry.compress_size == 0
            or entry.file_size / entry.compress_size > MAX_COMPRESSION_RATIO
        ):
            raise ActionWorkbookError("The workbook has an unsafe compression ratio.")
    if expanded > MAX_EXPANDED_BYTES:
        raise ActionWorkbookError("The expanded workbook exceeds the safe import limit.")
    for entry in entries:
        if not entry.filename.casefold().endswith(".rels"):
            continue
        payload = archive.read(entry)
        upper = payload.upper()
        if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
            raise ActionWorkbookError("Workbook XML declarations are not supported.")
        try:
            relationships = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise ActionWorkbookError(
                f"Workbook XML is corrupt: {entry.filename}"
            ) from exc
        if any(
            _local_name(relationship.tag) == "Relationship"
            and relationship.attrib.get("TargetMode", "").casefold() == "external"
            for relationship in relationships
        ):
            raise ActionWorkbookError("External workbook links are not supported.")


def _xml_part(archive: zipfile.ZipFile, name: str, *, required: bool = True) -> ET.Element | None:
    try:
        payload = archive.read(name)
    except KeyError as exc:
        if not required:
            return None
        raise ActionWorkbookError(f"Required workbook part is missing: {name}") from exc
    upper = payload.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ActionWorkbookError("Workbook XML declarations are not supported.")
    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ActionWorkbookError(f"Workbook XML is corrupt: {name}") from exc


def _worksheet_parts(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = _xml_part(archive, "xl/workbook.xml")
    relationships = _xml_part(archive, "xl/_rels/workbook.xml.rels")
    assert workbook is not None and relationships is not None
    target_by_id: dict[str, str] = {}
    for relationship in relationships:
        if _local_name(relationship.tag) != "Relationship":
            continue
        relationship_id = relationship.attrib.get("Id", "")
        target = relationship.attrib.get("Target", "")
        if relationship.attrib.get("TargetMode", "").casefold() == "external":
            continue
        if relationship_id and target:
            target_by_id[relationship_id] = _normalize_part_target(target)

    result: dict[str, str] = {}
    relationship_id_key = f"{{{_REL_NS}}}id"
    for sheet in (item for item in workbook.iter() if _local_name(item.tag) == "sheet"):
        name = sheet.attrib.get("name", "").strip()
        key = name.casefold()
        relationship_id = sheet.attrib.get(relationship_id_key, "")
        if not key or key in result:
            raise ActionWorkbookError("Workbook sheet names must be unique and non-empty.")
        target = target_by_id.get(relationship_id)
        if target is None or target not in archive.namelist():
            raise ActionWorkbookError(f'Worksheet "{name}" is missing or has an unsafe relationship.')
        result[key] = target
    return result


def _normalize_part_target(target: str) -> str:
    normalized = target.replace("\\", "/")
    if ":" in normalized or normalized.startswith("//"):
        raise ActionWorkbookError("Workbook contains an unsafe worksheet relationship.")
    if normalized.startswith("/"):
        combined = posixpath.normpath(normalized.lstrip("/"))
    else:
        combined = posixpath.normpath(posixpath.join("xl", normalized))
    if combined.startswith("../") or combined == ".." or not combined.startswith("xl/"):
        raise ActionWorkbookError("Workbook contains an unsafe worksheet relationship.")
    return combined


def _read_shared_strings(archive: zipfile.ZipFile) -> tuple[str, ...]:
    root = _xml_part(archive, "xl/sharedStrings.xml", required=False)
    if root is None:
        return ()
    strings: list[str] = []
    for item in (node for node in root if _local_name(node.tag) == "si"):
        value = "".join(node.text or "" for node in item.iter() if _local_name(node.tag) == "t")
        _validate_cell_text(value)
        strings.append(value)
        if len(strings) > MAX_SHARED_STRINGS:
            raise ActionWorkbookError(
                f"The workbook contains more than {MAX_SHARED_STRINGS:,} shared strings."
            )
    return tuple(strings)


def _read_sheet_cells(
    archive: zipfile.ZipFile,
    part: str,
    shared_strings: tuple[str, ...],
    *,
    max_rows: int,
) -> dict[int, dict[int, _CellValue]]:
    root = _xml_part(archive, part)
    assert root is not None
    rows: dict[int, dict[int, _CellValue]] = {}
    inspected = 0
    for cell in (node for node in root.iter() if _local_name(node.tag) == "c"):
        inspected += 1
        if inspected > MAX_INSPECTED_CELLS:
            raise ActionWorkbookError(
                f"A worksheet contains more than {MAX_INSPECTED_CELLS:,} cells."
            )
        reference = cell.attrib.get("r", "").upper()
        match = _CELL_REFERENCE.fullmatch(reference)
        if match is None:
            raise ActionWorkbookError("A worksheet cell has an invalid reference.")
        column = _column_number(match.group(1))
        row_number = int(match.group(2))
        value = _xlsx_cell_value(cell, shared_strings)
        if row_number > max_rows:
            if value.value.strip() or value.has_formula:
                if max_rows == MAX_ACTION_ROWS + 1:
                    raise ActionWorkbookError(
                        f"The Actions sheet supports at most {MAX_ACTION_ROWS:,} populated rows."
                    )
                raise ActionWorkbookError("A workbook identity sheet exceeds its safe row limit.")
            continue
        row = rows.setdefault(row_number, {})
        if column in row:
            raise ActionWorkbookError(f"Worksheet contains duplicate cell {reference}.")
        row[column] = value
    return rows


def _xlsx_cell_value(cell: ET.Element, shared_strings: tuple[str, ...]) -> _CellValue:
    formula = any(_local_name(node.tag) == "f" for node in cell)
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        value = "".join(
            node.text or "" for node in cell.iter() if _local_name(node.tag) == "t"
        )
    else:
        value_node = next((node for node in cell if _local_name(node.tag) == "v"), None)
        value = value_node.text or "" if value_node is not None else ""
        if cell_type == "s" and value:
            try:
                value = shared_strings[int(value)]
            except (ValueError, IndexError) as exc:
                raise ActionWorkbookError("A shared-string cell has an invalid index.") from exc
    _validate_cell_text(value)
    return _CellValue(value, formula)


def _validate_cell_text(value: str) -> None:
    if len(value) > MAX_CELL_CHARACTERS:
        raise ActionWorkbookError(
            f"A workbook cell exceeds Excel's {MAX_CELL_CHARACTERS:,}-character text limit."
        )


def _cell(
    rows: dict[int, dict[int, _CellValue]],
    row: int,
    column: int,
) -> _CellValue:
    return rows.get(row, {}).get(column, _CellValue("", False))


def _parse_action_row(row_number: int, values: tuple[str, ...]) -> ActionWorkbookRow:
    import_value = _trim_single_line(
        values[0], row_number=row_number, field="Import"
    ).casefold()
    if import_value in _INCLUDE_MARKERS:
        include = True
    elif import_value in _EXCLUDE_MARKERS:
        include = False
    else:
        raise ActionWorkbookError(
            f'Actions row {row_number} has invalid Import value "{values[0].strip()}". Use Yes, No, or blank.'
        )
    return ActionWorkbookRow(
        row_number=row_number,
        include=include,
        name=_trim_single_line(values[1], row_number=row_number, field="Name"),
        action_type=_trim_single_line(
            values[2], row_number=row_number, field="Action type"
        ),
        value=_multiline(values[3]),
        contexts=_split_delimited(values[4], ";"),
        tags=_split_delimited(values[5], ";"),
        description=_multiline(values[6]),
        quick_menu=_split_delimited(values[7], ">"),
        arguments=_split_lines(values[8]),
        working_folder=_trim_single_line(
            values[9], row_number=row_number, field="Working folder"
        ),
    )


def _trim_single_line(value: str, *, row_number: int, field: str) -> str:
    clean = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if "\n" in clean:
        raise ActionWorkbookError(
            f'Actions row {row_number} field "{field}" must contain one line.'
        )
    return clean


def _single_line(value: str) -> str:
    return " ".join(value.strip().split())


def _multiline(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def _split_delimited(value: str, delimiter: str) -> tuple[str, ...]:
    return tuple(_single_line(item) for item in value.split(delimiter) if item.strip())


def _split_lines(value: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in _multiline(value).splitlines() if line.strip())


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _column_number(label: str) -> int:
    value = 0
    for character in label.upper():
        value = value * 26 + ord(character) - ord("A") + 1
    return value


def _column_label(number: int) -> str:
    output = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        output = chr(ord("A") + remainder) + output
    return output


def _write_part(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(name, _FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, payload)


def _xml_bytes(root: ET.Element) -> bytes:
    namespace = root.tag[1:].split("}", 1)[0] if root.tag.startswith("{") else ""
    if namespace in _DEFAULT_XML_NAMESPACES:
        # Strict OPC/Open XML consumers do not all accept ElementTree's
        # generated ``ns0:`` prefix on package roots. Emit the conventional
        # default namespace used by Excel and the Open XML SDK.
        ET.register_namespace("", namespace)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _content_types_xml() -> bytes:
    root = ET.Element(f"{{{_CONTENT_TYPES_NS}}}Types")
    for extension, content_type in (
        ("rels", "application/vnd.openxmlformats-package.relationships+xml"),
        ("xml", "application/xml"),
    ):
        ET.SubElement(root, f"{{{_CONTENT_TYPES_NS}}}Default", Extension=extension, ContentType=content_type)
    overrides = (
        ("/xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"),
        ("/xl/worksheets/sheet1.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"),
        ("/xl/worksheets/sheet2.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"),
        ("/xl/worksheets/sheet3.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"),
        ("/xl/styles.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"),
        ("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
        ("/docProps/app.xml", "application/vnd.openxmlformats-officedocument.extended-properties+xml"),
    )
    for part_name, content_type in overrides:
        ET.SubElement(root, f"{{{_CONTENT_TYPES_NS}}}Override", PartName=part_name, ContentType=content_type)
    return _xml_bytes(root)


def _package_relationships_xml() -> bytes:
    root = ET.Element(f"{{{_PACKAGE_REL_NS}}}Relationships")
    relationships = (
        ("rId1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument", "xl/workbook.xml"),
        ("rId2", "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties", "docProps/core.xml"),
        ("rId3", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties", "docProps/app.xml"),
    )
    for relationship_id, relationship_type, target in relationships:
        ET.SubElement(root, f"{{{_PACKAGE_REL_NS}}}Relationship", Id=relationship_id, Type=relationship_type, Target=target)
    return _xml_bytes(root)


def _workbook_xml() -> bytes:
    ET.register_namespace("r", _REL_NS)
    root = ET.Element(f"{{{_MAIN_NS}}}workbook")
    ET.SubElement(root, f"{{{_MAIN_NS}}}workbookPr", date1904="0")
    views = ET.SubElement(root, f"{{{_MAIN_NS}}}bookViews")
    ET.SubElement(views, f"{{{_MAIN_NS}}}workbookView", activeTab="1")
    sheets = ET.SubElement(root, f"{{{_MAIN_NS}}}sheets")
    for index, name in enumerate(("Instructions", "Actions", "Reference"), 1):
        ET.SubElement(
            sheets,
            f"{{{_MAIN_NS}}}sheet",
            name=name,
            sheetId=str(index),
            attrib={f"{{{_REL_NS}}}id": f"rId{index}"},
        )
    return _xml_bytes(root)


def _workbook_relationships_xml() -> bytes:
    root = ET.Element(f"{{{_PACKAGE_REL_NS}}}Relationships")
    for index in range(1, 4):
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
        Id="rId4",
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles",
        Target="styles.xml",
    )
    return _xml_bytes(root)


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
    created = ET.SubElement(root, f"{{{dcterms_ns}}}created", attrib={f"{{{xsi_ns}}}type": "dcterms:W3CDTF"})
    created.text = "2020-01-01T00:00:00Z"
    modified = ET.SubElement(root, f"{{{dcterms_ns}}}modified", attrib={f"{{{xsi_ns}}}type": "dcterms:W3CDTF"})
    modified.text = "2020-01-01T00:00:00Z"
    return _xml_bytes(root)


def _app_properties_xml() -> bytes:
    app_ns = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
    vt_ns = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
    ET.register_namespace("vt", vt_ns)
    root = ET.Element(f"{{{app_ns}}}Properties")
    ET.SubElement(root, f"{{{app_ns}}}Application").text = "Context Palette"
    ET.SubElement(root, f"{{{app_ns}}}AppVersion").text = "1.0"
    return _xml_bytes(root)


def _styles_xml() -> bytes:
    root = ET.Element(f"{{{_MAIN_NS}}}styleSheet")
    fonts = ET.SubElement(root, f"{{{_MAIN_NS}}}fonts", count="3")
    for bold, color, size in ((False, "FF202124", "11"), (True, "FFFFFFFF", "11"), (True, "FFFFFFFF", "14")):
        font = ET.SubElement(fonts, f"{{{_MAIN_NS}}}font")
        ET.SubElement(font, f"{{{_MAIN_NS}}}name", val="Aptos")
        ET.SubElement(font, f"{{{_MAIN_NS}}}sz", val=size)
        if bold:
            ET.SubElement(font, f"{{{_MAIN_NS}}}b")
        ET.SubElement(font, f"{{{_MAIN_NS}}}color", rgb=color)
    fills = ET.SubElement(root, f"{{{_MAIN_NS}}}fills", count="4")
    ET.SubElement(ET.SubElement(fills, f"{{{_MAIN_NS}}}fill"), f"{{{_MAIN_NS}}}patternFill", patternType="none")
    ET.SubElement(ET.SubElement(fills, f"{{{_MAIN_NS}}}fill"), f"{{{_MAIN_NS}}}patternFill", patternType="gray125")
    for color in ("FF0F766E", "FFEF233C"):
        fill = ET.SubElement(fills, f"{{{_MAIN_NS}}}fill")
        pattern = ET.SubElement(fill, f"{{{_MAIN_NS}}}patternFill", patternType="solid")
        ET.SubElement(pattern, f"{{{_MAIN_NS}}}fgColor", rgb=color)
        ET.SubElement(pattern, f"{{{_MAIN_NS}}}bgColor", indexed="64")
    borders = ET.SubElement(root, f"{{{_MAIN_NS}}}borders", count="2")
    for styled in (False, True):
        border = ET.SubElement(borders, f"{{{_MAIN_NS}}}border")
        for side_name in ("left", "right", "top", "bottom"):
            side = ET.SubElement(
                border,
                f"{{{_MAIN_NS}}}{side_name}",
                **({"style": "thin"} if styled else {}),
            )
            if styled:
                ET.SubElement(side, f"{{{_MAIN_NS}}}color", rgb="FFD0D7DE")
        ET.SubElement(border, f"{{{_MAIN_NS}}}diagonal")
    cell_style_xfs = ET.SubElement(root, f"{{{_MAIN_NS}}}cellStyleXfs", count="1")
    ET.SubElement(cell_style_xfs, f"{{{_MAIN_NS}}}xf", numFmtId="0", fontId="0", fillId="0", borderId="0")
    cell_xfs = ET.SubElement(root, f"{{{_MAIN_NS}}}cellXfs", count="4")
    ET.SubElement(cell_xfs, f"{{{_MAIN_NS}}}xf", numFmtId="0", fontId="0", fillId="0", borderId="0", xfId="0")
    ET.SubElement(cell_xfs, f"{{{_MAIN_NS}}}xf", numFmtId="0", fontId="1", fillId="2", borderId="1", xfId="0", applyFont="1", applyFill="1", applyBorder="1", applyAlignment="1").append(ET.Element(f"{{{_MAIN_NS}}}alignment", vertical="center", wrapText="1"))
    ET.SubElement(cell_xfs, f"{{{_MAIN_NS}}}xf", numFmtId="0", fontId="2", fillId="3", borderId="0", xfId="0", applyFont="1", applyFill="1", applyAlignment="1").append(ET.Element(f"{{{_MAIN_NS}}}alignment", vertical="center"))
    ET.SubElement(cell_xfs, f"{{{_MAIN_NS}}}xf", numFmtId="0", fontId="0", fillId="0", borderId="1", xfId="0", applyBorder="1", applyAlignment="1").append(ET.Element(f"{{{_MAIN_NS}}}alignment", vertical="top", wrapText="1"))
    cell_styles = ET.SubElement(root, f"{{{_MAIN_NS}}}cellStyles", count="1")
    ET.SubElement(cell_styles, f"{{{_MAIN_NS}}}cellStyle", name="Normal", xfId="0", builtinId="0")
    return _xml_bytes(root)


def _instructions_sheet_xml() -> bytes:
    rows = (
        (WORKBOOK_TITLE,),
        ("Contract version", WORKBOOK_VERSION),
        (),
        ("How to use",),
        ("1. Add one Action per row on the Actions sheet. Blank Import means Yes; use No to skip a row." ,),
        ("2. Use an Action type ID or user label from the Reference sheet." ,),
        ("3. Separate Contexts and Tags with semicolons, Quick menu levels with >, and Arguments with line breaks." ,),
        ("4. Arguments and Working folder are used only by application and Windows-target Actions." ,),
        ("5. Contexts must already exist. Leave Contexts blank for General only." ,),
        ("6. Keep values as text. Formulas are rejected and never evaluated." ,),
        ("7. Context Palette reviews every included row before creating permanent personal Actions." ,),
    )
    return _worksheet_xml(rows, widths=(22, 100), title_rows={1: 2, 4: 1})


def _actions_sheet_xml() -> bytes:
    type_ids = [
        action_type
        for action_type in CREATABLE_ACTION_TYPES
        if action_type not in {"sequence", "excel_automation", "transform_file_text"}
    ]
    root = _worksheet_root(widths=(10, 28, 28, 50, 28, 24, 45, 28, 40, 40), frozen=True)
    sheet_data = ET.SubElement(root, f"{{{_MAIN_NS}}}sheetData")
    _append_row(sheet_data, 1, ACTION_HEADERS, style=1)
    ET.SubElement(root, f"{{{_MAIN_NS}}}autoFilter", ref="A1:J1")
    validations = ET.SubElement(root, f"{{{_MAIN_NS}}}dataValidations", count="2")
    import_validation = ET.SubElement(validations, f"{{{_MAIN_NS}}}dataValidation", type="list", allowBlank="1", showErrorMessage="1", errorTitle="Invalid Import value", error="Choose Yes or No.", sqref=f"A2:A{MAX_ACTION_ROWS + 1}")
    ET.SubElement(import_validation, f"{{{_MAIN_NS}}}formula1").text = '"Yes,No"'
    type_validation = ET.SubElement(validations, f"{{{_MAIN_NS}}}dataValidation", type="list", allowBlank="1", showErrorMessage="1", errorTitle="Unknown Action type", error="Choose a supported Action type ID.", sqref=f"C2:C{MAX_ACTION_ROWS + 1}")
    ET.SubElement(type_validation, f"{{{_MAIN_NS}}}formula1").text = '"' + ",".join(type_ids) + '"'
    return _xml_bytes(root)


def _reference_sheet_xml() -> bytes:
    rows: list[tuple[str, ...]] = [("Action type ID", "User label", "Purpose")]
    for action_type, definition in CREATABLE_ACTION_TYPES.items():
        if action_type in {"sequence", "excel_automation", "transform_file_text"}:
            continue
        rows.append((action_type, definition.label, definition.description))
    return _worksheet_xml(rows, widths=(30, 34, 100), header_rows={1}, frozen=True, auto_filter=f"A1:C{len(rows)}")


def _worksheet_xml(
    rows: Iterable[tuple[str, ...]],
    *,
    widths: tuple[int, ...],
    title_rows: dict[int, int] | None = None,
    header_rows: set[int] | None = None,
    frozen: bool = False,
    auto_filter: str = "",
) -> bytes:
    root = _worksheet_root(widths=widths, frozen=frozen)
    sheet_data = ET.SubElement(root, f"{{{_MAIN_NS}}}sheetData")
    title_rows = title_rows or {}
    header_rows = header_rows or set()
    for row_number, values in enumerate(rows, 1):
        if not values:
            continue
        style = title_rows.get(row_number, 1 if row_number in header_rows else 0)
        _append_row(sheet_data, row_number, values, style=style)
    if auto_filter:
        ET.SubElement(root, f"{{{_MAIN_NS}}}autoFilter", ref=auto_filter)
    return _xml_bytes(root)


def _worksheet_root(*, widths: tuple[int, ...], frozen: bool = False) -> ET.Element:
    root = ET.Element(f"{{{_MAIN_NS}}}worksheet")
    views = ET.SubElement(root, f"{{{_MAIN_NS}}}sheetViews")
    view = ET.SubElement(views, f"{{{_MAIN_NS}}}sheetView", workbookViewId="0")
    if frozen:
        ET.SubElement(view, f"{{{_MAIN_NS}}}pane", ySplit="1", topLeftCell="A2", activePane="bottomLeft", state="frozen")
        ET.SubElement(view, f"{{{_MAIN_NS}}}selection", pane="bottomLeft", activeCell="A2", sqref="A2")
    ET.SubElement(root, f"{{{_MAIN_NS}}}sheetFormatPr", defaultRowHeight="15")
    columns = ET.SubElement(root, f"{{{_MAIN_NS}}}cols")
    for number, width in enumerate(widths, 1):
        ET.SubElement(columns, f"{{{_MAIN_NS}}}col", min=str(number), max=str(number), width=str(width), customWidth="1")
    return root


def _append_row(
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
        text.set(_XML_SPACE, "preserve")
        text.text = value
