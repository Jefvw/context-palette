"""Reviewed assignment of saved Actions to configured Quick-action menus.

Configured menus are stored in the shared and personal command-surface files.
They are deliberately separate from the automatic Passwords, Folders, and
Prompts hierarchy derived from ``Action.quick_action_path``.  The placement
planner changes only configured-menu references.  The composite save boundary
also persists a caller-reviewed Action (including its automatic path) and
Context memberships so create/edit remains one rollback-protected operation.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path

from .actions import (
    ACTIVE_STATE,
    Action,
    ActionError,
    load_combined_stored_actions,
)
from .command_surface import (
    CommandGroup,
    CommandItem,
    CommandSurfaceError,
    CommandTarget,
    GROUP_PRESENTATION_NESTED_MENU,
    command_group_action_ids,
    command_item_action_ids,
    command_item_targets,
    load_combined_command_groups,
)
from .configuration_data import save_command_groups
from .configuration_mutation import configuration_mutation_gate
from .context_membership import (
    action_without_context_metadata,
    append_actions_with_context_memberships,
    update_action_with_context_memberships,
)
from .persistence import atomic_replace_bytes


SHARED_STORAGE = "shared"
LOCAL_STORAGE = "local"
CONFIGURED_PLACEMENT_STORAGES = frozenset({SHARED_STORAGE, LOCAL_STORAGE})


class ConfiguredPlacementError(ValueError):
    """Raised when configured-menu placement cannot complete safely."""

    def __init__(
        self,
        message: str,
        *,
        rollback_completed: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.rollback_completed = rollback_completed


@dataclass(frozen=True, slots=True, order=True)
class ConfiguredPlacementKey:
    """Stable identity for one configured menu root or nested location."""

    storage: str
    group_id: str
    item_id_path: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.storage not in CONFIGURED_PLACEMENT_STORAGES:
            raise ValueError("Configured placement storage must be shared or local.")
        if not isinstance(self.group_id, str) or not self.group_id.strip():
            raise ValueError("Configured placement group ID cannot be empty.")
        if isinstance(self.item_id_path, (str, bytes)) or any(
            not isinstance(item_id, str) or not item_id.strip()
            for item_id in self.item_id_path
        ):
            raise ValueError("Configured placement item IDs cannot be empty.")
        object.__setattr__(self, "group_id", self.group_id.strip())
        object.__setattr__(
            self,
            "item_id_path",
            tuple(item_id.strip() for item_id in self.item_id_path),
        )


@dataclass(frozen=True, slots=True)
class ConfiguredPlacementLocation:
    key: ConfiguredPlacementKey
    menu_path: tuple[str, ...]
    assigned: bool
    assignable: bool
    unavailable_reason: str
    action_target_count: int
    work_item_target_count: int
    child_menu_count: int
    reference_mode: str


@dataclass(frozen=True, slots=True)
class ConfiguredActionPlacementInventory:
    action_id: str
    action_title: str
    action_state: str
    action_storage: str
    locations: tuple[ConfiguredPlacementLocation, ...]
    current_locations: tuple[ConfiguredPlacementKey, ...]


@dataclass(frozen=True, slots=True)
class ConfiguredActionPlacementPlan:
    action_id: str
    action_title: str
    action_storage: str
    shared_actions_path: Path
    local_actions_path: Path
    shared_command_surface_path: Path
    local_command_surface_path: Path
    requested_desired_locations: tuple[ConfiguredPlacementKey, ...]
    desired_locations: tuple[ConfiguredPlacementKey, ...]
    current_locations: tuple[ConfiguredPlacementKey, ...]
    locations: tuple[ConfiguredPlacementLocation, ...]
    additions: tuple[ConfiguredPlacementKey, ...]
    removals: tuple[ConfiguredPlacementKey, ...]
    items_pruned: int
    shared_reference_changes: int
    local_reference_changes: int
    shared_items_pruned: int
    local_items_pruned: int
    files_to_write: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ConfiguredActionPlacementResult:
    action_id: str
    current_locations: tuple[ConfiguredPlacementKey, ...]
    additions: tuple[ConfiguredPlacementKey, ...]
    removals: tuple[ConfiguredPlacementKey, ...]
    items_pruned: int
    files_written: int


@dataclass(frozen=True, slots=True)
class _LoadedState:
    action: Action
    action_storage: str
    shared_groups: tuple[CommandGroup, ...]
    local_groups: tuple[CommandGroup, ...]
    file_bytes: tuple[bytes | None, bytes | None, bytes | None, bytes | None]


@dataclass(frozen=True, slots=True)
class _PreparedPlan:
    plan: ConfiguredActionPlacementPlan
    writes: tuple[tuple[Path, tuple[CommandGroup, ...]], ...]


def configured_action_placement_paths(
    action_id: str,
    groups: Iterable[CommandGroup],
) -> tuple[tuple[str, ...], ...]:
    """Return configured menu label paths that reference ``action_id``.

    The supplied group order is preserved.  Callers that already hold the
    combined command surface can therefore render an Action summary without
    rereading any files.  Automatic menu placement is intentionally absent.
    """

    clean_action_id = _validated_action_id(action_id)
    paths: list[tuple[str, ...]] = []
    for group in groups:
        if clean_action_id in command_group_action_ids(group):
            paths.append((group.label,))

        def visit(
            items: tuple[CommandItem, ...],
            label_path: tuple[str, ...],
        ) -> None:
            for item in items:
                item_labels = (*label_path, item.label)
                if clean_action_id in command_item_action_ids(item):
                    paths.append((group.label, *item_labels))
                visit(item.items, item_labels)

        visit(group.items, ())
    return tuple(paths)


def configured_action_placement_inventory(
    action_id: str,
    *,
    shared_actions_path: Path,
    local_actions_path: Path,
    shared_command_surface_path: Path,
    local_command_surface_path: Path,
) -> ConfiguredActionPlacementInventory:
    """Inventory every configured root/branch and current Action placement."""

    paths = _validated_storage_paths(
        shared_actions_path,
        local_actions_path,
        shared_command_surface_path,
        local_command_surface_path,
    )
    with configuration_mutation_gate():
        state = _load_state(_validated_action_id(action_id), *paths)
        return _inventory_from_state(state)


def draft_configured_action_placement_inventory(
    *,
    action_storage: str,
    shared_command_surface_path: Path,
    local_command_surface_path: Path,
    action_id: str = "",
    action_title: str = "",
) -> ConfiguredActionPlacementInventory:
    """Inventory configured locations for a saved or not-yet-saved Action.

    This read-only boundary intentionally does not require an Action record.
    Action creation can therefore stage stable menu-location keys before
    validation generates the Action ID.  Supplying ``action_id`` also exposes
    existing references, which is useful while editing an already-saved
    Action.  Final persistence must still use
    :func:`save_action_with_configured_placements`, which revalidates every
    requested key against current storage.
    """

    storage = _validated_action_storage(action_storage)
    shared_path, local_path = _validated_surface_paths(
        shared_command_surface_path,
        local_command_surface_path,
    )
    clean_action_id = action_id.strip() if isinstance(action_id, str) else ""
    if action_id and not clean_action_id:
        raise ConfiguredPlacementError("A draft Action ID cannot be blank.")
    clean_title = action_title.strip() if isinstance(action_title, str) else ""
    with configuration_mutation_gate():
        shared_groups, local_groups = _load_surface_groups(
            shared_path,
            local_path,
        )
        return _inventory_from_groups(
            action_id=clean_action_id,
            action_title=clean_title,
            action_state=ACTIVE_STATE,
            action_storage=storage,
            shared_groups=shared_groups,
            local_groups=local_groups,
        )


def save_action_with_configured_placements(
    action: Action,
    desired_locations: Iterable[ConfiguredPlacementKey],
    *,
    previous_action: Action | None = None,
    action_is_local: bool,
    shared_actions_path: Path,
    local_actions_path: Path,
    shared_contexts_path: Path,
    local_contexts_path: Path,
    shared_command_surface_path: Path,
    local_command_surface_path: Path,
) -> ConfiguredActionPlacementResult:
    """Create or update one Action and its configured placements atomically.

    ``previous_action is None`` selects creation; otherwise the saved Action is
    updated while retaining its stable identity.  Desired placements are
    stable configured-location keys selected by the UI.  They are validated
    before any write and planned again after the Action write, while the shared
    configuration mutation gate is held.  Any post-write failure restores the
    exact primary and ``.bak`` bytes for every participating file.
    """

    if not isinstance(action, Action):
        raise ConfiguredPlacementError("A validated Action is required.")
    if action.state != ACTIVE_STATE:
        raise ConfiguredPlacementError(
            "Legacy inactive Actions cannot have configured Quick-menu placements; "
            "they can only be deleted."
        )
    if previous_action is not None:
        if not isinstance(previous_action, Action):
            raise ConfiguredPlacementError("The previous Action is invalid.")
        if previous_action.id != action.id:
            raise ConfiguredPlacementError(
                "The edited Action does not match the saved Action identity."
            )

    requested = _requested_location_keys(desired_locations)
    paths = _validated_composite_paths(
        shared_actions_path,
        local_actions_path,
        shared_contexts_path,
        local_contexts_path,
        shared_command_surface_path,
        local_command_surface_path,
    )
    (
        shared_actions,
        local_actions,
        shared_contexts,
        local_contexts,
        shared_surface,
        local_surface,
    ) = paths
    action_storage = LOCAL_STORAGE if action_is_local else SHARED_STORAGE
    action_path = local_actions if action_is_local else shared_actions
    primary_paths = (
        action_path,
        shared_contexts,
        local_contexts,
        shared_surface,
        local_surface,
    )

    with configuration_mutation_gate():
        if previous_action is not None:
            _ensure_previous_action_is_current(
                previous_action,
                action_is_local=action_is_local,
                shared_actions_path=shared_actions,
                local_actions_path=local_actions,
            )
        draft = draft_configured_action_placement_inventory(
            action_storage=action_storage,
            action_id=action.id if previous_action is not None else "",
            action_title=action.title,
            shared_command_surface_path=shared_surface,
            local_command_surface_path=local_surface,
        )
        _validate_requested_locations(requested, draft)
        originals = _snapshot_primary_and_backups(primary_paths)
        mutation_started = False
        try:
            mutation_started = True
            if previous_action is None:
                append_actions_with_context_memberships(
                    action_path,
                    (action,),
                    actions_are_local=action_is_local,
                    shared_contexts_path=shared_contexts,
                    local_contexts_path=local_contexts,
                )
            else:
                update_action_with_context_memberships(
                    action_path,
                    action,
                    previous_action,
                    action_is_local=action_is_local,
                    shared_contexts_path=shared_contexts,
                    local_contexts_path=local_contexts,
                )

            plan = plan_configured_action_placements(
                action.id,
                requested,
                shared_actions_path=shared_actions,
                local_actions_path=local_actions,
                shared_command_surface_path=shared_surface,
                local_command_surface_path=local_surface,
            )
            return commit_configured_action_placements(plan)
        except Exception as exc:
            if not mutation_started:
                raise
            rollback_errors = _restore_snapshot(originals)
            if rollback_errors:
                raise ConfiguredPlacementError(
                    "The Action and configured placements could not be saved, "
                    "and automatic rollback was incomplete: "
                    + "; ".join(rollback_errors),
                    rollback_completed=False,
                ) from exc
            raise ConfiguredPlacementError(
                "The Action and configured placements could not be saved; all "
                f"participating files were restored. {exc}",
                rollback_completed=True,
            ) from exc


def _ensure_previous_action_is_current(
    previous_action: Action,
    *,
    action_is_local: bool,
    shared_actions_path: Path,
    local_actions_path: Path,
) -> None:
    """Reject an edit when its reviewed saved record changed meanwhile."""

    try:
        actions, local_ids = load_combined_stored_actions(
            shared_actions_path,
            local_actions_path,
            inspect_external_paths=False,
        )
    except (ActionError, OSError) as exc:
        raise ConfiguredPlacementError(
            f"The saved Action could not be rechecked before editing: {exc}"
        ) from exc
    current = next(
        (
            candidate
            for candidate in actions
            if candidate.id.casefold() == previous_action.id.casefold()
        ),
        None,
    )
    expected = action_without_context_metadata(previous_action)
    if current is None or current != expected:
        raise ConfiguredPlacementError(
            "The Action changed after this editor opened. Reload Configure and "
            "review the latest Action before saving."
        )
    current_is_local = current.id.casefold() in {
        action_id.casefold() for action_id in local_ids
    }
    if current_is_local != action_is_local:
        raise ConfiguredPlacementError(
            "The Action storage changed after this editor opened. Reload "
            "Configure and review the latest Action before saving."
        )


def plan_configured_action_placements(
    action_id: str,
    desired_locations: Iterable[ConfiguredPlacementKey],
    *,
    shared_actions_path: Path,
    local_actions_path: Path,
    shared_command_surface_path: Path,
    local_command_surface_path: Path,
) -> ConfiguredActionPlacementPlan:
    """Review replacing one Active Action's configured placement set."""

    paths = _validated_storage_paths(
        shared_actions_path,
        local_actions_path,
        shared_command_surface_path,
        local_command_surface_path,
    )
    requested = _requested_location_keys(desired_locations)
    with configuration_mutation_gate():
        return _prepare_plan(
            _validated_action_id(action_id),
            requested,
            *paths,
        ).plan


