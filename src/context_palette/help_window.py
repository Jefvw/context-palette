from __future__ import annotations

from html import escape
from pathlib import Path
import re
import tkinter as tk
from tkinter import ttk
from urllib.parse import unquote, urlparse
import webbrowser

from markdown_it import MarkdownIt
from tkinterweb import HtmlFrame

from .style import COLORS
from .window_geometry import configure_standard_window


_MARKDOWN = (
    MarkdownIt(
        "commonmark",
        {
            "html": False,
            "linkify": False,
            "typographer": False,
        },
    )
    .enable("table")
    .enable("strikethrough")
)

_DOCUMENT_CSS = f"""
html {{
    background: {COLORS["surface"]};
    color: {COLORS["text"]};
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 10pt;
}}
body {{
    margin: 18px 22px 28px 22px;
    line-height: 1.48;
}}
h1, h2, h3, h4, h5, h6 {{
    color: {COLORS["text"]};
    font-weight: 600;
    margin-top: 1.2em;
    margin-bottom: 0.45em;
}}
h1 {{
    font-size: 21pt;
    border-bottom: 1px solid {COLORS["border"]};
    padding-bottom: 0.25em;
}}
h2 {{
    font-size: 17pt;
    border-bottom: 1px solid {COLORS["topic_header"]};
    padding-bottom: 0.2em;
}}
h3 {{ font-size: 14pt; }}
h4 {{ font-size: 12pt; }}
h5 {{ font-size: 10.5pt; }}
h6 {{
    font-size: 10pt;
    color: {COLORS["muted_text"]};
}}
p, ul, ol, blockquote, pre, table {{
    margin-top: 0.55em;
    margin-bottom: 0.9em;
}}
ul, ol {{
    padding-left: 2em;
}}
li {{
    margin-top: 0.2em;
    margin-bottom: 0.2em;
}}
a {{
    color: {COLORS["focus"]};
    text-decoration: underline;
}}
code {{
    font-family: Consolas, "Courier New", monospace;
    font-size: 9pt;
    background: {COLORS["topic_header"]};
    padding: 2px 4px;
}}
pre {{
    font-family: Consolas, "Courier New", monospace;
    font-size: 9pt;
    line-height: 1.35;
    background: {COLORS["topic_header"]};
    border: 1px solid {COLORS["border"]};
    padding: 10px 12px;
    white-space: pre-wrap;
}}
pre code {{
    padding: 0;
}}
blockquote {{
    color: {COLORS["muted_text"]};
    border-left: 4px solid {COLORS["border"]};
    margin-left: 0;
    padding: 3px 12px;
}}
table {{
    width: 100%;
    border-collapse: collapse;
}}
th, td {{
    border: 1px solid {COLORS["border"]};
    padding: 7px 9px;
    text-align: left;
    vertical-align: top;
}}
th {{
    background: {COLORS["topic_header"]};
    font-weight: 600;
}}
tr:nth-child(even) td {{
    background: {COLORS["background"]};
}}
hr {{
    border: 0;
    border-top: 1px solid {COLORS["border"]};
    margin: 1.4em 0;
}}
"""


def render_markdown_html(markdown: str, *, title: str = "Document") -> str:
    """Render trusted local Markdown with raw HTML and automatic URL fetching disabled."""
    body = _MARKDOWN.render(markdown)
    return (
        "<!doctype html><html><head>"
        '<meta charset="utf-8">'
        f"<title>{escape(title)}</title>"
        f"<style>{_DOCUMENT_CSS}</style>"
        "</head><body>"
        f"{body}"
        "</body></html>"
    )


def resolve_local_markdown_link(
    target: str,
    *,
    current_path: Path,
    project_root: Path,
) -> tuple[Path | None, str]:
    """Resolve a clicked link while retaining the viewer's local-Markdown boundary."""
    parsed = urlparse(target)
    if parsed.scheme and parsed.scheme.casefold() != "file":
        return None, ""
    if parsed.scheme.casefold() == "file":
        path_text = unquote(parsed.path)
        if re.match(r"^/[A-Za-z]:/", path_text):
            path_text = path_text[1:]
        candidate = Path(path_text).resolve()
    else:
        path_text = unquote(parsed.path)
        candidate = current_path if not path_text else (current_path.parent / path_text).resolve()
    if (
        candidate.suffix.casefold() != ".md"
        or not candidate.is_relative_to(project_root.resolve())
    ):
        return None, ""
    return candidate, unquote(parsed.fragment)


