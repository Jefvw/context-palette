from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable

from .configuration_mutation import configuration_mutation_gate
from .persistence import atomic_replace_bytes, atomic_write_json


class ActionDeletionError(Exception):
    """Raised when an Action deletion cannot complete safely."""


@dataclass(frozen=True)
class ActionDeletionReport:
    references_removed: int = 0
    buttons_removed: int = 0
    files_changed: int = 0


@dataclass(frozen=True, slots=True)
class ActionDeletionTarget:
    """User-visible Action identity captured from the reviewed file."""

    id: str
    title: str
    state: str
    type: str
    quick_action_path: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ActionDeletionPlan:
    """Exact single-Action state approved by the destructive review."""

    action_path: Path
    action_id: str
    target: ActionDeletionTarget
    impact: ActionDeletionReport
    configuration_fingerprint: str
    context_paths: tuple[Path, ...]
    command_surface_paths: tuple[Path, ...]
    palette_path: Path
    sequence_paths: tuple[Path, ...] = ()

    @property
    def participant_paths(self) -> tuple[Path, ...]:
        return _deletion_participant_paths(
            self.action_path,
            context_paths=self.context_paths,
            command_surface_paths=self.command_surface_paths,
            palette_path=self.palette_path,
            sequence_paths=self.sequence_paths,
        )


def plan_action_deletion(
    action_path: Path,
    action_id: str,
    *,
    context_paths: tuple[Path, ...],
    command_surface_paths: tuple[Path, ...],
    palette_path: Path,
    sequence_paths: tuple[Path, ...] = (),
) -> ActionDeletionPlan:
    """Prepare one exact, read-only permanent-deletion review."""

    requested_ids = _validated_action_ids((action_id,))
    participants = _deletion_participant_paths(
        action_path,
        context_paths=context_paths,
        command_surface_paths=command_surface_paths,
        palette_path=palette_path,
        sequence_paths=sequence_paths,
    )
    with configuration_mutation_gate():
        fingerprint_before = action_deletion_configuration_fingerprint(participants)
        action_data = _read_object(action_path)
        records = _find_action_records(action_data, action_path, requested_ids)
        canonical_id = records[0]["id"]
        if not isinstance(canonical_id, str):
            raise ActionDeletionError("The reviewed Action has an invalid ID.")
        target = _deletion_target(records[0], canonical_id)
        _assert_no_sequence_dependencies_many(
            (canonical_id,),
            sequence_paths,
            include_archived=True,
        )
        references = inspect_action_references(
            canonical_id,
            context_paths=context_paths,
            command_surface_paths=command_surface_paths,
            palette_path=palette_path,
        )
        fingerprint_after = action_deletion_configuration_fingerprint(participants)
        if fingerprint_before != fingerprint_after:
            raise ActionDeletionError(
                "Saved Actions or assignments changed while the deletion review "
                "was being prepared. Review the Action again."
            )

    return ActionDeletionPlan(
        action_path=Path(action_path),
        action_id=canonical_id,
        target=target,
        impact=ActionDeletionReport(
            references.references_removed,
            references.buttons_removed,
            references.files_changed + 1,
        ),
        configuration_fingerprint=fingerprint_after,
        context_paths=tuple(context_paths),
        command_surface_paths=tuple(command_surface_paths),
        palette_path=Path(palette_path),
        sequence_paths=tuple(sequence_paths),
    )


def commit_action_deletion(plan: ActionDeletionPlan) -> ActionDeletionReport:
    """Commit one unchanged, reviewed single-Action deletion plan."""

    if not isinstance(plan, ActionDeletionPlan):
        raise ActionDeletionError("A reviewed Action deletion plan is required.")
    return delete_action_and_references(
        plan.action_path,
        plan.action_id,
        context_paths=plan.context_paths,
        command_surface_paths=plan.command_surface_paths,
        palette_path=plan.palette_path,
        sequence_paths=plan.sequence_paths,
        expected_report=plan.impact,
        expected_configuration_fingerprint=plan.configuration_fingerprint,
    )


