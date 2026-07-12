from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading
from typing import Callable


MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_P = 0x50
VK_F9 = 0x78
VK_C = 0x43
VK_CONTROL = 0x11
KEYEVENTF_KEYUP = 0x0002
WM_HOTKEY = 0x0312
MONITOR_DEFAULTTONEAREST = 0x00000002


class MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def cursor_location() -> tuple[int, int, int, int, int, int]:
    """Return cursor coordinates and the nearest monitor work area."""
    user32 = ctypes.windll.user32
    user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    user32.MonitorFromPoint.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    point = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        raise OSError("Windows could not read the cursor position.")
    monitor = user32.MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST)
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(MonitorInfo)
    if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        raise OSError("Windows could not read the cursor monitor.")
    return (
        int(point.x),
        int(point.y),
        int(info.rcWork.left),
        int(info.rcWork.top),
        int(info.rcWork.right),
        int(info.rcWork.bottom),
    )


def window_position_near_cursor(
    cursor: tuple[int, int],
    window_size: tuple[int, int],
    work_area: tuple[int, int, int, int],
    gap: int = 12,
) -> tuple[int, int]:
    """Place a window near the cursor while keeping it inside its monitor."""
    cursor_x, cursor_y = cursor
    width, height = window_size
    left, top, right, bottom = work_area
    x = cursor_x + gap
    y = cursor_y + gap
    if x + width > right:
        x = cursor_x - width - gap
    if y + height > bottom:
        y = cursor_y - height - gap
    return max(left, min(x, right - width)), max(top, min(y, bottom - height))


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
