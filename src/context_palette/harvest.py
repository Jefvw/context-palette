from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path, PurePosixPath
import queue
import re
import threading
from typing import Callable, Iterable
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4
import xml.etree.ElementTree as ET
import zipfile

from .actions import Action, ActionError, configured_draft_action, validate_http_url


SUPPORTED_EXTENSIONS = frozenset({".md", ".txt", ".docx", ".xlsx"})
MAX_SOURCES = 100
MAX_TOTAL_SOURCE_BYTES = 500 * 1024 * 1024
MAX_TEXT_BYTES = 25 * 1024 * 1024
MAX_OOXML_BYTES = 100 * 1024 * 1024
MAX_XML_PART_BYTES = 50 * 1024 * 1024
MAX_XML_TOTAL_BYTES = 250 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_ZIP_ENTRIES = 10_000
MAX_WORKSHEETS = 200
MAX_EXCEL_CELLS = 1_000_000
MAX_OCCURRENCES_PER_SOURCE = 20_000
MAX_CANDIDATES = 10_000
MAX_LABEL_CHARS = 500
MAX_CONTEXT_CHARS = 240

URL_RE = re.compile(r"https?://[^\s<>\]\[()\"']+", re.IGNORECASE)
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+['\"][^)]*['\"])?\)")
HYPERLINK_FORMULA_RE = re.compile(
    r'^\s*HYPERLINK\(\s*"((?:[^"]|"")*)"\s*[,;]\s*"((?:[^"]|"")*)"\s*\)\s*$',
    re.IGNORECASE,
)
GENERIC_LABELS = frozenset({"here", "link", "click here", "read more", "open", "website"})
OLE_COMPOUND_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


@dataclass(frozen=True, slots=True)
class HarvestOccurrence:
    source_id: str
    source_path: Path
    source_format: str
    location: str
    display_text: str
    target: str
    surrounding_text: str = ""


@dataclass(frozen=True, slots=True)
class HarvestSourceResult:
    id: str
    ordinal: int
    path: Path
    source_format: str
    status: str
    occurrences: tuple[HarvestOccurrence, ...] = ()
    warnings: tuple[str, ...] = ()
    error: str = ""
    size: int = 0
    modified_ns: int = 0


@dataclass(slots=True)
class HarvestCandidate:
    id: str
    name: str
    target: str
    comparison_key: str
    occurrences: list[HarvestOccurrence]
    classification: str = "Ready"
    duplicate_state: str = "New"
    warnings: list[str] = field(default_factory=list)
    contexts: set[str] = field(default_factory=set)
    tags: set[str] = field(default_factory=set)
    selected: bool = False
    user_modified: bool = False


@dataclass(slots=True)
class HarvestBatch:
    id: str = field(default_factory=lambda: f"harvest-{uuid4().hex[:12]}")
    sources: list[HarvestSourceResult] = field(default_factory=list)
    candidates: list[HarvestCandidate] = field(default_factory=list)
    cancelled: bool = False


class HarvestError(ValueError):
    pass


def normalize_url_for_comparison(target: str) -> str:
    parsed = urlsplit(target.strip())
    scheme = parsed.scheme.casefold()
    hostname = (parsed.hostname or "").casefold()
    port = parsed.port
    if (scheme, port) in {("http", 80), ("https", 443)}:
        port = None
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    netloc = f"{host}:{port}" if port is not None else host
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, parsed.fragment))


def _meaningful_label(label: str, target: str) -> str:
    clean = " ".join(label.split())[:MAX_LABEL_CHARS]
    if not clean or clean.casefold() in GENERIC_LABELS or clean.casefold() == target.casefold():
        parsed = urlsplit(target)
        subject = parsed.path.rstrip("/").rsplit("/", 1)[-1]
        clean = f"Open {parsed.hostname or 'website'}"
        if subject:
            clean += f" {subject}"
    return clean


def _context(text: str, start: int, end: int) -> str:
    half = MAX_CONTEXT_CHARS // 2
    return " ".join(text[max(0, start - half) : min(len(text), end + half)].split())[
        :MAX_CONTEXT_CHARS
    ]


