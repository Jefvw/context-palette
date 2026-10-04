"""Strict, transient protocol adapter for the read-only Python OneNote engine."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import re
from typing import Callable, Mapping
from uuid import uuid4

from .persistence import atomic_write_json


_SCHEMA = "1.0"
_MAX_MESSAGE_BYTES = 1024 * 1024
_ENGINE_CODE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_READ_CAPABILITIES = frozenset(
    {"inventory_desktop_hierarchy", "search_desktop_pages", "preview_desktop_page"}
)
_DESKTOP_READ_FAILURE_MESSAGE = (
    "OneNote could not complete this read. Make sure the notebook is open, "
    "then choose Search again. Your saved engine and notebook are unchanged."
)


class OneNoteSettingsError(ValueError):
    """The private Python OneNote launcher setting is invalid."""

    def __init__(self, message: str, *, notebook: NotebookRef | None = None) -> None:
        super().__init__(message)
        # Only independently validated metadata may survive launcher repair.
        self.notebook = notebook


@dataclass(frozen=True, slots=True)
class NotebookRef:
    object_id: str = field(repr=False)
    title: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class NotebookList:
    notebooks: tuple[NotebookRef, ...]
    total: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class OneNoteSettings:
    launcher_path: Path | None = None
    notebook: NotebookRef | None = None


@dataclass(frozen=True, slots=True)
class Description:
    can_probe: bool


@dataclass(frozen=True, slots=True)
class Readiness:
    ready_capabilities: tuple[str, ...]

    @property
    def can_search(self) -> bool:
        return "search_desktop_pages" in self.ready_capabilities

    @property
    def can_preview(self) -> bool:
        return "preview_desktop_page" in self.ready_capabilities


@dataclass(frozen=True, slots=True)
class SearchPage:
    object_id: str = field(repr=False)
    title: str = field(repr=False)
    breadcrumb: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class SearchResult:
    pages: tuple[SearchPage, ...]
    total: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class PagePreview:
    object_id: str = field(repr=False)
    text: str = field(repr=False)
    returned_characters: int
    source_characters: int
    truncated: bool

    @property
    def can_use(self) -> bool:
        return (
            not self.truncated
            and self.returned_characters == self.source_characters == len(self.text)
        )


class OneNoteError(Exception):
    """A fixed, non-sensitive engine or integration failure."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or {
            "backend.desktop_not_running": "Open OneNote, then choose Search to reconnect automatically.",
            "backend.desktop_process_exited": "OneNote changed. Choose Search to reconnect automatically.",
            "backend.desktop_busy": "OneNote is busy. Try again when ready.",
            "transport.timeout": "The OneNote request timed out. Choose Search to reconnect automatically.",
            "transport.cancelled": "OneNote request cancelled.",
            "internal.desktop_bridge": _DESKTOP_READ_FAILURE_MESSAGE,
        }.get(code, "OneNote integration could not complete the request.")
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message

    @property
    def invalidates_readiness(self) -> bool:
        return self.code not in {
            "backend.desktop_busy",
            "backend.desktop_timeout",
            "request.invalid_query",
            "target.not_found",
            "target.changed",
        }


Runner = Callable[[Path, bytes, float, object | None], object]


def load_onenote_settings(path: Path) -> OneNoteSettings:
    """Load an optional local launcher and explicitly chosen notebook."""

    settings_path = Path(path)
    if not settings_path.exists():
        return OneNoteSettings()
    try:
        with settings_path.open("rb") as source:
            payload = source.read(_MAX_MESSAGE_BYTES + 1)
    except OSError as exc:
        raise OneNoteSettingsError("OneNote settings could not be read.") from exc
    document = _decode_response(payload)
    if document is None or set(document) not in ({"launcher_path"}, {"launcher_path", "notebook"}):
        raise OneNoteSettingsError("OneNote settings must contain a launcher and optional notebook only.")
    raw_notebook = document.get("notebook")
    notebook = None
    if raw_notebook is not None:
        if not isinstance(raw_notebook, dict) or set(raw_notebook) != {"object_id", "title"}:
            raise OneNoteSettingsError("OneNote notebook settings are invalid.")
        notebook = NotebookRef(raw_notebook["object_id"], raw_notebook["title"])
        _validate_notebook(notebook)
    raw_path = document["launcher_path"]
    if not isinstance(raw_path, str):
        raise OneNoteSettingsError("OneNote launcher_path must be text.", notebook=notebook)
    clean_path = raw_path.strip()
    if not clean_path:
        return OneNoteSettings(notebook=notebook)
    launcher_path = Path(clean_path)
    try:
        _validate_launcher_path(launcher_path, require_exists=False)
    except OneNoteSettingsError:
        raise OneNoteSettingsError("The saved OneNote launcher needs repair.", notebook=notebook) from None
    return OneNoteSettings(launcher_path, notebook)


