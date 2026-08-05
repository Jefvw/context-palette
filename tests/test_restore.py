from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.backup import (
    BackupManifest,
    BackupOptions,
    create_configuration_backup,
)
from context_palette.data_catalog import AppDataPaths, is_catalogued_backup_payload
from context_palette.persistence import atomic_replace_bytes
from context_palette.restore import (
    FileIdentity,
    RestoreArchiveError,
    RestoreCommitError,
    RestoreCompatibilityError,
    RestoreConfirmation,
    RestoreConfirmationError,
    RestoreConfigurationError,
    RestoreLimitError,
    RestoreLimits,
    RestorePlanStaleError,
    RestoreRecoveryError,
    RestoreSensitiveCategory,
    RestoreTestHooks,
    commit_restore,
    inspect_restore_archive,
    recover_interrupted_restore,
)


NOW = datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def action(action_id: str, *, value: str = "safe") -> dict[str, object]:
    return {
        "id": action_id,
        "title": action_id,
        "type": "copy_text",
        "value": value,
        "state": "Active",
    }


def write_required_configuration(root: Path, action_id: str) -> AppDataPaths:
    paths = AppDataPaths.from_root(root)
    write_json(paths.built_in_actions_file, {"actions": [action(action_id)]})
    write_json(
        paths.built_in_contexts_file,
        {
            "contexts": [
                {
                    "name": "Focus",
                    "action_ids": [action_id],
                    "preferred_action_ids": [action_id],
                }
            ]
        },
    )
    return paths


def make_backup(
    base: Path,
    action_id: str = "restored-action",
    *,
    complete: bool = False,
) -> tuple[Path, AppDataPaths]:
    source = write_required_configuration(base / "source", action_id)
    if complete:
        write_json(
            source.personal_actions_file,
            {"actions": [action("personal-restored")]},
        )
        write_json(
            source.work_item_sources_file,
            {
                "sources": [
                    {
                        "id": "source-one",
                        "name": "Source",
                        "workitems_path": r"Z:\\Disconnected\\Private",
                    }
                ]
            },
        )
        write_json(
            source.inbox_file,
            {
                "items": [
                    {
                        "id": "private-inbox",
                        "title": "PRIVATE TITLE",
                        "content": "PRIVATE CONTENT",
                        "source": "clipboard",
                        "created_at": "2026-08-05T12:00:00+00:00",
                        "state": "Captured",
                        "suggested_context": "",
                    }
                ]
            },
        )
        source.managed_text_action_source_file.write_text(
            "PRIVATE MANAGED CONTENT", encoding="utf-8"
        )
    archive = base / "source-backup.zip"
    create_configuration_backup(
        source,
        archive,
        options=BackupOptions(include_managed_content=complete),
        created_at=NOW,
    )
    return archive, source


def read_archive(archive: Path) -> tuple[list[tuple[zipfile.ZipInfo, bytes]], dict]:
    with zipfile.ZipFile(archive, "r") as source:
        values = [(info, source.read(info)) for info in source.infolist()]
    manifest = json.loads(values[-1][1])
    return values, manifest


def write_archive(
    destination: Path,
    entries: list[tuple[str, bytes, int, int]],
) -> None:
    with zipfile.ZipFile(destination, "w") as archive:
        for name, payload, compression, external_attr in entries:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = compression
            info.create_system = 3 if external_attr else 0
            info.external_attr = external_attr
            archive.writestr(info, payload)


