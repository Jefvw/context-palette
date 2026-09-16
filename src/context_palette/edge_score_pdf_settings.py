"""Machine-local destination setting for Edge score PDF exports."""

from __future__ import annotations

import json
from pathlib import Path

from .persistence import atomic_write_json


class EdgeScorePdfSettingsError(ValueError):
    """The private Edge score PDF destination setting is invalid."""


def load_edge_score_pdf_folder(path: Path) -> Path | None:
    """Load one optional absolute destination folder without probing it."""

    settings_path = Path(path)
    if not settings_path.exists():
        return None
    try:
        document = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        raise EdgeScorePdfSettingsError(
            "Edge score PDF settings could not be read."
        ) from exc
    if not isinstance(document, dict) or set(document) != {"destination_folder"}:
        raise EdgeScorePdfSettingsError(
            "Edge score PDF settings must contain destination_folder text only."
        )
    value = document["destination_folder"]
    if not isinstance(value, str):
        raise EdgeScorePdfSettingsError(
            "Edge score PDF destination_folder must be text."
        )
    if not value:
        return None
    folder = Path(value)
    _validate_folder(folder)
    return folder


def save_edge_score_pdf_folder(path: Path, folder: Path | None) -> None:
    """Atomically save an optional absolute destination folder."""

    if folder is not None:
        folder = Path(folder)
        _validate_folder(folder)
    atomic_write_json(
        Path(path),
        {"destination_folder": str(folder) if folder is not None else ""},
    )


def _validate_folder(folder: Path) -> None:
    value = str(folder)
    if not value or "\x00" in value or not folder.is_absolute():
        raise EdgeScorePdfSettingsError(
            "The Edge score PDF destination folder must be an absolute path."
        )
