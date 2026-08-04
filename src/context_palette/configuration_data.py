from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path

from .command_surface import (
    CommandGroup,
    CommandItem,
    CommandSurfaceError,
    GROUP_PRESENTATIONS,
    GROUP_PRESENTATION_NESTED_MENU,
    GROUP_PRESENTATION_ROWS,
    MAX_COMMAND_MENU_LEVELS,
    command_group_action_ids,
    command_item_action_ids,
    command_item_targets,
    iter_command_items,
    load_command_groups,
)
from .contexts import ContextDefinition, ContextError, load_contexts
from .persistence import atomic_write_json


def _context_to_data(context: ContextDefinition) -> dict[str, object]:
    data = {
        key: value
        for key, value in asdict(context).items()
        if value not in ("", (), None)
    }
    if context.preferred_action_ids:
        data["preferred_action_ids"] = list(context.preferred_action_ids)
    if context.action_ids is not None:
        data["action_ids"] = list(context.action_ids)
    return data


def save_context(
    path: Path,
    context: ContextDefinition,
    *,
    original_name: str = "",
) -> None:
    contexts = load_contexts(path) if path.exists() else []
    replacement_key = (original_name or context.name).casefold()
    other_names = {
        item.name.casefold() for item in contexts if item.name.casefold() != replacement_key
    }
    if context.name.casefold() in other_names:
        raise ContextError(f"Duplicate configured context: {context.name}")
    updated = [item for item in contexts if item.name.casefold() != replacement_key]
    updated.append(context)
    updated.sort(key=lambda item: item.name.casefold())
    save_contexts(path, updated)


def save_contexts(
    path: Path,
    contexts: list[ContextDefinition],
) -> None:
    names: set[str] = set()
    for context in contexts:
        key = context.name.casefold()
        if key in names:
            raise ContextError(f"Duplicate configured context: {context.name}")
        names.add(key)
    atomic_write_json(
        path,
        {"contexts": [_context_to_data(item) for item in contexts]},
    )


def save_command_item(
    path: Path,
    *,
    group_id: str,
    group_label: str,
    item: CommandItem,
    original_group_id: str = "",
    original_item_id: str = "",
    parent_item_ids: tuple[str, ...] = (),
) -> None:
    clean_group_id = group_id.strip()
    clean_group_label = group_label.strip()
    if not clean_group_id or not clean_group_label:
        raise CommandSurfaceError("A button group needs an ID and visible name.")
    if not item.id.strip() or not item.label.strip():
        raise CommandSurfaceError("A button needs an ID and visible label.")

    groups = load_command_groups(path) if path.exists() else []
    target_group_key = (original_group_id or clean_group_id).casefold()
    if any(
        group.id.casefold() == clean_group_id.casefold()
        and group.id.casefold() != target_group_key
        for group in groups
    ):
        raise CommandSurfaceError(f"Duplicate command-surface group ID: {clean_group_id}")
    output: list[CommandGroup] = []
    matched_group = False
    for group in groups:
        if group.id.casefold() != target_group_key:
            output.append(group)
            continue
        matched_group = True
        replacement_item_key = (original_item_id or item.id).casefold()
        if any(
            existing.id.casefold() == item.id.casefold()
            and existing.id.casefold() != replacement_item_key
            for _item_path, existing in iter_command_items(group)
        ):
            raise CommandSurfaceError(f"Duplicate button ID in this group: {item.id}")
        if original_item_id:
            items, replaced = _replace_command_item(
                group.items,
                replacement_item_key,
                item,
            )
            if not replaced:
                raise CommandSurfaceError(
                    f"Quick action was not found in {group.id}: "
                    f"{original_item_id}"
                )
        else:
            items = _append_command_item(
                group.items,
                parent_item_ids,
                item,
            )
        output.append(
            replace(
                group,
                id=clean_group_id,
                label=clean_group_label,
                items=items,
            )
        )
    if not matched_group:
        if any(group.id.casefold() == clean_group_id.casefold() for group in output):
            raise CommandSurfaceError(f"Duplicate command-surface group ID: {clean_group_id}")
        if parent_item_ids:
            raise CommandSurfaceError(
                "A submenu parent cannot be selected in a new group."
            )
        output.append(CommandGroup(clean_group_id, clean_group_label, (item,)))

    save_command_groups(path, output)


