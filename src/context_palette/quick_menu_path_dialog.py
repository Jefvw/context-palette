from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Iterable

from .actions import (
    ACTION_BOUND_QUICK_MENU_SPECS,
    MAX_QUICK_ACTION_PATH_LEVELS,
    Action,
    ActionError,
    normalize_quick_action_path,
)
from .action_configured_placement import (
    ConfiguredPlacementKey,
    ConfiguredPlacementLocation,
)
from .window_geometry import place_child_window


@dataclass(frozen=True)
class QuickMenuPathNode:
    """One selectable location in an automatic action-bound Quick menu."""

    label: str
    path: tuple[str, ...]
    direct_action_count: int
    total_action_count: int
    current: bool = False
    children: tuple[QuickMenuPathNode, ...] = ()


@dataclass(frozen=True)
class QuickMenuPlacementSelection:
    """One staged automatic path plus optional configured-menu locations."""

    automatic_path: tuple[str, ...]
    configured_location_keys: tuple[ConfiguredPlacementKey, ...] = ()


class _MutablePathNode:
    def __init__(self, label: str, path: tuple[str, ...]) -> None:
        self.label = label
        self.path = path
        self.direct_action_count = 0
        self.current = False
        self.children: dict[str, _MutablePathNode] = {}


def quick_menu_root_label(action_type: str) -> str:
    """Return the fixed automatic-menu label owned by one Action type."""

    for _group_id, label, candidate_type in ACTION_BOUND_QUICK_MENU_SPECS:
        if candidate_type == action_type:
            return label
    raise ValueError(f"Unsupported automatic Quick-menu Action type: {action_type}")


def quick_menu_path_tree(
    actions: Iterable[Action],
    *,
    action_type: str,
    current_path: Iterable[str] = (),
) -> QuickMenuPathNode:
    """Build the canonical, launcher-compatible path tree for one menu.

    Active Actions establish existing branches and their counts. The supplied
    current path is injected when necessary so a legacy inactive or newly proposed
    location never disappears from the chooser.
    """

    root_label = quick_menu_root_label(action_type)
    root = _MutablePathNode(root_label, ())
    for action in actions:
        if action.type != action_type or action.state == "Archived":
            continue
        node = root
        for raw_label in action.quick_action_path:
            key = raw_label.casefold()
            child = node.children.get(key)
            if child is None:
                child = _MutablePathNode(raw_label, (*node.path, raw_label))
                node.children[key] = child
            node = child
        node.direct_action_count += 1

    normalized_current = normalize_quick_action_path(current_path)
    current_node = root
    canonical_current: list[str] = []
    for raw_label in normalized_current:
        key = raw_label.casefold()
        child = current_node.children.get(key)
        if child is None:
            child = _MutablePathNode(
                raw_label,
                (*current_node.path, raw_label),
            )
            current_node.children[key] = child
        canonical_current.append(child.label)
        current_node = child
    current_node.current = True

    def freeze(node: _MutablePathNode) -> QuickMenuPathNode:
        children = tuple(freeze(child) for child in node.children.values())
        return QuickMenuPathNode(
            label=node.label,
            path=node.path,
            direct_action_count=node.direct_action_count,
            total_action_count=(
                node.direct_action_count
                + sum(child.total_action_count for child in children)
            ),
            current=node.current,
            children=children,
        )

    return freeze(root)


def _walk_nodes(root: QuickMenuPathNode) -> tuple[QuickMenuPathNode, ...]:
    values: list[QuickMenuPathNode] = []

    def visit(node: QuickMenuPathNode) -> None:
        values.append(node)
        for child in node.children:
            visit(child)

    visit(root)
    return tuple(values)


def _matching_paths(
    root: QuickMenuPathNode,
    query: str,
) -> set[tuple[str, ...]]:
    terms = tuple(part.casefold() for part in query.split() if part.strip())
    if not terms:
        return {node.path for node in _walk_nodes(root)}

    visible: set[tuple[str, ...]] = {()}

    def add_subtree(node: QuickMenuPathNode) -> None:
        visible.add(node.path)
        for child in node.children:
            add_subtree(child)

    def visit(node: QuickMenuPathNode, ancestor_matches: bool = False) -> bool:
        searchable = " > ".join((root.label, *node.path))
        if not node.path:
            searchable += " menu root"
        matches = ancestor_matches or all(term in searchable.casefold() for term in terms)
        descendant_matches = False
        if matches:
            add_subtree(node)
            return True
        for child in node.children:
            if visit(child):
                descendant_matches = True
        if descendant_matches:
            visible.add(node.path)
        return descendant_matches

    visit(root)
    return visible