def commit_configured_action_placements(
    plan: ConfiguredActionPlacementPlan,
) -> ConfiguredActionPlacementResult:
    """Commit an unchanged reviewed placement plan transactionally."""

    if not isinstance(plan, ConfiguredActionPlacementPlan):
        raise ConfiguredPlacementError(
            "A reviewed configured-placement plan is required."
        )

    with configuration_mutation_gate():
        refreshed = _prepare_plan(
            plan.action_id,
            plan.requested_desired_locations,
            plan.shared_actions_path,
            plan.local_actions_path,
            plan.shared_command_surface_path,
            plan.local_command_surface_path,
        )
        if refreshed.plan.fingerprint != plan.fingerprint:
            raise ConfiguredPlacementError(
                "Actions or Quick actions changed after review. Review the "
                "configured placements again before applying them."
            )
        if not refreshed.writes:
            return _result_from_plan(refreshed.plan, files_written=0)

        originals = _snapshot_unchanged_files(refreshed)
        attempted: list[Path] = []
        try:
            for path, groups in refreshed.writes:
                attempted.append(path)
                save_command_groups(path, list(groups))
        except Exception as exc:
            rollback_errors = _restore_attempted_files(attempted, originals)
            if rollback_errors:
                raise ConfiguredPlacementError(
                    "Configured placements could not be saved and automatic "
                    "rollback was incomplete: " + "; ".join(rollback_errors),
                    rollback_completed=False,
                ) from exc
            raise ConfiguredPlacementError(
                "Configured placements could not be saved; all attempted "
                "Quick-action changes were restored.",
                rollback_completed=True,
            ) from exc

        return _result_from_plan(
            refreshed.plan,
            files_written=len(refreshed.writes),
        )