def _occurrence(
    source_id: str,
    path: Path,
    source_format: str,
    location: str,
    label: str,
    target: str,
    surrounding: str = "",
) -> HarvestOccurrence:
    return HarvestOccurrence(
        source_id,
        path,
        source_format,
        location,
        " ".join(label.split())[:MAX_LABEL_CHARS],
        target.strip().rstrip(".,;:!?"),
        surrounding[:MAX_CONTEXT_CHARS],
    )


def _text_occurrences(
    path: Path,
    source_id: str,
    *,
    markdown: bool,
    cancelled: Callable[[], bool],
) -> tuple[HarvestOccurrence, ...]:
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise HarvestError(f"File exceeds the {MAX_TEXT_BYTES // (1024 * 1024)} MiB text limit.")
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig")
    occurrences: list[HarvestOccurrence] = []
    in_code = False
    for number, line in enumerate(text.splitlines(), 1):
        if number % 1000 == 0 and cancelled():
            break
        if markdown and line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        occupied: list[tuple[int, int]] = []
        if markdown:
            for match in MARKDOWN_LINK_RE.finditer(line):
                occupied.append(match.span())
                occurrences.append(
                    _occurrence(
                        source_id,
                        path,
                        path.suffix.casefold(),
                        f"line {number}",
                        match.group(1),
                        match.group(2),
                        _context(line, *match.span()),
                    )
                )
                if len(occurrences) >= MAX_OCCURRENCES_PER_SOURCE:
                    break
        if len(occurrences) >= MAX_OCCURRENCES_PER_SOURCE:
            break
        for match in URL_RE.finditer(line):
            if any(start <= match.start() < end for start, end in occupied):
                continue
            occurrences.append(
                _occurrence(
                    source_id,
                    path,
                    path.suffix.casefold(),
                    f"line {number}",
                    match.group(0),
                    match.group(0),
                    _context(line, *match.span()),
                )
            )
            if len(occurrences) >= MAX_OCCURRENCES_PER_SOURCE:
                break
        if len(occurrences) >= MAX_OCCURRENCES_PER_SOURCE:
            break
    return tuple(occurrences)


def _safe_zip(path: Path) -> zipfile.ZipFile:
    if path.stat().st_size > MAX_OOXML_BYTES:
        raise HarvestError(f"Office package exceeds the {MAX_OOXML_BYTES // (1024 * 1024)} MiB limit.")
    try:
        with path.open("rb") as stream:
            signature = stream.read(len(OLE_COMPOUND_SIGNATURE))
        if signature == OLE_COMPOUND_SIGNATURE:
            raise HarvestError("Encrypted or legacy Office documents are not supported.")
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise HarvestError("The Office document is corrupt or is not a supported OOXML package.") from exc
    entries = archive.infolist()
    if len(entries) > MAX_ZIP_ENTRIES:
        archive.close()
        raise HarvestError(f"The Office package contains more than {MAX_ZIP_ENTRIES:,} entries.")
    total = 0
    for item in entries:
        if item.flag_bits & 0x1:
            archive.close()
            raise HarvestError("Encrypted Office documents are not supported.")
        total += item.file_size
        if item.file_size > MAX_XML_PART_BYTES and item.filename.casefold().endswith(".xml"):
            archive.close()
            raise HarvestError("An XML part exceeds the safe extraction limit.")
        unsafe_ratio = item.file_size > 0 and (
            item.compress_size == 0
            or item.file_size / item.compress_size > MAX_COMPRESSION_RATIO
        )
        if unsafe_ratio:
            archive.close()
            raise HarvestError("The Office package has an unsafe compression ratio.")
    if total > MAX_XML_TOTAL_BYTES:
        archive.close()
        raise HarvestError("The expanded Office package exceeds the safe extraction limit.")
    return archive


def _xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    try:
        with archive.open(name) as stream:
            return ET.parse(stream).getroot()
    except (KeyError, ET.ParseError, OSError) as exc:
        raise HarvestError(f"Required Office XML is missing or corrupt: {name}") from exc


def _relationships(archive: zipfile.ZipFile, name: str) -> dict[str, str]:
    try:
        root = _xml(archive, name)
    except HarvestError:
        return {}
    return {
        item.attrib.get("Id", ""): item.attrib.get("Target", "")
        for item in root
        if item.attrib.get("Id") and item.attrib.get("Target")
    }


