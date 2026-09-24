from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
import tkinter as tk


DEFAULT_WINDOW_WIDTH = 780
DEFAULT_WINDOW_HEIGHT = 600
MINIMUM_WINDOW_WIDTH = 700
MINIMUM_WINDOW_HEIGHT = 480
SCREEN_HORIZONTAL_MARGIN = 48
SCREEN_VERTICAL_MARGIN = 96
MONITOR_DEFAULTTONEAREST = 0x00000002

WindowBounds = tuple[int, int, int, int]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def cursor_location() -> tuple[int, int, int, int, int, int]:
    """Read the cursor and its monitor using the same native types as Tk placement.

    This also runs on the hotkey thread; it must not call Tk. Sharing the
    MONITORINFO type avoids competing ctypes signatures on GetMonitorInfoW.
    """
    user32 = ctypes.windll.user32
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    user32.MonitorFromPoint.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MonitorInfo)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    point = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        raise OSError("Windows could not read the cursor position.")
    monitor = user32.MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST)
    info = _MonitorInfo()
    info.cbSize = ctypes.sizeof(_MonitorInfo)
    if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        raise OSError("Windows could not read the cursor monitor.")
    return (
        int(point.x), int(point.y), int(info.rcWork.left), int(info.rcWork.top),
        int(info.rcWork.right), int(info.rcWork.bottom),
    )


def absolute_window_position(x: int, y: int) -> str:
    """Encode desktop coordinates, including screens left of/above the primary.

    Tk's leading '-' anchors to the right/bottom edge. A literal '+' followed
    by a signed number keeps the left/top anchor (for example '+-1350+240').
    """
    return f"+{x}+{y}"


def standard_window_size(screen_width: int, screen_height: int) -> tuple[int, int]:
    """Return the standard size, reduced only when the current screen requires it."""
    return (
        max(320, min(DEFAULT_WINDOW_WIDTH, screen_width - SCREEN_HORIZONTAL_MARGIN)),
        max(240, min(DEFAULT_WINDOW_HEIGHT, screen_height - SCREEN_VERTICAL_MARGIN)),
    )


def centered_window_position(
    owner_bounds: WindowBounds,
    window_size: tuple[int, int],
    work_area: WindowBounds,
) -> tuple[int, int]:
    """Center on the owner, clamped fully inside one monitor work area."""
    owner_x, owner_y, owner_width, owner_height = owner_bounds
    width, height = window_size
    left, top, right, bottom = work_area
    x = owner_x + (owner_width - width) // 2
    y = owner_y + (owner_height - height) // 2
    return (
        max(left, min(x, right - width)),
        max(top, min(y, bottom - height)),
    )


def centered_work_area_position(
    window_size: tuple[int, int],
    work_area: WindowBounds,
) -> tuple[int, int]:
    """Center a fitted window in one monitor's usable work area."""
    width, height = fit_window_size(window_size, work_area)
    left, top, right, bottom = work_area
    return (
        left + (right - left - width) // 2,
        top + (bottom - top - height) // 2,
    )


def window_position_below_owner(
    owner_bounds: WindowBounds,
    window_size: tuple[int, int],
    work_area: WindowBounds,
) -> tuple[int, int]:
    """Place a popup below its control, or above it when bottom space is tight."""
    owner_x, owner_y, _owner_width, owner_height = owner_bounds
    width, height = window_size
    left, top, right, bottom = work_area
    x = owner_x
    y = owner_y + owner_height
    if y + height > bottom:
        y = owner_y - height
    return (
        max(left, min(x, right - width)),
        max(top, min(y, bottom - height)),
    )


def fit_window_size(
    window_size: tuple[int, int],
    work_area: WindowBounds,
) -> tuple[int, int]:
    """Reduce a requested size only when needed to fit the monitor."""
    width, height = window_size
    left, top, right, bottom = work_area
    return (
        max(1, min(width, right - left)),
        max(1, min(height, bottom - top)),
    )


