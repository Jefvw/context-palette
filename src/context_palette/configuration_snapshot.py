from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from types import MappingProxyType
from typing import TypeVar

from .actions import (
    ACTIVE_STATE,
    Action,
    ActionError,
    load_stored_actions,
)
from .cheatsheets import CheatSheet, CheatSheetError, load_cheatsheet
from .command_surface import (
    CommandGroup,
    CommandItem,
    CommandSurfaceError,
    command_group_action_ids,
    command_item_action_ids,
    command_item_id_path,
    command_item_work_item_references,
    iter_command_items,
    load_command_groups,
)
from .context_membership import CONTEXT_MEMBERSHIP_VERSION
from .contexts import ContextDefinition, ContextError, load_contexts
from .data_catalog import (
    DATA_ASSET_CATALOG,
    AppDataPaths,
    AssetRequirement,
    BackupPolicy,
    asset_spec_by_id,
)
from .inbox import InboxError, InboxItem, load_inbox_items
from .palette_state import PaletteState, load_palette_state
from .work_item_storage import (
    WorkItemCreationSettings,
    WorkItemMetadata,
    WorkItemStorageError,
    load_work_item_creation_settings,
    load_work_item_metadata,
    load_work_item_sources,
)
from .work_items import WorkItemReference, WorkItemSource


class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class ValidationCategory(str, Enum):
    STRUCTURE = "structure"
    REFERENCE = "reference"
    OWNERSHIP = "ownership"
    PORTABILITY = "portability"
    LEGACY = "legacy"
    DEPENDENCY = "dependency"


class ValidationIssueCode(str, Enum):
    REQUIRED_ASSET_MISSING = "required_asset_missing"
    ASSET_INVALID = "asset_invalid"
    DEPENDENT_CHECK_SKIPPED = "dependent_check_skipped"
    DUPLICATE_ACTION_ID = "duplicate_action_id"
    DUPLICATE_CONTEXT_NAME = "duplicate_context_name"
    DUPLICATE_COMMAND_GROUP_ID = "duplicate_command_group_id"
    DUPLICATE_INBOX_ID = "duplicate_inbox_id"
    DUPLICATE_CHEAT_SHEET_ID = "duplicate_cheat_sheet_id"
    ACTION_REFERENCE_MISSING = "action_reference_missing"
    ACTION_REFERENCE_ARCHIVED = "action_reference_archived"
    BUILT_IN_CONTEXT_PERSONAL_ACTION = "built_in_context_personal_action"
    BUILT_IN_COMMAND_PERSONAL_ACTION = "built_in_command_personal_action"
    BUILT_IN_COMMAND_WORK_ITEM = "built_in_command_work_item"
    WORK_ITEM_SOURCE_UNAVAILABLE = "work_item_source_unavailable"
    WORK_ITEM_METADATA_SOURCE_UNAVAILABLE = (
        "work_item_metadata_source_unavailable"
    )
    PALETTE_CONTEXT_CANONICALIZATION = "palette_context_canonicalization"
    PALETTE_FOCUS_UNKNOWN = "palette_focus_unknown"
    PALETTE_SLOT_CONTEXT_UNKNOWN = "palette_slot_context_unknown"
    PALETTE_SLOT_CONTEXT_DUPLICATE = "palette_slot_context_duplicate"
    PORTABILITY_ACTION_VALUE = "portability_action_value"
    PORTABILITY_WORKING_DIRECTORY = "portability_working_directory"
    PORTABILITY_ARGUMENT = "portability_argument"
    PORTABILITY_WORK_ITEM_SOURCE = "portability_work_item_source"
    PORTABILITY_WORK_ITEM_TEMPLATE = "portability_work_item_template"
    LEGACY_COMMAND_ACTION_FIELDS = "legacy_command_action_fields"
    LEGACY_COMMAND_WORK_ITEM_FIELD = "legacy_command_work_item_field"
    LEGACY_CONTEXT_MEMBERSHIP = "legacy_context_membership"
    LEGACY_CONTEXT_MEMBERSHIP_MARKER = "legacy_context_membership_marker"


@dataclass(frozen=True, slots=True)
class SnapshotValidationIssue:
    severity: ValidationSeverity
    code: ValidationIssueCode
    asset_id: str
    summary: str
    category: ValidationCategory
    subject_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        asset_spec_by_id(self.asset_id)
        clean_summary = " ".join(self.summary.split())
        if not clean_summary:
            raise ValueError("Validation issue summaries cannot be empty.")
        object.__setattr__(self, "summary", clean_summary)
        object.__setattr__(
            self,
            "subject_ids",
            tuple(dict.fromkeys(value for value in self.subject_ids if value)),
        )


