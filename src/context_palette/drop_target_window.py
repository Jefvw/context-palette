"""Optional, small Toplevel drop surface owned by an existing Tk root."""

from __future__ import annotations

from collections import Counter
import logging
import ntpath
import tkinter as tk
from tkinter import ttk
from typing import Callable
from urllib.parse import urlparse

from .drop_adapter import (
    DropResolutionCoordinator,
    DropResult,
    decode_drop_values,
)
from .window_geometry import (
    fit_window_size,
    main_window_monitor_work_area,
    window_monitor_work_area,
)


DROP_COPY_ACTION = "copy"
DROP_REFUSE_ACTION = "refuse_drop"
DROP_HISTORY_LIMIT = 10
DROP_DETAILS_ITEM_LIMIT = 64
DROP_DETAILS_CHARACTER_LIMIT = 32_768


LOGGER = logging.getLogger("context_palette.drop_target")
DROP_COMPONENT_UNAVAILABLE = (
    "The Windows drag-and-drop component could not be loaded."
)
DROP_WINDOW_UNAVAILABLE = "The drop target window could not be initialized."


def drop_result_summary(result: DropResult) -> str:
    """Return a compact, privacy-conscious description of one useful drop."""

    if not result.items:
        return "No supported items"
    if len(result.items) == 1:
        item = result.items[0]
        if item.kind == "path":
            name = ntpath.basename(item.value.rstrip("\\/")) or item.value
            summary = f"Path: {name}"
        elif item.kind == "url":
            summary = f"Web link: {urlparse(item.value).hostname or 'link'}"
        else:
            character_label = "character" if len(item.value) == 1 else "characters"
            summary = f"Text: {len(item.value)} {character_label}"
    else:
        counts = Counter(item.kind for item in result.items)
        labels = (
            ("path", "path", "paths"),
            ("url", "web link", "web links"),
            ("text", "text", "text items"),
        )
        parts = [
            f"{counts[kind]} {singular if counts[kind] == 1 else plural}"
            for kind, singular, plural in labels
            if counts[kind]
        ]
        summary = f"{len(result.items)} items: {', '.join(parts)}"
    if result.warnings:
        warning_label = "warning" if len(result.warnings) == 1 else "warnings"
        summary += f" - {len(result.warnings)} {warning_label}"
    return summary


def drop_result_details(result: DropResult) -> str:
    """Render a bounded preview of explicitly requested prepared content."""

    item_count = len(result.items)
    item_label = "item" if item_count == 1 else "items"
    lines = [f"What will be sent to Input / Output ({item_count} {item_label})"]
    for index, item in enumerate(result.items[:DROP_DETAILS_ITEM_LIMIT], start=1):
        lines.append("")
        if item.kind == "text":
            line_count = item.value.count("\n") + 1
            line_label = "line" if line_count == 1 else "lines"
            label = (
                f"Text - {len(item.value)} characters, "
                f"{line_count} {line_label}"
            )
        else:
            label = {"path": "Path", "url": "Web link"}[item.kind]
        lines.extend((f"{index}. {label}", item.value))
    hidden_items = item_count - min(item_count, DROP_DETAILS_ITEM_LIMIT)
    if hidden_items:
        lines.extend(
            (
                "",
                f"... {hidden_items} more items are retained and will be sent.",
            )
        )
    if result.warnings:
        lines.extend(("", "Warnings"))
        lines.extend(f"- {warning.message}" for warning in result.warnings)
    content = "\n".join(lines)
    if len(content) > DROP_DETAILS_CHARACTER_LIMIT:
        content = content[:DROP_DETAILS_CHARACTER_LIMIT].rstrip()
        content += (
            "\n\n... Preview truncated. The complete prepared content is retained "
            "and will be sent."
        )
    return content


def _load_tk_dnd() -> object:
    from tkinterdnd2 import TkinterDnD

    return TkinterDnD