def window_monitor_work_area(window: tk.Misc) -> WindowBounds:
    """Return the work area of the monitor containing this specific Tk window."""
    if sys.platform == "win32":
        try:
            user32 = ctypes.windll.user32
            user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
            user32.MonitorFromWindow.restype = wintypes.HANDLE
            user32.GetMonitorInfoW.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(_MonitorInfo),
            ]
            user32.GetMonitorInfoW.restype = wintypes.BOOL
            monitor = user32.MonitorFromWindow(
                wintypes.HWND(window.winfo_id()),
                MONITOR_DEFAULTTONEAREST,
            )
            info = _MonitorInfo()
            info.cbSize = ctypes.sizeof(_MonitorInfo)
            if monitor and user32.GetMonitorInfoW(
                monitor,
                ctypes.byref(info),
            ):
                return (
                    int(info.rcWork.left),
                    int(info.rcWork.top),
                    int(info.rcWork.right),
                    int(info.rcWork.bottom),
                )
        except (AttributeError, OSError, tk.TclError):
            pass
    left = int(window.winfo_vrootx())
    top = int(window.winfo_vrooty())
    return (
        left,
        top,
        left + int(window.winfo_vrootwidth()),
        top + int(window.winfo_vrootheight()),
    )


def main_window_monitor_work_area(owner: tk.Misc) -> WindowBounds:
    """Return the work area of the monitor containing the application root."""
    return window_monitor_work_area(owner._root())


def place_child_window(
    window: tk.Toplevel,
    owner: tk.Misc,
    *,
    size: tuple[int, int] | None = None,
    below_owner: bool = False,
) -> tuple[int, int, int, int]:
    """Center a child on its owner's monitor, or anchor a compact popup."""
    window.update_idletasks()
    owner.update_idletasks()
    position_owner = owner if below_owner else owner.winfo_toplevel()
    work_area = window_monitor_work_area(position_owner)
    if size is None:
        size = (
            max(int(window.winfo_width()), int(window.winfo_reqwidth())),
            max(int(window.winfo_height()), int(window.winfo_reqheight())),
        )
    width, height = fit_window_size(size, work_area)
    if below_owner:
        owner_bounds = (
            int(position_owner.winfo_rootx()),
            int(position_owner.winfo_rooty()),
            max(1, int(position_owner.winfo_width())),
            max(1, int(position_owner.winfo_height())),
        )
        x, y = window_position_below_owner(
            owner_bounds,
            (width, height),
            work_area,
        )
    else:
        x, y = centered_work_area_position((width, height), work_area)
    window.geometry(f"{width}x{height}{absolute_window_position(x, y)}")
    return width, height, x, y


def configure_standard_window(
    window: tk.Tk | tk.Toplevel,
    owner: tk.Misc | None = None,
    *,
    work_area: WindowBounds | None = None,
) -> None:
    """Give an application screen shared, monitor-safe dimensions and placement."""
    if work_area is None:
        if owner is None:
            window.update_idletasks()
            work_area = window_monitor_work_area(window)
        else:
            work_area = window_monitor_work_area(owner.winfo_toplevel())
    left, top, right, bottom = work_area
    screen_width = right - left
    screen_height = bottom - top
    width, height = standard_window_size(screen_width, screen_height)
    if owner is None:
        x, y = centered_work_area_position((width, height), work_area)
        window.geometry(f"{width}x{height}{absolute_window_position(x, y)}")
    else:
        place_child_window(window, owner, size=(width, height))
    window.minsize(
        min(MINIMUM_WINDOW_WIDTH, width),
        min(MINIMUM_WINDOW_HEIGHT, height),
    )


def configure_main_window(window: tk.Tk) -> None:
    """Start the compact launcher on the cursor's monitor, when available."""
    try:
        work_area = cursor_location()[2:]
    except (AttributeError, OSError):
        work_area = None
    configure_standard_window(window, work_area=work_area)
