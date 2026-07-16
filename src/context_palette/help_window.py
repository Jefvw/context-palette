from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk


class HelpWindow:
    def __init__(self, parent: tk.Tk, help_path: Path) -> None:
        self.window = tk.Toplevel(parent)
        self.window.title("Context Palette Help")
        self.window.geometry("760x680")
        self.window.minsize(520, 420)
        self.search_var = tk.StringVar()

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(header, text="Context Palette Help", style="Heading.TLabel").pack(side=tk.LEFT)
        search = ttk.Entry(header, textvariable=self.search_var, width=28)
        search.pack(side=tk.RIGHT, padx=(6, 0))
        search.bind("<Return>", lambda _event: self._find_next())
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

        footer = ttk.Frame(outer)
        footer.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(footer, text=str(help_path), style="Muted.TLabel").pack(side=tk.LEFT)
        ttk.Button(footer, text="Close", command=self.window.destroy).pack(side=tk.RIGHT)
        self.window.transient(parent)
        self.window.lift()
        search.focus_set()

    def _find_next(self) -> None:
        query = self.search_var.get().strip()
        if not query:
            return
        self.content.tag_remove("found", "1.0", tk.END)
        start = self.content.index(f"{self.content.index(tk.INSERT)} +1c")
        position = self.content.search(query, start, stopindex=tk.END, nocase=True)
        if not position:
            position = self.content.search(query, "1.0", stopindex=tk.END, nocase=True)
        if not position:
            return
        end = f"{position}+{len(query)}c"
        self.content.tag_add("found", position, end)
        self.content.see(position)
        self.content.mark_set(tk.INSERT, end)
