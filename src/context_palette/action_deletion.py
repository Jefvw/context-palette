from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import json
from pathlib import Path

from .persistence import atomic_write_json


class ActionDeletionError(Exception):
    """Raised when an action and its references cannot be removed safely."""


@dataclass(frozen=True)
class ActionDeletionReport:
    references_removed: int = 0
    buttons_removed: int = 0
    files_changed: int = 0


def inspect_action_references(
    action_id: str,
    *,
    context_paths: tuple[Path, ...],
    command_surface_paths: tuple[Path, ...],
    palette_path: Path,
) -> ActionDeletionReport:
    references = 0
    buttons = 0
    files = 0
    for path in context_paths:
        data = _read_optional_object(path)
        if data is None:
            continue
        removed = _remove_context_references(deepcopy(data), action_id, path)
        references += removed
        files += bool(removed)
    for path in command_surface_paths:
        data = _read_optional_object(path)
        if data is None:
            continue
        removed, removed_buttons = _remove_command_references(
            deepcopy(data), action_id, path
        )
        references += removed
        buttons += removed_buttons
        files += bool(removed or removed_buttons)
    palette_data = _read_optional_object(palette_path)
    if palette_data is not None:
        removed = _remove_palette_references(deepcopy(palette_data), action_id)
        references += removed
        files += bool(removed)
    return ActionDeletionReport(references, buttons, files)


def delete_action_and_references(
    action_path: Path,
    action_id: str,
    *,
    context_paths: tuple[Path, ...],
    command_surface_paths: tuple[Path, ...],
    palette_path: Path,
) -> ActionDeletionReport:
    action_data = _read_object(action_path)
    actions = action_data.get("actions")
    if not isinstance(actions, list):
        raise ActionDeletionError(f"{action_path.name} must contain an 'actions' list.")
    retained_actions = [
        item
        for item in actions
        if not (isinstance(item, dict) and item.get("id") == action_id)
    ]
    if len(retained_actions) == len(actions):
        raise ActionDeletionError(f"Action was not found: {action_id}")

    pending_writes: list[tuple[Path, dict[str, object]]] = []
    references_removed = 0
    buttons_removed = 0
    for path in context_paths:
        data = _read_optional_object(path)
        if data is None:
            continue
        removed = _remove_context_references(data, action_id, path)
        references_removed += removed
        if removed:
            pending_writes.append((path, data))

    for path in command_surface_paths:
        data = _read_optional_object(path)
        if data is None:
            continue
        removed, removed_buttons = _remove_command_references(data, action_id, path)
        references_removed += removed
        buttons_removed += removed_buttons
        if removed or removed_buttons:
            pending_writes.append((path, data))

    palette_data = _read_optional_object(palette_path)
    if palette_data is not None:
        removed = _remove_palette_references(palette_data, action_id)
        references_removed += removed
        if removed:
            pending_writes.append((palette_path, palette_data))

    # Remove references first. If a later write fails, an unused action is safer
    # than configuration that points at an action that no longer exists.
    for path, data in pending_writes:
        atomic_write_json(path, data)
    action_data["actions"] = retained_actions
    atomic_write_json(action_path, action_data)
    return ActionDeletionReport(
        references_removed,
        buttons_removed,
        len(pending_writes) + 1,
    )


def _read_object(path: Path) -> dict[str, object]:
    data = _read_optional_object(path)
    if data is None:
        raise ActionDeletionError(f"Configuration file was not found: {path.name}")
    return data


def _read_optional_object(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ActionDeletionError(f"{path.name} could not be read as valid JSON.") from exc
    if not isinstance(value, dict):
        raise ActionDeletionError(f"{path.name} must contain a JSON object.")
    return value


def _remove_context_references(
    data: dict[str, object],
    action_id: str,
    path: Path,
) -> int:
    contexts = data.get("contexts")
    if not isinstance(contexts, list):
        raise ActionDeletionError(f"{path.name} must contain a 'contexts' list.")
    removed = 0
    for context in contexts:
        if not isinstance(context, dict):
            continue
        for field in ("preferred_action_ids", "action_ids"):
            references = context.get(field)
            if not isinstance(references, list):
                continue
            retained = [value for value in references if value != action_id]
            removed += len(references) - len(retained)
            context[field] = retained
    return removed


def _remove_command_references(
    data: dict[str, object],
    action_id: str,
    path: Path,
) -> tuple[int, int]:
    groups = data.get("groups")
    if not isinstance(groups, list):
        raise ActionDeletionError(f"{path.name} must contain a 'groups' list.")
    removed_references = 0
    removed_buttons = 0
    retained_groups: list[object] = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("items"), list):
            retained_groups.append(group)
            continue
        group_removed, group_buttons_removed = _clean_command_node(
            group,
            action_id,
        )
        removed_references += group_removed
        removed_buttons += group_buttons_removed
        if (
            group.get("primary_action_id")
            or group.get("action_ids")
            or group.get("items")
        ):
            retained_groups.append(group)
    data["groups"] = retained_groups
    return removed_references, removed_buttons


def _clean_command_node(
    node: dict[str, object],
    action_id: str,
) -> tuple[int, int]:
    removed_references = 0
    removed_items = 0
    action_ids = node.get("action_ids")
    if isinstance(action_ids, list):
        retained_ids = [value for value in action_ids if value != action_id]
        removed_references += len(action_ids) - len(retained_ids)
        node["action_ids"] = retained_ids
    if node.get("primary_action_id") == action_id:
        removed_references += 1
        node["primary_action_id"] = (
            node["action_ids"][0]
            if isinstance(node.get("action_ids"), list) and node["action_ids"]
            else ""
        )
    child_items = node.get("items")
    if not isinstance(child_items, list):
        return removed_references, removed_items
    retained_children: list[object] = []
    for child in child_items:
        if not isinstance(child, dict):
            retained_children.append(child)
            continue
        child_removed, descendants_removed = _clean_command_node(
            child,
            action_id,
        )
        removed_references += child_removed
        removed_items += descendants_removed
        if (
            child.get("primary_action_id")
            or child.get("action_ids")
            or child.get("items")
        ):
            retained_children.append(child)
        else:
            removed_items += 1
    node["items"] = retained_children
    return removed_references, removed_items


def _remove_palette_references(data: dict[str, object], action_id: str) -> int:
    removed = 0
    pinned = data.get("pinned_action_ids")
    if isinstance(pinned, list):
        retained = [value for value in pinned if value != action_id]
        removed += len(pinned) - len(retained)
        data["pinned_action_ids"] = retained
    slots = data.get("context_slots")
    if isinstance(slots, dict):
        for context, action_ids in slots.items():
            if not isinstance(action_ids, list):
                continue
            retained = [value for value in action_ids if value != action_id]
            removed += len(action_ids) - len(retained)
            slots[context] = retained
    return removed
