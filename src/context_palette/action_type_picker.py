from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable

from .window_geometry import configure_standard_window


@dataclass(frozen=True)
class ActionTypePickerOption:
    """One creatable Action type and its searchable presentation metadata."""

    action_type: str
    label: str
    family: str
    description: str

    @property
    def search_text(self) -> str:
        return " ".join((self.label, self.family, self.action_type, self.description))


def filter_action_type_picker_options(
    options: Iterable[ActionTypePickerOption],
    query: str,
) -> tuple[ActionTypePickerOption, ...]:
    """Keep catalogue order while requiring every case-insensitive search term."""

    terms = tuple(query.casefold().split())
    if not terms:
        return tuple(options)
    return tuple(
        option
        for option in options
        if all(term in option.search_text.casefold() for term in terms)
    )


class ActionTypePickerDialog:
    """Small keyboard-first chooser for starting the ordinary Action form."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        options: Iterable[ActionTypePickerOption],
        on_select: Callable[[str], None],
        on_close: Callable[[], None] | None = None,
    ) -> None:
        self.options = tuple(options)
        self.on_select = on_select
        self.on_close = on_close
        self.filtered_options: tuple[ActionTypePickerOption, ...] = ()
        self.closed = False
        self.previous_grab = parent.grab_current()

        self.window = tk.Toplevel(parent)
        self.window.title("Choose Action type")
        configure_standard_window(self.window, parent)
        self.window.protocol("WM_DELETE_WINDOW", self._close)
        self.window.bind("<Escape>", lambda _event: self._close())

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        search_row = ttk.Frame(outer)
        search_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(search_row, text="Find Action type").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 8))
        self.count_var = tk.StringVar()
        ttk.Label(search_row, textvariable=self.count_var, style="Muted.TLabel").pack(
            side=tk.RIGHT
        )

        list_frame = ttk.Frame(outer)
        list_frame.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self.results = tk.Listbox(
            list_frame,
            activestyle="dotbox",
            exportselection=False,
            yscrollcommand=scrollbar.set,
        )
        scrollbar.configure(command=self.results.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.results.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.empty_var = tk.StringVar()
        ttk.Label(outer, textvariable=self.empty_var, style="Muted.TLabel").pack(
            fill=tk.X, pady=(6, 0)
        )
        ttk.Label(
            outer,
            text=(
                "Searches the Action label, family, technical type, and description. "
                "Use Down Arrow, Enter, or double-click."
            ),
            style="Muted.TLabel",
            wraplength=620,
        ).pack(fill=tk.X, pady=(6, 0))
        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=(10, 0))
        self.choose_button = ttk.Button(
            controls, text="Choose", command=self._choose, style="Accent.TButton"
        )
        self.choose_button.pack(side=tk.LEFT)
        ttk.Button(controls, text="Cancel", command=self._close).pack(side=tk.RIGHT)

        self.search_trace = self.search_var.trace_add("write", lambda *_args: self._render())
        self.search_entry.bind("<Down>", self._focus_results)
        self.search_entry.bind("<Return>", lambda _event: self._choose())
        self.results.bind("<Return>", lambda _event: self._choose())
        self.results.bind("<Double-1>", lambda _event: self._choose())
        self._render()
        self.window.transient(parent.winfo_toplevel())
        self.window.grab_set()
        self.window.after_idle(self.search_entry.focus_set)

    def _render(self) -> None:
        self.filtered_options = filter_action_type_picker_options(
            self.options, self.search_var.get()
        )
        self.results.delete(0, tk.END)
        for option in self.filtered_options:
            self.results.insert(tk.END, option.label)
        count = len(self.filtered_options)
        self.count_var.set(f"{count} Action type{'s' if count != 1 else ''}")
        self.choose_button.configure(state=tk.NORMAL if count else tk.DISABLED)
        self.empty_var.set("" if count else "No matching Action types. Try fewer words.")
        if count:
            self.results.selection_set(0)
            self.results.activate(0)
            self.results.see(0)

    def _focus_results(self, _event: tk.Event[tk.Misc]) -> str:
        if self.filtered_options:
            self.results.focus_set()
        return "break"

    def _choose(self) -> None:
        selection = self.results.curselection()
        if selection:
            action_type = self.filtered_options[selection[0]].action_type
            self._close()
            self.on_select(action_type)

    def _close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.search_var.trace_remove("write", self.search_trace)
        except tk.TclError:
            pass
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
        if self.on_close is not None:
            self.on_close()
