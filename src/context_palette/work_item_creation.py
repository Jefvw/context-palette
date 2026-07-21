from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil

from .work_items import MARKER_PATTERN, WorkItemSource


INVALID_NAME_PATTERN = re.compile(r'[<>:"/\\|?*]|[\x00-\x1f]')
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class WorkItemCreationError(ValueError):
    """A Work Item cannot be created without risking existing data."""


@dataclass(frozen=True, slots=True)
class CreatedWorkItem:
    folder_path: Path
    workbook_path: Path


def suggest_work_item_name(
    kind_code: str,
    organisation: str,
    subject: str,
    project_code: str = "",
) -> str:
    parts = (
        kind_code.strip().upper(),
        organisation.strip().upper(),
        _name_part(subject),
        project_code.strip().upper(),
    )
    return "-".join(part for part in parts if part)


def validate_work_item_name(name: str) -> str:
    clean = name.strip()
    if not clean:
        raise WorkItemCreationError("Final Work Item name cannot be empty.")
    if clean in {".", ".."} or clean.endswith((".", " ")):
        raise WorkItemCreationError("Final Work Item name cannot end with a period or space.")
    if INVALID_NAME_PATTERN.search(clean):
        raise WorkItemCreationError("Final Work Item name contains a character Windows filenames cannot use.")
    if clean.split(".", 1)[0].upper() in RESERVED_NAMES:
        raise WorkItemCreationError("Final Work Item name is reserved by Windows.")
    if MARKER_PATTERN.search(clean):
        raise WorkItemCreationError("Final Work Item name cannot end with five or more hyphens.")
    return clean


def create_work_item_from_template(
    source: WorkItemSource,
    final_name: str,
    template_path: Path,
) -> CreatedWorkItem:
    name = validate_work_item_name(final_name)
    template = Path(template_path)
    if not template.is_absolute() or not template.is_file() or template.suffix.casefold() != ".xlsx":
        raise WorkItemCreationError("Choose an existing .xlsx generic template.")
    if not source.workitems_path.is_dir():
        raise WorkItemCreationError(f'Work Item source “{source.name}” is unavailable.')
    folder = source.workitems_path / name
    workbook = folder / f"{name}.xlsx"
    if folder.exists():
        raise WorkItemCreationError(f'A Work Item named “{name}” already exists in this source.')
    try:
        folder.mkdir()
        shutil.copy2(template, workbook)
    except OSError as exc:
        try:
            workbook.unlink(missing_ok=True)
            folder.rmdir()
        except OSError:
            pass
        raise WorkItemCreationError("The Work Item could not be created from the template.") from exc
    return CreatedWorkItem(folder, workbook)


def _name_part(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^A-Za-z0-9]+", "-", value.strip())).strip("-")
