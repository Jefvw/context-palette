from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from .actions import (
    Action,
    ActionError,
    append_actions,
    delete_actions,
    load_stored_actions,
    update_action,
)
from .configuration_data import save_contexts
from .configuration_mutation import gated_configuration_mutation
from .contexts import ContextDefinition, ContextError, load_contexts
from .palette_items import PaletteItemReference
from .palette_state import PaletteState, load_palette_state, save_palette_state


CONTEXT_MEMBERSHIP_VERSION = 1


@dataclass(frozen=True)
class ContextMembershipMigrationReport:
    memberships_migrated: int = 0
    contexts_created: int = 0
    incompatible_memberships_skipped: int = 0
    files_changed: int = 0
    already_current: bool = False


@dataclass(frozen=True)
class ContextMembershipUpdate:
    shared_path: Path
    local_path: Path
    shared_before: tuple[ContextDefinition, ...]
    local_before: tuple[ContextDefinition, ...]
    shared_after: tuple[ContextDefinition, ...]
    local_after: tuple[ContextDefinition, ...]

    def apply(self) -> int:
        return _write_context_sets(
            self.shared_path,
            self.local_path,
            self.shared_before,
            self.local_before,
            self.shared_after,
            self.local_after,
        )


def actions_with_canonical_contexts(
    actions: Iterable[Action],
    definitions: Iterable[ContextDefinition],
) -> list[Action]:
    """Project context-owned membership onto actions used by discovery UIs."""
    action_list = list(actions)
    definitions_list = list(definitions)
    action_ids = {action.id for action in action_list}
    contexts_by_action: dict[str, list[str]] = {
        action.id: [] for action in action_list
    }
    for definition in definitions_list:
        member_ids = (
            definition.action_ids
            if definition.action_ids is not None
            else tuple(
                action.id
                for action in action_list
                if action.belongs_to_context(definition.name)
            )
        )
        preferred_action_ids = tuple(
            reference.action_id
            for reference in definition.preferred_items
            if reference.action_id
        )
        for action_id in dict.fromkeys((*member_ids, *preferred_action_ids)):
            if action_id not in action_ids:
                continue
            contexts_by_action[action_id].append(definition.name)
    return [
        replace(
            action,
            context=(
                contexts_by_action[action.id][0]
                if contexts_by_action[action.id]
                else "General"
            ),
            contexts=tuple(contexts_by_action[action.id]),
        )
        for action in action_list
    ]


def action_without_context_metadata(action: Action) -> Action:
    """Return the canonical stored form; membership lives in context files."""
    return replace(action, context="General", contexts=())


def prepare_context_membership_update(
    assignments: Mapping[str, Iterable[str]],
    *,
    local_action_ids: set[str],
    shared_contexts_path: Path,
    local_contexts_path: Path,
    create_missing_local_contexts: bool = False,
) -> ContextMembershipUpdate:
    """Validate and prepare complete memberships for one or more actions."""
    shared_before = tuple(load_contexts(shared_contexts_path))
    local_before = tuple(_load_optional_contexts(local_contexts_path))
    shared_after = list(shared_before)
    local_after = list(local_before)
    locations = _context_locations(shared_after, local_after)
    canonical_assignments: dict[str, tuple[str, ...]] = {}
    for action_id, names in assignments.items():
        selected: list[str] = []
        seen: set[str] = set()
        for raw_name in names:
            key = raw_name.strip().casefold()
            if not key or key == "general":
                continue
            location = locations.get(key)
            if location is None:
                if not create_missing_local_contexts:
                    raise ContextError(f"Undefined context: {raw_name}")
                definition = ContextDefinition(
                    raw_name.strip(),
                    action_ids=(),
                )
                local_after.append(definition)
                location = ("local", len(local_after) - 1, definition)
                locations[key] = location
            source, _index, definition = location
            if source == "shared" and action_id in local_action_ids:
                raise ContextError(
                    f'My configuration action "{action_id}" cannot be assigned '
                    f'to Built-in context "{definition.name}". Create or use a '
                    "My configuration context instead."
                )
            if key not in seen:
                seen.add(key)
                selected.append(definition.name)
        canonical_assignments[action_id] = tuple(selected)

    assigned_ids = set(canonical_assignments)
    for source, definitions in (
        ("shared", shared_after),
        ("local", local_after),
    ):
        for index, definition in enumerate(definitions):
            selected_for_definition = {
                action_id
                for action_id, names in canonical_assignments.items()
                if any(
                    name.casefold() == definition.name.casefold()
                    for name in names
                )
            }
            members = [
                action_id
                for action_id in (
                    definition.action_ids
                    if definition.action_ids is not None
                    else definition.preferred_action_ids
                )
                if (
                    action_id not in assigned_ids
                    or action_id in selected_for_definition
                )
            ]
            preferred_items = tuple(
                reference
                for reference in definition.preferred_items
                if (
                    not reference.action_id
                    or reference.action_id not in assigned_ids
                    or reference.action_id in selected_for_definition
                )
            )
            preferred = tuple(
                reference.action_id
                for reference in preferred_items
                if reference.action_id
            )
            store_typed_preferred = bool(
                definition.preferred_item_refs
                or any(reference.work_item_ref is not None for reference in preferred_items)
            )
            for action_id in canonical_assignments:
                if action_id in selected_for_definition:
                    members.append(action_id)
            definitions[index] = replace(
                definition,
                preferred_action_ids=preferred,
                action_ids=tuple(dict.fromkeys(members)),
                preferred_item_refs=(
                    preferred_items if store_typed_preferred else ()
                ),
            )

    return ContextMembershipUpdate(
        shared_contexts_path,
        local_contexts_path,
        shared_before,
        local_before,
        tuple(shared_after),
        tuple(local_after),
    )


