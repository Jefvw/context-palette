from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys
import time
import tkinter as tk
import unittest
from ctypes import wintypes


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.launcher import LauncherApp


VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_1 = 0x31
VK_NUMPAD1 = 0x61
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1


class KeyboardInput(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class MouseInput(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class HardwareInput(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class InputUnion(ctypes.Union):
    _fields_ = (
        ("ki", KeyboardInput),
        ("mi", MouseInput),
        ("hi", HardwareInput),
    )


class Input(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = (("type", wintypes.DWORD), ("value", InputUnion))


def send_chord(modifier: int, key: int) -> None:
    events = (Input * 4)(
        Input(type=INPUT_KEYBOARD, ki=KeyboardInput(wVk=modifier)),
        Input(type=INPUT_KEYBOARD, ki=KeyboardInput(wVk=key)),
        Input(
            type=INPUT_KEYBOARD,
            ki=KeyboardInput(wVk=key, dwFlags=KEYEVENTF_KEYUP),
        ),
        Input(
            type=INPUT_KEYBOARD,
            ki=KeyboardInput(wVk=modifier, dwFlags=KEYEVENTF_KEYUP),
        ),
    )
    sent = ctypes.windll.user32.SendInput(len(events), events, ctypes.sizeof(Input))
    if sent != len(events):
        raise OSError(ctypes.get_last_error(), "Windows SendInput was incomplete")


@unittest.skipUnless(sys.platform == "win32", "Requires Windows keyboard input")
@unittest.skipUnless(
    os.environ.get("CONTEXT_PALETTE_PHYSICAL_KEY_TEST") == "1",
    "Run explicitly because this test temporarily takes keyboard focus",
)
class PhysicalKeyboardShortcutTests(unittest.TestCase):
    def test_shift_top_row_executes_slots_and_control_numpad_does_not(self) -> None:
        previous_foreground = ctypes.windll.user32.GetForegroundWindow()
        root = tk.Tk()
        root.title("Context Palette physical keyboard verification")
        entry = tk.Entry(root)
        entry.pack(padx=20, pady=20)
        executed: list[int] = []
        received: list[tuple[str, int, int, str]] = []

        app = LauncherApp.__new__(LauncherApp)
        app.root = root
        app.search_entry = entry
        app.results_view = "flat"
        app._execute_slot = lambda slot, _event: executed.append(slot) or "break"
        app._select_index = lambda _index, _event: "break"
        app._move_selection = lambda _offset, _event: "break"
        def handle_keypress(event: tk.Event) -> str | None:
            received.append(
                (
                    str(event.keysym),
                    int(event.keycode),
                    int(event.state),
                    str(event.char),
                )
            )
            return app._handle_keypress(event)

        entry.bind("<KeyPress>", handle_keypress)

        try:
            root.update()
            root.lift()
            root.focus_force()
            entry.focus_force()
            root.update()

            for offset in range(9):
                send_chord(VK_SHIFT, VK_1 + offset)
                deadline = time.monotonic() + 0.25
                while time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.005)

            self.assertEqual(
                executed,
                list(range(1, 10)),
                f"Received Windows/Tk events: {received!r}; Find text: {entry.get()!r}",
            )
            self.assertEqual(entry.get(), "")

            send_chord(VK_CONTROL, VK_NUMPAD1)
            deadline = time.monotonic() + 0.25
            while time.monotonic() < deadline:
                root.update()
                time.sleep(0.005)
            self.assertEqual(executed, list(range(1, 10)))
        finally:
            root.destroy()
            if previous_foreground:
                ctypes.windll.user32.SetForegroundWindow(previous_foreground)


if __name__ == "__main__":
    unittest.main()
