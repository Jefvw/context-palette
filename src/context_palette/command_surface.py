from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


class CommandSurfaceError(Exception):
    """Raised when command-surface configuration is invalid."""


@dataclass(frozen=True)
class CommandItem:
    id: str
    label: str
    primary_action_id: str = ""
    action_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandGroup:
    id: str
    label: str
    items: tuple[CommandItem, ...] = ()
    source_path: Path | None = None


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
    groups = load_command_groups(shared_path) + load_command_groups(local_path)
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
    if not isinstance(group_id, str) or not group_id.strip():
        raise CommandSurfaceError(f"Command-surface group #{index} requires an ID.")
    if not isinstance(label, str) or not label.strip():
        raise CommandSurfaceError(f"Command-surface group #{index} requires a label.")
    if not isinstance(items, list):
        raise CommandSurfaceError(f"Command-surface group #{index} has invalid items.")
    parsed_items = tuple(_parse_item(value, index, item_index) for item_index, value in enumerate(items, 1))
    item_ids = [value.id.casefold() for value in parsed_items]
    if len(item_ids) != len(set(item_ids)):
        raise CommandSurfaceError(f"Command-surface group #{index} has duplicate item IDs.")
    return CommandGroup(
        id=group_id.strip(),
        label=label.strip(),
        items=parsed_items,
        source_path=source_path,
    )


def _parse_item(item: object, group_index: int, item_index: int) -> CommandItem:
    if not isinstance(item, dict):
        raise CommandSurfaceError(
            f"Command-surface group #{group_index}, item #{item_index} must be an object."
        )
    item_id = item.get("id")
    label = item.get("label")
    primary_action_id = item.get("primary_action_id", "")
    action_ids = item.get("action_ids", [])
    if not isinstance(item_id, str) or not item_id.strip():
        raise CommandSurfaceError(
            f"Command-surface group #{group_index}, item #{item_index} requires an ID."
        )
    if not isinstance(label, str) or not label.strip():
        raise CommandSurfaceError(
            f"Command-surface group #{group_index}, item #{item_index} requires a label."
        )
    if not isinstance(primary_action_id, str):
        raise CommandSurfaceError(
            f"Command-surface group #{group_index}, item #{item_index} has invalid text fields."
        )
    if not isinstance(action_ids, list) or not all(isinstance(value, str) for value in action_ids):
        raise CommandSurfaceError(
            f"Command-surface group #{group_index}, item #{item_index} has invalid action_ids."
        )
    clean_action_ids = tuple(dict.fromkeys(value.strip() for value in action_ids if value.strip()))
    return CommandItem(
        id=item_id.strip(),
        label=label.strip(),
        primary_action_id=primary_action_id.strip(),
        action_ids=clean_action_ids,
    )