@gated_configuration_mutation
def append_actions_with_context_memberships(
    action_path: Path,
    actions: Iterable[Action],
    *,
    actions_are_local: bool,
    shared_contexts_path: Path,
    local_contexts_path: Path,
    create_missing_local_contexts: bool = False,
) -> None:
    new_actions = list(actions)
    if not new_actions:
        return
    assignments = {
        action.id: action.effective_contexts for action in new_actions
    }
    update = prepare_context_membership_update(
        assignments,
        local_action_ids=(
            {action.id for action in new_actions}
            if actions_are_local
            else set()
        ),
        shared_contexts_path=shared_contexts_path,
        local_contexts_path=local_contexts_path,
        create_missing_local_contexts=create_missing_local_contexts,
    )
    stored_actions = [
        action_without_context_metadata(action) for action in new_actions
    ]
    append_actions(action_path, stored_actions)
    try:
        update.apply()
    except (ContextError, OSError) as exc:
        try:
            delete_actions(
                action_path,
                (action.id for action in stored_actions),
            )
        except (ActionError, OSError) as rollback_exc:
            raise ContextError(
                "Context membership could not be saved and the newly created "
                f"actions could not be rolled back: {rollback_exc}"
            ) from exc
        raise


@gated_configuration_mutation
def update_action_with_context_memberships(
    action_path: Path,
    action: Action,
    previous_action: Action,
    *,
    action_is_local: bool,
    shared_contexts_path: Path,
    local_contexts_path: Path,
) -> None:
    update = prepare_context_membership_update(
        {action.id: action.effective_contexts},
        local_action_ids={action.id} if action_is_local else set(),
        shared_contexts_path=shared_contexts_path,
        local_contexts_path=local_contexts_path,
    )
    update_action(action_path, action_without_context_metadata(action))
    try:
        update.apply()
    except (ContextError, OSError) as exc:
        try:
            update_action(
                action_path,
                action_without_context_metadata(previous_action),
            )
        except (ActionError, OSError) as rollback_exc:
            raise ContextError(
                "Context membership could not be saved and the original "
                f"action could not be restored: {rollback_exc}"
            ) from exc
        raise


