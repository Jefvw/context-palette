"""Pure planning and guarded persistence for spreadsheet Action creation.

The workbook reader owns the bounded OOXML boundary.  This module converts its
typed rows into ordinary validated personal Actions, explains duplicates, and
keeps the final write tied to the exact workbook and Action collection that the
user reviewed.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable

from .action_sequences import sequence_steps_to_data
from .action_types import ACTION_TYPES
from .action_workbook import ActionWorkbook, ActionWorkbookRow, workbook_digest
from .actions import (
    Action,
    ActionError,
    configured_action,
    load_combined_stored_actions,
    validate_context_memberships,
)
from .configuration_data import load_contexts
from .context_membership import (
    actions_with_canonical_contexts,
    append_actions_with_context_memberships,
)
from .contexts import ContextError


EXCLUDED_BULK_TYPES = frozenset(
    {"sequence", "excel_automation", "transform_file_text"}
)
ARGUMENT_ACTION_TYPES = frozenset({"launch_app", "open_windows_target"})
WORKING_FOLDER_ACTION_TYPES = frozenset({"launch_app", "open_windows_target"})


class BulkActionError(ValueError):
    """Raised when a reviewed bulk-create plan is no longer safe to commit."""


@dataclass(frozen=True, slots=True)
class BulkActionCandidate:
    row_number: int
    action: Action | None
    status: str
    messages: tuple[str, ...]
    selected_by_default: bool


@dataclass(frozen=True, slots=True)
class BulkActionPlan:
    source_path: Path
    source_digest: str
    candidates: tuple[BulkActionCandidate, ...]
    existing_signature: str


def plan_bulk_action_create(
    workbook: ActionWorkbook,
    existing_actions: Iterable[Action],
    local_context_names: Iterable[str],
) -> BulkActionPlan:
    """Validate included workbook rows and classify create-only candidates."""

    existing = tuple(existing_actions)
    contexts = tuple(local_context_names)
    candidates: list[BulkActionCandidate] = []
    prior_records: dict[tuple[object, ...], int] = {}
    prior_effects: dict[tuple[object, ...], int] = {}

    existing_records = {_record_key(action) for action in existing}
    existing_effects = {_effect_key(action) for action in existing}

    for row in workbook.rows:
        if not row.include:
            candidates.append(
                BulkActionCandidate(
                    row_number=row.row_number,
                    action=None,
                    status="Not selected",
                    messages=("The workbook marks this row not to be imported.",),
                    selected_by_default=False,
                )
            )
            continue
        try:
            action = _action_from_row(row, existing, contexts)
        except (ActionError, BulkActionError) as exc:
            candidates.append(
                BulkActionCandidate(
                    row_number=row.row_number,
                    action=None,
                    status="Error",
                    messages=(str(exc),),
                    selected_by_default=False,
                )
            )
            continue

        record_key = _record_key(action)
        effect_key = _effect_key(action)
        if record_key in existing_records:
            candidate = BulkActionCandidate(
                row.row_number,
                action,
                "Already exists",
                ("An identical Action already exists.",),
                False,
            )
        elif effect_key in existing_effects:
            candidate = BulkActionCandidate(
                row.row_number,
                action,
                "Possible duplicate",
                (
                    "An existing Action has the same effect. Select this row "
                    "explicitly only if a second Action is intentional.",
                ),
                False,
            )
        elif record_key in prior_records:
            candidate = BulkActionCandidate(
                row.row_number,
                action,
                "Warning",
                (
                    f"This row duplicates workbook row {prior_records[record_key]}; "
                    "only one identical Action can be created.",
                ),
                False,
            )
        elif effect_key in prior_effects:
            candidate = BulkActionCandidate(
                row.row_number,
                action,
                "Warning",
                (
                    f"This row has the same effect as workbook row "
                    f"{prior_effects[effect_key]}. Select it explicitly only if "
                    "both named Actions are intentional.",
                ),
                False,
            )
        else:
            candidate = BulkActionCandidate(
                row.row_number,
                action,
                "Ready",
                (),
                True,
            )
        candidates.append(candidate)
        prior_records.setdefault(record_key, row.row_number)
        prior_effects.setdefault(effect_key, row.row_number)

    return BulkActionPlan(
        source_path=workbook.path,
        source_digest=workbook.digest,
        candidates=tuple(candidates),
        existing_signature=_actions_signature(existing),
    )


def commit_bulk_action_create(
    plan: BulkActionPlan,
    selected_row_numbers: Iterable[int],
    local_actions_path: Path,
    shared_actions_path: Path,
    shared_contexts_path: Path,
    local_contexts_path: Path,
) -> tuple[Action, ...]:
    """Append explicitly selected reviewed Actions in one guarded mutation."""

    selected = frozenset(selected_row_numbers)
    if not selected:
        raise BulkActionError("Select at least one Action to create.")
    if any(isinstance(number, bool) or not isinstance(number, int) for number in selected):
        raise BulkActionError("Selected workbook row numbers must be whole numbers.")

    try:
        current_digest = workbook_digest(plan.source_path)
    except (OSError, ValueError) as exc:
        raise BulkActionError(f"The reviewed workbook can no longer be read: {exc}") from exc
    if current_digest != plan.source_digest:
        raise BulkActionError(
            "The workbook changed after review. Review it again before creating Actions."
        )

    current_actions = _load_current_actions(
        shared_actions_path,
        local_actions_path,
        shared_contexts_path,
        local_contexts_path,
    )
    candidates_by_row = {candidate.row_number: candidate for candidate in plan.candidates}
    unknown = sorted(selected - candidates_by_row.keys())
    if unknown:
        raise BulkActionError(
            "Selected workbook rows were not part of the reviewed plan: "
            + ", ".join(str(number) for number in unknown)
        )

    chosen_candidates = tuple(candidates_by_row[number] for number in sorted(selected))
    unavailable = [
        candidate.row_number
        for candidate in chosen_candidates
        if candidate.action is None or candidate.status in {"Error", "Already exists"}
    ]
    if unavailable:
        raise BulkActionError(
            "These workbook rows cannot be created: "
            + ", ".join(str(number) for number in unavailable)
        )

    chosen = tuple(candidate.action for candidate in chosen_candidates if candidate.action)
    _reject_duplicate_selection(chosen)

    current_records = {_record_key(action) for action in current_actions}
    now_duplicates = [
        action.title for action in chosen if _record_key(action) in current_records
    ]
    if now_duplicates:
        raise BulkActionError(
            "One or more reviewed Actions now already exist: "
            + ", ".join(now_duplicates)
            + ". Review the workbook again."
        )
    if _actions_signature(current_actions) != plan.existing_signature:
        raise BulkActionError(
            "The saved Actions changed after review. Review the workbook again before creating Actions."
        )

    try:
        append_actions_with_context_memberships(
            local_actions_path,
            chosen,
            actions_are_local=True,
            shared_contexts_path=shared_contexts_path,
            local_contexts_path=local_contexts_path,
            create_missing_local_contexts=False,
        )
    except (ActionError, ContextError, OSError) as exc:
        raise BulkActionError(f"The Actions could not be created: {exc}") from exc
    return chosen


def _action_from_row(
    row: ActionWorkbookRow,
    existing_actions: tuple[Action, ...],
    local_context_names: tuple[str, ...],
) -> Action:
    action_type = _resolve_action_type(row.action_type)
    if action_type in EXCLUDED_BULK_TYPES:
        raise BulkActionError(
            f"{ACTION_TYPES[action_type].label} Actions cannot be created in bulk."
        )
    if row.arguments and action_type not in ARGUMENT_ACTION_TYPES:
        raise BulkActionError(
            f"Arguments are not supported for {ACTION_TYPES[action_type].label} Actions."
        )
    if row.working_folder and action_type not in WORKING_FOLDER_ACTION_TYPES:
        raise BulkActionError(
            "Working folder is supported only for Run an application and "
            "Open or run a Windows target Actions."
        )
    contexts = validate_context_memberships(row.contexts, local_context_names)
    return configured_action(
        title=row.name,
        context="General",
        action_type=action_type,
        value=row.value,
        contexts=contexts,
        tags=row.tags,
        arguments=row.arguments,
        working_directory=row.working_folder,
        description=row.description,
        quick_action_path=row.quick_menu,
        available_actions=existing_actions,
    )


def _resolve_action_type(value: str) -> str:
    clean = value.strip()
    if clean in ACTION_TYPES:
        return clean
    key = clean.casefold()
    matches = [
        action_type
        for action_type, definition in ACTION_TYPES.items()
        if key in {definition.label.casefold(), definition.display_label.casefold()}
    ]
    if len(matches) == 1:
        return matches[0]
    raise BulkActionError(f"Unknown Action type: {clean or '(blank)'}")


def _record_key(action: Action) -> tuple[object, ...]:
    return (
        action.title.strip().casefold(),
        *_effect_key(action),
        tuple(sorted(context.casefold() for context in action.effective_contexts)),
        tuple(sorted(action.effective_tags)),
        action.description.strip(),
        tuple(level.casefold() for level in action.quick_action_path),
    )


def _effect_key(action: Action) -> tuple[object, ...]:
    return (
        action.type,
        action.value.strip(),
        tuple(action.arguments),
        (action.working_directory or "").strip(),
        tuple(
            tuple(sorted(step.items()))
            for step in sequence_steps_to_data(action.sequence_steps)
        ),
    )


def _actions_signature(actions: Iterable[Action]) -> str:
    records = [
        {
            "id": action.id,
            "title": action.title,
            "type": action.type,
            "value": action.value,
            "state": action.state,
            "arguments": list(action.arguments),
            "working_directory": action.working_directory,
            "contexts": list(action.effective_contexts),
            "tags": list(action.effective_tags),
            "description": action.description,
            "quick_action_path": list(action.quick_action_path),
            "sequence_steps": sequence_steps_to_data(action.sequence_steps),
        }
        for action in actions
    ]
    records.sort(key=lambda item: (str(item["id"]).casefold(), str(item["id"])))
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _load_current_actions(
    shared_actions_path: Path,
    local_actions_path: Path,
    shared_contexts_path: Path,
    local_contexts_path: Path,
) -> tuple[Action, ...]:
    try:
        actions, _local_ids = load_combined_stored_actions(
            shared_actions_path,
            local_actions_path,
            inspect_external_paths=False,
        )
        definitions = list(load_contexts(shared_contexts_path))
        if local_contexts_path.exists():
            definitions.extend(load_contexts(local_contexts_path))
        return tuple(actions_with_canonical_contexts(actions, definitions))
    except (ActionError, ContextError, OSError) as exc:
        raise BulkActionError(f"Saved Actions could not be rechecked: {exc}") from exc


def _reject_duplicate_selection(actions: tuple[Action, ...]) -> None:
    records: set[tuple[object, ...]] = set()
    for action in actions:
        key = _record_key(action)
        if key in records:
            raise BulkActionError(
                "The selected rows contain an identical Action more than once."
            )
        records.add(key)
