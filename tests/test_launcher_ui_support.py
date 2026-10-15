"""Lifecycle and effect boundaries of the disposable launcher fixture."""
import gc
from http.client import HTTPConnection
from pathlib import Path
import subprocess
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from context_palette import launcher as launcher_module
from context_palette.actions import Action
from context_palette.excel_automation import PythonExcelProcessClient
from tests.support.launcher_ui import disposable_launcher


@unittest.skipUnless(sys.platform == "win32", "Requires Windows Tk.")
class LauncherUiSupportTests(unittest.TestCase):
    def setUp(self):
        gc.collect()
        self.real_tk = tk.Tk
        self.original_default_root = tk._default_root
        self.roots = []
        self.effect_targets = (
            (launcher_module.SingleInstanceServer, "start"),
            (launcher_module.SingleInstanceServer, "stop"),
            (launcher_module.GlobalHotkey, "start"),
            (launcher_module.GlobalHotkey, "stop"),
            (launcher_module.DropTargetWindow, "start"),
            (launcher_module.LauncherApp, "_start_work_item_refresh"),
            (launcher_module, "open_action_target"),
            (launcher_module, "execute_action"),
            (subprocess, "Popen"),
            (PythonExcelProcessClient, "call"),
            (HTTPConnection, "request"),
        )
        self.original_effects = tuple(getattr(owner, name) for owner, name in self.effect_targets)

    def _create_observed_root(self):
        root = self.real_tk()
        observation = {
            "root": root,
            "original_scaling": float(root.tk.call("tk", "scaling")),
        }
        self.roots.append(observation)
        destroy = root.destroy

        def observe_destroy():
            try:
                observation["scaling_at_destroy"] = float(root.tk.call("tk", "scaling"))
                observation["callbacks_at_destroy"] = root.tk.splitlist(root.tk.call("after", "info"))
                observation["effects_guarded_at_destroy"] = all(
                    isinstance(getattr(owner, name), Mock) for owner, name in self.effect_targets
                )
            finally:
                destroy()

        root.destroy = observe_destroy
        return root

    def _assert_cleaned_up(self, data, *, effects_guarded=True):
        self.assertEqual(len(self.roots), 1)
        observation = self.roots[0]
        self.assertEqual(observation["callbacks_at_destroy"], ())
        self.assertAlmostEqual(observation["scaling_at_destroy"], observation["original_scaling"], places=5)
        self.assertEqual(observation["effects_guarded_at_destroy"], effects_guarded)
        self.assertIs(tk._default_root, self.original_default_root)
        with self.assertRaises(tk.TclError):
            observation["root"].winfo_exists()
        self.assertIs(observation["root"].clipboard_get.__func__, tk.Misc.clipboard_get)
        self.assertIs(observation["root"].clipboard_clear.__func__, tk.Misc.clipboard_clear)
        self.assertIs(observation["root"].clipboard_append.__func__, tk.Misc.clipboard_append)
        for (owner, name), original in zip(self.effect_targets, self.original_effects):
            self.assertIs(getattr(owner, name), original)
        self.assertFalse(data.exists())

    def test_body_failure_cleans_callbacks_scaling_root_and_patches(self):
        with patch("tests.support.launcher_ui.tk.Tk", side_effect=self._create_observed_root):
            with self.assertRaisesRegex(RuntimeError, "fixture body failed"):
                with disposable_launcher(scaling=2) as (app, *_):
                    data = app.actions_path.parent
                    app.root.after(60_000, Mock())
                    app.root.tk.call("tk", "scaling", 3)
                    raise RuntimeError("fixture body failed")
        self._assert_cleaned_up(data)

    def test_constructor_failure_cleans_callbacks_scaling_root_and_patches(self):
        def fail_constructor(root, actions_path, *args, **kwargs):
            self.data = Path(actions_path).parent
            root.after(60_000, Mock())
            root.tk.call("tk", "scaling", 3)
            raise RuntimeError("fixture constructor failed")

        with patch("tests.support.launcher_ui.tk.Tk", side_effect=self._create_observed_root), \
                patch("tests.support.launcher_ui.LauncherApp", side_effect=fail_constructor):
            with self.assertRaisesRegex(RuntimeError, "fixture constructor failed"):
                with disposable_launcher(scaling=2):
                    self.fail("Failed construction must not yield a launcher")
        self._assert_cleaned_up(self.data)

    def test_patch_setup_failure_restores_scaling_and_destroys_root(self):
        patch_object = patch.object
        temporary_directory = tempfile.TemporaryDirectory
        data_directories = []

        def create_temporary_directory():
            temporary = temporary_directory()
            data_directories.append(Path(temporary.name))
            return temporary

        def fail_clipboard_patch(root, name, **kwargs):
            if name == "clipboard_clear":
                raise RuntimeError("fixture patch setup failed")
            return patch_object(root, name, **kwargs)

        with patch("tests.support.launcher_ui.tk.Tk", side_effect=self._create_observed_root), \
                patch("tests.support.launcher_ui.patch.object", side_effect=fail_clipboard_patch), \
                patch("tests.support.launcher_ui.tempfile.TemporaryDirectory", side_effect=create_temporary_directory), \
                patch("tests.support.launcher_ui.LauncherApp") as constructor:
            with self.assertRaisesRegex(RuntimeError, "fixture patch setup failed"):
                with disposable_launcher(scaling=2):
                    self.fail("Failed setup must not yield a launcher")
            constructor.assert_not_called()
        self.assertEqual(len(data_directories), 1)
        self._assert_cleaned_up(data_directories[0], effects_guarded=False)

    def test_clipboard_and_platform_effects_remain_isolated(self):
        excel_client = PythonExcelProcessClient()
        with patch("tests.support.launcher_ui.tk.Tk", side_effect=self._create_observed_root):
            with disposable_launcher() as (app, get, clear, append):
                data = app.actions_path.parent
                self.assertEqual([action.id for action in app.actions], ["sample"])
                self.assertIsNone(app.native_excel_availability)
                self.assertEqual(app.root.attributes("-alpha"), 0)
                for owner, name in self.effect_targets:
                    self.assertIsInstance(getattr(owner, name), Mock)
                self.assertIs(app.root.clipboard_get, get)
                self.assertIs(app.root.clipboard_clear, clear)
                self.assertIs(app.root.clipboard_append, append)
                self.assertEqual(app.root.clipboard_get(), "Clipboard fixture")
                app.root.clipboard_clear()
                app.root.clipboard_append("Fictional result")
                clear.assert_called_once_with()
                append.assert_called_once_with("Fictional result")
                action = Action("fictional", "Fictional target", "", "open_url", "https://example.invalid")
                with self.assertRaisesRegex(AssertionError, "must not open targets"):
                    launcher_module.open_action_target(action)
                with self.assertRaisesRegex(AssertionError, "must not execute Actions"):
                    launcher_module.execute_action(action)
                with self.assertRaisesRegex(AssertionError, "must not launch subprocesses"):
                    subprocess.Popen(["fictional-command"])
                with self.assertRaisesRegex(AssertionError, "must not call Python Excel"):
                    excel_client.call(
                        data / "fictional-excel.bat", {}, phase="describe", timeout_seconds=1,
                    )
                with self.assertRaisesRegex(AssertionError, "must not send HTTP requests"):
                    HTTPConnection("example.invalid").request("GET", "/")
        self._assert_cleaned_up(data)


if __name__ == "__main__":
    unittest.main()
