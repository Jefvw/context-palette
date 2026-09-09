from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.ui_icons import ICON_ROWS, _xbm_data


class UiIconTests(unittest.TestCase):
    def test_toolbar_bitmaps_are_bounded_valid_xbm_shapes(self) -> None:
        for name, rows in ICON_ROWS.items():
            with self.subTest(name=name):
                self.assertEqual(len(rows), 16)
                self.assertTrue(all(len(row) == 16 for row in rows))
                self.assertTrue(set("".join(rows)) <= {".", "#"})
                self.assertIn(f"#define {name}_width 16", _xbm_data(name, rows))

    def test_create_action_icon_is_distinct_from_edit_and_input_suggestion(self) -> None:
        self.assertNotEqual(ICON_ROWS["create_action"], ICON_ROWS["edit"])
        self.assertNotEqual(ICON_ROWS["create_action"], ICON_ROWS["create_from_input"])

    def test_refined_toolbar_icons_are_distinct_and_use_bounded_ink(self) -> None:
        names = ("back", "forward", "filters", "configure", "text_tools", "ocr")
        icons = [ICON_ROWS[name] for name in names]

        self.assertEqual(len(set(icons)), len(icons))
        for name, rows in zip(names, icons, strict=True):
            with self.subTest(name=name):
                ink = sum(pixel == "#" for row in rows for pixel in row)
                self.assertGreater(ink, 12)
                self.assertLess(ink, 100)

    def test_navigation_icons_are_exact_horizontal_mirrors(self) -> None:
        self.assertEqual(
            ICON_ROWS["forward"],
            tuple(row[::-1] for row in ICON_ROWS["back"]),
        )

    def test_create_action_icon_keeps_a_margin_for_its_page_and_plus(self) -> None:
        rows = ICON_ROWS["create_action"]

        self.assertTrue(all(row[0] == "." and row[-1] == "." for row in rows))
        self.assertTrue(all(pixel == "." for pixel in rows[0]))
        self.assertTrue(all(pixel == "." for pixel in rows[-1]))


if __name__ == "__main__":
    unittest.main()