def _prepare_plan(
    action_id: str,
    requested_desired: tuple[ConfiguredPlacementKey, ...],
    shared_actions_path: Path,
    local_actions_path: Path,
    shared_command_surface_path: Path,
    local_command_surface_path: Path,
) -> _PreparedPlan:
    state = _load_state(
        action_id,
        shared_actions_path,
        local_actions_path,
        shared_command_surface_path,
        local_command_surface_path,
    )
    inventory = _inventory_from_state(state)
    locations_by_identity = {
        _key_identity(location.key): location
        for location in inventory.locations
    }
    current_identities = {
        _key_identity(key) for key in inventory.current_locations
    }
    requested_identities: set[tuple[str, str, tuple[str, ...]]] = set()
    for requested in requested_desired:
        identity = _key_identity(requested)
        if identity in requested_identities:
            raise ConfiguredPlacementError(
                "A configured Quick-menu location was selected more than once."
            )
        requested_identities.add(identity)
        location = locations_by_identity.get(identity)
        if location is None:
            raise ConfiguredPlacementError(
                "A selected configured Quick-menu location no longer exists: "
                + _display_key(requested)
            )
        if not location.assignable and identity not in current_identities:
            raise ConfiguredPlacementError(location.unavailable_reason)

    desired = tuple(
        location.key
        for location in inventory.locations
        if _key_identity(location.key) in requested_identities
    )
    desired_identities = {_key_identity(key) for key in desired}
    additions = tuple(
        location.key
        for location in inventory.locations
        if (
            _key_identity(location.key) in desired_identities
            and _key_identity(location.key) not in current_identities
        )
    )
    removals = tuple(
        location.key
        for location in inventory.locations
        if (
            _key_identity(location.key) in current_identities
            and _key_identity(location.key) not in desired_identities
        )
    )

    shared_groups, shared_pruned = _apply_desired_locations(
        state.shared_groups,
        storage=SHARED_STORAGE,
        action_id=state.action.id,
        desired_identities=desired_identities,
    )
    local_groups, local_pruned = _apply_desired_locations(
        state.local_groups,
        storage=LOCAL_STORAGE,
        action_id=state.action.id,
        desired_identities=desired_identities,
    )
    writes: list[tuple[Path, tuple[CommandGroup, ...]]] = []
    if shared_groups != state.shared_groups:
        writes.append((shared_command_surface_path, shared_groups))
    if local_groups != state.local_groups:
        writes.append((local_command_surface_path, local_groups))

    shared_changes = sum(key.storage == SHARED_STORAGE for key in additions) + sum(
        key.storage == SHARED_STORAGE for key in removals
    )
    local_changes = sum(key.storage == LOCAL_STORAGE for key in additions) + sum(
        key.storage == LOCAL_STORAGE for key in removals
    )
    fingerprint = _plan_fingerprint(
        action_id=state.action.id,
        desired_locations=desired,
        shared_actions_path=shared_actions_path,
        local_actions_path=local_actions_path,
        shared_command_surface_path=shared_command_surface_path,
        local_command_surface_path=local_command_surface_path,
        file_bytes=state.file_bytes,
    )
    plan = ConfiguredActionPlacementPlan(
        action_id=state.action.id,
        action_title=state.action.title,
        action_storage=state.action_storage,
        shared_actions_path=shared_actions_path,
        local_actions_path=local_actions_path,
        shared_command_surface_path=shared_command_surface_path,
        local_command_surface_path=local_command_surface_path,
        requested_desired_locations=desired,
        desired_locations=desired,
        current_locations=inventory.current_locations,
        locations=inventory.locations,
        additions=additions,
        removals=removals,
        items_pruned=shared_pruned + local_pruned,
        shared_reference_changes=shared_changes,
        local_reference_changes=local_changes,
        shared_items_pruned=shared_pruned,
        local_items_pruned=local_pruned,
        files_to_write=len(writes),
        fingerprint=fingerprint,
    )
    return _PreparedPlan(plan, tuple(writes))


