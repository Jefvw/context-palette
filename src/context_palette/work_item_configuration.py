from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Callable
import weakref

from .work_items import DiscoveredWorkItem, WorkItemDiscoveryError, WorkItemSource
from .work_item_refresh import WorkItemIndex, WorkItemRefreshCoordinator
from .work_item_storage import (
    WorkItemMetadata,
    WorkItemStorageError,
    save_work_item_metadata,
    save_work_item_sources,
    work_item_metadata_key,
)


class WorkItemsConfigurationPanel:
    def __init__(
        self,
        parent: ttk.Frame,
        *,
        sources: tuple[WorkItemSource, ...],
        metadata: dict[str, WorkItemMetadata],
        index: WorkItemIndex,
        sources_path: Path,
        metadata_path: Path,
        on_change: Callable[[], None],
        feedback: Callable[[str, bool], None],
    ) -> None:
        self.parent = parent
        self.sources = list(sources)
        self.metadata = dict(metadata)
        self.index = index
        self.sources_path = sources_path
        self.metadata_path = metadata_path
        self.on_change = on_change
        self.feedback = feedback
        self.refresh_coordinator = WorkItemRefreshCoordinator()
        self.refresh_pending = False
        self.disposed = False
        parent.bind("<Destroy>", self._handle_destroy, add="+")

        ttk.Label(
            parent,
            text="Sources are stored only on this computer. Missing folders remain configured so they can recover later.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 6))
        self.source_tree = ttk.Treeview(
            parent,
            columns=("folder", "state"),
            show="tree headings",
            selectmode="browse",
            height=6,
        )
        self.source_tree.heading("#0", text="Source")
        self.source_tree.heading("folder", text="Workitems folder")
        self.source_tree.heading("state", text="State")
        self.source_tree.column("#0", width=170)
        self.source_tree.column("folder", width=430)
        self.source_tree.column("state", width=100, stretch=False)
        self.source_tree.pack(fill=tk.X)
        self.source_tree.bind("<Double-1>", lambda _event: self.edit_source())
        self.source_tree.bind("<Return>", lambda _event: self.edit_source())
        self.source_tree.bind("<Insert>", lambda _event: self._add_source_from_key())
        self.source_tree.bind("<Delete>", lambda _event: self._remove_source_from_key())
        self.source_tree.bind("<F5>", lambda _event: self._refresh_from_key())
        self.source_tree.bind("<F6>", self._focus_other_list)

        source_controls = ttk.Frame(parent)
        source_controls.pack(fill=tk.X, pady=(6, 10))
        ttk.Button(source_controls, text="Add source", command=self.add_source).pack(side=tk.LEFT)
        ttk.Button(source_controls, text="Edit selected", command=self.edit_source).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(source_controls, text="Remove selected", command=self.remove_source).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(source_controls, text="Refresh index", command=self.refresh).pack(side=tk.RIGHT)

        ttk.Label(parent, text="Discovered Work Items", style="Heading.TLabel").pack(anchor=tk.W)
        self.item_tree = ttk.Treeview(
            parent,
            columns=("source", "projects", "tags", "opens"),
            show="tree headings",
            selectmode="browse",
        )
        for column, label, width in (
            ("#0", "Work Item", 270),
            ("source", "Source", 140),
            ("projects", "Projects", 110),
            ("tags", "Personal tags", 160),
            ("opens", "Default", 80),
        ):
            self.item_tree.heading(column, text=label)
            self.item_tree.column(column, width=width, stretch=column in {"#0", "tags"})
        self.item_tree.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.item_tree.bind("<Double-1>", lambda _event: self.edit_tags())
        self.item_tree.bind("<Return>", lambda _event: self.edit_tags())
        self.item_tree.bind("<F5>", lambda _event: self._refresh_from_key())
        self.item_tree.bind("<F6>", self._focus_other_list)
        item_controls = ttk.Frame(parent)
        item_controls.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(item_controls, text="Edit personal tags", command=self.edit_tags).pack(side=tk.LEFT)
        self.summary_var = tk.StringVar()
        ttk.Label(item_controls, textvariable=self.summary_var, style="Muted.TLabel").pack(side=tk.RIGHT)
        self.render()

    def focus(self) -> None:
        self.source_tree.focus_set()

    def _focus_other_list(self, event: tk.Event) -> str:
        target = self.item_tree if event.widget == self.source_tree else self.source_tree
        target.focus_set()
        return "break"

    def _add_source_from_key(self) -> str:
        self.add_source()
        return "break"

    def _remove_source_from_key(self) -> str:
        self.remove_source()
        return "break"

    def _refresh_from_key(self) -> str:
        self.refresh()
        return "break"

    def _handle_destroy(self, event: tk.Event) -> None:
        if event.widget == self.parent:
            self.disposed = True

    def select_item(self, key: str) -> None:
        if self.item_tree.exists(key):
            self.item_tree.selection_set(key)
            self.item_tree.focus(key)
            self.item_tree.see(key)
            self.item_tree.focus_set()

    def render(self) -> None:
        self.source_tree.delete(*self.source_tree.get_children())
        source_states = {result.source.id: result for result in self.index.sources}
        for source in self.sources:
            result = source_states.get(source.id)
            if result is not None and result.error:
                state = "Unavailable"
            elif not source.workitems_path.is_dir():
                state = "Missing"
            elif result is None:
                state = "Not refreshed"
            else:
                state = "Ready"
            self.source_tree.insert("", tk.END, iid=source.id, text=source.name, values=(str(source.workitems_path), state))

        self.item_tree.delete(*self.item_tree.get_children())
        workbook_count = 0
        for item in self.index.items:
            key = work_item_metadata_key(item.source_id, item.relative_folder)
            tags = self.metadata.get(key, WorkItemMetadata()).tags
            opens = "Workbook" if item.matching_workbook_path else "Folder"
            workbook_count += item.matching_workbook_path is not None
            self.item_tree.insert(
                "",
                tk.END,
                iid=key,
                text=item.display_name,
                values=(item.source_name, ", ".join(item.project_codes) or "—", ", ".join(tags) or "—", opens),
            )
        count = len(self.index.items)
        self.summary_var.set(f"{count} items · {workbook_count} workbooks · {count - workbook_count} folder fallbacks")

    def add_source(self) -> None:
        SourceDialog(
            self.parent.winfo_toplevel(),
            None,
            lambda source: self._save_source(source, original_id=None),
        )

    def edit_source(self) -> None:
        selected = self.source_tree.selection()
        if not selected:
            self.feedback("Select a Work Item source first.", False)
            return
        source = next(item for item in self.sources if item.id == selected[0])
        SourceDialog(
            self.parent.winfo_toplevel(),
            source,
            lambda updated: self._save_source(updated, original_id=source.id),
        )

    def _save_source(self, source: WorkItemSource, *, original_id: str | None) -> bool:
        if any(
            item.id.casefold() == source.id.casefold() and item.id != original_id
            for item in self.sources
        ):
            messagebox.showerror("Work Items", "That source ID is already in use.", parent=self.parent)
            return False
        updated = [source if item.id == source.id else item for item in self.sources]
        if not any(item.id == source.id for item in self.sources):
            updated.append(source)
        try:
            save_work_item_sources(self.sources_path, tuple(updated))
        except (OSError, WorkItemStorageError) as exc:
            messagebox.showerror("Work Items", str(exc), parent=self.parent)
            return False
        self.sources = updated
        self._prune_index()
        self.feedback(f'Saved Work Item source “{source.name}”. Refreshing…', True)
        self.on_change()
        self.render()
        self._start_refresh()
        return True

    def remove_source(self) -> None:
        selected = self.source_tree.selection()
        if not selected:
            self.feedback("Select a Work Item source first.", False)
            return
        source_id = selected[0]
        source = next(item for item in self.sources if item.id == source_id)
        if not messagebox.askyesno(
            "Remove Work Item source?",
            f'Remove “{source.name}” from Context Palette?\n\nNo folders or files will be deleted.',
            parent=self.parent,
        ):
            return
        remaining = tuple(item for item in self.sources if item.id != source_id)
        try:
            save_work_item_sources(self.sources_path, remaining)
        except (OSError, WorkItemStorageError) as exc:
            messagebox.showerror("Work Items", str(exc), parent=self.parent)
            return
        self.sources = list(remaining)
        self._prune_index()
        self.feedback(
            f'Removed Work Item source “{source.name}”. Its private tags were retained for reuse.',
            True,
        )
        self.on_change()
        self.render()
        self._start_refresh()

    def edit_tags(self) -> None:
        selected = self.item_tree.selection()
        if not selected:
            self.feedback("Select a discovered Work Item first.", False)
            return
        key = selected[0]
        item = next(
            candidate
            for candidate in self.index.items
            if work_item_metadata_key(candidate.source_id, candidate.relative_folder) == key
        )
        TagDialog(
            self.parent.winfo_toplevel(),
            item,
            self.metadata.get(key, WorkItemMetadata()).tags,
            lambda tags: self._save_tags(key, tags),
        )

    def _save_tags(self, key: str, tags: tuple[str, ...]) -> bool:
        updated = dict(self.metadata)
        if tags:
            updated[key] = WorkItemMetadata(tags)
        else:
            updated.pop(key, None)
        try:
            save_work_item_metadata(self.metadata_path, updated)
        except (OSError, WorkItemStorageError) as exc:
            messagebox.showerror("Work Items", str(exc), parent=self.parent)
            return False
        self.metadata = updated
        self.feedback("Saved personal Work Item tags.", True)
        self.on_change()
        self.render()
        return True

    def refresh(self) -> None:
        self.on_change()
        self._start_refresh()

    def _prune_index(self) -> None:
        source_ids = {source.id.casefold() for source in self.sources}
        self.index = WorkItemIndex(
            tuple(
                result
                for result in self.index.sources
                if result.source.id.casefold() in source_ids
            ),
            self.index.elapsed_seconds,
        )

    def _start_refresh(self) -> None:
        if getattr(self, "disposed", False):
            return
        if not self.sources:
            self.index = WorkItemIndex()
            self.render()
            return
        panel_reference = weakref.ref(self)

        def accept_if_open(index: WorkItemIndex) -> None:
            panel = panel_reference()
            if panel is not None and not panel.disposed:
                panel._accept_refresh(index)

        if not self.refresh_coordinator.start(
            tuple(self.sources),
            self.index,
            accept_if_open,
        ):
            self.refresh_pending = True
            self.feedback("A Work Items refresh is already running; the latest changes are queued.", True)
            return
        self.feedback("Refreshing Work Items in the background…", True)
        self.parent.after(100, self._poll_refresh)

    def _poll_refresh(self) -> None:
        if self.disposed:
            return
        try:
            completed = self.refresh_coordinator.drain()
            if not completed:
                self.parent.after(100, self._poll_refresh)
        except tk.TclError:
            return

    def _accept_refresh(self, index: WorkItemIndex) -> None:
        self.index = index
        self._prune_index()
        if self.refresh_pending:
            self.refresh_pending = False
            self.render()
            self.parent.after_idle(self._start_refresh)
            return
        unavailable = sum(result.error is not None for result in self.index.sources)
        if unavailable:
            self.feedback(f"Refresh completed; {unavailable} source(s) are unavailable. Previous results were kept where possible.", False)
        else:
            self.feedback(f"Refresh completed: {len(self.index.items)} Work Items found.", True)
        self.render()


class SourceDialog:
    def __init__(self, parent: tk.Misc, source: WorkItemSource | None, on_save: Callable[[WorkItemSource], bool]) -> None:
        self.source = source
        self.on_save = on_save
        self.window = tk.Toplevel(parent)
        self.window.title("Edit Work Item source" if source else "Add Work Item source")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.resizable(True, False)
        outer = ttk.Frame(self.window, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)
        self.name = tk.StringVar(value=source.name if source else "")
        self.path = tk.StringVar(value=str(source.workitems_path) if source else "")
        self.source_id = tk.StringVar(value=source.id if source else "")
        self.name_entry = self._field(outer, "Source name", self.name)
        path_row = ttk.Frame(outer)
        path_row.pack(fill=tk.X, pady=4)
        ttk.Label(path_row, text="Workitems folder", width=18).pack(side=tk.LEFT)
        ttk.Entry(path_row, textvariable=self.path).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(path_row, text="Browse…", command=self._browse).pack(side=tk.LEFT, padx=(6, 0))
        id_entry = self._field(outer, "Stable source ID", self.source_id)
        if source:
            id_entry.configure(state="readonly")
        ttk.Label(outer, text="Choose the folder named workitems. The ID is local and remains stable for tags.", style="Muted.TLabel").pack(anchor=tk.W, pady=(4, 8))
        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X)
        ttk.Button(controls, text="Save source", command=self._save, style="Accent.TButton").pack(side=tk.RIGHT)
        ttk.Button(controls, text="Cancel", command=self.window.destroy).pack(side=tk.RIGHT, padx=(0, 6))
        self.name.trace_add("write", self._suggest_id)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.bind("<Return>", lambda _event: self._save())
        self.window.after_idle(self.name_entry.focus_set)

    def _field(self, parent: ttk.Frame, label: str, variable: tk.StringVar) -> ttk.Entry:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text=label, width=18).pack(side=tk.LEFT)
        entry = ttk.Entry(row, textvariable=variable)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return entry

    def _suggest_id(self, *_args: object) -> None:
        if self.source is None:
            self.source_id.set(_stable_source_id(self.name.get()))

    def _browse(self) -> None:
        selected = filedialog.askdirectory(parent=self.window, title="Choose the workitems folder")
        if selected:
            self.path.set(selected)

    def _save(self) -> None:
        folder = Path(self.path.get().strip())
        if not folder.is_absolute() or not folder.is_dir():
            messagebox.showerror("Work Items", "Choose an existing workitems folder.", parent=self.window)
            return
        if folder.name.casefold() != "workitems":
            messagebox.showerror(
                "Work Items",
                'Choose the folder named "workitems", not its parent folder.',
                parent=self.window,
            )
            return
        try:
            source = WorkItemSource(self.source_id.get(), self.name.get(), folder)
        except WorkItemDiscoveryError as exc:
            messagebox.showerror("Work Items", str(exc), parent=self.window)
            return
        if self.on_save(source):
            self.window.destroy()


