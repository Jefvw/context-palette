from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterator

from .palette_items import (
    PaletteItemReference,
    PaletteItemReferenceError,
)
from .work_items import WorkItemDiscoveryError, WorkItemReference


class CommandSurfaceError(Exception):
    """Raised when command-surface configuration is invalid."""


GROUP_PRESENTATION_ROWS = "rows"
GROUP_PRESENTATION_NESTED_MENU = "nested_menu"
GROUP_PRESENTATIONS = {
    GROUP_PRESENTATION_ROWS,
    GROUP_PRESENTATION_NESTED_MENU,
}
MAX_COMMAND_MENU_LEVELS = 3


CommandTarget = PaletteItemReference


@dataclass(frozen=True)
class CommandItem:
    id: str
    label: str
    primary_action_id: str = ""
    action_ids: tuple[str, ...] = ()
    items: tuple["CommandItem", ...] = ()
    work_item_ref: WorkItemReference | None = None
    targets: tuple[CommandTarget, ...] = ()


@dataclass(frozen=True)
class CommandGroup:
    id: str
    label: str
    items: tuple[CommandItem, ...] = ()
    source_path: Path | None = None
    presentation: str = GROUP_PRESENTATION_ROWS
    primary_action_id: str = ""
    action_ids: tuple[str, ...] = ()


def command_item_action_ids(item: CommandItem) -> tuple[str, ...]:
    """Return one primary-first, duplicate-free action order for an item."""
    if item.targets:
        return tuple(
            dict.fromkeys(
                target.action_id
                for target in item.targets
                if target.action_id
            )
        )
    return tuple(
        dict.fromkeys(
            action_id
            for action_id in (item.primary_action_id, *item.action_ids)
            if action_id
        )
    )


def command_item_targets(item: CommandItem) -> tuple[CommandTarget, ...]:
    """Return the canonical ordered mixed target list for one item."""
    if item.targets:
        return tuple(dict.fromkeys(item.targets))
    targets = [CommandTarget(action_id=value) for value in command_item_action_ids(item)]
    if item.work_item_ref is not None:
        targets.append(CommandTarget(work_item_ref=item.work_item_ref))
    return tuple(targets)


def command_item_work_item_references(
    item: CommandItem,
) -> tuple[WorkItemReference, ...]:
    return tuple(
        target.work_item_ref
        for target in command_item_targets(item)
        if target.work_item_ref is not None
    )


def command_group_action_ids(group: CommandGroup) -> tuple[str, ...]:
    """Return primary-first actions placed directly in a nested group menu."""
    return tuple(
        dict.fromkeys(
            action_id
            for action_id in (group.primary_action_id, *group.action_ids)
            if action_id
        )
    )


def iter_command_items(
    group: CommandGroup,
) -> Iterator[tuple[tuple[int, ...], CommandItem]]:
    """Yield every menu item with its zero-based index path."""
    def walk(
        items: tuple[CommandItem, ...],
        parent_path: tuple[int, ...],
    ) -> Iterator[tuple[tuple[int, ...], CommandItem]]:
        for index, item in enumerate(items):
            path = (*parent_path, index)
            yield path, item
            yield from walk(item.items, path)

    yield from walk(group.items, ())


def command_item_at_path(
    group: CommandGroup,
    path: tuple[int, ...],
) -> CommandItem:
    items = group.items
    item: CommandItem | None = None
    for index in path:
        item = items[index]
        items = item.items
    if item is None:
        raise IndexError("A command-item path cannot be empty.")
    return item


def command_item_id_path(
    group: CommandGroup,
    path: tuple[int, ...],
) -> tuple[str, ...]:
    ids: list[str] = []
    items = group.items
    for index in path:
        item = items[index]
        ids.append(item.id)
        items = item.items
    return tuple(ids)


def command_item_count(group: CommandGroup) -> int:
    return sum(1 for _path, _item in iter_command_items(group))


def command_group_all_action_ids(group: CommandGroup) -> tuple[str, ...]:
    action_ids = list(command_group_action_ids(group))
    for _path, item in iter_command_items(group):
        action_ids.extend(command_item_action_ids(item))
    return tuple(dict.fromkeys(action_ids))


