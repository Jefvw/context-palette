from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import threading
from typing import Callable, Literal
from uuid import uuid4


MAX_TRANSFER_FILES = 100
_COPY_CHUNK_SIZE = 1024 * 1024

FileDisposition = Literal["create", "replace", "skip_same"]


class FileTransferError(RuntimeError):
    """Files cannot be transferred without an explicit, safe result."""


class FileTransferStaleError(FileTransferError):
    """The reviewed transfer no longer describes current filesystem state."""


class FileTransferUnexpectedError(FileTransferError):
    """The worker stopped without a trustworthy effect report."""


@dataclass(frozen=True, slots=True)
class FileSnapshot:
    size: int
    mtime_ns: int
    device: int
    inode: int
    sha256: str


@dataclass(frozen=True, slots=True)
class PlannedFileCopy:
    source_path: Path
    destination_path: Path
    disposition: FileDisposition
    source_snapshot: FileSnapshot
    destination_snapshot: FileSnapshot | None
    renamed: bool
    original_conflict: bool


@dataclass(frozen=True, slots=True)
class FileTransferPlan:
    destination_folder: Path
    allow_overwrite: bool
    items: tuple[PlannedFileCopy, ...]
    fingerprint: str

    @property
    def create_count(self) -> int:
        return sum(item.disposition == "create" for item in self.items)

    @property
    def replace_count(self) -> int:
        return sum(item.disposition == "replace" for item in self.items)

    @property
    def renamed_count(self) -> int:
        return sum(item.renamed for item in self.items)

    @property
    def skipped_count(self) -> int:
        return sum(item.disposition == "skip_same" for item in self.items)

    @property
    def bytes_total(self) -> int:
        return sum(
            item.source_snapshot.size
            for item in self.items
            if item.disposition != "skip_same"
        )

    @property
    def requires_review(self) -> bool:
        return any(
            item.original_conflict
            or item.renamed
            or item.disposition in {"replace", "skip_same"}
            for item in self.items
        )


@dataclass(frozen=True, slots=True)
class FileTransferFailure:
    source_path: Path
    destination_path: Path | None
    message: str


@dataclass(frozen=True, slots=True)
class FileTransferResult:
    destination_folder: Path
    created: tuple[Path, ...]
    replaced: tuple[Path, ...]
    skipped: tuple[Path, ...]
    failures: tuple[FileTransferFailure, ...]
    bytes_copied: int
    stopped: bool = False


def parse_workspace_file_paths(
    value: str,
    *,
    max_files: int = MAX_TRANSFER_FILES,
) -> tuple[Path, ...]:
    """Parse one existing absolute file path per nonblank workspace line."""
    raw_lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not raw_lines:
        raise FileTransferError("Input / Output does not contain any file paths.")
    if len(raw_lines) > max_files:
        raise FileTransferError(
            f"Input / Output can send at most {max_files} files at once."
        )

    sources: list[Path] = []
    seen: set[str] = set()
    for raw_line in raw_lines:
        raw_path = _strip_matching_quotes(raw_line)
        source = Path(raw_path)
        if not source.is_absolute():
            raise FileTransferError(
                "Each Input / Output line must be one absolute file path."
            )
        if not source.is_file():
            if source.is_dir():
                raise FileTransferError(
                    "Input / Output contains a folder; Send to accepts files only."
                )
            raise FileTransferError(
                "An Input / Output file does not exist or is unavailable."
            )
        try:
            resolved = source.resolve(strict=True)
        except OSError as exc:
            raise FileTransferError(
                "An Input / Output file does not exist or is unavailable."
            ) from exc
        key = _path_key(resolved)
        if key in seen:
            raise FileTransferError(
                "Input / Output contains the same file path more than once."
            )
        seen.add(key)
        sources.append(resolved)
    return tuple(sources)


