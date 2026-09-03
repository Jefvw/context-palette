"""Reviewed, transactional organization for automatic Quick-menu paths.

Automatic Passwords, Folders, and Prompts menus derive their hierarchy from
the owning Action's ``quick_action_path``.  This service changes only that
field: it never deletes an Action, executes an Action, or touches its target.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path

from .actions import (
    ACTION_BOUND_QUICK_TYPES,
    ACTIVE_STATE,
    Action,
    ActionError,
    load_combined_stored_actions,
    normalize_quick_action_path,
    update_actions,
)
from .configuration_mutation import configuration_mutation_gate
from .persistence import atomic_replace_bytes


ASSIGN_OPERATION = "assign"
MOVE_BRANCH_OPERATION = "move_branch"


class QuickMenuOrganizationError(ValueError):
    """Raised when automatic Quick-menu organization cannot complete safely."""

    def __init__(
        self,
        message: str,
        *,
        rollback_completed: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.rollback_completed = rollback_completed


@dataclass(frozen=True, slots=True)
class QuickMenuOrganizationChange:
    action_id: str
    action_type: str
    state: str
    storage: str
    before_path: tuple[str, ...]
    after_path: tuple[str, ...]
    action: Action


@dataclass(frozen=True, slots=True)
class QuickMenuOrganizationPlan:
    operation: str
    action_type: str
    shared_actions_path: Path
    local_actions_path: Path
    requested_action_ids: tuple[str, ...]
    requested_source_prefix: tuple[str, ...]
    source_prefix: tuple[str, ...]
    requested_destination_path: tuple[str, ...]
    destination_path: tuple[str, ...]
    matched_action_ids: tuple[str, ...]
    changes: tuple[QuickMenuOrganizationChange, ...]
    affected_action_ids: tuple[str, ...]
    shared_action_count: int
    local_action_count: int
    active_action_count: int
    files_to_write: int
    destination_merged: bool
    canonicalization_applied: bool
    fingerprint: str


@dataclass(frozen=True, slots=True)
class QuickMenuOrganizationResult:
    affected_action_ids: tuple[str, ...]
    shared_action_count: int
    local_action_count: int
    active_action_count: int
    files_written: int
    updated_actions: tuple[Action, ...]


@dataclass(frozen=True, slots=True)
class _LoadedActionState:
    actions: tuple[Action, ...]
    local_action_ids: frozenset[str]
    shared_bytes: bytes | None
    local_bytes: bytes | None


def plan_quick_menu_assignment(
    action_ids: Iterable[str],
    destination_path: Iterable[str],
    *,
    shared_actions_path: Path,
    local_actions_path: Path,
) -> QuickMenuOrganizationPlan:
    """Plan assigning selected same-type Actions to one exact menu path."""

    with configuration_mutation_gate():
        return _plan_assignment(
            action_ids,
            destination_path,
            shared_actions_path=Path(shared_actions_path),
            local_actions_path=Path(local_actions_path),
        )


def plan_quick_menu_branch_move(
    action_type: str,
    source_prefix: Iterable[str],
    destination_prefix: Iterable[str],
    *,
    shared_actions_path: Path,
    local_actions_path: Path,
) -> QuickMenuOrganizationPlan:
    """Plan moving or renaming every Action below one branch prefix."""

    with configuration_mutation_gate():
        return _plan_branch_move(
            action_type,
            source_prefix,
            destination_prefix,
            shared_actions_path=Path(shared_actions_path),
            local_actions_path=Path(local_actions_path),
        )


def commit_quick_menu_organization(
    plan: QuickMenuOrganizationPlan,
) -> QuickMenuOrganizationResult:
    """Commit one unchanged reviewed plan with exact-byte rollback."""

    if not isinstance(plan, QuickMenuOrganizationPlan):
        raise QuickMenuOrganizationError("A reviewed Quick-menu plan is required.")

    with configuration_mutation_gate():
        if plan.operation == ASSIGN_OPERATION:
            refreshed = _plan_assignment(
                plan.requested_action_ids,
                plan.requested_destination_path,
                shared_actions_path=plan.shared_actions_path,
                local_actions_path=plan.local_actions_path,
            )
        elif plan.operation == MOVE_BRANCH_OPERATION:
            refreshed = _plan_branch_move(
                plan.action_type,
                plan.requested_source_prefix,
                plan.requested_destination_path,
                shared_actions_path=plan.shared_actions_path,
                local_actions_path=plan.local_actions_path,
            )
        else:
            raise QuickMenuOrganizationError(
                "The reviewed Quick-menu operation is unsupported."
            )

        if refreshed.fingerprint != plan.fingerprint:
            raise QuickMenuOrganizationError(
                "Actions changed after review. Review the Quick-menu change again "
                "before applying it."
            )

        writes = _writes_for_changes(refreshed)
        if not writes:
            return _result_from_plan(refreshed, files_written=0)

        originals = _snapshot_unchanged_action_files(refreshed, writes)
        attempted: list[Path] = []
        try:
            for path, actions in writes:
                attempted.append(path)
                update_actions(path, actions)
        except Exception as exc:
            rollback_errors = _restore_attempted_files(attempted, originals)
            if rollback_errors:
                raise QuickMenuOrganizationError(
                    "Quick-menu organization failed and automatic rollback was "
                    "incomplete: " + "; ".join(rollback_errors),
                    rollback_completed=False,
                ) from exc
            raise QuickMenuOrganizationError(
                "Quick-menu organization failed; all attempted Action-file "
                "changes were restored.",
                rollback_completed=True,
            ) from exc

        return _result_from_plan(refreshed, files_written=len(writes))


def _plan_assignment(
    action_ids: Iterable[str],
    destination_path: Iterable[str],
    *,
    shared_actions_path: Path,
    local_actions_path: Path,
) -> QuickMenuOrganizationPlan:
    _require_distinct_storage_paths(shared_actions_path, local_actions_path)
    requested_destination = _validated_path(
        destination_path,
        label="Destination path",
        allow_empty=True,
    )
    state = _load_action_state(shared_actions_path, local_actions_path)
    selected = _resolve_selected_actions(action_ids, state.actions)
    action_types = {action.type for action in selected}
    if len(action_types) != 1:
        raise QuickMenuOrganizationError(
            "Selected Actions must all belong to the same automatic menu type."
        )
    action_type = next(iter(action_types))
    _validate_action_type(action_type)

    selected_keys = {action.id.casefold() for action in selected}
    unaffected_paths = [
        action.quick_action_path
        for action in state.actions
        if action.type == action_type
        and action.state == ACTIVE_STATE
        and action.id.casefold() not in selected_keys
    ]
    canonical_destination = _canonicalize_path(
        requested_destination,
        unaffected_paths,
    )
    changes = tuple(
        _change_for_action(action, canonical_destination, state.local_action_ids)
        for action in selected
        if action.quick_action_path != canonical_destination
    )
    requested_ids = tuple(action.id for action in selected)
    return _build_plan(
        operation=ASSIGN_OPERATION,
        action_type=action_type,
        shared_actions_path=shared_actions_path,
        local_actions_path=local_actions_path,
        requested_action_ids=requested_ids,
        requested_source_prefix=(),
        source_prefix=(),
        requested_destination_path=requested_destination,
        destination_path=canonical_destination,
        matched_action_ids=requested_ids,
        changes=changes,
        destination_merged=_branch_exists(
            unaffected_paths,
            canonical_destination,
        ),
        canonicalization_applied=(
            canonical_destination != requested_destination
        ),
        state=state,
    )


def _plan_branch_move(
    action_type: str,
    source_prefix: Iterable[str],
    destination_prefix: Iterable[str],
    *,
    shared_actions_path: Path,
    local_actions_path: Path,
) -> QuickMenuOrganizationPlan:
    _require_distinct_storage_paths(shared_actions_path, local_actions_path)
    _validate_action_type(action_type)
    requested_source = _validated_path(
        source_prefix,
        label="Source branch",
        allow_empty=False,
    )
    requested_destination = _validated_path(
        destination_prefix,
        label="Destination path",
        allow_empty=True,
    )
    source_keys = _path_key(requested_source)
    destination_keys = _path_key(requested_destination)
    if (
        source_keys != destination_keys
        and destination_keys[: len(source_keys)] == source_keys
    ):
        raise QuickMenuOrganizationError(
            "A Quick-menu branch cannot be moved inside itself."
        )

    state = _load_action_state(shared_actions_path, local_actions_path)
    same_type = tuple(
        action
        for action in state.actions
        if action.type == action_type and action.state == ACTIVE_STATE
    )
    all_paths = [action.quick_action_path for action in same_type]
    canonical_source = _canonicalize_path(requested_source, all_paths)
    matched = tuple(
        action
        for action in same_type
        if _has_prefix(action.quick_action_path, canonical_source)
    )
    if not matched:
        raise QuickMenuOrganizationError(
            "The source branch does not contain any stored Actions."
        )

    matched_keys = {action.id.casefold() for action in matched}
    unaffected_paths = [
        action.quick_action_path
        for action in same_type
        if action.id.casefold() not in matched_keys
    ]
    canonical_destination = _canonicalize_path(
        requested_destination,
        unaffected_paths,
    )
    destination_merged = _branch_exists(
        unaffected_paths,
        canonical_destination,
    ) or _promoted_child_branch_merges(
        matched_paths=(action.quick_action_path for action in matched),
        source_prefix=canonical_source,
        destination_prefix=canonical_destination,
        unaffected_paths=unaffected_paths,
    )
    established_paths = list(unaffected_paths)
    changes_list: list[QuickMenuOrganizationChange] = []
    suffix_canonicalized = False
    for action in matched:
        suffix = action.quick_action_path[len(canonical_source) :]
        raw_after = (*canonical_destination, *suffix)
        if len(raw_after) > 3:
            raise QuickMenuOrganizationError(
                f'Moving branch "{_display_path(canonical_source)}" to '
                f'"{_display_path(canonical_destination)}" would make Action '
                f'"{action.title}" exceed the three-level Quick-menu limit.'
            )
        after = _canonicalize_path(raw_after, established_paths)
        suffix_canonicalized = suffix_canonicalized or after != raw_after
        established_paths.append(after)
        if after != action.quick_action_path:
            changes_list.append(
                _change_for_action(action, after, state.local_action_ids)
            )

    return _build_plan(
        operation=MOVE_BRANCH_OPERATION,
        action_type=action_type,
        shared_actions_path=shared_actions_path,
        local_actions_path=local_actions_path,
        requested_action_ids=(),
        requested_source_prefix=requested_source,
        source_prefix=canonical_source,
        requested_destination_path=requested_destination,
        destination_path=canonical_destination,
        matched_action_ids=tuple(action.id for action in matched),
        changes=tuple(changes_list),
        destination_merged=destination_merged,
        canonicalization_applied=(
            canonical_source != requested_source
            or canonical_destination != requested_destination
            or suffix_canonicalized
        ),
        state=state,
    )


def _build_plan(
    *,
    operation: str,
    action_type: str,
    shared_actions_path: Path,
    local_actions_path: Path,
    requested_action_ids: tuple[str, ...],
    requested_source_prefix: tuple[str, ...],
    source_prefix: tuple[str, ...],
    requested_destination_path: tuple[str, ...],
    destination_path: tuple[str, ...],
    matched_action_ids: tuple[str, ...],
    changes: tuple[QuickMenuOrganizationChange, ...],
    destination_merged: bool,
    canonicalization_applied: bool,
    state: _LoadedActionState,
) -> QuickMenuOrganizationPlan:
    affected_ids = tuple(change.action_id for change in changes)
    shared_count = sum(change.storage == "shared" for change in changes)
    local_count = sum(change.storage == "local" for change in changes)
    active_count = sum(change.state == ACTIVE_STATE for change in changes)
    fingerprint = _plan_fingerprint(
        operation=operation,
        action_type=action_type,
        shared_actions_path=shared_actions_path,
        local_actions_path=local_actions_path,
        requested_action_ids=requested_action_ids,
        requested_source_prefix=requested_source_prefix,
        requested_destination_path=requested_destination_path,
        shared_bytes=state.shared_bytes,
        local_bytes=state.local_bytes,
    )
    return QuickMenuOrganizationPlan(
        operation=operation,
        action_type=action_type,
        shared_actions_path=shared_actions_path,
        local_actions_path=local_actions_path,
        requested_action_ids=requested_action_ids,
        requested_source_prefix=requested_source_prefix,
        source_prefix=source_prefix,
        requested_destination_path=requested_destination_path,
        destination_path=destination_path,
        matched_action_ids=matched_action_ids,
        changes=changes,
        affected_action_ids=affected_ids,
        shared_action_count=shared_count,
        local_action_count=local_count,
        active_action_count=active_count,
        files_to_write=int(bool(shared_count)) + int(bool(local_count)),
        destination_merged=destination_merged,
        canonicalization_applied=canonicalization_applied,
        fingerprint=fingerprint,
    )


def _load_action_state(
    shared_actions_path: Path,
    local_actions_path: Path,
) -> _LoadedActionState:
    before_shared = _read_optional_bytes(shared_actions_path)
    before_local = _read_optional_bytes(local_actions_path)
    try:
        actions, local_ids = load_combined_stored_actions(
            shared_actions_path,
            local_actions_path,
            inspect_external_paths=False,
        )
    except (ActionError, OSError) as exc:
        raise QuickMenuOrganizationError(
            f"Stored Actions could not be reviewed: {exc}"
        ) from exc
    after_shared = _read_optional_bytes(shared_actions_path)
    after_local = _read_optional_bytes(local_actions_path)
    if before_shared != after_shared or before_local != after_local:
        raise QuickMenuOrganizationError(
            "Action files changed while they were being reviewed. Try again."
        )
    return _LoadedActionState(
        tuple(actions),
        frozenset(local_ids),
        after_shared,
        after_local,
    )


def _resolve_selected_actions(
    action_ids: Iterable[str],
    actions: tuple[Action, ...],
) -> tuple[Action, ...]:
    if isinstance(action_ids, (str, bytes)):
        raise QuickMenuOrganizationError("Choose one or more stored Actions.")
    requested: list[str] = []
    requested_keys: set[str] = set()
    for raw_id in action_ids:
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise QuickMenuOrganizationError("Action IDs must be non-empty text.")
        key = raw_id.strip().casefold()
        if key in requested_keys:
            raise QuickMenuOrganizationError(
                f"Action was selected more than once: {raw_id.strip()}"
            )
        requested_keys.add(key)
        requested.append(raw_id.strip())
    if not requested:
        raise QuickMenuOrganizationError("Choose one or more stored Actions.")

    available = {action.id.casefold(): action for action in actions}
    missing = [action_id for action_id in requested if action_id.casefold() not in available]
    if missing:
        raise QuickMenuOrganizationError(
            "Selected Actions were not found: " + ", ".join(missing)
        )
    selected = tuple(
        action for action in actions if action.id.casefold() in requested_keys
    )
    legacy_inactive = tuple(
        action.title for action in selected if action.state != ACTIVE_STATE
    )
    if legacy_inactive:
        raise QuickMenuOrganizationError(
            "Legacy inactive Actions can only be deleted: "
            + ", ".join(legacy_inactive)
        )
    return selected


def _validated_path(
    values: Iterable[str],
    *,
    label: str,
    allow_empty: bool,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise QuickMenuOrganizationError(f"{label} must be a sequence of levels.")
    raw = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in raw):
        raise QuickMenuOrganizationError(
            f"{label} cannot contain an empty menu level."
        )
    try:
        path = normalize_quick_action_path(raw)
    except ActionError as exc:
        raise QuickMenuOrganizationError(str(exc)) from exc
    if not allow_empty and not path:
        raise QuickMenuOrganizationError(f"{label} cannot be the menu root.")
    return path


def _validate_action_type(action_type: str) -> None:
    if action_type not in ACTION_BOUND_QUICK_TYPES:
        raise QuickMenuOrganizationError(
            "Quick-menu organization supports only Password, Folder, and AI prompt Actions."
        )


def _canonicalize_path(
    requested: tuple[str, ...],
    existing_paths: Iterable[tuple[str, ...]],
) -> tuple[str, ...]:
    existing = tuple(existing_paths)
    output: list[str] = []
    for depth, requested_level in enumerate(requested):
        prefix = tuple(value.casefold() for value in output)
        canonical = requested_level
        for path in existing:
            if len(path) <= depth:
                continue
            if tuple(value.casefold() for value in path[:depth]) != prefix:
                continue
            if path[depth].casefold() == requested_level.casefold():
                canonical = path[depth]
                break
        output.append(canonical)
    return tuple(output)


def _change_for_action(
    action: Action,
    after_path: tuple[str, ...],
    local_action_ids: frozenset[str],
) -> QuickMenuOrganizationChange:
    storage = "local" if action.id in local_action_ids else "shared"
    return QuickMenuOrganizationChange(
        action_id=action.id,
        action_type=action.type,
        state=action.state,
        storage=storage,
        before_path=action.quick_action_path,
        after_path=after_path,
        action=replace(action, quick_action_path=after_path),
    )


def _writes_for_changes(
    plan: QuickMenuOrganizationPlan,
) -> tuple[tuple[Path, tuple[Action, ...]], ...]:
    shared = tuple(
        change.action for change in plan.changes if change.storage == "shared"
    )
    local = tuple(
        change.action for change in plan.changes if change.storage == "local"
    )
    writes: list[tuple[Path, tuple[Action, ...]]] = []
    if shared:
        writes.append((plan.shared_actions_path, shared))
    if local:
        writes.append((plan.local_actions_path, local))
    return tuple(writes)


def _snapshot_unchanged_action_files(
    plan: QuickMenuOrganizationPlan,
    writes: tuple[tuple[Path, tuple[Action, ...]], ...],
) -> dict[Path, bytes | None]:
    shared_bytes = _read_optional_bytes(plan.shared_actions_path)
    local_bytes = _read_optional_bytes(plan.local_actions_path)
    snapshot_fingerprint = _plan_fingerprint(
        operation=plan.operation,
        action_type=plan.action_type,
        shared_actions_path=plan.shared_actions_path,
        local_actions_path=plan.local_actions_path,
        requested_action_ids=plan.requested_action_ids,
        requested_source_prefix=plan.requested_source_prefix,
        requested_destination_path=plan.requested_destination_path,
        shared_bytes=shared_bytes,
        local_bytes=local_bytes,
    )
    if snapshot_fingerprint != plan.fingerprint:
        raise QuickMenuOrganizationError(
            "Actions changed after review. Review the Quick-menu change again "
            "before applying it."
        )

    primary_bytes = {
        plan.shared_actions_path: shared_bytes,
        plan.local_actions_path: local_bytes,
    }
    originals: dict[Path, bytes | None] = {}
    for path, _actions in writes:
        originals[path] = primary_bytes[path]
        backup = path.with_name(path.name + ".bak")
        originals[backup] = _read_optional_bytes(backup)

    if (
        _read_optional_bytes(plan.shared_actions_path) != shared_bytes
        or _read_optional_bytes(plan.local_actions_path) != local_bytes
    ):
        raise QuickMenuOrganizationError(
            "Actions changed after review. Review the Quick-menu change again "
            "before applying it."
        )
    return originals


def _restore_attempted_files(
    attempted: Iterable[Path],
    originals: dict[Path, bytes | None],
) -> list[str]:
    errors: list[str] = []
    for action_path in reversed(tuple(attempted)):
        for path in (action_path, action_path.with_name(action_path.name + ".bak")):
            try:
                payload = originals[path]
                if payload is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_replace_bytes(path, payload, preserve_previous=False)
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
    return errors


def _result_from_plan(
    plan: QuickMenuOrganizationPlan,
    *,
    files_written: int,
) -> QuickMenuOrganizationResult:
    return QuickMenuOrganizationResult(
        affected_action_ids=plan.affected_action_ids,
        shared_action_count=plan.shared_action_count,
        local_action_count=plan.local_action_count,
        active_action_count=plan.active_action_count,
        files_written=files_written,
        updated_actions=tuple(change.action for change in plan.changes),
    )


def _plan_fingerprint(
    *,
    operation: str,
    action_type: str,
    shared_actions_path: Path,
    local_actions_path: Path,
    requested_action_ids: tuple[str, ...],
    requested_source_prefix: tuple[str, ...],
    requested_destination_path: tuple[str, ...],
    shared_bytes: bytes | None,
    local_bytes: bytes | None,
) -> str:
    record = {
        "operation": operation,
        "action_type": action_type,
        "shared_actions_path": str(shared_actions_path.resolve()),
        "local_actions_path": str(local_actions_path.resolve()),
        "requested_action_ids": list(requested_action_ids),
        "requested_source_prefix": list(requested_source_prefix),
        "requested_destination_path": list(requested_destination_path),
        "shared_file": _file_identity(shared_bytes),
        "local_file": _file_identity(local_bytes),
    }
    payload = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + sha256(payload).hexdigest()


def _file_identity(payload: bytes | None) -> dict[str, object]:
    return {
        "exists": payload is not None,
        "size": len(payload) if payload is not None else 0,
        "digest": sha256(payload).hexdigest() if payload is not None else "",
    }


def _read_optional_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise QuickMenuOrganizationError(
            f"Action file could not be read: {path}"
        ) from exc


def _require_distinct_storage_paths(shared_path: Path, local_path: Path) -> None:
    if str(shared_path.resolve()).casefold() == str(local_path.resolve()).casefold():
        raise QuickMenuOrganizationError(
            "Shared and personal Action storage must use different files."
        )


def _path_key(path: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(value.casefold() for value in path)


def _has_prefix(path: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    return _path_key(path[: len(prefix)]) == _path_key(prefix)


def _branch_exists(
    paths: Iterable[tuple[str, ...]],
    branch: tuple[str, ...],
) -> bool:
    if not branch:
        return any(not path for path in paths)
    return any(_has_prefix(path, branch) for path in paths)


def _promoted_child_branch_merges(
    *,
    matched_paths: Iterable[tuple[str, ...]],
    source_prefix: tuple[str, ...],
    destination_prefix: tuple[str, ...],
    unaffected_paths: Iterable[tuple[str, ...]],
) -> bool:
    """Detect child-branch collisions when a branch is promoted to menu root."""

    if destination_prefix:
        return False
    promoted_children = {
        path[len(source_prefix)].casefold()
        for path in matched_paths
        if len(path) > len(source_prefix)
    }
    existing_root_children = {
        path[0].casefold()
        for path in unaffected_paths
        if path
    }
    return bool(promoted_children & existing_root_children)


def _display_path(path: tuple[str, ...]) -> str:
    return " > ".join(path) if path else "menu root"
