from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def scrollable_tree(
    parent: tk.Misc,
    columns: tuple[str, ...],
    *,
    height: int | None = None,
) -> tuple[ttk.Frame, ttk.Treeview]:
    """Create a consistently scrollable tree table."""
    container = ttk.Frame(parent)
    scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL)
    options: dict[str, object] = {
        "columns": columns,
        "show": "tree headings",
        "selectmode": "browse",
        "yscrollcommand": scrollbar.set,
    }
    if height is not None:
        options["height"] = height
    tree = ttk.Treeview(container, **options)
    scrollbar.configure(command=tree.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    return container, tree