@dataclass(frozen=True)
class ConfigurationSnapshot:
    paths: AppDataPaths
    built_in_actions: tuple[Action, ...] = ()
    personal_actions: tuple[Action, ...] = ()
    active_actions: tuple[Action, ...] = ()
    built_in_contexts: tuple[ContextDefinition, ...] = ()
    personal_contexts: tuple[ContextDefinition, ...] = ()
    built_in_command_groups: tuple[CommandGroup, ...] = ()
    personal_command_groups: tuple[CommandGroup, ...] = ()
    palette_state: PaletteState = field(default_factory=PaletteState)
    inbox_items: tuple[InboxItem, ...] = ()
    cheat_sheets: tuple[CheatSheet, ...] = ()
    work_item_sources: tuple[WorkItemSource, ...] = ()
    work_item_metadata: Mapping[str, WorkItemMetadata] = field(default_factory=dict)
    work_item_settings: WorkItemCreationSettings = field(
        default_factory=WorkItemCreationSettings
    )
    managed_text_content_present: bool = False
    loaded_asset_ids: frozenset[str] = frozenset()
    present_asset_ids: frozenset[str] = frozenset()
    failed_asset_ids: frozenset[str] = frozenset()
    logical_schema_versions: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for attribute in (
            "built_in_actions",
            "personal_actions",
            "active_actions",
            "built_in_contexts",
            "personal_contexts",
            "built_in_command_groups",
            "personal_command_groups",
            "inbox_items",
            "cheat_sheets",
            "work_item_sources",
        ):
            object.__setattr__(self, attribute, tuple(getattr(self, attribute)))
        object.__setattr__(
            self,
            "work_item_metadata",
            MappingProxyType(dict(self.work_item_metadata)),
        )
        palette = self.palette_state
        object.__setattr__(
            self,
            "palette_state",
            PaletteState(
                tuple(palette.pinned_action_ids),
                palette.focus_context,
                MappingProxyType(
                    {
                        context: tuple(action_ids)
                        for context, action_ids in palette.context_slots.items()
                    }
                ),
                palette.context_membership_version,
            ),
        )
        object.__setattr__(self, "loaded_asset_ids", frozenset(self.loaded_asset_ids))
        object.__setattr__(self, "present_asset_ids", frozenset(self.present_asset_ids))
        object.__setattr__(self, "failed_asset_ids", frozenset(self.failed_asset_ids))
        object.__setattr__(
            self,
            "logical_schema_versions",
            MappingProxyType(dict(self.logical_schema_versions)),
        )

    @property
    def stored_actions(self) -> tuple[Action, ...]:
        return self.built_in_actions + self.personal_actions

    @property
    def contexts(self) -> tuple[ContextDefinition, ...]:
        return self.built_in_contexts + self.personal_contexts

    @property
    def command_groups(self) -> tuple[CommandGroup, ...]:
        return self.built_in_command_groups + self.personal_command_groups


@dataclass(frozen=True)
class SnapshotValidationReport:
    snapshot: ConfigurationSnapshot
    issues: tuple[SnapshotValidationIssue, ...]
    counts: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "issues", tuple(self.issues))
        object.__setattr__(self, "counts", MappingProxyType(dict(self.counts)))

    @property
    def errors(self) -> tuple[SnapshotValidationIssue, ...]:
        return tuple(
            issue
            for issue in self.issues
            if issue.severity is ValidationSeverity.ERROR
        )

    @property
    def warnings(self) -> tuple[SnapshotValidationIssue, ...]:
        return tuple(
            issue
            for issue in self.issues
            if issue.severity is ValidationSeverity.WARNING
        )

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def valid(self) -> bool:
        return self.ok

    @property
    def restore_ready(self) -> bool:
        return self.ok


_T = TypeVar("_T")

_LOAD_ERRORS = (
    ActionError,
    CheatSheetError,
    CommandSurfaceError,
    ContextError,
    InboxError,
    WorkItemStorageError,
    OSError,
    UnicodeError,
)

_ASSET_LABELS = {
    "built-in-actions": "Actions",
    "personal-actions": "Actions",
    "built-in-contexts": "Contexts",
    "personal-contexts": "Contexts",
    "built-in-command-surface": "Command surface",
    "personal-command-surface": "Command surface",
    "palette-state": "Palette state",
    "inbox": "Inbox",
    "built-in-cheat-sheets": "Cheat sheets",
    "work-item-sources": "Work Item sources",
    "work-item-metadata": "Work Item metadata",
    "work-item-settings": "Work Item settings",
}

_LOCAL_TARGET_ACTION_TYPES = frozenset(
    {
        "open_windows_target",
        "open_file",
        "open_folder",
        "launch_app",
        "transform_file_text",
    }
)

_ENVIRONMENT_PLACEHOLDER = re.compile(r"%[A-Za-z_][A-Za-z0-9_]*%")
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_WINDOWS_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:[\\/]")