def inspect_action_references(
    action_id: str,
    *,
    context_paths: tuple[Path, ...],
    command_surface_paths: tuple[Path, ...],
    palette_path: Path,
) -> ActionDeletionReport:
    return inspect_action_references_many(
        (action_id,),
        context_paths=context_paths,
        command_surface_paths=command_surface_paths,
        palette_path=palette_path,
    )


def inspect_action_references_many(
    action_ids: Iterable[str],
    *,
    context_paths: tuple[Path, ...],
    command_surface_paths: tuple[Path, ...],
    palette_path: Path,
) -> ActionDeletionReport:
    """Inventory the exact combined saved-placement effect for several Actions."""

    selected_ids = _validated_action_ids(action_ids, allow_empty=True)
    if not selected_ids:
        return ActionDeletionReport()
    references = 0
    buttons = 0
    files = 0
    for path in context_paths:
        data = _read_optional_object(path)
        if data is None:
            continue
        changed = deepcopy(data)
        removed = sum(
            _remove_context_references(changed, action_id, path)
            for action_id in selected_ids
        )
        references += removed
        files += bool(removed)
    for path in command_surface_paths:
        data = _read_optional_object(path)
        if data is None:
            continue
        changed = deepcopy(data)
        removed, removed_buttons = _remove_command_references_many(
            changed,
            selected_ids,
            path,
        )
        references += removed
        buttons += removed_buttons
        files += bool(removed or removed_buttons)
    palette_data = _read_optional_object(palette_path)
    if palette_data is not None:
        changed = deepcopy(palette_data)
        removed = sum(
            _remove_palette_references(changed, action_id)
            for action_id in selected_ids
        )
        references += removed
        files += bool(removed)
    return ActionDeletionReport(references, buttons, files)


def delete_action_and_references(
    action_path: Path,
    action_id: str,
    *,
    context_paths: tuple[Path, ...],
    command_surface_paths: tuple[Path, ...],
    palette_path: Path,
    sequence_paths: tuple[Path, ...] = (),
    expected_report: ActionDeletionReport | None = None,
    expected_configuration_fingerprint: str | None = None,
) -> ActionDeletionReport:
    return delete_actions_and_references(
        action_path,
        (action_id,),
        context_paths=context_paths,
        command_surface_paths=command_surface_paths,
        palette_path=palette_path,
        sequence_paths=sequence_paths,
        expected_report=expected_report,
        expected_configuration_fingerprint=expected_configuration_fingerprint,
    )


def delete_actions_and_references(
    action_path: Path,
    action_ids: Iterable[str],
    *,
    context_paths: tuple[Path, ...],
    command_surface_paths: tuple[Path, ...],
    palette_path: Path,
    sequence_paths: tuple[Path, ...] = (),
    expected_report: ActionDeletionReport | None = None,
    expected_configuration_fingerprint: str | None = None,
) -> ActionDeletionReport:
    """Permanently delete one reviewed Action batch in one transaction.

    Active Actions and legacy ``Archived`` records are both accepted.  The
    latter remain readable only for backward-compatible cleanup; deletion does
    not restore or otherwise migrate them first.
    """

    selected_ids = _validated_action_ids(action_ids)
    participant_paths = _deletion_participant_paths(
        action_path,
        context_paths=context_paths,
        command_surface_paths=command_surface_paths,
        palette_path=palette_path,
        sequence_paths=sequence_paths,
    )
    with configuration_mutation_gate():
        fingerprint_before = action_deletion_configuration_fingerprint(
            participant_paths
        )
        if (
            expected_configuration_fingerprint is not None
            and fingerprint_before != expected_configuration_fingerprint
        ):
            raise ActionDeletionError(
                "Saved Actions or assignments changed after review. Review the "
                "Action selection again; no configuration changes were made."
            )
        _assert_no_sequence_dependencies_many(
            selected_ids,
            sequence_paths,
            include_archived=True,
        )
        return _delete_actions_and_references(
            action_path,
            selected_ids,
            context_paths=context_paths,
            command_surface_paths=command_surface_paths,
            palette_path=palette_path,
            expected_report=expected_report,
            participant_paths=participant_paths,
            fingerprint_before=fingerprint_before,
        )


