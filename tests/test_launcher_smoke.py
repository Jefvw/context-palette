from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.launcher import LauncherApp


@unittest.skipUnless(sys.platform == "win32", "The launcher smoke test requires Windows Tk.")
class LauncherSmokeTests(unittest.TestCase):
    def test_complete_launcher_constructs_and_closes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            data = Path(temporary_directory)
            actions_path = self._write_json(data / "actions.json", {"actions": []})
            contexts_path = self._write_json(data / "contexts.json", {"contexts": []})
            command_surface_path = self._write_json(
                data / "command_surface.json",
                {"groups": []},
            )
            palette_path = self._write_json(data / "palette.json", {})
            inbox_path = self._write_json(data / "inbox.json", {"items": []})
            cheatsheets_dir = data / "cheatsheets"
            cheatsheets_dir.mkdir()

            root = tk.Tk()
            root_destroyed = False
            try:
                with (
                    patch(
                        "context_palette.launcher.SingleInstanceServer.start",
                        return_value=True,
                    ) as start_server,
                    patch(
                        "context_palette.launcher.SingleInstanceServer.stop"
                    ) as stop_server,
                    patch(
                        "context_palette.launcher.GlobalHotkey.start",
                        return_value=False,
                    ) as start_hotkey,
                    patch("context_palette.launcher.GlobalHotkey.stop") as stop_hotkey,
                ):
                    app = LauncherApp(
                        root,
                        actions_path,
                        data / "local_actions.json",
                        contexts_path,
                        data / "local_contexts.json",
                        command_surface_path,
                        data / "local_command_surface.json",
                        palette_path,
                        inbox_path,
                        cheatsheets_dir,
                        instance_port=0,
                    )

                    root.update_idletasks()

                    self.assertEqual(root.title(), "Context Palette")
                    self.assertTrue(root.winfo_exists())
                    self.assertIsNotNone(app.search_entry)
                    start_server.assert_called_once_with()
                    start_hotkey.assert_called_once_with()

                    stable_tooltip_count = len(app.widget_tooltips)
                    surface_tooltip_count = len(app.command_surface_tooltips)
                    for _index in range(5):
                        app._render_command_surface()
                    root.update_idletasks()
                    self.assertEqual(len(app.widget_tooltips), stable_tooltip_count)
                    self.assertEqual(
                        len(app.command_surface_tooltips),
                        surface_tooltip_count,
                    )

                    app._show_configuration()
                    root.update_idletasks()
                    configuration_windows = [
                        child
                        for child in root.winfo_children()
                        if isinstance(child, tk.Toplevel)
                        and child.title() == "Configure Context Palette"
                    ]
                    self.assertEqual(len(configuration_windows), 1)
                    configuration_windows[0].destroy()

                    app.quit_app()
                    root_destroyed = True

                    stop_hotkey.assert_called_once_with()
                    stop_server.assert_called_once_with()
            finally:
                if not root_destroyed:
                    root.destroy()

    def _write_json(self, path: Path, value: object) -> Path:
        path.write_text(json.dumps(value), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
