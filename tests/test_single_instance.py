import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.main import project_port
from context_palette.single_instance import MESSAGE_SHOW, notify_existing_instance


class SingleInstanceTests(unittest.TestCase):
    def test_notify_existing_instance_returns_false_when_connection_fails(self):
        with patch("context_palette.single_instance.socket.create_connection", side_effect=OSError):
            self.assertFalse(notify_existing_instance())

    def test_notify_existing_instance_sends_show_message(self):
        sent = []

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def sendall(self, message):
                sent.append(message)

        with patch("context_palette.single_instance.socket.create_connection", return_value=FakeClient()):
            self.assertTrue(notify_existing_instance())

        self.assertEqual(sent, [MESSAGE_SHOW])

    def test_project_port_is_stable_for_path(self):
        first = project_port(Path("C:/Project"))
        second = project_port(Path("C:/Project"))

        self.assertEqual(first, second)
        self.assertGreaterEqual(first, 49152)


if __name__ == "__main__":
    unittest.main()