def _delete_actions_and_references(
    action_path: Path,
    action_ids: tuple[str, ...],
    *,
    context_paths: tuple[Path, ...],
    command_surface_paths: tuple[Path, ...],
    palette_path: Path,
    expected_report: ActionDeletionReport | None,
    participant_paths: tuple[Path, ...],
    fingerprint_before: str,
) -> ActionDeletionReport:
    action_data = _read_object(action_path)
    actions = action_data.get("actions")
    if not isinstance(actions, list):
        raise ActionDeletionError(f"{action_path.name} must contain an 'actions' list.")
    selected_records = _find_action_records(action_data, action_path, action_ids)
    canonical_action_ids = tuple(
        action["id"]
        for action in selected_records
        if isinstance(action.get("id"), str)
    )
    selected_keys = {action_id.casefold() for action_id in canonical_action_ids}
    retained_actions = [
        item
        for item in actions
        if not (
            isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and item["id"].casefold() in selected_keys
        )
    ]

    pending_writes, references_removed, buttons_removed = _prepare_reference_removals_many(
        canonical_action_ids,
        context_paths=context_paths,
        command_surface_paths=command_surface_paths,
        palette_path=palette_path,
    )
    report = ActionDeletionReport(
        references_removed,
        buttons_removed,
        len(pending_writes) + 1,
    )
    _assert_expected_report(expected_report, report)
    if (
        action_deletion_configuration_fingerprint(participant_paths)
        != fingerprint_before
    ):
        raise ActionDeletionError(
            "Saved Actions or assignments changed while the deletion was being "
            "prepared. Review the Action selection again; no configuration "
            "changes were made."
        )

    action_data["actions"] = retained_actions
    _write_json_transaction(
        (*pending_writes, (action_path, action_data)),
        operation="The permanent Action deletion",
    )
    return report


def action_deletion_configuration_fingerprint(paths: Iterable[Path]) -> str:
    """Return a stable content fingerprint for deletion participants."""

    digest = sha256()
    candidates_by_label = {
        str(Path(path).absolute()).casefold(): Path(path)
        for path in paths
    }
    for normalized_label in sorted(candidates_by_label):
        candidate = candidates_by_label[normalized_label]
        label = normalized_label.encode("utf-8")
        digest.update(len(label).to_bytes(8, "big"))
        digest.update(label)
        try:
            payload = candidate.read_bytes()
        except FileNotFoundError:
            digest.update(b"\x00")
        except OSError as exc:
            raise ActionDeletionError(
                f"Configuration file could not be fingerprinted: {candidate.name}"
            ) from exc
        else:
            digest.update(b"\x01")
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(payload)
    return digest.hexdigest()


def _deletion_participant_paths(
    action_path: Path,
    *,
    context_paths: tuple[Path, ...],
    command_surface_paths: tuple[Path, ...],
    palette_path: Path,
    sequence_paths: tuple[Path, ...],
) -> tuple[Path, ...]:
    return tuple(
        dict.fromkeys(
            (
                Path(action_path),
                *(Path(path) for path in sequence_paths),
                *(Path(path) for path in context_paths),
                *(Path(path) for path in command_surface_paths),
                Path(palette_path),
            )
        )
    )


def _assert_expected_report(
    expected: ActionDeletionReport | None,
    actual: ActionDeletionReport,
) -> None:
    if expected is not None and actual != expected:
        raise ActionDeletionError(
            "The current saved-placement effect does not match the reviewed "
            "deletion impact. Review the Actions again; no configuration "
            "changes were made."
        )


