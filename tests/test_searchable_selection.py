from pathlib import Path
import sys
import tkinter as tk
from tkinter import font as tkfont, ttk
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.searchable_selection import SearchableSelectionPopup
from context_palette.style import configure_theme


class SearchableSelectionPopupTests(unittest.TestCase):
    def test_default_picker_has_no_details_row_or_browsing_effect(self):
        root = tk.Tk()
        root.withdraw()
        on_select = Mock()
        try:
            popup = SearchableSelectionPopup(
                root, ("first", "second"), multiple=False,
                on_select=on_select, title="Choose item",
            )
            outer = popup.window.winfo_children()[0]
            self.assertIsNone(popup.selection_detail_label)
            self.assertEqual(len(outer.winfo_children()), 3)
            self.assertTrue(all(isinstance(child, ttk.Frame) for child in outer.winfo_children()))
            popup.search_var.set("second")
            self.assertEqual(popup.visible_values, ("second",))
            on_select.assert_not_called()
        finally:
            root.update_idletasks()
            root.destroy()

    def test_details_show_first_or_preselected_choice_without_choosing(self):
        for preselected, expected in (((), "first"), (("second",), "second")):
            with self.subTest(preselected=preselected):
                root = tk.Tk()
                root.withdraw()
                on_select = Mock()
                details = Mock(side_effect=lambda value: f"Destination for {value}")
                try:
                    popup = SearchableSelectionPopup(
                        root, ("first", "second"), selected=preselected,
                        multiple=False, on_select=on_select, title="Choose item",
                        selection_detail=details,
                    )
                    self.assertEqual(popup.selection_detail_var.get(), f"Destination for {expected}")
                    details.assert_called_once_with(expected)
                    self.assertEqual(str(popup.selection_detail_label.cget("justify")), tk.LEFT)
                    self.assertEqual(float(popup.selection_detail_label.cget("wraplength")), 350)
                    on_select.assert_not_called()
                    root.update_idletasks()
                    popup.close()
                    on_select.assert_not_called()
                finally:
                    root.destroy()

    def test_details_follow_native_keyboard_mouse_and_filter_without_choosing(self):
        root = tk.Tk()
        root.attributes("-alpha", 0.0)
        root.geometry("300x150+-32000+-32000")
        on_select = Mock()
        details = Mock(side_effect=lambda value: f"Inbox: {value}.xlsx")
        try:
            popup = SearchableSelectionPopup(
                root, ("first", "second", "third"), multiple=False,
                on_select=on_select, title="Choose item", selection_detail=details,
                empty_label="No destination",
            )
            popup.window.attributes("-alpha", 0.0)
            root.update()
            self.assertEqual(popup.selection_detail_var.get(), "")
            details.assert_not_called()
            popup.listbox.focus_force()
            popup.listbox.event_generate("<KeyPress-Down>")
            root.update()
            self.assertEqual(popup.listbox.curselection(), (1,))
            self.assertEqual(popup.selection_detail_var.get(), "Inbox: first.xlsx")
            bounds = popup.listbox.bbox(2)
            self.assertIsNotNone(bounds)
            popup.listbox.event_generate("<Button-1>", x=5, y=bounds[1] + bounds[3] // 2)
            popup.listbox.event_generate("<ButtonRelease-1>", x=5, y=bounds[1] + bounds[3] // 2)
            root.update()
            self.assertEqual(popup.listbox.curselection(), (2,))
            self.assertEqual(popup.selection_detail_var.get(), "Inbox: second.xlsx")
            popup.search_var.set("third")
            root.update()
            self.assertEqual(popup.selection_detail_var.get(), "Inbox: third.xlsx")
            popup.search_var.set("no match")
            root.update()
            self.assertEqual(popup.selection_detail_var.get(), "")
            self.assertEqual(str(popup.apply_button.cget("state")), tk.DISABLED)
            popup.search_var.set("first")
            root.update()
            self.assertEqual(popup.selection_detail_var.get(), "Inbox: first.xlsx")
            self.assertEqual(
                {call.args[0] for call in details.call_args_list},
                {"first", "second", "third"},
            )
            popup.listbox.selection_clear(0, tk.END)
            popup.listbox.event_generate("<<ListboxSelect>>")
            root.update()
            self.assertEqual(popup.selection_detail_var.get(), "")
            on_select.assert_not_called()
            popup.close()
            on_select.assert_not_called()
        finally:
            root.destroy()

    def test_long_destination_details_wrap_inside_popup_at_supported_scaling(self):
        path = "D:\\" + "VeryLongUnbrokenDestinationDirectory" * 4 + "\\Report.xlsx"
        detail = f"Source: Example source (source-id)\nExcel Inbox: {path}"
        for percentage, scaling in ((100, 4 / 3), (125, 5 / 3), (150, 2.0)):
            with self.subTest(percentage=percentage):
                root = tk.Tk()
                root.attributes("-alpha", 0.0)
                root.geometry("300x150+-32000+-32000")
                original_scaling = float(root.tk.call("tk", "scaling"))
                root.tk.call("tk", "scaling", scaling)
                configure_theme(root)
                try:
                    popup = SearchableSelectionPopup(
                        root, ("Short destination", "Report — Example source"), multiple=False,
                        on_select=lambda _selected: self.fail("Browsing must not choose"),
                        title="Choose Work Item",
                        selection_detail=lambda value: detail if value.startswith("Report") else "Inbox: D:\\Short.xlsx",
                    )
                    popup.window.attributes("-alpha", 0.0)
                    root.update()
                    popup.listbox.selection_clear(0, tk.END)
                    popup.listbox.selection_set(1)
                    popup.listbox.event_generate("<<ListboxSelect>>")
                    root.update()
                    label = popup.selection_detail_label
                    self.assertEqual(popup.selection_detail_var.get(), detail)
                    font = tkfont.Font(root=root, font=ttk.Style(root).lookup("TLabel", "font"))
                    self.assertGreater(font.measure(path), popup.listbox.winfo_width())
                    # The complete unbroken path occupies additional lines;
                    # it is not a clipped single-line copy of the list row.
                    self.assertGreater(label.winfo_reqheight(), 2 * font.metrics("linespace"))
                    self.assertEqual(label.winfo_height(), label.winfo_reqheight())
                    self.assertLessEqual(
                        label.winfo_rootx() + label.winfo_width(),
                        popup.window.winfo_rootx() + popup.window.winfo_width(),
                    )
                    self.assertLessEqual(
                        label.winfo_rooty() + label.winfo_height(),
                        popup.window.winfo_rooty() + popup.window.winfo_height(),
                    )
                finally:
                    root.tk.call("tk", "scaling", original_scaling)
                    root.destroy()

    def test_details_reject_multiple_choice_before_creating_popup(self):
        root = tk.Tk()
        root.withdraw()
        try:
            with self.assertRaisesRegex(ValueError, "single-value chooser"):
                SearchableSelectionPopup(
                    root, ("first",), multiple=True,
                    on_select=lambda _selected: None, title="Choose tags",
                    selection_detail=lambda _value: "detail",
                )
            self.assertEqual(root.winfo_children(), [])
        finally:
            root.destroy()

    def test_details_layout_tolerates_popup_destruction_during_idle(self):
        for outcome in ("close", "destroy", "tcl_error"):
            with self.subTest(outcome=outcome):
                root = tk.Tk()
                root.withdraw()
                on_select = Mock()
                try:
                    popup = SearchableSelectionPopup(
                        root, ("first", "second"), multiple=False,
                        on_select=on_select, title="Choose item",
                        selection_detail=lambda value: f"Inbox: {value}.xlsx",
                    )
                    root.update_idletasks()
                    popup.listbox.selection_clear(0, tk.END)
                    popup.listbox.selection_set(1)
                    idle_effect = (
                        popup.close if outcome == "close"
                        else popup.window.destroy if outcome == "destroy"
                        else tk.TclError("application has been destroyed")
                    )
                    with (
                        patch.object(popup.window, "update_idletasks", side_effect=idle_effect),
                        patch.object(popup.window, "winfo_reqheight") as measure,
                        patch.object(popup.window, "winfo_height") as height,
                        patch.object(popup, "_place_near_owner") as place,
                    ):
                        popup._selection_changed()
                    measure.assert_not_called()
                    height.assert_not_called()
                    place.assert_not_called()
                    on_select.assert_not_called()
                    if outcome != "tcl_error":
                        self.assertFalse(popup.window.winfo_exists())
                finally:
                    root.destroy()

    def test_multiple_selection_search_preserves_matches_outside_search(self):
        root = tk.Tk()
        root.withdraw()
        selected: list[tuple[str, ...]] = []
        try:
            popup = SearchableSelectionPopup(
                root,
                ("database", "customer support", "urgent"),
                selected=("database",),
                multiple=True,
                on_select=selected.append,
                title="Choose tags",
            )
            popup.search_var.set("urgent")
            root.update()
            popup.listbox.selection_set(0)
            popup._selection_changed()
            popup.apply()

            self.assertEqual(selected, [("database", "urgent")])
        finally:
            root.destroy()

    def test_single_search_selects_first_match_and_down_focuses_results(self):
        root = tk.Tk()
        root.withdraw()
        selected: list[tuple[str, ...]] = []
        try:
            popup = SearchableSelectionPopup(
                root,
                ("database", "urgent"),
                selected=("database",),
                multiple=False,
                on_select=selected.append,
                title="Filter tags",
                empty_label="All tags",
            )
            popup.search_var.set("urgent")
            root.update_idletasks()

            self.assertEqual(popup.visible_values, ("urgent",))
            self.assertEqual(popup.listbox.curselection(), (0,))
            self.assertEqual(popup.count_var.get(), "1 tag")

            focus_requests: list[bool] = []
            original_focus_set = popup.listbox.focus_set
            popup.listbox.focus_set = lambda: focus_requests.append(True)
            try:
                self.assertEqual(popup._focus_results(), "break")
            finally:
                popup.listbox.focus_set = original_focus_set
            self.assertEqual(focus_requests, [True])

            self.assertEqual(popup._apply_event(), "break")

            self.assertEqual(selected, [("urgent",)])
        finally:
            root.destroy()

    def test_escape_closes_and_search_entry_receives_initial_focus(self):
        root = tk.Tk()
        root.geometry("300x150")
        try:
            popup = SearchableSelectionPopup(
                root,
                ("database",),
                multiple=False,
                on_select=lambda _selected: None,
                title="Filter tags",
            )
            root.update()
            self.assertTrue(popup.search_entry.winfo_exists())
            self.assertTrue(popup.search_entry.bind("<Down>"))
            self.assertIs(popup.window.grab_current(), popup.window)
            self.assertEqual(popup._close_event(), "break")
            self.assertFalse(popup.window.winfo_exists())
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
