from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import binascii
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import struct
import tempfile
import unicodedata
import uuid
import zipfile

from .backup import (
    BACKUP_DATA_MODEL_VERSION,
    BACKUP_FORMAT,
    BACKUP_FORMAT_VERSION,
    BACKUP_SCOPE,
    DEFAULT_BACKUP_LIMITS,
    BackupLimits,
    BackupManifest,
    BackupManifestEntry,
    BackupOptions,
    BackupTestHooks,
    _build_inventory,
    _is_relative_to,
    _is_reparse_point,
    _selected_specs,
    _stage_inventory,
)
from .configuration_mutation import configuration_mutation_gate
from .configuration_snapshot import (
    SnapshotValidationIssue,
    ValidationCategory,
    load_configuration_snapshot,
)
from .data_catalog import (
    DATA_ASSET_CATALOG,
    AppDataPaths,
    AssetOwnership,
    AssetRequirement,
    AssetSensitivity,
    BackupPolicy,
    asset_spec_by_id,
    asset_spec_for_path,
)
from .persistence import atomic_replace_bytes


RESTORE_JOURNAL_FORMAT = "context-palette-restore-journal"
RESTORE_JOURNAL_VERSION = 1
RECOVERY_ARCHIVE_FORMAT = "context-palette-recovery"
RECOVERY_ARCHIVE_VERSION = 1
MAX_RESTORE_MANIFEST_BYTES = 1024 * 1024
MAX_RESTORE_ARCHIVE_BYTES = 80 * 1024 * 1024
MAX_RESTORE_JOURNAL_BYTES = 1024 * 1024

_CHUNK_BYTES = 1024 * 1024
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_TRANSACTION_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_LOCAL_HEADER = struct.Struct("<4s5H3L2H")
_LOCAL_HEADER_SIGNATURE = b"PK\x03\x04"
_SUPPORTED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)
_WINDOWS_UNSAFE_CHARACTERS = frozenset('<>:"|?*')


class RestoreError(RuntimeError):
    """Base class for privacy-safe restore failures."""


class RestoreArchiveError(RestoreError):
    """An untrusted archive is malformed or unsafe."""


class RestoreCompatibilityError(RestoreArchiveError):
    """An archive uses an unsupported format or logical schema."""


class RestoreLimitError(RestoreArchiveError):
    """An archive exceeds a configured inspection limit."""


