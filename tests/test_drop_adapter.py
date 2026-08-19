from __future__ import annotations

import subprocess
import tkinter as tk
import unittest

from context_palette.drop_adapter import (
    MAX_RAW_DROP_LENGTH,
    DropResolutionCoordinator,
    decode_drop_event,
    decode_drop_values,
    resolve_decoded_values,
)
from context_palette.drop_extraction import DropItem


class _Event:
    def __init__(self, data: object, widget: object) -> None:
        self.data = data
        self.widget = widget


class DropAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tcl = tk.Tcl()

    def test_files_use_tcl_splitlist_and_preserve_order(self) -> None:
        event = _Event("{C:/A B.txt} C:/C.txt", self.tcl)
        result = decode_drop_event(event, "DND_Files")
        self.assertEqual(result.items, (DropItem("path", r"C:\A B.txt"), DropItem("path", r"C:\C.txt")))

    def test_text_is_one_native_payload_even_when_it_looks_braced(self) -> None:
        values, error = decode_drop_values(_Event("{A B} C", self.tcl), "DND_Text")
        self.assertIsNone(error)
        self.assertEqual(values, ("{A B} C",))
        self.assertEqual(decode_drop_event(_Event("{A B} C", self.tcl), "DND_Text").items, (DropItem("text", "{A B} C"),))

    def test_rejects_oversized_invalid_and_unsupported_payloads(self) -> None:
        for event, kind, code in (
            (_Event("x" * (MAX_RAW_DROP_LENGTH + 1), self.tcl), "DND_Text", "payload_length"),
            (_Event(3, self.tcl), "DND_Text", "payload_type"),
            (_Event("x", self.tcl), "DND_HTML", "unsupported_type"),
            (_Event("{unclosed", self.tcl), "DND_Files", "tcl_decode"),
        ):
            with self.subTest(code=code):
                result = decode_drop_event(event, kind)
                self.assertEqual(result.error.code if result.error else None, code)

    def test_url_shortcut_success_and_safe_fallback(self) -> None:
        success = resolve_decoded_values(
            (r"C:\Links\One.url",),
            read_bytes=lambda _path, _maximum: b"[InternetShortcut]\r\nURL=https://example.test/a\r\n",
        )
        self.assertEqual(success.items, (DropItem("url", "https://example.test/a"),))
        fallback = resolve_decoded_values(
            (r"C:\Links\One.url",), read_bytes=lambda _path, _maximum: b"[InternetShortcut]\nURL=ftp://bad"
        )
        self.assertEqual(fallback.items, (DropItem("path", r"C:\Links\One.url"),))
        self.assertEqual(fallback.warnings[0].code, "url_unresolved")

        utf16 = resolve_decoded_values(
            (r"C:\Links\Two.url",),
            read_bytes=lambda _path, _maximum: (
                "[InternetShortcut]\r\nURL=https://example.test/utf16\r\n".encode(
                    "utf-16"
                )
            ),
        )
        self.assertEqual(
            utf16.items,
            (DropItem("url", "https://example.test/utf16"),),
        )

    def test_lnk_uses_only_target_path_and_falls_back_on_timeout(self) -> None:
        calls: list[tuple[object, dict[str, object]]] = []
        def completed(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args[0], 0, stdout="C:/Target/App.exe", stderr="ignored")

        result = resolve_decoded_values((r"C:\Links\App.lnk",), run_process=completed)
        self.assertEqual(result.items, (DropItem("path", r"C:\Target\App.exe"),))
        command = calls[0][0][0]
        self.assertEqual(command[-1], r"C:\Links\App.lnk")
        self.assertIn("TargetPath", command[-2])
        self.assertNotIn("Arguments", command[-2])
        self.assertFalse(calls[0][1]["shell"])
        self.assertLessEqual(calls[0][1]["timeout"], 5)
        self.assertEqual(
            calls[0][1]["creationflags"],
            getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        def timed_out(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired("powershell.exe", 1)

        fallback = resolve_decoded_values((r"C:\Links\App.lnk",), run_process=timed_out)
        self.assertEqual(fallback.items, (DropItem("path", r"C:\Links\App.lnk"),))
        self.assertEqual(fallback.warnings[0].code, "lnk_unresolved")

        text_target = resolve_decoded_values(
            (r"C:\Links\App.lnk",),
            run_process=lambda *args, **kwargs: subprocess.CompletedProcess(
                args[0], 0, stdout="relative command text", stderr=""
            ),
        )
        self.assertEqual(
            text_target.items,
            (DropItem("path", r"C:\Links\App.lnk"),),
        )

    def test_resolution_preserves_order_and_type_aware_deduplication(self) -> None:
        def process(*args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(args[0], 0, stdout="C:/Work/File.txt", stderr="")
        result = resolve_decoded_values(
            ("hello", r"C:/Work/File.txt", r"c:\links\item.lnk", "hello", "https://example.test/A"),
            run_process=process,
        )
        self.assertEqual(
            result.items,
            (DropItem("text", "hello"), DropItem("path", r"C:\Work\File.txt"), DropItem("url", "https://example.test/A")),
        )

    def test_coordinator_is_single_flight_and_delivers_completed_result(self) -> None:
        coordinator = DropResolutionCoordinator(lambda values: resolve_decoded_values(values))
        self.assertTrue(coordinator.start(("hello",)))
        self.assertFalse(coordinator.start(("later",)))
        for _ in range(50):
            result = coordinator.drain()
            if result is not None:
                break
            __import__("time").sleep(0.01)
        self.assertEqual(result.items, (DropItem("text", "hello"),))


if __name__ == "__main__":
    unittest.main()
