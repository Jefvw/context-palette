"""Pure review planning and guarded persistence for bulk Action updates.

The update workbook owns the bounded OOXML boundary.  This module maps its
verified rows back onto existing personal Active Actions, explains the exact
semantic fields that would change, and rechecks both the workbook and saved
configuration while holding the shared configuration mutation gate.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable

from .action_sequences import sequence_steps_to_data
from .action_types import ACTION_TYPES
from .action_update_workbook import (
    ELIGIBLE_ACTION_TYPES,
    ActionUpdateWorkbook,
    ActionUpdateWorkbookError,
    ActionUpdateWorkbookRow,
    action_record_fingerprint,
    read_action_update_workbook,
)
from .actions import (
    ACTIVE_STATE,
    Action,
    ActionError,
    edited_configured_action,
    load_combined_stored_actions,
    validate_context_memberships,
)
from .configuration_data import load_contexts
from .configuration_mutation import configuration_mutation_gate
from .context_membership import (
    ContextMembershipUpdateError,
    actions_with_canonical_contexts,
    update_actions_with_context_memberships,
)
from .contexts import ContextDefinition, ContextError


ARGUMENT_ACTION_TYPES = frozenset({"launch_app", "open_windows_target"})
WORKING_FOLDER_ACTION_TYPES = frozenset({"launch_app", "open_windows_target"})


class BulkActionUpdateError(ValueError):
    """Raised when a reviewed Action update cannot be planned or committed."""

    def __init__(
        self,
        message: str,
        *,
        rollback_completed: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.rollback_completed = rollback_completed


class BulkActionUpdateEffectsUnknownError(BulkActionUpdateError):
    """Raised when a failed update may have left configuration changes."""

    def __init__(self, message: str) -> None:
        super().__init__(message, rollback_completed=False)


@dataclass(frozen=True, slots=True)
class BulkActionUpdateCandidate:
    row_number: int
    action_id: str
    original_action: Action | None
    action: Action | None
    status: str
    changed_fields: tuple[str, ...]
    messages: tuple[str, ...]
    selected_by_default: bool


@dataclass(frozen=True, slots=True)
class BulkActionUpdatePlan:
    source_path: Path
    source_digest: str
    candidates: tuple[BulkActionUpdateCandidate, ...]
    existing_signature: str


def eligible_personal_actions_for_update(
    actions: Iterable[Action],
    local_action_ids: Iterable[str],
) -> tuple[Action, ...]:
    """Return personal Active Actions supported by update workbook version 1."""

    local_keys = {
        action_id.casefold()
        for action_id in local_action_ids
        if isinstance(action_id, str) and action_id
    }
    return tuple(
        action
        for action in actions
        if action.id.casefold() in local_keys
        and action.state == ACTIVE_STATE
        and action.type in ELIGIBLE_ACTION_TYPES
    )


def plan_bulk_action_update(
    workbook: ActionUpdateWorkbook,
    existing_actions: Iterable[Action],
    local_action_ids: Iterable[str],
    local_context_names: Iterable[str],
) -> BulkActionUpdatePlan:
    """Validate workbook rows and classify their exact semantic changes."""

    existing = tuple(existing_actions)
    eligible = eligible_personal_actions_for_update(existing, local_action_ids)
    originals = {action.id.casefold(): action for action in eligible}
    contexts = tuple(local_context_names)
    candidates: list[BulkActionUpdateCandidate] = []
    seen_ids: dict[str, int] = {}

    for row in workbook.rows:
        key = row.action_id.casefold()
        duplicate_row = seen_ids.get(key)
        seen_ids.setdefault(key, row.row_number)
        original = originals.get(key)
        if duplicate_row is not None:
            candidates.append(
                _error_candidate(
                    row,
                    original,
                    f"This Action also appears in workbook row {duplicate_row}.",
                )
            )
            continue
        if original is None:
            candidates.append(
                _error_candidate(
                    row,
                    None,
                    "This row does not identify an eligible personal Active Action.",
                )
            )
            continue
        identity_error = _identity_error(row, original)
        if identity_error:
            candidates.append(_error_candidate(row, original, identity_error))
            continue
        try:
            updated = _updated_action_from_row(
                row,
                original,
                existing,
                contexts,
            )
        except (ActionError, BulkActionUpdateError, OSError) as exc:
            candidates.append(_error_candidate(row, original, str(exc)))
            continue

        changed_fields = _changed_fields(original, updated)
        if changed_fields:
            status = "Ready"
            messages = (
                "Will update: " + ", ".join(changed_fields) + ".",
            )
            selected_by_default = True
        else:
            status = "No changes"
            messages = ("This row matches the saved Action.",)
            selected_by_default = False
        candidates.append(
            BulkActionUpdateCandidate(
                row.row_number,
                original.id,
                original,
                updated,
                status,
                changed_fields,
                messages,
                selected_by_default,
            )
        )

    return BulkActionUpdatePlan(
        workbook.path,
        workbook.digest,
        tuple(candidates),
        _actions_signature(existing),
    )


def commit_bulk_action_update(
    plan: BulkActionUpdatePlan,
    selected_row_numbers: Iterable[int],
    local_actions_path: Path,
    shared_actions_path: Path,
    shared_contexts_path: Path,
    local_contexts_path: Path,
) -> tuple[Action, ...]:
    """Apply selected reviewed changes once after guarded revalidation."""

    selected = frozenset(selected_row_numbers)
    if not selected:
        raise BulkActionUpdateError("Select at least one changed Action to update.")
    if any(isinstance(number, bool) or not isinstance(number, int) for number in selected):
        raise BulkActionUpdateError(
            "Selected workbook row numbers must be whole numbers."
        )

    # A later configuration change must never promote a row the user reviewed
    # as an error or no-op into an update.  Revalidation below may only keep a
    # previously Ready row Ready or reject it as stale.
    _selected_ready_candidates(plan.candidates, selected)

    with configuration_mutation_gate():
        current_actions, current_local_ids, local_context_names = _load_current_state(
            shared_actions_path,
            local_actions_path,
            shared_contexts_path,
            local_contexts_path,
        )
        if _actions_signature(current_actions) != plan.existing_signature:
            raise BulkActionUpdateError(
                "The saved Actions changed after review. Review the workbook again before updating Actions."
            )

        eligible = eligible_personal_actions_for_update(
            current_actions,
            current_local_ids,
        )
        try:
            current_workbook = read_action_update_workbook(
                plan.source_path,
                eligible,
            )
        except (ActionUpdateWorkbookError, OSError) as exc:
            raise BulkActionUpdateError(
                f"The reviewed workbook is no longer valid: {exc}"
            ) from exc
        if current_workbook.digest != plan.source_digest:
            raise BulkActionUpdateError(
                "The workbook changed after review. Review it again before updating Actions."
            )
        refreshed = plan_bulk_action_update(
            current_workbook,
            current_actions,
            current_local_ids,
            local_context_names,
        )
        chosen_candidates = _selected_ready_candidates(
            refreshed.candidates,
            selected,
        )

        updated = tuple(
            candidate.action
            for candidate in chosen_candidates
            if candidate.action is not None
        )
        previous = tuple(
            candidate.original_action
            for candidate in chosen_candidates
            if candidate.original_action is not None
        )
        try:
            update_actions_with_context_memberships(
                local_actions_path,
                updated,
                previous,
                actions_are_local=True,
                shared_contexts_path=shared_contexts_path,
                local_contexts_path=local_contexts_path,
            )
        except ContextMembershipUpdateError as exc:
            if not exc.rollback_completed:
                raise BulkActionUpdateEffectsUnknownError(
                    "The Actions update failed and automatic rollback was "
                    "incomplete. Saved Actions or Contexts may have changed. "
                    "Do not retry this workbook. Inspect the latest backup and "
                    "Diagnostics before making more configuration changes.\n\n"
                    f"Details: {exc}"
                ) from exc
            raise BulkActionUpdateError(
                f"The Actions could not be updated: {exc}",
                rollback_completed=True,
            ) from exc
        except (ActionError, ContextError, OSError) as exc:
            raise BulkActionUpdateError(
                f"The Actions could not be updated: {exc}"
            ) from exc
        return updated


def _selected_ready_candidates(
    candidates: Iterable[BulkActionUpdateCandidate],
    selected: frozenset[int],
) -> tuple[BulkActionUpdateCandidate, ...]:
    candidates_by_row = {candidate.row_number: candidate for candidate in candidates}
    unknown = sorted(selected - candidates_by_row.keys())
    if unknown:
        raise BulkActionUpdateError(
            "Selected workbook rows were not part of the reviewed plan: "
            + ", ".join(str(number) for number in unknown)
        )
    chosen = tuple(candidates_by_row[number] for number in sorted(selected))
    unavailable = tuple(
        candidate.row_number
        for candidate in chosen
        if candidate.status != "Ready"
        or candidate.action is None
        or candidate.original_action is None
    )
    if unavailable:
        raise BulkActionUpdateError(
            "These workbook rows do not contain a reviewed change that can be updated: "
            + ", ".join(str(number) for number in unavailable)
        )
    return chosen


def _error_candidate(
    row: ActionUpdateWorkbookRow,
    original: Action | None,
    message: str,
) -> BulkActionUpdateCandidate:
    return BulkActionUpdateCandidate(
        row.row_number,
        row.action_id,
        original,
        None,
        "Error",
        (),
        (message,),
        False,
    )


def _identity_error(
    row: ActionUpdateWorkbookRow,
    original: Action,
) -> str:
    if row.action_id != original.id:
        return "Action ID was changed. Export a fresh workbook."
    if row.state != original.state:
        return "State is not editable in this workbook."
    if row.action_type != original.type:
        return "Action type is not editable in this workbook."
    if row.original_fingerprint != action_record_fingerprint(original):
        return "The original Action fingerprint no longer matches. Export a fresh workbook."
    return ""


def _updated_action_from_row(
    row: ActionUpdateWorkbookRow,
    original: Action,
    existing_actions: tuple[Action, ...],
    local_context_names: tuple[str, ...],
) -> Action:
    if row.arguments and original.type not in ARGUMENT_ACTION_TYPES:
        raise BulkActionUpdateError(
            f"Arguments are not supported for {ACTION_TYPES[original.type].label} Actions."
        )
    if row.working_folder and original.type not in WORKING_FOLDER_ACTION_TYPES:
        raise BulkActionUpdateError(
            "Working folder is supported only for Run an application and "
            "Open or run a Windows target Actions."
        )
    contexts = validate_context_memberships(row.contexts, local_context_names)
    validated = edited_configured_action(
        original,
        title=row.name,
        context="General",
        action_type=original.type,
        value=row.value,
        technology=original.technology,
        task=original.task,
        contexts=contexts,
        tags=row.tags,
        arguments=row.arguments,
        working_directory=row.working_folder,
        description=row.description,
        quick_action_path=row.quick_menu,
        sequence_steps=original.sequence_steps,
        available_actions=existing_actions,
    )
    # The ordinary editor is the type-aware canonicalization boundary. Preserve
    # exact stored text only when that workbook field was not edited; otherwise
    # the reviewed After record must be the same canonical record that will be
    # durable and executable after reload.
    return replace(
        validated,
        title=(original.title if row.name == original.title else validated.title),
        value=(original.value if row.value == original.value else validated.value),
        arguments=(
            original.arguments
            if row.arguments == original.arguments
            else validated.arguments
        ),
        working_directory=(
            original.working_directory
            if row.working_folder == (original.working_directory or "")
            else validated.working_directory
        ),
        technology=original.technology,
        task=original.task,
        description=(
            original.description
            if row.description == original.description
            else validated.description
        ),
    )


def _changed_fields(original: Action, updated: Action) -> tuple[str, ...]:
    comparisons = (
        ("Name", original.title, updated.title),
        ("Value", original.value, updated.value),
        ("Contexts", original.effective_contexts, updated.effective_contexts),
        ("Tags", original.effective_tags, updated.effective_tags),
        ("Description", original.description, updated.description),
        ("Quick menu", original.quick_action_path, updated.quick_action_path),
        ("Arguments", original.arguments, updated.arguments),
        (
            "Working folder",
            original.working_directory or "",
            updated.working_directory or "",
        ),
    )
    return tuple(label for label, before, after in comparisons if before != after)


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
    payload = json.dumps(
        records,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _load_current_state(
    shared_actions_path: Path,
    local_actions_path: Path,
    shared_contexts_path: Path,
    local_contexts_path: Path,
) -> tuple[tuple[Action, ...], set[str], tuple[str, ...]]:
    try:
        actions, local_ids = load_combined_stored_actions(
            shared_actions_path,
            local_actions_path,
            inspect_external_paths=False,
        )
        shared_contexts = tuple(load_contexts(shared_contexts_path))
        local_contexts: tuple[ContextDefinition, ...] = (
            tuple(load_contexts(local_contexts_path))
            if local_contexts_path.exists()
            else ()
        )
        canonical = tuple(
            actions_with_canonical_contexts(
                actions,
                (*shared_contexts, *local_contexts),
            )
        )
        return canonical, local_ids, tuple(
            context.name for context in local_contexts
        )
    except (ActionError, ContextError, OSError) as exc:
        raise BulkActionUpdateError(
            f"Saved Actions could not be rechecked: {exc}"
        ) from exc
