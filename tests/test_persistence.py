from pathlib import Path
from unittest.mock import patch
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.persistence import atomic_write_json


class PersistenceTests(unittest.TestCase):
    def test_atomic_write_creates_formatted_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"

            atomic_write_json(path, {"items": ["one"]})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"items": ["one"]})
            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))

    def test_replacing_existing_file_preserves_sibling_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text('{"version": 1}', encoding="utf-8")

            atomic_write_json(path, {"version": 2})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"version": 2})
            self.assertEqual(path.with_suffix(".json.bak").read_text(encoding="utf-8"), '{"version": 1}')

    def test_replacing_without_backup_preserves_existing_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            backup = path.with_suffix(".json.bak")
            path.write_text('{"version": 2}', encoding="utf-8")
            backup.write_text('{"version": 1}', encoding="utf-8")

            atomic_write_json(path, {"version": 3}, preserve_previous=False)

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"version": 3})
            self.assertEqual(backup.read_text(encoding="utf-8"), '{"version": 1}')

    def test_replace_failure_keeps_original_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text('{"version": 1}', encoding="utf-8")

            with patch("context_palette.persistence.os.replace", side_effect=OSError("blocked")):
                with self.assertRaises(OSError):
                    atomic_write_json(path, {"version": 2})

            self.assertEqual(path.read_text(encoding="utf-8"), '{"version": 1}')
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_serialization_failure_keeps_original_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text('{"version": 1}', encoding="utf-8")

            with self.assertRaises(TypeError):
                atomic_write_json(path, {"invalid": object()})

            self.assertEqual(path.read_text(encoding="utf-8"), '{"version": 1}')
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
