from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
import json
from pathlib import Path

from .contexts import ContextDefinition
from .persistence import atomic_write_json


class ContextDeletionError(Exception):
    """Raised when a context cannot be removed without corrupting configuration."""


@dataclass(frozen=True)
class ContextDeletionReport:
    action_memberships_removed: int = 0
    palette_references_removed: int = 0
    files_changed: int = 0


@dataclass(frozen=True)
class ContextRenameReport:
    action_references_updated: int = 0
    palette_references_updated: int = 0
    files_changed: int = 0


def rename_context_and_references(
    context_path: Path,
    original_name: str,
    replacement: ContextDefinition,
    *,
    action_paths: tuple[Path, ...],
    palette_path: Path,
) -> ContextRenameReport:
    """Rename a context without leaving saved references on its former name.

    For a materially different name, both definitions are written first. This
    intentionally safe intermediate state means an interrupted multi-file
    update can leave an unused alias, but never a reference to an undefined
    context.
    """

    original_key = original_name.strip().casefold()
    replacement_key = replacement.name.strip().casefold()
    context_data = _read_object(context_path)
    contexts = context_data.get("contexts")
    if not isinstance(contexts, list):
        raise ContextDeletionError(
            f"{context_path.name} must contain a 'contexts' list."
        )
    original_index = next(
        (
            index
            for index, context in enumerate(contexts)
            if isinstance(context, dict)
            and isinstance(context.get("name"), str)
            and context["name"].strip().casefold() == original_key
        ),
        -1,
    )
    if original_index < 0:
        raise ContextDeletionError(f"Context was not found: {original_name}")
    if any(
        index != original_index
        and isinstance(context, dict)
        and isinstance(context.get("name"), str)
        and context["name"].strip().casefold() == replacement_key
        for index, context in enumerate(contexts)
    ):
        raise ContextDeletionError(
            f"Another context already uses the name: {replacement.name}"
        )

    replacement_data = {
        key: value
        for key, value in asdict(replacement).items()
        if value not in ("", (), None)
    }
    if "preferred_action_ids" in replacement_data:
        replacement_data["preferred_action_ids"] = list(
            replacement.preferred_action_ids
        )
    if replacement.action_ids is not None:
        replacement_data["action_ids"] = list(replacement.action_ids)

    pending_writes: list[tuple[Path, dict[str, object]]] = []
    action_updates = 0
    for path in action_paths:
        data = _read_optional_object(path)
        if data is None:
            continue
        updated = _rename_action_references(
            data,
            original_key,
            replacement.name,
            path,
        )
        action_updates += updated
        if updated:
            pending_writes.append((path, data))

    palette_updates = 0
    palette_data = _read_optional_object(palette_path)
    if palette_data is not None:
        palette_updates = _rename_palette_references(
            palette_data,
            original_key,
            replacement.name,
        )
        if palette_updates:
            pending_writes.append((palette_path, palette_data))

    if original_key != replacement_key:
        staged_contexts = list(contexts)
        staged_contexts.insert(original_index + 1, replacement_data)
        staged_data = dict(context_data)
        staged_data["contexts"] = staged_contexts
        atomic_write_json(context_path, staged_data)

    for path, data in pending_writes:
        atomic_write_json(path, data)

    final_contexts = list(contexts)
    final_contexts[original_index] = replacement_data
    context_data["contexts"] = final_contexts
    atomic_write_json(
        context_path,
        context_data,
        preserve_previous=original_key == replacement_key,
    )
    return ContextRenameReport(
        action_references_updated=action_updates,
        palette_references_updated=palette_updates,
        files_changed=len(pending_writes) + 1,
    )


def delete_context_and_memberships(
    context_path: Path,
    context_name: str,
    *,
    action_paths: tuple[Path, ...],
    palette_path: Path,
) -> ContextDeletionReport:
    key = context_name.strip().casefold()
    context_data = _read_object(context_path)
    contexts = context_data.get("contexts")
    if not isinstance(contexts, list):
        raise ContextDeletionError(
            f"{context_path.name} must contain a 'contexts' list."
        )
    retained_contexts = [
        context
        for context in contexts
        if not (
            isinstance(context, dict)
            and isinstance(context.get("name"), str)
            and context["name"].strip().casefold() == key
        )
    ]
    if len(retained_contexts) == len(contexts):
        raise ContextDeletionError(f"Context was not found: {context_name}")

    pending_writes: list[tuple[Path, dict[str, object]]] = []
    memberships_removed = 0
    for path in action_paths:
        data = _read_optional_object(path)
        if data is None:
            continue
        removed = _remove_action_memberships(data, key, path)
        memberships_removed += removed
        if removed:
            pending_writes.append((path, data))

    palette_removed = 0
    palette_data = _read_optional_object(palette_path)
    if palette_data is not None:
        focus = palette_data.get("focus_context")
        if isinstance(focus, str) and focus.strip().casefold() == key:
            palette_data["focus_context"] = "General"
            palette_removed += 1
        slots = palette_data.get("context_slots")
        if isinstance(slots, dict):
            matching_names = [
                name
                for name in slots
                if isinstance(name, str) and name.strip().casefold() == key
            ]
            for name in matching_names:
                del slots[name]
                palette_removed += 1
        if palette_removed:
            pending_writes.append((palette_path, palette_data))

    # Remove usages first. If a later write fails, an unused definition is safer
    # than actions or palette state pointing at a missing context.
    for path, data in pending_writes:
        atomic_write_json(path, data)
    context_data["contexts"] = retained_contexts
    atomic_write_json(context_path, context_data)
    return ContextDeletionReport(
        action_memberships_removed=memberships_removed,
        palette_references_removed=palette_removed,
        files_changed=len(pending_writes) + 1,
    )


