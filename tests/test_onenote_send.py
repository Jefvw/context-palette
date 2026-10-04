"""Strict synthetic checks for the reviewed OneNote Send protocol.

No test imports the engine or accesses Office.  The one Windows subprocess test
uses a disposable local launcher/child to exercise Context Palette's native
owned-process transport.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from context_palette import onenote_process
from context_palette.onenote_process import OwnedProcessError, ProcessResult
from context_palette.onenote_send import (
    EXECUTE,
    LIMITS,
    Destination,
    Location,
    OneNoteSendClient,
    ReviewedPlan,
    SendError,
    canonical_plan,
    load_destination,
    normalize_text,
    parse_receipt,
    save_destination,
)


SECTION_ID = "section-α"
PAGE_ID = "created-page-β"
NORMALIZED_TITLE = "Café note"
NORMALIZED_BODY = "Line 1\n\t日本語\n\nFinal "
GOLDEN_DIGEST = "b171b1e63b9cd6d96a1557d69994156f721c409a0c795d6fe6cfa81fe6263ad2"


def target(kind: str, object_id: str) -> dict[str, str]:
    return {"backend": "desktop_automation", "kind": kind, "object_id": object_id}


def destination() -> Destination:
    return Destination(
        (
            Location("notebook", "book-1", "Private notebook"),
            Location("section_group", "group-1", "Private group"),
            Location("section", SECTION_ID, "Private section"),
        )
    )


def golden_plan() -> dict[str, object]:
    """Independent fixed engine-v1 fixture; do not build through host helpers."""

    section = target("section", SECTION_ID)
    return {
        "backend": "desktop_automation",
        "plan": {
            "plan_id": "create-page-b171b1e63b9cd6d96a1557d6",
            "capability_id": "plan_create_desktop_page",
            "capability_version": "1.0",
            "backend": "desktop_automation",
            "input_summary": "Create one reviewed text page (9 title characters, 19 body characters).",
            "effects": [
                {
                    "kind": "create",
                    "summary": "Create one reviewed text page as the last page in the exact section.",
                    "target": section,
                }
            ],
            "expected_last_modified": None,
            "digest": GOLDEN_DIGEST,
        },
        "normalized_input": {
            "section": section,
            "page": {
                "title": NORMALIZED_TITLE,
                "body": NORMALIZED_BODY,
                "content_format": "text/plain",
                "title_characters": 9,
                "title_bytes": 10,
                "body_characters": 19,
                "body_bytes": 25,
            },
        },
        "planned_effect": {
            "kind": "create",
            "target_section": section,
            "page_position": "last",
            "page_style": "blank_with_title",
            "existing_pages_updated": False,
            "existing_pages_deleted": False,
            "navigation": False,
            "synchronization_requested": False,
        },
        "execution": {
            "supported": True,
            "performed": False,
            "external_access_performed": False,
            "page_id_allocated": False,
        },
    }


def review() -> ReviewedPlan:
    return ReviewedPlan(
        destination(),
        json.dumps(golden_plan(), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )


def envelope(
    request_id: str,
    *,
    result: object,
    status: str = "success",
    error: object = None,
    warnings: list[object] | None = None,
    artifacts: list[object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_id": request_id,
        "operation": EXECUTE,
        "operation_version": "1.0",
        "status": status,
        "duration_ms": 1,
        "result": result,
        "warnings": [] if warnings is None else warnings,
        "artifacts": [] if artifacts is None else artifacts,
        "error": error,
    }


def error(code: str, category: str = "operation_failed") -> dict[str, object]:
    return {
        "code": code,
        "category": category,
        "message": "The operation did not verify completion.",
        "retryable": False,
        "details": {},
    }


def receipt(state: str) -> dict[str, object]:
    matrix = {
        "none": ("failed", None, False, False),
        "unknown": ("failed", None, None, False),
        "page_created": ("partial", target("page", PAGE_ID), False, False),
        "content_applied_unverified": (
            "partial",
            target("page", PAGE_ID),
            None,
            False,
        ),
        "content_verified": ("success", target("page", PAGE_ID), True, True),
    }
    outcome, page, applied, verified = matrix[state]
    failure = None if verified else "operation.synthetic_failure"
    return {
        "outcome": outcome,
        "commit_state": state,
        "target_section": target("section", SECTION_ID),
        "created_page": page,
        "content_applied": applied,
        "content_verified": verified,
        "error_code": failure,
        "retryable": False,
        "automatic_rollback_attempted": False,
        "automatic_delete_attempted": False,
        "navigation_performed": False,
    }


def response(document: dict[str, object], returncode: int) -> ProcessResult:
    return ProcessResult(json.dumps(document, ensure_ascii=False).encode("utf-8"), returncode)


INVENTORY_PROBE = {
    "effect": "attach_to_running_onenote_and_read_hierarchy",
    "attached_to_running_instance": True,
    "started_client": False,
    "navigated": False,
    "synchronized": False,
    "schema": "xs2013",
}


def hierarchy_page(items, total, next_offset, truncated):
    return {
        "backend": "desktop_automation",
        "probe": dict(INVENTORY_PROBE),
        "hierarchy": {
            "items": items,
            "returned": len(items),
            "total": total,
            "next_offset": next_offset,
            "truncated": truncated,
        },
    }


def hierarchy_item(kind, object_id, parent_kind, parent_id, label):
    return {
        "target": target(kind, object_id),
        "parent": target(parent_kind, parent_id) if parent_id is not None else None,
        "display_name": label,
        "last_modified": None,
    }


def capability_description(execute_available=False):
    common = {
        "version": "1.0",
        "implementation_state": "implemented",
        "safety": "create",
        "target_kinds": ["section"],
        "follow_on_execution_available": True,
    }
    return {
        "capabilities": [
            {
                "capability_id": "probe_desktop_read_backend",
                "version": "1.0",
                "backend": "desktop_automation",
                "safety": "read_only",
                "available": True,
                "requires_plan": False,
                "planning_only": False,
                "host_execution": "worker_process",
            },
            {
                **common,
                "capability_id": "plan_create_desktop_page",
                "backend": "core",
                "available": True,
                "requires_plan": False,
                "host_execution": "synchronous",
                "planning_only": True,
            },
            {
                **common,
                "capability_id": EXECUTE,
                "backend": "desktop_automation",
                "available": execute_available,
                "requires_plan": True,
                "host_execution": "worker_process",
                "planning_only": False,
            },
        ],
        "limits": dict(LIMITS),
    }


class CanonicalContractTests(unittest.TestCase):
    def test_character_byte_and_line_boundaries_preserve_complete_text(self):
        for title, body in (("x" * 255, "x" * 50_000),
                            ("é" * 255, "x" + "\n" * 999),
                            ("ok", "🎸" * 32_768)):
            self.assertEqual(normalize_text(title, body), (title, body))
        for title, body in (("🎸" * 129, "ok"), ("ok", "x" * 50_001),
                            ("ok", "🎸" * 32_769), ("ok", " \t\n")):
            with self.subTest(title=title[:4], length=len(body)), self.assertRaises(SendError):
                normalize_text(title, body)
    def test_normalization_and_digest_match_independent_golden_fixture(self):
        title, body = normalize_text(
            "  Café note  ", "Line 1\r\n\t日本語\r\r\nFinal "
        )
        self.assertEqual((title, body), (NORMALIZED_TITLE, NORMALIZED_BODY))
        self.assertEqual(
            canonical_plan(SECTION_ID, "  Café note  ", "Line 1\r\n\t日本語\r\r\nFinal "),
            golden_plan(),
        )
        self.assertEqual(golden_plan()["plan"]["digest"], GOLDEN_DIGEST)

    def test_normalization_rejects_wrong_types_controls_surrogates_and_limits(self):
        cases = (
            (True, "body"),
            ("Title", False),
            ("bad\ttitle", "body"),
            ("Title", "bad\x00body"),
            ("Title", "bad\ud800body"),
            ("x" * 256, "body"),
            ("Title", "line\n" * 1000),
        )
        for title, body in cases:
            with self.subTest(title=repr(title)[:30], body=repr(body)[:30]):
                with self.assertRaises(SendError):
                    normalize_text(title, body)

    def test_review_rejects_strict_type_changes_and_malicious_effects(self):
        mutations = []
        value = golden_plan()
        value["normalized_input"]["page"]["title_characters"] = True
        mutations.append(value)
        value = golden_plan()
        value["planned_effect"]["navigation"] = True
        mutations.append(value)
        value = golden_plan()
        value["plan"]["effects"].append(
            {"kind": "update", "summary": "Overwrite another page.", "target": target("page", "victim")}
        )
        mutations.append(value)
        value = golden_plan()
        value["execution"]["performed"] = 0
        mutations.append(value)
        value = golden_plan()
        value["planned_effect"]["existing_pages_deleted"] = True
        mutations.append(value)
        for value in mutations:
            candidate = ReviewedPlan(
                destination(),
                json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            )
            with self.subTest(value=value):
                with self.assertRaises(SendError):
                    candidate.document()


class CapabilityAndInventoryTests(unittest.TestCase):
    def test_static_execute_available_false_is_expected_and_accepted(self):
        client = OneNoteSendClient(Path("C:/synthetic/python-onenote.bat"), runner=Mock())
        with patch.object(client, "_request", return_value=capability_description(False)):
            client.describe_send(threading.Event())
        self.assertTrue(client._described)

    def test_capability_bool_is_strict_and_limits_cannot_shrink(self):
        client = OneNoteSendClient(Path("C:/synthetic/python-onenote.bat"), runner=Mock())
        bad = capability_description(False)
        bad["capabilities"][2]["available"] = 0
        with patch.object(client, "_request", return_value=bad):
            with self.assertRaises(SendError):
                client.describe_send(threading.Event())
        bad = capability_description(False)
        bad["limits"]["new_page_body_bytes"] -= 1
        with patch.object(client, "_request", return_value=bad):
            with self.assertRaises(SendError):
                client.describe_send(threading.Event())

    def test_inventory_keeps_cross_page_ancestry_at_the_200_item_boundary(self):
        book = Location("notebook", "book-1", "Book")
        first = [
            hierarchy_item("section_group", f"sibling-{index}", "notebook", "book-1", f"Group {index}")
            for index in range(199)
        ]
        first.append(hierarchy_item("section_group", "boundary", "notebook", "book-1", "Boundary"))
        second = [hierarchy_item("section", SECTION_ID, "section_group", "boundary", "Section")]
        pages = iter(
            (
                hierarchy_page(first, 201, 200, True),
                hierarchy_page(second, 201, None, False),
            )
        )
        client = OneNoteSendClient(Path("C:/synthetic/python-onenote.bat"), runner=Mock())
        with patch.object(client, "_request", side_effect=lambda *_a, **_k: next(pages)):
            result = client.inventory(book, threading.Event(), deadline=time.monotonic() + 10)
        self.assertEqual(len(result), 1)
        self.assertEqual(
            [(part.kind, part.object_id) for part in result[0].path],
            [("notebook", "book-1"), ("section_group", "boundary"), ("section", SECTION_ID)],
        )

    def test_inventory_rejects_changed_totals_cross_page_parent_and_depth_truncation(self):
        book = Location("notebook", "book-1", "Book")
        first = [
            hierarchy_item("section_group", f"group-{index}", "notebook", "book-1", f"Group {index}")
            for index in range(200)
        ]
        cases = (
            (
                hierarchy_page(first, 201, 200, True),
                hierarchy_page(
                    [hierarchy_item("section", SECTION_ID, "section_group", "group-199", "Section")],
                    202,
                    201,
                    True,
                ),
            ),
            (
                hierarchy_page(first, 201, 200, True),
                hierarchy_page(
                    [hierarchy_item("section", SECTION_ID, "section_group", "missing", "Section")],
                    201,
                    None,
                    False,
                ),
            ),
            (
                hierarchy_page(
                    [hierarchy_item("section", SECTION_ID, "notebook", "book-1", "Section")],
                    1,
                    None,
                    True,
                ),
            ),
        )
        for pages in cases:
            client = OneNoteSendClient(Path("C:/synthetic/python-onenote.bat"), runner=Mock())
            values = iter(pages)
            with self.subTest(pages=len(pages)), patch.object(
                client, "_request", side_effect=lambda *_a, **_k: next(values)
            ):
                with self.assertRaises(SendError):
                    client.inventory(book, threading.Event(), deadline=time.monotonic() + 10)


class DestinationSettingsTests(unittest.TestCase):
    def test_destination_round_trip_is_private_and_separate(self):
        chosen = destination()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "local_onenote_send_destination.json"
            save_destination(path, chosen)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(saved), {"version", "path"})
            self.assertNotIn("launcher_path", saved)
            self.assertNotIn("notebook", saved)
            self.assertEqual(load_destination(path), chosen)
        self.assertNotIn(SECTION_ID, repr(chosen))
        self.assertNotIn("Private section", repr(chosen))

    def test_destination_settings_fail_closed_on_unknown_or_duplicate_identity(self):
        documents = (
            {"version": 1, "path": [], "extra": True},
            {"version": True, "path": []},
            {"version": 1, "path": [{"kind": [], "object_id": [], "label": False}]},
            {
                "version": 1,
                "path": [
                    {"kind": "notebook", "object_id": "same", "label": "Book"},
                    {"kind": "section", "object_id": "same", "label": "Section"},
                ],
            },
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            for document in documents:
                with self.subTest(document=document):
                    path.write_text(json.dumps(document), encoding="utf-8")
                    with self.assertRaises(SendError):
                        load_destination(path)


class ReceiptTests(unittest.TestCase):
    def test_all_five_terminal_states_are_preserved(self):
        for state in (
            "none",
            "unknown",
            "page_created",
            "content_applied_unverified",
            "content_verified",
        ):
            value = receipt(state)
            verified = state == "content_verified"
            document = envelope(
                "request-1",
                result=value,
                status="success" if verified else "error",
                error=None if verified else error(value["error_code"]),
            )
            parsed = parse_receipt(response(document, 0 if verified else 5), "request-1", review())
            self.assertEqual(parsed.state, state)
            self.assertEqual(parsed.page_id, PAGE_ID if value["created_page"] else None)

    def test_valid_null_result_preexecution_errors_are_none(self):
        for category, exit_code in (
            ("invalid_request", 2),
            ("unsupported", 3),
            ("conflict", 4),
            ("not_found", 5),
            ("unavailable", 6),
        ):
            document = envelope(
                "request-1",
                result=None,
                status="error",
                error=error(f"request.synthetic_{category}", category),
            )
            self.assertEqual(
                parse_receipt(response(document, exit_code), "request-1", review()).state,
                "none",
            )

    def test_null_internal_or_missing_error_and_exit_mismatch_are_rejected(self):
        cases = (
            response(
                envelope(
                    "request-1",
                    result=None,
                    status="error",
                    error=error("internal.synthetic", "internal_error"),
                ),
                70,
            ),
            response(envelope("request-1", result=None, status="error", error=None), 5),
            response(
                envelope(
                    "request-1",
                    result=receipt("unknown"),
                    status="error",
                    error=error("operation.synthetic_failure"),
                ),
                4,
            ),
        )
        for completed in cases:
            with self.subTest(returncode=completed.returncode):
                with self.assertRaises(SendError):
                    parse_receipt(completed, "request-1", review())

    def test_malformed_effects_and_nonempty_protocol_lists_are_rejected(self):
        malformed = []
        value = receipt("content_verified")
        value["automatic_delete_attempted"] = True
        malformed.append(envelope("request-1", result=value))
        value = receipt("content_verified")
        value["target_section"] = target("section", "other-section")
        malformed.append(envelope("request-1", result=value))
        malformed.append(
            envelope("request-1", result=receipt("content_verified"), warnings=[{"code": "x"}])
        )
        malformed.append(
            envelope("request-1", result=receipt("content_verified"), artifacts=[{"kind": "x"}])
        )
        for document in malformed:
            with self.subTest(document=document):
                with self.assertRaises(SendError):
                    parse_receipt(response(document, 0), "request-1", review())


class ExecuteTests(unittest.TestCase):
    def test_invalid_or_lost_response_is_unknown_after_transport_attempt(self):
        for raw in (b'', b'{"status":"success","status":"error"}',
                    b'{}\n{}', b'\xff', b' ' * 1_048_577):
            client = OneNoteSendClient(Path("C:/synthetic/python-onenote.bat"),
                write_runner=Mock(return_value=ProcessResult(raw, 0)))
            outcome = client.execute(review(), review().authorize(datetime.now(timezone.utc)), threading.Event())
            self.assertEqual(outcome.state, "unknown")
    def test_expired_changed_and_cancelled_authorization_never_reaches_runner(self):
        runner = Mock()
        client = OneNoteSendClient(
            Path("C:/synthetic/python-onenote.bat"), runner=Mock(), write_runner=runner
        )
        old = datetime.now(timezone.utc) - timedelta(minutes=6)
        with self.assertRaises(SendError):
            client.execute(review(), review().authorize(old), threading.Event())
        changed = review().authorize(datetime.now(timezone.utc))
        changed["digest"] = "0" * 64
        with self.assertRaises(SendError):
            client.execute(review(), changed, threading.Event())
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(SendError):
            client.execute(
                review(), review().authorize(datetime.now(timezone.utc)), cancelled
            )
        runner.assert_not_called()

    def test_injected_transport_failures_preserve_dispatch_certainty(self):
        cases = (
            (OwnedProcessError("transport.launch", dispatched=False), "none", False),
            (OwnedProcessError("transport.timeout", dispatched=True), "unknown", False),
            (ValueError("synthetic private failure"), "unknown", False),
        )
        for failure, state, blocked in cases:
            client = OneNoteSendClient(
                Path("C:/synthetic/python-onenote.bat"),
                runner=Mock(),
                write_runner=Mock(side_effect=failure),
            )
            outcome = client.execute(
                review(), review().authorize(datetime.now(timezone.utc)), threading.Event()
            )
            self.assertEqual((outcome.state, outcome.cleanup_blocked), (state, blocked))

    def test_cleanup_failure_retains_a_valid_terminal_receipt(self):
        now = datetime.now(timezone.utc)
        authorization = review().authorize(now)
        def failing(_launcher, payload, _timeout, _cancel):
            request = json.loads(payload)
            document = envelope(request["request_id"], result=receipt("content_verified"))
            retained = response(document, 0)
            raise OwnedProcessError(
                "transport.cleanup", dispatched=True, response=retained
            )

        client = OneNoteSendClient(
            Path("C:/synthetic/python-onenote.bat"), runner=Mock(), write_runner=failing
        )
        outcome = client.execute(review(), authorization, threading.Event())
        self.assertEqual(outcome.state, "content_verified")
        self.assertTrue(outcome.cleanup_blocked)

    @unittest.skipUnless(sys.platform == "win32", "native owned transport is Windows-only")
    def test_default_execute_uses_native_write_transport_with_45_second_route(self):
        onenote_process._cleanup_uncertain.clear()
        child = r'''import json, sys
request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
section = request["arguments"]["reviewed_plan"]["normalized_input"]["section"]
result = {
    "outcome": "success", "commit_state": "content_verified",
    "target_section": section,
    "created_page": {"backend": "desktop_automation", "kind": "page", "object_id": "created-page-β"},
    "content_applied": True, "content_verified": True, "error_code": None,
    "retryable": False, "automatic_rollback_attempted": False,
    "automatic_delete_attempted": False, "navigation_performed": False,
}
response = {
    "schema_version": "1.0", "request_id": request["request_id"],
    "operation": request["operation"], "operation_version": "1.0",
    "status": "success", "duration_ms": 1, "result": result,
    "warnings": [], "artifacts": [], "error": None,
}
sys.stdout.buffer.write(json.dumps(response, ensure_ascii=True).encode("utf-8"))
'''
        with tempfile.TemporaryDirectory(prefix="onenote send 日本語 ") as temporary:
            root = Path(temporary)
            launcher = root / "python-onenote.bat"
            script = root / "synthetic.py"
            script.write_text(child, encoding="utf-8")
            launcher.write_text(
                '@echo off\r\n"' + sys._base_executable + '" "%~dp0synthetic.py" %*\r\n',
                encoding="utf-8",
            )
            original = onenote_process.run_owned_write_request
            observed = []

            def checked_native(*args, **kwargs):
                timeout = kwargs.get("timeout")
                try:
                    completed = original(*args, **kwargs)
                except OwnedProcessError as exc:
                    observed.append((timeout, exc.code, exc.dispatched, exc.response))
                    raise
                observed.append((timeout, completed.returncode, completed.stdout))
                return completed

            client = OneNoteSendClient(launcher)
            with patch.object(
                onenote_process, "run_owned_write_request", side_effect=checked_native
            ):
                outcome = client.execute(
                    review(),
                    review().authorize(datetime.now(timezone.utc)),
                    threading.Event(),
                )
            self.assertEqual(outcome.state, "content_verified", observed)
            self.assertEqual(observed[0][0], 45)
        self.assertFalse(onenote_process._cleanup_uncertain.is_set())


if __name__ == "__main__":
    unittest.main()
