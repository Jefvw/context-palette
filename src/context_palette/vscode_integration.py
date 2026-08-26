"""Constrained Input / Output handoff to the registered VS Code protocol."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable
from urllib.parse import quote


_MAX_INPUT_CHARACTERS = 32_767


class VsCodeIntegrationError(RuntimeError):
    """A workspace path cannot be opened safely in VS Code."""


def vscode_folder_from_workspace(value: str) -> Path:
    """Resolve one exact folder, or the parent folder of one exact file."""
    if len(value) > _MAX_INPUT_CHARACTERS:
        raise VsCodeIntegrationError("The Input / Output path is too long.")
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not lines:
        raise VsCodeIntegrationError(
            "Input / Output does not contain a folder or file path."
        )
    if len(lines) != 1:
        raise VsCodeIntegrationError(
            "Open in VS Code accepts exactly one folder or file path."
        )

    text = _strip_matching_quotes(lines[0])
    path = Path(text)
    if not path.is_absolute():
        raise VsCodeIntegrationError(
            "Open in VS Code requires one absolute folder or file path."
        )
    try:
        resolved = path.resolve(strict=True)
    except (OSError, ValueError, RuntimeError) as exc:
        raise VsCodeIntegrationError(
            "The folder or file does not exist or is unavailable."
        ) from exc
    if resolved.is_dir():
        return resolved
    if resolved.is_file():
        return resolved.parent
    raise VsCodeIntegrationError(
        "The Input / Output path is not a regular file or folder."
    )


def vscode_folder_uri(folder: Path) -> str:
    """Build a registered VS Code folder URI without interpreting commands."""
    normalized = folder.as_posix().rstrip("/")
    encoded = quote(normalized, safe="/:")
    if normalized.startswith("//"):
        return f"vscode://file{encoded}/"
    return f"vscode://file/{encoded}/"


def open_workspace_path_in_vscode(
    value: str,
    *,
    opener: Callable[[str], None] | None = None,
) -> Path:
    """Open one resolved workspace folder through Windows' vscode: handler."""
    folder = vscode_folder_from_workspace(value)
    open_uri = opener or _open_uri
    try:
        open_uri(vscode_folder_uri(folder))
    except OSError as exc:
        raise VsCodeIntegrationError(
            "Windows could not open VS Code. Check that VS Code is installed "
            "and registered for vscode: links."
        ) from exc
    return folder


def _strip_matching_quotes(value: str) -> str:
    starts_quote = value.startswith(('"', "'"))
    ends_quote = value.endswith(('"', "'"))
    if starts_quote or ends_quote:
        if len(value) < 2 or value[0] != value[-1] or value[0] not in {'"', "'"}:
            raise VsCodeIntegrationError(
                "The Input / Output path has unmatched quotation marks."
            )
        value = value[1:-1].strip()
    if not value:
        raise VsCodeIntegrationError(
            "Input / Output does not contain a folder or file path."
        )
    return value


def _open_uri(value: str) -> None:
    os.startfile(value, "open")  # type: ignore[attr-defined]
