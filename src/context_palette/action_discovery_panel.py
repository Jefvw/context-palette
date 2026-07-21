from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from .action_types import ACTION_TYPES
from .style import COLORS
from .tooltips import ListboxItemTooltip, TreeviewItemTooltip


TooltipText = str | Callable[[], str]


class ActionDiscoveryPanel:
    """Search and result widgets with launcher-owned discovery policy callbacks."""

    def __init__(
        self,
        parent: ttk.Panedwindow,
        *,
        heading_var: tk.StringVar,
        count_var: tk.StringVar,
        search_var: tk.StringVar,
        action_type_filter_var: tk.StringVar,
        tag_filter_var: tk.StringVar,
        tooltip_adder: Callable[[tk.Widget, TooltipText], None],
        keypress_handler: Callable[[tk.Event], object],
        execute_selected: Callable[[], None],
        update_preview: Callable[[], None],
        toggle_password_actions: Callable[[], None],
        select_action_type_filter: Callable[[str | None], None],
        select_tag_filter: Callable[[str | None], None],
        show_help: Callable[[], None],
        result_tooltip_text: Callable[[int], str],
        focus_tree_tooltip_text: Callable[[str], str],
        configure_flat_action: Callable[[tk.Event], object],
        configure_focus_action: Callable[[tk.Event], object],
    ) -> None:
        self.frame = ttk.Frame(parent)
        parent.add(self.frame, weight=1)

        header = ttk.Frame(self.frame)
        header.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(
            header,
            textvariable=heading_var,
            style="PaneHeader.TLabel",
        ).pack(side=tk.LEFT)
        ttk.Label(
            header,
            textvariable=count_var,
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)

        search_row = ttk.Frame(self.frame)
        search_row.pack(fill=tk.X, pady=(0, 5))
        find_label = ttk.Label(search_row, text="Find action", style="Heading.TLabel")
        find_label.pack(anchor=tk.W)
        tooltip_adder(
            find_label,
            "Type any tag, context, action name, type, or content.",
        )
        self.search_entry = ttk.Entry(
            search_row,
            textvariable=search_var,
            font=("Segoe UI", 11),
        )
        self.search_entry.pack(fill=tk.X, pady=(3, 0))
        self.search_entry.focus_set()
        self.search_entry.bind("<KeyPress>", keypress_handler)
        self.search_entry.bind("<Return>", lambda _event: execute_selected())

        body = ttk.Frame(self.frame)
        body.pack(fill=tk.BOTH, expand=True)
        self.tool_rail = ttk.Frame(body, width=88)
        self.tool_rail.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))
        self.tool_rail.pack_propagate(False)

        self.passwords_button = ttk.Button(
            self.tool_rail,
            text="Passwords",
            command=toggle_password_actions,
            style="Compact.TButton",
        )
        self.passwords_button.pack(fill=tk.X)
        tooltip_adder(
            self.passwords_button,
            "Passwords — Show only protected Windows Credential Manager actions. Activate again to show all actions.",
        )

        self.type_filter = ttk.Menubutton(
            self.tool_rail,
            text="Types ▾",
            style="Compact.TButton",
        )
        self.type_filter.pack(fill=tk.X, pady=(5, 0))
        type_menu = tk.Menu(self.type_filter, tearoff=False)
        type_menu.add_radiobutton(
            label="All types",
            variable=action_type_filter_var,
            value="All types",
            command=lambda: select_action_type_filter(None),
        )
        type_menu.add_separator()
        for action_type, definition in ACTION_TYPES.items():
            type_menu.add_radiobutton(
                label=definition.label,
                variable=action_type_filter_var,
                value=definition.label,
                command=lambda selected=action_type: select_action_type_filter(selected),
            )
        self.type_filter.configure(menu=type_menu)
        tooltip_adder(
            self.type_filter,
            "Types — Filter the action list by any built-in action type, or show all types.",
        )

        self.tag_filter_var = tag_filter_var
        self.select_tag_filter = select_tag_filter
        self.tag_filter = ttk.Menubutton(
            self.tool_rail,
            text="Tags ▾",
            style="Compact.TButton",
        )
        self.tag_filter.pack(fill=tk.X, pady=(5, 0))
        tooltip_adder(
            self.tag_filter,
            "Tags — Narrow actions by a reusable descriptive tag.",
        )
        self.set_tags(())

        self.run_button = ttk.Button(
            self.tool_rail,
            text="Run",
            command=execute_selected,
            style="Accent.TButton",
        )
        self.run_button.pack(fill=tk.X, pady=(12, 0))
        tooltip_adder(
            self.run_button,
            "Execute the highlighted action. Its input and effect appear in Action info below.",
        )
        self.help_button = ttk.Button(
            self.tool_rail,
            text="?",
            width=3,
            command=show_help,
            style="Compact.TButton",
        )
        self.help_button.pack(fill=tk.X, pady=(5, 0))
        tooltip_adder(
            self.help_button,
            "Search globally across tags, contexts, action names, types, and content.",
        )

        self.list_frame = ttk.Frame(body)
        self.list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar = ttk.Scrollbar(self.list_frame, orient=tk.VERTICAL)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.results = tk.Listbox(
            self.list_frame,
            activestyle="dotbox",
            font=("Segoe UI", 10),
            selectmode=tk.BROWSE,
            yscrollcommand=self.scrollbar.set,
            borderwidth=1,
            relief=tk.SOLID,
            highlightthickness=1,
            highlightcolor=COLORS["focus"],
            highlightbackground=COLORS["border"],
        )
        self.results.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.configure(command=self.results.yview)
        self.results.bind("<KeyPress>", keypress_handler)
        self.results.bind("<<ListboxSelect>>", lambda _event: update_preview())
        self.results.bind("<Double-Button-1>", lambda _event: execute_selected())
        self.results.bind("<Return>", lambda _event: execute_selected())
        self.results.bind("<Button-3>", configure_flat_action)
        self.results_tooltip = ListboxItemTooltip(
            self.results,
            result_tooltip_text,
        )

        self.focus_tree = ttk.Treeview(
            self.list_frame,
            show="tree",
            selectmode="browse",
        )
        self.focus_tree.bind("<<TreeviewSelect>>", lambda _event: update_preview())
        self.focus_tree.bind("<Double-Button-1>", lambda _event: execute_selected())
        self.focus_tree.bind("<Return>", lambda _event: execute_selected())
        self.focus_tree.bind("<Button-3>", configure_focus_action)
        self.focus_tree_tooltip = TreeviewItemTooltip(
            self.focus_tree,
            focus_tree_tooltip_text,
        )

    def set_tags(self, tags: tuple[str, ...]) -> None:
        previous_menu = getattr(self, "tag_menu", None)
        if previous_menu is not None:
            previous_menu.destroy()
        menu = tk.Menu(self.tag_filter, tearoff=False)
        menu.add_radiobutton(
            label="All tags",
            variable=self.tag_filter_var,
            value="All tags",
            command=lambda: self.select_tag_filter(None),
        )
        if tags:
            menu.add_separator()
        for tag in tags:
            menu.add_radiobutton(
                label=tag,
                variable=self.tag_filter_var,
                value=tag,
                command=lambda selected=tag: self.select_tag_filter(selected),
            )
        self.tag_filter.configure(menu=menu)
        self.tag_menu = menu
