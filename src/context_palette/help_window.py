from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tkinter as tk
from tkinter import ttk
from urllib.parse import unquote
import webbrowser

from .style import COLORS
from .window_geometry import configure_standard_window


_INLINE_MARKUP = re.compile(
    r"\[([^\]]+)\]\(([^)]+)\)|`([^`]+)`|\*\*([^*]+)\*\*|(?<!\*)\*([^*]+)\*(?!\*)"
)
_TABLE_DIVIDER = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")


@dataclass(frozen=True)
class MarkdownLine:
    kind: str
    text: str = ""
    level: int = 0


@dataclass(frozen=True)
class InlineSpan:
    text: str
    style: str = ""
    target: str = ""


def parse_markdown(markdown: str) -> tuple[MarkdownLine, ...]:
    """Parse the small presentation subset used by local project documents."""
    lines: list[MarkdownLine] = []
    in_code = False
    raw_lines = markdown.splitlines()
    for index, raw_line in enumerate(raw_lines):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            lines.append(MarkdownLine("code", raw_line))
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", raw_line)
        if heading:
            lines.append(MarkdownLine("heading", heading.group(2), len(heading.group(1))))
        elif _TABLE_DIVIDER.match(raw_line):
            continue
        elif stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            next_is_divider = (
                index + 1 < len(raw_lines)
                and _TABLE_DIVIDER.match(raw_lines[index + 1]) is not None
            )
            lines.append(
                MarkdownLine(
                    "table_header" if next_is_divider else "table",
                    "\t".join(cells),
                )
            )
        elif re.match(r"^\s*[-*+]\s+", raw_line):
            text = re.sub(r"^\s*[-*+]\s+", "", raw_line)
            lines.append(MarkdownLine("bullet", text))
        elif re.match(r"^\s*\d+[.)]\s+", raw_line):
            lines.append(MarkdownLine("number", stripped))
        elif stripped.startswith(">"):
            lines.append(MarkdownLine("quote", stripped.lstrip(">").strip()))
        elif re.match(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", raw_line):
            lines.append(MarkdownLine("rule"))
        elif not stripped:
            lines.append(MarkdownLine("blank"))
        else:
            lines.append(MarkdownLine("paragraph", raw_line.strip()))
    return tuple(lines)


def parse_inline(text: str) -> tuple[InlineSpan, ...]:
    spans: list[InlineSpan] = []
    cursor = 0
    for match in _INLINE_MARKUP.finditer(text):
        if match.start() > cursor:
            spans.append(InlineSpan(text[cursor : match.start()]))
        if match.group(1) is not None:
            spans.append(InlineSpan(match.group(1), "link", match.group(2)))
        elif match.group(3) is not None:
            spans.append(InlineSpan(match.group(3), "code"))
        elif match.group(4) is not None:
            spans.append(InlineSpan(match.group(4), "bold"))
        else:
            spans.append(InlineSpan(match.group(5), "italic"))
        cursor = match.end()
    if cursor < len(text):
        spans.append(InlineSpan(text[cursor:]))
    return tuple(spans)


class HelpWindow:
    """Searchable, rendered viewer for local Context Palette Markdown pages."""

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
        self.link_counter = 0

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        footer = ttk.Frame(outer)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        ttk.Label(footer, textvariable=self.search_status_var, style="Status.TLabel").pack(side=tk.LEFT)
        ttk.Button(footer, text="Close", command=self.window.destroy, style="Compact.TButton").pack(side=tk.RIGHT)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(header, textvariable=self.document_title_var, style="Heading.TLabel").pack(side=tk.LEFT)
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
        search = ttk.Entry(header, textvariable=self.search_var, width=24)
        search.pack(side=tk.RIGHT, padx=(6, 0))
        search.bind("<Return>", lambda _event: self._find_next())
        self.window.bind("<Control-f>", lambda _event: self._focus_search(search))
        self.window.bind("<Alt-Left>", lambda _event: self._go_back())
        self.window.bind("<Alt-Right>", lambda _event: self._go_forward())
        self.window.bind("<Alt-Home>", lambda _event: self._go_home())
        ttk.Button(header, text="Find next", command=self._find_next).pack(side=tk.RIGHT)
        self.documents_button = ttk.Menubutton(header, text="Documents ▾")
        self.documents_button.pack(side=tk.RIGHT, padx=(0, 8))
        self._build_documents_menu()

        content_frame = ttk.Frame(outer)
        content_frame.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(content_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.content = tk.Text(
            content_frame,
            wrap=tk.WORD,
            font=("Segoe UI", 10),
            padx=14,
            pady=10,
            spacing1=2,
            spacing3=4,
            yscrollcommand=scrollbar.set,
            cursor="arrow",
        )
        self.content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.content.bind("<KeyPress>", self._block_content_edit)
        scrollbar.configure(command=self.content.yview)
        self._configure_tags()
        self._load_document(self.current_path, initial_title=title)

        self.window.transient(parent)
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
        return tuple(sorted({path.resolve() for path in candidates}, key=lambda path: str(path).casefold()))

    def _build_documents_menu(self) -> None:
        menu = tk.Menu(self.documents_button, tearoff=False)
        for path in self._documentation_paths():
            label = str(path.relative_to(self.project_root)).replace("\\", " / ")
            menu.add_command(label=label, command=lambda selected=path: self._load_document(selected))
        self.documents_button.configure(menu=menu)
        self.documents_menu = menu

    def _configure_tags(self) -> None:
        self.content.tag_configure("found", background="#fff2a8")
        self.content.tag_configure("h1", font=("Segoe UI Semibold", 18), foreground=COLORS["text"], spacing1=12, spacing3=8)
        self.content.tag_configure("h2", font=("Segoe UI Semibold", 15), foreground=COLORS["text"], spacing1=10, spacing3=6)
        self.content.tag_configure("h3", font=("Segoe UI Semibold", 12), foreground=COLORS["text"], spacing1=8, spacing3=4)
        self.content.tag_configure("bold", font=("Segoe UI Semibold", 10))
        self.content.tag_configure("italic", font=("Segoe UI", 10, "italic"))
        self.content.tag_configure("inline_code", font=("Consolas", 9), background=COLORS["topic_header"])
        self.content.tag_configure("code_block", font=("Consolas", 9), background=COLORS["topic_header"], lmargin1=14, lmargin2=14)
        self.content.tag_configure("bullet", lmargin1=18, lmargin2=32)
        self.content.tag_configure("number", lmargin1=12, lmargin2=32)
        self.content.tag_configure("quote", foreground=COLORS["muted_text"], lmargin1=18, lmargin2=18)
        table_tabs = (170, 340, 510, 680)
        self.content.tag_configure(
            "table",
            font=("Segoe UI", 9),
            background=COLORS["surface"],
            lmargin1=8,
            lmargin2=8,
            rmargin=8,
            tabs=table_tabs,
            spacing1=3,
            spacing3=3,
        )
        self.content.tag_configure(
            "table_header",
            font=("Segoe UI Semibold", 9),
            background=COLORS["topic_header"],
            foreground=COLORS["text"],
            lmargin1=8,
            lmargin2=8,
            rmargin=8,
            tabs=table_tabs,
            spacing1=5,
            spacing3=5,
        )
        self.content.tag_configure("rule", foreground=COLORS["border"], justify=tk.CENTER)
        self.content.tag_configure("link", foreground=COLORS["focus"], underline=True)

    def _load_document(
        self,
        path: Path,
        *,
        initial_title: str | None = None,
        record_history: bool = True,
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
            else f"Context Palette — {self.document_title_var.get()}"
        )
        self.content.configure(state=tk.NORMAL)
        self.content.delete("1.0", tk.END)
        self._clear_link_tags()
        self._render(markdown)
        self.content.mark_set(tk.INSERT, "1.0")
        self.content.see("1.0")
        self.search_status_var.set("Ctrl+F focuses search · Enter finds next")
        if record_history:
            self._record_history(resolved)
        self._update_navigation_buttons()

    def _clear_link_tags(self) -> None:
        for tag_name in self.content.tag_names():
            if str(tag_name).startswith("doc_link_"):
                self.content.tag_delete(tag_name)
        self.link_counter = 0

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

    def _render(self, markdown: str) -> None:
        for line in parse_markdown(markdown):
            if line.kind == "blank":
                self.content.insert(tk.END, "\n")
                continue
            if line.kind == "rule":
                self.content.insert(tk.END, "─" * 48 + "\n", "rule")
                continue
            prefix = "•  " if line.kind == "bullet" else ""
            line_tag = {
                "heading": f"h{min(line.level, 3)}",
                "code": "code_block",
                "bullet": "bullet",
                "number": "number",
                "quote": "quote",
                "table": "table",
                "table_header": "table_header",
            }.get(line.kind, "")
            self.content.insert(tk.END, prefix, line_tag)
            if line.kind == "code":
                self.content.insert(tk.END, line.text, line_tag)
            else:
                for span in parse_inline(line.text):
                    self._insert_span(span, line_tag)
            self.content.insert(tk.END, "\n", line_tag)

    def _insert_span(self, span: InlineSpan, line_tag: str) -> None:
        tags = [line_tag] if line_tag else []
        if span.style == "code":
            tags.append("inline_code")
        elif span.style in {"bold", "italic"}:
            tags.append(span.style)
        elif span.style == "link":
            self.link_counter += 1
            link_tag = f"doc_link_{self.link_counter}"
            tags.extend(("link", link_tag))
            self.content.tag_bind(link_tag, "<Button-1>", lambda _event, target=span.target: self._open_link(target))
            self.content.tag_bind(link_tag, "<Enter>", lambda _event: self.content.configure(cursor="hand2"))
            self.content.tag_bind(link_tag, "<Leave>", lambda _event: self.content.configure(cursor="arrow"))
        self.content.insert(tk.END, span.text, tuple(tags))

    def _open_link(self, target: str) -> None:
        path_target, separator, anchor = target.partition("#")
        clean_target = unquote(path_target)
        candidate = (
            self.current_path
            if not clean_target
            else (self.current_path.parent / clean_target).resolve()
        )
        if candidate.suffix.casefold() == ".md" and candidate.is_relative_to(self.project_root):
            self._load_document(candidate)
            if separator and anchor:
                self._show_anchor(unquote(anchor))
        else:
            self.search_status_var.set("Only local Markdown links open in this viewer.")

    def _show_anchor(self, anchor: str) -> None:
        heading = re.sub(r"[-_]+", " ", anchor).strip()
        position = self.content.search(heading, "1.0", stopindex=tk.END, nocase=True)
        if not position:
            self.search_status_var.set(f'Section “{heading}” was not found in this document.')
            return
        self.content.see(position)
        self.content.mark_set(tk.INSERT, position)
        self.search_status_var.set(f'Opened section “{heading}”.')

    @staticmethod
    def _block_content_edit(event: tk.Event) -> str | None:
        keysym = str(getattr(event, "keysym", ""))
        state = int(getattr(event, "state", 0) or 0)
        if keysym in {
            "Left",
            "Right",
            "Up",
            "Down",
            "Home",
            "End",
            "Prior",
            "Next",
        }:
            return None
        if state & 0x0004 and keysym.casefold() in {"a", "c", "f"}:
            return None
        return "break"

    def _find_next(self) -> None:
        query = self.search_var.get().strip()
        if not query:
            self.search_status_var.set("Type a word or phrase to search this document.")
            return
        self.content.tag_remove("found", "1.0", tk.END)
        start = self.content.index(f"{self.content.index(tk.INSERT)} +1c")
        position = self.content.search(query, start, stopindex=tk.END, nocase=True)
        if not position:
            position = self.content.search(query, "1.0", stopindex=tk.END, nocase=True)
        if not position:
            self.search_status_var.set(f'No result for “{query}” in this document.')
            return
        end = f"{position}+{len(query)}c"
        self.content.tag_add("found", position, end)
        self.content.see(position)
        self.content.mark_set(tk.INSERT, end)
        self.search_status_var.set(f'Found “{query}”. Press Enter for the next result.')

    def _focus_search(self, search: ttk.Entry) -> str:
        search.focus_set()
        search.selection_range(0, tk.END)
        return "break"
