"""Real Tk with fake accounts and responses; no browser, network or credentials."""
from pathlib import Path
from types import SimpleNamespace
import gc
import queue
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from context_palette.actions import Action, ActionError
from context_palette.chatgpt_client import ChatGPTModel, ChatMessage
from context_palette.chatgpt_http import ChatGPTError
from context_palette.chatgpt_window import ChatGPTWindow
from context_palette.data_catalog import AppDataPaths
from context_palette.launcher import LauncherApp
from context_palette.style import configure_theme
from context_palette.workspace_panel import WorkspacePanel


class FakeAuth:
    def __init__(self):
        self.calls = []
        self.snapshot = None
        self.hook = None
        self.running = False

    @property
    def account(self):
        # A locked getter would block Tk; fail deterministically on that misuse.
        if self.running and threading.current_thread() is threading.main_thread():
            raise AssertionError("Tk read the busy auth manager")
        return self.snapshot

    def sign_in(self, cancel):
        self.calls.append("sign_in")
        self.running = True
        try:
            if self.hook:
                self.hook(cancel)
            self.snapshot = SimpleNamespace(display_label="Synthetic account", can_use_plan=True,
                                             needs_reauthorization=False)
            return self.snapshot
        finally:
            self.running = False

    def access_token(self, cancel):
        self.calls.append("access_token")
        return "synthetic-test-token"

    def sign_out(self):
        self.calls.append("sign_out")
        self.snapshot = None


class FakeClient:
    def __init__(self):
        self.calls = []
        self.hook = None

    def list_models(self, token, cancel):
        self.calls.append(("models",))
        return (ChatGPTModel("test-model", "Test model"),)

    def respond(self, token, model, messages, on_delta, cancel):
        self.calls.append(("respond", model, tuple(messages)))
        if self.hook:
            return self.hook(on_delta, cancel)
        on_delta("## Answer\n**Clear** and short.")
        return "## Answer\n**Clear** and short."


