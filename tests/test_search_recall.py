from __future__ import annotations

import gc
import sys
import tkinter as tk
import unittest
from unittest.mock import patch

from context_palette.launcher import DISCOVERY_ACTIONS, DISCOVERY_ALL
from tests.support.launcher_ui import disposable_launcher


@unittest.skipUnless(sys.platform == "win32", "Requires Windows Tk.")
class SearchRecallTests(unittest.TestCase):
    """Session search recall through real widgets with external effects isolated."""

    def setUp(self) -> None:
        gc.collect()

    def _show_and_complete_search_focus(self, app, request=None) -> None:
        scheduled_focus = []
        original_after = app.root.after

        def record_after(delay, callback=None, *args):
            timer = original_after(delay, callback, *args)
            if callback == app.focus_search:
                scheduled_focus.append((delay, timer, callback, args))
            return timer

        with patch.object(app.root, "after", side_effect=record_after):
            if request is None:
                app.show_window()
            else:
                app._handle_external_request(request)
        self.assertTrue(scheduled_focus)
        app.root.update()
        for delay, timer, callback, args in scheduled_focus:
            self.assertEqual(delay, 80)
            app.root.after_cancel(timer)
            callback(*args)
        app.root.update()
        self.assertEqual(app.root.focus_get(), app.search_entry)

    def _assert_whole_query_selected(self, app, expected) -> None:
        self.assertEqual(app.search_var.get(), expected)
        self.assertTrue(app.search_entry.selection_present())
        self.assertEqual(app.search_entry.index(tk.SEL_FIRST), 0)
        self.assertEqual(app.search_entry.index(tk.SEL_LAST), len(expected))

    def test_repeated_hide_and_reopen_retains_and_selects_current_query(self):
        with disposable_launcher() as (app, *_):
            app.hotkey_available = True
            for query in ("Sample", "another query", "Sample"):
                with self.subTest(query=query):
                    app.search_var.set(query)
                    app.hide_window()
                    self.assertEqual(app.root.state(), "withdrawn")
                    self._show_and_complete_search_focus(app)
                    self._assert_whole_query_selected(app, query)

    def test_delete_or_backspace_restores_results_without_resetting_filters(self):
        for key in ("Delete", "BackSpace"):
            with self.subTest(key=key), disposable_launcher() as (app, *_):
                app._select_discovery_scope(DISCOVERY_ACTIONS)
                app._select_action_type_filter("copy_text")
                app.search_var.set("no matching item")
                app._refresh_results()
                self.assertEqual(app.displayed_actions, [])
                app.root.withdraw()
                self._show_and_complete_search_focus(app)
                self._assert_whole_query_selected(app, "no matching item")

                app.search_entry.event_generate(f"<KeyPress-{key}>")
                app.root.update()
                app._refresh_results()

                self.assertEqual(app.search_var.get(), "")
                self.assertEqual(app.discovery_scope, DISCOVERY_ACTIONS)
                self.assertEqual(app.action_type_filter, "copy_text")
                self.assertEqual([action.id for action in app.displayed_actions], ["sample"])

    def test_typing_replaces_the_selected_recalled_query(self):
        with disposable_launcher() as (app, *_):
            app.search_var.set("old search")
            app.root.withdraw()
            self._show_and_complete_search_focus(app)
            self._assert_whole_query_selected(app, "old search")

            app.search_entry.event_generate("<KeyPress-a>")
            app.root.update()

            self.assertEqual(app.search_var.get(), "a")

    def test_f5_still_clears_query_and_restores_startup_view(self):
        with disposable_launcher() as (app, *_):
            app._select_discovery_scope(DISCOVERY_ACTIONS)
            app._select_action_type_filter("copy_text")
            app.search_var.set("Sample")
            app.root.withdraw()
            self._show_and_complete_search_focus(app)

            app.search_entry.event_generate("<KeyPress-F5>")
            app.root.update()

            self.assertEqual(app.search_var.get(), "")
            self.assertEqual(app.discovery_scope, DISCOVERY_ALL)
            self.assertIsNone(app.action_type_filter)

    def test_search_is_not_saved_and_a_new_app_starts_empty(self):
        with disposable_launcher() as (app, *_):
            settings_path = app.palette_path
            original_settings = settings_path.read_bytes() if settings_path.exists() else None
            app.search_var.set("session-only query")
            app.root.withdraw()
            self._show_and_complete_search_focus(app)
            self.assertEqual(
                settings_path.read_bytes() if settings_path.exists() else None,
                original_settings,
            )
        with disposable_launcher() as (new_app, *_):
            self.assertEqual(new_app.search_var.get(), "")

    def test_external_request_query_overrides_the_recalled_query(self):
        for request, expected in (
            ({"command": "show", "search": "  Sample  "}, "Sample"),
            ({"command": "show", "search": ""}, ""),
            ({"command": "show", "search": "   "}, ""),
            ({"command": "show"}, "old query"),
        ):
            with self.subTest(request=request), disposable_launcher() as (app, *_):
                app.search_var.set("old query")
                app.root.withdraw()

                self._show_and_complete_search_focus(app, request)

                if expected:
                    self._assert_whole_query_selected(app, expected)
                else:
                    self.assertEqual(app.search_var.get(), "")
                    self.assertFalse(app.search_entry.selection_present())


if __name__ == "__main__":
    unittest.main()
