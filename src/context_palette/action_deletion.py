from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import json
from pathlib import Path
from typing import Iterable

from .configuration_mutation import configuration_mutation_gate
from .persistence import atomic_replace_bytes, atomic_write_json


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
    return inspect_action_references_many(
        (action_id,),
        context_paths=context_paths,
        command_surface_paths=command_surface_paths,
        palette_path=palette_path,
    )


def inspect_action_references_many(
    action_ids: Iterable[str],
    *,
    context_paths: tuple[Path, ...],
    command_surface_paths: tuple[Path, ...],
    palette_path: Path,
) -> ActionDeletionReport:
    """Inventory the exact combined saved-placement effect for several Actions."""

    selected_ids = _validated_action_ids(action_ids, allow_empty=True)
    if not selected_ids:
        return ActionDeletionReport()
    references = 0
    buttons = 0
    files = 0
    for path in context_paths:
        data = _read_optional_object(path)
        if data is None:
            continue
        changed = deepcopy(data)
        removed = sum(
            _remove_context_references(changed, action_id, path)
            for action_id in selected_ids
        )
        references += removed
        files += bool(removed)
    for path in command_surface_paths:
        data = _read_optional_object(path)
        if data is None:
            continue
        changed = deepcopy(data)
        removed, removed_buttons = _remove_command_references_many(
            changed,
            selected_ids,
            path,
        )
        references += removed
        buttons += removed_buttons
        files += bool(removed or removed_buttons)
    palette_data = _read_optional_object(palette_path)
    if palette_data is not None:
        changed = deepcopy(palette_data)
        removed = sum(
            _remove_palette_references(changed, action_id)
            for action_id in selected_ids
        )
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
    return delete_actions_and_references(
        action_path,
        (action_id,),
        context_paths=context_paths,
        command_surface_paths=command_surface_paths,
        palette_path=palette_path,
        sequence_paths=sequence_paths,
    )


