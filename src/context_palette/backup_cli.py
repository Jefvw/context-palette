from __future__ import annotations

import argparse
from pathlib import Path
import sys
from collections.abc import Sequence

from .backup import BackupError, BackupOptions, create_configuration_backup
from .data_catalog import AppDataPaths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a validated Context Palette configuration backup."
    )
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Context Palette application root (defaults to this checkout).",
    )
    parser.add_argument(
        "--exclude-inbox",
        action="store_true",
        help="Exclude captured Inbox content.",
    )
    parser.add_argument(
        "--include-managed-content",
        action="store_true",
        help="Include the optional managed local text source.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Explicitly replace an existing destination archive.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    options = BackupOptions(
        include_inbox=not arguments.exclude_inbox,
        include_managed_content=arguments.include_managed_content,
        overwrite=arguments.overwrite,
    )
    try:
        result = create_configuration_backup(
            AppDataPaths.from_root(arguments.root),
            arguments.destination,
            options=options,
        )
    except (BackupError, OSError, ValueError) as exc:
        print(f"ERROR: Backup was not created: {exc}", file=sys.stderr)
        return 1

    inbox_scope = "included" if options.include_inbox else "excluded"
    managed_scope = (
        "included" if options.include_managed_content else "excluded"
    )
    print("Context Palette backup created successfully.")
    print(
        "Privacy scope: complete configuration; "
        f"Inbox {inbox_scope}; managed text {managed_scope}."
    )
    print(f"Included files: {len(result.included_files)}")
    print(
        "Always excluded: diagnostics/runtime artifacts, unknown files, "
        "external resources, templates, and credential secrets."
    )
    if result.snapshot_warnings:
        print(f"Validation warnings: {len(result.snapshot_warnings)}")
        for warning in result.snapshot_warnings:
            print(f"- {warning.summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
