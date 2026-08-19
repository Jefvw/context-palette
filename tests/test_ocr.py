from __future__ import annotations

from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from context_palette.ocr import (
    MAX_IMAGE_PIXELS,
    OcrCoordinator,
    OcrError,
    OcrResult,
    OcrSource,
    OcrSourceError,
    RapidOcrProvider,
    clipboard_image_source,
    image_source_from_path,
    image_source_from_text,
)


class FakeClipboardImage:
    def __init__(self, size: tuple[int, int] = (640, 480)) -> None:
        self.size = size
        self.closed = False

    def save(self, stream, *, format: str) -> None:
        assert format == "PNG"
        stream.write(b"portable-png-snapshot")

    def close(self) -> None:
        self.closed = True


class OcrTests(unittest.TestCase):
    def test_exact_absolute_image_path_is_selected_without_guessing_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            image_path = Path(temporary_directory) / "capture.PNG"
            image_path.write_bytes(b"fixture")

            source = image_source_from_text(f'"{image_path}"')

            self.assertIsNotNone(source)
            assert source is not None
            self.assertEqual(source.kind, "file")
            self.assertEqual(source.content, image_path)
            self.assertIsNone(image_source_from_text("notes and an image.png"))
            self.assertIsNone(image_source_from_text("one.png\ntwo.png"))

    def test_image_path_rejects_missing_unsupported_and_oversized_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with self.assertRaisesRegex(OcrSourceError, "does not exist"):
                image_source_from_path(root / "missing.png")
            text_path = root / "notes.txt"
            text_path.write_text("not an image", encoding="utf-8")
            with self.assertRaisesRegex(OcrSourceError, "Choose a PNG"):
                image_source_from_path(text_path)

    def test_clipboard_image_is_snapshotted_without_clipboard_writes(self) -> None:
        image = FakeClipboardImage()
        source = clipboard_image_source(lambda: image)

        self.assertIsNotNone(source)
        assert source is not None
        self.assertEqual(source.kind, "clipboard")
        self.assertEqual(source.content, b"portable-png-snapshot")
        self.assertTrue(image.closed)
        self.assertIsNone(clipboard_image_source(lambda: None))

    def test_clipboard_image_pixel_limit_is_enforced(self) -> None:
        image = FakeClipboardImage((MAX_IMAGE_PIXELS + 1, 1))
        with self.assertRaisesRegex(OcrSourceError, "too large"):
            clipboard_image_source(lambda: image)

    def test_rapidocr_adapter_returns_plain_lines_and_confidence(self) -> None:
        class RawResult:
            txts = (" First line ", "", "Second line")
            scores = (0.8, 0.6, 1.0)

        class Engine:
            def __call__(self, content: Path | bytes) -> RawResult:
                self.content = content
                return RawResult()

        engine = Engine()
        seen_params: list[dict[str, str]] = []

        def factory(*, params: dict[str, str]) -> Engine:
            seen_params.append(params)
            return engine

        provider = RapidOcrProvider(factory, image_validator=lambda _content: None)
        result = provider.recognize(OcrSource("clipboard", "clipboard image", b"png"))

        self.assertEqual(seen_params, [{"Global.log_level": "ERROR"}])
        self.assertEqual(result.text, "First line\nSecond line")
        self.assertEqual(result.line_count, 2)
        self.assertAlmostEqual(result.average_confidence or 0.0, 0.8)

    def test_coordinator_serializes_requests_and_delivers_on_drain(self) -> None:
        expected = OcrResult("Text", 1, 0.2, "Fake OCR", 0.9)

        class Provider:
            def recognize(self, _source: OcrSource) -> OcrResult:
                return expected

        coordinator = OcrCoordinator(Provider)
        completions: list[tuple[OcrResult | None, OcrError | None]] = []
        source = OcrSource("clipboard", "clipboard image", b"png")

        self.assertTrue(coordinator.start(source, lambda result, error: completions.append((result, error))))
        self.assertFalse(coordinator.start(source, lambda _result, _error: None))
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not coordinator.drain():
            time.sleep(0.005)

        self.assertEqual(completions, [(expected, None)])
        self.assertFalse(coordinator.running)

    def test_coordinator_converts_unexpected_failures_to_safe_error(self) -> None:
        class Provider:
            def recognize(self, _source: OcrSource) -> OcrResult:
                raise ValueError("private implementation detail")

        coordinator = OcrCoordinator(Provider)
        completions: list[tuple[OcrResult | None, OcrError | None]] = []
        with patch("context_palette.ocr.LOGGER.exception"):
            coordinator.start(
                OcrSource("clipboard", "clipboard image", b"png"),
                lambda result, error: completions.append((result, error)),
            )
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not coordinator.drain():
                time.sleep(0.005)

        self.assertIsNone(completions[0][0])
        self.assertIsInstance(completions[0][1], OcrError)
        self.assertNotIn("private implementation detail", str(completions[0][1]))


if __name__ == "__main__":
    unittest.main()
