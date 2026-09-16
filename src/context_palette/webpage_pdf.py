"""Render one public HTTP(S) webpage to a locally chosen PDF without Tk state.

The UI supplies this module from a worker thread.  Each render starts a private
Chromium profile and publishes only a validated completed PDF.
"""

from __future__ import annotations

import ipaddress
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit


MAX_WEBPAGE_URL_CHARACTERS = 4_096
_HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_IS_WINDOWS = os.name == "nt"


class WebpagePdfError(ValueError):
    """A webpage cannot be safely rendered to the requested PDF."""


def validate_webpage_url(text: str) -> str:
    """Return one complete HTTP(S) URL, rejecting ambiguous workspace text."""

    if not isinstance(text, str):
        raise WebpagePdfError("Input / Output must contain one complete website address.")
    value = text.strip()
    if not value:
        raise WebpagePdfError("Input / Output does not contain a website address.")
    if len(value) > MAX_WEBPAGE_URL_CHARACTERS:
        raise WebpagePdfError("The website address is too long to render safely.")
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in value):
        raise WebpagePdfError("Input / Output must contain one website address without spaces.")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise WebpagePdfError("The website address has an invalid host or port.") from exc
    if parts.scheme.casefold() not in {"http", "https"}:
        raise WebpagePdfError("Only complete HTTP or HTTPS website addresses can be saved as PDF.")
    if not parts.netloc or not parts.hostname:
        raise WebpagePdfError("The website address must include a host name.")
    if parts.username is not None or parts.password is not None:
        raise WebpagePdfError("Website addresses with embedded credentials cannot be rendered.")
    if port is not None and not 1 <= port <= 65_535:
        raise WebpagePdfError("The website address has an invalid port.")
    _validate_host(parts.hostname)
    return value


def suggested_pdf_name(url: str) -> str:
    """Return a portable filename derived from a validated URL's host and path."""

    value = validate_webpage_url(url)
    parts = urlsplit(value)
    host = _safe_component(parts.hostname or "webpage")
    leaf = parts.path.rstrip("/").rsplit("/", 1)[-1] or "page"
    leaf = _safe_component(leaf)
    name = f"webpage-{host}-{leaf}"
    return f"{name[:120].rstrip('._-') or 'webpage'}.pdf"


def find_pdf_browser() -> Path:
    """Find an installed Chromium browser without changing a user profile."""

    roots: list[Path] = []
    for root_name in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        root = os.environ.get(root_name)
        if not root:
            continue
        roots.append(Path(root))
    candidates = [
        root / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        for root in roots
    ] + [
        root / "Google" / "Chrome" / "Application" / "chrome.exe"
        for root in roots
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    for executable in ("msedge.exe", "msedge", "chrome.exe", "chrome"):
        found = shutil.which(executable)
        if found:
            return Path(found)
    raise WebpagePdfError(
        "No supported browser was found. Install Microsoft Edge or Google Chrome to save a webpage as PDF."
    )


def render_webpage_pdf(
    url: str,
    destination: Path,
    *,
    browser_path: Path | None = None,
    cancel_event: threading.Event | None = None,
    timeout: float = 60.0,
) -> Path:
    """Render ``url`` through a private Chromium process and publish one PDF.

    This function performs no Tk work and is intended for an already-started
    background worker.  It never overwrites an existing destination.
    """

    validated_url = validate_webpage_url(url)
    target = _validate_destination(destination)
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise WebpagePdfError("The webpage PDF timeout must be a positive number of seconds.")
    if cancel_event is not None and cancel_event.is_set():
        raise WebpagePdfError("Saving the webpage as PDF was cancelled before rendering started.")
    browser = Path(browser_path) if browser_path is not None else find_pdf_browser()
    if not browser.is_file():
        raise WebpagePdfError("The selected browser is unavailable. Choose an installed Edge or Chrome browser.")

    process: subprocess.Popen[bytes] | None = None
    profile_temporary = tempfile.TemporaryDirectory(prefix="context-palette-webpage-pdf-profile-")
    staging_temporary = tempfile.TemporaryDirectory(
        prefix=".context-palette-webpage-pdf-", dir=target.parent
    )
    try:
        profile = Path(profile_temporary.name) / "profile"
        staged_pdf = Path(staging_temporary.name) / "rendered.pdf"
        command = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={profile}",
            f"--print-to-pdf={staged_pdf}",
            "--no-pdf-header-footer",
            validated_url,
        ]
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=(
                    (subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    if _IS_WINDOWS
                    else 0
                ),
            )
        except OSError as exc:
            raise WebpagePdfError("The browser could not start to render the webpage.") from exc
        try:
            _wait_for_render(process, cancel_event, float(timeout))
        finally:
            if process.poll() is None:
                _terminate_process_tree(process)
        _validate_rendered_pdf(staged_pdf)
        if cancel_event is not None and cancel_event.is_set():
            raise WebpagePdfError("Saving the webpage as PDF was cancelled before publication.")
        _cleanup_profile_before_publication(profile_temporary)
        if cancel_event is not None and cancel_event.is_set():
            raise WebpagePdfError("Saving the webpage as PDF was cancelled before publication.")
        _publish_no_clobber(staged_pdf, target)
        return target
    finally:
        # Once publication succeeds, cleanup must not turn that true result into
        # a false failure. Both directories contain only temporary data.
        try:
            profile_temporary.cleanup()
        except OSError:
            pass
        try:
            staging_temporary.cleanup()
        except OSError:
            pass


