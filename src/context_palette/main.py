from __future__ import annotations

from pathlib import Path
import os
import zlib

from .launcher import run
from .single_instance import notify_existing_instance


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def project_port(root: Path) -> int:
    return 49152 + (zlib.crc32(str(root).encode("utf-8")) % 10000)


def main() -> None:
    root = project_root()
    os.environ.setdefault("PROJECT_ROOT", str(root))
    port = project_port(root)
    if notify_existing_instance(port):
        return

    run(
        root / "data" / "actions.json",
        root / "data" / "local_actions.json",
        root / "data" / "palette.json",
        root / "data" / "inbox.json",
        root / "data" / "cheatsheets",
        port,
    )


if __name__ == "__main__":
    main()
