from __future__ import annotations

from logging.handlers import RotatingFileHandler
from collections import Counter
from dataclasses import dataclass
import logging
from pathlib import Path
import re


LOGGER_NAME = "context_palette"
PASTE_EVENT_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[^:]*: "
    r"Automatic paste: category=(?P<category>[a-z_]+) "
    r"outcome=(?P<outcome>[a-z_]+) reason=(?P<reason>[a-z_]+)$"
)
ERROR_TIMESTAMP_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[^\n]* ERROR "
)
SAFE_CATEGORIES = frozenset({"saved_text", "protected_credential"})
SAFE_OUTCOMES = frozenset({"success", "clipboard_only", "failed", "cancelled"})
SAFE_REASONS = frozenset(
    {
        "dispatched",
        "no_destination",
        "destination_unavailable",
        "dispatch_error",
        "user_cancelled",
    }
)


@dataclass(frozen=True)
class PasteDiagnosticEvent:
    timestamp: str
    category: str
    outcome: str
    reason: str


@dataclass(frozen=True)
class DiagnosticSummary:
    log_available: bool
    error_count: int
    last_error_at: str
    paste_outcome_counts: tuple[tuple[str, int], ...]
    recent_paste_events: tuple[PasteDiagnosticEvent, ...]


def configure_logging(path: Path) -> logging.Logger:
    """Configure one bounded local diagnostic log without duplicating handlers."""
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            path,
            maxBytes=512 * 1024,
            backupCount=2,
            encoding="utf-8",
        )
    except OSError:
        handler = logging.NullHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def summarize_diagnostics(path: Path, *, max_lines: int = 2_000) -> DiagnosticSummary:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    except OSError:
        return DiagnosticSummary(False, 0, "", (), ())
    error_count = 0
    last_error_at = ""
    events: list[PasteDiagnosticEvent] = []
    counts: Counter[str] = Counter()
    for line in lines:
        error_match = ERROR_TIMESTAMP_PATTERN.match(line)
        if error_match:
            error_count += 1
            last_error_at = error_match.group("timestamp")
        event_match = PASTE_EVENT_PATTERN.match(line)
        if not event_match:
            continue
        values = event_match.groupdict()
        if (
            values["category"] not in SAFE_CATEGORIES
            or values["outcome"] not in SAFE_OUTCOMES
            or values["reason"] not in SAFE_REASONS
        ):
            continue
        event = PasteDiagnosticEvent(**values)
        events.append(event)
        counts[event.outcome] += 1
    return DiagnosticSummary(
        True,
        error_count,
        last_error_at,
        tuple(sorted(counts.items())),
        tuple(events[-10:]),
    )


def render_safe_diagnostics(
    summary: DiagnosticSummary,
    *,
    action_count: int,
    personal_action_count: int,
    context_count: int,
    button_group_count: int,
) -> str:
    lines = [
        "Context Palette diagnostics",
        "",
        "Configuration loaded",
        f"Actions: {action_count} ({personal_action_count} personal)",
        f"Contexts: {context_count}",
        f"Quick-action groups: {button_group_count}",
        "",
        "Recent local diagnostics",
    ]
    if not summary.log_available:
        lines.append("No local diagnostic log is available yet.")
        return "\n".join(lines)
    lines.append(f"Error entries: {summary.error_count}")
    lines.append(f"Last error: {summary.last_error_at or 'None recorded'}")
    counts = dict(summary.paste_outcome_counts)
    lines.extend(
        (
            "",
            "Automatic paste outcomes",
            f"Successful: {counts.get('success', 0)}",
            f"Clipboard only: {counts.get('clipboard_only', 0)}",
            f"Failed: {counts.get('failed', 0)}",
            f"Cancelled: {counts.get('cancelled', 0)}",
            "",
            "Recent automatic paste events",
        )
    )
    if summary.recent_paste_events:
        lines.extend(
            f"{event.timestamp} | {event.category} | {event.outcome} | {event.reason}"
            for event in summary.recent_paste_events
        )
    else:
        lines.append("No automatic paste events recorded yet.")
    lines.extend(
        (
            "",
            "Privacy",
            "This summary excludes pasted text, action values, credential details, and window titles.",
        )
    )
    return "\n".join(lines)
