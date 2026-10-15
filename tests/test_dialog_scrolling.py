"""Preserved Configure scrolling policies and owned Tk callback cleanup."""
from contextlib import ExitStack
from http.client import HTTPConnection
from types import SimpleNamespace
import subprocess
import sys
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, call, patch

from context_palette.dialog_scrolling import ScrollableDialogBody


@unittest.skipUnless(sys.platform == "win32", "Requires Windows Tk.")
class DialogScrollingTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.window = tk.Toplevel(self.root)
        self.window.withdraw()
        self.callback_errors = []
        self.root.report_callback_exception = lambda *error: self.callback_errors.append(error)

    def tearDown(self):
        for after_id in self.after_ids():
            self.root.after_cancel(after_id)
        self.root.destroy()
        self.assertEqual(self.callback_errors, [])

    def body(self, *, action_editor=False):
        parent = ttk.Frame(self.window)
        parent.pack(fill=tk.BOTH, expand=True)
        return ScrollableDialogBody(self.window, parent, action_editor=action_editor)

    def field(self, body):
        frame = ttk.Frame(body.content)
        frame.pack()
        entry = ttk.Entry(frame)
        entry.pack()
        return entry

    def after_ids(self):
        return set(self.root.tk.splitlist(self.root.tk.call("after", "info")))

    def geometry(self, body, field, *, top, height=20, viewport=100, offset=200):
        """Use controlled layout coordinates while retaining real Tk ancestry."""
        stack = ExitStack()
        stack.enter_context(patch.object(body.canvas, "winfo_height", return_value=viewport))
        stack.enter_context(patch.object(body.canvas, "canvasy", return_value=offset))
        stack.enter_context(patch.object(body.canvas, "bbox", return_value=(0, 0, 300, 1000)))
        stack.enter_context(patch.object(body.content, "winfo_reqheight", return_value=2000))
        stack.enter_context(patch.object(body.content, "winfo_rooty", return_value=100))
        stack.enter_context(patch.object(field, "winfo_rooty", return_value=100 + top))
        stack.enter_context(patch.object(field, "winfo_height", return_value=height))
        return stack

    def test_construction_has_no_process_network_or_clipboard_effect(self):
        with patch.object(subprocess, "Popen") as process, \
                patch.object(HTTPConnection, "request") as request, \
                patch.object(self.window, "clipboard_get") as get, \
                patch.object(self.window, "clipboard_clear") as clear, \
                patch.object(self.window, "clipboard_append") as append:
            for action_editor in (False, True):
                body = self.body(action_editor=action_editor)
                self.assertEqual(body.host.winfo_manager(), "pack")
                self.assertEqual(body.scrollbar.winfo_manager(), "pack")
                self.assertEqual(str(body.canvas.cget("takefocus")), "0")
                body.host.destroy()
            for effect in (process, request, get, clear, append):
                effect.assert_not_called()

    def test_action_wheel_keeps_fractional_steps_bounds_and_zero_delta_behavior(self):
        body = self.body(action_editor=True)
        with patch.object(body.canvas, "yview") as view, \
                patch.object(body.canvas, "yview_moveto") as move, \
                patch.object(body, "_pointer_is_over_canvas") as pointer:
            for fraction, delta, expected in (
                ((0.25, 0.50), -120, 0.33),
                ((0.25, 0.50), 120, 0.17),
                ((0.25, 0.50), 0, 0.33),
                ((0.01, 0.26), 120, 0.0),
                ((0.73, 0.98), -120, 0.75),
            ):
                with self.subTest(fraction=fraction, delta=delta):
                    view.return_value = fraction
                    move.reset_mock()
                    result = body._on_mousewheel(SimpleNamespace(widget=body.canvas, delta=delta))
                    self.assertEqual(result, "break")
                    self.assertEqual(move.call_count, 1)
                    self.assertAlmostEqual(move.call_args.args[0], expected)
            view.return_value = (0.0, 1.0)
            move.reset_mock()
            self.assertIsNone(body._on_mousewheel(SimpleNamespace(widget=body.canvas, delta=-120)))
            move.assert_not_called()
            pointer.assert_not_called()

    def test_default_wheel_requires_pointer_and_keeps_unit_steps(self):
        body = self.body()
        with patch.object(body, "_pointer_is_over_canvas", return_value=False) as pointer, \
                patch.object(body.canvas, "yview_scroll") as scroll:
            self.assertIsNone(body._on_mousewheel(SimpleNamespace(widget=body.canvas, delta=-120)))
            scroll.assert_not_called()
            pointer.return_value = True
            for delta, expected in ((-120, 1), (120, -1)):
                scroll.reset_mock()
                self.assertEqual(body._on_mousewheel(SimpleNamespace(widget=body.canvas, delta=delta)), "break")
                scroll.assert_called_once_with(expected, "units")
            for event in (SimpleNamespace(widget=body.canvas, delta=0), SimpleNamespace(widget=body.canvas)):
                scroll.reset_mock()
                self.assertIsNone(body._on_mousewheel(event))
                scroll.assert_not_called()

    def test_default_pointer_edges_are_left_top_inclusive_right_bottom_exclusive(self):
        body = self.body()
        with patch.object(body.canvas, "winfo_rootx", return_value=100), \
                patch.object(body.canvas, "winfo_rooty", return_value=200), \
                patch.object(body.canvas, "winfo_width", return_value=300), \
                patch.object(body.canvas, "winfo_height", return_value=150), \
                patch.object(self.window, "winfo_pointerxy") as pointer:
            for position, expected in (((100, 200), True), ((399, 349), True),
                                       ((99, 200), False), ((100, 199), False),
                                       ((400, 200), False), ((100, 350), False)):
                with self.subTest(position=position):
                    pointer.return_value = position
                    self.assertEqual(body._pointer_is_over_canvas(), expected)

    def test_native_text_list_and_combobox_wheels_are_not_consumed(self):
        for action_editor in (False, True):
            body = self.body(action_editor=action_editor)
            with patch.object(body.canvas, "yview") as view, \
                    patch.object(body.canvas, "yview_scroll") as scroll, \
                    patch.object(body.canvas, "yview_moveto") as move, \
                    patch.object(body, "_pointer_is_over_canvas") as pointer:
                for control_type in (tk.Text, tk.Listbox, ttk.Combobox):
                    control = control_type(body.content)
                    with self.subTest(action_editor=action_editor, control=control_type):
                        self.assertIsNone(body._on_mousewheel(SimpleNamespace(widget=control, delta=-120)))
                for operation in (view, scroll, move, pointer):
                    operation.assert_not_called()
            body.host.destroy()

    def test_action_focus_is_deferred_and_default_focus_is_immediate(self):
        for action_editor in (False, True):
            body = self.body(action_editor=action_editor)
            field = self.field(body)
            with patch.object(body, "ensure_visible") as reveal:
                body._on_focus_in(SimpleNamespace(widget=field))
                if action_editor:
                    reveal.assert_not_called()
                    self.root.update_idletasks()
                reveal.assert_called_once_with(field)
            body.host.destroy()

    def test_footer_focus_never_scrolls_or_schedules_a_reveal(self):
        footer = ttk.Button(self.window, text="Save")
        for action_editor in (False, True):
            body = self.body(action_editor=action_editor)
            before = self.after_ids()
            with patch.object(body, "ensure_visible") as reveal:
                body._on_focus_in(SimpleNamespace(widget=footer))
                self.assertEqual(self.after_ids(), before)
                reveal.assert_not_called()
            body.host.destroy()

    def test_focus_keeps_each_forms_padding_trigger_and_content_height(self):
        for action_editor in (False, True):
            body = self.body(action_editor=action_editor)
            field = self.field(body)
            for top, expected in ((205, .197 if action_editor else None),
                                  (190, .182 if action_editor else .092),
                                  (285, .213 if action_editor else .1055)):
                with self.subTest(action_editor=action_editor, top=top), \
                        self.geometry(body, field, top=top), \
                        patch.object(body.canvas, "yview_moveto") as move:
                    body.ensure_visible(field)
                    if expected is None:
                        move.assert_not_called()
                    else:
                        self.assertEqual(move.call_count, 1)
                        self.assertAlmostEqual(move.call_args.args[0], expected)
            body.host.destroy()

    def test_action_focus_clamps_both_scroll_boundaries(self):
        body = self.body(action_editor=True)
        field = self.field(body)
        for top, offset, expected in ((0, 0, 0.0), (990, 850, .9)):
            with self.subTest(top=top), self.geometry(body, field, top=top, offset=offset), \
                    patch.object(body.canvas, "yview_moveto") as move:
                body.ensure_visible(field)
                move.assert_called_once_with(expected)

    def test_action_focus_ignores_unlaid_out_or_missing_content_bounds(self):
        body = self.body(action_editor=True)
        field = self.field(body)
        with patch.object(body.canvas, "yview_moveto") as move:
            for viewport, bounds in ((1, (0, 0, 300, 1000)), (100, None)):
                with self.subTest(viewport=viewport, bounds=bounds), \
                        patch.object(body.canvas, "winfo_height", return_value=viewport), \
                        patch.object(body.canvas, "bbox", return_value=bounds):
                    body.ensure_visible(field)
            move.assert_not_called()

    def test_destroying_host_cancels_only_owned_work_and_bindings(self):
        foreign_wheel = self.window.bind("<MouseWheel>", Mock(), add="+")
        foreign_focus = self.window.bind("<FocusIn>", Mock(), add="+")
        original_bindings = {sequence: self.window.bind(sequence) for sequence in ("<MouseWheel>", "<FocusIn>")}
        body = self.body(action_editor=True)
        field = self.field(body)
        foreign_results = []
        foreign_after = self.window.after_idle(lambda: foreign_results.append("foreign"))
        before = self.after_ids()
        with patch.object(body, "ensure_visible") as reveal:
            body._on_focus_in(SimpleNamespace(widget=field))
            owned_after = self.after_ids() - before
            self.assertEqual(len(owned_after), 1)
            body.host.destroy()
            self.assertTrue(owned_after.isdisjoint(self.after_ids()))
            self.assertIn(foreign_after, self.after_ids())
            for sequence, original in original_bindings.items():
                self.assertEqual(self.window.bind(sequence).strip(), original.strip())
            self.assertIn(foreign_wheel, self.window.bind("<MouseWheel>"))
            self.assertIn(foreign_focus, self.window.bind("<FocusIn>"))
            self.root.update_idletasks()
            reveal.assert_not_called()
        self.assertEqual(foreign_results, ["foreign"])

    def test_child_destroy_leaves_owner_and_other_focus_work_alive(self):
        body = self.body(action_editor=True)
        first = self.field(body)
        second = self.field(body)
        with patch.object(body, "ensure_visible", wraps=body.ensure_visible) as reveal:
            body._on_focus_in(SimpleNamespace(widget=first))
            body._on_focus_in(SimpleNamespace(widget=second))
            pending = self.after_ids()
            body._on_destroy(SimpleNamespace(widget=first))
            self.assertEqual(self.after_ids(), pending)
            first.destroy()
            self.root.update_idletasks()
            self.assertIn(call(second), reveal.call_args_list)
        with patch.object(body.canvas, "yview", return_value=(.25, .5)), \
                patch.object(body.canvas, "yview_moveto") as move:
            self.assertEqual(body._on_mousewheel(SimpleNamespace(widget=body.canvas, delta=-120)), "break")
            self.assertAlmostEqual(move.call_args.args[0], .33)

    def test_destroyed_field_before_deferred_focus_is_harmless(self):
        body = self.body(action_editor=True)
        field = self.field(body)
        with patch.object(body.canvas, "yview_moveto") as move:
            body._on_focus_in(SimpleNamespace(widget=field))
            field.destroy()
            self.root.update_idletasks()
            move.assert_not_called()

    def test_destroyed_window_cancels_reveal_before_idle(self):
        body = self.body(action_editor=True)
        field = self.field(body)
        before = self.after_ids()
        with patch.object(body, "ensure_visible") as reveal:
            body._on_focus_in(SimpleNamespace(widget=field))
            owned_after = self.after_ids() - before
            self.assertEqual(len(owned_after), 1)
            self.window.destroy()
            self.assertTrue(owned_after.isdisjoint(self.after_ids()))
            self.root.update_idletasks()
            reveal.assert_not_called()

    def test_reentrant_idle_destruction_cannot_scroll_a_dead_body(self):
        for action_editor in (False, True):
            body = self.body(action_editor=action_editor)
            field = self.field(body)
            layout_owner = body.canvas if action_editor else self.window
            with patch.object(layout_owner, "update_idletasks", side_effect=body.host.destroy), \
                    patch.object(body.canvas, "yview_moveto") as move:
                body.ensure_visible(field)
                move.assert_not_called()

    def test_reentrant_idle_destruction_cannot_measure_a_dead_field(self):
        for action_editor in (False, True):
            body = self.body(action_editor=action_editor)
            field = self.field(body)
            layout_owner = body.canvas if action_editor else self.window
            with patch.object(layout_owner, "update_idletasks", side_effect=field.destroy), \
                    patch.object(body.canvas, "yview_moveto") as move:
                body.ensure_visible(field)
                move.assert_not_called()
            body.host.destroy()


if __name__ == "__main__":
    unittest.main()
