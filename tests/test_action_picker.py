from __future__ import annotations

from pathlib import Path
import sys
import tkinter as tk
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.action_picker import (
    ActionPickerDialog,
    ActionPickerOption,
    filter_action_picker_options,
)
from context_palette.actions import Action
from context_palette.configuration_window import _action_picker_options


class ActionPickerFilterTests(unittest.TestCase):
    def test_filter_requires_every_term_across_label_and_metadata(self) -> None:
        options = (
            ActionPickerOption(
                "invoice",
                "Open invoice portal · Finance",
                "Open website billing active",
            ),
            ActionPickerOption(
                "docs",
                "Open Python docs · Development",
                "Open website reference active",
            ),
        )

        self.assertEqual(
            [
                option.action_id
                for option in filter_action_picker_options(
                    options,
                    "invoice website",
                )
            ],
            ["invoice"],
        )
        self.assertEqual(filter_action_picker_options(options, "missing"), ())

    def test_configuration_options_search_action_type_context_and_tag(self) -> None:
        options = _action_picker_options(
            [
                Action(
                    "invoice",
                    "Open invoice portal",
                    "General",
                    "open_url",
                    "https://example.com",
                    contexts=("Finance",),
                    tags=("monthly",),
                    description="Review supplier billing",
                )
            ]
        )

        for query in ("website", "finance", "monthly", "supplier billing"):
            with self.subTest(query=query):
                self.assertEqual(
                    [
                        option.action_id
                        for option in filter_action_picker_options(options, query)
                    ],
                    ["invoice"],
                )


class ActionPickerDialogTests(unittest.TestCase):
    def test_dialog_filters_selects_and_reports_result_count(self) -> None:
        root = tk.Tk()
        root.withdraw()
        selected: list[str] = []
        try:
            dialog = ActionPickerDialog(
                root,
                options=(
                    ActionPickerOption(
                        "invoice",
                        "Open invoice portal · Finance",
                        "website monthly",
                    ),
                    ActionPickerOption(
                        "docs",
                        "Open Python docs · Development",
                        "website reference",
                    ),
                ),
                current_label="",
                on_select=selected.append,
                empty_label="Not assigned",
            )
            root.update()

            self.assertEqual(dialog.count_var.get(), "2 actions")
            self.assertEqual(dialog.results.size(), 3)

            dialog.search_var.set("monthly")
            root.update_idletasks()

            self.assertEqual(dialog.count_var.get(), "1 action")
            self.assertEqual(dialog.results.get(0), "Open invoice portal · Finance")
            dialog._select()
            self.assertEqual(selected, ["Open invoice portal · Finance"])
        finally:
            for child in root.winfo_children():
                child.destroy()
            root.destroy()


if __name__ == "__main__":
    unittest.main()
