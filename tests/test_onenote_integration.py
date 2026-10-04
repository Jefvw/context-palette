from __future__ import annotations

import json
import copy
from types import SimpleNamespace
from pathlib import Path
import tempfile
import unittest

from context_palette.onenote_integration import (
    NotebookRef,
    OneNoteClient,
    OneNoteError,
    OneNoteSettings,
    OneNoteSettingsError,
    load_onenote_settings,
    save_onenote_settings,
    discover_direct_sibling_python_onenote_launcher,
)


class _Result:
    def __init__(self, document: object, returncode: int = 0) -> None:
        self.stdout = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode()
        self.returncode = returncode


class OneNoteIntegrationTests(unittest.TestCase):
    def test_discovery_checks_only_exact_direct_sibling(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            application = root / "installed" / "Context Palette"
            application.mkdir(parents=True)
            ancestor_engine = root / "python-onenote" / "python-onenote.bat"
            ancestor_engine.parent.mkdir()
            ancestor_engine.write_text("never run")
            self.assertIsNone(discover_direct_sibling_python_onenote_launcher(application))
            self.assertIsNone(discover_direct_sibling_python_onenote_launcher(Path("relative")))
            candidate = application.parent / "python-onenote" / "python-onenote.bat"
            candidate.parent.mkdir()
            candidate.mkdir()
            self.assertIsNone(discover_direct_sibling_python_onenote_launcher(application))
            candidate.rmdir()
            candidate.write_text("never run")
            self.assertEqual(discover_direct_sibling_python_onenote_launcher(application), candidate)

    def test_discovery_inaccessible_candidate_is_unavailable(self):
        from unittest.mock import patch
        with patch.object(Path, "is_file", side_effect=OSError()):
            self.assertIsNone(discover_direct_sibling_python_onenote_launcher(Path("C:/installed/context-palette")))

    def test_invalid_explicit_launcher_error_retains_valid_notebook_privately(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            notebook = NotebookRef("Opaque-Case", "Private notebook")
            for invalid in ("relative/python-onenote.bat", "C:/wrong.exe", 7):
                path.write_text(json.dumps({"launcher_path": invalid, "notebook": {
                    "object_id": notebook.object_id, "title": notebook.title}}), encoding="utf-8")
                with self.subTest(kind=type(invalid)), self.assertRaises(OneNoteSettingsError) as caught:
                    load_onenote_settings(path)
                self.assertEqual(caught.exception.notebook, notebook)
                self.assertNotIn("Private notebook", repr(caught.exception))

    def _client(self, response: object, code: int = 0) -> OneNoteClient:
        def runner(_path: Path, request: bytes, timeout: float, cancel_event: object) -> _Result:
            self.request = json.loads(request.decode("utf-8"))
            self.timeout = timeout
            self.cancel_event = cancel_event
            document = response(self.request) if callable(response) else response
            return _Result(document, code)

        return OneNoteClient(Path("C:/engine/python-onenote.bat"), runner)

    def _envelope(self, request: dict[str, object], result: dict[str, object]) -> dict[str, object]:
        return {
            "schema_version": "1.0", "request_id": request["request_id"],
            "operation": request["operation"], "operation_version": "1.0",
            "status": "success", "duration_ms": 1, "result": result,
            "warnings": [], "artifacts": [], "error": None,
        }

    def test_describe_and_probe_accept_only_documented_readiness_evidence(self) -> None:
        client = self._client(lambda request: self._envelope(request, {
            "backends": [{"backend": "desktop_automation", "state": "unverified"}],
            "capabilities": [{"capability_id": "probe_desktop_read_backend", "available": True,
                                "version": "1.0", "backend": "desktop_automation", "safety": "read_only",
                                "requires_plan": False, "planning_only": False, "host_execution": "worker_process"}],
        }))
        self.assertTrue(client.describe().can_probe)  # type: ignore[union-attr]

        client = self._client(lambda request: self._envelope(request, {
            "backend": "desktop_automation", "state": "available", "available": True,
            "checked_by": "active_probe", "external_access_performed": True,
            "evidence": {"adapter_id": "windows_pia_subprocess", "adapter_version": "1.0", "pia_version": "15.0.0.0", "attached_to_existing_process": True, "started_client": False,
                         "schema": "xs2013", "lifecycle": "operation_owned", "apartment": "STA"},
            "ready_capabilities": ["search_desktop_pages", "preview_desktop_page"],
        }))
        readiness = client.probe()
        self.assertTrue(readiness.can_search)  # type: ignore[union-attr]
        self.assertTrue(readiness.can_preview)  # type: ignore[union-attr]

    def test_search_sends_first_slice_and_accepts_section_root_breadcrumb(self) -> None:
        def response(request: dict[str, object]) -> dict[str, object]:
            return self._envelope(request, {"backend": "desktop_automation", "probe": {
                "effect": "attach_to_running_onenote_and_search_pages_without_display",
                "attached_to_running_instance": True, "started_client": False,
                "displayed_search": False, "navigated": False, "synchronized": False,
                "schema": "xs2013",
            }, "search": {"matches": [{"page": {
                "target": {"backend": "desktop_automation", "kind": "page", "object_id": "Page-A"},
                "display_name": "", "parent": {"backend": "desktop_automation", "kind": "section", "object_id": "Section-A"},
            }, "ancestors": [{
                "target": {"backend": "desktop_automation", "kind": "section", "object_id": "Section-A"},
                "parent": None, "display_name": "Section", "last_modified": None,
            }]}], "returned": 1, "total": 3, "next_offset": 1, "truncated": True}})

        result = self._client(response).search("  review \U0001f4dd")
        self.assertEqual(result.pages[0].object_id, "Page-A")  # type: ignore[union-attr]
        self.assertEqual(result.pages[0].title, "Untitled page")  # type: ignore[union-attr]
        self.assertEqual(result.pages[0].breadcrumb, ("Section",))  # type: ignore[union-attr]
        self.assertTrue(result.truncated)  # type: ignore[union-attr]
        self.assertEqual(self.request["arguments"], {
            "effect_acknowledgement": "attach_to_running_onenote_and_search_pages_without_display",
            "query": "  review \U0001f4dd", "start_object_id": None, "start_kind": None,
            "include_unindexed_pages": True, "offset": 0, "limit": 20,
        })
        self.assertEqual(self.timeout, 30)

    def test_preview_requires_exact_plain_complete_unicode_scalar_text(self) -> None:
        text = "A\U0001f4dd"
        def response(request: dict[str, object]) -> dict[str, object]:
            return self._envelope(request, {"backend": "desktop_automation", "probe": {
                "effect": "attach_to_running_onenote_and_read_basic_page_text",
                "attached_to_running_instance": True, "started_client": False, "page_info": "piBasic",
                "binary_data_requested": False, "selection_markup_requested": False,
                "navigated": False, "synchronized": False, "schema": "xs2013",
            }, "page": {"target": {"backend": "desktop_automation", "kind": "page", "object_id": "Exact"},
                         "content_format": "text/plain", "text": text,
                         "returned_characters": 2, "source_characters": 2, "truncated": False}})
        preview = self._client(response).preview("Exact")
        self.assertTrue(preview.can_use)  # type: ignore[union-attr]
        self.assertEqual(self.request["arguments"]["max_characters"], 50000)

    def test_malformed_or_contradictory_protocol_never_becomes_a_result(self) -> None:
        client = self._client(lambda request: self._envelope(request, {"backend": "desktop_automation",
            "probe": {"effect": "attach_to_running_onenote_and_search_pages_without_display"},
            "search": {"matches": [], "returned": 0, "total": 0, "next_offset": None, "truncated": False},
        }))
        with self.assertRaises(OneNoteError) as captured:
            client.search("query")
        self.assertEqual(captured.exception.code, "integration.protocol_failed")

    def test_nonzero_engine_error_keeps_code_but_hides_raw_message(self) -> None:
        def response(request: dict[str, object]) -> dict[str, object]:
            return {**self._envelope(request, {}), "status": "error", "result": None,
                    "error": {"code": "backend.desktop_not_running", "category": "unavailable",
                              "message": "private stderr", "retryable": False, "details": {}}}
        with self.assertRaises(OneNoteError) as captured:
            self._client(response, 6).search("query")
        self.assertEqual(captured.exception.code, "backend.desktop_not_running")
        self.assertNotIn("private stderr", repr(captured.exception))

    def test_duplicate_json_fields_and_incomplete_preview_are_rejected(self) -> None:
        client = OneNoteClient(Path("C:/engine/python-onenote.bat"), lambda *_: type("R", (), {
            "stdout": b'{"schema_version":"1.0","schema_version":"1.0"}', "returncode": 0})())
        with self.assertRaisesRegex(OneNoteError, "invalid response"):
            client.describe()

        invalid_utf8 = OneNoteClient(Path("C:/engine/python-onenote.bat"), lambda *_: type("R", (), {
            "stdout": b"\xff", "returncode": 0})())
        with self.assertRaisesRegex(OneNoteError, "invalid response"):
            invalid_utf8.describe()

        def response(request: dict[str, object]) -> dict[str, object]:
            return self._envelope(request, {"backend": "desktop_automation", "probe": {
                "effect": "attach_to_running_onenote_and_read_basic_page_text", "attached_to_running_instance": True,
                "started_client": False, "page_info": "piBasic", "binary_data_requested": False,
                "selection_markup_requested": False, "navigated": False, "synchronized": False, "schema": "xs2013",
            }, "page": {"target": {"backend": "desktop_automation", "kind": "page", "object_id": "Exact"},
                         "content_format": "text/plain", "text": "half", "returned_characters": 4,
                         "source_characters": 8, "truncated": True}})
        with self.assertRaisesRegex(OneNoteError, "invalid response"):
            self._client(response).preview("Exact")

    def empty_search(self):
        return {"backend": "desktop_automation", "probe": {
            "effect": "attach_to_running_onenote_and_search_pages_without_display",
            "attached_to_running_instance": True, "started_client": False,
            "displayed_search": False, "navigated": False, "synchronized": False,
            "schema": "xs2013"}, "search": {"matches": [], "returned": 0,
            "total": 0, "next_offset": None, "truncated": False}}

    def plain_preview(self, text="A😀"):
        return {"backend": "desktop_automation", "probe": {
            "effect": "attach_to_running_onenote_and_read_basic_page_text",
            "attached_to_running_instance": True, "started_client": False,
            "page_info": "piBasic", "binary_data_requested": False,
            "selection_markup_requested": False, "navigated": False,
            "synchronized": False, "schema": "xs2013"}, "page": {
            "target": {"backend": "desktop_automation", "kind": "page", "object_id": "Exact"},
            "content_format": "text/plain", "text": text, "returned_characters": len(text),
            "source_characters": len(text), "truncated": False}}

    def test_empty_search_and_exact_unicode_query_bounds(self):
        query = "😀" * 512
        result = self._client(lambda r: self._envelope(r, self.empty_search())).search(query)
        self.assertEqual(result.pages, ())
        self.assertEqual(self.request["arguments"]["query"], query)
        for invalid in ("", "  ", "😀" * 513, "a" * 513, "\ud800"):
            with self.subTest(query_length=len(invalid)):
                client = OneNoteClient(Path("C:/engine/python-onenote.bat"),
                    lambda *_: self.fail("Invalid query reached process transport"))
                with self.assertRaises(OneNoteError):
                    client.search(invalid)

    def test_envelope_mismatch_and_nonzero_success_are_failures(self):
        for field, value in (("schema_version", "2.0"), ("request_id", "stale"),
                             ("operation", "preview_desktop_page"), ("operation_version", "2.0"),
                             ("status", "partial"), ("status", []), ("duration_ms", True),
                             ("error", {}), ("result", None)):
            with self.subTest(field=field, value=value):
                def response(request):
                    result = self._envelope(request, self.empty_search())
                    result[field] = value
                    return result
                with self.assertRaises(OneNoteError):
                    self._client(response).search("query")
        with self.assertRaises(OneNoteError):
            self._client(lambda r: self._envelope(r, self.empty_search()), 6).search("query")

    def test_raw_protocol_limits_and_invalid_encodings(self):
        for raw in (b"{}{}", b"[]", b"\xff", b"{" * (1024*1024+1),
                    b"[" * 1100 + b"0" + b"]" * 1100,
                    b'{"a":1e999}', b'{"a":"\\ud800"}', b'{"a":1,"a":2}'):
            with self.subTest(size=len(raw)):
                client = OneNoteClient(Path("C:/engine/python-onenote.bat"),
                    lambda *_: SimpleNamespace(stdout=raw, returncode=0))
                with self.assertRaises(OneNoteError):
                    client.describe()

    def test_preview_count_case_format_and_backend_validation(self):
        mutations = (("returned_characters", 3), ("source_characters", 3),
                     ("truncated", True), ("truncated", 0), ("text", "\ud800"),
                     ("content_format", "text/html"),
                     ("target", {"backend": "desktop_automation", "kind": "page", "object_id": "exact"}))
        for field, value in mutations:
            with self.subTest(field=field):
                result = self.plain_preview()
                result["page"][field] = value
                with self.assertRaises(OneNoteError):
                    self._client(lambda r: self._envelope(r, result)).preview("Exact")
        for modify in (lambda r: r.update(backend="graph"),
                       lambda r: r["probe"].update(navigated=0),
                       lambda r: r["probe"].update(started_client=True)):
            result = self.plain_preview()
            modify(result)
            with self.assertRaises(OneNoteError):
                self._client(lambda r: self._envelope(r, result)).preview("Exact")

    def test_valid_truncation_is_reviewable_but_cannot_be_used(self):
        result = self.plain_preview("x" * 50000)
        result["page"].update(source_characters=50001, truncated=True)
        preview = self._client(lambda r: self._envelope(r, result)).preview("Exact")
        self.assertTrue(preview.truncated)
        self.assertFalse(preview.can_use)
        self.assertNotIn("xxxxx", repr(preview))

    def test_search_pagination_types_and_lifecycle_evidence(self):
        for field, value in (("returned", 1), ("returned", True), ("total", -1),
                             ("next_offset", 0), ("truncated", True), ("matches", {})):
            result = self.empty_search()
            result["search"][field] = value
            with self.subTest(field=field), self.assertRaises(OneNoteError):
                self._client(lambda r: self._envelope(r, result)).search("query")
        result = self.empty_search()
        result["probe"]["attached_to_running_instance"] = 1
        with self.assertRaises(OneNoteError):
            self._client(lambda r: self._envelope(r, result)).search("query")

    def test_full_breadcrumb_keeps_exact_parent_identity(self):
        def target(kind, identifier):
            return {"backend": "desktop_automation", "kind": kind, "object_id": identifier}
        notebook, section, page = target("notebook", "Book"), target("section", "Section"), target("page", "Page")
        result = self.empty_search()
        result["search"].update(matches=[{"page": {"target": page, "parent": section, "display_name": "Note"},
            "ancestors": [{"target": notebook, "parent": None, "display_name": "Book"},
                          {"target": section, "parent": notebook, "display_name": "Section"}]}], returned=1, total=1)
        found = self._client(lambda r: self._envelope(r, result)).search("query")
        self.assertEqual(found.pages[0].breadcrumb, ("Book", "Section"))
        wrong = copy.deepcopy(result)
        wrong["search"]["matches"][0]["ancestors"][1]["parent"]["backend"] = "graph"
        with self.assertRaises(OneNoteError):
            self._client(lambda r: self._envelope(r, wrong)).search("query")

    def test_desktop_bridge_read_failure_is_not_an_engine_setup_failure(self):
        def response(request):
            return {**self._envelope(request, {}), "status": "error", "result": None,
                    "error": {"code": "internal.desktop_bridge", "category": "internal_error",
                              "message": "private notebook content", "retryable": False,
                              "details": {"location": "private notebook location"}}}
        with self.assertRaises(OneNoteError) as caught:
            self._client(response, 70).search("marker", notebook_id="exact-notebook")
        self.assertEqual(caught.exception.code, "internal.desktop_bridge")
        self.assertTrue(caught.exception.invalidates_readiness)
        self.assertIn("Make sure the notebook is open", str(caught.exception))
        self.assertNotIn("private", str(caught.exception))
        self.assertNotIn("private", repr(caught.exception))
        self.assertEqual(self.request["arguments"]["start_object_id"], "exact-notebook")
        # A known error code must not relax the envelope/exit consistency checks.
        with self.assertRaises(OneNoteError) as caught:
            self._client(response, 6).search("marker", notebook_id="exact-notebook")
        self.assertEqual(caught.exception.code, "integration.protocol_failed")

    def test_unknown_engine_error_never_exposes_private_code_or_message(self):
        def response(request):
            return {**self._envelope(request, {}), "status": "error", "result": None,
                    "error": {"code": "secret.notebook_name", "category": "unavailable",
                              "message": "private content", "retryable": False, "details": {}}}
        with self.assertRaises(OneNoteError) as captured:
            self._client(response, 6).search("query")
        self.assertEqual(captured.exception.code, "integration.engine_failed")
        self.assertNotIn("private", str(captured.exception))
        self.assertNotIn("notebook_name", repr(captured.exception))
        with self.assertRaises(OneNoteError) as captured:
            self._client(response, 70).search("query")
        self.assertEqual(captured.exception.code, "integration.protocol_failed")

    def test_local_settings_require_existing_absolute_named_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launcher = root / "python-onenote.bat"
            launcher.write_text("", encoding="utf-8")
            settings_path = root / "local_onenote_settings.json"
            save_onenote_settings(settings_path, OneNoteSettings(launcher))
            self.assertEqual(load_onenote_settings(settings_path), OneNoteSettings(launcher))
            with self.assertRaises(OneNoteSettingsError):
                save_onenote_settings(settings_path, OneNoteSettings(Path("relative.bat")))

    def notebook_inventory(self, count=1):
        return {"backend": "desktop_automation", "probe": {
            "effect": "attach_to_running_onenote_and_read_hierarchy",
            "attached_to_running_instance": True, "started_client": False,
            "navigated": False, "synchronized": False, "schema": "xs2013"},
            "hierarchy": {"items": [{"target": {"backend": "desktop_automation",
                "kind": "notebook", "object_id": f"Private-ID-{index}"}, "parent": None,
                "display_name": "Private notebook 😀", "last_modified": None}
                for index in range(count)], "returned": count, "total": count,
                "next_offset": None, "truncated": False}}

    def scoped_search(self):
        notebook = {"backend": "desktop_automation", "kind": "notebook", "object_id": "Exact-Book"}
        section = {"backend": "desktop_automation", "kind": "section", "object_id": "Section"}
        result = self.empty_search()
        result["search"].update(matches=[{"page": {"target": {"backend": "desktop_automation",
            "kind": "page", "object_id": "Page"}, "parent": section, "display_name": "Private note"},
            "ancestors": [{"target": notebook, "parent": None, "display_name": "Private notebook"},
                {"target": section, "parent": notebook, "display_name": "Section"}]}], returned=1, total=1)
        return result

    def test_notebooks_request_is_bounded_root_read_and_private(self):
        token = object()
        with self.assertNoLogs():
            result = self._client(lambda r: self._envelope(r, self.notebook_inventory())).notebooks(cancel_event=token)
        self.assertEqual(result.notebooks, (NotebookRef("Private-ID-0", "Private notebook 😀"),))
        self.assertEqual(result.total, 1)
        self.assertFalse(result.truncated)
        self.assertEqual(self.request["arguments"], {
            "effect_acknowledgement": "attach_to_running_onenote_and_read_hierarchy",
            "start_object_id": None, "start_kind": None, "scope": "notebooks",
            "offset": 0, "limit": 100, "max_depth": 4})
        self.assertEqual(self.timeout, 30)
        self.assertIs(self.cancel_event, token)
        self.assertNotIn("Private", repr(result))
        empty = self._client(lambda r: self._envelope(r, self.notebook_inventory(0))).notebooks()
        self.assertEqual(empty.notebooks, ())

    def test_notebook_inventory_accepts_bounded_pagination_without_followup(self):
        result = self.notebook_inventory(100)
        result["hierarchy"].update(total=101, next_offset=100, truncated=True)
        found = self._client(lambda r: self._envelope(r, result)).notebooks()
        self.assertEqual(len(found.notebooks), 100)
        self.assertEqual(found.total, 101)
        self.assertTrue(found.truncated)
        result = self.notebook_inventory(2)
        result["hierarchy"]["items"][1]["target"]["object_id"] = "private-id-0"
        found = self._client(lambda r: self._envelope(r, result)).notebooks()
        self.assertEqual(tuple(book.object_id for book in found.notebooks), ("Private-ID-0", "private-id-0"))

    def test_notebook_inventory_rejects_wrong_identity_evidence_and_paging(self):
        modifications = [
            lambda r: r.update(backend="graph"),
            lambda r: r.update(extra="private"),
            lambda r: r["probe"].update(attached_to_running_instance=1),
            lambda r: r["probe"].update(started_client=True),
            lambda r: r["probe"].update(navigated=True),
            lambda r: r["probe"].update(schema="xsCurrent"),
            lambda r: r["probe"].update(effect="search"),
            lambda r: r["hierarchy"].update(returned=True),
            lambda r: r["hierarchy"].update(returned=0),
            lambda r: r["hierarchy"].update(total=-1),
            lambda r: r["hierarchy"].update(items={}),
            lambda r: r["hierarchy"].update(next_offset=True),
            lambda r: r["hierarchy"].update(next_offset=1),
            lambda r: r["hierarchy"].update(truncated=True),
            lambda r: r["hierarchy"].update(total=2, next_offset=1, truncated=True),
            lambda r: r["hierarchy"]["items"][0]["target"].update(kind="section"),
            lambda r: r["hierarchy"]["items"][0]["target"].update(backend="graph"),
            lambda r: r["hierarchy"]["items"][0]["target"].update(object_id=""),
            lambda r: r["hierarchy"]["items"][0]["target"].update(object_id="x" * 2049),
            lambda r: r["hierarchy"]["items"][0]["target"].update(object_id="\ud800"),
            lambda r: r["hierarchy"]["items"][0]["target"].update(object_id="a\x00b"),
            lambda r: r["hierarchy"]["items"][0].update(parent={}),
            lambda r: r["hierarchy"]["items"][0].update(display_name="x" * 513),
            lambda r: r["hierarchy"]["items"][0].update(last_modified=[]),
            lambda r: r["hierarchy"]["items"][0].pop("parent"),
        ]
        for index, modify in enumerate(modifications):
            result = self.notebook_inventory()
            modify(result)
            with self.subTest(case=index), self.assertRaises(OneNoteError) as caught, self.assertNoLogs():
                self._client(lambda r: self._envelope(r, result)).notebooks()

    def test_notebook_inventory_rejects_mismatched_envelope(self):
        def response(request):
            document = self._envelope(request, self.notebook_inventory())
            document["operation"] = "search_desktop_pages"
            return document
        with self.assertRaises(OneNoteError):
            self._client(response).notebooks()
            self.assertEqual(caught.exception.code, "integration.protocol_failed")
            self.assertNotIn("Private", repr(caught.exception))
        for count in (2, 101):
            result = self.notebook_inventory(count)
            if count == 2:
                result["hierarchy"]["items"][1]["target"]["object_id"] = "Private-ID-0"
            with self.subTest(count=count), self.assertRaises(OneNoteError):
                self._client(lambda r: self._envelope(r, result)).notebooks()

    def test_scoped_search_keeps_exact_notebook_id_and_private_results(self):
        result = self.scoped_search()
        with self.assertNoLogs():
            found = self._client(lambda r: self._envelope(r, result)).search("private query", notebook_id="Exact-Book")
        self.assertEqual(found.pages[0].object_id, "Page")
        self.assertEqual(self.request["arguments"]["start_object_id"], "Exact-Book")
        self.assertEqual(self.request["arguments"]["start_kind"], "notebook")
        self.assertNotIn("Private", repr(found))

    def test_scoped_search_rejects_case_mismatch_wrong_or_absent_notebook(self):
        for actual in ("exact-book", "Other-Book", None):
            result = self.scoped_search()
            ancestors = result["search"]["matches"][0]["ancestors"]
            if actual is None:
                ancestors.pop(0)
                ancestors[0]["parent"] = None
            else:
                ancestors[0]["target"]["object_id"] = actual
            with self.subTest(actual=actual), self.assertRaises(OneNoteError):
                self._client(lambda r: self._envelope(r, result)).search("query", notebook_id="Exact-Book")
        empty = self._client(lambda r: self._envelope(r, self.empty_search())).search("query", notebook_id="Exact-Book")
        self.assertEqual(empty.pages, ())
        for identifier in ("", "  ", "x" * 2049, "\ud800", "a\x00b", 1):
            client = OneNoteClient(Path("C:/engine/python-onenote.bat"),
                lambda *_: self.fail("Invalid notebook identity reached transport"))
            with self.subTest(identifier_type=type(identifier)), self.assertRaises(OneNoteError):
                client.search("query", notebook_id=identifier)

    def test_notebook_settings_roundtrip_legacy_and_clear_preserve_privacy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launcher = root / "python-onenote.bat"
            launcher.write_text("", encoding="utf-8")
            path = root / "local_onenote_settings.json"
            notebook = NotebookRef("Exact-Book", "Private notebook 😀")
            settings = OneNoteSettings(launcher, notebook)
            with self.assertNoLogs():
                save_onenote_settings(path, settings)
                self.assertEqual(load_onenote_settings(path), settings)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["notebook"],
                {"object_id": "Exact-Book", "title": "Private notebook 😀"})
            self.assertNotIn("Exact-Book", repr(settings))
            self.assertNotIn("Private notebook", repr(settings))
            save_onenote_settings(path, OneNoteSettings(launcher))
            self.assertEqual(load_onenote_settings(path), OneNoteSettings(launcher))
            self.assertNotIn("notebook", json.loads(path.read_text(encoding="utf-8")))
            path.write_text('{"launcher_path":"", "notebook":null}', encoding="utf-8")
            self.assertEqual(load_onenote_settings(path), OneNoteSettings())

    def test_notebook_settings_reject_malformed_and_unbounded_private_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "local_onenote_settings.json"
            for notebook in ({}, {"object_id": "Book", "title": "Title", "extra": 1},
                    {"object_id": "", "title": "Title"}, {"object_id": "x" * 2049, "title": "Title"},
                    {"object_id": "Book", "title": "x" * 513}, {"object_id": "\ud800", "title": "Private"},
                    {"object_id": 1, "title": "Private"}, []):
                path.write_text(json.dumps({"launcher_path": "", "notebook": notebook}), encoding="utf-8")
                with self.subTest(notebook_type=type(notebook)), self.assertRaises(OneNoteSettingsError) as caught:
                    load_onenote_settings(path)
                self.assertNotIn("Private", repr(caught.exception))
            for raw in ('{"launcher_path":"","notebook":null,"notebook":null}',
                        '{"launcher_path":"","notebook":NaN}', "x" * (1024 * 1024 + 1)):
                path.write_text(raw, encoding="utf-8")
                with self.assertRaises(OneNoteSettingsError):
                    load_onenote_settings(path)
            for notebook in (NotebookRef("", "Private"), NotebookRef("Book", "x" * 513), "Private"):
                with self.assertRaises(OneNoteSettingsError):
                    save_onenote_settings(path, OneNoteSettings(notebook=notebook))

    def test_notebook_settings_and_scope_accept_engine_unicode_bounds_exactly(self):
        notebook = NotebookRef("😀" * 2048, "😀" * 512)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "local_onenote_settings.json"
            settings = OneNoteSettings(notebook=notebook)
            save_onenote_settings(path, settings)
            self.assertEqual(load_onenote_settings(path), settings)
            original = path.read_bytes()
            with self.assertRaises(OneNoteSettingsError):
                save_onenote_settings(path, OneNoteSettings(notebook=NotebookRef(notebook.object_id + "x", "Title")))
            self.assertEqual(path.read_bytes(), original)
        result = self._client(lambda r: self._envelope(r, self.empty_search())).search("query", notebook_id=notebook.object_id)
        self.assertEqual(result.pages, ())
        self.assertEqual(self.request["arguments"]["start_object_id"], notebook.object_id)

    def test_loading_missing_engine_preserves_remembered_notebook_but_save_rejects_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launcher = root / "moved-engine" / "python-onenote.bat"
            path = root / "local_onenote_settings.json"
            notebook = NotebookRef("Exact-Book", "Private notebook")
            path.write_text(json.dumps({"launcher_path": str(launcher),
                "notebook": {"object_id": notebook.object_id, "title": notebook.title}}), encoding="utf-8")
            settings = load_onenote_settings(path)
            self.assertEqual(settings, OneNoteSettings(launcher, notebook))
            original = path.read_bytes()
            with self.assertRaises(OneNoteSettingsError):
                save_onenote_settings(path, settings)
            self.assertEqual(path.read_bytes(), original)

    def test_missing_target_and_reconnect_errors_use_search_without_raw_details(self):
        for code in ("target.not_found", "backend.desktop_explicit_probe_required", "backend.desktop_process_exited"):
            def response(request):
                return {**self._envelope(request, {}), "status": "error", "result": None,
                    "error": {"code": code, "category": "unavailable", "message": "Private notebook title",
                        "retryable": False, "details": {"object_id": "Private-ID"}}}
            with self.subTest(code=code), self.assertRaises(OneNoteError) as caught, self.assertNoLogs():
                self._client(response, 6).search("query", notebook_id="Exact-Book")
            self.assertNotIn("Private", repr(caught.exception))
            if code == "target.not_found":
                self.assertIn("chosen notebook or note", str(caught.exception))
                self.assertIn("choose it again", str(caught.exception))
            else:
                self.assertIn("Search", str(caught.exception))
                self.assertNotIn("Connect", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