def _docx_occurrences(
    path: Path,
    source_id: str,
    cancelled: Callable[[], bool],
) -> tuple[HarvestOccurrence, ...]:
    with _safe_zip(path) as archive:
        root = _xml(archive, "word/document.xml")
        relationships = _relationships(archive, "word/_rels/document.xml.rels")
        r_id = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        occurrences: list[HarvestOccurrence] = []
        paragraph = 0
        for index, element in enumerate(root.iter(), 1):
            if index % 1000 == 0 and cancelled():
                break
            if element.tag.endswith("}p"):
                paragraph += 1
            if not element.tag.endswith("}hyperlink"):
                continue
            target = relationships.get(element.attrib.get(r_id, ""), "")
            label = "".join(node.text or "" for node in element.iter() if node.tag.endswith("}t"))
            occurrences.append(
                _occurrence(source_id, path, ".docx", f"paragraph {paragraph}", label, target, label)
            )
            if len(occurrences) >= MAX_OCCURRENCES_PER_SOURCE:
                break
        return tuple(occurrences)


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = _xml(archive, "xl/sharedStrings.xml")
    return ["".join(node.text or "" for node in item.iter() if node.tag.endswith("}t")) for item in root]


def _xlsx_occurrences(
    path: Path,
    source_id: str,
    cancelled: Callable[[], bool],
) -> tuple[tuple[HarvestOccurrence, ...], tuple[str, ...]]:
    with _safe_zip(path) as archive:
        warnings: list[str] = []
        strings = _shared_strings(archive)
        worksheets = sorted(
            name
            for name in archive.namelist()
            if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name, re.IGNORECASE)
        )
        if len(worksheets) > MAX_WORKSHEETS:
            warnings.append(f"Only the first {MAX_WORKSHEETS} worksheets were inspected.")
            worksheets = worksheets[:MAX_WORKSHEETS]
        occurrences: list[HarvestOccurrence] = []
        inspected_cells = 0
        r_id = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        for worksheet in worksheets:
            if cancelled():
                break
            root = _xml(archive, worksheet)
            cell_values: dict[str, str] = {}
            for cell in (item for item in root.iter() if item.tag.endswith("}c")):
                inspected_cells += 1
                if inspected_cells % 1000 == 0 and cancelled():
                    break
                if inspected_cells > MAX_EXCEL_CELLS:
                    warnings.append(f"Cell inspection stopped at {MAX_EXCEL_CELLS:,} cells.")
                    break
                reference = cell.attrib.get("r", "")
                formula_node = next((node for node in cell if node.tag.endswith("}f")), None)
                formula = formula_node.text if formula_node is not None else None
                value = ""
                if cell.attrib.get("t") == "inlineStr":
                    value = "".join(node.text or "" for node in cell.iter() if node.tag.endswith("}t"))
                else:
                    value_node = next((node for node in cell if node.tag.endswith("}v")), None)
                    if value_node is not None and value_node.text:
                        value = value_node.text
                        if cell.attrib.get("t") == "s":
                            try:
                                value = strings[int(value)]
                            except (ValueError, IndexError):
                                value = ""
                cell_values[reference] = value
                if formula_node is None:
                    for match in URL_RE.finditer(value):
                        occurrences.append(
                            _occurrence(source_id, path, ".xlsx", f"{PurePosixPath(worksheet).stem}!{reference}", value, match.group(0), value)
                        )
                        if len(occurrences) >= MAX_OCCURRENCES_PER_SOURCE:
                            break
                elif formula and (match := HYPERLINK_FORMULA_RE.match(formula)) is not None:
                    target = match.group(1).replace('""', '"')
                    label = match.group(2).replace('""', '"')
                    occurrences.append(
                        _occurrence(source_id, path, ".xlsx", f"{PurePosixPath(worksheet).stem}!{reference}", label, target, label)
                    )
                if len(occurrences) >= MAX_OCCURRENCES_PER_SOURCE:
                    break
            if cancelled():
                break
            rel_name = str(PurePosixPath(worksheet).parent / "_rels" / (PurePosixPath(worksheet).name + ".rels"))
            relationships = _relationships(archive, rel_name)
            for link_index, link in enumerate(
                (item for item in root.iter() if item.tag.endswith("}hyperlink")),
                1,
            ):
                if link_index % 1000 == 0 and cancelled():
                    break
                reference = link.attrib.get("ref", "")
                target = relationships.get(link.attrib.get(r_id, ""), link.attrib.get("location", ""))
                label = link.attrib.get("display", "") or cell_values.get(reference, "")
                occurrences.append(
                    _occurrence(source_id, path, ".xlsx", f"{PurePosixPath(worksheet).stem}!{reference}", label, target, label)
                )
                if len(occurrences) >= MAX_OCCURRENCES_PER_SOURCE:
                    break
            if inspected_cells > MAX_EXCEL_CELLS or len(occurrences) >= MAX_OCCURRENCES_PER_SOURCE:
                break
        if len(occurrences) >= MAX_OCCURRENCES_PER_SOURCE:
            warnings.append(f"Extraction stopped at {MAX_OCCURRENCES_PER_SOURCE:,} occurrences.")
        if cancelled():
            warnings.append("Extraction was cancelled after a bounded workbook unit.")
        return tuple(occurrences[:MAX_OCCURRENCES_PER_SOURCE]), tuple(dict.fromkeys(warnings))