class DropTargetWindow:
    """A lazily created drop surface with bounded, session-only history."""

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
        self._history_var: tk.StringVar | None = None
        self.previous_button: ttk.Button | None = None
        self.history_label: ttk.Label | None = None
        self.next_button: ttk.Button | None = None
        self.send_again_button: ttk.Button | None = None
        self.details_button: ttk.Button | None = None
        self.hide_button: ttk.Button | None = None
        self._details_frame: ttk.Frame | None = None
        self._details_text: tk.Text | None = None
        self._details_visible = False
        self._drop_history: list[DropResult] = []
        self._history_index = -1
        self._dnd_available: bool | None = None
        self.unavailable_reason: str | None = None
        self._polling = False

    def start(self) -> bool:
        if not self._ensure_dnd():
            return False
        if self.window is None or not self.window.winfo_exists():
            try:
                self._create_window()
            except Exception:
                LOGGER.exception("Drop target window initialization failed")
                self._mark_unavailable(DROP_WINDOW_UNAVAILABLE)
                self._destroy_partial_window()
                return False
        return True

    def show(self) -> bool:
        if not self.start():
            return False
        assert self.window is not None
        try:
            self.window.deiconify()
            self.window.lift()
        except Exception:
            LOGGER.exception("Drop target window could not be shown")
            self._mark_unavailable(DROP_WINDOW_UNAVAILABLE)
            self._destroy_partial_window()
            return False
        return True

    def hide(self) -> None:
        self._set_details_visible(False)
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
            LOGGER.exception("Windows drag-and-drop component failed to load")
            self._mark_unavailable(DROP_COMPONENT_UNAVAILABLE)
            return False
        self._dnd_available = True
        self.unavailable_reason = None
        return True

    def _mark_unavailable(self, reason: str) -> None:
        self._dnd_available = False
        self.unavailable_reason = reason

    def _destroy_partial_window(self) -> None:
        window = self.window
        try:
            if window is not None and window.winfo_exists():
                window.destroy()
        except Exception:
            LOGGER.exception("Partial drop target cleanup failed")
        finally:
            self.window = None
            self._status = None
            self._history_var = None
            self.previous_button = None
            self.history_label = None
            self.next_button = None
            self.send_again_button = None
            self.details_button = None
            self.hide_button = None
            self._details_frame = None
            self._details_text = None
            self._details_visible = False

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

        history = ttk.Frame(frame)
        history.grid(row=2, sticky="ew", pady=(0, 8))
        history.columnconfigure(1, weight=1, minsize=230)
        self.previous_button = ttk.Button(
            history,
            text="Previous",
            command=lambda: self._move_history(-1),
        )
        self.previous_button.grid(row=0, column=0)
        self._history_var = tk.StringVar(master=window)
        self.history_label = ttk.Label(
            history,
            textvariable=self._history_var,
            anchor=tk.CENTER,
            justify=tk.CENTER,
            wraplength=230,
        )
        self.history_label.grid(row=0, column=1, padx=8, sticky="ew")
        self.next_button = ttk.Button(
            history,
            text="Next",
            command=lambda: self._move_history(1),
        )
        self.next_button.grid(row=0, column=2)

        self._details_frame = ttk.Frame(frame)
        self._details_frame.grid(row=3, sticky="nsew", pady=(0, 8))
        self._details_frame.columnconfigure(0, weight=1)
        self._details_frame.rowconfigure(1, weight=1)
        ttk.Label(self._details_frame, text="Prepared content details").grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 4),
        )
        details_text = tk.Text(
            self._details_frame,
            width=54,
            height=9,
            wrap=tk.WORD,
            undo=False,
            takefocus=True,
        )
        self._details_text = details_text
        details_text.grid(row=1, column=0, sticky="nsew")
        vertical_scrollbar = ttk.Scrollbar(
            self._details_frame,
            orient=tk.VERTICAL,
            command=details_text.yview,
        )
        vertical_scrollbar.grid(row=1, column=1, sticky="ns")
        details_text.configure(yscrollcommand=vertical_scrollbar.set)
        self._details_frame.grid_remove()

        footer = ttk.Frame(frame)
        footer.grid(row=4, sticky="ew")
        self.send_again_button = ttk.Button(
            footer,
            text="Send again",
            command=self._send_again,
        )
        self.send_again_button.pack(side=tk.LEFT)
        self.details_button = ttk.Button(
            footer,
            text="Show details",
            command=self._toggle_details,
        )
        self.details_button.pack(side=tk.LEFT, padx=(8, 0))
        self.hide_button = ttk.Button(footer, text="Hide", command=self.hide)
        self.hide_button.pack(side=tk.RIGHT)
        self._sync_history_controls()
        window.drop_target_register("DND_Files", "DND_Text")
        window.dnd_bind("<<Drop:DND_Files>>", self._handle_files_drop)
        window.dnd_bind("<<Drop:DND_Text>>", self._handle_text_drop)
        window.update_idletasks()
        self._position_lower_right(window)
        window.deiconify()

    def _position_lower_right(self, window: tk.Toplevel) -> None:
        work_area = main_window_monitor_work_area(self.root)
        width, height = fit_window_size(
            (window.winfo_reqwidth(), window.winfo_reqheight()),
            work_area,
        )
        left, top, right, bottom = work_area
        x = max(left, min(right - width - 24, right - width))
        y = max(top, min(bottom - height - 24, bottom - height))
        window.geometry(f"{width}x{height}{x:+d}{y:+d}")

    def _bottom_right_anchor(self) -> tuple[int, int] | None:
        if (
            self.window is None
            or not self.window.winfo_exists()
            or self.window.state() == "withdrawn"
        ):
            return None
        self.window.update_idletasks()
        side_frame, top_frame = self._window_frame_offsets()
        return (
            self.window.winfo_x() + self.window.winfo_width() + (2 * side_frame),
            self.window.winfo_y() + self.window.winfo_height() + top_frame + side_frame,
        )

    def _window_origin(self) -> tuple[int, int] | None:
        if (
            self.window is None
            or not self.window.winfo_exists()
            or self.window.state() == "withdrawn"
        ):
            return None
        return self.window.winfo_x(), self.window.winfo_y()

    def _window_frame_offsets(self) -> tuple[int, int]:
        if self.window is None:
            return 0, 0
        side_frame = max(0, self.window.winfo_rootx() - self.window.winfo_x())
        top_frame = max(0, self.window.winfo_rooty() - self.window.winfo_y())
        return side_frame, top_frame

    def _fit_window_to_monitor(
        self,
        *,
        anchor: tuple[int, int] | None = None,
        origin: tuple[int, int] | None = None,
    ) -> None:
        if (
            (anchor is None and origin is None)
            or self.window is None
            or not self.window.winfo_exists()
        ):
            return
        self.window.update_idletasks()
        work_area = window_monitor_work_area(self.window)
        side_frame, top_frame = self._window_frame_offsets()
        left, top, right, bottom = work_area
        maximum_client_size = (
            max(1, right - left - (2 * side_frame)),
            max(1, bottom - top - top_frame - side_frame),
        )
        width = min(self.window.winfo_reqwidth(), maximum_client_size[0])
        height = min(self.window.winfo_reqheight(), maximum_client_size[1])
        outer_width = width + (2 * side_frame)
        outer_height = height + top_frame + side_frame
        if anchor is not None:
            requested_x = anchor[0] - outer_width
            requested_y = anchor[1] - outer_height
        else:
            assert origin is not None
            requested_x, requested_y = origin
        x = max(left, min(requested_x, right - outer_width))
        y = max(top, min(requested_y, bottom - outer_height))
        self.window.geometry(f"{width}x{height}{x:+d}{y:+d}")

    def _handle_files_drop(self, event: object) -> str:
        return self._handle_drop(event, "DND_Files")

    def _handle_text_drop(self, event: object) -> str:
        return self._handle_drop(event, "DND_Text")

    def _handle_drop(self, event: object, drop_type: str) -> str:
        self._set_details_visible(False)
        values, error = decode_drop_values(event, drop_type)
        if error is not None:
            self._complete(DropResult(error=error))
            return DROP_REFUSE_ACTION
        if not self._coordinator.start(values or ()):
            self._set_status("Still preparing the previous drop.")
            return DROP_REFUSE_ACTION
        self._set_status("Preparing drop...")
        self._polling = True
        self._sync_history_controls()
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
            self._remember_drop(result)
        self._set_status(status)
        self._sync_history_controls()
        self._on_drop(result)

    def _remember_drop(self, result: DropResult) -> None:
        self._drop_history.append(result)
        if len(self._drop_history) > DROP_HISTORY_LIMIT:
            del self._drop_history[: len(self._drop_history) - DROP_HISTORY_LIMIT]
        self._history_index = len(self._drop_history) - 1

    def _move_history(self, offset: int) -> None:
        if self._polling:
            return
        destination = self._history_index + offset
        if not 0 <= destination < len(self._drop_history):
            return
        self._history_index = destination
        self._sync_history_controls()

    def _send_again(self) -> None:
        if self._polling or not 0 <= self._history_index < len(self._drop_history):
            return
        self._on_drop(self._drop_history[self._history_index])

    def _toggle_details(self) -> None:
        if self._polling or not 0 <= self._history_index < len(self._drop_history):
            return
        self._set_details_visible(not self._details_visible)

    def _set_details_visible(self, visible: bool) -> None:
        anchor = self._bottom_right_anchor()
        self._details_visible = visible
        if self._details_frame is not None:
            if self._details_visible:
                self._details_frame.grid()
            else:
                self._details_frame.grid_remove()
        if self.details_button is not None:
            self.details_button.configure(
                text="Hide details" if self._details_visible else "Show details"
            )
        self._update_details()
        self._fit_window_to_monitor(anchor=anchor)

    def _update_details(self) -> None:
        if self._details_text is None:
            return
        content = ""
        if 0 <= self._history_index < len(self._drop_history):
            content = drop_result_details(self._drop_history[self._history_index])
        self._details_text.configure(state=tk.NORMAL)
        self._details_text.delete("1.0", tk.END)
        self._details_text.insert("1.0", content)
        self._details_text.configure(state=tk.DISABLED)
        self._details_text.yview_moveto(0.0)

    def _sync_history_controls(self) -> None:
        origin = self._window_origin()
        count = len(self._drop_history)
        if self._history_var is not None:
            if count:
                result = self._drop_history[self._history_index]
                self._history_var.set(
                    f"Drop {self._history_index + 1} of {count} - "
                    f"{drop_result_summary(result)}"
                )
            else:
                self._history_var.set("No recent drops")
        if self._details_visible:
            self._update_details()

        busy = self._polling
        if self.previous_button is not None:
            self.previous_button.configure(
                state=(
                    tk.NORMAL
                    if not busy and self._history_index > 0
                    else tk.DISABLED
                )
            )
        if self.next_button is not None:
            self.next_button.configure(
                state=(
                    tk.NORMAL
                    if not busy and 0 <= self._history_index < count - 1
                    else tk.DISABLED
                )
            )
        if self.send_again_button is not None:
            self.send_again_button.configure(
                state=(tk.NORMAL if not busy and count else tk.DISABLED)
            )
        if self.details_button is not None:
            self.details_button.configure(
                state=(tk.NORMAL if not busy and count else tk.DISABLED)
            )
        self._fit_window_to_monitor(origin=origin)

    def _set_status(self, text: str) -> None:
        origin = self._window_origin()
        if self._status is not None:
            self._status.configure(text=text)
        self._fit_window_to_monitor(origin=origin)
