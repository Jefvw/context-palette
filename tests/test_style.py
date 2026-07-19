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
        self.layouts = {}

    def theme_names(self):
        return ("vista", "clam")

    def theme_use(self, theme=None):
        if theme is not None:
            self.used_theme = theme

    def configure(self, style_name, **options):
        self.configurations[style_name] = options

    def map(self, style_name, **options):
        self.maps[style_name] = options

    def layout(self, style_name, specification):
        self.layouts[style_name] = specification


class StyleTests(unittest.TestCase):
    def test_palette_uses_high_contrast_text_and_selection_colors(self):
        self.assertEqual(COLORS["text"], "#1f2933")
        self.assertEqual(COLORS["accent"], "#087f78")
        self.assertEqual(COLORS["focus"], "#005fcc")
        self.assertNotEqual(COLORS["row_aqua"], COLORS["row_light"])

    def test_configure_theme_centralizes_fonts_colors_and_interaction_states(self):
        root = FakeRoot()
        style = FakeStyle()

        result = configure_theme(root, style)

        self.assertIs(result, style)
        self.assertEqual(style.used_theme, "clam")
        self.assertIn(("*Font", "{Segoe UI} 10"), root.options)
        self.assertEqual(root.configuration["background"], COLORS["background"])
        self.assertEqual(style.configurations["Title.TLabel"]["font"], ("Segoe UI Semibold", 14))
        self.assertEqual(style.configurations["Heading.TLabel"]["font"], ("Segoe UI Semibold", 11))
        self.assertEqual(style.configurations["Accent.TButton"]["background"], COLORS["accent"])
        self.assertEqual(style.configurations["Surface.TLabel"]["background"], COLORS["surface"])
        self.assertEqual(
            style.configurations["SurfaceMenu.TLabel"]["background"],
            COLORS["surface"],
        )
        self.assertIn("SurfaceMenu.TLabel", style.layouts)
        self.assertEqual(style.configurations["Treeview"]["rowheight"], 25)
        self.assertIn("background", style.maps["TButton"])
        self.assertIn("bordercolor", style.maps["TEntry"])


if __name__ == "__main__":
    unittest.main()