def delete_actions_and_references(
    action_path: Path,
    action_ids: Iterable[str],
    *,
    context_paths: tuple[Path, ...],
    command_surface_paths: tuple[Path, ...],
    palette_path: Path,
    sequence_paths: tuple[Path, ...] = (),
    expected_report: ActionDeletionReport | None = None,
) -> ActionDeletionReport:
    """Permanently delete one reviewed Archived batch in one transaction."""

    selected_ids = _validated_action_ids(action_ids)
    with configuration_mutation_gate():
        _assert_no_sequence_dependencies_many(
            selected_ids,
            sequence_paths,
            include_archived=True,
        )
        return _delete_actions_and_references(
            action_path,
            selected_ids,
            context_paths=context_paths,
            command_surface_paths=command_surface_paths,
            palette_path=palette_path,
            expected_report=expected_report,
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

    return archive_actions_and_references(
        action_path,
        (action_id,),
        context_paths=context_paths,
        command_surface_paths=command_surface_paths,
        palette_path=palette_path,
        sequence_paths=sequence_paths,
    )


def archive_actions_and_references(
    action_path: Path,
    action_ids: Iterable[str],
    *,
    context_paths: tuple[Path, ...],
    command_surface_paths: tuple[Path, ...],
    palette_path: Path,
    sequence_paths: tuple[Path, ...] = (),
    expected_report: ActionDeletionReport | None = None,
) -> ActionDeletionReport:
    """Archive one reviewed Active batch and detach its saved placements."""

    selected_ids = _validated_action_ids(action_ids)
    with configuration_mutation_gate():
        _assert_no_sequence_dependencies_many(
            selected_ids,
            sequence_paths,
            include_archived=False,
        )
        action_data = _read_object(action_path)
        actions = _find_action_records(action_data, action_path, selected_ids)
        already_archived = [
            action_id
            for action_id, action in zip(selected_ids, actions, strict=True)
            if action.get("state", "Active") == "Archived"
        ]
        if already_archived:
            raise ActionDeletionError(
                "Actions are already archived: " + ", ".join(already_archived)
            )

        pending_writes, references_removed, buttons_removed = (
            _prepare_reference_removals_many(
                selected_ids,
                context_paths=context_paths,
                command_surface_paths=command_surface_paths,
                palette_path=palette_path,
            )
        )
        report = ActionDeletionReport(
            references_removed,
            buttons_removed,
            len(pending_writes) + 1,
        )
        _assert_expected_report(expected_report, report)
        for action in actions:
            action["state"] = "Archived"
        _write_json_transaction(
            (*pending_writes, (action_path, action_data)),
            operation="The Action archive",
        )
        return report


def restore_action(action_path: Path, action_id: str) -> None:
    """Restore an Archived action without recreating its former assignments."""

    with configuration_mutation_gate():
        action_data = _read_object(action_path)
        action = _find_action_record(action_data, action_path, action_id)
        if action.get("state", "Active") != "Archived":
            raise ActionDeletionError(f"Action is not archived: {action_id}")
        action["state"] = "Active"
        atomic_write_json(action_path, action_data)


def _delete_actions_and_references(
    action_path: Path,
    action_ids: tuple[str, ...],
    *,
    context_paths: tuple[Path, ...],
    command_surface_paths: tuple[Path, ...],
    palette_path: Path,
    expected_report: ActionDeletionReport | None,
) -> ActionDeletionReport:
    action_data = _read_object(action_path)
    actions = action_data.get("actions")
    if not isinstance(actions, list):
        raise ActionDeletionError(f"{action_path.name} must contain an 'actions' list.")
    selected_actions = _find_action_records(action_data, action_path, action_ids)
    active_ids = [
        action_id
        for action_id, action in zip(action_ids, selected_actions, strict=True)
        if action.get("state", "Active") != "Archived"
    ]
    if active_ids:
        raise ActionDeletionError(
            "Actions must be Archived before permanent deletion: "
            + ", ".join(active_ids)
        )
    selected_keys = {action_id.casefold() for action_id in action_ids}
    retained_actions = [
        item
        for item in actions
        if not (
            isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and item["id"].casefold() in selected_keys
        )
    ]

    pending_writes, references_removed, buttons_removed = _prepare_reference_removals_many(
        action_ids,
        context_paths=context_paths,
        command_surface_paths=command_surface_paths,
        palette_path=palette_path,
    )
    report = ActionDeletionReport(
        references_removed,
        buttons_removed,
        len(pending_writes) + 1,
    )
    _assert_expected_report(expected_report, report)

    action_data["actions"] = retained_actions
    _write_json_transaction(
        (*pending_writes, (action_path, action_data)),
        operation="The permanent Action deletion",
    )
    return report


def _assert_expected_report(
    expected: ActionDeletionReport | None,
    actual: ActionDeletionReport,
) -> None:
    if expected is not None and actual != expected:
        raise ActionDeletionError(
            "The current saved-placement effect does not match the reviewed "
            "lifecycle impact. Review the Actions again; no configuration "
            "changes were made."
        )


def _find_action_record(
    action_data: dict[str, object],
    action_path: Path,
    action_id: str,
) -> dict[str, object]:
    return _find_action_records(action_data, action_path, (action_id,))[0]


def _find_action_records(
    action_data: dict[str, object],
    action_path: Path,
    action_ids: tuple[str, ...],
) -> tuple[dict[str, object], ...]:
    actions = action_data.get("actions")
    if not isinstance(actions, list):
        raise ActionDeletionError(f"{action_path.name} must contain an 'actions' list.")
    records_by_key = {
        action["id"].casefold(): action
        for action in actions
        if isinstance(action, dict) and isinstance(action.get("id"), str)
    }
    found: list[dict[str, object]] = []
    missing: list[str] = []
    for action_id in action_ids:
        action = records_by_key.get(action_id.casefold())
        if action is None:
            missing.append(action_id)
        else:
            found.append(action)
    if missing:
        label = "Action was" if len(missing) == 1 else "Actions were"
        raise ActionDeletionError(f"{label} not found: {', '.join(missing)}")
    return tuple(found)


def _validated_action_ids(
    action_ids: Iterable[str],
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    selected: list[str] = []
    seen: set[str] = set()
    for action_id in action_ids:
        if not isinstance(action_id, str) or not action_id.strip():
            raise ActionDeletionError("Action IDs must be non-empty text.")
        key = action_id.casefold()
        if key in seen:
            raise ActionDeletionError(
                f"Action was selected more than once: {action_id}"
            )
        seen.add(key)
        selected.append(action_id)
    if not selected and not allow_empty:
        raise ActionDeletionError("Select at least one Action.")
    return tuple(selected)


def _assert_no_sequence_dependencies_many(
    action_ids: tuple[str, ...],
    paths: tuple[Path, ...],
    *,
    include_archived: bool,
) -> None:
    selected_keys = {action_id.casefold() for action_id in action_ids}
    dependents: list[str] = []
    seen_dependents: set[str] = set()
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
            if not isinstance(owner_id, str):
                continue
            owner_key = owner_id.casefold()
            if owner_key in selected_keys:
                continue
            if not include_archived and action.get("state", "Active") == "Archived":
                continue
            steps = action.get("steps")
            if not isinstance(steps, list):
                continue
            if not any(
                isinstance(step, dict)
                and isinstance(step.get("action_id"), str)
                and step["action_id"].casefold() in selected_keys
                for step in steps
            ):
                continue
            title = action.get("title")
            label = title if isinstance(title, str) else owner_id
            if owner_key not in seen_dependents:
                seen_dependents.add(owner_key)
                dependents.append(label)
    if dependents:
        raise ActionDeletionError(
            "The Actions are used by these sequences: "
            + ", ".join(dependents)
            + ". Select those sequences too, or edit/archive/delete them first."
        )


def _assert_no_sequence_dependencies(
    action_id: str,
    paths: tuple[Path, ...],
    *,
    include_archived: bool,
) -> None:
    _assert_no_sequence_dependencies_many(
        (action_id,),
        paths,
        include_archived=include_archived,
    )


def _prepare_reference_removals(
    action_id: str,
    *,
    context_paths: tuple[Path, ...],
    command_surface_paths: tuple[Path, ...],
    palette_path: Path,
) -> tuple[list[tuple[Path, dict[str, object]]], int, int]:
    return _prepare_reference_removals_many(
        (action_id,),
        context_paths=context_paths,
        command_surface_paths=command_surface_paths,
        palette_path=palette_path,
    )


def _prepare_reference_removals_many(
    action_ids: tuple[str, ...],
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
        removed = sum(
            _remove_context_references(data, action_id, path)
            for action_id in action_ids
        )
        references_removed += removed
        if removed:
            pending_writes.append((path, data))

    for path in command_surface_paths:
        data = _read_optional_object(path)
        if data is None:
            continue
        removed, removed_buttons = _remove_command_references_many(
            data,
            action_ids,
            path,
        )
        references_removed += removed
        buttons_removed += removed_buttons
        if removed or removed_buttons:
            pending_writes.append((path, data))

    palette_data = _read_optional_object(palette_path)
    if palette_data is not None:
        removed = sum(
            _remove_palette_references(palette_data, action_id)
            for action_id in action_ids
        )
        references_removed += removed
        if removed:
            pending_writes.append((palette_path, palette_data))

    return pending_writes, references_removed, buttons_removed


def _write_json_transaction(
    writes: tuple[tuple[Path, dict[str, object]], ...],
    *,
    operation: str,
) -> None:
    """Best-effort all-or-nothing commit across several configuration files."""

    primary_paths: list[Path] = []
    for path, _data in writes:
        if path in primary_paths:
            raise ActionDeletionError(
                f"{operation} tried to update {path.name} more than once."
            )
        primary_paths.append(path)

    participating = tuple(
        dict.fromkeys(
            participant
            for path in primary_paths
            for participant in (path, path.with_name(path.name + ".bak"))
        )
    )
    originals: dict[Path, bytes | None] = {}
    for path in participating:
        try:
            originals[path] = path.read_bytes() if path.exists() else None
        except OSError as exc:
            raise ActionDeletionError(
                f"{operation} could not snapshot {path.name} before writing."
            ) from exc

    attempted: list[Path] = []
    try:
        for path, data in writes:
            attempted.append(path)
            atomic_write_json(path, data)
    except OSError as exc:
        rollback_errors: list[str] = []
        for path in reversed(attempted):
            for participant in (
                path,
                path.with_name(path.name + ".bak"),
            ):
                try:
                    payload = originals[participant]
                    if payload is None:
                        participant.unlink(missing_ok=True)
                    else:
                        atomic_replace_bytes(
                            participant,
                            payload,
                            preserve_previous=False,
                        )
                except OSError as rollback_exc:
                    rollback_errors.append(
                        f"{participant.name}: {rollback_exc}"
                    )
        if rollback_errors:
            raise ActionDeletionError(
                f"{operation} failed and automatic rollback was incomplete. "
                "Reload Context Palette and recover from backup if needed. "
                + "; ".join(rollback_errors)
            ) from exc
        raise ActionDeletionError(
            f"{operation} could not be completed; all attempted configuration "
            "changes were restored."
        ) from exc


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
    return _remove_command_references_many(data, (action_id,), path)


def _remove_command_references_many(
    data: dict[str, object],
    action_ids: tuple[str, ...],
    path: Path,
) -> tuple[int, int]:
    groups = data.get("groups")
    if not isinstance(groups, list):
        raise ActionDeletionError(f"{path.name} must contain a 'groups' list.")
    selected_ids = frozenset(action_ids)
    removed_references = 0
    removed_buttons = 0
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("items"), list):
            continue
        group_removed, group_buttons_removed = _clean_command_node_many(
            group,
            selected_ids,
        )
        removed_references += group_removed
        removed_buttons += group_buttons_removed
    return removed_references, removed_buttons


def _clean_command_node(
    node: dict[str, object],
    action_id: str,
) -> tuple[int, int]:
    return _clean_command_node_many(node, frozenset({action_id}))


def _clean_command_node_many(
    node: dict[str, object],
    selected_action_ids: frozenset[str],
) -> tuple[int, int]:
    removed_references = 0
    removed_items = 0
    node_action_ids = node.get("action_ids")
    if isinstance(node_action_ids, list):
        retained_ids = [
            value for value in node_action_ids if value not in selected_action_ids
        ]
        removed_references += len(node_action_ids) - len(retained_ids)
        node["action_ids"] = retained_ids
    if node.get("primary_action_id") in selected_action_ids:
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
                and target.get("action_id") in selected_action_ids
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
        child_removed, descendants_removed = _clean_command_node_many(
            child,
            selected_action_ids,
        )
        removed_references += child_removed
        removed_items += descendants_removed
        has_content = bool(
            child.get("primary_action_id")
            or child.get("action_ids")
            or child.get("work_item_ref")
            or child.get("targets")
            or child.get("items")
        )
        changed_by_cleanup = bool(child_removed or descendants_removed)
        if has_content or not changed_by_cleanup:
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
