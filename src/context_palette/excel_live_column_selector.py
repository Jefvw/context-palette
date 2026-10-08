"""Shared physical-column selection; headers never determine column identity."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def column_label(column) -> str:
    header = getattr(column, "header_value")
    shown = "(blank header)" if header is None or header == "" else str(header)
    return f"{column.column_index} · {column.column_letter} · {shown}"


class LiveExcelColumnSelector(ttk.Frame):
    """Keep legacy list order or explicit selection order for direct batches."""

    def __init__(self, parent, *, columns, selected_columns=(), selection_changed=None,
                 ordered_selection=False):
        super().__init__(parent)
        self.columns = tuple(columns)
        self.ordered_selection = ordered_selection
        self.selection_changed = selection_changed or (lambda: None)
        self._order = list(dict.fromkeys(selected_columns))
        self.listbox = tk.Listbox(self, selectmode=tk.MULTIPLE, exportselection=False,
                                  height=10, activestyle="dotbox")
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.grid(row=0, column=0, sticky=tk.NSEW)
        scrollbar.grid(row=0, column=1, sticky=tk.NS)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        for index, column in enumerate(self.columns):
            self.listbox.insert(tk.END, column_label(column))
            if column.column_index in self._order:
                self.listbox.selection_set(index)
        self.listbox.bind("<<ListboxSelect>>", self._selection_changed)

    def selected_columns(self):
        selected = tuple(self.columns[index].column_index for index in self.listbox.curselection())
        if not self.ordered_selection:
            return selected
        self._order = [value for value in self._order if value in selected]
        self._order.extend(value for value in selected if value not in self._order)
        return tuple(self._order)

    def _selection_changed(self, _event=None):
        self.selected_columns()
        self.selection_changed()
