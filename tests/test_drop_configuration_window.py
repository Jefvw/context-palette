from dataclasses import replace
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from context_palette.actions import Action
from context_palette.drop_action import DropActionSettings, approve_drop_action
from context_palette.drop_configuration_window import DropConfigurationWindow


class DropConfigurationWindowTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.action = Action("upper", "Uppercase", "General", "transform_text", "uppercase")
        self.unsafe = Action("credential", "Password", "General", "paste_credential", "secret-target")

    def dialog(self, settings=DropActionSettings(), on_save=None):
        dialog = DropConfigurationWindow(self.root, actions=[self.action, self.unsafe], settings=settings, on_save=on_save or Mock())
        self.root.update_idletasks()
        return dialog

    def test_no_save_or_execution_before_explicit_opt_in_and_save(self):
        saved = Mock()
        dialog = self.dialog(on_save=saved)
        self.assertEqual(dialog.mode_var.get(), "show")
        self.assertEqual(len(dialog.action_picker.options), 1)
        self.assertEqual(len(dialog.unavailable.get_children()), 1)
        self.assertIn("unchanged", dialog.effect_var.get())
        saved.assert_not_called()
        dialog.action_radio.invoke()
        self.assertEqual(str(dialog.save_button.cget("state")), "disabled")
        dialog.action_var.set("Uppercase [upper]")
        self.assertIn("clipboard", dialog.effect_var.get())
        saved.assert_not_called()
        dialog.save_button.invoke()
        saved.assert_called_once_with(approve_drop_action(self.action))

    def test_changed_action_requires_reselection_and_explicit_approval(self):
        settings = approve_drop_action(replace(self.action, value="lowercase"))
        dialog = self.dialog(settings)
        self.assertEqual(dialog.action_var.get(), "")
        self.assertEqual(str(dialog.save_button.cget("state")), "disabled")
        self.assertIn("changed", dialog.feedback_var.get())
        dialog.show_radio.invoke()
        self.assertEqual(str(dialog.save_button.cget("state")), "normal")

    def test_save_failure_keeps_dialog_open_and_cancel_does_not_save(self):
        saved = Mock(return_value=False)
        dialog = self.dialog(on_save=saved)
        dialog.save_button.invoke()
        self.assertTrue(dialog.window.winfo_exists())
        self.assertIn("not saved", dialog.feedback_var.get())
        dialog._close()
        saved.assert_called_once_with(DropActionSettings())

    def test_unavailable_reason_is_readable_outside_narrow_table(self):
        dialog = self.dialog()
        key = dialog.unavailable.get_children()[0]
        dialog.unavailable.selection_set(key)
        dialog._show_unavailable_reason()
        self.assertIn("fresh captured destination", dialog.reason_var.get())

    def test_configured_target_parameters_are_readonly_and_never_expanded(self):
        self.action = replace(
            self.action, type="workspace_template", value="Explain %CLIPBOARD%\nexact template",
            arguments=("first", "two\nlines"), working_directory="C:/configured",
        )
        with patch.object(self.root, "clipboard_get", side_effect=AssertionError("No clipboard read")):
            dialog = self.dialog()
            dialog.action_radio.invoke()
            dialog.action_var.set("Uppercase [upper]")
            details = dialog.configured_details.get("1.0", "end-1c")
        self.assertIn("Explain %CLIPBOARD%\nexact template", details)
        self.assertIn('["first", "two\\nlines"]', details)
        self.assertIn("C:/configured", details)
        self.assertIn("workspace_template", details)
        self.assertEqual(str(dialog.configured_details.cget("state")), "disabled")

    def test_minimum_size_at_150_percent_keeps_details_and_footer_visible(self):
        original_scaling = float(self.root.tk.call("tk", "scaling"))
        self.addCleanup(self.root.tk.call, "tk", "scaling", original_scaling)
        self.root.tk.call("tk", "scaling", 2.0)
        self.root.geometry("700x480+-32000+-32000")
        self.root.deiconify()
        dialog = self.dialog()
        dialog.window.geometry("700x480+-32000+-32000")
        dialog.action_radio.invoke()
        dialog.action_var.set("Uppercase [upper]")
        self.root.update()
        top = dialog.window.winfo_rooty()
        bottom = top + dialog.window.winfo_height()
        for widget in (dialog.configured_details, dialog.save_button, dialog.cancel_button):
            with self.subTest(widget=widget):
                self.assertGreater(widget.winfo_height(), 15)
                self.assertGreaterEqual(widget.winfo_rooty(), top)
                self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), bottom)


if __name__ == "__main__":
    unittest.main()
