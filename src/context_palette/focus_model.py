from __future__ import annotations

from dataclasses import dataclass

from .actions import Action, VISIBLE_STATES
from .contexts import ContextDefinition
from .palette_state import PaletteState


FocusActionHierarchy = list[tuple[str, list[tuple[str, list[Action]]]]]


@dataclass(frozen=True)
class ResolvedFocusState:
    palette_state: PaletteState
    available_names: tuple[str, ...]


def resolve_focus_state(
    actions: list[Action],
    definitions: list[ContextDefinition],
    palette_state: PaletteState,
) -> ResolvedFocusState:
    """Apply current Focus discovery, slot-preference, and fallback policy."""
    configured_names = {definition.name for definition in definitions}
    available_names = tuple(
        sorted(
            configured_names | {action.context for action in actions},
            key=str.casefold,
        )
    )
    configured_slots = dict(palette_state.context_slots)
    known_action_ids = {action.id for action in actions}
    for definition in definitions:
        if definition.name not in configured_slots and definition.preferred_action_ids:
            configured_slots[definition.name] = tuple(
                action_id
                for action_id in definition.preferred_action_ids
                if action_id in known_action_ids
            )

    focus_context = palette_state.focus_context
    if focus_context not in available_names and available_names:
        focus_context = available_names[0]
    return ResolvedFocusState(
        PaletteState(
            palette_state.pinned_action_ids,
            focus_context,
            configured_slots,
        ),
        available_names,
    )


def focus_action_hierarchy(
    actions: list[Action],
    focus_context: str,
) -> FocusActionHierarchy:
    """Group visible actions for an explicit Focus in canonical action order."""
    technologies: dict[str, dict[str, list[Action]]] = {}
    for action in actions:
        if (
            action.context.casefold() != focus_context.casefold()
            or action.state not in VISIBLE_STATES
        ):
            continue
        technology = action.technology.strip() or "Other"
        task = action.task.strip() or "Other"
        technologies.setdefault(technology, {}).setdefault(task, []).append(action)
    return [
        (technology, list(tasks.items()))
        for technology, tasks in technologies.items()
    ]
