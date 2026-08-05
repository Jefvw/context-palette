from __future__ import annotations

from pathlib import Path
import argparse
import os
import sys
import zlib

from .data_catalog import AppDataPaths
from .launcher import run
from .diagnostics import configure_logging
from .retired_feature_cleanup import (
    RetirementCleanupError,
    cleanup_retired_local_configuration,
)
from .restore import RestoreRecoveryError, recover_interrupted_restore
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
    paths = AppDataPaths.from_root(root)
    os.environ.setdefault("PROJECT_ROOT", str(root))
    logger = configure_logging(paths.diagnostic_log_file)
    port = project_port(root)
    request = integration_request(sys.argv[1:] if arguments is None else arguments)
    if notify_existing_instance(port, request):
        return
    try:
        recovery = recover_interrupted_restore(paths)
        if recovery.recovery_performed:
            logger.warning(
                "Completed rollback for an interrupted configuration restore"
            )
    except RestoreRecoveryError:
        logger.exception("Interrupted configuration restore recovery failed")
        raise SystemExit(
            "Context Palette could not safely recover an interrupted restore."
        )
    try:
        cleanup_report = cleanup_retired_local_configuration(root)
        if cleanup_report.files_changed:
            logger.info(
                "Updated retired local configuration: "
                "removed_actions=%d migrated_actions=%d references=%d files=%d",
                cleanup_report.actions_removed,
                cleanup_report.actions_migrated,
                cleanup_report.references_removed,
                cleanup_report.files_changed,
            )
    except RetirementCleanupError:
        logger.exception("Retired local configuration could not be cleaned")
    run(
        paths.built_in_actions_file,
        paths.personal_actions_file,
        paths.built_in_contexts_file,
        paths.personal_contexts_file,
        paths.built_in_command_surface_file,
        paths.personal_command_surface_file,
        paths.palette_state_file,
        paths.inbox_file,
        paths.cheat_sheets_directory,
        port,
        initial_launcher_request(request),
        data_paths=paths,
    )


if __name__ == "__main__":
    main()