def _rename_action_references(
    data: dict[str, object],
    original_key: str,
    replacement_name: str,
    path: Path,
) -> int:
    actions = data.get("actions")
    if not isinstance(actions, list):
        raise ContextDeletionError(f"{path.name} must contain an 'actions' list.")
    updated = 0
    for action in actions:
        if not isinstance(action, dict):
            continue
        contexts = action.get("contexts")
        if isinstance(contexts, list):
            renamed: list[object] = []
            seen_names: set[str] = set()
            changed = False
            for name in contexts:
                value: object = name
                if isinstance(name, str) and name.strip().casefold() == original_key:
                    value = replacement_name
                    updated += 1
                    changed = True
                if isinstance(value, str):
                    key = value.strip().casefold()
                    if key in seen_names:
                        changed = True
                        continue
                    seen_names.add(key)
                renamed.append(value)
            if changed:
                action["contexts"] = renamed
        primary = action.get("context")
        if isinstance(primary, str) and primary.strip().casefold() == original_key:
            action["context"] = replacement_name
            updated += 1
    return updated


def _rename_palette_references(
    data: dict[str, object],
    original_key: str,
    replacement_name: str,
) -> int:
    updated = 0
    focus = data.get("focus_context")
    if isinstance(focus, str) and focus.strip().casefold() == original_key:
        data["focus_context"] = replacement_name
        updated += 1
    slots = data.get("context_slots")
    if not isinstance(slots, dict):
        return updated

    renamed_slots: dict[object, object] = {}
    changed = False
    for name, action_ids in slots.items():
        output_name: object = name
        if isinstance(name, str) and name.strip().casefold() == original_key:
            output_name = replacement_name
            updated += 1
            changed = True
        if output_name in renamed_slots:
            existing_ids = renamed_slots[output_name]
            if isinstance(existing_ids, list) and isinstance(action_ids, list):
                renamed_slots[output_name] = list(
                    dict.fromkeys((*existing_ids, *action_ids))
                )[:4]
            continue
        renamed_slots[output_name] = action_ids
    if changed:
        data["context_slots"] = renamed_slots
    return updated


def _remove_action_memberships(
    data: dict[str, object],
    context_key: str,
    path: Path,
) -> int:
    actions = data.get("actions")
    if not isinstance(actions, list):
        raise ContextDeletionError(f"{path.name} must contain an 'actions' list.")
    removed = 0
    for action in actions:
        if not isinstance(action, dict):
            continue
        remaining_contexts: list[object] | None = None
        removed_from_contexts = 0
        contexts = action.get("contexts")
        if isinstance(contexts, list):
            remaining_contexts = [
                name
                for name in contexts
                if not (
                    isinstance(name, str)
                    and name.strip().casefold() == context_key
                )
            ]
            removed_from_contexts = len(contexts) - len(remaining_contexts)
            removed += removed_from_contexts
            if len(remaining_contexts) != len(contexts):
                action["contexts"] = remaining_contexts
        primary = action.get("context")
        if isinstance(primary, str) and primary.strip().casefold() == context_key:
            action["context"] = (
                next(
                    (
                        name
                        for name in (remaining_contexts or [])
                        if isinstance(name, str) and name.strip()
                    ),
                    "General",
                )
            )
            if not isinstance(contexts, list) or not removed_from_contexts:
                removed += 1
    return removed


def _read_object(path: Path) -> dict[str, object]:
    data = _read_optional_object(path)
    if data is None:
        raise ContextDeletionError(f"Configuration file was not found: {path.name}")
    return data


def _read_optional_object(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContextDeletionError(f"{path.name} could not be read as valid JSON.") from exc
    if not isinstance(value, dict):
        raise ContextDeletionError(f"{path.name} must contain a JSON object.")
    return value
