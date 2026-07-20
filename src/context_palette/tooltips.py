from __future__ import annotations

import tkinter as tk
from typing import Callable


class WidgetTooltip:
    """Delayed hover help for an ordinary Tk widget."""

    def __init__(self, widget: tk.Widget, text: str | Callable[[], str]) -> None:
        self.widget = widget
        self.text = text
        self.window: tk.Toplevel | None = None
        self.after_id: str | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<FocusIn>", self._schedule, add="+")
        widget.bind("<FocusOut>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")
        setattr(widget, "_context_palette_has_tooltip", True)

    def _schedule(self, _event=None) -> None:
        self.hide()
        self.after_id = self.widget.after(500, self.show)

    def show(self) -> None:
        self.after_id = None
        if not self.widget.winfo_exists():
            return
        window = tk.Toplevel(self.widget)
        setattr(window, "_context_palette_tooltip_window", True)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        label = tk.Label(
            window,
            text=self.text() if callable(self.text) else self.text,
            justify=tk.LEFT,
            wraplength=360,
            background="#ffffe0",
            foreground="#202124",
            relief=tk.SOLID,
            borderwidth=1,
            padx=7,
            pady=5,
            font=("Segoe UI", 9),
        )
        label.pack()
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        window.geometry(f"+{x}+{y}")
        self.window = window

    def hide(self, _event=None) -> None:
        if self.after_id is not None:
            try:
                self.widget.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None


class ListboxItemTooltip:
    """Delayed hover help for the listbox row currently under the pointer."""

    def __init__(self, listbox: tk.Listbox, text_provider: Callable[[int], str]) -> None:
        self.listbox = listbox
        self.text_provider = text_provider
        self.index: int | None = None
        self.after_id: str | None = None
        self.window: tk.Toplevel | None = None
        self.x_root = 0
        self.y_root = 0
        listbox.bind("<Motion>", self._motion, add="+")
        listbox.bind("<Leave>", self.hide, add="+")
        listbox.bind("<ButtonPress>", self.hide, add="+")
        listbox.bind("<Destroy>", self.hide, add="+")

    def _motion(self, event: tk.Event) -> None:
        index = self._index_at(event.y)
        self.x_root = event.x_root
        self.y_root = event.y_root
        if index == self.index:
            return
        self.hide()
        self.index = index
        if index is not None:
            self.after_id = self.listbox.after(450, self.show)

    def _index_at(self, y: int) -> int | None:
        if self.listbox.size() == 0:
            return None
        index = self.listbox.nearest(y)
        bounds = self.listbox.bbox(index)
        if bounds is None or not bounds[1] <= y < bounds[1] + bounds[3]:
            return None
        return index

    def show(self) -> None:
        self.after_id = None
        if self.index is None or not self.listbox.winfo_exists():
            return
        text = self.text_provider(self.index)
        if not text:
            return
        window = tk.Toplevel(self.listbox)
        setattr(window, "_context_palette_tooltip_window", True)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        tk.Label(
            window,
            text=text,
            justify=tk.LEFT,
            wraplength=380,
            background="#ffffe0",
            foreground="#202124",
            relief=tk.SOLID,
            borderwidth=1,
            padx=7,
            pady=5,
            font=("Segoe UI", 9),
        ).pack()
        window.update_idletasks()
        x = min(self.x_root + 14, window.winfo_screenwidth() - window.winfo_reqwidth() - 8)
        y = min(self.y_root + 18, window.winfo_screenheight() - window.winfo_reqheight() - 8)
        window.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.window = window

    def hide(self, _event=None) -> None:
        if self.after_id is not None:
            try:
                self.listbox.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None
        self.index = None


class TreeviewItemTooltip:
    """Delayed hover help for a Treeview item under the pointer."""

    def __init__(self, tree, text_provider: Callable[[str], str]) -> None:
        self.tree = tree
        self.text_provider = text_provider
        self.item_id = ""
        self.after_id: str | None = None
        self.window: tk.Toplevel | None = None
        self.x_root = 0
        self.y_root = 0
        tree.bind("<Motion>", self._motion, add="+")
        tree.bind("<Leave>", self.hide, add="+")
        tree.bind("<ButtonPress>", self.hide, add="+")
        tree.bind("<Destroy>", self.hide, add="+")

    def _motion(self, event: tk.Event) -> None:
        item_id = self.tree.identify_row(event.y)
        self.x_root = event.x_root
        self.y_root = event.y_root
        if item_id == self.item_id:
            return
        self.hide()
        self.item_id = item_id
        if item_id:
            self.after_id = self.tree.after(450, self.show)

    def show(self) -> None:
        self.after_id = None
        if not self.item_id or not self.tree.winfo_exists():
            return
        text = self.text_provider(self.item_id)
        if not text:
            return
        window = tk.Toplevel(self.tree)
        setattr(window, "_context_palette_tooltip_window", True)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        tk.Label(
            window,
            text=text,
            justify=tk.LEFT,
            wraplength=380,
            background="#ffffe0",
            foreground="#202124",
            relief=tk.SOLID,
            borderwidth=1,
            padx=7,
            pady=5,
            font=("Segoe UI", 9),
        ).pack()
        window.update_idletasks()
        x = min(self.x_root + 14, window.winfo_screenwidth() - window.winfo_reqwidth() - 8)
        y = min(self.y_root + 18, window.winfo_screenheight() - window.winfo_reqheight() - 8)
        window.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.window = window

    def hide(self, _event=None) -> None:
        if self.after_id is not None:
            try:
                self.tree.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None
        self.item_id = ""