def extract_source(
    path: Path,
    ordinal: int,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> HarvestSourceResult:
    resolved = path.resolve()
    source_id = f"source-{ordinal + 1}"
    suffix = resolved.suffix.casefold()
    try:
        stat = resolved.stat()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise HarvestError(f"Unsupported document format: {suffix or '(none)'}")
        warnings: tuple[str, ...] = ()
        if suffix == ".md":
            occurrences = _text_occurrences(resolved, source_id, markdown=True, cancelled=cancelled)
        elif suffix == ".txt":
            occurrences = _text_occurrences(resolved, source_id, markdown=False, cancelled=cancelled)
        elif suffix == ".docx":
            occurrences = _docx_occurrences(resolved, source_id, cancelled)
            warnings = ()
        else:
            occurrences, warnings = _xlsx_occurrences(resolved, source_id, cancelled)
        if cancelled():
            return HarvestSourceResult(
                source_id,
                ordinal,
                resolved,
                suffix,
                "Cancelled",
                warnings=("Extraction was cancelled; partial findings were discarded.",),
                size=stat.st_size,
                modified_ns=stat.st_mtime_ns,
            )
        warning = warnings or (
            (f"Extraction stopped at {MAX_OCCURRENCES_PER_SOURCE:,} occurrences.",)
            if len(occurrences) >= MAX_OCCURRENCES_PER_SOURCE
            else ()
        )
        return HarvestSourceResult(
            source_id,
            ordinal,
            resolved,
            suffix,
            "Complete with warnings" if warning else "Complete",
            occurrences,
            warning,
            size=stat.st_size,
            modified_ns=stat.st_mtime_ns,
        )
    except (HarvestError, OSError, UnicodeError) as exc:
        return HarvestSourceResult(source_id, ordinal, resolved, suffix, "Failed", error=str(exc))


def build_candidates(
    sources: Iterable[HarvestSourceResult],
    existing_actions: Iterable[Action],
    *,
    default_context: str = "General",
) -> list[HarvestCandidate]:
    candidates: dict[str, HarvestCandidate] = {}
    existing: dict[str, str] = {}
    for action in existing_actions:
        if action.type == "open_url" and action.state in {"Draft", "Trusted"}:
            try:
                key = normalize_url_for_comparison(action.value)
                if action.state == "Trusted" or key not in existing:
                    existing[key] = action.state
            except ValueError:
                continue
    for source in sorted(sources, key=lambda item: item.ordinal):
        for occurrence in source.occurrences:
            target = occurrence.target.strip()
            try:
                validate_http_url(target, label="Harvested URL")
                key = normalize_url_for_comparison(target)
                supported = True
            except (ActionError, ValueError):
                key = f"unsupported:{target.casefold()}"
                supported = False
            candidate = candidates.get(key)
            if candidate is None:
                if len(candidates) >= MAX_CANDIDATES:
                    break
                candidate = HarvestCandidate(
                    id=f"candidate-{sha256(key.encode('utf-8')).hexdigest()[:12]}",
                    name=_meaningful_label(occurrence.display_text, target),
                    target=target,
                    comparison_key=key,
                    occurrences=[],
                    contexts=set() if default_context.casefold() == "general" else {default_context},
                )
                candidates[key] = candidate
            candidate.occurrences.append(occurrence)
            if not supported:
                candidate.classification = "Unsupported"
                candidate.duplicate_state = "Unsupported"
                candidate.selected = False

    for candidate in candidates.values():
        if candidate.classification == "Unsupported":
            continue
        meaningful = {
            " ".join(item.display_text.split())
            for item in candidate.occurrences
            if item.display_text.strip()
            and item.display_text.strip().casefold() not in GENERIC_LABELS
            and item.display_text.strip().casefold() != item.target.casefold()
        }
        if len({label.casefold() for label in meaningful}) > 1:
            candidate.classification = "Needs attention"
            candidate.warnings.append("Conflicting meaningful labels were found.")
        state = existing.get(candidate.comparison_key)
        if state == "Draft":
            candidate.classification = "Existing Draft"
            candidate.duplicate_state = "Existing Draft"
        elif state == "Trusted":
            candidate.classification = "Already available"
            candidate.duplicate_state = "Already available"
        elif len(candidate.occurrences) > 1:
            candidate.duplicate_state = "Repeated in sources"
        candidate.selected = candidate.classification == "Ready" and state is None
    return list(candidates.values())


def update_candidate_values(
    candidates: Iterable[HarvestCandidate],
    *,
    field_name: str,
    operation: str,
    values: Iterable[str],
) -> None:
    normalized = {value.strip() for value in values if value.strip()}
    if field_name not in {"contexts", "tags"} or operation not in {"add", "remove"}:
        raise HarvestError("Bulk edit must add or remove contexts or tags.")
    for candidate in candidates:
        current: set[str] = getattr(candidate, field_name)
        if operation == "add":
            current.update(normalized)
        else:
            remove_keys = {value.casefold() for value in normalized}
            current.difference_update(
                {value for value in current if value.casefold() in remove_keys}
            )


def candidate_to_draft(candidate: HarvestCandidate) -> Action:
    if candidate.classification not in {"Ready", "Needs attention"}:
        raise HarvestError(f"Candidate is not importable: {candidate.classification}")
    return configured_draft_action(
        title=candidate.name,
        context="General",
        contexts=sorted(candidate.contexts, key=str.casefold),
        tags=sorted(candidate.tags, key=str.casefold),
        action_type="open_url",
        value=candidate.target,
    )


class HarvestScanCoordinator:
    """Scan documents off-thread and deliver immutable source results to Tk."""

    def __init__(self) -> None:
        self._queue: queue.SimpleQueue[tuple[str, object]] = queue.SimpleQueue()
        self._cancel = threading.Event()
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self, paths: Iterable[Path]) -> bool:
        if self._running:
            return False
        ordered = tuple(sorted({path.resolve() for path in paths}, key=lambda item: str(item).casefold()))
        if len(ordered) > MAX_SOURCES:
            raise HarvestError(f"Choose no more than {MAX_SOURCES} documents per batch.")
        total = sum(path.stat().st_size for path in ordered if path.exists())
        if total > MAX_TOTAL_SOURCE_BYTES:
            raise HarvestError("The selected documents exceed the 500 MiB batch limit.")
        self._cancel.clear()
        self._running = True

        def work() -> None:
            try:
                for ordinal, path in enumerate(ordered):
                    if self._cancel.is_set():
                        break
                    self._queue.put(("progress", (ordinal, len(ordered), path)))
                    try:
                        result = extract_source(path, ordinal, cancelled=self._cancel.is_set)
                    except Exception as exc:
                        result = HarvestSourceResult(
                            f"source-{ordinal + 1}",
                            ordinal,
                            path,
                            path.suffix.casefold(),
                            "Failed",
                            error=f"Unexpected extraction failure: {exc}",
                        )
                    self._queue.put(("source", result))
            finally:
                self._queue.put(("complete", self._cancel.is_set()))

        threading.Thread(target=work, daemon=True, name="harvest-scan").start()
        return True

    def cancel(self) -> None:
        self._cancel.set()

    def drain(self) -> list[tuple[str, object]]:
        events: list[tuple[str, object]] = []
        while True:
            try:
                event = self._queue.get_nowait()
            except queue.Empty:
                break
            events.append(event)
            if event[0] == "complete":
                self._running = False
        return events
