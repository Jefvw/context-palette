from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from .actions import (
    Action,
    ActionError,
    append_action,
    append_actions,
    build_url,
    build_url_action,
    copy_text_action,
    validate_context_memberships,
)
from .ai_guidance_window import AIGuidanceWindow
from .context_membership_field import ContextMembershipField, TagSelectionField
from .inbox import InboxError, InboxItem, load_inbox_items, update_inbox_item_state
from .style import COLORS
from .window_geometry import configure_standard_window


def suggest_url_template(value: str) -> str:
    current = value.strip()
    if not current or "{id}" in current or "{id_url}" in current:
        return current
    if current.startswith(("http://", "https://")):
        separator = "" if current.endswith("/") else "/"
        return current + separator + "{id_url}"
    return current


class InboxWindow:
    def __init__(
        self,
        parent: tk.Tk,
        items: list[InboxItem],
        actions: list[Action],
        focus_context: str,
        context_names: list[str],
        actions_path: Path,
        inbox_path: Path,
        on_change: Callable[[], None],
        on_harvest: Callable[[], None] | None = None,
    ) -> None:
        self.items = items
        self.actions = actions
        self.focus_context = focus_context
        self.context_names = context_names
        self.actions_path = actions_path
        self.inbox_path = inbox_path
        self.on_change = on_change
        self.on_harvest = on_harvest
        self.window = tk.Toplevel(parent)
        self.window.title("Context Palette Inbox")
        configure_standard_window(self.window)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(outer)
        controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        self.convert_button = ttk.Button(
            controls,
            text="Create action",
            command=self._convert_selected,
            style="Accent.TButton",
        )
        self.convert_button.pack(side=tk.LEFT)
        self.ai_button = ttk.Button(controls, text="Ask AI", command=self._ask_ai_for_selected)
        self.ai_button.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            controls,
            text="Harvest documents…",
            command=self.on_harvest or (lambda: None),
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            controls,
            text="Close",
            command=self.window.destroy,
            style="Compact.TButton",
        ).pack(side=tk.RIGHT)

        ttk.Label(outer, text="Capture Inbox", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            outer,
            text=f"{len(items)} captured item{'s' if len(items) != 1 else ''} · turn useful material into an action",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(2, 8))

        self.listbox = tk.Listbox(outer, activestyle="dotbox", height=8)
        self.listbox.pack(fill=tk.BOTH, expand=True, pady=(4, 8))
        self.listbox.bind("<<ListboxSelect>>", lambda _event: self._update_preview())

        ttk.Label(outer, text="Preview").pack(anchor=tk.W)
        self.preview = tk.Text(outer, height=8, wrap=tk.WORD)
        self.preview.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.preview.configure(state=tk.DISABLED)

        self._load_items()

    def _load_items(self) -> None:
        self.listbox.delete(0, tk.END)
        for item in self.items:
            self.listbox.insert(tk.END, f"{item.title} ({item.created_at})")
        if self.items:
            self.listbox.selection_set(0)
            self.listbox.activate(0)
            self.convert_button.configure(state=tk.NORMAL)
            self.ai_button.configure(state=tk.NORMAL)
        else:
            self.listbox.insert(
                tk.END,
                "Inbox is empty — use Capture in the main palette to save clipboard text.",
            )
            self.listbox.itemconfigure(0, foreground=COLORS["muted_text"])
            self.convert_button.configure(state=tk.DISABLED)
            self.ai_button.configure(state=tk.DISABLED)
        self._update_preview()

    def _update_preview(self) -> None:
        item = self._selected_item()
        if item is None:
            text = "No Inbox items yet."
        else:
            text = (
                f"Title: {item.title}\n"
                f"State: {item.state}\n"
                f"Source: {item.source}\n"
                f"Created: {item.created_at}\n"
                f"Suggested context: {item.suggested_context or '(none)'}\n\n"
                f"{item.content}"
            )

        self.preview.configure(state=tk.NORMAL)
        self.preview.delete("1.0", tk.END)
        self.preview.insert("1.0", text)
        self.preview.configure(state=tk.DISABLED)

    def _selected_item(self) -> InboxItem | None:
        selected = self.listbox.curselection()
        if not selected:
            return None
        index = selected[0]
        if index >= len(self.items):
            return None
        return self.items[index]

    def _convert_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            return

        ActionCreator(
            self.window,
            item,
            self.actions,
            item.suggested_context or self.focus_context,
            self.context_names,
            self._save_created_action,
        )

    def _ask_ai_for_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        contexts = {
            context
            for action in self.actions
            for context in action.effective_contexts
        }
        contexts.update((self.focus_context, item.suggested_context, "General"))
        AIGuidanceWindow(
            self.window,
            item,
            contexts,
            self._save_ai_actions,
        )

    def _save_ai_actions(self, item: InboxItem, actions: list[Action]) -> None:
        try:
            append_actions(self.actions_path, actions)
            update_inbox_item_state(self.inbox_path, item.id, "Converted")
            self.items = load_inbox_items(self.inbox_path)
            self._load_items()
            self.on_change()
            messagebox.showinfo(
                "Context Palette",
                f"Created {len(actions)} permanent local action(s).",
                parent=self.window,
            )
        except (ActionError, InboxError) as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.window)

    def _save_created_action(self, item: InboxItem, action: Action) -> None:
        try:
            append_action(self.actions_path, action)
            update_inbox_item_state(self.inbox_path, item.id, "Converted")
            self.items = load_inbox_items(self.inbox_path)
            self._load_items()
            self.on_change()
        except (ActionError, InboxError) as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.window)


