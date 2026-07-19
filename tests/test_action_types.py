from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.action_types import ACTION_TYPES, SUPPORTED_ACTION_TYPES, render_action_type_overview


class ActionTypeCatalogueTests(unittest.TestCase):
    def test_catalogue_covers_every_supported_action_type(self):
        self.assertEqual(set(ACTION_TYPES), SUPPORTED_ACTION_TYPES)
        self.assertEqual(len(ACTION_TYPES), 11)

    def test_every_definition_has_user_and_ai_adaptation_metadata(self):
        for action_type, definition in ACTION_TYPES.items():
            with self.subTest(action_type=action_type):
                self.assertEqual(definition.id, action_type)
                self.assertTrue(definition.label)
                self.assertTrue(definition.family)
                self.assertTrue(definition.description)
                self.assertTrue(definition.required_fields)
                self.assertTrue(definition.input_description)
                self.assertTrue(definition.output_description)
                self.assertTrue(definition.portability)

    def test_first_ai_enabled_types_are_copy_text_and_open_url(self):
        enabled = {item.id for item in ACTION_TYPES.values() if item.ai_proposable}

        self.assertEqual(enabled, {"copy_text", "open_url"})
        self.assertIn("HTTP", ACTION_TYPES["open_url"].ai_guidance)
        self.assertIn("untrusted", ACTION_TYPES["copy_text"].ai_guidance)

    def test_documented_overview_matches_the_catalogue(self):
        documented = (ROOT / "docs" / "ACTION_TYPES.md").read_text(encoding="utf-8")

        self.assertEqual(documented, render_action_type_overview())


if __name__ == "__main__":
    unittest.main()
