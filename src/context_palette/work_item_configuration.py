from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Callable
import weakref

from .work_items import DiscoveredWorkItem, WorkItemDiscoveryError, WorkItemSource
from .work_item_creation import (
    WorkItemCreationError,
    create_work_item_from_template,
    suggest_work_item_name,
    validate_work_item_name,
)
from .work_item_refresh import WorkItemIndex, WorkItemRefreshCoordinator
from .work_item_storage import (
    WorkItemMetadata,
    WorkItemCreationSettings,
    WorkItemStorageError,
    load_work_item_creation_settings,
    save_work_item_creation_settings,
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
        settings_path: Path,
        on_change: Callable[[], None],
        feedback: Callable[[str, bool], None],
    ) -> None:
        self.parent = parent
        self.sources = list(sources)
        self.metadata = dict(metadata)
        self.index = index
        self.sources_path = sources_path
        self.metadata_path = metadata_path
        self.settings_path = settings_path
        self.on_change = on_change
        self.feedback = feedback
        self.refresh_coordinator = WorkItemRefreshCoordinator()
        self.refresh_pending = False
        self.disposed = False
        parent.bind("<Destroy>", self._handle_destroy, add="+")

        try:
            self.creation_settings = load_work_item_creation_settings(settings_path)
        except WorkItemStorageError:
            self.creation_settings = WorkItemCreationSettings()

        template_row = ttk.Frame(parent)
        template_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(template_row, text="Generic Excel template").pack(side=tk.LEFT)
        self.template_var = tk.StringVar(
            value=str(self.creation_settings.template_path or "")
        )
        self.template_entry = ttk.Entry(template_row, textvariable=self.template_var)
        self.template_entry.pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 6)
        )
        ttk.Button(template_row, text="Browse…", command=self.choose_template).pack(side=tk.LEFT)
        ttk.Button(template_row, text="Save", command=self.save_template).pack(side=tk.LEFT, padx=(6, 0))

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
        self.add_source_button = ttk.Button(
            source_controls,
            text="Add source",
            command=self.add_source,
        )
        self.add_source_button.pack(side=tk.LEFT)
        self.create_button = ttk.Button(
            source_controls,
            text="Create Work Item",
            command=self.create_work_item,
            style="Accent.TButton",
        )
        self.create_button.pack(side=tk.LEFT, padx=(6, 0))
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

    def choose_template(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.parent,
            title="Choose the generic Work Item template",
            filetypes=(("Excel workbooks", "*.xlsx"),),
        )
        if selected:
            self.template_var.set(selected)

    def save_template(self) -> bool:
        raw_path = self.template_var.get().strip()
        template = Path(raw_path) if raw_path else None
        if template is not None and (
            not template.is_absolute()
            or not template.is_file()
            or template.suffix.casefold() != ".xlsx"
        ):
            messagebox.showerror(
                "Work Items",
                "Choose an existing .xlsx generic template.",
                parent=self.parent,
            )
            self.template_entry.focus_set()
            return False
        settings = WorkItemCreationSettings(template)
        try:
            save_work_item_creation_settings(self.settings_path, settings)
        except (OSError, WorkItemStorageError) as exc:
            messagebox.showerror("Work Items", str(exc), parent=self.parent)
            return False
        self.creation_settings = settings
        self.feedback("Saved the generic Work Item template.", True)
        return True

    def create_work_item(self) -> None:
        if not self.sources:
            self.feedback("Add a Work Item source before creating an item.", False)
            self.add_source_button.focus_set()
            return
        if not self.template_var.get().strip():
            self.feedback(
                "Choose a generic Excel template before creating a Work Item.",
                False,
            )
            self.template_entry.focus_set()
            return
        if not self.save_template() or self.creation_settings.template_path is None:
            return
        CreateWorkItemDialog(
            self.parent.winfo_toplevel(),
            tuple(self.sources),
            self.creation_settings.template_path,
            self._created_work_item,
        )

    def _created_work_item(
        self,
        source: WorkItemSource,
        final_name: str,
        tags: tuple[str, ...],
    ) -> bool:
        try:
            created = create_work_item_from_template(
                source,
                final_name,
                self.creation_settings.template_path,
            )
        except WorkItemCreationError as exc:
            messagebox.showerror("Work Item could not be created", str(exc), parent=self.parent)
            return False
        key = work_item_metadata_key(source.id, created.folder_path.name)
        if tags:
            updated = dict(self.metadata)
            updated[key] = WorkItemMetadata(tags)
            try:
                save_work_item_metadata(self.metadata_path, updated)
            except (OSError, WorkItemStorageError) as exc:
                messagebox.showwarning(
                    "Work Item created without tags",
                    f"The folder and workbook were created, but tags could not be saved.\n\n{exc}",
                    parent=self.parent,
                )
            else:
                self.metadata = updated
        self.select_after_refresh = key
        self.feedback(f'Created Work Item “{created.folder_path.name}”. Refreshing…', True)
        self.on_change()
        self._start_refresh()
        return True

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
        pending_selection = getattr(self, "select_after_refresh", None)
        if pending_selection:
            self.select_after_refresh = None
            self.select_item(pending_selection)


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


