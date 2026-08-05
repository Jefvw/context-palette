from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import context_palette.backup as backup_module
from context_palette.backup import (
    BACKUP_DATA_MODEL_VERSION,
    BACKUP_FORMAT,
    BACKUP_FORMAT_VERSION,
    BACKUP_SCOPE,
    BackupConfigurationError,
    BackupDestinationError,
    BackupExclusion,
    BackupLimitError,
    BackupLimits,
    BackupManifest,
    BackupManifestEntry,
    BackupOptions,
    BackupPublicationError,
    BackupSourceChangedError,
    BackupSourceSafetyError,
    BackupStagingError,
    BackupTestHooks,
    create_configuration_backup,
)
from context_palette.backup_cli import main as backup_cli_main
from context_palette.configuration_mutation import configuration_mutation_gate
from context_palette.configuration_snapshot import load_configuration_snapshot
from context_palette.data_catalog import AppDataPaths
from context_palette.persistence import atomic_write_json
from context_palette.work_item_file_copy import copy_file_to_work_item


CREATED_AT = datetime(2026, 8, 5, 12, 30, tzinfo=timezone.utc)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_required_project(root: Path) -> AppDataPaths:
    paths = AppDataPaths.from_root(root)
    write_json(
        paths.built_in_actions_file,
        {
            "actions": [
                {
                    "id": "built-in-action",
                    "title": "Built-in",
                    "type": "copy_text",
                    "value": "safe",
                    "state": "Active",
                }
            ]
        },
    )
    write_json(
        paths.built_in_contexts_file,
        {
            "contexts": [
                {
                    "name": "Work",
                    "action_ids": ["built-in-action"],
                    "preferred_action_ids": ["built-in-action"],
                }
            ]
        },
    )
    return paths


def write_complete_project(root: Path) -> AppDataPaths:
    paths = write_required_project(root)
    write_json(paths.personal_actions_file, {"actions": []})
    write_json(paths.personal_contexts_file, {"contexts": []})
    write_json(paths.built_in_command_surface_file, {"groups": []})
    write_json(paths.personal_command_surface_file, {"groups": []})
    write_json(
        paths.palette_state_file,
        {
            "pinned_action_ids": ["built-in-action"],
            "focus_context": "Work",
            "context_slots": {"Work": ["built-in-action"]},
            "context_membership_version": 1,
        },
    )
    write_json(
        paths.inbox_file,
        {
            "items": [
                {
                    "id": "private-inbox",
                    "title": "PRIVATE INBOX TITLE",
                    "content": "PRIVATE INBOX CONTENT",
                    "source": "clipboard",
                    "created_at": "2026-08-05T12:00:00+00:00",
                    "state": "Inbox",
                    "suggested_context": "Work",
                }
            ]
        },
    )
    write_json(
        paths.cheat_sheets_directory / "reference.json",
        {
            "id": "reference",
            "title": "Reference",
            "kind": "reference",
            "aliases": [],
            "summary": "Safe summary",
            "updated_at": "2026-08-05",
            "sections": [],
        },
    )
    write_json(paths.work_item_sources_file, {"sources": []})
    write_json(paths.work_item_metadata_file, {"work_items": {}})
    write_json(paths.work_item_settings_file, {"template_path": ""})
    paths.managed_text_action_source_file.write_bytes(b"PRIVATE MANAGED CONTENT")
    return paths


def read_manifest(archive_path: Path) -> tuple[list[str], dict[str, object]]:
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
    return names, manifest


def source_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


