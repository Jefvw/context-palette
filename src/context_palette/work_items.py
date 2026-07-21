from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


KIND_NAMES = {
    "CAS": "Case",
    "ISS": "Issue",
    "PRJ": "Project",
    "QST": "Question",
    "TRCK": "Track",
}
SOURCE_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
PROJECT_CODE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z0-9]{2}9[A-Za-z0-9](?![A-Za-z0-9])",
    re.IGNORECASE,
)
MARKER_PATTERN = re.compile(r"-{5,}\Z")


class WorkItemDiscoveryError(ValueError):
    """A configured source cannot be validated or safely enumerated."""


@dataclass(frozen=True, slots=True)
class WorkItemSource:
    id: str
    name: str
    workitems_path: Path

    def __post_init__(self) -> None:
        source_id = self.id.strip()
        source_name = self.name.strip()
        path = Path(self.workitems_path)
        if not SOURCE_ID_PATTERN.fullmatch(source_id):
            raise WorkItemDiscoveryError(
                "Work-item source ID must contain lowercase letters, numbers, "
                "and single hyphens only."
            )
        if not source_name:
            raise WorkItemDiscoveryError("Work-item source name cannot be empty.")
        if not path.is_absolute():
            raise WorkItemDiscoveryError("Work-item source folder must be an absolute path.")
        object.__setattr__(self, "id", source_id)
        object.__setattr__(self, "name", source_name)
        object.__setattr__(self, "workitems_path", path)


@dataclass(frozen=True, slots=True)
class ParsedWorkItemName:
    kind_code: str | None
    kind_name: str | None
    organisation: str | None
    subject: str
    project_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DiscoveredWorkItem:
    source_id: str
    source_name: str
    relative_folder: str
    folder_path: Path
    display_name: str
    kind_code: str | None
    kind_name: str | None
    organisation: str | None
    subject: str
    project_codes: tuple[str, ...]
    matching_workbook_path: Path | None

    @property
    def default_open_path(self) -> Path:
        return self.matching_workbook_path or self.folder_path


def is_marker_folder_name(name: str) -> bool:
    return MARKER_PATTERN.search(name) is not None


def parse_work_item_name(name: str) -> ParsedWorkItemName:
    clean = name.strip()
    parts = clean.split("-", 2)
    if len(parts) == 3 and parts[0] and parts[1] and parts[2]:
        kind_code = parts[0].upper()
        organisation = parts[1]
        subject = parts[2]
        kind_name = KIND_NAMES.get(kind_code, kind_code)
    else:
        kind_code = None
        kind_name = None
        organisation = None
        subject = clean

    project_codes: list[str] = []
    seen: set[str] = set()
    for match in PROJECT_CODE_PATTERN.finditer(clean):
        code = match.group(0).upper()
        if code not in seen:
            seen.add(code)
            project_codes.append(code)
    return ParsedWorkItemName(
        kind_code,
        kind_name,
        organisation,
        subject,
        tuple(project_codes),
    )


def work_item_matches(
    item: DiscoveredWorkItem,
    query: str,
    *,
    tags: tuple[str, ...] = (),
    project_code: str | None = None,
    tag: str | None = None,
) -> bool:
    if project_code is not None and project_code.casefold() not in {
        code.casefold() for code in item.project_codes
    }:
        return False
    if tag is not None and tag.casefold() not in {value.casefold() for value in tags}:
        return False
    searchable = " ".join(
        (
            item.display_name,
            item.kind_code or "",
            item.kind_name or "",
            item.organisation or "",
            item.subject,
            item.source_name,
            *item.project_codes,
            *tags,
        )
    ).casefold()
    return all(term in searchable for term in query.casefold().split())


def discover_work_items(source: WorkItemSource) -> tuple[DiscoveredWorkItem, ...]:
    root = source.workitems_path
    if not root.exists():
        raise WorkItemDiscoveryError(
            f'Work-item source "{source.name}" is unavailable.'
        )
    if not root.is_dir():
        raise WorkItemDiscoveryError(
            f'Work-item source "{source.name}" is not a folder.'
        )

    try:
        children = sorted(root.iterdir(), key=lambda path: path.name.casefold())
    except OSError as exc:
        raise WorkItemDiscoveryError(
            f'Work-item source "{source.name}" could not be read.'
        ) from exc

    discovered: list[DiscoveredWorkItem] = []
    for folder in children:
        if is_marker_folder_name(folder.name):
            continue
        try:
            if not folder.is_dir():
                continue
            workbook = _matching_workbook(folder)
        except OSError as exc:
            raise WorkItemDiscoveryError(
                f'Work item "{folder.name}" could not be read.'
            ) from exc
        parsed = parse_work_item_name(folder.name)
        discovered.append(
            DiscoveredWorkItem(
                source_id=source.id,
                source_name=source.name,
                relative_folder=folder.name,
                folder_path=folder,
                display_name=folder.name,
                kind_code=parsed.kind_code,
                kind_name=parsed.kind_name,
                organisation=parsed.organisation,
                subject=parsed.subject,
                project_codes=parsed.project_codes,
                matching_workbook_path=workbook,
            )
        )
    return tuple(discovered)


def _matching_workbook(folder: Path) -> Path | None:
    expected_name = f"{folder.name}.xlsx".casefold()
    matches = sorted(
        (
        child
        for child in folder.iterdir()
        if child.is_file() and child.name.casefold() == expected_name
        ),
        key=lambda path: path.name,
    )
    return matches[0] if matches else None
