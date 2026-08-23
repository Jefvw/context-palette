from __future__ import annotations

import tkinter as tk
import sys
import unittest
from unittest.mock import Mock, patch

from context_palette.drop_adapter import (
    DropItem,
    DropProblem,
    DropResolutionCoordinator,
    DropResult,
    DropWarning,
)
from context_palette.drop_target_window import (
    DROP_COPY_ACTION,
    DROP_DETAILS_CHARACTER_LIMIT,
    DROP_DETAILS_ITEM_LIMIT,
    DROP_HISTORY_LIMIT,
    DROP_REFUSE_ACTION,
    DropTargetWindow,
    drop_result_details,
    drop_result_summary,
)


class _Dnd:
    calls: list[object] = []

    @classmethod
    def require(cls, root: object) -> None:
        cls.calls.append(root)


class _Event:
    def __init__(self, root: tk.Tk, *, data: str = "{Note with braces}", event_type: str = "CF_UNICODETEXT") -> None:
        self.data = data
        self.widget = root
        self.type = event_type


class DropTargetWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.addCleanup(self.root.destroy)
        self.root.withdraw()
        _Dnd.calls.clear()

    def test_one_existing_root_owns_non_transient_topmost_target_and_hide_show(self) -> None:
        received: list[DropResult] = []
        with patch("context_palette.drop_target_window._load_tk_dnd", return_value=_Dnd), \
             patch.object(tk.Toplevel, "drop_target_register", create=True), \
             patch.object(tk.Toplevel, "dnd_bind", create=True) as dnd_bind:
            target = DropTargetWindow(self.root, received.append)
            self.assertTrue(target.start())
            self.assertIsNotNone(target.window)
            window = target.window
            self.assertEqual(_Dnd.calls, [self.root])
            self.assertEqual(window.transient(), "")
            self.assertTrue(bool(window.attributes("-topmost")))
            self.assertFalse(bool(self.root.attributes("-topmost")))
            target.close()
            self.assertEqual(window.state(), "withdrawn")
            self.assertTrue(target.show())
            self.assertNotEqual(window.state(), "withdrawn")
            self.root.withdraw()
            self.root.update()
            self.assertNotEqual(window.state(), "withdrawn")
            bound_sequences = [call.args[0] for call in dnd_bind.call_args_list]
            self.assertEqual(bound_sequences, ["<<Drop:DND_Files>>", "<<Drop:DND_Text>>"])

    def test_completed_callback_keeps_window_visible(self) -> None:
        received: list[DropResult] = []
        coordinator = DropResolutionCoordinator(lambda _values: DropResult(items=(DropItem("text", "{Note with braces}"),)))
        with patch("context_palette.drop_target_window._load_tk_dnd", return_value=_Dnd), \
             patch.object(tk.Toplevel, "drop_target_register", create=True), \
             patch.object(tk.Toplevel, "dnd_bind", create=True):
            target = DropTargetWindow(self.root, received.append, coordinator=coordinator)
            target.show()
            self.assertEqual(
                target._handle_text_drop(_Event(self.root)),
                DROP_COPY_ACTION,
            )
            for _ in range(30):
                self.root.update()
                if received:
                    break
                self.root.after(10)
            self.assertEqual(received, [DropResult(items=(DropItem("text", "{Note with braces}"),))])
            self.assertNotEqual(target.window.state(), "withdrawn")
            self.assertEqual(
                target._history_var.get(),
                "Drop 1 of 1 - Text: 18 characters",
            )
            self.assertEqual(str(target.send_again_button.cget("state")), "normal")

    def test_summary_identifies_safe_item_metadata_and_warning_counts(self) -> None:
        self.assertEqual(
            drop_result_summary(
                DropResult(items=(DropItem("path", r"C:\Dropped\report.xlsx"),))
            ),
            "Path: report.xlsx",
        )
        self.assertEqual(
            drop_result_summary(
                DropResult(items=(DropItem("url", "https://example.com/private?q=1"),))
            ),
            "Web link: example.com",
        )
        self.assertEqual(
            drop_result_summary(DropResult(items=(DropItem("text", "secret text"),))),
            "Text: 11 characters",
        )
        self.assertEqual(
            drop_result_summary(
                DropResult(
                    items=(
                        DropItem("path", r"C:\one.txt"),
                        DropItem("path", r"C:\two.txt"),
                        DropItem("text", "note"),
                    ),
                    warnings=(DropWarning("shortcut", "Shortcut path was kept."),),
                )
            ),
            "3 items: 2 paths, 1 text - 1 warning",
        )

    def test_details_show_exact_normalized_values_and_warning_messages(self) -> None:
        result = DropResult(
            items=(
                DropItem("path", r"C:\Dropped\report.xlsx"),
                DropItem("url", "https://example.com/report"),
                DropItem("text", "first line\nsecond line"),
            ),
            warnings=(DropWarning("shortcut", "Shortcut path was kept."),),
        )

        self.assertEqual(
            drop_result_details(result),
            "What will be sent to Input / Output (3 items)\n\n"
            "1. Path\n"
            "C:\\Dropped\\report.xlsx\n\n"
            "2. Web link\n"
            "https://example.com/report\n\n"
            "3. Text - 22 characters, 2 lines\n"
            "first line\nsecond line\n\n"
            "Warnings\n"
            "- Shortcut path was kept.",
        )

    def test_details_preview_is_bounded_without_changing_the_result(self) -> None:
        items = tuple(
            DropItem("text", f"item {index}")
            for index in range(DROP_DETAILS_ITEM_LIMIT + 1)
        )
        result = DropResult(items=items)

        details = drop_result_details(result)

        self.assertIn("... 1 more items are retained and will be sent.", details)
        self.assertEqual(result.items, items)

        long_result = DropResult(
            items=(DropItem("text", "x" * (DROP_DETAILS_CHARACTER_LIMIT + 100)),)
        )
        long_details = drop_result_details(long_result)
        self.assertIn("... Preview truncated.", long_details)
        self.assertEqual(long_result.items[0].value, "x" * (DROP_DETAILS_CHARACTER_LIMIT + 100))

    def test_typed_files_binding_uses_tcl_splitlist_despite_native_event_type(self) -> None:
        received: list[DropResult] = []
        coordinator = DropResolutionCoordinator(
            lambda values: DropResult(items=tuple(DropItem("text", value) for value in values))
        )
        event = _Event(
            self.root,
            data=r"{C:\Program Files\note.txt} {C:\Temp\second.txt}",
            event_type="CF_HDROP",
        )
        with patch("context_palette.drop_target_window._load_tk_dnd", return_value=_Dnd), \
             patch.object(tk.Toplevel, "drop_target_register", create=True), \
             patch.object(tk.Toplevel, "dnd_bind", create=True):
            target = DropTargetWindow(self.root, received.append, coordinator=coordinator)
            target.show()
            self.assertEqual(target._handle_files_drop(event), DROP_COPY_ACTION)
            for _ in range(30):
                self.root.update()
                if received:
                    break
                self.root.after(10)
            self.assertEqual(
                received,
                [
                    DropResult(
                        items=(
                            DropItem("text", r"C:\Program Files\note.txt"),
                            DropItem("text", r"C:\Temp\second.txt"),
                        )
                    )
                ],
            )

    def test_unknown_drop_type_is_refused_without_starting_resolution(self) -> None:
        received: list[DropResult] = []
        coordinator = DropResolutionCoordinator()
        event = _Event(self.root)
        with patch("context_palette.drop_target_window._load_tk_dnd", return_value=_Dnd), \
             patch.object(tk.Toplevel, "drop_target_register", create=True), \
             patch.object(tk.Toplevel, "dnd_bind", create=True):
            target = DropTargetWindow(
                self.root,
                received.append,
                coordinator=coordinator,
            )
            target.show()
            self.assertEqual(target._handle_drop(event, "DND_HTML"), DROP_REFUSE_ACTION)
            self.assertFalse(coordinator.running)
            self.assertEqual(received[0].error.code, "unsupported_type")

    def test_history_keeps_last_ten_successful_events_and_duplicate_events(self) -> None:
        received: list[DropResult] = []
        with patch("context_palette.drop_target_window._load_tk_dnd", return_value=_Dnd), \
             patch.object(tk.Toplevel, "drop_target_register", create=True), \
             patch.object(tk.Toplevel, "dnd_bind", create=True):
            target = DropTargetWindow(self.root, received.append)
            target.show()
            distinct = tuple(
                DropResult(items=(DropItem("text", f"drop {index}"),))
                for index in range(DROP_HISTORY_LIMIT + 1)
            )
            duplicate = distinct[-1]

            for result in (*distinct, duplicate):
                target._complete(result)

            expected = [*distinct[2:], duplicate]
            self.assertEqual(target._drop_history, expected)
            self.assertIs(target._drop_history[-1], duplicate)
            self.assertEqual(len(received), DROP_HISTORY_LIMIT + 2)
            self.assertEqual(
                target._history_var.get(),
                f"Drop {DROP_HISTORY_LIMIT} of {DROP_HISTORY_LIMIT} - Text: 7 characters",
            )

            target.hide()
            self.assertTrue(target.show())
            self.assertEqual(target._drop_history, expected)
            self.assertEqual(
                target._history_var.get(),
                f"Drop {DROP_HISTORY_LIMIT} of {DROP_HISTORY_LIMIT} - Text: 7 characters",
            )

    def test_errors_and_empty_results_are_not_retained(self) -> None:
        received: list[DropResult] = []
        with patch("context_palette.drop_target_window._load_tk_dnd", return_value=_Dnd), \
             patch.object(tk.Toplevel, "drop_target_register", create=True), \
             patch.object(tk.Toplevel, "dnd_bind", create=True):
            target = DropTargetWindow(self.root, received.append)
            target.show()
            useful = DropResult(
                items=(DropItem("path", r"C:\Dropped\report.xlsx"),),
                warnings=(DropWarning("shortcut", "Shortcut path was kept."),),
            )
            empty = DropResult()
            failed = DropResult(error=DropProblem("payload", "Drop failed."))

            target._complete(useful)
            target._complete(empty)
            target._complete(failed)

            self.assertEqual(target._drop_history, [useful])
            self.assertIs(target._drop_history[0], useful)
            self.assertEqual(received, [useful, empty, failed])
            self.assertEqual(
                target._history_var.get(),
                "Drop 1 of 1 - Path: report.xlsx - 1 warning",
            )

    def test_navigation_and_send_again_use_the_selected_exact_result(self) -> None:
        received: list[DropResult] = []
        coordinator = Mock(spec=DropResolutionCoordinator)
        with patch("context_palette.drop_target_window._load_tk_dnd", return_value=_Dnd), \
             patch.object(tk.Toplevel, "drop_target_register", create=True), \
             patch.object(tk.Toplevel, "dnd_bind", create=True):
            target = DropTargetWindow(
                self.root,
                received.append,
                coordinator=coordinator,
            )
            target.show()
            results = (
                DropResult(items=(DropItem("text", "first"),)),
                DropResult(
                    items=(
                        DropItem("text", "second a"),
                        DropItem("text", "second b"),
                    )
                ),
                DropResult(items=(DropItem("text", "third"),)),
            )
            for result in results:
                target._complete(result)
            received.clear()

            target.previous_button.invoke()
            self.assertEqual(
                target._history_var.get(),
                "Drop 2 of 3 - 2 items: 2 text items",
            )
            self.assertEqual(str(target.next_button.cget("state")), "normal")
            target.previous_button.invoke()
            self.assertEqual(
                target._history_var.get(),
                "Drop 1 of 3 - Text: 5 characters",
            )
            self.assertEqual(str(target.previous_button.cget("state")), "disabled")

            target.send_again_button.invoke()

            self.assertEqual(received, [results[0]])
            self.assertIs(received[0], results[0])
            self.assertEqual(target._drop_history, list(results))
            coordinator.start.assert_not_called()

            newest = DropResult(items=(DropItem("text", "fourth"),))
            target._complete(newest)
            self.assertEqual(target._drop_history, [*results, newest])
            self.assertEqual(
                target._history_var.get(),
                "Drop 4 of 4 - Text: 6 characters",
            )
            self.assertEqual(str(target.next_button.cget("state")), "disabled")

    def test_details_expand_in_place_and_follow_history_selection(self) -> None:
        received: list[DropResult] = []
        with patch("context_palette.drop_target_window._load_tk_dnd", return_value=_Dnd), \
             patch.object(tk.Toplevel, "drop_target_register", create=True), \
             patch.object(tk.Toplevel, "dnd_bind", create=True):
            target = DropTargetWindow(self.root, received.append)
            target.show()
            first = DropResult(
                items=(DropItem("path", r"C:\Dropped\report.xlsx"),),
                warnings=(DropWarning("shortcut", "Shortcut path was kept."),),
            )
            second = DropResult(items=(DropItem("text", "later text"),))
            target._complete(first)
            target._complete(second)

            self.assertEqual(str(target.details_button.cget("state")), "normal")
            self.assertEqual(target._details_frame.winfo_manager(), "")
            target.window.geometry("+240+260")
            self.root.update_idletasks()
            compact_anchor = (
                target.window.winfo_x() + target.window.winfo_width(),
                target.window.winfo_y() + target.window.winfo_height(),
            )
            target.details_button.invoke()
            self.root.update_idletasks()

            self.assertEqual(target._details_frame.winfo_manager(), "grid")
            self.assertEqual(target.details_button.cget("text"), "Hide details")
            expanded_anchor = (
                target.window.winfo_x() + target.window.winfo_width(),
                target.window.winfo_y() + target.window.winfo_height(),
            )
            self.assertEqual(expanded_anchor, compact_anchor)
            self.assertEqual(
                target._details_text.get("1.0", "end-1c"),
                "What will be sent to Input / Output (1 item)\n\n"
                "1. Text - 10 characters, 1 line\n"
                "later text",
            )
            self.assertEqual(str(target._details_text.cget("state")), "disabled")

            target.previous_button.invoke()
            self.assertEqual(
                target._details_text.get("1.0", "end-1c"),
                "What will be sent to Input / Output (1 item)\n\n"
                "1. Path\n"
                "C:\\Dropped\\report.xlsx\n\n"
                "Warnings\n"
                "- Shortcut path was kept.",
            )

            target.hide()
            self.assertTrue(target.show())
            self.assertFalse(target._details_visible)
            self.assertEqual(target._details_frame.winfo_manager(), "")
            self.assertEqual(target.details_button.cget("text"), "Show details")

            target.details_button.invoke()
            target.details_button.invoke()
            self.assertEqual(target._details_frame.winfo_manager(), "")
            self.assertEqual(target.details_button.cget("text"), "Show details")

    def test_dynamic_content_keeps_every_control_inside_monitor_work_area(self) -> None:
        received: list[DropResult] = []
        work_area = (0, 0, 1000, 700)
        original_scaling = float(self.root.tk.call("tk", "scaling"))
        self.root.tk.call("tk", "scaling", 2.0)
        self.addCleanup(self.root.tk.call, "tk", "scaling", original_scaling)
        with patch("context_palette.drop_target_window._load_tk_dnd", return_value=_Dnd), \
             patch("context_palette.drop_target_window.main_window_monitor_work_area", return_value=work_area), \
             patch("context_palette.drop_target_window.window_monitor_work_area", return_value=work_area), \
             patch.object(tk.Toplevel, "drop_target_register", create=True), \
            patch.object(tk.Toplevel, "dnd_bind", create=True):
            target = DropTargetWindow(self.root, received.append)
            target.show()
            target.window.geometry("+100+100")
            self.root.update_idletasks()

            target._complete(
                DropResult(
                    items=(
                        DropItem(
                            "path",
                            r"C:\A very long folder name\another long folder\test1.xlsx",
                        ),
                    ),
                )
            )
            self.root.update_idletasks()
            self.assertEqual((target.window.winfo_x(), target.window.winfo_y()), (100, 100))

            target.window.geometry("+980+650")
            self.root.update_idletasks()
            target._sync_history_controls()
            self.root.update_idletasks()

            self._assert_drop_window_controls_fit(target, work_area)
            self.assertGreaterEqual(
                target.history_label.winfo_height(),
                target.history_label.winfo_reqheight(),
            )

            target.details_button.invoke()
            self.root.update_idletasks()
            self._assert_drop_window_controls_fit(target, work_area)

    def _assert_drop_window_controls_fit(
        self,
        target: DropTargetWindow,
        work_area: tuple[int, int, int, int],
    ) -> None:
        left, top, right, bottom = work_area
        window_left = target.window.winfo_rootx()
        window_top = target.window.winfo_rooty()
        window_right = window_left + target.window.winfo_width()
        window_bottom = window_top + target.window.winfo_height()
        side_frame, top_frame = target._window_frame_offsets()
        outer_right = target.window.winfo_x() + target.window.winfo_width() + (2 * side_frame)
        outer_bottom = (
            target.window.winfo_y()
            + target.window.winfo_height()
            + top_frame
            + side_frame
        )
        self.assertGreaterEqual(window_left, left)
        self.assertGreaterEqual(window_top, top)
        self.assertLessEqual(window_right, right)
        self.assertLessEqual(window_bottom, bottom)
        self.assertLessEqual(outer_right, right)
        self.assertLessEqual(outer_bottom, bottom)
        for widget in (
            target.previous_button,
            target.history_label,
            target.next_button,
            target.send_again_button,
            target.details_button,
            target.hide_button,
        ):
            with self.subTest(widget=widget):
                widget_left = widget.winfo_rootx()
                widget_right = widget_left + widget.winfo_width()
                self.assertGreaterEqual(widget_left, window_left)
                self.assertLessEqual(widget_right, window_right)

    def test_history_controls_are_disabled_while_a_drop_is_preparing(self) -> None:
        received: list[DropResult] = []
        coordinator = Mock(spec=DropResolutionCoordinator)
        coordinator.start.return_value = True
        with patch("context_palette.drop_target_window._load_tk_dnd", return_value=_Dnd), \
             patch.object(tk.Toplevel, "drop_target_register", create=True), \
             patch.object(tk.Toplevel, "dnd_bind", create=True):
            target = DropTargetWindow(
                self.root,
                received.append,
                coordinator=coordinator,
            )
            target.show()
            target._complete(DropResult(items=(DropItem("text", "first"),)))
            target._complete(DropResult(items=(DropItem("text", "second"),)))
            received.clear()
            self.assertEqual(str(target.previous_button.cget("state")), "normal")
            self.assertEqual(str(target.send_again_button.cget("state")), "normal")
            target.details_button.invoke()
            self.assertTrue(target._details_visible)

            with patch.object(self.root, "after") as schedule:
                self.assertEqual(
                    target._handle_text_drop(_Event(self.root)),
                    DROP_COPY_ACTION,
                )
            schedule.assert_called_once_with(40, target._poll)

            coordinator.start.assert_called_once_with(("{Note with braces}",))
            self.assertTrue(target._polling)
            self.assertFalse(target._details_visible)
            self.assertEqual(target._details_frame.winfo_manager(), "")
            self.assertEqual(str(target.previous_button.cget("state")), "disabled")
            self.assertEqual(str(target.next_button.cget("state")), "disabled")
            self.assertEqual(str(target.send_again_button.cget("state")), "disabled")
            self.assertEqual(str(target.details_button.cget("state")), "disabled")
            target.previous_button.invoke()
            target.send_again_button.invoke()
            target.details_button.invoke()
            self.assertEqual(
                target._history_var.get(),
                "Drop 2 of 2 - Text: 6 characters",
            )
            self.assertFalse(target._details_visible)
            self.assertEqual(received, [])

    def test_unavailable_optional_library_does_not_create_a_window(self) -> None:
        with patch("context_palette.drop_target_window._load_tk_dnd", side_effect=ImportError("missing")):
            target = DropTargetWindow(self.root, lambda _result: None)
            self.assertFalse(target.start())
            self.assertIsNone(target.window)

    @unittest.skipUnless(sys.platform == "win32", "Native TkDND check requires Windows.")
    def test_native_library_registers_toplevel_on_an_ordinary_tk_root(self) -> None:
        received: list[DropResult] = []
        target = DropTargetWindow(self.root, received.append)

        self.assertEqual(type(self.root), tk.Tk)
        self.assertTrue(target.start())
        self.assertIsNotNone(target.window)
        self.assertTrue(target.window.dnd_bind("<<Drop:DND_Files>>"))
        self.assertTrue(target.window.dnd_bind("<<Drop:DND_Text>>"))
        self.assertEqual(target.window.transient(), "")
        self.assertTrue(bool(target.window.attributes("-topmost")))
        self.assertFalse(bool(self.root.attributes("-topmost")))


if __name__ == "__main__":
    unittest.main()
