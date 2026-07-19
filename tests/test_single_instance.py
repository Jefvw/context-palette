import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.main import integration_request, project_port
from context_palette.single_instance import (
    CLIENT_RECEIVE_TIMEOUT_SECONDS,
    MESSAGE_SHOW,
    decode_request,
    encode_request,
    notify_existing_instance,
    receive_request,
)


class SingleInstanceTests(unittest.TestCase):
    def test_receive_request_times_out_stalled_client(self):
        class StalledClient:
            def __init__(self):
                self.timeout = None

            def settimeout(self, value):
                self.timeout = value

            def recv(self, _size):
                raise TimeoutError

        client = StalledClient()

        self.assertIsNone(receive_request(client))
        self.assertEqual(client.timeout, CLIENT_RECEIVE_TIMEOUT_SECONDS)

    def test_receive_request_decodes_valid_bounded_message(self):
        class FakeClient:
            def __init__(self, message):
                self.message = message
                self.timeout = None

            def settimeout(self, value):
                self.timeout = value

            def recv(self, size):
                return self.message[:size]

        request = {"command": "show", "search": "SQL"}
        client = FakeClient(encode_request(request))

        self.assertEqual(receive_request(client), request)
        self.assertEqual(client.timeout, CLIENT_RECEIVE_TIMEOUT_SECONDS)

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

    def test_notify_existing_instance_sends_structured_request(self):
        sent = []

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def sendall(self, message):
                sent.append(message)

        request = {"command": "show", "search": "window layout"}
        with patch("context_palette.single_instance.socket.create_connection", return_value=FakeClient()):
            self.assertTrue(notify_existing_instance(request=request))
        self.assertEqual(decode_request(sent[0]), request)

    def test_integration_request_supports_context_and_search(self):
        self.assertEqual(
            integration_request(["--context", "Database", "--search", "SQL template"]),
            {"command": "show", "context": "Database", "search": "SQL template"},
        )

    @patch.dict("context_palette.main.os.environ", {"CONTEXT_PALETTE_CONTEXT": "Email"})
    def test_integration_request_supports_wrapper_environment(self):
        self.assertEqual(integration_request([]), {"command": "show", "context": "Email"})

    def test_integration_protocol_rejects_unknown_fields(self):
        with self.assertRaises(ValueError):
            encode_request({"command": "show", "run": "action-id"})
        self.assertIsNone(decode_request(b'{"command":"run"}'))

    def test_project_port_is_stable_for_path(self):
        first = project_port(Path("C:/Project"))
        second = project_port(Path("C:/Project"))

        self.assertEqual(first, second)
        self.assertGreaterEqual(first, 49152)


if __name__ == "__main__":
    unittest.main()