def _count_label(node: QuickMenuPathNode) -> str:
    if node.total_action_count == 0:
        return "No Active Actions here"
    direct = node.direct_action_count
    total = node.total_action_count
    if direct == total:
        return f"{direct} Action{'s' if direct != 1 else ''} here"
    if direct == 0:
        return f"{total} Actions in branch"
    return f"{direct} here · {total} in branch"


def _configured_key_identity(
    key: ConfiguredPlacementKey,
) -> tuple[str, str, tuple[str, ...]]:
    return (
        key.storage.casefold(),
        key.group_id.casefold(),
        tuple(item_id.casefold() for item_id in key.item_id_path),
    )


def _configured_storage_label(storage: str) -> str:
    if storage.casefold() == "local":
        return "My configuration"
    if storage.casefold() == "shared":
        return "Built-in"
    return storage


class QuickMenuPathDialog:
    """Choose automatic and optional configured locations for one Action.

    ``on_select`` remains as a temporary path-only compatibility callback.
    New callers supply ``on_select_placements`` and receive one staged result;
    this dialog never persists either placement model itself.
    """

    def __init__(
        self,
        parent: tk.Misc,
        *,
        action_type: str,
        actions: Iterable[Action],
        current_path: Iterable[str] = (),
        configured_locations: Iterable[ConfiguredPlacementLocation] = (),
        selected_configured_location_keys: (
            Iterable[ConfiguredPlacementKey] | None
        ) = None,
        on_select_placements: (
            Callable[[QuickMenuPlacementSelection], None] | None
        ) = None,
        on_select: Callable[[tuple[str, ...]], None] | None = None,
        dialog_title: str | None = None,
        instructions: str | None = None,
        use_label: str | None = None,
        allow_new_submenu: bool = True,
    ) -> None:
        if (on_select is None) == (on_select_placements is None):
            raise ValueError(
                "Provide exactly one Quick-menu placement result callback."
            )
        self.parent = parent
        self.action_type = action_type
        self.actions = tuple(actions)
        self.on_select = on_select
        self.on_select_placements = on_select_placements
        self.placement_mode = on_select_placements is not None
        self.allow_new_submenu = allow_new_submenu
        self.configured_locations = tuple(configured_locations)
        self.configured_location_by_key = {
            location.key: location for location in self.configured_locations
        }
        if len(self.configured_location_by_key) != len(self.configured_locations):
            raise ValueError("Configured Quick-menu locations must be unique.")
        selected_identities = (
            {
                _configured_key_identity(key)
                for key in selected_configured_location_keys
            }
            if selected_configured_location_keys is not None
            else {
                _configured_key_identity(location.key)
                for location in self.configured_locations
                if location.assigned
            }
        )
        self.selected_configured_location_keys: set[ConfiguredPlacementKey] = {
            location.key
            for location in self.configured_locations
            if _configured_key_identity(location.key) in selected_identities
        }
        self.configured_key_by_iid: dict[str, ConfiguredPlacementKey] = {}
        self.configured_iid_by_key: dict[ConfiguredPlacementKey, str] = {}
        self.root_label = quick_menu_root_label(action_type)
        self.path_tree = quick_menu_path_tree(
            self.actions,
            action_type=action_type,
            current_path=current_path,
        )
        current_node = next(
            node for node in _walk_nodes(self.path_tree) if node.current
        )
        self.current_path = current_node.path
        self.path_by_iid: dict[str, tuple[str, ...]] = {}
        self.iid_by_path: dict[tuple[str, ...], str] = {}
        self.closed = False
        self.previous_grab = parent.grab_current()

        self.window = tk.Toplevel(parent)
        self.window.title(
            dialog_title
            or (
                "Choose menu locations"
                if self.placement_mode
                else f"Choose location in {self.root_label}"
            )
        )
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self._close_event())
        self.window.bind("<Control-f>", self._focus_search)
        self.window.bind("<Control-n>", self._new_submenu_event)
        self.window.transient(parent.winfo_toplevel())

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        self.controls_frame = ttk.Frame(outer)
        self.controls_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        self.use_button = ttk.Button(
            self.controls_frame,
            text=(
                use_label
                or (
                    "Use these placements"
                    if self.placement_mode
                    else "Use this location"
                )
            ),
            command=self.use_selected,
            style="Accent.TButton",
        )
        self.use_button.pack(side=tk.LEFT)
        self.new_submenu_button = ttk.Button(
            self.controls_frame,
            text="New submenu…",
            command=self.new_submenu,
        )
        if self.allow_new_submenu:
            self.new_submenu_button.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            self.controls_frame,
            text="Cancel",
            command=self.close,
        ).pack(side=tk.RIGHT)

        body = ttk.Frame(outer)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            body,
            text=(
                instructions
                or (
                    f"This Action always appears in {self.root_label}. Choose where "
                    f"inside {self.root_label} it appears, and optionally choose "
                    "other configured menus where it should also appear."
                    if self.placement_mode
                    else
                    f"Every matching Active Action appears automatically in "
                    f"{self.root_label}. Choose only its location inside that menu; "
                    "creating a submenu takes effect when the Action is saved."
                )
            ),
            wraplength=610,
        ).pack(fill=tk.X, pady=(0, 8))

        search_row = ttk.Frame(body)
        search_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(search_row, text="Find location").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        self.search_entry.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=(6, 8),
        )
        self.count_var = tk.StringVar()
        ttk.Label(
            search_row,
            textvariable=self.count_var,
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)

        if self.placement_mode:
            ttk.Label(
                body,
                text=f"In {self.root_label} (automatic)",
                style="Heading.TLabel",
            ).pack(fill=tk.X, pady=(2, 4))

        tree_frame = ttk.Frame(body)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("actions",),
            show="tree headings",
            selectmode="browse",
            height=7 if self.placement_mode else 10,
            yscrollcommand=scrollbar.set,
        )
        self.tree.heading("#0", text="Menu location")
        self.tree.heading("actions", text="Active Actions")
        self.tree.column("#0", width=330, minwidth=220)
        self.tree.column("actions", width=210, minwidth=160)
        scrollbar.configure(command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.tag_configure("current", background="#e8f5f1")

        self.selection_var = tk.StringVar()
        ttk.Label(
            body,
            textvariable=self.selection_var,
            style="Muted.TLabel",
            wraplength=610,
        ).pack(fill=tk.X, pady=(7, 0))

        if self.placement_mode:
            ttk.Separator(body).pack(fill=tk.X, pady=(8, 7))
            ttk.Label(
                body,
                text="Also show in these menus (optional)",
                style="Heading.TLabel",
            ).pack(fill=tk.X)
            ttk.Label(
                body,
                text=(
                    "Select zero, one, or several configured menu locations. "
                    "Unavailable locations stay visible so their storage rule "
                    "is clear."
                ),
                style="Muted.TLabel",
                wraplength=610,
            ).pack(fill=tk.X, pady=(2, 5))
            self._build_configured_tree(body)

        self.search_var.trace_add("write", lambda *_args: self._render())
        self.search_entry.bind("<Down>", self._focus_tree)
        self.search_entry.bind("<Return>", self._focus_tree)
        self.tree.bind("<Return>", lambda _event: self._use_event())
        self.tree.bind("<Double-1>", lambda _event: self._use_event())
        self.tree.bind(
            "<<TreeviewSelect>>",
            lambda _event: self._update_selection(),
        )

        self._render()
        place_child_window(
            self.window,
            parent,
            size=(820, 680) if self.placement_mode else (680, 520),
        )
        self.window.minsize(
            600 if self.placement_mode else 520,
            480 if self.placement_mode else 380,
        )
        self.window.grab_set()
        self.window.after_idle(self.search_entry.focus_set)

    def _render(
        self,
        preferred_path: tuple[str, ...] | None = None,
    ) -> None:
        selected = (
            preferred_path
            if preferred_path is not None
            else self.selected_path()
        )
        visible_paths = _matching_paths(self.path_tree, self.search_var.get())
        if self.placement_mode:
            # The shared Find field also searches configured locations. Keep
            # the staged automatic selection visible so a configured-only
            # query cannot silently replace it with the automatic menu root.
            retained_path = selected if selected is not None else self.current_path
            visible_paths.update(
                retained_path[:level]
                for level in range(len(retained_path) + 1)
            )
        self.tree.delete(*self.tree.get_children(""))
        self.path_by_iid.clear()
        self.iid_by_path.clear()
        counter = 0

        def insert(node: QuickMenuPathNode, parent_iid: str) -> None:
            nonlocal counter
            if node.path not in visible_paths:
                return
            counter += 1
            iid = f"location-{counter}"
            self.path_by_iid[iid] = node.path
            self.iid_by_path[node.path] = iid
            label = (
                f"{node.label} — menu root"
                if not node.path
                else node.label
            )
            self.tree.insert(
                parent_iid,
                tk.END,
                iid=iid,
                text=label,
                values=(_count_label(node),),
                tags=("current",) if node.current else (),
                open=True,
            )
            for child in node.children:
                insert(child, iid)

        insert(self.path_tree, "")
        preferred = selected if selected in self.iid_by_path else self.current_path
        if preferred not in self.iid_by_path:
            preferred = ()
        iid = self.iid_by_path.get(preferred)
        if iid is not None:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
        self.count_var.set(
            (
                f"{len(self.iid_by_path)} automatic · "
                f"{len(self._visible_configured_locations())} other"
                if self.placement_mode
                else
                f"{len(self.iid_by_path)} location"
                f"{'s' if len(self.iid_by_path) != 1 else ''}"
            )
        )
        if self.placement_mode:
            self._render_configured_locations()
        self._update_selection()

    def _build_configured_tree(self, parent: ttk.Frame) -> None:
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        self.configured_tree = ttk.Treeview(
            tree_frame,
            columns=("use", "location", "storage", "status"),
            show="headings",
            selectmode="browse",
            height=8,
            yscrollcommand=scrollbar.set,
        )
        scrollbar.configure(command=self.configured_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.configured_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for column, label, width, minimum, stretch, anchor in (
            ("use", "Use", 48, 40, False, tk.CENTER),
            ("location", "Menu location", 320, 180, True, tk.W),
            ("storage", "Storage", 135, 105, False, tk.W),
            ("status", "Status", 190, 140, True, tk.W),
        ):
            self.configured_tree.heading(column, text=label)
            self.configured_tree.column(
                column,
                width=width,
                minwidth=minimum,
                stretch=stretch,
                anchor=anchor,
            )
        self.configured_tree.tag_configure("unavailable", foreground="#777777")
        self.configured_tree.bind("<ButtonRelease-1>", self._configured_tree_clicked)
        self.configured_tree.bind("<space>", self._toggle_configured_event)
        self.configured_tree.bind("<Return>", self._toggle_configured_event)

    def _visible_configured_locations(
        self,
    ) -> tuple[ConfiguredPlacementLocation, ...]:
        terms = tuple(
            term.casefold()
            for term in self.search_var.get().split()
            if term.strip()
        )
        if not terms:
            return self.configured_locations
        return tuple(
            location
            for location in self.configured_locations
            if all(
                term
                in " ".join(
                    (
                        " > ".join(location.menu_path),
                        _configured_storage_label(location.key.storage),
                        self._configured_status(location),
                        location.unavailable_reason,
                    )
                ).casefold()
                for term in terms
            )
        )

    def _configured_status(self, location: ConfiguredPlacementLocation) -> str:
        selected = location.key in self.selected_configured_location_keys
        if selected and not location.assignable:
            return "Assigned · removal allowed"
        if selected:
            return "Selected"
        if not location.assignable:
            return location.unavailable_reason or "Unavailable"
        return "Available"

    def _render_configured_locations(self) -> None:
        if not self.placement_mode:
            return
        selected_key = self.selected_configured_key()
        self.configured_tree.delete(*self.configured_tree.get_children(""))
        self.configured_key_by_iid.clear()
        self.configured_iid_by_key.clear()
        visible = self._visible_configured_locations()
        for index, location in enumerate(visible):
            iid = f"configured-{index}"
            self.configured_key_by_iid[iid] = location.key
            self.configured_iid_by_key[location.key] = iid
            selected = location.key in self.selected_configured_location_keys
            self.configured_tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    "[x]" if selected else "—" if not location.assignable else "[ ]",
                    " > ".join(location.menu_path),
                    _configured_storage_label(location.key.storage),
                    self._configured_status(location),
                ),
                tags=("unavailable",) if not location.assignable and not selected else (),
            )
        preferred = (
            self.configured_iid_by_key.get(selected_key)
            if selected_key is not None
            else None
        )
        if preferred is None and visible:
            preferred = self.configured_iid_by_key[visible[0].key]
        if preferred is not None:
            self.configured_tree.selection_set(preferred)
            self.configured_tree.focus(preferred)
            self.configured_tree.see(preferred)

    def selected_configured_key(self) -> ConfiguredPlacementKey | None:
        if not self.placement_mode:
            return None
        selection = self.configured_tree.selection()
        if not selection:
            return None
        return self.configured_key_by_iid.get(selection[0])

    def toggle_selected_configured_location(self) -> None:
        key = self.selected_configured_key()
        if key is None:
            return
        location = self.configured_location_by_key[key]
        if key in self.selected_configured_location_keys:
            self.selected_configured_location_keys.remove(key)
        elif location.assignable:
            self.selected_configured_location_keys.add(key)
        else:
            return
        self._render_configured_locations()
        self._update_selection()

    def _toggle_configured_event(self, _event: tk.Event | None = None) -> str:
        self.toggle_selected_configured_location()
        return "break"

    def _configured_tree_clicked(self, event: tk.Event) -> None:
        if self.configured_tree.identify_region(event.x, event.y) != "cell":
            return
        if self.configured_tree.identify_column(event.x) != "#1":
            return
        iid = self.configured_tree.identify_row(event.y)
        if not iid:
            return
        self.configured_tree.selection_set(iid)
        self.configured_tree.focus(iid)
        self.toggle_selected_configured_location()

    def selected_path(self) -> tuple[str, ...] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self.path_by_iid.get(selection[0])

    def _update_selection(self) -> None:
        path = self.selected_path()
        if path is None:
            self.selection_var.set("Choose a menu location.")
            self.use_button.configure(state=tk.DISABLED)
            self.new_submenu_button.configure(state=tk.DISABLED)
            return
        complete_path = " > ".join((self.root_label, *path))
        if not path:
            complete_path = f"{self.root_label} menu root"
        if self.placement_mode:
            configured_count = len(self.selected_configured_location_keys)
            self.selection_var.set(
                f"Automatic: {complete_path} · Also in: "
                f"{configured_count} configured location"
                f"{'s' if configured_count != 1 else ''}"
            )
        else:
            self.selection_var.set(f"Selected location: {complete_path}")
        self.use_button.configure(state=tk.NORMAL)
        self.new_submenu_button.configure(
            state=(
                tk.NORMAL
                if len(path) < MAX_QUICK_ACTION_PATH_LEVELS
                else tk.DISABLED
            )
        )

    def use_selected(self) -> None:
        path = self.selected_path()
        if path is None:
            return
        if self.on_select_placements is not None:
            ordered_keys = tuple(
                location.key
                for location in self.configured_locations
                if location.key in self.selected_configured_location_keys
            )
            self.on_select_placements(
                QuickMenuPlacementSelection(path, ordered_keys)
            )
        else:
            assert self.on_select is not None
            self.on_select(path)
        self.close()

    def new_submenu(self) -> None:
        if not self.allow_new_submenu:
            return
        parent_path = self.selected_path()
        if parent_path is None:
            return
        if len(parent_path) >= MAX_QUICK_ACTION_PATH_LEVELS:
            messagebox.showinfo(
                "Maximum menu depth",
                f"Automatic Quick menus support at most "
                f"{MAX_QUICK_ACTION_PATH_LEVELS} submenu levels.",
                parent=self.window,
            )
            return
        QuickMenuSubmenuNameDialog(
            self.window,
            root_label=self.root_label,
            parent_path=parent_path,
            on_submit=lambda name: self._accept_new_submenu(parent_path, name),
        )

    def _accept_new_submenu(
        self,
        parent_path: tuple[str, ...],
        name: str,
    ) -> None:
        proposed = normalize_quick_action_path((*parent_path, name))
        parent_node = next(
            node for node in _walk_nodes(self.path_tree) if node.path == parent_path
        )
        existing = next(
            (
                child
                for child in parent_node.children
                if child.label.casefold() == proposed[-1].casefold()
            ),
            None,
        )
        if existing is not None:
            proposed = existing.path
        self.current_path = proposed
        self.path_tree = quick_menu_path_tree(
            self.actions,
            action_type=self.action_type,
            current_path=proposed,
        )
        current_node = next(
            node for node in _walk_nodes(self.path_tree) if node.current
        )
        self.current_path = current_node.path
        self.search_var.set("")
        self._render(self.current_path)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            if self.window.grab_current() is self.window:
                self.window.grab_release()
        except tk.TclError:
            pass
        self.window.destroy()
        if self.previous_grab is not None:
            try:
                if self.previous_grab.winfo_exists():
                    self.previous_grab.grab_set()
            except tk.TclError:
                pass

    def _focus_search(self, _event: tk.Event | None = None) -> str:
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, tk.END)
        return "break"

    def _focus_tree(self, _event: tk.Event | None = None) -> str:
        if self.tree.selection():
            self.tree.focus_set()
        return "break"

    def _use_event(self) -> str:
        self.use_selected()
        return "break"

    def _new_submenu_event(self, _event: tk.Event | None = None) -> str:
        self.new_submenu()
        return "break"

    def _close_event(self) -> str:
        self.close()
        return "break"


