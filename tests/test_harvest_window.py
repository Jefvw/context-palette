from __future__ import annotations

import json
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from context_palette.actions import load_actions
from context_palette.harvest import (
    HarvestBatch,
    HarvestCandidate,
    HarvestError,
    normalize_url_for_comparison,
)
from context_palette.harvest_window import HarvestWindow


class FakeButton:
    def __init__(self) -> None:
        self.state = "normal"

    def configure(self, **options: str) -> None:
        self.state = options.get("state", self.state)


class FakeVariable:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


def ready_candidate(*, selected: bool = True) -> HarvestCandidate:
    return HarvestCandidate(
        "candidate",
        "Open guide",
        "https://example.test/guide",
        normalize_url_for_comparison("https://example.test/guide"),
        [],
        selected=selected,
    )


def minimal_window(path: Path, candidate: HarvestCandidate) -> HarvestWindow:
    window = HarvestWindow.__new__(HarvestWindow)
    window.batch = HarvestBatch(candidates=[candidate])
    window.actions = []
    window.actions_path = path
    window.submitting = False
    window.create_button = FakeButton()
    window.status_var = FakeVariable()
    window.window = Mock()
    window.on_change = Mock()
    window._render_candidates = Mock()
    window._update_create_state = Mock()
    return window


def descendants(widget: tk.Misc):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class HarvestCreationTests(unittest.TestCase):
    def test_selected_drafts_are_created_in_one_atomic_batch(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "actions.json"
            path.write_text('{"actions": []}\n', encoding="utf-8")
            window = minimal_window(path, ready_candidate())
            with patch("context_palette.harvest_window.messagebox.askyesno", return_value=True), patch(
                "context_palette.harvest_window.messagebox.showinfo"
            ):
                window._create()

            actions = load_actions(path)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].state, "Draft")
        self.assertEqual(actions[0].type, "open_url")
        window.on_change.assert_called_once_with()

    def test_confirmation_cancel_does_not_change_action_store(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "actions.json"
            original = '{"actions": []}\n'
            path.write_text(original, encoding="utf-8")
            window = minimal_window(path, ready_candidate())
            with patch("context_palette.harvest_window.messagebox.askyesno", return_value=False):
                window._create()
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_first_creation_supports_an_absent_personal_action_store(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "actions.json"
            window = minimal_window(path, ready_candidate())

            drafts = window._drafts()

        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].type, "open_url")

    def test_invalid_selected_candidate_is_reported_before_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "actions.json"
            path.write_text('{"actions": []}\n', encoding="utf-8")
            candidate = ready_candidate()
            candidate.classification = "Unsupported"
            window = minimal_window(path, candidate)
            with patch("context_palette.harvest_window.append_actions") as append, patch(
                "context_palette.harvest_window.messagebox.showerror"
            ) as showerror:
                window._create()

        append.assert_not_called()
        showerror.assert_called_once()

    def test_double_submission_is_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "actions.json"
            window = minimal_window(path, ready_candidate())
            window.submitting = True
            with patch("context_palette.harvest_window.append_actions") as append:
                window._create()
        append.assert_not_called()

    def test_existing_url_is_rechecked_immediately_before_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "actions.json"
            path.write_text(
                json.dumps(
                    {
                        "actions": [
                            {
                                "id": "existing-guide",
                                "title": "Existing guide",
                                "type": "open_url",
                                "value": "https://example.test/guide",
                                "state": "Draft",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            window = minimal_window(path, ready_candidate())
            with patch("context_palette.harvest_window.append_actions") as append, patch(
                "context_palette.harvest_window.messagebox.showerror"
            ) as showerror:
                window._create()

        append.assert_not_called()
        self.assertIn("already uses this URL", showerror.call_args.args[1])

    def test_duplicate_is_rechecked_after_confirmation_before_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "actions.json"
            path.write_text('{"actions": []}\n', encoding="utf-8")
            window = minimal_window(path, ready_candidate())
            draft = window._drafts()[0]
            with patch.object(
                window,
                "_drafts",
                side_effect=[[draft], HarvestError("A Draft already uses this URL.")],
            ), patch(
                "context_palette.harvest_window.messagebox.askyesno", return_value=True
            ), patch(
                "context_palette.harvest_window.messagebox.showerror"
            ) as showerror, patch(
                "context_palette.harvest_window.append_actions"
            ) as append:
                window._create()

        append.assert_not_called()
        self.assertIn("confirmation was open", showerror.call_args.args[1])

    def test_duplicate_edited_targets_are_rejected_as_one_batch(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "actions.json"
            path.write_text('{"actions": []}\n', encoding="utf-8")
            first = ready_candidate()
            second = ready_candidate()
            second.id = "second"
            window = minimal_window(path, first)
            window.batch.candidates.append(second)

            with self.assertRaisesRegex(ValueError, "Another selected candidate uses this URL"):
                window._drafts()


class HarvestWindowSmokeTests(unittest.TestCase):
    def test_real_window_exposes_bulk_review_controls(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        root.geometry("1x1+0+0")
        root.update_idletasks()
        try:
            with tempfile.TemporaryDirectory() as temporary, patch(
                "context_palette.harvest_window.filedialog.askopenfilenames",
                return_value=(),
            ):
                actions_path = Path(temporary) / "actions.json"
                actions_path.write_text(json.dumps({"actions": []}), encoding="utf-8")
                window = HarvestWindow(
                    root,
                    actions=[],
                    context_names=("General", "Database"),
                    focus_context="Database",
                    actions_path=actions_path,
                    on_change=lambda: None,
                )
                root.update()
                button_labels = {
                    child.cget("text")
                    for child in descendants(window.window)
                    if isinstance(child, ttk.Button)
                }
                for label in (
                    "Add documents…",
                    "Remove",
                    "Scan / Rescan",
                    "Cancel scan",
                    "Select all Ready",
                    "Select source",
                    "Deselect source",
                    "Edit candidate…",
                    "Preview selected Drafts",
                    "Create selected Drafts",
                ):
                    self.assertIn(label, button_labels)
                window.window.update_idletasks()
                window_bottom = window.window.winfo_rooty() + window.window.winfo_height()
                entries = [
                    child
                    for child in descendants(window.window)
                    if isinstance(child, ttk.Entry)
                ]
                self.assertGreaterEqual(len(entries), 3)
                for entry in entries:
                    self.assertTrue(entry.winfo_ismapped())
                    self.assertLessEqual(
                        entry.winfo_rooty() + entry.winfo_height(),
                        window_bottom,
                    )
                window._close()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
