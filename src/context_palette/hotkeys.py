from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading
from typing import Callable

from .window_geometry import cursor_location


MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_P = 0x50
VK_F9 = 0x78
VK_C = 0x43
VK_V = 0x56
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


def send_paste_shortcut() -> None:
    """Ask the foreground application to paste the protected clipboard item."""
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_V, 0, 0, 0)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def focus_window(handle: int) -> bool:
    user32 = ctypes.windll.user32
    return bool(handle and user32.IsWindow(handle) and user32.SetForegroundWindow(handle))


def window_title(handle: int) -> str:
    if not handle:
        return ""
    user32 = ctypes.windll.user32
    length = int(user32.GetWindowTextLengthW(handle))
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(handle, buffer, len(buffer))
    return buffer.value.strip()


def window_process_id(handle: int) -> int | None:
    """Return the owning process ID for a valid top-level window handle."""

    if not handle:
        return None
    user32 = ctypes.windll.user32
    if not user32.IsWindow(handle):
        return None
    process_id = wintypes.DWORD()
    thread_id = user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
    if not thread_id or not process_id.value:
        return None
    return int(process_id.value)


class GlobalHotkey:
    def __init__(self, on_activate: Callable[[], None]) -> None:
        self.on_activate = on_activate
        self._hotkeys = {
            1: (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_P),
            2: (MOD_NOREPEAT, VK_F9),
        }
        self._registered_ids: set[int] = set()
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._started = threading.Event()
        self._registered = False

    def start(self) -> bool:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._started.wait(timeout=1.0)
        return self._registered

    @property
    def available_shortcuts(self) -> tuple[str, ...]:
        labels = {1: "Ctrl+Alt+P", 2: "F9"}
        return tuple(labels[hotkey_id] for hotkey_id in sorted(self._registered_ids))

    def stop(self) -> None:
        if self._thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)

    def _run(self) -> None:
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        for hotkey_id, (modifiers, virtual_key) in self._hotkeys.items():
            if ctypes.windll.user32.RegisterHotKey(None, hotkey_id, modifiers, virtual_key):
                self._registered_ids.add(hotkey_id)
        self._registered = bool(self._registered_ids)
        self._started.set()
        if not self._registered:
            return

        message = wintypes.MSG()
        try:
            while ctypes.windll.user32.GetMessageW(ctypes.byref(message), None, 0, 0) != 0:
                if message.message == WM_HOTKEY and int(message.wParam) in self._registered_ids:
                    self.on_activate()
        finally:
            for hotkey_id in self._registered_ids:
                ctypes.windll.user32.UnregisterHotKey(None, hotkey_id)
