from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .palette_items import PaletteItemReference, palette_item_reference_data
from .palette_state import MAX_CONTEXT_SLOT_ACTIONS
from .work_items import WorkItemDiscoveryError, WorkItemReference


class ContextError(Exception):
    """Raised when configured context data is invalid."""


@dataclass(frozen=True)
class ContextDefinition:
    name: str
    description: str = ""
    technology: str = ""
    task: str = ""
    preferred_action_ids: tuple[str, ...] = ()
    action_ids: tuple[str, ...] | None = None
    work_item_refs: tuple[WorkItemReference, ...] = ()
    preferred_item_refs: tuple[PaletteItemReference, ...] = ()

    @property
    def preferred_items(self) -> tuple[PaletteItemReference, ...]:
        if self.preferred_item_refs:
            return self.preferred_item_refs
        return tuple(
            PaletteItemReference(action_id=action_id)
            for action_id in self.preferred_action_ids
        )

    @property
    def member_items(self) -> tuple[PaletteItemReference, ...]:
        members = [
            PaletteItemReference(action_id=action_id)
            for action_id in (self.action_ids or ())
        ]
        members.extend(
            PaletteItemReference(work_item_ref=reference)
            for reference in self.work_item_refs
        )
        for reference in self.preferred_items:
            if reference not in members:
                members.append(reference)
        return tuple(dict.fromkeys(members))


def load_contexts(path: Path) -> list[ContextDefinition]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContextError(f"Context file was not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContextError(f"Context file is not valid JSON: {path}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("contexts"), list):
        raise ContextError("Context file must contain a 'contexts' list.")
    return [_parse_context(item, index) for index, item in enumerate(raw["contexts"], 1)]


def load_combined_contexts(shared_path: Path, local_path: Path) -> list[ContextDefinition]:
    contexts = load_contexts(shared_path)
    if any(
        context.work_item_refs
        or any(item.work_item_ref is not None for item in context.preferred_items)
        for context in contexts
    ):
        raise ContextError("Built-in contexts cannot reference personal Work Items.")
    if local_path.exists():
        contexts += load_contexts(local_path)
    names: set[str] = set()
    for context in contexts:
        key = context.name.casefold()
        if key in names:
            raise ContextError(f"Duplicate configured context: {context.name}")
        names.add(key)
    return contexts


def _parse_context(item: object, index: int) -> ContextDefinition:
    if not isinstance(item, dict):
        raise ContextError(f"Context #{index} must be an object.")
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ContextError(f"Context #{index} needs a name.")
    text_fields = {}
    for field in ("description", "technology", "task"):
        value = item.get(field, "")
        if not isinstance(value, str):
            raise ContextError(f"Context #{index} has invalid {field}.")
        text_fields[field] = value.strip()
    preferred = item.get("preferred_action_ids", [])
    if not isinstance(preferred, list) or not all(isinstance(value, str) for value in preferred):
        raise ContextError(f"Context #{index} has invalid preferred_action_ids.")
    clean_ids = tuple(value.strip() for value in preferred if value.strip())
    if len(clean_ids) > MAX_CONTEXT_SLOT_ACTIONS:
        raise ContextError(
            f"Context #{index} may define at most "
            f"{MAX_CONTEXT_SLOT_ACTIONS} preferred actions."
        )
    members = item.get("action_ids")
    if members is None:
        clean_members = None
    elif not isinstance(members, list) or not all(
        isinstance(value, str) for value in members
    ):
        raise ContextError(f"Context #{index} has invalid action_ids.")
    else:
        clean_members = tuple(
            dict.fromkeys(value.strip() for value in members if value.strip())
        )
    work_item_refs = _parse_work_item_references(
        item.get("work_item_refs", []),
        f"Context #{index} work_item_refs",
    )
    preferred_items = _parse_preferred_items(
        item.get("preferred_items"),
        f"Context #{index} preferred_items",
    )
    if len(preferred_items or clean_ids) > MAX_CONTEXT_SLOT_ACTIONS:
        raise ContextError(
            f"Context #{index} may define at most "
            f"{MAX_CONTEXT_SLOT_ACTIONS} preferred items."
        )
    if preferred_items:
        clean_ids = tuple(
            reference.action_id
            for reference in preferred_items
            if reference.action_id
        )
    return ContextDefinition(
        name=name.strip(),
        preferred_action_ids=clean_ids,
        action_ids=clean_members,
        work_item_refs=work_item_refs,
        preferred_item_refs=preferred_items,
        **text_fields,
    )


def context_definition_data(context: ContextDefinition) -> dict[str, object]:
    data: dict[str, object] = {"name": context.name}
    for field in ("description", "technology", "task"):
        value = getattr(context, field)
        if value:
            data[field] = value
    if context.preferred_item_refs:
        data["preferred_items"] = [
            palette_item_reference_data(reference)
            for reference in context.preferred_items
        ]
    elif context.preferred_action_ids:
        data["preferred_action_ids"] = list(context.preferred_action_ids)
    if context.action_ids is not None:
        data["action_ids"] = list(context.action_ids)
    if context.work_item_refs:
        data["work_item_refs"] = [
            {
                "source_id": reference.source_id,
                "relative_folder": reference.relative_folder,
            }
            for reference in context.work_item_refs
        ]
    return data


def _parse_work_item_references(
    value: object,
    label: str,
) -> tuple[WorkItemReference, ...]:
    if not isinstance(value, list):
        raise ContextError(f"{label} must be a list.")
    references: list[WorkItemReference] = []
    for position, raw in enumerate(value, start=1):
        if not isinstance(raw, dict) or set(raw) != {"source_id", "relative_folder"}:
            raise ContextError(f"{label} item #{position} is invalid.")
        if not all(isinstance(raw[field], str) for field in raw):
            raise ContextError(f"{label} item #{position} is invalid.")
        try:
            reference = WorkItemReference(raw["source_id"], raw["relative_folder"])
        except WorkItemDiscoveryError as exc:
            raise ContextError(f"{label} item #{position}: {exc}") from exc
        if reference not in references:
            references.append(reference)
    return tuple(references)


def _parse_preferred_items(
    value: object,
    label: str,
) -> tuple[PaletteItemReference, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ContextError(f"{label} must be a list.")
    references: list[PaletteItemReference] = []
    for position, raw in enumerate(value, start=1):
        if not isinstance(raw, dict):
            raise ContextError(f"{label} item #{position} is invalid.")
        target_type = raw.get("type")
        if target_type == "action":
            if set(raw) != {"type", "action_id"} or not isinstance(
                raw.get("action_id"), str
            ):
                raise ContextError(f"{label} item #{position} is invalid.")
            try:
                reference = PaletteItemReference(action_id=raw["action_id"])
            except ValueError as exc:
                raise ContextError(f"{label} item #{position}: {exc}") from exc
        elif target_type == "work_item":
            work_items = _parse_work_item_references(
                [
                    {
                        "source_id": raw.get("source_id"),
                        "relative_folder": raw.get("relative_folder"),
                    }
                ],
                f"{label} item #{position}",
            )
            if set(raw) != {"type", "source_id", "relative_folder"}:
                raise ContextError(f"{label} item #{position} is invalid.")
            reference = PaletteItemReference(work_item_ref=work_items[0])
        else:
            raise ContextError(f"{label} item #{position} has an unknown type.")
        if reference not in references:
            references.append(reference)
    return tuple(references)