class HelpWindow:
    """Searchable, high-fidelity viewer for local Context Palette Markdown pages."""

    def __init__(
        self,
        parent: tk.Tk,
        help_path: Path,
        *,
        title: str = "Context Palette Help",
    ) -> None:
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        configure_standard_window(self.window)
        self.window.resizable(True, True)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.search_var = tk.StringVar()
        self.search_status_var = tk.StringVar(value="Ctrl+F focuses search · Enter finds next")
        self.document_title_var = tk.StringVar(value=title)
        self.project_root = self._project_root(help_path)
        self.current_path = help_path.resolve()
        self.home_path = self.current_path
        self.home_title = title
        self.history: list[Path] = []
        self.history_index = -1
        self.search_match_index = 0

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        footer = ttk.Frame(outer)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        ttk.Label(
            footer,
            textvariable=self.search_status_var,
            style="Status.TLabel",
        ).pack(side=tk.LEFT)
        ttk.Button(
            footer,
            text="Close",
            command=self.window.destroy,
            style="Compact.TButton",
        ).pack(side=tk.RIGHT)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(
            header,
            textvariable=self.document_title_var,
            style="Heading.TLabel",
        ).pack(side=tk.LEFT)
        self.back_button = ttk.Button(
            header,
            text="←",
            width=3,
            command=self._go_back,
            style="Compact.TButton",
        )
        self.back_button.pack(side=tk.LEFT, padx=(10, 2))
        self.forward_button = ttk.Button(
            header,
            text="→",
            width=3,
            command=self._go_forward,
            style="Compact.TButton",
        )
        self.forward_button.pack(side=tk.LEFT, padx=2)
        self.home_button = ttk.Button(
            header,
            text="Home",
            command=self._go_home,
            style="Compact.TButton",
        )
        self.home_button.pack(side=tk.LEFT, padx=(2, 0))
        self.browser_button = ttk.Button(
            header,
            text="Browser",
            command=self._open_in_browser,
            style="Compact.TButton",
        )
        self.browser_button.pack(side=tk.LEFT, padx=(6, 0))
        search = ttk.Entry(header, textvariable=self.search_var, width=20)
        search.pack(side=tk.RIGHT, padx=(6, 0))
        search.bind("<Return>", lambda _event: self._find_next())
        search.bind("<KeyRelease>", self._reset_search)
        self.window.bind("<Control-f>", lambda _event: self._focus_search(search))
        self.window.bind("<Alt-Left>", lambda _event: self._go_back())
        self.window.bind("<Alt-Right>", lambda _event: self._go_forward())
        self.window.bind("<Alt-Home>", lambda _event: self._go_home())
        ttk.Button(header, text="Find next", command=self._find_next).pack(side=tk.RIGHT)
        self.documents_button = ttk.Menubutton(header, text="Documents")
        self.documents_button.pack(side=tk.RIGHT, padx=(0, 8))
        self._build_documents_menu()

        self.content = HtmlFrame(
            outer,
            messages_enabled=False,
            on_link_click=self._open_link,
            selection_enabled=True,
            images_enabled=False,
            forms_enabled=False,
            objects_enabled=False,
            javascript_enabled=False,
            threading_enabled=False,
            horizontal_scrollbar=False,
            textwrap=True,
        )
        self.content.pack(fill=tk.BOTH, expand=True)
        self._load_document(self.current_path, initial_title=title)

        self.window.lift()
        search.focus_set()

    @staticmethod
    def _project_root(path: Path) -> Path:
        resolved = path.resolve()
        return resolved.parent.parent if resolved.parent.name.casefold() == "docs" else resolved.parent

    def _documentation_paths(self) -> tuple[Path, ...]:
        candidates = list(self.project_root.glob("*.md"))
        for folder in ("docs", "integrations"):
            directory = self.project_root / folder
            if directory.is_dir():
                candidates.extend(directory.rglob("*.md"))
        return tuple(
            sorted(
                {path.resolve() for path in candidates},
                key=lambda path: str(path).casefold(),
            )
        )

    def _build_documents_menu(self) -> None:
        menu = tk.Menu(self.documents_button, tearoff=False)
        for path in self._documentation_paths():
            label = str(path.relative_to(self.project_root)).replace("\\", " / ")
            menu.add_command(
                label=label,
                command=lambda selected=path: self._load_document(selected),
            )
        self.documents_button.configure(menu=menu)
        self.documents_menu = menu

    def _load_document(
        self,
        path: Path,
        *,
        initial_title: str | None = None,
        record_history: bool = True,
        anchor: str = "",
    ) -> None:
        resolved = path.resolve()
        if resolved.suffix.casefold() != ".md" or not resolved.is_relative_to(self.project_root):
            self.search_status_var.set("Only local project Markdown documents can be opened.")
            return
        try:
            markdown = resolved.read_text(encoding="utf-8")
        except OSError as exc:
            markdown = f"# Document could not be loaded\n\n`{resolved}`\n\n{exc}"
        self.current_path = resolved
        displayed_title = (
            self.home_title
            if resolved == self.home_path
            else initial_title or resolved.stem.replace("_", " ").title()
        )
        self.document_title_var.set(displayed_title)
        self.window.title(
            self.home_title
            if resolved == self.home_path
            else f"Context Palette — {displayed_title}"
        )
        self.content.load_html(
            render_markdown_html(markdown, title=displayed_title),
            base_url=resolved.parent.as_uri() + "/",
            fragment=anchor or None,
        )
        self.search_match_index = 0
        self.search_status_var.set("Ctrl+F focuses search · Enter finds next")
        if record_history:
            self._record_history(resolved)
        self._update_navigation_buttons()

    def _record_history(self, path: Path) -> None:
        if self.history_index >= 0 and self.history[self.history_index] == path:
            return
        del self.history[self.history_index + 1 :]
        self.history.append(path)
        self.history_index = len(self.history) - 1

    def _update_navigation_buttons(self) -> None:
        self.back_button.configure(state=tk.NORMAL if self.history_index > 0 else tk.DISABLED)
        self.forward_button.configure(
            state=tk.NORMAL if self.history_index + 1 < len(self.history) else tk.DISABLED
        )
        self.home_button.configure(
            state=tk.NORMAL if self.current_path != self.home_path else tk.DISABLED
        )

    def _go_back(self) -> str:
        if self.history_index > 0:
            self.history_index -= 1
            self._load_document(self.history[self.history_index], record_history=False)
        return "break"

    def _go_forward(self) -> str:
        if self.history_index + 1 < len(self.history):
            self.history_index += 1
            self._load_document(self.history[self.history_index], record_history=False)
        return "break"

    def _go_home(self) -> str:
        if self.current_path != self.home_path:
            self._load_document(self.home_path)
        return "break"

    def _open_in_browser(self) -> None:
        try:
            opened = webbrowser.open(self.current_path.as_uri())
        except (OSError, ValueError) as exc:
            self.search_status_var.set(f"Could not open this document in the browser: {exc}")
            return
        self.search_status_var.set(
            "Opened the current document in the default browser."
            if opened
            else "The default browser did not accept this document."
        )

    def _open_link(self, target: str) -> None:
        candidate, anchor = resolve_local_markdown_link(
            target,
            current_path=self.current_path,
            project_root=self.project_root,
        )
        if candidate is None:
            self.search_status_var.set("Only local Markdown links open in this viewer.")
            return
        self._load_document(candidate, anchor=anchor)

    def _reset_search(self, _event: tk.Event | None = None) -> None:
        self.search_match_index = 0

    def _find_next(self) -> None:
        query = self.search_var.get().strip()
        if not query:
            self.content.find_text("")
            self.search_match_index = 0
            self.search_status_var.set("Type a word or phrase to search this document.")
            return
        self.search_match_index += 1
        try:
            count = self.content.find_text(
                re.escape(query),
                select=self.search_match_index,
                ignore_case=True,
                highlight_all=True,
            )
        except (re.error, tk.TclError):
            count = 0
        if count and self.search_match_index > count:
            self.search_match_index = 1
            count = self.content.find_text(
                re.escape(query),
                select=1,
                ignore_case=True,
                highlight_all=True,
            )
        if not count:
            self.search_match_index = 0
            self.search_status_var.set(f'No result for “{query}” in this document.')
            return
        self.search_status_var.set(
            f'Found “{query}” · result {self.search_match_index} of {count}.'
        )

    @staticmethod
    def _focus_search(search: ttk.Entry) -> str:
        search.focus_set()
        search.selection_range(0, tk.END)
        return "break"
