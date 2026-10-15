from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import IO

from .configuration_mutation import configuration_mutation_gate


def atomic_write_json(
    path: Path,
    data: object,
    *,
    preserve_previous: bool = True,
) -> None:
    """Atomically write JSON, optionally preserving the previous file as .bak."""
    with configuration_mutation_gate():
        with _atomic_output_unlocked(
            path, preserve_previous=preserve_previous, binary=False,
        ) as temporary:
            json.dump(data, temporary, indent=2)
            temporary.write("\n")


def atomic_replace_bytes(
    path: Path,
    payload: bytes,
    *,
    preserve_previous: bool = False,
) -> None:
    """Atomically replace one file with exact bytes under the mutation gate."""

    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    with configuration_mutation_gate():
        with _atomic_output_unlocked(
            Path(path), preserve_previous=preserve_previous, binary=True,
        ) as temporary:
            temporary.write(payload)


@contextmanager
def _atomic_output_unlocked(
    path: Path,
    *,
    preserve_previous: bool,
    binary: bool,
) -> Iterator[IO]:
    """Publish the streamed sibling only after writing, syncing and closing it.

    The public writer owns the mutation gate and serialization. Failures during
    writing, syncing, backup or replacement leave the original untouched and
    remove the temporary file; a failed backup copy may itself be partial.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b" if binary else "w",
            encoding=None if binary else "utf-8",
            newline=None if binary else "\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            yield temporary
            temporary.flush()
            os.fsync(temporary.fileno())

        if preserve_previous and path.exists():
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
