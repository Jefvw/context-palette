from __future__ import annotations

import tkinter as tk
from tkinter import ttk


COLORS = {
    "background": "#f7f9f9",
    "topic_header": "#a6a6a6",
    "accent": "#43bdb3",
    "accent_hover": "#35aaa1",
    "row_aqua": "#cce7e5",
    "row_light": "#e4f1f0",
    "text": "#45484a",
    "muted_text": "#687173",
    "white": "#ffffff",
    "border": "#9bcac6",
    "focus": "#168f87",
}

DEFAULT_FONT = "{Segoe UI} 10"
HEADING_FONT = ("Segoe UI Semibold", 11)


def configure_theme(root: tk.Misc, style: ttk.Style | None = None) -> ttk.Style:
    """Apply the shared visual theme without changing widget layout or geometry."""
    style = style or ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    root.option_add("*Font", DEFAULT_FONT)
    root.option_add("*Listbox.background", COLORS["row_light"])
    root.option_add("*Listbox.foreground", COLORS["text"])
    root.option_add("*Listbox.selectBackground", COLORS["accent"])
    root.option_add("*Listbox.selectForeground", COLORS["white"])
    root.option_add("*Text.background", COLORS["white"])
    root.option_add("*Text.foreground", COLORS["text"])
    root.option_add("*Canvas.background", COLORS["background"])
    root.configure(background=COLORS["background"])

    style.configure(".", background=COLORS["background"], foreground=COLORS["text"])
    style.configure("TFrame", background=COLORS["background"])
    style.configure("TLabel", background=COLORS["background"], foreground=COLORS["text"])
    style.configure(
        "Heading.TLabel",
        background=COLORS["topic_header"],
        foreground=COLORS["text"],
        font=HEADING_FONT,
        padding=(6, 3),
    )
    style.configure("Muted.TLabel", foreground=COLORS["muted_text"])
    style.configure(
        "TButton",
        background=COLORS["row_light"],
        foreground=COLORS["text"],
        bordercolor=COLORS["border"],
        padding=6,
    )
    style.map(
        "TButton",
        background=[("active", COLORS["row_aqua"]), ("pressed", COLORS["accent"])],
        bordercolor=[("focus", COLORS["focus"])],
    )
    style.configure(
        "Accent.TButton",
        background=COLORS["accent"],
        foreground=COLORS["white"],
        font=("Segoe UI Semibold", 10),
        padding=(14, 6),
    )
    style.map(
        "Accent.TButton",
        background=[("active", COLORS["accent_hover"]), ("pressed", COLORS["focus"])],
        foreground=[("disabled", COLORS["row_light"]), ("!disabled", COLORS["white"])],
    )
    style.configure(
        "TEntry",
        fieldbackground=COLORS["white"],
        foreground=COLORS["text"],
        bordercolor=COLORS["border"],
        insertcolor=COLORS["text"],
    )
    style.map("TEntry", bordercolor=[("focus", COLORS["focus"])])
    style.configure(
        "TCombobox",
        fieldbackground=COLORS["white"],
        foreground=COLORS["text"],
        bordercolor=COLORS["border"],
        arrowcolor=COLORS["text"],
    )
    style.map("TCombobox", bordercolor=[("focus", COLORS["focus"])])
    style.configure("TLabelframe", background=COLORS["background"], bordercolor=COLORS["border"])
    style.configure(
        "TLabelframe.Label",
        background=COLORS["accent"],
        foreground=COLORS["white"],
        font=("Segoe UI Semibold", 10),
    )
    style.configure(
        "Surface.TLabel",
        background=COLORS["row_light"],
        foreground=COLORS["text"],
        bordercolor=COLORS["border"],
    )
    style.map("Surface.TLabel", background=[("active", COLORS["row_aqua"])])
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
    return style