class TagDialog:
    def __init__(self, parent: tk.Misc, item: DiscoveredWorkItem, tags: tuple[str, ...], on_save: Callable[[tuple[str, ...]], bool]) -> None:
        self.on_save = on_save
        self.window = tk.Toplevel(parent)
        self.window.title("Edit Work Item tags")
        self.window.transient(parent)
        self.window.grab_set()
        outer = ttk.Frame(self.window, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)
        ttk.Label(outer, text=item.display_name, style="Heading.TLabel").pack(anchor=tk.W)
        ttk.Label(outer, text=f"{item.source_name} · Projects: {', '.join(item.project_codes) or 'none'}", style="Muted.TLabel").pack(anchor=tk.W, pady=(2, 10))
        ttk.Label(outer, text="Personal tags (comma-separated)").pack(anchor=tk.W)
        self.tags = tk.StringVar(value=", ".join(tags))
        entry = ttk.Entry(outer, textvariable=self.tags, width=60)
        entry.pack(fill=tk.X, pady=(3, 10))
        ttk.Label(outer, text="Tags stay in Context Palette; the Work Item folder is not modified.", style="Muted.TLabel").pack(anchor=tk.W, pady=(0, 8))
        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X)
        ttk.Button(controls, text="Save tags", command=self._save, style="Accent.TButton").pack(side=tk.RIGHT)
        ttk.Button(controls, text="Cancel", command=self.window.destroy).pack(side=tk.RIGHT, padx=(0, 6))
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.bind("<Return>", lambda _event: self._save())
        entry.focus_set()

    def _save(self) -> None:
        tags = tuple(dict.fromkeys(" ".join(value.strip().split()).casefold() for value in self.tags.get().split(",") if value.strip()))
        if self.on_save(tags):
            self.window.destroy()


def _stable_source_id(label: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", label.strip().casefold()).strip("-")