def _validate_host(host: str) -> None:
    try:
        ipaddress.ip_address(host)
        return
    except ValueError:
        pass
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise WebpagePdfError("The website address has an invalid host name.") from exc
    if len(ascii_host) > 253 or ascii_host.endswith(".") or any(
        not _HOST_LABEL.fullmatch(label) for label in ascii_host.split(".")
    ):
        raise WebpagePdfError("The website address has an invalid host name.")


def _safe_component(value: str) -> str:
    cleaned = _SAFE_NAME.sub("-", value).strip(" ._-")
    return cleaned[:80] or "page"


def _validate_destination(destination: Path) -> Path:
    path = Path(destination)
    if not path.is_absolute():
        raise WebpagePdfError("Choose an absolute PDF destination.")
    if path.suffix.casefold() != ".pdf":
        raise WebpagePdfError("The webpage destination must use the .pdf extension.")
    parent = path.parent
    if not parent.is_dir():
        raise WebpagePdfError("The selected PDF folder is unavailable.")
    try:
        target = parent.resolve(strict=True) / path.name
    except OSError as exc:
        raise WebpagePdfError("The selected PDF folder is unavailable.") from exc
    if target.exists():
        raise WebpagePdfError("A PDF already exists at the selected destination. Choose a new name.")
    return target


def _wait_for_render(
    process: subprocess.Popen[bytes],
    cancel_event: threading.Event | None,
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    while process.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            _terminate_process_tree(process)
            raise WebpagePdfError("Saving the webpage as PDF was cancelled.")
        if time.monotonic() >= deadline:
            _terminate_process_tree(process)
            raise WebpagePdfError("Saving the webpage as PDF timed out. The website may be unavailable or still loading.")
        time.sleep(0.05)
    if process.returncode != 0:
        raise WebpagePdfError("The browser could not load the webpage as a PDF. Check the website and try again.")


def _validate_rendered_pdf(path: Path) -> None:
    try:
        with path.open("rb") as stream:
            header = stream.read(5)
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - 1_024))
            tail = stream.read()
    except OSError as exc:
        raise WebpagePdfError("The browser finished without creating a readable PDF.") from exc
    if header != b"%PDF-" or size < 10 or b"%%EOF" not in tail:
        raise WebpagePdfError("The browser created an invalid PDF. The webpage may have failed to load.")


def _publish_no_clobber(staged: Path, destination: Path) -> None:
    if destination.exists():
        raise WebpagePdfError("A PDF already exists at the selected destination. Choose a new name.")
    try:
        if _IS_WINDOWS:
            os.rename(staged, destination)
        else:
            os.link(staged, destination)
            staged.unlink()
    except FileExistsError as exc:
        raise WebpagePdfError("A PDF appeared at the selected destination. Choose a new name.") from exc
    except OSError as exc:
        raise WebpagePdfError("The completed PDF could not be saved at the selected destination.") from exc


def _cleanup_profile_before_publication(profile_temporary: tempfile.TemporaryDirectory[str]) -> None:
    try:
        profile_temporary.cleanup()
    except OSError as exc:
        raise WebpagePdfError("The private browser data could not be removed before saving the PDF.") from exc


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if _IS_WINDOWS:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            process.terminate()
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        try:
            process.kill()
        except OSError:
            pass
