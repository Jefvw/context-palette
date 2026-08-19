"""Pure, bounded normalization for already-decoded drag-and-drop values.

The TkDND adapter is deliberately responsible for decoding the Tcl payload.  This
module never reads files, touches Tk, or inspects the clipboard; it only turns
individual decoded values into safe, typed candidates for the launcher.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Literal
from urllib.parse import unquote, urlparse


DropKind = Literal["path", "url", "text"]

# These limits apply before any UI work.  They keep a malformed or hostile drop
# from turning a convenience intake path into an unbounded text processor.
MAX_DROP_VALUES = 128
MAX_DROP_VALUE_LENGTH = 16_384
MAX_DROP_TOTAL_LENGTH = 256_000
MAX_DROP_ITEMS = 256

_WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_WINDOWS_UNC_PATH = re.compile(r"^(?:\\\\|//)")
_HTTP_URL = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_URL_TRAILING_PUNCTUATION = ".,;:!?)]}"


class DropExtractionError(ValueError):
    """A bounded drop intake request could not be processed safely."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class DropItem:
    """One normalized candidate with no implied filesystem or network access."""

    kind: DropKind
    value: str

    def __post_init__(self) -> None:
        if self.kind not in {"path", "url", "text"}:
            raise ValueError("Drop item kind must be path, url, or text.")
        if not self.value:
            raise ValueError("Drop item value must not be empty.")


def extract_drop_values(values: Iterable[str]) -> tuple[DropItem, ...]:
    """Normalize decoded drop values in stable first-seen order.

    A value that contains one or more valid HTTP(S) addresses yields only those
    addresses.  Otherwise it yields one Windows path, file URI path, or ordinary
    text value.  ``.url`` and ``.lnk`` names intentionally remain paths: a later
    Windows adapter may decide whether it is appropriate to resolve them.
    """

    total_length = 0
    extracted: list[DropItem] = []
    seen: set[tuple[str, str]] = set()
    for value_count, value in enumerate(values, start=1):
        if value_count > MAX_DROP_VALUES:
            raise DropExtractionError("value_count", "Too many dropped values.")
        if not isinstance(value, str):
            raise DropExtractionError("value_type", "Dropped values must be text.")
        if len(value) > MAX_DROP_VALUE_LENGTH:
            raise DropExtractionError("value_length", "A dropped value is too large.")
        total_length += len(value)
        if total_length > MAX_DROP_TOTAL_LENGTH:
            raise DropExtractionError("total_length", "Dropped text is too large.")

        for item in _extract_value(value):
            key = _dedupe_key(item)
            if key in seen:
                continue
            seen.add(key)
            extracted.append(item)
            if len(extracted) > MAX_DROP_ITEMS:
                raise DropExtractionError("output_count", "Too many usable dropped items.")
    return tuple(extracted)


def parse_internet_shortcut_url(content: str) -> str | None:
    """Return the HTTP(S) URL from decoded ``.url`` content, if it has one.

    This intentionally parses supplied text only.  Opening a shortcut file and
    deciding which encoding to use are platform-adapter responsibilities.
    """

    if not isinstance(content, str):
        raise DropExtractionError("shortcut_type", "Internet Shortcut content must be text.")
    if len(content) > MAX_DROP_VALUE_LENGTH:
        raise DropExtractionError("shortcut_length", "Internet Shortcut content is too large.")

    in_shortcut_section = False
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith((";", "#")):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_shortcut_section = stripped[1:-1].strip().casefold() == "internetshortcut"
            continue
        if not in_shortcut_section or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip().casefold() != "url":
            continue
        candidate = _clean_http_url(value.strip())
        return candidate if candidate is not None else None
    return None


def _extract_value(value: str) -> tuple[DropItem, ...]:
    candidate = value.strip()
    if not candidate:
        return ()

    path = _windows_path(candidate)
    if path is not None:
        return (DropItem("path", path),)

    file_path = _file_uri_to_windows_path(candidate)
    if file_path is not None:
        return (DropItem("path", file_path),)

    urls = tuple(
        DropItem("url", clean)
        for match in _HTTP_URL.finditer(candidate)
        if (clean := _clean_http_url(match.group(0))) is not None
    )
    if urls:
        return urls
    return (DropItem("text", candidate),)


def _windows_path(value: str) -> str | None:
    decoded = unquote(value) if "%" in value else value
    if not (_WINDOWS_DRIVE_PATH.match(decoded) or _WINDOWS_UNC_PATH.match(decoded)):
        return None
    if decoded.startswith("//"):
        decoded = "\\\\" + decoded[2:]
    return decoded.replace("/", "\\")


def _file_uri_to_windows_path(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme.casefold() != "file":
        return None
    if parsed.query or parsed.fragment:
        return None
    path = unquote(parsed.path)
    if parsed.netloc and parsed.netloc.casefold() != "localhost":
        if not path or path == "/":
            return None
        return "\\\\" + parsed.netloc + path.replace("/", "\\")
    if re.match(r"^/[A-Za-z]:/", path):
        return path[1:].replace("/", "\\")
    return None


def _clean_http_url(value: str) -> str | None:
    cleaned = value.rstrip(_URL_TRAILING_PUNCTUATION)
    if not cleaned:
        return None
    parsed = urlparse(cleaned)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return None
    return cleaned


def _dedupe_key(item: DropItem) -> tuple[str, str]:
    if item.kind == "path":
        return (item.kind, item.value.casefold())
    return (item.kind, item.value)
