from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from .actions import Action, ActionError
from .palette_items import PaletteItemReference, palette_item_reference_data
from .persistence import atomic_write_json
from .work_items import WorkItemDiscoveryError, WorkItemReference


MAX_CONTEXT_SLOT_ACTIONS = 5
CONTEXT_SLOT_NUMBERS = (6, 7, 8, 9, 10)


def slot_display_number(slot: int) -> str:
    return "0" if slot == 10 else str(slot)


@dataclass(frozen=True)
class PaletteState:
    pinned_action_ids: tuple[str, ...] = ()
    focus_context: str = "General"
    context_slots: dict[str, tuple[str, ...]] = field(default_factory=dict)
    context_membership_version: int = 0
    context_item_slots: dict[str, tuple[PaletteItemReference, ...]] = field(
        default_factory=dict
    )


def load_palette_state(path: Path) -> PaletteState:
    if not path.exists():
        return PaletteState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ActionError(f"Palette configuration could not be read: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ActionError(f"Palette configuration is not valid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ActionError("Palette configuration must be an object.")

    pinned = raw.get("pinned_action_ids", [])
    focus = raw.get("focus_context", "General")
    slots = raw.get("context_slots", {})
    item_slots = raw.get("context_item_slots", {})
    context_membership_version = raw.get("context_membership_version", 0)
    if not isinstance(pinned, list) or not all(isinstance(item, str) for item in pinned):
        raise ActionError("Palette pins must be a list of action IDs.")
    if len(pinned) > 5:
        raise ActionError("At most five actions can be pinned.")
    if not isinstance(focus, str):
        raise ActionError("Palette focus context must be text.")
    if not isinstance(slots, dict):
        raise ActionError("Palette context slots must be an object.")
    if not isinstance(item_slots, dict):
        raise ActionError("Palette context item slots must be an object.")
    if (
        not isinstance(context_membership_version, int)
        or isinstance(context_membership_version, bool)
        or context_membership_version < 0
    ):
        raise ActionError("Palette context membership version must be a non-negative integer.")

    parsed_slots: dict[str, tuple[str, ...]] = {}
    for context, ids in slots.items():
        if not isinstance(context, str) or not isinstance(ids, list):
            raise ActionError("Each context slot list must contain action IDs.")
        if len(ids) > MAX_CONTEXT_SLOT_ACTIONS or not all(
            isinstance(item, str) for item in ids
        ):
            raise ActionError(
                f"Each context can have at most {MAX_CONTEXT_SLOT_ACTIONS} action IDs."
            )
        parsed_slots[context] = tuple(ids)
    parsed_item_slots: dict[str, tuple[PaletteItemReference, ...]] = {}
    for context, values in item_slots.items():
        if not isinstance(context, str) or not isinstance(values, list):
            raise ActionError("Each context item slot list must contain Palette items.")
        if len(values) > MAX_CONTEXT_SLOT_ACTIONS:
            raise ActionError(
                f"Each context can have at most {MAX_CONTEXT_SLOT_ACTIONS} Palette items."
            )
        parsed_item_slots[context] = _parse_item_references(
            values,
            f'Palette context item slots for "{context}"',
        )
    return PaletteState(
        tuple(pinned),
        focus.strip() or "General",
        parsed_slots,
        context_membership_version,
        parsed_item_slots,
    )


def save_palette_state(path: Path, state: PaletteState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "pinned_action_ids": list(state.pinned_action_ids[:5]),
        "focus_context": state.focus_context,
        "context_slots": {
            context: list(ids[:MAX_CONTEXT_SLOT_ACTIONS])
            for context, ids in (state.context_slots or {}).items()
        },
    }
    if state.context_item_slots:
        data["context_item_slots"] = {
            context: [
                palette_item_reference_data(reference)
                for reference in references[:MAX_CONTEXT_SLOT_ACTIONS]
            ]
            for context, references in state.context_item_slots.items()
        }
    if state.context_membership_version:
        data["context_membership_version"] = state.context_membership_version
    atomic_write_json(path, data)


def action_slots(actions: list[Action], state: PaletteState) -> dict[int, Action]:
    by_id = {action.id: action for action in actions}
    result: dict[int, Action] = {}
    for slot, reference in palette_item_slots(actions, state).items():
        action = by_id.get(reference.action_id)
        if action is not None:
            result[slot] = action
    return result


def palette_item_slots(
    actions: list[Action],
    state: PaletteState,
) -> dict[int, PaletteItemReference]:
    by_id = {action.id: action for action in actions}
    result: dict[int, PaletteItemReference] = {}

    configured_items = (state.context_item_slots or {}).get(state.focus_context)
    if configured_items is None:
        configured = (state.context_slots or {}).get(state.focus_context, ())
        context_items = [
            PaletteItemReference(action_id=action_id)
            for action_id in configured
            if action_id in by_id
        ]
    else:
        context_items = [
            reference
            for reference in configured_items
            if not reference.action_id or reference.action_id in by_id
        ]
    context_actions = [
        by_id[reference.action_id]
        for reference in context_items
        if reference.action_id and reference.action_id in by_id
    ]
    used_ids = {action.id for action in context_actions}
    context_fallbacks = [
        action
        for action in actions
        if action.id not in used_ids
        and action.belongs_to_context(state.focus_context)
    ]
    context_items.extend(
        PaletteItemReference(action_id=action.id)
        for action in context_fallbacks[: MAX_CONTEXT_SLOT_ACTIONS - len(context_items)]
    )
    for slot, reference in zip(
        CONTEXT_SLOT_NUMBERS,
        context_items[:MAX_CONTEXT_SLOT_ACTIONS],
    ):
        result[slot] = reference
    return result


def _parse_item_references(
    values: list[object],
    label: str,
) -> tuple[PaletteItemReference, ...]:
    references: list[PaletteItemReference] = []
    for index, raw in enumerate(values, start=1):
        if not isinstance(raw, dict):
            raise ActionError(f"{label}, item #{index} is invalid.")
        target_type = raw.get("type")
        if target_type == "action":
            if set(raw) != {"type", "action_id"} or not isinstance(
                raw.get("action_id"), str
            ):
                raise ActionError(f"{label}, item #{index} is invalid.")
            try:
                reference = PaletteItemReference(action_id=raw["action_id"])
            except ValueError as exc:
                raise ActionError(f"{label}, item #{index}: {exc}") from exc
        elif target_type == "work_item":
            if set(raw) != {"type", "source_id", "relative_folder"} or not all(
                isinstance(raw.get(field), str)
                for field in ("source_id", "relative_folder")
            ):
                raise ActionError(f"{label}, item #{index} is invalid.")
            try:
                work_item = WorkItemReference(
                    raw["source_id"],
                    raw["relative_folder"],
                )
            except WorkItemDiscoveryError as exc:
                raise ActionError(f"{label}, item #{index}: {exc}") from exc
            reference = PaletteItemReference(work_item_ref=work_item)
        else:
            raise ActionError(f"{label}, item #{index} has an unknown type.")
        if reference not in references:
            references.append(reference)
    return tuple(references)
