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

    def test_configuration_options_use_complete_shared_action_metadata(self) -> None:
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
                    arguments=("--profile", "accounts"),
                    working_directory=r"C:\Invoice Workspace",
                )
            ]
        )

        for query in (
            "invoice",
            "website",
            "finance",
            "monthly",
            "supplier billing",
            "example.com",
            "profile accounts",
            "invoice workspace",
        ):
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

    def test_dialog_explains_empty_restricted_scope(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            dialog = ActionPickerDialog(
                root,
                options=(),
                current_label="",
                on_select=lambda _label: None,
                scope_note="Built-in actions only.",
            )
            root.update_idletasks()

            self.assertEqual(dialog.count_var.get(), "0 actions")
            self.assertEqual(
                dialog.empty_result_var.get(),
                "No matching actions in this scope.",
            )
            self.assertEqual(str(dialog.select_button["state"]), "disabled")
        finally:
            for child in root.winfo_children():
                child.destroy()
            root.destroy()


if __name__ == "__main__":
    unittest.main()
