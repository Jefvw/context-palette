from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.main import initial_launcher_request


class MainTests(unittest.TestCase):
    def test_bare_first_launch_does_not_replay_show_request(self):
        self.assertIsNone(initial_launcher_request({"command": "show"}))

    def test_first_launch_preserves_integration_parameters(self):
        request = {"command": "show", "context": "Archives", "search": "product"}

        self.assertIs(initial_launcher_request(request), request)


if __name__ == "__main__":
    unittest.main()
