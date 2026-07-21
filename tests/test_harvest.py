from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from context_palette.actions import Action
from context_palette.harvest import (
    HarvestCandidate,
    HarvestScanCoordinator,
    build_candidates,
    candidate_to_draft,
    extract_source,
    normalize_url_for_comparison,
    update_candidate_values,
)


def write_docx(path: Path) -> None:
    document = """<?xml version="1.0" encoding="UTF-8"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <w:body><w:p><w:hyperlink r:id="rId1"><w:r><w:t>Word guide</w:t></w:r></w:hyperlink></w:p></w:body>
    </w:document>"""
    rels = """<?xml version="1.0" encoding="UTF-8"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
       Target="https://example.test/word" TargetMode="External"/>
    </Relationships>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)
        archive.writestr("word/_rels/document.xml.rels", rels)


def write_xlsx(path: Path) -> None:
    worksheet = """<?xml version="1.0" encoding="UTF-8"?>
    <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <sheetData>
        <row r="1"><c r="A1" t="inlineStr"><is><t>Excel guide</t></is></c></row>
        <row r="2"><c r="A2" t="str"><f>HYPERLINK("https://example.test/formula","Formula guide")</f><v>Formula guide</v></c></row>
        <row r="3"><c r="A3" t="inlineStr"><is><t>https://example.test/plain</t></is></c></row>
        <row r="4"><c r="A4" t="str"><f>RUN("powershell")</f><v>https://evil.test/ignored</v></c></row>
      </sheetData>
      <hyperlinks><hyperlink ref="A1" r:id="rId1"/></hyperlinks>
    </worksheet>"""
    rels = """<?xml version="1.0" encoding="UTF-8"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
       Target="https://example.test/excel" TargetMode="External"/>
    </Relationships>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
        archive.writestr("xl/worksheets/_rels/sheet1.xml.rels", rels)


