from pathlib import Path
import os
import sys
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import context_palette.main as main_module
from context_palette.data_catalog import AppDataPaths
from context_palette.main import initial_launcher_request
from context_palette.restore import RestoreRecoveryError


class MainTests(unittest.TestCase):
    def test_bare_first_launch_does_not_replay_show_request(self):
        self.assertIsNone(initial_launcher_request({"command": "show"}))

    def test_first_launch_preserves_integration_parameters(self):
        request = {"command": "show", "context": "Archives", "search": "product"}

        self.assertIs(initial_launcher_request(request), request)

    def test_main_constructs_and_passes_the_canonical_data_paths(self):
        root = Path("C:/portable/context-palette")
        paths = AppDataPaths.from_root(root)
        cleanup_report = Mock(files_changed=0)
        logger = Mock()
        with (
            patch.dict(os.environ, {"PROJECT_ROOT": str(root)}),
            patch.object(main_module, "project_root", return_value=root),
            patch.object(
                main_module,
                "configure_logging",
                return_value=logger,
            ) as configure_logging,
            patch.object(
                main_module,
                "recover_interrupted_restore",
                return_value=Mock(recovery_performed=False),
            ) as recover,
            patch.object(
                main_module,
                "cleanup_retired_local_configuration",
                return_value=cleanup_report,
            ),
            patch.object(
                main_module,
                "notify_existing_instance",
                return_value=False,
            ),
            patch.object(main_module, "run") as run,
        ):
            main_module.main([])

        configure_logging.assert_called_once_with(paths.diagnostic_log_file)
        recover.assert_called_once_with(paths)
        run.assert_called_once_with(
            paths.built_in_actions_file,
            paths.personal_actions_file,
            paths.built_in_contexts_file,
            paths.personal_contexts_file,
            paths.built_in_command_surface_file,
            paths.personal_command_surface_file,
            paths.palette_state_file,
            paths.inbox_file,
            paths.cheat_sheets_directory,
            main_module.project_port(root),
            None,
            data_paths=paths,
        )

    def test_main_stops_before_cleanup_when_interrupted_restore_recovery_fails(self):
        root = Path("C:/portable/context-palette")
        logger = Mock()
        with (
            patch.object(main_module, "project_root", return_value=root),
            patch.object(main_module, "configure_logging", return_value=logger),
            patch.object(main_module, "notify_existing_instance", return_value=False),
            patch.object(
                main_module,
                "recover_interrupted_restore",
                side_effect=RestoreRecoveryError("privacy-safe"),
            ),
            patch.object(main_module, "cleanup_retired_local_configuration") as cleanup,
            patch.object(main_module, "run") as run,
        ):
            with self.assertRaises(SystemExit):
                main_module.main([])

        cleanup.assert_not_called()
        run.assert_not_called()

    def test_existing_instance_is_not_mistaken_for_an_interrupted_restore(self):
        root = Path("C:/portable/context-palette")
        with (
            patch.object(main_module, "project_root", return_value=root),
            patch.object(main_module, "configure_logging", return_value=Mock()),
            patch.object(main_module, "notify_existing_instance", return_value=True),
            patch.object(main_module, "recover_interrupted_restore") as recover,
            patch.object(main_module, "cleanup_retired_local_configuration") as cleanup,
            patch.object(main_module, "run") as run,
        ):
            main_module.main([])

        recover.assert_not_called()
        cleanup.assert_not_called()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
