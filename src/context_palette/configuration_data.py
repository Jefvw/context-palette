from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from .command_surface import CommandGroup, CommandItem, CommandSurfaceError, load_command_groups
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
    atomic_write_json(
        path,
        {"contexts": [_context_to_data(item) for item in updated]},
    )


def save_command_item(
    path: Path,
    *,
    group_id: str,
    group_label: str,
    item: CommandItem,
    original_group_id: str = "",
    original_item_id: str = "",
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
            for existing in group.items
        ):
            raise CommandSurfaceError(f"Duplicate button ID in this group: {item.id}")
        items = list(group.items)
        replaced = False
        for index, existing in enumerate(items):
            if existing.id.casefold() == replacement_item_key:
                items[index] = item
                replaced = True
                break
        if not replaced:
            items.append(item)
        output.append(CommandGroup(clean_group_id, clean_group_label, tuple(items)))
    if not matched_group:
        if any(group.id.casefold() == clean_group_id.casefold() for group in output):
            raise CommandSurfaceError(f"Duplicate command-surface group ID: {clean_group_id}")
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
            output[index] = CommandGroup(
                group.id.strip(),
                group.label.strip(),
                group.items,
            )
            break
    else:
        output.append(CommandGroup(group.id.strip(), group.label.strip(), group.items))
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
        items = tuple(
            item for item in group.items if item.id.casefold() != item_id.casefold()
        )
        found = len(items) != len(group.items)
        output.append(CommandGroup(group.id, group.label, items))
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
    items = list(group.items)
    item_index = next(
        (i for i, item in enumerate(items) if item.id.casefold() == item_id.casefold()),
        -1,
    )
    target = item_index + offset
    if item_index < 0:
        raise CommandSurfaceError(f"Quick action was not found in {group_id}: {item_id}")
    if target < 0 or target >= len(items):
        return False
    items[item_index], items[target] = items[target], items[item_index]
    output[group_index] = CommandGroup(group.id, group.label, tuple(items))
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
                {
                    "id": group.id.strip(),
                    "label": group.label.strip(),
                    "items": [
                        {
                            "id": entry.id.strip(),
                            "label": entry.label.strip(),
                            **(
                                {"primary_action_id": entry.primary_action_id}
                                if entry.primary_action_id
                                else {}
                            ),
                            "action_ids": list(entry.action_ids),
                        }
                        for entry in group.items
                    ],
                }
                for group in groups
            ]
        },
    )


def _validate_group(group: CommandGroup) -> None:
    if not group.id.strip() or not group.label.strip():
        raise CommandSurfaceError("A Quick-action group needs a visible name.")
    item_ids: set[str] = set()
    for item in group.items:
        if not item.id.strip() or not item.label.strip():
            raise CommandSurfaceError("A Quick action needs a visible name.")
        key = item.id.casefold()
        if key in item_ids:
            raise CommandSurfaceError(
                f"Duplicate button ID in this group: {item.id}"
            )
        item_ids.add(key)
