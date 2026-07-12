from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading
from typing import Callable


MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
VK_P = 0x50
VK_C = 0x43
VK_CONTROL = 0x11
KEYEVENTF_KEYUP = 0x0002
WM_HOTKEY = 0x0312


def send_copy_shortcut() -> None:
    """Ask the foreground application to copy its current selection."""
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_C, 0, 0, 0)
    user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


class GlobalHotkey:
    def __init__(self, on_activate: Callable[[], None]) -> None:
        self.on_activate = on_activate
        self._hotkey_id = 1
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._started = threading.Event()
        self._registered = False

    def start(self) -> bool:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._started.wait(timeout=1.0)
        return self._registered

    def stop(self) -> None:
        if self._thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)

    def _run(self) -> None:
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        self._registered = bool(
            ctypes.windll.user32.RegisterHotKey(
                None,
                self._hotkey_id,
                MOD_CONTROL | MOD_ALT,
                VK_P,
            )
        )
        self._started.set()
        if not self._registered:
            return

        message = wintypes.MSG()
        try:
            while ctypes.windll.user32.GetMessageW(ctypes.byref(message), None, 0, 0) != 0:
                if message.message == WM_HOTKEY and message.wParam == self._hotkey_id:
                    self.on_activate()
        finally:
            ctypes.windll.user32.UnregisterHotKey(None, self._hotkey_id)
