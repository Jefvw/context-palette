from __future__ import annotations

import tkinter as tk


DEFAULT_WINDOW_WIDTH = 780
DEFAULT_WINDOW_HEIGHT = 600
MAXIMUM_MAIN_WINDOW_HEIGHT = 1000
MINIMUM_WINDOW_WIDTH = 700
MINIMUM_WINDOW_HEIGHT = 480
SCREEN_HORIZONTAL_MARGIN = 48
SCREEN_VERTICAL_MARGIN = 96


def standard_window_size(screen_width: int, screen_height: int) -> tuple[int, int]:
    """Return the standard size, reduced only when the current screen requires it."""
    return (
        max(320, min(DEFAULT_WINDOW_WIDTH, screen_width - SCREEN_HORIZONTAL_MARGIN)),
        max(240, min(DEFAULT_WINDOW_HEIGHT, screen_height - SCREEN_VERTICAL_MARGIN)),
    )


def configure_standard_window(window: tk.Tk | tk.Toplevel) -> None:
    """Give an application screen the shared, screen-safe window dimensions."""
    width, height = standard_window_size(
        window.winfo_screenwidth(),
        window.winfo_screenheight(),
    )
    window.geometry(f"{width}x{height}")
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