class _SnapshotBuilder:
    def __init__(self, paths: AppDataPaths) -> None:
        self.paths = paths
        self.issues: list[SnapshotValidationIssue] = []
        self.loaded_asset_ids: set[str] = set()
        self.present_asset_ids: set[str] = set()
        self.failed_asset_ids: set[str] = set()

    def issue(
        self,
        severity: ValidationSeverity,
        code: ValidationIssueCode,
        asset_id: str,
        summary: str,
        category: ValidationCategory,
        subject_ids: tuple[str, ...] = (),
    ) -> None:
        self.issues.append(
            SnapshotValidationIssue(
                severity,
                code,
                asset_id,
                summary,
                category,
                subject_ids,
            )
        )

    def load_asset(
        self,
        asset_id: str,
        path: Path,
        loader: Callable[[], _T],
        default: _T,
    ) -> _T:
        spec = asset_spec_by_id(asset_id)
        if not path.exists():
            if spec.requirement is AssetRequirement.REQUIRED:
                self.failed_asset_ids.add(asset_id)
                self.issue(
                    ValidationSeverity.ERROR,
                    ValidationIssueCode.REQUIRED_ASSET_MISSING,
                    asset_id,
                    f"{_ASSET_LABELS[asset_id]}: required file is missing.",
                    ValidationCategory.STRUCTURE,
                )
            else:
                self.loaded_asset_ids.add(asset_id)
            return default
        self.present_asset_ids.add(asset_id)
        try:
            result = loader()
        except _LOAD_ERRORS as exc:
            self.failed_asset_ids.add(asset_id)
            self.issue(
                ValidationSeverity.ERROR,
                ValidationIssueCode.ASSET_INVALID,
                asset_id,
                _safe_loader_summary(asset_id, exc),
                ValidationCategory.STRUCTURE,
            )
            return default
        self.loaded_asset_ids.add(asset_id)
        return result


def load_configuration_snapshot(paths: AppDataPaths) -> SnapshotValidationReport:
    """Load and validate one complete, read-only application-data snapshot."""

    builder = _SnapshotBuilder(paths)

    built_in_actions = tuple(
        builder.load_asset(
            "built-in-actions",
            paths.built_in_actions_file,
            lambda: load_stored_actions(
                paths.built_in_actions_file,
                inspect_external_paths=False,
            ),
            [],
        )
    )
    personal_actions = tuple(
        builder.load_asset(
            "personal-actions",
            paths.personal_actions_file,
            lambda: load_stored_actions(
                paths.personal_actions_file,
                inspect_external_paths=False,
            ),
            [],
        )
    )
    built_in_contexts = tuple(
        builder.load_asset(
            "built-in-contexts",
            paths.built_in_contexts_file,
            lambda: load_contexts(paths.built_in_contexts_file),
            [],
        )
    )
    personal_contexts = tuple(
        builder.load_asset(
            "personal-contexts",
            paths.personal_contexts_file,
            lambda: load_contexts(paths.personal_contexts_file),
            [],
        )
    )
    built_in_command_groups = tuple(
        builder.load_asset(
            "built-in-command-surface",
            paths.built_in_command_surface_file,
            lambda: load_command_groups(paths.built_in_command_surface_file),
            [],
        )
    )
    personal_command_groups = tuple(
        builder.load_asset(
            "personal-command-surface",
            paths.personal_command_surface_file,
            lambda: load_command_groups(paths.personal_command_surface_file),
            [],
        )
    )
    palette_state = builder.load_asset(
        "palette-state",
        paths.palette_state_file,
        lambda: load_palette_state(paths.palette_state_file),
        PaletteState(),
    )
    inbox_items = tuple(
        builder.load_asset(
            "inbox",
            paths.inbox_file,
            lambda: load_inbox_items(paths.inbox_file),
            [],
        )
    )
    cheat_sheets = _load_cheat_sheets(builder)
    work_item_sources = tuple(
        builder.load_asset(
            "work-item-sources",
            paths.work_item_sources_file,
            lambda: load_work_item_sources(paths.work_item_sources_file),
            (),
        )
    )
    work_item_metadata = builder.load_asset(
        "work-item-metadata",
        paths.work_item_metadata_file,
        lambda: load_work_item_metadata(paths.work_item_metadata_file),
        {},
    )
    work_item_settings = builder.load_asset(
        "work-item-settings",
        paths.work_item_settings_file,
        lambda: load_work_item_creation_settings(paths.work_item_settings_file),
        WorkItemCreationSettings(),
    )

    managed_content_present = paths.managed_text_action_source_file.exists()
    if managed_content_present:
        builder.present_asset_ids.add("managed-text-action-source")
    builder.loaded_asset_ids.add("managed-text-action-source")

    stored_actions = built_in_actions + personal_actions
    active_actions = tuple(
        action for action in stored_actions if action.state == ACTIVE_STATE
    )
    logical_schema_versions = {
        spec.asset_id: spec.schema_version
        for spec in DATA_ASSET_CATALOG
        if spec.schema_version is not None
        and spec.backup_policy is not BackupPolicy.EXCLUDED
    }
    snapshot = ConfigurationSnapshot(
        paths=paths,
        built_in_actions=built_in_actions,
        personal_actions=personal_actions,
        active_actions=active_actions,
        built_in_contexts=built_in_contexts,
        personal_contexts=personal_contexts,
        built_in_command_groups=built_in_command_groups,
        personal_command_groups=personal_command_groups,
        palette_state=palette_state,
        inbox_items=inbox_items,
        cheat_sheets=cheat_sheets,
        work_item_sources=work_item_sources,
        work_item_metadata=work_item_metadata,
        work_item_settings=work_item_settings,
        managed_text_content_present=managed_content_present,
        loaded_asset_ids=frozenset(builder.loaded_asset_ids),
        present_asset_ids=frozenset(builder.present_asset_ids),
        failed_asset_ids=frozenset(builder.failed_asset_ids),
        logical_schema_versions=logical_schema_versions,
    )

    action_identities_valid = _validate_stable_identities(builder, snapshot)
    _validate_action_references(builder, snapshot, action_identities_valid)
    _validate_work_item_references(builder, snapshot)
    _classify_palette_contexts(builder, snapshot)
    _classify_portability(builder, snapshot)
    _classify_legacy_data(builder, snapshot)

    counts = {
        "actions": len(snapshot.active_actions),
        "archived_actions": len(snapshot.stored_actions) - len(snapshot.active_actions),
        "stored_actions": len(snapshot.stored_actions),
        "contexts": len(snapshot.contexts),
        "command_groups": len(snapshot.command_groups),
        "pinned_actions": len(snapshot.palette_state.pinned_action_ids),
        "inbox_items": len(snapshot.inbox_items),
        "cheatsheets": len(snapshot.cheat_sheets),
        "work_item_sources": len(snapshot.work_item_sources),
        "work_item_metadata": len(snapshot.work_item_metadata),
        "work_item_settings": int(snapshot.work_item_settings.template_path is not None),
        "managed_text_content": int(snapshot.managed_text_content_present),
    }
    return SnapshotValidationReport(snapshot, tuple(builder.issues), counts)


