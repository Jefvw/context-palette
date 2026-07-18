from __future__ import annotations

import tkinter as tk
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.launcher import HelpWindow, suggest_url_template


class FakeSearchVar:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class FakeHelpContent:
    def __init__(self, positions: dict[str, str] | None = None) -> None:
        self.positions = positions or {}
        self.calls: list[tuple] = []

    def tag_remove(self, tag: str, start: str, end: str) -> None:
        self.calls.append(("tag_remove", tag, start, end))

    def index(self, index: str) -> str:
        self.calls.append(("index", index))
        if index == tk.INSERT:
            return "2.4"
        return index

    def search(self, query: str, start: str, **options) -> str:
        self.calls.append(("search", query, start, options))
        return self.positions.get(start, "")

    def tag_add(self, tag: str, start: str, end: str) -> None:
        self.calls.append(("tag_add", tag, start, end))

    def see(self, index: str) -> None:
        self.calls.append(("see", index))

    def mark_set(self, mark: str, index: str) -> None:
        self.calls.append(("mark_set", mark, index))


def help_window(query: str, content: FakeHelpContent) -> HelpWindow:
    window = HelpWindow.__new__(HelpWindow)
    window.search_var = FakeSearchVar(query)
    window.content = content
    return window


class HelpWindowSearchTests(unittest.TestCase):
    def test_empty_search_does_not_change_content(self):
        content = FakeHelpContent()

        help_window("   ", content)._find_next()

        self.assertEqual(content.calls, [])

    def test_search_starts_after_insert_and_selects_the_match(self):
        content = FakeHelpContent({"2.4 +1c": "4.2"})

        help_window("Help", content)._find_next()

        self.assertEqual(
            content.calls,
            [
                ("tag_remove", "found", "1.0", tk.END),
                ("index", tk.INSERT),
                ("index", "2.4 +1c"),
                ("search", "Help", "2.4 +1c", {"stopindex": tk.END, "nocase": True}),
                ("tag_add", "found", "4.2", "4.2+4c"),
                ("see", "4.2"),
                ("mark_set", tk.INSERT, "4.2+4c"),
            ],
        )

    def test_search_wraps_to_the_start_of_the_document(self):
        content = FakeHelpContent({"1.0": "1.3"})

        help_window("palette", content)._find_next()

        searches = [call for call in content.calls if call[0] == "search"]
        self.assertEqual(
            searches,
            [
                ("search", "palette", "2.4 +1c", {"stopindex": tk.END, "nocase": True}),
                ("search", "palette", "1.0", {"stopindex": tk.END, "nocase": True}),
            ],
        )
        self.assertIn(("tag_add", "found", "1.3", "1.3+7c"), content.calls)

    def test_missing_search_only_clears_the_previous_highlight(self):
        content = FakeHelpContent()

        help_window("missing", content)._find_next()

        self.assertEqual(content.calls[-1][0], "search")
        self.assertNotIn("tag_add", [call[0] for call in content.calls])


class DraftActionCreatorHelperTests(unittest.TestCase):
    def test_suggest_url_template_appends_identifier_placeholder_to_base_url(self):
        self.assertEqual(
            suggest_url_template("https://domain-product.atlassian.net/browse/"),
            "https://domain-product.atlassian.net/browse/{id_url}",
        )

    def test_suggest_url_template_preserves_existing_placeholder(self):
        self.assertEqual(
            suggest_url_template("https://domain-product.atlassian.net/browse/{id_url}"),
            "https://domain-product.atlassian.net/browse/{id_url}",
        )


if __name__ == "__main__":
    unittest.main()
