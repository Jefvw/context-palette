from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.diagnostics import configure_logging
from context_palette.launcher import LauncherApp, _warn_if_slow


class FakeRoot:
    def __init__(self) -> None:
        self.after_callbacks: dict[str, object] = {}
        self.cancelled: list[str] = []
        self.configurations: list[dict[str, str]] = []

    def after(self, _delay: int, callback):
        identifier = f"after-{len(self.after_callbacks) + 1}"
        self.after_callbacks[identifier] = callback
        return identifier

    def after_cancel(self, identifier: str) -> None:
        self.cancelled.append(identifier)

    def configure(self, **options: str) -> None:
        self.configurations.append(options)

    def update_idletasks(self) -> None:
        pass


class FakeVariable:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class PerformanceLifecycleTests(unittest.TestCase):
    def test_slow_operation_warning_contains_only_safe_metrics(self):
        with (
            patch("context_palette.launcher.time.perf_counter", return_value=1.2),
            patch("context_palette.launcher.LOGGER.warning") as warning,
        ):
            _warn_if_slow("result refresh", 1.0, 0.1, action_count=31)

        warning.assert_called_once()
        self.assertEqual(warning.call_args.args[1], "result refresh")
        self.assertAlmostEqual(warning.call_args.args[2], 200.0)
        self.assertEqual(warning.call_args.args[3], 31)

    def test_fast_operation_does_not_write_performance_warning(self):
        with (
            patch("context_palette.launcher.time.perf_counter", return_value=1.05),
            patch("context_palette.launcher.LOGGER.warning") as warning,
        ):
            _warn_if_slow("result refresh", 1.0, 0.1, action_count=31)

        warning.assert_not_called()

    def test_unchanged_configuration_skips_full_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / f"config-{index}.json" for index in range(7)]
            for path in paths:
                path.write_text("{}", encoding="utf-8")
            app = LauncherApp.__new__(LauncherApp)
            (
                app.actions_path,
                app.local_actions_path,
                app.contexts_path,
                app.local_contexts_path,
                app.command_surface_path,
                app.local_command_surface_path,
                app.palette_path,
            ) = paths
            app.configuration_signature_cache = app._configuration_signature()
            reloads: list[bool] = []
            app._reload = lambda: reloads.append(True)

            app._reload_if_changed()
            paths[0].write_text('{"changed": true}', encoding="utf-8")
            app._reload_if_changed()

            self.assertEqual(reloads, [True])

    def test_search_refresh_coalesces_repeated_changes(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = FakeRoot()
        app.search_refresh_after_id = None

        app._schedule_refresh_results()
        first_identifier = app.search_refresh_after_id
        app._schedule_refresh_results()

        self.assertEqual(app.root.cancelled, [first_identifier])
        self.assertEqual(len(app.root.after_callbacks), 2)

    def test_coordinated_reload_renders_quick_actions_once_after_state_load(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = FakeRoot()
        app.status_var = FakeVariable()
        app.actions = []
        events: list[object] = []
        app._load_actions = lambda: events.append("actions")
        app._load_command_surface = (
            lambda *, render=True: events.append(("commands", render))
        )
        app._load_contexts = lambda: events.append("contexts")
        app._load_palette_state = (
            lambda *, render=True: events.append(("palette", render))
        )
        app._render_command_surface = lambda: events.append("surface")
        app._refresh_results = lambda: events.append("results")
        app._configuration_signature = lambda: ()

        app._reload()

        self.assertEqual(
            events,
            [
                "actions",
                ("commands", False),
                "contexts",
                ("palette", False),
                "surface",
                "results",
            ],
        )

    def test_diagnostic_log_is_rotating_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = logging.getLogger("context_palette")
            old_handlers = list(logger.handlers)
            logger.handlers.clear()
            try:
                configured = configure_logging(Path(directory) / "context-palette.log")
                handler = next(
                    item for item in configured.handlers if isinstance(item, RotatingFileHandler)
                )
                self.assertEqual(handler.maxBytes, 512 * 1024)
                self.assertEqual(handler.backupCount, 2)
            finally:
                for handler in logger.handlers:
                    handler.close()
                logger.handlers[:] = old_handlers


if __name__ == "__main__":
    unittest.main()
