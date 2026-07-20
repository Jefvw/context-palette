from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DocumentationNavigationTests(unittest.TestCase):
    def test_primary_configuration_guides_name_current_entry_routes(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        context_guide = (
            ROOT / "docs" / "CONTEXT_CONFIGURATION.md"
        ).read_text(encoding="utf-8")
        button_guide = (
            ROOT / "docs" / "COMMAND_SURFACE_CONFIGURATION.md"
        ).read_text(encoding="utf-8")
        help_document = (ROOT / "docs" / "HELP.md").read_text(encoding="utf-8")

        self.assertIn("Ctrl+,", readme)
        self.assertIn("Manage focus → Configure actions and buttons", readme)
        self.assertIn("Ctrl+,", context_guide)
        self.assertIn("Manage focus", context_guide)
        self.assertIn("Ctrl+,", button_guide)
        self.assertIn(
            "Manage focus → Configure actions and buttons",
            button_guide,
        )
        self.assertIn("Right-side buttons", button_guide)
        self.assertIn("press `Ctrl+,`, then open **Actions**", help_document)
        self.assertIn(
            "Manage focus → Configure actions and buttons",
            help_document,
        )
        self.assertIn(
            "Press `Ctrl+,`, then choose **Built-in action types",
            help_document,
        )
        self.assertNotIn("Configure >", help_document)
        self.assertNotIn("Configure →", help_document)


if __name__ == "__main__":
    unittest.main()