def _load_cheat_sheets(builder: _SnapshotBuilder) -> tuple[CheatSheet, ...]:
    asset_id = "built-in-cheat-sheets"
    spec = asset_spec_by_id(asset_id)
    pattern = PurePosixPath(spec.relative_pattern or "")
    directory = builder.paths.cheat_sheets_directory
    if not directory.exists():
        builder.loaded_asset_ids.add(asset_id)
        return ()
    builder.present_asset_ids.add(asset_id)
    if not directory.is_dir():
        builder.failed_asset_ids.add(asset_id)
        builder.issue(
            ValidationSeverity.ERROR,
            ValidationIssueCode.ASSET_INVALID,
            asset_id,
            "Cheat sheets: catalogued location is not a directory.",
            ValidationCategory.STRUCTURE,
        )
        return ()
    sheets: list[CheatSheet] = []
    failed = False
    try:
        matching_paths = sorted(directory.glob(pattern.name))
    except OSError as exc:
        matching_paths = []
        failed = True
        builder.issue(
            ValidationSeverity.ERROR,
            ValidationIssueCode.ASSET_INVALID,
            asset_id,
            _safe_loader_summary(asset_id, exc),
            ValidationCategory.STRUCTURE,
        )
    for path in matching_paths:
        try:
            sheets.append(load_cheatsheet(path))
        except (CheatSheetError, OSError, UnicodeError) as exc:
            failed = True
            builder.issue(
                ValidationSeverity.ERROR,
                ValidationIssueCode.ASSET_INVALID,
                asset_id,
                _safe_loader_summary(asset_id, exc),
                ValidationCategory.STRUCTURE,
            )
    if failed:
        builder.failed_asset_ids.add(asset_id)
    else:
        builder.loaded_asset_ids.add(asset_id)
    return tuple(sheets)


def _safe_loader_summary(asset_id: str, error: Exception) -> str:
    label = _ASSET_LABELS[asset_id]
    detail = str(error).casefold()
    if "json" in detail:
        return f"{label}: file is not valid JSON."
    return f"{label}: configuration is malformed or could not be read."