class ActionCreator:
    ACTION_TYPES = {
        "Copy captured text": "copy_text",
        "Build URL — open from selected or copied ID": "build_url_selection_open",
        "Build URL — copy only and ask for input": "build_url_copy",
        "Build URL — open only and ask for input": "build_url_open",
    }

    def __init__(
        self,
        parent: tk.Toplevel,
        item: InboxItem,
        actions: list[Action],
        initial_context: str,
        context_names: list[str],
        on_save: Callable[[InboxItem, Action], None],
    ) -> None:
        self.item = item
        self.on_save = on_save
        self.context_names = tuple(context_names)
        self.window = tk.Toplevel(parent)
        self.window.title("Create Action")
        configure_standard_window(self.window)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())

        tags = sorted(
            {tag for action in actions for tag in action.effective_tags},
            key=str.casefold,
        )
        self.tags_var = tk.StringVar()
        self.contexts_var = tk.StringVar(
            value="" if initial_context.casefold() == "general" else initial_context
        )
        self.title_var = tk.StringVar(value=item.title)
        self.description_var = tk.StringVar()
        self.action_type_var = tk.StringVar(value="Copy captured text")
        self.guidance_var = tk.StringVar()
        self.example_var = tk.StringVar()

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(outer)
        controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        ttk.Button(controls, text="Create action", command=self._save).pack(side=tk.LEFT)
        ttk.Button(controls, text="Cancel", command=self.window.destroy).pack(side=tk.RIGHT)

        form = ttk.Frame(outer)
        form.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        ttk.Label(
            form,
            text="What should this action do?",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            form,
            text="Choose the result first; the fields below adapt to that choice.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(1, 6))
        type_field = ttk.Combobox(
            form,
            textvariable=self.action_type_var,
            values=list(self.ACTION_TYPES),
            state="readonly",
        )
        type_field.pack(fill=tk.X)
        type_field.bind("<<ComboboxSelected>>", lambda _event: self._action_type_changed())

        metadata = ttk.Frame(form)
        metadata.pack(fill=tk.X, pady=(6, 0))
        left = ttk.Frame(metadata)
        left.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        right = ttk.Frame(metadata)
        right.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.context_field = ContextMembershipField(
            left,
            self.contexts_var,
            self.context_names,
            label="Specific contexts",
        )
        self.tag_field = TagSelectionField(
            right,
            self.tags_var,
            tags,
        )

        ttk.Label(right, text="Short name").pack(anchor=tk.W, pady=(8, 0))
        title_entry = ttk.Entry(right, textvariable=self.title_var)
        title_entry.pack(fill=tk.X, pady=(3, 0))

        ttk.Label(
            form,
            text="Description (optional; searchable, not shown in the action list)",
        ).pack(anchor=tk.W, pady=(8, 0))
        ttk.Entry(form, textvariable=self.description_var).pack(
            fill=tk.X,
            pady=(3, 0),
        )

        self.content_label = ttk.Label(form, text="Captured text to copy")
        self.content_label.pack(anchor=tk.W, pady=(8, 0))
        self.content = tk.Text(form, height=7, wrap=tk.WORD, undo=True)
        self.content.pack(fill=tk.BOTH, expand=True, pady=(3, 0))
        self.content.insert("1.0", item.content)
        self.content.bind("<KeyRelease>", lambda _event: self._update_example())

        ttk.Label(form, textvariable=self.guidance_var, style="Muted.TLabel", wraplength=620).pack(
            anchor=tk.W, pady=(6, 0)
        )
        ttk.Label(form, textvariable=self.example_var, wraplength=620).pack(anchor=tk.W, pady=(4, 0))

        self.path_var = tk.StringVar()
        ttk.Label(form, textvariable=self.path_var).pack(anchor=tk.W, pady=(6, 0))
        for variable in (self.tags_var, self.contexts_var, self.title_var):
            variable.trace_add("write", lambda *_args: self._update_path())

        self._update_path()
        self._action_type_changed()
        self.window.transient(parent)
        self.window.grab_set()
        title_entry.focus_set()
        title_entry.selection_range(0, tk.END)

    def _field(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        values: list[str],
    ) -> None:
        ttk.Label(parent, text=label).pack(anchor=tk.W, pady=(8, 0))
        ttk.Combobox(parent, textvariable=variable, values=values).pack(fill=tk.X, pady=(3, 0))

    def _update_path(self) -> None:
        parts = [
            value.strip()
            for value in (
                self.contexts_var.get() or "General",
                self.tags_var.get(),
                self.title_var.get(),
            )
            if value.strip()
        ]
        self.path_var.set("Displayed as: " + " > ".join(parts))

    def _action_type_changed(self) -> None:
        action_type = self.ACTION_TYPES[self.action_type_var.get()]
        if action_type == "copy_text":
            self.content_label.configure(text="Captured text to copy")
            self.guidance_var.set("The Inbox capture becomes the reusable text produced by this action.")
        else:
            self.content_label.configure(text="URL template")
            self.guidance_var.set(
                "Keep the stable base URL from Inbox and put {id_url} where the runtime ID belongs. "
                "This action reads the selected text first, then falls back to copied text. "
                "Example: https://domain-product.atlassian.net/browse/{id_url}"
            )
            current = self.content.get("1.0", "end-1c")
            suggested = suggest_url_template(current)
            if suggested != current.strip():
                self.content.delete("1.0", tk.END)
                self.content.insert("1.0", suggested)
        self._update_example()

    def _update_example(self) -> None:
        action_type = self.ACTION_TYPES[self.action_type_var.get()]
        if action_type == "copy_text":
            self.example_var.set("Result: copies the text above.")
            return
        template = self.content.get("1.0", "end-1c").strip()
        try:
            example = build_url(template, "ABC 123")
            effect = "copy and open" if action_type == "build_url_selection_open" else (
                "copy" if action_type == "build_url_copy" else "open"
            )
            self.example_var.set(f"Example input: ABC 123  →  {example}\nEffect: {effect}")
        except ActionError as exc:
            self.example_var.set(f"Template needs attention: {exc}")

    def _save(self) -> None:
        try:
            action_type = self.ACTION_TYPES[self.action_type_var.get()]
            contexts = validate_context_memberships(
                (
                    part.strip()
                    for part in self.contexts_var.get().split(",")
                    if part.strip()
                ),
                self.context_names,
            )
            common = {
                "title": self.title_var.get(),
                "description": self.description_var.get(),
                "context": "General",
                "contexts": contexts,
                "tags": tuple(
                    part.strip()
                    for part in self.tags_var.get().split(",")
                    if part.strip()
                ),
            }
            if action_type == "copy_text":
                action = copy_text_action(
                    **common,
                    value=self.content.get("1.0", "end-1c"),
                )
            else:
                action = build_url_action(
                    **common,
                    template=self.content.get("1.0", "end-1c"),
                    action_type=action_type,
                )
        except ActionError as exc:
            messagebox.showerror("Context Palette", str(exc), parent=self.window)
            return
        self.on_save(self.item, action)
        self.window.destroy()
