from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable

from .window_geometry import configure_standard_window


@dataclass(frozen=True)
class ActionPickerOption:
    """One human-readable action choice and the metadata used to find it."""

    action_id: str
    label: str
    search_text: str


def filter_action_picker_options(
    options: Iterable[ActionPickerOption],
    query: str,
) -> tuple[ActionPickerOption, ...]:
    """Return options containing every case-insensitive search term."""

    terms = tuple(query.casefold().split())
    if not terms:
        return tuple(options)
    return tuple(
        option
        for option in options
        if all(
            term in f"{option.label} {option.search_text}".casefold()
            for term in terms
        )
    )


class ActionPickerField(ttk.Frame):
    """Readonly action field backed by a consistent searchable selection dialog."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        variable: tk.StringVar,
        options: Iterable[ActionPickerOption] = (),
        empty_label: str | None = None,
        title: str = "Choose action",
        entry_width: int | None = None,
        button_text: str = "Find…",
        button_width: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.variable = variable
        self.options = tuple(options)
        self.empty_label = empty_label
        self.title = title

        entry_options: dict[str, object] = {
            "textvariable": variable,
            "state": "readonly",
        }
        if entry_width is not None:
            entry_options["width"] = entry_width
        self.entry = ttk.Entry(self, **entry_options)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        button_options: dict[str, object] = {
            "text": button_text,
            "command": self.open,
            "style": "Compact.TButton",
        }
        if button_width is not None:
            button_options["width"] = button_width
        self.choose_button = ttk.Button(
            self,
            **button_options,
        )
        self.choose_button.pack(side=tk.RIGHT, padx=(5, 0))

    def set_options(
        self,
        options: Iterable[ActionPickerOption],
        *,
        empty_label: str | None = None,
    ) -> None:
        self.options = tuple(options)
        if empty_label is not None:
            self.empty_label = empty_label

    def open(self) -> None:
        ActionPickerDialog(
            self,
            options=self.options,
            current_label=self.variable.get(),
            on_select=self.variable.set,
            empty_label=self.empty_label,
            title=self.title,
        )


class ActionPickerDialog:
    """Keyboard-friendly searchable list used by every Configure action picker."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        options: Iterable[ActionPickerOption],
        current_label: str,
        on_select: Callable[[str], None],
        empty_label: str | None = None,
        title: str = "Choose action",
    ) -> None:
        self.options = tuple(options)
        self.current_label = current_label
        self.on_select = on_select
        self.empty_label = empty_label
        self.filtered_options: tuple[ActionPickerOption, ...] = ()
        self.previous_grab = parent.grab_current()
        self.closed = False

        self.window = tk.Toplevel(parent)
        self.window.title(title)
        configure_standard_window(self.window)
        self.window.protocol("WM_DELETE_WINDOW", self._close)
        self.window.bind("<Escape>", lambda _event: self._close())

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        search_row = ttk.Frame(outer)
        search_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(search_row, text="Find action").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        self.search_entry.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=(6, 8),
        )
        self.count_var = tk.StringVar()
        ttk.Label(
            search_row,
            textvariable=self.count_var,
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)

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

        ttk.Label(
            outer,
            text=(
                "Searches action name, description, built-in type, context, "
                "tag, and state. Use Down Arrow, Enter, or double-click."
            ),
            style="Muted.TLabel",
            wraplength=720,
        ).pack(fill=tk.X, pady=(6, 0))

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=(10, 0))
        self.select_button = ttk.Button(
            controls,
            text="Select",
            command=self._select,
            style="Accent.TButton",
        )
        self.select_button.pack(side=tk.LEFT)
        ttk.Button(
            controls,
            text="Cancel",
            command=self._close,
        ).pack(side=tk.RIGHT)

        self.search_trace = self.search_var.trace_add(
            "write",
            lambda *_args: self._render(),
        )
        self.search_entry.bind("<Down>", self._focus_results)
        self.search_entry.bind("<Return>", lambda _event: self._select())
        self.results.bind("<Return>", lambda _event: self._select())
        self.results.bind("<Double-1>", lambda _event: self._select())
        self._render()

        self.window.transient(parent.winfo_toplevel())
        self.window.grab_set()
        self.window.after_idle(self.search_entry.focus_set)

    def _display_options(self) -> tuple[tuple[str, str], ...]:
        options = tuple(
            (option.action_id, option.label)
            for option in filter_action_picker_options(
                self.options,
                self.search_var.get(),
            )
        )
        if self.empty_label is not None and not self.search_var.get().strip():
            return (("", self.empty_label), *options)
        return options

    def _render(self) -> None:
        display_options = self._display_options()
        self.filtered_options = tuple(
            ActionPickerOption(action_id, label, label)
            for action_id, label in display_options
        )
        self.results.delete(0, tk.END)
        for option in self.filtered_options:
            self.results.insert(tk.END, option.label)

        count = len(display_options) - (
            1
            if self.empty_label is not None
            and not self.search_var.get().strip()
            else 0
        )
        self.count_var.set(f"{count} action{'s' if count != 1 else ''}")
        self.select_button.configure(
            state=tk.NORMAL if display_options else tk.DISABLED
        )
        if not display_options:
            return

        selected = next(
            (
                index
                for index, option in enumerate(self.filtered_options)
                if option.label == self.current_label
            ),
            0,
        )
        self.results.selection_set(selected)
        self.results.activate(selected)
        self.results.see(selected)

    def _focus_results(self, _event: tk.Event[tk.Misc]) -> str:
        if self.filtered_options:
            self.results.focus_set()
        return "break"

    def _select(self) -> None:
        selection = self.results.curselection()
        if not selection:
            return
        self.on_select(self.filtered_options[selection[0]].label)
        self._close()

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
