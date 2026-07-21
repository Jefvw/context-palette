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
        self.assertIn("Quick actions", button_guide)
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

    def test_change_guide_is_linked_and_names_current_owners(self):
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        documentation_index = (ROOT / "docs" / "README.md").read_text(
            encoding="utf-8"
        )
        change_guide = (ROOT / "docs" / "CHANGE_GUIDE.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("docs/CHANGE_GUIDE.md", contributing)
        self.assertIn("CHANGE_GUIDE.md", documentation_index)
        for owner in (
            "workspace_transforms.py",
            "workspace_panel.py",
            "action_discovery_panel.py",
            "focus_model.py",
            "configuration_window.py",
            "command_surface.py",
            "persistence.py",
        ):
            self.assertIn(owner, change_guide)
        self.assertIn(r".\develop-context-palette.bat", change_guide)
        self.assertIn("git diff --check", change_guide)

    def test_shortcut_page_is_linked_and_covers_primary_scopes(self):
        documentation_index = (ROOT / "docs" / "README.md").read_text(
            encoding="utf-8"
        )
        shortcuts = (ROOT / "docs" / "SHORTCUTS.md").read_text(encoding="utf-8")

        self.assertIn("SHORTCUTS.md", documentation_index)
        for shortcut in ("F9", "Ctrl+Alt+P", "Ctrl+,", "Alt+A", "Alt+C", "F4"):
            self.assertIn(shortcut, shortcuts)
        self.assertIn("AZERTY", shortcuts)


if __name__ == "__main__":
    unittest.main()