class QuickMenuSubmenuNameDialog:
    """Collect one normalized automatic submenu level without persisting it."""

    def __init__(
        self,
        parent: tk.Toplevel,
        *,
        root_label: str,
        parent_path: tuple[str, ...],
        on_submit: Callable[[str], None],
        title: str = "New automatic submenu",
        submit_label: str = "Use new submenu",
        context_label: str = "Create under",
        initial_name: str = "",
        error_title: str = "Submenu name is invalid",
    ) -> None:
        self.parent = parent
        self.on_submit = on_submit
        self.error_title = error_title
        self.previous_grab = parent.grab_current()
        self.closed = False
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self._close_event())
        self.window.transient(parent)

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        controls = ttk.Frame(outer)
        controls.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        ttk.Button(
            controls,
            text=submit_label,
            command=self.submit,
            style="Accent.TButton",
        ).pack(side=tk.LEFT)
        ttk.Button(controls, text="Cancel", command=self.close).pack(side=tk.RIGHT)

        body = ttk.Frame(outer)
        body.pack(fill=tk.BOTH, expand=True)
        parent_label = " > ".join((root_label, *parent_path))
        ttk.Label(
            body,
            text=f"{context_label}: {parent_label}",
            style="Muted.TLabel",
            wraplength=440,
        ).pack(fill=tk.X, pady=(0, 8))
        ttk.Label(body, text="Submenu name").pack(anchor=tk.W)
        self.name_var = tk.StringVar(value=initial_name)
        self.name_entry = ttk.Entry(body, textvariable=self.name_var)
        self.name_entry.pack(fill=tk.X, pady=(3, 0))
        self.name_entry.bind("<Return>", lambda _event: self._submit_event())

        place_child_window(self.window, parent, size=(480, 190))
        self.window.resizable(True, False)
        self.window.grab_set()
        self.window.after_idle(self._focus_name)

    def _focus_name(self) -> None:
        self.name_entry.focus_set()
        self.name_entry.selection_range(0, tk.END)

    def submit(self) -> None:
        raw_name = self.name_var.get()
        try:
            normalized = normalize_quick_action_path((raw_name,))
        except ActionError as exc:
            messagebox.showerror(
                self.error_title,
                str(exc),
                parent=self.window,
            )
            return
        if not normalized:
            messagebox.showerror(
                self.error_title,
                "Enter a submenu name.",
                parent=self.window,
            )
            return
        self.on_submit(normalized[0])
        self.close()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            if self.window.grab_current() is self.window:
                self.window.grab_release()
        except tk.TclError:
            pass
        self.window.destroy()
        if self.previous_grab is not None:
            try:
                if self.previous_grab.winfo_exists():
                    self.previous_grab.grab_set()
            except tk.TclError:
                pass

    def _submit_event(self) -> str:
        self.submit()
        return "break"

    def _close_event(self) -> str:
        self.close()
        return "break"
