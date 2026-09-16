from __future__ import annotations

from pathlib import Path
import os
import math
import tempfile
import threading
import unittest
from unittest.mock import patch

import context_palette.webpage_pdf as webpage_pdf
from context_palette.webpage_pdf import (
    WebpagePdfError,
    find_pdf_browser,
    render_webpage_pdf,
    suggested_pdf_name,
    validate_webpage_url,
)


class WebpageUrlTests(unittest.TestCase):
    def test_validates_one_complete_http_url_and_preserves_query_and_fragment(self) -> None:
        value = "  https://example.com/docs?q=one%20two#overview  "
        self.assertEqual(validate_webpage_url(value), "https://example.com/docs?q=one%20two#overview")

    def test_rejects_ambiguous_or_unsafe_urls(self) -> None:
        for value in (
            "https://example.com https://other.example",
            "ftp://example.com/file",
            "https://user:secret@example.com/",
            "https://example.com:99999/",
            "https://bad_host.example/",
            "https://example.com\nnext",
        ):
            with self.subTest(value=value):
                with self.assertRaises(WebpagePdfError):
                    validate_webpage_url(value)

    def test_suggested_name_excludes_query_fragment_and_is_portable(self) -> None:
        name = suggested_pdf_name("https://www.example.com/reports/Quarter_1.html?secret=1#top")
        self.assertEqual(name, "webpage-www.example.com-Quarter_1.html.pdf")
        self.assertNotIn("secret", name)
        self.assertNotIn("#", name)


class _FakeProcess:
    def __init__(self, command: list[str], *, output: bytes = b"%PDF-1.4\n%%EOF\n", code: int = 0) -> None:
        self.command = command
        self.returncode = code
        self.pid = 42
        self._running = False
        for argument in command:
            if argument.startswith("--print-to-pdf=") and code == 0:
                Path(argument.split("=", 1)[1]).write_bytes(output)

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9


class _RunningProcess(_FakeProcess):
    def __init__(self, command: list[str], cancelled: threading.Event | None = None) -> None:
        super().__init__(command)
        self.returncode = None
        self._cancelled = cancelled

    def poll(self):
        if self._cancelled is not None:
            self._cancelled.set()
        return self.returncode


class WebpagePdfRenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.browser = self.root / "msedge.exe"
        self.browser.write_bytes(b"browser")
        self.destination = self.root / "page.pdf"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_render_uses_isolated_headless_arguments_and_preserves_url_as_one_argument(self) -> None:
        commands: list[list[str]] = []

        def start(command, **_kwargs):
            commands.append(command)
            return _FakeProcess(command)

        url = "https://example.com/report?q=one%20two&x=1"
        with patch("context_palette.webpage_pdf.subprocess.Popen", side_effect=start):
            result = render_webpage_pdf(url, self.destination, browser_path=self.browser)

        self.assertEqual(result, self.destination)
        self.assertEqual(self.destination.read_bytes(), b"%PDF-1.4\n%%EOF\n")
        command = commands[0]
        self.assertIn(url, command)
        self.assertIn("--headless=new", command)
        self.assertIn("--no-pdf-header-footer", command)
        self.assertNotIn("--no-sandbox", command)
        self.assertFalse(any("ignore-certificate" in argument for argument in command))
        profile = next(argument for argument in command if argument.startswith("--user-data-dir="))
        self.assertNotIn(str(self.root), profile)

    def test_refuses_existing_and_raced_destination_without_overwriting(self) -> None:
        self.destination.write_bytes(b"existing")
        with self.assertRaisesRegex(WebpagePdfError, "already exists"):
            render_webpage_pdf("https://example.com/", self.destination, browser_path=self.browser)

        self.destination.unlink()

        def start(command, **_kwargs):
            fake = _FakeProcess(command)
            self.destination.write_bytes(b"raced")
            return fake

        with patch("context_palette.webpage_pdf.subprocess.Popen", side_effect=start):
            with self.assertRaisesRegex(WebpagePdfError, "already exists"):
                render_webpage_pdf("https://example.com/", self.destination, browser_path=self.browser)
        self.assertEqual(self.destination.read_bytes(), b"raced")

    def test_rejects_invalid_completion_without_publishing(self) -> None:
        with patch(
            "context_palette.webpage_pdf.subprocess.Popen",
            side_effect=lambda command, **_kwargs: _FakeProcess(command, output=b"not-a-pdf"),
        ):
            with self.assertRaisesRegex(WebpagePdfError, "invalid PDF"):
                render_webpage_pdf("https://example.com/", self.destination, browser_path=self.browser)
        self.assertFalse(self.destination.exists())

    def test_rejects_truncated_pdf_without_publishing(self) -> None:
        with patch(
            "context_palette.webpage_pdf.subprocess.Popen",
            side_effect=lambda command, **_kwargs: _FakeProcess(command, output=b"%PDF-1.4\n"),
        ):
            with self.assertRaisesRegex(WebpagePdfError, "invalid PDF"):
                render_webpage_pdf("https://example.com/", self.destination, browser_path=self.browser)
        self.assertFalse(self.destination.exists())

    def test_early_errors_do_not_start_browser_or_write_a_pdf(self) -> None:
        with patch("context_palette.webpage_pdf.subprocess.Popen") as start:
            with self.assertRaises(WebpagePdfError):
                render_webpage_pdf("file:///C:/secret", self.destination, browser_path=self.browser)
            with self.assertRaises(WebpagePdfError):
                render_webpage_pdf("https://example.com", self.root / "page.txt", browser_path=self.browser)
        start.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_nonfinite_timeout_is_rejected_before_browser_launch(self) -> None:
        with patch("context_palette.webpage_pdf.subprocess.Popen") as start:
            for value in (math.inf, math.nan):
                with self.subTest(value=value):
                    with self.assertRaisesRegex(WebpagePdfError, "positive"):
                        render_webpage_pdf("https://example.com", self.destination, browser_path=self.browser, timeout=value)
        start.assert_not_called()

    def test_cancellation_before_launch_does_not_start_browser(self) -> None:
        cancelled = threading.Event()
        cancelled.set()
        with patch("context_palette.webpage_pdf.subprocess.Popen") as start:
            with self.assertRaisesRegex(WebpagePdfError, "cancelled"):
                render_webpage_pdf("https://example.com", self.destination, browser_path=self.browser, cancel_event=cancelled)
        start.assert_not_called()

    def test_cancellation_after_launch_terminates_only_the_spawned_process(self) -> None:
        cancelled = threading.Event()
        process: _RunningProcess | None = None

        def start(command, **_kwargs):
            nonlocal process
            process = _RunningProcess(command, cancelled)
            return process

        with patch("context_palette.webpage_pdf._IS_WINDOWS", False), patch(
            "context_palette.webpage_pdf.subprocess.Popen", side_effect=start
        ):
            with self.assertRaisesRegex(WebpagePdfError, "cancelled"):
                render_webpage_pdf("https://example.com", self.destination, browser_path=self.browser, cancel_event=cancelled)
        self.assertIsNotNone(process)
        self.assertEqual(process.returncode, -15)

    def test_timeout_terminates_the_spawned_process_without_publishing(self) -> None:
        process: _RunningProcess | None = None

        def start(command, **_kwargs):
            nonlocal process
            process = _RunningProcess(command)
            return process

        with patch("context_palette.webpage_pdf._IS_WINDOWS", False), patch(
            "context_palette.webpage_pdf.subprocess.Popen", side_effect=start
        ):
            with self.assertRaisesRegex(WebpagePdfError, "timed out"):
                render_webpage_pdf("https://example.com", self.destination, browser_path=self.browser, timeout=0.001)
        self.assertIsNotNone(process)
        self.assertEqual(process.returncode, -15)
        self.assertFalse(self.destination.exists())

    def test_cancellation_after_valid_pdf_before_publish_leaves_no_destination(self) -> None:
        cancelled = threading.Event()
        original_validate = webpage_pdf._validate_rendered_pdf

        def validate_then_cancel(path: Path) -> None:
            original_validate(path)
            cancelled.set()

        with patch("context_palette.webpage_pdf._validate_rendered_pdf", side_effect=validate_then_cancel), patch(
            "context_palette.webpage_pdf.subprocess.Popen",
            side_effect=lambda command, **_kwargs: _FakeProcess(command),
        ):
            with self.assertRaisesRegex(WebpagePdfError, "before publication"):
                render_webpage_pdf("https://example.com", self.destination, browser_path=self.browser, cancel_event=cancelled)
        self.assertFalse(self.destination.exists())

    def test_cancellation_during_profile_cleanup_before_publish_leaves_no_destination(self) -> None:
        cancelled = threading.Event()
        original_cleanup = webpage_pdf._cleanup_profile_before_publication

        def cleanup_then_cancel(profile_temporary) -> None:
            original_cleanup(profile_temporary)
            cancelled.set()

        with patch(
            "context_palette.webpage_pdf._cleanup_profile_before_publication",
            side_effect=cleanup_then_cancel,
        ), patch(
            "context_palette.webpage_pdf.subprocess.Popen",
            side_effect=lambda command, **_kwargs: _FakeProcess(command),
        ):
            with self.assertRaisesRegex(WebpagePdfError, "before publication"):
                render_webpage_pdf("https://example.com", self.destination, browser_path=self.browser, cancel_event=cancelled)
        self.assertFalse(self.destination.exists())

    def test_missing_browser_reports_clear_error(self) -> None:
        with patch("context_palette.webpage_pdf.shutil.which", return_value=None), patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(WebpagePdfError, "No supported browser"):
                find_pdf_browser()

    def test_browser_discovery_prefers_edge_over_chrome_in_another_standard_location(self) -> None:
        chrome_root = self.root / "program-files-x86"
        edge_root = self.root / "program-files"
        chrome = chrome_root / "Google" / "Chrome" / "Application" / "chrome.exe"
        edge = edge_root / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        chrome.parent.mkdir(parents=True)
        edge.parent.mkdir(parents=True)
        chrome.write_bytes(b"chrome")
        edge.write_bytes(b"edge")
        with patch.dict(
            os.environ,
            {"ProgramFiles(x86)": str(chrome_root), "ProgramFiles": str(edge_root)},
            clear=True,
        ), patch("context_palette.webpage_pdf.shutil.which", return_value=None):
            self.assertEqual(find_pdf_browser(), edge)


if __name__ == "__main__":
    unittest.main()