def _validate_stable_identities(
    builder: _SnapshotBuilder,
    snapshot: ConfigurationSnapshot,
) -> bool:
    action_conflicts = _duplicate_identities(
        (
            ("built-in-actions", action.id)
            for action in snapshot.built_in_actions
        ),
        (
            ("personal-actions", action.id)
            for action in snapshot.personal_actions
        ),
    )
    for asset_id, first_id, duplicate_id in action_conflicts:
        builder.issue(
            ValidationSeverity.ERROR,
            ValidationIssueCode.DUPLICATE_ACTION_ID,
            asset_id,
            "Action IDs conflict case-insensitively across Built-in and "
            f"personal configuration: {first_id} and {duplicate_id}",
            ValidationCategory.STRUCTURE,
            (first_id, duplicate_id),
        )

    context_conflicts = _duplicate_identities(
        (("built-in-contexts", item.name) for item in snapshot.built_in_contexts),
        (("personal-contexts", item.name) for item in snapshot.personal_contexts),
    )
    for asset_id, first_name, duplicate_name in context_conflicts:
        builder.issue(
            ValidationSeverity.ERROR,
            ValidationIssueCode.DUPLICATE_CONTEXT_NAME,
            asset_id,
            "Context names conflict case-insensitively: "
            f"{first_name} and {duplicate_name}",
            ValidationCategory.STRUCTURE,
            (first_name, duplicate_name),
        )

    group_conflicts = _duplicate_identities(
        (
            ("built-in-command-surface", item.id)
            for item in snapshot.built_in_command_groups
        ),
        (
            ("personal-command-surface", item.id)
            for item in snapshot.personal_command_groups
        ),
    )
    for asset_id, first_id, duplicate_id in group_conflicts:
        builder.issue(
            ValidationSeverity.ERROR,
            ValidationIssueCode.DUPLICATE_COMMAND_GROUP_ID,
            asset_id,
            "Quick-action group IDs conflict case-insensitively: "
            f"{first_id} and {duplicate_id}",
            ValidationCategory.STRUCTURE,
            (first_id, duplicate_id),
        )

    _report_single_collection_duplicates(
        builder,
        "inbox",
        ((item.id, item.id) for item in snapshot.inbox_items),
        ValidationIssueCode.DUPLICATE_INBOX_ID,
        "Inbox item IDs must be unique case-insensitively",
    )
    _report_single_collection_duplicates(
        builder,
        "built-in-cheat-sheets",
        ((item.id, item.id) for item in snapshot.cheat_sheets),
        ValidationIssueCode.DUPLICATE_CHEAT_SHEET_ID,
        "Cheat-sheet IDs must be unique case-insensitively",
    )
    return not action_conflicts


def _duplicate_identities(
    *collections: Iterable[tuple[str, str]],
) -> list[tuple[str, str, str]]:
    seen: dict[str, tuple[str, str]] = {}
    conflicts: list[tuple[str, str, str]] = []
    for collection in collections:
        for asset_id, identity in collection:
            key = identity.casefold()
            if key in seen:
                conflicts.append((asset_id, seen[key][1], identity))
            else:
                seen[key] = (asset_id, identity)
    return conflicts


def _report_single_collection_duplicates(
    builder: _SnapshotBuilder,
    asset_id: str,
    identities: Iterable[tuple[str, str]],
    code: ValidationIssueCode,
    summary: str,
) -> None:
    seen: dict[str, str] = {}
    for identity, subject_id in identities:
        key = identity.casefold()
        if key in seen:
            builder.issue(
                ValidationSeverity.ERROR,
                code,
                asset_id,
                f"{summary}: {seen[key]} and {identity}",
                ValidationCategory.STRUCTURE,
                (seen[key], subject_id),
            )
        else:
            seen[key] = identity


