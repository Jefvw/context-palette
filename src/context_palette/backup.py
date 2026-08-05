from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile

from .configuration_mutation import configuration_mutation_gate
from .configuration_snapshot import (
    SnapshotValidationIssue,
    load_configuration_snapshot,
)
from .data_catalog import (
    DATA_ASSET_CATALOG,
    AppDataPaths,
    BackupPolicy,
    DataAssetSpec,
    asset_spec_by_id,
    asset_spec_for_path,
)


BACKUP_FORMAT = "context-palette-backup"
BACKUP_FORMAT_VERSION = 1
BACKUP_DATA_MODEL_VERSION = 1
BACKUP_SCOPE = "complete-configuration"
MAX_BACKUP_ENTRIES = 256
MAX_BACKUP_ENTRY_BYTES = 16 * 1024 * 1024
MAX_BACKUP_TOTAL_BYTES = 64 * 1024 * 1024
DEFAULT_CONSISTENCY_ATTEMPTS = 3

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_UTC_TIMESTAMP_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z"
)
_COPY_CHUNK_BYTES = 1024 * 1024
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class BackupError(RuntimeError):
    """Base class for privacy-safe backup failures."""


class BackupDestinationError(BackupError):
    """The selected archive destination is unsafe or unavailable."""


class BackupSourceError(BackupError):
    """A catalogued source cannot be read safely."""


class BackupSourceSafetyError(BackupSourceError):
    """A catalogued source uses an unsafe link or root escape."""


class BackupSourceChangedError(BackupSourceError):
    """Configuration did not remain stable during bounded staging attempts."""


class BackupLimitError(BackupError):
    """The selected catalogued payload exceeds a declared backup limit."""


class BackupStagingError(BackupError):
    """The private temporary snapshot could not be created safely."""


class BackupPublicationError(BackupError):
    """A complete temporary archive could not be published atomically."""


class BackupConfigurationError(BackupError):
    """The staged configuration contains hard validation errors."""

    def __init__(self, issues: Iterable[SnapshotValidationIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(
            "The staged configuration is invalid; no backup archive was published."
        )


class BackupExclusion(str, Enum):
    INBOX = "captured Inbox content"
    MANAGED_CONTENT = "optional managed text content"
    RUNTIME_ARTIFACTS = "diagnostic and runtime artifacts"
    UNKNOWN_FILES = "uncatalogued application-directory files"
    EXTERNAL_RESOURCES = "external Action and Work Item resources"
    CREDENTIAL_SECRETS = "Windows credential secrets"


@dataclass(frozen=True, slots=True)
class BackupLimits:
    max_entries: int = MAX_BACKUP_ENTRIES
    max_entry_bytes: int = MAX_BACKUP_ENTRY_BYTES
    max_total_bytes: int = MAX_BACKUP_TOTAL_BYTES

    def __post_init__(self) -> None:
        for label, value in (
            ("entry count", self.max_entries),
            ("individual entry size", self.max_entry_bytes),
            ("total payload size", self.max_total_bytes),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"Backup {label} limit must be a positive integer.")


DEFAULT_BACKUP_LIMITS = BackupLimits()


@dataclass(frozen=True, slots=True)
class BackupManifestEntry:
    asset_id: str
    archive_path: PurePosixPath
    schema_version: int | None
    size: int
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.archive_path, PurePosixPath):
            raise ValueError("Manifest archive paths must be PurePosixPath values.")
        if (
            not self.archive_path.parts
            or self.archive_path.is_absolute()
            or self.archive_path.parts[0] != "payload"
            or ".." in self.archive_path.parts
            or str(self.archive_path) != self.archive_path.as_posix()
        ):
            raise ValueError("Manifest entries must use normalized payload/ paths.")
        try:
            spec = asset_spec_by_id(self.asset_id)
        except KeyError as exc:
            raise ValueError("Manifest asset ID is not catalogued.") from exc
        if spec.backup_policy is BackupPolicy.EXCLUDED:
            raise ValueError("Excluded catalog assets cannot be manifest entries.")
        relative_path = PurePosixPath(*self.archive_path.parts[1:])
        if asset_spec_for_path(relative_path) != spec:
            raise ValueError("Manifest asset ID and archive path do not match.")
        if (
            self.schema_version != spec.schema_version
            or isinstance(self.schema_version, bool)
            or (
                self.schema_version is not None
                and not isinstance(self.schema_version, int)
            )
        ):
            raise ValueError("Manifest schema version does not match the catalog.")
        if (
            not isinstance(self.size, int)
            or isinstance(self.size, bool)
            or self.size < 0
        ):
            raise ValueError("Manifest entry size must be a non-negative integer.")
        if not isinstance(self.sha256, str) or not _SHA256_PATTERN.fullmatch(
            self.sha256
        ):
            raise ValueError("Manifest SHA-256 must be 64 lowercase hexadecimal characters.")

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "asset_id": self.asset_id,
            "path": self.archive_path.as_posix(),
            "size": self.size,
            "sha256": self.sha256,
        }
        if self.schema_version is not None:
            data["schema_version"] = self.schema_version
        return data


