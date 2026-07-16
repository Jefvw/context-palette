from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from .persistence import atomic_write_json


class InboxError(Exception):
    """Raised when an inbox item cannot be saved or loaded."""


@dataclass(frozen=True)
class InboxItem:
    id: str
    title: str
    content: str
    source: str
    created_at: str
    state: str = "Inbox"
    suggested_context: str = ""


def create_clipboard_item(
    *,
    title: str,
    content: str,
    suggested_context: str = "",
    now: datetime | None = None,
) -> InboxItem:
    clean_title = title.strip()
    clean_content = content.strip()
    if not clean_title:
        raise InboxError("Capture title cannot be empty.")
    if not clean_content:
        raise InboxError("Clipboard text is empty.")

    timestamp = (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    return InboxItem(
        id=f"inbox-{uuid4().hex[:12]}",
        title=clean_title,
        content=clean_content,
        source="clipboard",
        created_at=timestamp,
        suggested_context=suggested_context.strip(),
    )


def append_inbox_item(path: Path, item: InboxItem) -> None:
    data = _load_inbox_data(path)
    data["items"].append(_item_to_dict(item))
    atomic_write_json(path, data)


def update_inbox_item_state(path: Path, item_id: str, state: str) -> None:
    data = _load_inbox_data(path)
    changed = False
    for raw_item in data["items"]:
        if isinstance(raw_item, dict) and raw_item.get("id") == item_id:
            raw_item["state"] = state
            changed = True
            break

    if not changed:
        raise InboxError(f"Inbox item was not found: {item_id}")

    atomic_write_json(path, data)


def load_inbox_items(path: Path) -> list[InboxItem]:
    data = _load_inbox_data(path)
    return [_item_from_dict(raw_item, index) for index, raw_item in enumerate(data["items"], start=1)]


def _load_inbox_data(path: Path) -> dict[str, list[object]]:
    if not path.exists():
        return {"items": []}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InboxError(f"Inbox file is not valid JSON: {path}") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise InboxError("Inbox file must contain an 'items' list.")
    return raw


def _item_to_dict(item: InboxItem) -> dict[str, str]:
    return {
        "id": item.id,
        "title": item.title,
        "content": item.content,
        "source": item.source,
        "created_at": item.created_at,
        "state": item.state,
        "suggested_context": item.suggested_context,
    }


def _item_from_dict(raw: object, index: int) -> InboxItem:
    if not isinstance(raw, dict):
        raise InboxError(f"Inbox item #{index} must be an object.")

    required = ["id", "title", "content", "source", "created_at", "state", "suggested_context"]
    missing = [field for field in required if not isinstance(raw.get(field), str)]
    if missing:
        raise InboxError(f"Inbox item #{index} is missing text fields: {', '.join(missing)}")

    return InboxItem(
        id=raw["id"],
        title=raw["title"],
        content=raw["content"],
        source=raw["source"],
        created_at=raw["created_at"],
        state=raw["state"],
        suggested_context=raw["suggested_context"],
    )
