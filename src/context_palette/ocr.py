from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import importlib.metadata
import logging
from pathlib import Path
import queue
import threading
import time
from typing import Callable, Protocol
import warnings


LOGGER = logging.getLogger(__name__)

IMAGE_FILE_SUFFIXES = frozenset(
    {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
)
MAX_IMAGE_FILE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000


class OcrError(RuntimeError):
    """Image text extraction could not complete safely."""


class OcrUnavailableError(OcrError):
    """The optional local OCR runtime is not available."""


class OcrSourceError(OcrError):
    """The selected clipboard or file source is not a usable image."""


@dataclass(frozen=True, slots=True)
class OcrSource:
    kind: str
    label: str
    content: Path | bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class OcrResult:
    text: str
    line_count: int
    elapsed_seconds: float
    engine: str
    average_confidence: float | None = None


class OcrProvider(Protocol):
    def recognize(self, source: OcrSource) -> OcrResult: ...


def image_source_from_text(value: str) -> OcrSource | None:
    """Return one exact absolute image path, or None for ordinary workspace text."""

    candidate = value.strip()
    if (
        len(candidate) >= 2
        and candidate[0] == candidate[-1]
        and candidate[0] in {'"', "'"}
    ):
        candidate = candidate[1:-1].strip()
    if not candidate or "\n" in candidate or "\r" in candidate:
        return None

    path = Path(candidate)
    if not path.is_absolute():
        return None
    return image_source_from_path(path)


def image_source_from_path(path: Path) -> OcrSource:
    candidate = Path(path)
    if candidate.suffix.casefold() not in IMAGE_FILE_SUFFIXES:
        raise OcrSourceError(
            "Choose a PNG, JPEG, BMP, GIF, TIFF, or WebP image file."
        )
    if not candidate.is_file():
        raise OcrSourceError("The selected image file does not exist or is unavailable.")
    try:
        size = candidate.stat().st_size
    except OSError as exc:
        raise OcrSourceError("Windows could not inspect the selected image file.") from exc
    if size > MAX_IMAGE_FILE_BYTES:
        raise OcrSourceError(
            "The selected image is larger than 50 MB. Choose a smaller image."
        )
    return OcrSource("file", str(candidate), candidate)


def clipboard_image_source(
    grabber: Callable[[], object] | None = None,
) -> OcrSource | None:
    """Snapshot a clipboard bitmap as PNG bytes without changing the clipboard."""

    if grabber is None:
        try:
            from PIL import ImageGrab
        except (ImportError, OSError) as exc:
            raise OcrUnavailableError(
                "The optional local OCR component is not set up on this copy of "
                "Context Palette."
            ) from exc
        grabber = ImageGrab.grabclipboard

    try:
        grabbed = grabber()
    except OSError as exc:
        raise OcrSourceError("Windows could not read the clipboard image.") from exc
    if grabbed is None:
        return None
    if isinstance(grabbed, list):
        image_paths = [
            Path(value)
            for value in grabbed
            if Path(value).suffix.casefold() in IMAGE_FILE_SUFFIXES
        ]
        if len(image_paths) == 1:
            return image_source_from_path(image_paths[0])
        return None

    dimensions = getattr(grabbed, "size", None)
    save = getattr(grabbed, "save", None)
    if (
        not isinstance(dimensions, tuple)
        or len(dimensions) != 2
        or not callable(save)
    ):
        return None
    width, height = dimensions
    if (
        not isinstance(width, int)
        or not isinstance(height, int)
        or width <= 0
        or height <= 0
    ):
        raise OcrSourceError("The clipboard image has invalid dimensions.")
    if width * height > MAX_IMAGE_PIXELS:
        raise OcrSourceError(
            "The clipboard image is too large to process safely. Capture a smaller region."
        )

    output = BytesIO()
    try:
        save(output, format="PNG")
    except (OSError, ValueError) as exc:
        raise OcrSourceError("Windows returned an unreadable clipboard image.") from exc
    finally:
        close = getattr(grabbed, "close", None)
        if callable(close):
            close()
    content = output.getvalue()
    if len(content) > MAX_IMAGE_FILE_BYTES:
        raise OcrSourceError(
            "The clipboard image is too large to process safely. Capture a smaller region."
        )
    return OcrSource("clipboard", "clipboard image", content)


class RapidOcrProvider:
    """Lazy adapter around the optional, fully local RapidOCR runtime."""

    def __init__(
        self,
        engine_factory: Callable[..., object] | None = None,
        image_validator: Callable[[Path | bytes], None] | None = None,
    ) -> None:
        if engine_factory is None:
            try:
                from rapidocr import RapidOCR
            except (ImportError, OSError) as exc:
                raise OcrUnavailableError(
                    "The optional local OCR component is not set up on this copy of "
                    "Context Palette."
                ) from exc
            engine_factory = RapidOCR
        try:
            self._engine = engine_factory(params={"Global.log_level": "ERROR"})
        except Exception as exc:
            raise OcrUnavailableError(
                "The local OCR component could not start on this computer."
            ) from exc
        try:
            version = importlib.metadata.version("rapidocr")
        except importlib.metadata.PackageNotFoundError:
            version = ""
        self.engine_name = f"RapidOCR {version}".strip()
        self._image_validator = image_validator or _validate_image_content

    def recognize(self, source: OcrSource) -> OcrResult:
        self._image_validator(source.content)
        started = time.perf_counter()
        try:
            raw_result = self._engine(source.content)
        except Exception as exc:
            raise OcrError(
                "The image could not be read by the local OCR engine. Nothing was changed."
            ) from exc
        elapsed = time.perf_counter() - started
        raw_lines = getattr(raw_result, "txts", None) or ()
        lines = tuple(str(line).strip() for line in raw_lines if str(line).strip())
        raw_scores = getattr(raw_result, "scores", None) or ()
        scores = tuple(
            float(score)
            for score in raw_scores
            if isinstance(score, (float, int))
        )
        average = sum(scores) / len(scores) if scores else None
        return OcrResult(
            "\n".join(lines),
            len(lines),
            elapsed,
            self.engine_name,
            average,
        )


def _validate_image_content(content: Path | bytes) -> None:
    """Reject damaged or decompression-bomb images before native inference."""

    try:
        from PIL import Image, UnidentifiedImageError
    except (ImportError, OSError) as exc:
        raise OcrUnavailableError(
            "The optional local OCR component is incomplete on this computer."
        ) from exc

    source = BytesIO(content) if isinstance(content, bytes) else content
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as image:
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                    raise OcrSourceError(
                        "The image is too large to process safely. Capture a smaller region."
                    )
                image.verify()
    except OcrSourceError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise OcrSourceError(
            "The image is too large to process safely. Capture a smaller region."
        ) from exc
    except (OSError, SyntaxError, UnidentifiedImageError, ValueError) as exc:
        raise OcrSourceError(
            "The selected image is damaged or uses an unsupported encoding."
        ) from exc


class OcrCoordinator:
    """Run one local OCR request off-thread and deliver it through UI polling."""

    def __init__(
        self,
        provider_factory: Callable[[], OcrProvider] = RapidOcrProvider,
    ) -> None:
        self._provider_factory = provider_factory
        self._provider: OcrProvider | None = None
        self._lock = threading.Lock()
        self._running = False
        self._completed: queue.SimpleQueue[
            tuple[
                OcrResult | None,
                OcrError | None,
                Callable[[OcrResult | None, OcrError | None], None],
            ]
        ] = queue.SimpleQueue()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def start(
        self,
        source: OcrSource,
        on_complete: Callable[[OcrResult | None, OcrError | None], None],
    ) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True

        def work() -> None:
            result: OcrResult | None = None
            error: OcrError | None = None
            try:
                if self._provider is None:
                    self._provider = self._provider_factory()
                result = self._provider.recognize(source)
            except OcrError as exc:
                error = exc
            except Exception:
                LOGGER.exception("Unexpected local OCR background failure")
                error = OcrError(
                    "Image text extraction stopped because of an unexpected local error. "
                    "Nothing was changed."
                )
            self._completed.put((result, error, on_complete))

        threading.Thread(target=work, daemon=True, name="local-ocr").start()
        return True

    def drain(self) -> bool:
        try:
            result, error, on_complete = self._completed.get_nowait()
        except queue.Empty:
            return False
        try:
            on_complete(result, error)
        finally:
            with self._lock:
                self._running = False
        return True