def command_group_launcher_count(group: CommandGroup) -> int:
    """Return the number of visible launchers contributed by a group."""
    if group.presentation == GROUP_PRESENTATION_NESTED_MENU:
        return 1
    return len(group.items)


def load_command_groups(path: Path) -> list[CommandGroup]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as exc:
        raise CommandSurfaceError(f"Command-surface file is not valid JSON: {path}") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("groups"), list):
        raise CommandSurfaceError("Command-surface file must contain a 'groups' list.")
    return [_parse_group(item, index, path) for index, item in enumerate(raw["groups"], start=1)]


def load_combined_command_groups(shared_path: Path, local_path: Path) -> list[CommandGroup]:
    shared_groups = load_command_groups(shared_path)
    for group in shared_groups:
        for _path, item in iter_command_items(group):
            if command_item_work_item_references(item):
                raise CommandSurfaceError(
                    "Built-in Quick actions cannot reference personal Work Items."
                )
    groups = shared_groups + load_command_groups(local_path)
    seen: set[str] = set()
    for group in groups:
        key = group.id.casefold()
        if key in seen:
            raise CommandSurfaceError(f"Duplicate command-surface group ID: {group.id}")
        seen.add(key)
    return groups


def command_configuration_paths(
    group: CommandGroup,
    shared_surface_path: Path,
    local_surface_path: Path,
    shared_actions_path: Path,
    local_actions_path: Path,
) -> tuple[Path, Path]:
    surface_path = group.source_path or shared_surface_path
    is_local = surface_path.resolve() == local_surface_path.resolve()
    actions_path = local_actions_path if is_local else shared_actions_path
    return surface_path, actions_path


def _parse_group(item: object, index: int, source_path: Path) -> CommandGroup:
    if not isinstance(item, dict):
        raise CommandSurfaceError(f"Command-surface group #{index} must be an object.")
    group_id = item.get("id")
    label = item.get("label")
    items = item.get("items", [])
    presentation = item.get("presentation", GROUP_PRESENTATION_ROWS)
    primary_action_id, action_ids = _parse_action_references(
        item,
        f"Command-surface group #{index}",
    )
    if not isinstance(group_id, str) or not group_id.strip():
        raise CommandSurfaceError(f"Command-surface group #{index} requires an ID.")
    if not isinstance(label, str) or not label.strip():
        raise CommandSurfaceError(f"Command-surface group #{index} requires a label.")
    if not isinstance(items, list):
        raise CommandSurfaceError(f"Command-surface group #{index} has invalid items.")
    if (
        not isinstance(presentation, str)
        or presentation not in GROUP_PRESENTATIONS
    ):
        raise CommandSurfaceError(
            f"Command-surface group #{index} has invalid presentation: {presentation}"
        )
    seen_item_ids: set[str] = set()
    parsed_items = tuple(
        _parse_item(
            value,
            index,
            (item_index,),
            seen_item_ids,
        )
        for item_index, value in enumerate(items, 1)
    )
    if (
        presentation == GROUP_PRESENTATION_ROWS
        and (primary_action_id or action_ids)
    ):
        raise CommandSurfaceError(
            f"Command-surface group #{index} can place actions directly in "
            "the group only with nested_menu presentation."
        )
    return CommandGroup(
        id=group_id.strip(),
        label=label.strip(),
        items=parsed_items,
        source_path=source_path,
        presentation=presentation,
        primary_action_id=primary_action_id,
        action_ids=action_ids,
    )


