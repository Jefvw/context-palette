import base64
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from context_palette.chatgpt_auth import (
    ChatGPTAuth, ISSUER, JWKS_URL, LoopbackListener, RESOURCE, SCOPES, TOKEN_URL, validate_callback,
)
from context_palette.chatgpt_http import ChatGPTError


def encoded(payload):
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def identity(nonce="nonce", **changes):
    claims = {"iss": ISSUER, "aud": "oaiapp_test", "sub": "synthetic-subject",
              "exp": 10000, "iat": 1000, "nonce": nonce, "email": "user@example.test"}
    claims.update(changes)
    return encoded({"alg": "RS256", "kid": "synthetic-key"}) + "." + encoded(claims) + "." + encoded(b"s" * 256)


KEYS = {"keys": [{"kty": "RSA", "kid": "synthetic-key", "alg": "RS256", "use": "sig",
                   "n": encoded(b"\x80" + b"n" * 255), "e": encoded(b"\x01\x00\x01")}]}


def token_response(nonce="nonce", **changes):
    result = {"access_token": "synthetic-access-secret", "refresh_token": "synthetic-refresh-secret",
              "id_token": identity(nonce), "token_type": "Bearer", "expires_in": 3600, "scope": SCOPES}
    result.update(changes)
    return result


class FakeHTTP:
    def __init__(self):
        self.calls = []
        self.responses = []

    @contextmanager
    def open(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        result = self.responses.pop(0) if self.responses else KEYS
        if isinstance(result, Exception):
            raise result
        yield io.BytesIO(json.dumps(result).encode())


class FakeListener:
    redirect_uri = "http://127.0.0.1:54321/auth/callback"

    def __init__(self, fixture):
        self.fixture = fixture
        self.closed = False

    def __enter__(self):
        self.fixture.listener_started = True
        return self

    def __exit__(self, *args):
        self.closed = True

    def wait(self, cancel_event, deadline):
        self.fixture.deadline = deadline
        if self.fixture.callback is not None:
            return self.fixture.callback
        state = self.fixture.params["state"][0]
        client = self.fixture.callback_client
        values = {"code": "synthetic-code", "state": state}
        if client is not None:
            values["client_id"] = client
        return "/auth/callback?" + urlencode(values)


class ChatGPTAuthTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "chatgpt.credentials"
        self.http = FakeHTTP()
        self.now = 1000
        self.callback = None
        self.callback_client = "oaiapp_test"
        self.listener_started = False
        self.params = None
        self.response_changes = {}
        self.cancel = threading.Event()
        self.listener = FakeListener(self)
        self.verifies = []
        self.signature_valid = True
        self.auth = self.make_auth()

    def make_auth(self):
        return ChatGPTAuth(self.path, self.http, browser_open=self.browser,
                           listener_factory=lambda: self.listener,
                           protector=lambda data: b"test-only:" + base64.b64encode(data),
                           unprotector=lambda data: base64.b64decode(data.removeprefix(b"test-only:")),
                           signature_verifier=self.verify, clock=lambda: self.now)

    def browser(self, url):
        self.assertTrue(self.listener_started)
        self.params = parse_qs(urlsplit(url).query)
        if not self.http.responses:
            self.http.responses.append(token_response(self.params["nonce"][0], **self.response_changes))
        return True

    def verify(self, modulus, exponent, message, signature):
        self.verifies.append((modulus, exponent, message, signature))
        return self.signature_valid

    def signed_in(self):
        return self.auth.sign_in(self.cancel)

    def expire(self):
        self.now = 4600

    def test_construction_does_not_open_browser_network_or_credential_store(self):
        self.assertEqual(self.http.calls, [])
        self.assertIsNone(self.params)
        self.assertFalse(self.path.exists())
        self.assertIsNone(self.auth.account)

    def test_dynamic_registration_listener_first_pkce_and_exact_token_form(self):
        account = self.signed_in()
        self.assertEqual(account.display_label, "user@example.test")
        self.assertTrue(account.can_use_plan)
        self.assertEqual(self.params["client_id"], ["dynamic_agent_client"])
        self.assertEqual(self.params["agent_name_hint"], ["Context Palette"])
        self.assertEqual(self.params["resource"], [RESOURCE])
        self.assertEqual(self.params["scope"], [SCOPES])
        form = parse_qs(self.http.calls[0][2]["body"].decode())
        self.assertEqual(form["client_id"], ["oaiapp_test"])
        self.assertEqual(form["redirect_uri"], self.params["redirect_uri"])
        challenge = encoded(hashlib.sha256(form["code_verifier"][0].encode()).digest())
        self.assertEqual(self.params["code_challenge"], [challenge])
        self.assertEqual(self.params["code_challenge_method"], ["S256"])
        self.assertTrue(self.listener.closed)
        self.assertEqual(self.http.calls[1][1], JWKS_URL)
        self.assertEqual(len(self.verifies), 1)
        self.assertFalse(self.path.with_name(self.path.name + ".bak").exists())

    def test_scopes_come_from_token_response_and_missing_plan_permission_blocks_access(self):
        self.response_changes["scope"] = "openid profile email"
        account = self.signed_in()
        self.assertFalse(account.can_use_plan)
        with self.assertRaises(ChatGPTError) as caught:
            self.auth.access_token(self.cancel)
        self.assertEqual(caught.exception.code, "permission")
        self.assertEqual(len(self.http.calls), 2)

    def test_no_scope_does_not_infer_requested_permission(self):
        self.response_changes["scope"] = ""
        self.assertFalse(self.signed_in().can_use_plan)

    def test_explicit_reauthorization_after_missing_permission_requests_consent(self):
        self.response_changes["scope"] = "openid profile email"
        self.signed_in()
        self.callback_client = None
        self.signed_in()
        self.assertEqual(self.params["prompt"], ["consent"])
        self.auth.sign_out()
        self.signed_in()
        self.assertEqual(self.params["prompt"], ["consent"])

    def test_forged_state_is_checked_before_access_denied_or_code_exchange(self):
        self.callback = "/auth/callback?state=forged&error=access_denied&code=secret-code&client_id=oaiapp_test"
        with self.assertRaises(ChatGPTError) as caught:
            self.signed_in()
        self.assertEqual(caught.exception.code, "invalid_state")
        self.assertEqual(self.http.calls, [])
        self.assertNotIn("secret-code", str(caught.exception))
        self.assertTrue(self.listener.closed)

    def test_denial_with_valid_state_is_safe(self):
        with self.assertRaises(ChatGPTError) as caught:
            validate_callback("/auth/callback?state=correct&error=access_denied&error_description=secret", "correct", None)
        self.assertEqual(caught.exception.code, "access_denied")
        self.assertNotIn("secret", str(caught.exception))

    def test_new_registration_requires_issued_id(self):
        self.callback_client = None
        with self.assertRaises(ChatGPTError) as caught:
            self.signed_in()
        self.assertEqual(caught.exception.code, "invalid_callback")
        self.assertEqual(self.http.calls, [])

    def test_callback_rejects_duplicate_parameters_bad_paths_and_bad_encoding(self):
        paths = ("/auth/callback?state=s&state=s&code=c&client_id=oaiapp_test",
                 "/callback?state=s&code=c&client_id=oaiapp_test",
                 "/auth/callback?state=s&code=%ZZ&client_id=oaiapp_test",
                 "/auth/callback?state=s&code=%FF&client_id=oaiapp_test",
                 "http://evil.test/auth/callback?state=s&code=c&client_id=oaiapp_test",
                 "/auth/callback?state=s&code=c&client_id=dynamic_agent_client",
                 "/auth/callback?state=s&code=&client_id=oaiapp_test")
        for path in paths:
            with self.subTest(path=path), self.assertRaises(ChatGPTError):
                validate_callback(path, "s", None)

    def test_returning_callback_may_omit_client_but_never_change_it(self):
        self.signed_in()
        old_tokens = self.auth._tokens
        self.callback_client = None
        self.signed_in()
        self.assertEqual(self.params["client_id"], ["oaiapp_test"])
        self.assertNotIn("agent_name_hint", self.params)
        self.assertEqual(self.params["id_token_hint"], [old_tokens.id_token])
        self.assertNotIn("prompt", self.params)
        self.callback_client = "oaiapp_other"
        with self.assertRaises(ChatGPTError) as caught:
            self.signed_in()
        self.assertEqual(caught.exception.code, "identity_mismatch")
        self.assertEqual(self.auth.account.client_id, "oaiapp_test")

    def test_invalid_signature_cannot_create_connection(self):
        self.signature_valid = False
        with self.assertRaises(ChatGPTError) as caught:
            self.signed_in()
        self.assertEqual(caught.exception.code, "invalid_identity")
        self.assertIsNone(self.auth.account)
        self.assertNotIn(b"synthetic-access-secret", self.path.read_bytes())

    def test_identity_validates_issuer_audience_expiry_nonce_and_subject(self):
        failures = ({"iss": "https://evil.test"}, {"aud": "other-client"}, {"exp": 1000},
                    {"nonce": "forged"}, {"sub": ""}, {"iat": 1006}, {"nbf": 1006},
                    {"aud": ["oaiapp_test", "other"]}, {"exp": True})
        for changes in failures:
            with self.subTest(changes=changes), self.assertRaises(ChatGPTError) as caught:
                self.auth._identity(identity(**changes), "oaiapp_test", "nonce")
            self.assertEqual(caught.exception.code, "invalid_identity")

    def test_unsigned_or_algorithm_confused_token_is_rejected_without_verification(self):
        for alg in ("none", "HS256", "RS512"):
            token = encoded({"alg": alg, "kid": "synthetic-key"}) + "." + encoded({}) + "." + encoded(b"sig")
            with self.subTest(alg=alg), self.assertRaises(ChatGPTError):
                self.auth._identity(token, "oaiapp_test", "nonce")
        self.assertEqual(self.verifies, [])

    def test_unknown_key_refreshes_cached_jwks_once(self):
        self.auth._identity(identity(), "oaiapp_test", "nonce")
        self.auth._jwks = []
        self.auth._identity(identity(), "oaiapp_test", "nonce")
        self.assertEqual(len(self.http.calls), 2)

    def test_duplicate_jwt_claims_are_rejected(self):
        token = encoded({"alg": "RS256", "kid": "synthetic-key"}) + "." + encoded(b'{"sub":"one","sub":"two"}') + "." + encoded(b"s" * 256)
        with self.assertRaises(ChatGPTError):
            self.auth._identity(token, "oaiapp_test", "nonce")

    def test_valid_connection_loads_only_protected_store_without_network(self):
        self.signed_in()
        self.http.calls.clear()
        original_read_bytes = Path.read_bytes
        with patch.object(Path, "read_bytes", autospec=True, side_effect=original_read_bytes) as read:
            loaded = self.make_auth()
        read.assert_called_once_with(self.path)
        self.assertEqual(self.http.calls, [])
        self.assertEqual(loaded.host_id, self.auth.host_id)
        self.assertEqual(loaded.account, self.auth.account)
        self.assertEqual(loaded.access_token(self.cancel), "synthetic-access-secret")

    def test_forget_clears_tokens_retains_registration_host_and_never_contacts_network(self):
        self.signed_in()
        host = self.auth.host_id
        self.http.calls.clear()
        self.auth.sign_out()
        self.assertIsNone(self.auth.account)
        self.assertEqual(self.http.calls, [])
        loaded = self.make_auth()
        self.assertIsNone(loaded.account)
        self.assertEqual(loaded.host_id, host)
        self.assertEqual(loaded._registration["client_id"], "oaiapp_test")
        self.callback_client = None
        self.auth.sign_in(self.cancel)
        self.assertEqual(self.params["client_id"], ["oaiapp_test"])
        self.assertNotIn("id_token_hint", self.params)

    def test_refresh_rotates_tokens_expiry_and_scopes_together(self):
        self.signed_in()
        self.expire()
        response = token_response(access_token="new-access", refresh_token="new-refresh")
        response.pop("id_token")
        self.http.responses.append(response)
        self.assertEqual(self.auth.access_token(self.cancel), "new-access")
        form = parse_qs(self.http.calls[-1][2]["body"].decode())
        self.assertEqual(form["grant_type"], ["refresh_token"])
        self.assertEqual(form["refresh_token"], ["synthetic-refresh-secret"])
        self.assertNotIn("scope", form)
        loaded = self.make_auth()
        self.assertEqual(loaded._tokens.refresh_token, "new-refresh")
        self.assertEqual(loaded._tokens.expires_at, 8200)
        self.assertEqual(loaded.access_token(self.cancel), "new-access")

    def test_refresh_new_identity_must_match_registered_account(self):
        self.signed_in()
        self.expire()
        self.http.responses.append(token_response(id_token=identity(self.auth._tokens.nonce, sub="other-account", iat=4600)))
        with self.assertRaises(ChatGPTError) as caught:
            self.auth.access_token(self.cancel)
        self.assertEqual(caught.exception.code, "identity_mismatch")
        self.assertEqual(self.auth.account.subject, "synthetic-subject")

    def test_uncertain_refresh_is_not_replayed_even_after_reload(self):
        self.signed_in()
        self.expire()
        self.http.responses.append(ChatGPTError("timeout", "The ChatGPT connection timed out."))
        with self.assertRaises(ChatGPTError):
            self.auth.access_token(self.cancel)
        calls = len(self.http.calls)
        with self.assertRaises(ChatGPTError) as caught:
            self.auth.access_token(self.cancel)
        self.assertEqual(caught.exception.code, "refresh_uncertain")
        self.assertTrue(self.auth.account.needs_reauthorization)
        self.assertEqual(len(self.http.calls), calls)
        loaded = self.make_auth()
        with self.assertRaises(ChatGPTError) as caught:
            loaded.access_token(self.cancel)
        self.assertEqual(caught.exception.code, "refresh_uncertain")
        self.assertEqual(len(self.http.calls), calls)

    def test_terminal_refresh_failure_forgets_tokens_but_keeps_host_and_client(self):
        self.signed_in()
        host = self.auth.host_id
        self.expire()
        self.http.responses.append(ChatGPTError("refresh_token_reused", "Session expired."))
        with self.assertRaises(ChatGPTError):
            self.auth.access_token(self.cancel)
        self.assertIsNone(self.auth.account)
        loaded = self.make_auth()
        self.assertIsNone(loaded.account)
        self.assertEqual(loaded.host_id, host)
        self.assertEqual(loaded._registration["client_id"], "oaiapp_test")

    def test_refresh_without_scope_disables_plan_usage(self):
        self.signed_in()
        self.expire()
        response = token_response(scope="")
        response.pop("id_token")
        self.http.responses.append(response)
        with self.assertRaises(ChatGPTError) as caught:
            self.auth.access_token(self.cancel)
        self.assertEqual(caught.exception.code, "permission")
        self.assertFalse(self.auth.account.can_use_plan)

    def test_earliest_refresh_time_prevents_early_refresh(self):
        self.response_changes["earliest_refresh_at"] = 4700
        self.signed_in()
        self.now = 4550
        self.assertEqual(self.auth.access_token(self.cancel), "synthetic-access-secret")
        self.now = 4600
        with self.assertRaises(ChatGPTError) as caught:
            self.auth.access_token(self.cancel)
        self.assertEqual(caught.exception.code, "refresh_not_ready")
        self.assertEqual(len(self.http.calls), 2)

    def test_failed_atomic_initial_save_keeps_previous_connection_and_no_tokens_in_errors(self):
        self.signed_in()
        original = self.path.read_bytes()
        with patch("context_palette.chatgpt_auth.atomic_replace_bytes", side_effect=OSError("synthetic-refresh-secret")):
            with self.assertRaises(ChatGPTError) as caught:
                self.auth.sign_in(self.cancel)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertNotIn("synthetic-refresh-secret", repr(caught.exception))
        self.assertIsNotNone(self.auth.account)

    def test_failed_rotation_save_stops_local_use_and_never_retries(self):
        self.signed_in()
        self.expire()
        response = token_response(access_token="new-access", refresh_token="new-refresh")
        response.pop("id_token")
        self.http.responses.append(response)
        with patch("context_palette.chatgpt_auth.atomic_replace_bytes", side_effect=OSError("secret")):
            with self.assertRaises(ChatGPTError):
                self.auth.access_token(self.cancel)
        calls = len(self.http.calls)
        self.assertIsNone(self.auth.account)
        with self.assertRaises(ChatGPTError):
            self.auth.access_token(self.cancel)
        self.assertEqual(len(self.http.calls), calls)

    def test_cancellation_before_sign_in_has_no_effects(self):
        self.cancel.set()
        with self.assertRaises(ChatGPTError) as caught:
            self.signed_in()
        self.assertEqual(caught.exception.code, "cancelled")
        self.assertFalse(self.path.exists())
        self.assertEqual(self.http.calls, [])

    def test_callback_listener_closes_on_cancellation_without_serving(self):
        with patch("context_palette.chatgpt_auth._QuietHTTPServer") as server_type:
            server = server_type.return_value
            server.server_port = 54321
            self.cancel.set()
            with self.assertRaises(ChatGPTError) as caught:
                with LoopbackListener() as listener:
                    listener.wait(self.cancel, 10000)
            self.assertEqual(caught.exception.code, "cancelled")
            server_type.assert_called_once()
            self.assertEqual(server_type.call_args.args[0], ("127.0.0.1", 0))
            server.handle_request.assert_not_called()
            server.server_close.assert_called_once()

    def test_callback_listener_deadline_closes_without_serving(self):
        with patch("context_palette.chatgpt_auth._QuietHTTPServer") as server_type, \
                patch("context_palette.chatgpt_auth.time.monotonic", return_value=181):
            server = server_type.return_value
            server.server_port = 54321
            with self.assertRaises(ChatGPTError) as caught:
                with LoopbackListener() as listener:
                    listener.wait(self.cancel, 180)
            self.assertEqual(caught.exception.code, "sign_in_timeout")
            server.handle_request.assert_not_called()
            server.server_close.assert_called_once()

    def test_fresh_state_nonce_and_pkce_each_attempt(self):
        self.signed_in()
        first = self.params
        self.callback_client = None
        self.signed_in()
        for key in ("state", "nonce", "code_challenge"):
            self.assertNotEqual(first[key], self.params[key])

    def test_token_dataclass_repr_has_no_credentials(self):
        self.signed_in()
        for secret in ("synthetic-access-secret", "synthetic-refresh-secret", self.auth._tokens.id_token):
            self.assertNotIn(secret, repr(self.auth._tokens))
            self.assertNotIn(secret, repr(self.auth.account))
            self.assertNotIn(secret.encode(), self.path.read_bytes())

    def test_plaintext_or_corrupt_store_is_rejected_without_network(self):
        self.path.write_text('{"access_token":"synthetic-secret"}')
        with self.assertRaises(ChatGPTError) as caught:
            self.make_auth()
        self.assertEqual(caught.exception.code, "credential_store")
        self.assertNotIn("synthetic-secret", str(caught.exception))
        self.assertEqual(self.http.calls, [])

    def test_invalid_grant_retains_issued_id_for_next_fresh_attempt(self):
        self.http.responses.append(ChatGPTError("invalid_grant", "Code expired."))
        with self.assertRaises(ChatGPTError):
            self.signed_in()
        first_state = self.params["state"]
        self.callback_client = None
        self.signed_in()
        self.assertEqual(self.params["client_id"], ["oaiapp_test"])
        self.assertNotEqual(self.params["state"], first_state)
        self.assertNotIn("agent_name_hint", self.params)


if __name__ == "__main__":
    unittest.main()
