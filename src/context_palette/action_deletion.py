from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import json
from pathlib import Path

from .configuration_mutation import configuration_mutation_gate
from .persistence import atomic_write_json


class ActionDeletionError(Exception):
    """Raised when an action lifecycle mutation cannot complete safely."""


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
    sequence_paths: tuple[Path, ...] = (),
) -> ActionDeletionReport:
    with configuration_mutation_gate():
        _assert_no_sequence_dependencies(
            action_id,
            sequence_paths,
            include_archived=True,
        )
        return _delete_action_and_references(
            action_path,
            action_id,
            context_paths=context_paths,
            command_surface_paths=command_surface_paths,
            palette_path=palette_path,
        )


def archive_action_and_references(
    action_path: Path,
    action_id: str,
    *,
    context_paths: tuple[Path, ...],
    command_surface_paths: tuple[Path, ...],
    palette_path: Path,
    sequence_paths: tuple[Path, ...] = (),
) -> ActionDeletionReport:
    """Archive an action after detaching every active-only saved reference."""

    with configuration_mutation_gate():
        _assert_no_sequence_dependencies(
            action_id,
            sequence_paths,
            include_archived=False,
        )
        action_data = _read_object(action_path)
        action = _find_action_record(action_data, action_path, action_id)
        if action.get("state", "Active") == "Archived":
            raise ActionDeletionError(f"Action is already archived: {action_id}")

        pending_writes, references_removed, buttons_removed = (
            _prepare_reference_removals(
                action_id,
                context_paths=context_paths,
                command_surface_paths=command_surface_paths,
                palette_path=palette_path,
            )
        )
        # References must disappear before the state changes. If the final write
        # fails, an unassigned Active action remains a valid, recoverable state.
        try:
            for path, data in pending_writes:
                atomic_write_json(path, data)
            action["state"] = "Archived"
            atomic_write_json(action_path, action_data)
        except OSError as exc:
            raise ActionDeletionError(
                "The Action was not archived and remains Active, but some saved "
                "placements may already have been removed. Reload Context Palette "
                "before trying again."
            ) from exc
        return ActionDeletionReport(
            references_removed,
            buttons_removed,
            len(pending_writes) + 1,
        )


def restore_action(action_path: Path, action_id: str) -> None:
    """Restore an Archived action without recreating its former assignments."""

    with configuration_mutation_gate():
        action_data = _read_object(action_path)
        action = _find_action_record(action_data, action_path, action_id)
        if action.get("state", "Active") != "Archived":
            raise ActionDeletionError(f"Action is not archived: {action_id}")
        action["state"] = "Active"
        atomic_write_json(action_path, action_data)


def _delete_action_and_references(
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

    pending_writes, references_removed, buttons_removed = _prepare_reference_removals(
        action_id,
        context_paths=context_paths,
        command_surface_paths=command_surface_paths,
        palette_path=palette_path,
    )

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


def _find_action_record(
    action_data: dict[str, object],
    action_path: Path,
    action_id: str,
) -> dict[str, object]:
    actions = action_data.get("actions")
    if not isinstance(actions, list):
        raise ActionDeletionError(f"{action_path.name} must contain an 'actions' list.")
    for action in actions:
        if isinstance(action, dict) and action.get("id") == action_id:
            return action
    raise ActionDeletionError(f"Action was not found: {action_id}")


def _assert_no_sequence_dependencies(
    action_id: str,
    paths: tuple[Path, ...],
    *,
    include_archived: bool,
) -> None:
    key = action_id.casefold()
    dependents: list[str] = []
    for path in paths:
        data = _read_optional_object(path)
        if data is None:
            continue
        actions = data.get("actions")
        if not isinstance(actions, list):
            raise ActionDeletionError(f"{path.name} must contain an 'actions' list.")
        for action in actions:
            if not isinstance(action, dict) or action.get("type") != "sequence":
                continue
            owner_id = action.get("id")
            if not isinstance(owner_id, str) or owner_id.casefold() == key:
                continue
            if not include_archived and action.get("state", "Active") == "Archived":
                continue
            steps = action.get("steps")
            if not isinstance(steps, list):
                continue
            if any(
                isinstance(step, dict)
                and isinstance(step.get("action_id"), str)
                and step["action_id"].casefold() == key
                for step in steps
            ):
                title = action.get("title")
                dependents.append(title if isinstance(title, str) else owner_id)
    if dependents:
        raise ActionDeletionError(
            "The Action is used by these sequences: "
            + ", ".join(dependents)
            + ". Edit or archive/delete those sequences first."
        )


def _prepare_reference_removals(
    action_id: str,
    *,
    context_paths: tuple[Path, ...],
    command_surface_paths: tuple[Path, ...],
    palette_path: Path,
) -> tuple[list[tuple[Path, dict[str, object]]], int, int]:
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

    return pending_writes, references_removed, buttons_removed


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
        preferred_items = context.get("preferred_items")
        if isinstance(preferred_items, list):
            retained_items = [
                value
                for value in preferred_items
                if not (
                    isinstance(value, dict)
                    and value.get("type") == "action"
                    and value.get("action_id") == action_id
                )
            ]
            removed += len(preferred_items) - len(retained_items)
            context["preferred_items"] = retained_items
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
            or group.get("targets")
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
    targets = node.get("targets")
    if isinstance(targets, list):
        retained_targets = [
            target
            for target in targets
            if not (
                isinstance(target, dict)
                and target.get("type") == "action"
                and target.get("action_id") == action_id
            )
        ]
        removed_references += len(targets) - len(retained_targets)
        node["targets"] = retained_targets
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
            or child.get("work_item_ref")
            or child.get("targets")
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
    item_slots = data.get("context_item_slots")
    if isinstance(item_slots, dict):
        for context, references in item_slots.items():
            if not isinstance(references, list):
                continue
            retained_references = [
                reference
                for reference in references
                if not (
                    isinstance(reference, dict)
                    and reference.get("type") == "action"
                    and reference.get("action_id") == action_id
                )
            ]
            removed += len(references) - len(retained_references)
            item_slots[context] = retained_references
    return removed
