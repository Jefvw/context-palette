from __future__ import annotations

import tkinter as tk
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.help_window import render_markdown_html, resolve_local_markdown_link
from context_palette.inbox_window import suggest_url_template
from context_palette.launcher import HelpWindow


class FakeSearchVar:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class FakeHelpContent:
    def __init__(self, counts: list[int] | None = None) -> None:
        self.counts = list(counts or [])
        self.calls: list[tuple] = []

    def find_text(self, text: str, **options) -> int:
        self.calls.append(("find_text", text, options))
        return self.counts.pop(0) if self.counts else 0


def help_window(query: str, content: FakeHelpContent) -> HelpWindow:
    window = HelpWindow.__new__(HelpWindow)
    window.search_var = FakeSearchVar(query)
    window.search_status_var = FakeSearchVar("")
    window.content = content
    window.search_match_index = 0
    return window


class HelpWindowSearchTests(unittest.TestCase):
    def test_empty_search_does_not_change_content(self):
        content = FakeHelpContent()

        help_window("   ", content)._find_next()

        self.assertEqual(content.calls, [("find_text", "", {})])

    def test_search_selects_first_match_and_reports_count(self):
        content = FakeHelpContent([3])

        help_window("Help", content)._find_next()

        self.assertEqual(
            content.calls,
            [
                (
                    "find_text",
                    "Help",
                    {
                        "select": 1,
                        "ignore_case": True,
                        "highlight_all": True,
                    },
                ),
            ],
        )
        self.assertEqual(
            help_window("Help", FakeHelpContent()).search_match_index,
            0,
        )

    def test_search_wraps_after_last_match(self):
        content = FakeHelpContent([2, 2, 2, 2])
        viewer = help_window("palette", content)

        viewer._find_next()
        viewer._find_next()
        viewer._find_next()

        self.assertEqual(
            [call[2]["select"] for call in content.calls],
            [1, 2, 3, 1],
        )
        self.assertEqual(viewer.search_match_index, 1)

    def test_missing_search_reports_no_result(self):
        content = FakeHelpContent()
        viewer = help_window("missing", content)

        viewer._find_next()

        self.assertEqual(viewer.search_match_index, 0)
        self.assertIn("No result", viewer.search_status_var.get())


class MarkdownRenderingTests(unittest.TestCase):
    def test_renderer_supports_common_document_structures(self):
        html = render_markdown_html(
            "# Title\n\n- First **item**\n\n```text\nrun.bat\n```\n\n"
            "| A | B |\n| --- | --- |\n| 1 | 2 |"
        )

        self.assertIn("<h1>Title</h1>", html)
        self.assertIn("<strong>item</strong>", html)
        self.assertIn('<code class="language-text">run.bat', html)
        self.assertIn("<table>", html)
        self.assertIn("<th>A</th>", html)
        self.assertIn("<td>1</td>", html)

    def test_renderer_disables_raw_html(self):
        html = render_markdown_html("# Safe\n\n<script>alert('no')</script>")

        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_link_resolution_accepts_only_local_project_markdown(self):
        current = ROOT / "docs" / "HELP.md"

        local, anchor = resolve_local_markdown_link(
            "ARCHITECTURE.md#runtime-overview",
            current_path=current,
            project_root=ROOT,
        )
        external, _ = resolve_local_markdown_link(
            "https://example.com",
            current_path=current,
            project_root=ROOT,
        )
        outside, _ = resolve_local_markdown_link(
            "../../outside.md",
            current_path=current,
            project_root=ROOT,
        )

        self.assertEqual(local, (ROOT / "docs" / "ARCHITECTURE.md").resolve())
        self.assertEqual(anchor, "runtime-overview")
        self.assertIsNone(external)
        self.assertIsNone(outside)

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
                self.assertEqual(viewer.window.resizable(), (1, 1))
                self.assertEqual(viewer.window.transient(), "")
                viewer._open_link("SECOND.md")
                root.update()

                self.assertEqual(viewer.current_path, second.resolve())
                self.assertIn("Destination text.", viewer.content.get_page_text())
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

class ActionCreatorHelperTests(unittest.TestCase):
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
