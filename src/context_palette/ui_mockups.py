from __future__ import annotations

"""Inert real-Tk visual baselines for reviewing future Context Palette UI work.

The mockups deliberately use fixed in-memory examples. They do not import the
launcher or configuration stores, inspect local targets, use the clipboard, or
dispatch any operating-system effect.
"""

import argparse
from dataclasses import dataclass
import subprocess
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Callable, Iterable

from .style import CAPTION_FONT, COLORS, DEFAULT_FONT, configure_theme
from .ui_icons import load_ui_icons


MOCKUP_MAIN = "main"
MOCKUP_WORK_ITEMS = "configure-work-items"
MOCKUP_ACTIONS = "configure-actions"
MOCKUP_KEYS = (MOCKUP_MAIN, MOCKUP_WORK_ITEMS, MOCKUP_ACTIONS)
SIZE_NORMAL = "normal"
SIZE_MINIMUM = "minimum"
SIZE_KEYS = (SIZE_NORMAL, SIZE_MINIMUM)
SCALE_PERCENTAGES = (100, 125, 150)
SYSTEM_SCALING = "system"
BASE_TK_SCALING = 96 / 72
CONTEXT_SCOPE_EVERYWHERE = "everywhere"
CONTEXT_SCOPE_THIS = "this"


@dataclass(frozen=True)
class MockupDefinition:
    key: str
    label: str
    normal_size: tuple[int, int]
    minimum_size: tuple[int, int]
    scenarios: tuple[tuple[str, str], ...]

    def size(self, size_key: str) -> tuple[int, int]:
        if size_key == SIZE_NORMAL:
            return self.normal_size
        if size_key == SIZE_MINIMUM:
            return self.minimum_size
        raise ValueError(f"Unsupported mockup size: {size_key}")


MOCKUP_DEFINITIONS = {
    MOCKUP_MAIN: MockupDefinition(
        MOCKUP_MAIN,
        "Main palette",
        (780, 600),
        (700, 480),
        (
            ("no-selection", "Populated, no selection"),
            ("selected", "Selected Action"),
            ("work-item", "Selected Work Item"),
            ("context-slots", "Working context slots 6–0"),
            ("this-context", "This context results"),
            ("zero-match", "Find with no matches"),
            ("sequence", "Sequence waiting"),
            ("empty-context", "This context has no members"),
            ("sequence-stopped", "Sequence stopped"),
        ),
    ),
    MOCKUP_WORK_ITEMS: MockupDefinition(
        MOCKUP_WORK_ITEMS,
        "Configure - Work Items",
        (960, 680),
        (900, 520),
        (
            ("selected", "Selected Work Item"),
            ("no-match", "No search matches"),
            ("unavailable", "Unavailable source with last-known rows"),
        ),
    ),
    MOCKUP_ACTIONS: MockupDefinition(
        MOCKUP_ACTIONS,
        "Configure - Actions",
        (960, 680),
        (900, 520),
        (
            ("active", "Selected Active Action"),
            ("archived", "Selected Archived Action"),
        ),
    ),
}


def tk_scaling_for_percentage(percentage: int) -> float:
    if percentage not in SCALE_PERCENTAGES:
        raise ValueError(f"Unsupported mockup scaling: {percentage}")
    return BASE_TK_SCALING * percentage / 100


def _configure_mockup_theme(
    root: tk.Misc,
    percentage: int | None,
) -> ttk.Style:
    if percentage is not None:
        root.tk.call("tk", "scaling", tk_scaling_for_percentage(percentage))
    style = configure_theme(root)
    body_font = tkfont.Font(root=root, font=DEFAULT_FONT)
    row_height = max(25, body_font.metrics("linespace") + 8)
    style.configure("Treeview", rowheight=row_height)
    style.configure(
        "Mockup.Nav.TButton",
        anchor=tk.W,
        padding=(10, 6),
        background=COLORS["background"],
        borderwidth=0,
        relief=tk.FLAT,
    )
    style.map(
        "Mockup.Nav.TButton",
        background=[("active", COLORS["row_aqua"])],
        foreground=[("disabled", COLORS["muted_text"])],
    )
    style.configure(
        "Mockup.NavSelected.TButton",
        anchor=tk.W,
        padding=(10, 6),
        background=COLORS["accent"],
        foreground=COLORS["white"],
        font=("Segoe UI Semibold", 10),
        borderwidth=0,
    )
    style.map(
        "Mockup.NavSelected.TButton",
        background=[("active", COLORS["accent_hover"])],
        foreground=[("!disabled", COLORS["white"])],
    )
    style.configure(
        "Mockup.Card.TFrame",
        background=COLORS["surface"],
        bordercolor=COLORS["border"],
        relief=tk.SOLID,
        borderwidth=1,
    )
    style.configure(
        "Mockup.Card.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["text"],
    )
    style.configure(
        "Mockup.CardMuted.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["muted_text"],
        font=CAPTION_FONT,
    )
    style.configure(
        "Mockup.Danger.TButton",
        foreground=COLORS["error"],
        background=COLORS["surface"],
        bordercolor=COLORS["error"],
        padding=(8, 5),
    )
    style.map(
        "Mockup.Danger.TButton",
        background=[("active", "#fde8e7")],
        foreground=[("disabled", COLORS["muted_text"]), ("!disabled", COLORS["error"])],
    )
    style.configure(
        "Mockup.Scope.TButton",
        padding=(6, 4),
        font=("Segoe UI", 9),
    )
    style.configure(
        "Mockup.ScopeSelected.TButton",
        padding=(6, 4),
        background=COLORS["accent"],
        foreground=COLORS["white"],
        font=("Segoe UI Semibold", 9),
    )
    style.map(
        "Mockup.ScopeSelected.TButton",
        background=[("active", COLORS["accent_hover"])],
        foreground=[("!disabled", COLORS["white"])],
    )
    return style


def _descendant_rect(widget: tk.Misc, ancestor: tk.Misc) -> tuple[int, int, int, int]:
    """Return a widget rectangle relative to an ancestor, even while withdrawn."""

    x = 0
    y = 0
    current: tk.Misc = widget
    while current != ancestor:
        x += int(current.winfo_x())
        y += int(current.winfo_y())
        parent_name = current.winfo_parent()
        if not parent_name:
            raise ValueError("Widget is not a descendant of the supplied ancestor.")
        current = current._nametowidget(parent_name)
    return x, y, int(widget.winfo_width()), int(widget.winfo_height())


