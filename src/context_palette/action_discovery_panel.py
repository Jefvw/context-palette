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
        project_filter_var: tk.StringVar,
        work_tag_filter_var: tk.StringVar,
        tooltip_adder: Callable[[tk.Widget, TooltipText], None],
        keypress_handler: Callable[[tk.Event], object],
        execute_selected: Callable[..., None],
        update_preview: Callable[[], None],
        toggle_password_actions: Callable[[], None],
        toggle_work_items: Callable[[], None],
        create_work_item: Callable[[], None],
        send_work_item_inbox: Callable[[], None],
        select_action_type_filter: Callable[[str | None], None],
        select_tag_filter: Callable[[str | None], None],
        select_project_filter: Callable[[str | None], None],
        select_work_tag_filter: Callable[[str | None], None],
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
        self.find_label = ttk.Label(
            search_row, text="Find action", style="Heading.TLabel"
        )
        self.find_label.pack(anchor=tk.W)
        tooltip_adder(
            self.find_label,
            lambda: self.find_help_text,
        )
        self.find_help_text = "Type any tag, context, action name, type, or content."
        self.search_entry = ttk.Entry(
            search_row,
            textvariable=search_var,
            font=("Segoe UI", 11),
        )
        self.search_entry.pack(fill=tk.X, pady=(3, 0))
        self.search_entry.focus_set()
        self.search_entry.bind("<KeyPress>", keypress_handler)
        self.search_entry.bind(
            "<Shift-Return>",
            lambda _event: execute_selected(open_folder=True),
        )
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

        self.work_items_button = ttk.Button(
            self.tool_rail,
            text="Work",
            command=toggle_work_items,
            style="Compact.TButton",
        )
        self.work_items_button.pack(fill=tk.X, pady=(5, 0))
        tooltip_adder(
            self.work_items_button,
            "Work — Find configured work-item folders and their exact matching Excel workbook.",
        )

        self.new_work_item_button = ttk.Button(
            self.tool_rail,
            text="New item",
            command=create_work_item,
            style="Compact.TButton",
        )
        tooltip_adder(
            self.new_work_item_button,
            "New Work Item — Create a folder and exact-name Excel workbook from the configured generic template.",
        )

        self.send_work_item_inbox_button = ttk.Button(
            self.tool_rail,
            text="To inbox",
            command=send_work_item_inbox,
            style="Compact.TButton",
        )
        tooltip_adder(
            self.send_work_item_inbox_button,
            "Send to Inbox — Append Input / Output to columns A–D of the selected Work Item workbook's Inbox sheet.",
        )

        self.type_filter = ttk.Menubutton(
            self.tool_rail,
            text="Types ▾",
            style="Compact.TButton",
        )
        self.type_filter.pack(fill=tk.X, pady=(5, 0))
        self.action_type_filter_var = action_type_filter_var
        self.project_filter_var = project_filter_var
        self.select_action_type_filter = select_action_type_filter
        self.select_project_filter = select_project_filter
        self._set_action_type_menu()
        tooltip_adder(
            self.type_filter,
            "Types — Filter the action list by any built-in action type, or show all types.",
        )

        self.tag_filter_var = tag_filter_var
        self.select_tag_filter = select_tag_filter
        self.work_tag_filter_var = work_tag_filter_var
        self.select_work_tag_filter = select_work_tag_filter
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
            lambda: self.primary_help_text,
        )
        self.primary_help_text = (
            "Execute the highlighted action. Its input and effect appear in Action info below."
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
            lambda: self.mode_help_text,
        )
        self.mode_help_text = (
            "Search globally across tags, contexts, action names, types, and content."
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
        self.results.bind(
            "<Shift-Return>",
            lambda _event: execute_selected(open_folder=True),
        )
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

    def set_work_item_mode(
        self,
        enabled: bool,
        *,
        project_codes: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
    ) -> None:
        self.work_items_button.configure(
            style="Accent.TButton" if enabled else "Compact.TButton"
        )
        if enabled:
            self.passwords_button.pack_forget()
            if not self.new_work_item_button.winfo_manager():
                self.new_work_item_button.pack(
                    fill=tk.X,
                    pady=(5, 0),
                    before=self.type_filter,
                )
            if not self.send_work_item_inbox_button.winfo_manager():
                self.send_work_item_inbox_button.pack(
                    fill=tk.X,
                    pady=(5, 0),
                    before=self.type_filter,
                )
            self.find_label.configure(text="Find Work Item")
            self.type_filter.configure(text="Projects ▾")
            self.run_button.configure(text="Open")
            self.find_help_text = (
                "Find by Work Item name, kind, organisation, subject, source, project code, or tag."
            )
            self.primary_help_text = (
                "Open the highlighted Work Item's exact matching workbook, or its folder when none exists."
            )
            self.mode_help_text = (
                "Work Items are indexed folders, not actions. Choose Work again to return to Actions."
            )
            self._set_project_menu(project_codes)
            self.set_tags(
                tags,
                variable=self.work_tag_filter_var,
                select=self.select_work_tag_filter,
                empty_label="All work tags",
            )
        else:
            self.send_work_item_inbox_button.pack_forget()
            self.new_work_item_button.pack_forget()
            if not self.passwords_button.winfo_manager():
                self.passwords_button.pack(fill=tk.X, before=self.work_items_button)
            self.find_label.configure(text="Find action")
            self.type_filter.configure(text="Types ▾")
            self.run_button.configure(text="Run")
            self.find_help_text = "Type any tag, context, action name, type, or content."
            self.primary_help_text = (
                "Execute the highlighted action. Its input and effect appear in Action info below."
            )
            self.mode_help_text = (
                "Search globally across tags, contexts, action names, types, and content."
            )
            self._set_action_type_menu()
            self.set_tags(tags)

    def _set_action_type_menu(self) -> None:
        previous_menu = getattr(self, "type_menu", None)
        if previous_menu is not None:
            previous_menu.destroy()
        menu = tk.Menu(self.type_filter, tearoff=False)
        menu.add_radiobutton(
            label="All types",
            variable=self.action_type_filter_var,
            value="All types",
            command=lambda: self.select_action_type_filter(None),
        )
        menu.add_separator()
        for action_type, definition in ACTION_TYPES.items():
            menu.add_radiobutton(
                label=definition.label,
                variable=self.action_type_filter_var,
                value=definition.label,
                command=lambda selected=action_type: self.select_action_type_filter(selected),
            )
        self.type_filter.configure(menu=menu)
        self.type_menu = menu

    def _set_project_menu(self, project_codes: tuple[str, ...]) -> None:
        previous_menu = getattr(self, "type_menu", None)
        if previous_menu is not None:
            previous_menu.destroy()
        menu = tk.Menu(self.type_filter, tearoff=False)
        menu.add_radiobutton(
            label="All project codes",
            variable=self.project_filter_var,
            value="All project codes",
            command=lambda: self.select_project_filter(None),
        )
        if project_codes:
            menu.add_separator()
        for project_code in project_codes:
            menu.add_radiobutton(
                label=project_code,
                variable=self.project_filter_var,
                value=project_code,
                command=lambda selected=project_code: self.select_project_filter(selected),
            )
        self.type_filter.configure(menu=menu)
        self.type_menu = menu

    def set_tags(
        self,
        tags: tuple[str, ...],
        *,
        variable: tk.StringVar | None = None,
        select: Callable[[str | None], None] | None = None,
        empty_label: str = "All tags",
    ) -> None:
        selected_variable = variable or self.tag_filter_var
        selected_callback = select or self.select_tag_filter
        previous_menu = getattr(self, "tag_menu", None)
        if previous_menu is not None:
            previous_menu.destroy()
        menu = tk.Menu(self.tag_filter, tearoff=False)
        menu.add_radiobutton(
            label=empty_label,
            variable=selected_variable,
            value=empty_label,
            command=lambda: selected_callback(None),
        )
        if tags:
            menu.add_separator()
        for tag in tags:
            menu.add_radiobutton(
                label=tag,
                variable=selected_variable,
                value=tag,
                command=lambda selected=tag: selected_callback(selected),
            )
        self.tag_filter.configure(menu=menu)
        self.tag_menu = menu
