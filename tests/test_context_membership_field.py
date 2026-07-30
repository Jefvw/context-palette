from pathlib import Path
import sys
import tkinter as tk
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.context_membership_field import (
    ContextMembershipField,
    TagSelectionField,
    reusable_tag_names,
    specific_context_names,
)


class ContextMembershipFieldTests(unittest.TestCase):
    def test_specific_names_remove_general_deduplicate_and_sort(self):
        self.assertEqual(
            specific_context_names(
                ("General", "mail", "Database", "Mail", "", "Customer support")
            ),
            ("Customer support", "Database", "mail"),
        )

    def test_picker_adds_and_removes_contexts_while_preserving_typed_values(self):
        root = tk.Tk()
        root.withdraw()
        try:
            value = tk.StringVar(value="Manually typed")
            field = ContextMembershipField(
                root,
                value,
                ("General", "Mail", "Database"),
            )

            mail_index = field.context_names.index("Mail")
            field.menu.invoke(mail_index)
            self.assertEqual(value.get(), "Manually typed, Mail")
            self.assertTrue(field.selected_vars["Mail"].get())

            field.menu.invoke(mail_index)
            self.assertEqual(value.get(), "Manually typed")

            value.set("database")
            root.update_idletasks()
            self.assertTrue(field.selected_vars["Database"].get())
        finally:
            root.destroy()

    def test_tag_names_are_normalized_and_picker_allows_new_typed_tags(self):
        self.assertEqual(
            reusable_tag_names((" SQL ", "sql", "Data   Quality", "")),
            ("data quality", "sql"),
        )
        root = tk.Tk()
        root.withdraw()
        try:
            value = tk.StringVar(value="new tag")
            field = TagSelectionField(root, value, ("sql", "data quality"))

            field.picker.invoke()
            root.update()
            sql_index = field.tag_picker.visible_values.index("sql")
            field.tag_picker.listbox.selection_set(sql_index)
            field.tag_picker._selection_changed()
            field.tag_picker.apply()

            self.assertEqual(value.get(), "new tag, sql")
            self.assertEqual(str(field.picker.winfo_class()), "TButton")
        finally:
            root.destroy()

    def test_tag_picker_is_disabled_when_no_existing_tags_are_available(self):
        root = tk.Tk()
        root.withdraw()
        try:
            field = TagSelectionField(root, tk.StringVar(value="new tag"), ())

            self.assertEqual(str(field.picker.cget("state")), tk.DISABLED)
            self.assertEqual(field._post_picker(), "break")
            self.assertFalse(hasattr(field, "tag_picker"))
        finally:
            root.destroy()

    def test_keyboard_shortcuts_focus_entry_and_open_picker(self):
        root = tk.Tk()
        root.geometry("400x200")
        try:
            value = tk.StringVar()
            field = ContextMembershipField(root, value, ("Mail", "Database"))
            root.update()

            self.assertEqual(field.label.cget("underline"), 3)
            self.assertTrue(field.entry.bind("<Alt-Down>"))
            self.assertTrue(field.entry.bind("<F4>"))

            focus_requests: list[bool] = []
            original_focus_set = field.entry.focus_set
            field.entry.focus_set = lambda: focus_requests.append(True)
            try:
                self.assertEqual(field._focus_entry(), "break")
                self.assertEqual(focus_requests, [True])

                focus_requests.clear()
                self.assertEqual(
                    field._handle_mnemonic_keypress(
                        SimpleNamespace(state=0x20000, keysym="c"),
                    ),
                    "break",
                )
                self.assertEqual(focus_requests, [True])
            finally:
                field.entry.focus_set = original_focus_set

            calls: list[tuple[object, ...]] = []
            original_tk = field.picker.tk
            original_cget = field.picker.cget

            class FakeTk:
                def call(self, *args: object) -> None:
                    calls.append(args)

            field.picker.tk = FakeTk()
            field.picker.cget = lambda _option: "normal"
            try:
                self.assertEqual(field._post_picker(), "break")
            finally:
                field.picker.tk = original_tk
                field.picker.cget = original_cget
            self.assertEqual(
                calls,
                [("ttk::menubutton::Post", field.picker)],
            )
        finally:
            root.destroy()

    def test_inline_picker_places_label_beside_the_editable_row(self):
        root = tk.Tk()
        root.withdraw()
        try:
            field = ContextMembershipField(
                root,
                tk.StringVar(),
                ("Mail",),
                label="Contexts",
                inline=True,
                label_width=14,
            )

            self.assertEqual(field.label.pack_info()["side"], "left")
            self.assertEqual(field.row.pack_info()["side"], "left")
            self.assertEqual(int(field.label.cget("width")), 14)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