def save_command_group(
    path: Path,
    group: CommandGroup,
    *,
    original_group_id: str = "",
) -> None:
    _validate_group(group)
    groups = load_command_groups(path) if path.exists() else []
    replacement_key = (original_group_id or group.id).casefold()
    if any(
        existing.id.casefold() == group.id.casefold()
        and existing.id.casefold() != replacement_key
        for existing in groups
    ):
        raise CommandSurfaceError(f"Duplicate command-surface group ID: {group.id}")
    output = list(groups)
    for index, existing in enumerate(output):
        if existing.id.casefold() == replacement_key:
            output[index] = replace(
                group,
                id=group.id.strip(),
                label=group.label.strip(),
            )
            break
    else:
        output.append(
            replace(
                group,
                id=group.id.strip(),
                label=group.label.strip(),
            )
        )
    save_command_groups(path, output)


def delete_command_group(path: Path, group_id: str) -> None:
    groups = load_command_groups(path) if path.exists() else []
    retained = [group for group in groups if group.id.casefold() != group_id.casefold()]
    if len(retained) == len(groups):
        raise CommandSurfaceError(f"Quick-action group was not found: {group_id}")
    save_command_groups(path, retained)


def delete_command_item(path: Path, group_id: str, item_id: str) -> None:
    groups = load_command_groups(path) if path.exists() else []
    output: list[CommandGroup] = []
    found = False
    for group in groups:
        if group.id.casefold() != group_id.casefold():
            output.append(group)
            continue
        items, found = _delete_command_item(
            group.items,
            item_id.casefold(),
        )
        output.append(replace(group, items=items))
    if not found:
        raise CommandSurfaceError(
            f"Quick action was not found in {group_id}: {item_id}"
        )
    save_command_groups(path, output)


def move_command_group(path: Path, group_id: str, offset: int) -> bool:
    groups = load_command_groups(path) if path.exists() else []
    index = next(
        (i for i, group in enumerate(groups) if group.id.casefold() == group_id.casefold()),
        -1,
    )
    target = index + offset
    if index < 0:
        raise CommandSurfaceError(f"Quick-action group was not found: {group_id}")
    if target < 0 or target >= len(groups):
        return False
    groups[index], groups[target] = groups[target], groups[index]
    save_command_groups(path, groups)
    return True


def move_command_item(
    path: Path,
    group_id: str,
    item_id: str,
    offset: int,
) -> bool:
    groups = load_command_groups(path) if path.exists() else []
    output = list(groups)
    group_index = next(
        (i for i, group in enumerate(groups) if group.id.casefold() == group_id.casefold()),
        -1,
    )
    if group_index < 0:
        raise CommandSurfaceError(f"Quick-action group was not found: {group_id}")
    group = groups[group_index]
    items, found, moved = _move_command_item(
        group.items,
        item_id.casefold(),
        offset,
    )
    if not found:
        raise CommandSurfaceError(f"Quick action was not found in {group_id}: {item_id}")
    if not moved:
        return False
    output[group_index] = replace(group, items=items)
    save_command_groups(path, output)
    return True


def save_command_groups(path: Path, groups: list[CommandGroup]) -> None:
    seen: set[str] = set()
    for group in groups:
        _validate_group(group)
        key = group.id.casefold()
        if key in seen:
            raise CommandSurfaceError(f"Duplicate command-surface group ID: {group.id}")
        seen.add(key)
    atomic_write_json(
        path,
        {
            "groups": [
                _command_group_to_data(group)
                for group in groups
            ]
        },
    )


def _validate_group(group: CommandGroup) -> None:
    if not group.id.strip() or not group.label.strip():
        raise CommandSurfaceError("A Quick-action group needs a visible name.")
    if (
        not isinstance(group.presentation, str)
        or group.presentation not in GROUP_PRESENTATIONS
    ):
        raise CommandSurfaceError(
            f"Invalid Quick-action group presentation: {group.presentation}"
        )
    if (
        group.presentation != GROUP_PRESENTATION_NESTED_MENU
        and command_group_action_ids(group)
    ):
        raise CommandSurfaceError(
            "Direct group actions require Nested subject menu presentation."
        )
    item_ids: set[str] = set()

    def validate_items(
        items: tuple[CommandItem, ...],
        depth: int,
    ) -> None:
        if not items:
            return
        if depth > MAX_COMMAND_MENU_LEVELS:
            raise CommandSurfaceError(
                f"Quick-action menus support at most "
                f"{MAX_COMMAND_MENU_LEVELS} submenu levels."
            )
        for item in items:
            if not item.id.strip() or not item.label.strip():
                raise CommandSurfaceError("A Quick action needs a visible name.")
            key = item.id.casefold()
            if key in item_ids:
                raise CommandSurfaceError(
                    f"Duplicate button ID in this group: {item.id}"
                )
            item_ids.add(key)
            if item.targets and (
                item.primary_action_id
                or item.action_ids
                or item.work_item_ref is not None
            ):
                raise CommandSurfaceError(
                    "A Quick action cannot combine targets with legacy target fields."
                )
            command_item_targets(item)
            validate_items(item.items, depth + 1)

    validate_items(group.items, 1)