class CreateWorkItemDialog:
    KIND_CHOICES = ("ISS", "CAS", "TRCK", "QST", "PRJ")

    def __init__(
        self,
        parent: tk.Misc,
        sources: tuple[WorkItemSource, ...],
        template_path: Path,
        on_create: Callable[[WorkItemSource, str, tuple[str, ...]], bool],
    ) -> None:
        self.sources = sources
        self.on_create = on_create
        self.previous_suggestion = ""
        self.window = tk.Toplevel(parent)
        self.window.title("Create Work Item")
        self.window.transient(parent)
        self.window.grab_set()
        outer = ttk.Frame(self.window, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)
        self.source_labels = {
            f"{source.name} ({source.id})": source for source in sources
        }
        self.source_name = tk.StringVar(value=next(iter(self.source_labels)))
        self.kind = tk.StringVar(value="ISS")
        self.organisation = tk.StringVar()
        self.subject = tk.StringVar()
        self.project_code = tk.StringVar()
        self.suggestion = tk.StringVar()
        self.final_name = tk.StringVar()
        self.tags = tk.StringVar()
        source_names = tuple(self.source_labels)
        self._combo(outer, "Source", self.source_name, source_names)
        self._combo(outer, "Kind", self.kind, self.KIND_CHOICES)
        self._entry(outer, "Organisation", self.organisation)
        self.subject_entry = self._entry(outer, "Subject", self.subject)
        self._entry(outer, "Project code (optional)", self.project_code)
        self._readonly(outer, "Suggested name", self.suggestion)
        self._entry(outer, "Final Work Item name", self.final_name)
        self._entry(outer, "Personal tags (optional)", self.tags)
        self.preview = tk.StringVar()
        ttk.Label(outer, textvariable=self.preview, style="Muted.TLabel", wraplength=650).pack(anchor=tk.W, pady=(8, 8))
        ttk.Label(outer, text=f"Template: {template_path}", style="Muted.TLabel", wraplength=650).pack(anchor=tk.W)
        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(controls, text="Create Work Item", command=self._create, style="Accent.TButton").pack(side=tk.RIGHT)
        ttk.Button(controls, text="Cancel", command=self.window.destroy).pack(side=tk.RIGHT, padx=(0, 6))
        for variable in (self.kind, self.organisation, self.subject, self.project_code, self.source_name):
            variable.trace_add("write", self._update_suggestion)
        self.final_name.trace_add("write", self._update_preview)
        self._update_suggestion()
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.after_idle(self.subject_entry.focus_set)

    def _row(self, parent: ttk.Frame, label: str) -> ttk.Frame:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=label, width=24).pack(side=tk.LEFT)
        return row

    def _entry(self, parent: ttk.Frame, label: str, variable: tk.StringVar) -> ttk.Entry:
        row = self._row(parent, label)
        entry = ttk.Entry(row, textvariable=variable)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return entry

    def _combo(self, parent: ttk.Frame, label: str, variable: tk.StringVar, values: tuple[str, ...]) -> None:
        row = self._row(parent, label)
        ttk.Combobox(row, textvariable=variable, values=values, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _readonly(self, parent: ttk.Frame, label: str, variable: tk.StringVar) -> None:
        row = self._row(parent, label)
        ttk.Entry(row, textvariable=variable, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _selected_source(self) -> WorkItemSource:
        return self.source_labels[self.source_name.get()]

    def _update_suggestion(self, *_args: object) -> None:
        suggestion = suggest_work_item_name(
            self.kind.get(), self.organisation.get(), self.subject.get(), self.project_code.get()
        )
        current_final = self.final_name.get()
        self.suggestion.set(suggestion)
        if not current_final or current_final == self.previous_suggestion:
            self.final_name.set(suggestion)
        self.previous_suggestion = suggestion
        self._update_preview()

    def _update_preview(self, *_args: object) -> None:
        source = self._selected_source()
        name = self.final_name.get().strip() or "<final-name>"
        folder = source.workitems_path / name
        self.preview.set(f"Folder: {folder}\nWorkbook: {folder / (name + '.xlsx')}")

    def _create(self) -> None:
        try:
            name = validate_work_item_name(self.final_name.get())
        except WorkItemCreationError as exc:
            messagebox.showerror("Work Items", str(exc), parent=self.window)
            return
        source = self._selected_source()
        folder = source.workitems_path / name
        if not messagebox.askyesno(
            "Create Work Item?",
            f"Create folder:\n{folder}\n\nCreate workbook:\n{folder / (name + '.xlsx')}",
            parent=self.window,
        ):
            return
        tags = tuple(dict.fromkeys(" ".join(value.strip().split()).casefold() for value in self.tags.get().split(",") if value.strip()))
        if self.on_create(source, name, tags):
            self.window.destroy()


def _stable_source_id(label: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", label.strip().casefold()).strip("-")
