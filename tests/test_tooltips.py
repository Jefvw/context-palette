from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.tooltips import WidgetTooltip


class FakeWidget:
    def __init__(self):
        self.bindings: dict[str, tuple[object, str | None]] = {}

    def bind(self, sequence, callback, add=None):
        self.bindings[sequence] = (callback, add)


class WidgetTooltipTests(unittest.TestCase):
    def test_tooltip_is_available_to_mouse_and_keyboard_users(self):
        widget = FakeWidget()

        tooltip = WidgetTooltip(widget, "Capture — Save clipboard text.")

        self.assertEqual(
            set(widget.bindings),
            {
                "<Enter>",
                "<Leave>",
                "<FocusIn>",
                "<FocusOut>",
                "<ButtonPress>",
                "<Destroy>",
            },
        )
        self.assertIs(widget.bindings["<FocusIn>"][0].__self__, tooltip)
        self.assertEqual(widget.bindings["<FocusIn>"][0].__name__, "_schedule")
        self.assertIs(widget.bindings["<FocusOut>"][0].__self__, tooltip)
        self.assertEqual(widget.bindings["<FocusOut>"][0].__name__, "hide")
        self.assertTrue(all(add == "+" for _, add in widget.bindings.values()))


if __name__ == "__main__":
    unittest.main()