class HarvestExtractionTests(unittest.TestCase):
    def test_markdown_extracts_links_and_bare_urls_but_not_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "links.md"
            path.write_text(
                "[Guide](https://example.test/guide) and https://example.test/bare\n"
                "```text\nhttps://ignored.test/code\n```\n"
                "[Local](notes.txt)\n",
                encoding="utf-8",
            )

            result = extract_source(path, 0)

        self.assertEqual(result.status, "Complete")
        self.assertEqual(
            [item.target for item in result.occurrences],
            ["https://example.test/guide", "https://example.test/bare", "notes.txt"],
        )
        self.assertEqual(result.occurrences[0].location, "line 1")

    def test_text_extracts_bare_http_urls(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "links.txt"
            path.write_text("Use https://example.test/one then http://example.test/two.", encoding="utf-8")
            result = extract_source(path, 0)

        self.assertEqual(len(result.occurrences), 2)
        self.assertEqual(result.occurrences[1].target, "http://example.test/two")

    def test_docx_reads_hyperlink_relationship_without_office(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "links.docx"
            write_docx(path)
            with patch("os.startfile") as startfile:
                result = extract_source(path, 0)

        self.assertEqual(result.status, "Complete")
        self.assertEqual(result.occurrences[0].display_text, "Word guide")
        self.assertEqual(result.occurrences[0].target, "https://example.test/word")
        startfile.assert_not_called()

    def test_xlsx_reads_relationship_literal_hyperlink_formula_and_plain_url(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "links.xlsx"
            write_xlsx(path)
            result = extract_source(path, 0)

        self.assertEqual(
            {item.target for item in result.occurrences},
            {
                "https://example.test/excel",
                "https://example.test/formula",
                "https://example.test/plain",
            },
        )
        self.assertNotIn("https://evil.test/ignored", {item.target for item in result.occurrences})

    def test_corrupt_unsupported_and_encrypted_sources_fail_individually(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            corrupt = root / "bad.docx"
            corrupt.write_bytes(b"not a zip")
            unsupported = root / "old.doc"
            unsupported.write_bytes(b"old")

            self.assertEqual(extract_source(corrupt, 0).status, "Failed")
            self.assertEqual(extract_source(unsupported, 1).status, "Failed")

    def test_oversized_office_package_fails_with_clear_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "large.docx"
            write_docx(path)
            with patch("context_palette.harvest.MAX_OOXML_BYTES", 1):
                result = extract_source(path, 0)

        self.assertEqual(result.status, "Failed")
        self.assertIn("limit", result.error)

    def test_encrypted_package_is_rejected_before_xml_read(self):
        class FakeArchive:
            def infolist(self):
                return [SimpleNamespace(flag_bits=1, file_size=10, compress_size=10, filename="word/document.xml")]

            def close(self):
                return None

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "protected.docx"
            path.write_bytes(b"placeholder")
            with patch("context_palette.harvest.zipfile.ZipFile", return_value=FakeArchive()):
                result = extract_source(path, 0)

        self.assertEqual(result.status, "Failed")
        self.assertIn("Encrypted", result.error)

    def test_password_protected_office_container_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "protected.xlsx"
            path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1content")
            result = extract_source(path, 0)

        self.assertEqual(result.status, "Failed")
        self.assertIn("Encrypted or legacy", result.error)

    def test_zero_compressed_size_with_content_is_rejected(self):
        class FakeArchive:
            def infolist(self):
                return [SimpleNamespace(flag_bits=0, file_size=10, compress_size=0, filename="word/document.xml")]

            def close(self):
                return None

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "unsafe.docx"
            path.write_bytes(b"placeholder")
            with patch("context_palette.harvest.zipfile.ZipFile", return_value=FakeArchive()):
                result = extract_source(path, 0)

        self.assertEqual(result.status, "Failed")
        self.assertIn("compression ratio", result.error)

    def test_excessive_zip_entry_count_is_rejected(self):
        entry = SimpleNamespace(
            flag_bits=0,
            file_size=0,
            compress_size=0,
            filename="empty.xml",
        )

        class FakeArchive:
            def infolist(self):
                return [entry, entry]

            def close(self):
                return None

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "unsafe.docx"
            path.write_bytes(b"placeholder")
            with patch("context_palette.harvest.MAX_ZIP_ENTRIES", 1), patch(
                "context_palette.harvest.zipfile.ZipFile", return_value=FakeArchive()
            ):
                result = extract_source(path, 0)

        self.assertEqual(result.status, "Failed")
        self.assertIn("more than 1 entries", result.error)

    def test_cancelled_source_discards_partial_findings(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "links.txt"
            path.write_text("https://example.test/one\nhttps://example.test/two", encoding="utf-8")
            result = extract_source(path, 0, cancelled=lambda: True)

        self.assertEqual(result.status, "Cancelled")
        self.assertEqual(result.occurrences, ())
        self.assertIn("discarded", result.warnings[0])

    def test_excel_cell_limit_reports_partial_extraction_warning(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "links.xlsx"
            write_xlsx(path)
            with patch("context_palette.harvest.MAX_EXCEL_CELLS", 1):
                result = extract_source(path, 0)

        self.assertEqual(result.status, "Complete with warnings")
        self.assertIn("Cell inspection stopped", result.warnings[0])

    def test_occurrence_limit_is_enforced_inside_one_dense_text_line(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dense.txt"
            path.write_text(
                " ".join(f"https://example.test/{index}" for index in range(20)),
                encoding="utf-8",
            )
            with patch("context_palette.harvest.MAX_OCCURRENCES_PER_SOURCE", 3):
                result = extract_source(path, 0)

        self.assertEqual(len(result.occurrences), 3)
        self.assertEqual(result.status, "Complete with warnings")

    def test_extraction_never_opens_or_executes_document_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "malicious.txt"
            path.write_text("https://example.test; powershell -Command calc", encoding="utf-8")
            with patch("os.startfile") as startfile, patch("subprocess.Popen") as popen, patch(
                "webbrowser.open"
            ) as browser:
                result = extract_source(path, 0)

        self.assertEqual(result.status, "Complete")
        startfile.assert_not_called()
        popen.assert_not_called()
        browser.assert_not_called()


class HarvestCandidateTests(unittest.TestCase):
    def test_cross_file_duplicates_preserve_provenance_and_conflicting_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "a.md"
            second = root / "b.md"
            first.write_text("[Architecture](https://EXAMPLE.test:443/docs?q=1#top)", encoding="utf-8")
            second.write_text("[System design](https://example.test/docs?q=1#top)", encoding="utf-8")
            sources = [extract_source(first, 0), extract_source(second, 1)]

            candidates = build_candidates(sources, [], default_context="Database")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(len(candidates[0].occurrences), 2)
        self.assertEqual(candidates[0].classification, "Needs attention")
        self.assertEqual(candidates[0].contexts, {"Database"})

    def test_existing_states_and_default_selection_are_distinct(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "links.txt"
            path.write_text(
                "https://example.test/draft https://example.test/trusted https://example.test/new",
                encoding="utf-8",
            )
            source = extract_source(path, 0)
        existing = [
            Action("draft", "Draft", "General", "open_url", "https://example.test/draft", "Draft"),
            Action("trusted", "Trusted", "General", "open_url", "https://example.test/trusted", "Trusted"),
        ]

        candidates = build_candidates([source], existing)
        by_target = {candidate.target: candidate for candidate in candidates}

        self.assertEqual(by_target["https://example.test/draft"].classification, "Existing Draft")
        self.assertEqual(by_target["https://example.test/trusted"].classification, "Already available")
        self.assertTrue(by_target["https://example.test/new"].selected)
        self.assertFalse(by_target["https://example.test/draft"].selected)

    def test_archived_url_does_not_block_a_new_draft(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "links.txt"
            path.write_text("https://example.test/archived", encoding="utf-8")
            source = extract_source(path, 0)
        existing = [
            Action(
                "archived",
                "Archived",
                "General",
                "open_url",
                "https://example.test/archived",
                "Archived",
            )
        ]

        candidate = build_candidates([source], existing)[0]

        self.assertEqual(candidate.classification, "Ready")
        self.assertTrue(candidate.selected)

    def test_same_title_with_different_targets_remains_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "links.md"
            path.write_text(
                "[Dashboard](https://example.test/one)\n[Dashboard](https://example.test/two)",
                encoding="utf-8",
            )
            candidates = build_candidates([extract_source(path, 0)], [])

        self.assertEqual(len(candidates), 2)
        self.assertEqual({candidate.target for candidate in candidates}, {"https://example.test/one", "https://example.test/two"})

    def test_unsupported_scheme_is_inert_and_cannot_become_draft(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "links.md"
            path.write_text("[Run](javascript:powershell())", encoding="utf-8")
            candidates = build_candidates([extract_source(path, 0)], [])

        self.assertEqual(candidates[0].classification, "Unsupported")
        with self.assertRaisesRegex(ValueError, "not importable"):
            candidate_to_draft(candidates[0])

    def test_bulk_add_and_remove_preserve_other_values(self):
        candidate = HarvestCandidate("id", "Name", "https://example.test", "key", [])
        candidate.contexts = {"Database", "Mail"}
        candidate.tags = {"docs", "urgent"}

        update_candidate_values([candidate], field_name="contexts", operation="add", values=["Web"])
        update_candidate_values([candidate], field_name="contexts", operation="remove", values=["mail"])
        update_candidate_values([candidate], field_name="tags", operation="remove", values=["docs"])

        self.assertEqual(candidate.contexts, {"Database", "Web"})
        self.assertEqual(candidate.tags, {"urgent"})

    def test_candidate_maps_only_to_personal_draft_url_action(self):
        candidate = HarvestCandidate(
            "id",
            "Open guide",
            "https://example.test/guide",
            normalize_url_for_comparison("https://example.test/guide"),
            [],
            contexts={"Database"},
            tags={"docs"},
        )

        action = candidate_to_draft(candidate)

        self.assertEqual(action.type, "open_url")
        self.assertEqual(action.state, "Draft")
        self.assertIn("Database", action.effective_contexts)
        self.assertEqual(action.effective_tags, ("docs",))


class HarvestCoordinatorTests(unittest.TestCase):
    def test_multiple_sources_are_deterministic_and_one_failure_does_not_abort(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            good = root / "b.txt"
            bad = root / "a.docx"
            good.write_text("https://example.test", encoding="utf-8")
            bad.write_bytes(b"bad")
            coordinator = HarvestScanCoordinator()
            coordinator.start([good, bad])
            events = []
            deadline = time.monotonic() + 2
            while coordinator.running and time.monotonic() < deadline:
                events.extend(coordinator.drain())
                time.sleep(0.01)
            events.extend(coordinator.drain())

        sources = [value for kind, value in events if kind == "source"]
        self.assertEqual([source.path.name for source in sources], ["a.docx", "b.txt"])
        self.assertEqual([source.status for source in sources], ["Failed", "Complete"])

    def test_cancellation_stops_between_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / f"{name}.txt" for name in ("a", "b", "c")]
            for path in paths:
                path.write_text("https://example.test", encoding="utf-8")
            first_started = threading.Event()

            def slow_extract(path, ordinal, *, cancelled):
                first_started.set()
                time.sleep(0.05)
                return extract_source(path, ordinal, cancelled=cancelled)

            coordinator = HarvestScanCoordinator()
            with patch("context_palette.harvest.extract_source", side_effect=slow_extract):
                coordinator.start(paths)
                self.assertTrue(first_started.wait(1))
                coordinator.cancel()
                deadline = time.monotonic() + 2
                events = []
                while coordinator.running and time.monotonic() < deadline:
                    events.extend(coordinator.drain())
                    time.sleep(0.01)
                events.extend(coordinator.drain())

        sources = [value for kind, value in events if kind == "source"]
        self.assertEqual(len(sources), 1)
        self.assertTrue(any(kind == "complete" and value is True for kind, value in events))

    def test_unexpected_extractor_error_still_completes_with_failed_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "links.txt"
            path.write_text("https://example.test", encoding="utf-8")
            coordinator = HarvestScanCoordinator()
            with patch("context_palette.harvest.extract_source", side_effect=RuntimeError("boom")):
                coordinator.start([path])
                deadline = time.monotonic() + 2
                events = []
                while coordinator.running and time.monotonic() < deadline:
                    events.extend(coordinator.drain())
                    time.sleep(0.01)
                events.extend(coordinator.drain())

        sources = [value for kind, value in events if kind == "source"]
        self.assertEqual(sources[0].status, "Failed")
        self.assertIn("Unexpected extraction failure", sources[0].error)
        self.assertTrue(any(kind == "complete" for kind, _value in events))


if __name__ == "__main__":
    unittest.main()