class ManifestParsingTests(unittest.TestCase):
    def test_strict_parser_returns_existing_immutable_models(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive, _source = make_backup(Path(directory))
            _values, raw = read_archive(archive)
            manifest = BackupManifest.from_json_bytes(
                (json.dumps(raw) + "\n").encode("utf-8")
            )

        self.assertIsInstance(manifest, BackupManifest)
        self.assertIsInstance(manifest.entries, tuple)
        with self.assertRaises(FrozenInstanceError):
            manifest.scope = "other"

    def test_strict_parser_rejects_unknown_missing_duplicate_and_boolean_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive, _source = make_backup(Path(directory))
            _values, raw = read_archive(archive)

        variants = []
        unknown = dict(raw)
        unknown["unknown"] = 1
        variants.append(json.dumps(unknown).encode())
        missing = dict(raw)
        missing.pop("scope")
        variants.append(json.dumps(missing).encode())
        boolean = dict(raw)
        boolean["format_version"] = True
        variants.append(json.dumps(boolean).encode())
        unknown_asset = json.loads(json.dumps(raw))
        unknown_asset["entries"][0]["asset_id"] = "unknown-asset"
        variants.append(json.dumps(unknown_asset).encode())
        variants.append(b'{"format":"one","format":"two"}')
        for payload in variants:
            with self.subTest(payload=payload[:30]):
                with self.assertRaises(ValueError):
                    BackupManifest.from_json_bytes(payload)


class RestoreInspectionTests(unittest.TestCase):
    def test_complete_plan_is_immutable_private_and_preserves_omitted_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive, _source = make_backup(base, complete=True)
            live = write_required_configuration(base / "live", "live-action")
            write_json(live.palette_state_file, {})
            write_json(
                live.cheat_sheets_directory / "historical.json",
                {
                    "id": "historical",
                    "title": "Historical",
                    "kind": "reference",
                    "aliases": [],
                    "summary": "summary",
                    "updated_at": "2026-08-05",
                    "sections": [],
                },
            )
            plan = inspect_restore_archive(live, archive)

        self.assertTrue(plan.explicit_confirmation_required)
        self.assertTrue(plan.built_in_acknowledgement_required)
        self.assertIn(RestoreSensitiveCategory.PRIVATE_PATHS, plan.sensitive_categories)
        self.assertIn(RestoreSensitiveCategory.CAPTURED_INBOX, plan.sensitive_categories)
        self.assertIn(RestoreSensitiveCategory.MANAGED_CONTENT, plan.sensitive_categories)
        self.assertIn(
            PurePosixPath("data/palette.json"),
            {item.relative_path for item in plan.preserved_live_files},
        )
        self.assertIn(
            PurePosixPath("data/cheatsheets/historical.json"),
            {item.relative_path for item in plan.preserved_live_files},
        )
        self.assertTrue(plan.snapshot_warnings)
        rendered = repr(plan)
        self.assertNotIn("PRIVATE CONTENT", rendered)
        self.assertNotIn(r"Z:\\Disconnected", rendered)
        with self.assertRaises(FrozenInstanceError):
            plan.live_state_sha256 = "0" * 64

    def test_legacy_data_is_classified_without_migrating_staged_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = write_required_configuration(base / "source", "restored-action")
            write_json(
                source.palette_state_file,
                {
                    "pinned_action_ids": [],
                    "focus_context": "General",
                    "context_slots": {},
                    "context_membership_version": 0,
                },
            )
            original = source.palette_state_file.read_bytes()
            archive = base / "legacy.zip"
            create_configuration_backup(source, archive, created_at=NOW)
            live = write_required_configuration(base / "live", "live-action")

            plan = inspect_restore_archive(live, archive)

            self.assertTrue(plan.compatibility.legacy_forms_present)
            with zipfile.ZipFile(archive, "r") as packaged:
                self.assertEqual(packaged.read("payload/data/palette.json"), original)

    def test_malformed_staged_configuration_is_rejected_without_live_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive, _source = make_backup(base)
            values, manifest = read_archive(archive)
            payloads = {info.filename: payload for info, payload in values}
            broken = b'{"actions": ['
            entry = manifest["entries"][0]
            entry["size"] = len(broken)
            entry["sha256"] = hashlib.sha256(broken).hexdigest()
            payloads[entry["path"]] = broken
            payloads["manifest.json"] = (
                json.dumps(manifest, indent=2, sort_keys=True) + "\n"
            ).encode()
            malicious = base / "invalid.zip"
            write_archive(
                malicious,
                [
                    (name, payloads[name], zipfile.ZIP_DEFLATED, 0)
                    for name in [entry["path"] for entry in manifest["entries"]]
                    + ["manifest.json"]
                ],
            )
            live = write_required_configuration(base / "live", "live-action")
            before = live.built_in_actions_file.read_bytes()
            with self.assertRaises(RestoreConfigurationError):
                inspect_restore_archive(live, malicious)
            self.assertEqual(live.built_in_actions_file.read_bytes(), before)

    def test_unknown_versions_and_manifest_payload_disagreement_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive, _source = make_backup(base)
            values, manifest = read_archive(archive)
            live = write_required_configuration(base / "live", "live-action")

            manifest["format_version"] = 99
            incompatible = base / "incompatible.zip"
            entries = [
                (info.filename, payload, zipfile.ZIP_DEFLATED, 0)
                for info, payload in values[:-1]
            ]
            entries.append(
                (
                    "manifest.json",
                    (json.dumps(manifest) + "\n").encode(),
                    zipfile.ZIP_DEFLATED,
                    0,
                )
            )
            write_archive(incompatible, entries)
            with self.assertRaises(RestoreCompatibilityError):
                inspect_restore_archive(live, incompatible)

            extra = base / "extra.zip"
            original, _raw = read_archive(archive)
            extra_entries = [
                (info.filename, payload, zipfile.ZIP_DEFLATED, 0)
                for info, payload in original[:-1]
            ]
            extra_entries.extend(
                [
                    ("payload/data/unknown.json", b"{}", zipfile.ZIP_DEFLATED, 0),
                    ("manifest.json", original[-1][1], zipfile.ZIP_DEFLATED, 0),
                ]
            )
            write_archive(extra, extra_entries)
            with self.assertRaises(RestoreArchiveError):
                inspect_restore_archive(live, extra)

    def test_hostile_paths_collisions_directories_and_links_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive, _source = make_backup(base)
            values, _manifest = read_archive(archive)
            live = write_required_configuration(base / "live", "live-action")
            attacks = (
                "../manifest.json",
                "/manifest.json",
                r"C:\\manifest.json",
                r"\\server\\share\\manifest.json",
                "payload/data/CON.json",
                "payload/data/bad\\name.json",
                "payload/data/trailing. ",
            )
            for index, name in enumerate(attacks):
                candidate = base / f"attack-{index}.zip"
                write_archive(
                    candidate,
                    [(name, b"{}", zipfile.ZIP_DEFLATED, 0), ("manifest.json", values[-1][1], zipfile.ZIP_DEFLATED, 0)],
                )
                with self.subTest(name=name):
                    with self.assertRaises(RestoreArchiveError):
                        inspect_restore_archive(live, candidate)

            collision = base / "collision.zip"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                write_archive(
                    collision,
                    [
                        ("payload/data/actions.json", b"{}", zipfile.ZIP_DEFLATED, 0),
                        ("PAYLOAD/DATA/ACTIONS.JSON", b"{}", zipfile.ZIP_DEFLATED, 0),
                        ("manifest.json", values[-1][1], zipfile.ZIP_DEFLATED, 0),
                    ],
                )
            with self.assertRaises(RestoreArchiveError):
                inspect_restore_archive(live, collision)

            directory_entry = base / "directory.zip"
            write_archive(
                directory_entry,
                [("payload/", b"", zipfile.ZIP_STORED, 0), ("manifest.json", values[-1][1], zipfile.ZIP_DEFLATED, 0)],
            )
            with self.assertRaises(RestoreArchiveError):
                inspect_restore_archive(live, directory_entry)

            symlink = base / "symlink.zip"
            write_archive(
                symlink,
                [("payload/data/actions.json", b"target", zipfile.ZIP_STORED, 0o120777 << 16), ("manifest.json", values[-1][1], zipfile.ZIP_DEFLATED, 0)],
            )
            with self.assertRaises(RestoreArchiveError):
                inspect_restore_archive(live, symlink)

    def test_truncation_checksum_size_and_limits_are_rejected_privately(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive, _source = make_backup(base)
            live = write_required_configuration(base / "live", "PRIVATE-LIVE")
            truncated = base / "truncated.zip"
            truncated.write_bytes(archive.read_bytes()[:-8])
            with self.assertRaises(RestoreArchiveError) as captured:
                inspect_restore_archive(live, truncated)
            self.assertNotIn(str(base), str(captured.exception))
            self.assertNotIn("PRIVATE-LIVE", str(captured.exception))

            values, manifest = read_archive(archive)
            manifest["entries"][0]["sha256"] = "0" * 64
            mismatch = base / "mismatch.zip"
            write_archive(
                mismatch,
                [
                    (info.filename, payload, zipfile.ZIP_DEFLATED, 0)
                    for info, payload in values[:-1]
                ]
                + [("manifest.json", (json.dumps(manifest) + "\n").encode(), zipfile.ZIP_DEFLATED, 0)],
            )
            with self.assertRaises(RestoreArchiveError):
                inspect_restore_archive(live, mismatch)

            tiny = RestoreLimits(max_archive_bytes=8)
            with self.assertRaises(RestoreLimitError):
                inspect_restore_archive(live, archive, limits=tiny)


class RestoreCommitTests(unittest.TestCase):
    def test_commit_requires_explicit_and_built_in_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive, _source = make_backup(base)
            live = write_required_configuration(base / "live", "live-action")
            plan = inspect_restore_archive(live, archive)
            no = RestoreConfirmation(
                plan.archive.sha256, plan.live_state_sha256, False, False
            )
            with self.assertRaises(RestoreConfirmationError):
                commit_restore(
                    live, archive, plan, no, recovery_directory=base / "recovery"
                )
            missing_built_in = RestoreConfirmation.for_plan(plan)
            with self.assertRaises(RestoreConfirmationError):
                commit_restore(
                    live,
                    archive,
                    plan,
                    missing_built_in,
                    recovery_directory=base / "recovery",
                )

    def test_success_replaces_manifest_files_preserves_omissions_and_unknowns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive, source = make_backup(base)
            live = write_required_configuration(base / "live", "live-action")
            write_json(live.palette_state_file, {})
            unknown = live.data_directory / "unknown-private.json"
            unknown.write_text("PRIVATE UNKNOWN", encoding="utf-8")
            plan = inspect_restore_archive(live, archive)
            result = commit_restore(
                live,
                archive,
                plan,
                RestoreConfirmation.for_plan(plan, built_in_acknowledged=True),
                recovery_directory=base / "recovery",
                now=NOW,
            )

            self.assertEqual(
                live.built_in_actions_file.read_bytes(),
                source.built_in_actions_file.read_bytes(),
            )
            self.assertTrue(live.palette_state_file.exists())
            self.assertEqual(unknown.read_text(encoding="utf-8"), "PRIVATE UNKNOWN")
            self.assertTrue(result.recovery_archive.is_file())
            self.assertFalse(live.restore_journal_file.exists())
            self.assertEqual(list(live.data_directory.glob("*.bak")), [])

    def test_plan_aborts_when_live_state_or_archive_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive, _source = make_backup(base)
            live = write_required_configuration(base / "live", "live-action")
            plan = inspect_restore_archive(live, archive)
            write_json(live.palette_state_file, {})
            with self.assertRaises(RestorePlanStaleError):
                commit_restore(
                    live,
                    archive,
                    plan,
                    RestoreConfirmation.for_plan(plan, built_in_acknowledged=True),
                    recovery_directory=base / "recovery",
                )

    def test_failure_after_each_replacement_rolls_back_all_candidates(self) -> None:
        for failing_index in (1, 2):
            with self.subTest(failing_index=failing_index), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                archive, _source = make_backup(base)
                live = write_required_configuration(base / "live", "live-action")
                before = {
                    live.built_in_actions_file: live.built_in_actions_file.read_bytes(),
                    live.built_in_contexts_file: live.built_in_contexts_file.read_bytes(),
                }
                plan = inspect_restore_archive(live, archive)

                def fail(index: int, _asset_id: str) -> None:
                    if index == failing_index:
                        raise OSError("injected")

                with self.assertRaises(RestoreCommitError) as captured:
                    commit_restore(
                        live,
                        archive,
                        plan,
                        RestoreConfirmation.for_plan(plan, built_in_acknowledged=True),
                        recovery_directory=base / "recovery",
                        now=NOW,
                        test_hooks=RestoreTestHooks(after_replacement=fail),
                    )
                self.assertTrue(captured.exception.rollback_completed)
                for path, payload in before.items():
                    self.assertEqual(path.read_bytes(), payload)
                self.assertFalse(live.restore_journal_file.exists())

    def test_ordinary_failure_after_durable_journal_rolls_back_and_clears_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive, _source = make_backup(base)
            live = write_required_configuration(base / "live", "live-action")
            before = live.built_in_actions_file.read_bytes()
            plan = inspect_restore_archive(live, archive)

            with self.assertRaises(RestoreCommitError) as captured:
                commit_restore(
                    live,
                    archive,
                    plan,
                    RestoreConfirmation.for_plan(plan, built_in_acknowledged=True),
                    recovery_directory=base / "recovery",
                    now=NOW,
                    test_hooks=RestoreTestHooks(
                        after_journal=lambda: (_ for _ in ()).throw(OSError("injected"))
                    ),
                )

            self.assertTrue(captured.exception.rollback_completed)
            self.assertEqual(live.built_in_actions_file.read_bytes(), before)
            self.assertFalse(live.restore_journal_file.exists())

    def test_corrupt_recovery_archive_is_rejected_before_journal_or_live_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive, _source = make_backup(base)
            live = write_required_configuration(base / "live", "live-action")
            before = live.built_in_actions_file.read_bytes()
            plan = inspect_restore_archive(live, archive)
            recovery = base / "recovery"

            def corrupt_recovery() -> None:
                next(recovery.glob("*.zip")).write_bytes(b"corrupt")

            with self.assertRaises(RestoreRecoveryError):
                commit_restore(
                    live,
                    archive,
                    plan,
                    RestoreConfirmation.for_plan(plan, built_in_acknowledged=True),
                    recovery_directory=recovery,
                    now=NOW,
                    test_hooks=RestoreTestHooks(
                        after_recovery_archive=corrupt_recovery
                    ),
                )

            self.assertEqual(live.built_in_actions_file.read_bytes(), before)
            self.assertFalse(live.restore_journal_file.exists())

    def test_preserved_file_interference_prevents_successful_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive, _source = make_backup(base)
            live = write_required_configuration(base / "live", "live-action")
            write_json(live.palette_state_file, {})
            plan = inspect_restore_archive(live, archive)

            def interfere() -> None:
                write_json(live.palette_state_file, {"search": "changed externally"})

            with self.assertRaises(RestoreCommitError) as captured:
                commit_restore(
                    live,
                    archive,
                    plan,
                    RestoreConfirmation.for_plan(plan, built_in_acknowledged=True),
                    recovery_directory=base / "recovery",
                    now=NOW,
                    test_hooks=RestoreTestHooks(before_final_validation=interfere),
                )

            self.assertFalse(captured.exception.rollback_completed)
            self.assertTrue(live.restore_journal_file.exists())

    def test_interruption_leaves_journal_and_startup_recovery_is_idempotent(self) -> None:
        class SimulatedProcessExit(BaseException):
            pass

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive, _source = make_backup(base)
            live = write_required_configuration(base / "live", "live-action")
            before = live.built_in_actions_file.read_bytes()
            plan = inspect_restore_archive(live, archive)

            def interrupt(index: int, _asset_id: str) -> None:
                if index == 1:
                    raise SimulatedProcessExit

            with self.assertRaises(SimulatedProcessExit):
                commit_restore(
                    live,
                    archive,
                    plan,
                    RestoreConfirmation.for_plan(plan, built_in_acknowledged=True),
                    recovery_directory=base / "recovery",
                    now=NOW,
                    test_hooks=RestoreTestHooks(after_replacement=interrupt),
                )
            self.assertTrue(live.restore_journal_file.exists())
            recovered = recover_interrupted_restore(live)
            self.assertTrue(recovered.recovery_performed)
            self.assertEqual(live.built_in_actions_file.read_bytes(), before)
            self.assertFalse(live.restore_journal_file.exists())
            self.assertFalse(recover_interrupted_restore(live).recovery_performed)

    def test_missing_live_required_files_can_be_recovered_without_live_validation(self) -> None:
        class SimulatedProcessExit(BaseException):
            pass

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive, _source = make_backup(base)
            live = AppDataPaths.from_root(base / "live")
            live.data_directory.mkdir(parents=True)
            plan = inspect_restore_archive(live, archive)

            with self.assertRaises(SimulatedProcessExit):
                commit_restore(
                    live,
                    archive,
                    plan,
                    RestoreConfirmation.for_plan(plan, built_in_acknowledged=True),
                    recovery_directory=base / "recovery",
                    now=NOW,
                    test_hooks=RestoreTestHooks(
                        after_replacement=lambda _index, _asset: (_ for _ in ()).throw(
                            SimulatedProcessExit()
                        )
                    ),
                )
            recover_interrupted_restore(live)
            self.assertFalse(live.built_in_actions_file.exists())
            self.assertFalse(live.built_in_contexts_file.exists())


class PersistenceAndCatalogTests(unittest.TestCase):
    def test_exact_byte_replacement_defaults_to_no_adjacent_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.bin"
            path.write_bytes(b"old\r\nbytes")
            atomic_replace_bytes(path, b"new\x00\xffbytes")
            self.assertEqual(path.read_bytes(), b"new\x00\xffbytes")
            self.assertFalse(path.with_name("data.bin.bak").exists())

    def test_restore_journal_is_never_backup_eligible(self) -> None:
        self.assertFalse(is_catalogued_backup_payload("data/restore-journal.json"))


if __name__ == "__main__":
    unittest.main()
