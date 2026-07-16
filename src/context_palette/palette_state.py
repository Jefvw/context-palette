from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .actions import Action, ActionError
from .persistence import atomic_write_json


@dataclass(frozen=True)
class PaletteState:
    pinned_action_ids: tuple[str, ...] = ()
    focus_context: str = "General"
    context_slots: dict[str, tuple[str, ...]] | None = None


def load_palette_state(path: Path) -> PaletteState:
    if not path.exists():
        return PaletteState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ActionError(f"Palette configuration is not valid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ActionError("Palette configuration must be an object.")

    pinned = raw.get("pinned_action_ids", [])
    focus = raw.get("focus_context", "General")
    slots = raw.get("context_slots", {})
    if not isinstance(pinned, list) or not all(isinstance(item, str) for item in pinned):
        raise ActionError("Palette pins must be a list of action IDs.")
    if len(pinned) > 5:
        raise ActionError("At most five actions can be pinned.")
    if not isinstance(focus, str):
        raise ActionError("Palette focus context must be text.")
    if not isinstance(slots, dict):
        raise ActionError("Palette context slots must be an object.")

    parsed_slots: dict[str, tuple[str, ...]] = {}
    for context, ids in slots.items():
        if not isinstance(context, str) or not isinstance(ids, list):
            raise ActionError("Each context slot list must contain action IDs.")
        if len(ids) > 4 or not all(isinstance(item, str) for item in ids):
            raise ActionError("Each context can have at most four action IDs.")
        parsed_slots[context] = tuple(ids)
    return PaletteState(tuple(pinned), focus.strip() or "General", parsed_slots)


def save_palette_state(path: Path, state: PaletteState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "pinned_action_ids": list(state.pinned_action_ids[:5]),
        "focus_context": state.focus_context,
        "context_slots": {
            context: list(ids[:4]) for context, ids in (state.context_slots or {}).items()
        },
    }
    atomic_write_json(path, data)


def action_slots(actions: list[Action], state: PaletteState) -> dict[int, Action]:
    by_id = {action.id: action for action in actions}
    result: dict[int, Action] = {}
    for slot, action_id in enumerate(state.pinned_action_ids[:5], start=1):
        if action_id in by_id:
            result[slot] = by_id[action_id]

    configured = (state.context_slots or {}).get(state.focus_context, ())
    context_actions = [by_id[action_id] for action_id in configured if action_id in by_id]
    if not context_actions:
        context_actions = [action for action in actions if action.context == state.focus_context][:4]
    if len(context_actions) < 4:
        used_ids = {action.id for action in context_actions}
        fallbacks = [
            action
            for action in actions
            if action.id not in used_ids and action.context == "General"
        ]
        context_actions.extend(fallbacks[: 4 - len(context_actions)])
    if len(context_actions) < 4:
        used_ids = {action.id for action in context_actions}
        fallbacks = [action for action in actions if action.id not in used_ids]
        context_actions.extend(fallbacks[: 4 - len(context_actions)])
    for slot, action in enumerate(context_actions[:4], start=6):
        result[slot] = action
    return result


def toggle_pin(state: PaletteState, action_id: str) -> PaletteState:
    pins = list(state.pinned_action_ids)
    if action_id in pins:
        pins.remove(action_id)
    elif len(pins) >= 5:
        raise ActionError("All five pinned slots are occupied. Unpin an action first.")
    else:
        pins.append(action_id)
    return PaletteState(tuple(pins), state.focus_context, state.context_slots)
