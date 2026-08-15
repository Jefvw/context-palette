from __future__ import annotations

from dataclasses import dataclass
from pathlib import PureWindowsPath
import re
from urllib.parse import unquote, urlparse

from .actions import ActionError, validate_http_url


EXECUTABLE_FILE_SUFFIXES = frozenset(
    {
        ".appref-ms", ".bat", ".cmd", ".com", ".cpl", ".js", ".jse",
        ".lnk", ".msi", ".msp", ".ps1", ".reg", ".scr", ".url",
        ".vbs", ".wsf", ".wsh",
    }
)


@dataclass(frozen=True)
class ActionCreationSuggestion:
    """One high-confidence Action prefill derived from Working text."""

    action_type: str
    title: str
    value: str


def suggest_action_from_text(value: str) -> ActionCreationSuggestion | None:
    """Return one obvious reviewed Action prefill, without executing anything."""

    candidate = _single_candidate(value)
    if candidate is None:
        return None

    try:
        validate_http_url(candidate, label="Working-text URL")
    except ActionError:
        pass
    else:
        if not any(character.isspace() for character in candidate):
            hostname = urlparse(candidate).hostname
            if hostname:
                return ActionCreationSuggestion(
                    "open_url",
                    f"Open {hostname}",
                    candidate,
                )

    local_value = _absolute_local_path(candidate)
    if local_value is None:
        return None
    path = PureWindowsPath(local_value)
    suffix = path.suffix.casefold()
    name = path.name or path.drive or str(path)
    if suffix == ".exe":
        return ActionCreationSuggestion(
            "launch_app",
            f"Launch {path.stem or name}",
            str(path),
        )
    if suffix in EXECUTABLE_FILE_SUFFIXES:
        return None
    if suffix:
        return ActionCreationSuggestion(
            "open_file",
            f"Open {name}",
            str(path),
        )
    return ActionCreationSuggestion(
        "open_folder",
        f"Open {name}",
        str(path),
    )


def _single_candidate(value: str) -> str | None:
    candidate = value.strip()
    if (
        len(candidate) >= 2
        and candidate[0] == candidate[-1]
        and candidate[0] in {'"', "'"}
    ):
        candidate = candidate[1:-1].strip()
    if (
        not candidate
        or "\x00" in candidate
        or "\r" in candidate
        or "\n" in candidate
        or '"' in candidate
        or "'" in candidate
    ):
        return None
    return candidate


def _absolute_local_path(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme.casefold() == "file":
        path = unquote(parsed.path)
        if parsed.netloc:
            return "\\\\" + parsed.netloc + path.replace("/", "\\")
        if re.match(r"^/[A-Za-z]:/", path):
            path = path[1:]
        return path.replace("/", "\\") if re.match(r"^[A-Za-z]:/", path) else None
    if re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith("\\\\"):
        return value
    return None
