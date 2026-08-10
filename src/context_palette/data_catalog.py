from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath, PureWindowsPath


class AssetOwnership(str, Enum):
    BUILT_IN = "built-in/shared"
    PERSONAL = "personal/local"
    MACHINE_LOCAL = "machine-local"
    CAPTURED_CONTENT = "captured-content"
    DERIVED_RUNTIME = "derived/runtime"


class AssetRequirement(str, Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"


class AssetSensitivity(str, Enum):
    CONFIGURATION = "configuration"
    PRIVATE_PATHS = "private-paths"
    CAPTURED_CONTENT = "captured-content"
    DIAGNOSTICS = "diagnostics"
    PRIVATE_RUNTIME_DATA = "private-runtime-data"


class BackupPolicy(str, Enum):
    CORE_CONFIGURATION = "core-configuration"
    COMPLETE_CONFIGURATION_ADDITION = "complete-configuration-addition"
    OPTIONAL_MANAGED_CONTENT = "optional-managed-content"
    EXCLUDED = "excluded"


@dataclass(frozen=True)
class AppDataPaths:
    """Known application-owned paths derived from one data directory."""

    data_directory: Path

    @classmethod
    def from_root(cls, application_root: Path) -> AppDataPaths:
        return cls(Path(application_root) / "data")

    @classmethod
    def from_data_directory(cls, data_directory: Path) -> AppDataPaths:
        return cls(Path(data_directory))

    @property
    def application_root(self) -> Path:
        return self.data_directory.parent

    @property
    def built_in_actions_file(self) -> Path:
        return self.data_directory / "actions.json"

    @property
    def personal_actions_file(self) -> Path:
        return self.data_directory / "local_actions.json"

    @property
    def built_in_contexts_file(self) -> Path:
        return self.data_directory / "contexts.json"

    @property
    def personal_contexts_file(self) -> Path:
        return self.data_directory / "local_contexts.json"

    @property
    def built_in_command_surface_file(self) -> Path:
        return self.data_directory / "command_surface.json"

    @property
    def personal_command_surface_file(self) -> Path:
        return self.data_directory / "local_command_surface.json"

    @property
    def palette_state_file(self) -> Path:
        return self.data_directory / "palette.json"

    @property
    def inbox_file(self) -> Path:
        return self.data_directory / "inbox.json"

    @property
    def cheat_sheets_directory(self) -> Path:
        return self.data_directory / "cheatsheets"

    @property
    def work_item_sources_file(self) -> Path:
        return self.data_directory / "local_work_item_sources.json"

    @property
    def work_item_metadata_file(self) -> Path:
        return self.data_directory / "local_work_item_metadata.json"

    @property
    def work_item_settings_file(self) -> Path:
        return self.data_directory / "local_work_item_settings.json"

    @property
    def managed_text_action_source_file(self) -> Path:
        return self.data_directory / "local_text_action_source.txt"

    @property
    def diagnostic_log_file(self) -> Path:
        return self.data_directory / "context-palette.log"

    @property
    def restore_journal_file(self) -> Path:
        return self.data_directory / "restore-journal.json"


@dataclass(frozen=True)
class DataAssetSpec:
    asset_id: str
    ownership: AssetOwnership
    requirement: AssetRequirement
    sensitivity: AssetSensitivity
    backup_policy: BackupPolicy
    relative_path: PurePosixPath | None = None
    relative_pattern: str | None = None
    schema_version: int | None = None

    def __post_init__(self) -> None:
        if not self.asset_id or self.asset_id != self.asset_id.strip():
            raise ValueError("Asset IDs must be non-empty and trimmed.")
        if (self.relative_path is None) == (self.relative_pattern is None):
            raise ValueError("An asset needs exactly one relative path or pattern.")
        if self.schema_version is not None and (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version < 1
        ):
            raise ValueError("Schema versions must be positive integers.")
        if self.relative_path is not None:
            _validate_relative_location(self.relative_path, allow_pattern=False)
        else:
            _validate_relative_location(
                PurePosixPath(self.relative_pattern or ""),
                allow_pattern=True,
            )

    @property
    def is_pattern(self) -> bool:
        return self.relative_pattern is not None

    def path_for(self, paths: AppDataPaths) -> Path:
        if self.relative_path is None:
            raise ValueError(f"Pattern asset {self.asset_id!r} has no single path.")
        if self.relative_path.parts[0] == "data":
            return paths.data_directory.joinpath(*self.relative_path.parts[1:])
        return paths.application_root.joinpath(*self.relative_path.parts)

    def matches(self, relative_path: str | Path | PurePosixPath) -> bool:
        candidate = _safe_relative_path(relative_path)
        if candidate is None:
            return False
        if self.relative_path is not None:
            return candidate == self.relative_path
        pattern = PurePosixPath(self.relative_pattern or "")
        return (
            candidate.parent == pattern.parent
            and fnmatchcase(candidate.name, pattern.name)
        )


def _validate_relative_location(path: PurePosixPath, *, allow_pattern: bool) -> None:
    text = str(path)
    windows_path = PureWindowsPath(text)
    if (
        not path.parts
        or path.is_absolute()
        or windows_path.drive
        or windows_path.root
        or "\\" in text
        or ".." in path.parts
    ):
        raise ValueError("Asset locations must remain below the application root.")
    if any(part in {"", "."} for part in path.parts):
        raise ValueError("Asset locations must use normalized relative paths.")
    wildcard_parts = [
        index
        for index, part in enumerate(path.parts)
        if any(character in part for character in "*?[]")
    ]
    if wildcard_parts and (
        not allow_pattern
        or wildcard_parts != [len(path.parts) - 1]
        or "**" in path.parts[-1]
    ):
        raise ValueError("Catalog patterns may vary only the final path component.")


def _safe_relative_path(
    path: str | Path | PurePosixPath,
) -> PurePosixPath | None:
    raw_text = str(path)
    windows_path = PureWindowsPath(raw_text)
    if windows_path.drive or windows_path.root:
        return None
    text = raw_text.replace("\\", "/")
    candidate = PurePosixPath(text)
    try:
        _validate_relative_location(candidate, allow_pattern=False)
    except ValueError:
        return None
    return candidate


DATA_ASSET_CATALOG: tuple[DataAssetSpec, ...] = (
    DataAssetSpec(
        "built-in-actions",
        AssetOwnership.BUILT_IN,
        AssetRequirement.REQUIRED,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.COMPLETE_CONFIGURATION_ADDITION,
        relative_path=PurePosixPath("data/actions.json"),
        schema_version=1,
    ),
    DataAssetSpec(
        "built-in-contexts",
        AssetOwnership.BUILT_IN,
        AssetRequirement.REQUIRED,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.COMPLETE_CONFIGURATION_ADDITION,
        relative_path=PurePosixPath("data/contexts.json"),
        schema_version=2,
    ),
    DataAssetSpec(
        "built-in-command-surface",
        AssetOwnership.BUILT_IN,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.COMPLETE_CONFIGURATION_ADDITION,
        relative_path=PurePosixPath("data/command_surface.json"),
        schema_version=1,
    ),
    DataAssetSpec(
        "built-in-cheat-sheets",
        AssetOwnership.BUILT_IN,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.COMPLETE_CONFIGURATION_ADDITION,
        relative_pattern="data/cheatsheets/*.json",
        schema_version=1,
    ),
    DataAssetSpec(
        "personal-actions",
        AssetOwnership.PERSONAL,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.CORE_CONFIGURATION,
        relative_path=PurePosixPath("data/local_actions.json"),
        schema_version=1,
    ),
    DataAssetSpec(
        "personal-contexts",
        AssetOwnership.PERSONAL,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.CORE_CONFIGURATION,
        relative_path=PurePosixPath("data/local_contexts.json"),
        schema_version=2,
    ),
    DataAssetSpec(
        "personal-command-surface",
        AssetOwnership.PERSONAL,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.CORE_CONFIGURATION,
        relative_path=PurePosixPath("data/local_command_surface.json"),
        schema_version=1,
    ),
    DataAssetSpec(
        "palette-state",
        AssetOwnership.MACHINE_LOCAL,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.CORE_CONFIGURATION,
        relative_path=PurePosixPath("data/palette.json"),
        schema_version=2,
    ),
    DataAssetSpec(
        "work-item-sources",
        AssetOwnership.MACHINE_LOCAL,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.PRIVATE_PATHS,
        BackupPolicy.CORE_CONFIGURATION,
        relative_path=PurePosixPath("data/local_work_item_sources.json"),
        schema_version=1,
    ),
    DataAssetSpec(
        "work-item-metadata",
        AssetOwnership.PERSONAL,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.CORE_CONFIGURATION,
        relative_path=PurePosixPath("data/local_work_item_metadata.json"),
        schema_version=1,
    ),
    DataAssetSpec(
        "work-item-settings",
        AssetOwnership.MACHINE_LOCAL,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.PRIVATE_PATHS,
        BackupPolicy.CORE_CONFIGURATION,
        relative_path=PurePosixPath("data/local_work_item_settings.json"),
        schema_version=1,
    ),
    DataAssetSpec(
        "inbox",
        AssetOwnership.CAPTURED_CONTENT,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CAPTURED_CONTENT,
        BackupPolicy.COMPLETE_CONFIGURATION_ADDITION,
        relative_path=PurePosixPath("data/inbox.json"),
        schema_version=1,
    ),
    DataAssetSpec(
        "managed-text-action-source",
        AssetOwnership.CAPTURED_CONTENT,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CAPTURED_CONTENT,
        BackupPolicy.OPTIONAL_MANAGED_CONTENT,
        relative_path=PurePosixPath("data/local_text_action_source.txt"),
    ),
    DataAssetSpec(
        "diagnostic-logs",
        AssetOwnership.DERIVED_RUNTIME,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.DIAGNOSTICS,
        BackupPolicy.EXCLUDED,
        relative_pattern="data/context-palette.log*",
    ),
    DataAssetSpec(
        "restore-journal",
        AssetOwnership.DERIVED_RUNTIME,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.PRIVATE_RUNTIME_DATA,
        BackupPolicy.EXCLUDED,
        relative_path=PurePosixPath("data/restore-journal.json"),
    ),
    DataAssetSpec(
        "recovery-backups",
        AssetOwnership.DERIVED_RUNTIME,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.PRIVATE_RUNTIME_DATA,
        BackupPolicy.EXCLUDED,
        relative_pattern="data/*.bak",
    ),
    DataAssetSpec(
        "temporary-data-files",
        AssetOwnership.DERIVED_RUNTIME,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.PRIVATE_RUNTIME_DATA,
        BackupPolicy.EXCLUDED,
        relative_pattern="data/*.tmp",
    ),
    DataAssetSpec(
        "python-environment",
        AssetOwnership.DERIVED_RUNTIME,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.PRIVATE_RUNTIME_DATA,
        BackupPolicy.EXCLUDED,
        relative_path=PurePosixPath(".venv"),
    ),
    DataAssetSpec(
        "preserved-python-environments",
        AssetOwnership.DERIVED_RUNTIME,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.PRIVATE_RUNTIME_DATA,
        BackupPolicy.EXCLUDED,
        relative_pattern=".venv-*",
    ),
)


def asset_spec_by_id(asset_id: str) -> DataAssetSpec:
    """Return one stable catalog declaration or reject an unknown ID."""

    for spec in DATA_ASSET_CATALOG:
        if spec.asset_id == asset_id:
            return spec
    raise KeyError(f"Unknown data asset ID: {asset_id}")


def asset_spec_for_path(
    relative_path: str | Path | PurePosixPath,
) -> DataAssetSpec | None:
    """Return the catalog declaration for one application-relative path."""

    return next(
        (spec for spec in DATA_ASSET_CATALOG if spec.matches(relative_path)),
        None,
    )


def is_catalogued_backup_payload(
    relative_path: str | Path | PurePosixPath,
) -> bool:
    """Report eligibility from explicit catalog policy, never filename inference."""

    spec = asset_spec_for_path(relative_path)
    return spec is not None and spec.backup_policy is not BackupPolicy.EXCLUDED