@gated_configuration_mutation
def migrate_legacy_action_contexts(
    *,
    shared_actions_path: Path,
    local_actions_path: Path,
    shared_contexts_path: Path,
    local_contexts_path: Path,
    palette_path: Path,
) -> ContextMembershipMigrationReport:
    """Move legacy action-side memberships into context definitions once."""
    palette_state = load_palette_state(palette_path)
    if palette_state.context_membership_version >= CONTEXT_MEMBERSHIP_VERSION:
        return ContextMembershipMigrationReport(already_current=True)

    shared_actions = load_stored_actions(shared_actions_path)
    local_actions = (
        load_stored_actions(local_actions_path)
        if local_actions_path.exists()
        else []
    )
    shared_before = tuple(load_contexts(shared_contexts_path))
    local_before = tuple(_load_optional_contexts(local_contexts_path))
    shared_after = [
        replace(
            definition,
            action_ids=tuple(
                dict.fromkeys(
                    (
                        *(
                            definition.action_ids
                            if definition.action_ids is not None
                            else ()
                        ),
                        *definition.preferred_action_ids,
                    )
                )
            ),
        )
        for definition in shared_before
    ]
    local_after = [
        replace(
            definition,
            action_ids=tuple(
                dict.fromkeys(
                    (
                        *(
                            definition.action_ids
                            if definition.action_ids is not None
                            else ()
                        ),
                        *definition.preferred_action_ids,
                    )
                )
            ),
        )
        for definition in local_before
    ]
    locations = _context_locations(shared_after, local_after)
    memberships_migrated = 0
    contexts_created = 0
    incompatible_skipped = 0

    for action, is_local in (
        *((action, False) for action in shared_actions),
        *((action, True) for action in local_actions),
    ):
        for context_name in action.effective_contexts:
            key = context_name.casefold()
            location = locations.get(key)
            if location is None:
                definition = ContextDefinition(
                    context_name,
                    action_ids=(action.id,),
                )
                local_after.append(definition)
                locations[key] = (
                    "local",
                    len(local_after) - 1,
                    definition,
                )
                contexts_created += 1
                memberships_migrated += 1
                continue
            source, index, definition = location
            if source == "shared" and is_local:
                incompatible_skipped += 1
                continue
            definitions = shared_after if source == "shared" else local_after
            members = tuple(definition.action_ids or ())
            if action.id in members:
                continue
            updated = replace(
                definition,
                action_ids=(*members, action.id),
            )
            definitions[index] = updated
            locations[key] = (source, index, updated)
            memberships_migrated += 1

    files_changed = _write_context_sets(
        shared_contexts_path,
        local_contexts_path,
        shared_before,
        local_before,
        tuple(shared_after),
        tuple(local_after),
    )
    marker_needed = bool(files_changed or incompatible_skipped)
    if marker_needed:
        try:
            save_palette_state(
                palette_path,
                replace(
                    palette_state,
                    context_membership_version=CONTEXT_MEMBERSHIP_VERSION,
                ),
            )
        except (ActionError, OSError) as exc:
            try:
                _write_context_sets(
                    shared_contexts_path,
                    local_contexts_path,
                    tuple(shared_after),
                    tuple(local_after),
                    shared_before,
                    local_before,
                )
            except (ContextError, OSError) as rollback_exc:
                raise ContextError(
                    "The migration marker could not be saved and the context "
                    f"files could not be restored: {rollback_exc}"
                ) from exc
            raise
    return ContextMembershipMigrationReport(
        memberships_migrated,
        contexts_created,
        incompatible_skipped,
        files_changed + int(marker_needed),
    )


def _context_locations(
    shared: Iterable[ContextDefinition],
    local: Iterable[ContextDefinition],
) -> dict[str, tuple[str, int, ContextDefinition]]:
    locations: dict[str, tuple[str, int, ContextDefinition]] = {}
    for source, definitions in (("shared", shared), ("local", local)):
        for index, definition in enumerate(definitions):
            key = definition.name.casefold()
            if key in locations:
                raise ContextError(
                    f"Duplicate configured context: {definition.name}"
                )
            locations[key] = (source, index, definition)
    return locations


def _load_optional_contexts(path: Path) -> list[ContextDefinition]:
    return load_contexts(path) if path.exists() else []


@gated_configuration_mutation
def _write_context_sets(
    shared_path: Path,
    local_path: Path,
    shared_before: tuple[ContextDefinition, ...],
    local_before: tuple[ContextDefinition, ...],
    shared_after: tuple[ContextDefinition, ...],
    local_after: tuple[ContextDefinition, ...],
) -> int:
    pending = [
        (shared_path, shared_before, shared_after),
        (local_path, local_before, local_after),
    ]
    changed = [
        (path, before, after)
        for path, before, after in pending
        if before != after
    ]
    written: list[tuple[Path, tuple[ContextDefinition, ...]]] = []
    try:
        for path, before, after in changed:
            save_contexts(path, list(after))
            written.append((path, before))
    except (ContextError, OSError) as exc:
        rollback_errors: list[str] = []
        for path, before in reversed(written):
            try:
                save_contexts(path, list(before))
            except (ContextError, OSError) as rollback_exc:
                rollback_errors.append(f"{path.name}: {rollback_exc}")
        if rollback_errors:
            raise ContextError(
                "Context files could not be updated and rollback was incomplete: "
                + "; ".join(rollback_errors)
            ) from exc
        raise
    return len(changed)
