from __future__ import annotations

import unittest

from context_palette.drop_extraction import (
    DropExtractionError,
    DropItem,
    MAX_DROP_ITEMS,
    MAX_DROP_TOTAL_LENGTH,
    MAX_DROP_VALUE_LENGTH,
    MAX_DROP_VALUES,
    extract_drop_values,
    parse_internet_shortcut_url,
)


class DropExtractionTests(unittest.TestCase):
    def test_normalizes_drive_and_unc_paths_without_reading_them(self) -> None:
        self.assertEqual(
            extract_drop_values((r"C:/Work/One%20File.txt", "//server/share/One File.txt")),
            (
                DropItem("path", r"C:\Work\One File.txt"),
                DropItem("path", r"\\server\share\One File.txt"),
            ),
        )

    def test_converts_drive_and_unc_file_uris(self) -> None:
        self.assertEqual(
            extract_drop_values((
                "file:///C:/Work/One%20File.txt",
                "file://localhost/C:/Work/Local%20File.txt",
                "file://server/share/One%20File.txt",
            )),
            (
                DropItem("path", r"C:\Work\One File.txt"),
                DropItem("path", r"C:\Work\Local File.txt"),
                DropItem("path", r"\\server\share\One File.txt"),
            ),
        )

    def test_url_and_shortcut_paths_are_not_resolved_here(self) -> None:
        self.assertEqual(
            extract_drop_values((r"C:/Links/Start.url", r"C:\Links\App.lnk")),
            (
                DropItem("path", r"C:\Links\Start.url"),
                DropItem("path", r"C:\Links\App.lnk"),
            ),
        )

    def test_extracts_embedded_http_urls_in_left_to_right_order(self) -> None:
        self.assertEqual(
            extract_drop_values(("See https://one.example/a). then HTTP://two.example/x?q=A.",)),
            (
                DropItem("url", "https://one.example/a"),
                DropItem("url", "HTTP://two.example/x?q=A"),
            ),
        )

    def test_ordinary_and_braced_looking_text_is_not_tcl_parsed(self) -> None:
        self.assertEqual(
            extract_drop_values(("{Invoice 123 - line item text}", "A { B } C")),
            (
                DropItem("text", "{Invoice 123 - line item text}"),
                DropItem("text", "A { B } C"),
            ),
        )

    def test_mixed_order_and_type_aware_deduplication_preserve_first_spelling(self) -> None:
        self.assertEqual(
            extract_drop_values((
                "hello",
                r"C:/Work/File.txt",
                "https://example.test/A",
                r"c:\work\file.TXT",
                "https://example.test/a",
                "hello",
            )),
            (
                DropItem("text", "hello"),
                DropItem("path", r"C:\Work\File.txt"),
                DropItem("url", "https://example.test/A"),
                DropItem("url", "https://example.test/a"),
            ),
        )

    def test_empty_values_produce_no_items(self) -> None:
        self.assertEqual(extract_drop_values(("", "  ")), ())

    def test_unsupported_or_malformed_uri_stays_ordinary_text(self) -> None:
        self.assertEqual(
            extract_drop_values(("ftp://example.test/file", "file:///not-a-drive", "file:///C:/x?q=1")),
            (
                DropItem("text", "ftp://example.test/file"),
                DropItem("text", "file:///not-a-drive"),
                DropItem("text", "file:///C:/x?q=1"),
            ),
        )

    def test_parses_decoded_internet_shortcut_content_without_file_access(self) -> None:
        self.assertEqual(
            parse_internet_shortcut_url("[InternetShortcut]\nURL=https://example.test/a).\n"),
            "https://example.test/a",
        )
        self.assertIsNone(parse_internet_shortcut_url("[InternetShortcut]\nURL=ftp://example.test\n"))
        self.assertIsNone(parse_internet_shortcut_url("[Other]\nURL=https://example.test\n"))

    def test_rejects_every_input_and_output_bound(self) -> None:
        cases = (
            (tuple("x" for _ in range(MAX_DROP_VALUES + 1)), "value_count"),
            (("x" * (MAX_DROP_VALUE_LENGTH + 1),), "value_length"),
            (
                ("x" * MAX_DROP_VALUE_LENGTH,)
                * (MAX_DROP_TOTAL_LENGTH // MAX_DROP_VALUE_LENGTH + 1),
                "total_length",
            ),
            ((" ".join(f"https://{index}.example" for index in range(MAX_DROP_ITEMS + 1)),), "output_count"),
        )
        for values, code in cases:
            with self.subTest(code=code):
                with self.assertRaisesRegex(DropExtractionError, ".*") as raised:
                    extract_drop_values(values)
                self.assertEqual(raised.exception.code, code)

    def test_value_count_bound_does_not_materialize_an_unbounded_iterable(self) -> None:
        def values():
            while True:
                yield "x"

        with self.assertRaisesRegex(DropExtractionError, "Too many") as raised:
            extract_drop_values(values())
        self.assertEqual(raised.exception.code, "value_count")

    def test_rejects_non_text_values_and_oversized_shortcut_content(self) -> None:
        with self.assertRaisesRegex(DropExtractionError, "must be text"):
            extract_drop_values(("ok", 2))  # type: ignore[arg-type]
        with self.assertRaisesRegex(DropExtractionError, "too large"):
            parse_internet_shortcut_url("x" * (MAX_DROP_VALUE_LENGTH + 1))


if __name__ == "__main__":
    unittest.main()
