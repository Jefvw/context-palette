"""Reviewed, one-page OneNote writes. No Office imports or access on import.

Read envelopes remain in onenote_integration. Mutation receipts have their own
strict parser: a failed request may still identify a newly created page.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import time
import unicodedata
from uuid import uuid4

from . import onenote_integration as read
from .persistence import atomic_write_json

PLAN = "plan_create_desktop_page"
EXECUTE = "execute_create_desktop_page"
ACK = "create_one_page_in_exact_section_then_write_reviewed_text_without_navigation"
LIMITS = {"new_page_title_characters": 255, "new_page_title_bytes": 512,
          "new_page_body_characters": 50_000, "new_page_body_bytes": 131_072,
          "new_page_body_lines": 1000, "request_bytes": 1_048_576,
          "response_bytes": 1_048_576, "hierarchy_items": 200, "hierarchy_depth": 8}


class SendError(ValueError):
    """Fixed, non-sensitive message suitable for the Send UI."""


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":"))


def _target(kind, object_id):
    if (not isinstance(kind, str) or kind not in {"notebook", "section_group", "section", "page"}
            or not read._valid_notebook_id(object_id)):
        raise SendError("The destination identity is invalid. Choose the section again.")
    return {"backend": "desktop_automation", "kind": kind, "object_id": object_id}


@dataclass(frozen=True, slots=True)
class Location:
    kind: str
    object_id: str = field(repr=False)
    label: str = field(repr=False)

    def target(self):
        return _target(self.kind, self.object_id)


@dataclass(frozen=True, slots=True)
class Destination:
    path: tuple[Location, ...] = field(repr=False)

    def __post_init__(self):
        if not isinstance(self.path, tuple) or not all(isinstance(p, Location) for p in self.path):
            raise SendError("Choose an exact existing notebook and section.")
        for part in self.path:
            part.target()
        if (not 2 <= len(self.path) <= 10 or self.path[0].kind != "notebook"
                or self.path[-1].kind != "section"
                or any(p.kind != "section_group" for p in self.path[1:-1])
                or len({p.object_id for p in self.path}) != len(self.path)):
            raise SendError("Choose an exact existing notebook and section.")
        for part in self.path:
            part.target()
            if not read._valid_text(part.label, maximum=512, maximum_bytes=2048):
                raise SendError("The destination label is invalid.")

    @property
    def label(self):
        return " / ".join(p.label or "(untitled)" for p in self.path)

    @property
    def section_id(self):
        return self.path[-1].object_id


def save_destination(path: Path, destination: Destination):
    atomic_write_json(path, {"version": 1, "path": [
        {"kind": p.kind, "object_id": p.object_id, "label": p.label}
        for p in destination.path]})


def load_destination(path: Path) -> Destination | None:
    if not path.exists():
        return None
    with path.open("rb") as source:
        value = read._decode_response(source.read(1_048_577))
    if (not isinstance(value, dict) or set(value) != {"version", "path"}
            or type(value["version"]) is not int or value["version"] != 1
            or not isinstance(value["path"], list)):
        raise SendError("The saved Send destination needs reselection.")
    parts = []
    for part in value["path"]:
        if not isinstance(part, dict) or set(part) != {"kind", "object_id", "label"}:
            raise SendError("The saved Send destination needs reselection.")
        parts.append(Location(**part))
    return Destination(tuple(parts))


def normalize_text(title: str, body: str) -> tuple[str, str]:
    if not isinstance(title, str) or not isinstance(body, str):
        raise SendError("Title and page text must be plain text.")
    title = title.strip()
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    try:
        title_bytes, body_bytes = len(title.encode("utf-8")), len(body.encode("utf-8"))
    except UnicodeError:
        raise SendError("The text contains invalid Unicode characters.") from None
    if not title or len(title) > 255 or title_bytes > 512:
        raise SendError("Use a title of 1–255 characters, within 512 UTF-8 bytes.")
    if any(unicodedata.category(c) == "Cc" for c in title):
        raise SendError("Use a single-line title without control characters.")
    if not body.strip():
        raise SendError("Enter text in Input / Output before sending to OneNote.")
    if len(body) > 50_000 or body_bytes > 131_072 or len(body.split("\n")) > 1000:
        raise SendError("Text is too large: use at most 50,000 characters, 128 KiB and 1,000 lines. Nothing was shortened.")
    if any(unicodedata.category(c) == "Cc" and c not in "\t\n" for c in body):
        raise SendError("Page text may contain tabs and line breaks, but no other control characters.")
    return title, body


def suggested_title(body: str) -> str:
    first = next((line.strip() for line in body.splitlines() if line.strip()), "Note")
    first = " ".join(first.split())
    if len(first) > 60:
        excerpt = first[:60]
        boundary = excerpt.rfind(" ")
        first = (excerpt[:boundary] if boundary > 0 else excerpt) + "…"
    return f"{datetime.now():%Y-%m-%d} — {first}"


def canonical_plan(section_id, title, body):
    title, body = normalize_text(title, body)
    section = _target("section", section_id)
    digest = hashlib.sha256(_json({"operation": PLAN, "operation_version": "1.0",
        "section": section, "title": title, "body": body, "content_format": "text/plain",
        "page_position": "last", "page_style": "blank_with_title"}).encode("utf-8")).hexdigest()
    return {"backend": "desktop_automation", "plan": {
        "plan_id": "create-page-" + digest[:24], "capability_id": PLAN,
        "capability_version": "1.0", "backend": "desktop_automation",
        "input_summary": f"Create one reviewed text page ({len(title)} title characters, {len(body)} body characters).",
        "effects": [{"kind": "create", "summary": "Create one reviewed text page as the last page in the exact section.", "target": section}],
        "expected_last_modified": None, "digest": digest},
        "normalized_input": {"section": section, "page": {"title": title, "body": body,
            "content_format": "text/plain", "title_characters": len(title),
            "title_bytes": len(title.encode("utf-8")), "body_characters": len(body),
            "body_bytes": len(body.encode("utf-8"))}},
        "planned_effect": {"kind": "create", "target_section": section, "page_position": "last",
            "page_style": "blank_with_title", "existing_pages_updated": False,
            "existing_pages_deleted": False, "navigation": False, "synchronization_requested": False},
        "execution": {"supported": True, "performed": False, "external_access_performed": False,
                      "page_id_allocated": False}}


@dataclass(frozen=True, slots=True)
class ReviewedPlan:
    destination: Destination = field(repr=False)
    payload: str = field(repr=False)

    def document(self):
        value = read._decode_response(self.payload.encode("utf-8"))
        try:
            page = value["normalized_input"]["page"]
            expected = canonical_plan(self.destination.section_id, page["title"], page["body"])
            if _json(value) != _json(expected):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise SendError("The review changed or is invalid. Make a new review.") from None
        return value

    def authorize(self, now: datetime):
        if now.tzinfo is None or now.utcoffset() is None:
            raise SendError("Confirmation needs an aware timestamp.")
        plan = self.document()["plan"]
        return {"plan_id": plan["plan_id"], "digest": plan["digest"],
                "effect_acknowledgement": ACK, "confirmed_at": now.isoformat(),
                "expires_at": (now + timedelta(seconds=300)).isoformat()}


@dataclass(frozen=True, slots=True)
class SendOutcome:
    state: str
    page_id: str | None = field(default=None, repr=False)
    cleanup_blocked: bool = False

    @property
    def message(self):
        return {
            "none": "No page creation was reported. Check the problem before choosing Send again.",
            "unknown": "A page may have been created. Inspect OneNote before another send; do not send again blindly.",
            "page_created": "A new page exists, but the reviewed text was not applied. Inspect that page before another send.",
            "content_applied_unverified": "A new page exists. Its text could not be verified. Inspect that page before another send.",
            "content_verified": "Page created and verified. Input / Output is unchanged.",
        }[self.state] + (" Process cleanup is unconfirmed. Further OneNote requests are blocked in this session." if self.cleanup_blocked else "")


def parse_receipt(response, request_id, review: ReviewedPlan) -> SendOutcome:
    """Validate mutation envelopes without weakening the read-only parser."""
    code = getattr(response, "returncode", None)
    raw = getattr(response, "stdout", None)
    if type(code) is not int or not isinstance(raw, bytes):
        raise SendError("Invalid execution response.")
    doc = read._decode_response(raw)
    if doc is None:
        raise SendError("Invalid execution response.")
    shell = dict(doc)
    if shell.get("status") == "error":
        shell["result"] = None
    if not read._valid_envelope(shell, request_id, EXECUTE):
        raise SendError("Invalid execution envelope.")
    if doc["warnings"] != [] or doc["artifacts"] != []:
        raise SendError("Unexpected execution warnings or artifacts.")
    result, error = doc["result"], doc["error"]
    if result is None:
        # Only validated, documented pre-execution rejection categories prove
        # no creation. An internal/operation failure without a receipt does not.
        if (doc["status"] == "error" and read._valid_error_exit(error, code)
                and error["category"] in {"invalid_request", "unsupported", "conflict", "not_found", "unavailable"}
                and read._ENGINE_CODE.fullmatch(error["code"]) and len(error["code"]) <= 128):
            return SendOutcome("none")
        raise SendError("No execution receipt.")
    if not isinstance(result, dict):
        raise SendError("Invalid execution receipt.")
    states = {"none": ("failed", None, False, False),
              "unknown": ("failed", None, None, False),
              "page_created": ("partial", "page", False, False),
              "content_applied_unverified": ("partial", "page", None, False),
              "content_verified": ("success", "page", True, True)}
    state = result.get("commit_state")
    if not isinstance(state, str) or state not in states:
        raise SendError("Invalid execution state.")
    outcome, page_kind, applied, verified = states[state]
    page = result.get("created_page")
    if page_kind:
        if not isinstance(page, dict) or page != _target("page", page.get("object_id")):
            raise SendError("Invalid created-page identity.")
    elif page is not None:
        raise SendError("Unexpected created-page identity.")
    error_code = result.get("error_code")
    if verified:
        if doc["status"] != "success" or code != 0 or error_code is not None:
            raise SendError("Execution success mismatch.")
    elif (doc["status"] != "error" or code != 5 or error["category"] != "operation_failed"
          or not isinstance(error_code, str) or len(error_code) > 128
          or not read._ENGINE_CODE.fullmatch(error_code) or error["code"] != error_code
          or error["retryable"] is not False):
        raise SendError("Execution error mismatch.")
    expected = {"outcome": outcome, "commit_state": state,
        "target_section": _target("section", review.destination.section_id), "created_page": page,
        "content_applied": applied, "content_verified": verified, "error_code": error_code,
        "retryable": False, "automatic_rollback_attempted": False,
        "automatic_delete_attempted": False, "navigation_performed": False}
    if _json(result) != _json(expected):
        raise SendError("Execution effects mismatch.")
    return SendOutcome(state, page["object_id"] if page else None)


class OneNoteSendClient(read.OneNoteClient):
    def __init__(self, launcher_path, runner=None, write_runner=None):
        super().__init__(launcher_path, runner)
        self._write_runner = write_runner or _write_runner
        self._described = False
        self._session = None

    def _request(self, operation, arguments, cancel, timeout=30):
        response = self._call(operation, arguments, timeout, cancel)
        if isinstance(response, read.OneNoteError):
            if response.code == "transport.cleanup":
                raise response
            raise SendError("OneNote could not complete this step. Check the engine and open notebook, then choose the destination again. No Send was issued.")
        return response

    def describe_send(self, cancel):
        response = self._request("describe_capabilities", {}, cancel, 10)
        caps = response.get("capabilities")
        limits = response.get("limits")
        if not isinstance(caps, list) or not isinstance(limits, dict):
            raise SendError("This engine does not advertise the required Send contract.")
        by_id = {}
        for cap in caps:
            if not isinstance(cap, dict) or not isinstance(cap.get("capability_id"), str) or cap["capability_id"] in by_id:
                raise SendError("Invalid engine capability list.")
            by_id[cap["capability_id"]] = cap
        for operation, backend, requires, execution, planning in (
            (PLAN, "core", False, "synchronous", True),
            (EXECUTE, "desktop_automation", True, "worker_process", False),
        ):
            cap = by_id.get(operation, {})
            expected = {"version": "1.0", "implementation_state": "implemented", "safety": "create",
                        "backend": backend, "target_kinds": ["section"], "requires_plan": requires,
                        "host_execution": execution, "planning_only": planning,
                        "follow_on_execution_available": True}
            if (any(_json(cap.get(k)) != _json(v) for k, v in expected.items())
                    or type(cap.get("available")) is not bool
                    or (planning and cap["available"] is not True)):
                raise SendError("This engine does not support reviewed text-page creation.")
        if not read._valid_probe_capability(by_id.get("probe_desktop_read_backend", {})):
            raise SendError("This engine cannot check the running OneNote session.")
        if any(type(limits.get(k)) is not int or limits[k] < v for k, v in LIMITS.items()):
            raise SendError("This engine's Send limits are incompatible.")
        self._described = True

    def prepare(self, session_reader, cancel):
        _check(cancel)
        if not self._described:
            self.describe_send(cancel)
        before = session_reader()
        if not before:
            raise SendError("Open OneNote and the chosen notebook, then choose the destination again.")
        if self._session != before:
            ready = self.probe(cancel_event=cancel)
            if "inventory_desktop_hierarchy" not in ready.ready_capabilities:
                raise SendError("This engine cannot list notebook sections.")
        _check(cancel)
        if session_reader() != before:
            self._session = None
            raise SendError("OneNote changed during setup. Choose the destination again.")
        self._session = before
        return before

    def inventory(self, notebook: Location | None, cancel, *, deadline=None):
        """Bounded pages; exact ancestry includes the omitted request anchor."""
        deadline = deadline or time.monotonic() + 90
        offset, total = 0, None
        known = {notebook.object_id: (notebook,)} if notebook else {}
        entries = []
        while True:
            _check(cancel)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SendError("Listing sections took too long. No Send was issued.")
            response = self._request("inventory_desktop_hierarchy", {
                "effect_acknowledgement": "attach_to_running_onenote_and_read_hierarchy",
                "start_object_id": notebook.object_id if notebook else None,
                "start_kind": "notebook" if notebook else None,
                "scope": "sections" if notebook else "notebooks",
                "offset": offset, "limit": 200, "max_depth": 8}, cancel, min(30, remaining))
            if (set(response) != {"backend", "probe", "hierarchy"}
                    or response["backend"] != "desktop_automation"
                    or not read._valid_probe_result(response["probe"], "inventory")):
                raise SendError("Invalid notebook inventory response.")
            value = response["hierarchy"]
            if not isinstance(value, dict) or set(value) != {"items", "returned", "total", "next_offset", "truncated"}:
                raise SendError("Invalid inventory page.")
            items, count, next_offset = value["items"], value["total"], value["next_offset"]
            if (not isinstance(items, list) or len(items) > 200 or type(value["returned"]) is not int
                    or value["returned"] != len(items) or type(count) is not int
                    or not offset + len(items) <= count <= 5000
                    or (total is not None and total != count) or type(value["truncated"]) is not bool):
                raise SendError("The inventory changed or exceeded its bounds. Choose the destination again.")
            total = count
            expected_next = offset + len(items) if offset + len(items) < total else None
            if (type(next_offset) is not type(expected_next) or next_offset != expected_next
                    or (next_offset is not None and (not items or value["truncated"] is not True))):
                raise SendError("Invalid inventory paging.")
            for item in items:
                if not isinstance(item, dict) or set(item) != {"target", "parent", "display_name", "last_modified"}:
                    raise SendError("Invalid inventory item.")
                target, parent = item["target"], item["parent"]
                if not isinstance(target, dict):
                    raise SendError("Invalid inventory identity.")
                kind, object_id = target.get("kind"), target.get("object_id")
                if (target != _target(kind, object_id) or object_id in known
                        or not read._valid_text(item["display_name"], maximum=512, maximum_bytes=2048)
                        or (item["last_modified"] is not None and not read._valid_text(item["last_modified"], maximum=128))):
                    raise SendError("Invalid or repeated inventory identity.")
                part = Location(kind, object_id, item["display_name"])
                if notebook is None:
                    if kind != "notebook" or parent is not None:
                        raise SendError("Invalid notebook ancestry.")
                    path = (part,)
                else:
                    ancestor = known.get(parent.get("object_id")) if isinstance(parent, dict) else None
                    if (kind not in {"section_group", "section"} or not ancestor
                            or ancestor[-1].kind not in {"notebook", "section_group"}
                            or parent != ancestor[-1].target()):
                        raise SendError("The section is outside the selected notebook or its ancestry is incomplete.")
                    path = (*ancestor, part)
                known[object_id] = path
                if notebook is None:
                    entries.append(part)
                elif kind == "section":
                    entries.append(Destination(path))
            if next_offset is None:
                if value["truncated"]:
                    raise SendError("This list is incomplete (hierarchy depth limit). No destination was selected. Use a section within eight levels.")
                return tuple(entries)
            offset = next_offset

    def plan(self, destination, title, body, cancel):
        expected = canonical_plan(destination.section_id, title, body)
        if not self._described:
            self.describe_send(cancel)
        response = self._request(PLAN, {"section_object_id": destination.section_id,
                                       "title": title, "body": body}, cancel, 10)
        if _json(response) != _json(expected):
            raise SendError("The engine returned a different plan. Nothing was sent.")
        return ReviewedPlan(destination, _json(response))

    def execute(self, review, authorization, cancel):
        """Exactly one transport attempt; caller consumes the review before entry."""
        document = review.document()
        now = datetime.now(timezone.utc)
        try:
            confirmed = datetime.fromisoformat(authorization["confirmed_at"])
            expires = datetime.fromisoformat(authorization["expires_at"])
            if (authorization != review.authorize(confirmed) or not confirmed <= now < expires):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise SendError("Confirmation expired or changed. Review the text again.") from None
        _check(cancel)
        request_id = uuid4().hex
        payload = read._encode_request({"schema_version": "1.0", "operation_version": "1.0",
            "request_id": request_id, "operation": EXECUTE,
            "arguments": {"reviewed_plan": document, "review_authorization": authorization}})
        try:
            response = self._write_runner(self.launcher_path, payload, 45, cancel)
        except Exception as exc:
            blocked = getattr(exc, "code", None) == "transport.cleanup"
            retained = getattr(exc, "response", None)
            if retained is not None:
                try:
                    return replace(parse_receipt(retained, request_id, review), cleanup_blocked=blocked)
                except (SendError, TypeError, ValueError):
                    pass
            # Unknown exception types cannot prove that no input was released.
            from .onenote_process import OwnedProcessError
            before = isinstance(exc, OwnedProcessError) and not exc.dispatched and not blocked
            return SendOutcome("none" if before else "unknown", cleanup_blocked=blocked)
        try:
            return parse_receipt(response, request_id, review)
        except Exception:
            # After a transport attempt, an unrecognized response/parser failure
            # cannot prove absence of a write. Never expose read-style retries.
            return SendOutcome("unknown")


def _check(cancel):
    if cancel.is_set():
        raise SendError("Cancelled before Send. No execution request was issued.")


def _write_runner(launcher, payload, timeout, cancel):
    from .onenote_process import run_owned_write_request
    return run_owned_write_request(launcher, payload, timeout=timeout, cancel_event=cancel)
