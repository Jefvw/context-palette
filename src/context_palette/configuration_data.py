from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from .command_surface import CommandGroup, CommandItem, CommandSurfaceError, load_command_groups
from .contexts import ContextDefinition, ContextError, load_contexts
from .persistence import atomic_write_json


def save_local_context(
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
        {
            "contexts": [
                {
                    key: value
                    for key, value in asdict(item).items()
                    if value not in ("", (), None)
                }
                for item in updated
            ]
        },
    )


def save_local_command_item(
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
        items = [
            existing
            for existing in group.items
            if existing.id.casefold() != replacement_item_key
        ]
        if any(existing.id.casefold() == item.id.casefold() for existing in items):
            raise CommandSurfaceError(f"Duplicate button ID in this group: {item.id}")
        items.append(item)
        output.append(CommandGroup(clean_group_id, clean_group_label, tuple(items)))
    if not matched_group:
        if any(group.id.casefold() == clean_group_id.casefold() for group in output):
            raise CommandSurfaceError(f"Duplicate command-surface group ID: {clean_group_id}")
        output.append(CommandGroup(clean_group_id, clean_group_label, (item,)))

    atomic_write_json(
        path,
        {
            "groups": [
                {
                    "id": group.id,
                    "label": group.label,
                    "items": [
                        {
                            "id": entry.id,
                            "label": entry.label,
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
                for group in output
            ]
        },
    )