class ChatGPTWindowTests(unittest.TestCase):
    def setUp(self):
        gc.collect()
        self.root = tk.Tk()
        self.root.withdraw()
        self.original_scaling = float(self.root.tk.call("tk", "scaling"))
        configure_theme(self.root)
        self.temp = tempfile.TemporaryDirectory(prefix="palette synthetic chat ")
        self.auth = FakeAuth()
        self.client = FakeClient()
        self.placed = []
        self.copied = []
        self.closed = []
        self.prompts = []
        self.prompt_reads = []
        self.view = self.make_window()

    def make_window(self, parent=None):
        return ChatGPTWindow(parent or self.root,
            settings_path=Path(self.temp.name) / "private.json",
            initial_text="Explain this clearly", expected_workspace="Original workspace",
            apply_text=lambda value, current, expected: self.placed.append((value, current(), expected)) or True,
            copy_text=self.copied.append, on_close=lambda: self.closed.append(True),
            prompt_actions=lambda: self.prompts, prompt_reader=self.read_prompt,
            auth_factory=lambda _path: self.auth, client_factory=lambda: self.client)

    def read_prompt(self, action_id):
        self.prompt_reads.append(action_id)
        action = next((action for action in self.prompts
                       if action.id == action_id and action.type == "ai_prompt" and action.state == "Active"), None)
        if action is None:
            raise ActionError("This prompt is no longer available. Open Prompts again.")
        return action.title, action.value

    def menu_labels(self, menu):
        end = menu.index(tk.END)
        return [menu.entrycget(index, "label") for index in range(end + 1)
                if menu.type(index) != "separator"] if end is not None else []

    def tearDown(self):
        if not self.view._closed:
            self.view.close()
            self.wait(lambda: self.view._closed)
        self.root.tk.call("tk", "scaling", self.original_scaling)
        self.root.destroy()
        self.temp.cleanup()
        gc.collect()

    def wait(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not predicate():
            self.root.update()
            time.sleep(0.005)
        self.root.update()
        self.assertTrue(predicate())

    def connect(self):
        self.view.connect()
        self.wait(lambda: not self.view.busy)

    def send(self):
        self.view.send()
        self.wait(lambda: not self.view.busy)

    def test_open_typing_and_show_do_not_connect_or_persist(self):
        self.view.composer.insert(tk.END, "\nQuestion")
        self.view.show()
        self.root.update()
        self.assertEqual(self.auth.calls, [])
        self.assertEqual(self.client.calls, [])
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        self.assertEqual(self.placed + self.copied, [])

    def test_prompt_menu_reuses_root_icons_nested_order_and_active_membership(self):
        self.prompts = [
            Action("root", "Start project", "AI", "ai_prompt", "Root prompt"),
            Action("short", "Brief answer", "AI", "ai_prompt", "Keep it brief", quick_action_path=("Clear answers",)),
            Action("deep", "New project", "AI", "ai_prompt", "Project prompt", quick_action_path=("Project setup", "Owner")),
            Action("archived", "Old prompt", "AI", "ai_prompt", "Old", state="Archived"),
            Action("other", "A folder", "AI", "open_folder", "D:/example"),
        ]
        self.view._refresh_prompt_menu()
        self.assertEqual(self.menu_labels(self.view.prompts_menu),
                         [self.prompts[0].compact_display_text, "Clear answers", "Project setup"])
        clear = self.view.window.nametowidget(self.view.prompts_menu.entrycget(2, "menu"))
        project = self.view.window.nametowidget(self.view.prompts_menu.entrycget(3, "menu"))
        owner = self.view.window.nametowidget(project.entrycget(0, "menu"))
        self.assertEqual(self.menu_labels(clear), [self.prompts[1].compact_display_text])
        self.assertEqual(self.menu_labels(owner), [self.prompts[2].compact_display_text])
        self.assertEqual(self.prompt_reads, [])
        self.assertEqual(self.auth.calls + self.client.calls + self.placed + self.copied, [])

    def test_prompt_selection_preserves_draft_and_inserts_as_one_undoable_edit(self):
        self.prompts = [Action("short", "Brief", "AI", "ai_prompt", "Keep the answer short.")]
        self.view.composer.mark_set(tk.INSERT, tk.END)
        self.view._refresh_prompt_menu()
        self.view.prompts_menu.invoke(0)
        self.assertEqual(self.view.composer.get("1.0", "end-1c"),
                         "Explain this clearly\n\nKeep the answer short.")
        self.assertEqual(self.prompt_reads, ["short"])
        self.assertEqual(self.view._history, [])
        self.assertEqual(self.auth.calls + self.client.calls + self.placed + self.copied, [])
        self.view.composer.edit_undo()
        self.assertEqual(self.view.composer.get("1.0", "end-1c"), "Explain this clearly")

    def test_prompt_selection_preserves_selected_text_at_the_cursor(self):
        self.prompts = [Action("plain", "Plain", "AI", "ai_prompt", "Prompt")]
        self.view.composer.tag_add(tk.SEL, "1.0", "1.7")
        self.view.composer.mark_set(tk.INSERT, "1.0")
        self.view.insert_prompt("plain")
        self.assertEqual(self.view.composer.get("1.0", "end-1c"), "Prompt\n\nExplain this clearly")
        self.assertEqual(self.placed + self.copied, [])

    def test_prompt_menu_refreshes_current_configuration_and_removes_old_submenus(self):
        self.prompts = [Action("first", "First", "AI", "ai_prompt", "First", quick_action_path=("Old group",))]
        self.view._refresh_prompt_menu()
        old_menu = self.view._prompt_submenus[0]
        self.prompts = [Action("second", "Second", "AI", "ai_prompt", "Second", quick_action_path=("New group",))]
        self.view._refresh_prompt_menu()
        self.assertEqual(self.menu_labels(self.view.prompts_menu), ["New group"])
        self.assertFalse(old_menu.winfo_exists())
        self.assertEqual(len(self.view._prompt_submenus), 1)

    def test_prompt_callback_rechecks_current_value_and_unavailable_ids(self):
        self.prompts = [Action("first", "First", "AI", "ai_prompt", "Old value")]
        self.view._refresh_prompt_menu()
        self.prompts = [Action("first", "First", "AI", "ai_prompt", "Updated value")]
        self.view.prompts_menu.invoke(0)
        self.assertIn("Updated value", self.view.composer.get("1.0", "end-1c"))
        before = self.view.composer.get("1.0", "end-1c")
        self.prompts = []
        self.view.prompts_menu.invoke(0)
        self.assertEqual(self.view.composer.get("1.0", "end-1c"), before)
        self.assertIn("no longer available", self.view.notice_var.get())
        self.assertEqual(self.auth.calls + self.client.calls + self.placed + self.copied, [])

    def test_empty_prompt_menu_and_empty_prompt_have_clear_guidance(self):
        self.view._refresh_prompt_menu()
        self.assertEqual(self.menu_labels(self.view.prompts_menu), ["No saved prompts yet"])
        self.assertEqual(self.view.prompts_menu.entrycget(0, "state"), "disabled")
        self.prompts = [Action("empty", "Empty", "AI", "ai_prompt", " ")]
        self.view.insert_prompt("empty")
        self.assertEqual(self.view.composer.get("1.0", "end-1c"), "Explain this clearly")
        self.assertIn("empty", self.view.notice_var.get())

    def test_prompt_insertion_is_refused_while_busy_or_closing(self):
        self.prompts = [Action("first", "First", "AI", "ai_prompt", "Prompt")]
        self.view._job = object()
        self.view._refresh_controls()
        self.assertEqual(str(self.view.prompts_button.cget("state")), "disabled")
        self.view.insert_prompt("first")
        self.view._refresh_prompt_menu()
        self.assertEqual(self.menu_labels(self.view.prompts_menu), ["Wait for the current request"])
        self.assertEqual(self.prompt_reads, [])
        self.view._job = None
        self.view._closing = True
        self.view.insert_prompt("first")
        self.assertEqual(self.prompt_reads, [])
        self.view._closing = False

    def test_shift_tab_from_message_reaches_the_prompts_control(self):
        with patch.object(self.view.prompts_button, "focus_set") as prompt_focus:
            self.assertEqual(self.view._focus_model(), "break")
            prompt_focus.assert_called_once()

    def test_sign_in_only_loads_models_and_does_not_send(self):
        self.connect()
        self.assertEqual(self.auth.calls, ["sign_in", "access_token"])
        self.assertEqual(self.client.calls, [("models",)])
        self.assertEqual(self.view.composer.get("1.0", "end-1c"), "Explain this clearly")
        self.assertEqual(self.placed + self.copied, [])

    def test_complete_followup_retains_exact_history_and_places_only_on_request(self):
        self.connect()
        self.send()
        self.assertEqual(self.placed + self.copied, [])
        self.view.composer.insert("1.0", "What next?")
        self.send()
        request = self.client.calls[-1]
        self.assertEqual(request[2], (
            ChatMessage("user", "Explain this clearly"),
            ChatMessage("assistant", "## Answer\n**Clear** and short."),
            ChatMessage("user", "What next?")))
        self.view.copy_answer()
        self.view.use_answer()
        self.assertEqual(self.copied, ["## Answer\n**Clear** and short."])
        self.assertEqual(self.placed, [(self.copied[0], True, "Original workspace")])

    def test_incomplete_delta_cannot_be_used_or_added_to_history(self):
        self.connect()
        def incomplete(delta, cancel):
            delta("Provisional private text")
            raise ChatGPTError("incomplete", "Reply incomplete")
        self.client.hook = incomplete
        self.send()
        self.view.copy_answer()
        self.view.use_answer()
        self.assertEqual(self.view._history, [])
        self.assertEqual(self.placed + self.copied, [])
        self.assertEqual(self.view.composer.get("1.0", "end-1c"), "Explain this clearly")
        self.assertIn("Incomplete answer", self.view.transcript.get("1.0", tk.END))

    def test_busy_auth_never_blocks_tk_controls_and_can_stop(self):
        started = threading.Event()
        def blocking(cancel):
            started.set()
            cancel.wait(2)
        self.auth.hook = blocking
        self.view.connect()
        self.assertTrue(started.wait(1))
        self.root.update()
        self.view.cancel()
        self.wait(lambda: not self.view.busy)
        self.assertEqual(self.client.calls, [("models",)])
        self.assertEqual(self.view._models, ())

    def test_cancel_drops_a_late_complete_answer_without_retry(self):
        self.connect()
        started = threading.Event()
        def late(delta, cancel):
            started.set()
            cancel.wait(2)
            return "Late completed answer"
        self.client.hook = late
        self.view.send()
        self.assertTrue(started.wait(1))
        self.view.cancel()
        self.wait(lambda: not self.view.busy)
        self.assertEqual(self.view._answer, "")
        self.assertEqual(self.view._history, [])
        self.assertEqual(sum(call[0] == "respond" for call in self.client.calls), 1)

    def test_stale_worker_response_is_ignored(self):
        generation = self.view._generation
        self.view.new_chat()
        self.view._queue.put((generation, "delta", "stale", None))
        self.view._queue.put((generation, "send", "stale", None))
        self.view._poll()
        self.assertEqual(self.view._history, [])
        self.assertEqual(self.view._answer, "")
        self.assertNotIn("stale", self.view.transcript.get("1.0", tk.END))

    def test_new_chat_clears_history_without_external_effects(self):
        self.connect()
        self.send()
        calls = list(self.client.calls)
        self.view.new_chat()
        self.assertEqual(self.view._history, [])
        self.assertEqual(self.view._answer, "")
        self.assertEqual(self.client.calls, calls)
        self.assertEqual(self.placed + self.copied, [])

    def test_forget_clears_chat_and_says_it_is_local_only(self):
        self.connect()
        self.send()
        self.view.forget()
        self.assertIsNone(self.auth.account)
        self.assertEqual(self.view._history, [])
        self.assertIn("remaining access", self.view.notice_var.get())
        self.assertEqual(self.auth.calls[-1], "sign_out")

    def test_authorization_failure_offers_returning_sign_in(self):
        self.connect()
        def rejected(delta, cancel):
            raise ChatGPTError("refresh_uncertain", "Sign in again")
        self.client.hook = rejected
        self.send()
        self.assertEqual(self.view.connect_button.cget("text"), "Continue with ChatGPT")
        self.connect()
        self.assertEqual(self.auth.calls.count("sign_in"), 2)

    def test_close_waits_for_cancelled_worker_then_discards_chat(self):
        self.connect()
        started = threading.Event()
        def blocking(delta, cancel):
            started.set()
            cancel.wait(2)
            return "late"
        self.client.hook = blocking
        self.view.send()
        self.assertTrue(started.wait(1))
        self.assertFalse(self.view.close())
        self.wait(lambda: self.view._closed)
        self.assertEqual(self.view._history, [])
        self.assertEqual(self.closed, [True])
        self.assertEqual(self.placed, [])

    def test_repeated_send_key_is_one_request_until_key_release(self):
        self.connect()
        self.view._send_key_press()
        self.wait(lambda: not self.view.busy)
        self.view.composer.insert("1.0", "Do not send on key repeat")
        self.view._send_key_press()
        self.assertEqual(sum(call[0] == "respond" for call in self.client.calls), 1)
        self.view._send_key_release()
        self.view._send_key_press()
        self.wait(lambda: not self.view.busy)
        self.assertEqual(sum(call[0] == "respond" for call in self.client.calls), 2)

    def test_reply_rendering_never_interprets_html_as_ui(self):
        self.connect()
        self.client.hook = lambda delta, cancel: "<script>private()</script>\n## Heading\n**Bold**"
        self.send()
        text = self.view.transcript.get("1.0", tk.END)
        self.assertIn("<script>private()</script>", text)
        self.assertIn("Heading", text)
        self.assertNotIn("**Bold**", text)

    def test_primary_controls_fit_supported_windows_scaling(self):
        for scaling in (4 / 3, 5 / 3, 2.0):
            with self.subTest(scaling=scaling):
                root = tk.Tk()
                root.withdraw()
                previous_scaling = float(root.tk.call("tk", "scaling"))
                root.tk.call("tk", "scaling", scaling)
                configure_theme(root)
                view = self.make_window(root)
                try:
                    root.update()
                    for widget in (view.connect_button, view.forget_button, view.new_button,
                                   view.copy_button, view.use_button, view.send_button, view.close_button,
                                   view.prompts_button):
                        self.assertGreaterEqual(widget.winfo_width() + 1, widget.winfo_reqwidth())
                        self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(),
                                             view.window.winfo_rootx() + view.window.winfo_width())
                finally:
                    view.close()
                    root.tk.call("tk", "scaling", previous_scaling)
                    root.destroy()