def _validate_action_references(
    builder: _SnapshotBuilder,
    snapshot: ConfigurationSnapshot,
    action_identities_valid: bool,
) -> None:
    for group in snapshot.built_in_command_groups:
        for _path, item in iter_command_items(group):
            if command_item_work_item_references(item):
                builder.issue(
                    ValidationSeverity.ERROR,
                    ValidationIssueCode.BUILT_IN_COMMAND_WORK_ITEM,
                    "built-in-command-surface",
                    "Built-in Quick actions cannot reference personal Work Items.",
                    ValidationCategory.OWNERSHIP,
                    (group.id, item.id),
                )

    action_assets = {"built-in-actions", "personal-actions"}
    if (
        not action_assets.issubset(snapshot.loaded_asset_ids)
        or not action_identities_valid
    ):
        failed_asset = next(
            iter(action_assets & snapshot.failed_asset_ids),
            "built-in-actions",
        )
        builder.issue(
            ValidationSeverity.WARNING,
            ValidationIssueCode.DEPENDENT_CHECK_SKIPPED,
            failed_asset,
            "Action-reference checks were skipped because complete, "
            "unambiguous Action data is unavailable.",
            ValidationCategory.DEPENDENCY,
        )
        return

    active_ids = {action.id for action in snapshot.active_actions}
    stored_ids = {action.id for action in snapshot.stored_actions}
    personal_ids = {action.id for action in snapshot.personal_actions}

    for asset_id, contexts, built_in in (
        ("built-in-contexts", snapshot.built_in_contexts, True),
        ("personal-contexts", snapshot.personal_contexts, False),
    ):
        if asset_id not in snapshot.loaded_asset_ids:
            continue
        for context in contexts:
            for action_id in dict.fromkeys(
                (*(context.action_ids or ()), *context.preferred_action_ids)
            ):
                _report_action_reference(
                    builder,
                    asset_id,
                    action_id,
                    active_ids,
                    stored_ids,
                    f"Context '{context.name}'",
                )
                if built_in and action_id in personal_ids:
                    builder.issue(
                        ValidationSeverity.ERROR,
                        ValidationIssueCode.BUILT_IN_CONTEXT_PERSONAL_ACTION,
                        asset_id,
                        f"Built-in context '{context.name}' references "
                        f"My configuration action: {action_id}",
                        ValidationCategory.OWNERSHIP,
                        (action_id,),
                    )

    if "palette-state" in snapshot.loaded_asset_ids:
        for action_id in snapshot.palette_state.pinned_action_ids:
            _report_action_reference(
                builder,
                "palette-state",
                action_id,
                active_ids,
                stored_ids,
                "Pinned action",
            )
        for context_name, action_ids in snapshot.palette_state.context_slots.items():
            for action_id in action_ids:
                _report_action_reference(
                    builder,
                    "palette-state",
                    action_id,
                    active_ids,
                    stored_ids,
                    f"Palette context '{context_name}'",
                )

    for asset_id, groups, built_in in (
        (
            "built-in-command-surface",
            snapshot.built_in_command_groups,
            True,
        ),
        (
            "personal-command-surface",
            snapshot.personal_command_groups,
            False,
        ),
    ):
        if asset_id not in snapshot.loaded_asset_ids:
            continue
        for group in groups:
            nodes = [(group.id, command_group_action_ids(group))]
            nodes.extend(
                (
                    "/".join((group.id, *command_item_id_path(group, path))),
                    command_item_action_ids(item),
                )
                for path, item in iter_command_items(group)
            )
            for _node_id, action_ids in nodes:
                for action_id in action_ids:
                    _report_action_reference(
                        builder,
                        asset_id,
                        action_id,
                        active_ids,
                        stored_ids,
                        "Command item",
                    )
                    if built_in and action_id in personal_ids:
                        builder.issue(
                            ValidationSeverity.ERROR,
                            ValidationIssueCode.BUILT_IN_COMMAND_PERSONAL_ACTION,
                            asset_id,
                            "Built-in Quick action references local-only "
                            f"action: {action_id}",
                            ValidationCategory.OWNERSHIP,
                            (action_id,),
                        )


def _report_action_reference(
    builder: _SnapshotBuilder,
    asset_id: str,
    action_id: str,
    active_ids: set[str],
    stored_ids: set[str],
    owner: str,
) -> None:
    if action_id in active_ids:
        return
    archived = action_id in stored_ids
    builder.issue(
        ValidationSeverity.ERROR,
        (
            ValidationIssueCode.ACTION_REFERENCE_ARCHIVED
            if archived
            else ValidationIssueCode.ACTION_REFERENCE_MISSING
        ),
        asset_id,
        f"{owner} references {'archived' if archived else 'missing'} action: "
        f"{action_id}",
        ValidationCategory.REFERENCE,
        (action_id,),
    )


def _validate_work_item_references(
    builder: _SnapshotBuilder,
    snapshot: ConfigurationSnapshot,
) -> None:
    references_by_asset: dict[str, list[WorkItemReference]] = {
        "built-in-command-surface": [],
        "personal-command-surface": [],
    }
    for asset_id, groups in (
        ("built-in-command-surface", snapshot.built_in_command_groups),
        ("personal-command-surface", snapshot.personal_command_groups),
    ):
        if asset_id not in snapshot.loaded_asset_ids:
            continue
        for group in groups:
            for _path, item in iter_command_items(group):
                references_by_asset[asset_id].extend(
                    command_item_work_item_references(item)
                )

    if "work-item-sources" not in snapshot.loaded_asset_ids:
        if any(references_by_asset.values()) or snapshot.work_item_metadata:
            builder.issue(
                ValidationSeverity.WARNING,
                ValidationIssueCode.DEPENDENT_CHECK_SKIPPED,
                "work-item-sources",
                "Work Item source-reference checks were skipped because source "
                "configuration is unavailable.",
                ValidationCategory.DEPENDENCY,
            )
        return

    source_ids = {source.id.casefold() for source in snapshot.work_item_sources}
    for asset_id, references in references_by_asset.items():
        if asset_id == "built-in-command-surface":
            continue
        for source_id in sorted(
            {
                reference.source_id
                for reference in references
                if reference.source_id.casefold() not in source_ids
            },
            key=str.casefold,
        ):
            builder.issue(
                ValidationSeverity.WARNING,
                ValidationIssueCode.WORK_ITEM_SOURCE_UNAVAILABLE,
                asset_id,
                "Quick action references unavailable Work Item source: "
                f"{source_id}",
                ValidationCategory.REFERENCE,
                (source_id,),
            )

    if "work-item-metadata" not in snapshot.loaded_asset_ids:
        return
    missing_metadata_sources = sorted(
        {
            key.partition("/")[0]
            for key in snapshot.work_item_metadata
            if key.partition("/")[0].casefold() not in source_ids
        },
        key=str.casefold,
    )
    for source_id in missing_metadata_sources:
        builder.issue(
            ValidationSeverity.WARNING,
            ValidationIssueCode.WORK_ITEM_METADATA_SOURCE_UNAVAILABLE,
            "work-item-metadata",
            "Work Item metadata references unavailable source: "
            f"{source_id}",
            ValidationCategory.REFERENCE,
            (source_id,),
        )


