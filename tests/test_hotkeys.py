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
    window_process_id,
)


class HotkeyTests(unittest.TestCase):
    def test_ctrl_alt_p_constants(self):
        self.assertEqual(MOD_CONTROL, 0x0002)
        self.assertEqual(MOD_ALT, 0x0001)
        self.assertEqual(VK_P, 0x50)
        self.assertEqual(VK_F9, 0x78)
        self.assertEqual(MOD_NOREPEAT, 0x4000)
        self.assertEqual(WM_HOTKEY, 0x0312)

    def test_zero_window_handle_has_no_process(self):
        self.assertIsNone(window_process_id(0))

if __name__ == "__main__":
    unittest.main()
