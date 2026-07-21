from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable, Iterable

from .actions import Action, ActionError, append_actions, load_actions
from .harvest import (
    HarvestBatch,
    HarvestCandidate,
    HarvestError,
    HarvestScanCoordinator,
    HarvestSourceResult,
    build_candidates,
    candidate_to_draft,
    normalize_url_for_comparison,
    update_candidate_values,
)
from .window_geometry import configure_standard_window


class HarvestWindow:
    """Attended bulk review for deterministic document-link candidates."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        actions: list[Action],
        context_names: Iterable[str],
        focus_context: str,
        actions_path: Path,
        on_change: Callable[[], None],
    ) -> None:
        self.actions = actions
        self.context_names = tuple(context_names)
        self.focus_context = focus_context
        self.actions_path = actions_path
        self.on_change = on_change
        self.batch = HarvestBatch()
        self.source_paths: list[Path] = []
        self.coordinator = HarvestScanCoordinator()
        self.submitting = False
        self.poll_after_id: str | None = None

        self.window = tk.Toplevel(parent)
        self.window.title("Harvest actions")
        configure_standard_window(self.window)
        self.window.geometry("900x700")
        self.window.minsize(760, 560)
        self.window.protocol("WM_DELETE_WINDOW", self._close)
        self.window.bind("<Escape>", lambda _event: self._close())

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        ttk.Label(outer, text="Harvest actions", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            outer,
            text="Extract explicit links locally, review them, then create selected personal Draft actions.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(2, 8))

        self.status_var = tk.StringVar(value="Add one or more Markdown, text, Word, or Excel documents.")
        ttk.Label(outer, textvariable=self.status_var, style="Status.TLabel").pack(
            side=tk.BOTTOM, fill=tk.X, pady=(8, 0)
        )
        footer = ttk.Frame(outer)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        self.preview_button = ttk.Button(footer, text="Preview selected Drafts", command=self._preview)
        self.preview_button.pack(side=tk.LEFT)
        self.create_button = ttk.Button(
            footer,
            text="Create selected Drafts",
            command=self._create,
            state=tk.DISABLED,
            style="Accent.TButton",
        )
        self.create_button.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(footer, text="Close", command=self._close).pack(side=tk.RIGHT)

        panes = ttk.Panedwindow(outer, orient=tk.VERTICAL)
        panes.pack(fill=tk.BOTH, expand=True)
        self._build_sources(panes)
        self._build_candidates(panes)

        self.window.transient(parent)
        self.window.lift()
        self.window.after_idle(self.add_documents)

    def _build_sources(self, panes: ttk.Panedwindow) -> None:
        frame = ttk.Frame(panes, padding=(0, 0, 0, 6))
        panes.add(frame, weight=1)
        header = ttk.Frame(frame)
        header.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(header, text="Sources", style="Heading.TLabel").pack(side=tk.LEFT)
        ttk.Button(header, text="Add documents…", command=self.add_documents).pack(side=tk.LEFT, padx=(10, 4))
        self.remove_source_button = ttk.Button(header, text="Remove", command=self.remove_source)
        self.remove_source_button.pack(side=tk.LEFT, padx=4)
        self.scan_button = ttk.Button(header, text="Scan / Rescan", command=self.scan, style="Accent.TButton")
        self.scan_button.pack(side=tk.LEFT, padx=4)
        self.cancel_button = ttk.Button(header, text="Cancel scan", command=self.cancel_scan, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT, padx=4)
        self.source_tree = ttk.Treeview(
            frame,
            columns=("format", "status", "findings"),
            show="tree headings",
            height=3,
            selectmode="browse",
        )
        self.source_tree.heading("#0", text="Document")
        self.source_tree.heading("format", text="Format")
        self.source_tree.heading("status", text="Status")
        self.source_tree.heading("findings", text="Findings")
        self.source_tree.column("#0", width=360)
        self.source_tree.column("format", width=70, stretch=False)
        self.source_tree.column("status", width=170, stretch=False)
        self.source_tree.column("findings", width=80, stretch=False, anchor=tk.E)
        self.source_tree.pack(fill=tk.BOTH, expand=True)
        self.source_tree.bind("<<TreeviewSelect>>", lambda _event: self._show_source_status())

    def _build_candidates(self, panes: ttk.Panedwindow) -> None:
        frame = ttk.Frame(panes, padding=(0, 6, 0, 0))
        panes.add(frame, weight=3)
        filters = ttk.Frame(frame)
        filters.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(filters, text="Candidates", style="Heading.TLabel").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        search = ttk.Entry(filters, textvariable=self.search_var, width=24)
        search.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 5))
        self.status_filter = ttk.Combobox(filters, state="readonly", width=17)
        self.status_filter["values"] = ("All readiness", "Ready", "Needs attention", "Unsupported", "Existing Draft", "Already available")
        self.status_filter.set("All readiness")
        self.status_filter.pack(side=tk.LEFT, padx=3)
        self.duplicate_filter = ttk.Combobox(filters, state="readonly", width=18)
        self.duplicate_filter["values"] = ("All duplicates", "New", "Repeated in sources", "Existing Draft", "Already available", "Unsupported")
        self.duplicate_filter.set("All duplicates")
        self.duplicate_filter.pack(side=tk.LEFT, padx=3)
        self.source_filter = ttk.Combobox(filters, state="readonly", width=20)
        self.source_filter.set("All sources")
        self.source_filter.pack(side=tk.LEFT, padx=(3, 0))
        self.search_var.trace_add("write", lambda *_args: self._render_candidates())
        for control in (self.status_filter, self.duplicate_filter, self.source_filter):
            control.bind("<<ComboboxSelected>>", lambda _event: self._render_candidates())

        candidate_area = ttk.Panedwindow(frame, orient=tk.HORIZONTAL)
        candidate_area.pack(fill=tk.BOTH, expand=True)
        list_frame = ttk.Frame(candidate_area)
        candidate_area.add(list_frame, weight=3)
        self.candidate_tree = ttk.Treeview(
            list_frame,
            columns=("state", "duplicate", "sources", "occurrences"),
            show="tree headings",
            height=3,
            selectmode="extended",
        )
        for column, label, width in (
            ("#0", "Use / Action name", 290),
            ("state", "Readiness", 125),
            ("duplicate", "Duplicate", 135),
            ("sources", "Sources", 70),
            ("occurrences", "Found", 60),
        ):
            self.candidate_tree.heading(column, text=label)
            self.candidate_tree.column(column, width=width, stretch=column == "#0")
        self.candidate_tree.pack(fill=tk.BOTH, expand=True)
        self.candidate_tree.bind("<<TreeviewSelect>>", lambda _event: self._selection_changed())
        self.candidate_tree.bind("<Double-1>", lambda _event: self.toggle_selected_candidates())
        self.candidate_tree.bind("<space>", lambda _event: self.toggle_selected_candidates())

        detail = ttk.Frame(candidate_area, padding=(10, 0, 0, 0))
        candidate_area.add(detail, weight=2)
        ttk.Label(detail, text="Provenance", style="Heading.TLabel").pack(anchor=tk.W)
        self.provenance = tk.Text(detail, width=38, height=12, wrap=tk.WORD)
        self.provenance.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.provenance.configure(state=tk.DISABLED)

        selection_controls = ttk.Frame(frame)
        selection_controls.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(selection_controls, text="Select all Ready", command=self.select_all_ready).pack(side=tk.LEFT)
        ttk.Button(selection_controls, text="Toggle selected", command=self.toggle_selected_candidates).pack(side=tk.LEFT, padx=4)
        ttk.Button(selection_controls, text="Select source", command=lambda: self.select_source(True)).pack(side=tk.LEFT, padx=4)
        ttk.Button(selection_controls, text="Deselect source", command=lambda: self.select_source(False)).pack(side=tk.LEFT, padx=4)
        ttk.Button(selection_controls, text="Edit candidate…", command=self.edit_candidate).pack(side=tk.LEFT, padx=4)

        bulk = ttk.Frame(frame)
        bulk.pack(fill=tk.X, pady=(6, 0))
        self.context_value = tk.StringVar()
        self.tag_value = tk.StringVar()
        ttk.Label(bulk, text="Contexts").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(bulk, textvariable=self.context_value, width=25).grid(row=0, column=1, sticky=tk.EW, padx=(5, 3))
        ttk.Button(bulk, text="Add", command=lambda: self.bulk_edit("contexts", "add")).grid(row=0, column=2, padx=2)
        ttk.Button(bulk, text="Remove", command=lambda: self.bulk_edit("contexts", "remove")).grid(row=0, column=3, padx=2)
        ttk.Label(bulk, text="Tags").grid(row=1, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Entry(bulk, textvariable=self.tag_value, width=25).grid(row=1, column=1, sticky=tk.EW, padx=(5, 3), pady=(4, 0))
        ttk.Button(bulk, text="Add", command=lambda: self.bulk_edit("tags", "add")).grid(row=1, column=2, padx=2, pady=(4, 0))
        ttk.Button(bulk, text="Remove", command=lambda: self.bulk_edit("tags", "remove")).grid(row=1, column=3, padx=2, pady=(4, 0))
        bulk.columnconfigure(1, weight=1)
        self.mixed_var = tk.StringVar(value="Bulk Add merges values; Remove removes only the named values.")
        ttk.Label(bulk, textvariable=self.mixed_var, style="Muted.TLabel").grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=(4, 0))

    def add_documents(self) -> None:
        selected = filedialog.askopenfilenames(
            parent=self.window,
            title="Choose documents to harvest",
            filetypes=(
                ("Supported documents", "*.md *.txt *.docx *.xlsx"),
                ("Markdown", "*.md"),
                ("Text", "*.txt"),
                ("Word", "*.docx"),
                ("Excel", "*.xlsx"),
            ),
        )
        existing = {str(path).casefold() for path in self.source_paths}
        for value in selected:
            path = Path(value).resolve()
            if str(path).casefold() not in existing:
                self.source_paths.append(path)
                existing.add(str(path).casefold())
        self.source_paths.sort(key=lambda path: str(path).casefold())
        self._render_sources()
        if selected:
            self.scan()

    def remove_source(self) -> None:
        selected = self.source_tree.selection()
        if not selected or self.coordinator.running:
            return
        path = Path(selected[0])
        self.source_paths = [item for item in self.source_paths if item != path]
        self.batch.sources = [item for item in self.batch.sources if item.path != path]
        self._rebuild_candidates()
        self._render_sources()

    def scan(self) -> None:
        if not self.source_paths or self.coordinator.running:
            return
        self.batch.sources.clear()
        self.batch.candidates.clear()
        self.batch.cancelled = False
        try:
            self.coordinator.start(self.source_paths)
        except (HarvestError, OSError) as exc:
            messagebox.showerror("Harvest actions", str(exc), parent=self.window)
            return
        self.scan_button.configure(state=tk.DISABLED)
        self.cancel_button.configure(state=tk.NORMAL)
        self.remove_source_button.configure(state=tk.DISABLED)
        self.status_var.set(f"Scanning {len(self.source_paths)} document(s)…")
        self._schedule_poll()

    def cancel_scan(self) -> None:
        self.coordinator.cancel()
        self.status_var.set("Cancelling after the current bounded extraction unit…")

    def _schedule_poll(self) -> None:
        self.poll_after_id = self.window.after(80, self._poll)

    def _poll(self) -> None:
        self.poll_after_id = None
        for kind, value in self.coordinator.drain():
            if kind == "progress":
                ordinal, total, path = value
                self.status_var.set(f"Scanning {ordinal + 1} of {total}: {path.name}")
            elif kind == "source":
                self.batch.sources.append(value)
                self._render_sources()
            elif kind == "complete":
                self.batch.cancelled = bool(value)
                self._scan_complete()
        if self.coordinator.running:
            self._schedule_poll()

    def _scan_complete(self) -> None:
        self.scan_button.configure(state=tk.NORMAL)
        self.cancel_button.configure(state=tk.DISABLED)
        self.remove_source_button.configure(state=tk.NORMAL)
        self._rebuild_candidates()
        failures = sum(source.status == "Failed" for source in self.batch.sources)
        self.status_var.set(
            f"{len(self.batch.sources)} source(s) scanned · {len(self.batch.candidates)} candidate(s) · {failures} failed"
            + (" · cancelled" if self.batch.cancelled else "")
        )

    def _render_sources(self) -> None:
        existing = {source.path: source for source in self.batch.sources}
        self.source_tree.delete(*self.source_tree.get_children())
        for path in self.source_paths:
            source = existing.get(path)
            self.source_tree.insert(
                "",
                tk.END,
                iid=str(path),
                text=path.name,
                values=(
                    path.suffix.casefold(),
                    source.status if source else "Waiting",
                    len(source.occurrences) if source else 0,
                ),
            )

    def _rebuild_candidates(self) -> None:
        self.batch.candidates = build_candidates(
            self.batch.sources,
            self.actions,
            default_context=self.focus_context,
        )
        source_names = [source.path.name for source in self.batch.sources]
        self.source_filter["values"] = ("All sources", *source_names)
        self.source_filter.set("All sources")
        self._render_candidates()

    def _candidate_visible(self, candidate: HarvestCandidate) -> bool:
        query = self.search_var.get().strip().casefold()
        if query and query not in " ".join((candidate.name, candidate.target)).casefold():
            return False
        if self.status_filter.get() != "All readiness" and candidate.classification != self.status_filter.get():
            return False
        if self.duplicate_filter.get() != "All duplicates" and candidate.duplicate_state != self.duplicate_filter.get():
            return False
        source = self.source_filter.get()
        return source == "All sources" or any(item.source_path.name == source for item in candidate.occurrences)

    def _render_candidates(self) -> None:
        selected_ids = set(self.candidate_tree.selection())
        self.candidate_tree.delete(*self.candidate_tree.get_children())
        for candidate in self.batch.candidates:
            if not self._candidate_visible(candidate):
                continue
            sources = {item.source_id for item in candidate.occurrences}
            self.candidate_tree.insert(
                "",
                tk.END,
                iid=candidate.id,
                text=f"{'[x]' if candidate.selected else '[ ]'} {candidate.name}",
                values=(candidate.classification, candidate.duplicate_state, len(sources), len(candidate.occurrences)),
            )
        retained = [item for item in selected_ids if self.candidate_tree.exists(item)]
        if retained:
            self.candidate_tree.selection_set(retained)
        elif self.candidate_tree.get_children():
            self.candidate_tree.selection_set(self.candidate_tree.get_children()[0])
        self._update_create_state()
        self._show_provenance()

    def _selected_candidates(self) -> list[HarvestCandidate]:
        ids = set(self.candidate_tree.selection())
        return [candidate for candidate in self.batch.candidates if candidate.id in ids]

    def select_all_ready(self) -> None:
        for candidate in self.batch.candidates:
            candidate.selected = candidate.classification == "Ready" and candidate.duplicate_state in {"New", "Repeated in sources"}
        self._render_candidates()

    def toggle_selected_candidates(self) -> str:
        for candidate in self._selected_candidates():
            if candidate.classification in {"Ready", "Needs attention"}:
                candidate.selected = not candidate.selected
        self._render_candidates()
        return "break"

    def select_source(self, selected: bool) -> None:
        source_selection = self.source_tree.selection()
        if not source_selection:
            return
        path = Path(source_selection[0])
        for candidate in self.batch.candidates:
            if any(item.source_path == path for item in candidate.occurrences) and candidate.classification in {"Ready", "Needs attention"}:
                candidate.selected = selected
        self._render_candidates()

    def bulk_edit(self, field_name: str, operation: str) -> None:
        candidates = self._selected_candidates()
        raw = self.context_value.get() if field_name == "contexts" else self.tag_value.get()
        values = [value.strip() for value in raw.split(",") if value.strip()]
        if not candidates or not values:
            self.status_var.set("Select candidate rows and enter one or more comma-separated values.")
            return
        if field_name == "contexts":
            available = {value.casefold(): value for value in self.context_names}
            unknown = [value for value in values if value.casefold() not in available and value.casefold() != "general"]
            if unknown:
                self.status_var.set("Unknown Focus membership: " + ", ".join(unknown))
                return
            values = [available.get(value.casefold(), value) for value in values if value.casefold() != "general"]
        update_candidate_values(candidates, field_name=field_name, operation=operation, values=values)
        self.mixed_var.set(
            f"{operation.title()}ed {', '.join(values)} for {len(candidates)} candidate(s); other values were preserved."
        )
        self._show_provenance()

    def _selection_changed(self) -> None:
        self._show_provenance()
        selected = self._selected_candidates()
        if len(selected) < 2:
            self.mixed_var.set("Bulk Add merges values; Remove removes only the named values.")
            return
        context_sets = {tuple(sorted(candidate.contexts, key=str.casefold)) for candidate in selected}
        tag_sets = {tuple(sorted(candidate.tags, key=str.casefold)) for candidate in selected}
        self.mixed_var.set(
            f"Contexts: {'Mixed' if len(context_sets) > 1 else 'Same'} · "
            f"Tags: {'Mixed' if len(tag_sets) > 1 else 'Same'} · "
            "Add/Remove preserves other values."
        )

    def _show_source_status(self) -> None:
        selected = self.source_tree.selection()
        if not selected:
            return
        path = Path(selected[0])
        source = next((item for item in self.batch.sources if item.path == path), None)
        if source is None:
            return
        detail = source.error or "; ".join(source.warnings)
        self.status_var.set(
            f"{source.path.name}: {source.status} · {len(source.occurrences)} finding(s)"
            + (f" · {detail}" if detail else "")
        )

    def edit_candidate(self) -> None:
        selected = self._selected_candidates()
        if len(selected) != 1:
            self.status_var.set("Select one candidate to edit.")
            return
        candidate = selected[0]
        name = simpledialog.askstring("Edit candidate", "Action name:", initialvalue=candidate.name, parent=self.window)
        if name is None:
            return
        target = simpledialog.askstring("Edit candidate", "HTTP or HTTPS target:", initialvalue=candidate.target, parent=self.window)
        if target is None:
            return
        candidate.name = name.strip()
        candidate.target = target.strip()
        candidate.user_modified = True
        candidate.classification = "Ready"
        candidate.duplicate_state = (
            "Repeated in sources" if len(candidate.occurrences) > 1 else "New"
        )
        candidate.warnings.clear()
        try:
            candidate_to_draft(candidate)
            candidate.comparison_key = normalize_url_for_comparison(candidate.target)
            collision = next(
                (
                    item
                    for item in self.batch.candidates
                    if item is not candidate and item.comparison_key == candidate.comparison_key
                ),
                None,
            )
            existing_state = next(
                (
                    action.state
                    for action in self.actions
                    if action.type == "open_url"
                    and normalize_url_for_comparison(action.value) == candidate.comparison_key
                    and action.state in {"Draft", "Trusted"}
                ),
                None,
            )
            if collision is not None:
                candidate.duplicate_state = "Repeated in sources"
                raise HarvestError(f'The edited target duplicates candidate "{collision.name}".')
            if existing_state is not None:
                candidate.classification = "Existing Draft" if existing_state == "Draft" else "Already available"
                candidate.duplicate_state = candidate.classification
                candidate.selected = False
        except (ActionError, HarvestError) as exc:
            if candidate.classification == "Ready":
                candidate.classification = "Needs attention"
            candidate.warnings = [str(exc)]
            candidate.selected = False
        self._render_candidates()

    def _show_provenance(self) -> None:
        selected = self._selected_candidates()
        if not selected:
            text = "Select a candidate to inspect its target and every source occurrence."
        else:
            candidate = selected[0]
            contexts = ", ".join(sorted(candidate.contexts, key=str.casefold)) or "General only"
            tags = ", ".join(sorted(candidate.tags, key=str.casefold)) or "(none)"
            lines = [
                candidate.name,
                candidate.target,
                f"State: {candidate.classification}",
                f"Contexts: {contexts}",
                f"Tags: {tags}",
                f"Found {len(candidate.occurrences)} time(s):",
            ]
            for item in candidate.occurrences:
                lines.append(f"\n{item.source_path.name} · {item.location}\n{item.display_text or '(no label)'}")
            if candidate.warnings:
                lines.append("\nWarnings:\n" + "\n".join(candidate.warnings))
            text = "\n".join(lines)
        self.provenance.configure(state=tk.NORMAL)
        self.provenance.delete("1.0", tk.END)
        self.provenance.insert("1.0", text)
        self.provenance.configure(state=tk.DISABLED)

    def _drafts(self) -> list[Action]:
        candidates = [candidate for candidate in self.batch.candidates if candidate.selected]
        if not candidates:
            raise HarvestError("Select at least one Ready or reviewed candidate.")
        try:
            latest_local = load_actions(self.actions_path) if self.actions_path.exists() else []
            current_actions = [*getattr(self, "actions", ()), *latest_local]
        except ActionError as exc:
            raise HarvestError(f"The personal action store could not be rechecked: {exc}") from exc
        existing_keys = {
            normalize_url_for_comparison(action.value)
            for action in current_actions
            if action.type == "open_url" and action.state in {"Draft", "Trusted"}
        }
        actions: list[Action] = []
        issues: list[str] = []
        batch_keys: set[str] = set()
        for candidate in candidates:
            try:
                key = normalize_url_for_comparison(candidate.target)
                if key in existing_keys:
                    raise HarvestError("A Draft or Trusted action already uses this URL.")
                if key in batch_keys:
                    raise HarvestError("Another selected candidate uses this URL.")
                batch_keys.add(key)
                actions.append(candidate_to_draft(candidate))
            except (ActionError, HarvestError, ValueError) as exc:
                issues.append(f"{candidate.name}: {exc}")
        if issues:
            raise HarvestError("No Drafts were created. Correct these candidates:\n\n" + "\n".join(issues))
        return actions

    def _preview(self) -> None:
        try:
            actions = self._drafts()
        except HarvestError as exc:
            messagebox.showerror("Harvest actions", str(exc), parent=self.window)
            return
        preview = tk.Toplevel(self.window)
        preview.title("Harvest Draft preview")
        configure_standard_window(preview)
        text = tk.Text(preview, wrap=tk.WORD, padx=12, pady=10)
        text.pack(fill=tk.BOTH, expand=True)
        for action in actions:
            text.insert(
                tk.END,
                f"{action.title}\nType: Open a website\nState: Draft\nTarget: {action.value}\n"
                f"Contexts: {', '.join(action.effective_contexts)}\nTags: {', '.join(action.effective_tags) or '(none)'}\n\n",
            )
        text.configure(state=tk.DISABLED)

    def _create(self) -> None:
        if self.submitting:
            return
        try:
            actions = self._drafts()
        except HarvestError as exc:
            messagebox.showerror("Harvest actions", str(exc), parent=self.window)
            return
        if not messagebox.askyesno(
            "Create harvested Drafts",
            f"Create {len(actions)} selected personal Draft action(s) in one atomic write?",
            parent=self.window,
        ):
            return
        try:
            actions = self._drafts()
        except HarvestError as exc:
            messagebox.showerror(
                "Harvest actions",
                "The selected Drafts changed while confirmation was open.\n\n" + str(exc),
                parent=self.window,
            )
            return
        self.submitting = True
        self.create_button.configure(state=tk.DISABLED)
        try:
            append_actions(self.actions_path, actions)
            self.on_change()
        except (ActionError, OSError) as exc:
            self.submitting = False
            self._update_create_state()
            messagebox.showerror("Harvest actions", str(exc), parent=self.window)
            return
        selected = [candidate for candidate in self.batch.candidates if candidate.selected]
        for candidate in selected:
            candidate.selected = False
            candidate.classification = "Created Draft"
            candidate.duplicate_state = "Existing Draft"
        self.status_var.set(f"Created {len(actions)} personal Draft action(s).")
        messagebox.showinfo("Harvest actions", f"Created {len(actions)} personal Draft action(s).", parent=self.window)
        self._render_candidates()

    def _update_create_state(self) -> None:
        count = sum(candidate.selected for candidate in self.batch.candidates)
        self.create_button.configure(state=tk.NORMAL if count and not self.submitting else tk.DISABLED)
        self.preview_button.configure(state=tk.NORMAL if count else tk.DISABLED)

    def _close(self) -> None:
        self.coordinator.cancel()
        if self.poll_after_id is not None:
            try:
                self.window.after_cancel(self.poll_after_id)
            except tk.TclError:
                pass
        self.window.destroy()
