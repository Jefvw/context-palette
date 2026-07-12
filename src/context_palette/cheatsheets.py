from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .actions import Action, draft_copy_text_action


class CheatSheetError(Exception):
    """Raised when a cheat sheet cannot be loaded."""


@dataclass(frozen=True)
class CheatSheetItem:
    label: str
    detail: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class CheatSheetSection:
    title: str
    items: tuple[CheatSheetItem, ...]


@dataclass(frozen=True)
class CheatSheet:
    id: str
    title: str
    kind: str
    aliases: tuple[str, ...]
    summary: str
    updated_at: str
    sections: tuple[CheatSheetSection, ...]


def load_cheatsheets(directory: Path) -> list[CheatSheet]:
    if not directory.exists():
        return []

    sheets = []
    for path in sorted(directory.glob("*.json")):
        sheets.append(load_cheatsheet(path))
    return sheets


def load_cheatsheet(path: Path) -> CheatSheet:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CheatSheetError(f"Cheat sheet is not valid JSON: {path}") from exc

    if not isinstance(raw, dict):
        raise CheatSheetError(f"Cheat sheet must be an object: {path}")

    required = ["id", "title", "kind", "summary", "updated_at"]
    missing = [field for field in required if not isinstance(raw.get(field), str)]
    if missing:
        raise CheatSheetError(f"Cheat sheet is missing text fields: {', '.join(missing)}")

    aliases = raw.get("aliases", [])
    if not isinstance(aliases, list) or not all(isinstance(alias, str) for alias in aliases):
        raise CheatSheetError("Cheat sheet aliases must be a list of text values.")

    sections = raw.get("sections", [])
    if not isinstance(sections, list):
        raise CheatSheetError("Cheat sheet sections must be a list.")

    return CheatSheet(
        id=raw["id"],
        title=raw["title"],
        kind=raw["kind"],
        aliases=tuple(aliases),
        summary=raw["summary"],
        updated_at=raw["updated_at"],
        sections=tuple(_section_from_raw(section, index) for index, section in enumerate(sections, start=1)),
    )


def _section_from_raw(raw: object, index: int) -> CheatSheetSection:
    if not isinstance(raw, dict):
        raise CheatSheetError(f"Cheat sheet section #{index} must be an object.")
    if not isinstance(raw.get("title"), str):
        raise CheatSheetError(f"Cheat sheet section #{index} is missing a title.")

    items = raw.get("items", [])
    if not isinstance(items, list):
        raise CheatSheetError(f"Cheat sheet section #{index} items must be a list.")

    return CheatSheetSection(
        title=raw["title"],
        items=tuple(_item_from_raw(item, item_index) for item_index, item in enumerate(items, start=1)),
    )


def _item_from_raw(raw: object, index: int) -> CheatSheetItem:
    if not isinstance(raw, dict):
        raise CheatSheetError(f"Cheat sheet item #{index} must be an object.")
    if not isinstance(raw.get("label"), str) or not isinstance(raw.get("detail"), str):
        raise CheatSheetError(f"Cheat sheet item #{index} is missing label or detail.")

    tags = raw.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise CheatSheetError(f"Cheat sheet item #{index} tags must be a list of text values.")

    return CheatSheetItem(label=raw["label"], detail=raw["detail"], tags=tuple(tags))


def filter_cheatsheet(sheet: CheatSheet, query: str) -> CheatSheet:
    terms = [term.casefold() for term in query.split() if term.strip()]
    if not terms:
        return sheet

    matched_sections = []
    for section in sheet.sections:
        section_text = section.title.casefold()
        matched_items = []
        for item in section.items:
            item_text = " ".join([item.label, item.detail, *item.tags]).casefold()
            combined = f"{section_text} {item_text}"
            if all(term in combined for term in terms):
                matched_items.append(item)

        if matched_items:
            matched_sections.append(
                CheatSheetSection(title=section.title, items=tuple(matched_items))
            )

    return CheatSheet(
        id=sheet.id,
        title=sheet.title,
        kind=sheet.kind,
        aliases=sheet.aliases,
        summary=sheet.summary,
        updated_at=sheet.updated_at,
        sections=tuple(matched_sections),
    )


def draft_action_from_cheatsheet_item(sheet: CheatSheet, item: CheatSheetItem) -> Action:
    return draft_copy_text_action(
        title=item.label,
        context=sheet.title,
        value=f"{item.label}: {item.detail}",
    )
