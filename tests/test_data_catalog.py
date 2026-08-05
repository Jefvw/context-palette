from dataclasses import FrozenInstanceError
from pathlib import Path, PurePosixPath
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.data_catalog import (
    DATA_ASSET_CATALOG,
    AppDataPaths,
    AssetOwnership,
    AssetRequirement,
    AssetSensitivity,
    BackupPolicy,
    DataAssetSpec,
    asset_spec_by_id,
    asset_spec_for_path,
    is_catalogued_backup_payload,
)


EXPECTED_ASSETS = {
    "built-in-actions": (
        "data/actions.json",
        AssetOwnership.BUILT_IN,
        AssetRequirement.REQUIRED,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.COMPLETE_CONFIGURATION_ADDITION,
        1,
    ),
    "built-in-contexts": (
        "data/contexts.json",
        AssetOwnership.BUILT_IN,
        AssetRequirement.REQUIRED,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.COMPLETE_CONFIGURATION_ADDITION,
        1,
    ),
    "built-in-command-surface": (
        "data/command_surface.json",
        AssetOwnership.BUILT_IN,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.COMPLETE_CONFIGURATION_ADDITION,
        1,
    ),
    "built-in-cheat-sheets": (
        "data/cheatsheets/*.json",
        AssetOwnership.BUILT_IN,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.COMPLETE_CONFIGURATION_ADDITION,
        1,
    ),
    "personal-actions": (
        "data/local_actions.json",
        AssetOwnership.PERSONAL,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.CORE_CONFIGURATION,
        1,
    ),
    "personal-contexts": (
        "data/local_contexts.json",
        AssetOwnership.PERSONAL,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.CORE_CONFIGURATION,
        1,
    ),
    "personal-command-surface": (
        "data/local_command_surface.json",
        AssetOwnership.PERSONAL,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.CORE_CONFIGURATION,
        1,
    ),
    "palette-state": (
        "data/palette.json",
        AssetOwnership.MACHINE_LOCAL,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.CORE_CONFIGURATION,
        1,
    ),
    "work-item-sources": (
        "data/local_work_item_sources.json",
        AssetOwnership.MACHINE_LOCAL,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.PRIVATE_PATHS,
        BackupPolicy.CORE_CONFIGURATION,
        1,
    ),
    "work-item-metadata": (
        "data/local_work_item_metadata.json",
        AssetOwnership.PERSONAL,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CONFIGURATION,
        BackupPolicy.CORE_CONFIGURATION,
        1,
    ),
    "work-item-settings": (
        "data/local_work_item_settings.json",
        AssetOwnership.MACHINE_LOCAL,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.PRIVATE_PATHS,
        BackupPolicy.CORE_CONFIGURATION,
        1,
    ),
    "inbox": (
        "data/inbox.json",
        AssetOwnership.CAPTURED_CONTENT,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CAPTURED_CONTENT,
        BackupPolicy.COMPLETE_CONFIGURATION_ADDITION,
        1,
    ),
    "managed-text-action-source": (
        "data/local_text_action_source.txt",
        AssetOwnership.CAPTURED_CONTENT,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.CAPTURED_CONTENT,
        BackupPolicy.OPTIONAL_MANAGED_CONTENT,
        None,
    ),
    "diagnostic-logs": (
        "data/context-palette.log*",
        AssetOwnership.DERIVED_RUNTIME,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.DIAGNOSTICS,
        BackupPolicy.EXCLUDED,
        None,
    ),
    "restore-journal": (
        "data/restore-journal.json",
        AssetOwnership.DERIVED_RUNTIME,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.PRIVATE_RUNTIME_DATA,
        BackupPolicy.EXCLUDED,
        None,
    ),
    "recovery-backups": (
        "data/*.bak",
        AssetOwnership.DERIVED_RUNTIME,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.PRIVATE_RUNTIME_DATA,
        BackupPolicy.EXCLUDED,
        None,
    ),
    "temporary-data-files": (
        "data/*.tmp",
        AssetOwnership.DERIVED_RUNTIME,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.PRIVATE_RUNTIME_DATA,
        BackupPolicy.EXCLUDED,
        None,
    ),
    "python-environment": (
        ".venv",
        AssetOwnership.DERIVED_RUNTIME,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.PRIVATE_RUNTIME_DATA,
        BackupPolicy.EXCLUDED,
        None,
    ),
    "preserved-python-environments": (
        ".venv-*",
        AssetOwnership.DERIVED_RUNTIME,
        AssetRequirement.OPTIONAL,
        AssetSensitivity.PRIVATE_RUNTIME_DATA,
        BackupPolicy.EXCLUDED,
        None,
    ),
}


