"""Attended editor for one Action's configured Quick-menu placements."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from .action_configured_placement import (
    ConfiguredPlacementError,
    ConfiguredPlacementKey,
    ConfiguredPlacementLocation,
    commit_configured_action_placements,
    configured_action_placement_inventory,
    plan_configured_action_placements,
)
from .actions import ACTION_BOUND_QUICK_MENU_SPECS, Action
from .window_geometry import configure_standard_window


def automatic_quick_menu_placement(action: Action) -> str:
    """Return the read-only automatic placement shown beside configured menus."""

    for _group_id, root_label, action_type in ACTION_BOUND_QUICK_MENU_SPECS:
        if action.type != action_type:
            continue
        if action.quick_action_path:
            return " > ".join((root_label, *action.quick_action_path))
        return f"{root_label} > Menu root"
    return "None for this Action type"


def _storage_label(storage: str) -> str:
    key = storage.strip().casefold()
    if key in {"local", "personal", "my configuration"}:
        return "My configuration"
    if key in {"shared", "project", "built-in", "built in"}:
        return "Built-in"
    return storage


class ActionConfiguredPlacementWindow:
    """Review and apply one Action's explicit configured-menu references."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        action: Action,
        shared_actions_path: Path,
        local_actions_path: Path,
        shared_command_surface_path: Path,
        local_command_surface_path: Path,
        on_change: Callable[[], None],
        on_refresh: Callable[[], None],
    ) -> None:
        self.parent = parent
        self.action = action
        self.shared_actions_path = Path(shared_actions_path)
        self.local_actions_path = Path(local_actions_path)
        self.shared_command_surface_path = Path(shared_command_surface_path)
        self.local_command_surface_path = Path(local_command_surface_path)
        self.on_change = on_change
        self.on_refresh = on_refresh
        self.inventory = None
        self.plan = None
        self.locations: tuple[ConfiguredPlacementLocation, ...] = ()
        self.location_by_key: dict[
            ConfiguredPlacementKey,
            ConfiguredPlacementLocation,
        ] = {}
        self.current_locations: frozenset[ConfiguredPlacementKey] = frozenset()
        self.desired_locations: set[ConfiguredPlacementKey] = set()
        self.key_by_iid: dict[str, ConfiguredPlacementKey] = {}
        self.iid_by_key: dict[ConfiguredPlacementKey, str] = {}
        self.submitting = False
        self.review_locked = False
        self.refresh_requested = False
        self._transition_message = ""

        self.window = tk.Toplevel(parent)
        self.window.title(f"Quick-action placements · {action.title}")
        configure_standard_window(self.window, parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.bind("<Control-f>", self._focus_search)

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(5, weight=1)

        ttk.Label(
            outer,
            text="Other Quick-menu placements",
            style="Title.TLabel",
        ).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            outer,
            text=(
                "Choose where this Action also appears in configured Quick-action "
                "menus. Automatic Passwords, Folders, and Prompts placement remains "
                "separate and is not changed here."
            ),
            style="Muted.TLabel",
            wraplength=740,
            justify=tk.LEFT,
        ).grid(row=1, column=0, sticky=tk.EW, pady=(2, 8))

        summary = ttk.Frame(outer, style="Card.TFrame", padding=(10, 8))
        summary.grid(row=2, column=0, sticky=tk.EW, pady=(0, 8))
        summary.columnconfigure(1, weight=1)
        ttk.Label(summary, text="Action", style="Card.TLabel").grid(
            row=0,
            column=0,
            sticky=tk.W,
        )
        ttk.Label(
            summary,
            text=action.title,
            style="Card.TLabel",
            wraplength=560,
        ).grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        ttk.Label(
            summary,
            text="Automatic placement (read-only)",
            style="CardMuted.TLabel",
        ).grid(row=1, column=0, sticky=tk.W, pady=(4, 0))
        self.automatic_placement_var = tk.StringVar(
            value=automatic_quick_menu_placement(action)
        )
        ttk.Label(
            summary,
            textvariable=self.automatic_placement_var,
            style="CardMuted.TLabel",
            wraplength=560,
        ).grid(row=1, column=1, sticky=tk.W, padx=(10, 0), pady=(4, 0))
        ttk.Label(
            summary,
            text="Action storage",
            style="CardMuted.TLabel",
        ).grid(row=2, column=0, sticky=tk.W, pady=(4, 0))
        self.action_storage_var = tk.StringVar(value="Loading…")
        ttk.Label(
            summary,
            textvariable=self.action_storage_var,
            style="CardMuted.TLabel",
        ).grid(row=2, column=1, sticky=tk.W, padx=(10, 0), pady=(4, 0))

        search_row = ttk.Frame(outer)
        search_row.grid(row=3, column=0, sticky=tk.EW, pady=(0, 6))
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="Find location").grid(
            row=0,
            column=0,
            sticky=tk.W,
        )
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        self.search_entry.grid(row=0, column=1, sticky=tk.EW, padx=(6, 8))
        self.count_var = tk.StringVar()
        ttk.Label(
            search_row,
            textvariable=self.count_var,
            style="Muted.TLabel",
        ).grid(row=0, column=2, sticky=tk.E)

        guidance = ttk.Label(
            outer,
            text=(
                "Use Space, Enter, or the Use column to include or remove a "
                "location. A personal Action cannot be added to a Built-in menu."
            ),
            style="Muted.TLabel",
            wraplength=740,
            justify=tk.LEFT,
        )
        guidance.grid(row=4, column=0, sticky=tk.EW, pady=(0, 6))

        review = ttk.Panedwindow(outer, orient=tk.VERTICAL)
        review.grid(row=5, column=0, sticky=tk.NSEW)

        table_frame = ttk.Frame(review)
        review.add(table_frame, weight=3)
        vertical = ttk.Scrollbar(table_frame, orient=tk.VERTICAL)
        horizontal = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL)
        self.tree = ttk.Treeview(
            table_frame,
            columns=("use", "location", "storage", "status"),
            show="headings",
            selectmode="browse",
            yscrollcommand=vertical.set,
            xscrollcommand=horizontal.set,
        )
        vertical.configure(command=self.tree.yview)
        horizontal.configure(command=self.tree.xview)
        vertical.pack(side=tk.RIGHT, fill=tk.Y)
        horizontal.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for column, label, width, stretch, anchor in (
            ("use", "Use", 48, False, tk.CENTER),
            ("location", "Location", 350, True, tk.W),
            ("storage", "Storage", 135, False, tk.W),
            ("status", "Status", 180, True, tk.W),
        ):
            self.tree.heading(column, text=label)
            self.tree.column(
                column,
                width=width,
                minwidth=width,
                stretch=stretch,
                anchor=anchor,
            )
        self.tree.tag_configure("unavailable", foreground="#777777")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._render_review())
        self.tree.bind("<ButtonRelease-1>", self._tree_clicked)
        self.tree.bind("<space>", self._toggle_event)
        self.tree.bind("<Return>", self._toggle_event)

        detail_frame = ttk.Frame(review, padding=(0, 8, 0, 0))
        review.add(detail_frame, weight=2)
        ttk.Label(
            detail_frame,
            text="Reviewed placement effects",
            style="Heading.TLabel",
        ).pack(anchor=tk.W)
        detail_scrollbar = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL)
        self.detail = tk.Text(
            detail_frame,
            height=7,
            wrap=tk.WORD,
            padx=8,
            pady=6,
            yscrollcommand=detail_scrollbar.set,
        )
        detail_scrollbar.configure(command=self.detail.yview)
        detail_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(4, 0))
        self.detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(4, 0))
        self.detail.configure(state=tk.DISABLED)

        self.status_var = tk.StringVar(value="Loading configured menu locations…")
        self.status_label = ttk.Label(
            outer,
            textvariable=self.status_var,
            style="Status.TLabel",
            wraplength=740,
            justify=tk.LEFT,
        )
        self.status_label.grid(row=6, column=0, sticky=tk.EW, pady=(7, 0))

        self.footer = ttk.Frame(outer)
        self.footer.grid(row=7, column=0, sticky=tk.EW, pady=(8, 0))
        self.apply_button = ttk.Button(
            self.footer,
            text="No changes",
            command=self.apply_changes,
            state=tk.DISABLED,
            style="Accent.TButton",
        )
        self.apply_button.pack(side=tk.LEFT)
        ttk.Button(self.footer, text="Close", command=self.close).pack(side=tk.RIGHT)

        self.search_var.trace_add("write", lambda *_args: self._render_locations())
        self._load_inventory(initial=True)
        self.window.transient(parent.winfo_toplevel())
        self.window.lift()
        self.window.after_idle(self.search_entry.focus_set)

    def _service_kwargs(self) -> dict[str, Path]:
        return {
            "shared_actions_path": self.shared_actions_path,
            "local_actions_path": self.local_actions_path,
            "shared_command_surface_path": self.shared_command_surface_path,
            "local_command_surface_path": self.local_command_surface_path,
        }

    def _load_inventory(self, *, initial: bool = False) -> bool:
        try:
            inventory = configured_action_placement_inventory(
                self.action.id,
                **self._service_kwargs(),
            )
        except (ConfiguredPlacementError, OSError) as exc:
            self.inventory = None
            self.plan = None
            self.review_locked = True
            self._transition_message = (
                "Configured placements could not be loaded. Close this window "
                "and refresh Configure before trying again."
            )
            self.status_var.set(self._transition_message)
            self._render_locations()
            self._render_review()
            self._update_controls()
            if initial:
                messagebox.showerror(
                    "Quick-action placements are unavailable",
                    str(exc),
                    parent=self.window,
                )
            return False

        self.inventory = inventory
        self.locations = tuple(inventory.locations)
        self.location_by_key = {
            location.key: location for location in self.locations
        }
        self.current_locations = frozenset(inventory.current_locations)
        self.desired_locations = set(inventory.current_locations)
        self.action_storage_var.set(_storage_label(inventory.action_storage))
        self.review_locked = False
        self.plan = None
        self._transition_message = ""
        return self._replan(show_error=not initial)

    def _ordered_desired_locations(self) -> tuple[ConfiguredPlacementKey, ...]:
        return tuple(
            location.key
            for location in self.locations
            if location.key in self.desired_locations
        )

    def _replan(self, *, show_error: bool = True) -> bool:
        if self.review_locked:
            self.plan = None
            self._render_locations()
            self._render_review()
            self._update_controls()
            return False
        try:
            reviewed_plan = plan_configured_action_placements(
                self.action.id,
                self._ordered_desired_locations(),
                **self._service_kwargs(),
            )
        except (ConfiguredPlacementError, OSError) as exc:
            self.plan = None
            self._transition_message = "The selected placements could not be reviewed."
            if show_error:
                messagebox.showerror(
                    "Placement changes could not be reviewed",
                    str(exc),
                    parent=self.window,
                )
        else:
            if (
                tuple(reviewed_plan.locations) != self.locations
                or frozenset(reviewed_plan.current_locations)
                != self.current_locations
            ):
                self.plan = None
                self.review_locked = True
                self._transition_message = (
                    "Configured placements changed while this window was open. "
                    "Configure was refreshed; close and reopen Placements before "
                    "making another change."
                )
                self._request_refresh_once()
            else:
                self.plan = reviewed_plan
                self._transition_message = ""
        self._render_locations()
        self._render_review()
        self._update_controls()
        return self.plan is not None

    def _location_text(self, location: ConfiguredPlacementLocation) -> str:
        return " > ".join(location.menu_path) or location.key.group_id

    def _status_for(self, location: ConfiguredPlacementLocation) -> str:
        current = location.key in self.current_locations
        desired = location.key in self.desired_locations
        if current and not desired:
            return "Will remove"
        if not current and desired:
            return "Will add"
        if current:
            return "Assigned"
        if not location.assignable:
            return location.unavailable_reason or "Unavailable"
        return "Available"

    def _visible_locations(self) -> tuple[ConfiguredPlacementLocation, ...]:
        terms = tuple(
            term.casefold() for term in self.search_var.get().split() if term.strip()
        )
        if not terms:
            return self.locations
        return tuple(
            location
            for location in self.locations
            if all(
                term
                in " ".join(
                    (
                        self._location_text(location),
                        _storage_label(location.key.storage),
                        self._status_for(location),
                        location.unavailable_reason,
                        location.reference_mode,
                    )
                ).casefold()
                for term in terms
            )
        )

    def _render_locations(self) -> None:
        selected_key = self.selected_key()
        self.tree.delete(*self.tree.get_children(""))
        self.key_by_iid.clear()
        self.iid_by_key.clear()
        visible = self._visible_locations()
        for index, location in enumerate(visible):
            iid = f"placement-{index}"
            self.key_by_iid[iid] = location.key
            self.iid_by_key[location.key] = iid
            desired = location.key in self.desired_locations
            self.tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    "[x]" if desired else "—" if not location.assignable else "[ ]",
                    self._location_text(location),
                    _storage_label(location.key.storage),
                    self._status_for(location),
                ),
                tags=("unavailable",) if not location.assignable and not desired else (),
            )
        preferred_iid = self.iid_by_key.get(selected_key) if selected_key else None
        if preferred_iid is None and visible:
            preferred_iid = self.iid_by_key[visible[0].key]
        if preferred_iid is not None:
            self.tree.selection_set(preferred_iid)
            self.tree.focus(preferred_iid)
            self.tree.see(preferred_iid)
        self.count_var.set(
            f"{len(visible)} of {len(self.locations)} location"
            f"{'s' if len(self.locations) != 1 else ''}"
        )

    def selected_key(self) -> ConfiguredPlacementKey | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self.key_by_iid.get(selection[0])

    def toggle_selected(self) -> None:
        if self.submitting or self.review_locked:
            return
        key = self.selected_key()
        if key is None:
            return
        location = self.location_by_key[key]
        if key in self.desired_locations:
            self.desired_locations.remove(key)
        elif location.assignable:
            self.desired_locations.add(key)
        else:
            self._transition_message = (
                location.unavailable_reason
                or "This Action cannot be added to that configured menu."
            )
            self.status_var.set(self._transition_message)
            return
        self._replan()

    def _tree_clicked(self, event: tk.Event) -> None:
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        self.toggle_selected()

    def _toggle_event(self, _event: tk.Event | None = None) -> str:
        self.toggle_selected()
        return "break"

    def _location_for_key(
        self,
        key: ConfiguredPlacementKey,
    ) -> ConfiguredPlacementLocation | None:
        if self.plan is not None:
            for location in self.plan.locations:
                if location.key == key:
                    return location
        return self.location_by_key.get(key)

    def _effect_location_line(self, key: ConfiguredPlacementKey) -> str:
        location = self._location_for_key(key)
        if location is None:
            return f"{_storage_label(key.storage)} · {key.group_id}"
        return (
            f"{_storage_label(key.storage)} · "
            f"{self._location_text(location)}"
        )

    def _render_review(self) -> None:
        lines = [
            f"Action: {self.action.title}",
            f"Automatic placement unchanged: {self.automatic_placement_var.get()}",
            "",
        ]
        if self.review_locked:
            lines.append(
                "This review is disabled until Configure is refreshed and the window is reopened."
            )
        elif self.plan is None:
            lines.append("No valid configured-placement review is available.")
        else:
            additions = tuple(self.plan.additions)
            removals = tuple(self.plan.removals)
            lines.append(
                f"Configured placements after apply: {len(self.plan.desired_locations)}"
            )
            lines.append("")
            lines.append(f"Add ({len(additions)}):")
            lines.extend(
                (f"  {self._effect_location_line(key)}" for key in additions),
            )
            if not additions:
                lines.append("  None")
            lines.append("")
            lines.append(f"Remove ({len(removals)}):")
            lines.extend(
                (f"  {self._effect_location_line(key)}" for key in removals),
            )
            if not removals:
                lines.append("  None")
            lines.extend(
                (
                    "",
                    f"Empty Quick-action items/branches pruned: {self.plan.items_pruned}",
                    f"  Built-in: {self.plan.shared_items_pruned}",
                    f"  My configuration: {self.plan.local_items_pruned}",
                    f"Reference changes · Built-in: {self.plan.shared_reference_changes}"
                    f" · My configuration: {self.plan.local_reference_changes}",
                    f"Configuration files to write: {self.plan.files_to_write}",
                )
            )
            if (
                self.plan.shared_reference_changes
                or self.plan.shared_items_pruned
            ):
                lines.extend(
                    (
                        "",
                        "Built-in Quick-action changes are Git-tracked and can "
                        "reach other computers after commit and pull.",
                    )
                )

        key = self.selected_key()
        location = self.location_by_key.get(key) if key is not None else None
        if location is not None:
            lines.extend(
                (
                    "",
                    "Selected location:",
                    f"  {self._location_text(location)}",
                    f"  Storage: {_storage_label(location.key.storage)}",
                    f"  Existing Action targets: {location.action_target_count}",
                    f"  Existing Work Item targets: {location.work_item_target_count}",
                    f"  Child menus: {location.child_menu_count}",
                )
            )
            if not location.assignable and location.unavailable_reason:
                lines.append(f"  Unavailable: {location.unavailable_reason}")
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        self.detail.insert("1.0", "\n".join(lines))
        self.detail.configure(state=tk.DISABLED)

    def _update_controls(self) -> None:
        change_count = 0
        if self.plan is not None:
            change_count = len(self.plan.additions) + len(self.plan.removals)
        self.apply_button.configure(
            text=(
                f"Apply {change_count} placement "
                f"change{'s' if change_count != 1 else ''}"
                if change_count
                else "No changes"
            ),
            state=(
                tk.NORMAL
                if change_count
                and not self.submitting
                and not self.review_locked
                else tk.DISABLED
            ),
        )
        if self._transition_message:
            self.status_var.set(self._transition_message)
        elif self.plan is None:
            self.status_var.set("Configured placement changes are not ready for review.")
        elif change_count:
            self.status_var.set(
                f"{change_count} placement change"
                f"{'s' if change_count != 1 else ''} ready. Review the exact effects."
            )
        else:
            self.status_var.set("No configured placement changes selected.")

    def apply_changes(self) -> None:
        if (
            self.submitting
            or self.review_locked
            or self.plan is None
            or not self.plan.additions
            and not self.plan.removals
        ):
            return
        reviewed_plan = self.plan
        self.submitting = True
        self._transition_message = "Applying the reviewed configured placements…"
        self._update_controls()
        self.window.update_idletasks()
        try:
            result = commit_configured_action_placements(reviewed_plan)
        except ConfiguredPlacementError as exc:
            self.submitting = False
            if exc.rollback_completed is True:
                self._transition_message = (
                    "Placement changes failed, but all attempted writes were restored."
                )
                self._load_inventory()
                messagebox.showerror(
                    "Placement changes were not applied",
                    str(exc),
                    parent=self.window,
                )
                return
            self._lock_after_invalidated_review(str(exc))
            messagebox.showerror(
                "Placement outcome requires refresh",
                str(exc),
                parent=self.window,
            )
            return
        except OSError as exc:
            self.submitting = False
            self._lock_after_invalidated_review(str(exc))
            messagebox.showerror(
                "Placement outcome requires refresh",
                str(exc),
                parent=self.window,
            )
            return

        self.submitting = False
        self.on_change()
        applied = len(result.additions) + len(result.removals)
        if not self._load_inventory():
            self._request_refresh_once()
            return
        self._transition_message = (
            f"Applied {applied} configured placement "
            f"change{'s' if applied != 1 else ''}."
        )
        self._render_locations()
        self._render_review()
        self._update_controls()

    def _lock_after_invalidated_review(self, message: str) -> None:
        self.review_locked = True
        self.plan = None
        self._transition_message = (
            "The reviewed configuration is stale or its write outcome is not "
            "safe to continue from. Configure was refreshed; close and reopen "
            f"this window before making another change. {message}"
        )
        self._render_locations()
        self._render_review()
        self._update_controls()
        self._request_refresh_once()

    def _request_refresh_once(self) -> None:
        if self.refresh_requested:
            return
        self.refresh_requested = True
        self.on_refresh()

    def close(self) -> None:
        self.window.destroy()

    def _focus_search(self, _event: tk.Event | None = None) -> str:
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, tk.END)
        return "break"
