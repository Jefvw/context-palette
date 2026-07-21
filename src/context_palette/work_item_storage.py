from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .persistence import atomic_write_json
from .work_items import SOURCE_ID_PATTERN, WorkItemDiscoveryError, WorkItemSource


class WorkItemStorageError(ValueError):
    """Local Work Items configuration is malformed or cannot be interpreted."""


@dataclass(frozen=True, slots=True)
class WorkItemMetadata:
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkItemCreationSettings:
    template_path: Path | None = None


def load_work_item_creation_settings(path: Path) -> WorkItemCreationSettings:
    if not path.exists():
        return WorkItemCreationSettings()
    payload = _read_object(path, "Work-item creation settings")
    if set(payload) != {"template_path"} or not isinstance(payload["template_path"], str):
        raise WorkItemStorageError("Work-item creation settings must contain template_path text only.")
    raw_path = payload["template_path"].strip()
    if not raw_path:
        return WorkItemCreationSettings()
    template_path = Path(raw_path)
    if not template_path.is_absolute():
        raise WorkItemStorageError("Work-item template path must be absolute.")
    return WorkItemCreationSettings(template_path)


def save_work_item_creation_settings(path: Path, settings: WorkItemCreationSettings) -> None:
    template = settings.template_path
    if template is not None and not Path(template).is_absolute():
        raise WorkItemStorageError("Work-item template path must be absolute.")
    atomic_write_json(path, {"template_path": str(template) if template is not None else ""})


def work_item_metadata_key(source_id: str, relative_folder: str) -> str:
    clean_source_id = source_id.strip()
    clean_folder = relative_folder.strip()
    if not SOURCE_ID_PATTERN.fullmatch(clean_source_id):
        raise WorkItemStorageError("Work-item metadata has an invalid source ID.")
    if not clean_folder or "/" in clean_folder or "\\" in clean_folder:
        raise WorkItemStorageError("Work-item metadata has an invalid relative folder.")
    return f"{clean_source_id}/{clean_folder}"


def load_work_item_sources(path: Path) -> tuple[WorkItemSource, ...]:
    if not path.exists():
        return ()
    payload = _read_object(path, "Work-item sources")
    raw_sources = payload.get("sources", [])
    if not isinstance(raw_sources, list):
        raise WorkItemStorageError("Work-item sources must contain a sources list.")

    sources: list[WorkItemSource] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_sources, start=1):
        if not isinstance(raw, dict):
            raise WorkItemStorageError(f"Work-item source #{index} must be an object.")
        if set(raw) != {"id", "name", "workitems_path"}:
            raise WorkItemStorageError(
                f"Work-item source #{index} must contain id, name, and workitems_path only."
            )
        if not all(isinstance(raw[field], str) for field in raw):
            raise WorkItemStorageError(f"Work-item source #{index} fields must be text.")
        try:
            source = WorkItemSource(
                raw["id"],
                raw["name"],
                Path(raw["workitems_path"]),
            )
        except WorkItemDiscoveryError as exc:
            raise WorkItemStorageError(f"Work-item source #{index}: {exc}") from exc
        key = source.id.casefold()
        if key in seen:
            raise WorkItemStorageError(f"Duplicate work-item source ID: {source.id}")
        seen.add(key)
        sources.append(source)
    return tuple(sources)


def save_work_item_sources(path: Path, sources: tuple[WorkItemSource, ...]) -> None:
    seen: set[str] = set()
    for source in sources:
        key = source.id.casefold()
        if key in seen:
            raise WorkItemStorageError(f"Duplicate work-item source ID: {source.id}")
        seen.add(key)
    atomic_write_json(
        path,
        {
            "sources": [
                {
                    "id": source.id,
                    "name": source.name,
                    "workitems_path": str(source.workitems_path),
                }
                for source in sources
            ]
        },
    )


def load_work_item_metadata(path: Path) -> dict[str, WorkItemMetadata]:
    if not path.exists():
        return {}
    payload = _read_object(path, "Work-item metadata")
    raw_items = payload.get("work_items", {})
    if not isinstance(raw_items, dict):
        raise WorkItemStorageError("Work-item metadata must contain a work_items object.")

    metadata: dict[str, WorkItemMetadata] = {}
    for raw_key, raw_value in raw_items.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, dict):
            raise WorkItemStorageError("Each work-item metadata entry must be an object.")
        if set(raw_value) != {"tags"} or not isinstance(raw_value["tags"], list):
            raise WorkItemStorageError(
                f'Work-item metadata "{raw_key}" must contain a tags list only.'
            )
        source_id, separator, relative_folder = raw_key.partition("/")
        if not separator:
            raise WorkItemStorageError(f'Invalid work-item metadata key: "{raw_key}".')
        key = work_item_metadata_key(source_id, relative_folder)
        metadata[key] = WorkItemMetadata(_normalized_tags(raw_value["tags"], key))
    return metadata


def save_work_item_metadata(
    path: Path,
    metadata: dict[str, WorkItemMetadata],
) -> None:
    normalized: dict[str, WorkItemMetadata] = {}
    for raw_key, value in metadata.items():
        source_id, separator, relative_folder = raw_key.partition("/")
        if not separator:
            raise WorkItemStorageError(f'Invalid work-item metadata key: "{raw_key}".')
        key = work_item_metadata_key(source_id, relative_folder)
        normalized[key] = WorkItemMetadata(_normalized_tags(list(value.tags), key))
    atomic_write_json(
        path,
        {
            "work_items": {
                key: {"tags": list(value.tags)}
                for key, value in sorted(normalized.items(), key=lambda pair: pair[0].casefold())
            }
        },
    )


def _read_object(path: Path, label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkItemStorageError(f"{label} could not be read.") from exc
    if not isinstance(payload, dict):
        raise WorkItemStorageError(f"{label} must be a JSON object.")
    return payload


def _normalized_tags(raw_tags: list[object], key: str) -> tuple[str, ...]:
    tags: list[str] = []
    seen: set[str] = set()
    for raw_tag in raw_tags:
        if not isinstance(raw_tag, str):
            raise WorkItemStorageError(f'Work-item metadata "{key}" tags must be text.')
        tag = " ".join(raw_tag.strip().split()).casefold()
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tuple(tags)
