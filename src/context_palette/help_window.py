from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk

from .window_geometry import configure_standard_window


class HelpWindow:
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
        ttk.Label(header, text=title, style="Heading.TLabel").pack(side=tk.LEFT)
        search = ttk.Entry(header, textvariable=self.search_var, width=28)
        search.pack(side=tk.RIGHT, padx=(6, 0))
        search.bind("<Return>", lambda _event: self._find_next())
        self.window.bind("<Control-f>", lambda _event: self._focus_search(search))
        ttk.Button(header, text="Find next", command=self._find_next).pack(side=tk.RIGHT)

        content_frame = ttk.Frame(outer)
        content_frame.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(content_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.content = tk.Text(
            content_frame,
            wrap=tk.WORD,
            font=("Segoe UI", 10),
            padx=10,
            pady=8,
            yscrollcommand=scrollbar.set,
        )
        self.content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.configure(command=self.content.yview)
        self.content.tag_configure("found", background="#fff2a8")

        try:
            text = help_path.read_text(encoding="utf-8")
        except OSError as exc:
            text = f"Help could not be loaded from:\n{help_path}\n\n{exc}"
        self.content.insert("1.0", text)
        self.content.configure(state=tk.DISABLED)

        self.window.transient(parent)
        self.window.lift()
        search.focus_set()

    def _find_next(self) -> None:
        query = self.search_var.get().strip()
        if not query:
            self.search_status_var.set("Type a word or phrase to search Help.")
            return
        self.content.tag_remove("found", "1.0", tk.END)
        start = self.content.index(f"{self.content.index(tk.INSERT)} +1c")
        position = self.content.search(query, start, stopindex=tk.END, nocase=True)
        if not position:
            position = self.content.search(query, "1.0", stopindex=tk.END, nocase=True)
        if not position:
            self.search_status_var.set(f'No Help result for “{query}”.')
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