@dataclass(frozen=True, slots=True)
class BackupManifest:
    created_at: str
    entries: tuple[BackupManifestEntry, ...]
    format: str = BACKUP_FORMAT
    format_version: int = BACKUP_FORMAT_VERSION
    data_model_version: int = BACKUP_DATA_MODEL_VERSION
    scope: str = BACKUP_SCOPE

    def __post_init__(self) -> None:
        if self.format != BACKUP_FORMAT:
            raise ValueError("Unsupported backup format identifier.")
        if (
            not isinstance(self.format_version, int)
            or isinstance(self.format_version, bool)
            or self.format_version != BACKUP_FORMAT_VERSION
        ):
            raise ValueError("Unsupported backup format version.")
        if (
            not isinstance(self.data_model_version, int)
            or isinstance(self.data_model_version, bool)
            or self.data_model_version != BACKUP_DATA_MODEL_VERSION
        ):
            raise ValueError("Unsupported backup data-model version.")
        if self.scope != BACKUP_SCOPE:
            raise ValueError("Unsupported backup scope.")
        if not isinstance(self.entries, tuple):
            raise ValueError("Manifest entries must be an immutable tuple.")
        _validate_utc_timestamp(self.created_at)
        paths = tuple(entry.archive_path for entry in self.entries)
        if paths != tuple(sorted(paths, key=lambda value: value.as_posix())):
            raise ValueError("Manifest entries must be ordered by archive path.")
        if len(paths) != len(set(paths)):
            raise ValueError("Manifest archive paths must be unique.")

    def to_dict(self) -> dict[str, object]:
        return {
            "format": self.format,
            "format_version": self.format_version,
            "data_model_version": self.data_model_version,
            "created_at": self.created_at,
            "scope": self.scope,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    def to_json_bytes(self) -> bytes:
        return (
            json.dumps(
                self.to_dict(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")

    @classmethod
    def from_json_bytes(cls, payload: bytes) -> BackupManifest:
        """Strictly parse the existing version-1 manifest representation."""

        if not isinstance(payload, bytes):
            raise ValueError("Manifest input must be bytes.")
        try:
            decoded = payload.decode("utf-8")
            raw = json.loads(
                decoded,
                object_pairs_hook=_reject_duplicate_json_keys,
                parse_constant=lambda _value: (_ for _ in ()).throw(
                    ValueError("Manifest JSON constants are not supported.")
                ),
            )
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Manifest must contain valid UTF-8 JSON.") from exc
        if not isinstance(raw, dict):
            raise ValueError("Manifest must contain a JSON object.")
        required_keys = {
            "format",
            "format_version",
            "data_model_version",
            "created_at",
            "scope",
            "entries",
        }
        if set(raw) != required_keys:
            raise ValueError("Manifest keys do not match format version 1.")
        entries_raw = raw["entries"]
        if not isinstance(entries_raw, list):
            raise ValueError("Manifest entries must be a JSON array.")
        entries = tuple(_parse_manifest_entry(value) for value in entries_raw)
        return cls(
            format=_require_string(raw["format"], "format"),
            format_version=_require_integer(raw["format_version"], "format version"),
            data_model_version=_require_integer(
                raw["data_model_version"], "data-model version"
            ),
            created_at=_require_string(raw["created_at"], "creation time"),
            scope=_require_string(raw["scope"], "scope"),
            entries=entries,
        )


@dataclass(frozen=True, slots=True)
class BackupOptions:
    include_inbox: bool = True
    include_managed_content: bool = False
    overwrite: bool = False
    limits: BackupLimits = DEFAULT_BACKUP_LIMITS
    max_consistency_attempts: int = DEFAULT_CONSISTENCY_ATTEMPTS

    def __post_init__(self) -> None:
        for label, value in (
            ("include_inbox", self.include_inbox),
            ("include_managed_content", self.include_managed_content),
            ("overwrite", self.overwrite),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"Backup option {label} must be boolean.")
        if not isinstance(self.limits, BackupLimits):
            raise ValueError("Backup options require a BackupLimits value.")
        if (
            not isinstance(self.max_consistency_attempts, int)
            or isinstance(self.max_consistency_attempts, bool)
            or self.max_consistency_attempts < 1
        ):
            raise ValueError("Consistency attempts must be a positive integer.")


@dataclass(frozen=True, slots=True)
class BackupTestHooks:
    """Deterministic fault and mutation hooks used by focused tests."""

    after_initial_inventory: Callable[[int], None] | None = None
    after_staged_file: Callable[[str, PurePosixPath, int], None] | None = None
    after_staging: Callable[[int], None] | None = None
    after_archive_entry: Callable[[PurePosixPath], None] | None = None
    before_publication: Callable[[], None] | None = None
    staging_parent: Path | None = None


@dataclass(frozen=True, slots=True)
class IncludedBackupFile:
    asset_id: str
    archive_path: PurePosixPath
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class BackupResult:
    destination: Path
    manifest: BackupManifest
    included_files: tuple[IncludedBackupFile, ...]
    excluded_categories: tuple[BackupExclusion, ...]
    snapshot_warnings: tuple[SnapshotValidationIssue, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "included_files", tuple(self.included_files))
        object.__setattr__(
            self,
            "excluded_categories",
            tuple(self.excluded_categories),
        )
        object.__setattr__(
            self,
            "snapshot_warnings",
            tuple(self.snapshot_warnings),
        )

    @property
    def included_asset_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.asset_id for item in self.included_files))


@dataclass(frozen=True, slots=True)
class _FileFingerprint:
    size: int
    modified_ns: int
    changed_ns: int
    device: int
    inode: int
    sha256: str


@dataclass(frozen=True, slots=True)
class _InventoryItem:
    asset_id: str
    relative_path: PurePosixPath
    source_path: Path
    fingerprint: _FileFingerprint | None

    @property
    def archive_path(self) -> PurePosixPath:
        return PurePosixPath("payload") / self.relative_path


class _SourceChangedDuringRead(Exception):
    pass


def create_configuration_backup(
    paths: AppDataPaths,
    destination: Path,
    *,
    options: BackupOptions = BackupOptions(),
    created_at: datetime | None = None,
    test_hooks: BackupTestHooks | None = None,
) -> BackupResult:
    """Create one validated, deterministic complete-configuration archive."""

    if not isinstance(paths, AppDataPaths):
        raise TypeError("paths must be an AppDataPaths value")
    if not isinstance(options, BackupOptions):
        raise TypeError("options must be a BackupOptions value")
    if paths.restore_journal_file.exists() or _is_reparse_point(
        paths.restore_journal_file
    ):
        raise BackupSourceSafetyError(
            "An unfinished restore must be recovered before creating a backup."
        )
    hooks = test_hooks or BackupTestHooks()
    destination_path = _validate_destination(
        paths,
        Path(destination),
        overwrite=options.overwrite,
    )
    timestamp = _format_created_at(created_at)
    specs = _selected_specs(options)

    with configuration_mutation_gate():
        if paths.restore_journal_file.exists() or _is_reparse_point(
            paths.restore_journal_file
        ):
            raise BackupSourceSafetyError(
                "An unfinished restore must be recovered before creating a backup."
            )
        for attempt in range(1, options.max_consistency_attempts + 1):
            try:
                inventory = _build_inventory(paths, specs, options.limits)
                _assert_destination_not_source(destination_path, inventory)
                if hooks.after_initial_inventory is not None:
                    hooks.after_initial_inventory(attempt)
                with tempfile.TemporaryDirectory(
                    prefix="context-palette-backup-stage-",
                    dir=hooks.staging_parent,
                ) as directory:
                    stage_root = Path(directory)
                    _stage_inventory(
                        paths,
                        inventory,
                        stage_root,
                        attempt,
                        hooks,
                    )
                    if hooks.after_staging is not None:
                        hooks.after_staging(attempt)
                    repeated = _build_inventory(paths, specs, options.limits)
                    if inventory != repeated:
                        raise _SourceChangedDuringRead

                    snapshot_report = load_configuration_snapshot(
                        AppDataPaths.from_root(stage_root)
                    )
                    if not snapshot_report.ok:
                        raise BackupConfigurationError(snapshot_report.errors)

                    manifest = _build_manifest(timestamp, inventory)
                    _write_archive_atomically(
                        stage_root,
                        destination_path,
                        manifest,
                        overwrite=options.overwrite,
                        hooks=hooks,
                    )
                    included_files = tuple(
                        IncludedBackupFile(
                            entry.asset_id,
                            entry.archive_path,
                            entry.size,
                            entry.sha256,
                        )
                        for entry in manifest.entries
                    )
                    return BackupResult(
                        destination_path,
                        manifest,
                        included_files,
                        _excluded_categories(options),
                        snapshot_report.warnings,
                    )
            except _SourceChangedDuringRead:
                continue
            except BackupError:
                raise
            except OSError as exc:
                raise BackupSourceError(
                    "A catalogued configuration source could not be read safely."
                ) from exc

    raise BackupSourceChangedError(
        "Configuration changed during every bounded staging attempt; "
        "no backup archive was published."
    )


def _selected_specs(options: BackupOptions) -> tuple[DataAssetSpec, ...]:
    selected: list[DataAssetSpec] = []
    for spec in DATA_ASSET_CATALOG:
        if spec.backup_policy is BackupPolicy.EXCLUDED:
            continue
        if spec.asset_id == "inbox" and not options.include_inbox:
            continue
        if (
            spec.backup_policy is BackupPolicy.OPTIONAL_MANAGED_CONTENT
            and not options.include_managed_content
        ):
            continue
        selected.append(spec)
    return tuple(selected)


def _excluded_categories(options: BackupOptions) -> tuple[BackupExclusion, ...]:
    excluded: list[BackupExclusion] = []
    if not options.include_inbox:
        excluded.append(BackupExclusion.INBOX)
    if not options.include_managed_content:
        excluded.append(BackupExclusion.MANAGED_CONTENT)
    excluded.extend(
        (
            BackupExclusion.RUNTIME_ARTIFACTS,
            BackupExclusion.UNKNOWN_FILES,
            BackupExclusion.EXTERNAL_RESOURCES,
            BackupExclusion.CREDENTIAL_SECRETS,
        )
    )
    return tuple(excluded)


def _build_inventory(
    paths: AppDataPaths,
    specs: tuple[DataAssetSpec, ...],
    limits: BackupLimits,
) -> tuple[_InventoryItem, ...]:
    root = paths.application_root.absolute()
    _validate_application_root(root)
    items: list[_InventoryItem] = []
    existing_count = 0
    total_bytes = 0

    def fingerprint_source(source_path: Path) -> _FileFingerprint:
        nonlocal existing_count, total_bytes
        if existing_count >= limits.max_entries:
            raise BackupLimitError(
                f"Catalogued payload exceeds the {limits.max_entries} entry limit."
            )
        result = _fingerprint_file(
            source_path,
            limits.max_entry_bytes,
            limits.max_total_bytes - total_bytes,
        )
        existing_count += 1
        total_bytes += result.size
        return result

    for spec in specs:
        if spec.relative_path is not None:
            source_path = spec.path_for(paths).absolute()
            _assert_safe_source_path(root, source_path)
            source_fingerprint = (
                fingerprint_source(source_path)
                if _path_exists_or_link(source_path)
                else None
            )
            items.append(
                _InventoryItem(
                    spec.asset_id,
                    spec.relative_path,
                    source_path,
                    source_fingerprint,
                )
            )
            continue

        pattern = PurePosixPath(spec.relative_pattern or "")
        if pattern.parts[0] == "data":
            directory = paths.data_directory.joinpath(
                *pattern.parent.parts[1:]
            ).absolute()
        else:
            directory = root.joinpath(*pattern.parent.parts)
        _assert_safe_source_path(root, directory)
        if not _path_exists_or_link(directory):
            continue
        if not directory.is_dir():
            raise BackupSourceSafetyError(
                "A catalogued pattern location is not a safe directory."
            )
        matching_paths: list[tuple[PurePosixPath, Path]] = []
        for source_path in directory.glob(pattern.name):
            source_path = source_path.absolute()
            relative_path = PurePosixPath(
                source_path.relative_to(root).as_posix()
            )
            if not spec.matches(relative_path):
                continue
            _assert_safe_source_path(root, source_path)
            if existing_count + len(matching_paths) >= limits.max_entries:
                raise BackupLimitError(
                    "Catalogued payload exceeds the "
                    f"{limits.max_entries} entry limit."
                )
            matching_paths.append((relative_path, source_path))
        for relative_path, source_path in sorted(
            matching_paths,
            key=lambda value: value[0].as_posix(),
        ):
            items.append(
                _InventoryItem(
                    spec.asset_id,
                    relative_path,
                    source_path,
                    fingerprint_source(source_path),
                )
            )

    items.sort(key=lambda item: item.relative_path.as_posix())
    _enforce_inventory_limits(items, limits)
    return tuple(items)


def _enforce_inventory_limits(
    inventory: Iterable[_InventoryItem],
    limits: BackupLimits,
) -> None:
    existing = tuple(item for item in inventory if item.fingerprint is not None)
    if len(existing) > limits.max_entries:
        raise BackupLimitError(
            f"Catalogued payload exceeds the {limits.max_entries} entry limit."
        )
    total = sum(item.fingerprint.size for item in existing if item.fingerprint)
    if total > limits.max_total_bytes:
        raise BackupLimitError(
            "Catalogued payload exceeds the configured total byte limit."
        )


def _assert_destination_not_source(
    destination: Path,
    inventory: tuple[_InventoryItem, ...],
) -> None:
    if not destination.exists():
        return
    for item in inventory:
        if item.fingerprint is None:
            continue
        try:
            if destination.samefile(item.source_path):
                raise BackupDestinationError(
                    "The backup destination overlaps a catalogued application asset."
                )
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise BackupDestinationError(
                "The backup destination could not be compared safely."
            ) from exc


def _validate_application_root(root: Path) -> None:
    if not root.is_dir():
        raise BackupSourceError("The application root is unavailable.")
    if _is_reparse_point(root):
        raise BackupSourceSafetyError(
            "The application root cannot be a link or reparse point."
        )


def _assert_safe_source_path(root: Path, path: Path) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise BackupSourceSafetyError(
            "A catalogued source escapes the application root."
        ) from exc

    current = root
    for part in relative.parts:
        current = current / part
        if _path_exists_or_link(current) and _is_reparse_point(current):
            raise BackupSourceSafetyError(
                "A catalogued source uses a link or reparse point."
            )

    try:
        resolved_root = root.resolve(strict=True)
        resolved_path = path.resolve(strict=path.exists())
        resolved_path.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise BackupSourceSafetyError(
            "A catalogued source does not resolve below the application root."
        ) from exc


def _path_exists_or_link(path: Path) -> bool:
    return path.exists() or path.is_symlink() or _is_junction(path)


def _is_junction(path: Path) -> bool:
    checker = getattr(path, "is_junction", None)
    if checker is None:
        return False
    try:
        return bool(checker())
    except OSError:
        return False


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink() or _is_junction(path):
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _fingerprint_file(
    path: Path,
    max_entry_bytes: int,
    max_total_remaining: int,
) -> _FileFingerprint:
    try:
        before = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise BackupSourceSafetyError(
                "A catalogued payload entry is not a regular file."
            )
        if before.st_size > max_entry_bytes:
            raise BackupLimitError(
                "A catalogued payload entry exceeds the configured byte limit."
            )
        if before.st_size > max_total_remaining:
            raise BackupLimitError(
                "Catalogued payload exceeds the configured total byte limit."
            )
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if _stable_stat_signature(opened) != _stable_stat_signature(before):
                raise _SourceChangedDuringRead
            while chunk := stream.read(_COPY_CHUNK_BYTES):
                digest.update(chunk)
            closed = os.fstat(stream.fileno())
        after = path.stat(follow_symlinks=False)
    except FileNotFoundError as exc:
        raise _SourceChangedDuringRead from exc
    except (BackupError, _SourceChangedDuringRead):
        raise
    except OSError as exc:
        raise BackupSourceError(
            "A catalogued payload entry could not be read safely."
        ) from exc
    if not (
        _stable_stat_signature(before)
        == _stable_stat_signature(opened)
        == _stable_stat_signature(closed)
        == _stable_stat_signature(after)
        and before.st_ctime_ns == after.st_ctime_ns
    ):
        raise _SourceChangedDuringRead
    return _FileFingerprint(
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_dev,
        before.st_ino,
        digest.hexdigest(),
    )


def _stable_stat_signature(value: os.stat_result) -> tuple[int, int, int, int]:
    return (
        value.st_size,
        value.st_mtime_ns,
        value.st_dev,
        value.st_ino,
    )


def _stage_inventory(
    paths: AppDataPaths,
    inventory: tuple[_InventoryItem, ...],
    stage_root: Path,
    attempt: int,
    hooks: BackupTestHooks,
) -> None:
    root = paths.application_root.absolute()
    existing_index = 0
    for item in inventory:
        if item.fingerprint is None:
            continue
        _assert_safe_source_path(root, item.source_path)
        destination = stage_root.joinpath(*item.relative_path.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            digest = hashlib.sha256()
            with item.source_path.open("rb") as source:
                opened = os.fstat(source.fileno())
                if not _open_stat_matches_fingerprint(opened, item.fingerprint):
                    raise _SourceChangedDuringRead
                with destination.open("xb") as staged:
                    while chunk := source.read(_COPY_CHUNK_BYTES):
                        digest.update(chunk)
                        staged.write(chunk)
                    staged.flush()
                    os.fsync(staged.fileno())
                closed = os.fstat(source.fileno())
            after = item.source_path.stat(follow_symlinks=False)
        except FileNotFoundError as exc:
            raise _SourceChangedDuringRead from exc
        except (BackupError, _SourceChangedDuringRead):
            raise
        except OSError as exc:
            raise BackupStagingError(
                "The private staged snapshot could not be written safely."
            ) from exc
        if (
            not _open_stat_matches_fingerprint(closed, item.fingerprint)
            or digest.hexdigest() != item.fingerprint.sha256
            or _fingerprint_from_stat(after, digest.hexdigest()) != item.fingerprint
        ):
            raise _SourceChangedDuringRead
        existing_index += 1
        if hooks.after_staged_file is not None:
            hooks.after_staged_file(
                item.asset_id,
                item.relative_path,
                existing_index,
            )


def _fingerprint_from_stat(
    value: os.stat_result,
    digest: str,
) -> _FileFingerprint:
    return _FileFingerprint(
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_dev,
        value.st_ino,
        digest,
    )


def _open_stat_matches_fingerprint(
    value: os.stat_result,
    fingerprint: _FileFingerprint,
) -> bool:
    return _stable_stat_signature(value) == (
        fingerprint.size,
        fingerprint.modified_ns,
        fingerprint.device,
        fingerprint.inode,
    )


def _build_manifest(
    created_at: str,
    inventory: tuple[_InventoryItem, ...],
) -> BackupManifest:
    entries = tuple(
        BackupManifestEntry(
            item.asset_id,
            item.archive_path,
            asset_spec_by_id(item.asset_id).schema_version,
            item.fingerprint.size,
            item.fingerprint.sha256,
        )
        for item in inventory
        if item.fingerprint is not None
    )
    return BackupManifest(created_at=created_at, entries=entries)


def _write_archive_atomically(
    stage_root: Path,
    destination: Path,
    manifest: BackupManifest,
    *,
    overwrite: bool,
    hooks: BackupTestHooks,
) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            with zipfile.ZipFile(
                temporary,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as archive:
                for entry in manifest.entries:
                    staged_path = stage_root.joinpath(
                        *entry.archive_path.parts[1:]
                    )
                    payload = staged_path.read_bytes()
                    if (
                        len(payload) != entry.size
                        or hashlib.sha256(payload).hexdigest() != entry.sha256
                    ):
                        raise BackupStagingError(
                            "The staged payload changed before archive creation."
                        )
                    archive.writestr(
                        _zip_info(entry.archive_path.as_posix()),
                        payload,
                        compress_type=zipfile.ZIP_DEFLATED,
                        compresslevel=9,
                    )
                    if hooks.after_archive_entry is not None:
                        hooks.after_archive_entry(entry.archive_path)
                archive.writestr(
                    _zip_info("manifest.json"),
                    manifest.to_json_bytes(),
                    compress_type=zipfile.ZIP_DEFLATED,
                    compresslevel=9,
                )
            temporary.flush()
            os.fsync(temporary.fileno())

        if hooks.before_publication is not None:
            hooks.before_publication()
        if destination.exists() and not overwrite:
            raise BackupDestinationError(
                "The backup destination already exists; enable overwrite explicitly."
            )
        try:
            if overwrite:
                os.replace(temporary_path, destination)
            elif os.name == "nt":
                # Unlike POSIX rename, Windows rename is atomic and refuses to
                # replace a destination created after the preceding check.
                os.rename(temporary_path, destination)
            else:
                # A same-directory hard link provides atomic no-clobber
                # publication on POSIX, where rename would replace its target.
                os.link(temporary_path, destination)
                os.unlink(temporary_path)
        except FileExistsError as exc:
            raise BackupDestinationError(
                "The backup destination already exists; enable overwrite explicitly."
            ) from exc
        except OSError as exc:
            raise BackupPublicationError(
                "The complete temporary archive could not be published atomically."
            ) from exc
        temporary_path = None
    except BackupError:
        raise
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        raise BackupPublicationError(
            "The temporary backup archive could not be written safely."
        ) from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 0
    info.external_attr = 0
    return info


def _validate_destination(
    paths: AppDataPaths,
    destination: Path,
    *,
    overwrite: bool,
) -> Path:
    candidate = destination.expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.absolute()
    parent = candidate.parent
    if not parent.is_dir():
        raise BackupDestinationError("The backup destination folder is unavailable.")
    if _is_reparse_point(candidate):
        raise BackupDestinationError(
            "The backup destination cannot be a link or reparse point."
        )
    if candidate.exists() and not candidate.is_file():
        raise BackupDestinationError("The backup destination is not a regular file.")
    if candidate.exists() and not overwrite:
        raise BackupDestinationError(
            "The backup destination already exists; enable overwrite explicitly."
        )

    root = paths.application_root.absolute()
    try:
        resolved_root = root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=False)
    except OSError as exc:
        raise BackupDestinationError(
            "The backup destination could not be resolved safely."
        ) from exc
    if _is_relative_to(candidate, root) or _is_relative_to(
        resolved_candidate,
        resolved_root,
    ):
        raise BackupDestinationError(
            "Backup archives and temporary output must remain outside the application root."
        )
    return candidate


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _format_created_at(value: datetime | None) -> str:
    if value is None:
        value = datetime.now(timezone.utc).replace(microsecond=0)
    if not isinstance(value, datetime):
        raise ValueError("Backup creation time must be a datetime value.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Backup creation time must be timezone-aware UTC.")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError("Backup creation time must use UTC.")
    timespec = "microseconds" if value.microsecond else "seconds"
    return value.isoformat(timespec=timespec).replace("+00:00", "Z")


def _validate_utc_timestamp(value: str) -> None:
    if not isinstance(value, str) or not _UTC_TIMESTAMP_PATTERN.fullmatch(value):
        raise ValueError("Manifest creation time must be canonical UTC text.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("Manifest creation time is invalid.") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("Manifest creation time must use UTC.")


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Manifest JSON contains duplicate object keys.")
        result[key] = value
    return result


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Manifest {label} must be text.")
    return value


def _require_integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Manifest {label} must be an integer.")
    return value


def _parse_manifest_entry(value: object) -> BackupManifestEntry:
    if not isinstance(value, dict):
        raise ValueError("Manifest entries must be JSON objects.")
    base_keys = {"asset_id", "path", "size", "sha256"}
    if not base_keys.issubset(value) or not set(value).issubset(
        base_keys | {"schema_version"}
    ):
        raise ValueError("Manifest entry keys do not match format version 1.")
    asset_id = _require_string(value["asset_id"], "asset ID")
    try:
        spec = asset_spec_by_id(asset_id)
    except KeyError as exc:
        raise ValueError("Manifest entry uses an unknown catalog asset ID.") from exc
    has_schema_version = "schema_version" in value
    if has_schema_version != (spec.schema_version is not None):
        raise ValueError("Manifest entry schema-version presence is invalid.")
    schema_version = (
        _require_integer(value["schema_version"], "schema version")
        if has_schema_version
        else None
    )
    return BackupManifestEntry(
        asset_id=asset_id,
        archive_path=PurePosixPath(_require_string(value["path"], "entry path")),
        schema_version=schema_version,
        size=_require_integer(value["size"], "entry size"),
        sha256=_require_string(value["sha256"], "entry SHA-256"),
    )