class AppDataPathsTests(unittest.TestCase):
    def test_paths_are_deterministic_for_an_arbitrary_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "portable-copy"
            paths = AppDataPaths.from_root(root)

        self.assertEqual(paths.application_root, root)
        self.assertEqual(paths.data_directory, root / "data")
        self.assertEqual(paths.built_in_actions_file, root / "data" / "actions.json")
        self.assertEqual(paths.personal_actions_file, root / "data" / "local_actions.json")
        self.assertEqual(paths.built_in_contexts_file, root / "data" / "contexts.json")
        self.assertEqual(paths.personal_contexts_file, root / "data" / "local_contexts.json")
        self.assertEqual(
            paths.built_in_command_surface_file,
            root / "data" / "command_surface.json",
        )
        self.assertEqual(
            paths.personal_command_surface_file,
            root / "data" / "local_command_surface.json",
        )
        self.assertEqual(paths.palette_state_file, root / "data" / "palette.json")
        self.assertEqual(paths.inbox_file, root / "data" / "inbox.json")
        self.assertEqual(paths.cheat_sheets_directory, root / "data" / "cheatsheets")
        self.assertEqual(
            paths.work_item_sources_file,
            root / "data" / "local_work_item_sources.json",
        )
        self.assertEqual(
            paths.work_item_metadata_file,
            root / "data" / "local_work_item_metadata.json",
        )
        self.assertEqual(
            paths.work_item_settings_file,
            root / "data" / "local_work_item_settings.json",
        )
        self.assertEqual(
            paths.managed_text_action_source_file,
            root / "data" / "local_text_action_source.txt",
        )
        self.assertEqual(
            paths.diagnostic_log_file,
            root / "data" / "context-palette.log",
        )
        self.assertEqual(
            paths.restore_journal_file,
            root / "data" / "restore-journal.json",
        )

    def test_data_directory_constructor_preserves_compatibility_location(self):
        data = Path("custom") / "state"

        paths = AppDataPaths.from_data_directory(data)

        self.assertEqual(paths.data_directory, data)
        self.assertEqual(paths.application_root, data.parent)
        self.assertEqual(paths.work_item_sources_file, data / "local_work_item_sources.json")

        personal_actions = next(
            spec
            for spec in DATA_ASSET_CATALOG
            if spec.asset_id == "personal-actions"
        )
        environment = next(
            spec
            for spec in DATA_ASSET_CATALOG
            if spec.asset_id == "python-environment"
        )
        self.assertEqual(personal_actions.path_for(paths), paths.personal_actions_file)
        self.assertEqual(environment.path_for(paths), data.parent / ".venv")

    def test_paths_model_is_immutable(self):
        paths = AppDataPaths.from_root(Path("portable"))

        with self.assertRaises(FrozenInstanceError):
            paths.data_directory = Path("elsewhere")


