from __future__ import annotations

import unittest
from unittest.mock import patch

from context_palette.window_geometry import (
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    MAXIMUM_MAIN_WINDOW_HEIGHT,
    MINIMUM_WINDOW_HEIGHT,
    MINIMUM_WINDOW_WIDTH,
    centered_window_position,
    configure_main_window,
    configure_standard_window,
    fit_window_size,
    place_child_window,
    standard_window_size,
    window_position_below_owner,
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

    def update_idletasks(self) -> None:
        pass


class FakeOwner:
    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        toplevel: "FakeOwner | None" = None,
    ) -> None:
        self.bounds = (x, y, width, height)
        self.toplevel = toplevel or self

    def update_idletasks(self) -> None:
        pass

    def winfo_rootx(self) -> int:
        return self.bounds[0]

    def winfo_rooty(self) -> int:
        return self.bounds[1]

    def winfo_width(self) -> int:
        return self.bounds[2]

    def winfo_height(self) -> int:
        return self.bounds[3]

    def winfo_toplevel(self) -> "FakeOwner":
        return self.toplevel


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

    def test_centered_position_uses_negative_coordinate_monitor(self) -> None:
        position = centered_window_position(
            (-1700, 100, 800, 800),
            (780, 600),
            (-1920, 0, 0, 1040),
        )

        self.assertEqual(position, (-1690, 200))

    def test_centered_position_clamps_every_edge_to_work_area(self) -> None:
        position = centered_window_position(
            (-50, 900, 200, 100),
            (780, 600),
            (0, 0, 1920, 1040),
        )

        self.assertEqual(position, (0, 440))

    def test_popup_moves_above_owner_when_bottom_space_is_tight(self) -> None:
        position = window_position_below_owner(
            (1800, 900, 100, 30),
            (360, 240),
            (0, 0, 1920, 1040),
        )

        self.assertEqual(position, (1560, 660))

    def test_requested_size_is_reduced_to_monitor_work_area(self) -> None:
        self.assertEqual(
            fit_window_size((2000, 1200), (1920, 0, 3520, 900)),
            (1600, 900),
        )

    def test_standard_child_uses_main_monitor_and_owner_center(self) -> None:
        window = FakeWindow(1920, 1080)
        owner = FakeOwner(2100, 100, 800, 700)

        with patch(
            "context_palette.window_geometry.main_window_monitor_work_area",
            return_value=(1920, 0, 3520, 900),
        ):
            configure_standard_window(  # type: ignore[arg-type]
                window,
                owner,  # type: ignore[arg-type]
            )

        self.assertEqual(window.geometry_value, "780x600+2110+150")
        self.assertEqual(
            window.minimum_size,
            (MINIMUM_WINDOW_WIDTH, MINIMUM_WINDOW_HEIGHT),
        )

    def test_auto_sized_child_is_centered_and_clamped(self) -> None:
        window = FakeWindow(1920, 1080)
        owner = FakeOwner(-1700, 200, 800, 700)

        with patch(
            "context_palette.window_geometry.main_window_monitor_work_area",
            return_value=(-1920, 0, 0, 1040),
        ):
            result = place_child_window(  # type: ignore[arg-type]
                window,
                owner,  # type: ignore[arg-type]
                size=(500, 300),
            )

        self.assertEqual(result, (500, 300, -1550, 400))
        self.assertEqual(window.geometry_value, "500x300-1550+400")

    def test_dialog_uses_owner_toplevel_but_popup_uses_control(self) -> None:
        window = FakeWindow(1920, 1080)
        toplevel = FakeOwner(2000, 100, 800, 700)
        control = FakeOwner(2500, 700, 120, 30, toplevel=toplevel)

        with patch(
            "context_palette.window_geometry.main_window_monitor_work_area",
            return_value=(1920, 0, 3520, 900),
        ):
            dialog = place_child_window(  # type: ignore[arg-type]
                window,
                control,  # type: ignore[arg-type]
                size=(500, 300),
            )
            popup = place_child_window(  # type: ignore[arg-type]
                window,
                control,  # type: ignore[arg-type]
                size=(300, 160),
                below_owner=True,
            )

        self.assertEqual(dialog, (500, 300, 2150, 300))
        self.assertEqual(popup, (300, 160, 2500, 730))


if __name__ == "__main__":
    unittest.main()
