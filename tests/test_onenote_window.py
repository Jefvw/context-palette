"""Real Tk with synthetic OneNote responses; never reads the external app."""
from pathlib import Path
import json
import os
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from context_palette.onenote_integration import (
    Description, Readiness, SearchPage, SearchResult, PagePreview, OneNoteError,
    OneNoteSettings, NotebookRef, NotebookList, load_onenote_settings,
    save_onenote_settings,
)
from context_palette.onenote_window import OneNoteWindow, NotebookChoiceDialog
from context_palette.workspace_panel import WorkspacePanel
from context_palette.data_catalog import AppDataPaths
from context_palette.launcher import LauncherApp
from unittest.mock import Mock


class FakeClient:
    def __init__(self):
        self.calls = []
        self.search_hook = None
        self.preview_hook = None
        self.probe_hook = None
        self.scopes = []
        self.books = (NotebookRef("notebook-one", "First notebook"), NotebookRef("notebook-two", "Second notebook"))
        self.pages = (SearchPage("CaSe-秘密", "Untitled page", ("Notebook", "Section")),
                      SearchPage("second", "Décision 🎸", ("Section only",)))

    def describe(self, *, cancel_event):
        self.calls.append(("describe",))
        return Description(True)

    def probe(self, *, cancel_event):
        self.calls.append(("probe",))
        if self.probe_hook:
            self.probe_hook(cancel_event)
        return Readiness(("inventory_desktop_hierarchy", "search_desktop_pages", "preview_desktop_page"))

    def notebooks(self, *, cancel_event):
        self.calls.append(("notebooks",))
        return NotebookList(self.books, len(self.books), False)

    def search(self, query, *, notebook_id=None, cancel_event):
        self.calls.append(("search", query))
        self.scopes.append(notebook_id)
        if self.search_hook:
            return self.search_hook(cancel_event)
        return SearchResult(self.pages, len(self.pages), False)

    def preview(self, page_id, *, cancel_event):
        self.calls.append(("preview", page_id))
        if self.preview_hook:
            return self.preview_hook(cancel_event)
        return PagePreview(page_id, "Reviewed 😀 text", 15, 15, False)


class OneNoteWindowTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.tmp = tempfile.TemporaryDirectory()
        self.client = FakeClient()
        self.applied = []
        self.closed = []
        self.session = ((11, 234),)
        self.application_root = Path(self.tmp.name) / "installed é" / "Context Palette"
        self.application_root.mkdir(parents=True)
        self.view = OneNoteWindow(
            self.root, settings_path=Path(self.tmp.name) / "settings.json",
            initial_query="selected query", client_factory=lambda _path: self.client,
            session_reader=lambda: self.session,
            apply_text=lambda text, current: self.applied.append(text) or current(),
            on_close=lambda: self.closed.append(True),
            application_root=self.application_root,
        )
        self.view._client = self.client
        self.launcher = Path(self.tmp.name) / "python-onenote.bat"
        self.launcher.write_text("synthetic launcher, never executed")
        self.view._settings = OneNoteSettings(self.launcher)

    def tearDown(self):
        if self.view._job is not None:
            self.view.cancel()
            self.wait(lambda: self.view._job is None)
        self.root.destroy()
        self.tmp.cleanup()

    def wait(self, predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not predicate():
            self.root.update()
            time.sleep(.005)
        self.root.update()
        self.assertTrue(predicate())

    def connect(self):
        # Existing-ready session fixture for tests focused on reads and UI state.
        self.view._described = True
        self.view._ready = frozenset(("inventory_desktop_hierarchy", "search_desktop_pages", "preview_desktop_page"))
        self.view._session = self.session
        self.view._sync()

    def search_select(self):
        self.connect()
        self.view.search()
        self.wait(lambda: not self.view.busy)
        self.view.results.selection_set("0")
        self.root.update()

    def test_explicit_full_journey_no_automatic_search_or_preview(self):
        self.assertEqual(self.client.calls, [])
        self.assertFalse(self.view._ready)
        self.view.query_var.set("new exact query ")
        self.root.update()
        self.assertEqual(self.client.calls, [])
        self.view.search()
        self.wait(lambda: not self.view.busy)
        self.assertEqual(self.client.calls[:2], [("describe",), ("probe",)])
        self.assertEqual(self.view.status_var.get(), "Choose a note, then Preview text.")
        self.assertEqual(self.view.preview_var.get(), "")
        self.view.results.selection_set("0")
        self.root.update()
        self.assertEqual(self.view.status_var.get(), "Choose Preview text to read the selected note.")
        self.assertTrue(self.view.basic_text_warning.winfo_ismapped())
        self.assertEqual(self.client.calls[-1], ("search", "new exact query "))
        self.assertIsNone(self.view._preview)
        self.assertEqual(self.view.results.item("0", "values"), ("Notebook / Section",))
        self.view.preview()
        self.wait(lambda: not self.view.busy)
        self.assertEqual(self.client.calls[-1], ("preview", "CaSe-秘密"))
        self.assertEqual(self.applied, [])
        self.assertIn("Complete basic text", self.view.preview_var.get())
        self.assertIn("Replace or Append", self.view.status_var.get())
        self.assertTrue(self.view.basic_text_warning.winfo_ismapped())
        self.view.use_text()
        self.assertEqual(self.applied, ["Reviewed 😀 text"])
        self.assertIn("placed in Input / Output", self.view.status_var.get())
        self.view.query_var.set("next query")
        self.root.update()
        self.assertEqual(self.view.preview_var.get(), "")
        self.assertFalse(self.view.basic_text_warning.winfo_ismapped())
        self.assertIn("Search", self.view.status_var.get())

    def test_compact_initial_guidance_keeps_repair_visible_and_find_inline(self):
        self.root.update()
        self.assertEqual(self.view.find_label.master, self.view.query_entry.master)
        label_center = self.view.find_label.winfo_rooty() + self.view.find_label.winfo_height() / 2
        entry_center = self.view.query_entry.winfo_rooty() + self.view.query_entry.winfo_height() / 2
        self.assertLessEqual(abs(label_center - entry_center), 2)
        self.assertIn("No sibling engine found", self.view.status_var.get())
        self.assertFalse(self.view.cancel_button.winfo_ismapped())
        self.assertFalse(self.view.basic_text_warning.winfo_ismapped())
        self.assertEqual(self.view.results_var.get(), "Notes")
        self.assertEqual(self.view.preview_var.get(), "")
        self.assertEqual(self.client.calls, [])
        with patch("context_palette.onenote_window.filedialog.askopenfilename", return_value=str(self.launcher)):
            self.view.choose_engine()
        self.root.update()
        self.assertFalse(self.view.search_button.instate(("disabled",)))
        self.assertIn("Choose Search", self.view.status_var.get())
        self.assertEqual(self.client.calls, [])

    def test_preview_is_inert_and_truncation_blocks_use(self):
        self.search_select()
        self.client.preview_hook = lambda _: PagePreview("CaSe-秘密", "<script>example</script>", 24, 60000, True)
        self.view.preview()
        self.wait(lambda: not self.view.busy)
        self.assertIn("<script>", self.view.preview_text.get("1.0", "end-1c"))
        self.assertTrue(self.view.use_button.instate(("disabled",)))
        self.view.use_text()
        self.assertEqual(self.applied, [])
        self.assertIn("50,000", self.view.status_var.get())
        self.assertIn("24 of 60,000", self.view.preview_var.get())
        self.assertTrue(self.view.basic_text_warning.winfo_ismapped())

    def test_query_change_invalidates_delayed_search_and_readiness(self):
        self.connect()
        release = threading.Event()
        self.client.search_hook = lambda _: (release.wait(2), SearchResult(self.client.pages, 2, False))[1]
        self.view.search()
        self.view.query_var.set("different")
        self.assertTrue(self.view.busy)
        self.view.search()
        release.set()
        self.wait(lambda: not self.view.busy)
        self.assertEqual(self.view.results.get_children(), ())
        self.assertFalse(self.view._ready)
        self.assertEqual(sum(c[0] == "search" for c in self.client.calls), 1)

    def test_selection_change_discards_old_preview(self):
        self.search_select()
        release = threading.Event()
        self.client.preview_hook = lambda _: (release.wait(2), PagePreview("CaSe-秘密", "old", 3, 3, False))[1]
        self.view.preview()
        self.view.results.selection_set("1")
        self.root.update()
        release.set()
        self.wait(lambda: not self.view.busy)
        self.assertIsNone(self.view._preview)
        self.view.use_text()
        self.assertEqual(self.applied, [])

    def test_close_waits_for_cleanup_clears_state_and_ignores_late_success(self):
        self.connect()
        release = threading.Event()
        self.client.search_hook = lambda _: (release.wait(2), SearchResult(self.client.pages, 2, False))[1]
        self.view.search()
        self.assertFalse(self.view.close())
        self.assertEqual(self.view.query_var.get(), "")
        self.assertEqual(self.closed, [])
        release.set()
        self.wait(lambda: bool(self.closed))
        self.assertFalse(self.view._ready)
        self.assertEqual(self.applied, [])

    def test_session_change_rechecks_before_searching(self):
        self.connect()
        self.session = ((12, 567),)
        self.view.search()
        self.wait(lambda: not self.view.busy)
        self.assertEqual(self.client.calls, [("probe",), ("search", "selected query")])
        self.assertEqual(self.view._session, self.session)

    def test_session_change_during_reconnect_stops_before_search(self):
        self.client.probe_hook = lambda _: setattr(self, "session", ((12, 567),))
        self.view.search()
        self.wait(lambda: not self.view.busy)
        self.assertFalse(self.view._ready)
        self.assertFalse(any(c[0] == "search" for c in self.client.calls))

    def test_session_change_during_read_discards_result(self):
        self.connect()
        def change(_):
            self.session = ()
            return SearchResult(self.client.pages, 2, False)
        self.client.search_hook = change
        self.view.search()
        self.wait(lambda: not self.view.busy)
        self.assertFalse(self.view._ready)
        self.assertFalse(self.view._pages)

    def test_busy_preview_preserves_selected_result_but_not_old_text(self):
        self.search_select()
        def busy(_):
            raise OneNoteError("backend.desktop_busy")
        self.client.preview_hook = busy
        self.view.preview()
        self.wait(lambda: not self.view.busy)
        self.assertTrue(self.view._ready)
        self.assertEqual(self.view._selected_id, "CaSe-秘密")
        self.assertIsNone(self.view._preview)

    def test_unknown_exception_does_not_expose_payload(self):
        self.connect()
        def fail(_):
            raise RuntimeError("PRIVATE QUERY AND BODY")
        self.client.search_hook = fail
        self.view.search()
        self.wait(lambda: not self.view.busy)
        self.assertNotIn("PRIVATE", self.view.status_var.get())
        self.assertFalse(self.view._ready)

    def test_cleanup_uncertainty_blocks_retry_even_after_close(self):
        self.connect()
        def fail(_):
            raise OneNoteError("transport.cleanup")
        self.client.search_hook = fail
        self.view.search()
        self.wait(lambda: self.view._job is None)
        self.assertTrue(self.view.busy)
        self.assertFalse(self.view.close())
        self.view.search()
        self.assertEqual(sum(c[0] == "search" for c in self.client.calls), 1)

    def test_worker_start_failure_does_not_block_close(self):
        with patch("context_palette.onenote_window.threading.Thread.start", side_effect=RuntimeError("secret")):
            self.view.search()
        self.assertFalse(self.view.busy)
        self.assertTrue(self.view.close())
        self.assertNotIn("secret", self.view.status_var.get())

    def test_limited_results_are_labelled_no_automatic_pagination(self):
        self.connect()
        self.client.search_hook = lambda _: SearchResult(self.client.pages, 100, True)
        self.view.search()
        self.wait(lambda: not self.view.busy)
        self.assertIn("2 of 100", self.view.results_var.get())
        self.assertIn("narrow the query", self.view.status_var.get())
        self.assertEqual(sum(c[0] == "search" for c in self.client.calls), 1)

    def test_repeated_search_reuses_checks_but_never_searches_while_typing(self):
        self.view.search()
        self.wait(lambda: not self.view.busy)
        self.view.query_var.set("second query")
        self.root.update()
        self.assertEqual(len(self.client.calls), 3)
        self.view.search()
        self.wait(lambda: not self.view.busy)
        self.assertEqual(self.client.calls, [("describe",), ("probe",),
            ("search", "selected query"), ("search", "second query")])

    def test_missing_onenote_does_not_probe_or_search(self):
        self.session = ()
        self.view.search()
        self.wait(lambda: not self.view.busy)
        self.assertEqual(self.client.calls, [("describe",)])
        self.assertFalse(self.view._ready)

    def test_cancel_during_connection_never_runs_pending_search(self):
        release = threading.Event()
        self.client.probe_hook = lambda _: release.wait(2)
        self.view.search()
        self.wait(lambda: ("probe",) in self.client.calls)
        self.assertTrue(self.view.cancel_button.winfo_ismapped())
        self.assertFalse(self.view.cancel_button.instate(("disabled",)))
        self.assertIn("Connecting", self.view.status_var.get())
        self.view.cancel()
        self.root.update()
        self.assertTrue(self.view.cancel_button.winfo_ismapped())
        self.assertIn("Cancelling", self.view.status_var.get())
        release.set()
        self.wait(lambda: not self.view.busy)
        self.assertFalse(self.view.cancel_button.winfo_ismapped())
        self.assertIn("Choose Search", self.view.status_var.get())
        self.assertEqual(self.client.calls, [("describe",), ("probe",)])
        self.assertFalse(self.view._ready)

    def test_remembered_notebook_survives_reopen_and_limits_search(self):
        notebook = self.client.books[1]
        with patch("context_palette.onenote_window.NotebookChoiceDialog") as chooser:
            chooser.return_value.show.return_value = (True, notebook)
            self.view.choose_notebook()
            self.wait(lambda: not self.view.busy)
        self.assertEqual(self.client.calls, [("describe",), ("probe",), ("notebooks",)])
        self.assertEqual(load_onenote_settings(self.view.settings_path).notebook, notebook)
        settings_path = self.view.settings_path
        self.view.close()
        self.client.calls.clear()
        self.view = OneNoteWindow(self.root, settings_path=settings_path, initial_query="another query",
            client_factory=lambda _: self.client, session_reader=lambda: self.session,
            apply_text=lambda *_: False, on_close=lambda: None, application_root=self.application_root)
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.view.notebook_var.get(), "Second notebook")
        self.assertFalse(self.view.search_button.instate(("disabled",)))
        self.view.search()
        self.wait(lambda: not self.view.busy)
        self.assertEqual(self.client.scopes, [notebook.object_id])

    def test_unavailable_notebook_does_not_widen_search(self):
        self.view._settings = OneNoteSettings(self.launcher, self.client.books[0])
        def missing(_):
            raise OneNoteError("target.not_found")
        self.client.search_hook = missing
        self.view.search()
        self.wait(lambda: not self.view.busy)
        self.assertEqual(self.client.scopes, ["notebook-one"])
        self.assertEqual(self.view._settings.notebook, self.client.books[0])
        self.assertEqual(self.view._pages, ())

    def test_bridge_failure_keeps_engine_and_notebook_for_explicit_retry(self):
        settings = OneNoteSettings(self.launcher, self.client.books[0])
        save_onenote_settings(self.view.settings_path, settings)
        self.view._settings = settings
        self.view._show_scope()
        self.view.setup_var.set("Engine remembered on this PC. Search connects automatically.")
        self.search_select()
        self.view.preview()
        self.wait(lambda: not self.view.busy)
        self.assertIsNotNone(self.view._preview)
        self.client.calls.clear()
        self.client.scopes.clear()
        def failed(_):
            raise OneNoteError("internal.desktop_bridge")
        self.client.search_hook = failed
        self.view.search()
        self.wait(lambda: not self.view.busy)
        self.assertIs(self.view._client, self.client)
        self.assertEqual(load_onenote_settings(self.view.settings_path), settings)
        self.assertEqual(self.view.notebook_var.get(), settings.notebook.title)
        self.assertEqual(self.client.scopes, [settings.notebook.object_id])
        self.assertEqual(self.client.calls, [("search", "selected query")])
        self.assertEqual(self.view._pages, ())
        self.assertIsNone(self.view._preview)
        self.assertFalse(self.view._ready)
        self.assertIsNone(self.view._session)
        self.assertFalse(self.view._described)
        self.assertTrue(self.view.use_button.instate(("disabled",)))
        self.assertFalse(self.view.search_button.instate(("disabled",)))
        self.assertFalse(self.view.notebook_button.instate(("disabled",)))
        self.assertNotIn("repair", self.view.setup_var.get())
        self.assertIn("Make sure the notebook is open", self.view.status_var.get())
        self.assertEqual(self.applied, [])
        # Recovery is explicitly requested, re-probes, and reuses the same scope.
        self.client.search_hook = None
        self.view.search()
        self.wait(lambda: not self.view.busy)
        self.assertEqual(self.client.calls[1:], [("describe",), ("probe",), ("search", "selected query")])
        self.assertEqual(self.client.scopes, [settings.notebook.object_id] * 2)
        self.assertEqual(self.view._pages, self.client.pages)

    def test_changing_engine_never_widens_remembered_notebook(self):
        alternative = Path(self.tmp.name) / "other" / "python-onenote.bat"
        alternative.parent.mkdir()
        alternative.write_text("another synthetic launcher")
        for launcher in (self.launcher, alternative):
            with self.subTest(launcher=launcher.name):
                self.view._settings = OneNoteSettings(self.launcher, self.client.books[0])
                with patch("context_palette.onenote_window.filedialog.askopenfilename", return_value=str(launcher)):
                    self.view.choose_engine()
                self.assertEqual(self.view._settings.notebook, self.client.books[0])
                self.assertEqual(self.view.notebook_var.get(), "First notebook")
                self.assertEqual(load_onenote_settings(self.view.settings_path).notebook, self.client.books[0])

    def test_cancelled_notebook_choice_preserves_scope(self):
        self.view._settings = OneNoteSettings(self.launcher, self.client.books[0])
        with patch("context_palette.onenote_window.NotebookChoiceDialog") as chooser:
            chooser.return_value.show.return_value = (False, None)
            self.view.choose_notebook()
            self.wait(lambda: not self.view.busy)
        self.assertEqual(self.view._settings.notebook, self.client.books[0])

    def test_closing_during_notebook_choice_cannot_save_or_touch_closed_widgets(self):
        def close_during_choice():
            self.view.close()
            return True, self.client.books[0]
        with patch("context_palette.onenote_window.NotebookChoiceDialog") as chooser:
            chooser.return_value.show.side_effect = close_during_choice
            self.view.choose_notebook()
            self.wait(lambda: self.view._closed)
        self.assertFalse(self.view.settings_path.exists())

    def test_changed_generation_during_notebook_choice_rejects_selection(self):
        def change_during_choice():
            self.view.query_var.set("new query")
            return True, self.client.books[0]
        with patch("context_palette.onenote_window.NotebookChoiceDialog") as chooser:
            chooser.return_value.show.side_effect = change_during_choice
            self.view.choose_notebook()
            self.wait(lambda: not self.view.busy)
        self.assertIsNone(self.view._settings.notebook)
        self.assertFalse(self.view.settings_path.exists())

    def test_missing_saved_engine_preserves_notebook_for_replacement(self):
        self.view._settings = OneNoteSettings(self.launcher, self.client.books[0])
        save_onenote_settings(self.view.settings_path, self.view._settings)
        settings_path = self.view.settings_path
        self.view.close()
        self.launcher.unlink()
        self.view = OneNoteWindow(self.root, settings_path=settings_path, initial_query="query",
            client_factory=lambda _: self.client, session_reader=lambda: self.session,
            apply_text=lambda *_: False, on_close=lambda: None, application_root=self.application_root)
        self.assertEqual(self.view._settings.notebook, self.client.books[0])
        self.assertTrue(self.view.search_button.instate(("disabled",)))
        self.assertEqual(self.client.calls, [])
        self.launcher.write_text("replacement fixture")
        with patch("context_palette.onenote_window.filedialog.askopenfilename", return_value=str(self.launcher)):
            self.view.choose_engine()
        self.assertEqual(self.view._settings.notebook, self.client.books[0])
        self.assertFalse(self.view.search_button.instate(("disabled",)))

    def test_failed_notebook_save_keeps_previous_scope(self):
        self.view._settings = OneNoteSettings(self.launcher, self.client.books[0])
        with patch("context_palette.onenote_window.NotebookChoiceDialog") as chooser, \
             patch("context_palette.onenote_window.save_onenote_settings", side_effect=OSError()):
            chooser.return_value.show.return_value = (True, self.client.books[1])
            self.view.choose_notebook()
            self.wait(lambda: not self.view.busy)
        self.assertEqual(self.view._settings.notebook, self.client.books[0])
        self.assertIn("could not be saved", self.view.status_var.get())

    def test_all_notebooks_requires_explicit_choice_and_clears_saved_scope(self):
        self.view._settings = OneNoteSettings(self.launcher, self.client.books[0])
        with patch("context_palette.onenote_window.NotebookChoiceDialog") as chooser:
            chooser.return_value.show.return_value = (True, None)
            self.view.choose_notebook()
            self.wait(lambda: not self.view.busy)
        self.assertIsNone(load_onenote_settings(self.view.settings_path).notebook)
        self.assertEqual(self.view.notebook_var.get(), "All open notebooks")

    def test_notebook_picker_does_not_default_to_all_when_saved_book_is_absent(self):
        picker = NotebookChoiceDialog(self.view.window, NotebookList(self.client.books, 2, False),
                                      NotebookRef("missing", "Closed notebook"))
        self.assertEqual(picker.results.selection(), ())
        picker.choose()
        self.assertTrue(picker.window.winfo_exists())
        picker.results.selection_set("1")
        picker.choose()
        self.assertEqual(picker.result, (True, self.client.books[1]))

    def test_controls_fit_and_keyboard_navigation_remains_available(self):
        self.root.update()
        height = self.view.window.winfo_height()
        for widget in (self.view.query_entry, self.view.results, self.view.preview_text,
                       self.view.use_button, self.view.close_button):
            self.assertTrue(widget.winfo_ismapped())
            self.assertGreater(widget.winfo_height(), 15)
            bottom = widget.winfo_rooty() + widget.winfo_height() - self.view.window.winfo_rooty()
            self.assertLessEqual(bottom, height)

    def sibling_launcher(self):
        launcher = self.application_root.parent / "python-onenote" / "python-onenote.bat"
        launcher.parent.mkdir(exist_ok=True)
        launcher.write_text("synthetic launcher, never executed")
        return launcher

    def reopen_for_discovery(self):
        settings_path = self.view.settings_path
        self.view.close()
        factory = Mock(return_value=self.client)
        self.view = OneNoteWindow(self.root, settings_path=settings_path,
            initial_query="selected query", client_factory=factory,
            session_reader=lambda: self.session, apply_text=lambda *_: False,
            on_close=lambda: None, application_root=self.application_root)
        return factory

    def test_explicit_engine_takes_precedence_over_present_sibling(self):
        self.sibling_launcher()
        settings = OneNoteSettings(self.launcher, self.client.books[0])
        save_onenote_settings(self.view.settings_path, settings)
        with patch("context_palette.onenote_window.discover_direct_sibling_python_onenote_launcher") as discovery:
            factory = self.reopen_for_discovery()
        discovery.assert_not_called()
        factory.assert_called_once_with(self.launcher)
        self.assertEqual(self.view._settings, settings)
        self.assertEqual(self.client.calls, [])
        self.assertFalse(self.view._ready)

    def test_missing_explicit_engine_blocks_present_sibling(self):
        self.sibling_launcher()
        settings = OneNoteSettings(self.launcher, self.client.books[0])
        save_onenote_settings(self.view.settings_path, settings)
        self.launcher.unlink()
        with patch("context_palette.onenote_window.discover_direct_sibling_python_onenote_launcher") as discovery:
            factory = self.reopen_for_discovery()
        discovery.assert_not_called()
        factory.assert_not_called()
        self.assertEqual(self.view._settings, settings)
        self.assertTrue(self.view.search_button.instate(("disabled",)))
        self.assertIn("unavailable", self.view.setup_var.get())
        self.assertEqual(self.view.status_var.get(), self.view.setup_var.get())
        self.view.query_var.set("repair still needed")
        self.root.update()
        self.assertEqual(self.view.status_var.get(), self.view.setup_var.get())

    def test_invalid_explicit_engine_blocks_sibling_and_preserves_notebook_on_repair(self):
        self.sibling_launcher()
        self.view.settings_path.write_text(json.dumps({"launcher_path": "relative/python-onenote.bat",
            "notebook": {"object_id": "notebook-one", "title": "First notebook"}}), encoding="utf-8")
        with patch("context_palette.onenote_window.discover_direct_sibling_python_onenote_launcher") as discovery:
            factory = self.reopen_for_discovery()
        discovery.assert_not_called()
        factory.assert_not_called()
        self.assertTrue(self.view.search_button.instate(("disabled",)))
        self.assertEqual(self.view._settings.notebook, self.client.books[0])
        with patch("context_palette.onenote_window.filedialog.askopenfilename", return_value=str(self.launcher)):
            self.view.choose_engine()
        self.assertEqual(load_onenote_settings(self.view.settings_path),
                         OneNoteSettings(self.launcher, self.client.books[0]))
        self.assertFalse(self.view._ready)
        self.assertIsNone(self.view._session)

    def test_corrupt_settings_do_not_fall_back_to_sibling(self):
        self.sibling_launcher()
        self.view.settings_path.write_text("invalid JSON", encoding="utf-8")
        with patch("context_palette.onenote_window.discover_direct_sibling_python_onenote_launcher") as discovery:
            factory = self.reopen_for_discovery()
        discovery.assert_not_called()
        factory.assert_not_called()
        self.assertIn("repair", self.view.setup_var.get())
        self.assertIn("Change engine", self.view.status_var.get())
        self.assertFalse(self.view.choose_button.instate(("disabled",)))

    def test_absent_sibling_keeps_manual_choice_and_reads_disabled(self):
        factory = self.reopen_for_discovery()
        factory.assert_not_called()
        self.assertEqual(self.client.calls, [])
        self.assertIn("No sibling engine found", self.view.setup_var.get())
        self.assertFalse(self.view.choose_button.instate(("disabled",)))
        self.assertTrue(self.view.search_button.instate(("disabled",)))

    def test_space_unicode_installation_discovery_ignores_foreign_cwd_and_settings_location(self):
        sibling = self.sibling_launcher()
        foreign = Path(self.tmp.name) / "foreign 秘密" / "Context Palette"
        foreign.mkdir(parents=True)
        decoy = foreign.parent / "python-onenote" / "python-onenote.bat"
        decoy.parent.mkdir()
        decoy.write_text("never executed")
        previous = Path.cwd()
        try:
            os.chdir(foreign)
            factory = self.reopen_for_discovery()
        finally:
            os.chdir(previous)
        factory.assert_called_once_with(sibling)
        self.assertEqual(self.client.calls, [])
        self.assertFalse(self.view.settings_path.exists())
        self.view.query_var.set("typing must not read")
        self.root.update()
        self.assertEqual(self.client.calls, [])
        self.assertFalse(self.view._ready)
        self.assertIsNone(self.view._session)
        self.assertFalse(self.view._described)
        self.assertTrue(self.view.preview_button.instate(("disabled",)))
        self.assertTrue(self.view.use_button.instate(("disabled",)))
        self.view.search()
        self.wait(lambda: not self.view.busy)
        self.assertEqual(self.client.calls, [("describe",), ("probe",), ("search", "typing must not read")])

    def test_discovered_engine_can_save_notebook_without_pinning_engine_path(self):
        sibling = self.sibling_launcher()
        self.reopen_for_discovery()
        with patch("context_palette.onenote_window.NotebookChoiceDialog") as chooser:
            chooser.return_value.show.return_value = (True, self.client.books[1])
            self.view.choose_notebook()
            self.wait(lambda: not self.view.busy)
        saved = load_onenote_settings(self.view.settings_path)
        self.assertIsNone(saved.launcher_path)
        self.assertEqual(saved.notebook, self.client.books[1])
        factory = self.reopen_for_discovery()
        factory.assert_called_once_with(sibling)
        self.assertEqual(self.view._settings.notebook, self.client.books[1])

    def test_default_discovery_root_comes_from_installed_module(self):
        sibling = self.sibling_launcher()
        settings_path = self.view.settings_path
        self.view.close()
        factory = Mock(return_value=self.client)
        installed_module = self.application_root / "src" / "context_palette" / "onenote_window.py"
        with patch("context_palette.onenote_window.__file__", str(installed_module)):
            self.view = OneNoteWindow(self.root, settings_path=settings_path,
                initial_query="", client_factory=factory, session_reader=lambda: self.session,
                apply_text=lambda *_: False, on_close=lambda: None)
        factory.assert_called_once_with(sibling)
        self.assertEqual(self.view.application_root, self.application_root)
        self.assertEqual(self.client.calls, [])

    def test_unusable_explicit_engine_requires_repair_without_sibling_fallback(self):
        self.sibling_launcher()
        settings = OneNoteSettings(self.launcher, self.client.books[0])
        save_onenote_settings(self.view.settings_path, settings)
        factory = self.reopen_for_discovery()
        with patch.object(self.client, "describe", side_effect=OneNoteError("integration.engine_failed")):
            self.view.search()
            self.wait(lambda: not self.view.busy)
        factory.assert_called_once_with(self.launcher)
        self.assertIsNone(self.view._client)
        self.assertTrue(self.view.search_button.instate(("disabled",)))
        self.assertIn("repair", self.view.setup_var.get())
        self.assertEqual(load_onenote_settings(self.view.settings_path), settings)
        self.assertFalse(self.view._ready)
        self.assertEqual(self.client.calls, [])


class ReviewedPlacementTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.status = []
        self.panel = WorkspacePanel(ttk.Frame(self.root), clipboard_getter=lambda: "unchanged",
            clipboard_setter=lambda _: self.fail("Clipboard must stay unchanged"),
            status_setter=self.status.append, tooltip_adder=lambda *args: None)

    def tearDown(self):
        for callback in self.root.tk.splitlist(self.root.tk.call("after", "info")):
            self.root.tk.call("after", "cancel", callback)
        self.root.destroy()

    def place(self, expected="original", current=lambda: True):
        return self.panel.apply_reviewed_text("reviewed", expected_text=expected,
                                            is_current=current, parent=self.root)

    def test_replace_append_cancel_and_undo(self):
        for choice, expected in (("replace", "reviewed"), ("append", "original\n\nreviewed"), (None, "original")):
            self.panel.set_text("original")
            with patch("context_palette.workspace_panel.TextPlacementDialog.show", return_value=choice):
                self.place()
            self.assertEqual(self.panel.raw_text(), expected)
            if choice:
                self.panel.text.edit_undo()
                self.assertEqual(self.panel.raw_text(), "original")

    def test_empty_destination_still_requires_choice(self):
        with patch("context_palette.workspace_panel.TextPlacementDialog.show", return_value=None) as choose:
            self.place(expected="")
        choose.assert_called_once()
        self.assertEqual(self.panel.raw_text(), "")
        with patch("context_palette.workspace_panel.TextPlacementDialog.show", return_value="append"):
            self.place(expected="")
        self.assertEqual(self.panel.raw_text(), "reviewed")

    def test_changed_destination_during_choice_is_not_overwritten(self):
        self.panel.set_text("original")
        def changed():
            self.panel.set_text("newer")
            return "replace"
        with patch("context_palette.workspace_panel.TextPlacementDialog.show", side_effect=changed):
            self.assertIsNone(self.place())
        self.assertEqual(self.panel.raw_text(), "newer")

    def test_stale_workflow_during_choice_cannot_apply(self):
        states = iter((True, False))
        self.panel.set_text("original")
        with patch("context_palette.workspace_panel.TextPlacementDialog.show", return_value="replace"):
            self.assertIsNone(self.place(current=lambda: next(states)))
        self.assertEqual(self.panel.raw_text(), "original")

    def test_launcher_seeds_only_selection_reuses_window_and_routes_reviewed_text(self):
        self.panel.set_text("choose these words only")
        self.panel.text.tag_add(tk.SEL, "1.7", "1.12")
        app = LauncherApp.__new__(LauncherApp)
        app.root = self.root
        app.workspace_component = self.panel
        app.data_paths = AppDataPaths(Path(tempfile.gettempdir()))
        app.status_var = tk.StringVar()
        app._set_workspace_visible = Mock()
        app._reveal_window = Mock(return_value=True)
        app.captured_selection = "old authority"
        app.source_foreground_handle = 42
        workflow = Mock()
        workflow.window = self.root
        with patch("context_palette.launcher.OneNoteWindow", return_value=workflow) as factory:
            app._find_onenote_notes()
            args = factory.call_args.kwargs
            self.assertEqual(args["initial_query"], "these")
            app._find_onenote_notes()
            factory.assert_called_once()
            workflow.show.assert_called_once()
            with patch("context_palette.workspace_panel.TextPlacementDialog.show", return_value="replace"):
                self.assertTrue(args["apply_text"]("exact reviewed", lambda: True))
            self.assertEqual(self.panel.raw_text(), "exact reviewed")
            app._reveal_window.assert_called_once_with(
                sync_workspace=False, focus_search=False, temporary_attention=False,
            )
            self.assertIsNone(app.captured_selection)
            self.assertIsNone(app.source_foreground_handle)
            args["on_close"]()
            self.assertIsNone(app.onenote_window)
            self.panel.text.tag_remove(tk.SEL, "1.0", tk.END)
            app._find_onenote_notes()
            self.assertEqual(factory.call_args.kwargs["initial_query"], "")

    def test_quit_cancels_read_and_waits_for_cleanup(self):
        app = LauncherApp.__new__(LauncherApp)
        app.onenote_window = Mock()
        app.onenote_window.close.return_value = False
        app.status_var = tk.StringVar()
        app.root = Mock()
        app.quit_app()
        app.onenote_window.close.assert_called_once()
        app.root.destroy.assert_not_called()
        self.assertIn("cleanup", app.status_var.get())
