from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import queue
import shutil
import threading
from typing import Callable
from uuid import uuid4


class WorkItemFileCopyError(RuntimeError):
    """A file cannot be copied into a Work Item without risking existing data."""


@dataclass(frozen=True, slots=True)
class WorkItemFileCopyResult:
    source_path: Path
    destination_path: Path
    size: int


def file_path_from_workspace(value: str) -> Path:
    raw_path = value.strip()
    if (
        len(raw_path) >= 2
        and raw_path[0] == raw_path[-1]
        and raw_path[0] in {'"', "'"}
    ):
        raw_path = raw_path[1:-1].strip()
    if not raw_path:
        raise WorkItemFileCopyError("Input / Output does not contain a file path.")
    if "\n" in raw_path or "\r" in raw_path:
        raise WorkItemFileCopyError(
            "Input / Output must contain one exact file path, without other text."
        )
    source = Path(raw_path)
    if not source.is_absolute():
        raise WorkItemFileCopyError("The source file path must be absolute.")
    if not source.is_file():
        if source.is_dir():
            raise WorkItemFileCopyError("The source path is a folder, not a file.")
        raise WorkItemFileCopyError("The source file does not exist or is unavailable.")
    return source


def copy_file_to_work_item(
    source_path: Path,
    work_item_folder: Path,
) -> WorkItemFileCopyResult:
    source = Path(source_path)
    folder = Path(work_item_folder)
    if not source.is_absolute() or not source.is_file():
        raise WorkItemFileCopyError("The source file does not exist or is unavailable.")
    if not folder.is_absolute() or not folder.is_dir():
        raise WorkItemFileCopyError("The selected Work Item folder is unavailable.")
    destination = folder / source.name
    if _same_path(source, destination):
        raise WorkItemFileCopyError("The source file is already in this Work Item folder.")

    if destination.exists():
        raise WorkItemFileCopyError(
            f'A file named "{source.name}" already exists in this Work Item; '
            "nothing was overwritten."
        )
    temporary = folder / (
        f".{source.name}.{uuid4().hex}.context-palette-copy"
    )
    try:
        with source.open("rb") as source_file:
            with temporary.open("xb") as destination_file:
                shutil.copyfileobj(
                    source_file,
                    destination_file,
                    length=1024 * 1024,
                )
        try:
            shutil.copystat(source, temporary)
        except OSError:
            # Some filesystems do not support all Windows metadata.
            pass
        temporary.rename(destination)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        if destination.exists():
            raise WorkItemFileCopyError(
                f'A file named "{source.name}" already exists in this Work Item; '
                "nothing was overwritten."
            ) from exc
        raise WorkItemFileCopyError(
            "The file could not be copied into the selected Work Item."
        ) from exc

    try:
        size = destination.stat().st_size
    except OSError:
        size = 0
    return WorkItemFileCopyResult(source, destination, size)


class WorkItemFileCopyCoordinator:
    """Copy off-thread and deliver one completion through main-thread polling."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._completed: queue.SimpleQueue[
            tuple[
                WorkItemFileCopyResult | None,
                WorkItemFileCopyError | None,
                Callable[
                    [WorkItemFileCopyResult | None, WorkItemFileCopyError | None],
                    None,
                ],
            ]
        ] = queue.SimpleQueue()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def start(
        self,
        source_path: Path,
        work_item_folder: Path,
        on_complete: Callable[
            [WorkItemFileCopyResult | None, WorkItemFileCopyError | None],
            None,
        ],
    ) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True

        def work() -> None:
            result: WorkItemFileCopyResult | None = None
            error: WorkItemFileCopyError | None = None
            try:
                result = copy_file_to_work_item(source_path, work_item_folder)
            except WorkItemFileCopyError as exc:
                error = exc
            except Exception:
                error = WorkItemFileCopyError(
                    "The file copy stopped because of an unexpected local error."
                )
            self._completed.put((result, error, on_complete))

        threading.Thread(
            target=work,
            daemon=True,
            name="work-item-file-copy",
        ).start()
        return True

    def drain(self) -> bool:
        try:
            result, error, on_complete = self._completed.get_nowait()
        except queue.Empty:
            return False
        try:
            on_complete(result, error)
        finally:
            with self._lock:
                self._running = False
        return True


def _same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(str(first.resolve(strict=False))) == os.path.normcase(
        str(second.resolve(strict=False))
    )
