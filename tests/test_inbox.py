from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.inbox import (
    InboxError,
    append_inbox_item,
    create_clipboard_item,
    load_inbox_items,
    update_inbox_item_state,
)


class InboxTests(unittest.TestCase):
    def test_create_clipboard_item_cleans_text_and_sets_metadata(self):
        item = create_clipboard_item(
            title="  Useful note  ",
            content="  Remember this  ",
            now=datetime(2026, 7, 11, 12, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(item.title, "Useful note")
        self.assertEqual(item.content, "Remember this")
        self.assertEqual(item.source, "clipboard")
        self.assertEqual(item.state, "Inbox")
        self.assertEqual(item.created_at, "2026-07-11T12:30:00+00:00")

    def test_empty_clipboard_text_is_rejected(self):
        with self.assertRaises(InboxError):
            create_clipboard_item(title="Empty", content="   ")

    def test_append_and_load_inbox_item(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inbox.json"
            item = create_clipboard_item(title="Note", content="Text")

            append_inbox_item(path, item)
            loaded = load_inbox_items(path)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].title, "Note")
        self.assertEqual(loaded[0].content, "Text")

    def test_update_inbox_item_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inbox.json"
            item = create_clipboard_item(title="Note", content="Text")
            append_inbox_item(path, item)

            update_inbox_item_state(path, item.id, "Draft")
            loaded = load_inbox_items(path)

        self.assertEqual(loaded[0].state, "Draft")


if __name__ == "__main__":
    unittest.main()
