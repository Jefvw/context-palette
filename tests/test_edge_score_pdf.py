from __future__ import annotations

from pathlib import Path
import io
import json
import gc
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import queue
import subprocess

from context_palette.edge_score_pdf import (
    EdgeScorePdfCancelled,
    EdgeScorePdfError,
    EdgeScorePdfHelperTerminationError,
    EdgeScorePdfManualSave,
    _filename,
    _drain_lines,
    _parse_response,
    _publish_with_suffix,
    _validate_pdf,
    _validate_ultimate_guitar_url,
    _run_helper,
    save_edge_score_pdf,
)


class _FakeProcess:
    def __init__(self, output: str = "", *, running: bool = False, stubborn: bool = False, stream=None):
        self.stdout = io.StringIO(output) if stream is None else stream
        self.returncode = None if running else 0
        self.stubborn = stubborn
        self.terminated = 0
        self.killed = 0

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated += 1
        if not self.stubborn:
            self.returncode = 1

    def kill(self):
        self.killed += 1
        if not self.stubborn:
            self.returncode = 1

    def wait(self, timeout=None):
        if self.stubborn:
            raise subprocess.TimeoutExpired("powershell", timeout)
        return self.returncode


class _BlockingStream:
    def __init__(self):
        self.release = threading.Event()
        self.close_called = False

    def __iter__(self):
        return self

    def __next__(self):
        self.release.wait()
        raise StopIteration

    def close(self):
        self.close_called = True


