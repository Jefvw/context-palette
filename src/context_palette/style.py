from __future__ import annotations

import tkinter as tk
from tkinter import ttk


COLORS = {
    "background": "#f5f7f8",
    "surface": "#ffffff",
    "topic_header": "#eef2f4",
    "accent": "#087f78",
    "accent_hover": "#066a65",
    "row_aqua": "#d8eeeb",
    "row_light": "#e8f3f2",
    "text": "#1f2933",
    "muted_text": "#52616b",
    "white": "#ffffff",
    "border": "#c4cdd3",
    "focus": "#005fcc",
    "success": "#18794e",
    "warning": "#9a6700",
    "error": "#b42318",
}

DEFAULT_FONT = "{Segoe UI} 10"
TITLE_FONT = ("Segoe UI Semibold", 14)
HEADING_FONT = ("Segoe UI Semibold", 11)
CAPTION_FONT = ("Segoe UI", 9)


def configure_theme(root: tk.Misc, style: ttk.Style | None = None) -> ttk.Style:
    """Apply the shared accessible Windows theme."""
    style = style or ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    root.option_add("*Font", DEFAULT_FONT)
    root.option_add("*Listbox.background", COLORS["surface"])
    root.option_add("*Listbox.foreground", COLORS["text"])
    root.option_add("*Listbox.selectBackground", COLORS["accent"])
    root.option_add("*Listbox.selectForeground", COLORS["white"])
    root.option_add("*Text.background", COLORS["surface"])
    root.option_add("*Text.foreground", COLORS["text"])
    root.option_add("*Canvas.background", COLORS["background"])
    root.configure(background=COLORS["background"])

    style.configure(".", background=COLORS["background"], foreground=COLORS["text"])
    style.configure("TFrame", background=COLORS["background"])
    style.configure("TLabel", background=COLORS["background"], foreground=COLORS["text"])
    style.configure(
        "Title.TLabel",
        background=COLORS["background"],
        foreground=COLORS["text"],
        font=TITLE_FONT,
    )
    style.configure(
        "Heading.TLabel",
        background=COLORS["background"],
        foreground=COLORS["text"],
        font=HEADING_FONT,
    )
    style.configure(
        "PaneHeader.TLabel",
        background=COLORS["background"],
        foreground=COLORS["text"],
        font=HEADING_FONT,
    )
    style.configure("Muted.TLabel", foreground=COLORS["muted_text"], font=CAPTION_FONT)
    style.configure(
        "Status.TLabel",
        foreground=COLORS["muted_text"],
        font=CAPTION_FONT,
        padding=(2, 2),
    )
    style.configure(
        "Success.TLabel",
        foreground=COLORS["success"],
        font=CAPTION_FONT,
        padding=(2, 2),
    )
    style.configure(
        "Error.TLabel",
        foreground=COLORS["error"],
        font=CAPTION_FONT,
        padding=(2, 2),
    )
    style.configure(
        "TButton",
        background=COLORS["topic_header"],
        foreground=COLORS["text"],
        bordercolor=COLORS["border"],
        padding=(8, 5),
    )
    style.map(
        "TButton",
        background=[("active", COLORS["row_aqua"]), ("pressed", COLORS["accent"])],
        foreground=[("pressed", COLORS["white"])],
        bordercolor=[("focus", COLORS["focus"])],
    )
    style.configure(
        "Compact.TButton",
        background=COLORS["topic_header"],
        foreground=COLORS["text"],
        bordercolor=COLORS["border"],
        padding=(6, 3),
        font=CAPTION_FONT,
    )
    style.map(
        "Compact.TButton",
        background=[("active", COLORS["row_aqua"]), ("pressed", COLORS["accent"])],
        bordercolor=[("focus", COLORS["focus"])],
    )
    style.configure(
        "Accent.TButton",
        background=COLORS["accent"],
        foreground=COLORS["white"],
        font=("Segoe UI Semibold", 10),
        padding=(14, 7),
    )
    style.map(
        "Accent.TButton",
        background=[("active", COLORS["accent_hover"]), ("pressed", COLORS["focus"])],
        foreground=[("disabled", COLORS["muted_text"]), ("!disabled", COLORS["white"])],
        bordercolor=[("focus", COLORS["focus"])],
    )
    style.configure(
        "TEntry",
        fieldbackground=COLORS["surface"],
        foreground=COLORS["text"],
        bordercolor=COLORS["border"],
        insertcolor=COLORS["text"],
        padding=5,
    )
    style.map("TEntry", bordercolor=[("focus", COLORS["focus"])])
    style.configure(
        "TCombobox",
        fieldbackground=COLORS["surface"],
        foreground=COLORS["text"],
        bordercolor=COLORS["border"],
        arrowcolor=COLORS["text"],
        padding=4,
    )
    style.map("TCombobox", bordercolor=[("focus", COLORS["focus"])])
    style.configure(
        "TLabelframe",
        background=COLORS["background"],
        bordercolor=COLORS["border"],
        padding=4,
    )
    style.configure(
        "TLabelframe.Label",
        background=COLORS["background"],
        foreground=COLORS["text"],
        font=("Segoe UI Semibold", 10),
    )
    style.configure(
        "Surface.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["text"],
        bordercolor=COLORS["border"],
        padding=(4, 3),
    )
    style.map(
        "Surface.TLabel",
        background=[("active", COLORS["row_aqua"]), ("focus", COLORS["row_aqua"])],
        bordercolor=[("focus", COLORS["focus"])],
    )
    style.configure(
        "Pin.TLabel",
        background=COLORS["row_light"],
        foreground=COLORS["text"],
        padding=(7, 3),
    )
    style.configure(
        "Context.TLabel",
        background=COLORS["row_aqua"],
        foreground=COLORS["text"],
        padding=(7, 3),
    )
    style.configure("TNotebook.Tab", padding=(12, 7), font=("Segoe UI Semibold", 10))
    style.map(
        "TNotebook.Tab",
        background=[("selected", COLORS["surface"]), ("active", COLORS["row_light"])],
        foreground=[("selected", COLORS["text"])],
    )
    style.configure(
        "Treeview",
        background=COLORS["surface"],
        fieldbackground=COLORS["surface"],
        foreground=COLORS["text"],
        rowheight=25,
        bordercolor=COLORS["border"],
    )
    style.map(
        "Treeview",
        background=[("selected", COLORS["accent"])],
        foreground=[("selected", COLORS["white"])],
    )
    style.configure(
        "Treeview.Heading",
        background=COLORS["topic_header"],
        foreground=COLORS["text"],
        font=("Segoe UI Semibold", 9),
        padding=(6, 5),
    )
    return style
