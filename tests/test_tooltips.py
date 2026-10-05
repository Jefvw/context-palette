from pathlib import Path
import sys
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.tooltips import WidgetTooltip, widget_tooltip_position


class FakeWidget:
    def __init__(self):
        self.bindings: dict[str, tuple[object, str | None]] = {}

    def bind(self, sequence, callback, add=None):
        self.bindings[sequence] = (callback, add)

    def after(self, delay, callback):
        self.scheduled = (delay, callback)
        return "pending-tooltip"

    def after_cancel(self, after_id):
        self.cancelled = after_id


class WidgetTooltipTests(unittest.TestCase):
    def test_position_prefers_below_when_it_fits(self):
        self.assertEqual(
            widget_tooltip_position(
                (100, 100, 80, 30),
                (200, 60),
                (0, 0, 1920, 1080),
            ),
            (100, 134),
        )

    def test_position_moves_above_and_clamps_at_bottom_right(self):
        self.assertEqual(
            widget_tooltip_position(
                (1870, 1030, 40, 30),
                (240, 80),
                (0, 0, 1920, 1080),
            ),
            (1672, 946),
        )

    def test_position_supports_negative_secondary_monitor_coordinates(self):
        self.assertEqual(
            widget_tooltip_position(
                (-120, 980, 60, 30),
                (220, 70),
                (-1920, 0, 0, 1080),
            ),
            (-228, 906),
        )

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

    def test_hover_only_help_does_not_follow_focus_and_typing_cancels_it(self):
        widget = FakeWidget()
        tooltip = WidgetTooltip(widget, "Find help", show_on_focus=False)
        self.assertNotIn("<FocusIn>", widget.bindings)
        self.assertIsNone(tooltip.after_id)
        widget.bindings["<Enter>"][0]()
        self.assertEqual(widget.scheduled, (500, tooltip.show))
        self.assertEqual(tooltip.after_id, "pending-tooltip")
        visible = Mock()
        tooltip.window = visible
        widget.bindings["<KeyPress>"][0]()
        self.assertEqual(widget.cancelled, "pending-tooltip")
        visible.destroy.assert_called_once_with()
        self.assertIsNone(tooltip.after_id)
        self.assertIsNone(tooltip.window)
        self.assertTrue(all(add == "+" for _, add in widget.bindings.values()))


if __name__ == "__main__":
    unittest.main()
