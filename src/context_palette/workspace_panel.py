from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

from .actions import (
    ActionError,
    TextFileTransformPreview,
    replace_text_file_from_preview,
    save_text_file_preview_as,
    transform_text,
)
from .style import COLORS
from .ui_icons import load_ui_icons
from .window_geometry import place_child_window
from .workspace_transforms import WORKSPACE_TRANSFORM_GROUPS, WorkspaceTransform


class TextPlacementDialog:
    """Explicit Replace / Append / Cancel choice for incoming workspace text."""

    def __init__(self, parent: tk.Misc, message: str, *, title: str) -> None:
        self.result: str | None = None
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        outer = ttk.Frame(self.window, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            outer,
            text=message,
            wraplength=470,
            justify=tk.LEFT,
        ).pack(anchor=tk.W)
        ttk.Label(
            outer,
            text="Choose exactly how Input / Output should change.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(6, 12))
        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X)
        self.cancel_button = ttk.Button(
            controls,
            text="Cancel",
            command=self._cancel,
        )
        self.cancel_button.pack(side=tk.RIGHT)
        self.append_button = ttk.Button(
            controls,
            text="Append",
            command=lambda: self._choose("append"),
        )
        self.append_button.pack(side=tk.RIGHT, padx=(0, 6))
        self.replace_button = ttk.Button(
            controls,
            text="Replace",
            command=lambda: self._choose("replace"),
            style="Accent.TButton",
        )
        self.replace_button.pack(side=tk.RIGHT, padx=(0, 6))
        self.window.bind("<Escape>", lambda _event: self._cancel())
        place_child_window(self.window, parent)
        self.window.grab_set()
        self.replace_button.focus_set()

    def show(self) -> str | None:
        self.window.wait_window()
        return self.result

    def _choose(self, result: str) -> None:
        self.result = result
        self.window.destroy()

    def _cancel(self) -> None:
        self.window.destroy()


class OcrPlacementDialog(TextPlacementDialog):
    """Compatibility wrapper for the OCR-specific placement title."""

    def __init__(self, parent: tk.Misc, message: str) -> None:
        super().__init__(parent, message, title="Place extracted text")


def ask_ocr_placement(parent: tk.Misc, message: str) -> str | None:
    return OcrPlacementDialog(parent, message).show()


def ask_text_placement(parent: tk.Misc, message: str) -> str | None:
    return TextPlacementDialog(
        parent,
        message,
        title="Place dropped content",
    ).show()


class TransformParametersDialog(simpledialog.Dialog):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        transform: WorkspaceTransform,
    ) -> None:
        self.transform = transform
        self.variables: list[tk.StringVar] = []
        super().__init__(parent, title=transform.label.rstrip("…"))

    def body(self, master: tk.Misc) -> tk.Widget:
        first_entry: ttk.Entry | None = None
        for index, label in enumerate(self.transform.parameter_labels):
            ttk.Label(master, text=label).grid(
                row=index * 2,
                column=0,
                sticky=tk.W,
            )
            default = (
                self.transform.parameter_defaults[index]
                if index < len(self.transform.parameter_defaults)
                else ""
            )
            variable = tk.StringVar(value=default)
            entry = ttk.Entry(master, textvariable=variable, width=42)
            entry.grid(
                row=index * 2 + 1,
                column=0,
                sticky=tk.EW,
                pady=(3, 9 if index + 1 < len(self.transform.parameter_labels) else 0),
            )
            self.variables.append(variable)
            first_entry = first_entry or entry
        master.columnconfigure(0, weight=1)
        assert first_entry is not None
        return first_entry

    def apply(self) -> None:
        self.result = tuple(variable.get() for variable in self.variables)


