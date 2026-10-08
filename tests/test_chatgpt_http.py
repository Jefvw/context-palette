from contextlib import contextmanager
import io
from http.client import IncompleteRead
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from context_palette.chatgpt_http import (
    ChatGPTError, HTTPSClient, _NoRedirects, classify_http_error, read_json, request_json,
)


class ChatGPTHTTPTests(unittest.TestCase):
    def test_only_trusted_https_hosts_without_credentials_or_custom_ports(self):
        opener = Mock()
        client = HTTPSClient(opener=opener)
        for url in ("http://auth.openai.com/token", "https://evil.example/token",
                    "https://auth.openai.com.evil.example/token", "https://user@auth.openai.com/token",
                    "https://api.openai.com:444/v1/models", "https://auth.openai.com/token#fragment"):
            with self.subTest(url=url):
                with self.assertRaises(ChatGPTError) as caught:
                    with client.open("GET", url):
                        pass
                self.assertEqual(caught.exception.code, "invalid_endpoint")
        opener.open.assert_not_called()

    def test_tls_request_preserves_headers_and_closes_stream(self):
        response = io.BytesIO(b'{}')
        opener = Mock()
        opener.open.return_value = response
        with HTTPSClient(opener=opener).open("POST", "https://api.openai.com/v1/responses",
                                           headers={"Authorization": "Bearer synthetic-secret"}, body=b'{}') as stream:
            self.assertIs(stream, response)
        self.assertTrue(response.closed)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-secret")
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 15)

    def test_redirect_handler_never_follows_even_same_host(self):
        self.assertIsNone(_NoRedirects().redirect_request(None, None, 302, "", {}, "https://auth.openai.com/other"))

    def test_error_messages_never_include_raw_remote_text_or_credentials(self):
        secret = "synthetic-access-token-DO-NOT-LEAK"
        for payload in ({"error": {"code": secret, "message": secret}}, {"detail": secret}, {"error": secret}):
            with self.subTest(payload=payload):
                error = classify_http_error(403, payload, {"x-request-id": secret})
                self.assertNotIn(secret, str(error))
                self.assertNotIn(secret, repr(error))
                self.assertIsNone(error.request_id)
                self.assertEqual(error.status, 403)

    def test_usage_limit_and_terminal_refresh_codes_are_classified(self):
        error = classify_http_error(429, {"error": {"code": "subscription_sharing_usage_limit_exceeded"}},
                                    {"x-request-id": "req_synthetic123"})
        self.assertEqual(error.code, "usage_limit")
        self.assertEqual(error.request_id, "req_synthetic123")
        for code in ("invalid_grant", "refresh_token_reused", "invalid_client"):
            self.assertEqual(classify_http_error(400, {"error": code}).code, code)

    def test_http_error_body_is_bounded_and_closed(self):
        secret = "secret-diagnostic"
        failure = HTTPError("https://auth.openai.com/token", 400, secret, {},
                            io.BytesIO(json.dumps({"error": "invalid_grant", "error_description": secret}).encode()))
        opener = Mock()
        opener.open.side_effect = failure
        with self.assertRaises(ChatGPTError) as caught:
            with HTTPSClient(opener=opener).open("POST", "https://auth.openai.com/token"):
                pass
        self.assertEqual(caught.exception.code, "invalid_grant")
        self.assertNotIn(secret, str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(failure.fp.closed)

    def test_network_failure_does_not_expose_url_or_exception_message(self):
        opener = Mock()
        opener.open.side_effect = URLError("synthetic-token-in-network-error")
        with self.assertRaises(ChatGPTError) as caught:
            with HTTPSClient(opener=opener).open("GET", "https://api.openai.com/v1/models"):
                pass
        self.assertEqual(caught.exception.code, "connection")
        self.assertNotIn("synthetic-token", repr(caught.exception))

    def test_json_reader_rejects_oversized_invalid_and_non_object_payloads(self):
        for payload, expected in ((b'x' * 101, "response_too_large"), (b'[]', "invalid_response"),
                                  (b'not-json-secret', "invalid_response"), (b'\xff', "invalid_response")):
            with self.subTest(payload=payload):
                with self.assertRaises(ChatGPTError) as caught:
                    read_json(io.BytesIO(payload), max_bytes=100)
                self.assertEqual(caught.exception.code, expected)

    def test_read_timeout_is_sanitized(self):
        response = Mock(spec=["read"])
        response.read.side_effect = socket.timeout("secret")
        with self.assertRaises(ChatGPTError) as caught:
            read_json(response)
        self.assertEqual(caught.exception.code, "timeout")
        self.assertNotIn("secret", str(caught.exception))

    def test_slow_drip_json_response_is_bounded_by_deadline(self):
        response = Mock(spec=["read1"])
        response.read1.return_value = b" "
        with patch("context_palette.chatgpt_http.time.monotonic", side_effect=[0, 0, 5, 10, 15]):
            with self.assertRaises(ChatGPTError) as caught:
                read_json(response, timeout=15)
        self.assertEqual(caught.exception.code, "timeout")
        self.assertEqual(response.read1.call_count, 3)

    def test_truncated_http_response_is_sanitized(self):
        response = Mock(spec=["read"])
        response.read.side_effect = IncompleteRead(b"synthetic-secret")
        with self.assertRaises(ChatGPTError) as caught:
            read_json(response)
        self.assertEqual(caught.exception.code, "connection")
        self.assertNotIn("synthetic-secret", str(caught.exception))

    def test_request_json_uses_supplied_transport(self):
        class Transport:
            @contextmanager
            def open(self, method, url, **kwargs):
                self.call = method, url, kwargs
                yield io.BytesIO(b'{"ok":true}')
        http = Transport()
        self.assertEqual(request_json(http, "GET", "https://api.openai.com/v1/models"), {"ok": True})
        self.assertEqual(http.call[0], "GET")


if __name__ == "__main__":
    unittest.main()
