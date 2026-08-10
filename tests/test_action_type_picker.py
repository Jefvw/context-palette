from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.action_type_picker import (
    ActionTypePickerOption,
    filter_action_type_picker_options,
)


class ActionTypePickerTests(unittest.TestCase):
    def test_filter_matches_label_family_type_and_description_in_catalogue_order(self):
        options = (
            ActionTypePickerOption("copy_text", "Copy text", "Saved content", "Paste text."),
            ActionTypePickerOption("open_url", "Open a website", "Open target", "Open HTTP."),
        )

        self.assertEqual(
            filter_action_type_picker_options(options, "target open_url http"),
            (options[1],),
        )
        self.assertEqual(
            filter_action_type_picker_options(options, ""),
            options,
        )


if __name__ == "__main__":
    unittest.main()
