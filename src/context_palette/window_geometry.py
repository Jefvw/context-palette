from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
import tkinter as tk


DEFAULT_WINDOW_WIDTH = 780
DEFAULT_WINDOW_HEIGHT = 600
MAXIMUM_MAIN_WINDOW_HEIGHT = 1000
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


def main_window_monitor_work_area(owner: tk.Misc) -> WindowBounds:
    """Return the work area of the monitor containing the application root."""
    root = owner._root()
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
                wintypes.HWND(root.winfo_id()),
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
    left = int(root.winfo_vrootx())
    top = int(root.winfo_vrooty())
    return (
        left,
        top,
        left + int(root.winfo_vrootwidth()),
        top + int(root.winfo_vrootheight()),
    )


def place_child_window(
    window: tk.Toplevel,
    owner: tk.Misc,
    *,
    size: tuple[int, int] | None = None,
    below_owner: bool = False,
) -> tuple[int, int, int, int]:
    """Place a child relative to its owner on the main window's monitor."""
    window.update_idletasks()
    owner.update_idletasks()
    work_area = main_window_monitor_work_area(owner)
    if size is None:
        size = (
            max(int(window.winfo_width()), int(window.winfo_reqwidth())),
            max(int(window.winfo_height()), int(window.winfo_reqheight())),
        )
    width, height = fit_window_size(size, work_area)
    position_owner = owner if below_owner else owner.winfo_toplevel()
    owner_bounds = (
        int(position_owner.winfo_rootx()),
        int(position_owner.winfo_rooty()),
        max(1, int(position_owner.winfo_width())),
        max(1, int(position_owner.winfo_height())),
    )
    positioner = (
        window_position_below_owner
        if below_owner
        else centered_window_position
    )
    x, y = positioner(owner_bounds, (width, height), work_area)
    window.geometry(f"{width}x{height}{x:+d}{y:+d}")
    return width, height, x, y


def configure_standard_window(
    window: tk.Tk | tk.Toplevel,
    owner: tk.Misc | None = None,
) -> None:
    """Give an application screen shared, monitor-safe dimensions and placement."""
    if owner is None:
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
    else:
        left, top, right, bottom = main_window_monitor_work_area(owner)
        screen_width = right - left
        screen_height = bottom - top
    width, height = standard_window_size(screen_width, screen_height)
    if owner is None:
        window.geometry(f"{width}x{height}")
    else:
        place_child_window(window, owner, size=(width, height))
    window.minsize(
        min(MINIMUM_WINDOW_WIDTH, width),
        min(MINIMUM_WINDOW_HEIGHT, height),
    )


def configure_main_window(window: tk.Tk) -> None:
    """Use extra monitor height for the editor-focused main window only."""
    width, minimum_height = standard_window_size(
        window.winfo_screenwidth(),
        window.winfo_screenheight(),
    )
    height = max(
        minimum_height,
        min(MAXIMUM_MAIN_WINDOW_HEIGHT, window.winfo_screenheight() - SCREEN_VERTICAL_MARGIN),
    )
    window.geometry(f"{width}x{height}")
    window.minsize(
        min(MINIMUM_WINDOW_WIDTH, width),
        min(MINIMUM_WINDOW_HEIGHT, height),
    )
