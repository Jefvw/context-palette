from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable

from .actions import ActionError
from .command_surface import CommandSurfaceError, load_command_groups
from .configuration_mutation import configuration_mutation_gate
from .contexts import ContextError, load_contexts
from .palette_state import load_palette_state
from .persistence import atomic_replace_bytes, atomic_write_json
from .work_item_storage import (
    WorkItemStorageError,
    load_work_item_metadata,
    work_item_metadata_key,
)
from .work_items import WorkItemReference


class WorkItemOrganizationError(Exception):
    """Raised when personal organization cannot be inspected or forgotten safely."""

    def __init__(self, message: str, *, rollback_completed: bool = True) -> None:
        super().__init__(message)
        self.rollback_completed = rollback_completed


@dataclass(frozen=True, slots=True)
class WorkItemOrganizationReport:
    metadata_entries_removed: int = 0
    context_memberships_removed: int = 0
    preferred_references_removed: int = 0
    palette_references_removed: int = 0
    quick_action_references_removed: int = 0
    quick_action_items_removed: int = 0
    files_changed: int = 0

    @property
    def references_removed(self) -> int:
        """Return the number of saved placements, excluding metadata and items."""

        return (
            self.context_memberships_removed
            + self.preferred_references_removed
            + self.palette_references_removed
            + self.quick_action_references_removed
        )


@dataclass(frozen=True, slots=True)
class _LoadedFile:
    path: Path
    payload: dict[str, object]
    original_bytes: bytes


@dataclass(frozen=True, slots=True)
class _PreparedForget:
    report: WorkItemOrganizationReport
    writes: tuple[tuple[Path, dict[str, object]], ...]
    originals: dict[Path, bytes]


def inspect_work_item_organization(
    reference: WorkItemReference,
    *,
    metadata_path: Path,
    context_paths: tuple[Path, ...],
    palette_path: Path,
    command_surface_path: Path,
) -> WorkItemOrganizationReport:
    """Report personal saved organization that Forget would remove.

    Missing personal files and a Work Item with no saved organization are valid
    empty states. The external Work Item source, folder, workbook, and Inbox are
    deliberately outside this service's inputs and cannot be changed here.
    """

    with configuration_mutation_gate():
        prepared = _prepare_forget(
            reference,
            metadata_path=Path(metadata_path),
            context_paths=_unique_paths(context_paths),
            palette_path=Path(palette_path),
            command_surface_path=Path(command_surface_path),
        )
    return prepared.report


def forget_work_item_organization(
    reference: WorkItemReference,
    *,
    metadata_path: Path,
    context_paths: tuple[Path, ...],
    palette_path: Path,
    command_surface_path: Path,
) -> WorkItemOrganizationReport:
    """Remove one Work Item's personal palette organization transactionally.

    Every participating file is read and validated before the first mutation.
    Each changed file is then replaced atomically while the shared configuration
    gate remains held. A failed write restores all attempted files from their
    exact original bytes. Calling the operation again is therefore harmless.
    """

    with configuration_mutation_gate():
        prepared = _prepare_forget(
            reference,
            metadata_path=Path(metadata_path),
            context_paths=_unique_paths(context_paths),
            palette_path=Path(palette_path),
            command_surface_path=Path(command_surface_path),
        )
        if not prepared.writes:
            return prepared.report

        attempted: list[Path] = []
        try:
            for path, payload in prepared.writes:
                attempted.append(path)
                atomic_write_json(path, payload, preserve_previous=False)
        except Exception as exc:
            rollback_errors: list[str] = []
            for path in reversed(attempted):
                try:
                    atomic_replace_bytes(
                        path,
                        prepared.originals[path],
                        preserve_previous=False,
                    )
                except Exception as rollback_exc:
                    rollback_errors.append(f"{path.name}: {rollback_exc}")
            if rollback_errors:
                raise WorkItemOrganizationError(
                    "Work Item organization could not be forgotten and automatic "
                    "rollback was incomplete: " + "; ".join(rollback_errors),
                    rollback_completed=False,
                ) from exc
            raise WorkItemOrganizationError(
                "Work Item organization could not be forgotten; all attempted "
                "configuration changes were restored.",
                rollback_completed=True,
            ) from exc
        return prepared.report


