from __future__ import annotations

import tkinter as tk
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.help_window import MarkdownLine, parse_inline, parse_markdown
from context_palette.launcher import HelpWindow, suggest_url_template


class FakeSearchVar:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


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
    window.search_status_var = FakeSearchVar("")
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


class MarkdownRenderingTests(unittest.TestCase):
    def test_parser_removes_markdown_structure_and_preserves_content(self):
        lines = parse_markdown(
            "# Title\n\n- First **item**\n\n```text\nrun.bat\n```\n\n| A | B |\n| --- | --- |\n| 1 | 2 |"
        )

        self.assertEqual(
            [(line.kind, line.text) for line in lines],
            [
                ("heading", "Title"),
                ("blank", ""),
                ("bullet", "First **item**"),
                ("blank", ""),
                ("code", "run.bat"),
                ("blank", ""),
                ("table_header", "A\tB"),
                ("table", "1\t2"),
            ],
        )

    def test_table_header_requires_the_markdown_divider_row(self):
        lines = parse_markdown("| Key | Meaning |\n| :--- | ---: |\n| F1 | Help |")

        self.assertEqual(lines[0], MarkdownLine("table_header", "Key\tMeaning"))
        self.assertEqual(lines[1], MarkdownLine("table", "F1\tHelp"))

    def test_help_prominent_document_references_are_real_links(self):
        help_markdown = (ROOT / "docs" / "HELP.md").read_text(encoding="utf-8")

        self.assertIn("[Architecture](ARCHITECTURE.md)", help_markdown)
        self.assertIn("[Decisions](DECISIONS.md)", help_markdown)
        self.assertIn("[Multi-PC development](MULTI_PC_DEVELOPMENT.md)", help_markdown)
        self.assertIn("[Power Automate integration](../integrations/README.md)", help_markdown)

    def test_real_text_link_click_opens_local_markdown_document(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        root.geometry("320x200+20+20")
        try:
            with tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                docs = project / "docs"
                docs.mkdir()
                first = docs / "FIRST.md"
                second = docs / "SECOND.md"
                first.write_text("# First\n\nOpen [Second](SECOND.md).", encoding="utf-8")
                second.write_text("# Second\n\nDestination text.", encoding="utf-8")

                viewer = HelpWindow(root, first)
                viewer.window.geometry("720x520+40+40")
                viewer.window.deiconify()
                root.update()
                link_start = viewer.content.tag_ranges("doc_link_1")[0]
                bounds = viewer.content.bbox(link_start)
                self.assertIsNotNone(bounds)
                viewer.content.event_generate(
                    "<Motion>",
                    x=bounds[0] + 2,
                    y=bounds[1] + 2,
                )
                root.update()
                viewer.content.event_generate(
                    "<Button-1>",
                    x=bounds[0] + 2,
                    y=bounds[1] + 2,
                )
                root.update()

                self.assertEqual(viewer.current_path, second.resolve())
                self.assertIn("Destination text.", viewer.content.get("1.0", tk.END))
                self.assertEqual(str(viewer.back_button.cget("state")), "normal")
                viewer._go_back()
                self.assertEqual(viewer.current_path, first.resolve())
                self.assertEqual(str(viewer.forward_button.cget("state")), "normal")
                viewer._go_forward()
                self.assertEqual(viewer.current_path, second.resolve())
                viewer._go_home()
                self.assertEqual(viewer.current_path, first.resolve())
                self.assertEqual(viewer.window.title(), "Context Palette Help")
                with patch("context_palette.help_window.webbrowser.open", return_value=True) as browser:
                    viewer._open_in_browser()
                browser.assert_called_once_with(first.resolve().as_uri())
                self.assertEqual(
                    viewer.search_status_var.get(),
                    "Opened the current document in the default browser.",
                )
                viewer.window.destroy()
        finally:
            root.destroy()

    def test_document_reload_removes_obsolete_link_tags(self):
        content = unittest.mock.Mock()
        content.tag_names.return_value = ("sel", "doc_link_1", "doc_link_2", "bold")
        viewer = HelpWindow.__new__(HelpWindow)
        viewer.content = content
        viewer.link_counter = 8

        viewer._clear_link_tags()

        self.assertEqual(
            content.tag_delete.call_args_list,
            [unittest.mock.call("doc_link_1"), unittest.mock.call("doc_link_2")],
        )
        self.assertEqual(viewer.link_counter, 0)

    def test_inline_parser_exposes_styles_and_local_link_target(self):
        spans = parse_inline("Read **Help**, use `F1`, or open [MVP](MVP.md).")

        self.assertEqual(
            [(span.text, span.style, span.target) for span in spans],
            [
                ("Read ", "", ""),
                ("Help", "bold", ""),
                (", use ", "", ""),
                ("F1", "code", ""),
                (", or open ", "", ""),
                ("MVP", "link", "MVP.md"),
                (".", "", ""),
            ],
        )


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
