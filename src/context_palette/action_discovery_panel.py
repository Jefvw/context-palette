from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from .action_types import ACTION_TYPES
from .searchable_selection import SearchableSelectionPopup
from .style import COLORS
from .tooltips import ListboxItemTooltip, TreeviewItemTooltip


TooltipText = str | Callable[[], str]
DISCOVERY_ALL = "all"
DISCOVERY_ACTIONS = "actions"
DISCOVERY_WORK_ITEMS = "work_items"
DISCOVERY_SCOPES = (DISCOVERY_ALL, DISCOVERY_ACTIONS, DISCOVERY_WORK_ITEMS)
PINNED_SLOT_ROW_TAG = "slot_pinned"
FOCUS_SLOT_ROW_TAG = "slot_focus"
FOCUS_GROUP_ROW_TAG = "focus_group"


def slot_row_tag(slot: int | None) -> str | None:
    """Return the visual shortcut group without exposing its slot number."""

    if slot is not None and 1 <= slot <= 5:
        return PINNED_SLOT_ROW_TAG
    if slot is not None and 6 <= slot <= 10:
        return FOCUS_SLOT_ROW_TAG
    return None


def visible_result_row_count(tk_scaling: float) -> int:
    """Keep discovery and Quick actions usable as Windows text scales up."""

    if tk_scaling <= 0:
        return 10
    return max(7, min(10, round(13.333 / tk_scaling)))


def compact_rail_width(tk_scaling: float, requested_width: int) -> int:
    """Bound the expert rail tightly while allowing scaled text enough room."""

    scale = max(1.333, tk_scaling)
    scaling_cap = round(114 + (scale - 1.333) * 51)
    scaling_cap = max(114, min(148, scaling_cap))
    return max(114, min(scaling_cap, requested_width))