def _prepare_forget(
    reference: WorkItemReference,
    *,
    metadata_path: Path,
    context_paths: tuple[Path, ...],
    palette_path: Path,
    command_surface_path: Path,
) -> _PreparedForget:
    metadata = _load_optional_file(
        metadata_path,
        "Work-item metadata",
        load_work_item_metadata,
    )
    contexts = tuple(
        loaded
        for path in context_paths
        if (
            loaded := _load_optional_file(
                path,
                "Context configuration",
                load_contexts,
            )
        )
        is not None
    )
    palette = _load_optional_file(
        palette_path,
        "Palette state",
        load_palette_state,
    )
    command_surface = _load_optional_file(
        command_surface_path,
        "Personal Quick actions",
        load_command_groups,
    )

    # All reads and schema validation above finish before any staged payload is
    # changed, and before the caller can start writing.
    originals: dict[Path, bytes] = {}
    writes: list[tuple[Path, dict[str, object]]] = []
    metadata_removed = 0
    memberships_removed = 0
    preferred_removed = 0
    palette_removed = 0
    quick_references_removed = 0
    quick_items_removed = 0

    for loaded in contexts:
        payload = deepcopy(loaded.payload)
        memberships, preferred = _remove_context_references(payload, reference)
        memberships_removed += memberships
        preferred_removed += preferred
        if memberships or preferred:
            _stage_write(loaded, payload, originals, writes)

    if palette is not None:
        payload = deepcopy(palette.payload)
        palette_removed = _remove_palette_references(payload, reference)
        if palette_removed:
            _stage_write(palette, payload, originals, writes)

    if command_surface is not None:
        payload = deepcopy(command_surface.payload)
        quick_references_removed, quick_items_removed = (
            _remove_command_surface_references(payload, reference)
        )
        if quick_references_removed or quick_items_removed:
            _stage_write(command_surface, payload, originals, writes)

    if metadata is not None:
        payload = deepcopy(metadata.payload)
        metadata_removed = _remove_metadata(payload, reference)
        if metadata_removed:
            _stage_write(metadata, payload, originals, writes)

    report = WorkItemOrganizationReport(
        metadata_entries_removed=metadata_removed,
        context_memberships_removed=memberships_removed,
        preferred_references_removed=preferred_removed,
        palette_references_removed=palette_removed,
        quick_action_references_removed=quick_references_removed,
        quick_action_items_removed=quick_items_removed,
        files_changed=len(writes),
    )
    return _PreparedForget(report, tuple(writes), originals)


def _load_optional_file(
    path: Path,
    label: str,
    validator: Callable[[Path], object],
) -> _LoadedFile | None:
    try:
        original = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise WorkItemOrganizationError(f"{label} could not be read: {path}") from exc
    try:
        decoded = original.decode("utf-8")
        payload = json.loads(decoded)
        if not isinstance(payload, dict):
            raise ValueError("root is not an object")
        validator(path)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        ContextError,
        ActionError,
        CommandSurfaceError,
        WorkItemStorageError,
        OSError,
    ) as exc:
        raise WorkItemOrganizationError(
            f"{label} must be valid before Work Item organization can be changed: "
            f"{path}"
        ) from exc
    return _LoadedFile(path, payload, original)


def _unique_paths(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    output: list[Path] = []
    seen: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path)
        if path not in seen:
            seen.add(path)
            output.append(path)
    return tuple(output)


def _stage_write(
    loaded: _LoadedFile,
    payload: dict[str, object],
    originals: dict[Path, bytes],
    writes: list[tuple[Path, dict[str, object]]],
) -> None:
    originals[loaded.path] = loaded.original_bytes
    writes.append((loaded.path, payload))


def _matches_plain_reference(value: object, reference: WorkItemReference) -> bool:
    return (
        isinstance(value, dict)
        and value.get("source_id") == reference.source_id
        and value.get("relative_folder") == reference.relative_folder
    )


def _matches_typed_reference(value: object, reference: WorkItemReference) -> bool:
    return (
        isinstance(value, dict)
        and value.get("type") == "work_item"
        and value.get("source_id") == reference.source_id
        and value.get("relative_folder") == reference.relative_folder
    )


def _remove_metadata(
    payload: dict[str, object],
    reference: WorkItemReference,
) -> int:
    work_items = payload.get("work_items")
    if not isinstance(work_items, dict):
        return 0
    key = work_item_metadata_key(reference.source_id, reference.relative_folder)
    if key not in work_items:
        return 0
    del work_items[key]
    return 1