def _inventory_from_state(
    state: _LoadedState,
) -> ConfiguredActionPlacementInventory:
    return _inventory_from_groups(
        action_id=state.action.id,
        action_title=state.action.title,
        action_state=state.action.state,
        action_storage=state.action_storage,
        shared_groups=state.shared_groups,
        local_groups=state.local_groups,
    )


def _inventory_from_groups(
    *,
    action_id: str,
    action_title: str,
    action_state: str,
    action_storage: str,
    shared_groups: tuple[CommandGroup, ...],
    local_groups: tuple[CommandGroup, ...],
) -> ConfiguredActionPlacementInventory:
    action_is_local = action_storage == LOCAL_STORAGE
    locations: list[ConfiguredPlacementLocation] = []
    # Match launcher order: personal configured menus precede Built-in menus.
    for storage, groups in (
        (LOCAL_STORAGE, local_groups),
        (SHARED_STORAGE, shared_groups),
    ):
        assignable = storage == LOCAL_STORAGE or not action_is_local
        unavailable_reason = (
            "A My configuration Action cannot be placed in Built-in Quick "
            "actions. Choose a My configuration menu instead."
            if not assignable
            else ""
        )
        for group in groups:
            root_action_ids = command_group_action_ids(group)
            locations.append(
                ConfiguredPlacementLocation(
                    key=ConfiguredPlacementKey(storage, group.id),
                    menu_path=(group.label,),
                    assigned=action_id in root_action_ids,
                    assignable=assignable,
                    unavailable_reason=unavailable_reason,
                    action_target_count=len(root_action_ids),
                    work_item_target_count=0,
                    child_menu_count=len(group.items),
                    reference_mode="actions" if root_action_ids else "empty",
                )
            )

            def visit(
                items: tuple[CommandItem, ...],
                item_ids: tuple[str, ...],
                labels: tuple[str, ...],
            ) -> None:
                for item in items:
                    current_ids = (*item_ids, item.id)
                    current_labels = (*labels, item.label)
                    targets = command_item_targets(item)
                    action_ids = tuple(
                        target.action_id for target in targets if target.action_id
                    )
                    work_item_count = sum(
                        target.work_item_ref is not None for target in targets
                    )
                    locations.append(
                        ConfiguredPlacementLocation(
                            key=ConfiguredPlacementKey(
                                storage,
                                group.id,
                                current_ids,
                            ),
                            menu_path=(group.label, *current_labels),
                            assigned=action_id in action_ids,
                            assignable=assignable,
                            unavailable_reason=unavailable_reason,
                            action_target_count=len(action_ids),
                            work_item_target_count=work_item_count,
                            child_menu_count=len(item.items),
                            reference_mode=_reference_mode(
                                len(action_ids),
                                work_item_count,
                            ),
                        )
                    )
                    visit(item.items, current_ids, current_labels)

            visit(group.items, (), ())

    current = tuple(location.key for location in locations if location.assigned)
    return ConfiguredActionPlacementInventory(
        action_id=action_id,
        action_title=action_title,
        action_state=action_state,
        action_storage=action_storage,
        locations=tuple(locations),
        current_locations=current,
    )


