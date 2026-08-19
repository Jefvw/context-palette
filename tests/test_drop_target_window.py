from __future__ import annotations

import tkinter as tk
import sys
import unittest
from unittest.mock import patch

from context_palette.drop_adapter import DropItem, DropResolutionCoordinator, DropResult
from context_palette.drop_target_window import (
    DROP_COPY_ACTION,
    DROP_REFUSE_ACTION,
    DropTargetWindow,
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