def discover_direct_sibling_python_onenote_launcher(application_root: Path) -> Path | None:
    """Check one installation-relative location; never execute or persist it."""
    root = Path(application_root)
    if not root.is_absolute():
        return None
    candidate = root.parent / "python-onenote" / "python-onenote.bat"
    try:
        return candidate if candidate.is_file() else None
    except OSError:
        return None


def save_onenote_settings(path: Path, settings: OneNoteSettings) -> None:
    launcher_path = settings.launcher_path
    if launcher_path is not None:
        _validate_launcher_path(Path(launcher_path))
    document: dict[str, object] = {"launcher_path": str(launcher_path) if launcher_path else ""}
    if settings.notebook is not None:
        _validate_notebook(settings.notebook)
        document["notebook"] = {"object_id": settings.notebook.object_id, "title": settings.notebook.title}
    atomic_write_json(Path(path), document)


class OneNoteClient:
    """Build and validate narrowly-scoped read-only engine calls.

    The runner is injected for tests.  In production it is the owned-process
    transport, which must return an object exposing ``stdout`` and ``returncode``.
    """

    def __init__(self, launcher_path: Path, runner: Runner | None = None) -> None:
        self.launcher_path = Path(launcher_path)
        self._runner = runner or _default_runner

    def describe(self, *, cancel_event: object | None = None) -> Description:
        response = self._call("describe_capabilities", {}, 10, cancel_event)
        if isinstance(response, OneNoteError):
            raise response
        capabilities = response.get("capabilities")
        backends = response.get("backends")
        if not isinstance(capabilities, list) or not isinstance(backends, list):
            raise _protocol_error()
        can_probe = False
        seen: set[str] = set()
        for capability in capabilities:
            if not isinstance(capability, dict):
                raise _protocol_error()
            capability_id = capability.get("capability_id")
            if not isinstance(capability_id, str) or capability_id in seen:
                raise _protocol_error()
            seen.add(capability_id)
            if capability_id == "probe_desktop_read_backend":
                can_probe = _valid_probe_capability(capability)
        desktop = [item for item in backends if isinstance(item, dict) and item.get("backend") == "desktop_automation"]
        if len(desktop) != 1 or desktop[0].get("state") != "unverified":
            raise _protocol_error()
        return Description(can_probe)

    def probe(self, *, cancel_event: object | None = None) -> Readiness:
        response = self._call(
            "probe_desktop_read_backend",
            {"effect_acknowledgement": "attach_to_running_onenote_and_probe_read_backend"},
            30,
            cancel_event,
        )
        if isinstance(response, OneNoteError):
            raise response
        if not _valid_probe_result(response, "probe"):
            raise _protocol_error()
        raw_capabilities = response.get("ready_capabilities")
        if not isinstance(raw_capabilities, list) or not raw_capabilities:
            raise _protocol_error()
        capabilities: list[str] = []
        for capability in raw_capabilities:
            if not isinstance(capability, str) or capability not in _READ_CAPABILITIES:
                raise _protocol_error()
            if capability not in capabilities:
                capabilities.append(capability)
        return Readiness(tuple(capabilities))

    def notebooks(self, *, cancel_event: object | None = None) -> NotebookList:
        response = self._call(
            "inventory_desktop_hierarchy",
            {"effect_acknowledgement": "attach_to_running_onenote_and_read_hierarchy",
             "start_object_id": None, "start_kind": None, "scope": "notebooks",
             "offset": 0, "limit": 100, "max_depth": 4},
            30, cancel_event,
        )
        if isinstance(response, OneNoteError):
            raise response
        if (set(response) != {"backend", "probe", "hierarchy"}
                or response.get("backend") != "desktop_automation"
                or not _valid_probe_result(response.get("probe"), "inventory")):
            raise _protocol_error()
        return _parse_notebooks(response.get("hierarchy"))

    def search(
        self, query: str, *, notebook_id: str | None = None, cancel_event: object | None = None
    ) -> SearchResult:
        if not _valid_text(query, nonblank=True, maximum=512, maximum_bytes=2048):
            raise OneNoteError("request.invalid_query", "Enter a valid OneNote search query.")
        if notebook_id is not None and not _valid_notebook_id(notebook_id):
            raise OneNoteError("target.invalid", "Choose a valid OneNote notebook before searching.")
        response = self._call(
            "search_desktop_pages",
            {
                "effect_acknowledgement": "attach_to_running_onenote_and_search_pages_without_display",
                "query": query,
                "start_object_id": notebook_id,
                "start_kind": "notebook" if notebook_id is not None else None,
                "include_unindexed_pages": True,
                "offset": 0,
                "limit": 20,
            },
            30,
            cancel_event,
        )
        if isinstance(response, OneNoteError):
            raise response
        if response.get("backend") != "desktop_automation" or not _valid_probe_result(response.get("probe"), "search"):
            raise _protocol_error()
        search = response.get("search")
        if not isinstance(search, dict):
            raise _protocol_error()
        parsed = _parse_search(search, notebook_id=notebook_id)
        if isinstance(parsed, OneNoteError):
            raise parsed
        return parsed

    def preview(
        self, page_id: str, *, cancel_event: object | None = None
    ) -> PagePreview:
        if not _valid_text(page_id, nonblank=True, maximum=4096, maximum_bytes=16384):
            raise OneNoteError("target.invalid", "Choose a valid OneNote result before previewing.")
        response = self._call(
            "preview_desktop_page",
            {
                "effect_acknowledgement": "attach_to_running_onenote_and_read_basic_page_text",
                "page_object_id": page_id,
                "max_characters": 50000,
            },
            30,
            cancel_event,
        )
        if isinstance(response, OneNoteError):
            raise response
        if response.get("backend") != "desktop_automation" or not _valid_probe_result(response.get("probe"), "preview"):
            raise _protocol_error()
        page = response.get("page")
        if not isinstance(page, dict) or not _exact_target(page.get("target"), page_id):
            raise _protocol_error()
        text = page.get("text")
        returned = page.get("returned_characters")
        source = page.get("source_characters")
        truncated = page.get("truncated")
        if (
            page.get("content_format") != "text/plain"
            or not _valid_text(text, maximum=50000, maximum_bytes=_MAX_MESSAGE_BYTES)
            or not _nonnegative_int(returned)
            or not _nonnegative_int(source)
            or not isinstance(truncated, bool)
            or returned != len(text)
            or source < returned
            or (not truncated and source != returned)
            or (truncated and (source <= returned or returned != 50000))
        ):
            raise _protocol_error()
        return PagePreview(page_id, text, returned, source, truncated)

    def _call(
        self, operation: str, arguments: Mapping[str, object], timeout: float, cancel_event: object | None
    ) -> dict[str, object] | OneNoteError:
        if cancel_event is None:
            # The Windows transport requires an event even for an ordinary
            # synchronous caller.  It remains unset unless the UI cancels it.
            import threading

            cancel_event = threading.Event()
        request_id = uuid4().hex
        request = {
            "schema_version": _SCHEMA,
            "request_id": request_id,
            "operation": operation,
            "operation_version": _SCHEMA,
            "arguments": dict(arguments),
        }
        try:
            payload = _encode_request(request)
            outcome = self._runner(self.launcher_path, payload, timeout, cancel_event)
            stdout = getattr(outcome, "stdout")
            returncode = getattr(outcome, "returncode")
        except Exception as exc:
            code = getattr(exc, "code", None)
            if isinstance(code, str) and code in {
                "transport.cancelled", "transport.timeout", "transport.oversized",
                "transport.launch", "transport.cleanup",
            }:
                return OneNoteError(code)
            return OneNoteError("integration.transport_failed", "OneNote integration could not run.")
        if not isinstance(stdout, bytes) or not isinstance(returncode, int) or isinstance(returncode, bool):
            return _protocol_error()
        document = _decode_response(stdout)
        if document is None:
            return _protocol_error()
        if not _valid_envelope(document, request_id, operation):
            return _protocol_error()
        status = document["status"]
        if status == "success":
            if returncode != 0:
                return _protocol_error()
            return document["result"]
        if returncode == 0:
            return _protocol_error()
        if not _valid_error_exit(document["error"], returncode):
            return _protocol_error()
        return _engine_error(document["error"])


