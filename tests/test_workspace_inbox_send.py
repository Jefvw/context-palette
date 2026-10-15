from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from context_palette.launcher import LauncherApp
from context_palette.work_items import DiscoveredWorkItem


class RecordingMenu:
    """Keep menu commands without constructing a Tk window."""

    def __init__(self) -> None:
        self.entries: list[dict[str, object]] = []

    def add_command(self, **options: object) -> None:
        self.entries.append(options)

    def add_separator(self) -> None:
        pass

    def add_cascade(self, **options: object) -> None:
        self.entries.append(options)

    @property
    def labels(self) -> list[str]:
        return [str(entry["label"]) for entry in self.entries]

    def options_for(self, label: str) -> dict[str, object]:
        return next(entry for entry in self.entries if entry.get("label") == label)


class WorkspaceInboxSendTests(unittest.TestCase):
    def _app(self, text: str, item: object | None, *, busy: bool = False) -> LauncherApp:
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.workspace_component = Mock()
        app.workspace_component.raw_text.return_value = text
        app.workspace_component.get_text.return_value = text.strip()
        app.work_item_inbox = Mock(running=busy)
        app.work_item_inbox.start.return_value = True
        app.work_item_index = Mock(items=())
        app._selected_work_item = Mock(return_value=item)
        app._choose_work_item_inbox = Mock()
        app._send_workspace_to_work_item_inbox = Mock()
        app._work_item_send_destination = Mock()
        app._add_send_destination_command = Mock()
        app._folder_send_destinations = Mock(return_value=[])
        app._clipboard_folder_actions = Mock(return_value=[])
        app.item_context_filter = None
        app.recent_send_destinations = []
        app.status_var = Mock()
        app.send_work_item_inbox_button = Mock()
        app._work_item_inbox_source = Mock(return_value="Input / Output")
        return app

    def test_url_input_offers_text_receivers_without_file_routes_or_dispatching(self):
        item = Mock(display_name="Issue report")
        app = self._app("https://example.com/report", item)
        menu = RecordingMenu()
        with (
            patch("context_palette.work_item_inbox.subprocess.run") as process,
            patch("context_palette.work_item_inbox.create_work_item_inbox_entry") as entry,
        ):
            app._populate_send_text_menu(menu)

        label = "Work Item Excel Inbox — Issue report"
        self.assertEqual(menu.options_for(label)["state"], "normal")
        self.assertIn("OneNote — new text page…", menu.labels)
        self.assertIn("ChatGPT…", menu.labels)
        self.assertNotIn("Save webpage as PDF…", menu.labels)
        self.assertNotIn("Copy files to:", menu.labels)
        self.assertNotIn("Open folder in VS Code", menu.labels)
        app._send_workspace_to_work_item_inbox.assert_not_called()
        app.work_item_inbox.start.assert_not_called()
        process.assert_not_called()
        entry.assert_not_called()
        app.workspace_component.raw_text.assert_called_once_with()
        app.workspace_component.selected_or_full_text.assert_not_called()
        app.root.clipboard_get.assert_not_called()
        app.root.clipboard_clear.assert_not_called()

    def test_empty_input_disables_both_selected_inbox_and_chooser(self):
        app = self._app(" \n\t", Mock(display_name="Issue report"))
        menu = RecordingMenu()
        app._populate_send_text_menu(menu)

        label = "Work Item Excel Inbox — Issue report"
        self.assertEqual(menu.options_for(label)["state"], "disabled")
        self.assertEqual(menu.options_for("Choose Work Item Excel Inbox…")["state"], "disabled")
        self.assertNotIn("Paste a webpage URL or file paths first", menu.labels)
        app.work_item_inbox.start.assert_not_called()

    def test_chooser_is_available_without_main_work_item_selection(self):
        app = self._app("A useful note", None)
        menu = RecordingMenu()
        app.work_item_index.items = (Mock(display_name="Available report"),)
        app._populate_send_text_menu(menu)

        label = "Choose Work Item Excel Inbox…"
        self.assertEqual(menu.options_for(label)["state"], "normal")
        self.assertNotIn("Work Item Excel Inbox — select a Work Item first", menu.labels)
        menu.options_for(label)["command"]()
        app._choose_work_item_inbox.assert_called_once_with()
        app._send_workspace_to_work_item_inbox.assert_not_called()

    def test_busy_inbox_disables_selected_destination(self):
        app = self._app("A useful note", Mock(display_name="Issue report"), busy=True)
        menu = RecordingMenu()
        app.work_item_index.items = (Mock(display_name="Available report"),)
        app._populate_send_text_menu(menu)

        self.assertEqual(menu.options_for("Work Item Excel Inbox — Issue report")["state"], "disabled")
        self.assertEqual(menu.options_for("Choose Work Item Excel Inbox…")["state"], "disabled")
        app.work_item_inbox.start.assert_not_called()

    def test_menu_command_keeps_exact_destination_when_main_selection_changes(self):
        item = Mock(display_name="Issue report")
        app = self._app("https://example.com/report", item)
        menu = RecordingMenu()
        app._populate_send_text_menu(menu)
        app._selected_work_item.return_value = Mock(display_name="Another issue")

        menu.options_for("Work Item Excel Inbox — Issue report")["command"]()

        app._send_workspace_to_work_item_inbox.assert_called_once_with(item)
        app.work_item_inbox.start.assert_not_called()

    def test_command_rechecks_existing_single_flight_guard_after_menu_opens(self):
        app = self._app("https://example.com/report", Mock(display_name="Issue report"))
        del app._send_workspace_to_work_item_inbox
        menu = RecordingMenu()
        app._populate_send_text_menu(menu)
        app.work_item_inbox.running = True

        menu.options_for("Work Item Excel Inbox — Issue report")["command"]()

        app.work_item_inbox.start.assert_not_called()
        app.workspace_component.get_text.assert_not_called()
        app.status_var.set.assert_called_once_with("An Inbox update is already running.")

    def test_plain_text_is_not_misrepresented_as_a_file_path_count(self):
        app = self._app("A note\nAnother line", None)
        menu = RecordingMenu()
        app._populate_send_files_menu(menu)

        self.assertIn("Copy files to:", menu.labels)
        self.assertFalse(any(label.startswith("Copy 2 file") for label in menu.labels))

    def test_menu_dispatch_reuses_existing_whole_text_and_exact_workbook_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "ISS-CAP40-report"
            folder.mkdir()
            workbook = folder / f"{folder.name}.xlsx"
            workbook.write_bytes(b"synthetic workbook marker")
            item = DiscoveredWorkItem(
                "cap40", "CAP40", folder.name, folder, folder.name,
                "ISS", "Issue", "CAP40", "report", (), workbook,
            )
            text = "  https://example.com/report\nThe entire note  "
            app = self._app(text, item)
            # Use the production boundary; this test replaces only the external
            # coordinator and native dialogs, not validation or entry creation.
            del app._send_workspace_to_work_item_inbox
            menu = RecordingMenu()
            app._populate_send_text_menu(menu)
            with patch("context_palette.launcher.messagebox.askyesno") as confirm:
                menu.options_for(f"Work Item Excel Inbox — {item.display_name}")["command"]()

            confirm.assert_not_called()
            app.work_item_inbox.start.assert_called_once()
            args = app.work_item_inbox.start.call_args.args
            self.assertEqual(args[0], folder)
            self.assertEqual(args[1], workbook)
            self.assertIsNone(args[2])
            self.assertEqual(args[3].text, text.strip())
            self.assertEqual(args[3].link, "https://example.com/report")
            app.workspace_component.selected_or_full_text.assert_not_called()
            app.workspace_component.set_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
