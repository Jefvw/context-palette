from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Iterable

from .searchable_selection import SearchableSelectionPopup


def specific_context_names(contexts: Iterable[str]) -> tuple[str, ...]:
    """Return distinct canonical context names suitable for guided selection."""
    names_by_key: dict[str, str] = {}
    for context in contexts:
        clean = context.strip()
        key = clean.casefold()
        if clean and key != "general":
            names_by_key.setdefault(key, clean)
    return tuple(sorted(names_by_key.values(), key=str.casefold))


def reusable_tag_names(tags: Iterable[str]) -> tuple[str, ...]:
    """Return distinct existing tags suitable for optional guided selection."""
    names_by_key: dict[str, str] = {}
    for tag in tags:
        clean = " ".join(tag.strip().split()).casefold()
        if clean:
            names_by_key.setdefault(clean, clean)
    return tuple(sorted(names_by_key.values(), key=str.casefold))


class CommaSeparatedPickerField:
    """Editable comma-separated values with an optional checklist picker."""

    def __init__(
        self,
        parent: tk.Misc,
        variable: tk.StringVar,
        names: Iterable[str],
        *,
        label: str,
        empty_text: str,
        mnemonic: str,
        searchable: bool = False,
        inline: bool = False,
        label_width: int = 0,
    ) -> None:
        self.variable = variable
        self.names = tuple(names)
        self.mnemonic = mnemonic.casefold()
        self.searchable = searchable
        self.selected_vars: dict[str, tk.BooleanVar] = {}
        self._syncing = False

        self.frame = ttk.Frame(parent)
        self.frame.pack(fill=tk.X, pady=(5 if inline else 8, 0))
        mnemonic_index = label.casefold().find(mnemonic.casefold())
        self.label = ttk.Label(
            self.frame,
            text=label,
            underline=mnemonic_index,
            width=label_width,
        )

        self.row = ttk.Frame(self.frame)
        if inline:
            self.label.pack(side=tk.LEFT, anchor=tk.W, padx=(0, 8))
            self.row.pack(side=tk.LEFT, fill=tk.X, expand=True)
        else:
            self.label.pack(anchor=tk.W)
            self.row.pack(fill=tk.X, pady=(3, 0))
        self.entry = ttk.Entry(self.row, textvariable=variable)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        picker_class = ttk.Button if searchable else ttk.Menubutton
        self.picker = picker_class(
            self.row,
            text="Choose…",
            style="Compact.TButton",
        )
        self.picker.pack(side=tk.RIGHT, padx=(5, 0))
        self.menu: tk.Menu | None = None
        if not searchable:
            self.menu = tk.Menu(self.picker, tearoff=False)
            self.picker.configure(menu=self.menu)
        else:
            self.picker.configure(command=self._show_searchable_picker)

        if self.names and not searchable:
            assert self.menu is not None
            for name in self.names:
                selected = tk.BooleanVar(value=False)
                self.selected_vars[name] = selected
                self.menu.add_checkbutton(
                    label=name,
                    variable=selected,
                    command=lambda selected_name=name: self._selection_changed(selected_name),
                )
        elif not searchable:
            assert self.menu is not None
            self.menu.add_command(label=empty_text, state=tk.DISABLED)
            self.picker.configure(state=tk.DISABLED)
        elif not self.names:
            self.picker.configure(state=tk.DISABLED)

        self.label.bind("<Button-1>", self._focus_entry)
        self.entry.bind("<Alt-Down>", self._post_picker)
        self.entry.bind("<F4>", self._post_picker)
        self.picker.bind("<Alt-Down>", self._post_picker)
        self.picker.bind("<F4>", self._post_picker)
        self.frame.winfo_toplevel().bind(
            "<KeyPress>",
            self._handle_mnemonic_keypress,
            add="+",
        )
        self.variable.trace_add("write", self._text_changed)
        self._sync_checks()

    def _focus_entry(self, _event: tk.Event | None = None) -> str:
        self.entry.focus_set()
        return "break"

    def _handle_mnemonic_keypress(self, event: tk.Event) -> str | None:
        state = int(getattr(event, "state", 0) or 0)
        if not state & 0x20000 or state & 0x0004:
            return None
        if str(getattr(event, "keysym", "")).casefold() != self.mnemonic:
            return None
        return self._focus_entry(event)

    def _post_picker(self, _event: tk.Event | None = None) -> str:
        if str(self.picker.cget("state")) == tk.DISABLED:
            return "break"
        if self.searchable:
            self._show_searchable_picker()
            return "break"
        self.picker.tk.call("ttk::menubutton::Post", self.picker)
        return "break"

    def _show_searchable_picker(self) -> None:
        """Override in searchable fields that supply a selection callback."""

    def _text_changed(self, *_args: object) -> None:
        self._sync_checks()

    def _sync_checks(self) -> None:
        if self._syncing:
            return
        selected_keys = {
            part.strip().casefold()
            for part in self.variable.get().split(",")
            if part.strip()
        }
        self._syncing = True
        try:
            for name, variable in self.selected_vars.items():
                variable.set(name.casefold() in selected_keys)
        finally:
            self._syncing = False

    def _selection_changed(self, name: str) -> None:
        if self._syncing:
            return
        parts = [
            part.strip()
            for part in self.variable.get().split(",")
            if part.strip()
        ]
        key = name.casefold()
        parts = [part for part in parts if part.casefold() != key]
        if self.selected_vars[name].get():
            parts.append(name)
        self.variable.set(", ".join(parts))


