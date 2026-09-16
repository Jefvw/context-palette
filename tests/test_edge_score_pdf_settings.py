from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.edge_score_pdf_settings import (
    EdgeScorePdfSettingsError,
    load_edge_score_pdf_folder,
    save_edge_score_pdf_folder,
)


class EdgeScorePdfSettingsTests(unittest.TestCase):
    def test_missing_empty_and_absolute_folder_round_trip_without_probing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / "settings.json"
            folder = Path(directory) / "not-created-yet"

            self.assertIsNone(load_edge_score_pdf_folder(settings))
            save_edge_score_pdf_folder(settings, folder)
            self.assertEqual(
                json.loads(settings.read_text(encoding="utf-8")),
                {"destination_folder": str(folder)},
            )
            self.assertEqual(load_edge_score_pdf_folder(settings), folder)
            save_edge_score_pdf_folder(settings, None)
            self.assertIsNone(load_edge_score_pdf_folder(settings))

    def test_load_rejects_noncanonical_or_relative_documents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / "settings.json"
            invalid = (
                {},
                {"destination_folder": None},
                {"destination_folder": "relative"},
                {"destination_folder": str(Path(directory)), "extra": "value"},
            )
            for document in invalid:
                with self.subTest(document=document):
                    settings.write_text(json.dumps(document), encoding="utf-8")
                    with self.assertRaises(EdgeScorePdfSettingsError):
                        load_edge_score_pdf_folder(settings)

    def test_save_rejects_a_relative_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(EdgeScorePdfSettingsError):
                save_edge_score_pdf_folder(Path(directory) / "settings.json", Path("relative"))


if __name__ == "__main__":
    unittest.main()