class RestoreConfigurationError(RestoreError):
    """The conservative staged overlay contains hard validation errors."""

    def __init__(self, issues: Iterable[SnapshotValidationIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(
            "The staged restore configuration is invalid; live data was unchanged."
        )


class RestorePlanStaleError(RestoreError):
    """The archive or relevant live state changed after inspection."""


class RestoreConfirmationError(RestoreError):
    """The explicit confirmation does not authorize this restore plan."""


class RestoreRecoveryError(RestoreError):
    """Recovery state is missing, invalid, or could not be applied safely."""


class RestoreRecoveryRequiredError(RestoreRecoveryError):
    """An unfinished journal must be recovered before another commit."""


class RestoreCommitError(RestoreError):
    """Restore commit failed and either did or did not complete rollback."""

    def __init__(self, *, rollback_completed: bool) -> None:
        self.rollback_completed = rollback_completed
        message = (
            "Restore failed; the prior catalogued state was restored."
            if rollback_completed
            else "Restore failed and automatic rollback remains incomplete."
        )
        super().__init__(message)


class RestoreSensitiveCategory(str, Enum):
    PRIVATE_PATHS = "machine-local and external path references"
    CAPTURED_INBOX = "captured Inbox content"
    MANAGED_CONTENT = "optional managed text content"


@dataclass(frozen=True, slots=True)
class RestoreLimits:
    payload: BackupLimits = DEFAULT_BACKUP_LIMITS
    max_manifest_bytes: int = MAX_RESTORE_MANIFEST_BYTES
    max_archive_bytes: int = MAX_RESTORE_ARCHIVE_BYTES

    def __post_init__(self) -> None:
        if not isinstance(self.payload, BackupLimits):
            raise ValueError("Restore payload limits must be BackupLimits.")
        for label, value in (
            ("manifest", self.max_manifest_bytes),
            ("archive", self.max_archive_bytes),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"Restore {label} limit must be a positive integer.")


DEFAULT_RESTORE_LIMITS = RestoreLimits()


@dataclass(frozen=True, slots=True)
class FileIdentity:
    size: int
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.size, int) or isinstance(self.size, bool) or self.size < 0:
            raise ValueError("File identity size must be a non-negative integer.")
        if not isinstance(self.sha256, str) or not _SHA256_PATTERN.fullmatch(
            self.sha256
        ):
            raise ValueError("File identity SHA-256 is invalid.")


@dataclass(frozen=True, slots=True)
class RestoreFile:
    asset_id: str
    relative_path: PurePosixPath
    restored: FileIdentity

    def __post_init__(self) -> None:
        spec = asset_spec_by_id(self.asset_id)
        _validate_catalog_relative_path(self.relative_path, spec.asset_id)
        if asset_spec_for_path(self.relative_path) != spec:
            raise ValueError("Restore file does not match its catalog asset ID.")


@dataclass(frozen=True, slots=True)
class PreservedRestoreFile:
    asset_id: str
    relative_path: PurePosixPath

    def __post_init__(self) -> None:
        spec = asset_spec_by_id(self.asset_id)
        _validate_catalog_relative_path(self.relative_path, spec.asset_id)
        if asset_spec_for_path(self.relative_path) != spec:
            raise ValueError("Preserved file does not match its catalog asset ID.")


@dataclass(frozen=True, slots=True)
class RestoreCompatibility:
    archive_format: str
    archive_format_version: int
    data_model_version: int
    scope: str
    migration_required: bool
    legacy_forms_present: bool


@dataclass(frozen=True, slots=True)
class RestorePlan:
    archive: FileIdentity
    manifest_sha256: str
    live_state_sha256: str
    files_to_replace: tuple[RestoreFile, ...]
    files_to_create: tuple[RestoreFile, ...]
    preserved_live_files: tuple[PreservedRestoreFile, ...]
    built_in_files: tuple[RestoreFile, ...]
    sensitive_categories: tuple[RestoreSensitiveCategory, ...]
    snapshot_warnings: tuple[SnapshotValidationIssue, ...]
    compatibility: RestoreCompatibility
    explicit_confirmation_required: bool = True
    built_in_acknowledgement_required: bool = False

    def __post_init__(self) -> None:
        for name in (
            "files_to_replace",
            "files_to_create",
            "preserved_live_files",
            "built_in_files",
            "sensitive_categories",
            "snapshot_warnings",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if not _SHA256_PATTERN.fullmatch(self.manifest_sha256):
            raise ValueError("Manifest identity is invalid.")
        if not _SHA256_PATTERN.fullmatch(self.live_state_sha256):
            raise ValueError("Live-state identity is invalid.")

    @property
    def affected_files(self) -> tuple[RestoreFile, ...]:
        return self.files_to_replace + self.files_to_create


@dataclass(frozen=True, slots=True)
class RestoreConfirmation:
    archive_sha256: str
    live_state_sha256: str
    confirmed: bool
    built_in_acknowledged: bool = False

    @classmethod
    def for_plan(
        cls,
        plan: RestorePlan,
        *,
        built_in_acknowledged: bool = False,
    ) -> RestoreConfirmation:
        return cls(
            plan.archive.sha256,
            plan.live_state_sha256,
            True,
            built_in_acknowledged,
        )


@dataclass(frozen=True, slots=True)
class RestoreResult:
    recovery_archive: Path
    replaced_files: tuple[RestoreFile, ...]
    created_files: tuple[RestoreFile, ...]
    snapshot_warnings: tuple[SnapshotValidationIssue, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "recovery_archive", Path(self.recovery_archive))
        object.__setattr__(self, "replaced_files", tuple(self.replaced_files))
        object.__setattr__(self, "created_files", tuple(self.created_files))
        object.__setattr__(self, "snapshot_warnings", tuple(self.snapshot_warnings))


@dataclass(frozen=True, slots=True)
class StartupRecoveryResult:
    recovery_performed: bool


@dataclass(frozen=True, slots=True)
class RestoreTestHooks:
    after_recovery_archive: Callable[[], None] | None = None
    after_journal: Callable[[], None] | None = None
    after_replacement: Callable[[int, str], None] | None = None
    before_final_validation: Callable[[], None] | None = None
    staging_parent: Path | None = None


@dataclass(frozen=True, slots=True)
class _InspectedArchive:
    manifest: BackupManifest
    archive: FileIdentity
    manifest_sha256: str


@dataclass(frozen=True, slots=True)
class _JournalOperation:
    asset_id: str
    relative_path: PurePosixPath
    existed_before: bool
    previous: FileIdentity | None
    restored: FileIdentity

    def __post_init__(self) -> None:
        spec = asset_spec_by_id(self.asset_id)
        _validate_catalog_relative_path(self.relative_path, self.asset_id)
        if spec.backup_policy is BackupPolicy.EXCLUDED:
            raise ValueError("Excluded assets cannot be restore operations.")
        if asset_spec_for_path(self.relative_path) != spec:
            raise ValueError("Journal operation does not match its catalog asset.")
        if self.existed_before != (self.previous is not None):
            raise ValueError("Journal previous-state identity is inconsistent.")


@dataclass(frozen=True, slots=True)
class _RestoreJournal:
    transaction_id: str
    recovery_archive: Path
    recovery_archive_identity: FileIdentity
    source_archive: FileIdentity
    live_state_sha256: str
    operations: tuple[_JournalOperation, ...]
    state: str = "pending"
    format: str = RESTORE_JOURNAL_FORMAT
    version: int = RESTORE_JOURNAL_VERSION

    def __post_init__(self) -> None:
        if self.format != RESTORE_JOURNAL_FORMAT or self.version != 1:
            raise ValueError("Unsupported restore journal format.")
        if not _TRANSACTION_ID_PATTERN.fullmatch(self.transaction_id):
            raise ValueError("Restore transaction ID is invalid.")
        if not self.recovery_archive.is_absolute():
            raise ValueError("Recovery archive path must be absolute.")
        if self.state != "pending":
            raise ValueError("Unsupported restore journal state.")
        if not _SHA256_PATTERN.fullmatch(self.live_state_sha256):
            raise ValueError("Restore journal live-state identity is invalid.")
        object.__setattr__(self, "operations", tuple(self.operations))
        paths = tuple(operation.relative_path for operation in self.operations)
        if paths != tuple(sorted(paths, key=str)) or len(paths) != len(set(paths)):
            raise ValueError("Restore journal operations must be unique and ordered.")

    def to_json_bytes(self) -> bytes:
        def identity(value: FileIdentity | None) -> object:
            return None if value is None else {
                "size": value.size,
                "sha256": value.sha256,
            }

        return (
            json.dumps(
                {
                    "format": self.format,
                    "version": self.version,
                    "transaction_id": self.transaction_id,
                    "state": self.state,
                    "recovery_archive": str(self.recovery_archive),
                    "recovery_archive_identity": identity(
                        self.recovery_archive_identity
                    ),
                    "source_archive_identity": identity(self.source_archive),
                    "live_state_sha256": self.live_state_sha256,
                    "operations": [
                        {
                            "asset_id": operation.asset_id,
                            "path": operation.relative_path.as_posix(),
                            "existed_before": operation.existed_before,
                            "previous": identity(operation.previous),
                            "restored": identity(operation.restored),
                        }
                        for operation in self.operations
                    ],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")


def inspect_restore_archive(
    paths: AppDataPaths,
    archive_path: Path,
    *,
    limits: RestoreLimits = DEFAULT_RESTORE_LIMITS,
    test_hooks: RestoreTestHooks | None = None,
) -> RestorePlan:
    """Inspect an untrusted backup and return a content-free restore plan."""

    _require_restore_arguments(paths, limits)
    hooks = test_hooks or RestoreTestHooks()
    source = _validate_archive_source(paths, Path(archive_path))
    with configuration_mutation_gate():
        with tempfile.TemporaryDirectory(
            prefix=".context-palette-restore-stage-",
            dir=hooks.staging_parent or paths.application_root,
        ) as directory:
            stage_root = Path(directory)
            live_inventory = _current_inventory(paths, limits.payload)
            live_identity = _inventory_identity(live_inventory)
            inspected = _inspect_archive_to_stage(source, stage_root, limits)
            manifest_paths = {
                PurePosixPath(*entry.archive_path.parts[1:])
                for entry in inspected.manifest.entries
            }
            preserved = _stage_preserved_optional_files(
                paths,
                stage_root,
                live_inventory,
                manifest_paths,
            )
            if live_inventory != _current_inventory(paths, limits.payload):
                raise RestorePlanStaleError(
                    "Relevant live configuration changed during restore inspection."
                )
            snapshot_report = load_configuration_snapshot(
                AppDataPaths.from_root(stage_root)
            )
            if not snapshot_report.ok:
                raise RestoreConfigurationError(snapshot_report.errors)
            return _build_restore_plan(
                inspected,
                live_inventory,
                live_identity,
                preserved,
                snapshot_report.warnings,
            )


def commit_restore(
    paths: AppDataPaths,
    archive_path: Path,
    plan: RestorePlan,
    confirmation: RestoreConfirmation,
    *,
    recovery_directory: Path,
    limits: RestoreLimits = DEFAULT_RESTORE_LIMITS,
    now: datetime | None = None,
    test_hooks: RestoreTestHooks | None = None,
) -> RestoreResult:
    """Commit one previously inspected plan with recoverable all-file rollback."""

    _require_restore_arguments(paths, limits)
    if not isinstance(plan, RestorePlan):
        raise TypeError("plan must be a RestorePlan value")
    if not isinstance(confirmation, RestoreConfirmation):
        raise TypeError("confirmation must be a RestoreConfirmation value")
    _validate_confirmation(plan, confirmation)
    hooks = test_hooks or RestoreTestHooks()
    source = _validate_archive_source(paths, Path(archive_path))

    with configuration_mutation_gate():
        if _path_exists_or_reparse(paths.restore_journal_file):
            raise RestoreRecoveryRequiredError(
                "An unfinished restore must be recovered before another commit."
            )
        with tempfile.TemporaryDirectory(
            prefix=".context-palette-restore-commit-",
            dir=hooks.staging_parent or paths.application_root,
        ) as directory:
            stage_root = Path(directory)
            live_inventory = _current_inventory(paths, limits.payload)
            inspected = _inspect_archive_to_stage(source, stage_root, limits)
            manifest_paths = {
                PurePosixPath(*entry.archive_path.parts[1:])
                for entry in inspected.manifest.entries
            }
            preserved = _stage_preserved_optional_files(
                paths,
                stage_root,
                live_inventory,
                manifest_paths,
            )
            if live_inventory != _current_inventory(paths, limits.payload):
                raise RestorePlanStaleError(
                    "Relevant live configuration changed before restore commit."
                )
            snapshot_report = load_configuration_snapshot(
                AppDataPaths.from_root(stage_root)
            )
            if not snapshot_report.ok:
                raise RestoreConfigurationError(snapshot_report.errors)
            repeated_plan = _build_restore_plan(
                inspected,
                live_inventory,
                _inventory_identity(live_inventory),
                preserved,
                snapshot_report.warnings,
            )
            _assert_plan_unchanged(plan, repeated_plan)

            transaction_id = uuid.uuid4().hex
            recovery_path, recovery_identity = _create_recovery_archive(
                paths,
                Path(recovery_directory),
                live_inventory,
                transaction_id,
                limits,
                now,
            )
            if hooks.after_recovery_archive is not None:
                hooks.after_recovery_archive()
            # Prove that the independently published recovery artifact can be
            # parsed and supplies the promised bytes before live mutation starts.
            _read_recovery_archive(
                paths,
                recovery_path,
                recovery_identity,
                limits,
            )
            journal = _build_journal(
                transaction_id,
                recovery_path,
                recovery_identity,
                inspected.archive,
                inspected.manifest.entries,
                live_inventory,
            )
            atomic_replace_bytes(
                paths.restore_journal_file,
                journal.to_json_bytes(),
                preserve_previous=False,
            )
            _fsync_existing_file(paths.restore_journal_file)
            try:
                if hooks.after_journal is not None:
                    hooks.after_journal()
                for index, operation in enumerate(journal.operations, start=1):
                    staged = stage_root.joinpath(*operation.relative_path.parts)
                    atomic_replace_bytes(
                        _destination_path(paths, operation.relative_path),
                        staged.read_bytes(),
                        preserve_previous=False,
                    )
                    if hooks.after_replacement is not None:
                        hooks.after_replacement(index, operation.asset_id)
                if hooks.before_final_validation is not None:
                    hooks.before_final_validation()
                _verify_restored_operations(paths, journal.operations)
                _verify_expected_live_state(
                    paths, live_inventory, journal.operations, limits
                )
                final_report = load_configuration_snapshot(paths)
                if not final_report.ok:
                    raise RestoreConfigurationError(final_report.errors)
                _verify_expected_live_state(
                    paths, live_inventory, journal.operations, limits
                )
                _remove_journal(paths.restore_journal_file)
            except Exception as exc:
                try:
                    _rollback_from_journal(paths, journal, limits)
                    _remove_journal(paths.restore_journal_file)
                except Exception as rollback_exc:
                    raise RestoreCommitError(rollback_completed=False) from rollback_exc
                raise RestoreCommitError(rollback_completed=True) from exc

            return RestoreResult(
                recovery_path,
                repeated_plan.files_to_replace,
                repeated_plan.files_to_create,
                final_report.warnings,
            )


def recover_interrupted_restore(
    paths: AppDataPaths,
    *,
    limits: RestoreLimits = DEFAULT_RESTORE_LIMITS,
) -> StartupRecoveryResult:
    """Complete idempotent rollback from a durable pending journal, if present."""

    _require_restore_arguments(paths, limits)
    journal_path = paths.restore_journal_file
    if not _path_exists_or_reparse(journal_path):
        return StartupRecoveryResult(False)
    with configuration_mutation_gate():
        if not _path_exists_or_reparse(journal_path):
            return StartupRecoveryResult(False)
        try:
            journal = _read_journal(journal_path)
            _rollback_from_journal(paths, journal, limits)
            _remove_journal(journal_path)
        except RestoreRecoveryError:
            raise
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            raise RestoreRecoveryError(
                "The unfinished restore could not be rolled back safely."
            ) from exc
    return StartupRecoveryResult(True)


def _require_restore_arguments(paths: AppDataPaths, limits: RestoreLimits) -> None:
    if not isinstance(paths, AppDataPaths):
        raise TypeError("paths must be an AppDataPaths value")
    if not isinstance(limits, RestoreLimits):
        raise TypeError("limits must be a RestoreLimits value")


def _validate_confirmation(
    plan: RestorePlan,
    confirmation: RestoreConfirmation,
) -> None:
    if (
        confirmation.archive_sha256 != plan.archive.sha256
        or confirmation.live_state_sha256 != plan.live_state_sha256
    ):
        raise RestoreConfirmationError(
            "Restore confirmation does not match the inspected plan."
        )
    if not confirmation.confirmed:
        raise RestoreConfirmationError("Restore requires explicit confirmation.")
    if plan.built_in_acknowledgement_required and not confirmation.built_in_acknowledged:
        raise RestoreConfirmationError(
            "Replacing Built-in configuration requires separate acknowledgement."
        )


def _assert_plan_unchanged(expected: RestorePlan, actual: RestorePlan) -> None:
    if expected != actual:
        raise RestorePlanStaleError(
            "The archive or relevant live configuration changed after inspection."
        )


def _validate_archive_source(paths: AppDataPaths, source: Path) -> Path:
    candidate = source.expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.absolute()
    root = paths.application_root.absolute()
    try:
        if _is_relative_to(candidate, root) or _is_relative_to(
            candidate.resolve(strict=True), root.resolve(strict=True)
        ):
            raise RestoreArchiveError(
                "Restore archives must remain outside the application root."
            )
    except OSError as exc:
        raise RestoreArchiveError("The restore archive is unavailable.") from exc
    if _is_reparse_point(candidate):
        raise RestoreArchiveError("The restore archive cannot be a link or reparse point.")
    try:
        metadata = candidate.stat(follow_symlinks=False)
    except OSError as exc:
        raise RestoreArchiveError("The restore archive is unavailable.") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise RestoreArchiveError("The restore archive is not a regular file.")
    return candidate


def _inspect_archive_to_stage(
    source: Path,
    stage_root: Path,
    limits: RestoreLimits,
) -> _InspectedArchive:
    try:
        with source.open("rb") as raw:
            before = os.fstat(raw.fileno())
            if before.st_size > limits.max_archive_bytes:
                raise RestoreLimitError("The restore archive exceeds the size limit.")
            archive_digest = _hash_stream_bounded(
                raw,
                limits.max_archive_bytes,
                "restore archive",
            )
            archive_identity = FileIdentity(before.st_size, archive_digest)
            raw.seek(0)
            with zipfile.ZipFile(raw, "r") as archive:
                infos = archive.infolist()
                _validate_zip_inventory(raw, infos, limits)
                manifest_info = infos[-1]
                manifest_bytes = _read_zip_entry(
                    archive,
                    manifest_info,
                    expected_size=manifest_info.file_size,
                    expected_sha256=None,
                    max_bytes=limits.max_manifest_bytes,
                    destination=None,
                )
                try:
                    manifest = BackupManifest.from_json_bytes(manifest_bytes)
                except (KeyError, ValueError) as exc:
                    raise RestoreCompatibilityError(
                        "The backup manifest is invalid or incompatible."
                    ) from exc
                _validate_manifest_limits(manifest, limits.payload)
                expected_names = [
                    entry.archive_path.as_posix() for entry in manifest.entries
                ] + ["manifest.json"]
                if [info.filename for info in infos] != expected_names:
                    raise RestoreArchiveError(
                        "Archive payload entries do not match the manifest one-to-one."
                    )
                for info, entry in zip(infos[:-1], manifest.entries, strict=True):
                    relative_path = PurePosixPath(*entry.archive_path.parts[1:])
                    _validate_catalog_relative_path(relative_path, entry.asset_id)
                    destination = stage_root.joinpath(*relative_path.parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    _read_zip_entry(
                        archive,
                        info,
                        expected_size=entry.size,
                        expected_sha256=entry.sha256,
                        max_bytes=limits.payload.max_entry_bytes,
                        destination=destination,
                    )
            after = os.fstat(raw.fileno())
        if _stat_identity(before) != _stat_identity(after):
            raise RestorePlanStaleError(
                "The restore archive changed during bounded inspection."
            )
    except RestoreError:
        raise
    except (OSError, EOFError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        raise RestoreArchiveError("The restore archive is invalid or truncated.") from exc
    return _InspectedArchive(
        manifest,
        archive_identity,
        hashlib.sha256(manifest_bytes).hexdigest(),
    )


def _validate_zip_inventory(
    raw,
    infos: list[zipfile.ZipInfo],
    limits: RestoreLimits,
) -> None:
    if not infos or len(infos) > limits.payload.max_entries + 1:
        raise RestoreLimitError("The restore archive exceeds the entry-count limit.")
    if infos[-1].filename != "manifest.json":
        raise RestoreArchiveError("The restore archive has no final manifest entry.")
    names: set[str] = set()
    collision_keys: set[str] = set()
    manifest_count = 0
    for info in infos:
        name = _validate_zip_name(info.filename)
        if name in names:
            raise RestoreArchiveError("The restore archive contains duplicate paths.")
        names.add(name)
        collision_key = unicodedata.normalize("NFC", name).casefold()
        if collision_key in collision_keys:
            raise RestoreArchiveError(
                "The restore archive contains case-insensitive path collisions."
            )
        collision_keys.add(collision_key)
        if name == "manifest.json":
            manifest_count += 1
            if info.file_size > limits.max_manifest_bytes:
                raise RestoreLimitError("The restore manifest exceeds the size limit.")
        elif info.file_size > limits.payload.max_entry_bytes:
            raise RestoreLimitError("A restore payload exceeds the entry-size limit.")
        if info.is_dir() or name.endswith("/"):
            raise RestoreArchiveError("Directory entries are not supported.")
        if info.flag_bits & 0x1:
            raise RestoreArchiveError("Encrypted archive entries are not supported.")
        if info.flag_bits & 0x8:
            raise RestoreArchiveError("Streaming ZIP descriptors are not supported.")
        if info.compress_type not in _SUPPORTED_COMPRESSION:
            raise RestoreArchiveError("The archive uses unsupported compression.")
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        file_type = stat.S_IFMT(unix_mode)
        if file_type not in {0, stat.S_IFREG}:
            raise RestoreArchiveError("Archive entries must represent regular files.")
        if (info.external_attr & 0xFFFF) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise RestoreArchiveError("Archive entries cannot represent reparse points.")
        if (info.external_attr & 0xFFFF) & 0x10:
            raise RestoreArchiveError("Archive entries cannot represent directories.")
        _validate_local_header(raw, info)
    if manifest_count != 1:
        raise RestoreArchiveError("The restore archive must contain one manifest.")


def _validate_local_header(raw, info: zipfile.ZipInfo) -> None:
    raw.seek(info.header_offset)
    header = raw.read(_LOCAL_HEADER.size)
    if len(header) != _LOCAL_HEADER.size:
        raise RestoreArchiveError("An archive local header is truncated.")
    (
        signature,
        _version,
        flags,
        compression,
        _time,
        _date,
        crc,
        compressed_size,
        file_size,
        name_length,
        extra_length,
    ) = _LOCAL_HEADER.unpack(header)
    if signature != _LOCAL_HEADER_SIGNATURE:
        raise RestoreArchiveError("An archive local header is invalid.")
    raw_name = raw.read(name_length)
    if len(raw_name) != name_length or len(raw.read(extra_length)) != extra_length:
        raise RestoreArchiveError("An archive local header is truncated.")
    encoding = "utf-8" if flags & 0x800 else "cp437"
    try:
        header_name = raw_name.decode(encoding)
    except UnicodeError as exc:
        raise RestoreArchiveError("An archive local path is malformed.") from exc
    if (
        header_name != info.filename
        or flags != info.flag_bits
        or compression != info.compress_type
        or crc != info.CRC
        or compressed_size != info.compress_size
        or file_size != info.file_size
    ):
        raise RestoreArchiveError("Archive local and central headers disagree.")


def _validate_zip_name(name: str) -> str:
    if not isinstance(name, str) or not name or name != unicodedata.normalize("NFC", name):
        raise RestoreArchiveError("An archive path is malformed or ambiguous.")
    if "\\" in name or name.startswith("/") or name.endswith("/") or "//" in name:
        raise RestoreArchiveError("Archive paths must use canonical relative separators.")
    windows = PureWindowsPath(name)
    if windows.drive or windows.root:
        raise RestoreArchiveError("Absolute archive paths are not supported.")
    components = name.split("/")
    if any(not _safe_windows_component(part) for part in components):
        raise RestoreArchiveError("An archive path contains an unsafe component.")
    return name


def _safe_windows_component(part: str) -> bool:
    if not part or part in {".", ".."} or part.endswith((" ", ".")):
        return False
    if any(ord(character) < 32 or character == "\x7f" for character in part):
        return False
    if any(character in _WINDOWS_UNSAFE_CHARACTERS for character in part):
        return False
    stem = part.split(".", 1)[0].rstrip(" .").upper()
    return stem not in _WINDOWS_RESERVED_NAMES


def _read_zip_entry(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    expected_size: int,
    expected_sha256: str | None,
    max_bytes: int,
    destination: Path | None,
) -> bytes:
    if info.file_size != expected_size:
        raise RestoreArchiveError("Archive and manifest entry sizes disagree.")
    digest = hashlib.sha256()
    crc = 0
    size = 0
    captured = bytearray() if destination is None else None
    output = destination.open("xb") if destination is not None else None
    try:
        with archive.open(info, "r") as source:
            while chunk := source.read(_CHUNK_BYTES):
                size += len(chunk)
                if size > max_bytes or size > expected_size:
                    raise RestoreLimitError("An archive entry exceeds its byte limit.")
                digest.update(chunk)
                crc = binascii.crc32(chunk, crc)
                if output is not None:
                    output.write(chunk)
                else:
                    captured.extend(chunk)
        if output is not None:
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        if output is not None:
            output.close()
        if destination is not None:
            destination.unlink(missing_ok=True)
        raise
    else:
        if output is not None:
            output.close()
    if size != expected_size:
        raise RestoreArchiveError("An archive entry ended before its declared size.")
    if (crc & 0xFFFFFFFF) != info.CRC:
        raise RestoreArchiveError("An archive entry CRC check failed.")
    if expected_sha256 is not None and digest.hexdigest() != expected_sha256:
        raise RestoreArchiveError("An archive payload checksum does not match its manifest.")
    return bytes(captured or b"")


def _validate_manifest_limits(manifest: BackupManifest, limits: BackupLimits) -> None:
    if len(manifest.entries) > limits.max_entries:
        raise RestoreLimitError("The manifest exceeds the entry-count limit.")
    total = 0
    seen_casefolded: set[str] = set()
    for entry in manifest.entries:
        if entry.size > limits.max_entry_bytes:
            raise RestoreLimitError("A manifest entry exceeds the entry-size limit.")
        total += entry.size
        if total > limits.max_total_bytes:
            raise RestoreLimitError("The manifest exceeds the total payload-size limit.")
        path = entry.archive_path.as_posix()
        key = unicodedata.normalize("NFC", path).casefold()
        if key in seen_casefolded:
            raise RestoreArchiveError("Manifest paths collide case-insensitively.")
        seen_casefolded.add(key)


def _validate_catalog_relative_path(path: PurePosixPath, asset_id: str) -> None:
    _validate_zip_name(path.as_posix())
    spec = asset_spec_by_id(asset_id)
    if spec.backup_policy is BackupPolicy.EXCLUDED or asset_spec_for_path(path) != spec:
        raise RestoreCompatibilityError(
            "A restore entry is not eligible under the current data catalog."
        )


def _stage_preserved_optional_files(
    paths: AppDataPaths,
    stage_root: Path,
    inventory,
    manifest_paths: set[PurePosixPath],
) -> tuple[PreservedRestoreFile, ...]:
    candidates = tuple(
        item
        for item in inventory
        if item.fingerprint is not None
        and item.relative_path not in manifest_paths
        and asset_spec_by_id(item.asset_id).requirement is AssetRequirement.OPTIONAL
    )
    if candidates:
        _stage_inventory(paths, candidates, stage_root, 1, BackupTestHooks())
    return tuple(
        PreservedRestoreFile(item.asset_id, item.relative_path) for item in candidates
    )


def _current_inventory(paths: AppDataPaths, limits: BackupLimits):
    return _build_inventory(
        paths,
        _selected_specs(
            BackupOptions(
                include_inbox=True,
                include_managed_content=True,
                limits=limits,
            )
        ),
        limits,
    )


def _inventory_identity(inventory) -> str:
    digest = hashlib.sha256()
    for item in inventory:
        digest.update(item.asset_id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.relative_path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        if item.fingerprint is None:
            digest.update(b"absent")
        else:
            digest.update(str(item.fingerprint.size).encode("ascii"))
            digest.update(b":")
            digest.update(item.fingerprint.sha256.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _build_restore_plan(
    inspected: _InspectedArchive,
    live_inventory,
    live_identity: str,
    preserved: tuple[PreservedRestoreFile, ...],
    warnings: tuple[SnapshotValidationIssue, ...],
) -> RestorePlan:
    live = {
        item.relative_path: item.fingerprint
        for item in live_inventory
        if item.fingerprint is not None
    }
    files = tuple(
        RestoreFile(
            entry.asset_id,
            PurePosixPath(*entry.archive_path.parts[1:]),
            FileIdentity(entry.size, entry.sha256),
        )
        for entry in inspected.manifest.entries
    )
    replacements = tuple(item for item in files if item.relative_path in live)
    creations = tuple(item for item in files if item.relative_path not in live)
    built_in = tuple(
        item
        for item in files
        if asset_spec_by_id(item.asset_id).ownership is AssetOwnership.BUILT_IN
    )
    sensitive: list[RestoreSensitiveCategory] = []
    specs = tuple(asset_spec_by_id(item.asset_id) for item in files)
    if any(spec.sensitivity is AssetSensitivity.PRIVATE_PATHS for spec in specs):
        sensitive.append(RestoreSensitiveCategory.PRIVATE_PATHS)
    if any(item.asset_id == "inbox" for item in files):
        sensitive.append(RestoreSensitiveCategory.CAPTURED_INBOX)
    if any(item.asset_id == "managed-text-action-source" for item in files):
        sensitive.append(RestoreSensitiveCategory.MANAGED_CONTENT)
    legacy = any(issue.category is ValidationCategory.LEGACY for issue in warnings)
    return RestorePlan(
        inspected.archive,
        inspected.manifest_sha256,
        live_identity,
        replacements,
        creations,
        preserved,
        built_in,
        tuple(sensitive),
        warnings,
        RestoreCompatibility(
            BACKUP_FORMAT,
            BACKUP_FORMAT_VERSION,
            BACKUP_DATA_MODEL_VERSION,
            BACKUP_SCOPE,
            False,
            legacy,
        ),
        True,
        bool(built_in),
    )


def _build_journal(
    transaction_id: str,
    recovery_archive: Path,
    recovery_identity: FileIdentity,
    source_archive: FileIdentity,
    entries: tuple[BackupManifestEntry, ...],
    live_inventory,
) -> _RestoreJournal:
    live = {item.relative_path: item.fingerprint for item in live_inventory}
    operations: list[_JournalOperation] = []
    for entry in entries:
        relative = PurePosixPath(*entry.archive_path.parts[1:])
        fingerprint = live.get(relative)
        previous = (
            None
            if fingerprint is None
            else FileIdentity(fingerprint.size, fingerprint.sha256)
        )
        operations.append(
            _JournalOperation(
                entry.asset_id,
                relative,
                previous is not None,
                previous,
                FileIdentity(entry.size, entry.sha256),
            )
        )
    return _RestoreJournal(
        transaction_id,
        recovery_archive.absolute(),
        recovery_identity,
        source_archive,
        _inventory_identity(live_inventory),
        tuple(operations),
    )


def _create_recovery_archive(
    paths: AppDataPaths,
    recovery_directory: Path,
    live_inventory,
    transaction_id: str,
    limits: RestoreLimits,
    now: datetime | None,
) -> tuple[Path, FileIdentity]:
    directory = _validate_recovery_directory(paths, recovery_directory)
    timestamp = _recovery_timestamp(now)
    destination = directory / (
        f"context-palette-recovery-{timestamp}-{transaction_id[:12]}.zip"
    )
    if destination.exists():
        raise RestoreRecoveryError("A recovery archive name collision occurred.")
    with tempfile.TemporaryDirectory(
        prefix=".context-palette-recovery-stage-",
        dir=paths.application_root,
    ) as staging_directory:
        stage_root = Path(staging_directory)
        _stage_inventory(paths, live_inventory, stage_root, 1, BackupTestHooks())
        if live_inventory != _current_inventory(paths, limits.payload):
            raise RestorePlanStaleError(
                "Relevant live configuration changed during recovery capture."
            )
        _write_recovery_zip(stage_root, destination, live_inventory)
    identity = _fingerprint_plain_file(destination, limits.max_archive_bytes)
    _fsync_existing_file(destination)
    _read_recovery_archive(paths, destination, identity, limits)
    return destination, identity


def _validate_recovery_directory(paths: AppDataPaths, directory: Path) -> Path:
    candidate = directory.expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.absolute()
    root = paths.application_root.absolute()
    try:
        resolved_parent = candidate.parent.resolve(strict=True)
        resolved_candidate = resolved_parent / candidate.name
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        raise RestoreRecoveryError("The recovery destination is unavailable.") from exc
    if _is_relative_to(candidate, root) or _is_relative_to(resolved_candidate, resolved_root):
        raise RestoreRecoveryError(
            "Recovery archives must remain outside the application root."
        )
    try:
        candidate.mkdir(parents=False, exist_ok=True)
    except OSError as exc:
        raise RestoreRecoveryError("The recovery destination is unavailable.") from exc
    if _is_reparse_point(candidate) or not candidate.is_dir():
        raise RestoreRecoveryError("The recovery destination is unsafe.")
    return candidate


def _recovery_timestamp(value: datetime | None) -> str:
    timestamp = value or datetime.now(timezone.utc).replace(microsecond=0)
    if (
        not isinstance(timestamp, datetime)
        or timestamp.tzinfo is None
        or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp)
    ):
        raise ValueError("Recovery creation time must use timezone-aware UTC.")
    return timestamp.strftime("%Y%m%dT%H%M%SZ")


def _write_recovery_zip(stage_root: Path, destination: Path, inventory) -> None:
    existing = tuple(item for item in inventory if item.fingerprint is not None)
    absent_fixed = tuple(
        item.relative_path.as_posix()
        for item in inventory
        if item.fingerprint is None
        and asset_spec_by_id(item.asset_id).relative_path is not None
    )
    entries = [
        {
            "asset_id": item.asset_id,
            "path": (PurePosixPath("payload") / item.relative_path).as_posix(),
            "size": item.fingerprint.size,
            "sha256": item.fingerprint.sha256,
        }
        for item in existing
    ]
    manifest = (
        json.dumps(
            {
                "format": RECOVERY_ARCHIVE_FORMAT,
                "version": RECOVERY_ARCHIVE_VERSION,
                "entries": entries,
                "absent_fixed_paths": list(absent_fixed),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
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
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as archive:
                for item in existing:
                    source = stage_root.joinpath(*item.relative_path.parts)
                    archive.writestr(
                        _recovery_zip_info(
                            (PurePosixPath("payload") / item.relative_path).as_posix()
                        ),
                        source.read_bytes(),
                    )
                archive.writestr(_recovery_zip_info("recovery-manifest.json"), manifest)
            temporary.flush()
            os.fsync(temporary.fileno())
        try:
            if os.name == "nt":
                os.rename(temporary_path, destination)
            else:
                os.link(temporary_path, destination)
                os.unlink(temporary_path)
        except FileExistsError as exc:
            raise RestoreRecoveryError("A recovery archive name collision occurred.") from exc
        temporary_path = None
    except RestoreRecoveryError:
        raise
    except RestoreError as exc:
        raise RestoreRecoveryError("The recovery archive is invalid.") from exc
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        raise RestoreRecoveryError("The recovery archive could not be published safely.") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _recovery_zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 0
    info.external_attr = 0
    return info


def _rollback_from_journal(
    paths: AppDataPaths,
    journal: _RestoreJournal,
    limits: RestoreLimits,
) -> None:
    recovery_payloads = _read_recovery_archive(
        paths,
        journal.recovery_archive,
        journal.recovery_archive_identity,
        limits,
    )
    for operation in journal.operations:
        destination = _destination_path(paths, operation.relative_path)
        if operation.existed_before:
            payload = recovery_payloads.get(operation.relative_path)
            if payload is None or FileIdentity(
                len(payload), hashlib.sha256(payload).hexdigest()
            ) != operation.previous:
                raise RestoreRecoveryError("Recovery payload identity is incomplete.")
            if not _path_exists_or_reparse(destination):
                raise RestoreRecoveryError(
                    "A restore destination disappeared before rollback."
                )
            current = _fingerprint_plain_file(
                destination, limits.payload.max_entry_bytes
            )
            if current == operation.previous:
                continue
            if current != operation.restored:
                raise RestoreRecoveryError(
                    "A restore destination changed before rollback."
                )
            atomic_replace_bytes(destination, payload, preserve_previous=False)
            continue
        if not _path_exists_or_reparse(destination):
            continue
        current = _fingerprint_plain_file(destination, limits.payload.max_entry_bytes)
        if current != operation.restored:
            raise RestoreRecoveryError(
                "A newly created restore destination changed before rollback."
            )
        try:
            destination.unlink()
        except OSError as exc:
            raise RestoreRecoveryError(
                "A newly created restore destination could not be removed."
            ) from exc
    _verify_rolled_back_operations(paths, journal.operations, limits)
    if (
        _inventory_identity(_current_inventory(paths, limits.payload))
        != journal.live_state_sha256
    ):
        raise RestoreRecoveryError(
            "Relevant configuration changed before rollback completed."
        )


def _read_recovery_archive(
    paths: AppDataPaths,
    archive_path: Path,
    expected_identity: FileIdentity,
    limits: RestoreLimits,
) -> dict[PurePosixPath, bytes]:
    candidate = archive_path.absolute()
    root = paths.application_root.absolute()
    try:
        if _is_relative_to(candidate, root) or _is_relative_to(
            candidate.resolve(strict=True), root.resolve(strict=True)
        ):
            raise RestoreRecoveryError("The recovery archive location is unsafe.")
    except OSError as exc:
        raise RestoreRecoveryError("The recovery archive is unavailable.") from exc
    if _is_reparse_point(candidate):
        raise RestoreRecoveryError("The recovery archive is unsafe.")
    try:
        with candidate.open("rb") as raw:
            before = os.fstat(raw.fileno())
            identity = FileIdentity(
                before.st_size,
                _hash_stream_bounded(
                    raw, limits.max_archive_bytes, "recovery file"
                ),
            )
            if identity != expected_identity:
                raise RestoreRecoveryError(
                    "The recovery archive identity does not match the journal."
                )
            raw.seek(0)
            with zipfile.ZipFile(raw, "r") as archive:
                infos = archive.infolist()
                _validate_recovery_zip_inventory(raw, infos, limits)
                manifest_info = infos[-1]
                manifest_bytes = _read_zip_entry(
                    archive,
                    manifest_info,
                    expected_size=manifest_info.file_size,
                    expected_sha256=None,
                    max_bytes=MAX_RESTORE_MANIFEST_BYTES,
                    destination=None,
                )
                manifest = _parse_recovery_manifest(manifest_bytes)
                expected_names = [entry[1] for entry in manifest] + ["recovery-manifest.json"]
                if [info.filename for info in infos] != expected_names:
                    raise RestoreRecoveryError("Recovery payloads do not match the manifest.")
                payloads: dict[PurePosixPath, bytes] = {}
                total = 0
                for info, (asset_id, name, entry_identity) in zip(
                    infos[:-1], manifest, strict=True
                ):
                    relative = PurePosixPath(*PurePosixPath(name).parts[1:])
                    _validate_catalog_relative_path(relative, asset_id)
                    payload = _read_zip_entry(
                        archive,
                        info,
                        expected_size=entry_identity.size,
                        expected_sha256=entry_identity.sha256,
                        max_bytes=limits.payload.max_entry_bytes,
                        destination=None,
                    )
                    total += len(payload)
                    if total > limits.payload.max_total_bytes:
                        raise RestoreRecoveryError("The recovery payload exceeds its limit.")
                    payloads[relative] = payload
            after = os.fstat(raw.fileno())
        if _stat_identity(before) != _stat_identity(after):
            raise RestoreRecoveryError("The recovery archive changed while being read.")
        return payloads
    except RestoreRecoveryError:
        raise
    except RestoreError as exc:
        raise RestoreRecoveryError("The recovery archive is invalid.") from exc
    except (OSError, EOFError, KeyError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        raise RestoreRecoveryError("The recovery archive is invalid.") from exc


def _validate_recovery_zip_inventory(
    raw,
    infos: list[zipfile.ZipInfo],
    limits: RestoreLimits,
) -> None:
    if not infos or len(infos) > limits.payload.max_entries + 1:
        raise RestoreRecoveryError("The recovery archive has too many entries.")
    if infos[-1].filename != "recovery-manifest.json":
        raise RestoreRecoveryError("The recovery archive manifest is missing.")
    names: set[str] = set()
    collisions: set[str] = set()
    total = 0
    for info in infos:
        name = _validate_zip_name(info.filename)
        key = unicodedata.normalize("NFC", name).casefold()
        if name in names or key in collisions:
            raise RestoreRecoveryError("Recovery archive paths are not unique.")
        names.add(name)
        collisions.add(key)
        if info.is_dir() or info.flag_bits & 0x9:
            raise RestoreRecoveryError("A recovery archive entry is unsafe.")
        if info.compress_type not in _SUPPORTED_COMPRESSION:
            raise RestoreRecoveryError("Recovery archive compression is unsupported.")
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_IFMT(unix_mode) not in {0, stat.S_IFREG}:
            raise RestoreRecoveryError("Recovery entries must be regular files.")
        if (info.external_attr & 0xFFFF) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
        ):
            raise RestoreRecoveryError("Recovery entries cannot be reparse points.")
        if (info.external_attr & 0xFFFF) & 0x10:
            raise RestoreRecoveryError("Recovery entries cannot be directories.")
        if name == "recovery-manifest.json":
            if info.file_size > MAX_RESTORE_MANIFEST_BYTES:
                raise RestoreRecoveryError("The recovery manifest is too large.")
        else:
            if info.file_size > limits.payload.max_entry_bytes:
                raise RestoreRecoveryError("A recovery payload is too large.")
            total += info.file_size
            if total > limits.payload.max_total_bytes:
                raise RestoreRecoveryError("The recovery payload exceeds its limit.")
        _validate_local_header(raw, info)


def _parse_recovery_manifest(
    payload: bytes,
) -> tuple[tuple[str, str, FileIdentity], ...]:
    raw = _strict_json_object(payload, "recovery manifest")
    if set(raw) != {"format", "version", "entries", "absent_fixed_paths"}:
        raise ValueError("Recovery manifest keys are invalid.")
    if raw["format"] != RECOVERY_ARCHIVE_FORMAT or raw["version"] != 1:
        raise ValueError("Recovery manifest format is unsupported.")
    if not isinstance(raw["entries"], list) or not isinstance(
        raw["absent_fixed_paths"], list
    ):
        raise ValueError("Recovery manifest collections are invalid.")
    result = []
    for value in raw["entries"]:
        if not isinstance(value, dict) or set(value) != {
            "asset_id", "path", "size", "sha256"
        }:
            raise ValueError("Recovery manifest entry keys are invalid.")
        asset_id = _strict_text(value["asset_id"])
        name = _strict_text(value["path"])
        result.append(
            (
                asset_id,
                name,
                FileIdentity(
                    _strict_integer(value["size"]),
                    _strict_text(value["sha256"]),
                ),
            )
        )
    names = tuple(item[1] for item in result)
    if names != tuple(sorted(names)) or len(names) != len(set(names)):
        raise ValueError("Recovery manifest entries are not unique and ordered.")
    present_relative_paths: set[PurePosixPath] = set()
    collision_keys: set[str] = set()
    for asset_id, name, _identity in result:
        path = PurePosixPath(name)
        if not path.parts or path.parts[0] != "payload":
            raise ValueError("Recovery payload path is invalid.")
        relative = PurePosixPath(*path.parts[1:])
        _validate_catalog_relative_path(relative, asset_id)
        collision_key = relative.as_posix().casefold()
        if collision_key in collision_keys:
            raise ValueError("Recovery payload paths collide case-insensitively.")
        collision_keys.add(collision_key)
        present_relative_paths.add(relative)
    absent = tuple(_strict_text(value) for value in raw["absent_fixed_paths"])
    if absent != tuple(sorted(absent)) or len(absent) != len(set(absent)):
        raise ValueError("Recovery absent paths are not unique and ordered.")
    for name in absent:
        relative = PurePosixPath(name)
        spec = asset_spec_for_path(relative)
        if (
            spec is None
            or spec.relative_path != relative
            or spec.backup_policy is BackupPolicy.EXCLUDED
        ):
            raise ValueError("Recovery absent path is not a fixed catalog asset.")
    absent_paths = {PurePosixPath(name) for name in absent}
    fixed_paths = {
        spec.relative_path
        for spec in DATA_ASSET_CATALOG
        if spec.relative_path is not None
        and spec.backup_policy is not BackupPolicy.EXCLUDED
    }
    present_fixed_paths = present_relative_paths & fixed_paths
    if (
        present_fixed_paths & absent_paths
        or present_fixed_paths | absent_paths != fixed_paths
    ):
        raise ValueError("Recovery fixed-asset inventory is incomplete.")
    return tuple(result)


def _read_journal(path: Path) -> _RestoreJournal:
    if _is_reparse_point(path):
        raise RestoreRecoveryError("The restore journal is unsafe.")
    try:
        metadata = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_RESTORE_JOURNAL_BYTES:
            raise RestoreRecoveryError("The restore journal is invalid.")
        with path.open("rb") as stream:
            payload = stream.read(MAX_RESTORE_JOURNAL_BYTES + 1)
        if len(payload) > MAX_RESTORE_JOURNAL_BYTES:
            raise RestoreRecoveryError("The restore journal is invalid.")
        raw = _strict_json_object(payload, "restore journal")
        expected = {
            "format", "version", "transaction_id", "state", "recovery_archive",
            "recovery_archive_identity", "source_archive_identity", "live_state_sha256",
            "operations",
        }
        if set(raw) != expected or not isinstance(raw["operations"], list):
            raise ValueError("Restore journal keys are invalid.")
        if not raw["operations"]:
            raise ValueError("Restore journal contains no operations.")
        if len(raw["operations"]) > DEFAULT_BACKUP_LIMITS.max_entries:
            raise ValueError("Restore journal contains too many operations.")
        operations = tuple(_parse_journal_operation(value) for value in raw["operations"])
        return _RestoreJournal(
            transaction_id=_strict_text(raw["transaction_id"]),
            recovery_archive=Path(_strict_text(raw["recovery_archive"])),
            recovery_archive_identity=_parse_identity(raw["recovery_archive_identity"]),
            source_archive=_parse_identity(raw["source_archive_identity"]),
            live_state_sha256=_strict_text(raw["live_state_sha256"]),
            operations=operations,
            state=_strict_text(raw["state"]),
            format=_strict_text(raw["format"]),
            version=_strict_integer(raw["version"]),
        )
    except RestoreRecoveryError:
        raise
    except RestoreError as exc:
        raise RestoreRecoveryError("The restore journal is invalid.") from exc
    except (OSError, KeyError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise RestoreRecoveryError("The restore journal is invalid.") from exc


def _parse_journal_operation(value: object) -> _JournalOperation:
    if not isinstance(value, dict) or set(value) != {
        "asset_id", "path", "existed_before", "previous", "restored"
    }:
        raise ValueError("Restore journal operation keys are invalid.")
    existed = value["existed_before"]
    if not isinstance(existed, bool):
        raise ValueError("Restore journal existence marker must be boolean.")
    previous = None if value["previous"] is None else _parse_identity(value["previous"])
    return _JournalOperation(
        _strict_text(value["asset_id"]),
        PurePosixPath(_strict_text(value["path"])),
        existed,
        previous,
        _parse_identity(value["restored"]),
    )


def _parse_identity(value: object) -> FileIdentity:
    if not isinstance(value, dict) or set(value) != {"size", "sha256"}:
        raise ValueError("File identity keys are invalid.")
    return FileIdentity(_strict_integer(value["size"]), _strict_text(value["sha256"]))


def _strict_json_object(payload: bytes, label: str) -> dict[str, object]:
    if not isinstance(payload, bytes):
        raise ValueError(f"{label} input must be bytes.")

    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{label} contains duplicate keys.")
            result[key] = value
        return result

    raw = json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=reject_duplicates,
        parse_constant=lambda _value: (_ for _ in ()).throw(
            ValueError(f"{label} constants are unsupported.")
        ),
    )
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object.")
    return raw


def _strict_text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Expected text.")
    return value


def _strict_integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("Expected an integer.")
    return value


def _verify_restored_operations(
    paths: AppDataPaths,
    operations: tuple[_JournalOperation, ...],
) -> None:
    for operation in operations:
        destination = _destination_path(paths, operation.relative_path)
        if _fingerprint_plain_file(destination, operation.restored.size) != operation.restored:
            raise RestoreCommitError(rollback_completed=False)


def _verify_expected_live_state(
    paths: AppDataPaths,
    initial_inventory,
    operations: tuple[_JournalOperation, ...],
    limits: RestoreLimits,
) -> None:
    expected = {
        item.relative_path: (
            None
            if item.fingerprint is None
            else FileIdentity(item.fingerprint.size, item.fingerprint.sha256)
        )
        for item in initial_inventory
    }
    for operation in operations:
        expected[operation.relative_path] = operation.restored
    current = {
        item.relative_path: (
            None
            if item.fingerprint is None
            else FileIdentity(item.fingerprint.size, item.fingerprint.sha256)
        )
        for item in _current_inventory(paths, limits.payload)
    }
    if current != expected:
        raise RestorePlanStaleError(
            "Relevant configuration changed during restore commit."
        )


def _verify_rolled_back_operations(
    paths: AppDataPaths,
    operations: tuple[_JournalOperation, ...],
    limits: RestoreLimits,
) -> None:
    for operation in operations:
        destination = _destination_path(paths, operation.relative_path)
        if operation.existed_before:
            if _fingerprint_plain_file(
                destination, limits.payload.max_entry_bytes
            ) != operation.previous:
                raise RestoreRecoveryError("Rollback verification failed.")
        elif destination.exists():
            raise RestoreRecoveryError("Rollback left a transaction-created file.")


def _destination_path(paths: AppDataPaths, relative: PurePosixPath) -> Path:
    spec = asset_spec_for_path(relative)
    if spec is None or spec.backup_policy is BackupPolicy.EXCLUDED:
        raise RestoreRecoveryError("A restore destination is not catalogued.")
    destination = paths.application_root.joinpath(*relative.parts).absolute()
    root = paths.application_root.absolute()
    if not _is_relative_to(destination, root):
        raise RestoreRecoveryError("A restore destination escapes the application root.")
    current = root
    for part in relative.parts[:-1]:
        current /= part
        if _path_exists_or_reparse(current) and _is_reparse_point(current):
            raise RestoreRecoveryError("A restore destination uses a reparse point.")
    if _path_exists_or_reparse(destination) and (
        _is_reparse_point(destination) or not destination.is_file()
    ):
        raise RestoreRecoveryError("A restore destination is not a regular file.")
    return destination


def _path_exists_or_reparse(path: Path) -> bool:
    return path.exists() or _is_reparse_point(path)


def _fingerprint_plain_file(path: Path, max_bytes: int) -> FileIdentity:
    try:
        metadata = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode) or _is_reparse_point(path):
            raise RestoreRecoveryError("A recovery file is not a regular file.")
        if metadata.st_size > max_bytes:
            raise RestoreLimitError("A recovery file exceeds its byte limit.")
        with path.open("rb") as stream:
            digest = _hash_stream_bounded(stream, max_bytes, "recovery file")
        return FileIdentity(metadata.st_size, digest)
    except RestoreError:
        raise
    except OSError as exc:
        raise RestoreRecoveryError("A recovery file is unavailable.") from exc


def _hash_stream_bounded(stream, max_bytes: int, label: str) -> str:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(_CHUNK_BYTES):
        size += len(chunk)
        if size > max_bytes:
            if label == "restore archive":
                raise RestoreLimitError("The restore archive exceeds the size limit.")
            raise RestoreRecoveryError("A recovery file exceeds its byte limit.")
        digest.update(chunk)
    return digest.hexdigest()


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return (value.st_size, value.st_mtime_ns, value.st_dev, value.st_ino)


def _fsync_existing_file(path: Path) -> None:
    try:
        # Windows requires a writable handle for ``FlushFileBuffers``, which is
        # the operation used by ``os.fsync`` there.
        with path.open("r+b") as stream:
            os.fsync(stream.fileno())
    except OSError as exc:
        raise RestoreRecoveryError("Durable recovery state could not be flushed.") from exc


def _remove_journal(path: Path) -> None:
    try:
        path.unlink()
    except OSError as exc:
        raise RestoreRecoveryError("The completed restore journal could not be removed.") from exc
