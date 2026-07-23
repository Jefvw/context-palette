from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
from typing import Callable

from .work_item_creation import (
    WorkItemCreationError,
    create_matching_workbook_from_template,
)


MAX_EXCEL_CELL_CHARS = 32_767
MAX_LINK_CHARS = 2_048
URL_PATTERN = re.compile(r"https?://[^\s<>\]\[()\"']+", re.IGNORECASE)
UNSUPPORTED_CELL_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "integrations"
    / "Append-WorkItemInbox.ps1"
)
LOGGER = logging.getLogger(__name__)


class WorkItemInboxError(RuntimeError):
    """Input / Output could not be appended without risking workbook data."""


@dataclass(frozen=True, slots=True)
class WorkItemInboxEntry:
    added: str
    text: str
    link: str
    source: str


@dataclass(frozen=True, slots=True)
class WorkItemInboxResult:
    workbook_path: Path
    row: int
    created_sheet: bool
    created_workbook: bool


def first_http_url(text: str) -> str:
    match = URL_PATTERN.search(text)
    if match is None:
        return ""
    return match.group(0).rstrip(".,;:!?")


def create_work_item_inbox_entry(
    text: str,
    *,
    source: str,
    now: datetime | None = None,
) -> WorkItemInboxEntry:
    clean_text = text.strip()
    clean_source = " ".join(source.split()) or "Input / Output"
    if not clean_text:
        raise WorkItemInboxError("Input / Output is empty.")
    if UNSUPPORTED_CELL_CONTROL_PATTERN.search(clean_text):
        raise WorkItemInboxError(
            "Input / Output contains a control character Excel cells cannot store."
        )
    if _utf16_length(clean_text) > MAX_EXCEL_CELL_CHARS:
        raise WorkItemInboxError(
            f"Input / Output exceeds Excel's {MAX_EXCEL_CELL_CHARS:,}-character cell limit."
        )
    clean_source = _truncate_utf16(clean_source, MAX_EXCEL_CELL_CHARS)
    link = first_http_url(clean_text)
    if len(link) > MAX_LINK_CHARS:
        raise WorkItemInboxError(
            f"The first link exceeds the supported {MAX_LINK_CHARS:,}-character limit."
        )
    timestamp = (now or datetime.now().astimezone()).isoformat()
    return WorkItemInboxEntry(timestamp, clean_text, link, clean_source)


def append_work_item_inbox(
    workbook_path: Path,
    entry: WorkItemInboxEntry,
    *,
    script_path: Path = SCRIPT_PATH,
    timeout_seconds: int = 60,
) -> tuple[int, bool]:
    workbook = Path(workbook_path)
    script = Path(script_path)
    if (
        not workbook.is_absolute()
        or not workbook.is_file()
        or workbook.suffix.casefold() != ".xlsx"
    ):
        raise WorkItemInboxError("Choose an existing matching .xlsx workbook.")
    if not script.is_file():
        raise WorkItemInboxError("The Excel Inbox integration is not installed.")
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        raise WorkItemInboxError("Windows PowerShell is unavailable.")
    request = json.dumps(
        {
            "workbook": str(workbook),
            "added": entry.added,
            "text": entry.text,
            "link": entry.link,
            "source": entry.source,
        },
        ensure_ascii=False,
    )
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            [
                powershell,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ],
            input=request,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            creationflags=creation_flags,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkItemInboxError(
            "Excel did not complete the Inbox update."
        ) from exc
    if completed.returncode != 0:
        detail = _safe_process_error(completed.stderr)
        raise WorkItemInboxError(
            detail or "Excel could not append the Inbox record."
        )
    try:
        response = json.loads(completed.stdout)
        row = int(response["row"])
        created_sheet = bool(response["created_sheet"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise WorkItemInboxError(
            "Excel returned an invalid Inbox update result."
        ) from exc
    if row < 2:
        raise WorkItemInboxError("Excel returned an invalid Inbox row.")
    return row, created_sheet


def send_to_work_item_inbox(
    folder_path: Path,
    workbook_path: Path | None,
    template_path: Path | None,
    entry: WorkItemInboxEntry,
    *,
    appender: Callable[[Path, WorkItemInboxEntry], tuple[int, bool]] = append_work_item_inbox,
) -> WorkItemInboxResult:
    folder = Path(folder_path)
    if not folder.is_absolute() or not folder.is_dir():
        raise WorkItemInboxError("The selected Work Item folder is unavailable.")
    expected_workbook = folder / f"{folder.name}.xlsx"
    workbook = Path(workbook_path) if workbook_path is not None else expected_workbook
    if os.path.normcase(str(workbook.resolve(strict=False))) != os.path.normcase(
        str(expected_workbook.resolve(strict=False))
    ):
        raise WorkItemInboxError("The selected workbook does not exactly match the Work Item name.")
    created_workbook = False
    if not workbook.is_file():
        if template_path is None:
            raise WorkItemInboxError("The selected Work Item has no matching workbook.")
        try:
            workbook = create_matching_workbook_from_template(folder, template_path)
        except WorkItemCreationError as exc:
            raise WorkItemInboxError(str(exc)) from exc
        created_workbook = True
    try:
        row, created_sheet = appender(workbook, entry)
    except WorkItemInboxError as exc:
        if created_workbook:
            raise WorkItemInboxError(
                f"The matching workbook was created, but its Inbox could not be updated. {exc}"
            ) from exc
        raise
    return WorkItemInboxResult(
        workbook,
        row,
        created_sheet,
        created_workbook,
    )


class WorkItemInboxCoordinator:
    """Run the Excel operation off-thread and deliver completion on the UI thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._completed: queue.SimpleQueue[
            tuple[
                WorkItemInboxResult | None,
                WorkItemInboxError | None,
                Callable[[WorkItemInboxResult | None, WorkItemInboxError | None], None],
            ]
        ] = queue.SimpleQueue()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def start(
        self,
        folder_path: Path,
        workbook_path: Path | None,
        template_path: Path | None,
        entry: WorkItemInboxEntry,
        on_complete: Callable[
            [WorkItemInboxResult | None, WorkItemInboxError | None],
            None,
        ],
    ) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True

        def work() -> None:
            result: WorkItemInboxResult | None = None
            error: WorkItemInboxError | None = None
            try:
                result = send_to_work_item_inbox(
                    folder_path,
                    workbook_path,
                    template_path,
                    entry,
                )
            except WorkItemInboxError as exc:
                error = exc
            except Exception:
                LOGGER.exception("Unexpected Work Item Inbox background failure")
                error = WorkItemInboxError(
                    "The Inbox update stopped because of an unexpected local error."
                )
            self._completed.put((result, error, on_complete))

        threading.Thread(
            target=work,
            daemon=True,
            name="work-item-inbox",
        ).start()
        return True

    def drain(self) -> bool:
        try:
            result, error, on_complete = self._completed.get_nowait()
        except queue.Empty:
            return False
        try:
            on_complete(result, error)
        finally:
            with self._lock:
                self._running = False
        return True


def _safe_process_error(stderr: str) -> str:
    lines = [" ".join(line.split()) for line in stderr.splitlines() if line.strip()]
    if not lines:
        return ""
    detail = lines[-1]
    return detail[:500]


def _utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _truncate_utf16(value: str, limit: int) -> str:
    if _utf16_length(value) <= limit:
        return value
    result: list[str] = []
    length = 0
    for character in value:
        character_length = _utf16_length(character)
        if length + character_length > limit:
            break
        result.append(character)
        length += character_length
    return "".join(result)
