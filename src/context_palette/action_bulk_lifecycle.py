"""Read-only review plans and guarded bulk Action deletion commits."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .action_deletion import (
    ActionDeletionError,
    ActionDeletionReport,
    action_deletion_configuration_fingerprint,
    delete_actions_and_references,
    inspect_action_references_many,
)
from .action_sequences import dependent_sequences
from .actions import Action, ActionError, load_combined_stored_actions
from .configuration_mutation import configuration_mutation_gate


class BulkActionLifecycleError(ValueError):
    """Raised when a bulk Action deletion review or commit is not safe."""


@dataclass(frozen=True, slots=True)
class BulkActionLifecyclePaths:
    shared_actions_path: Path
    local_actions_path: Path
    shared_contexts_path: Path
    local_contexts_path: Path
    shared_command_surface_path: Path
    local_command_surface_path: Path
    palette_path: Path

    @property
    def context_paths(self) -> tuple[Path, ...]:
        return (self.shared_contexts_path, self.local_contexts_path)

    @property
    def command_surface_paths(self) -> tuple[Path, ...]:
        return (
            self.shared_command_surface_path,
            self.local_command_surface_path,
        )

    @property
    def sequence_paths(self) -> tuple[Path, ...]:
        return (self.shared_actions_path, self.local_actions_path)

    @property
    def participant_paths(self) -> tuple[Path, ...]:
        return tuple(
            dict.fromkeys(
                (
                    self.shared_actions_path,
                    self.local_actions_path,
                    *self.context_paths,
                    *self.command_surface_paths,
                    self.palette_path,
                )
            )
        )


@dataclass(frozen=True, slots=True)
class BulkActionLifecycleCandidate:
    action: Action
    status: str
    messages: tuple[str, ...] = ()
    blocking_sequence_ids: tuple[str, ...] = ()

    @property
    def action_id(self) -> str:
        return self.action.id

    @property
    def title(self) -> str:
        return self.action.title

    @property
    def state(self) -> str:
        return self.action.state


@dataclass(frozen=True, slots=True)
class BulkActionLifecyclePlan:
    action_ids: tuple[str, ...]
    candidates: tuple[BulkActionLifecycleCandidate, ...]
    impact: ActionDeletionReport
    configuration_fingerprint: str
    paths: BulkActionLifecyclePaths

    @property
    def can_commit(self) -> bool:
        return bool(self.candidates) and all(
            candidate.status == "Ready" for candidate in self.candidates
        )


def eligible_personal_actions_for_deletion(
    actions: Iterable[Action],
    local_action_ids: Iterable[str],
) -> tuple[Action, ...]:
    """Return all stored personal Actions eligible for direct deletion."""

    local_keys = {
        action_id.casefold()
        for action_id in local_action_ids
        if isinstance(action_id, str) and action_id
    }
    return tuple(
        action
        for action in actions
        if action.id.casefold() in local_keys
    )


def plan_bulk_action_deletion(
    action_ids: Iterable[str],
    *,
    paths: BulkActionLifecyclePaths,
) -> BulkActionLifecyclePlan:
    """Build an exact, read-only personal-Action deletion review."""

    requested_ids = _validated_action_ids(action_ids)
    with configuration_mutation_gate():
        fingerprint_before = _configuration_fingerprint(paths.participant_paths)
        try:
            actions, local_action_ids = load_combined_stored_actions(
                paths.shared_actions_path,
                paths.local_actions_path,
                inspect_external_paths=False,
            )
            selected = _selected_personal_actions(
                requested_ids,
                actions,
                local_action_ids,
            )
            candidates = _lifecycle_candidates(
                selected,
                actions,
            )
            reference_impact = inspect_action_references_many(
                (action.id for action in selected),
                context_paths=paths.context_paths,
                command_surface_paths=paths.command_surface_paths,
                palette_path=paths.palette_path,
            )
        except (ActionError, ActionDeletionError, OSError) as exc:
            raise BulkActionLifecycleError(str(exc)) from exc
        fingerprint_after = _configuration_fingerprint(paths.participant_paths)
        if fingerprint_before != fingerprint_after:
            raise BulkActionLifecycleError(
                "Saved Actions or assignments changed while the review was being prepared. Review them again."
            )

    return BulkActionLifecyclePlan(
        action_ids=tuple(action.id for action in selected),
        candidates=candidates,
        impact=ActionDeletionReport(
            reference_impact.references_removed,
            reference_impact.buttons_removed,
            reference_impact.files_changed + 1,
        ),
        configuration_fingerprint=fingerprint_after,
        paths=paths,
    )


def commit_bulk_action_deletion(
    plan: BulkActionLifecyclePlan,
) -> ActionDeletionReport:
    """Commit one unchanged reviewed deletion plan in a single transaction."""

    if not isinstance(plan, BulkActionLifecyclePlan):
        raise BulkActionLifecycleError("A reviewed Action deletion plan is required.")
    if not plan.can_commit:
        raise BulkActionLifecycleError(
            "The selected Actions include sequence dependencies that must be deleted too or resolved first."
        )

    with configuration_mutation_gate():
        refreshed = plan_bulk_action_deletion(
            plan.action_ids,
            paths=plan.paths,
        )
        if (
            refreshed.configuration_fingerprint
            != plan.configuration_fingerprint
            or refreshed.action_ids != plan.action_ids
        ):
            raise BulkActionLifecycleError(
                "Saved Actions or assignments changed after review. Review the selection again before continuing."
            )
        if not refreshed.can_commit:
            raise BulkActionLifecycleError(
                "Sequence dependencies changed after review. Review the selection again before continuing."
            )
        if refreshed.impact != plan.impact:
            raise BulkActionLifecycleError(
                "The current saved-placement effect does not match the reviewed "
                "deletion impact. Review the Actions again; no configuration "
                "changes were made."
            )

        try:
            report = delete_actions_and_references(
                plan.paths.local_actions_path,
                plan.action_ids,
                context_paths=plan.paths.context_paths,
                command_surface_paths=plan.paths.command_surface_paths,
                palette_path=plan.paths.palette_path,
                sequence_paths=plan.paths.sequence_paths,
                expected_report=plan.impact,
                expected_configuration_fingerprint=(
                    plan.configuration_fingerprint
                ),
            )
        except (ActionDeletionError, OSError) as exc:
            raise BulkActionLifecycleError(str(exc)) from exc

    return report


def _selected_personal_actions(
    requested_ids: tuple[str, ...],
    actions: Iterable[Action],
    local_action_ids: Iterable[str],
) -> tuple[Action, ...]:
    action_by_key = {action.id.casefold(): action for action in actions}
    local_keys = {action_id.casefold() for action_id in local_action_ids}
    selected: list[Action] = []
    missing: list[str] = []
    built_in: list[str] = []
    for action_id in requested_ids:
        action = action_by_key.get(action_id.casefold())
        if action is None:
            missing.append(action_id)
        elif action.id.casefold() not in local_keys:
            built_in.append(action.title)
        else:
            selected.append(action)
    if missing:
        raise BulkActionLifecycleError(
            "Actions were not found: " + ", ".join(missing)
        )
    if built_in:
        raise BulkActionLifecycleError(
            "Bulk Action removal is limited to personal Actions: "
            + ", ".join(built_in)
        )

    return tuple(selected)


def _lifecycle_candidates(
    selected: tuple[Action, ...],
    actions: Iterable[Action],
) -> tuple[BulkActionLifecycleCandidate, ...]:
    selected_keys = {action.id.casefold() for action in selected}
    candidates: list[BulkActionLifecycleCandidate] = []
    for action in selected:
        blockers = tuple(
            sequence
            for sequence in dependent_sequences(
                actions,
                action.id,
                include_archived=True,
            )
            if sequence.id.casefold() not in selected_keys
        )
        if blockers:
            labels = ", ".join(sequence.title for sequence in blockers)
            messages = (
                "Also select these dependent sequences, or edit them first: "
                + labels,
            )
            status = "Blocked"
        else:
            messages = ()
            status = "Ready"
        candidates.append(
            BulkActionLifecycleCandidate(
                action,
                status,
                messages,
                tuple(sequence.id for sequence in blockers),
            )
        )
    return tuple(candidates)


def _validated_action_ids(action_ids: Iterable[str]) -> tuple[str, ...]:
    selected: list[str] = []
    seen: set[str] = set()
    for action_id in action_ids:
        if not isinstance(action_id, str) or not action_id.strip():
            raise BulkActionLifecycleError("Action IDs must be non-empty text.")
        key = action_id.casefold()
        if key in seen:
            raise BulkActionLifecycleError(
                f"Action was selected more than once: {action_id}"
            )
        seen.add(key)
        selected.append(action_id)
    if not selected:
        raise BulkActionLifecycleError("Select at least one Action.")
    return tuple(selected)


def _configuration_fingerprint(paths: Iterable[Path]) -> str:
    try:
        return action_deletion_configuration_fingerprint(paths)
    except ActionDeletionError as exc:
        raise BulkActionLifecycleError(str(exc)) from exc
