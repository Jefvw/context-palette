"""Attended export of the current Ultimate Guitar score in Microsoft Edge.

This boundary deliberately controls only one captured Edge window through the
fixed companion script.  It never starts Edge, reads a browser profile, or
uses coordinates/keystrokes to drive another application.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Callable
from urllib.parse import urlsplit


_SCRIPT = Path(__file__).with_name("edge_score_pdf.ps1")
_SAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}
_PROGRESS_PREFIX = "CONTEXT_PALETTE_PROGRESS:"
_RESULT_PREFIX = "CONTEXT_PALETTE_RESULT:"
_ERROR_PREFIX = "CONTEXT_PALETTE_ERROR:"
_MAX_PROTOCOL_LINE = 4_096
_MAX_PROTOCOL_LINES = 128

_PROGRESS_MESSAGES = {
    "checking": "Checking the captured Edge score.",
    "opening": "Opening Edge's score print preview.",
    "saving": "Saving the score PDF.",
    "verifying": "Verifying the saved score PDF.",
}
_ERROR_MESSAGES = {
    "not_edge": "The captured window is not Microsoft Edge.",
    "unavailable_window": "The captured Edge window is no longer available.",
    "focus_changed": "The captured Edge window is no longer in the foreground.",
    "unsupported_page": "Open an Official score or Guitar Pro tab on Ultimate Guitar in Edge, then try again.",
    "page_changed": "The captured Edge score changed before printing.",
    "unsupported_controls": "Edge did not expose the required score print controls.",
    "score_print_disabled": "The score's PRINT button is disabled. Wait for the score to finish loading, then try again.",
    "score_print_hidden": "The score's PRINT button is outside the visible page area. Make the button visible in Edge, then try again.",
    "choose_pdf_printer": "Select Save as PDF in Edge print preview, then try again.",
    "preview_timeout": "Edge print preview did not open in time.",
    "save_dialog_timeout": "Edge's Save As dialog was not ready in time. Close the print and Save As dialogs, then try again.",
    "file_timeout": "Edge did not create the staged PDF in time.",
    "invoke_failed": "Edge could not invoke a required score print control.",
    "filename_changed": "Windows Save As did not retain the private staging filename.",
    "unexpected_dialog": "An unexpected Windows dialog interrupted the score export.",
    "invalid_staging": "Edge did not create a valid staged PDF.",
    "unknown": "Edge could not verify or save the current Ultimate Guitar score.",
}
for _stage, _control in {
    "address": "Edge's address bar",
    "score_print": "the score's PRINT button",
    "printer_group": "the printer settings in Edge's print preview",
    "printer_selector": "the printer selector in Edge's print preview",
    "filename": "the filename field in Windows Save As",
    "native_save": "the Save button in Windows Save As",
}.items():
    _ERROR_MESSAGES[f"{_stage}_missing"] = f"Could not find {_control}. Nothing further was clicked."
    _ERROR_MESSAGES[f"{_stage}_ambiguous"] = f"More than one control matched {_control}. Saving stopped instead of guessing."
_GENERIC_HELPER_ERROR = _ERROR_MESSAGES["unknown"]


class EdgeScorePdfError(RuntimeError):
    """The attended Edge score could not be saved safely."""


class EdgeScorePdfCancelled(EdgeScorePdfError):
    """The caller cancelled the helper before it reported completion."""


class EdgeScorePdfManualSave(EdgeScorePdfError):
    """The verified Save As dialog was left untouched for manual completion."""


class EdgeScorePdfHelperTerminationError(EdgeScorePdfError):
    """The owned helper may still be interacting with Windows controls."""


@dataclass(frozen=True, slots=True)
class EdgeScorePdfResult:
    destination_path: Path
    url: str
    title: str


def save_edge_score_pdf(
    source_hwnd: int,
    destination_folder: Path,
    *,
    cancel_event: threading.Event | None = None,
    progress: Callable[[str], None] | None = None,
    timeout: float = 75.0,
    script_path: Path = _SCRIPT,
) -> EdgeScorePdfResult:
    """Save one visible UG score from the exact captured Edge window.

    The PowerShell process is the only process this function may terminate on
    cancellation or timeout.  It never kills, starts, or profiles Edge.
    """
    hwnd = _validate_hwnd(source_hwnd)
    if os.name != "nt":
        raise EdgeScorePdfError("Saving the current Edge score is available only on Windows.")
    folder = _validate_folder(destination_folder)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise EdgeScorePdfError("The Edge score PDF timeout must be a positive number of seconds.")
    if cancel_event is not None and cancel_event.is_set():
        raise EdgeScorePdfCancelled("Saving the Edge score PDF was cancelled before it started.")
    script = Path(script_path)
    if not script.is_file():
        raise EdgeScorePdfError("The Ultimate Guitar Edge integration is not installed.")
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        raise EdgeScorePdfError("Windows PowerShell is unavailable for the Edge score export.")

    temporary_path = Path(tempfile.mkdtemp(prefix=".context-palette-edge-score-", dir=folder))
    staged = temporary_path / "score.pdf"
    preserve_staging = False
    try:
        command = [powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(script), "-SourceHwnd", str(hwnd), "-StagedPdf", str(staged)]
        response = _run_helper(command, cancel_event=cancel_event, progress=progress, timeout=float(timeout))
        if cancel_event is not None and cancel_event.is_set():
            raise EdgeScorePdfCancelled("Saving the Edge score PDF was cancelled before publication.")
        url, title = _parse_response(response)
        _validate_ultimate_guitar_url(url)
        _validate_pdf(staged)
        if cancel_event is not None and cancel_event.is_set():
            raise EdgeScorePdfCancelled("Saving the Edge score PDF was cancelled before publication.")
        destination = _publish_with_suffix(staged, folder, title)
        return EdgeScorePdfResult(destination, url, title)
    except EdgeScorePdfHelperTerminationError:
        preserve_staging = True
        raise
    finally:
        # A completed publication remains truthful even if Windows retains a
        # transient handle to this private staging directory.
        if not preserve_staging:
            try:
                staged.unlink(missing_ok=True)
                temporary_path.rmdir()
            except OSError:
                pass


def _validate_hwnd(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise EdgeScorePdfError("Capture the active Ultimate Guitar tab in Edge before saving it.")
    return value


def _validate_folder(value: Path) -> Path:
    folder = Path(value)
    if not folder.is_absolute() or not folder.is_dir():
        raise EdgeScorePdfError("Choose an available absolute folder for the Edge score PDF.")
    try:
        return folder.resolve(strict=True)
    except OSError as exc:
        raise EdgeScorePdfError("Choose an available absolute folder for the Edge score PDF.") from exc


def _run_helper(command: list[str], *, cancel_event: threading.Event | None, progress: Callable[[str], None] | None, timeout: float) -> dict[str, object]:
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as exc:
        raise EdgeScorePdfError("Windows PowerShell could not start the Edge score export.") from exc
    lines: queue.Queue[str] = queue.Queue(maxsize=_MAX_PROTOCOL_LINES)
    assert process.stdout is not None
    reader = threading.Thread(
        target=_read_helper_output,
        args=(process.stdout, lines),
        daemon=True,
    )
    reader.start()
    deadline = time.monotonic() + timeout
    response: dict[str, object] | None = None
    controlled_error: EdgeScorePdfError | None = None
    try:
        while process.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                _stop_helper(process)
                raise EdgeScorePdfCancelled("Saving the Edge score PDF was cancelled. Close Edge print preview if it remains open.")
            if time.monotonic() >= deadline:
                _stop_helper(process)
                raise EdgeScorePdfError("Saving the Edge score PDF timed out. Close Edge print preview and try again.")
            response, controlled_error = _drain_lines(lines, progress, response, controlled_error)
            time.sleep(0.04)
        reader.join(timeout=1)
        response, controlled_error = _drain_lines(lines, progress, response, controlled_error)
        if controlled_error is not None and (response is not None or process.returncode == 0):
            raise EdgeScorePdfError("Edge returned conflicting score PDF results.")
        if process.returncode != 0:
            raise controlled_error or EdgeScorePdfError("Edge could not verify or save the current Ultimate Guitar score. Keep the score tab visible and Save as PDF selected.")
        if response is None:
            raise EdgeScorePdfError("Edge returned no verified score PDF result.")
        return response
    finally:
        stopped = _stop_helper(process)
        if not stopped:
            # Closing a pipe while a live reader owns its lock can itself block.
            # Keep the private staging path and do not claim cancellation ended.
            raise EdgeScorePdfHelperTerminationError(
                "The score-export helper could not be stopped safely. Close Edge print preview before trying again."
            )
        reader.join(timeout=1)
        if not reader.is_alive():
            _close_helper_output(process.stdout)


def _read_helper_output(stream, lines: queue.Queue[str]) -> None:
    """Copy bounded protocol candidates without letting helper output block it."""

    try:
        for raw_line in stream:
            line = raw_line.rstrip("\r\n")[:_MAX_PROTOCOL_LINE]
            try:
                lines.put_nowait(line)
            except queue.Full:
                continue
    except (OSError, ValueError):
        return


def _close_helper_output(stream) -> None:
    try:
        stream.close()
    except (OSError, ValueError):
        pass


def _stop_helper(process: subprocess.Popen[str]) -> bool:
    """Stop only the owned PowerShell helper and prove it has exited."""

    if process.poll() is not None:
        return True
    try:
        process.terminate()
        process.wait(timeout=3)
        return True
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
            process.wait(timeout=3)
            return True
        except (OSError, subprocess.TimeoutExpired):
            return process.poll() is not None


def _drain_lines(lines: queue.Queue[str], progress: Callable[[str], None] | None, response: dict[str, object] | None, controlled_error: EdgeScorePdfError | None) -> tuple[dict[str, object] | None, EdgeScorePdfError | None]:
    while True:
        try:
            line = lines.get_nowait()
        except queue.Empty:
            return response, controlled_error
        if line.startswith(_PROGRESS_PREFIX):
            message = _PROGRESS_MESSAGES.get(line[len(_PROGRESS_PREFIX):])
            if message is not None and progress is not None:
                progress(message)
        elif line.startswith(_RESULT_PREFIX):
            if response is not None:
                raise EdgeScorePdfError("Edge returned more than one score PDF result.")
            try:
                decoded = json.loads(line[len(_RESULT_PREFIX):])
            except json.JSONDecodeError as exc:
                raise EdgeScorePdfError("Edge returned an invalid score PDF result.") from exc
            if not isinstance(decoded, dict):
                raise EdgeScorePdfError("Edge returned an invalid score PDF result.")
            response = decoded
        elif line.startswith(_ERROR_PREFIX):
            code = line[len(_ERROR_PREFIX):]
            # This fixed helper stage is reached only after verifying native
            # Save As, and before changing its filename or invoking Save.
            if code == "filename_missing":
                error = EdgeScorePdfManualSave(
                    "Finish saving in Edge: choose a folder and filename, then select Save."
                )
            else:
                error = EdgeScorePdfError(_ERROR_MESSAGES.get(code, _GENERIC_HELPER_ERROR))
            # A handoff must never hide another failure in malformed output.
            if controlled_error is not None:
                error = EdgeScorePdfError("Edge returned conflicting score PDF results.")
            controlled_error = error


def _parse_response(response: dict[str, object]) -> tuple[str, str]:
    url, title = response.get("url"), response.get("title")
    if not isinstance(url, str) or not isinstance(title, str) or not title.strip() or len(title) > 240:
        raise EdgeScorePdfError("Edge returned an invalid score identity.")
    return url, title.strip()


def _validate_ultimate_guitar_url(url: str) -> None:
    try:
        parts = urlsplit(url)
        has_port = parts.port is not None
    except ValueError as exc:
        raise EdgeScorePdfError("The captured Edge tab is not an Official or Guitar Pro Ultimate Guitar score URL.") from exc
    if (
        parts.scheme != "https" or parts.hostname != "tabs.ultimate-guitar.com"
        or parts.username is not None or parts.password is not None
        or has_port or parts.query or parts.fragment
        or not re.fullmatch(r"https://tabs\.ultimate-guitar\.com/tab/[a-z0-9-]+/[a-z0-9-]+-(?:official|guitar-pro)-[0-9]+", url, re.IGNORECASE)
    ):
        raise EdgeScorePdfError("The captured Edge tab is not an Official or Guitar Pro Ultimate Guitar score URL.")


def _validate_pdf(path: Path) -> None:
    try:
        with path.open("rb") as stream:
            header = stream.read(5)
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - 1024))
            tail = stream.read()
    except OSError as exc:
        raise EdgeScorePdfError("Edge did not create a readable staged PDF.") from exc
    if header != b"%PDF-" or size < 10 or b"%%EOF" not in tail:
        raise EdgeScorePdfError("Edge did not create a valid staged PDF.")


def _filename(title: str) -> str:
    clean = _SAFE_NAME.sub("-", title).strip(" .-")[:120]
    device_name = clean.rstrip(" .").split(".", 1)[0]
    if device_name.casefold() in {name.casefold() for name in _WINDOWS_RESERVED}:
        clean = f"score-{clean}"
    return f"{clean or 'ultimate-guitar-score'}.pdf"


def _publish_with_suffix(staged: Path, folder: Path, title: str) -> Path:
    stem = Path(_filename(title)).stem
    for number in range(10_000):
        suffix = "" if number == 0 else f" ({number})"
        target = folder / f"{stem[:120-len(suffix)]}{suffix}.pdf"
        try:
            os.rename(staged, target)
            return target
        except FileExistsError:
            continue
        except OSError as exc:
            raise EdgeScorePdfError("The completed Edge score PDF could not be published.") from exc
    raise EdgeScorePdfError("Too many matching Edge score PDF names exist in the selected folder.")
