"""Bounded, side-effect-free preparation of TkDND drops.

This module deliberately contains no Tk widgets or application integration.
The only platform reads it performs are the narrowly scoped shortcut lookups
needed to turn a dropped shortcut into a candidate; it never executes a target.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import queue
import subprocess
import threading
from typing import Callable, Literal

from .drop_extraction import (
    DropExtractionError,
    DropItem,
    extract_drop_values,
    parse_internet_shortcut_url,
)


DropType = Literal["DND_Files", "DND_Text"]
MAX_RAW_DROP_LENGTH = 256_000
MAX_SHORTCUT_BYTES = 16_384
SHORTCUT_TIMEOUT_SECONDS = 4.0
_POWERSHELL_SHORTCUT_COMMAND = (
    "$shell = New-Object -ComObject WScript.Shell; "
    "[Console]::Out.Write($shell.CreateShortcut($args[0]).TargetPath)"
)


@dataclass(frozen=True, slots=True)
class DropProblem:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class DropWarning:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class DropResult:
    """A completed, immutable drop result; errors have no items."""

    items: tuple[DropItem, ...] = ()
    warnings: tuple[DropWarning, ...] = ()
    error: DropProblem | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def decode_drop_values(
    event: object,
    drop_type: str,
) -> tuple[tuple[str, ...] | None, DropProblem | None]:
    """Decode a DnD event with its actual Tcl interpreter.

    ``DND_Text`` is intentionally a single native payload.  Only Tcl's own
    ``splitlist`` is permitted to interpret a ``DND_Files`` payload.
    """
    if drop_type not in {"DND_Files", "DND_Text"}:
        return None, DropProblem("unsupported_type", "This drop type is not supported.")
    raw = getattr(event, "data", None)
    if not isinstance(raw, str):
        return None, DropProblem("payload_type", "Dropped data was not text.")
    if len(raw) > MAX_RAW_DROP_LENGTH:
        return None, DropProblem("payload_length", "Dropped data is too large.")
    if drop_type == "DND_Text":
        return (raw,), None
    widget = getattr(event, "widget", None)
    interpreter = getattr(widget, "tk", None)
    splitlist = getattr(interpreter, "splitlist", None)
    if not callable(splitlist):
        return None, DropProblem("tcl_unavailable", "File-drop decoding is unavailable.")
    try:
        values = tuple(splitlist(raw))
    except Exception:
        return None, DropProblem("tcl_decode", "The file drop could not be decoded safely.")
    return values, None


def decode_drop_event(event: object, drop_type: str) -> DropResult:
    """Synchronously decode and resolve an event for non-UI callers."""
    values, error = decode_drop_values(event, drop_type)
    return DropResult(error=error) if error is not None else resolve_decoded_values(values or ())


def resolve_decoded_values(
    values: tuple[str, ...] | list[str],
    *,
    read_bytes: Callable[[str, int], bytes] | None = None,
    run_process: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> DropResult:
    """Resolve decoded values synchronously, with deterministic fallbacks."""
    try:
        initial = extract_drop_values(values)
    except DropExtractionError as exc:
        return DropResult(error=DropProblem(exc.code, str(exc)))
    warnings: list[DropWarning] = []
    resolved: list[DropItem] = []
    reader = read_bytes or _read_bounded_bytes
    for item in initial:
        replacement = _resolve_shortcut(item, reader, run_process, warnings)
        resolved.extend(replacement)
    return DropResult(items=_dedupe(resolved), warnings=tuple(warnings))


def _resolve_shortcut(
    item: DropItem,
    read_bytes: Callable[[str, int], bytes],
    run_process: Callable[..., subprocess.CompletedProcess[str]],
    warnings: list[DropWarning],
) -> tuple[DropItem, ...]:
    if item.kind != "path":
        return (item,)
    suffix = Path(item.value).suffix.casefold()
    if suffix == ".url":
        try:
            target = _url_from_shortcut_bytes(
                read_bytes(item.value, MAX_SHORTCUT_BYTES + 1)
            )
        except (OSError, UnicodeError, DropExtractionError):
            target = None
        if target:
            return _normalize_target(target, item, warnings, "url_target")
        warnings.append(DropWarning("url_unresolved", "A web shortcut could not be read; its path was kept."))
        return (item,)
    if suffix == ".lnk":
        target = _read_lnk_target(item.value, run_process)
        if target:
            return _normalize_target(target, item, warnings, "lnk_target")
        warnings.append(DropWarning("lnk_unresolved", "A Windows shortcut could not be resolved; its path was kept."))
    return (item,)


def _read_bounded_bytes(path: str, maximum: int) -> bytes:
    with open(path, "rb") as source:
        return source.read(maximum)


def _url_from_shortcut_bytes(data: bytes) -> str | None:
    if len(data) > MAX_SHORTCUT_BYTES:
        raise UnicodeError("shortcut too large")
    encodings = (
        ("utf-16", "utf-8-sig", "cp1252")
        if data.startswith((b"\xff\xfe", b"\xfe\xff"))
        else ("utf-8-sig", "cp1252")
    )
    for encoding in encodings:
        try:
            target = parse_internet_shortcut_url(data.decode(encoding))
        except UnicodeDecodeError:
            continue
        if target is not None:
            return target
    return None


def _read_lnk_target(path: str, run_process: Callable[..., subprocess.CompletedProcess[str]]) -> str | None:
    try:
        completed = run_process(
            ["powershell.exe", "-NoProfile", "-Command", _POWERSHELL_SHORTCUT_COMMAND, path],
            shell=False,
            capture_output=True,
            text=True,
            timeout=SHORTCUT_TIMEOUT_SECONDS,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, UnicodeError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    output = completed.stdout.strip()
    if not output or "\n" in output or "\r" in output or len(output) > MAX_RAW_DROP_LENGTH:
        return None
    return output


def _normalize_target(
    target: str,
    fallback: DropItem,
    warnings: list[DropWarning],
    warning_code: str,
) -> tuple[DropItem, ...]:
    try:
        normalized = extract_drop_values((target,))
    except DropExtractionError:
        normalized = ()
    if normalized and all(item.kind in {"path", "url"} for item in normalized):
        return normalized
    warnings.append(DropWarning(warning_code, "A shortcut target was unusable; its path was kept."))
    return (fallback,)


def _dedupe(items: list[DropItem]) -> tuple[DropItem, ...]:
    kept: list[DropItem] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item.kind, item.value.casefold() if item.kind == "path" else item.value)
        if key not in seen:
            seen.add(key)
            kept.append(item)
    return tuple(kept)


class DropResolutionCoordinator:
    """Single-flight worker for shortcut reads; callers poll on the Tk thread."""

    def __init__(self, resolver: Callable[[tuple[str, ...]], DropResult] = resolve_decoded_values) -> None:
        self._resolver = resolver
        self._completed: queue.SimpleQueue[DropResult] = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._running = False

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def start(self, values: tuple[str, ...]) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True

        def work() -> None:
            try:
                result = self._resolver(values)
            except Exception:
                result = DropResult(error=DropProblem("resolution", "The drop could not be prepared safely."))
            self._completed.put(result)

        threading.Thread(target=work, daemon=True, name="drop-resolution").start()
        return True

    def drain(self) -> DropResult | None:
        try:
            result = self._completed.get_nowait()
        except queue.Empty:
            return None
        with self._lock:
            self._running = False
        return result
