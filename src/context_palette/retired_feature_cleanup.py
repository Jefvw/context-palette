from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys

from .persistence import atomic_write_json


RETIRED_ACTION_TYPES = frozenset({"window_layout", "restore_window_snapshot"})
RETIRED_ACTION_IDS = frozenset({"developing-arrange-three-explorers"})


class RetirementCleanupError(Exception):
    """Raised when obsolete local references cannot be migrated safely."""


@dataclass(frozen=True)
class RetirementCleanupReport:
    actions_removed: int = 0
    references_removed: int = 0
    files_changed: int = 0


def cleanup_retired_local_configuration(root: Path) -> RetirementCleanupReport:
    data = root / "data"
    actions_path = data / "local_actions.json"
    removed_ids = set(RETIRED_ACTION_IDS)
    actions_removed = 0
    references_removed = 0
    files_changed = 0

    actions_data = _read_optional_object(actions_path)
    if actions_data is not None:
        actions = actions_data.get("actions")
        if not isinstance(actions, list):
            raise RetirementCleanupError("Local action file must contain an 'actions' list.")
        retained_actions: list[object] = []
        for action in actions:
            if isinstance(action, dict) and action.get("type") in RETIRED_ACTION_TYPES:
                action_id = action.get("id")
                if isinstance(action_id, str):
                    removed_ids.add(action_id)
                actions_removed += 1
            else:
                retained_actions.append(action)
        if len(retained_actions) != len(actions):
            actions_data["actions"] = retained_actions
            atomic_write_json(actions_path, actions_data)
            files_changed += 1

    for path, cleaner in (
        (data / "local_contexts.json", _clean_context_references),
        (data / "local_command_surface.json", _clean_command_references),
        (data / "palette.json", _clean_palette_references),
    ):
        content = _read_optional_object(path)
        if content is None:
            continue
        cleaned, removed = cleaner(content, removed_ids)
        if removed:
            atomic_write_json(path, cleaned)
            references_removed += removed
            files_changed += 1

    return RetirementCleanupReport(actions_removed, references_removed, files_changed)


def _read_optional_object(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RetirementCleanupError(f"{path.name} is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise RetirementCleanupError(f"{path.name} must contain a JSON object.")
    return value


def _clean_context_references(
    data: dict[str, object],
    removed_ids: set[str],
) -> tuple[dict[str, object], int]:
    contexts = data.get("contexts")
    if not isinstance(contexts, list):
        raise RetirementCleanupError("Local context file must contain a 'contexts' list.")
    removed = 0
    for context in contexts:
        if not isinstance(context, dict):
            continue
        preferred = context.get("preferred_action_ids")
        if not isinstance(preferred, list):
            continue
        retained = [value for value in preferred if value not in removed_ids]
        removed += len(preferred) - len(retained)
        context["preferred_action_ids"] = retained
    return data, removed


def _clean_command_references(
    data: dict[str, object],
    removed_ids: set[str],
) -> tuple[dict[str, object], int]:
    groups = data.get("groups")
    if not isinstance(groups, list):
        raise RetirementCleanupError("Local command-surface file must contain a 'groups' list.")
    removed = 0
    retained_groups: list[object] = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("items"), list):
            retained_groups.append(group)
            continue
        retained_items: list[object] = []
        for item in group["items"]:
            if not isinstance(item, dict):
                retained_items.append(item)
                continue
            action_ids = item.get("action_ids")
            if isinstance(action_ids, list):
                retained_ids = [value for value in action_ids if value not in removed_ids]
                removed += len(action_ids) - len(retained_ids)
                item["action_ids"] = retained_ids
            primary = item.get("primary_action_id")
            if isinstance(primary, str) and primary in removed_ids:
                removed += 1
                item["primary_action_id"] = (
                    item["action_ids"][0]
                    if isinstance(item.get("action_ids"), list) and item["action_ids"]
                    else ""
                )
            if item.get("primary_action_id") or item.get("action_ids"):
                retained_items.append(item)
        group["items"] = retained_items
        if retained_items:
            retained_groups.append(group)
    data["groups"] = retained_groups
    return data, removed


def _clean_palette_references(
    data: dict[str, object],
    removed_ids: set[str],
) -> tuple[dict[str, object], int]:
    removed = 0
    pinned = data.get("pinned_action_ids")
    if isinstance(pinned, list):
        retained = [value for value in pinned if value not in removed_ids]
        removed += len(pinned) - len(retained)
        data["pinned_action_ids"] = retained
    slots = data.get("context_slots")
    if isinstance(slots, dict):
        for context, action_ids in slots.items():
            if not isinstance(action_ids, list):
                continue
            retained = [value for value in action_ids if value not in removed_ids]
            removed += len(action_ids) - len(retained)
            slots[context] = retained
    return data, removed


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    try:
        report = cleanup_retired_local_configuration(root)
    except RetirementCleanupError as exc:
        print(f"ERROR: Retired-feature cleanup failed: {exc}")
        return 1
    if report.files_changed:
        print(
            "Removed retired local configuration: "
            f"{report.actions_removed} action(s), "
            f"{report.references_removed} reference(s), "
            f"{report.files_changed} file(s)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