class WorkspacePanel:
    """Editable Input / Output surface and its constrained text commands."""

    def __init__(
        self,
        parent: ttk.Frame,
        *,
        clipboard_getter: Callable[[], str],
        clipboard_setter: Callable[[str], None],
        status_setter: Callable[[str], None],
        tooltip_adder: Callable[[tk.Widget, str], None],
        create_action: Callable[[str], None] | None = None,
        extract_text: Callable[[str], None] | None = None,
        capture: Callable[[], None] | None = None,
        show_inbox: Callable[[], None] | None = None,
        text_change_callback: Callable[[], None] | None = None,
    ) -> None:
        self.clipboard_getter = clipboard_getter
        self.clipboard_setter = clipboard_setter
        self.status_setter = status_setter
        self.create_action = create_action
        self.extract_text = extract_text
        self.text_change_callback = text_change_callback

        self.frame = ttk.Frame(parent)
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.ui_icons = load_ui_icons(
            self.frame,
            ("capture", "inbox", "create_from_input", "ocr", "text_tools"),
            foreground=COLORS["text"],
        )
        header = ttk.Frame(self.frame)
        header.pack(fill=tk.X, pady=(0, 4))
        self.text_tools_button = ttk.Menubutton(
            header,
            image=self.ui_icons["text_tools"],
            style="Icon.TButton",
            takefocus=True,
        )
        self.text_tools_button.pack(side=tk.RIGHT)
        self.ocr_button = ttk.Button(
            header,
            image=self.ui_icons["ocr"],
            command=self._extract_text,
            state=tk.NORMAL if extract_text is not None else tk.DISABLED,
            style="Icon.TButton",
        )
        self.ocr_button.pack(side=tk.RIGHT, padx=(0, 4))
        self.create_action_button = ttk.Button(
            header,
            image=self.ui_icons["create_from_input"],
            command=self._create_action,
            state=tk.DISABLED,
            style="Icon.TButton",
        )
        self.create_action_button.pack(side=tk.RIGHT, padx=(0, 4))
        self.inbox_button = ttk.Button(
            header,
            image=self.ui_icons["inbox"],
            command=show_inbox,
            state=tk.NORMAL if show_inbox is not None else tk.DISABLED,
            style="Icon.TButton",
        )
        self.inbox_button.pack(side=tk.RIGHT, padx=(0, 4))
        self.capture_button = ttk.Button(
            header,
            image=self.ui_icons["capture"],
            command=capture,
            state=tk.NORMAL if capture is not None else tk.DISABLED,
            style="Icon.TButton",
        )
        self.capture_button.pack(side=tk.RIGHT, padx=(0, 4))

        self.file_preview: TextFileTransformPreview | None = None
        self.file_preview_frame = ttk.Frame(self.frame)
        self.file_preview_path_var = tk.StringVar()
        ttk.Label(
            self.file_preview_frame,
            textvariable=self.file_preview_path_var,
            style="Muted.TLabel",
            wraplength=430,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            self.file_preview_frame,
            text="Replace original…",
            command=self.replace_preview_source,
        ).pack(side=tk.RIGHT)
        ttk.Button(
            self.file_preview_frame,
            text="Save as…",
            command=self.save_preview_as,
        ).pack(side=tk.RIGHT, padx=(0, 6))
        ttk.Button(
            self.file_preview_frame,
            text="Dismiss",
            command=self.clear_file_preview,
            style="Compact.TButton",
        ).pack(side=tk.RIGHT, padx=(0, 6))

        body = ttk.Frame(self.frame)
        body.pack(fill=tk.BOTH, expand=True)
        self.text = tk.Text(
            body,
            height=8,
            wrap=tk.WORD,
            undo=True,
            font=("Consolas", 10),
            borderwidth=1,
            relief=tk.SOLID,
            padx=7,
            pady=6,
        )
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.text.bind("<Control-a>", self.select_all)
        self.text.bind("<Control-A>", self.select_all)
        self.text.bind("<Button-3>", self.show_context_menu)
        self.text.bind("<<Modified>>", self._on_text_modified, add="+")
        self.text.edit_modified(False)

        self.context_menu = tk.Menu(self.text, tearoff=False)
        self._build_context_menu()
        self.text_tools_button.configure(menu=self.transform_menu)
        # Compatibility alias for launcher integrations that used the former
        # symbol-only transform control.
        self.transform_button = self.text_tools_button
        tooltip_adder(
            self.text_tools_button,
            "Text tools — Transform selected text, or the complete field when nothing is selected. Results are copied.",
        )
        tooltip_adder(
            self.ocr_button,
            (
                "Extract text — Read text from a selected image file or clipboard image. "
                "Processing stays on this computer."
            ),
        )
        tooltip_adder(
            self.create_action_button,
            (
                "Create from Input — Prefill a reviewed Action from one clear website, file, folder, "
                "or application in Input / Output."
            ),
        )
        tooltip_adder(
            self.capture_button,
            "Capture — Save current clipboard text to Inbox after asking for a title.",
        )
        tooltip_adder(
            self.inbox_button,
            "Inbox — Review captures and convert them into permanent Actions.",
        )

    def _on_text_modified(self, _event: tk.Event) -> None:
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        self._sync_create_action_state()
        if self.text_change_callback is not None:
            self.text_change_callback()

    def _sync_create_action_state(self) -> None:
        self.create_action_button.configure(
            state=(
                tk.NORMAL
                if self.create_action is not None and self.raw_text().strip()
                else tk.DISABLED
            )
        )

    def selected_or_full_text(self) -> str:
        """Return a non-blank selection first, otherwise the complete field."""

        try:
            selected = self.text.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            selected = ""
        return selected if selected.strip() else self.raw_text()

    def _create_action(self) -> None:
        if self.create_action is not None:
            self.create_action(self.selected_or_full_text())

    def _extract_text(self) -> None:
        if self.extract_text is not None:
            self.extract_text(self.selected_or_full_text())

    def set_ocr_running(self, running: bool) -> None:
        self.ocr_button.configure(
            state=(
                tk.DISABLED
                if running or self.extract_text is None
                else tk.NORMAL
            )
        )

    def apply_ocr_text(
        self,
        value: str,
        *,
        source_label: str,
        expected_text: str,
    ) -> str | None:
        """Place an OCR result as one undoable edit without overwriting silently."""

        if not value.strip():
            return None
        current = self.raw_text()
        placement = "replace"
        if current:
            changed_note = (
                "\n\nInput / Output changed while extraction was running."
                if current != expected_text
                else ""
            )
            placement = ask_ocr_placement(
                self.text.winfo_toplevel(),
                f"Text was extracted from {source_label}.{changed_note}\n\n"
                "Replace discards the current Input / Output text. Append keeps "
                "it and adds the extracted text below.",
            )
            if placement is None:
                return None

        return self._apply_text_placement(value, placement, current)

    def apply_incoming_text(
        self,
        value: str,
        *,
        source_label: str,
    ) -> str | None:
        """Place dropped text without reading or changing the clipboard."""

        if not value.strip():
            return None
        current = self.raw_text()
        placement = "replace"
        if current:
            placement = ask_text_placement(
                self.text.winfo_toplevel(),
                f"Content was received from {source_label}.\n\n"
                "Replace discards the current Input / Output text. Append keeps "
                "it and adds the dropped content below.",
            )
            if placement is None:
                return None

        return self._apply_text_placement(value, placement, current)

    def _apply_text_placement(
        self,
        value: str,
        placement: str,
        current: str,
    ) -> str:
        """Apply one already-approved incoming value as one undoable edit."""

        self.clear_file_preview()
        self.text.edit_separator()
        if placement == "replace":
            self.text.delete("1.0", tk.END)
            self.text.insert("1.0", value)
        else:
            separator = "" if current.endswith(("\n", "\r")) else "\n\n"
            self.text.insert("end-1c", f"{separator}{value}")
        self.text.edit_separator()
        self._sync_create_action_state()
        return placement

    def _build_context_menu(self) -> None:
        for label, event_name in (
            ("Undo", "<<Undo>>"),
            ("Redo", "<<Redo>>"),
        ):
            self.context_menu.add_command(
                label=label,
                command=lambda event=event_name: self.text.event_generate(event),
            )
        self.context_menu.add_separator()
        for label, event_name in (
            ("Cut", "<<Cut>>"),
            ("Copy", "<<Copy>>"),
            ("Paste", "<<Paste>>"),
        ):
            self.context_menu.add_command(
                label=label,
                command=lambda event=event_name: self.text.event_generate(event),
            )
        self.context_menu.add_command(label="Select all", command=self.select_all)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Copy all", command=self.copy_all)
        self.context_menu.add_command(
            label="Replace with clipboard",
            command=self.replace_with_clipboard,
        )
        self.context_menu.add_command(label="Clear", command=lambda: self.set_text(""))

        self.transform_menu = tk.Menu(self.context_menu, tearoff=False)
        for group in WORKSPACE_TRANSFORM_GROUPS:
            group_menu = tk.Menu(self.transform_menu, tearoff=False)
            for transform in group.transforms:
                group_menu.add_command(
                    label=transform.label,
                    command=self._transform_command(transform),
                )
            self.transform_menu.add_cascade(label=group.label, menu=group_menu)
        self.context_menu.add_cascade(label="Transform", menu=self.transform_menu)

    def _transform_command(
        self,
        transform: WorkspaceTransform,
    ) -> Callable[[], None]:
        if transform.parameter_labels:
            return lambda: self.prompted_transform(transform)
        return lambda: self.transform(
            transform.operation,
            transform.success_message,
        )

    def get_text(self) -> str:
        return self.text.get("1.0", "end-1c").strip()

    def set_text(self, value: str) -> None:
        self.clear_file_preview()
        self._replace_text(value)

    def _replace_text(self, value: str) -> None:
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", value)
        self._sync_create_action_state()

    def show_file_preview(self, preview: TextFileTransformPreview) -> None:
        self.file_preview = preview
        self._replace_text(preview.result)
        self.file_preview_path_var.set(
            f"Preview from {preview.source_path} — original unchanged"
        )
        if not self.file_preview_frame.winfo_manager():
            self.file_preview_frame.pack(
                fill=tk.X,
                pady=(0, 5),
                before=self.text.master,
            )

    def clear_file_preview(self) -> None:
        self.file_preview = None
        if self.file_preview_frame.winfo_manager():
            self.file_preview_frame.pack_forget()
        self.file_preview_path_var.set("")

    def replace_preview_source(self) -> None:
        preview = self.file_preview
        if preview is None:
            return
        if not messagebox.askyesno(
            "Replace original text file?",
            "Replace the original file with the current Input / Output text?\n\n"
            f"{preview.source_path}\n\n"
            "Context Palette will refuse if another program changed the file "
            "after this preview was created.",
            parent=self.text.winfo_toplevel(),
        ):
            return
        try:
            self.file_preview = replace_text_file_from_preview(
                preview,
                self.raw_text(),
            )
        except ActionError as exc:
            messagebox.showerror(
                "Original file was not replaced",
                str(exc),
                parent=self.text.winfo_toplevel(),
            )
            return
        self.file_preview_path_var.set(
            f"Saved to {preview.source_path} — preview is current"
        )
        self.status_setter(f"Replaced original text file: {preview.source_path}")

    def save_preview_as(self) -> None:
        preview = self.file_preview
        if preview is None:
            return
        selected = filedialog.asksaveasfilename(
            parent=self.text.winfo_toplevel(),
            title="Save transformed text as",
            initialdir=str(preview.source_path.parent),
            initialfile=preview.source_path.name,
            confirmoverwrite=True,
            filetypes=(
                ("Text files", "*.txt *.csv *.tsv *.json *.md *.xml *.sql *.log"),
                ("All files", "*.*"),
            ),
        )
        if not selected:
            return
        try:
            updated_preview = save_text_file_preview_as(
                preview,
                Path(selected),
                self.raw_text(),
            )
        except ActionError as exc:
            messagebox.showerror(
                "Transformed text was not saved",
                str(exc),
                parent=self.text.winfo_toplevel(),
            )
            return
        if updated_preview is not None:
            self.file_preview = updated_preview
            self.file_preview_path_var.set(
                f"Saved to {preview.source_path} — preview is current"
            )
        self.status_setter(f"Saved transformed text as: {selected}")

    def raw_text(self) -> str:
        return self.text.get("1.0", "end-1c")

    def select_all(self, _event: tk.Event | None = None) -> str:
        self.text.tag_add(tk.SEL, "1.0", "end-1c")
        self.text.mark_set(tk.INSERT, "1.0")
        self.text.see(tk.INSERT)
        return "break"

    def show_context_menu(self, event: tk.Event) -> str:
        self.text.focus_set()
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()
        return "break"

    def show_transform_menu(self) -> None:
        self.text.focus_set()
        try:
            self.transform_menu.tk_popup(
                self.transform_button.winfo_rootx(),
                self.transform_button.winfo_rooty()
                + self.transform_button.winfo_height(),
            )
        finally:
            self.transform_menu.grab_release()

    def _transform_range(self) -> tuple[str, str, bool]:
        try:
            return self.text.index(tk.SEL_FIRST), self.text.index(tk.SEL_LAST), True
        except tk.TclError:
            return "1.0", "end-1c", False

    def transform(
        self,
        operation: str,
        description: str,
        *,
        prefix: str = "",
        suffix: str = "",
        arguments: tuple[str, ...] = (),
    ) -> None:
        start, end, had_selection = self._transform_range()
        source = self.text.get(start, end)
        if not source:
            self.status_setter("Input / Output is empty; nothing was transformed.")
            return
        try:
            result = transform_text(
                source,
                operation,
                prefix=prefix,
                suffix=suffix,
                arguments=arguments,
            )
        except ActionError as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.text.winfo_toplevel())
            return
        self.text.edit_separator()
        self.text.replace(start, end, result)
        self.text.edit_separator()
        result_end = self.text.index(f"{start}+{len(result)}c")
        self.text.mark_set(tk.INSERT, result_end)
        if had_selection:
            self.text.tag_add(tk.SEL, start, result_end)
        self.clipboard_setter(result)
        scope = "selection" if had_selection else "complete field"
        self.status_setter(f"{description} in {scope}; result copied to clipboard.")

    def prefix_suffix_lines(self) -> None:
        transform = next(
            item
            for group in WORKSPACE_TRANSFORM_GROUPS
            for item in group.transforms
            if item.operation == "prefix_suffix_lines"
        )
        self.prompted_transform(transform)

    def prompted_transform(self, transform: WorkspaceTransform) -> None:
        dialog = TransformParametersDialog(
            self.text.winfo_toplevel(),
            transform=transform,
        )
        if dialog.result is None:
            return
        arguments = tuple(dialog.result)
        if transform.operation == "prefix_suffix_lines":
            prefix, suffix = arguments
            self.transform(
                transform.operation,
                transform.success_message,
                prefix=prefix,
                suffix=suffix,
            )
            return
        self.transform(
            transform.operation,
            transform.success_message,
            arguments=arguments,
        )

    def replace_with_clipboard(self) -> None:
        try:
            self.set_text(self.clipboard_getter())
            self.status_setter("Pasted clipboard text into Input / Output")
        except tk.TclError:
            messagebox.showerror(
                "Context Palette",
                "The clipboard does not contain text.",
                parent=self.text.winfo_toplevel(),
            )

    def sync_from_clipboard(self) -> None:
        try:
            value = self.clipboard_getter()
        except tk.TclError:
            return
        self.set_text(value)

    def copy_all(self) -> None:
        value = self.get_text()
        if not value:
            self.status_setter("Input / Output is empty; nothing was copied.")
            return
        self.clipboard_setter(value)
        self.status_setter("Copied Input / Output to the clipboard.")
