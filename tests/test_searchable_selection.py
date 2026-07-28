from pathlib import Path
import sys
import tkinter as tk
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.searchable_selection import SearchableSelectionPopup


class SearchableSelectionPopupTests(unittest.TestCase):
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