def _classify_palette_contexts(
    builder: _SnapshotBuilder,
    snapshot: ConfigurationSnapshot,
) -> None:
    if "palette-state" not in snapshot.loaded_asset_ids:
        return
    context_assets = {"built-in-contexts", "personal-contexts"}
    context_duplicates = any(
        issue.code is ValidationIssueCode.DUPLICATE_CONTEXT_NAME
        for issue in builder.issues
    )
    if not context_assets.issubset(snapshot.loaded_asset_ids) or context_duplicates:
        builder.issue(
            ValidationSeverity.WARNING,
            ValidationIssueCode.DEPENDENT_CHECK_SKIPPED,
            "palette-state",
            "Palette context classification was skipped because complete, "
            "unambiguous Context data is unavailable.",
            ValidationCategory.DEPENDENCY,
        )
        return

    names_by_key = {"general": "General"}
    for context in snapshot.contexts:
        names_by_key[context.name.casefold()] = context.name

    focus = snapshot.palette_state.focus_context
    focus_canonical = names_by_key.get(focus.casefold())
    if focus_canonical is None:
        builder.issue(
            ValidationSeverity.WARNING,
            ValidationIssueCode.PALETTE_FOCUS_UNKNOWN,
            "palette-state",
            f"Palette Focus context is unknown and runtime falls back to "
            f"General: {focus}",
            ValidationCategory.REFERENCE,
            (focus,),
        )
    elif focus != focus_canonical:
        builder.issue(
            ValidationSeverity.WARNING,
            ValidationIssueCode.PALETTE_CONTEXT_CANONICALIZATION,
            "palette-state",
            f"Palette Focus context uses non-canonical spelling; runtime uses "
            f"{focus_canonical}.",
            ValidationCategory.REFERENCE,
            (focus, focus_canonical),
        )

    keys_by_casefold: dict[str, list[str]] = {}
    for raw_key in snapshot.palette_state.context_slots:
        keys_by_casefold.setdefault(raw_key.casefold(), []).append(raw_key)
        canonical = names_by_key.get(raw_key.casefold())
        if canonical is None:
            builder.issue(
                ValidationSeverity.WARNING,
                ValidationIssueCode.PALETTE_SLOT_CONTEXT_UNKNOWN,
                "palette-state",
                "Palette context slots preserve an unknown historical context: "
                f"{raw_key}",
                ValidationCategory.REFERENCE,
                (raw_key,),
            )
        elif raw_key != canonical:
            builder.issue(
                ValidationSeverity.WARNING,
                ValidationIssueCode.PALETTE_CONTEXT_CANONICALIZATION,
                "palette-state",
                "Palette context-slot key uses non-canonical spelling; runtime "
                f"uses {canonical}.",
                ValidationCategory.REFERENCE,
                (raw_key, canonical),
            )
    for key_group in keys_by_casefold.values():
        if len(key_group) < 2:
            continue
        canonical = names_by_key.get(key_group[0].casefold())
        precedence = (
            f"exact canonical key {canonical} takes precedence"
            if canonical in key_group
            else "the first matching spelling takes precedence"
        )
        builder.issue(
            ValidationSeverity.WARNING,
            ValidationIssueCode.PALETTE_SLOT_CONTEXT_DUPLICATE,
            "palette-state",
            "Palette contains case-insensitive duplicate context-slot keys; "
            f"{precedence}.",
            ValidationCategory.REFERENCE,
            tuple(key_group),
        )