def plan_file_transfer(
    workspace_text: str,
    destination_folder: Path,
    *,
    allow_overwrite: bool = False,
) -> FileTransferPlan:
    """Read filesystem state and return a deterministic, effect-free copy plan."""
    sources = parse_workspace_file_paths(workspace_text)
    folder = _validated_destination_folder(destination_folder)
    used_destinations: set[str] = set()
    items: list[PlannedFileCopy] = []

    for source in sources:
        source_snapshot = _snapshot_file(
            source,
            unavailable_message="An Input / Output file changed or became unavailable.",
        )
        requested = folder / source.name
        requested_key = _path_key(requested)

        if _same_path(source, requested):
            items.append(
                PlannedFileCopy(
                    source,
                    requested,
                    "skip_same",
                    source_snapshot,
                    source_snapshot,
                    False,
                    True,
                )
            )
            used_destinations.add(requested_key)
            continue

        requested_exists = requested.exists()
        requested_used = requested_key in used_destinations
        original_conflict = requested_exists or requested_used

        if allow_overwrite and requested_exists and not requested_used:
            if not requested.is_file():
                raise FileTransferError(
                    "A destination name is occupied by something other than a file."
                )
            destination = requested
            disposition: FileDisposition = "replace"
            destination_snapshot = _snapshot_file(
                destination,
                unavailable_message="A destination file changed or became unavailable.",
            )
        elif requested_exists or requested_used:
            destination = _next_available_destination(requested, used_destinations)
            disposition = "create"
            destination_snapshot = None
        else:
            destination = requested
            disposition = "create"
            destination_snapshot = None

        used_destinations.add(_path_key(destination))
        items.append(
            PlannedFileCopy(
                source,
                destination,
                disposition,
                source_snapshot,
                destination_snapshot,
                destination.name != source.name,
                original_conflict,
            )
        )

    fingerprint = _plan_fingerprint(folder, allow_overwrite, items)
    return FileTransferPlan(folder, allow_overwrite, tuple(items), fingerprint)


def execute_file_transfer_plan(
    plan: FileTransferPlan,
    *,
    stop_requested: Callable[[], bool] | None = None,
) -> FileTransferResult:
    """Revalidate, stage complete files, and publish the reviewed plan."""
    should_stop = stop_requested or (lambda: False)
    current = plan_file_transfer(
        "\n".join(str(item.source_path) for item in plan.items),
        plan.destination_folder,
        allow_overwrite=plan.allow_overwrite,
    )
    if current.fingerprint != plan.fingerprint:
        raise FileTransferStaleError(
            "The files or destination changed after review. Review Send to again."
        )

    skipped = tuple(
        item.destination_path
        for item in current.items
        if item.disposition == "skip_same"
    )
    staged: list[tuple[PlannedFileCopy, Path]] = []
    try:
        for item in current.items:
            if item.disposition == "skip_same":
                continue
            if should_stop():
                _cleanup_staged(staged)
                return FileTransferResult(
                    current.destination_folder,
                    (),
                    (),
                    skipped,
                    (),
                    0,
                    True,
                )
            temporary = _temporary_path(current.destination_folder)
            try:
                _stage_copy(item, temporary)
            except FileTransferError:
                _remove_temporary(temporary)
                raise
            except OSError as exc:
                _remove_temporary(temporary)
                raise FileTransferError(
                    "A file could not be copied into the destination folder."
                ) from exc
            staged.append((item, temporary))

        if should_stop():
            _cleanup_staged(staged)
            return FileTransferResult(
                current.destination_folder,
                (),
                (),
                skipped,
                (),
                0,
                True,
            )
        _revalidate_destinations(current.items)

        created: list[Path] = []
        replaced: list[Path] = []
        failures: list[FileTransferFailure] = []
        bytes_copied = 0
        for index, (item, temporary) in enumerate(staged):
            if should_stop():
                _cleanup_staged(staged[index:])
                return FileTransferResult(
                    current.destination_folder,
                    tuple(created),
                    tuple(replaced),
                    skipped,
                    tuple(failures),
                    bytes_copied,
                    True,
                )
            try:
                _revalidate_destination(item)
                _publish_item(item, temporary)
            except (FileTransferError, OSError):
                _remove_temporary(temporary)
                failures.append(
                    FileTransferFailure(
                        item.source_path,
                        item.destination_path,
                        "The reviewed destination changed or could not be updated.",
                    )
                )
                for pending_item, pending_temporary in staged[index + 1 :]:
                    _remove_temporary(pending_temporary)
                    failures.append(
                        FileTransferFailure(
                            pending_item.source_path,
                            pending_item.destination_path,
                            "Not copied because an earlier destination failed.",
                        )
                    )
                return FileTransferResult(
                    current.destination_folder,
                    tuple(created),
                    tuple(replaced),
                    skipped,
                    tuple(failures),
                    bytes_copied,
                )

            bytes_copied += item.source_snapshot.size
            if item.disposition == "replace":
                replaced.append(item.destination_path)
            else:
                created.append(item.destination_path)

        return FileTransferResult(
            current.destination_folder,
            tuple(created),
            tuple(replaced),
            skipped,
            tuple(failures),
            bytes_copied,
        )
    except Exception:
        _cleanup_staged(staged)
        raise


