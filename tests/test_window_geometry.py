from __future__ import annotations

import unittest
import sys
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import Mock, patch

from context_palette.window_geometry import (
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    MINIMUM_WINDOW_HEIGHT,
    MINIMUM_WINDOW_WIDTH,
    absolute_window_position,
    centered_window_position,
    centered_work_area_position,
    configure_main_window,
    configure_standard_window,
    cursor_location,
    fit_window_size,
    main_window_monitor_work_area,
    place_child_window,
    standard_window_size,
    window_monitor_work_area,
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


class FakeMonitorWindow:
    def __init__(
        self,
        window_id: int,
        *,
        virtual_root: tuple[int, int, int, int] = (0, 0, 1920, 1080),
        root: "FakeMonitorWindow | None" = None,
    ) -> None:
        self.window_id = window_id
        self.virtual_root = virtual_root
        self.root = root or self

    def winfo_id(self) -> int:
        return self.window_id

    def winfo_vrootx(self) -> int:
        return self.virtual_root[0]

    def winfo_vrooty(self) -> int:
        return self.virtual_root[1]

    def winfo_vrootwidth(self) -> int:
        return self.virtual_root[2]

    def winfo_vrootheight(self) -> int:
        return self.virtual_root[3]

    def _root(self) -> "FakeMonitorWindow":
        return self.root


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

        with patch(
            "context_palette.window_geometry.window_monitor_work_area",
            return_value=(0, 0, 1920, 1040),
        ):
            configure_standard_window(window)  # type: ignore[arg-type]

        self.assertEqual(window.geometry_value, "780x600+570+220")
        self.assertEqual(
            window.minimum_size,
            (MINIMUM_WINDOW_WIDTH, MINIMUM_WINDOW_HEIGHT),
        )

    def test_minimum_never_exceeds_small_screen_geometry(self) -> None:
        window = FakeWindow(640, 400)

        with patch(
            "context_palette.window_geometry.window_monitor_work_area",
            return_value=(0, 0, 640, 400),
        ):
            configure_standard_window(window)  # type: ignore[arg-type]

        self.assertEqual(window.geometry_value, "592x304+24+48")
        self.assertEqual(window.minimum_size, (592, 304))

    def test_main_window_uses_compact_standard_size(self) -> None:
        window = FakeWindow(1920, 1080)

        with patch(
            "context_palette.window_geometry.cursor_location",
            return_value=(900, 500, 0, 0, 1920, 1040),
        ):
            configure_main_window(window)  # type: ignore[arg-type]

        self.assertEqual(window.geometry_value, "780x600+570+220")
        self.assertEqual(window.minimum_size, (700, 480))

    def test_large_monitor_does_not_inflate_main_window(self) -> None:
        window = FakeWindow(2560, 1440)

        with patch(
            "context_palette.window_geometry.cursor_location",
            return_value=(900, 500, 0, 0, 2560, 1400),
        ):
            configure_main_window(window)  # type: ignore[arg-type]

        self.assertEqual(window.geometry_value, "780x600+890+400")

    def test_startup_uses_cursor_screen_instead_of_initial_window_screen(self):
        window = FakeWindow(1920, 1080)
        with (
            patch("context_palette.window_geometry.cursor_location",
                  return_value=(-1500, -500, -1920, -1080, 0, -40)),
            patch("context_palette.window_geometry.window_monitor_work_area") as by_window,
        ):
            configure_main_window(window)
        self.assertEqual(window.geometry_value, "780x600+-1350+-860")
        by_window.assert_not_called()

    def test_startup_falls_back_to_window_monitor_if_cursor_read_fails(self):
        window = FakeWindow(1920, 1080)
        with (
            patch("context_palette.window_geometry.cursor_location", side_effect=OSError),
            patch("context_palette.window_geometry.window_monitor_work_area",
                  return_value=(0, 0, 1920, 1040)),
        ):
            configure_main_window(window)
        self.assertEqual(window.geometry_value, "780x600+570+220")

    @unittest.skipUnless(sys.platform == "win32", "Windows Tk placement regression")
    def test_real_tk_preserves_absolute_negative_coordinates(self):
        # Invisible disposable Tk window, not the running Palette or a claim
        # of physical multi-monitor/DPI verification. An undecorated window
        # lets us compare exact coordinates without title-bar offsets.
        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-alpha", 0)
        root.geometry("100x80+0+0")
        root.deiconify()
        for x, y in ((-1350, 240), (240, -860), (-1350, -860), (2330, 150)):
            with self.subTest(x=x, y=y):
                root.geometry("100x80" + absolute_window_position(x, y))
                root.update_idletasks()
                self.assertEqual((root.winfo_x(), root.winfo_y()), (x, y))

    def test_cursor_and_window_monitor_queries_can_interleave(self):
        # ctypes caches native function objects. Re-enter the window provider
        # during the cursor query to detect incompatible POINTER types.
        user32 = SimpleNamespace(
            GetCursorPos=Mock(), MonitorFromPoint=Mock(),
            MonitorFromWindow=Mock(return_value=99), GetMonitorInfoW=Mock(),
        )
        def get_cursor(pointer):
            pointer._obj.x, pointer._obj.y = -1800, -700
            return True
        def get_info(_monitor, pointer):
            self.assertIs(user32.GetMonitorInfoW.argtypes[1]._type_, type(pointer._obj))
            info = pointer._obj
            info.rcWork.left, info.rcWork.top = -1920, -1080
            info.rcWork.right, info.rcWork.bottom = 0, -40
            return True
        def from_point(point, flags):
            self.assertEqual((point.x, point.y, flags), (-1800, -700, 2))
            window_monitor_work_area(FakeMonitorWindow(456))
            return 99
        user32.GetCursorPos.side_effect = get_cursor
        user32.MonitorFromPoint.side_effect = from_point
        user32.GetMonitorInfoW.side_effect = get_info
        with (
            patch("context_palette.window_geometry.sys.platform", "win32"),
            patch("context_palette.window_geometry.ctypes.windll",
                  SimpleNamespace(user32=user32), create=True),
        ):
            self.assertEqual(cursor_location(), (-1800, -700, -1920, -1080, 0, -40))

    def test_cursor_monitor_failure_does_not_use_combined_desktop_bounds(self):
        user32 = SimpleNamespace(
            GetCursorPos=Mock(return_value=True), MonitorFromPoint=Mock(return_value=0),
            GetMonitorInfoW=Mock(),
        )
        with patch("context_palette.window_geometry.ctypes.windll",
                   SimpleNamespace(user32=user32), create=True):
            with self.assertRaises(OSError):
                cursor_location()

    def test_work_area_center_respects_taskbar_and_negative_coordinates(self) -> None:
        self.assertEqual(
            centered_work_area_position(
                (780, 600),
                (-1920, 40, 0, 1040),
            ),
            (-1350, 240),
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

    def test_monitor_work_area_uses_the_specific_window_handle(self) -> None:
        window = FakeMonitorWindow(456)
        user32 = SimpleNamespace(
            MonitorFromWindow=Mock(return_value=123),
            GetMonitorInfoW=Mock(),
        )

        def populate_work_area(_monitor: object, pointer: object) -> bool:
            info = pointer._obj  # type: ignore[attr-defined]
            info.rcWork.left = 1920
            info.rcWork.top = 40
            info.rcWork.right = 3520
            info.rcWork.bottom = 900
            return True

        user32.GetMonitorInfoW.side_effect = populate_work_area
        with (
            patch("context_palette.window_geometry.sys.platform", "win32"),
            patch(
                "context_palette.window_geometry.ctypes.windll",
                SimpleNamespace(user32=user32),
                create=True,
            ),
        ):
            result = window_monitor_work_area(window)  # type: ignore[arg-type]

        handle, flags = user32.MonitorFromWindow.call_args.args
        self.assertEqual(handle.value, 456)
        self.assertEqual(flags, 2)
        self.assertEqual(result, (1920, 40, 3520, 900))

    def test_monitor_work_area_uses_window_virtual_root_as_fallback(self) -> None:
        window = FakeMonitorWindow(456, virtual_root=(-1920, 0, 3840, 1040))

        with patch("context_palette.window_geometry.sys.platform", "linux"):
            result = window_monitor_work_area(window)  # type: ignore[arg-type]

        self.assertEqual(result, (-1920, 0, 1920, 1040))

    def test_main_monitor_work_area_still_resolves_application_root(self) -> None:
        root = FakeMonitorWindow(100)
        owner = FakeMonitorWindow(456, root=root)

        with patch(
            "context_palette.window_geometry.window_monitor_work_area",
            return_value=(0, 0, 1920, 1040),
        ) as monitor_work_area:
            result = main_window_monitor_work_area(owner)  # type: ignore[arg-type]

        monitor_work_area.assert_called_once_with(root)
        self.assertEqual(result, (0, 0, 1920, 1040))

    def test_standard_child_uses_owner_monitor_and_work_area_center(self) -> None:
        window = FakeWindow(1920, 1080)
        owner = FakeOwner(2100, 100, 800, 700)

        with patch(
            "context_palette.window_geometry.window_monitor_work_area",
            return_value=(1920, 0, 3520, 900),
        ) as monitor_work_area:
            configure_standard_window(  # type: ignore[arg-type]
                window,
                owner,  # type: ignore[arg-type]
            )

        monitor_work_area.assert_called_with(owner)
        self.assertEqual(window.geometry_value, "780x600+2330+150")
        self.assertEqual(
            window.minimum_size,
            (MINIMUM_WINDOW_WIDTH, MINIMUM_WINDOW_HEIGHT),
        )

    def test_auto_sized_child_is_centered_and_clamped(self) -> None:
        window = FakeWindow(1920, 1080)
        owner = FakeOwner(-1700, 200, 800, 700)

        with patch(
            "context_palette.window_geometry.window_monitor_work_area",
            return_value=(-1920, 0, 0, 1040),
        ):
            result = place_child_window(  # type: ignore[arg-type]
                window,
                owner,  # type: ignore[arg-type]
                size=(500, 300),
            )

        self.assertEqual(result, (500, 300, -1210, 370))
        self.assertEqual(window.geometry_value, "500x300+-1210+370")

    def test_dialog_uses_owner_toplevel_but_popup_uses_control(self) -> None:
        window = FakeWindow(1920, 1080)
        toplevel = FakeOwner(2000, 100, 800, 700)
        control = FakeOwner(2500, 700, 120, 30, toplevel=toplevel)

        with patch(
            "context_palette.window_geometry.window_monitor_work_area",
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

        self.assertEqual(dialog, (500, 300, 2470, 300))
        self.assertEqual(popup, (300, 160, 2500, 730))


if __name__ == "__main__":
    unittest.main()