def _find_action_records(
    action_data: dict[str, object],
    action_path: Path,
    action_ids: tuple[str, ...],
) -> tuple[dict[str, object], ...]:
    actions = action_data.get("actions")
    if not isinstance(actions, list):
        raise ActionDeletionError(f"{action_path.name} must contain an 'actions' list.")
    records_by_key: dict[str, dict[str, object]] = {}
    duplicate_ids: list[str] = []
    for action in actions:
        if not isinstance(action, dict) or not isinstance(action.get("id"), str):
            continue
        key = action["id"].casefold()
        if key in records_by_key:
            duplicate_ids.append(action["id"])
        else:
            records_by_key[key] = action
    if duplicate_ids:
        raise ActionDeletionError(
            f"{action_path.name} contains duplicate Action IDs: "
            + ", ".join(duplicate_ids)
        )
    found: list[dict[str, object]] = []
    missing: list[str] = []
    for action_id in action_ids:
        action = records_by_key.get(action_id.casefold())
        if action is None:
            missing.append(action_id)
        else:
            found.append(action)
    if missing:
        label = "Action was" if len(missing) == 1 else "Actions were"
        raise ActionDeletionError(f"{label} not found: {', '.join(missing)}")
    return tuple(found)


def _deletion_target(
    record: dict[str, object],
    canonical_id: str,
) -> ActionDeletionTarget:
    title = record.get("title")
    state = record.get("state", "Active")
    action_type = record.get("type")
    raw_path = record.get("quick_action_path")
    return ActionDeletionTarget(
        id=canonical_id,
        title=title if isinstance(title, str) and title else canonical_id,
        state=state if isinstance(state, str) else "Active",
        type=action_type if isinstance(action_type, str) else "",
        quick_action_path=(
            tuple(value for value in raw_path if isinstance(value, str))
            if isinstance(raw_path, list)
            else ()
        ),
    )