class ContextMembershipField(CommaSeparatedPickerField):
    """Editable context memberships with a checklist of defined contexts."""

    def __init__(
        self,
        parent: tk.Misc,
        variable: tk.StringVar,
        context_names: Iterable[str],
        *,
        label: str = "Specific contexts",
        inline: bool = False,
        label_width: int = 0,
    ) -> None:
        names = specific_context_names(context_names)
        self.context_names = names
        super().__init__(
            parent,
            variable,
            names,
            label=label,
            empty_text="No specific contexts defined",
            mnemonic="c",
            inline=inline,
            label_width=label_width,
        )


class TagSelectionField(CommaSeparatedPickerField):
    """Free-form tag entry with a checklist of tags already in use."""

    def __init__(
        self,
        parent: tk.Misc,
        variable: tk.StringVar,
        tags: Iterable[str],
        *,
        label: str = "Tags (optional)",
        inline: bool = False,
        label_width: int = 0,
    ) -> None:
        names = reusable_tag_names(tags)
        self.tag_names = names
        super().__init__(
            parent,
            variable,
            names,
            label=label,
            empty_text="No existing tags",
            mnemonic="t",
            searchable=True,
            inline=inline,
            label_width=label_width,
        )

    def _show_searchable_picker(self) -> None:
        existing = getattr(self, "tag_picker", None)
        if existing is not None and existing.window.winfo_exists():
            existing.window.lift()
            existing.search_entry.focus_set()
            return
        selected = {
            part.strip().casefold()
            for part in self.variable.get().split(",")
            if part.strip()
        }
        self.tag_picker = SearchableSelectionPopup(
            self.picker,
            self.tag_names,
            selected=selected,
            multiple=True,
            on_select=self._replace_selected_tags,
            title="Choose tags",
        )

    def _replace_selected_tags(self, selected: tuple[str, ...]) -> None:
        selected_keys = {tag.casefold() for tag in selected}
        known_keys = {tag.casefold() for tag in self.tag_names}
        typed = [
            part.strip()
            for part in self.variable.get().split(",")
            if part.strip() and part.strip().casefold() not in known_keys
        ]
        typed.extend(tag for tag in self.tag_names if tag.casefold() in selected_keys)
        self.variable.set(", ".join(typed))