class ActionDiscoveryPanel:
    """Search and result widgets with launcher-owned discovery policy callbacks."""

    def __init__(
        self,
        parent: ttk.Frame,
        *,
        heading_var: tk.StringVar,
        count_var: tk.StringVar,
        search_var: tk.StringVar,
        action_type_filter_var: tk.StringVar,
        tag_filter_var: tk.StringVar,
        project_filter_var: tk.StringVar,
        context_filter_var: tk.StringVar,
        focus_launcher_var: tk.StringVar,
        tooltip_adder: Callable[[tk.Widget, TooltipText], None],
        keypress_handler: Callable[[tk.Event], object],
        execute_selected: Callable[..., None],
        update_preview: Callable[[], None],
        toggle_password_actions: Callable[[], None],
        toggle_focus_items: Callable[[], None],
        select_scope: Callable[[str], None],
        create_action: Callable[[], None],
        create_work_item: Callable[[], None],
        send_work_item_inbox: Callable[[], None],
        copy_file_to_work_item: Callable[[], None],
        select_action_type_filter: Callable[[str | None], None],
        select_tag_filter: Callable[[str | None], None],
        select_project_filter: Callable[[str | None], None],
        select_context_filter: Callable[[str | None], None],
        toggle_pin: Callable[[], None],
        capture: Callable[[], None],
        show_inbox: Callable[[], None],
        edit_item: Callable[[], None],
        configure: Callable[[], None],
        show_help: Callable[[], None],
        show_shortcuts: Callable[[], None],
        hide_window: Callable[[], None],
        quit_app: Callable[[], None],
        result_tooltip_text: Callable[[int], str],
        focus_tree_tooltip_text: Callable[[str], str],
        configure_flat_action: Callable[[tk.Event], object],
        configure_focus_action: Callable[[tk.Event], object],
    ) -> None:
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill=tk.X)

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

        body = ttk.Frame(self.frame)
        body.pack(fill=tk.X)
        self.tool_rail = ttk.Frame(body)
        self.tool_rail.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))
        self.tool_rail.columnconfigure(0, weight=1, uniform="rail")
        self.tool_rail.columnconfigure(1, weight=1, uniform="rail")

        discovery_column = ttk.Frame(body)
        discovery_column.pack(side=tk.LEFT, fill=tk.X, expand=True)
        search_row = ttk.Frame(discovery_column)
        search_row.pack(fill=tk.X, pady=(0, 5))
        self.find_label = ttk.Label(
            search_row,
            text="Find action",
            style="Heading.TLabel",
            takefocus=False,
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

        self.context_picker = ttk.Menubutton(
            self.tool_rail,
            textvariable=focus_launcher_var,
            width=15,
            style="Compact.TButton",
        )
        self.context_picker.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky=tk.EW,
            pady=(0, 2),
        )
        self.focus_menu = tk.Menu(self.context_picker, tearoff=False)
        self.context_picker.configure(menu=self.focus_menu)
        tooltip_adder(
            self.context_picker,
            "Focus — Choose what you are working on. This sets slots 6–0 and groups matching All items first without limiting global Find.",
        )

        self.focus_items_button = ttk.Button(
            self.tool_rail,
            text="Focus items",
            command=toggle_focus_items,
            style="Compact.TButton",
        )
        self.focus_items_button.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky=tk.EW,
            pady=(0, 2),
        )
        tooltip_adder(
            self.focus_items_button,
            "Focus items — Show only members of the active Focus. All items keeps global matches and groups Focus matches first.",
        )

        self.scope_buttons: dict[str, ttk.Button] = {}
        for column, (scope, label) in enumerate(
            (
                (DISCOVERY_ALL, "All"),
                (DISCOVERY_ACTIONS, "Actions"),
            )
        ):
            button = ttk.Button(
                self.tool_rail,
                text=label,
                command=lambda selected=scope: select_scope(selected),
                style="RailAccent.TButton" if scope == DISCOVERY_ALL else "Compact.TButton",
            )
            button.grid(
                row=2,
                column=column,
                sticky=tk.EW,
                padx=(0, 2) if column == 0 else (2, 0),
                pady=(0, 2),
            )
            self.scope_buttons[scope] = button
            tooltip_adder(
                button,
                (
                    "All — Find remains global; matching items in the selected "
                    "Focus appear before other matches."
                    if scope == DISCOVERY_ALL
                    else f"{label} — Choose which kinds of Palette items appear in Find."
                ),
            )
        self.work_items_button = ttk.Button(
            self.tool_rail,
            text="Work Items",
            command=lambda: select_scope(DISCOVERY_WORK_ITEMS),
            style="Compact.TButton",
        )
        self.work_items_button.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky=tk.EW,
            pady=(0, 2),
        )
        self.scope_buttons[DISCOVERY_WORK_ITEMS] = self.work_items_button
        tooltip_adder(
            self.work_items_button,
            "Work Items — Show indexed Work Items and their file-oriented commands.",
        )
        self.all_items_button = self.scope_buttons[DISCOVERY_ALL]
        self.actions_button = self.scope_buttons[DISCOVERY_ACTIONS]

        self.passwords_button = ttk.Button(
            self.tool_rail,
            text=ACTION_TYPES["paste_credential"].icon,
            command=toggle_password_actions,
            style="RailIcon.TButton",
        )
        self.passwords_button.grid(row=4, column=0, sticky=tk.EW, padx=(0, 2), pady=(0, 2))
        tooltip_adder(
            self.passwords_button,
            "Passwords — Show only protected Windows Credential Manager actions. Activate again to show all actions.",
        )

        self.new_work_item_button = ttk.Button(
            self.tool_rail,
            text="+W",
            command=create_work_item,
            style="RailIcon.TButton",
        )
        self.new_work_item_button.grid(row=4, column=0, sticky=tk.EW, padx=(0, 2), pady=(0, 2))
        tooltip_adder(
            self.new_work_item_button,
            "New Work Item — Create a folder and exact-name Excel workbook from the configured generic template.",
        )

        self.send_work_item_inbox_button = ttk.Button(
            self.tool_rail,
            text="→▣",
            command=send_work_item_inbox,
            style="RailIcon.TButton",
        )
        self.send_work_item_inbox_button.grid(row=4, column=1, sticky=tk.EW, padx=(2, 0), pady=(0, 2))
        tooltip_adder(
            self.send_work_item_inbox_button,
            "Send to Inbox — Append Input / Output to columns A–D of the selected Work Item workbook's Inbox sheet.",
        )

        self.copy_file_to_work_item_button = ttk.Button(
            self.tool_rail,
            text="⧉",
            command=copy_file_to_work_item,
            style="RailIcon.TButton",
        )
        self.copy_file_to_work_item_button.grid(row=5, column=0, sticky=tk.EW, padx=(0, 2), pady=(0, 2))
        tooltip_adder(
            self.copy_file_to_work_item_button,
            "Copy file — Copy the one exact file path in Input / Output into the selected Work Item folder without overwriting.",
        )

        self.type_filter = ttk.Menubutton(
            self.tool_rail,
            text="Types ▾",
            style="Compact.TButton",
        )
        self.type_filter.grid(row=4, column=1, sticky=tk.EW, padx=(2, 0), pady=(0, 2))
        self.action_type_filter_var = action_type_filter_var
        self.project_filter_var = project_filter_var
        self.select_action_type_filter = select_action_type_filter
        self.select_project_filter = select_project_filter
        self._set_action_type_menu()
        self.type_filter_help_text = (
            "Types — Filter the action list by any built-in action type, or show all types."
        )
        tooltip_adder(self.type_filter, lambda: self.type_filter_help_text)

        self.tag_filter_var = tag_filter_var
        self.select_tag_filter = select_tag_filter
        self.context_filter_var = context_filter_var
        self.select_context_filter = select_context_filter
        self.context_filter = ttk.Menubutton(
            self.tool_rail,
            text="C",
            style="RailIcon.TButton",
        )
        self.context_filter.grid(row=6, column=0, sticky=tk.EW, padx=(0, 2), pady=(0, 2))
        self.set_contexts(())
        tooltip_adder(
            self.context_filter,
            "Contexts — Filter Actions and Work Items through their shared Context membership.",
        )
        self.tag_filter = ttk.Button(
            self.tool_rail,
            text="#",
            style="RailIcon.TButton",
            command=self._show_tag_picker,
        )
        self.tag_filter.grid(row=6, column=1, sticky=tk.EW, padx=(2, 0), pady=(0, 2))
        self.tag_filter.bind("<Alt-Down>", self._show_tag_picker)
        self.tag_filter.bind("<F4>", self._show_tag_picker)
        self.tag_filter_help_text = (
            "Tags — Narrow actions by a reusable descriptive tag."
        )
        tooltip_adder(self.tag_filter, lambda: self.tag_filter_help_text)
        self.set_tags(())

        self.new_action_button = ttk.Button(
            self.tool_rail,
            text="+A",
            command=create_action,
            style="RailIconAccent.TButton",
        )
        self.new_action_button.grid(row=7, column=0, sticky=tk.EW, padx=(0, 2), pady=(0, 2))
        tooltip_adder(
            self.new_action_button,
            "+ Action — Choose an Action type, then complete the validated Action form.",
        )
        self.pin_button = ttk.Button(
            self.tool_rail,
            text="⌖",
            command=toggle_pin,
            style="RailIcon.TButton",
        )
        self.pin_button.grid(row=7, column=1, sticky=tk.EW, padx=(2, 0), pady=(0, 2))
        tooltip_adder(
            self.pin_button,
            "Pin — Pin or unpin the selected Action in stable slots 1–5.",
        )

        self.capture_button = ttk.Button(
            self.tool_rail,
            text="⇩",
            command=capture,
            style="RailIcon.TButton",
        )
        self.capture_button.grid(row=8, column=0, sticky=tk.EW, padx=(0, 2), pady=(0, 2))
        tooltip_adder(
            self.capture_button,
            "Capture — Save current clipboard text to Inbox after asking for a title.",
        )
        self.inbox_button = ttk.Button(
            self.tool_rail,
            text="▣",
            command=show_inbox,
            style="RailIcon.TButton",
        )
        self.inbox_button.grid(row=8, column=1, sticky=tk.EW, padx=(2, 0), pady=(0, 2))
        tooltip_adder(
            self.inbox_button,
            "Inbox — Review captures and convert them into permanent Actions.",
        )

        self.edit_button = ttk.Button(
            self.tool_rail,
            text="✎",
            command=edit_item,
            style="RailIcon.TButton",
        )
        self.edit_button.grid(row=9, column=0, sticky=tk.EW, padx=(0, 2), pady=(0, 2))
        tooltip_adder(
            self.edit_button,
            "Edit item — Configure the selected Action or Work Item.",
        )
        self.configure_button = ttk.Button(
            self.tool_rail,
            text="⚙",
            command=configure,
            style="RailIcon.TButton",
        )
        self.configure_button.grid(row=9, column=1, sticky=tk.EW, padx=(2, 0), pady=(0, 2))
        tooltip_adder(
            self.configure_button,
            "Configure — Manage Actions, Focuses, Quick actions, Work Items, and diagnostics.",
        )

        self.help_button = ttk.Button(
            self.tool_rail,
            text="?",
            command=show_help,
            style="RailIcon.TButton",
        )
        self.help_button.grid(row=10, column=0, sticky=tk.EW, padx=(0, 2), pady=(0, 2))
        tooltip_adder(self.help_button, lambda: self.mode_help_text)
        self.mode_help_text = (
            "Search globally across tags, contexts, Action names, types, and content."
        )
        self.more_menu = tk.Menu(self.tool_rail, tearoff=False)
        self.more_menu.add_command(label="Keyboard shortcuts", command=show_shortcuts)
        self.more_menu.add_separator()
        self.more_menu.add_command(label="Hide", command=hide_window)
        self.more_menu.add_command(label="Quit", command=quit_app)
        self.more_button = ttk.Menubutton(
            self.tool_rail,
            text="⋯",
            menu=self.more_menu,
            style="RailIcon.TButton",
        )
        self.more_button.grid(row=10, column=1, sticky=tk.EW, padx=(2, 0), pady=(0, 2))
        tooltip_adder(
            self.more_button,
            "More — Open keyboard shortcuts, hide Context Palette, or quit.",
        )

        self.primary_action_frame = ttk.Frame(self.tool_rail)
        self.primary_action_frame.grid(
            row=11,
            column=0,
            columnspan=2,
            sticky=tk.EW,
            pady=(4, 0),
        )
        self.primary_action_frame.columnconfigure(0, weight=1)
        self.run_button = ttk.Button(
            self.primary_action_frame,
            text="Run",
            command=execute_selected,
            style="RailAccent.TButton",
        )
        self.run_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tooltip_adder(
            self.run_button,
            lambda: self.primary_help_text,
        )
        self.work_item_folder_button = ttk.Button(
            self.primary_action_frame,
            text="📁",
            width=3,
            command=lambda: execute_selected(open_folder=True),
            style="Compact.TButton",
            takefocus=True,
        )
        tooltip_adder(
            self.work_item_folder_button,
            "Open folder — Always open the selected Work Item folder instead of its matching workbook.",
        )
        self.primary_help_text = (
            "Execute the highlighted action. Its input and effect appear in Action info below."
        )
        self.list_frame = ttk.Frame(discovery_column)
        self.list_frame.pack(fill=tk.X)
        self.scrollbar = ttk.Scrollbar(self.list_frame, orient=tk.VERTICAL)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        visible_rows = visible_result_row_count(
            float(self.frame.tk.call("tk", "scaling"))
        )
        self.results = tk.Listbox(
            self.list_frame,
            activestyle="dotbox",
            height=visible_rows,
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
            height=visible_rows,
            style="Flat.Treeview",
        )
        self.focus_tree.tag_configure(
            PINNED_SLOT_ROW_TAG,
            background=COLORS["slot_pinned"],
            foreground=COLORS["text"],
        )
        self.focus_tree.tag_configure(
            FOCUS_SLOT_ROW_TAG,
            background=COLORS["slot_focus"],
            foreground=COLORS["text"],
        )
        self.focus_tree.tag_configure(
            FOCUS_GROUP_ROW_TAG,
            background=COLORS["surface"],
            foreground=COLORS["muted_text"],
            font=("Segoe UI", 9, "bold"),
        )
        self.focus_tree.bind("<<TreeviewSelect>>", lambda _event: update_preview())
        self.focus_tree.bind("<Double-Button-1>", lambda _event: execute_selected())
        self.focus_tree.bind("<Return>", lambda _event: execute_selected())
        self.focus_tree.bind("<Button-3>", configure_focus_action)
        self.focus_tree_tooltip = TreeviewItemTooltip(
            self.focus_tree,
            focus_tree_tooltip_text,
        )
        # Bound only the rail width. Its height is measured from the complete
        # scope-specific command set so Windows text scaling cannot clip the
        # bottom commands.
        self.tool_rail.update_idletasks()
        rail_width = compact_rail_width(
            float(self.frame.tk.call("tk", "scaling")),
            self.tool_rail.winfo_reqwidth(),
        )
        rail_height = self.tool_rail.winfo_reqheight()
        self.tool_rail.grid_propagate(False)
        self.tool_rail.configure(width=rail_width, height=rail_height)

    def set_filter_indicators(
        self,
        *,
        scope: str,
        primary_value: str | None,
        context_value: str | None,
        tag_value: str | None,
    ) -> None:
        """Keep compact filter controls explicit about hidden active state."""
        work_items = scope == DISCOVERY_WORK_ITEMS
        primary_label = "Proj" if work_items else "Types"
        self.type_filter.configure(
            text=f"{primary_label} ✓" if primary_value else f"{primary_label} ▾",
            style="RailAccent.TButton" if primary_value else "Compact.TButton",
        )
        self.context_filter.configure(
            text="C✓" if context_value else "C",
            style="RailIconAccent.TButton" if context_value else "RailIcon.TButton",
        )
        self.tag_filter.configure(
            text="#✓" if tag_value else "#",
            style="RailIconAccent.TButton" if tag_value else "RailIcon.TButton",
        )
        if primary_value:
            clear_label = "project codes" if work_items else "types"
            self.type_filter_help_text = (
                f"{primary_label} — Active filter: {primary_value}. "
                f"Choose All {clear_label} to clear it."
            )
        else:
            self.type_filter_help_text = (
                "Projects — Filter Work Items by a detected project code."
                if work_items
                else "Types — Filter the action list by any built-in action type, or show all types."
            )
        if tag_value:
            clear_label = "work tags" if work_items else "tags"
            self.tag_filter_help_text = (
                f"Tags — Active filter: {tag_value}. "
                f"Choose All {clear_label} to clear it."
            )
        else:
            self.tag_filter_help_text = (
                "Tags — Narrow Actions and Work Items by a reusable tag."
            )

    def set_discovery_scope(
        self,
        scope: str,
        *,
        project_codes: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
    ) -> None:
        if scope not in DISCOVERY_SCOPES:
            raise ValueError(f"Unsupported discovery scope: {scope}")
        self.discovery_scope = scope
        for candidate, button in self.scope_buttons.items():
            button.configure(
                style=(
                    "RailAccent.TButton"
                    if candidate == scope
                    else "Compact.TButton"
                )
            )
        if scope == DISCOVERY_WORK_ITEMS:
            self.passwords_button.grid_remove()
            self.new_work_item_button.grid()
            self.send_work_item_inbox_button.grid()
            self.copy_file_to_work_item_button.grid()
            self.type_filter.grid_configure(row=5, column=1)
            self.type_filter.grid()
            self.pin_button.configure(state=tk.DISABLED)
            self.find_label.configure(text="Find Work Item")
            self.type_filter.configure(text="Projects ▾")
            self.run_button.configure(text="Open")
            self.run_button.pack_forget()
            self.work_item_folder_button.pack(side=tk.RIGHT)
            self.run_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.find_help_text = (
                "Find by Work Item name, kind, organisation, subject, source, project code, or tag."
            )
            self.primary_help_text = (
                "Open the highlighted Work Item's exact matching workbook, or its folder when none exists."
            )
            self.mode_help_text = (
                "Work Items are indexed folders with workbook-first opening. "
                "Choose All items to browse them beside Actions."
            )
            self._set_project_menu(project_codes)
        elif scope == DISCOVERY_ACTIONS:
            self.copy_file_to_work_item_button.grid_remove()
            self.send_work_item_inbox_button.grid_remove()
            self.new_work_item_button.grid_remove()
            self.passwords_button.grid()
            self.type_filter.grid_configure(row=4, column=1)
            self.type_filter.grid()
            self.pin_button.configure(state=tk.NORMAL)
            self.find_label.configure(text="Find action")
            self.type_filter.configure(text="Types ▾")
            self.run_button.configure(text="Run")
            self.work_item_folder_button.pack_forget()
            self.run_button.pack_forget()
            self.run_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.find_help_text = "Type any tag, context, action name, type, or content."
            self.primary_help_text = (
                "Execute the highlighted action. Its input and effect appear in Action info below."
            )
            self.mode_help_text = (
                "Search globally across tags, contexts, action names, types, and content."
            )
            self._set_action_type_menu()
        else:
            self.copy_file_to_work_item_button.grid_remove()
            self.send_work_item_inbox_button.grid_remove()
            self.new_work_item_button.grid_remove()
            self.passwords_button.grid_remove()
            self.type_filter.grid_remove()
            self.pin_button.configure(state=tk.NORMAL)
            self.find_label.configure(text="Find item")
            self.run_button.configure(text="Open / Run")
            self.work_item_folder_button.pack_forget()
            self.run_button.pack_forget()
            self.run_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.find_help_text = (
                "Find Actions or Work Items by name, content, Context, tag, type, source, or project code."
            )
            self.primary_help_text = (
                "Run the selected Action or open the selected Work Item."
            )
            self.mode_help_text = (
                "All items keeps Find global and groups matching items in the "
                "selected Focus before other matches. Use Actions or Work Items "
                "for type-specific filters."
            )
        self._fit_rail_height()
        self.set_tags(tags)

    def _fit_rail_height(self) -> None:
        """Reserve height for the active scope without leaving hidden-row gaps."""

        self.tool_rail.update_idletasks()
        visible_bottom = max(
            (
                child.winfo_y() + max(child.winfo_height(), child.winfo_reqheight())
                for child in self.tool_rail.winfo_children()
                if child.winfo_manager()
            ),
            default=1,
        )
        self.tool_rail.configure(height=visible_bottom)

    def set_selected_item_kind(self, *, work_item: bool | None) -> None:
        """Make mixed-view commands describe the selected Palette item."""

        if getattr(self, "discovery_scope", DISCOVERY_ALL) != DISCOVERY_ALL:
            return
        self.run_button.configure(
            text=(
                "Open"
                if work_item is True
                else "Run"
                if work_item is False
                else "Open / Run"
            )
        )
        self.primary_help_text = (
            "Open the selected Work Item's workbook, or its folder when none exists."
            if work_item is True
            else "Run the selected Action."
            if work_item is False
            else "Run the selected Action or open the selected Work Item."
        )
        self.work_item_folder_button.pack_forget()
        self.run_button.pack_forget()
        if work_item is True:
            self.work_item_folder_button.pack(side=tk.RIGHT)
        self.run_button.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def set_work_item_mode(
        self,
        enabled: bool,
        *,
        project_codes: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
    ) -> None:
        """Compatibility adapter for older launcher integrations and tests."""

        self.set_discovery_scope(
            DISCOVERY_WORK_ITEMS if enabled else DISCOVERY_ACTIONS,
            project_codes=project_codes,
            tags=tags,
        )

    def set_contexts(self, contexts: tuple[str, ...]) -> None:
        previous_menu = getattr(self, "context_menu", None)
        if previous_menu is not None:
            previous_menu.destroy()
        menu = tk.Menu(self.context_filter, tearoff=False)
        menu.add_radiobutton(
            label="All contexts",
            variable=self.context_filter_var,
            value="All contexts",
            command=lambda: self.select_context_filter(None),
        )
        specific = tuple(
            context for context in contexts if context.casefold() != "general"
        )
        if specific:
            menu.add_separator()
        for context in specific:
            menu.add_radiobutton(
                label=context,
                variable=self.context_filter_var,
                value=context,
                command=lambda selected=context: self.select_context_filter(selected),
            )
        self.context_filter.configure(menu=menu)
        self.context_menu = menu

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
                label=definition.display_label,
                variable=self.action_type_filter_var,
                value=definition.display_label,
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
        existing_popup = getattr(self, "tag_picker_popup", None)
        if existing_popup is not None and existing_popup.window.winfo_exists():
            existing_popup.close()
        self._tag_options = tuple(tags)
        self._tag_empty_label = empty_label
        self._tag_selected_variable = selected_variable
        self._tag_selected_callback = selected_callback

    def _show_tag_picker(self, _event: tk.Event | None = None) -> str | None:
        existing_popup = getattr(self, "tag_picker_popup", None)
        if existing_popup is not None and existing_popup.window.winfo_exists():
            existing_popup.window.lift()
            existing_popup.search_entry.focus_set()
            return "break"
        self.tag_picker_popup = SearchableSelectionPopup(
            self.tag_filter,
            self._tag_options,
            selected=(self._tag_selected_variable.get(),),
            multiple=False,
            on_select=self._select_tag_from_picker,
            title="Filter tags",
            empty_label=self._tag_empty_label,
        )
        return "break" if _event is not None else None

    def _select_tag_from_picker(self, selected: tuple[str, ...]) -> None:
        value = selected[0] if selected else self._tag_empty_label
        self._tag_selected_callback(
            None if value == self._tag_empty_label else value
        )
