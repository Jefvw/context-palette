from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.configuration_check import (
    format_configuration_report,
    validate_project_configuration,
)
from context_palette.configuration_snapshot import (
    ConfigurationSnapshot,
    ValidationCategory,
    ValidationIssueCode,
    ValidationSeverity,
    load_configuration_snapshot,
)
from context_palette.data_catalog import AppDataPaths, asset_spec_by_id


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def action(
    action_id: str,
    *,
    state: str = "Active",
    action_type: str = "copy_text",
    value: str = "safe text",
    arguments: list[str] | None = None,
    working_directory: str | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "id": action_id,
        "title": action_id,
        "type": action_type,
        "value": value,
        "state": state,
    }
    if arguments is not None:
        result["arguments"] = arguments
    if working_directory is not None:
        result["working_directory"] = working_directory
    return result


def write_required_project(
    root: Path,
    *,
    built_in_actions: list[dict[str, object]] | None = None,
    contexts: list[dict[str, object]] | None = None,
) -> AppDataPaths:
    paths = AppDataPaths.from_root(root)
    write_json(
        paths.built_in_actions_file,
        {"actions": built_in_actions or [action("built-in-active")]},
    )
    write_json(
        paths.built_in_contexts_file,
        {
            "contexts": contexts
            if contexts is not None
            else [
                {
                    "name": "Mail",
                    "action_ids": ["built-in-active"],
                    "preferred_action_ids": ["built-in-active"],
                }
            ]
        },
    )
    return paths


def write_complete_project(root: Path) -> AppDataPaths:
    paths = write_required_project(
        root,
        built_in_actions=[
            action("built-in-active"),
            action("built-in-archived", state="Archived"),
        ],
    )
    write_json(
        paths.personal_actions_file,
        {"actions": [action("personal-active")]},
    )
    write_json(
        paths.personal_contexts_file,
        {
            "contexts": [
                {
                    "name": "Personal",
                    "action_ids": ["personal-active"],
                    "preferred_action_ids": ["personal-active"],
                }
            ]
        },
    )
    write_json(
        paths.built_in_command_surface_file,
        {
            "groups": [
                {
                    "id": "built-in",
                    "label": "Built-in",
                    "items": [
                        {
                            "id": "run-built-in",
                            "label": "Run",
                            "targets": [
                                {"type": "action", "action_id": "built-in-active"}
                            ],
                        }
                    ],
                }
            ]
        },
    )
    write_json(
        paths.personal_command_surface_file,
        {
            "groups": [
                {
                    "id": "personal",
                    "label": "Personal",
                    "items": [
                        {
                            "id": "mixed",
                            "label": "Mixed",
                            "targets": [
                                {"type": "action", "action_id": "personal-active"},
                                {
                                    "type": "work_item",
                                    "source_id": "source-one",
                                    "relative_folder": "ISS-ONE",
                                },
                            ],
                        }
                    ],
                }
            ]
        },
    )
    write_json(
        paths.palette_state_file,
        {
            "pinned_action_ids": ["built-in-active"],
            "focus_context": "Mail",
            "context_slots": {"Mail": ["built-in-active"]},
            "context_membership_version": 1,
        },
    )
    write_json(
        paths.inbox_file,
        {
            "items": [
                {
                    "id": "inbox-one",
                    "title": "Private title",
                    "content": "Private content",
                    "source": "clipboard",
                    "created_at": "2026-08-04T12:00:00+00:00",
                    "state": "Inbox",
                    "suggested_context": "Mail",
                }
            ]
        },
    )
    write_json(
        paths.cheat_sheets_directory / "one.json",
        {
            "id": "sheet-one",
            "title": "Sheet",
            "kind": "reference",
            "aliases": [],
            "summary": "Summary",
            "updated_at": "2026-08-04",
            "sections": [],
        },
    )
    write_json(
        paths.work_item_sources_file,
        {
            "sources": [
                {
                    "id": "source-one",
                    "name": "Source",
                    "workitems_path": str(root / "disconnected" / "workitems"),
                }
            ]
        },
    )
    write_json(
        paths.work_item_metadata_file,
        {"work_items": {"source-one/ISS-ONE": {"tags": ["urgent"]}}},
    )
    write_json(
        paths.work_item_settings_file,
        {"template_path": str(root / "missing" / "template.xlsx")},
    )
    paths.managed_text_action_source_file.write_text(
        "managed private text",
        encoding="utf-8",
    )
    return paths