def _apply_desired_locations(
    groups: tuple[CommandGroup, ...],
    *,
    storage: str,
    action_id: str,
    desired_identities: set[tuple[str, str, tuple[str, ...]]],
) -> tuple[tuple[CommandGroup, ...], int]:
    output: list[CommandGroup] = []
    pruned_total = 0
    for group in groups:
        root_key = ConfiguredPlacementKey(storage, group.id)
        root_wanted = _key_identity(root_key) in desired_identities
        root_assigned = action_id in command_group_action_ids(group)
        updated_group = (
            _set_group_assignment(group, action_id, root_wanted)
            if root_assigned != root_wanted
            else group
        )
        items, pruned = _apply_desired_items(
            updated_group.items,
            storage=storage,
            group_id=group.id,
            parent_item_ids=(),
            action_id=action_id,
            desired_identities=desired_identities,
        )
        if items != updated_group.items:
            updated_group = replace(updated_group, items=items)
        output.append(updated_group)
        pruned_total += pruned
    return tuple(output), pruned_total


def _apply_desired_items(
    items: tuple[CommandItem, ...],
    *,
    storage: str,
    group_id: str,
    parent_item_ids: tuple[str, ...],
    action_id: str,
    desired_identities: set[tuple[str, str, tuple[str, ...]]],
) -> tuple[tuple[CommandItem, ...], int]:
    output: list[CommandItem] = []
    pruned_total = 0
    for item in items:
        item_ids = (*parent_item_ids, item.id)
        key = ConfiguredPlacementKey(storage, group_id, item_ids)
        wanted = _key_identity(key) in desired_identities
        assigned = action_id in command_item_action_ids(item)
        membership_removed = assigned and not wanted
        updated = (
            _set_item_assignment(item, action_id, wanted)
            if assigned != wanted
            else item
        )
        children, child_pruned = _apply_desired_items(
            updated.items,
            storage=storage,
            group_id=group_id,
            parent_item_ids=item_ids,
            action_id=action_id,
            desired_identities=desired_identities,
        )
        if children != updated.items:
            updated = replace(updated, items=children)
        changed_by_removal = membership_removed or child_pruned > 0
        if changed_by_removal and not _item_has_content(updated):
            pruned_total += child_pruned + 1
            continue
        output.append(updated)
        pruned_total += child_pruned
    return tuple(output), pruned_total