class ChatGPTHostTests(unittest.TestCase):
    def test_chat_prompt_reader_expands_current_action_only_on_selection(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.root.clipboard_get.return_value = "Chosen clipboard text"
        app._set_clipboard = Mock()
        app._execute_action = Mock()
        app.actions = [Action("first", "Prompt", "AI", "ai_prompt", "Source: %CLIPBOARD%\\nReview it")]
        self.assertEqual(app._read_chat_prompt("first"), ("Prompt", "Source: Chosen clipboard text\nReview it"))
        app.root.clipboard_get.assert_called_once()
        app._set_clipboard.assert_not_called()
        app._execute_action.assert_not_called()

    def test_plain_chat_prompt_does_not_read_clipboard_and_wrong_type_or_state_cannot_run(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.actions = [Action("plain", "Plain", "AI", "ai_prompt", "Use this text"),
                       Action("archived", "Old", "AI", "ai_prompt", "Old", state="Archived"),
                       Action("other", "Folder", "AI", "open_folder", "D:/example")]
        self.assertEqual(app._read_chat_prompt("plain"), ("Plain", "Use this text"))
        for action_id in ("missing", "archived", "other"):
            with self.subTest(action_id=action_id), self.assertRaises(ActionError):
                app._read_chat_prompt(action_id)
        app.root.clipboard_get.assert_not_called()

    def test_launcher_stages_selection_and_reuses_window_without_sending(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.data_paths = AppDataPaths.from_root(Path("D:/synthetic"))
        app.workspace_component = Mock()
        app.workspace_component.raw_text.return_value = "Full workspace"
        app.workspace_component.selected_or_full_text.return_value = "Only selection"
        app._set_clipboard = Mock()
        with patch("context_palette.launcher.ChatGPTWindow") as factory:
            app._chat_with_chatgpt()
            kwargs = factory.call_args.kwargs
            self.assertEqual(kwargs["initial_text"], "Only selection")
            self.assertEqual(kwargs["expected_workspace"], "Full workspace")
            self.assertEqual(kwargs["settings_path"], app.data_paths.chatgpt_connection_file)
            app.actions = [Action("current", "Current", "AI", "ai_prompt", "Current prompt")]
            self.assertIs(kwargs["prompt_actions"](), app.actions)
            self.assertEqual(kwargs["prompt_reader"], app._read_chat_prompt)
            app._chat_with_chatgpt()
            factory.assert_called_once()
            factory.return_value.show.assert_called_once()
            app._set_clipboard.assert_not_called()

    def test_reviewed_chat_placement_uses_same_undoable_stale_checked_path(self):
        root = tk.Tk()
        root.withdraw()
        try:
            panel = WorkspacePanel(root, clipboard_getter=lambda: "unused",
                clipboard_setter=Mock(), status_setter=Mock(), tooltip_adder=lambda *_: None)
            panel.set_text("Keep me")
            with patch("context_palette.workspace_panel.TextPlacementDialog") as dialog:
                dialog.return_value.show.return_value = "append"
                result = panel.apply_reviewed_text("Answer", expected_text="Keep me",
                    is_current=lambda: True, parent=root, source_label="ChatGPT")
                self.assertEqual(result, "append")
                self.assertEqual(panel.raw_text(), "Keep me\n\nAnswer")
                self.assertIn("ChatGPT", dialog.call_args.args[1])
                panel.clipboard_setter.assert_not_called()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
