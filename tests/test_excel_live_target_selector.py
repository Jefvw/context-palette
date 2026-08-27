from __future__ import annotations

import tkinter as tk
import unittest

from context_palette.excel_automation import (
    LiveExcelApplication,
    LiveExcelInventoryResult,
    LiveExcelSheet,
    LiveExcelWorkbook,
)
from context_palette.excel_live_target_selector import (
    CapturedExcelSource,
    LiveExcelTargetSelector,
    can_return_to_captured_excel,
    inventory_process_ids,
    preferred_visible_worksheet,
    preferred_workbook,
    visible_inventory_workbooks,
    visible_worksheet_names,
    workbook_labels,
)


def workbook(
    token: str,
    *,
    name: str,
    process_id: int = 42,
    active_sheet: str | None = "Data",
    sheets: tuple[LiveExcelSheet, ...] = (
        LiveExcelSheet(1, "Data", "visible"),
        LiveExcelSheet(2, "Hidden", "hidden"),
    ),
) -> LiveExcelWorkbook:
    return LiveExcelWorkbook(
        token,
        process_id,
        name,
        rf"D:\work\{name}",
        True,
        False,
        False,
        active_sheet,
        len(sheets),
        False,
        sheets,
    )


class LiveExcelTargetPolicyTests(unittest.TestCase):
    def test_inventory_keeps_only_visible_applications_and_reports_all_processes(self) -> None:
        visible = workbook("visible", name="Visible.xlsx", process_id=42)
        hidden = workbook("hidden", name="Hidden.xlsx", process_id=99)
        inventory = LiveExcelInventoryResult(
            2,
            False,
            (
                LiveExcelApplication(42, True, True, 1, False, (visible,)),
                LiveExcelApplication(99, False, False, 1, False, (hidden,)),
            ),
            (),
        )

        self.assertEqual(inventory_process_ids(inventory), frozenset({42, 99}))
        self.assertEqual(visible_inventory_workbooks(inventory), (visible,))

    def test_duplicate_unicode_workbook_labels_are_unambiguous(self) -> None:
        first = workbook("one", name="Büdget.xlsx")
        second = workbook("two", name="Büdget.xlsx")

        labels = workbook_labels((first, second))

        self.assertEqual(tuple(labels.values()), (first, second))
        self.assertEqual(len(labels), 2)
        self.assertNotEqual(*tuple(labels))

    def test_captured_title_uses_a_boundary_and_not_a_substring(self) -> None:
        book1 = workbook("one", name="Book1.xlsx")
        book10 = workbook("ten", name="Book10.xlsx")
        source = CapturedExcelSource(7, 42, "Book10.xlsx - Excel")

        self.assertEqual(preferred_workbook((book1, book10), source), book10)

    def test_same_process_and_deterministic_fallbacks(self) -> None:
        first = workbook("first", name="First.xlsx", process_id=1)
        second = workbook("second", name="Second.xlsx", process_id=2)

        self.assertEqual(
            preferred_workbook(
                (first, second), CapturedExcelSource(None, 2, "Unrelated window")
            ),
            second,
        )
        self.assertEqual(
            preferred_workbook(
                (first, second), CapturedExcelSource(None, None, "")
            ),
            first,
        )

    def test_visible_sheet_policy_prefers_active_then_first(self) -> None:
        visible = (
            LiveExcelSheet(1, "First", "visible"),
            LiveExcelSheet(2, "Hidden", "hidden"),
            LiveExcelSheet(3, "Last", "visible"),
        )
        active = workbook("active", name="Active.xlsx", active_sheet="Last", sheets=visible)
        hidden_active = workbook(
            "fallback", name="Fallback.xlsx", active_sheet="Hidden", sheets=visible
        )
        none = workbook(
            "none",
            name="None.xlsx",
            active_sheet="Hidden",
            sheets=(LiveExcelSheet(1, "Hidden", "hidden"),),
        )

        self.assertEqual(visible_worksheet_names(active), ("First", "Last"))
        self.assertEqual(preferred_visible_worksheet(active), "Last")
        self.assertEqual(preferred_visible_worksheet(hidden_active), "First")
        self.assertIsNone(preferred_visible_worksheet(none))

    def test_return_requires_captured_handle_and_inventoried_process(self) -> None:
        self.assertTrue(
            can_return_to_captured_excel(
                CapturedExcelSource(7, 42, "Book.xlsx - Excel"), frozenset({42})
            )
        )
        self.assertFalse(
            can_return_to_captured_excel(
                CapturedExcelSource(None, 42, "Book.xlsx - Excel"), frozenset({42})
            )
        )
        self.assertFalse(
            can_return_to_captured_excel(
                CapturedExcelSource(7, 99, "Other app"), frozenset({42})
            )
        )


class LiveExcelTargetSelectorTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def test_shared_selector_changes_workbook_sheet_and_optional_scope(self) -> None:
        first = workbook("first", name="First.xlsx")
        second = workbook(
            "second",
            name="Second.xlsx",
            active_sheet="Summary",
            sheets=(
                LiveExcelSheet(1, "Data", "visible"),
                LiveExcelSheet(2, "Summary", "visible"),
            ),
        )
        changes: list[tuple[str, str | None, str]] = []
        refreshes: list[bool] = []
        selector: LiveExcelTargetSelector

        def changed() -> None:
            changes.append(
                (
                    selector.selected_workbook.token,
                    selector.selected_worksheet,
                    selector.selected_scope,
                )
            )

        selector = LiveExcelTargetSelector(
            self.root,
            workbooks=(first, second),
            source=CapturedExcelSource(None, None, ""),
            refresh_command=lambda: refreshes.append(True),
            selection_changed=changed,
            allow_all_visible_worksheets=True,
        )
        selector.pack()
        self.addCleanup(selector.destroy)
        second_label = next(
            label
            for label, item in selector.workbooks_by_label.items()
            if item == second
        )

        selector.workbook_var.set(second_label)
        selector.select_workbook_from_variable()
        selector.scope_var.set("workbook")
        selector.select_scope_from_variable()
        selector.refresh_button.invoke()

        self.assertEqual(selector.selected_workbook, second)
        self.assertEqual(selector.selected_worksheet, "Summary")
        self.assertEqual(selector.selected_scope, "workbook")
        self.assertTrue(selector.worksheet_picker.instate(["disabled"]))
        self.assertEqual(changes[-1], ("second", "Summary", "workbook"))
        self.assertEqual(refreshes, [True])


if __name__ == "__main__":
    unittest.main()
