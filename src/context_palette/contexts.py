from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


class ContextError(Exception):
    """Raised when configured context data is invalid."""


@dataclass(frozen=True)
class ContextDefinition:
    name: str
    description: str = ""
    technology: str = ""
    task: str = ""
    preferred_action_ids: tuple[str, ...] = ()


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
    if len(clean_ids) > 4:
        raise ContextError(f"Context #{index} may define at most four preferred actions.")
    return ContextDefinition(name=name.strip(), preferred_action_ids=clean_ids, **text_fields)