def _default_runner(launcher_path: Path, request: bytes, timeout: float, cancel_event: object | None) -> object:
    from .onenote_process import run_owned_request

    return run_owned_request(launcher_path, request, timeout=timeout, cancel_event=cancel_event)


def _validate_launcher_path(path: Path, *, require_exists: bool = True) -> None:
    if not path.is_absolute() or path.name.casefold() != "python-onenote.bat":
        raise OneNoteSettingsError("The OneNote launcher must be an absolute python-onenote.bat path.")
    if not require_exists:
        return
    try:
        exists = path.is_file()
    except OSError as exc:
        raise OneNoteSettingsError("The OneNote launcher path could not be checked.") from exc
    if not exists:
        raise OneNoteSettingsError("The OneNote launcher must identify an existing file.")


def _valid_notebook_id(value: object) -> bool:
    return _valid_text(value, nonblank=True, maximum=2048, maximum_bytes=8192) and "\x00" not in value


def _validate_notebook(notebook: NotebookRef) -> None:
    if (not isinstance(notebook, NotebookRef) or not _valid_notebook_id(notebook.object_id)
            or not _valid_text(notebook.title, maximum=512, maximum_bytes=2048)):
        raise OneNoteSettingsError("OneNote notebook settings are invalid.")


def _encode_request(document: Mapping[str, object]) -> bytes:
    _reject_invalid_text(document)
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > _MAX_MESSAGE_BYTES:
        raise ValueError("request limit")
    return payload


