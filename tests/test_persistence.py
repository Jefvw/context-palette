from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import json
import os
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.persistence import atomic_replace_bytes, atomic_write_json


JSON_PAYLOAD = {
    "z-last": "caf\u00e9 \U0001f600",
    "nested": {"enabled": True, "empty": None, "values": [1, -2, 3.5, 'line\n"quoted"\\']},
    "a-first": [],
}
JSON_BYTES = (
    b'{\n'
    b'  "z-last": "caf\\u00e9 \\ud83d\\ude00",\n'
    b'  "nested": {\n'
    b'    "enabled": true,\n'
    b'    "empty": null,\n'
    b'    "values": [\n'
    b'      1,\n'
    b'      -2,\n'
    b'      3.5,\n'
    b'      "line\\n\\"quoted\\"\\\\"\n'
    b'    ]\n'
    b'  },\n'
    b'  "a-first": []\n'
    b'}\n'
)
BINARY_BYTES = b"\x00\xff\x80\r\n\n\x1aexact bytes\x00"
ORIGINAL_BYTES = b'{"version": 1}\r\n'
BACKUP_BYTES = b"older backup\x00\xff"


class TrackingTemporaryFile:
    """Track publication milestones while retaining a real temporary file."""

    def __init__(self, temporary, events):
        self.temporary = temporary
        self.events = events
        self.name = temporary.name

    def __enter__(self):
        self.temporary.__enter__()
        return self

    def __exit__(self, *args):
        result = self.temporary.__exit__(*args)
        self.events.append("closed")
        return result

    def write(self, value):
        return self.temporary.write(value)

    def flush(self):
        self.events.append("flush")
        self.temporary.flush()

    def fileno(self):
        return self.temporary.fileno()