def _set_group_assignment(
    group: CommandGroup,
    action_id: str,
    assigned: bool,
) -> CommandGroup:
    action_ids = list(command_group_action_ids(group))
    if assigned:
        if action_id not in action_ids:
            action_ids.append(action_id)
    else:
        action_ids = [value for value in action_ids if value != action_id]
    return replace(
        group,
        presentation=(
            GROUP_PRESENTATION_NESTED_MENU if assigned else group.presentation
        ),
        primary_action_id=action_ids[0] if action_ids else "",
        action_ids=tuple(action_ids),
    )


def _set_item_assignment(
    item: CommandItem,
    action_id: str,
    assigned: bool,
) -> CommandItem:
    if item.targets or item.work_item_ref is not None:
        targets = list(command_item_targets(item))
        if assigned:
            target = CommandTarget(action_id=action_id)
            if target not in targets:
                targets.append(target)
        else:
            targets = [target for target in targets if target.action_id != action_id]
        return replace(
            item,
            primary_action_id="",
            action_ids=(),
            work_item_ref=None,
            targets=tuple(targets),
        )

    action_ids = list(command_item_action_ids(item))
    if assigned:
        if action_id not in action_ids:
            action_ids.append(action_id)
    else:
        action_ids = [value for value in action_ids if value != action_id]
    return replace(
        item,
        primary_action_id=action_ids[0] if action_ids else "",
        action_ids=tuple(action_ids),
    )


def _item_has_content(item: CommandItem) -> bool:
    return bool(command_item_targets(item) or item.items)


def _load_state(
    action_id: str,
    shared_actions_path: Path,
    local_actions_path: Path,
    shared_command_surface_path: Path,
    local_command_surface_path: Path,
) -> _LoadedState:
    paths = (
        shared_actions_path,
        local_actions_path,
        shared_command_surface_path,
        local_command_surface_path,
    )
    before = tuple(_read_optional_bytes(path) for path in paths)
    try:
        actions, local_action_ids = load_combined_stored_actions(
            shared_actions_path,
            local_actions_path,
            inspect_external_paths=False,
        )
        groups = load_combined_command_groups(
            shared_command_surface_path,
            local_command_surface_path,
        )
    except (ActionError, CommandSurfaceError, OSError) as exc:
        raise ConfiguredPlacementError(
            f"Actions and configured Quick actions could not be reviewed: {exc}"
        ) from exc
    after = tuple(_read_optional_bytes(path) for path in paths)
    if before != after:
        raise ConfiguredPlacementError(
            "Actions or Quick actions changed while placements were being "
            "reviewed. Try again."
        )

    action = next(
        (
            candidate
            for candidate in actions
            if candidate.id.casefold() == action_id.casefold()
        ),
        None,
    )
    if action is None:
        raise ConfiguredPlacementError(f"Action was not found: {action_id}")
    if action.state != ACTIVE_STATE:
        raise ConfiguredPlacementError(
            "Legacy inactive Actions cannot have configured Quick-menu placements; "
            "they can only be deleted."
        )
    local_keys = {value.casefold() for value in local_action_ids}
    local_surface = local_command_surface_path.resolve()
    shared_groups: list[CommandGroup] = []
    local_groups: list[CommandGroup] = []
    for group in groups:
        if group.source_path is not None and group.source_path.resolve() == local_surface:
            local_groups.append(group)
        else:
            shared_groups.append(group)
    return _LoadedState(
        action=action,
        action_storage=(
            LOCAL_STORAGE if action.id.casefold() in local_keys else SHARED_STORAGE
        ),
        shared_groups=tuple(shared_groups),
        local_groups=tuple(local_groups),
        file_bytes=after,
    )