def _validated_action_ids(
    action_ids: Iterable[str],
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    selected: list[str] = []
    seen: set[str] = set()
    for action_id in action_ids:
        if not isinstance(action_id, str) or not action_id.strip():
            raise ActionDeletionError("Action IDs must be non-empty text.")
        key = action_id.casefold()
        if key in seen:
            raise ActionDeletionError(
                f"Action was selected more than once: {action_id}"
            )
        seen.add(key)
        selected.append(action_id)
    if not selected and not allow_empty:
        raise ActionDeletionError("Select at least one Action.")
    return tuple(selected)


def _assert_no_sequence_dependencies_many(
    action_ids: tuple[str, ...],
    paths: tuple[Path, ...],
    *,
    include_archived: bool,
) -> None:
    selected_keys = {action_id.casefold() for action_id in action_ids}
    dependents: list[str] = []
    seen_dependents: set[str] = set()
    for path in paths:
        data = _read_optional_object(path)
        if data is None:
            continue
        actions = data.get("actions")
        if not isinstance(actions, list):
            raise ActionDeletionError(f"{path.name} must contain an 'actions' list.")
        for action in actions:
            if not isinstance(action, dict) or action.get("type") != "sequence":
                continue
            owner_id = action.get("id")
            if not isinstance(owner_id, str):
                continue
            owner_key = owner_id.casefold()
            if owner_key in selected_keys:
                continue
            if not include_archived and action.get("state", "Active") == "Archived":
                continue
            steps = action.get("steps")
            if not isinstance(steps, list):
                continue
            if not any(
                isinstance(step, dict)
                and isinstance(step.get("action_id"), str)
                and step["action_id"].casefold() in selected_keys
                for step in steps
            ):
                continue
            title = action.get("title")
            label = title if isinstance(title, str) else owner_id
            if owner_key not in seen_dependents:
                seen_dependents.add(owner_key)
                dependents.append(label)
    if dependents:
        raise ActionDeletionError(
            "The Actions are used by these sequences: "
            + ", ".join(dependents)
            + ". Select those sequences too, or edit or delete them first."
        )


def _prepare_reference_removals_many(
    action_ids: tuple[str, ...],
    *,
    context_paths: tuple[Path, ...],
    command_surface_paths: tuple[Path, ...],
    palette_path: Path,
) -> tuple[list[tuple[Path, dict[str, object]]], int, int]:
    pending_writes: list[tuple[Path, dict[str, object]]] = []
    references_removed = 0
    buttons_removed = 0
    for path in context_paths:
        data = _read_optional_object(path)
        if data is None:
            continue
        removed = sum(
            _remove_context_references(data, action_id, path)
            for action_id in action_ids
        )
        references_removed += removed
        if removed:
            pending_writes.append((path, data))

    for path in command_surface_paths:
        data = _read_optional_object(path)
        if data is None:
            continue
        removed, removed_buttons = _remove_command_references_many(
            data,
            action_ids,
            path,
        )
        references_removed += removed
        buttons_removed += removed_buttons
        if removed or removed_buttons:
            pending_writes.append((path, data))

    palette_data = _read_optional_object(palette_path)
    if palette_data is not None:
        removed = sum(
            _remove_palette_references(palette_data, action_id)
            for action_id in action_ids
        )
        references_removed += removed
        if removed:
            pending_writes.append((palette_path, palette_data))

    return pending_writes, references_removed, buttons_removed


def _write_json_transaction(
    writes: tuple[tuple[Path, dict[str, object]], ...],
    *,
    operation: str,
) -> None:
    """Best-effort all-or-nothing commit across several configuration files."""

    primary_paths: list[Path] = []
    for path, _data in writes:
        if path in primary_paths:
            raise ActionDeletionError(
                f"{operation} tried to update {path.name} more than once."
            )
        primary_paths.append(path)

    participating = tuple(
        dict.fromkeys(
            participant
            for path in primary_paths
            for participant in (path, path.with_name(path.name + ".bak"))
        )
    )
    originals: dict[Path, bytes | None] = {}
    for path in participating:
        try:
            originals[path] = path.read_bytes() if path.exists() else None
        except OSError as exc:
            raise ActionDeletionError(
                f"{operation} could not snapshot {path.name} before writing."
            ) from exc

    attempted: list[Path] = []
    try:
        for path, data in writes:
            attempted.append(path)
            atomic_write_json(path, data)
    except OSError as exc:
        rollback_errors: list[str] = []
        for path in reversed(attempted):
            for participant in (
                path,
                path.with_name(path.name + ".bak"),
            ):
                try:
                    payload = originals[participant]
                    if payload is None:
                        participant.unlink(missing_ok=True)
                    else:
                        atomic_replace_bytes(
                            participant,
                            payload,
                            preserve_previous=False,
                        )
                except OSError as rollback_exc:
                    rollback_errors.append(
                        f"{participant.name}: {rollback_exc}"
                    )
        if rollback_errors:
            raise ActionDeletionError(
                f"{operation} failed and automatic rollback was incomplete. "
                "Reload Context Palette and recover from backup if needed. "
                + "; ".join(rollback_errors)
            ) from exc
        raise ActionDeletionError(
            f"{operation} could not be completed; all attempted configuration "
            "changes were restored."
        ) from exc


def _read_object(path: Path) -> dict[str, object]:
    data = _read_optional_object(path)
    if data is None:
        raise ActionDeletionError(f"Configuration file was not found: {path.name}")
    return data


def _read_optional_object(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ActionDeletionError(f"{path.name} could not be read as valid JSON.") from exc
    if not isinstance(value, dict):
        raise ActionDeletionError(f"{path.name} must contain a JSON object.")
    return value


def _remove_context_references(
    data: dict[str, object],
    action_id: str,
    path: Path,
) -> int:
    contexts = data.get("contexts")
    if not isinstance(contexts, list):
        raise ActionDeletionError(f"{path.name} must contain a 'contexts' list.")
    removed = 0
    for context in contexts:
        if not isinstance(context, dict):
            continue
        for field in ("preferred_action_ids", "action_ids"):
            references = context.get(field)
            if not isinstance(references, list):
                continue
            retained = [value for value in references if value != action_id]
            removed += len(references) - len(retained)
            context[field] = retained
        preferred_items = context.get("preferred_items")
        if isinstance(preferred_items, list):
            retained_items = [
                value
                for value in preferred_items
                if not (
                    isinstance(value, dict)
                    and value.get("type") == "action"
                    and value.get("action_id") == action_id
                )
            ]
            removed += len(preferred_items) - len(retained_items)
            context["preferred_items"] = retained_items
    return removed


def _remove_command_references(
    data: dict[str, object],
    action_id: str,
    path: Path,
) -> tuple[int, int]:
    return _remove_command_references_many(data, (action_id,), path)


def _remove_command_references_many(
    data: dict[str, object],
    action_ids: tuple[str, ...],
    path: Path,
) -> tuple[int, int]:
    groups = data.get("groups")
    if not isinstance(groups, list):
        raise ActionDeletionError(f"{path.name} must contain a 'groups' list.")
    selected_ids = frozenset(action_ids)
    removed_references = 0
    removed_buttons = 0
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("items"), list):
            continue
        group_removed, group_buttons_removed = _clean_command_node_many(
            group,
            selected_ids,
        )
        removed_references += group_removed
        removed_buttons += group_buttons_removed
    return removed_references, removed_buttons


def _clean_command_node(
    node: dict[str, object],
    action_id: str,
) -> tuple[int, int]:
    return _clean_command_node_many(node, frozenset({action_id}))


def _clean_command_node_many(
    node: dict[str, object],
    selected_action_ids: frozenset[str],
) -> tuple[int, int]:
    removed_references = 0
    removed_items = 0
    node_action_ids = node.get("action_ids")
    if isinstance(node_action_ids, list):
        retained_ids = [
            value for value in node_action_ids if value not in selected_action_ids
        ]
        removed_references += len(node_action_ids) - len(retained_ids)
        node["action_ids"] = retained_ids
    if node.get("primary_action_id") in selected_action_ids:
        removed_references += 1
        node["primary_action_id"] = (
            node["action_ids"][0]
            if isinstance(node.get("action_ids"), list) and node["action_ids"]
            else ""
        )
    targets = node.get("targets")
    if isinstance(targets, list):
        retained_targets = [
            target
            for target in targets
            if not (
                isinstance(target, dict)
                and target.get("type") == "action"
                and target.get("action_id") in selected_action_ids
            )
        ]
        removed_references += len(targets) - len(retained_targets)
        node["targets"] = retained_targets
    child_items = node.get("items")
    if not isinstance(child_items, list):
        return removed_references, removed_items
    retained_children: list[object] = []
    for child in child_items:
        if not isinstance(child, dict):
            retained_children.append(child)
            continue
        child_removed, descendants_removed = _clean_command_node_many(
            child,
            selected_action_ids,
        )
        removed_references += child_removed
        removed_items += descendants_removed
        has_content = bool(
            child.get("primary_action_id")
            or child.get("action_ids")
            or child.get("work_item_ref")
            or child.get("targets")
            or child.get("items")
        )
        changed_by_cleanup = bool(child_removed or descendants_removed)
        if has_content or not changed_by_cleanup:
            retained_children.append(child)
        else:
            removed_items += 1
    node["items"] = retained_children
    return removed_references, removed_items


def _remove_palette_references(data: dict[str, object], action_id: str) -> int:
    removed = 0
    pinned = data.get("pinned_action_ids")
    if isinstance(pinned, list):
        retained = [value for value in pinned if value != action_id]
        removed += len(pinned) - len(retained)
        data["pinned_action_ids"] = retained
    slots = data.get("context_slots")
    if isinstance(slots, dict):
        for context, action_ids in slots.items():
            if not isinstance(action_ids, list):
                continue
            retained = [value for value in action_ids if value != action_id]
            removed += len(action_ids) - len(retained)
            slots[context] = retained
    item_slots = data.get("context_item_slots")
    if isinstance(item_slots, dict):
        for context, references in item_slots.items():
            if not isinstance(references, list):
                continue
            retained_references = [
                reference
                for reference in references
                if not (
                    isinstance(reference, dict)
                    and reference.get("type") == "action"
                    and reference.get("action_id") == action_id
                )
            ]
            removed += len(references) - len(retained_references)
            item_slots[context] = retained_references
    return removed