def _classify_portability(
    builder: _SnapshotBuilder,
    snapshot: ConfigurationSnapshot,
) -> None:
    for asset_id, actions in (
        ("built-in-actions", snapshot.built_in_actions),
        ("personal-actions", snapshot.personal_actions),
    ):
        if asset_id not in snapshot.loaded_asset_ids:
            continue
        value_ids = tuple(
            action.id
            for action in actions
            if action.type in _LOCAL_TARGET_ACTION_TYPES
            and _is_absolute_windows_dependency(action.value)
        )
        working_directory_ids = tuple(
            action.id
            for action in actions
            if action.working_directory
            and _is_absolute_windows_dependency(action.working_directory)
        )
        argument_ids = tuple(
            action.id
            for action in actions
            if any(
                _is_absolute_windows_dependency(argument)
                for argument in action.arguments
            )
        )
        _add_portability_issue(
            builder,
            asset_id,
            ValidationIssueCode.PORTABILITY_ACTION_VALUE,
            value_ids,
            "Action target",
        )
        _add_portability_issue(
            builder,
            asset_id,
            ValidationIssueCode.PORTABILITY_WORKING_DIRECTORY,
            working_directory_ids,
            "Action working directory",
        )
        _add_portability_issue(
            builder,
            asset_id,
            ValidationIssueCode.PORTABILITY_ARGUMENT,
            argument_ids,
            "Action argument",
        )

    if (
        "work-item-sources" in snapshot.loaded_asset_ids
        and snapshot.work_item_sources
    ):
        _add_portability_issue(
            builder,
            "work-item-sources",
            ValidationIssueCode.PORTABILITY_WORK_ITEM_SOURCE,
            tuple(source.id for source in snapshot.work_item_sources),
            "Work Item source",
        )
    if (
        "work-item-settings" in snapshot.loaded_asset_ids
        and snapshot.work_item_settings.template_path is not None
    ):
        _add_portability_issue(
            builder,
            "work-item-settings",
            ValidationIssueCode.PORTABILITY_WORK_ITEM_TEMPLATE,
            ("template",),
            "Work Item template",
        )


def _add_portability_issue(
    builder: _SnapshotBuilder,
    asset_id: str,
    code: ValidationIssueCode,
    subject_ids: tuple[str, ...],
    label: str,
) -> None:
    if not subject_ids:
        return
    builder.issue(
        ValidationSeverity.WARNING,
        code,
        asset_id,
        f"{label} configuration contains {len(subject_ids)} machine-local "
        "path reference(s); raw paths are omitted.",
        ValidationCategory.PORTABILITY,
        subject_ids,
    )


def _is_absolute_windows_dependency(value: str) -> bool:
    clean = value.strip()
    if len(clean) >= 2 and clean[0] == clean[-1] and clean[0] in {'"', "'"}:
        clean = clean[1:-1].strip()
    if not clean or _ENVIRONMENT_PLACEHOLDER.search(clean):
        return False
    if clean.casefold().startswith("file:"):
        return True
    if _URI_SCHEME.match(clean) and not _WINDOWS_DRIVE_PREFIX.match(clean):
        return False
    return PureWindowsPath(clean).is_absolute()


def _classify_legacy_data(
    builder: _SnapshotBuilder,
    snapshot: ConfigurationSnapshot,
) -> None:
    for asset_id, groups in (
        ("built-in-command-surface", snapshot.built_in_command_groups),
        ("personal-command-surface", snapshot.personal_command_groups),
    ):
        if asset_id not in snapshot.loaded_asset_ids:
            continue
        legacy_action_items: list[str] = []
        legacy_work_item_items: list[str] = []
        for group in groups:
            for _path, item in iter_command_items(group):
                if not item.targets and (
                    item.primary_action_id or item.action_ids
                ):
                    legacy_action_items.append(item.id)
                if item.work_item_ref is not None:
                    legacy_work_item_items.append(item.id)
        if legacy_action_items:
            builder.issue(
                ValidationSeverity.WARNING,
                ValidationIssueCode.LEGACY_COMMAND_ACTION_FIELDS,
                asset_id,
                "Quick actions use legacy action-reference fields accepted by "
                "the current loader.",
                ValidationCategory.LEGACY,
                tuple(legacy_action_items),
            )
        if legacy_work_item_items:
            builder.issue(
                ValidationSeverity.WARNING,
                ValidationIssueCode.LEGACY_COMMAND_WORK_ITEM_FIELD,
                asset_id,
                "Quick actions use the legacy single Work Item reference field "
                "accepted by the current loader.",
                ValidationCategory.LEGACY,
                tuple(legacy_work_item_items),
            )

    for asset_id, contexts in (
        ("built-in-contexts", snapshot.built_in_contexts),
        ("personal-contexts", snapshot.personal_contexts),
    ):
        if asset_id not in snapshot.loaded_asset_ids:
            continue
        legacy_names = tuple(
            context.name for context in contexts if context.action_ids is None
        )
        if legacy_names:
            builder.issue(
                ValidationSeverity.WARNING,
                ValidationIssueCode.LEGACY_CONTEXT_MEMBERSHIP,
                asset_id,
                "Context definitions rely on legacy Action-side membership.",
                ValidationCategory.LEGACY,
                legacy_names,
            )

    if (
        "palette-state" in snapshot.loaded_asset_ids
        and "palette-state" in snapshot.present_asset_ids
        and snapshot.palette_state.context_membership_version
        < CONTEXT_MEMBERSHIP_VERSION
    ):
        builder.issue(
            ValidationSeverity.WARNING,
            ValidationIssueCode.LEGACY_CONTEXT_MEMBERSHIP_MARKER,
            "palette-state",
            "Palette context-membership migration marker is older than the "
            "current logical model; no migration was run.",
            ValidationCategory.LEGACY,
        )
