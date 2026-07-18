from __future__ import annotations

from pathlib import Path
import argparse
import os
import sys
import zlib

from .launcher import run
from .diagnostics import configure_logging
from .single_instance import notify_existing_instance


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def project_port(root: Path) -> int:
    return 49152 + (zlib.crc32(str(root).encode("utf-8")) % 10000)


def integration_request(arguments: list[str]) -> dict[str, str]:
    parser = argparse.ArgumentParser(description="Show Context Palette from a Windows integration.")
    parser.add_argument(
        "--search",
        default=os.environ.get("CONTEXT_PALETTE_SEARCH", ""),
        help="Initial safe search text.",
    )
    parser.add_argument(
        "--context",
        default=os.environ.get("CONTEXT_PALETTE_CONTEXT", ""),
        help="Initial focus context name.",
    )
    options = parser.parse_args(arguments)
    request = {"command": "show"}
    if options.search.strip():
        request["search"] = options.search.strip()
    if options.context.strip():
        request["context"] = options.context.strip()
    return request


def initial_launcher_request(request: dict[str, str]) -> dict[str, str] | None:
    """Keep a bare first-launch workspace empty.

    The first process already owns a visible root window. Replaying a plain
    ``show`` request would synchronize stale clipboard text into the workspace.
    """
    return request if request.get("search") or request.get("context") else None


def main(arguments: list[str] | None = None) -> None:
    root = project_root()
    os.environ.setdefault("PROJECT_ROOT", str(root))
    configure_logging(root / "data" / "context-palette.log")
    port = project_port(root)
    request = integration_request(sys.argv[1:] if arguments is None else arguments)
    if notify_existing_instance(port, request):
        return

    run(
        root / "data" / "actions.json",
        root / "data" / "local_actions.json",
        root / "data" / "contexts.json",
        root / "data" / "local_contexts.json",
        root / "data" / "command_surface.json",
        root / "data" / "local_command_surface.json",
        root / "data" / "palette.json",
        root / "data" / "inbox.json",
        root / "data" / "cheatsheets",
        port,
        initial_launcher_request(request),
    )


if __name__ == "__main__":
    main()