class MockupView:
    """Common geometry audit surface shared by the inert mockups."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.critical_widgets: list[tk.Widget] = []

    def critical(self, *widgets: tk.Widget) -> None:
        self.critical_widgets.extend(widgets)

    def layout_issues(self) -> tuple[str, ...]:
        self.root.update_idletasks()
        width = int(self.root.winfo_width())
        height = int(self.root.winfo_height())
        issues: list[str] = []
        for widget in self.critical_widgets:
            if not widget.winfo_manager():
                continue
            x, y, widget_width, widget_height = _descendant_rect(widget, self.root)
            if x < -1 or y < -1 or x + widget_width > width + 1 or y + widget_height > height + 1:
                issues.append(
                    f"{widget.winfo_class()} {str(widget)} is outside "
                    f"{width}x{height}: {(x, y, widget_width, widget_height)}"
                )
        return tuple(issues)


@dataclass(frozen=True)
class WorkItemExample:
    name: str
    kind: str
    project: str
    contexts: str
    tags: str


WORK_ITEM_EXAMPLES = (
    WorkItemExample("CAS-CAP40-KILIT", "Case", "-", "CAP40 delivery", "urgent"),
    WorkItemExample("ISS-CAP40-age-verification", "Issue", "-", "Age verification", "age"),
    WorkItemExample("PRJ-CAP40-DWH-rationalisation", "Project", "-", "CAP40 delivery", "data"),
    WorkItemExample("PRJ-CAP40-VS9D", "Project", "VS9D", "CAP40 delivery", "visual"),
    WorkItemExample("PRJ-CAP40-W994-pi-fast", "Project", "W994", "CAP40 delivery", "performance"),
    WorkItemExample("QST-CAP40-nutrivalue-analysis", "Question", "-", "Research", "nutrition"),
    WorkItemExample("QST-CAP40-TEST-WW9W", "Question", "WW9W", "Testing", "test"),
    WorkItemExample("TRCK-CAP40-business-rules", "Track", "-", "CAP40 delivery", "rules"),
    WorkItemExample("TRCK-CAP40-data-reservoir", "Track", "-", "Data", "data"),
)


@dataclass
class ActionExample:
    name: str
    kind: str
    contexts: str
    source: str
    state: str
    tags: str


ACTION_EXAMPLES = (
    ActionExample("Professional greeting", "Copy text", "General, Mail", "My configuration", "Active", "communication"),
    ActionExample("Context Palette in VS Code", "Open Windows target", "Developing", "My configuration", "Active", "development"),
    ActionExample("Bioplanet cart", "Open website", "Shopping", "Built-in", "Active", "shopping"),
    ActionExample("Current date and time", "Transform text", "General", "Built-in", "Active", "date"),
    ActionExample("Project folder", "Open folder", "Developing", "My configuration", "Active", "project"),
    ActionExample("Python documentation", "Open website", "Developing", "Built-in", "Active", "python"),
    ActionExample("Selected archive item", "Archive selection", "General", "Built-in", "Active", "archive"),
    ActionExample("Older greeting", "Copy text", "Mail", "My configuration", "Archived", "communication"),
    ActionExample("Previous project folder", "Open folder", "Developing", "My configuration", "Archived", "project"),
)


@dataclass(frozen=True)
class PaletteExample:
    key: str
    name: str
    kind: str
    contexts: tuple[str, ...]
    context_slots: tuple[tuple[str, int], ...]
    tags: tuple[str, ...]
    effect: str


PALETTE_EXAMPLES = (
    PaletteExample(
        "professional-greeting",
        "Professional greeting",
        "action",
        ("General", "Mail"),
        (),
        ("communication",),
        "paste saved text into the captured app; clipboard fallback",
    ),
    PaletteExample(
        "vscode",
        "Context Palette in VS Code",
        "action",
        ("Developing",),
        (("Developing", 6),),
        ("development",),
        "open a reviewed Windows target",
    ),
    PaletteExample(
        "cart",
        "Bioplanet cart",
        "action",
        ("Shopping",),
        (),
        ("shopping",),
        "open a website",
    ),
    PaletteExample(
        "guitar-tab",
        "IVE BEEN LOSING YOU TAB",
        "action",
        ("Music",),
        (),
        ("music",),
        "open a PDF file",
    ),
    PaletteExample(
        "current-date",
        "Current date and time",
        "action",
        ("General", "Developing"),
        (("Developing", 7),),
        ("date",),
        "replace Input / Output with the current date and time",
    ),
    PaletteExample(
        "project-folder",
        "Project folder",
        "action",
        ("Developing",),
        (("Developing", 8),),
        ("project",),
        "open a configured folder",
    ),
    PaletteExample(
        "python-docs",
        "Python documentation",
        "action",
        ("Developing",),
        (("Developing", 9),),
        ("python",),
        "open a website",
    ),
    PaletteExample(
        "url-encode",
        "URL-encoded clipboard text",
        "action",
        ("General",),
        (),
        ("text",),
        "transform clipboard text locally",
    ),
    PaletteExample(
        "selected-archive",
        "Selected archive item",
        "action",
        ("General",),
        (),
        ("archive",),
        "archive the selected item after confirmation",
    ),
    PaletteExample(
        "work-item-kilit",
        "Case - CAP40 KILIT",
        "work-item",
        ("CAP40 delivery", "Developing"),
        (("Developing", 10),),
        ("urgent",),
        "open workbook CAS-CAP40-KILIT.xlsx",
    ),
    PaletteExample(
        "work-item-age",
        "Issue - CAP40 age verification",
        "work-item",
        ("Age verification",),
        (),
        ("age",),
        "open workbook ISS-CAP40-age-verification.xlsx",
    ),
    PaletteExample(
        "sequence",
        "UAT: Run a harmless sequence",
        "sequence",
        ("General",),
        (),
        ("uat",),
        "dispatch a folder, wait 5 seconds, then dispatch the folder again",
    ),
)


QUICK_ACTION_MOCKUP_GROUPS = (
    ("Standard", "fixed standard menu"),
    ("My work", "personal configured menu"),
    ("Shared tools", "shared configured menu"),
    ("Passwords", "automatic Action-bound menu"),
    ("Folders", "automatic Action-bound menu"),
    ("Prompts", "automatic Action-bound menu"),
)


def _scrollable_tree(
    parent: tk.Misc,
    columns: tuple[str, ...],
) -> tuple[ttk.Frame, ttk.Treeview]:
    frame = ttk.Frame(parent)
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    tree = ttk.Treeview(
        frame,
        columns=columns,
        show="tree headings",
        selectmode="browse",
    )
    scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    tree.grid(row=0, column=0, sticky=tk.NSEW)
    scrollbar.grid(row=0, column=1, sticky=tk.NS)
    return frame, tree


class ConfigureMockup(MockupView):
    """Frame-stack Configure mockup with representative table pages."""

    SETUP_PAGES = (
        ("start", "Start"),
        ("actions", "Actions"),
        ("contexts", "Contexts"),
        ("quick-actions", "Quick actions"),
        ("work-items", "Work Items"),
    )
    SUPPORT_PAGES = (
        ("backup", "Backup & restore"),
        ("diagnostics", "Diagnostics"),
    )

    def __init__(self, root: tk.Tk, *, page: str, scenario: str) -> None:
        super().__init__(root)
        self.scenario = scenario
        self.pages: dict[str, ttk.Frame] = {}
        self.navigation_buttons: dict[str, ttk.Button] = {}
        self.status_var = tk.StringVar(value="Mockup only - no files or settings are changed.")
        self.selected_page = page

        outer = ttk.Frame(root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        body = ttk.Frame(outer)
        body.grid(row=0, column=0, sticky=tk.NSEW)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(2, weight=1)

        navigation_font = tkfont.Font(root=root, font=DEFAULT_FONT)
        navigation_width = max(
            160,
            navigation_font.measure("Backup & restore") + 34,
        )
        navigation = ttk.Frame(body, width=navigation_width)
        navigation.grid(row=0, column=0, sticky=tk.NS, padx=(0, 10))
        navigation.grid_propagate(False)
        navigation.rowconfigure(2, weight=1)
        ttk.Separator(body, orient=tk.VERTICAL).grid(row=0, column=1, sticky=tk.NS)
        self.page_host = ttk.Frame(body)
        self.page_host.grid(row=0, column=2, sticky=tk.NSEW, padx=(12, 0))
        self.page_host.rowconfigure(0, weight=1)
        self.page_host.columnconfigure(0, weight=1)

        self._build_navigation_group(navigation, 0, "SET UP", self.SETUP_PAGES)
        self._build_navigation_group(navigation, 3, "SUPPORT", self.SUPPORT_PAGES)

        self._build_placeholder_page(
            "start",
            "Choose a setup task",
            "Create an Action, organize Contexts, or set up Work Items.",
        )
        self._build_actions_page()
        self._build_placeholder_page(
            "contexts",
            "Manage Contexts",
            "A Context organizes items; the Working context is highlighted in the palette.",
        )
        self._build_placeholder_page(
            "quick-actions",
            "Manage Quick actions",
            "Arrange menu launchers without changing discovery results.",
        )
        self._build_work_items_page()
        self._build_placeholder_page(
            "backup",
            "Backup & restore",
            "Create a backup or inspect one before applying changes.",
        )
        self._build_placeholder_page(
            "diagnostics",
            "Support information",
            "Review a privacy-safe summary of this setup.",
        )

        footer = ttk.Frame(outer)
        footer.grid(row=1, column=0, sticky=tk.EW, pady=(10, 0))
        self.status_label = ttk.Label(footer, textvariable=self.status_var, style="Status.TLabel")
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.close_button = ttk.Button(footer, text="Close", command=root.destroy)
        self.close_button.pack(side=tk.RIGHT)
        self.critical(self.status_label, self.close_button)
        self.show_page(page)
        self._apply_initial_scenario()

    def _build_navigation_group(
        self,
        parent: ttk.Frame,
        row: int,
        heading: str,
        pages: Iterable[tuple[str, str]],
    ) -> None:
        group = ttk.Frame(parent)
        group.grid(row=row, column=0, sticky=tk.EW)
        ttk.Label(group, text=heading, style="Muted.TLabel").pack(anchor=tk.W, pady=(0, 5))
        for key, label in pages:
            button = ttk.Button(
                group,
                text=label,
                style="Mockup.Nav.TButton",
                command=lambda selected=key: self.show_page(selected),
            )
            button.pack(fill=tk.X, pady=(0, 2))
            self.navigation_buttons[key] = button
            self.critical(button)

    def _new_page(self, key: str) -> ttk.Frame:
        page = ttk.Frame(self.page_host)
        page.grid(row=0, column=0, sticky=tk.NSEW)
        page.grid_remove()
        self.pages[key] = page
        return page

    def _build_placeholder_page(self, key: str, title: str, purpose: str) -> None:
        page = self._new_page(key)
        page.columnconfigure(0, weight=1)
        ttk.Label(page, text=title, style="Title.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(page, text=purpose, style="Muted.TLabel").grid(
            row=1, column=0, sticky=tk.W, pady=(3, 14)
        )
        card = ttk.Frame(page, style="Mockup.Card.TFrame", padding=14)
        card.grid(row=2, column=0, sticky=tk.EW)
        ttk.Label(
            card,
            text="This page keeps the same shell but is outside this mockup batch.",
            style="Mockup.Card.TLabel",
        ).pack(anchor=tk.W)

    def show_page(self, page: str) -> None:
        if page not in self.pages:
            raise ValueError(f"Unknown Configure mockup page: {page}")
        for key, frame in self.pages.items():
            if key == page:
                frame.grid()
                frame.tkraise()
            else:
                frame.grid_remove()
        for key, button in self.navigation_buttons.items():
            button.configure(
                style="Mockup.NavSelected.TButton" if key == page else "Mockup.Nav.TButton"
            )
        self.selected_page = page

    def _page_header(
        self,
        page: ttk.Frame,
        *,
        title: str,
        purpose: str,
        primary_text: str,
        primary_command: Callable[[], None],
        secondary: ttk.Widget | None = None,
    ) -> ttk.Button:
        header = ttk.Frame(page)
        header.grid(row=0, column=0, sticky=tk.EW, pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=title, style="Title.TLabel").grid(row=0, column=0, sticky=tk.W)
        commands = ttk.Frame(header)
        commands.grid(row=0, column=1, rowspan=2, sticky=tk.E)
        if secondary is not None:
            secondary.pack(in_=commands, side=tk.LEFT, padx=(0, 6))
        primary = ttk.Button(
            commands,
            text=primary_text,
            command=primary_command,
            style="Accent.TButton",
        )
        primary.pack(side=tk.LEFT)
        ttk.Label(header, text=purpose, style="Muted.TLabel").grid(
            row=1, column=0, sticky=tk.W, pady=(3, 0)
        )
        self.critical(primary)
        return primary

    def _build_work_items_page(self) -> None:
        page = self._new_page("work-items")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(3, weight=1)
        self.work_page = page
        self.work_new_button = self._page_header(
            page,
            title="Manage Work Items",
            purpose="Find, create, and organize Work Items from a configured folder.",
            primary_text="New Work Item...",
            primary_command=lambda: self._mock_status("Mockup: New Work Item would open an attended form."),
        )

        source = ttk.Frame(page, style="Mockup.Card.TFrame", padding=(10, 8))
        source.grid(row=1, column=0, sticky=tk.EW, pady=(0, 10))
        source.columnconfigure(1, weight=1)
        ttk.Label(source, text="CURRENT SOURCE", style="Mockup.CardMuted.TLabel").grid(
            row=0, column=0, columnspan=4, sticky=tk.W, pady=(0, 5)
        )
        ttk.Label(source, text="Source", style="Mockup.Card.TLabel").grid(
            row=1, column=0, sticky=tk.W, padx=(0, 8)
        )
        self.work_source_var = tk.StringVar(value="CAP40 Product")
        self.work_source_combo = ttk.Combobox(
            source,
            textvariable=self.work_source_var,
            values=("CAP40 Product", "Unavailable archive"),
            state="readonly",
        )
        self.work_source_combo.grid(row=1, column=1, sticky=tk.EW)
        self.work_source_combo.bind("<<ComboboxSelected>>", self._work_source_changed)
        self.manage_sources_button = ttk.Button(
            source,
            text="Manage sources...",
            command=self._show_manage_sources,
        )
        self.manage_sources_button.grid(row=1, column=2, padx=(8, 0))
        self.work_refresh_button = ttk.Button(source, text="Refresh", command=self._mock_refresh)
        self.work_refresh_button.grid(row=1, column=3, padx=(8, 0))
        ttk.Label(source, text="Folder", style="Mockup.Card.TLabel").grid(
            row=2, column=0, sticky=tk.NW, padx=(0, 8), pady=(7, 0)
        )
        self.work_path_var = tk.StringVar(value=r"D:\work\cap40-product\workitems")
        self.work_path_label = ttk.Label(
            source,
            textvariable=self.work_path_var,
            style="Mockup.Card.TLabel",
            justify=tk.LEFT,
            wraplength=560,
        )
        self.work_path_label.grid(row=2, column=1, columnspan=3, sticky=tk.EW, pady=(7, 0))
        self.work_source_status_var = tk.StringVar(value="Available - 9 Work Items discovered")
        self.work_source_status_label = ttk.Label(
            source,
            textvariable=self.work_source_status_var,
            style="Success.TLabel",
        )
        self.work_source_status_label.grid(row=3, column=1, columnspan=3, sticky=tk.W, pady=(4, 0))
        source.bind(
            "<Configure>",
            lambda event: self.work_path_label.configure(wraplength=max(240, int(event.width) - 100)),
        )

        find = ttk.Frame(page)
        find.grid(row=2, column=0, sticky=tk.EW, pady=(0, 6))
        find.columnconfigure(1, weight=1)
        ttk.Label(find, text="Find").grid(row=0, column=0, sticky=tk.W, padx=(0, 6))
        self.work_search_var = tk.StringVar()
        self.work_search = ttk.Entry(find, textvariable=self.work_search_var)
        self.work_search.grid(row=0, column=1, sticky=tk.EW)
        self.work_search.bind("<KeyRelease>", lambda _event: self._render_work_items())
        self.work_count_var = tk.StringVar()
        ttk.Label(find, textvariable=self.work_count_var, style="Muted.TLabel").grid(
            row=0, column=2, sticky=tk.E, padx=(8, 0)
        )

        self.work_tree_frame, self.work_tree = _scrollable_tree(page, ("type", "project"))
        self.work_tree_frame.grid(row=3, column=0, sticky=tk.NSEW)
        self.work_tree.heading("#0", text="Work Item")
        self.work_tree.heading("type", text="Type")
        self.work_tree.heading("project", text="Project")
        self.work_tree.column("#0", width=420, minwidth=220, stretch=True)
        self.work_tree.column("type", width=110, minwidth=90, stretch=False)
        self.work_tree.column("project", width=100, minwidth=84, stretch=False)
        self.work_tree.bind("<<TreeviewSelect>>", self._work_item_selected)

        self.work_selection = ttk.Frame(page, style="Mockup.Card.TFrame", padding=(10, 8))
        self.work_selection.grid(row=4, column=0, sticky=tk.EW, pady=(10, 0))
        self.work_selection.columnconfigure(0, weight=1)
        self.work_detail_title_var = tk.StringVar(value="Select a Work Item")
        self.work_detail_meta_var = tk.StringVar(value="Folder, Contexts, and personal tags appear here.")
        ttk.Label(
            self.work_selection,
            textvariable=self.work_detail_title_var,
            style="Mockup.Card.TLabel",
            font=("Segoe UI Semibold", 10),
        ).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            self.work_selection,
            textvariable=self.work_detail_meta_var,
            style="Mockup.CardMuted.TLabel",
            justify=tk.LEFT,
        ).grid(row=1, column=0, sticky=tk.W, pady=(4, 0))
        selection_commands = ttk.Frame(self.work_selection, style="Mockup.Card.TFrame")
        selection_commands.grid(row=0, column=1, rowspan=2, sticky=tk.E)
        self.work_organize_button = ttk.Menubutton(
            selection_commands,
            text="Organize",
            state=tk.DISABLED,
        )
        self.work_organize_menu = tk.Menu(
            self.work_organize_button,
            tearoff=False,
        )
        self.work_organize_menu.add_command(
            label="Edit tags & contexts…",
            command=lambda: self._mock_status(
                "Mockup: tags and Context membership would open."
            ),
        )
        self.work_organize_menu.add_separator()
        self.work_organize_menu.add_command(
            label="Forget Palette organization…",
            command=lambda: self._mock_status(
                "Mockup: a precise Forget preview would open."
            ),
        )
        self.work_organize_button.configure(menu=self.work_organize_menu)
        self.work_organize_button.pack(side=tk.LEFT)
        self.work_open_button = ttk.Button(
            selection_commands,
            text="Open folder",
            state=tk.DISABLED,
            command=lambda: self._mock_status("Mockup only: no folder was opened."),
        )
        self.work_open_button.pack(side=tk.LEFT, padx=(6, 0))
        self.critical(
            self.work_source_combo,
            self.manage_sources_button,
            self.work_refresh_button,
            self.work_search,
            self.work_tree,
            self.work_organize_button,
            self.work_open_button,
        )
        self._render_work_items()

    def _build_actions_page(self) -> None:
        page = self._new_page("actions")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)
        self.actions_page = page
        other_menu = tk.Menu(page, tearoff=False)
        other_menu.add_command(
            label="Browse Action types...",
            command=lambda: self._mock_status("Mockup: the Action type catalogue would open within Actions."),
        )
        other_menu.add_command(
            label="Harvest documents...",
            command=lambda: self._mock_status("Mockup: attended document harvesting would open."),
        )
        other_button = ttk.Menubutton(page, text="Other ways to create", menu=other_menu)
        self.actions_new_button = self._page_header(
            page,
            title="Manage Actions",
            purpose="Create, find, edit, archive, and restore saved Actions.",
            primary_text="New Action...",
            primary_command=lambda: self._mock_status("Mockup: the Action type chooser would open."),
            secondary=other_button,
        )
        self.critical(other_button)

        find = ttk.Frame(page)
        find.grid(row=1, column=0, sticky=tk.EW, pady=(0, 6))
        find.columnconfigure(1, weight=1)
        ttk.Label(find, text="Find").grid(row=0, column=0, sticky=tk.W, padx=(0, 6))
        self.action_search_var = tk.StringVar()
        self.action_search = ttk.Entry(find, textvariable=self.action_search_var)
        self.action_search.grid(row=0, column=1, sticky=tk.EW)
        self.action_search.bind("<KeyRelease>", lambda _event: self._render_actions())
        ttk.Label(find, text="Show").grid(row=0, column=2, padx=(10, 6))
        self.action_state_var = tk.StringVar(value="Active")
        self.action_state = ttk.Combobox(
            find,
            textvariable=self.action_state_var,
            values=("Active", "Archived", "All"),
            state="readonly",
            width=10,
        )
        self.action_state.grid(row=0, column=3)
        self.action_state.bind("<<ComboboxSelected>>", lambda _event: self._render_actions())
        self.action_count_var = tk.StringVar()
        ttk.Label(find, textvariable=self.action_count_var, style="Muted.TLabel").grid(
            row=0, column=4, padx=(8, 0)
        )

        self.actions_tree_frame, self.actions_tree = _scrollable_tree(
            page, ("type", "contexts", "source")
        )
        self.actions_tree_frame.grid(row=2, column=0, sticky=tk.NSEW)
        for column, label in (
            ("#0", "Action"),
            ("type", "Type"),
            ("contexts", "Contexts"),
            ("source", "Source"),
        ):
            self.actions_tree.heading(column, text=label)
        self.actions_tree.column("#0", width=310, minwidth=220, stretch=True)
        self.actions_tree.column("type", width=150, minwidth=120, stretch=False)
        self.actions_tree.column("contexts", width=150, minwidth=120, stretch=False)
        self.actions_tree.column("source", width=140, minwidth=120, stretch=False)
        self.actions_tree.bind("<<TreeviewSelect>>", self._action_selected)
        page.bind("<Configure>", self._resize_action_columns, add="+")

        self.action_selection = ttk.Frame(page, style="Mockup.Card.TFrame", padding=(10, 8))
        self.action_selection.grid(row=3, column=0, sticky=tk.EW, pady=(10, 0))
        self.action_selection.columnconfigure(0, weight=1)
        self.action_detail_title_var = tk.StringVar(value="Select an Action")
        self.action_detail_meta_var = tk.StringVar(value="Contexts, tags, ownership, and lifecycle appear here.")
        ttk.Label(
            self.action_selection,
            textvariable=self.action_detail_title_var,
            style="Mockup.Card.TLabel",
            font=("Segoe UI Semibold", 10),
        ).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            self.action_selection,
            textvariable=self.action_detail_meta_var,
            style="Mockup.CardMuted.TLabel",
        ).grid(row=1, column=0, sticky=tk.W, pady=(4, 0))
        action_commands = ttk.Frame(self.action_selection, style="Mockup.Card.TFrame")
        action_commands.grid(row=0, column=1, rowspan=2, sticky=tk.E)
        self.action_edit_button = ttk.Button(
            action_commands,
            text="Edit...",
            state=tk.DISABLED,
            command=lambda: self._mock_status("Mockup: the selected Action editor would open."),
        )
        self.action_edit_button.pack(side=tk.LEFT)
        self.action_lifecycle_button = ttk.Button(
            action_commands,
            text="Archive...",
            state=tk.DISABLED,
            command=self._mock_lifecycle,
        )
        self.action_lifecycle_button.pack(side=tk.LEFT, padx=(6, 0))
        self.action_delete_button = ttk.Button(
            action_commands,
            text="Delete permanently...",
            state=tk.DISABLED,
            style="Mockup.Danger.TButton",
            command=lambda: self._mock_status("Mockup only: no Action was deleted."),
        )
        self.action_delete_button.pack(side=tk.LEFT, padx=(6, 0))
        self.critical(
            self.action_search,
            self.action_state,
            self.actions_tree,
            self.action_edit_button,
            self.action_lifecycle_button,
            self.action_delete_button,
        )
        self._render_actions()

    def _apply_initial_scenario(self) -> None:
        if self.selected_page == "work-items":
            if self.scenario == "no-match":
                self.work_search_var.set("no matching work item")
                self._render_work_items()
            elif self.scenario == "unavailable":
                self.work_source_var.set("Unavailable archive")
                self._work_source_changed()
                self._select_first(self.work_tree)
            else:
                self._select_first(self.work_tree)
        elif self.selected_page == "actions":
            if self.scenario == "archived":
                self.action_state_var.set("Archived")
                self._render_actions()
            self._select_first(self.actions_tree)

    @staticmethod
    def _select_first(tree: ttk.Treeview) -> None:
        children = tree.get_children("")
        if children:
            tree.selection_set(children[0])
            tree.focus(children[0])
            tree.event_generate("<<TreeviewSelect>>")

    def _mock_status(self, message: str) -> None:
        self.status_var.set(message)

    def _render_work_items(self) -> None:
        query = self.work_search_var.get().strip().casefold() if hasattr(self, "work_search_var") else ""
        selected = self.work_tree.selection() if hasattr(self, "work_tree") else ()
        if hasattr(self, "work_tree"):
            self.work_tree.delete(*self.work_tree.get_children(""))
            visible = [
                item
                for item in WORK_ITEM_EXAMPLES
                if not query
                or query in " ".join(
                    (item.name, item.kind, item.project, item.contexts, item.tags)
                ).casefold()
            ]
            for item in visible:
                self.work_tree.insert("", tk.END, iid=item.name, text=item.name, values=(item.kind, item.project))
            self.work_count_var.set(f"{len(visible)} shown")
            if selected and self.work_tree.exists(selected[0]):
                self.work_tree.selection_set(selected[0])
            elif not visible:
                self.work_detail_title_var.set("No Work Items match this search")
                self.work_detail_meta_var.set("Clear Find to show the source again.")
                self.work_organize_button.configure(state=tk.DISABLED)
                self.work_open_button.configure(state=tk.DISABLED)

    def _work_item_selected(self, _event: tk.Event | None = None) -> None:
        selection = self.work_tree.selection()
        if not selection:
            return
        item = next(value for value in WORK_ITEM_EXAMPLES if value.name == selection[0])
        self.work_detail_title_var.set(f"{item.name}    {item.kind} - {item.project}")
        self.work_detail_meta_var.set(
            f"Folder: {item.name}\nContexts: {item.contexts}    Tags: {item.tags}"
        )
        self.work_organize_button.configure(state=tk.NORMAL)
        self.work_open_button.configure(state=tk.NORMAL)

    def _work_source_changed(self, _event: tk.Event | None = None) -> None:
        if self.work_source_var.get() == "Unavailable archive":
            self.work_path_var.set(r"Z:\archive\cap40\workitems")
            self.work_source_status_var.set("Unavailable - showing 9 last-known Work Items")
            self.work_source_status_label.configure(style="Error.TLabel")
        else:
            self.work_path_var.set(r"D:\work\cap40-product\workitems")
            self.work_source_status_var.set("Available - 9 Work Items discovered")
            self.work_source_status_label.configure(style="Success.TLabel")

    def _mock_refresh(self) -> None:
        self.work_refresh_button.configure(state=tk.DISABLED)
        self.status_var.set("Mockup: refreshing the in-memory examples...")
        self.root.after(
            450,
            lambda: (
                self.work_refresh_button.configure(state=tk.NORMAL),
                self.status_var.set("Mockup: refresh complete; no files were inspected."),
            ),
        )

    def _show_manage_sources(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Manage Work Item sources - mockup")
        dialog.transient(self.root)
        dialog.geometry("520x300")
        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Manage sources", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            frame,
            text="This inert example shows where Add, Edit, Remove, and template setup converge.",
            style="Muted.TLabel",
            wraplength=460,
        ).pack(anchor=tk.W, pady=(3, 12))
        tree = ttk.Treeview(frame, columns=("folder", "state"), show="headings", height=5)
        tree.heading("folder", text="Folder")
        tree.heading("state", text="State")
        tree.column("folder", width=300, stretch=True)
        tree.column("state", width=100, stretch=False)
        tree.insert("", tk.END, values=(r"D:\work\cap40-product\workitems", "Available"))
        tree.insert("", tk.END, values=(r"Z:\archive\cap40\workitems", "Unavailable"))
        tree.pack(fill=tk.BOTH, expand=True)
        commands = ttk.Frame(frame)
        commands.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(commands, text="Add source...", command=lambda: None).pack(side=tk.LEFT)
        ttk.Button(commands, text="Edit source...", command=lambda: None).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(commands, text="Creation template...", command=lambda: None).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(commands, text="Close", command=dialog.destroy).pack(side=tk.RIGHT)

    def _render_actions(self) -> None:
        query = self.action_search_var.get().strip().casefold() if hasattr(self, "action_search_var") else ""
        state = self.action_state_var.get() if hasattr(self, "action_state_var") else "Active"
        selected = self.actions_tree.selection() if hasattr(self, "actions_tree") else ()
        if hasattr(self, "actions_tree"):
            self.actions_tree.delete(*self.actions_tree.get_children(""))
            visible = [
                action
                for action in ACTION_EXAMPLES
                if (state == "All" or action.state == state)
                and (
                    not query
                    or query in " ".join(
                        (action.name, action.kind, action.contexts, action.source, action.tags)
                    ).casefold()
                )
            ]
            for index, action in enumerate(visible):
                self.actions_tree.insert(
                    "",
                    tk.END,
                    iid=f"action-{index}",
                    text=action.name,
                    values=(action.kind, action.contexts, action.source),
                    tags=(action.state.casefold(),),
                )
            self.action_count_var.set(f"{len(visible)} shown")
            if selected and self.actions_tree.exists(selected[0]):
                self.actions_tree.selection_set(selected[0])
            elif not visible:
                self.action_detail_title_var.set("No Actions match this view")
                self.action_detail_meta_var.set("Change Find or Show to see Actions.")
                self._set_action_commands(None)

    def _selected_action(self) -> ActionExample | None:
        selection = self.actions_tree.selection()
        if not selection:
            return None
        values = self.actions_tree.item(selection[0])
        name = str(values.get("text", ""))
        return next((action for action in ACTION_EXAMPLES if action.name == name), None)

    def _action_selected(self, _event: tk.Event | None = None) -> None:
        action = self._selected_action()
        if action is None:
            self._set_action_commands(None)
            return
        self.action_detail_title_var.set(
            f"{action.name}    {action.kind} - {action.state} - {action.source}"
        )
        self.action_detail_meta_var.set(
            f"Contexts: {action.contexts}    Tags: {action.tags}"
        )
        self._set_action_commands(action)

    def _set_action_commands(self, action: ActionExample | None) -> None:
        state = tk.NORMAL if action is not None else tk.DISABLED
        self.action_edit_button.configure(state=state)
        self.action_lifecycle_button.configure(
            state=state,
            text="Restore..." if action is not None and action.state == "Archived" else "Archive...",
        )
        self.action_delete_button.configure(state=state)

    def _mock_lifecycle(self) -> None:
        action = self._selected_action()
        if action is None:
            return
        verb = "restore" if action.state == "Archived" else "archive"
        self.status_var.set(f"Mockup only: would review references before {verb}.")

    def _resize_action_columns(self, event: tk.Event) -> None:
        if not hasattr(self, "actions_tree"):
            return
        self.actions_tree.configure(
            displaycolumns=("type", "contexts", "source")
            if int(event.width) >= 720
            else ("type", "source")
        )


class MainPaletteMockup(MockupView):
    """Compact daily-use mockup with no real actions or clipboard access."""

    def __init__(
        self,
        root: tk.Tk,
        *,
        scenario: str,
        size_key: str,
        scaling: int | None,
    ) -> None:
        super().__init__(root)
        self.scenario = scenario
        self.size_key = size_key
        self.scaling = scaling or 100
        self.scope = "all"
        self.current_context = "General"
        self.context_scope = CONTEXT_SCOPE_EVERYWHERE
        self.tag_filter: str | None = None
        self.sequence_running = False
        self._placeholder_active = True
        self.result_items: dict[str, PaletteExample] = {}
        self.preview_var = tk.StringVar(
            value="Select an Action or Work Item to see Input -> Effect before Run or Open."
        )
        self.icons = load_ui_icons(
            root,
            (
                "filters",
                "edit",
                "folder",
                "configure",
                "help",
                "more",
                "capture",
                "inbox",
                "ocr",
                "create_from_input",
                "text_tools",
            ),
            foreground=COLORS["text"],
        )

        outer = ttk.Frame(root, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)
        self.panes = ttk.Panedwindow(outer, orient=tk.HORIZONTAL)
        self.panes.pack(fill=tk.BOTH, expand=True)
        self.discovery = ttk.Frame(self.panes, padding=(0, 0, 6, 0))
        self.workspace = ttk.Frame(self.panes, padding=(6, 0, 0, 0))
        self.panes.add(self.discovery, weight=41)
        self.panes.add(self.workspace, weight=59)
        self._last_split_width = 0
        self._split_after_id: str | None = None
        self.panes.bind("<Configure>", self._queue_split, add="+")
        self.discovery.columnconfigure(0, weight=1)
        self.discovery.rowconfigure(3, weight=1)
        self.workspace.columnconfigure(0, weight=1)
        self.workspace.rowconfigure(1, weight=1)
        self._build_discovery()
        self._build_workspace()
        self._apply_initial_scenario()

    def _build_discovery(self) -> None:
        context_row = ttk.Frame(self.discovery)
        context_row.grid(row=0, column=0, sticky=tk.EW, pady=(0, 4))
        context_row.columnconfigure(0, weight=1)
        self.context_var = tk.StringVar(value="Context: All contexts")
        self.context_picker = ttk.Menubutton(
            context_row,
            textvariable=self.context_var,
            style="Compact.TButton",
        )
        self.context_menu = tk.Menu(self.context_picker, tearoff=False)
        for context in ("General", "Developing", "CAP40 delivery", "Empty UAT"):
            self.context_menu.add_command(
                label="All contexts" if context == "General" else context,
                command=lambda value=context: self._set_working_context(value),
            )
        self.context_menu.add_separator()
        self.context_menu.add_command(
            label="Manage contexts...",
            command=lambda: self._mock_preview("Mockup: Context management would open."),
        )
        self.context_picker.configure(menu=self.context_menu)
        self.context_picker.grid(row=0, column=0, sticky=tk.EW, padx=(0, 3))
        self._hint(
            self.context_picker,
            "Context — Choose your Working context. It supplies slots 6–0 when Find is empty.",
        )

        self.context_scope_var = tk.StringVar(value="Everywhere")
        self.context_scope_picker = ttk.Menubutton(
            context_row,
            textvariable=self.context_scope_var,
            style="Compact.TButton",
            takefocus=True,
        )
        self.context_scope_menu = tk.Menu(self.context_scope_picker, tearoff=False)
        self.context_scope_menu.add_command(
            label="Everywhere",
            command=lambda: self._set_context_scope(CONTEXT_SCOPE_EVERYWHERE),
        )
        self.context_scope_menu.add_command(
            label="This context",
            command=lambda: self._set_context_scope(CONTEXT_SCOPE_THIS),
        )
        self.context_scope_picker.configure(menu=self.context_scope_menu)
        self.context_scope_picker.grid(row=0, column=1, sticky=tk.EW)
        self._hint(
            self.context_scope_picker,
            "Search scope — Choose Everywhere to browse all Contexts, or This context to limit results to the Working context.",
        )
        self._sync_context_scope_control()

        scopes = ttk.Frame(self.discovery)
        scopes.grid(row=1, column=0, sticky=tk.EW, pady=(0, 4))
        for column in range(3):
            scopes.columnconfigure(column, weight=1, uniform="scope")
        self.scope_buttons: dict[str, ttk.Button] = {}
        for column, (key, label, hint) in enumerate(
            (
                ("all", "All items", "Show Actions and Work Items together."),
                ("actions", "Actions", "Show Actions only."),
                ("work-items", "Work Items", "Show Work Items only."),
            )
        ):
            button = ttk.Button(
                scopes,
                text=label,
                width=1,
                command=lambda value=key: self._set_scope(value),
                style="Mockup.ScopeSelected.TButton" if key == "all" else "Mockup.Scope.TButton",
            )
            button.grid(row=0, column=column, sticky=tk.EW, padx=(0 if column == 0 else 2, 0))
            self.scope_buttons[key] = button
            self._hint(button, hint)

        find = ttk.Frame(self.discovery)
        find.grid(row=2, column=0, sticky=tk.EW, pady=(0, 4))
        find.columnconfigure(0, weight=1)
        self.find_var = tk.StringVar(value="Find items...")
        self.find_entry = ttk.Entry(find, textvariable=self.find_var)
        self.find_entry.grid(row=0, column=0, sticky=tk.EW, padx=(0, 4))
        self.find_entry.bind("<FocusIn>", self._clear_placeholder)
        self.find_entry.bind("<FocusOut>", self._restore_placeholder)
        self.find_entry.bind("<KeyRelease>", lambda _event: self._render_results())
        self.filter_menu = tk.Menu(find, tearoff=False)
        self.filter_menu.add_command(
            label="Filter by tag: project",
            command=lambda: self._set_tag_filter("project"),
        )
        self.filter_menu.add_separator()
        self.filter_menu.add_command(label="Clear filters", command=lambda: self._set_tag_filter(None))
        self.filter_button = ttk.Menubutton(
            find,
            image=self.icons["filters"],
            menu=self.filter_menu,
            style="Icon.TButton",
            takefocus=True,
        )
        self.filter_button.grid(row=0, column=1)
        self._hint(
            self.filter_button,
            "Filters narrow results without changing the Working context or search scope.",
        )

        self.filter_chip = ttk.Button(
            self.discovery,
            text="",
            command=lambda: self._set_tag_filter(None),
            style="Compact.TButton",
        )

        self.results_host = ttk.Frame(self.discovery)
        self.results_host.grid(row=3, column=0, sticky=tk.NSEW)
        self.results_host.rowconfigure(0, weight=1)
        self.results_host.columnconfigure(0, weight=1)
        self.results_tree_frame, self.results = _scrollable_tree(self.results_host, ())
        self.results_tree_frame.grid(row=0, column=0, sticky=tk.NSEW)
        self.results.configure(show="tree", selectmode="browse")
        self.results.column("#0", stretch=True, width=260, minwidth=180)
        self.results.tag_configure("context_slot", background=COLORS["slot_focus"])
        self.results.bind("<<TreeviewSelect>>", self._selection_changed)
        self.results.bind("<Double-1>", lambda _event: self._activate_primary())
        self.empty_state = ttk.Frame(
            self.results_host,
            style="Mockup.Card.TFrame",
            padding=14,
        )
        self.empty_state.columnconfigure(0, weight=1)
        self.empty_state_var = tk.StringVar()
        ttk.Label(
            self.empty_state,
            textvariable=self.empty_state_var,
            style="Mockup.Card.TLabel",
            justify=tk.CENTER,
            wraplength=240,
        ).grid(row=0, column=0, sticky=tk.EW)

        toolbar = ttk.Frame(self.discovery)
        toolbar.grid(row=4, column=0, sticky=tk.EW, pady=(6, 0))
        toolbar.columnconfigure(2, weight=1)
        self.new_action_button = ttk.Button(
            toolbar,
            text="+A",
            command=lambda: self._mock_preview("Mockup: the normal Action type chooser would open."),
            style="RailAccent.TButton",
        )
        self.new_action_button.grid(row=0, column=0, sticky=tk.EW)
        self.edit_button = ttk.Button(
            toolbar,
            image=self.icons["edit"],
            command=lambda: self._mock_preview("Mockup: the selected item editor would open."),
            style="Icon.TButton",
            state=tk.DISABLED,
        )
        self.edit_button.grid(row=0, column=1, padx=(4, 0))
        self.folder_button = ttk.Button(
            toolbar,
            image=self.icons["folder"],
            command=lambda: self._mock_preview("Mockup only: no Work Item folder was opened."),
            style="Icon.TButton",
        )
        self.folder_button.grid(row=0, column=3, padx=(4, 0))
        self.folder_button.grid_remove()
        self.primary_button = ttk.Button(
            toolbar,
            text="Open / Run",
            command=self._activate_primary,
            style="RailAccent.TButton",
            state=tk.DISABLED,
        )
        self.primary_button.grid(row=0, column=4, sticky=tk.E, padx=(4, 0))
        self._hint(self.new_action_button, "New Action - choose a type and review its form.")
        self._hint(self.edit_button, "Edit the selected Action or Work Item.")
        self._hint(self.folder_button, "Open the selected Work Item folder.")

        self.quick_host = ttk.Frame(self.discovery)
        self.quick_host.grid(row=5, column=0, sticky=tk.EW, pady=(7, 0))
        self.quick_host.columnconfigure(0, weight=1)
        self.quick_canvas = tk.Canvas(
            self.quick_host,
            highlightthickness=0,
            borderwidth=0,
            background=COLORS["background"],
        )
        self.quick_scrollbar = ttk.Scrollbar(
            self.quick_host,
            orient=tk.VERTICAL,
            command=self.quick_canvas.yview,
        )
        self.quick_canvas.configure(yscrollcommand=self.quick_scrollbar.set)
        self.quick_canvas.grid(row=0, column=0, sticky=tk.EW)
        self.quick_scrollbar.grid(row=0, column=1, sticky=tk.NS)
        self.quick_body = ttk.Frame(self.quick_canvas)
        self.quick_window = self.quick_canvas.create_window(
            (0, 0),
            window=self.quick_body,
            anchor=tk.NW,
        )
        self.quick_buttons: list[ttk.Menubutton] = []
        self.quick_group_order = tuple(label for label, _source in QUICK_ACTION_MOCKUP_GROUPS)
        for label, source in QUICK_ACTION_MOCKUP_GROUPS:
            menu = tk.Menu(self.quick_body, tearoff=False)
            menu.add_command(
                label=f"Example from {label}",
                command=lambda value=label: self._mock_preview(
                    f"Mockup only: a {value} Quick action would run."
                ),
            )
            button = ttk.Menubutton(
                self.quick_body,
                text=label,
                menu=menu,
                style="SurfaceMenu.TLabel",
            )
            setattr(button, "mockup_quick_source", source)
            self.quick_buttons.append(button)
        self.quick_body.bind("<Configure>", self._sync_quick_scrollregion)
        self.quick_canvas.bind("<Configure>", self._resize_quick_actions)
        self.quick_canvas.bind(
            "<MouseWheel>",
            lambda event: self.quick_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units"),
        )
        self.root.after_idle(self._size_quick_actions)

        app_controls = ttk.Frame(self.discovery)
        app_controls.grid(row=6, column=0, sticky=tk.EW, pady=(6, 0))
        self.configure_button = ttk.Button(
            app_controls,
            image=self.icons["configure"],
            command=lambda: self._mock_preview("Mockup: Configure would open."),
            style="Icon.TButton",
        )
        self.configure_button.pack(side=tk.LEFT)
        self.help_button = ttk.Button(
            app_controls,
            image=self.icons["help"],
            command=lambda: self._mock_preview("Mockup: task-oriented Help would open."),
            style="Icon.TButton",
        )
        self.help_button.pack(side=tk.LEFT, padx=(4, 0))
        more_menu = tk.Menu(app_controls, tearoff=False)
        more_menu.add_command(label="Keyboard shortcuts", command=lambda: self._mock_preview("Mockup: shortcuts."))
        more_menu.add_command(label="Hide", command=lambda: self._mock_preview("Mockup only: window kept open."))
        more_menu.add_command(label="Quit", command=self.root.destroy)
        self.more_button = ttk.Menubutton(
            app_controls,
            image=self.icons["more"],
            menu=more_menu,
            style="Icon.TButton",
        )
        self.more_button.pack(side=tk.LEFT, padx=(4, 0))
        self._hint(self.configure_button, "Configure Context Palette.")
        self._hint(self.help_button, "Open Help.")
        self._hint(self.more_button, "Keyboard shortcuts, Hide, and Quit.")

        self.critical(
            self.context_picker,
            self.context_scope_picker,
            *self.scope_buttons.values(),
            self.find_entry,
            self.filter_button,
            self.results,
            self.new_action_button,
            self.edit_button,
            self.primary_button,
            self.quick_canvas,
            self.configure_button,
            self.help_button,
            self.more_button,
        )

    def _build_workspace(self) -> None:
        tools = ttk.Frame(self.workspace)
        tools.grid(row=0, column=0, sticky=tk.EW, pady=(0, 4))
        tool_commands = ttk.Frame(tools)
        tool_commands.pack(side=tk.RIGHT)
        self.workspace_buttons: list[ttk.Button | ttk.Menubutton] = []
        tool_specs = (
            ("capture", "Capture clipboard text to Inbox", "Mockup only: clipboard was not read."),
            ("inbox", "Open Inbox", "Mockup: Inbox would open."),
            ("ocr", "Extract image text", "Mockup only: no image or clipboard was read."),
            (
                "create_from_input",
                "Create Action from Input",
                "Mockup: a defensible suggestion would open for review.",
            ),
        )
        for icon, hint, status in tool_specs:
            button = ttk.Button(
                tool_commands,
                image=self.icons[icon],
                command=lambda message=status: self._mock_preview(message),
                style="Icon.TButton",
                takefocus=True,
            )
            button.pack(side=tk.LEFT, padx=(0, 4))
            self._hint(button, hint)
            self.workspace_buttons.append(button)
        text_menu = tk.Menu(tools, tearoff=False)
        text_menu.add_command(
            label="Clean whitespace",
            command=lambda: self._mock_preview("Mockup: text would be transformed locally."),
        )
        text_menu.add_command(
            label="Lists and quoting",
            command=lambda: self._mock_preview("Mockup: a text tool would be selected."),
        )
        self.text_tools_button = ttk.Menubutton(
            tool_commands,
            image=self.icons["text_tools"],
            menu=text_menu,
            style="Icon.TButton",
            takefocus=True,
        )
        self.text_tools_button.pack(side=tk.LEFT)
        self._hint(self.text_tools_button, "Text tools for the current Input / Output content.")
        self.workspace_buttons.append(self.text_tools_button)

        text_frame = ttk.Frame(self.workspace)
        text_frame.grid(row=1, column=0, sticky=tk.NSEW)
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)
        self.text = tk.Text(
            text_frame,
            wrap=tk.WORD,
            width=1,
            height=1,
            font=("Consolas", 10),
            undo=True,
            borderwidth=1,
            relief=tk.SOLID,
            highlightthickness=0,
        )
        text_scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=text_scrollbar.set)
        self.text.grid(row=0, column=0, sticky=tk.NSEW)
        text_scrollbar.grid(row=0, column=1, sticky=tk.NS)
        self.text.insert(
            "1.0",
            "Prompt Helper is a planned Windows command-palette app for helping users work efficiently with ChatGPT, Codex, GitHub Copilot, and other agents.",
        )

        preview = ttk.Frame(self.workspace, style="Mockup.Card.TFrame", padding=(8, 6))
        preview.grid(row=2, column=0, sticky=tk.EW, pady=(6, 0))
        preview.columnconfigure(0, weight=1)
        self.preview_label = ttk.Label(
            preview,
            textvariable=self.preview_var,
            style="Mockup.CardMuted.TLabel",
            justify=tk.LEFT,
            width=1,
            wraplength=260,
        )
        self.preview_label.grid(row=0, column=0, sticky=tk.EW)
        preview.bind(
            "<Configure>",
            lambda event: self.preview_label.configure(wraplength=max(260, int(event.width) - 18)),
        )
        self.critical(*self.workspace_buttons, self.text, self.preview_label)

    def _hint(self, widget: tk.Widget, text: str) -> None:
        setattr(widget, "mockup_accessible_name", text)
        widget.bind("<Enter>", lambda _event, value=text: self.preview_var.set(value), add="+")
        widget.bind("<FocusIn>", lambda _event, value=text: self.preview_var.set(value), add="+")
        widget.bind("<Leave>", lambda _event: self._restore_selection_preview(), add="+")

    def _set_split(self) -> None:
        self._split_after_id = None
        self.root.update_idletasks()
        width = int(self.panes.winfo_width())
        if width <= 1:
            return
        desired = round(width * 0.41)
        high_scale = self.scaling >= 150
        minimum_discovery = 315 if high_scale else 286
        minimum_workspace = 340 if high_scale else 350
        position = max(minimum_discovery, min(desired, width - minimum_workspace))
        try:
            self.panes.sashpos(0, position)
        except tk.TclError:
            return

    def _queue_split(self, event: tk.Event) -> None:
        width = int(event.width)
        if width <= 1 or width == self._last_split_width:
            return
        self._last_split_width = width
        if self._split_after_id is not None:
            try:
                self.root.after_cancel(self._split_after_id)
            except tk.TclError:
                pass
        self._split_after_id = self.root.after_idle(self._set_split)

    def _clear_placeholder(self, _event: tk.Event) -> None:
        if self._placeholder_active:
            self.find_var.set("")
            self._placeholder_active = False

    def _restore_placeholder(self, _event: tk.Event) -> None:
        if not self.find_var.get():
            self.find_var.set("Find items...")
            self._placeholder_active = True

    def _set_working_context(self, context: str) -> None:
        self.current_context = context
        self.context_var.set(
            "Context: All contexts"
            if context.casefold() == "general"
            else f"Context: {context}"
        )
        self._sync_context_scope_control()
        self._render_results()

    def _set_context_scope(self, scope: str) -> None:
        if scope not in {CONTEXT_SCOPE_EVERYWHERE, CONTEXT_SCOPE_THIS}:
            raise ValueError(f"Unsupported Context scope: {scope}")
        if scope == CONTEXT_SCOPE_THIS and self.current_context.casefold() == "general":
            scope = CONTEXT_SCOPE_EVERYWHERE
            self._mock_preview(
                "Choose a specific Working context before limiting results to it."
            )
        self.context_scope = scope
        self._sync_context_scope_control()
        self._render_results()

    def _sync_context_scope_control(self) -> None:
        specific_context = self.current_context.casefold() != "general"
        if not specific_context and self.context_scope == CONTEXT_SCOPE_THIS:
            self.context_scope = CONTEXT_SCOPE_EVERYWHERE
        self.context_scope_var.set(
            "This context"
            if self.context_scope == CONTEXT_SCOPE_THIS
            else "Everywhere"
        )
        self.context_scope_picker.configure(
            style=(
                "Mockup.ScopeSelected.TButton"
                if self.context_scope == CONTEXT_SCOPE_THIS
                else "Compact.TButton"
            )
        )
        self.context_scope_menu.entryconfigure(
            1,
            state=tk.NORMAL if specific_context else tk.DISABLED,
        )

    def _set_scope(self, scope: str) -> None:
        self.scope = scope
        for key, button in self.scope_buttons.items():
            button.configure(
                style="Mockup.ScopeSelected.TButton" if key == scope else "Mockup.Scope.TButton"
            )
        self._render_results()

    def _set_tag_filter(self, tag: str | None) -> None:
        self.tag_filter = tag
        if tag is None:
            self.filter_chip.grid_remove()
        else:
            self.filter_chip.configure(text=f"Tag: {tag}  x")
            self.filter_chip.grid(row=3, column=0, sticky=tk.W, pady=(0, 4))
        self._render_results()

    def _query(self) -> str:
        if self._placeholder_active:
            return ""
        return self.find_var.get().strip().casefold()

    def _context_slot(self, item: PaletteExample) -> int | None:
        for context, slot in item.context_slots:
            if context.casefold() == self.current_context.casefold():
                return slot
        return None

    def _result_key(self, item: PaletteExample, query: str) -> tuple[int, str, str]:
        name = item.name.casefold()
        contexts = " ".join(item.contexts).casefold()
        tags = " ".join(item.tags).casefold()
        effect = item.effect.casefold()
        if not query:
            return 0, name, item.key
        rank = (
            0
            if name.startswith(query)
            else 1
            if query in name
            else 2
            if query in contexts or query in tags
            else 3
            if query in effect
            else 4
        )
        return rank, name, item.key

    def _render_results(self) -> None:
        selected = self.results.selection()
        query = self._query()
        visible: list[PaletteExample] = []
        for item in PALETTE_EXAMPLES:
            if self.scope == "actions" and item.kind not in {"action", "sequence"}:
                continue
            if self.scope == "work-items" and item.kind != "work-item":
                continue
            if (
                self.context_scope == CONTEXT_SCOPE_THIS
                and self.current_context.casefold()
                not in {context.casefold() for context in item.contexts}
            ):
                continue
            if self.tag_filter and self.tag_filter.casefold() not in {
                tag.casefold() for tag in item.tags
            }:
                continue
            document = " ".join(
                (item.name, item.kind, *item.contexts, *item.tags, item.effect)
            ).casefold()
            if query and query not in document:
                continue
            visible.append(item)

        self.results.delete(*self.results.get_children(""))
        self.result_items = {}
        slotted = (
            []
            if query
            else sorted(
                (
                    (slot, item)
                    for item in visible
                    if (slot := self._context_slot(item)) is not None
                ),
                key=lambda row: row[0],
            )
        )
        slotted_keys = {item.key for _slot, item in slotted}
        ordinary = sorted(
            (item for item in visible if item.key not in slotted_keys),
            key=lambda item: self._result_key(item, query),
        )
        rows = [*slotted, *((None, item) for item in ordinary)]
        for slot, item in rows:
            tags = ("context_slot",) if slot is not None else ()
            self.results.insert("", tk.END, iid=item.key, text=item.name, tags=tags)
            self.result_items[item.key] = item

        if visible:
            self.empty_state.grid_remove()
            self.results_tree_frame.grid()
            if selected and self.results.exists(selected[0]):
                self.results.selection_set(selected[0])
            else:
                self.results.selection_remove(self.results.selection())
                self._sync_selection_controls(None)
        else:
            self.results_tree_frame.grid_remove()
            self.empty_state_var.set(
                f"This context ({self.current_context}) has no members."
                if self.context_scope == CONTEXT_SCOPE_THIS and not query
                else "No items match Find and the active filters."
            )
            self.empty_state.grid(row=0, column=0, sticky=tk.NSEW)
            self._sync_selection_controls(None)

    def _selection_changed(self, _event: tk.Event | None = None) -> None:
        selection = self.results.selection()
        item = self.result_items.get(selection[0]) if selection else None
        self._sync_selection_controls(item)

    def _sync_selection_controls(self, item: PaletteExample | None) -> None:
        if self.sequence_running:
            self.primary_button.configure(text="Stop remaining", state=tk.NORMAL)
            self.edit_button.configure(state=tk.DISABLED)
            self.folder_button.grid_remove()
            return
        if item is None:
            self.primary_button.configure(text="Open / Run", state=tk.DISABLED)
            self.edit_button.configure(state=tk.DISABLED)
            self.folder_button.grid_remove()
            self.preview_var.set(
                "Select an Action or Work Item to see Input -> Effect before Run or Open."
            )
            return
        self.edit_button.configure(state=tk.NORMAL)
        if item.kind == "work-item":
            self.primary_button.configure(text="Open", state=tk.NORMAL)
            self.folder_button.grid()
        else:
            self.primary_button.configure(text="Run", state=tk.NORMAL)
            self.folder_button.grid_remove()
        self.preview_var.set(f"Input: selected {item.kind} -> Effect: {item.effect}")

    def _restore_selection_preview(self) -> None:
        if self.sequence_running:
            self.preview_var.set("Sequence step 2/3: waiting 5 seconds. Stop skips remaining steps.")
            return
        selection = self.results.selection()
        self._sync_selection_controls(self.result_items.get(selection[0]) if selection else None)

    def _activate_primary(self) -> None:
        if self.sequence_running:
            self.sequence_running = False
            self.preview_var.set(
                "Sequence stopped. Started 1 Action; remaining steps were skipped."
            )
            selection = self.results.selection()
            self._sync_selection_controls(self.result_items.get(selection[0]) if selection else None)
            return
        selection = self.results.selection()
        item = self.result_items.get(selection[0]) if selection else None
        if item is None:
            return
        if item.kind == "sequence":
            self.sequence_running = True
            self._sync_selection_controls(item)
            self.preview_var.set("Sequence step 2/3: waiting 5 seconds. Stop skips remaining steps.")
        else:
            verb = "open" if item.kind == "work-item" else "run"
            self.preview_var.set(f"Mockup only: would {verb} {item.name}; nothing was dispatched.")

    def _mock_preview(self, text: str) -> None:
        self.preview_var.set(text)

    def _sync_quick_scrollregion(self, _event: tk.Event | None = None) -> None:
        self.quick_canvas.configure(scrollregion=self.quick_canvas.bbox("all"))

    def _resize_quick_actions(self, event: tk.Event) -> None:
        width = max(1, int(event.width))
        self.quick_canvas.itemconfigure(self.quick_window, width=width)
        columns = 1 if width < 250 else 2
        for child in self.quick_buttons:
            child.grid_forget()
        for index, button in enumerate(self.quick_buttons):
            row = index // columns
            column = index % columns
            button.grid(
                row=row,
                column=column,
                sticky=tk.EW,
                padx=(0 if column == 0 else 4, 0),
                pady=(0, 4),
            )
        for column in range(2):
            self.quick_body.columnconfigure(column, weight=1 if column < columns else 0)
        self._sync_quick_scrollregion()

    def _size_quick_actions(self) -> None:
        self.root.update_idletasks()
        rows = 4 if self.size_key == SIZE_NORMAL else 3
        if self.scaling >= 150:
            rows -= 1
        if self.size_key == SIZE_MINIMUM and self.scaling >= 150:
            rows = 1
        example_height = max((button.winfo_reqheight() for button in self.quick_buttons), default=28)
        self.quick_canvas.configure(height=max(54, rows * (example_height + 4)))

    def _apply_initial_scenario(self) -> None:
        self._render_results()
        if self.scenario == "no-selection":
            return
        if self.scenario == "work-item":
            self._set_scope("all")
            self._select_result("work-item-kilit")
        elif self.scenario == "context-slots":
            self._set_working_context("Developing")
            self._select_first_result()
        elif self.scenario == "this-context":
            self._set_working_context("Developing")
            self._set_context_scope(CONTEXT_SCOPE_THIS)
            self._select_first_result()
        elif self.scenario == "zero-match":
            self._set_working_context("Developing")
            self._set_context_scope(CONTEXT_SCOPE_THIS)
            self._placeholder_active = False
            self.find_var.set("nothing can match this")
            self._render_results()
        elif self.scenario == "sequence":
            self._select_result("sequence")
            self._activate_primary()
        elif self.scenario == "empty-context":
            self._set_working_context("Empty UAT")
            self._set_context_scope(CONTEXT_SCOPE_THIS)
        elif self.scenario == "sequence-stopped":
            self._select_result("sequence")
            self.sequence_running = False
            self.preview_var.set(
                "Sequence stopped. Started 1 Action; remaining steps were skipped."
            )
        else:
            self._select_result("professional-greeting")

    def _select_result(self, key: str) -> None:
        if self.results.exists(key):
            self.results.selection_set(key)
            self.results.focus(key)
            self.results.see(key)
            self._selection_changed()

    def _select_first_result(self) -> None:
        children = self.results.get_children("")
        if children:
            self._select_result(children[0])


def _set_window_geometry(root: tk.Tk, definition: MockupDefinition, size_key: str) -> None:
    width, height = definition.size(size_key)
    root.geometry(f"{width}x{height}")
    minimum_width, minimum_height = definition.minimum_size
    root.minsize(minimum_width, minimum_height)


def build_mockup(
    root: tk.Tk,
    *,
    screen: str,
    scenario: str,
    size: str,
    scaling: int | None,
) -> MockupView:
    definition = MOCKUP_DEFINITIONS.get(screen)
    if definition is None:
        raise ValueError(f"Unknown mockup screen: {screen}")
    scenario_keys = {key for key, _label in definition.scenarios}
    if scenario not in scenario_keys:
        raise ValueError(f"Unknown scenario {scenario!r} for {screen!r}")
    _configure_mockup_theme(root, scaling)
    _set_window_geometry(root, definition, size)
    root.title(f"{definition.label} - inert UI mockup")
    root.bind("<Escape>", lambda _event: root.destroy())
    if screen == MOCKUP_MAIN:
        return MainPaletteMockup(
            root,
            scenario=scenario,
            size_key=size,
            scaling=scaling,
        )
    page = "work-items" if screen == MOCKUP_WORK_ITEMS else "actions"
    return ConfigureMockup(root, page=page, scenario=scenario)


class MockupGallery:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        _configure_mockup_theme(root, None)
        root.title("Context Palette UI mockups")
        root.geometry("560x430")
        root.minsize(520, 390)
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Real-Tk UI mockups", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky=tk.W
        )
        ttk.Label(
            frame,
            text=(
                "Review the next visual baseline with safe example data. These windows "
                "do not read or change your Context Palette configuration."
            ),
            style="Muted.TLabel",
            wraplength=510,
            justify=tk.LEFT,
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(4, 18))

        self.screen_labels = {definition.label: key for key, definition in MOCKUP_DEFINITIONS.items()}
        self.screen_var = tk.StringVar(value=MOCKUP_DEFINITIONS[MOCKUP_MAIN].label)
        self.scenario_var = tk.StringVar()
        self.size_var = tk.StringVar(value="Normal")
        self.scaling_var = tk.StringVar(value="System")
        self._field(frame, 2, "Screen", self._screen_combo(frame))
        self.scenario_combo = ttk.Combobox(frame, textvariable=self.scenario_var, state="readonly")
        self._field(frame, 3, "State", self.scenario_combo)
        size_combo = ttk.Combobox(
            frame,
            textvariable=self.size_var,
            values=("Normal", "Minimum"),
            state="readonly",
        )
        self._field(frame, 4, "Window size", size_combo)
        scaling_combo = ttk.Combobox(
            frame,
            textvariable=self.scaling_var,
            values=("System",) + tuple(f"{value}%" for value in SCALE_PERCENTAGES),
            state="readonly",
        )
        self._field(frame, 5, "Text scaling", scaling_combo)
        self._sync_scenarios()

        notice = ttk.Frame(frame, style="Mockup.Card.TFrame", padding=10)
        notice.grid(row=6, column=0, columnspan=2, sticky=tk.EW, pady=(18, 0))
        ttk.Label(
            notice,
            text="What to check",
            style="Mockup.Card.TLabel",
            font=("Segoe UI Semibold", 10),
        ).pack(anchor=tk.W)
        ttk.Label(
            notice,
            text=(
                "No clipped commands; one clear primary action; results/table space dominates; "
                "and controls keep their place when the state changes."
            ),
            style="Mockup.CardMuted.TLabel",
            wraplength=490,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))
        commands = ttk.Frame(frame)
        commands.grid(row=7, column=0, columnspan=2, sticky=tk.EW, pady=(18, 0))
        ttk.Button(commands, text="Close", command=root.destroy).pack(side=tk.RIGHT)
        ttk.Button(
            commands,
            text="Open mockup",
            command=self.open_mockup,
            style="Accent.TButton",
        ).pack(side=tk.RIGHT, padx=(0, 8))

    def _field(self, parent: ttk.Frame, row: int, label: str, widget: ttk.Widget) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=4, padx=(0, 12))
        widget.grid(row=row, column=1, sticky=tk.EW, pady=4)

    def _screen_combo(self, parent: ttk.Frame) -> ttk.Combobox:
        combo = ttk.Combobox(
            parent,
            textvariable=self.screen_var,
            values=tuple(self.screen_labels),
            state="readonly",
        )
        combo.bind("<<ComboboxSelected>>", lambda _event: self._sync_scenarios())
        return combo

    def _sync_scenarios(self) -> None:
        key = self.screen_labels[self.screen_var.get()]
        scenarios = MOCKUP_DEFINITIONS[key].scenarios
        labels = tuple(label for _scenario, label in scenarios)
        self.scenario_combo.configure(values=labels)
        self.scenario_var.set(labels[0])

    def open_mockup(self) -> None:
        screen = self.screen_labels[self.screen_var.get()]
        definition = MOCKUP_DEFINITIONS[screen]
        scenarios = {label: key for key, label in definition.scenarios}
        scenario = scenarios[self.scenario_var.get()]
        size = SIZE_NORMAL if self.size_var.get() == "Normal" else SIZE_MINIMUM
        scaling_label = self.scaling_var.get()
        scaling = SYSTEM_SCALING if scaling_label == "System" else scaling_label.rstrip("%")
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "context_palette.ui_mockups",
                "--screen",
                screen,
                "--scenario",
                scenario,
                "--size",
                size,
                "--scaling",
                scaling,
            ],
            close_fds=True,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open inert real-Tk Context Palette UI mockups.")
    parser.add_argument("--screen", choices=MOCKUP_KEYS)
    parser.add_argument("--scenario")
    parser.add_argument("--size", choices=SIZE_KEYS, default=SIZE_NORMAL)
    parser.add_argument(
        "--scaling",
        choices=(SYSTEM_SCALING,) + tuple(str(value) for value in SCALE_PERCENTAGES),
        default=SYSTEM_SCALING,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = tk.Tk()
    if args.screen is None:
        MockupGallery(root)
    else:
        definition = MOCKUP_DEFINITIONS[args.screen]
        scenario = args.scenario or definition.scenarios[0][0]
        scaling = None if args.scaling == SYSTEM_SCALING else int(args.scaling)
        build_mockup(
            root,
            screen=args.screen,
            scenario=scenario,
            size=args.size,
            scaling=scaling,
        )
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
