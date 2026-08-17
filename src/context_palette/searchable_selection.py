from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable

from .window_geometry import place_child_window


class SearchableSelectionPopup:
    """Small searchable chooser for a finite set of short labels.

    The same popup deliberately supports both the checklist used by editable
    tag fields and the single-value filters in the launcher.  It leaves the
    surrounding widget responsible for persistence and display state.
    """

    def __init__(
        self,
        owner: tk.Widget,
        values: Iterable[str],
        *,
        selected: Iterable[str] = (),
        multiple: bool,
        on_select: Callable[[tuple[str, ...]], None],
        title: str,
        empty_label: str | None = None,
        search_label: str = "Find tag",
        item_name: str = "tag",
    ) -> None:
        self.owner = owner
        self.values = tuple(values)
        self.multiple = multiple
        self.on_select = on_select
        self.empty_label = empty_label
        self.item_name = item_name
        self._selected_keys = {value.casefold() for value in selected}
        self.previous_grab = owner.grab_current()
        self.closed = False
        self.search_var = tk.StringVar(master=owner)

        self.window = tk.Toplevel(owner)
        self.window.title(title)
        self.window.transient(owner.winfo_toplevel())
        self.window.resizable(False, True)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self._close_event())

        outer = ttk.Frame(self.window, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)
        search_row = ttk.Frame(outer)
        search_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(search_row, text=search_label).pack(side=tk.LEFT)
        self.search_entry = ttk.Entry(
            search_row,
            textvariable=self.search_var,
            width=28,
        )
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 8))
        self.count_var = tk.StringVar(master=owner)
        ttk.Label(
            search_row,
            textvariable=self.count_var,
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)

        list_frame = ttk.Frame(outer)
        list_frame.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self.listbox = tk.Listbox(
            list_frame,
            height=min(max(len(self.values) + (1 if empty_label else 0), 3), 10),
            selectmode=tk.MULTIPLE if multiple else tk.BROWSE,
            exportselection=False,
            yscrollcommand=scrollbar.set,
        )
        scrollbar.configure(command=self.listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(controls, text="Cancel", command=self.close).pack(side=tk.RIGHT)
        self.apply_button = ttk.Button(
            controls,
            text="Add selected" if multiple else "Choose",
            command=self.apply,
            style="Accent.TButton",
        )
        self.apply_button.pack(side=tk.RIGHT, padx=(0, 5))

        self.search_var.trace_add("write", self._render)
        self.search_entry.bind("<Down>", self._focus_results)
        self.search_entry.bind("<Escape>", lambda _event: self._close_event())
        self.listbox.bind("<Escape>", lambda _event: self._close_event())
        self.search_entry.bind("<Return>", lambda _event: self._apply_event())
        self.listbox.bind("<Return>", lambda _event: self._apply_event())
        self.listbox.bind("<Double-Button-1>", lambda _event: self._apply_event())
        self.listbox.bind("<<ListboxSelect>>", self._selection_changed)
        self._render()
        self._place_near_owner()
        self.window.grab_set()
        self.window.after_idle(self.search_entry.focus_set)

    def _place_near_owner(self) -> None:
        place_child_window(
            self.window,
            self.owner,
            below_owner=True,
        )

    def _entries(self) -> tuple[str, ...]:
        query = self.search_var.get().strip().casefold()
        entries = self.values
        if query:
            entries = tuple(value for value in entries if query in value.casefold())
        if self.empty_label is not None and (not query or query in self.empty_label.casefold()):
            return (self.empty_label, *entries)
        return entries

    def _render(self, *_args: object) -> None:
        self.listbox.delete(0, tk.END)
        self.visible_values = self._entries()
        for index, value in enumerate(self.visible_values):
            self.listbox.insert(tk.END, value)
            if value.casefold() in self._selected_keys:
                self.listbox.selection_set(index)
        result_count = len(self.visible_values) - (
            1
            if self.empty_label is not None
            and self.empty_label in self.visible_values
            else 0
        )
        self.count_var.set(
            f"{result_count} {self.item_name}"
            f"{'s' if result_count != 1 else ''}"
        )
        self.apply_button.configure(
            state=tk.NORMAL if self.visible_values else tk.DISABLED
        )
        if not self.visible_values:
            return
        selection = self.listbox.curselection()
        if not self.multiple and not selection:
            self.listbox.selection_set(0)
            selection = (0,)
        active_index = selection[0] if selection else 0
        self.listbox.activate(active_index)
        self.listbox.see(active_index)

    def selected_values(self) -> tuple[str, ...]:
        return tuple(
            value
            for value in ((self.empty_label,) if self.empty_label else ()) + self.values
            if value.casefold() in self._selected_keys
        )

    def _selection_changed(self, _event: tk.Event | None = None) -> None:
        visible_keys = {value.casefold() for value in self.visible_values}
        selected_keys = {
            self.visible_values[index].casefold()
            for index in self.listbox.curselection()
        }
        if self.multiple:
            self._selected_keys.difference_update(visible_keys)
            self._selected_keys.update(selected_keys)
        else:
            self._selected_keys = selected_keys

    def apply(self) -> None:
        if not self.visible_values:
            return
        self._selection_changed()
        selected = self.selected_values()
        if not self.multiple:
            selected = selected[:1]
        self.on_select(selected)
        self.close()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            if self.window.grab_current() is self.window:
                self.window.grab_release()
        except tk.TclError:
            pass
        self.window.destroy()
        if self.previous_grab is not None:
            try:
                if self.previous_grab.winfo_exists():
                    self.previous_grab.grab_set()
            except tk.TclError:
                pass

    def _focus_results(self, _event: tk.Event | None = None) -> str:
        if self.visible_values:
            self.listbox.focus_set()
        return "break"

    def _apply_event(self) -> str:
        self.apply()
        return "break"

    def _close_event(self) -> str:
        self.close()
        return "break"
