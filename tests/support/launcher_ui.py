"""Disposable real-Tk launcher helpers with fictional data and isolated effects."""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import json
from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch

from context_palette.launcher import LauncherApp


@contextmanager
def disposable_launcher(*, scaling: float = 4 / 3, size: str = "780x600"):
    """Yield a launcher and mocked clipboard in one owned, temporary Tk root."""
    with tempfile.TemporaryDirectory() as temporary_directory, ExitStack() as stack:
        data = Path(temporary_directory)
        payloads = {
            "actions.json": {"actions": [
                {"id": "sample", "title": "Sample text", "context": "",
                 "type": "copy_text", "value": "Sample result"},
            ]},
            "contexts.json": {"contexts": []},
            "command_surface.json": {"groups": []},
        }
        for filename, payload in payloads.items():
            (data / filename).write_text(json.dumps(payload), encoding="utf-8")
        (data / "cheatsheets").mkdir()
        root = tk.Tk()
        original_scaling = None
        try:
            root.withdraw()
            # Show now follows the pointer; keep disposable test windows
            # invisible even when placement moves them back onto a monitor.
            root.attributes("-alpha", 0)
            original_scaling = float(root.tk.call("tk", "scaling"))
            root.tk.call("tk", "scaling", scaling)
            clipboard_get = stack.enter_context(patch.object(root, "clipboard_get", return_value="Clipboard fixture"))
            clipboard_clear = stack.enter_context(patch.object(root, "clipboard_clear"))
            clipboard_append = stack.enter_context(patch.object(root, "clipboard_append"))
            for target, options in (
                ("SingleInstanceServer.start", {"return_value": True}),
                ("SingleInstanceServer.stop", {}),
                ("GlobalHotkey.start", {"return_value": False}),
                ("GlobalHotkey.stop", {}),
                ("DropTargetWindow.start", {"return_value": True}),
                ("LauncherApp._start_work_item_refresh", {}),
                ("open_action_target", {"side_effect": AssertionError("UI smoke must not open targets")}),
                ("execute_action", {"side_effect": AssertionError("UI smoke must not execute Actions")}),
            ):
                stack.enter_context(patch(f"context_palette.launcher.{target}", **options))
            stack.enter_context(patch(
                "subprocess.Popen",
                side_effect=AssertionError("UI smoke must not launch subprocesses"),
            ))
            # The Excel client captures Popen in its constructor default.
            stack.enter_context(patch(
                "context_palette.excel_automation.PythonExcelProcessClient.call",
                side_effect=AssertionError("UI smoke must not call Python Excel"),
            ))
            stack.enter_context(patch(
                "http.client.HTTPConnection.request",
                side_effect=AssertionError("UI smoke must not send HTTP requests"),
            ))
            app = LauncherApp(
                root, data / "actions.json", data / "local_actions.json",
                data / "contexts.json", data / "local_contexts.json",
                data / "command_surface.json", data / "local_command_surface.json",
                data / "palette.json", data / "inbox.json", data / "cheatsheets",
                instance_port=0,
            )
            root.geometry(f"{size}+-32000+-32000")
            root.deiconify()
            root.update()
            app._set_initial_main_split()
            root.update_idletasks()
            yield app, clipboard_get, clipboard_clear, clipboard_append
        finally:
            try:
                # Polling and tooltip timers belong to this interpreter only.
                for callback in root.tk.splitlist(root.tk.call("after", "info")):
                    root.tk.call("after", "cancel", callback)
            finally:
                try:
                    # Scaling is shared between Tk interpreters in this process.
                    if original_scaling is not None:
                        root.tk.call("tk", "scaling", original_scaling)
                finally:
                    root.destroy()


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def assert_control_fits(test_case, control, container) -> None:
    test_case.assertTrue(control.winfo_ismapped(), str(control))
    test_case.assertGreaterEqual(control.winfo_width() + 1, control.winfo_reqwidth(), str(control))
    test_case.assertGreaterEqual(control.winfo_height() + 1, control.winfo_reqheight(), str(control))
    test_case.assertGreaterEqual(control.winfo_rootx(), container.winfo_rootx(), str(control))
    test_case.assertGreaterEqual(control.winfo_rooty(), container.winfo_rooty(), str(control))
    test_case.assertLessEqual(
        control.winfo_rootx() + control.winfo_width(),
        container.winfo_rootx() + container.winfo_width(), str(control),
    )
    test_case.assertLessEqual(
        control.winfo_rooty() + control.winfo_height(),
        container.winfo_rooty() + container.winfo_height(), str(control),
    )
