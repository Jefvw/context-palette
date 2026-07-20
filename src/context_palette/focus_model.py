from __future__ import annotations

from dataclasses import dataclass

from .actions import Action, VISIBLE_STATES
from .contexts import ContextDefinition
from .palette_state import PaletteState


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
    names_by_key = {"general": "General"}
    for definition in definitions:
        names_by_key.setdefault(definition.name.casefold(), definition.name)
    for action in actions:
        for context in action.effective_contexts:
            names_by_key.setdefault(context.casefold(), context)
    available_names = (
        "General",
        *sorted(
            (name for key, name in names_by_key.items() if key != "general"),
            key=str.casefold,
        ),
    )
    configured_slots: dict[str, tuple[str, ...]] = {}
    for context, action_ids in palette_state.context_slots.items():
        canonical_context = names_by_key.get(context.casefold(), context)
        if canonical_context not in configured_slots or context == canonical_context:
            configured_slots[canonical_context] = action_ids
    known_action_ids = {action.id for action in actions}
    for definition in definitions:
        if definition.name not in configured_slots and definition.preferred_action_ids:
            configured_slots[definition.name] = tuple(
                action_id
                for action_id in definition.preferred_action_ids
                if action_id in known_action_ids
            )

    focus_context = palette_state.focus_context
    focus_context = names_by_key.get(focus_context.casefold(), "General")
    return ResolvedFocusState(
        PaletteState(
            palette_state.pinned_action_ids,
            focus_context,
            configured_slots,
        ),
        available_names,
    )


def actions_for_context(
    actions: list[Action],
    focus_context: str,
) -> list[Action]:
    """Return visible actions belonging to an explicit Focus in canonical order."""
    return [
        action
        for action in actions
        if action.belongs_to_context(focus_context)
        and action.state in VISIBLE_STATES
    ]