def _decode_response(payload: bytes) -> dict[str, object] | None:
    if len(payload) > _MAX_MESSAGE_BYTES:
        return None
    try:
        text = payload.decode("utf-8-sig")
        value = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (UnicodeError, ValueError, TypeError, RecursionError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    try:
        _reject_invalid_text(value)
    except ValueError:
        return None
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(_: str) -> object:
    raise ValueError("non-finite JSON")


def _reject_invalid_text(value: object, depth: int = 0) -> None:
    if depth > 64:
        raise ValueError("nesting limit")
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError("lone surrogate")
    elif isinstance(value, dict):
        for key, item in value.items():
            _reject_invalid_text(key, depth + 1)
            _reject_invalid_text(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _reject_invalid_text(item, depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite JSON")


def _valid_envelope(document: dict[str, object], request_id: str, operation: str) -> bool:
    required = {
        "schema_version", "request_id", "operation", "operation_version", "status",
        "duration_ms", "result", "warnings", "artifacts", "error",
    }
    if set(document) != required:
        return False
    if (
        document["schema_version"] != _SCHEMA
        or document["request_id"] != request_id
        or document["operation"] != operation
        or document["operation_version"] != _SCHEMA
        or not isinstance(document["status"], str)
        or document["status"] not in {"success", "error"}
        or not _nonnegative_int(document["duration_ms"])
        or not isinstance(document["warnings"], list)
        or not isinstance(document["artifacts"], list)
    ):
        return False
    if document["status"] == "success":
        return isinstance(document["result"], dict) and document["error"] is None
    error = document["error"]
    return (
        document["result"] is None
        and isinstance(error, dict)
        and set(error) == {"code", "category", "message", "retryable", "details"}
        and isinstance(error["code"], str)
        and isinstance(error["category"], str)
        and isinstance(error["message"], str)
        and isinstance(error["retryable"], bool)
        and isinstance(error["details"], dict)
    )


def _valid_probe_result(value: object, operation: str) -> bool:
    if not isinstance(value, dict):
        return False
    expected = {
        "probe": (
            "attach_to_running_onenote_and_probe_read_backend",
            {"adapter_id": "windows_pia_subprocess", "adapter_version": "1.0", "attached_to_existing_process": True, "started_client": False, "schema": "xs2013", "lifecycle": "operation_owned", "apartment": "STA"},
        ),
        "search": (
            "attach_to_running_onenote_and_search_pages_without_display",
            {"attached_to_running_instance": True, "started_client": False, "displayed_search": False, "navigated": False, "synchronized": False, "schema": "xs2013"},
        ),
        "inventory": (
            "attach_to_running_onenote_and_read_hierarchy",
            {"attached_to_running_instance": True, "started_client": False, "navigated": False,
             "synchronized": False, "schema": "xs2013"},
        ),
        "preview": (
            "attach_to_running_onenote_and_read_basic_page_text",
            {"attached_to_running_instance": True, "started_client": False, "page_info": "piBasic", "binary_data_requested": False, "selection_markup_requested": False, "navigated": False, "synchronized": False, "schema": "xs2013"},
        ),
    }
    effect, evidence = expected[operation]
    if operation == "probe":
        if value.get("backend") != "desktop_automation" or value.get("state") != "available" or value.get("available") is not True or value.get("checked_by") != "active_probe" or value.get("external_access_performed") is not True:
            return False
        value = value.get("evidence")
        return (
            isinstance(value, dict)
            and _evidence_matches(value, evidence)
            and _valid_pia_version(value.get("pia_version"))
        )
    return (value.get("effect") == effect and _evidence_matches(value, evidence)
            and (operation != "inventory" or set(value) == {"effect", *evidence}))


def _evidence_matches(value: dict[str, object], expected: dict[str, object]) -> bool:
    return all(
        value.get(key) is item if isinstance(item, bool) else value.get(key) == item
        for key, item in expected.items()
    )


def _valid_probe_capability(value: dict[str, object]) -> bool:
    return (
        value.get("version") == _SCHEMA
        and value.get("backend") == "desktop_automation"
        and value.get("safety") == "read_only"
        and value.get("available") is True
        and value.get("requires_plan") is False
        and value.get("planning_only") is False
        and value.get("host_execution") == "worker_process"
    )


def _valid_pia_version(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,15}", value)) and len(value) <= 64


def _parse_notebooks(value: object) -> NotebookList:
    if not isinstance(value, dict) or set(value) != {"items", "returned", "total", "next_offset", "truncated"}:
        raise _protocol_error()
    items, returned, total, next_offset, truncated = (
        value["items"], value["returned"], value["total"], value["next_offset"], value["truncated"]
    )
    if (not isinstance(items, list) or len(items) > 100
            or not _nonnegative_int(returned) or returned != len(items)
            or not _nonnegative_int(total) or total < returned or not isinstance(truncated, bool)
            or (next_offset is not None and not _nonnegative_int(next_offset))):
        raise _protocol_error()
    incomplete = total > returned
    if (truncated is not incomplete or (incomplete and (returned != 100 or next_offset != returned))
            or (not incomplete and next_offset is not None)):
        raise _protocol_error()
    notebooks: list[NotebookRef] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"target", "parent", "display_name", "last_modified"}:
            raise _protocol_error()
        target = item["target"]
        if (not isinstance(target, dict) or set(target) != {"backend", "kind", "object_id"}
                or target["backend"] != "desktop_automation" or target["kind"] != "notebook"
                or not _valid_notebook_id(target["object_id"]) or item["parent"] is not None
                or not _valid_text(item["display_name"], maximum=512, maximum_bytes=2048)
                or (item["last_modified"] is not None
                    and not _valid_text(item["last_modified"], maximum=128, maximum_bytes=512))):
            raise _protocol_error()
        object_id = target["object_id"]
        if object_id in seen:
            raise _protocol_error()
        seen.add(object_id)
        notebooks.append(NotebookRef(object_id, item["display_name"]))
    return NotebookList(tuple(notebooks), total, incomplete)


def _parse_search(search: dict[str, object], *, notebook_id: str | None = None) -> SearchResult | OneNoteError:
    matches, returned, total, next_offset, truncated = (
        search.get("matches"), search.get("returned"), search.get("total"), search.get("next_offset"), search.get("truncated")
    )
    if (
        not isinstance(matches, list) or len(matches) > 20 or not _nonnegative_int(returned)
        or not _nonnegative_int(total) or returned != len(matches) or total < returned
        or not isinstance(truncated, bool) or (next_offset is not None and not _nonnegative_int(next_offset))
    ):
        return _protocol_error()
    incomplete = total > returned
    if truncated is not incomplete or (incomplete and next_offset != returned) or (not incomplete and next_offset is not None):
        return _protocol_error()
    pages: list[SearchPage] = []
    seen_ids: set[str] = set()
    for match in matches:
        if not isinstance(match, dict) or set(match) != {"page", "ancestors"}:
            return _protocol_error()
        page, ancestors = match["page"], match["ancestors"]
        if not isinstance(page, dict) or not isinstance(ancestors, list):
            return _protocol_error()
        target = page.get("target")
        object_id = _page_id(target)
        title = page.get("display_name")
        if object_id is None or object_id in seen_ids or not _valid_text(title, maximum=4096, maximum_bytes=16384):
            return _protocol_error()
        breadcrumb = _breadcrumb(ancestors)
        if breadcrumb is None or not ancestors or page.get("parent") != ancestors[-1].get("target"):
            return _protocol_error()
        if notebook_id is not None:
            notebook_ancestors = [ancestor for ancestor in ancestors if ancestor["target"]["kind"] == "notebook"]
            if (len(notebook_ancestors) != 1 or notebook_ancestors[0] is not ancestors[0]
                    or notebook_ancestors[0]["target"]["object_id"] != notebook_id):
                return _protocol_error()
        seen_ids.add(object_id)
        pages.append(SearchPage(object_id, title.strip() or "Untitled page", breadcrumb))
    return SearchResult(tuple(pages), total, incomplete)


def _breadcrumb(ancestors: list[object]) -> tuple[str, ...] | None:
    names: list[str] = []
    previous_target: dict | None = None
    seen_ids: set[str] = set()
    for index, ancestor in enumerate(ancestors):
        if not isinstance(ancestor, dict):
            return None
        target, parent, name = ancestor.get("target"), ancestor.get("parent"), ancestor.get("display_name")
        if (not isinstance(target, dict) or target.get("backend") != "desktop_automation"
                or not isinstance(target.get("kind"), str)
                or target.get("kind") not in {"notebook", "section_group", "section"}):
            return None
        object_id = target.get("object_id")
        if not _valid_text(object_id, nonblank=True, maximum=4096, maximum_bytes=16384) or not _valid_text(name, maximum=4096, maximum_bytes=16384):
            return None
        if object_id in seen_ids:
            return None
        if index == 0:
            if parent is not None:
                return None
        elif parent != previous_target:
            return None
        previous_target = target
        seen_ids.add(object_id)
        names.append(name)
    if ancestors and ancestors[-1].get("target", {}).get("kind") != "section":
        return None
    return tuple(names)


def _page_id(target: object) -> str | None:
    if not isinstance(target, dict) or target.get("backend") != "desktop_automation" or target.get("kind") != "page":
        return None
    value = target.get("object_id")
    return value if _valid_text(value, nonblank=True, maximum=4096, maximum_bytes=16384) else None


def _target_id(target: object) -> str | None:
    if not isinstance(target, dict):
        return None
    value = target.get("object_id")
    return value if _valid_text(value, nonblank=True, maximum=4096, maximum_bytes=16384) else None


def _exact_target(target: object, object_id: str) -> bool:
    return _page_id(target) == object_id


def _valid_text(value: object, *, nonblank: bool = False, maximum: int = 1_000_000, maximum_bytes: int = _MAX_MESSAGE_BYTES) -> bool:
    if not isinstance(value, str) or any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        return False
    return len(value) <= maximum and len(value.encode("utf-8")) <= maximum_bytes and (not nonblank or bool(value.strip()))


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _engine_error(error: dict[str, object]) -> OneNoteError:
    code = error.get("code")
    if not isinstance(code, str) or not _ENGINE_CODE.fullmatch(code):
        return _protocol_error()
    messages = {
        "backend.desktop_dependency_missing": "OneNote desktop setup is unavailable.",
        "backend.desktop_not_running": "Open OneNote, then choose Search to reconnect automatically.",
        "backend.desktop_process_exited": "OneNote changed. Choose Search to reconnect automatically.",
        "backend.desktop_busy": "OneNote is busy. Try again when ready.",
        "backend.desktop_timeout": "OneNote did not respond in time. Try again.",
        "backend.desktop_interface_unsupported": "This OneNote desktop client is unsupported.",
        "backend.desktop_unexpected_start": "OneNote changed unexpectedly; the request stopped.",
        "backend.desktop_explicit_probe_required": "Choose Search to reconnect automatically.",
        "target.not_found": "The chosen notebook or note is unavailable; choose it again.",
        "target.changed": "The chosen notebook or note changed; choose it again.",
        # A valid engine response can report a PIA read failure for a closed or
        # stale scope. It neither proves that cause nor means the launcher broke.
        # Keep this code so readiness is cleared without forcing engine repair.
        "internal.desktop_bridge": _DESKTOP_READ_FAILURE_MESSAGE,
    }
    if code not in messages:
        return OneNoteError("integration.engine_failed", "OneNote integration could not complete the request.")
    return OneNoteError(code, messages[code])


def _valid_error_exit(error: object, returncode: int) -> bool:
    if not isinstance(error, dict):
        return False
    expected = {
        "invalid_request": 2, "unsupported": 3, "conflict": 4,
        "not_found": 5, "operation_failed": 5, "unavailable": 6,
        "internal_error": 70,
    }
    return expected.get(error.get("category")) == returncode


def _protocol_error() -> OneNoteError:
    return OneNoteError("integration.protocol_failed", "OneNote integration returned an invalid response.")