class BackupManifestTests(unittest.TestCase):
    def test_manifest_models_reject_noncanonical_values(self) -> None:
        valid = BackupManifestEntry(
            "built-in-actions",
            PurePosixPath("payload/data/actions.json"),
            1,
            0,
            "0" * 64,
        )
        manifest = BackupManifest(
            created_at="2026-08-05T12:30:00Z",
            entries=(valid,),
        )
        self.assertEqual(manifest.format, BACKUP_FORMAT)
        self.assertEqual(manifest.format_version, BACKUP_FORMAT_VERSION)
        self.assertEqual(manifest.data_model_version, BACKUP_DATA_MODEL_VERSION)
        self.assertEqual(manifest.scope, BACKUP_SCOPE)

        invalid_entries = (
            dict(archive_path=PurePosixPath("data/actions.json")),
            dict(archive_path=PurePosixPath("payload/../actions.json")),
            dict(archive_path=PurePosixPath("payload/data/contexts.json")),
            dict(schema_version=True),
            dict(size=-1),
            dict(sha256="A" * 64),
        )
        base = {
            "asset_id": valid.asset_id,
            "archive_path": valid.archive_path,
            "schema_version": valid.schema_version,
            "size": valid.size,
            "sha256": valid.sha256,
        }
        for change in invalid_entries:
            with self.subTest(change=change), self.assertRaises(ValueError):
                BackupManifestEntry(**(base | change))

        with self.assertRaises(ValueError):
            BackupManifest("2026-08-05T12:30:00+00:00", (valid,))
        with self.assertRaises(ValueError):
            BackupManifest(
                "2026-08-05T12:30:00Z",
                [valid],  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            BackupManifest(
                "2026-08-05T12:30:00Z",
                (valid,),
                format_version=True,
            )

    def test_limits_reject_boolean_zero_and_negative_values(self) -> None:
        for values in (
            (True, 1, 1),
            (1, 0, 1),
            (1, 1, -1),
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                BackupLimits(*values)


class BackupArchiveTests(unittest.TestCase):
    def test_backup_refuses_an_unresolved_restore_journal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_required_project(base / "project")
            paths.restore_journal_file.write_text("pending", encoding="utf-8")

            with self.assertRaises(BackupSourceSafetyError):
                create_configuration_backup(
                    paths,
                    base / "backup.zip",
                    created_at=CREATED_AT,
                )

    def test_complete_archive_manifest_layout_hashes_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_complete_project(base / "application")
            destination = base / "backup.zip"

            result = create_configuration_backup(
                paths,
                destination,
                created_at=CREATED_AT,
            )

            names, raw_manifest = read_manifest(destination)
            self.assertEqual(names[-1], "manifest.json")
            self.assertEqual(names[:-1], sorted(names[:-1]))
            self.assertNotIn(
                "payload/data/local_text_action_source.txt",
                names,
            )
            self.assertIn("payload/data/inbox.json", names)
            self.assertEqual(raw_manifest, result.manifest.to_dict())
            self.assertEqual(raw_manifest["created_at"], "2026-08-05T12:30:00Z")
            self.assertIn(BackupExclusion.MANAGED_CONTENT, result.excluded_categories)

            with zipfile.ZipFile(destination) as archive:
                for entry in result.manifest.entries:
                    payload = archive.read(entry.archive_path.as_posix())
                    self.assertEqual(entry.size, len(payload))
                    self.assertEqual(entry.sha256, hashlib.sha256(payload).hexdigest())
                for info in archive.infolist():
                    self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                    self.assertEqual(info.create_system, 0)

    def test_archive_bytes_are_deterministic_for_same_state_and_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_complete_project(base / "application")
            first = base / "first.zip"
            second = base / "second.zip"

            create_configuration_backup(paths, first, created_at=CREATED_AT)
            create_configuration_backup(paths, second, created_at=CREATED_AT)

            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_missing_optional_files_are_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_required_project(base / "application")
            destination = base / "backup.zip"

            result = create_configuration_backup(
                paths,
                destination,
                created_at=CREATED_AT,
            )

            self.assertEqual(
                tuple(item.archive_path.as_posix() for item in result.included_files),
                (
                    "payload/data/actions.json",
                    "payload/data/contexts.json",
                ),
            )

    def test_missing_or_invalid_required_configuration_prevents_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for variant in ("missing", "invalid"):
                with self.subTest(variant=variant):
                    root = base / variant
                    paths = write_required_project(root)
                    if variant == "missing":
                        paths.built_in_actions_file.unlink()
                    else:
                        paths.built_in_actions_file.write_text("not json", encoding="utf-8")
                    destination = base / f"{variant}.zip"
                    with self.assertRaises(BackupConfigurationError):
                        create_configuration_backup(
                            paths,
                            destination,
                            created_at=CREATED_AT,
                        )
                    self.assertFalse(destination.exists())

    def test_inbox_and_managed_content_require_their_documented_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_complete_project(base / "application")

            default = create_configuration_backup(
                paths,
                base / "default.zip",
                created_at=CREATED_AT,
            )
            excluded = create_configuration_backup(
                paths,
                base / "excluded.zip",
                options=BackupOptions(include_inbox=False),
                created_at=CREATED_AT,
            )
            managed = create_configuration_backup(
                paths,
                base / "managed.zip",
                options=BackupOptions(include_managed_content=True),
                created_at=CREATED_AT,
            )

            default_names, _ = read_manifest(default.destination)
            excluded_names, _ = read_manifest(excluded.destination)
            managed_names, _ = read_manifest(managed.destination)
            self.assertIn("payload/data/inbox.json", default_names)
            self.assertNotIn("payload/data/inbox.json", excluded_names)
            self.assertIn(BackupExclusion.INBOX, excluded.excluded_categories)
            self.assertIn(
                "payload/data/local_text_action_source.txt",
                managed_names,
            )
            managed_entry = next(
                entry
                for entry in managed.manifest.to_dict()["entries"]
                if entry["asset_id"] == "managed-text-action-source"
            )
            self.assertNotIn("schema_version", managed_entry)

    def test_uncatalogued_runtime_environment_and_external_files_never_enter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "application"
            paths = write_complete_project(root)
            external = base / "external-secret.txt"
            external.write_text("EXTERNAL SECRET", encoding="utf-8")
            paths.diagnostic_log_file.write_text("PRIVATE LOG", encoding="utf-8")
            (paths.data_directory / "actions.json.bak").write_text("BACKUP", encoding="utf-8")
            (paths.data_directory / ".actions.json.test.tmp").write_text("TEMP", encoding="utf-8")
            (paths.data_directory / "unknown.json").write_text("UNKNOWN", encoding="utf-8")
            nested = paths.cheat_sheets_directory / "nested" / "private.json"
            nested.parent.mkdir()
            nested.write_text("PRIVATE NESTED", encoding="utf-8")
            (root / ".venv").mkdir()
            (root / ".venv" / "secret.txt").write_text("ENV", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("GIT", encoding="utf-8")

            destination = base / "backup.zip"
            result = create_configuration_backup(
                paths,
                destination,
                created_at=CREATED_AT,
            )

            names, _ = read_manifest(destination)
            joined = "\n".join(names)
            for forbidden in (
                "context-palette.log",
                ".bak",
                ".tmp",
                "unknown.json",
                "private.json",
                ".venv",
                ".git",
                "external-secret.txt",
            ):
                self.assertNotIn(forbidden, joined)
            self.assertIn(BackupExclusion.RUNTIME_ARTIFACTS, result.excluded_categories)
            self.assertIn(BackupExclusion.UNKNOWN_FILES, result.excluded_categories)
            self.assertIn(BackupExclusion.EXTERNAL_RESOURCES, result.excluded_categories)
            self.assertIn(BackupExclusion.CREDENTIAL_SECRETS, result.excluded_categories)

    def test_manifest_and_messages_do_not_expose_private_values_or_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_complete_project(base / "PRIVATE-ROOT")
            destination = base / "backup.zip"

            result = create_configuration_backup(
                paths,
                destination,
                created_at=CREATED_AT,
            )
            manifest_bytes = result.manifest.to_json_bytes()

            self.assertNotIn(b"PRIVATE INBOX", manifest_bytes)
            self.assertNotIn(b"PRIVATE MANAGED", manifest_bytes)
            self.assertNotIn(str(paths.application_root).encode(), manifest_bytes)
            self.assertNotIn(str(destination).encode(), manifest_bytes)

    def test_source_symlink_is_rejected_when_platform_allows_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_required_project(base / "application")
            outside = base / "outside.json"
            write_json(outside, {"actions": []})
            try:
                os.symlink(outside, paths.personal_actions_file)
            except OSError as exc:
                self.skipTest(f"Symlink creation unavailable: {exc}")

            with self.assertRaises(BackupSourceSafetyError):
                create_configuration_backup(
                    paths,
                    base / "backup.zip",
                    created_at=CREATED_AT,
                )

    def test_destination_inside_application_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "application"
            paths = write_required_project(root)

            with self.assertRaises(BackupDestinationError):
                create_configuration_backup(
                    paths,
                    root / "backup.zip",
                    created_at=CREATED_AT,
                )

    def test_source_bytes_are_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "application"
            paths = write_complete_project(root)
            before = source_bytes(root)

            create_configuration_backup(
                paths,
                base / "backup.zip",
                options=BackupOptions(include_managed_content=True),
                created_at=CREATED_AT,
            )

            self.assertEqual(source_bytes(root), before)


class BackupLimitTests(unittest.TestCase):
    def test_entry_count_limit_accepts_exact_boundary_and_rejects_one_less(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_required_project(base / "application")
            accepted = BackupLimits(2, 1024, 2048)

            create_configuration_backup(
                paths,
                base / "accepted.zip",
                options=BackupOptions(limits=accepted),
                created_at=CREATED_AT,
            )
            with self.assertRaisesRegex(Exception, "entry limit"):
                create_configuration_backup(
                    paths,
                    base / "rejected.zip",
                    options=BackupOptions(limits=BackupLimits(1, 1024, 2048)),
                    created_at=CREATED_AT,
                )

    def test_individual_limit_accepts_exact_boundary_and_rejects_one_less(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_required_project(base / "application")
            content = b"x" * 256
            paths.managed_text_action_source_file.write_bytes(content)

            create_configuration_backup(
                paths,
                base / "accepted.zip",
                options=BackupOptions(
                    include_managed_content=True,
                    limits=BackupLimits(10, len(content), 4096),
                ),
                created_at=CREATED_AT,
            )
            with self.assertRaisesRegex(Exception, "entry.*byte limit"):
                create_configuration_backup(
                    paths,
                    base / "rejected.zip",
                    options=BackupOptions(
                        include_managed_content=True,
                        limits=BackupLimits(10, len(content) - 1, 4096),
                    ),
                    created_at=CREATED_AT,
                )

    def test_total_limit_accepts_exact_boundary_and_rejects_one_less(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_required_project(base / "application")
            total = (
                paths.built_in_actions_file.stat().st_size
                + paths.built_in_contexts_file.stat().st_size
            )

            create_configuration_backup(
                paths,
                base / "accepted.zip",
                options=BackupOptions(limits=BackupLimits(2, 1024, total)),
                created_at=CREATED_AT,
            )
            with self.assertRaisesRegex(Exception, "total byte limit"):
                create_configuration_backup(
                    paths,
                    base / "rejected.zip",
                    options=BackupOptions(
                        limits=BackupLimits(2, 1024, total - 1)
                    ),
                    created_at=CREATED_AT,
                )

    def test_limits_stop_before_excess_entries_or_bytes_are_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_required_project(base / "application")
            write_json(
                paths.cheat_sheets_directory / "excess.json",
                {
                    "id": "excess",
                    "title": "Excess",
                    "kind": "reference",
                    "aliases": [],
                    "summary": "summary",
                    "updated_at": "2026-08-05",
                    "sections": [],
                },
            )
            with patch(
                "context_palette.backup._fingerprint_file",
                wraps=backup_module._fingerprint_file,
            ) as fingerprint:
                with self.assertRaises(BackupLimitError):
                    create_configuration_backup(
                        paths,
                        base / "entries.zip",
                        options=BackupOptions(
                            limits=BackupLimits(2, 4096, 8192)
                        ),
                        created_at=CREATED_AT,
                    )
            self.assertEqual(fingerprint.call_count, 2)

            managed = paths.managed_text_action_source_file
            managed.write_bytes(b"managed content that must not be read")
            total = (
                paths.built_in_actions_file.stat().st_size
                + paths.built_in_contexts_file.stat().st_size
            )
            original_open = Path.open

            def guarded_open(path: Path, *args, **kwargs):
                if path == managed and args and args[0] == "rb":
                    raise AssertionError("Excess payload content was read.")
                return original_open(path, *args, **kwargs)

            with patch.object(Path, "open", guarded_open):
                with self.assertRaises(BackupLimitError):
                    create_configuration_backup(
                        paths,
                        base / "bytes.zip",
                        options=BackupOptions(
                            include_managed_content=True,
                            limits=BackupLimits(10, 4096, total),
                        ),
                        created_at=CREATED_AT,
                    )


class BackupConsistencyTests(unittest.TestCase):
    def test_source_appearance_and_disappearance_are_detected_and_retried(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            appearance_paths = write_required_project(base / "appearance")
            appearance_attempts: list[int] = []

            def appear(attempt: int) -> None:
                appearance_attempts.append(attempt)
                if attempt == 1:
                    write_json(appearance_paths.personal_actions_file, {"actions": []})

            appeared = create_configuration_backup(
                appearance_paths,
                base / "appearance.zip",
                options=BackupOptions(max_consistency_attempts=2),
                created_at=CREATED_AT,
                test_hooks=BackupTestHooks(after_initial_inventory=appear),
            )
            self.assertEqual(appearance_attempts, [1, 2])
            self.assertIn("personal-actions", appeared.included_asset_ids)

            disappearance_paths = write_complete_project(base / "disappearance")
            disappearance_attempts: list[int] = []

            def disappear(attempt: int) -> None:
                disappearance_attempts.append(attempt)
                if attempt == 1:
                    disappearance_paths.inbox_file.unlink()

            disappeared = create_configuration_backup(
                disappearance_paths,
                base / "disappearance.zip",
                options=BackupOptions(max_consistency_attempts=2),
                created_at=CREATED_AT,
                test_hooks=BackupTestHooks(after_staging=disappear),
            )
            self.assertEqual(disappearance_attempts, [1, 2])
            self.assertNotIn("inbox", disappeared.included_asset_ids)

    def test_same_and_different_size_mutations_abort_when_retries_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for variant in ("same", "different"):
                with self.subTest(variant=variant):
                    paths = write_required_project(base / variant)

                    def mutate(_attempt: int) -> None:
                        content = paths.built_in_actions_file.read_text(encoding="utf-8")
                        replacement = (
                            content.replace("safe", "risk")
                            if variant == "same"
                            else content + " "
                        )
                        paths.built_in_actions_file.write_text(
                            replacement,
                            encoding="utf-8",
                        )

                    destination = base / f"{variant}.zip"
                    with self.assertRaises(BackupSourceChangedError):
                        create_configuration_backup(
                            paths,
                            destination,
                            options=BackupOptions(max_consistency_attempts=1),
                            created_at=CREATED_AT,
                            test_hooks=BackupTestHooks(after_staging=mutate),
                        )
                    self.assertFalse(destination.exists())

    def test_copy_time_mutation_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_required_project(base / "application")
            mutated = False

            def mutate_after_copy(
                _asset_id: str,
                relative_path: PurePosixPath,
                _index: int,
            ) -> None:
                nonlocal mutated
                if not mutated and relative_path == PurePosixPath("data/actions.json"):
                    mutated = True
                    paths.built_in_contexts_file.write_text(
                        paths.built_in_contexts_file.read_text(encoding="utf-8") + " ",
                        encoding="utf-8",
                    )

            with self.assertRaises(BackupSourceChangedError):
                create_configuration_backup(
                    paths,
                    base / "backup.zip",
                    options=BackupOptions(max_consistency_attempts=1),
                    created_at=CREATED_AT,
                    test_hooks=BackupTestHooks(
                        after_staged_file=mutate_after_copy
                    ),
                )

    def test_staged_snapshot_is_validated_and_invalid_utf8_is_structured(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_required_project(base / "valid")
            with patch(
                "context_palette.backup.load_configuration_snapshot",
                wraps=load_configuration_snapshot,
            ) as loader:
                create_configuration_backup(
                    paths,
                    base / "valid.zip",
                    created_at=CREATED_AT,
                )
            staged_paths = loader.call_args.args[0]
            self.assertNotEqual(staged_paths.application_root, paths.application_root)
            self.assertFalse(staged_paths.application_root.exists())

            invalid = write_required_project(base / "invalid")
            invalid.built_in_actions_file.write_bytes(b"\xff")
            with self.assertRaises(BackupConfigurationError) as captured:
                create_configuration_backup(
                    invalid,
                    base / "invalid.zip",
                    created_at=CREATED_AT,
                )
            self.assertTrue(captured.exception.issues)
            self.assertNotIn(str(invalid.application_root), str(captured.exception))


class BackupFailureAndGateTests(unittest.TestCase):
    def test_application_json_writer_waits_for_backup_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_required_project(base / "application")
            started = threading.Event()
            finished = threading.Event()
            writer: threading.Thread | None = None

            def hold_writer(_attempt: int) -> None:
                nonlocal writer

                def write() -> None:
                    started.set()
                    atomic_write_json(paths.personal_actions_file, {"actions": []})
                    finished.set()

                writer = threading.Thread(target=write)
                writer.start()
                self.assertTrue(started.wait(1))
                self.assertFalse(finished.wait(0.05))

            create_configuration_backup(
                paths,
                base / "backup.zip",
                created_at=CREATED_AT,
                test_hooks=BackupTestHooks(after_initial_inventory=hold_writer),
            )
            self.assertIsNotNone(writer)
            writer.join(1)
            self.assertTrue(finished.is_set())

    def test_external_work_item_file_copy_does_not_wait_for_configuration_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source.txt"
            folder = base / "work-item"
            source.write_text("content", encoding="utf-8")
            folder.mkdir()
            finished = threading.Event()

            def copy() -> None:
                copy_file_to_work_item(source, folder)
                finished.set()

            with configuration_mutation_gate():
                worker = threading.Thread(target=copy)
                worker.start()
                self.assertTrue(finished.wait(1))
            worker.join(1)
            self.assertEqual((folder / source.name).read_text(encoding="utf-8"), "content")

    def test_interrupted_staging_and_zip_writing_leave_no_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_required_project(base / "application")
            staging_parent = base / "staging"
            staging_parent.mkdir()

            def interrupt_stage(
                _asset_id: str,
                _relative_path: PurePosixPath,
                _index: int,
            ) -> None:
                raise BackupStagingError("Injected staging interruption.")

            with self.assertRaises(BackupStagingError):
                create_configuration_backup(
                    paths,
                    base / "stage.zip",
                    created_at=CREATED_AT,
                    test_hooks=BackupTestHooks(
                        after_staged_file=interrupt_stage,
                        staging_parent=staging_parent,
                    ),
                )
            self.assertEqual(list(staging_parent.iterdir()), [])
            self.assertFalse((base / "stage.zip").exists())

            def interrupt_archive(_path: PurePosixPath) -> None:
                raise BackupPublicationError("Injected ZIP interruption.")

            with self.assertRaises(BackupPublicationError):
                create_configuration_backup(
                    paths,
                    base / "archive.zip",
                    created_at=CREATED_AT,
                    test_hooks=BackupTestHooks(
                        after_archive_entry=interrupt_archive,
                        staging_parent=staging_parent,
                    ),
                )
            self.assertEqual(list(staging_parent.iterdir()), [])
            self.assertEqual(list(base.glob(".archive.zip.*.tmp")), [])
            self.assertFalse((base / "archive.zip").exists())

    def test_publication_failure_preserves_existing_destination_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_required_project(base / "application")
            destination = base / "backup.zip"
            destination.write_bytes(b"previous archive")

            with patch(
                "context_palette.backup.os.replace",
                side_effect=OSError("blocked"),
            ):
                with self.assertRaises(BackupPublicationError):
                    create_configuration_backup(
                        paths,
                        destination,
                        options=BackupOptions(overwrite=True),
                        created_at=CREATED_AT,
                    )

            self.assertEqual(destination.read_bytes(), b"previous archive")
            self.assertEqual(list(base.glob(".backup.zip.*.tmp")), [])

    def test_overwrite_requires_explicit_option(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_required_project(base / "application")
            destination = base / "backup.zip"
            destination.write_bytes(b"old")

            with self.assertRaises(BackupDestinationError):
                create_configuration_backup(paths, destination, created_at=CREATED_AT)
            create_configuration_backup(
                paths,
                destination,
                options=BackupOptions(overwrite=True),
                created_at=CREATED_AT,
            )
            self.assertTrue(zipfile.is_zipfile(destination))

    def test_non_overwrite_publication_preserves_a_racing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = write_required_project(base / "application")
            destination = base / "backup.zip"
            primitive_name = "rename" if os.name == "nt" else "link"
            real_publish = getattr(os, primitive_name)

            def collide(source, target, *args, **kwargs):
                Path(target).write_bytes(b"racing destination")
                return real_publish(source, target, *args, **kwargs)

            with patch(
                f"context_palette.backup.os.{primitive_name}",
                side_effect=collide,
            ):
                with self.assertRaises(BackupDestinationError):
                    create_configuration_backup(
                        paths,
                        destination,
                        created_at=CREATED_AT,
                    )

            self.assertEqual(destination.read_bytes(), b"racing destination")
            self.assertEqual(list(base.glob(".backup.zip.*.tmp")), [])


class BackupCliTests(unittest.TestCase):
    def test_cli_success_reports_scope_without_private_content_or_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "PRIVATE-APPLICATION-ROOT"
            write_complete_project(root)
            destination = base / "backup.zip"
            output = StringIO()
            errors = StringIO()

            with redirect_stdout(output), redirect_stderr(errors):
                exit_code = backup_cli_main(
                    [
                        str(destination),
                        "--root",
                        str(root),
                        "--exclude-inbox",
                        "--include-managed-content",
                    ]
                )

            rendered = output.getvalue() + errors.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertTrue(destination.is_file())
            self.assertIn("Inbox excluded", rendered)
            self.assertIn("managed text included", rendered)
            self.assertNotIn("PRIVATE INBOX", rendered)
            self.assertNotIn("PRIVATE MANAGED", rendered)
            self.assertNotIn(str(root), rendered)
            self.assertNotIn(str(destination), rendered)

    def test_cli_failure_returns_one_without_leaking_invalid_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "PRIVATE-ROOT"
            paths = write_required_project(root)
            paths.built_in_actions_file.write_text(
                '"PRIVATE ACTION VALUE C:\\\\Sensitive"',
                encoding="utf-8",
            )
            destination = base / "backup.zip"
            output = StringIO()
            errors = StringIO()

            with redirect_stdout(output), redirect_stderr(errors):
                exit_code = backup_cli_main(
                    [str(destination), "--root", str(root)]
                )

            rendered = output.getvalue() + errors.getvalue()
            self.assertEqual(exit_code, 1)
            self.assertFalse(destination.exists())
            self.assertIn("Backup was not created", rendered)
            self.assertNotIn("PRIVATE ACTION VALUE", rendered)
            self.assertNotIn(str(root), rendered)
            self.assertNotIn(str(destination), rendered)


if __name__ == "__main__":
    unittest.main()