class EdgeScorePdfTests(unittest.TestCase):
    def test_only_accepts_supported_ultimate_guitar_score_urls(self) -> None:
        _validate_ultimate_guitar_url("https://tabs.ultimate-guitar.com/tab/radiohead/there-there-official-2463302")
        _validate_ultimate_guitar_url("https://tabs.ultimate-guitar.com/tab/j-j-cale/dont-cry-sister-guitar-pro-2369257")
        for value in (
            "http://tabs.ultimate-guitar.com/tab/a",
            "https://www.ultimate-guitar.com/tab/a",
            "https://tabs.ultimate-guitar.com/song/a",
            "https://tabs.ultimate-guitar.com/tab/radiohead/there-there-2463302",
            "https://user@tabs.ultimate-guitar.com/tab/radiohead/there-there-official-2463302",
            "https://tabs.ultimate-guitar.com:443/tab/radiohead/there-there-official-2463302",
            "https://tabs.ultimate-guitar.com:notaport/tab/radiohead/there-there-official-2463302",
        ):
            with self.subTest(value=value):
                with self.assertRaises(EdgeScorePdfError):
                    _validate_ultimate_guitar_url(value)

    def test_title_filename_is_portable_and_bounded(self) -> None:
        name = _filename('There There (Official) / Radiohead: "Tabs"')
        self.assertTrue(name.endswith(".pdf"))
        self.assertNotRegex(name, r'[<>:"/\\|?*]')
        self.assertLessEqual(len(name), 124)

    def test_filename_handles_windows_reserved_extensions_and_unicode(self) -> None:
        self.assertEqual(_filename("CON.txt"), "score-CON.txt.pdf")
        self.assertEqual(_filename("Beyoncé — déjà vu"), "Beyoncé — déjà vu.pdf")

    def test_publication_keeps_existing_files_and_suffixes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            first = folder / "Score.pdf"
            first.write_bytes(b"old")
            staged = folder / "stage.pdf"
            staged.write_bytes(b"%PDF-1.4\n%%EOF")
            saved = _publish_with_suffix(staged, folder, "Score")
            self.assertEqual(saved.name, "Score (1).pdf")
            self.assertEqual(first.read_bytes(), b"old")

    def test_response_requires_bounded_string_identity(self) -> None:
        self.assertEqual(_parse_response({"url": "https://tabs.ultimate-guitar.com/tab/a-1", "title": "Song"})[1], "Song")
        for response in ({}, {"url": 3, "title": "x"}, {"url": "x", "title": " "}):
            with self.subTest(response=response):
                with self.assertRaises(EdgeScorePdfError):
                    _parse_response(response)

    def test_cancelled_before_start_never_launches_powershell(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            event = threading.Event(); event.set()
            with patch("context_palette.edge_score_pdf.subprocess.Popen") as start:
                with self.assertRaises(EdgeScorePdfCancelled):
                    save_edge_score_pdf(123, Path(temporary), cancel_event=event)
            start.assert_not_called()

    def test_windows_only_stops_before_staging_or_helper_launch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch("context_palette.edge_score_pdf.os.name", "posix"):
            with patch("context_palette.edge_score_pdf.subprocess.Popen") as start:
                with self.assertRaisesRegex(EdgeScorePdfError, "only on Windows"):
                    save_edge_score_pdf(123, Path(temporary))
            start.assert_not_called()

    def test_reader_maps_only_fixed_protocol_codes_and_ignores_other_output(self) -> None:
        lines: queue.Queue[str] = queue.Queue()
        lines.put("private browser output https://secret.example/?token=hidden")
        lines.put("CONTEXT_PALETTE_PROGRESS:opening")
        lines.put("CONTEXT_PALETTE_ERROR:choose_pdf_printer")
        lines.put("CONTEXT_PALETTE_RESULT:" + json.dumps({"url": "https://tabs.ultimate-guitar.com/tab/a-1", "title": "Song"}))
        progress: list[str] = []
        result, error = _drain_lines(lines, progress.append, None, None)
        self.assertEqual(progress, ["Opening Edge's score print preview."])
        self.assertEqual(str(error), "Select Save as PDF in Edge print preview, then try again.")
        self.assertEqual(result["title"], "Song")

    def test_reader_rejects_duplicate_result_frames(self) -> None:
        lines: queue.Queue[str] = queue.Queue()
        frame = "CONTEXT_PALETTE_RESULT:" + json.dumps({"url": "https://tabs.ultimate-guitar.com/tab/a-1", "title": "Song"})
        lines.put(frame)
        lines.put(frame)
        with self.assertRaisesRegex(EdgeScorePdfError, "more than one"):
            _drain_lines(lines, None, None, None)

    def test_control_failures_identify_the_stage_without_exposing_raw_output(self) -> None:
        for code, expected in (
            ("score_print_missing", "score's PRINT button"),
            ("score_print_ambiguous", "More than one control"),
            ("score_print_disabled", "finish loading"),
            ("score_print_hidden", "Make the button visible"),
            ("address_missing", "Edge's address bar"),
            ("printer_selector_ambiguous", "printer selector"),
            ("filename_ambiguous", "filename field"),
            ("native_save_missing", "Save button in Windows Save As"),
            ("unrecognized_private_detail", "could not verify or save"),
        ):
            with self.subTest(code=code):
                lines: queue.Queue[str] = queue.Queue()
                lines.put("private browser output")
                lines.put("CONTEXT_PALETTE_ERROR:" + code)
                result, error = _drain_lines(lines, None, None, None)
                self.assertIsNone(result)
                self.assertIn(expected, str(error))
                self.assertNotIn("private", str(error))

    def test_only_filename_missing_becomes_manual_handoff_after_helper_exit(self) -> None:
        for code in ("filename_missing", "filename_ambiguous", "native_save_missing",
                     "focus_changed", "save_dialog_timeout", "unknown"):
            with self.subTest(code=code):
                process = _FakeProcess("CONTEXT_PALETTE_ERROR:" + code + "\n")
                process.returncode = 1
                with patch("context_palette.edge_score_pdf.subprocess.Popen", return_value=process):
                    with self.assertRaises(EdgeScorePdfError) as raised:
                        _run_helper(["powershell"], cancel_event=None, progress=None, timeout=1)
                self.assertEqual(isinstance(raised.exception, EdgeScorePdfManualSave), code == "filename_missing")
                self.assertTrue(process.stdout.closed)

    def test_conflicting_helper_output_never_becomes_manual_handoff(self) -> None:
        handoff = "CONTEXT_PALETTE_ERROR:filename_missing\n"
        failure = "CONTEXT_PALETTE_ERROR:focus_changed\n"
        result = 'CONTEXT_PALETTE_RESULT:{"title":"Song","url":"unexpected"}\n'
        for output in (failure + handoff, handoff + failure, result + handoff):
            for returncode in (0, 1):
                with self.subTest(output=output, returncode=returncode):
                    process = _FakeProcess(output)
                    process.returncode = returncode
                    with patch("context_palette.edge_score_pdf.subprocess.Popen", return_value=process):
                        with self.assertRaises(EdgeScorePdfError) as raised:
                            _run_helper(["powershell"], cancel_event=None, progress=None, timeout=1)
                    self.assertNotIsInstance(raised.exception, EdgeScorePdfManualSave)

    def test_manual_handoff_cleans_staging_and_does_not_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            process = _FakeProcess("CONTEXT_PALETTE_ERROR:filename_missing\n")
            process.returncode = 1
            with (
                patch("context_palette.edge_score_pdf.subprocess.Popen", return_value=process),
                patch("context_palette.edge_score_pdf.shutil.which", return_value="powershell.exe"),
                patch("context_palette.edge_score_pdf._publish_with_suffix") as publish,
            ):
                with self.assertRaises(EdgeScorePdfManualSave):
                    save_edge_score_pdf(123, folder)
            publish.assert_not_called()
            self.assertEqual(list(folder.iterdir()), [])

    def test_helper_joins_reader_before_the_final_drain(self) -> None:
        process = _FakeProcess(
            "CONTEXT_PALETTE_RESULT:" + json.dumps({"url": "https://tabs.ultimate-guitar.com/tab/a-1", "title": "Song"}) + "\n"
        )
        with patch("context_palette.edge_score_pdf.subprocess.Popen", return_value=process):
            result = _run_helper(["powershell"], cancel_event=None, progress=None, timeout=1)
        self.assertEqual(result["title"], "Song")
        self.assertTrue(process.stdout.closed)

    def test_cancel_waits_for_owned_helper_to_exit(self) -> None:
        process = _FakeProcess(running=True)
        event = threading.Event(); event.set()
        with patch("context_palette.edge_score_pdf.subprocess.Popen", return_value=process):
            with self.assertRaises(EdgeScorePdfCancelled):
                _run_helper(["powershell"], cancel_event=event, progress=None, timeout=1)
        self.assertGreaterEqual(process.terminated, 1)
        self.assertIsNotNone(process.returncode)

    def test_timeout_waits_for_owned_helper_to_exit(self) -> None:
        process = _FakeProcess(running=True)
        with (
            patch("context_palette.edge_score_pdf.subprocess.Popen", return_value=process),
            patch("context_palette.edge_score_pdf.time.monotonic", side_effect=(0.0, 2.0)),
        ):
            with self.assertRaisesRegex(EdgeScorePdfError, "timed out"):
                _run_helper(["powershell"], cancel_event=None, progress=None, timeout=1)
        self.assertGreaterEqual(process.terminated, 1)

    def test_unstoppable_helper_reports_unknown_state(self) -> None:
        process = _FakeProcess(running=True, stubborn=True)
        event = threading.Event(); event.set()
        with patch("context_palette.edge_score_pdf.subprocess.Popen", return_value=process):
            with self.assertRaises(EdgeScorePdfHelperTerminationError):
                _run_helper(["powershell"], cancel_event=event, progress=None, timeout=1)
        self.assertGreaterEqual(process.killed, 1)

    def test_unstoppable_helper_does_not_close_a_live_reader_pipe(self) -> None:
        stream = _BlockingStream()
        process = _FakeProcess(running=True, stubborn=True, stream=stream)
        event = threading.Event(); event.set()
        try:
            with patch("context_palette.edge_score_pdf.subprocess.Popen", return_value=process):
                with self.assertRaises(EdgeScorePdfHelperTerminationError):
                    _run_helper(["powershell"], cancel_event=event, progress=None, timeout=1)
            self.assertFalse(stream.close_called)
        finally:
            stream.release.set()

    def test_cancellation_immediately_before_publish_writes_no_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            event = threading.Event()

            def helper(command, **_kwargs):
                Path(command[-1]).write_bytes(b"%PDF-1.4\n%%EOF")
                return {"url": "https://tabs.ultimate-guitar.com/tab/radiohead/there-there-official-2463302", "title": "Song"}

            def validate_then_cancel(path):
                _validate_pdf(path)
                event.set()

            with (
                patch("context_palette.edge_score_pdf._run_helper", side_effect=helper),
                patch("context_palette.edge_score_pdf._validate_pdf", side_effect=validate_then_cancel),
                patch("context_palette.edge_score_pdf._publish_with_suffix") as publish,
                patch("context_palette.edge_score_pdf.shutil.which", return_value="powershell.exe"),
            ):
                with self.assertRaises(EdgeScorePdfCancelled):
                    save_edge_score_pdf(123, folder, cancel_event=event)
            publish.assert_not_called()

    def test_invalid_staged_pdf_is_never_published(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)

            def helper(command, **_kwargs):
                Path(command[-1]).write_bytes(b"not a PDF")
                return {"url": "https://tabs.ultimate-guitar.com/tab/radiohead/there-there-official-2463302", "title": "Song"}

            with (
                patch("context_palette.edge_score_pdf._run_helper", side_effect=helper),
                patch("context_palette.edge_score_pdf._publish_with_suffix") as publish,
                patch("context_palette.edge_score_pdf.shutil.which", return_value="powershell.exe"),
            ):
                with self.assertRaisesRegex(EdgeScorePdfError, "valid staged PDF"):
                    save_edge_score_pdf(123, folder)
            publish.assert_not_called()

    def test_unknown_helper_termination_preserves_actual_staging_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            staging = folder / ".staging-that-must-remain"
            staging.mkdir()
            with (
                patch("context_palette.edge_score_pdf.tempfile.mkdtemp", return_value=str(staging)),
                patch("context_palette.edge_score_pdf._run_helper", side_effect=EdgeScorePdfHelperTerminationError("helper still live")),
                patch("context_palette.edge_score_pdf.shutil.which", return_value="powershell.exe"),
            ):
                with self.assertRaises(EdgeScorePdfHelperTerminationError):
                    save_edge_score_pdf(123, folder)
            gc.collect()
            self.assertTrue(staging.is_dir())


if __name__ == "__main__":
    unittest.main()
