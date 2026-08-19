from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.inbox import InboxItem
from context_palette.inbox_window import InboxWindow


ITEM = InboxItem(
    "inbox-one",
    "Useful capture",
    "Captured text",
    "clipboard",
    "2026-08-18T12:00:00+00:00",
)


class InboxWindowTests(unittest.TestCase):
    def _window(self) -> InboxWindow:
        window = InboxWindow.__new__(InboxWindow)
        window.window = Mock()
        window.inbox_path = Path("inbox.json")
        window.items = [ITEM]
        window.on_change = Mock()
        window._selected_item = Mock(return_value=ITEM)
        window._load_items = Mock()
        return window

    def test_confirmed_delete_removes_capture_and_refreshes_window(self) -> None:
        window = self._window()
        with (
            patch(
                "context_palette.inbox_window.messagebox.askyesno",
                return_value=True,
            ) as confirmation,
            patch("context_palette.inbox_window.delete_inbox_item") as delete,
            patch(
                "context_palette.inbox_window.load_inbox_items",
                return_value=[],
            ),
        ):
            window._delete_selected()

        self.assertIn(
            "Any Action already created from it remains available",
            confirmation.call_args.args[1],
        )
        delete.assert_called_once_with(window.inbox_path, ITEM.id)
        self.assertEqual(window.items, [])
        window._load_items.assert_called_once_with()
        window.on_change.assert_called_once_with()

    def test_cancelled_delete_preserves_capture(self) -> None:
        window = self._window()
        with (
            patch(
                "context_palette.inbox_window.messagebox.askyesno",
                return_value=False,
            ),
            patch("context_palette.inbox_window.delete_inbox_item") as delete,
        ):
            window._delete_selected()

        delete.assert_not_called()
        window._load_items.assert_not_called()
        window.on_change.assert_not_called()

    def test_delete_storage_failure_preserves_window_state(self) -> None:
        window = self._window()
        with (
            patch(
                "context_palette.inbox_window.messagebox.askyesno",
                return_value=True,
            ),
            patch(
                "context_palette.inbox_window.delete_inbox_item",
                side_effect=OSError("The Inbox file is locked."),
            ),
            patch(
                "context_palette.inbox_window.messagebox.showerror"
            ) as error,
        ):
            window._delete_selected()

        window._load_items.assert_not_called()
        window.on_change.assert_not_called()
        self.assertIn("locked", error.call_args.args[1])


@unittest.skipUnless(sys.platform == "win32", "The Inbox UI requires Windows Tk.")
class InboxWindowSmokeTests(unittest.TestCase):
    def test_delete_and_advanced_creation_controls_are_clear(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            root.withdraw()
            try:
                base = Path(directory)
                window = InboxWindow(
                    root,
                    [ITEM],
                    [],
                    "General",
                    [],
                    base / "actions.json",
                    base / "inbox.json",
                    Mock(),
                    shared_contexts_path=base / "contexts.json",
                    local_contexts_path=base / "local-contexts.json",
                )
                root.update()

                self.assertEqual(window.delete_button.cget("text"), "Delete capture…")
                self.assertEqual(window.delete_button.cget("style"), "Danger.TButton")
                self.assertEqual(
                    window.other_creation_button.cget("text"),
                    "Other ways to create",
                )
                self.assertEqual(
                    [
                        window.other_creation_menu.entrycget(index, "label")
                        for index in (0, 1)
                    ],
                    ["Ask AI…", "Harvest documents…"],
                )
                window.window.destroy()
                root.update()
            finally:
                root.destroy()


if __name__ == "__main__":
    unittest.main()
