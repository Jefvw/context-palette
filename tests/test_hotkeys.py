import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.hotkeys import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    VK_F9,
    VK_P,
    WM_HOTKEY,
    window_position_near_cursor,
)


class HotkeyTests(unittest.TestCase):
    def test_ctrl_alt_p_constants(self):
        self.assertEqual(MOD_CONTROL, 0x0002)
        self.assertEqual(MOD_ALT, 0x0001)
        self.assertEqual(VK_P, 0x50)
        self.assertEqual(VK_F9, 0x78)
        self.assertEqual(MOD_NOREPEAT, 0x4000)
        self.assertEqual(WM_HOTKEY, 0x0312)

    def test_cursor_is_window_top_left_when_space_is_available(self):
        self.assertEqual(
            window_position_near_cursor((100, 100), (300, 200), (0, 0, 1920, 1040)),
            (100, 100),
        )

    def test_window_clamps_inside_cursor_monitor_near_bottom_right(self):
        self.assertEqual(
            window_position_near_cursor((1900, 1000), (700, 600), (0, 0, 1920, 1040)),
            (1220, 440),
        )

    def test_window_supports_monitor_with_negative_coordinates(self):
        self.assertEqual(
            window_position_near_cursor((-100, 100), (700, 600), (-1920, 0, 0, 1040)),
            (-700, 100),
        )


if __name__ == "__main__":
    unittest.main()
