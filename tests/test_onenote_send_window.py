"""Synthetic Tk lifecycle tests for attended OneNote Send; no Office access."""

from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from pathlib import Path
import gc
import json
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from context_palette.launcher import LauncherApp
from context_palette.onenote_integration import (
    NotebookRef,
    OneNoteSettings,
    load_onenote_settings,
    save_onenote_settings,
)
from context_palette.onenote_send import (
    Destination,
    Location,
    ReviewedPlan,
    SendError,
    SendOutcome,
    canonical_plan,
    load_destination,
    save_destination,
    suggested_title,
)
from context_palette.onenote_process import OwnedProcessError
from context_palette.onenote_send_window import DestinationChoice, OneNoteSendWindow
from context_palette.style import COLORS, configure_theme


def destination() -> Destination:
    return Destination((
        Location("notebook", "book-id", "Private notebook"),
        Location("section_group", "group-id", "Projects"),
        Location("section", "section-id", "Exact section"),
    ))


class FakeClient:
    def __init__(self) -> None:
        self.calls = []
        self.prepare_hook = None
        self.plan_hook = None
        self.inventory_hook = None
        self.execute_hook = None
        self.prepare_started = None

    def prepare(self, session_reader, cancel):
        self.calls.append(("prepare",))
        self.prepare_started = datetime.now().astimezone()
        if self.prepare_hook is not None:
            return self.prepare_hook(session_reader, cancel)
        return session_reader()

    def inventory(self, notebook, cancel):
        self.calls.append(("inventory", notebook))
        if self.inventory_hook is not None:
            return self.inventory_hook(notebook, cancel)
        return (destination(),)

    def plan(self, chosen, title, body, cancel):
        self.calls.append(("plan", chosen, title, body))
        if self.plan_hook is not None:
            return self.plan_hook(chosen, title, body, cancel)
        document = canonical_plan(chosen.section_id, title, body)
        return ReviewedPlan(chosen, json.dumps(document, ensure_ascii=False))

    def execute(self, review, authorization, cancel):
        self.calls.append(("execute", review, authorization))
        if self.execute_hook is not None:
            return self.execute_hook(review, authorization, cancel)
        return SendOutcome("content_verified", "created-page")


class OneNoteSendWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        # Finalize earlier Tk variables before creating another interpreter;
        # otherwise native callbacks and grabs can leak across the full suite.
        gc.collect()
        self.root = tk.Tk()
        self.root.withdraw()
        self.original_scaling = float(self.root.tk.call("tk", "scaling"))
        self.root.tk.call("tk", "scaling", 4 / 3)
        configure_theme(self.root)
        self.temporary = tempfile.TemporaryDirectory(prefix="palette send window ")
        self.base = Path(self.temporary.name)
        self.application_root = self.base / "installed" / "Context Palette"
        self.application_root.mkdir(parents=True)
        self.launcher = self.base / "python-onenote.bat"
        self.launcher.write_text("synthetic launcher, never executed", encoding="utf-8")
        self.settings_path = self.base / "local_onenote_settings.json"
        self.destination_path = self.base / "local_onenote_send_settings.json"
        self.notebook = NotebookRef("search-book", "Search scope")
        save_onenote_settings(
            self.settings_path, OneNoteSettings(self.launcher, self.notebook),
        )
        save_destination(self.destination_path, destination())
        self.source = {"text": "First line\nReviewed body", "revision": 1, "reads": 0}
        self.client = FakeClient()
        self.factory_paths = []
        self.session = ((101, 202),)
        self.now = datetime.now(timezone.utc)
        self.gesture = 100.0
        self.view = self.make_window()

    def tearDown(self) -> None:
        if self.view.busy:
            self.view.cancel()
            self.wait(lambda: not self.view.busy)
        self.root.tk.call("tk", "scaling", self.original_scaling)
        self.root.destroy()
        self.temporary.cleanup()

    def source_reader(self):
        self.source["reads"] += 1
        return self.source["text"], self.source["revision"]

    def client_factory(self, path):
        self.factory_paths.append(Path(path))
        return self.client

    def make_window(self, parent=None, **overrides):
        arguments = {
            "settings_path": self.settings_path,
            "destination_path": self.destination_path,
            "source_reader": self.source_reader,
            "client_factory": self.client_factory,
            "session_reader": lambda: self.session,
            "application_root": self.application_root,
            "clock": lambda: self.now,
            "gesture_clock": lambda: self.gesture,
        }
        arguments.update(overrides)
        return OneNoteSendWindow(parent or self.root, **arguments)

    @contextmanager
    def scaled_root(self, scaling):
        # Widget font caches use the scale at first construction. A fresh
        # interpreter per scale models startup at that DPI, rather than reusing
        # the setup window's fonts after changing the display-wide Tk scale.
        root = tk.Tk()
        root.withdraw()
        previous = float(root.tk.call("tk", "scaling"))
        try:
            root.tk.call("tk", "scaling", scaling)
            configure_theme(root)
            yield root
        finally:
            root.tk.call("tk", "scaling", previous)
            root.destroy()

    def wait(self, predicate, timeout=3, root=None):
        event_root = root or self.root
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not predicate():
            event_root.update()
            time.sleep(0.005)
        event_root.update()
        self.assertTrue(predicate())

    def settle_window(self, window):
        """Wait for native mapping and wrapping to settle, keeping fit checks strict."""
        window.deiconify()
        window.lift()
        previous = None
        stable = 0

        def settled():
            nonlocal previous, stable
            geometry = (window.winfo_geometry(), window.winfo_reqwidth(), window.winfo_reqheight())
            stable = stable + 1 if geometry == previous else 0
            previous = geometry
            return bool(window.winfo_ismapped()) and stable >= 2
        self.wait(settled, root=window)

    def test_open_title_and_source_notifications_do_not_access_onenote(self):
        self.assertEqual(self.source["reads"], 1)
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.view._destination, destination())

        self.view.title_var.set("Edited locally")
        self.view.source_changed()
        self.root.update()
        self.assertEqual(self.source["reads"], 1)
        self.assertEqual(self.client.calls, [])

        self.source.update(text="New source text", revision=2)
        self.view.capture_source()
        self.assertEqual(self.source["reads"], 2)
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.view.body_text.get("1.0", "end-1c"), "New source text")

    def test_source_revision_and_engine_change_require_fresh_click(self):
        self.source["revision"] += 1
        self.view.send()
        self.root.update()

        self.assertEqual(self.source["text"], "First line\nReviewed body")
        self.assertEqual(self.source["revision"], 2)
        self.assertFalse(any(call[0] == "execute" for call in self.client.calls))
        self.assertIn("Input / Output changed", self.view.status_var.get())

        self.view.capture_source()
        replacement = self.base / "replacement" / "python-onenote.bat"
        replacement.parent.mkdir()
        replacement.write_text("replacement fixture", encoding="utf-8")
        save_onenote_settings(
            self.settings_path, OneNoteSettings(replacement, self.notebook),
        )
        self.view.send()
        self.root.update()
        self.assertFalse(any(call[0] == "execute" for call in self.client.calls))
        self.assertIn("Engine changed", self.view.status_var.get())

    def test_double_send_is_one_execution_and_authority_precedes_readiness(self):
        self.view.send()
        self.view.send()
        self.wait(lambda: not self.view.busy)

        executions = [call for call in self.client.calls if call[0] == "execute"]
        self.assertEqual(len(executions), 1)
        self.assertEqual([call[0] for call in self.client.calls],
                         ["plan", "prepare", "inventory", "execute"])
        authorization = executions[0][2]
        confirmed = datetime.fromisoformat(authorization["confirmed_at"])
        self.assertIsNotNone(self.client.prepare_started)
        self.assertLessEqual(confirmed, self.client.prepare_started)
        self.assertEqual([receipt.state for receipt in self.view.receipts],
                         ["content_verified"])
        self.assertEqual(self.source["text"], "First line\nReviewed body")
        self.assertEqual(self.source["revision"], 1)

    def test_stale_cancelled_send_keeps_unknown_receipt_through_close(self):
        started = threading.Event()

        def delayed_unknown(_review, _authorization, cancel):
            started.set()
            cancel.wait(2)
            return SendOutcome("unknown")

        self.client.execute_hook = delayed_unknown
        self.view.send()
        self.wait(started.is_set)
        self.view.source_changed()  # Cancels and advances the read-generation token.
        self.assertFalse(self.view.close())
        self.wait(lambda: not self.view.busy)

        self.assertEqual([receipt.state for receipt in self.view.receipts], ["unknown"])
        self.assertTrue(self.view._receipt_unacknowledged)
        self.assertIn("may have been created", self.view.status_var.get())
        with patch("context_palette.onenote_send_window.messagebox.askyesno", return_value=False):
            self.assertFalse(self.view.close())
        with patch("context_palette.onenote_send_window.messagebox.askyesno", return_value=True):
            self.assertTrue(self.view.close())
        self.assertEqual([receipt.state for receipt in self.view.receipts], ["unknown"])
        self.assertEqual(self.view.window.state(), "withdrawn")

    def test_exception_after_execution_call_boundary_is_unknown(self):
        def lost_after_execute_started(_review, _authorization, _cancel):
            raise RuntimeError("synthetic lost execution response")

        self.client.execute_hook = lost_after_execute_started
        self.view.send()
        self.wait(lambda: not self.view.busy)

        self.assertEqual(sum(call[0] == "execute" for call in self.client.calls), 1)
        self.assertEqual([receipt.state for receipt in self.view.receipts], ["unknown"])
        self.assertTrue(self.view._receipt_unacknowledged)
        self.assertIn("may have been created", self.view.status_var.get())

    def test_stale_exact_section_stops_before_execution(self):
        other = Destination((
            Location("notebook", "book-id", "Private notebook"),
            Location("section", "different-section", "Different section"),
        ))
        self.client.inventory_hook = lambda _notebook, _cancel: (other,)
        self.view.send()
        self.wait(lambda: not self.view.busy)

        self.assertFalse(any(call[0] == "execute" for call in self.client.calls))
        self.assertEqual([receipt.state for receipt in self.view.receipts], ["none"])
        self.assertIn("exact destination is unavailable", self.view.status_var.get())

    def test_partial_receipt_keeps_known_page_id_until_acknowledged(self):
        self.client.execute_hook = lambda *_args: SendOutcome("page_created", "known-page-id")
        self.view.send()
        self.wait(lambda: not self.view.busy)

        self.assertEqual(self.view.receipts,
                         [SendOutcome("page_created", "known-page-id")])
        self.assertTrue(self.view._receipt_unacknowledged)
        self.assertTrue(self.view.ack_button.instate(("!disabled",)))
        self.view.acknowledge()
        self.assertFalse(self.view._receipt_unacknowledged)
        self.assertEqual(self.view.receipts[0].page_id, "known-page-id")

    def test_edited_title_is_locally_visible_and_equal_content_can_be_sent_intentionally(self):
        self.view.title_var.set("Edited title")
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.view.final_title_var.get(), "Title to send: Edited title")
        self.view.send()
        self.wait(lambda: not self.view.busy)
        self.gesture += 1
        self.view.send()
        self.wait(lambda: not self.view.busy)
        self.assertEqual(sum(call[0] == "execute" for call in self.client.calls), 2)
        self.assertEqual([r.state for r in self.view.receipts], ["content_verified"] * 2)

    def test_cleanup_uncertainty_blocks_quit_and_keeps_unknown_result(self):
        def cleanup_failed(*_args):
            raise OwnedProcessError("transport.cleanup", dispatched=True)

        self.client.execute_hook = cleanup_failed
        self.view.send()
        self.wait(lambda: not self.view.busy)
        self.assertTrue(self.view._blocked)
        self.assertEqual(self.view.receipts,
                         [SendOutcome("unknown", cleanup_blocked=True)])
        self.assertIn("cleanup is unconfirmed", self.view.status_var.get())

        app = LauncherApp.__new__(LauncherApp)
        app.onenote_send_window = self.view
        app.root = self.root
        app.status_var = tk.StringVar()
        app.quit_app()
        self.assertTrue(self.root.winfo_exists())
        self.assertIn("Pending cleanup", app.status_var.get())

    def test_readiness_pause_does_not_refresh_confirmation_timestamp(self):
        fixed = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
        self.now = fixed
        self.view.clock = lambda: self.now

        def pause_readiness(session_reader, _cancel):
            self.now = fixed + timedelta(seconds=301)
            return session_reader()

        self.client.prepare_hook = pause_readiness
        self.view.send()
        self.wait(lambda: not self.view.busy)

        self.assertFalse(any(c[0] == "execute" for c in self.client.calls))
        self.assertEqual(self.view.receipts, [SendOutcome("none")])
        self.assertIn("Confirmation expired", self.view.status_var.get())

    def test_quit_cancels_before_execution_and_waits_for_receipt(self):
        preparing = threading.Event()

        def wait_for_cancel(_session_reader, cancel):
            preparing.set()
            cancel.wait(2)
            raise SendError("Cancelled before Send. No execution request was issued.")

        self.client.prepare_hook = wait_for_cancel
        self.view.send()
        self.wait(preparing.is_set)

        app = LauncherApp.__new__(LauncherApp)
        app.onenote_send_window = self.view
        app.root = self.root
        app.status_var = tk.StringVar()
        app.quit_app()
        self.assertTrue(self.root.winfo_exists())
        self.assertIn("OneNote Send result", app.status_var.get())
        self.wait(lambda: not self.view.busy)
        self.assertEqual([receipt.state for receipt in self.view.receipts], ["none"])
        self.assertFalse(any(call[0] == "execute" for call in self.client.calls))

    def test_destination_is_separate_and_discovery_is_not_persisted_until_override(self):
        second_settings = self.base / "second_onenote_settings.json"
        second_destination = self.base / "second_onenote_send_settings.json"
        save_onenote_settings(second_settings, OneNoteSettings(notebook=self.notebook))
        save_destination(second_destination, destination())
        sibling = self.application_root.parent / "python-onenote" / "python-onenote.bat"
        sibling.parent.mkdir()
        sibling.write_text("discovered fixture", encoding="utf-8")
        selected_paths = []
        second = self.make_window(
            settings_path=second_settings,
            destination_path=second_destination,
            client_factory=lambda path: selected_paths.append(Path(path)) or FakeClient(),
        )
        try:
            self.assertEqual(selected_paths, [sibling])
            self.assertIsNone(load_onenote_settings(second_settings).launcher_path)
            self.assertEqual(load_destination(second_destination), destination())

            replacement = self.base / "manual" / "python-onenote.bat"
            replacement.parent.mkdir()
            replacement.write_text("manual fixture", encoding="utf-8")
            with patch("context_palette.onenote_send_window.filedialog.askopenfilename",
                       return_value=str(replacement)):
                second.choose_engine()
            settings = load_onenote_settings(second_settings)
            self.assertEqual(settings, OneNoteSettings(replacement, self.notebook))
            self.assertEqual(load_destination(second_destination), destination())
            self.assertEqual(selected_paths[-1], replacement)
        finally:
            second.window.destroy()

    def test_explicit_missing_launcher_never_uses_available_sibling(self):
        sibling = self.application_root.parent / "python-onenote" / "python-onenote.bat"
        sibling.parent.mkdir()
        sibling.write_text("synthetic sibling", encoding="utf-8")
        self.assertTrue(self.view._refresh_engine())
        self.assertEqual(self.view._engine_key, (self.launcher, self.launcher))
        self.launcher.unlink()
        self.assertFalse(self.view._refresh_engine())
        self.assertIsNone(self.view._client)
        self.assertEqual(load_destination(self.destination_path), destination())
        self.assertEqual(load_onenote_settings(self.settings_path).notebook, self.notebook)
        self.assertNotIn(sibling, self.factory_paths)

    def test_local_display_shows_complete_normalized_unicode_text_and_title(self):
        self.source.update(text="Café\r\n\t日本語\r\n\r\n" + "x" * 40_000, revision=2)
        self.view.capture_source()
        self.view.title_var.set("  Reviewed title  ")
        expected = self.source["text"].replace("\r\n", "\n")
        self.assertEqual(self.view.body_text.get("1.0", "end-1c"), expected)
        self.assertEqual(self.view.final_title_var.get(), "Title to send: Reviewed title")
        self.assertEqual(self.client.calls, [])
        self.view.send()  # Redisplay normalized title, requiring a fresh click.
        self.assertEqual(self.view.title_var.get(), "Reviewed title")
        self.assertEqual(self.client.calls, [])
        self.view.send()
        self.wait(lambda: not self.view.busy)
        self.assertEqual(self.client.calls[0][2:], ("Reviewed title", expected))

    def test_controls_fit_at_scaled_tk_and_escape_closes_from_keyboard(self):
        self.view.window.withdraw()
        with self.scaled_root(2.0) as root:
            scaled = self.make_window(parent=root)
            scaled.window.geometry("820x700")
            self.settle_window(scaled.window)
            top = scaled.window.winfo_rooty()
            bottom = top + scaled.window.winfo_height()
            for widget in (scaled.title_entry, scaled.body_text, scaled.send_button,
                           scaled.status_label, scaled.close_button, scaled.engine_button):
                self.assertTrue(widget.winfo_ismapped())
                self.assertGreater(widget.winfo_height(), 15)
                self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), bottom)
            self.assertTrue(scaled.window.bind("<Escape>"))
            scaled.window.focus_force()
            root.update()
            scaled.window.event_generate("<Escape>")
            root.update()
            self.assertEqual(scaled.window.state(), "withdrawn")

    def test_destination_choice_requires_selection_and_keeps_long_breadcrumb_readable(self):
        long_choice = Destination((
            Location("notebook", "long-book", "Research notebook"),
            Location("section_group", "long-group", "Quarterly planning and decisions"),
            Location("section", "long-section", "Reviewed launch notes"),
        ))
        choices = (destination(), long_choice)
        picker = DestinationChoice(self.view.window, "Choose exact section", choices)
        try:
            self.root.update()
            self.assertEqual(picker.rows.curselection(), ())
            picker.choose()
            self.assertTrue(picker.window.winfo_exists())
            self.assertEqual(picker.rows.get(1), long_choice.label)
            self.assertGreater(picker.rows.winfo_width(), 300)
            picker.rows.selection_set(1)
            picker.rows.focus_force()
            self.root.update()
            picker.rows.event_generate("<Return>")
            self.root.update()
            self.assertEqual(picker.result, long_choice)
            self.assertFalse(picker.window.winfo_exists())
        finally:
            if picker.window.winfo_exists():
                picker.window.destroy()

    def test_one_primary_button_and_conditional_controls(self):
        self.root.update()
        self.assertFalse(hasattr(self.view, "review_button"))
        self.assertEqual(self.view.send_button.cget("text"), "Send to OneNote")
        self.assertFalse(self.view.cancel_button.winfo_ismapped())
        self.assertFalse(self.view.details_button.winfo_ismapped())
        self.assertFalse(self.view.ack_button.winfo_ismapped())
        self.assertFalse(self.view.refresh_button.winfo_ismapped())
        self.assertTrue(self.view.send_button.instate(("!disabled",)))
        self.view.source_changed()
        self.root.update()
        self.assertEqual(self.view.status_tone, "warning")
        self.assertTrue(self.view.refresh_button.winfo_ismapped())
        self.assertTrue(self.view.send_button.instate(("disabled",)))

    def test_heading_font_has_visible_hierarchy_despite_global_font_defaults(self):
        from tkinter import font
        title_font = font.Font(root=self.root, font=self.view.title_label.cget("font"))
        body_font = font.Font(root=self.root, font=self.view.body_text.cget("font"))
        self.assertGreater(title_font.actual("size"), body_font.actual("size"))

    def test_success_clears_on_edit_but_receipt_remains_in_details(self):
        self.view.send_button.invoke()
        self.wait(lambda: not self.view.busy)
        self.assertEqual(self.view.status_tone, "success")
        self.assertIn("Page created and verified", self.view.status_var.get())
        self.assertTrue(self.view.details_button.winfo_ismapped())
        self.assertFalse(self.view.ack_button.winfo_ismapped())
        self.view.title_var.set("Next title")
        self.assertEqual(self.view.status_tone, "neutral")
        self.assertNotIn("created and verified", self.view.status_var.get())
        self.assertEqual(self.view.receipts, [SendOutcome("content_verified", "created-page")])

    def test_unknown_warning_survives_edit_refresh_and_reopen_until_acknowledged(self):
        self.client.execute_hook = lambda *_: SendOutcome("unknown")
        self.view.send()
        self.wait(lambda: not self.view.busy)
        self.view.title_var.set("Edited after unknown")
        self.source.update(text="Different source", revision=2)
        self.view.source_changed()
        self.assertIn("may have been created", self.view.status_var.get())
        self.assertEqual(self.view.status_tone, "warning")
        self.view.capture_source()
        self.view.window.withdraw()
        self.view.show()
        self.root.update()
        self.assertIn("may have been created", self.view.status_var.get())
        self.assertTrue(self.view.ack_button.winfo_ismapped())
        self.assertTrue(self.view.send_button.instate(("disabled",)))
        self.view.ack_button.invoke()
        self.root.update()
        self.assertFalse(self.view.ack_button.winfo_ismapped())
        self.assertEqual(self.view.receipts, [SendOutcome("unknown")])
        self.assertNotEqual(self.view.status_tone, "success")
        self.assertEqual(sum(c[0] == "execute" for c in self.client.calls), 1)

    def test_all_five_outcomes_have_correct_banner_and_acknowledgement(self):
        for state, tone, attention in (
            ("none", "error", False), ("unknown", "warning", True),
            ("page_created", "warning", True), ("content_applied_unverified", "warning", True),
            ("content_verified", "success", False),
        ):
            with self.subTest(state=state):
                self.client.execute_hook = lambda *_, state=state: SendOutcome(state, "page" if state not in {"none", "unknown"} else None)
                self.gesture += 1
                self.view.send()
                self.wait(lambda: not self.view.busy)
                self.assertEqual(self.view.status_tone, tone)
                self.assertEqual(self.view._receipt_unacknowledged, attention)
                self.assertEqual(self.view.status_stripe.cget("background"), COLORS[tone])
                self.assertEqual(bool(self.view.ack_button.winfo_ismapped()), attention)
                if attention:
                    self.view.acknowledge()
        self.assertEqual(len(self.view.receipts), 5)

    def test_local_validation_disables_send_without_external_calls(self):
        for invalid_title in ("", "x" * 256, "日本語" * 100, "Line\nBreak"):
            with self.subTest(title_length=len(invalid_title)):
                self.view.title_var.set(invalid_title)
                self.assertTrue(self.view.send_button.instate(("disabled",)))
                self.view.send()
                self.assertEqual(self.client.calls, [])
        self.source.update(text="x" * 50_001, revision=2)
        self.view.capture_source()
        self.assertTrue(self.view.send_button.instate(("disabled",)))
        self.assertIn("Nothing was shortened", self.view.status_var.get())
        self.assertEqual(len(self.view.body_text.get("1.0", "end-1c")), 50_001)
        self.assertEqual(self.client.calls, [])

    def test_altered_valid_canonical_plan_stops_before_readiness(self):
        self.client.plan_hook = lambda chosen, title, body, _: ReviewedPlan(
            chosen, json.dumps(canonical_plan(chosen.section_id, title, body + " altered")))
        self.view.send()
        self.wait(lambda: not self.view.busy)
        self.assertEqual([c[0] for c in self.client.calls], ["plan"])
        self.assertEqual(self.view.receipts, [SendOutcome("none")])
        self.assertIn("different plan", self.view.status_var.get())

    def test_expiry_during_planning_never_executes_or_renews_time(self):
        def slow_plan(chosen, title, body, _cancel):
            self.now += timedelta(seconds=301)
            return ReviewedPlan(chosen, json.dumps(canonical_plan(chosen.section_id, title, body)))
        self.client.plan_hook = slow_plan
        self.view.send()
        self.wait(lambda: not self.view.busy)
        self.assertEqual([c[0] for c in self.client.calls], ["plan"])
        self.assertIn("Confirmation expired", self.view.status_var.get())

    def test_changes_or_cancellation_during_each_preflight_stage_never_execute(self):
        for stage in ("plan", "prepare", "inventory"):
            for change in ("source", "title", "destination", "engine", "session", "cancel"):
                with self.subTest(stage=stage, change=change):
                    self.gesture += 1
                    self.client.calls.clear()
                    self.client.plan_hook = self.client.prepare_hook = self.client.inventory_hook = None
                    self.session = ((101, 202),)
                    self.source.update(text="Fresh source", revision=self.source["revision"] + 1)
                    self.view.capture_source()
                    self.view._destination = destination()
                    save_onenote_settings(self.settings_path, OneNoteSettings(self.launcher, self.notebook))
                    self.view._refresh_engine()
                    started, release = threading.Event(), threading.Event()
                    def pause(*args):
                        started.set()
                        release.wait(2)
                        if stage == "plan":
                            chosen, title, body, _cancel = args
                            return ReviewedPlan(chosen, json.dumps(canonical_plan(chosen.section_id, title, body)))
                        if stage == "prepare":
                            return ((101, 202),)
                        return (destination(),)
                    setattr(self.client, stage + "_hook", pause)
                    self.view.send()
                    self.wait(started.is_set)
                    if change == "source":
                        self.source["revision"] += 1  # Deliberately omit notification; Tk gate must catch it.
                    elif change == "title":
                        self.view.title_var.set("Changed during preflight")
                    elif change == "destination":
                        self.view._destination = Destination((Location("notebook", "other", "Other"), Location("section", "new", "Section")))
                    elif change == "engine":
                        self.settings_path.write_text("{}", encoding="utf-8")
                    elif change == "session":
                        self.session = ((999, 888),)
                    else:
                        self.view.cancel()
                    release.set()
                    self.wait(lambda: not self.view.busy)
                    self.assertFalse(any(c[0] == "execute" for c in self.client.calls))
                    self.assertEqual(self.view.receipts[-1].state, "none")
                    self.assertFalse(self.view._receipt_unacknowledged)

    def test_preflight_callback_exception_releases_gate_and_consumes_no_effect_result(self):
        original_reader = self.view.source_reader
        calls = 0
        def broken_reader():
            nonlocal calls
            calls += 1
            if calls > 1:
                raise RuntimeError("synthetic callback failure")
            return original_reader()
        self.view.source_reader = broken_reader
        self.view.send()
        self.wait(lambda: not self.view.busy)
        self.assertFalse(any(c[0] == "execute" for c in self.client.calls))
        self.assertEqual(self.view.receipts, [SendOutcome("none")])

    def test_metadata_cleanup_failure_blocks_without_fabricating_a_send_receipt(self):
        from context_palette.onenote_integration import OneNoteError
        def cleanup_failure(*_):
            raise OneNoteError("transport.cleanup", "synthetic")
        self.client.prepare_hook = cleanup_failure
        self.view.choose_destination()
        self.wait(lambda: not self.view.busy)
        self.assertTrue(self.view._blocked)
        self.assertEqual(self.view.receipts, [])
        self.assertFalse(self.view.details_button.winfo_ismapped())
        self.assertIn("cleanup is unconfirmed", self.view.status_var.get())
        self.assertFalse(self.view.close())

    def test_metadata_cleanup_after_success_does_not_repeat_stale_success(self):
        from context_palette.onenote_integration import OneNoteError
        self.view.send()
        self.wait(lambda: not self.view.busy)
        def cleanup_failure(*_):
            raise OneNoteError("transport.cleanup", "synthetic")
        self.client.prepare_hook = cleanup_failure
        self.view.choose_destination()
        self.wait(lambda: not self.view.busy)
        self.assertTrue(self.view._blocked)
        self.assertEqual(self.view.receipts, [SendOutcome("content_verified", "created-page")])
        self.assertEqual(self.view.status_tone, "error")
        self.assertNotIn("created and verified", self.view.status_var.get())

    def test_metadata_cleanup_does_not_hide_an_earlier_unknown_write(self):
        from context_palette.onenote_integration import OneNoteError
        self.client.execute_hook = lambda *_: SendOutcome("unknown")
        self.view.send()
        self.wait(lambda: not self.view.busy)
        def cleanup_failure(*_):
            raise OneNoteError("transport.cleanup", "synthetic")
        self.client.prepare_hook = cleanup_failure
        self.view.choose_destination()
        self.wait(lambda: not self.view.busy)
        self.assertIn("Earlier Send still needs attention", self.view.status_var.get())
        self.assertIn("may have been created", self.view.status_var.get())
        self.view.acknowledge()
        self.assertTrue(self.view._receipt_unacknowledged)
        self.assertFalse(self.view.close())

    def test_ctrl_enter_repeat_across_completion_requires_key_release(self):
        self.view.title_entry.focus_force()
        self.root.update()
        self.view.title_entry.event_generate("<Control-Return>")
        self.wait(lambda: not self.view.busy)
        self.gesture += 1  # A long held key cannot bypass the release latch.
        self.view.title_entry.event_generate("<Control-Return>")
        self.root.update()
        self.assertEqual(sum(c[0] == "execute" for c in self.client.calls), 1)
        self.view.title_entry.event_generate("<KeyRelease-Return>")
        self.view.title_entry.event_generate("<Control-Return>")
        self.wait(lambda: not self.view.busy)
        self.assertEqual(sum(c[0] == "execute" for c in self.client.calls), 2)

    def test_fast_completed_double_click_cannot_create_second_page(self):
        self.view.send_button.invoke()
        self.wait(lambda: not self.view.busy)
        self.gesture += 0.2
        self.view.send_button.invoke()
        self.root.update()
        self.assertEqual(sum(c[0] == "execute" for c in self.client.calls), 1)

    def test_worker_never_reads_tk_source(self):
        main_thread = threading.get_ident()
        original = self.view.source_reader
        def guarded_reader():
            self.assertEqual(threading.get_ident(), main_thread)
            return original()
        self.view.source_reader = guarded_reader
        self.view.send()
        self.wait(lambda: not self.view.busy)
        self.assertEqual(self.view.receipts[0].state, "content_verified")

    def test_suggested_title_shortens_at_a_word_boundary_and_keeps_complete_body(self):
        first = "A human readable title " + "reusable words " * 10
        suggestion = suggested_title(first)
        self.assertTrue(suggestion.endswith("…"))
        excerpt = suggestion.split(" — ", 1)[1][:-1]
        self.assertTrue(first.startswith(excerpt + " "))
        self.source.update(text=first + "\nRest of text", revision=2)
        self.view.capture_source()
        self.assertIn("Suggested title", self.view.title_hint_var.get())
        self.assertEqual(self.view.body_text.get("1.0", "end-1c"), self.source["text"])

    def test_final_preflight_validation_expires_without_execute(self):
        original = self.view._approve_preflight
        def expiry_at_gate(snapshot):
            self.now += timedelta(seconds=301)
            original(snapshot)
        self.view._approve_preflight = expiry_at_gate
        self.view.send()
        self.wait(lambda: not self.view.busy)
        self.assertFalse(any(c[0] == "execute" for c in self.client.calls))
        self.assertIn("Confirmation expired", self.view.status_var.get())

    def test_engine_and_session_changes_after_tk_gate_stop_before_execute(self):
        original = self.view._approve_preflight
        for change in ("engine", "session"):
            with self.subTest(change=change):
                self.gesture += 1
                self.client.calls.clear()
                self.session = ((101, 202),)
                save_onenote_settings(self.settings_path, OneNoteSettings(self.launcher, self.notebook))
                self.view._refresh_engine()
                def change_at_gate(snapshot):
                    class ChangeOnRelease:
                        def set(inner):
                            if change == "engine":
                                self.settings_path.write_text("{}", encoding="utf-8")
                            else:
                                self.session = ((555, 444),)
                            snapshot[0].set()
                    original((ChangeOnRelease(), *snapshot[1:]))
                self.view._approve_preflight = change_at_gate
                self.view.send()
                self.wait(lambda: not self.view.busy)
                self.assertFalse(any(c[0] == "execute" for c in self.client.calls))

    def test_text_tab_moves_focus_and_shared_styles_are_unchanged(self):
        from tkinter import ttk
        self.view.window.withdraw()
        before = ttk.Style(self.root).map("Accent.TButton")
        second = self.make_window()
        try:
            self.assertEqual(ttk.Style(self.root).map("Accent.TButton"), before)
            self.settle_window(second.window)
            second.body_text.focus_force()
            self.wait(lambda: self.root.focus_get() == second.body_text)
            self.assertEqual(self.root.focus_get(), second.body_text)
            second.body_text.event_generate("<Tab>")
            self.root.update()
            self.assertNotEqual(self.root.focus_get(), second.body_text)
            self.assertTrue(second.window.bind("<Control-Return>"))
        finally:
            second.window.destroy()

    def test_real_tk_layout_matrix_at_windows_scaling_and_long_content(self):
        self.view.window.withdraw()
        heading_heights = {}
        for percent in (100, 125, 150, 200):
            for long in (False, True):
                with self.subTest(percent=percent, long=long):
                    with self.scaled_root((96 / 72) * percent / 100) as root:
                        body = "Complete synthetic page text.\nCafé 日本語\n\nTab\tkept\n" * 100 if long else self.source["text"]
                        scaled = self.make_window(parent=root, source_reader=lambda: (body, 1))
                        try:
                            if long:
                                scaled._destination = Destination((Location("notebook", "book-id", "Synthetic research notebook with a longer display name"),
                                    Location("section_group", "group-id", "Planning and decisions for this project"),
                                    Location("section", "section-id", "Notes and reference material")))
                                scaled._show_destination()
                                scaled.title_var.set("A useful complete title with words that can be read without horizontal scrolling. " * 3)
                                scaled._source_current = False
                                scaled.receipts.append(SendOutcome("unknown"))
                                scaled._receipt_unacknowledged = True
                                scaled._sync()
                            width = 640 if not long else 820
                            height = 560 if percent <= 125 and not long else 760 if percent < 200 else 1000
                            scaled.window.geometry(f"{width}x{height}")
                            self.settle_window(scaled.window)
                            heading_heights[percent] = scaled.title_label.winfo_reqheight()
                            self.assertEqual(scaled.body_text.get("1.0", "end-1c"), body)
                            if long:
                                scaled.body_text.yview_moveto(1)
                                self.assertGreater(scaled.body_text.yview()[0], 0)
                            left, top = scaled.window.winfo_rootx(), scaled.window.winfo_rooty()
                            right, bottom = left + scaled.window.winfo_width(), top + scaled.window.winfo_height()
                            for widget in (scaled.destination_label, scaled.destination_button, scaled.title_entry,
                                           scaled.title_preview, scaled.title_hint, scaled.body_text, scaled.status_label,
                                           scaled.close_button, scaled.send_button, scaled.engine_button,
                                           *((scaled.ack_button, scaled.refresh_button) if long else ())):
                                self.assertTrue(widget.winfo_ismapped(), str(widget))
                                self.assertGreater(widget.winfo_height(), 12, str(widget))
                                self.assertGreaterEqual(widget.winfo_rootx(), left)
                                self.assertGreaterEqual(widget.winfo_rooty(), top)
                                self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), right, str(widget))
                                self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), bottom, str(widget))
                        finally:
                            scaled.window.destroy()
        self.assertEqual(len(heading_heights), 4)
        for lower, higher in ((100, 125), (125, 150), (150, 200)):
            self.assertLess(heading_heights[lower], heading_heights[higher])


if __name__ == "__main__":
    unittest.main()
