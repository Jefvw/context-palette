from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.action_suggestions import suggest_action_from_text


class ActionSuggestionTests(unittest.TestCase):
    def test_complete_url_becomes_open_website_suggestion(self) -> None:
        suggestion = suggest_action_from_text(" https://example.com/report?id=7 ")

        self.assertIsNotNone(suggestion)
        assert suggestion is not None
        self.assertEqual(suggestion.action_type, "open_url")
        self.assertEqual(suggestion.title, "Open example.com")
        self.assertEqual(suggestion.value, "https://example.com/report?id=7")

    @unittest.skipUnless(sys.platform == "win32", "Uses Windows path semantics.")
    def test_file_folder_and_executable_paths_use_specific_action_types(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "Quarterly Reports"
            folder.mkdir()
            document = folder / "Quarterly report.pdf"
            document.write_bytes(b"pdf")
            application = folder / "Viewer.EXE"
            application.write_bytes(b"exe")

            file_suggestion = suggest_action_from_text(f'  "{document}"  ')
            folder_suggestion = suggest_action_from_text(str(folder))
            app_suggestion = suggest_action_from_text(str(application))

        self.assertIsNotNone(file_suggestion)
        self.assertIsNotNone(folder_suggestion)
        self.assertIsNotNone(app_suggestion)
        assert file_suggestion and folder_suggestion and app_suggestion
        self.assertEqual(file_suggestion.action_type, "open_file")
        self.assertEqual(file_suggestion.title, "Open Quarterly report.pdf")
        self.assertEqual(file_suggestion.value, str(document))
        self.assertEqual(folder_suggestion.action_type, "open_folder")
        self.assertEqual(folder_suggestion.title, "Open Quarterly Reports")
        self.assertEqual(app_suggestion.action_type, "launch_app")
        self.assertEqual(app_suggestion.title, "Launch Viewer")

    def test_absolute_path_suggestions_do_not_probe_the_filesystem(self) -> None:
        file_suggestion = suggest_action_from_text(r"W:\Unavailable\report.pdf")
        folder_suggestion = suggest_action_from_text(r"W:\Unavailable\Reports")

        self.assertIsNotNone(file_suggestion)
        self.assertIsNotNone(folder_suggestion)
        assert file_suggestion and folder_suggestion
        self.assertEqual(file_suggestion.action_type, "open_file")
        self.assertEqual(folder_suggestion.action_type, "open_folder")

    def test_ambiguous_or_unsupported_text_is_not_guessed(self) -> None:
        for value in (
            "",
            "See https://example.com for details",
            "https://example.com\nhttps://openai.com",
            "relative/report.pdf",
            "mailto:person@example.com",
            '"C:\\Tools\\viewer.exe" --safe',
            r"C:\Tools\run.cmd",
        ):
            with self.subTest(value=value):
                self.assertIsNone(suggest_action_from_text(value))


if __name__ == "__main__":
    unittest.main()
