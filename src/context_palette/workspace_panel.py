from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Callable

from .actions import ActionError, transform_text
from .workspace_transforms import WORKSPACE_TRANSFORM_GROUPS, WorkspaceTransform


class PrefixSuffixDialog(simpledialog.Dialog):
    def body(self, master: tk.Misc) -> tk.Widget:
        ttk.Label(master, text="Prefix for every line").grid(row=0, column=0, sticky=tk.W)
        self.prefix_var = tk.StringVar()
        prefix_entry = ttk.Entry(master, textvariable=self.prefix_var, width=42)
        prefix_entry.grid(row=1, column=0, sticky=tk.EW, pady=(3, 9))
        ttk.Label(master, text="Suffix for every line").grid(row=2, column=0, sticky=tk.W)
        self.suffix_var = tk.StringVar()
        ttk.Entry(master, textvariable=self.suffix_var, width=42).grid(
            row=3,
            column=0,
            sticky=tk.EW,
            pady=(3, 0),
        )
        master.columnconfigure(0, weight=1)
        return prefix_entry

    def apply(self) -> None:
        self.result = (self.prefix_var.get(), self.suffix_var.get())


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
    ) -> None:
        self.clipboard_getter = clipboard_getter
        self.clipboard_setter = clipboard_setter
        self.status_setter = status_setter

        self.frame = ttk.Frame(parent)
        self.frame.pack(fill=tk.BOTH, expand=True)
        header = ttk.Frame(self.frame)
        header.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(
            header,
            text="Input / Output",
            style="PaneHeader.TLabel",
        ).pack(side=tk.LEFT)
        ttk.Label(
            header,
            text="Selection, clipboard, and transformation workspace",
            style="Muted.TLabel",
        ).pack(side=tk.LEFT, padx=(8, 0))

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

        self.context_menu = tk.Menu(self.text, tearoff=False)
        self._build_context_menu()
        self.transform_button = ttk.Button(
            body,
            text="⋮",
            width=3,
            command=self.show_transform_menu,
            style="Compact.TButton",
        )
        self.transform_button.pack(side=tk.RIGHT, anchor=tk.N, padx=(5, 0))
        tooltip_adder(
            self.transform_button,
            "Transform selected text, or the complete field when nothing is selected. Results are copied.",
        )

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
        if transform.prompts_for_affixes:
            return self.prefix_suffix_lines
        return lambda: self.transform(
            transform.operation,
            transform.success_message,
        )

    def get_text(self) -> str:
        return self.text.get("1.0", "end-1c").strip()

    def set_text(self, value: str) -> None:
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", value)

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
    ) -> None:
        start, end, had_selection = self._transform_range()
        source = self.text.get(start, end)
        if not source:
            self.status_setter("Input / Output is empty; nothing was transformed.")
            return
        try:
            result = transform_text(source, operation, prefix=prefix, suffix=suffix)
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
        dialog = PrefixSuffixDialog(
            self.text.winfo_toplevel(),
            title="Prefix / suffix every line",
        )
        if dialog.result is None:
            return
        prefix, suffix = dialog.result
        self.transform(
            "prefix_suffix_lines",
            "Added line prefix / suffix",
            prefix=prefix,
            suffix=suffix,
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
