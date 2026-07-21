from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.ai_guidance import MAX_AI_RESPONSE_CHARACTERS
from context_palette.ai_guidance_window import AIGuidanceWindow


class FakeWindow:
    def clipboard_get(self) -> str:
        return "x" * (MAX_AI_RESPONSE_CHARACTERS + 1)


class FakeResponse:
    def __init__(self) -> None:
        self.delete_calls = 0
        self.insert_calls = 0

    def delete(self, *_args: object) -> None:
        self.delete_calls += 1

    def insert(self, *_args: object) -> None:
        self.insert_calls += 1


class AIGuidanceWindowTests(unittest.TestCase):
    def test_oversized_clipboard_response_does_not_replace_current_text(self):
        guidance = AIGuidanceWindow.__new__(AIGuidanceWindow)
        guidance.window = FakeWindow()
        guidance.response = FakeResponse()

        with patch("context_palette.ai_guidance_window.messagebox.showerror") as error:
            guidance._paste_response()

        self.assertEqual(guidance.response.delete_calls, 0)
        self.assertEqual(guidance.response.insert_calls, 0)
        self.assertEqual(error.call_args.args[0], "AI response is too large")
        self.assertIn("1,000,000 characters", error.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