def _command_group_to_data(group: CommandGroup) -> dict[str, object]:
    return {
        "id": group.id.strip(),
        "label": group.label.strip(),
        **(
            {"presentation": group.presentation}
            if group.presentation != GROUP_PRESENTATION_ROWS
            else {}
        ),
        **(
            {"primary_action_id": group.primary_action_id}
            if group.primary_action_id
            else {}
        ),
        "action_ids": list(group.action_ids),
        "items": [_command_item_to_data(item) for item in group.items],
    }


def _command_item_to_data(item: CommandItem) -> dict[str, object]:
    data: dict[str, object] = {
        "id": item.id.strip(),
        "label": item.label.strip(),
    }
    if item.targets:
        data["targets"] = [
            (
                {"type": "action", "action_id": target.action_id}
                if target.action_id
                else {
                    "type": "work_item",
                    "source_id": target.work_item_ref.source_id,
                    "relative_folder": target.work_item_ref.relative_folder,
                }
            )
            for target in command_item_targets(item)
        ]
    else:
        if item.primary_action_id:
            data["primary_action_id"] = item.primary_action_id
        data["action_ids"] = list(item.action_ids)
        if item.work_item_ref is not None:
            data["work_item_ref"] = {
                "source_id": item.work_item_ref.source_id,
                "relative_folder": item.work_item_ref.relative_folder,
            }
    if item.items:
        data["items"] = [_command_item_to_data(child) for child in item.items]
    return data


def _replace_command_item(
    items: tuple[CommandItem, ...],
    target_key: str,
    replacement: CommandItem,
) -> tuple[tuple[CommandItem, ...], bool]:
    output: list[CommandItem] = []
    found = False
    for item in items:
        if item.id.casefold() == target_key:
            output.append(replacement)
            found = True
            continue
        children, child_found = _replace_command_item(
            item.items,
            target_key,
            replacement,
        )
        output.append(replace(item, items=children) if child_found else item)
        found = found or child_found
    return tuple(output), found


def _append_command_item(
    items: tuple[CommandItem, ...],
    parent_item_ids: tuple[str, ...],
    item: CommandItem,
) -> tuple[CommandItem, ...]:
    if not parent_item_ids:
        return (*items, item)
    parent_key = parent_item_ids[0].casefold()
    output: list[CommandItem] = []
    found = False
    for existing in items:
        if existing.id.casefold() != parent_key:
            output.append(existing)
            continue
        children = _append_command_item(
            existing.items,
            parent_item_ids[1:],
            item,
        )
        output.append(replace(existing, items=children))
        found = True
    if not found:
        raise CommandSurfaceError(
            f"Quick-action submenu parent was not found: {parent_item_ids[0]}"
        )
    return tuple(output)


def _delete_command_item(
    items: tuple[CommandItem, ...],
    target_key: str,
) -> tuple[tuple[CommandItem, ...], bool]:
    output: list[CommandItem] = []
    found = False
    for item in items:
        if item.id.casefold() == target_key:
            found = True
            continue
        children, child_found = _delete_command_item(item.items, target_key)
        output.append(replace(item, items=children) if child_found else item)
        found = found or child_found
    return tuple(output), found


def _move_command_item(
    items: tuple[CommandItem, ...],
    target_key: str,
    offset: int,
) -> tuple[tuple[CommandItem, ...], bool, bool]:
    current = list(items)
    index = next(
        (
            item_index
            for item_index, item in enumerate(current)
            if item.id.casefold() == target_key
        ),
        -1,
    )
    if index >= 0:
        target = index + offset
        if target < 0 or target >= len(current):
            return items, True, False
        current[index], current[target] = current[target], current[index]
        return tuple(current), True, True
    output: list[CommandItem] = []
    for item in items:
        children, found, moved = _move_command_item(
            item.items,
            target_key,
            offset,
        )
        output.append(replace(item, items=children) if found else item)
        if found:
            output.extend(items[len(output):])
            return tuple(output), True, moved
    return items, False, False