def _load_surface_groups(
    shared_command_surface_path: Path,
    local_command_surface_path: Path,
) -> tuple[tuple[CommandGroup, ...], tuple[CommandGroup, ...]]:
    paths = (shared_command_surface_path, local_command_surface_path)
    before = tuple(_read_optional_bytes(path) for path in paths)
    try:
        groups = load_combined_command_groups(*paths)
    except (CommandSurfaceError, OSError) as exc:
        raise ConfiguredPlacementError(
            f"Configured Quick actions could not be reviewed: {exc}"
        ) from exc
    after = tuple(_read_optional_bytes(path) for path in paths)
    if before != after:
        raise ConfiguredPlacementError(
            "Quick actions changed while placements were being reviewed. Try again."
        )

    local_surface = local_command_surface_path.resolve()
    shared_groups: list[CommandGroup] = []
    local_groups: list[CommandGroup] = []
    for group in groups:
        if group.source_path is not None and group.source_path.resolve() == local_surface:
            local_groups.append(group)
        else:
            shared_groups.append(group)
    return tuple(shared_groups), tuple(local_groups)


def _validate_requested_locations(
    requested: tuple[ConfiguredPlacementKey, ...],
    inventory: ConfiguredActionPlacementInventory,
) -> None:
    locations = {
        _key_identity(location.key): location for location in inventory.locations
    }
    current = {_key_identity(key) for key in inventory.current_locations}
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for requested_key in requested:
        identity = _key_identity(requested_key)
        if identity in seen:
            raise ConfiguredPlacementError(
                "A configured Quick-menu location was selected more than once."
            )
        seen.add(identity)
        location = locations.get(identity)
        if location is None:
            raise ConfiguredPlacementError(
                "A selected configured Quick-menu location no longer exists: "
                + _display_key(requested_key)
            )
        if not location.assignable and identity not in current:
            raise ConfiguredPlacementError(location.unavailable_reason)


def _snapshot_primary_and_backups(
    primary_paths: Iterable[Path],
) -> dict[Path, bytes | None]:
    originals: dict[Path, bytes | None] = {}
    for primary in dict.fromkeys(Path(path) for path in primary_paths):
        originals[primary] = _read_optional_bytes(primary)
        backup = primary.with_name(primary.name + ".bak")
        originals[backup] = _read_optional_bytes(backup)
    return originals


def _restore_snapshot(
    originals: dict[Path, bytes | None],
) -> list[str]:
    errors: list[str] = []
    for path, payload in reversed(tuple(originals.items())):
        try:
            if payload is None:
                path.unlink(missing_ok=True)
            else:
                atomic_replace_bytes(path, payload, preserve_previous=False)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    return errors


def _snapshot_unchanged_files(
    prepared: _PreparedPlan,
) -> dict[Path, bytes | None]:
    plan = prepared.plan
    all_paths = (
        plan.shared_actions_path,
        plan.local_actions_path,
        plan.shared_command_surface_path,
        plan.local_command_surface_path,
    )
    file_bytes = tuple(_read_optional_bytes(path) for path in all_paths)
    fingerprint = _plan_fingerprint(
        action_id=plan.action_id,
        desired_locations=plan.desired_locations,
        shared_actions_path=plan.shared_actions_path,
        local_actions_path=plan.local_actions_path,
        shared_command_surface_path=plan.shared_command_surface_path,
        local_command_surface_path=plan.local_command_surface_path,
        file_bytes=file_bytes,
    )
    if fingerprint != plan.fingerprint:
        raise ConfiguredPlacementError(
            "Actions or Quick actions changed after review. Review the "
            "configured placements again before applying them."
        )

    originals: dict[Path, bytes | None] = {}
    for path, _groups in prepared.writes:
        originals[path] = _read_optional_bytes(path)
        backup = path.with_name(path.name + ".bak")
        originals[backup] = _read_optional_bytes(backup)
    if tuple(_read_optional_bytes(path) for path in all_paths) != file_bytes:
        raise ConfiguredPlacementError(
            "Actions or Quick actions changed after review. Review the "
            "configured placements again before applying them."
        )
    return originals


def _restore_attempted_files(
    attempted: Iterable[Path],
    originals: dict[Path, bytes | None],
) -> list[str]:
    errors: list[str] = []
    for primary in reversed(tuple(attempted)):
        for path in (primary, primary.with_name(primary.name + ".bak")):
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
    plan: ConfiguredActionPlacementPlan,
    *,
    files_written: int,
) -> ConfiguredActionPlacementResult:
    return ConfiguredActionPlacementResult(
        action_id=plan.action_id,
        current_locations=plan.desired_locations,
        additions=plan.additions,
        removals=plan.removals,
        items_pruned=plan.items_pruned,
        files_written=files_written,
    )