def issue_codes(report) -> set[ValidationIssueCode]:
    return {issue.code for issue in report.issues}


class ConfigurationSnapshotTests(unittest.TestCase):
    def test_complete_snapshot_loads_every_structured_asset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = write_complete_project(Path(directory))

            report = load_configuration_snapshot(paths)

        self.assertTrue(report.ok)
        self.assertEqual(
            [item.id for item in report.snapshot.stored_actions],
            ["built-in-active", "built-in-archived", "personal-active"],
        )
        self.assertEqual(
            [item.id for item in report.snapshot.active_actions],
            ["built-in-active", "personal-active"],
        )
        self.assertEqual(report.counts["actions"], 2)
        self.assertEqual(report.counts["stored_actions"], 3)
        self.assertEqual(report.counts["archived_actions"], 1)
        self.assertEqual(report.counts["contexts"], 2)
        self.assertEqual(report.counts["command_groups"], 2)
        self.assertEqual(report.counts["inbox_items"], 1)
        self.assertEqual(report.counts["cheatsheets"], 1)
        self.assertEqual(report.counts["work_item_sources"], 1)
        self.assertEqual(report.counts["work_item_metadata"], 1)
        self.assertEqual(report.counts["work_item_settings"], 1)
        self.assertTrue(report.snapshot.managed_text_content_present)
        self.assertFalse(
            {
                ValidationIssueCode.PALETTE_CONTEXT_CANONICALIZATION,
                ValidationIssueCode.PALETTE_FOCUS_UNKNOWN,
                ValidationIssueCode.PALETTE_SLOT_CONTEXT_UNKNOWN,
                ValidationIssueCode.PALETTE_SLOT_CONTEXT_DUPLICATE,
            }
            & issue_codes(report)
        )
        for asset_id in (
            "built-in-actions",
            "personal-actions",
            "built-in-contexts",
            "personal-contexts",
            "built-in-command-surface",
            "personal-command-surface",
            "palette-state",
            "inbox",
            "built-in-cheat-sheets",
            "work-item-sources",
            "work-item-metadata",
            "work-item-settings",
            "managed-text-action-source",
        ):
            self.assertIn(asset_id, report.snapshot.loaded_asset_ids)

    def test_snapshot_collections_are_defensively_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = load_configuration_snapshot(
                write_complete_project(Path(directory))
            )
            snapshot = report.snapshot

            with self.assertRaises(FrozenInstanceError):
                snapshot.active_actions = ()
            with self.assertRaises(TypeError):
                snapshot.work_item_metadata["new/item"] = object()
            with self.assertRaises(TypeError):
                snapshot.palette_state.context_slots["Mail"] = ()
            with self.assertRaises(TypeError):
                snapshot.logical_schema_versions["inbox"] = 2

            mutable_slots = {"Mail": ["built-in-active"]}
            independent = ConfigurationSnapshot(
                paths=report.snapshot.paths,
                palette_state=report.snapshot.palette_state.__class__(
                    context_slots=mutable_slots
                ),
            )
            mutable_slots["Mail"].append("changed")

        self.assertEqual(
            independent.palette_state.context_slots["Mail"],
            ("built-in-active",),
        )

    def test_missing_optional_assets_use_empty_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = write_required_project(Path(directory), contexts=[])

            report = load_configuration_snapshot(paths)

        self.assertTrue(report.ok)
        self.assertEqual(report.snapshot.personal_actions, ())
        self.assertEqual(report.snapshot.personal_contexts, ())
        self.assertEqual(report.snapshot.command_groups, ())
        self.assertEqual(report.snapshot.inbox_items, ())
        self.assertEqual(report.snapshot.cheat_sheets, ())
        self.assertEqual(report.snapshot.work_item_sources, ())
        self.assertEqual(dict(report.snapshot.work_item_metadata), {})
        self.assertIsNone(report.snapshot.work_item_settings.template_path)
        self.assertFalse(report.snapshot.managed_text_content_present)

    def test_missing_required_assets_are_errors_with_catalog_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = load_configuration_snapshot(
                AppDataPaths.from_root(Path(directory))
            )

        missing = [
            issue
            for issue in report.errors
            if issue.code is ValidationIssueCode.REQUIRED_ASSET_MISSING
        ]
        self.assertFalse(report.ok)
        self.assertFalse(report.restore_ready)
        self.assertEqual(
            {issue.asset_id for issue in missing},
            {"built-in-actions", "built-in-contexts"},
        )

    def test_malformed_asset_does_not_suppress_unrelated_loading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = write_required_project(root)
            paths.built_in_actions_file.write_text("not json", encoding="utf-8")
            write_json(
                paths.inbox_file,
                {
                    "items": [
                        {
                            "id": "one",
                            "title": "title",
                            "content": "content",
                            "source": "clipboard",
                            "created_at": "now",
                            "state": "Inbox",
                            "suggested_context": "",
                        }
                    ]
                },
            )

            report = load_configuration_snapshot(paths)

        self.assertFalse(report.ok)
        self.assertEqual(report.counts["contexts"], 1)
        self.assertEqual(report.counts["inbox_items"], 1)
        self.assertIn(ValidationIssueCode.ASSET_INVALID, issue_codes(report))
        self.assertIn(
            ValidationIssueCode.DEPENDENT_CHECK_SKIPPED,
            issue_codes(report),
        )

    def test_invalid_utf8_is_contained_to_the_affected_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = write_required_project(root)
            paths.built_in_actions_file.write_bytes(b"\xff")
            paths.cheat_sheets_directory.mkdir(parents=True)
            (paths.cheat_sheets_directory / "invalid.json").write_bytes(b"\xff")
            write_json(
                paths.inbox_file,
                {
                    "items": [
                        {
                            "id": "one",
                            "title": "title",
                            "content": "content",
                            "source": "clipboard",
                            "created_at": "now",
                            "state": "Inbox",
                            "suggested_context": "",
                        }
                    ]
                },
            )

            report = load_configuration_snapshot(paths)

        invalid_assets = {
            issue.asset_id
            for issue in report.errors
            if issue.code is ValidationIssueCode.ASSET_INVALID
        }
        self.assertEqual(
            invalid_assets,
            {"built-in-actions", "built-in-cheat-sheets"},
        )
        self.assertEqual(report.counts["contexts"], 1)
        self.assertEqual(report.counts["inbox_items"], 1)

    def test_cheat_sheet_enumeration_failure_is_an_asset_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = write_required_project(Path(directory), contexts=[])
            paths.cheat_sheets_directory.mkdir(parents=True)

            with patch.object(Path, "glob", side_effect=OSError("private path")):
                report = load_configuration_snapshot(paths)

        issue = next(
            issue
            for issue in report.errors
            if issue.asset_id == "built-in-cheat-sheets"
        )
        self.assertEqual(issue.code, ValidationIssueCode.ASSET_INVALID)
        self.assertNotIn("private path", issue.summary)
        self.assertIn(
            "built-in-cheat-sheets",
            report.snapshot.failed_asset_ids,
        )

    def test_invalid_work_item_metadata_and_settings_are_independent_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = write_required_project(root)
            write_json(
                paths.work_item_sources_file,
                {"sources": []},
            )
            write_json(
                paths.work_item_metadata_file,
                {"work_items": {"source/folder": {"tags": [42]}}},
            )
            write_json(
                paths.work_item_settings_file,
                {"template_path": "relative.xlsx"},
            )

            report = load_configuration_snapshot(paths)

        invalid_assets = {
            issue.asset_id
            for issue in report.errors
            if issue.code is ValidationIssueCode.ASSET_INVALID
        }
        self.assertEqual(
            invalid_assets,
            {"work-item-metadata", "work-item-settings"},
        )
        self.assertIn("work-item-sources", report.snapshot.loaded_asset_ids)

    def test_archived_action_id_conflict_across_owners_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = write_required_project(
                root,
                built_in_actions=[action("Conflict", state="Archived")],
                contexts=[],
            )
            write_json(
                paths.personal_actions_file,
                {"actions": [action("conflict", state="Archived")]},
            )

            report = load_configuration_snapshot(paths)

        duplicate = next(
            issue
            for issue in report.errors
            if issue.code is ValidationIssueCode.DUPLICATE_ACTION_ID
        )
        self.assertEqual(duplicate.asset_id, "personal-actions")
        self.assertEqual(len(report.snapshot.stored_actions), 2)
        self.assertEqual(report.snapshot.active_actions, ())

    def test_other_documented_stable_id_conflicts_are_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = write_required_project(
                root,
                contexts=[{"name": "Mail", "action_ids": []}],
            )
            write_json(
                paths.personal_contexts_file,
                {"contexts": [{"name": "MAIL", "action_ids": []}]},
            )
            write_json(
                paths.built_in_command_surface_file,
                {"groups": [{"id": "Group", "label": "One", "items": []}]},
            )
            write_json(
                paths.personal_command_surface_file,
                {"groups": [{"id": "group", "label": "Two", "items": []}]},
            )
            write_json(
                paths.inbox_file,
                {
                    "items": [
                        {
                            "id": inbox_id,
                            "title": "title",
                            "content": "content",
                            "source": "clipboard",
                            "created_at": "now",
                            "state": "Inbox",
                            "suggested_context": "",
                        }
                        for inbox_id in ("Inbox-One", "inbox-one")
                    ]
                },
            )
            for filename, sheet_id in (
                ("one.json", "Sheet-One"),
                ("two.json", "sheet-one"),
            ):
                write_json(
                    paths.cheat_sheets_directory / filename,
                    {
                        "id": sheet_id,
                        "title": filename,
                        "kind": "reference",
                        "aliases": [],
                        "summary": "summary",
                        "updated_at": "now",
                        "sections": [],
                    },
                )

            report = load_configuration_snapshot(paths)

        codes = issue_codes(report)
        self.assertIn(ValidationIssueCode.DUPLICATE_CONTEXT_NAME, codes)
        self.assertIn(ValidationIssueCode.DUPLICATE_COMMAND_GROUP_ID, codes)
        self.assertIn(ValidationIssueCode.DUPLICATE_INBOX_ID, codes)
        self.assertIn(ValidationIssueCode.DUPLICATE_CHEAT_SHEET_ID, codes)

    def test_missing_and_archived_action_references_are_hard_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = write_required_project(
                Path(directory),
                built_in_actions=[
                    action("active"),
                    action("archived", state="Archived"),
                ],
                contexts=[
                    {
                        "name": "Mail",
                        "action_ids": ["active", "archived", "missing"],
                    }
                ],
            )

            report = load_configuration_snapshot(paths)

        self.assertIn(ValidationIssueCode.ACTION_REFERENCE_ARCHIVED, issue_codes(report))
        self.assertIn(ValidationIssueCode.ACTION_REFERENCE_MISSING, issue_codes(report))
        self.assertFalse(report.ok)

    def test_built_in_ownership_boundaries_are_hard_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = write_required_project(
                root,
                contexts=[
                    {"name": "Built", "action_ids": ["personal-active"]}
                ],
            )
            write_json(
                paths.personal_actions_file,
                {"actions": [action("personal-active")]},
            )
            write_json(
                paths.built_in_command_surface_file,
                {
                    "groups": [
                        {
                            "id": "built",
                            "label": "Built",
                            "items": [
                                {
                                    "id": "mixed",
                                    "label": "Mixed",
                                    "targets": [
                                        {
                                            "type": "action",
                                            "action_id": "personal-active",
                                        },
                                        {
                                            "type": "work_item",
                                            "source_id": "source-one",
                                            "relative_folder": "ISS-ONE",
                                        },
                                    ],
                                }
                            ],
                        }
                    ]
                },
            )

            report = load_configuration_snapshot(paths)

        codes = issue_codes(report)
        self.assertIn(ValidationIssueCode.BUILT_IN_CONTEXT_PERSONAL_ACTION, codes)
        self.assertIn(ValidationIssueCode.BUILT_IN_COMMAND_PERSONAL_ACTION, codes)
        self.assertIn(ValidationIssueCode.BUILT_IN_COMMAND_WORK_ITEM, codes)

    def test_work_item_references_and_metadata_use_soft_source_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = write_required_project(Path(directory))
            write_json(
                paths.personal_command_surface_file,
                {
                    "groups": [
                        {
                            "id": "work",
                            "label": "Work",
                            "items": [
                                {
                                    "id": "item",
                                    "label": "Item",
                                    "targets": [
                                        {
                                            "type": "work_item",
                                            "source_id": "missing-source",
                                            "relative_folder": "PRIVATE-FOLDER",
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                },
            )
            write_json(
                paths.work_item_metadata_file,
                {
                    "work_items": {
                        "metadata-source/PRIVATE-FOLDER": {"tags": ["tag"]}
                    }
                },
            )

            report = load_configuration_snapshot(paths)

        self.assertTrue(report.ok)
        codes = issue_codes(report)
        self.assertIn(ValidationIssueCode.WORK_ITEM_SOURCE_UNAVAILABLE, codes)
        self.assertIn(
            ValidationIssueCode.WORK_ITEM_METADATA_SOURCE_UNAVAILABLE,
            codes,
        )
        self.assertTrue(
            all("PRIVATE-FOLDER" not in issue.summary for issue in report.issues)
        )

    def test_disconnected_external_paths_do_not_fail_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = load_configuration_snapshot(
                write_complete_project(Path(directory))
            )

        self.assertTrue(report.ok)
        portability = [
            issue
            for issue in report.warnings
            if issue.category is ValidationCategory.PORTABILITY
        ]
        self.assertTrue(portability)
        self.assertTrue(all("raw paths are omitted" in item.summary for item in portability))

    def test_snapshot_does_not_inspect_transform_file_external_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            external_directory = root / "external-directory-not-text-file"
            external_directory.mkdir()
            paths = write_required_project(
                root,
                built_in_actions=[
                    action(
                        "transform-external",
                        action_type="transform_file_text",
                        value=str(external_directory),
                        arguments=["uppercase"],
                    )
                ],
                contexts=[],
            )

            report = load_configuration_snapshot(paths)

        self.assertTrue(report.ok)
        self.assertEqual(
            [item.id for item in report.snapshot.active_actions],
            ["transform-external"],
        )

    def test_palette_context_references_are_classified_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = write_required_project(
                root,
                built_in_actions=[action("active")],
                contexts=[{"name": "Mail", "action_ids": ["active"]}],
            )
            write_json(
                paths.palette_state_file,
                {
                    "pinned_action_ids": [],
                    "focus_context": "MAIL",
                    "context_slots": {
                        "Mail": ["active"],
                        "mail": ["active"],
                        "Historical": ["active"],
                    },
                    "context_membership_version": 1,
                },
            )

            report = load_configuration_snapshot(paths)

        codes = issue_codes(report)
        self.assertTrue(report.ok)
        self.assertIn(ValidationIssueCode.PALETTE_CONTEXT_CANONICALIZATION, codes)
        self.assertIn(ValidationIssueCode.PALETTE_SLOT_CONTEXT_UNKNOWN, codes)
        self.assertIn(ValidationIssueCode.PALETTE_SLOT_CONTEXT_DUPLICATE, codes)
        self.assertEqual(report.snapshot.palette_state.focus_context, "MAIL")
        self.assertEqual(
            tuple(report.snapshot.palette_state.context_slots),
            ("Mail", "mail", "Historical"),
        )

    def test_unknown_focus_is_a_soft_runtime_fallback_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = write_required_project(Path(directory))
            write_json(
                paths.palette_state_file,
                {
                    "focus_context": "Removed Context",
                    "context_slots": {},
                    "context_membership_version": 1,
                },
            )

            report = load_configuration_snapshot(paths)

        self.assertTrue(report.ok)
        self.assertIn(ValidationIssueCode.PALETTE_FOCUS_UNKNOWN, issue_codes(report))

    def test_portability_detects_windows_paths_without_url_false_positives(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = write_required_project(
                Path(directory),
                built_in_actions=[
                    action("drive", action_type="open_file", value=r"C:\Private\one.txt"),
                    action("unc", action_type="open_folder", value=r"\\server\share\folder"),
                    action(
                        "working",
                        action_type="launch_app",
                        value="tool.exe",
                        working_directory=r"D:\Work",
                    ),
                    action(
                        "argument",
                        action_type="launch_app",
                        value="tool.exe",
                        arguments=[r"E:\Inputs\one.csv"],
                    ),
                    action(
                        "placeholder",
                        action_type="open_file",
                        value=r"%PROJECT_ROOT%\README.md",
                    ),
                    action(
                        "url",
                        action_type="open_windows_target",
                        value="https://example.com/path",
                    ),
                    action(
                        "protocol",
                        action_type="open_windows_target",
                        value="shell:AppsFolder",
                    ),
                ],
                contexts=[],
            )

            report = load_configuration_snapshot(paths)

        portability = {
            issue.code: set(issue.subject_ids)
            for issue in report.warnings
            if issue.category is ValidationCategory.PORTABILITY
        }
        self.assertEqual(
            portability[ValidationIssueCode.PORTABILITY_ACTION_VALUE],
            {"drive", "unc"},
        )
        self.assertEqual(
            portability[ValidationIssueCode.PORTABILITY_WORKING_DIRECTORY],
            {"working"},
        )
        self.assertEqual(
            portability[ValidationIssueCode.PORTABILITY_ARGUMENT],
            {"argument"},
        )
        self.assertNotIn("placeholder", set().union(*portability.values()))
        self.assertNotIn("url", set().union(*portability.values()))
        self.assertNotIn("protocol", set().union(*portability.values()))

    def test_configuration_output_omits_private_values_and_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = write_required_project(
                root,
                built_in_actions=[
                    action(
                        "private-path",
                        action_type="open_file",
                        value=r"C:\Secret\Client\plan.txt",
                        working_directory=r"D:\Secret\Working",
                    ),
                    action(
                        "credential",
                        action_type="paste_credential",
                        value="credential-secret-target",
                    ),
                ],
                contexts=[],
            )
            write_json(
                paths.inbox_file,
                {
                    "items": [
                        {
                            "id": "private-inbox",
                            "title": "private-title",
                            "content": "private-inbox-content",
                            "source": "clipboard",
                            "created_at": "now",
                            "state": "Inbox",
                            "suggested_context": "",
                        }
                    ]
                },
            )

            formatted = format_configuration_report(
                validate_project_configuration(root)
            )

        for private_value in (
            r"C:\Secret\Client\plan.txt",
            r"D:\Secret\Working",
            "credential-secret-target",
            "private-title",
            "private-inbox-content",
            str(root),
        ):
            self.assertNotIn(private_value, formatted)
        self.assertIn("raw paths are omitted", formatted)

    def test_excluded_runtime_artifacts_are_not_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = write_required_project(root, contexts=[])
            paths.diagnostic_log_file.write_text(
                "private diagnostic C:\\Secret\\log",
                encoding="utf-8",
            )
            paths.built_in_actions_file.with_name(
                "actions.json.bak"
            ).write_text("not json", encoding="utf-8")
            paths.built_in_actions_file.with_name(
                ".actions.json.private.tmp"
            ).write_text("not json", encoding="utf-8")

            report = load_configuration_snapshot(paths)

        self.assertTrue(report.ok)
        self.assertTrue(
            all(
                issue.asset_id
                not in {
                    "diagnostic-logs",
                    "recovery-backups",
                    "temporary-data-files",
                    "python-environment",
                    "preserved-python-environments",
                }
                for issue in report.issues
            )
        )

    def test_legacy_forms_are_classified_without_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = write_required_project(
                root,
                contexts=[{"name": "Legacy", "preferred_action_ids": []}],
            )
            write_json(
                paths.personal_command_surface_file,
                {
                    "groups": [
                        {
                            "id": "legacy",
                            "label": "Legacy",
                            "items": [
                                {
                                    "id": "action-fields",
                                    "label": "Action",
                                    "primary_action_id": "built-in-active",
                                    "action_ids": ["built-in-active"],
                                },
                                {
                                    "id": "work-item-field",
                                    "label": "Work item",
                                    "work_item_ref": {
                                        "source_id": "missing-source",
                                        "relative_folder": "PRIVATE-FOLDER",
                                    },
                                },
                            ],
                        }
                    ]
                },
            )
            write_json(
                paths.palette_state_file,
                {
                    "focus_context": "General",
                    "context_slots": {},
                    "context_membership_version": 0,
                },
            )
            before = {
                path: path.read_bytes()
                for path in (
                    paths.built_in_contexts_file,
                    paths.personal_command_surface_file,
                    paths.palette_state_file,
                )
            }

            report = load_configuration_snapshot(paths)

            after = {path: path.read_bytes() for path in before}

        codes = issue_codes(report)
        self.assertTrue(report.ok)
        self.assertIn(ValidationIssueCode.LEGACY_COMMAND_ACTION_FIELDS, codes)
        self.assertIn(ValidationIssueCode.LEGACY_COMMAND_WORK_ITEM_FIELD, codes)
        self.assertIn(ValidationIssueCode.LEGACY_CONTEXT_MEMBERSHIP, codes)
        self.assertIn(
            ValidationIssueCode.LEGACY_CONTEXT_MEMBERSHIP_MARKER,
            codes,
        )
        self.assertEqual(before, after)

    def test_every_issue_uses_a_catalog_asset_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = load_configuration_snapshot(
                AppDataPaths.from_root(Path(directory))
            )

        self.assertTrue(report.issues)
        for issue in report.issues:
            self.assertEqual(asset_spec_by_id(issue.asset_id).asset_id, issue.asset_id)
            self.assertIn(issue.severity, ValidationSeverity)


if __name__ == "__main__":
    unittest.main()
