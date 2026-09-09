"""Attended opt-in drop settings; this dialog never executes an Action."""

from __future__ import annotations

import tkinter as tk
import json
from tkinter import ttk
from typing import Callable, Iterable

from .action_picker import ActionPickerField, ActionPickerOption
from .actions import Action, ActionError, action_search_text
from .drop_action import (
    DropActionSettings,
    approve_drop_action,
    drop_action_eligibility,
    resolve_drop_action,
)
from .window_geometry import configure_standard_window


class DropConfigurationWindow:
    def __init__(
        self,
        parent: tk.Misc,
        *,
        actions: Iterable[Action],
        settings: DropActionSettings,
        on_save: Callable[[DropActionSettings], bool | None],
    ) -> None:
        self.actions = tuple(actions)
        self.on_save = on_save
        self.previous_grab = parent.grab_current()
        self.window = tk.Toplevel(parent)
        self.window.title("Drop settings")
        configure_standard_window(self.window, parent)
        self.window.protocol("WM_DELETE_WINDOW", self._close)
        self.window.bind("<Escape>", lambda _event: self._close())
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)

        body = ttk.Frame(self.window, padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(4, weight=1)
        body.rowconfigure(7, weight=1)
        ttk.Label(body, text="On drop").grid(row=0, sticky="w", pady=(0, 8))
        self.mode_var = tk.StringVar(self.window, value=settings.mode)
        self.show_radio = ttk.Radiobutton(
            body, text="Show in Context Palette (default)",
            value="show", variable=self.mode_var, command=self._refresh,
        )
        self.show_radio.grid(row=1, sticky="w")
        self.action_radio = ttk.Radiobutton(
            body, text="Run an Action…", value="action",
            variable=self.mode_var, command=self._refresh,
        )
        self.action_radio.grid(row=2, sticky="w", pady=(6, 6))
        self.actions_by_label = {
            f"{action.title} [{action.id}]": action
            for action in self.actions
            if drop_action_eligibility(action).eligible
        }
        resolution = resolve_drop_action(settings, self.actions)
        approved = resolution.action
        current_label = f"{approved.title} [{approved.id}]" if approved else ""
        self.action_var = tk.StringVar(self.window, value=current_label)
        self.action_picker = ActionPickerField(
            body, variable=self.action_var,
            options=(
                ActionPickerOption(action.id, label, action_search_text(action))
                for label, action in self.actions_by_label.items()
            ),
            title="Choose an Action to run on drop", button_text="Choose…",
            scope_note="Run directly on dropped content, without placing it in Input / Output. Only compatible Active Actions are selectable; existing Action-specific confirmations still apply.",
        )
        self.action_picker.grid(row=3, sticky="ew", pady=(0, 8))
        self.effect_var = tk.StringVar(self.window)
        details = ttk.Frame(body)
        details.grid(row=4, sticky="nsew", pady=(0, 10))
        details.columnconfigure(0, weight=1)
        details.rowconfigure(0, weight=1)
        self.configured_details = tk.Text(
            details, height=8, width=1, wrap=tk.WORD, undo=False, takefocus=True,
        )
        self.configured_details.grid(row=0, column=0, sticky="nsew")
        details_scrollbar = ttk.Scrollbar(details, command=self.configured_details.yview)
        details_scrollbar.grid(row=0, column=1, sticky="ns")
        self.configured_details.configure(yscrollcommand=details_scrollbar.set)
        ttk.Label(body, text="Unavailable Actions — why they cannot run on drop").grid(
            row=6, sticky="w", pady=(0, 4),
        )
        unavailable_frame = ttk.Frame(body)
        unavailable_frame.grid(row=7, sticky="nsew")
        unavailable_frame.columnconfigure(0, weight=1)
        unavailable_frame.rowconfigure(0, weight=1)
        self.unavailable = ttk.Treeview(
            unavailable_frame, columns=("action", "reason"), show="headings", height=4,
        )
        self.unavailable.heading("action", text="Action")
        self.unavailable.heading("reason", text="Reason")
        self.unavailable.column("action", width=185, minwidth=120)
        self.unavailable.column("reason", width=480, minwidth=250)
        self.unavailable.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(unavailable_frame, command=self.unavailable.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.unavailable.configure(yscrollcommand=scrollbar.set)
        self.unavailable_reasons: dict[str, str] = {}
        for index, action in enumerate(self.actions):
            eligibility = drop_action_eligibility(action)
            if not eligibility.eligible:
                key = str(index)
                self.unavailable.insert("", tk.END, iid=key, values=(action.title, eligibility.reason))
                self.unavailable_reasons[key] = eligibility.reason
        self.reason_var = tk.StringVar(self.window)
        ttk.Label(body, textvariable=self.reason_var, wraplength=680).grid(
            row=8, sticky="ew", pady=(6, 0),
        )
        self.unavailable.bind("<<TreeviewSelect>>", self._show_unavailable_reason)

        footer = ttk.Frame(self.window, padding=(12, 0, 12, 12))
        footer.grid(row=1, column=0, sticky="ew")
        self.feedback_var = tk.StringVar(self.window, value=resolution.reason)
        ttk.Label(footer, textvariable=self.feedback_var, wraplength=680).pack(
            fill=tk.X, pady=(0, 8),
        )
        self.save_button = ttk.Button(footer, text="Save", command=self._save, style="Accent.TButton")
        self.save_button.pack(side=tk.LEFT)
        self.cancel_button = ttk.Button(footer, text="Cancel", command=self._close)
        self.cancel_button.pack(side=tk.RIGHT)
        self.action_var.trace_add("write", lambda *_args: self._refresh())
        self._refresh()
        self.window.transient(parent.winfo_toplevel())
        self.window.grab_set()
        self._focus_after_id = self.window.after_idle(self.show_radio.focus_set)

    def _show_unavailable_reason(self, _event: object = None) -> None:
        selected = self.unavailable.selection()
        self.reason_var.set(self.unavailable_reasons.get(selected[0], "") if selected else "")

    def _refresh(self) -> None:
        is_action = self.mode_var.get() == "action"
        self.action_picker.choose_button.configure(state=tk.NORMAL if is_action else tk.DISABLED)
        action = self.actions_by_label.get(self.action_var.get()) if is_action else None
        self.effect_var.set(
            drop_action_eligibility(action).effect if action else (
                "Choose an Action to review its exact input and effect."
                if is_action else
                "Reveal the Palette and Input / Output. Existing text keeps its Replace / Append / Cancel choice; the clipboard stays unchanged."
            )
        )
        lines = [self.effect_var.get()]
        if action is not None:
            lines.extend((
                "", f"Action type: {action.type}",
                "Configured target / template / operation:", action.value,
                "", "Configured arguments (in order):",
                json.dumps(list(action.arguments), ensure_ascii=False),
                f"Working folder: {action.working_directory or '(not configured)'}",
                "", "Input: the exact dropped content, sent directly to the Action without Replace / Append or reading Input / Output. Supported input placeholders use that content; nothing is expanded or executed in this view.",
                "Input / Output changes only if this Action produces text output. Failed drops remain available in Drop history.",
                "Saving permits this effect on each new drop. Existing Action confirmations still apply. Send again only shows the content; failures are not retried automatically.",
            ))
        self.configured_details.configure(state=tk.NORMAL)
        self.configured_details.delete("1.0", tk.END)
        self.configured_details.insert("1.0", "\n".join(lines))
        self.configured_details.configure(state=tk.DISABLED)
        self.configured_details.yview_moveto(0.0)
        self.save_button.configure(state=tk.NORMAL if not is_action or action else tk.DISABLED)

    def _save(self) -> None:
        try:
            if self.mode_var.get() == "action":
                action = self.actions_by_label.get(self.action_var.get())
                if action is None:
                    self.feedback_var.set("Choose a compatible Action first.")
                    return
                settings = approve_drop_action(action)
            else:
                settings = DropActionSettings()
            if self.on_save(settings) is False:
                self.feedback_var.set("Drop settings were not saved. Review the reported error and try again.")
                return
        except (ActionError, OSError) as exc:
            self.feedback_var.set(f"Drop settings were not saved: {exc}")
            return
        self._close()

    def _close(self) -> None:
        self.window.after_cancel(self._focus_after_id)
        self.window.destroy()
        if self.previous_grab is not None:
            try:
                self.previous_grab.grab_set()
            except tk.TclError:
                pass