def _plan_fingerprint(
    *,
    action_id: str,
    desired_locations: tuple[ConfiguredPlacementKey, ...],
    shared_actions_path: Path,
    local_actions_path: Path,
    shared_command_surface_path: Path,
    local_command_surface_path: Path,
    file_bytes: tuple[bytes | None, bytes | None, bytes | None, bytes | None],
) -> str:
    paths = (
        shared_actions_path,
        local_actions_path,
        shared_command_surface_path,
        local_command_surface_path,
    )
    record = {
        "action_id": action_id,
        "desired_locations": [_key_record(key) for key in desired_locations],
        "files": [
            {
                "path": str(path.resolve()),
                **_file_identity(payload),
            }
            for path, payload in zip(paths, file_bytes)
        ],
    }
    payload = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + sha256(payload).hexdigest()


def _requested_location_keys(
    values: Iterable[ConfiguredPlacementKey],
) -> tuple[ConfiguredPlacementKey, ...]:
    if isinstance(values, (str, bytes)):
        raise ConfiguredPlacementError(
            "Configured placements must be selected from menu locations."
        )
    try:
        keys = tuple(values)
    except TypeError as exc:
        raise ConfiguredPlacementError(
            "Configured placements must be an iterable of menu locations."
        ) from exc
    if any(not isinstance(key, ConfiguredPlacementKey) for key in keys):
        raise ConfiguredPlacementError(
            "Configured placements must use stable menu-location keys."
        )
    return keys


def _validated_storage_paths(
    shared_actions_path: Path,
    local_actions_path: Path,
    shared_command_surface_path: Path,
    local_command_surface_path: Path,
) -> tuple[Path, Path, Path, Path]:
    paths = tuple(
        Path(path)
        for path in (
            shared_actions_path,
            local_actions_path,
            shared_command_surface_path,
            local_command_surface_path,
        )
    )
    identities = [str(path.resolve()).casefold() for path in paths]
    if len(set(identities)) != len(identities):
        raise ConfiguredPlacementError(
            "Action and Quick-action storage must use four different files."
        )
    return paths[0], paths[1], paths[2], paths[3]


def _validated_surface_paths(
    shared_command_surface_path: Path,
    local_command_surface_path: Path,
) -> tuple[Path, Path]:
    paths = (
        Path(shared_command_surface_path),
        Path(local_command_surface_path),
    )
    if str(paths[0].resolve()).casefold() == str(paths[1].resolve()).casefold():
        raise ConfiguredPlacementError(
            "Built-in and personal Quick actions must use different files."
        )
    return paths


def _validated_composite_paths(
    shared_actions_path: Path,
    local_actions_path: Path,
    shared_contexts_path: Path,
    local_contexts_path: Path,
    shared_command_surface_path: Path,
    local_command_surface_path: Path,
) -> tuple[Path, Path, Path, Path, Path, Path]:
    paths = tuple(
        Path(path)
        for path in (
            shared_actions_path,
            local_actions_path,
            shared_contexts_path,
            local_contexts_path,
            shared_command_surface_path,
            local_command_surface_path,
        )
    )
    identities = [str(path.resolve()).casefold() for path in paths]
    if len(set(identities)) != len(identities):
        raise ConfiguredPlacementError(
            "Action, Context, and Quick-action storage must use six different files."
        )
    return paths  # type: ignore[return-value]


def _validated_action_storage(action_storage: str) -> str:
    if action_storage not in CONFIGURED_PLACEMENT_STORAGES:
        raise ConfiguredPlacementError(
            "Action storage must be shared or local."
        )
    return action_storage


def _validated_action_id(action_id: str) -> str:
    if not isinstance(action_id, str) or not action_id.strip():
        raise ConfiguredPlacementError("Choose one saved Action.")
    return action_id.strip()


def _key_identity(
    key: ConfiguredPlacementKey,
) -> tuple[str, str, tuple[str, ...]]:
    return (
        key.storage,
        key.group_id.casefold(),
        tuple(item_id.casefold() for item_id in key.item_id_path),
    )


def _key_record(key: ConfiguredPlacementKey) -> dict[str, object]:
    return {
        "storage": key.storage,
        "group_id": key.group_id,
        "item_id_path": list(key.item_id_path),
    }


def _display_key(key: ConfiguredPlacementKey) -> str:
    parts = (key.group_id, *key.item_id_path)
    return f"{key.storage}: " + " > ".join(parts)


def _reference_mode(action_count: int, work_item_count: int) -> str:
    if action_count and work_item_count:
        return "mixed"
    if work_item_count:
        return "work_items"
    if action_count:
        return "actions"
    return "empty"


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
        raise ConfiguredPlacementError(
            f"Configuration file could not be read: {path}"
        ) from exc
