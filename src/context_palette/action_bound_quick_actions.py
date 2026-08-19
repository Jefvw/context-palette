from __future__ import annotations

from .actions import ACTION_BOUND_QUICK_MENU_SPECS, Action
from .command_surface import (
    CommandGroup,
    CommandItem,
    GROUP_PRESENTATION_NESTED_MENU,
)


def action_bound_quick_group(
    actions: list[Action],
    *,
    group_id: str,
    label: str,
    action_type: str,
) -> CommandGroup:
    """Build one live menu directly from active actions of a single type.

    Actions without a Quick-menu path belong at the menu root.  A path creates
    only the requested nested branches; it never adds a synthetic ``Unsorted``
    level that costs the user another click.
    """

    entries = [
        (action.quick_action_path, action)
        for action in actions
        if action.type == action_type
        and action.state != "Archived"
        and action.quick_action_path
    ]
    root_action_ids = tuple(
        action.id
        for action in actions
        if action.type == action_type
        and action.state != "Archived"
        and not action.quick_action_path
    )
    item_counter = 0

    def build_items(
        values: list[tuple[tuple[str, ...], Action]],
        depth: int,
    ) -> tuple[CommandItem, ...]:
        nonlocal item_counter
        grouped: dict[str, tuple[str, list[tuple[tuple[str, ...], Action]]]] = {}
        for path, action in values:
            key = path[depth].casefold()
            if key not in grouped:
                grouped[key] = (path[depth], [])
            grouped[key][1].append((path, action))

        items: list[CommandItem] = []
        for visible_label, grouped_values in grouped.values():
            item_counter += 1
            direct_action_ids = tuple(
                action.id
                for path, action in grouped_values
                if len(path) == depth + 1
            )
            nested_values = [
                (path, action)
                for path, action in grouped_values
                if len(path) > depth + 1
            ]
            items.append(
                CommandItem(
                    id=f"{group_id}-level-{item_counter}",
                    label=visible_label,
                    action_ids=direct_action_ids,
                    items=(
                        build_items(nested_values, depth + 1)
                        if nested_values
                        else ()
                    ),
                )
            )
        return tuple(items)

    return CommandGroup(
        id=f"action-bound-{group_id}",
        label=label,
        items=build_items(entries, 0) if entries else (),
        presentation=GROUP_PRESENTATION_NESTED_MENU,
        action_ids=root_action_ids,
    )


def action_bound_quick_groups(actions: list[Action]) -> tuple[CommandGroup, ...]:
    return tuple(
        action_bound_quick_group(
            actions,
            group_id=group_id,
            label=label,
            action_type=action_type,
        )
        for group_id, label, action_type in ACTION_BOUND_QUICK_MENU_SPECS
    )
