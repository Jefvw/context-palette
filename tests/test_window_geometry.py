from __future__ import annotations

import unittest

from context_palette.window_geometry import (
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    MAXIMUM_MAIN_WINDOW_HEIGHT,
    MINIMUM_WINDOW_HEIGHT,
    MINIMUM_WINDOW_WIDTH,
    configure_main_window,
    configure_standard_window,
    standard_window_size,
)


class FakeWindow:
    def __init__(self, screen_width: int, screen_height: int) -> None:
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.geometry_value = ""
        self.minimum_size = (0, 0)

    def winfo_screenwidth(self) -> int:
        return self.screen_width

    def winfo_screenheight(self) -> int:
        return self.screen_height

    def geometry(self, value: str) -> None:
        self.geometry_value = value

    def minsize(self, width: int, height: int) -> None:
        self.minimum_size = (width, height)


class WindowGeometryTests(unittest.TestCase):
    def test_standard_screen_uses_main_window_size(self) -> None:
        self.assertEqual(
            standard_window_size(1920, 1080),
            (DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT),
        )

    def test_small_screen_keeps_window_inside_safe_margins(self) -> None:
        self.assertEqual(standard_window_size(720, 540), (672, 444))

    def test_configuration_sets_matching_geometry_and_safe_minimum(self) -> None:
        window = FakeWindow(1920, 1080)

        configure_standard_window(window)  # type: ignore[arg-type]

        self.assertEqual(window.geometry_value, "780x600")
        self.assertEqual(
            window.minimum_size,
            (MINIMUM_WINDOW_WIDTH, MINIMUM_WINDOW_HEIGHT),
        )

    def test_minimum_never_exceeds_small_screen_geometry(self) -> None:
        window = FakeWindow(640, 400)

        configure_standard_window(window)  # type: ignore[arg-type]

        self.assertEqual(window.geometry_value, "592x304")
        self.assertEqual(window.minimum_size, (592, 304))

    def test_main_window_uses_extra_vertical_space_without_growing_wider(self) -> None:
        window = FakeWindow(1920, 1080)

        configure_main_window(window)  # type: ignore[arg-type]

        self.assertEqual(window.geometry_value, "780x984")
        self.assertEqual(window.minimum_size, (700, 480))

    def test_main_window_height_is_capped_near_twice_the_original(self) -> None:
        window = FakeWindow(2560, 1440)

        configure_main_window(window)  # type: ignore[arg-type]

        self.assertEqual(
            window.geometry_value,
            f"780x{MAXIMUM_MAIN_WINDOW_HEIGHT}",
        )


if __name__ == "__main__":
    unittest.main()
