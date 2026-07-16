from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.style import COLORS, configure_theme


class FakeRoot:
    def __init__(self) -> None:
        self.options = []
        self.configuration = {}

    def option_add(self, pattern, value) -> None:
        self.options.append((pattern, value))

    def configure(self, **options) -> None:
        self.configuration.update(options)


class FakeStyle:
    def __init__(self) -> None:
        self.used_theme = None
        self.configurations = {}
        self.maps = {}

    def theme_names(self):
        return ("vista", "clam")

    def theme_use(self, theme=None):
        if theme is not None:
            self.used_theme = theme

    def configure(self, style_name, **options):
        self.configurations[style_name] = options

    def map(self, style_name, **options):
        self.maps[style_name] = options


class StyleTests(unittest.TestCase):
    def test_reference_palette_uses_supplied_grey_teal_and_aqua_colors(self):
        self.assertEqual(COLORS["topic_header"], "#a6a6a6")
        self.assertEqual(COLORS["accent"], "#43bdb3")
        self.assertEqual(COLORS["row_aqua"], "#cce7e5")
        self.assertEqual(COLORS["row_light"], "#e4f1f0")

    def test_configure_theme_centralizes_fonts_colors_and_interaction_states(self):
        root = FakeRoot()
        style = FakeStyle()

        result = configure_theme(root, style)

        self.assertIs(result, style)
        self.assertEqual(style.used_theme, "clam")
        self.assertIn(("*Font", "{Segoe UI} 10"), root.options)
        self.assertEqual(root.configuration["background"], COLORS["background"])
        self.assertEqual(style.configurations["Heading.TLabel"]["font"], ("Segoe UI Semibold", 11))
        self.assertEqual(style.configurations["Accent.TButton"]["background"], COLORS["accent"])
        self.assertEqual(style.configurations["Surface.TLabel"]["background"], COLORS["row_light"])
        self.assertIn("background", style.maps["TButton"])
        self.assertIn("bordercolor", style.maps["TEntry"])


if __name__ == "__main__":
    unittest.main()