def _parse_item(
    item: object,
    group_index: int,
    item_path: tuple[int, ...],
    seen_item_ids: set[str],
) -> CommandItem:
    item_location = ".".join(str(index) for index in item_path)
    prefix = f"Command-surface group #{group_index}, item #{item_location}"
    if not isinstance(item, dict):
        raise CommandSurfaceError(f"{prefix} must be an object.")
    item_id = item.get("id")
    label = item.get("label")
    child_items = item.get("items", [])
    primary_action_id, action_ids = _parse_action_references(item, prefix)
    work_item_ref = _parse_work_item_reference(item.get("work_item_ref"), prefix)
    targets = _parse_targets(item.get("targets"), prefix)
    if not isinstance(item_id, str) or not item_id.strip():
        raise CommandSurfaceError(f"{prefix} requires an ID.")
    if not isinstance(label, str) or not label.strip():
        raise CommandSurfaceError(f"{prefix} requires a label.")
    if not isinstance(child_items, list):
        raise CommandSurfaceError(f"{prefix} has invalid items.")
    clean_item_id = item_id.strip()
    key = clean_item_id.casefold()
    if key in seen_item_ids:
        raise CommandSurfaceError(
            f"Command-surface group #{group_index} has duplicate item ID: "
            f"{clean_item_id}"
        )
    seen_item_ids.add(key)
    if len(item_path) >= MAX_COMMAND_MENU_LEVELS and child_items:
        raise CommandSurfaceError(
            f"{prefix} exceeds the maximum of "
            f"{MAX_COMMAND_MENU_LEVELS} submenu levels."
        )
    parsed_children = tuple(
        _parse_item(
            value,
            group_index,
            (*item_path, child_index),
            seen_item_ids,
        )
        for child_index, value in enumerate(child_items, 1)
    )
    if targets and (primary_action_id or action_ids or work_item_ref is not None):
        raise CommandSurfaceError(
            f"{prefix} cannot combine targets with legacy target fields."
        )
    if work_item_ref is not None and (primary_action_id or action_ids):
        raise CommandSurfaceError(
            f"{prefix} cannot assign both actions and a Work Item."
        )
    return CommandItem(
        id=clean_item_id,
        label=label.strip(),
        primary_action_id=primary_action_id,
        action_ids=action_ids,
        items=parsed_children,
        work_item_ref=work_item_ref,
        targets=targets,
    )


def _parse_targets(value: object, prefix: str) -> tuple[CommandTarget, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise CommandSurfaceError(f"{prefix} has invalid targets.")
    targets: list[CommandTarget] = []
    for index, raw_target in enumerate(value, start=1):
        target_prefix = f"{prefix}, target #{index}"
        if not isinstance(raw_target, dict):
            raise CommandSurfaceError(f"{target_prefix} must be an object.")
        target_type = raw_target.get("type")
        if target_type == "action":
            if set(raw_target) != {"type", "action_id"} or not isinstance(
                raw_target.get("action_id"), str
            ):
                raise CommandSurfaceError(f"{target_prefix} has invalid action data.")
            try:
                target = CommandTarget(action_id=raw_target["action_id"])
            except PaletteItemReferenceError as exc:
                raise CommandSurfaceError(f"{target_prefix}: {exc}") from exc
        elif target_type == "work_item":
            if set(raw_target) != {"type", "source_id", "relative_folder"}:
                raise CommandSurfaceError(f"{target_prefix} has invalid Work Item data.")
            reference = _parse_work_item_reference(
                {
                    "source_id": raw_target.get("source_id"),
                    "relative_folder": raw_target.get("relative_folder"),
                },
                target_prefix,
            )
            target = CommandTarget(work_item_ref=reference)
        else:
            raise CommandSurfaceError(f"{target_prefix} has an unknown type.")
        if target not in targets:
            targets.append(target)
    return tuple(targets)


def _parse_work_item_reference(
    value: object,
    prefix: str,
) -> WorkItemReference | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"source_id", "relative_folder"}:
        raise CommandSurfaceError(
            f"{prefix} has an invalid work_item_ref."
        )
    if not all(isinstance(value[field], str) for field in value):
        raise CommandSurfaceError(
            f"{prefix} has an invalid work_item_ref."
        )
    try:
        return WorkItemReference(
            value["source_id"],
            value["relative_folder"],
        )
    except WorkItemDiscoveryError as exc:
        raise CommandSurfaceError(f"{prefix}: {exc}") from exc


def _parse_action_references(
    item: dict[str, object],
    prefix: str,
) -> tuple[str, tuple[str, ...]]:
    primary_action_id = item.get("primary_action_id", "")
    action_ids = item.get("action_ids", [])
    if not isinstance(primary_action_id, str):
        raise CommandSurfaceError(f"{prefix} has invalid primary_action_id.")
    if not isinstance(action_ids, list) or not all(
        isinstance(value, str) for value in action_ids
    ):
        raise CommandSurfaceError(f"{prefix} has invalid action_ids.")
    return (
        primary_action_id.strip(),
        tuple(
            dict.fromkeys(
                value.strip()
                for value in action_ids
                if value.strip()
            )
        ),
    )
