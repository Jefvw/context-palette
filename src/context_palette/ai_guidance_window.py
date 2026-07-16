from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Iterable

from .actions import Action
from .ai_guidance import (
    AIGuidanceError,
    ActionProposal,
    PROMPT_VARIATIONS,
    PromptVariation,
    build_ai_request,
    build_example_response,
    review_ai_proposals,
)
from .inbox import InboxItem


class AIGuidanceWindow:
    def __init__(
        self,
        parent: tk.Toplevel,
        item: InboxItem,
        contexts: Iterable[str],
        on_create: Callable[[InboxItem, list[Action]], None],
    ) -> None:
        self.item = item
        self.contexts = tuple(contexts)
        self.on_create = on_create
        self.proposals: list[ActionProposal] = []

        self.window = tk.Toplevel(parent)
        self.window.title("Ask AI for Draft Action Proposals")
        self.window.geometry("780x700")
        self.window.minsize(620, 520)

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text=f"Captured item: {item.title}", style="Heading.TLabel").pack(
            fill=tk.X
        )
        variation_row = ttk.Frame(outer)
        variation_row.pack(fill=tk.X, pady=(8, 6))
        ttk.Label(variation_row, text="AI guidance").pack(side=tk.LEFT)
        self.variation_var = tk.StringVar(value=PROMPT_VARIATIONS[0].label)
        self.variation_box = ttk.Combobox(
            variation_row,
            textvariable=self.variation_var,
            values=[variation.label for variation in PROMPT_VARIATIONS],
            state="readonly",
            width=42,
        )
        self.variation_box.pack(side=tk.LEFT, padx=(8, 0))
        self.variation_box.bind("<<ComboboxSelected>>", lambda _event: self._update_request())

        ttk.Label(outer, text="Request to send to your AI").pack(anchor=tk.W)
        self.request = tk.Text(outer, height=13, wrap=tk.WORD)
        self.request.pack(fill=tk.BOTH, expand=True, pady=(3, 6))

        request_controls = ttk.Frame(outer)
        request_controls.pack(fill=tk.X)
        ttk.Button(request_controls, text="Copy AI request", command=self._copy_request).pack(
            side=tk.LEFT
        )
        ttk.Label(
            request_controls,
            text="Review captured content before sharing it with an external AI.",
            style="Muted.TLabel",
        ).pack(side=tk.LEFT, padx=(10, 0))

        ttk.Label(outer, text="AI JSON response").pack(anchor=tk.W, pady=(10, 0))
        self.response = tk.Text(outer, height=9, wrap=tk.NONE)
        self.response.pack(fill=tk.BOTH, expand=True, pady=(3, 6))

        response_controls = ttk.Frame(outer)
        response_controls.pack(fill=tk.X)
        ttk.Button(response_controls, text="Paste response", command=self._paste_response).pack(
            side=tk.LEFT
        )
        ttk.Button(
            response_controls,
            text="Insert test response",
            command=self._insert_test_response,
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(response_controls, text="Review proposals", command=self._review_response).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        self.review_status_var = tk.StringVar(
            value="No response reviewed yet. Test responses stay entirely local."
        )
        ttk.Label(
            outer,
            textvariable=self.review_status_var,
            style="Muted.TLabel",
        ).pack(fill=tk.X, pady=(4, 0))

        ttk.Label(outer, text="Validated Draft proposals").pack(anchor=tk.W, pady=(10, 0))
        proposal_area = ttk.Frame(outer)
        proposal_area.pack(fill=tk.BOTH, expand=True, pady=(3, 0))
        self.proposal_list = tk.Listbox(
            proposal_area,
            height=5,
            selectmode=tk.EXTENDED,
            exportselection=False,
        )
        self.proposal_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.proposal_list.bind("<<ListboxSelect>>", lambda _event: self._update_preview())
        self.preview = tk.Text(proposal_area, height=5, width=42, wrap=tk.WORD)
        self.preview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        self.preview.configure(state=tk.DISABLED)

        footer = ttk.Frame(outer)
        footer.pack(fill=tk.X, pady=(10, 0))
        self.create_button = ttk.Button(
            footer,
            text="Create selected Drafts",
            command=self._create_selected,
            state=tk.DISABLED,
            style="Accent.TButton",
        )
        self.create_button.pack(side=tk.LEFT)
        ttk.Button(footer, text="Close", command=self.window.destroy).pack(side=tk.RIGHT)

        self._update_request()
        self.window.transient(parent)
        self.window.lift()

    def _variation(self) -> PromptVariation:
        label = self.variation_var.get()
        return next(
            (variation for variation in PROMPT_VARIATIONS if variation.label == label),
            PROMPT_VARIATIONS[0],
        )

    def _update_request(self) -> None:
        text = build_ai_request(self.item, self._variation(), self.contexts)
        self.request.delete("1.0", tk.END)
        self.request.insert("1.0", text)

    def _copy_request(self) -> None:
        text = self.request.get("1.0", "end-1c")
        self.window.clipboard_clear()
        self.window.clipboard_append(text)
        messagebox.showinfo(
            "Context Palette",
            "AI request copied. Paste it into your chosen AI, then paste its JSON response here.",
            parent=self.window,
        )

    def _paste_response(self) -> None:
        try:
            text = self.window.clipboard_get()
        except tk.TclError:
            messagebox.showerror(
                "Context Palette", "The clipboard does not contain text.", parent=self.window
            )
            return
        self.response.delete("1.0", tk.END)
        self.response.insert("1.0", text)

    def _insert_test_response(self) -> None:
        text = build_example_response(
            self.item,
            self.item.suggested_context or next(iter(self.contexts), "General"),
            self._variation(),
        )
        self.response.delete("1.0", tk.END)
        self.response.insert("1.0", text)
        self.review_status_var.set("Local test response inserted. Click Review proposals.")

    def _review_response(self) -> None:
        try:
            review = review_ai_proposals(
                self.response.get("1.0", "end-1c"),
                self._variation(),
            )
        except AIGuidanceError as exc:
            self.proposals = []
            self._render_proposals()
            self.review_status_var.set("Response envelope could not be validated.")
            messagebox.showerror("Context Palette", str(exc), parent=self.window)
            return
        self.proposals = list(review.proposals)
        self._render_proposals()
        if review.issues:
            self.review_status_var.set(
                f"{len(review.proposals)} valid; {len(review.issues)} rejected."
            )
            messagebox.showwarning(
                "Some proposals were rejected",
                "\n\n".join(review.issues),
                parent=self.window,
            )
        else:
            self.review_status_var.set(f"{len(review.proposals)} valid proposal(s).")

    def _render_proposals(self) -> None:
        self.proposal_list.delete(0, tk.END)
        for proposal in self.proposals:
            self.proposal_list.insert(tk.END, proposal.action.display_text)
        if self.proposals:
            self.proposal_list.selection_set(0, tk.END)
            self.proposal_list.activate(0)
            self.create_button.configure(state=tk.NORMAL)
        else:
            self.create_button.configure(state=tk.DISABLED)
        self._update_preview()

    def _update_preview(self) -> None:
        selected = self.proposal_list.curselection()
        if not selected or selected[0] >= len(self.proposals):
            text = "Validate an AI response to review its proposals."
        else:
            proposal = self.proposals[selected[0]]
            action = proposal.action
            text = (
                f"{action.display_text}\n"
                f"Type: {action.type}\n"
                f"State: Draft\n\n"
                f"Why proposed: {proposal.explanation}\n\n"
                f"Action text:\n{action.value}"
            )
        self.preview.configure(state=tk.NORMAL)
        self.preview.delete("1.0", tk.END)
        self.preview.insert("1.0", text)
        self.preview.configure(state=tk.DISABLED)

    def _create_selected(self) -> None:
        indexes = self.proposal_list.curselection()
        actions = [self.proposals[index].action for index in indexes if index < len(self.proposals)]
        if not actions:
            messagebox.showerror(
                "Context Palette", "Select at least one validated proposal.", parent=self.window
            )
            return
        if not messagebox.askyesno(
            "Create Draft actions",
            f"Create {len(actions)} selected local Draft action(s)?",
            parent=self.window,
        ):
            return
        self.on_create(self.item, actions)
        self.window.destroy()