class DataAssetCatalogTests(unittest.TestCase):
    def test_inventory_and_policy_match_the_documented_data_model(self):
        actual = {}
        for spec in DATA_ASSET_CATALOG:
            location = str(spec.relative_path or spec.relative_pattern)
            actual[spec.asset_id] = (
                location,
                spec.ownership,
                spec.requirement,
                spec.sensitivity,
                spec.backup_policy,
                spec.schema_version,
            )

        self.assertEqual(actual, EXPECTED_ASSETS)

    def test_asset_ids_and_fixed_paths_are_unique(self):
        asset_ids = [spec.asset_id for spec in DATA_ASSET_CATALOG]
        fixed_paths = [
            spec.relative_path
            for spec in DATA_ASSET_CATALOG
            if spec.relative_path is not None
        ]

        self.assertEqual(len(asset_ids), len(set(asset_ids)))
        self.assertEqual(len(fixed_paths), len(set(fixed_paths)))

    def test_stable_asset_lookup_uses_the_catalog(self):
        self.assertEqual(
            asset_spec_by_id("work-item-metadata").relative_path,
            PurePosixPath("data/local_work_item_metadata.json"),
        )
        with self.assertRaises(KeyError):
            asset_spec_by_id("not-catalogued")

    def test_catalog_locations_cannot_escape_the_application_root(self):
        paths = AppDataPaths.from_root(Path("C:/portable/context-palette"))
        for spec in DATA_ASSET_CATALOG:
            location = spec.relative_path or PurePosixPath(spec.relative_pattern or "")
            self.assertFalse(location.is_absolute())
            self.assertNotIn("..", location.parts)
            if spec.relative_path is not None:
                self.assertTrue(spec.path_for(paths).is_relative_to(paths.application_root))

        common = dict(
            asset_id="escape",
            ownership=AssetOwnership.DERIVED_RUNTIME,
            requirement=AssetRequirement.OPTIONAL,
            sensitivity=AssetSensitivity.PRIVATE_RUNTIME_DATA,
            backup_policy=BackupPolicy.EXCLUDED,
        )
        with self.assertRaises(ValueError):
            DataAssetSpec(**common, relative_path=PurePosixPath("../secret.json"))
        with self.assertRaises(ValueError):
            DataAssetSpec(**common, relative_pattern="data/**/secret.json")
        with self.assertRaises(ValueError):
            DataAssetSpec(
                **common,
                relative_path=PurePosixPath("C:/external/secret.json"),
            )
        with self.assertRaises(ValueError):
            DataAssetSpec(
                **common,
                relative_path=PurePosixPath(r"..\external\secret.json"),
            )
        with self.assertRaises(ValueError):
            DataAssetSpec(
                **common,
                relative_path=PurePosixPath("data/invalid.json"),
                schema_version=True,
            )

    def test_personal_and_runtime_assets_are_never_built_in_portable_data(self):
        for spec in DATA_ASSET_CATALOG:
            if spec.ownership in {
                AssetOwnership.PERSONAL,
                AssetOwnership.MACHINE_LOCAL,
                AssetOwnership.CAPTURED_CONTENT,
                AssetOwnership.DERIVED_RUNTIME,
            }:
                self.assertIsNot(spec.ownership, AssetOwnership.BUILT_IN)
                if spec.asset_id != "inbox":
                    self.assertNotEqual(
                        spec.backup_policy,
                        BackupPolicy.COMPLETE_CONFIGURATION_ADDITION,
                        msg=spec.asset_id,
                    )

    def test_only_explicit_catalogued_payloads_are_eligible(self):
        eligible = (
            "data/actions.json",
            "data/local_actions.json",
            "data/palette.json",
            "data/inbox.json",
            "data/local_text_action_source.txt",
            "data/cheatsheets/win11.json",
        )
        excluded_or_external = (
            "data/context-palette.log",
            "data/context-palette.log.1",
            "data/restore-journal.json",
            "data/actions.json.bak",
            "data/.actions.json.temporary.tmp",
            ".venv",
            ".venv-unusable-20260804",
            "__pycache__/module.pyc",
            ".git/config",
            "data/unknown.json",
            "data/cheatsheets/private/nested.json",
            "C:/external/workitems/ISS-1/ISS-1.xlsx",
            "../external-template.xlsx",
        )

        for path in eligible:
            self.assertTrue(is_catalogued_backup_payload(path), msg=path)
        for path in excluded_or_external:
            self.assertFalse(is_catalogued_backup_payload(path), msg=path)

        self.assertEqual(
            asset_spec_for_path("data/context-palette.log.2").backup_policy,
            BackupPolicy.EXCLUDED,
        )

    def test_catalog_patterns_are_anchored_to_the_application_root(self):
        prefixed_paths = (
            "other/data/cheatsheets/win11.json",
            "other/data/context-palette.log.1",
            "other/data/actions.json.bak",
            "other/.venv-unusable",
        )

        for path in prefixed_paths:
            self.assertIsNone(asset_spec_for_path(path), msg=path)
            self.assertFalse(is_catalogued_backup_payload(path), msg=path)


if __name__ == "__main__":
    unittest.main()
