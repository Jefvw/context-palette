from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ScrollableDialogBody:
    """Own a Configure form's viewport, input bindings and deferred focus work.

    The footer belongs to the caller, outside this body. ``action_editor``
    preserves the Action form's fractional wheel steps and deferred focus;
    other Configure forms retain pointer-gated unit steps and immediate focus.
    """

    def __init__(
        self,
        window: tk.Toplevel,
        parent: ttk.Frame,
        *,
        action_editor: bool = False,
    ) -> None:
        self.window = window
        self._action_editor = action_editor
        self._closed = False
        self._pending_focus: set[str] = set()
        self.host = ttk.Frame(parent)
        self.host.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(
            self.host,
            borderwidth=0,
            highlightthickness=0,
            background=window.cget("background"),
            takefocus=False,
        )
        self.scrollbar = ttk.Scrollbar(
            self.host,
            orient=tk.VERTICAL,
            command=self.canvas.yview,
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.content = ttk.Frame(self.canvas)
        self.content_window_id = self.canvas.create_window(
            (0, 0), window=self.content, anchor=tk.NW,
        )
        self.content.bind("<Configure>", self._update_scrollregion, add="+")
        self.canvas.bind("<Configure>", self._resize_content, add="+")
        self._window_bindings = (
            ("<MouseWheel>", window.bind("<MouseWheel>", self._on_mousewheel, add="+")),
            ("<FocusIn>", window.bind("<FocusIn>", self._on_focus_in, add="+")),
        )
        self.host.bind("<Destroy>", self._on_destroy, add="+")

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is not self.host or self._closed:
            return
        self._closed = True
        for after_id in self._pending_focus:
            try:
                self.window.after_cancel(after_id)
            except tk.TclError:
                pass
        self._pending_focus.clear()
        for sequence, binding_id in self._window_bindings:
            if binding_id:
                try:
                    self.window.unbind(sequence, binding_id)
                except tk.TclError:
                    pass

    def _update_scrollregion(self, _event: tk.Event | None = None) -> None:
        if self._closed:
            return
        bounds = self.canvas.bbox("all")
        if bounds is not None or not self._action_editor:
            self.canvas.configure(scrollregion=bounds or (0, 0, 0, 0))

    def _resize_content(self, event: tk.Event) -> None:
        if not self._closed:
            self.canvas.itemconfigure(
                self.content_window_id, width=max(1, int(event.width)),
            )

    def _pointer_is_over_canvas(self) -> bool:
        x, y = self.window.winfo_pointerxy()
        left = self.canvas.winfo_rootx()
        top = self.canvas.winfo_rooty()
        return (
            left <= x < left + self.canvas.winfo_width()
            and top <= y < top + self.canvas.winfo_height()
        )

    def _on_mousewheel(self, event: tk.Event) -> str | None:
        if self._closed or isinstance(event.widget, (tk.Text, tk.Listbox, ttk.Combobox)):
            return None
        try:
            if self._action_editor:
                first, last = self.canvas.yview()
                if first <= 0.0 and last >= 1.0:
                    return None
                direction = -1 if int(event.delta) > 0 else 1
                maximum_start = max(0.0, 1.0 - max(0.0, last - first))
                self.canvas.yview_moveto(
                    max(0.0, min(first + direction * 0.08, maximum_start))
                )
                return "break"
            if not self._pointer_is_over_canvas():
                return None
            delta = int(getattr(event, "delta", 0) or 0)
            if delta:
                self.canvas.yview_scroll(-1 if delta > 0 else 1, "units")
                return "break"
        except tk.TclError:
            pass
        return None

    def _contains_widget(self, widget: tk.Misc) -> bool:
        current: tk.Misc | None = widget
        while current is not None:
            if current is self.content:
                return True
            if current is self.window:
                return False
            current = getattr(current, "master", None)
        return False

    def _on_focus_in(self, event: tk.Event) -> None:
        if self._closed or not self._contains_widget(event.widget):
            return
        if not self._action_editor:
            self.ensure_visible(event.widget)
            return

        def reveal_field() -> None:
            self._pending_focus.discard(after_id)
            self.ensure_visible(event.widget)

        try:
            after_id = self.window.after_idle(reveal_field)
            self._pending_focus.add(after_id)
        except tk.TclError:
            pass

    def ensure_visible(self, widget: tk.Misc) -> None:
        try:
            if self._closed or not widget.winfo_exists() or not self._contains_widget(widget):
                return
            geometry_owner = self.canvas if self._action_editor else self.window
            geometry_owner.update_idletasks()
            # Idle layout can destroy this body or the field before returning.
            if self._closed or not widget.winfo_exists():
                return
            viewport_height = self.canvas.winfo_height()
            if self._action_editor:
                bounds = self.canvas.bbox("all")
                if viewport_height <= 1 or bounds is None:
                    return
                content_height = max(1, bounds[3] - bounds[1])
            else:
                content_height = max(1, self.content.winfo_reqheight())
            viewport_top = float(self.canvas.canvasy(0))
            viewport_bottom = viewport_top + viewport_height
            widget_top = widget.winfo_rooty() - self.content.winfo_rooty()
            widget_bottom = widget_top + widget.winfo_height()
            margin = 8 if self._action_editor else 6
            trigger_margin = margin if self._action_editor else 0
            if widget_top < viewport_top + trigger_margin:
                target_top = widget_top - margin
            elif widget_bottom > viewport_bottom - trigger_margin:
                target_top = widget_bottom - viewport_height + margin
            else:
                return
            if self._action_editor:
                maximum_top = max(0, content_height - viewport_height)
                target_top = max(0.0, min(float(target_top), maximum_top))
            else:
                target_top = max(0.0, min(float(target_top), content_height))
            self.canvas.yview_moveto(target_top / content_height)
        except tk.TclError:
            # A queued reveal is harmless if its field/window has gone away.
            return
