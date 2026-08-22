from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Callable
import weakref

from .configuration_data import save_contexts
from .context_membership_field import ContextMembershipField
from .contexts import (
    ContextDefinition,
    ContextError,
    update_work_item_context_memberships,
)
from .persistence import atomic_replace_bytes
from .work_items import (
    DiscoveredWorkItem,
    WorkItemDiscoveryError,
    WorkItemReference,
    WorkItemSource,
)
from .work_item_creation import (
    WorkItemCreationError,
    create_work_item_from_template,
    suggest_work_item_name,
    validate_work_item_name,
)
from .work_item_refresh import WorkItemIndex, WorkItemRefreshCoordinator
from .work_item_organization import (
    WorkItemOrganizationError,
    WorkItemOrganizationReport,
    forget_work_item_organization,
    inspect_work_item_organization,
)
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
from .treeview_utils import scrollable_tree
from .window_geometry import place_child_window


def work_item_organization_summary(report: WorkItemOrganizationReport) -> str:
    """Describe exactly which personal Palette records Forget will remove."""

    parts: list[str] = []
    if report.metadata_entries_removed:
        parts.append(
            f"{report.metadata_entries_removed} personal tag record(s)"
        )
    if report.context_memberships_removed:
        parts.append(
            f"membership in {report.context_memberships_removed} Context(s)"
        )
    if report.preferred_references_removed:
        parts.append(
            f"{report.preferred_references_removed} preferred Context placement(s)"
        )
    if report.palette_references_removed:
        parts.append(
            f"{report.palette_references_removed} context slot placement(s)"
        )
    if report.quick_action_references_removed:
        parts.append(
            f"{report.quick_action_references_removed} Quick-menu placement(s)"
        )
    if report.quick_action_items_removed:
        parts.append(
            f"{report.quick_action_items_removed} newly empty Quick-menu item(s)"
        )
    return "\n".join(f"- {part}" for part in parts)


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
        contexts_path: Path,
        on_change: Callable[[], None],
        feedback: Callable[[str, bool], None],
        refresh_configuration: Callable[[], None] | None = None,
        palette_path: Path | None = None,
        command_surface_path: Path | None = None,
    ) -> None:
        self.parent = parent
        self.sources = list(sources)
        self.metadata = dict(metadata)
        self.index = index
        self.sources_path = sources_path
        self.metadata_path = metadata_path
        self.settings_path = settings_path
        self.contexts_path = contexts_path
        self.palette_path = Path(palette_path) if palette_path is not None else None
        self.command_surface_path = (
            Path(command_surface_path)
            if command_surface_path is not None
            else None
        )
        self.contexts: list[ContextDefinition] = []
        self.on_change = on_change
        self.feedback = feedback
        self.refresh_configuration = refresh_configuration
        self.refresh_coordinator = WorkItemRefreshCoordinator()
        self.refresh_pending = False
        self.disposed = False
        parent.bind("<Destroy>", self._handle_destroy, add="+")

        try:
            self.creation_settings = load_work_item_creation_settings(settings_path)
        except WorkItemStorageError:
            self.creation_settings = WorkItemCreationSettings()

        self.template_var = tk.StringVar(
            value=str(self.creation_settings.template_path or "")
        )
        self.template_entry: ttk.Entry | None = None
        self.selected_source_id = self.sources[0].id if self.sources else None
        self.source_labels: dict[str, str] = {}

        header = ttk.Frame(parent)
        header.pack(fill=tk.X, pady=(0, 8))
        heading = ttk.Frame(header)
        heading.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            heading,
            text="Manage Work Items",
            style="Title.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            heading,
            text="Find, create, and organize Work Items from a configured folder.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))
        self.create_button = ttk.Button(
            header,
            text="New Work Item…",
            command=self.create_work_item,
            style="Accent.TButton",
        )
        self.create_button.pack(side=tk.RIGHT)

        source_panel = ttk.LabelFrame(parent, text="Current source", padding=(10, 8))
        source_panel.pack(fill=tk.X, pady=(0, 9))
        source_controls = ttk.Frame(source_panel)
        source_controls.pack(fill=tk.X)
        ttk.Label(source_controls, text="Source").pack(side=tk.LEFT, padx=(0, 8))
        self.source_var = tk.StringVar()
        self.source_combo = ttk.Combobox(
            source_controls,
            textvariable=self.source_var,
            state="readonly",
            width=26,
        )
        self.source_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.source_combo.bind("<<ComboboxSelected>>", self._source_selected)
        self.source_combo.bind("<F5>", lambda _event: self._refresh_from_key())
        self.source_combo.bind("<F6>", self._focus_other_list)
        self.manage_sources_button = ttk.Menubutton(
            source_controls,
            text="Manage sources…",
        )
        self.manage_sources_menu = tk.Menu(
            self.manage_sources_button,
            tearoff=False,
        )
        self.manage_sources_menu.add_command(
            label="Add source…",
            command=self.add_source,
        )
        self._add_source_menu_index = int(
            self.manage_sources_menu.index(tk.END)
        )
        self.manage_sources_menu.add_command(
            label="Edit selected source…",
            command=self.edit_source,
        )
        self._edit_source_menu_index = int(
            self.manage_sources_menu.index(tk.END)
        )
        self.manage_sources_menu.add_command(
            label="Remove selected source…",
            command=self.remove_source,
        )
        self._remove_source_menu_index = int(
            self.manage_sources_menu.index(tk.END)
        )
        self.manage_sources_menu.add_separator()
        self.manage_sources_menu.add_command(
            label="Creation template…",
            command=self.configure_template,
        )
        self._creation_template_menu_index = int(
            self.manage_sources_menu.index(tk.END)
        )
        self.manage_sources_button.configure(menu=self.manage_sources_menu)
        self.manage_sources_button.pack(side=tk.LEFT, padx=(6, 0))
        self.refresh_button = ttk.Button(
            source_controls,
            text="Refresh",
            command=self.refresh,
        )
        self.refresh_button.pack(side=tk.LEFT, padx=(6, 0))

        path_row = ttk.Frame(source_panel)
        path_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(path_row, text="Folder", style="Heading.TLabel").pack(
            side=tk.LEFT,
            anchor=tk.N,
        )
        self.source_path_var = tk.StringVar(value="—")
        self.source_path_label = ttk.Label(
            path_row,
            textvariable=self.source_path_var,
            wraplength=560,
            justify=tk.LEFT,
        )
        self.source_path_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        source_panel.bind("<Configure>", self._resize_source_path, add="+")
        self.source_status_var = tk.StringVar()
        self.source_status_label = ttk.Label(
            source_panel,
            textvariable=self.source_status_var,
            style="Muted.TLabel",
        )
        self.source_status_label.pack(
            anchor=tk.W,
            padx=(54, 0),
            pady=(5, 0),
        )

        list_panel = ttk.Frame(parent)
        list_panel.pack(fill=tk.BOTH, expand=True)
        search_row = ttk.Frame(list_panel)
        search_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(search_row, text="Find").pack(side=tk.LEFT, padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.search_entry.bind("<KeyRelease>", lambda _event: self.render_items())
        self.count_var = tk.StringVar()
        ttk.Label(search_row, textvariable=self.count_var, style="Muted.TLabel").pack(
            side=tk.RIGHT,
            padx=(8, 0),
        )
        self.item_tree_frame, self.item_tree = scrollable_tree(
            list_panel,
            ("type", "projects"),
        )
        for column, label, width in (
            ("#0", "Work Item", 340),
            ("type", "Type", 90),
            ("projects", "Project", 90),
        ):
            self.item_tree.heading(column, text=label)
            self.item_tree.column(
                column,
                width=width,
                minwidth=(220 if column == "#0" else 84),
                stretch=column == "#0",
            )
        self.item_tree_frame.pack(fill=tk.BOTH, expand=True)
        self.item_tree.bind("<Double-1>", lambda _event: self.edit_tags())
        self.item_tree.bind("<Return>", lambda _event: self.edit_tags())
        self.item_tree.bind("<<TreeviewSelect>>", self._item_selected)
        self.item_tree.bind("<F5>", lambda _event: self._refresh_from_key())
        self.item_tree.bind("<F6>", self._focus_other_list)

        detail = ttk.Frame(
            parent,
            padding=(10, 8),
            style="Card.TFrame",
        )
        detail.pack(fill=tk.X, pady=(9, 0))
        detail_top = ttk.Frame(detail, style="Card.TFrame")
        detail_top.pack(fill=tk.X)
        self.detail_title_var = tk.StringVar(value="Select a Work Item")
        ttk.Label(
            detail_top,
            textvariable=self.detail_title_var,
            style="Card.TLabel",
            font=("Segoe UI Semibold", 10),
        ).pack(side=tk.LEFT)
        self.detail_kind_var = tk.StringVar()
        ttk.Label(
            detail_top,
            textvariable=self.detail_kind_var,
            style="CardMuted.TLabel",
        ).pack(side=tk.LEFT, padx=(8, 0))
        self.open_folder_button = ttk.Button(
            detail_top,
            text="Open folder",
            command=self.open_folder,
            state=tk.DISABLED,
        )
        self.open_folder_button.pack(side=tk.RIGHT)
        self.edit_details_button = ttk.Menubutton(
            detail_top,
            text="Organize",
            state=tk.DISABLED,
        )
        self.organize_menu = tk.Menu(self.edit_details_button, tearoff=False)
        self.organize_menu.add_command(
            label="Edit tags & contexts…",
            command=self.edit_tags,
        )
        self._edit_organization_menu_index = int(self.organize_menu.index(tk.END))
        self.organize_menu.add_separator()
        self.organize_menu.add_command(
            label="Forget Palette organization…",
            command=self.forget_organization,
        )
        self._forget_organization_menu_index = int(
            self.organize_menu.index(tk.END)
        )
        self.edit_details_button.configure(menu=self.organize_menu)
        self.edit_details_button.pack(side=tk.RIGHT, padx=(0, 6))
        self.detail_summary_var = tk.StringVar(
            value="Folder, Contexts, and personal tags appear here."
        )
        self.detail_summary_label = ttk.Label(
            detail,
            textvariable=self.detail_summary_var,
            style="CardMuted.TLabel",
            wraplength=650,
            justify=tk.LEFT,
        )
        self.detail_summary_label.pack(fill=tk.X, pady=(6, 0))
        detail.bind("<Configure>", self._resize_detail_summary, add="+")
        self.summary_var = self.count_var
        self.render()

    def focus(self) -> None:
        self.search_entry.focus_set()

    def _focus_other_list(self, event: tk.Event) -> str:
        target = self.item_tree if event.widget == self.source_combo else self.source_combo
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
        item = self._item_for_key(key)
        if item is not None and item.source_id != self.selected_source_id:
            self.selected_source_id = item.source_id
            self.render()
        if self.item_tree.exists(key):
            self.item_tree.selection_set(key)
            self.item_tree.focus(key)
            self.item_tree.see(key)
            self.item_tree.focus_set()
            self._sync_item_details()

    def set_contexts(self, contexts: tuple[ContextDefinition, ...]) -> None:
        """Refresh the personal Context choices owned by Configure."""

        self.contexts = list(contexts)
        if hasattr(self, "item_tree"):
            self.render()

    def render(self) -> None:
        current_selection = self.item_tree.selection()
        selected_key = current_selection[0] if current_selection else None
        self._render_source_selector()
        self.render_items(selected_key=selected_key)

    def _render_source_selector(self) -> None:
        if self.selected_source_id not in {source.id for source in self.sources}:
            self.selected_source_id = self.sources[0].id if self.sources else None
        counts: dict[str, int] = {}
        for source in self.sources:
            counts[source.name.casefold()] = counts.get(source.name.casefold(), 0) + 1
        self.source_labels = {
            (
                source.name
                if counts[source.name.casefold()] == 1
                else f"{source.name} [{source.id}]"
            ): source.id
            for source in self.sources
        }
        self.source_combo.configure(values=tuple(self.source_labels))
        selected_source = self._selected_source()
        selected_label = next(
            (
                label
                for label, source_id in self.source_labels.items()
                if source_id == self.selected_source_id
            ),
            "",
        )
        self.source_var.set(selected_label)
        has_source = selected_source is not None
        state = tk.NORMAL if has_source else tk.DISABLED
        self.manage_sources_button.configure(state=tk.NORMAL)
        self.manage_sources_menu.entryconfigure(
            self._add_source_menu_index,
            state=tk.NORMAL,
        )
        self.manage_sources_menu.entryconfigure(
            self._edit_source_menu_index,
            state=state,
        )
        self.manage_sources_menu.entryconfigure(
            self._remove_source_menu_index,
            state=state,
        )
        self.manage_sources_menu.entryconfigure(
            self._creation_template_menu_index,
            state=tk.NORMAL,
        )
        self.refresh_button.configure(state=state)
        if selected_source is None:
            self.source_path_var.set("No Work Item source configured.")
            self.source_status_var.set("Add a source to discover Work Items.")
            self.source_status_label.configure(style="Muted.TLabel")
            return
        self.source_path_var.set(str(selected_source.workitems_path))
        result = next(
            (
                candidate
                for candidate in self.index.sources
                if candidate.source.id.casefold() == selected_source.id.casefold()
            ),
            None,
        )
        if result is not None and result.error:
            suffix = (
                f" · showing {len(result.items)} last-known Work Items"
                if result.using_last_known_good
                else ""
            )
            self.source_status_var.set(f"Unavailable{suffix} · {result.error}")
            self.source_status_label.configure(style="Error.TLabel")
        elif result is None:
            self.source_status_var.set("Not refreshed yet.")
            self.source_status_label.configure(style="Muted.TLabel")
        else:
            self.source_status_var.set(
                f"Available · {len(result.items)} Work Items discovered"
            )
            self.source_status_label.configure(style="Success.TLabel")

    def render_items(self, *, selected_key: str | None = None) -> None:
        self.item_tree.delete(*self.item_tree.get_children())
        query = self.search_var.get().strip().casefold()
        shown = 0
        for item in self._selected_source_items():
            key = work_item_metadata_key(item.source_id, item.relative_folder)
            tags = self.metadata.get(key, WorkItemMetadata()).tags
            reference = WorkItemReference(item.source_id, item.relative_folder)
            contexts = tuple(
                context.name
                for context in self.contexts
                if reference in context.work_item_refs
            )
            searchable = " ".join(
                (
                    item.display_name,
                    item.kind_name or item.kind_code or "",
                    *item.project_codes,
                    *contexts,
                    *tags,
                )
            ).casefold()
            if query and not all(term in searchable for term in query.split()):
                continue
            self.item_tree.insert(
                "",
                tk.END,
                iid=key,
                text=item.display_name,
                values=(
                    item.kind_name or item.kind_code or "—",
                    ", ".join(item.project_codes) or "—",
                ),
            )
            shown += 1
        self.count_var.set(f"{shown} shown")
        if selected_key and self.item_tree.exists(selected_key):
            self.item_tree.selection_set(selected_key)
            self.item_tree.focus(selected_key)
        elif shown:
            first = self.item_tree.get_children()[0]
            self.item_tree.selection_set(first)
            self.item_tree.focus(first)
        self._sync_item_details()

    def _source_selected(self, _event: tk.Event | None = None) -> None:
        self.selected_source_id = self.source_labels.get(self.source_var.get())
        self.search_var.set("")
        self.render()
        self.item_tree.focus_set()

    def _selected_source(self) -> WorkItemSource | None:
        selected_source_id = getattr(
            self,
            "selected_source_id",
            self.sources[0].id if self.sources else None,
        )
        return next(
            (
                source
                for source in self.sources
                if source.id == selected_source_id
            ),
            None,
        )

    def _selected_source_items(self) -> tuple[DiscoveredWorkItem, ...]:
        if self.selected_source_id is None:
            return ()
        source_id = self.selected_source_id.casefold()
        return tuple(
            item
            for item in self.index.items
            if item.source_id.casefold() == source_id
        )

    def _item_for_key(self, key: str) -> DiscoveredWorkItem | None:
        return next(
            (
                item
                for item in self.index.items
                if work_item_metadata_key(item.source_id, item.relative_folder) == key
            ),
            None,
        )

    def _selected_item(self) -> tuple[str, DiscoveredWorkItem] | None:
        selection = self.item_tree.selection()
        if not selection:
            return None
        item = self._item_for_key(selection[0])
        return (selection[0], item) if item is not None else None

    def _item_selected(self, _event: tk.Event | None = None) -> None:
        self._sync_item_details()

    def _sync_item_details(self) -> None:
        selected = self._selected_item()
        if selected is None:
            self.detail_title_var.set("Select a Work Item")
            self.detail_kind_var.set("")
            self.detail_summary_var.set(
                "Folder, Contexts, and personal tags appear here."
            )
            self.edit_details_button.configure(state=tk.DISABLED)
            if hasattr(self, "organize_menu"):
                self.organize_menu.entryconfigure(
                    self._edit_organization_menu_index,
                    state=tk.DISABLED,
                )
                self.organize_menu.entryconfigure(
                    self._forget_organization_menu_index,
                    state=tk.DISABLED,
                )
            self.open_folder_button.configure(state=tk.DISABLED)
            return
        key, item = selected
        tags = self.metadata.get(key, WorkItemMetadata()).tags
        reference = WorkItemReference(item.source_id, item.relative_folder)
        contexts = tuple(
            context.name
            for context in self.contexts
            if reference in context.work_item_refs
        )
        self.detail_title_var.set(item.display_name)
        detail_kind = item.kind_name or item.kind_code or "Work Item"
        if item.project_codes:
            detail_kind += f" · {', '.join(item.project_codes)}"
        self.detail_kind_var.set(detail_kind)
        self.detail_summary_var.set(
            "   ".join(
                (
                    f"Folder: {item.relative_folder}",
                    f"Contexts: {', '.join(contexts) or '—'}",
                    f"Tags: {', '.join(tags) or '—'}",
                )
            )
        )
        self.edit_details_button.configure(state=tk.NORMAL)
        if hasattr(self, "organize_menu"):
            self.organize_menu.entryconfigure(
                self._edit_organization_menu_index,
                state=tk.NORMAL,
            )
            self.organize_menu.entryconfigure(
                self._forget_organization_menu_index,
                state=(
                    tk.NORMAL
                    if self.palette_path is not None
                    and self.command_surface_path is not None
                    else tk.DISABLED
                ),
            )
        self.open_folder_button.configure(state=tk.NORMAL)

    def _resize_source_path(self, event: tk.Event) -> None:
        self.source_path_label.configure(wraplength=max(180, int(event.width) - 90))

    def _resize_detail_summary(self, event: tk.Event) -> None:
        self.detail_summary_label.configure(wraplength=max(240, int(event.width) - 24))

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

    def configure_template(self) -> None:
        """Choose and immediately save the creation template."""

        previous = self.template_var.get()
        self.choose_template()
        if self.template_var.get() != previous:
            self.save_template()

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
            if self.template_entry is not None:
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
            self.manage_sources_button.focus_set()
            return
        if not self.template_var.get().strip():
            self.feedback(
                "Choose a generic Excel template before creating a Work Item.",
                False,
            )
            self.configure_template()
            return
        if not self.save_template() or self.creation_settings.template_path is None:
            return
        selected_source = self._selected_source()
        ordered_sources = tuple(
            sorted(
                self.sources,
                key=lambda source: source.id != getattr(selected_source, "id", None),
            )
        )
        CreateWorkItemDialog(
            self.parent.winfo_toplevel(),
            ordered_sources,
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
        source = self._selected_source()
        if source is None:
            self.feedback("Select a Work Item source first.", False)
            return
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
        self.selected_source_id = source.id
        self._prune_index()
        self.feedback(f'Saved Work Item source “{source.name}”. Refreshing…', True)
        self.on_change()
        self.render()
        self._start_refresh()
        return True

    def remove_source(self) -> None:
        source = self._selected_source()
        if source is None:
            self.feedback("Select a Work Item source first.", False)
            return
        source_id = source.id
        if not messagebox.askyesno(
            "Remove Work Item source?",
            (
                f'Remove “{source.name}” from Context Palette on this PC?\n\n'
                f"Source folder: {source.workitems_path}\n\n"
                "Context Palette will stop discovering every Work Item in this "
                "source. No folder, workbook, or other file will be deleted.\n\n"
                "Saved tags, Context memberships, context slots, and Quick actions "
                "will be kept but unavailable. They become available again if you "
                f'add a source with ID “{source.id}” and the same Work Item folder names.'
            ),
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
        self.selected_source_id = remaining[0].id if remaining else None
        self._prune_index()
        self.feedback(
            f'Removed Work Item source “{source.name}”. Its Palette organization was retained for reuse.',
            True,
        )
        self.on_change()
        self.render()
        self._start_refresh()

    def edit_tags(self) -> None:
        selected = self._selected_item()
        if selected is None:
            self.feedback("Select a discovered Work Item first.", False)
            return
        key, item = selected
        reference = WorkItemReference(item.source_id, item.relative_folder)
        TagDialog(
            self.parent.winfo_toplevel(),
            item,
            self.metadata.get(key, WorkItemMetadata()).tags,
            tuple(context.name for context in self.contexts),
            tuple(
                context.name
                for context in self.contexts
                if reference in context.work_item_refs
            ),
            lambda tags, contexts: self._save_details(
                key,
                reference,
                tags,
                contexts,
            ),
        )

    def forget_organization(self) -> None:
        """Remove only Context Palette's personal references to one Work Item."""

        selected = self._selected_item()
        if selected is None:
            self.feedback("Select a discovered Work Item first.", False)
            return
        key, item = selected
        if self.palette_path is None or self.command_surface_path is None:
            self.feedback("Work Item organization cleanup is unavailable.", False)
            return
        reference = WorkItemReference(item.source_id, item.relative_folder)
        service_arguments = {
            "metadata_path": self.metadata_path,
            "context_paths": (self.contexts_path,),
            "palette_path": self.palette_path,
            "command_surface_path": self.command_surface_path,
        }
        try:
            report = inspect_work_item_organization(reference, **service_arguments)
        except WorkItemOrganizationError as exc:
            messagebox.showerror(
                "Work Item organization could not be inspected",
                str(exc),
                parent=self.parent,
            )
            return
        if report.files_changed == 0:
            self.feedback(
                f'“{item.display_name}” has no saved Palette organization to forget.',
                True,
            )
            return
        summary = work_item_organization_summary(report)
        if not messagebox.askyesno(
            "Forget Palette organization?",
            (
                f'Forget Palette organization for “{item.display_name}”?\n\n'
                f"This will remove:\n{summary}\n\n"
                "The Work Item source, folder, workbook, files, and Inbox contents "
                "will not be changed. Context Palette has no one-click Undo."
            ),
            icon=messagebox.WARNING,
            parent=self.parent,
        ):
            return
        try:
            forgotten = forget_work_item_organization(
                reference,
                **service_arguments,
            )
        except WorkItemOrganizationError as exc:
            if not exc.rollback_completed:
                # A mixed-but-valid set of files is possible after a failed
                # rollback.  Never let this panel keep writing from its stale
                # pre-operation view.
                self.on_change()
                if self.refresh_configuration is not None:
                    self.refresh_configuration()
                self.render_items(selected_key=key)
            messagebox.showerror(
                "Work Item organization was not forgotten",
                (
                    f"{exc}\n\nContext Palette reloaded the current saved state. "
                    "Review it before making another change."
                    if not exc.rollback_completed
                    else str(exc)
                ),
                parent=self.parent,
            )
            return
        self.metadata.pop(key, None)
        self.on_change()
        if self.refresh_configuration is not None:
            self.refresh_configuration()
        self.render_items(selected_key=key)
        self.feedback(
            f'Forgot Palette organization for “{item.display_name}” '
            f"across {forgotten.files_changed} personal file(s).",
            True,
        )

    def open_folder(self) -> None:
        selected = self._selected_item()
        if selected is None:
            self.feedback("Select a discovered Work Item first.", False)
            return
        _key, item = selected
        try:
            os.startfile(item.folder_path)  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror(
                "Work Item folder could not be opened",
                str(exc),
                parent=self.parent,
            )
            return
        self.feedback(f'Opened folder for “{item.display_name}”.', True)

    def _save_details(
        self,
        key: str,
        reference: WorkItemReference,
        tags: tuple[str, ...],
        context_names: tuple[str, ...],
    ) -> bool:
        updated_metadata = dict(self.metadata)
        if tags:
            updated_metadata[key] = WorkItemMetadata(tags)
        else:
            updated_metadata.pop(key, None)
        try:
            updated_contexts = update_work_item_context_memberships(
                self.contexts,
                reference,
                context_names,
            )
        except ContextError as exc:
            messagebox.showerror("Work Items", str(exc), parent=self.parent)
            return False

        contexts_changed = updated_contexts != self.contexts
        previous_context_bytes: bytes | None = None
        context_file_existed = self.contexts_path.exists()
        try:
            if contexts_changed:
                if self.contexts_path.exists():
                    previous_context_bytes = self.contexts_path.read_bytes()
                save_contexts(self.contexts_path, updated_contexts)
            save_work_item_metadata(self.metadata_path, updated_metadata)
        except (OSError, ContextError, WorkItemStorageError) as exc:
            if contexts_changed and previous_context_bytes is not None:
                try:
                    atomic_replace_bytes(
                        self.contexts_path,
                        previous_context_bytes,
                        preserve_previous=False,
                    )
                except OSError:
                    messagebox.showerror(
                        "Work Items need recovery",
                        "Tags could not be saved and the previous Context file could "
                        "not be restored. Close Configure without making more changes, "
                        "then restore the adjacent .bak file.",
                        parent=self.parent,
                    )
                    return False
            elif contexts_changed and not context_file_existed:
                try:
                    self.contexts_path.unlink(missing_ok=True)
                except OSError:
                    messagebox.showerror(
                        "Work Items need recovery",
                        "Tags could not be saved and the newly created Context file "
                        "could not be removed. Close Configure and review the file.",
                        parent=self.parent,
                    )
                    return False
            messagebox.showerror(
                "Work Items",
                f"Work Item changes could not be saved. Existing settings were restored.\n\n{exc}",
                parent=self.parent,
            )
            return False
        self.metadata = updated_metadata
        self.contexts = updated_contexts
        self.feedback("Saved Work Item tags and contexts.", True)
        self.on_change()
        self.render()
        if contexts_changed and self.refresh_configuration is not None:
            self.refresh_configuration()
        return True

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
        place_child_window(self.window, parent)
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
    def __init__(
        self,
        parent: tk.Misc,
        item: DiscoveredWorkItem,
        tags: tuple[str, ...],
        context_names: tuple[str, ...],
        selected_contexts: tuple[str, ...],
        on_save: Callable[[tuple[str, ...], tuple[str, ...]], bool],
    ) -> None:
        self.on_save = on_save
        self.window = tk.Toplevel(parent)
        self.window.title("Work Item tags and contexts")
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
        self.contexts = tk.StringVar(value=", ".join(selected_contexts))
        self.context_field = ContextMembershipField(
            outer,
            self.contexts,
            context_names,
            label="Contexts",
        )
        ttk.Label(
            outer,
            text=(
                "Tags and Context membership stay in Context Palette; the Work "
                "Item folder is not modified. Create new Contexts in Configure first."
            ),
            style="Muted.TLabel",
            wraplength=520,
        ).pack(anchor=tk.W, pady=(8, 8))
        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X)
        ttk.Button(controls, text="Save changes", command=self._save, style="Accent.TButton").pack(side=tk.RIGHT)
        ttk.Button(controls, text="Cancel", command=self.window.destroy).pack(side=tk.RIGHT, padx=(0, 6))
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.bind("<Return>", lambda _event: self._save())
        place_child_window(self.window, parent)
        entry.focus_set()

    def _save(self) -> None:
        tags = tuple(dict.fromkeys(" ".join(value.strip().split()).casefold() for value in self.tags.get().split(",") if value.strip()))
        contexts = tuple(
            dict.fromkeys(
                value.strip()
                for value in self.contexts.get().split(",")
                if value.strip()
            )
        )
        if self.on_save(tags, contexts):
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
        place_child_window(self.window, parent)
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