def _remove_context_references(
    payload: dict[str, object],
    reference: WorkItemReference,
) -> tuple[int, int]:
    contexts = payload.get("contexts")
    if not isinstance(contexts, list):
        return 0, 0
    memberships_removed = 0
    preferred_removed = 0
    for context in contexts:
        if not isinstance(context, dict):
            continue
        memberships = context.get("work_item_refs")
        if isinstance(memberships, list):
            retained = [
                item
                for item in memberships
                if not _matches_plain_reference(item, reference)
            ]
            memberships_removed += len(memberships) - len(retained)
            if len(retained) != len(memberships):
                context["work_item_refs"] = retained
        preferred = context.get("preferred_items")
        if isinstance(preferred, list):
            retained = [
                item
                for item in preferred
                if not _matches_typed_reference(item, reference)
            ]
            preferred_removed += len(preferred) - len(retained)
            if len(retained) != len(preferred):
                context["preferred_items"] = retained
    return memberships_removed, preferred_removed


def _remove_palette_references(
    payload: dict[str, object],
    reference: WorkItemReference,
) -> int:
    slots = payload.get("context_item_slots")
    if not isinstance(slots, dict):
        return 0
    removed = 0
    for context_name, values in tuple(slots.items()):
        if not isinstance(values, list):
            continue
        retained = [
            value
            for value in values
            if not _matches_typed_reference(value, reference)
        ]
        removed += len(values) - len(retained)
        if len(retained) != len(values):
            slots[context_name] = retained
    return removed


def _remove_command_surface_references(
    payload: dict[str, object],
    reference: WorkItemReference,
) -> tuple[int, int]:
    groups = payload.get("groups")
    if not isinstance(groups, list):
        return 0, 0
    references_removed = 0
    items_removed = 0
    for group in groups:
        if not isinstance(group, dict):
            continue
        items = group.get("items")
        if not isinstance(items, list):
            continue
        retained, removed_refs, removed_items, _changed = _clean_command_items(
            items,
            reference,
        )
        references_removed += removed_refs
        items_removed += removed_items
        if removed_refs or removed_items:
            # Keep the configured root group even when Forget empties it.
            group["items"] = retained
    return references_removed, items_removed


def _clean_command_items(
    items: list[object],
    reference: WorkItemReference,
) -> tuple[list[object], int, int, bool]:
    output: list[object] = []
    references_removed = 0
    items_removed = 0
    any_changed = False
    for raw_item in items:
        if not isinstance(raw_item, dict):
            output.append(raw_item)
            continue
        item = deepcopy(raw_item)
        child_values = item.get("items")
        child_changed = False
        if isinstance(child_values, list):
            (
                retained_children,
                child_references_removed,
                child_items_removed,
                child_changed,
            ) = _clean_command_items(child_values, reference)
            references_removed += child_references_removed
            items_removed += child_items_removed
            if child_changed:
                item["items"] = retained_children

        own_removed = 0
        legacy_reference = item.get("work_item_ref")
        if _matches_plain_reference(legacy_reference, reference):
            del item["work_item_ref"]
            own_removed += 1
        targets = item.get("targets")
        if isinstance(targets, list):
            retained_targets = [
                target
                for target in targets
                if not _matches_typed_reference(target, reference)
            ]
            own_removed += len(targets) - len(retained_targets)
            if len(retained_targets) != len(targets):
                item["targets"] = retained_targets

        references_removed += own_removed
        changed = bool(own_removed or child_changed)
        if changed and not _command_item_has_content(item):
            items_removed += 1
            any_changed = True
            continue
        output.append(item if changed else raw_item)
        any_changed = any_changed or changed
    return output, references_removed, items_removed, any_changed


def _command_item_has_content(item: dict[str, object]) -> bool:
    children = item.get("items")
    if isinstance(children, list) and children:
        return True
    primary = item.get("primary_action_id")
    if isinstance(primary, str) and primary.strip():
        return True
    action_ids = item.get("action_ids")
    if isinstance(action_ids, list) and any(
        isinstance(value, str) and value.strip() for value in action_ids
    ):
        return True
    if isinstance(item.get("work_item_ref"), dict):
        return True
    targets = item.get("targets")
    return isinstance(targets, list) and bool(targets)
