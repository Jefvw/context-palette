from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from context_palette.vscode_integration import (
    VsCodeIntegrationError,
    open_workspace_path_in_vscode,
    vscode_folder_from_workspace,
    vscode_folder_uri,
)


class VsCodeIntegrationTests(unittest.TestCase):
    def test_folder_path_opens_that_folder_and_encodes_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "Project folder"
            folder.mkdir()
            opener = Mock()

            result = open_workspace_path_in_vscode(
                f'"{folder}"',
                opener=opener,
            )

        self.assertEqual(result, folder.resolve())
        opener.assert_called_once_with(vscode_folder_uri(folder.resolve()))
        self.assertIn("Project%20folder", opener.call_args.args[0])
        self.assertTrue(opener.call_args.args[0].endswith("/"))

    def test_file_path_opens_its_containing_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "project"
            folder.mkdir()
            source = folder / "app.py"
            source.write_text("print('hello')", encoding="utf-8")

            result = vscode_folder_from_workspace(str(source))

        self.assertEqual(result, folder.resolve())

    def test_uri_shape_matches_local_and_unc_folder_contracts(self) -> None:
        self.assertEqual(
            vscode_folder_uri(Path(r"C:\work\Project folder")),
            "vscode://file/C:/work/Project%20folder/",
        )
        self.assertEqual(
            vscode_folder_uri(Path(r"\\server\share\Project folder")),
            "vscode://file//server/share/Project%20folder/",
        )

    def test_rejects_empty_multiple_relative_missing_and_unmatched_paths(self) -> None:
        cases = (
            "",
            "C:/one\nC:/two",
            "relative/project",
            "C:/definitely-missing-context-palette-project",
            '"C:/missing',
        )
        for value in cases:
            with self.subTest(value=value), self.assertRaises(VsCodeIntegrationError):
                vscode_folder_from_workspace(value)

    def test_protocol_failure_is_actionable_and_does_not_expose_os_detail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)

            with self.assertRaisesRegex(
                VsCodeIntegrationError,
                "installed.*registered",
            ) as caught:
                open_workspace_path_in_vscode(
                    str(folder),
                    opener=Mock(side_effect=OSError("private registry detail")),
                )

        self.assertNotIn("private", str(caught.exception))

    def test_malformed_path_is_translated_to_product_error(self) -> None:
        with self.assertRaises(VsCodeIntegrationError):
            vscode_folder_from_workspace("C:\\bad\0path")


if __name__ == "__main__":
    unittest.main()
