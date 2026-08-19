from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from .action_types import ACTION_TYPES
from .searchable_selection import SearchableSelectionPopup
from .style import COLORS
from .tooltips import ListboxItemTooltip, TreeviewItemTooltip
from .ui_icons import load_ui_icons


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
        return 7
    return max(5, min(7, round(9.333 / tk_scaling)))


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
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.discovery_scope = DISCOVERY_ALL
        self._selected_work_item: bool | None = None
        self._has_selection = False
        self._sequence_running = False
        self.ui_icons = load_ui_icons(
            self.frame,
            (
                "focus",
                "filters",
                "edit",
                "pin",
                "folder",
                "configure",
                "help",
                "more",
            ),
            foreground=COLORS["text"],
        )

        navigation = ttk.Frame(self.frame)
        navigation.pack(fill=tk.X, pady=(0, 5))
        focus_row = ttk.Frame(navigation)
        focus_row.pack(fill=tk.X, pady=(0, 3))
        focus_row.columnconfigure(0, weight=1)
        scope_row = ttk.Frame(navigation)
        scope_row.pack(fill=tk.X)
        for column in range(3):
            scope_row.columnconfigure(column, weight=1, uniform="scope")

        body = ttk.Frame(self.frame)
        body.pack(fill=tk.BOTH, expand=True)
        discovery_column = ttk.Frame(body)
        discovery_column.pack(fill=tk.BOTH, expand=True)
        # Compatibility name retained for integrations. This is now a
        # horizontal item toolbar below results instead of a narrow side rail.
        self.tool_rail = ttk.Frame(discovery_column)
        search_row = ttk.Frame(discovery_column)
        search_row.pack(fill=tk.X, pady=(0, 5))
        search_header = ttk.Frame(search_row)
        search_header.pack(fill=tk.X)
        self.find_label = ttk.Label(
            search_header,
            text="Find action",
            style="Heading.TLabel",
            takefocus=False,
        )
        self.find_help_text = "Type any tag, context, action name, type, or content."
        self.search_entry = ttk.Entry(
            search_header,
            textvariable=search_var,
            font=("Segoe UI", 11),
        )
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        tooltip_adder(self.search_entry, lambda: self.find_help_text)
        self.search_entry.focus_set()
        self.search_entry.bind("<KeyPress>", keypress_handler)
        self.search_entry.bind(
            "<Shift-Return>",
            lambda _event: execute_selected(open_folder=True),
        )
        self.search_entry.bind("<Return>", lambda _event: execute_selected())

        self.context_picker = ttk.Menubutton(
            focus_row,
            textvariable=focus_launcher_var,
            style="Compact.TButton",
        )
        self.context_picker.grid(
            row=0,
            column=0,
            sticky=tk.EW,
            padx=(0, 3),
        )
        self.focus_menu = tk.Menu(self.context_picker, tearoff=False)
        self.context_picker.configure(menu=self.focus_menu)
        tooltip_adder(
            self.context_picker,
            "Focus — Choose what you are working on. This sets slots 6–0 and groups matching All items first without limiting global Find.",
        )

        self.focus_items_button = ttk.Button(
            focus_row,
            image=self.ui_icons["focus"],
            command=toggle_focus_items,
            style="Icon.TButton",
            takefocus=True,
        )
        self.focus_items_button.grid(
            row=0,
            column=1,
            sticky=tk.EW,
        )
        tooltip_adder(
            self.focus_items_button,
            "Focus items — Show only members of the active Focus. All items keeps global matches and groups Focus matches first.",
        )

        self.scope_buttons: dict[str, ttk.Button] = {}
        for column, (scope, label) in enumerate(
            (
                (DISCOVERY_ALL, "All items"),
                (DISCOVERY_ACTIONS, "Actions"),
            )
        ):
            button = ttk.Button(
                scope_row,
                text=label,
                command=lambda selected=scope: select_scope(selected),
                style="RailAccent.TButton" if scope == DISCOVERY_ALL else "Compact.TButton",
            )
            button.grid(
                row=0,
                column=column,
                sticky=tk.EW,
                padx=(0, 2),
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
            scope_row,
            text="Work Items",
            command=lambda: select_scope(DISCOVERY_WORK_ITEMS),
            style="Compact.TButton",
        )
        self.work_items_button.grid(
            row=0,
            column=2,
            sticky=tk.EW,
            padx=(0, 2),
        )
        self.scope_buttons[DISCOVERY_WORK_ITEMS] = self.work_items_button
        tooltip_adder(
            self.work_items_button,
            "Work Items — Show indexed Work Items and their file-oriented commands.",
        )
        self.all_items_button = self.scope_buttons[DISCOVERY_ALL]
        self.actions_button = self.scope_buttons[DISCOVERY_ACTIONS]

        self.scope_options_menu = tk.Menu(search_header, tearoff=False)
        self.scope_options_button = ttk.Menubutton(
            search_header,
            image=self.ui_icons["filters"],
            menu=self.scope_options_menu,
            style="Icon.TButton",
            takefocus=True,
        )
        self.scope_options_button.pack(side=tk.RIGHT)
        tooltip_adder(
            self.scope_options_button,
            lambda: self.scope_options_help_text,
        )
        self.scope_options_help_text = "Filters and tools for the current item view."

        self.filter_chip = ttk.Button(
            search_row,
            text="",
            command=self._clear_active_filters,
            style="Compact.TButton",
        )
        tooltip_adder(
            self.filter_chip,
            "Active filters. Activate to clear the Context, tag, type, or project filters.",
        )

        self.passwords_button = ttk.Button(
            self.tool_rail,
            text=ACTION_TYPES["paste_credential"].icon,
            command=toggle_password_actions,
            style="RailIcon.TButton",
        )
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
        tooltip_adder(
            self.copy_file_to_work_item_button,
            "Copy file — Copy the one exact file path in Input / Output into the selected Work Item folder without overwriting.",
        )

        self.type_filter = ttk.Menubutton(
            self.tool_rail,
            text="Types ▾",
            style="Compact.TButton",
        )
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
        self.context_filter.grid(row=0, column=0, sticky=tk.EW, padx=(0, 2), pady=(0, 2))
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
        self.tag_filter.grid(row=0, column=1, sticky=tk.EW, padx=(2, 0), pady=(0, 2))
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
        self.new_action_button.grid(row=1, column=0, sticky=tk.EW, padx=(0, 2), pady=(0, 2))
        tooltip_adder(
            self.new_action_button,
            "+ Action — Choose an Action type, then complete the validated Action form.",
        )
        self.pin_button = ttk.Button(
            self.tool_rail,
            image=self.ui_icons["pin"],
            command=toggle_pin,
            style="Icon.TButton",
        )
        self.pin_button.grid(row=1, column=1, sticky=tk.EW, padx=(2, 0), pady=(0, 2))
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
        self.capture_button.grid(row=2, column=0, sticky=tk.EW, padx=(0, 2), pady=(0, 2))
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
        self.inbox_button.grid(row=2, column=1, sticky=tk.EW, padx=(2, 0), pady=(0, 2))
        tooltip_adder(
            self.inbox_button,
            "Inbox — Review captures and convert them into permanent Actions.",
        )

        self.edit_button = ttk.Button(
            self.tool_rail,
            image=self.ui_icons["edit"],
            command=edit_item,
            style="Icon.TButton",
        )
        self.edit_button.grid(row=3, column=0, sticky=tk.EW, padx=(0, 2), pady=(0, 2))
        tooltip_adder(
            self.edit_button,
            "Edit item — Configure the selected Action or Work Item.",
        )
        self.configure_button = ttk.Button(
            self.tool_rail,
            image=self.ui_icons["configure"],
            command=configure,
            style="Icon.TButton",
        )
        self.configure_button.grid(row=3, column=1, sticky=tk.EW, padx=(2, 0), pady=(0, 2))
        tooltip_adder(
            self.configure_button,
            "Configure — Manage Actions, Focuses, Quick actions, Work Items, and diagnostics.",
        )

        self.help_button = ttk.Button(
            self.tool_rail,
            image=self.ui_icons["help"],
            command=show_help,
            style="Icon.TButton",
        )
        self.help_button.grid(row=4, column=0, sticky=tk.EW, padx=(0, 2), pady=(0, 2))
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
            image=self.ui_icons["more"],
            menu=self.more_menu,
            style="Icon.TButton",
        )
        self.more_button.grid(row=4, column=1, sticky=tk.EW, padx=(2, 0), pady=(0, 2))
        tooltip_adder(
            self.more_button,
            "More — Open keyboard shortcuts, hide Context Palette, or quit.",
        )

        self.primary_action_frame = ttk.Frame(self.tool_rail)
        self.primary_action_frame.grid(
            row=5,
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
            image=self.ui_icons["folder"],
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
        self.list_frame.pack(fill=tk.BOTH, expand=True)
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
        # The result toolbar is deliberately stable across scopes. Scope-only
        # commands stay in the Filters menu rather than reshaping the screen.
        for child in self.tool_rail.winfo_children():
            child.grid_forget()
        self.tool_rail.pack(fill=tk.X, pady=(5, 0))
        self.tool_rail.columnconfigure(3, weight=1)
        self.new_action_button.grid(row=0, column=0, padx=(0, 4))
        self.edit_button.grid(row=0, column=1, padx=(0, 4))
        self.pin_button.grid(row=0, column=2, padx=(0, 6))
        self.primary_action_frame.grid(row=0, column=3, sticky=tk.EW)

    def set_filter_indicators(
        self,
        *,
        scope: str,
        primary_value: str | None,
        context_value: str | None,
        tag_value: str | None,
    ) -> None:
        """Keep the single filter control explicit about hidden active state."""
        work_items = scope == DISCOVERY_WORK_ITEMS
        primary_label = "Proj" if work_items else "Types"
        self.type_filter.configure(
            text=f"{primary_label} ✓" if primary_value else f"{primary_label} ▾",
            style="RailAccent.TButton" if primary_value else "Compact.TButton",
        )
        active_values = tuple(
            value for value in (primary_value, context_value, tag_value) if value
        )
        self.scope_options_button.configure(
            style="RailIconAccent.TButton" if active_values else "Icon.TButton"
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
        if active_values:
            parts: list[str] = []
            if context_value:
                parts.append(f"Context: {context_value}")
            if tag_value:
                parts.append(f"Tag: {tag_value}")
            if primary_value:
                parts.append(f"{primary_label}: {primary_value}")
            self.filter_chip.configure(text=" | ".join(parts) + " (clear)")
            if not self.filter_chip.winfo_manager():
                self.filter_chip.pack(fill=tk.X, pady=(4, 0))
        elif self.filter_chip.winfo_manager():
            self.filter_chip.pack_forget()

    def _clear_active_filters(self) -> None:
        """Clear only active filters through the launcher-owned callbacks."""

        if self.context_filter_var.get() != "All contexts":
            self.select_context_filter(None)
        if self.tag_filter_var.get() not in {"All tags", "All work tags"}:
            self.select_tag_filter(None)
        if self.action_type_filter_var.get() != "All types":
            self.select_action_type_filter(None)
        if self.project_filter_var.get() != "All project codes":
            self.select_project_filter(None)

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
            self._set_scope_options_menu(scope)
        elif scope == DISCOVERY_ACTIONS:
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
            self._set_scope_options_menu(scope)
        else:
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
            self._set_scope_options_menu(scope)
        self.set_tags(tags)
        self.render_control_state()

    def set_selected_item_kind(self, *, work_item: bool | None) -> None:
        """Make mixed-view commands describe the selected Palette item."""

        self._selected_work_item = work_item
        self._has_selection = work_item is not None
        self.render_control_state()

    def render_control_state(
        self,
        *,
        work_item: bool | None = None,
        has_selection: bool | None = None,
        sequence_running: bool | None = None,
    ) -> None:
        """Render one coherent command state for scope, selection, and sequence."""

        if work_item is not None or has_selection is False:
            self._selected_work_item = work_item
        if has_selection is not None:
            self._has_selection = has_selection
        if sequence_running is not None:
            self._sequence_running = sequence_running
        selected_work_item = self._selected_work_item is True
        can_select = self._has_selection
        self.edit_button.configure(state=tk.NORMAL if can_select else tk.DISABLED)
        self.pin_button.configure(
            state=(
                tk.NORMAL
                if can_select and not selected_work_item
                else tk.DISABLED
            )
        )
        self.run_button.configure(
            state=tk.NORMAL if can_select or self._sequence_running else tk.DISABLED,
            text=(
                "Stop remaining"
                if self._sequence_running
                else "Open"
                if selected_work_item
                else "Run"
                if can_select
                else "Run"
                if self.discovery_scope == DISCOVERY_ACTIONS
                else "Open"
                if self.discovery_scope == DISCOVERY_WORK_ITEMS
                else "Open / Run"
            ),
            style="RailAccent.TButton",
        )
        self.primary_help_text = (
            "Stop the sequence before its next step starts."
            if self._sequence_running
            else "Open the selected Work Item's workbook, or its folder when none exists."
            if selected_work_item
            else "Run the selected Action."
            if can_select
            else "Select an Action or Work Item to preview and run or open it."
        )
        self.work_item_folder_button.pack_forget()
        self.run_button.pack_forget()
        if selected_work_item and can_select and not self._sequence_running:
            self.work_item_folder_button.pack(side=tk.RIGHT, padx=(0, 4))
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
        self._context_options = specific
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
        if hasattr(self, "discovery_scope"):
            self._set_scope_options_menu(self.discovery_scope)

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

    def _set_scope_options_menu(self, scope: str) -> None:
        """Compose filters and scope tools behind one stable icon button."""

        previous_menu = getattr(self, "scope_options_menu", None)
        if previous_menu is not None:
            previous_menu.destroy()
        menu = tk.Menu(self.scope_options_button, tearoff=False)
        if scope == DISCOVERY_ACTIONS:
            menu.add_cascade(label="Filter by type", menu=self.type_menu)
            help_text = "Filter Actions by type, Context, or tag."
        elif scope == DISCOVERY_WORK_ITEMS:
            menu.add_command(
                label="New Work Item…",
                command=self.new_work_item_button.invoke,
            )
            menu.add_separator()
            menu.add_command(
                label="Send Input / Output to Inbox",
                command=self.send_work_item_inbox_button.invoke,
            )
            menu.add_command(
                label="Copy file into Work Item",
                command=self.copy_file_to_work_item_button.invoke,
            )
            menu.add_separator()
            menu.add_cascade(label="Filter by project", menu=self.type_menu)
            help_text = (
                "Create or update a Work Item, or filter by project, Context, or tag."
            )
        else:
            help_text = "Filter All items by Context or tag."
        if menu.index(tk.END) is not None:
            menu.add_separator()
        menu.add_command(
            label="Filter by context…",
            command=self._queue_context_picker,
        )
        menu.add_command(label="Filter by tag…", command=self._show_tag_picker)
        self.scope_options_menu = menu
        self.scope_options_help_text = help_text
        self.scope_options_button.configure(
            menu=menu,
            state=tk.NORMAL,
        )

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
            self.scope_options_button,
            self._tag_options,
            selected=(self._tag_selected_variable.get(),),
            multiple=False,
            on_select=self._select_tag_from_picker,
            title="Filter tags",
            empty_label=self._tag_empty_label,
        )
        return "break" if _event is not None else None

    def _queue_context_picker(self) -> None:
        # Let the menu invocation return before the grabbed popup can process
        # pending layout work that may rebuild the same options menu.
        self.scope_options_button.after_idle(self._show_context_picker)

    def _show_context_picker(self) -> None:
        existing_popup = getattr(self, "context_picker_popup", None)
        if existing_popup is not None and existing_popup.window.winfo_exists():
            existing_popup.window.lift()
            existing_popup.search_entry.focus_set()
            return
        self.context_picker_popup = SearchableSelectionPopup(
            self.scope_options_button,
            self._context_options,
            selected=(self.context_filter_var.get(),),
            multiple=False,
            on_select=self._select_context_from_picker,
            title="Filter contexts",
            empty_label="All contexts",
            search_label="Find context",
            item_name="context",
        )

    def _select_context_from_picker(self, selected: tuple[str, ...]) -> None:
        value = selected[0] if selected else "All contexts"
        self.select_context_filter(None if value == "All contexts" else value)

    def _select_tag_from_picker(self, selected: tuple[str, ...]) -> None:
        value = selected[0] if selected else self._tag_empty_label
        self._tag_selected_callback(
            None if value == self._tag_empty_label else value
        )
