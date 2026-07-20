from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from .actions import ActionError, append_action
from .cheatsheets import (
    CheatSheet,
    CheatSheetItem,
    draft_action_from_cheatsheet_item,
    filter_cheatsheet,
)
from .style import COLORS
from .window_geometry import configure_standard_window


class CheatSheetWindow:
    """Search and promote entries from configured local reference sheets."""

    def __init__(
        self,
        parent: tk.Tk,
        sheets: list[CheatSheet],
        actions_path: Path,
        on_change: Callable[[], None],
    ) -> None:
        self.sheets = sheets
        self.actions_path = actions_path
        self.on_change = on_change
        self.filtered_items: list[tuple[CheatSheet, str, CheatSheetItem]] = []
        self.selected_sheet_index = 0
        self.selected_item_index = 0
        self.search_entry: ttk.Entry | None = None
        self.status_var = tk.StringVar(value="")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_args: self._refresh_items())
        self.window = tk.Toplevel(parent)
        self.window.title("Context Palette Cheat Sheets")
        configure_standard_window(self.window)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(outer)
        controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        ttk.Label(controls, textvariable=self.status_var, style="Status.TLabel").pack(side=tk.LEFT)
        ttk.Button(
            controls,
            text="Close",
            command=self.window.destroy,
            style="Compact.TButton",
        ).pack(side=tk.RIGHT)

        ttk.Label(outer, text="Cheat sheets", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            outer,
            text=f"{len(sheets)} local reference sheet{'s' if len(sheets) != 1 else ''}",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(2, 8))

        self.listbox = tk.Listbox(outer, activestyle="dotbox", height=6, exportselection=False)
        self.listbox.pack(fill=tk.X, pady=(4, 8))
        self.listbox.bind("<<ListboxSelect>>", lambda _event: self._select_sheet())

        ttk.Label(outer, text="Search selected sheet").pack(anchor=tk.W)
        search_row = ttk.Frame(outer)
        search_row.pack(fill=tk.X, pady=(4, 8))

        search = ttk.Entry(search_row, textvariable=self.search_var)
        self.search_entry = search
        search.pack(side=tk.LEFT, fill=tk.X, expand=True)
        search.bind("<Escape>", lambda _event: self.window.destroy())
        ttk.Button(search_row, text="Promote to Draft", command=self._promote_selected).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        self.items = tk.Listbox(outer, activestyle="dotbox", height=8, exportselection=False)
        self.items.pack(fill=tk.BOTH, expand=True)
        self.items.bind("<<ListboxSelect>>", lambda _event: self._select_item())

        self.preview = tk.Text(outer, wrap=tk.WORD)
        self.preview.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.preview.configure(state=tk.DISABLED)

        self._load_sheets()
        self.window.transient(parent)
        self.window.lift()
        self.window.after(80, self.focus_search)

    def _load_sheets(self) -> None:
        for sheet in self.sheets:
            self.listbox.insert(tk.END, sheet.title)
        if self.sheets:
            self.listbox.selection_set(0)
            self.listbox.activate(0)
        self._refresh_items()

    def _refresh_items(self) -> None:
        sheet = self._selected_sheet()
        self.filtered_items = []
        self.selected_item_index = 0
        self.items.delete(0, tk.END)

        if sheet is None:
            self.items.insert(
                tk.END,
                "No cheat sheets are available. Add a local sheet or check configuration.",
            )
            self.items.itemconfigure(0, foreground=COLORS["muted_text"])
            self.status_var.set("No cheat sheets available")
            self._update_preview()
            return

        filtered_sheet = filter_cheatsheet(sheet, self.search_var.get())
        for section in filtered_sheet.sections:
            for item in section.items:
                self.filtered_items.append((sheet, section.title, item))
                self.items.insert(tk.END, f"{section.title} > {item.label}: {item.detail}")

        if self.filtered_items:
            self.items.selection_set(0)
            self.items.activate(0)
            self.status_var.set(f"{len(self.filtered_items)} matching items")
        else:
            query = self.search_var.get().strip()
            self.items.insert(
                tk.END,
                f'No entries match “{query}”. Clear search to show all entries.'
                if query
                else "This sheet has no entries.",
            )
            self.items.itemconfigure(0, foreground=COLORS["muted_text"])
            self.status_var.set("No matching entries")
        self._update_preview()

    def _select_sheet(self) -> None:
        selected = self.listbox.curselection()
        if selected:
            self.selected_sheet_index = selected[0]
        self._refresh_items()

    def _select_item(self) -> None:
        selected = self.items.curselection()
        if selected:
            self.selected_item_index = selected[0]
        self._update_preview()

    def _update_preview(self) -> None:
        selected = self._selected_item()
        if selected is None:
            sheet = self._selected_sheet()
            if sheet is None:
                text = "No cheat sheets available."
            elif self.search_var.get().strip():
                text = f"No matching items for: {self.search_var.get().strip()}"
            else:
                text = "Select a cheat-sheet item."
        else:
            sheet, section_title, item = selected
            text = (
                f"Sheet: {sheet.title}\n"
                f"Section: {section_title}\n"
                f"Item: {item.label}\n\n"
                f"{item.detail}\n\n"
                f"Tags: {', '.join(item.tags) if item.tags else '(none)'}"
            )

        self.preview.configure(state=tk.NORMAL)
        self.preview.delete("1.0", tk.END)
        self.preview.insert("1.0", text)
        self.preview.configure(state=tk.DISABLED)

    def _selected_sheet(self) -> CheatSheet | None:
        if not self.sheets:
            return None
        if self.selected_sheet_index >= len(self.sheets):
            self.selected_sheet_index = 0
        if self.selected_sheet_index < 0:
            return None
        return self.sheets[self.selected_sheet_index]

    def _selected_item(self) -> tuple[CheatSheet, str, CheatSheetItem] | None:
        if not self.filtered_items:
            return None
        if self.selected_item_index >= len(self.filtered_items):
            self.selected_item_index = 0
        if self.selected_item_index < 0:
            return None
        return self.filtered_items[self.selected_item_index]

    def _promote_selected(self) -> None:
        selected = self._selected_item()
        if selected is None:
            self.status_var.set("Select a cheat-sheet item first")
            return

        sheet, _section_title, item = selected
        try:
            action = draft_action_from_cheatsheet_item(sheet, item)
            append_action(self.actions_path, action)
            self.on_change()
            self.status_var.set(f"Promoted: {item.label}")
            messagebox.showinfo(
                "Context Palette",
                f"Created draft action:\n\n{sheet.title} > {item.label}",
                parent=self.window,
            )
        except ActionError as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.window)

    def focus_search(self) -> None:
        if self.search_entry is not None:
            self.search_entry.focus_force()
            self.search_entry.selection_range(0, tk.END)