class PersistenceTests(unittest.TestCase):
    def writers(self):
        return (
            ("json", atomic_write_json, JSON_PAYLOAD, JSON_BYTES),
            ("bytes", atomic_replace_bytes, BINARY_BYTES, BINARY_BYTES),
        )

    def existing_files(self, directory):
        path = Path(directory) / "data.payload"
        backup = path.with_name(path.name + ".bak")
        path.write_bytes(ORIGINAL_BYTES)
        backup.write_bytes(BACKUP_BYTES)
        return path, backup

    def assert_only_expected_files(self, path, expected_bytes, expected_backup):
        self.assertEqual(path.read_bytes(), expected_bytes)
        backup = path.with_name(path.name + ".bak")
        if expected_backup is None:
            self.assertFalse(backup.exists())
            expected_files = [path]
        else:
            self.assertEqual(backup.read_bytes(), expected_backup)
            expected_files = [path, backup]
        self.assertCountEqual(list(path.parent.iterdir()), expected_files)

    def test_atomic_write_creates_formatted_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "data.json"

            atomic_write_json(path, JSON_PAYLOAD)

            self.assert_only_expected_files(path, JSON_BYTES, None)

    def test_atomic_replace_bytes_creates_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "data.bin"

            atomic_replace_bytes(path, BINARY_BYTES)

            self.assert_only_expected_files(path, BINARY_BYTES, None)

    def test_new_files_do_not_create_backups_when_requested(self):
        for name, writer, payload, expected_bytes in self.writers():
            with self.subTest(writer=name), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "data.payload"

                writer(path, payload, preserve_previous=True)

                self.assert_only_expected_files(path, expected_bytes, None)

    def test_default_backup_policies(self):
        for name, writer, payload, expected_bytes in self.writers():
            with self.subTest(writer=name), tempfile.TemporaryDirectory() as directory:
                path, _ = self.existing_files(directory)

                writer(path, payload)

                expected_backup = ORIGINAL_BYTES if name == "json" else BACKUP_BYTES
                self.assert_only_expected_files(path, expected_bytes, expected_backup)

    def test_replacing_existing_file_preserves_sibling_backup(self):
        for name, writer, payload, expected_bytes in self.writers():
            with self.subTest(writer=name), tempfile.TemporaryDirectory() as directory:
                path, _ = self.existing_files(directory)

                writer(path, payload, preserve_previous=True)

                self.assert_only_expected_files(path, expected_bytes, ORIGINAL_BYTES)

    def test_replacing_without_backup_preserves_existing_backup(self):
        for name, writer, payload, expected_bytes in self.writers():
            for existing_backup in (False, True):
                with self.subTest(writer=name, existing_backup=existing_backup):
                    with tempfile.TemporaryDirectory() as directory:
                        path, backup = self.existing_files(directory)
                        if not existing_backup:
                            backup.unlink()

                        writer(path, payload, preserve_previous=False)

                        expected_backup = BACKUP_BYTES if existing_backup else None
                        self.assert_only_expected_files(path, expected_bytes, expected_backup)

    def test_replace_failure_keeps_original_and_removes_temporary_file(self):
        for name, writer, payload, _ in self.writers():
            for preserve_previous in (False, True):
                with self.subTest(writer=name, preserve_previous=preserve_previous):
                    with tempfile.TemporaryDirectory() as directory:
                        path, _ = self.existing_files(directory)

                        with patch("context_palette.persistence.os.replace", side_effect=OSError("blocked")):
                            with self.assertRaisesRegex(OSError, "blocked"):
                                writer(path, payload, preserve_previous=preserve_previous)

                        expected_backup = ORIGINAL_BYTES if preserve_previous else BACKUP_BYTES
                        self.assert_only_expected_files(path, ORIGINAL_BYTES, expected_backup)

    def test_serialization_failure_keeps_original_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _ = self.existing_files(directory)

            with patch("context_palette.persistence.shutil.copy2") as copy_previous:
                with patch("context_palette.persistence.os.replace") as replace:
                    with self.assertRaises(TypeError):
                        atomic_write_json(path, {"valid": [1, 2], "invalid": object()})

            copy_previous.assert_not_called()
            replace.assert_not_called()
            self.assert_only_expected_files(path, ORIGINAL_BYTES, BACKUP_BYTES)

    def test_json_serialization_runs_under_gate_after_temporary_creation(self):
        real_dump = json.dump
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "data.json"
            self.assertFalse(path.parent.exists())
            gate_active = False

            @contextmanager
            def tracked_gate():
                nonlocal gate_active
                gate_active = True
                try:
                    yield
                finally:
                    gate_active = False

            def observed_dump(data, stream, *args, **kwargs):
                self.assertTrue(gate_active)
                self.assertTrue(path.parent.is_dir())
                temporary_path = Path(stream.name)
                self.assertEqual(temporary_path.parent, path.parent)
                self.assertNotEqual(temporary_path, path)
                self.assertTrue(temporary_path.is_file())
                return real_dump(data, stream, *args, **kwargs)

            with patch("context_palette.persistence.configuration_mutation_gate", tracked_gate):
                with patch("context_palette.persistence.json.dump", side_effect=observed_dump) as dump:
                    with self.assertRaises(TypeError):
                        atomic_write_json(path, {"valid": [1, 2], "invalid": object()})

            dump.assert_called_once()
            self.assertFalse(gate_active)
            self.assertFalse(path.exists())
            self.assertEqual(list(path.parent.iterdir()), [])

    def test_fsync_failure_keeps_original_and_backup_and_removes_temporary_file(self):
        for name, writer, payload, _ in self.writers():
            with self.subTest(writer=name), tempfile.TemporaryDirectory() as directory:
                path, _ = self.existing_files(directory)

                with patch("context_palette.persistence.os.fsync", side_effect=OSError("flush failed")):
                    with patch("context_palette.persistence.shutil.copy2") as copy_previous:
                        with patch("context_palette.persistence.os.replace") as replace:
                            with self.assertRaisesRegex(OSError, "flush failed"):
                                writer(path, payload, preserve_previous=True)

                copy_previous.assert_not_called()
                replace.assert_not_called()
                self.assert_only_expected_files(path, ORIGINAL_BYTES, BACKUP_BYTES)

    def test_backup_failure_keeps_original_and_removes_temporary_file(self):
        def fail_during_copy(source, destination):
            Path(destination).write_bytes(b"partial backup")
            raise OSError("backup failed")

        for name, writer, payload, _ in self.writers():
            with self.subTest(writer=name), tempfile.TemporaryDirectory() as directory:
                path, _ = self.existing_files(directory)

                with patch("context_palette.persistence.shutil.copy2", side_effect=fail_during_copy):
                    with patch("context_palette.persistence.os.replace") as replace:
                        with self.assertRaisesRegex(OSError, "backup failed"):
                            writer(path, payload, preserve_previous=True)

                replace.assert_not_called()
                self.assert_only_expected_files(path, ORIGINAL_BYTES, b"partial backup")

    def test_invalid_byte_payloads_do_not_enter_gate_or_change_files(self):
        for payload in ("text", bytearray(b"bytes"), memoryview(b"bytes"), None, 1):
            with self.subTest(payload_type=type(payload).__name__):
                with tempfile.TemporaryDirectory() as directory:
                    path, _ = self.existing_files(directory)
                    with patch("context_palette.persistence.configuration_mutation_gate") as gate:
                        with patch("context_palette.persistence.tempfile.NamedTemporaryFile") as temporary:
                            with self.assertRaisesRegex(TypeError, "payload must be bytes"):
                                atomic_replace_bytes(path, payload, preserve_previous=True)

                    gate.assert_not_called()
                    temporary.assert_not_called()
                    self.assert_only_expected_files(path, ORIGINAL_BYTES, BACKUP_BYTES)

    def test_public_writers_hold_gate_through_ordered_publication(self):
        real_temporary_file = tempfile.NamedTemporaryFile
        real_fsync = os.fsync
        real_copy = shutil.copy2
        real_replace = os.replace

        for name, writer, payload, expected_bytes in self.writers():
            with self.subTest(writer=name), tempfile.TemporaryDirectory() as directory:
                path, _ = self.existing_files(directory)
                events = []
                gate_active = False

                @contextmanager
                def tracked_gate():
                    nonlocal gate_active
                    self.assertFalse(gate_active)
                    events.append("gate entered")
                    gate_active = True
                    try:
                        yield
                    finally:
                        gate_active = False
                        events.append("gate exited")

                def tracked_temporary_file(*args, **kwargs):
                    self.assertTrue(gate_active)
                    temporary = real_temporary_file(*args, **kwargs)
                    self.assertEqual(Path(temporary.name).parent, path.parent)
                    return TrackingTemporaryFile(temporary, events)

                def tracked_fsync(descriptor):
                    self.assertTrue(gate_active)
                    events.append("fsync")
                    real_fsync(descriptor)

                def tracked_copy(source, destination):
                    self.assertTrue(gate_active)
                    events.append("backup")
                    return real_copy(source, destination)

                def tracked_replace(source, destination):
                    self.assertTrue(gate_active)
                    events.append("replace")
                    return real_replace(source, destination)

                with patch("context_palette.persistence.configuration_mutation_gate", tracked_gate):
                    with patch("context_palette.persistence.tempfile.NamedTemporaryFile", tracked_temporary_file):
                        with patch("context_palette.persistence.os.fsync", tracked_fsync):
                            with patch("context_palette.persistence.shutil.copy2", tracked_copy):
                                with patch("context_palette.persistence.os.replace", tracked_replace):
                                    writer(path, payload, preserve_previous=True)

                self.assertEqual(
                    events,
                    ["gate entered", "flush", "fsync", "closed", "backup", "replace", "gate exited"],
                )
                self.assert_only_expected_files(path, expected_bytes, ORIGINAL_BYTES)


if __name__ == "__main__":
    unittest.main()
