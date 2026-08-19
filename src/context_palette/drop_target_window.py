"""Optional, small Toplevel drop surface owned by an existing Tk root."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from .drop_adapter import (
    DropResolutionCoordinator,
    DropResult,
    decode_drop_values,
)


DROP_COPY_ACTION = "copy"
DROP_REFUSE_ACTION = "refuse_drop"


def _load_tk_dnd() -> object:
    from tkinterdnd2 import TkinterDnD

    return TkinterDnD


class DropTargetWindow:
    """A lazily created singleton-style drop surface; it owns no app state."""

    def __init__(
        self,
        root: tk.Misc,
        on_drop: Callable[[DropResult], None],
        *,
        coordinator: DropResolutionCoordinator | None = None,
    ) -> None:
        self.root = root
        self._on_drop = on_drop
        self._coordinator = coordinator or DropResolutionCoordinator()
        self.window: tk.Toplevel | None = None
        self._status: ttk.Label | None = None
        self._dnd_available: bool | None = None
        self._polling = False

    def start(self) -> bool:
        if not self._ensure_dnd():
            return False
        if self.window is None or not self.window.winfo_exists():
            self._create_window()
        return True

    def show(self) -> bool:
        if not self.start():
            return False
        assert self.window is not None
        self.window.deiconify()
        self.window.lift()
        return True

    def hide(self) -> None:
        if self.window is not None and self.window.winfo_exists():
            self.window.withdraw()

    def close(self) -> None:
        self.hide()

    def _ensure_dnd(self) -> bool:
        if self._dnd_available is not None:
            return self._dnd_available
        try:
            _load_tk_dnd().require(self.root)
        except Exception:
            self._dnd_available = False
            return False
        self._dnd_available = True
        return True

    def _create_window(self) -> None:
        window = tk.Toplevel(self.root)
        window.withdraw()
        self.window = window
        window.title("Drop into Context Palette")
        window.attributes("-topmost", True)
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", self.hide)
        frame = ttk.Frame(window, padding=12)
        frame.grid(sticky="nsew")
        ttk.Label(frame, text="Drop files, folders, links, or text here", wraplength=280).grid(sticky="w")
        self._status = ttk.Label(frame, text="Ready to receive a drop.", wraplength=280)
        self._status.grid(row=1, pady=(8, 8), sticky="w")
        ttk.Button(frame, text="Hide", command=self.hide).grid(row=2, sticky="e")
        window.drop_target_register("DND_Files", "DND_Text")
        window.dnd_bind("<<Drop:DND_Files>>", self._handle_files_drop)
        window.dnd_bind("<<Drop:DND_Text>>", self._handle_text_drop)
        window.update_idletasks()
        self._position_lower_right(window)
        window.deiconify()

    def _position_lower_right(self, window: tk.Toplevel) -> None:
        width, height = window.winfo_reqwidth(), window.winfo_reqheight()
        screen_width, screen_height = window.winfo_screenwidth(), window.winfo_screenheight()
        window.geometry(f"+{max(0, screen_width - width - 24)}+{max(0, screen_height - height - 72)}")

    def _handle_files_drop(self, event: object) -> str:
        return self._handle_drop(event, "DND_Files")

    def _handle_text_drop(self, event: object) -> str:
        return self._handle_drop(event, "DND_Text")

    def _handle_drop(self, event: object, drop_type: str) -> str:
        values, error = decode_drop_values(event, drop_type)
        if error is not None:
            self._complete(DropResult(error=error))
            return DROP_REFUSE_ACTION
        if not self._coordinator.start(values or ()):
            self._set_status("Still preparing the previous drop.")
            return DROP_REFUSE_ACTION
        self._set_status("Preparing drop…")
        if not self._polling:
            self._polling = True
            self.root.after(40, self._poll)
        return DROP_COPY_ACTION

    def _poll(self) -> None:
        result = self._coordinator.drain()
        if result is None:
            self.root.after(40, self._poll)
            return
        self._polling = False
        self._complete(result)

    def _complete(self, result: DropResult) -> None:
        if result.error is not None:
            status = result.error.message
        elif not result.items:
            status = "No supported content was found."
        else:
            status = f"Ready: {len(result.items)} item(s)."
        self._set_status(status)
        self._on_drop(result)

    def _set_status(self, text: str) -> None:
        if self._status is not None:
            self._status.configure(text=text)
