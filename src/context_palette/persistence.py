from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile

from .configuration_mutation import configuration_mutation_gate


def atomic_write_json(
    path: Path,
    data: object,
    *,
    preserve_previous: bool = True,
) -> None:
    """Atomically write JSON, optionally preserving the previous file as .bak."""
    with configuration_mutation_gate():
        _atomic_write_json_unlocked(
            path,
            data,
            preserve_previous=preserve_previous,
        )


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
        _atomic_replace_bytes_unlocked(
            Path(path),
            payload,
            preserve_previous=preserve_previous,
        )


def _atomic_replace_bytes_unlocked(
    path: Path,
    payload: bytes,
    *,
    preserve_previous: bool,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())

        if preserve_previous and path.exists():
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _atomic_write_json_unlocked(
    path: Path,
    data: object,
    *,
    preserve_previous: bool,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(data, temporary, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())

        if preserve_previous and path.exists():
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