PlanCallback = Callable[[FileTransferPlan | None, FileTransferError | None], None]
ExecutionCallback = Callable[
    [FileTransferResult | None, FileTransferError | None],
    None,
]


class FileTransferCoordinator:
    """Run one planning or copy operation off-thread and drain it on Tk's thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._phase: str | None = None
        self._stop = threading.Event()
        self._completed: queue.SimpleQueue[
            tuple[object | None, FileTransferError | None, Callable[..., None]]
        ] = queue.SimpleQueue()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def phase(self) -> str | None:
        with self._lock:
            return self._phase

    def start_plan(
        self,
        workspace_text: str,
        destination_folder: Path,
        allow_overwrite: bool,
        on_complete: PlanCallback,
    ) -> bool:
        return self._start(
            "planning",
            lambda: plan_file_transfer(
                workspace_text,
                destination_folder,
                allow_overwrite=allow_overwrite,
            ),
            on_complete,
        )

    def start_execute(
        self,
        plan: FileTransferPlan,
        on_complete: ExecutionCallback,
    ) -> bool:
        return self._start(
            "copying",
            lambda: execute_file_transfer_plan(
                plan,
                stop_requested=self._stop.is_set,
            ),
            on_complete,
        )

    def request_stop(self) -> None:
        if self.running:
            self._stop.set()

    def drain(self) -> bool:
        try:
            result, error, on_complete = self._completed.get_nowait()
        except queue.Empty:
            return False
        with self._lock:
            self._running = False
            self._phase = None
        on_complete(result, error)
        return True

    def _start(
        self,
        phase: str,
        operation: Callable[[], object],
        on_complete: Callable[..., None],
    ) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._phase = phase
            self._stop.clear()

        def work() -> None:
            result: object | None = None
            error: FileTransferError | None = None
            try:
                result = operation()
            except FileTransferError as exc:
                error = exc
            except Exception:
                error = FileTransferUnexpectedError(
                    "Send to stopped because of an unexpected local error."
                )
            self._completed.put((result, error, on_complete))

        threading.Thread(
            target=work,
            daemon=True,
            name=f"file-transfer-{phase}",
        ).start()
        return True


def _strip_matching_quotes(value: str) -> str:
    starts_quote = value.startswith(('"', "'"))
    ends_quote = value.endswith(('"', "'"))
    if starts_quote or ends_quote:
        if len(value) < 2 or value[0] != value[-1] or value[0] not in {'"', "'"}:
            raise FileTransferError(
                "A file path has unmatched quotation marks."
            )
        value = value[1:-1].strip()
    if not value:
        raise FileTransferError("Input / Output contains an empty file path.")
    return value


def _validated_destination_folder(value: Path) -> Path:
    folder = Path(value)
    if not folder.is_absolute():
        raise FileTransferError("The Send to destination must be an absolute folder.")
    if not folder.is_dir():
        raise FileTransferError("The Send to destination folder is unavailable.")
    try:
        return folder.resolve(strict=True)
    except OSError as exc:
        raise FileTransferError(
            "The Send to destination folder is unavailable."
        ) from exc


def _snapshot_file(path: Path, *, unavailable_message: str) -> FileSnapshot:
    try:
        before = path.stat()
        if not path.is_file():
            raise OSError("not a regular file")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(_COPY_CHUNK_SIZE), b""):
                digest.update(chunk)
        after = path.stat()
    except OSError as exc:
        raise FileTransferError(unavailable_message) from exc
    before_identity = _stat_identity(before)
    if before_identity != _stat_identity(after):
        raise FileTransferError(unavailable_message)
    return FileSnapshot(*before_identity, digest.hexdigest())


def _stat_identity(stat_result: os.stat_result) -> tuple[int, int, int, int]:
    return (
        stat_result.st_size,
        stat_result.st_mtime_ns,
        stat_result.st_dev,
        stat_result.st_ino,
    )


def _next_available_destination(requested: Path, used: set[str]) -> Path:
    stem = requested.stem
    suffix = requested.suffix
    index = 1
    while True:
        candidate = requested.with_name(f"{stem}({index}){suffix}")
        if _path_key(candidate) not in used and not candidate.exists():
            return candidate
        index += 1


def _plan_fingerprint(
    folder: Path,
    allow_overwrite: bool,
    items: list[PlannedFileCopy],
) -> str:
    payload = {
        "allow_overwrite": allow_overwrite,
        "destination_folder": str(folder),
        "items": [
            {
                "source_path": str(item.source_path),
                "destination_path": str(item.destination_path),
                "disposition": item.disposition,
                "source_snapshot": _snapshot_payload(item.source_snapshot),
                "destination_snapshot": (
                    _snapshot_payload(item.destination_snapshot)
                    if item.destination_snapshot is not None
                    else None
                ),
                "renamed": item.renamed,
                "original_conflict": item.original_conflict,
            }
            for item in items
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _snapshot_payload(snapshot: FileSnapshot) -> dict[str, int | str]:
    return {
        "size": snapshot.size,
        "mtime_ns": snapshot.mtime_ns,
        "device": snapshot.device,
        "inode": snapshot.inode,
        "sha256": snapshot.sha256,
    }


def _temporary_path(folder: Path) -> Path:
    return folder / f".context-palette-{uuid4().hex}.tmp"


def _stage_copy(item: PlannedFileCopy, temporary: Path) -> None:
    try:
        before = item.source_path.stat()
    except OSError as exc:
        raise FileTransferStaleError(
            "A source file changed after review. Review Send to again."
        ) from exc
    if _stat_identity(before) != (
        item.source_snapshot.size,
        item.source_snapshot.mtime_ns,
        item.source_snapshot.device,
        item.source_snapshot.inode,
    ):
        raise FileTransferStaleError(
            "A source file changed after review. Review Send to again."
        )

    digest = hashlib.sha256()
    try:
        with item.source_path.open("rb") as source_stream:
            with temporary.open("xb") as destination_stream:
                while True:
                    chunk = source_stream.read(_COPY_CHUNK_SIZE)
                    if not chunk:
                        break
                    destination_stream.write(chunk)
                    digest.update(chunk)
        after = item.source_path.stat()
    except OSError as exc:
        raise FileTransferError(
            "A file could not be copied into the destination folder."
        ) from exc
    if (
        _stat_identity(after) != _stat_identity(before)
        or digest.hexdigest() != item.source_snapshot.sha256
    ):
        raise FileTransferStaleError(
            "A source file changed while it was being copied; nothing was published."
        )
    try:
        shutil.copystat(item.source_path, temporary)
    except OSError:
        # Some Windows filesystems do not support every metadata field.
        pass


def _revalidate_destinations(items: tuple[PlannedFileCopy, ...]) -> None:
    for item in items:
        if item.disposition != "skip_same":
            _revalidate_destination(item)


def _revalidate_destination(item: PlannedFileCopy) -> None:
    if item.disposition == "create":
        if item.destination_path.exists():
            raise FileTransferStaleError(
                "A destination changed after review. Review Send to again."
            )
        return
    if item.disposition == "replace":
        if item.destination_snapshot is None:
            raise FileTransferStaleError(
                "The reviewed replacement is incomplete. Review Send to again."
            )
        current = _snapshot_file(
            item.destination_path,
            unavailable_message=(
                "A destination changed after review. Review Send to again."
            ),
        )
        if current != item.destination_snapshot:
            raise FileTransferStaleError(
                "A destination changed after review. Review Send to again."
            )


def _publish_item(item: PlannedFileCopy, temporary: Path) -> None:
    if item.disposition == "replace":
        os.replace(temporary, item.destination_path)
    else:
        # On the target Windows platform os.rename refuses to replace an existing
        # destination, so a create cannot silently become an overwrite.
        os.rename(temporary, item.destination_path)


def _cleanup_staged(staged: list[tuple[PlannedFileCopy, Path]]) -> None:
    for _item, temporary in staged:
        _remove_temporary(temporary)


def _remove_temporary(temporary: Path) -> None:
    try:
        temporary.unlink(missing_ok=True)
    except OSError:
        pass


def _path_key(path: Path) -> str:
    # Context Palette targets Windows: paths and collision names compare without
    # case, including when a test host happens to use a case-sensitive filesystem.
    return str(path.resolve(strict=False)).replace("/", "\\").casefold()


def _same_path(first: Path, second: Path) -> bool:
    return _path_key(first) == _path_key(second)
