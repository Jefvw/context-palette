from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile


def atomic_write_json(path: Path, data: object) -> None:
    """Write JSON through a flushed sibling file, preserving the previous file as .bak."""
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

        if path.exists():
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
