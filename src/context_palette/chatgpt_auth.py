"""Attended public-client Sign in with ChatGPT for one selected registration.

The session worker owns this manager. Construction reads only its supplied
protected store; it performs no network, browser, clipboard or app discovery.
"""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass, field
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit
import uuid
import webbrowser

from .chatgpt_http import ChatGPTError, HTTPSClient, request_json
from .chatgpt_windows import protect_credentials, unprotect_credentials, verify_rs256
from .persistence import atomic_replace_bytes


ISSUER = "https://auth.openai.com"
AUTHORIZE_URL = ISSUER + "/api/accounts/authorize"
TOKEN_URL = ISSUER + "/api/accounts/oauth/token"
JWKS_URL = ISSUER + "/.well-known/jwks.json"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
_MAGIC = b"ContextPaletteChatGPT-DPAPI-v1\x00"
_MAX_STORE = 524288
_TERMINAL_REFRESH = frozenset({"invalid_grant", "invalid_refresh_token", "token_expired",
                              "refresh_token_expired", "refresh_token_invalidated", "refresh_token_reused"})


def _text(value, limit=65536):
    return isinstance(value, str) and 0 < len(value) <= limit and not any(ord(c) < 32 for c in value)


def _label(value):
    if not isinstance(value, str):
        return "ChatGPT account"
    cleaned = "".join(c for c in value if c.isprintable())[:160].strip()
    return cleaned or "ChatGPT account"


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _decode(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError()
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


@dataclass(frozen=True)
class ChatGPTAccount:
    display_label: str
    can_use_plan: bool
    client_id: str = field(repr=False)
    subject: str = field(repr=False)
    needs_reauthorization: bool = False


@dataclass(frozen=True, repr=False)
class _Tokens:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    id_token: str = field(repr=False)
    expires_at: float = field(repr=False)
    scopes: tuple[str, ...] = field(repr=False)
    nonce: str = field(repr=False)
    earliest_refresh_at: float = field(default=0, repr=False)


class _QuietHTTPServer(HTTPServer):
    allow_reuse_address = False

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(1)
        return connection, address

    def handle_error(self, request, client_address):
        # Base implementation prints a traceback, including callback material.
        pass


class LoopbackListener:
    """One bounded callback on an ephemeral IPv4 loopback listener."""

    def __init__(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def send_error(self, code, message=None, explain=None):
                # Avoid the base handler's reflection of malformed request text.
                super().send_error(code, "Request refused.", "Return to Context Palette.")

            def do_GET(self):
                if self.client_address[0] != "127.0.0.1":
                    self.send_error(400)
                    return
                try:
                    parts = urlsplit(self.path)
                    valid_path = (parts.path == "/auth/callback" and not parts.scheme
                                  and not parts.netloc and not parts.fragment)
                except ValueError:
                    valid_path = False
                if not valid_path:
                    self.send_error(404)
                    return
                if len(self.path) > 8192 or self.headers.get("Host") != owner.host:
                    owner.result = ChatGPTError("invalid_callback", "The ChatGPT sign-in callback was invalid.")
                    self.send_error(400)
                    return
                owner.result = self.path
                content = (b"<!doctype html><meta charset=utf-8><title>Context Palette</title>"
                           b"<p>Sign-in response received. Return to Context Palette to review the result.</p>"
                           b"<p>No text has been sent to ChatGPT.</p>")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy", "default-src 'none'")
                self.end_headers()
                self.wfile.write(content)

        try:
            self._server = _QuietHTTPServer(("127.0.0.1", 0), Handler)
        except OSError:
            raise ChatGPTError("callback_listener", "Context Palette could not open the local sign-in callback.") from None
        self._server.timeout = 0.2
        self.host = f"127.0.0.1:{self._server.server_port}"
        self.redirect_uri = f"http://{self.host}/auth/callback"
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._server.server_close()

    def wait(self, cancel_event, deadline):
        while self.result is None:
            if cancel_event.is_set():
                raise ChatGPTError("cancelled", "ChatGPT sign-in was cancelled.")
            if time.monotonic() >= deadline:
                raise ChatGPTError("sign_in_timeout", "ChatGPT sign-in timed out. Start a new sign-in when ready.")
            self._server.handle_request()
        if isinstance(self.result, ChatGPTError):
            raise self.result
        return self.result


def validate_callback(path: str, state: str, existing_client_id: str | None) -> tuple[str, str]:
    """Validate state before interpreting OAuth errors or accepting a code."""
    try:
        if len(path) > 8192 or re.search(r"%(?![0-9A-Fa-f]{2})", path):
            raise ValueError()
        parts = urlsplit(path)
        if parts.path != "/auth/callback" or parts.scheme or parts.netloc or parts.fragment:
            raise ValueError()
        query = parse_qs(parts.query, keep_blank_values=True, strict_parsing=True,
                         errors="strict", max_num_fields=20)
        if any(len(values) != 1 for values in query.values()):
            raise ValueError()
        returned_state = query.get("state", [""])[0]
        if not returned_state or not secrets.compare_digest(returned_state, state):
            raise ChatGPTError("invalid_state", "The ChatGPT sign-in response could not be verified. Start a new sign-in.")
        if "error" in query:
            if query["error"][0] == "access_denied":
                raise ChatGPTError("access_denied", "ChatGPT sign-in or plan permission was declined.")
            raise ChatGPTError("authorization_failed", "ChatGPT sign-in could not be completed. Start a new sign-in.")
        code = query.get("code", [""])[0]
        client_id = query.get("client_id", [existing_client_id or ""])[0]
        if not _text(code, 4096) or not _text(client_id, 512) or client_id == "dynamic_agent_client":
            raise ValueError()
        if existing_client_id and client_id != existing_client_id:
            raise ChatGPTError("identity_mismatch", "ChatGPT returned a different registration. The saved connection was kept.")
        return code, client_id
    except ChatGPTError:
        raise
    except (ValueError, TypeError, UnicodeError):
        raise ChatGPTError("invalid_callback", "The ChatGPT sign-in callback was invalid. Start a new sign-in.") from None


class ChatGPTAuth:
    """Protected registration and renewable tokens, owned by the session worker."""

    def __init__(self, settings_path, http=None, *, browser_open=None, listener_factory=None,
                 protector=None, unprotector=None, signature_verifier=None,
                 clock=None, monotonic=None, random_value=None):
        self.settings_path = Path(settings_path)
        self._http = http or HTTPSClient()
        self._browser_open = browser_open or webbrowser.open
        self._listener_factory = listener_factory or LoopbackListener
        self._protect = protector or protect_credentials
        self._unprotect = unprotector or unprotect_credentials
        self._verify_signature = signature_verifier or verify_rs256
        self._clock = clock or time.time
        self._monotonic = monotonic or time.monotonic
        self._random = random_value or (lambda: secrets.token_urlsafe(32))
        self._lock = threading.RLock()
        self._host_id = "urn:uuid:" + str(uuid.uuid4())
        self._registration = None
        self._tokens = None
        self._refresh_blocked = False
        self._pending_client_id = None
        self._jwks = None
        self._jwks_expires = 0
        self._load()

    @property
    def account(self):
        with self._lock:
            if self._registration is None or self._tokens is None:
                return None
            return ChatGPTAccount(_label(self._registration.get("email")),
                                  "chatgpt.tokens.use.direct" in self._tokens.scopes,
                                  self._registration["client_id"], self._registration["subject"],
                                  self._refresh_blocked or (self._tokens.expires_at <= self._clock()
                                                           and not self._tokens.refresh_token))

    @property
    def host_id(self):
        return self._host_id

    def _load(self):
        if not self.settings_path.exists():
            return
        try:
            if self.settings_path.stat().st_size > _MAX_STORE:
                raise ValueError()
            protected = self.settings_path.read_bytes()
            if not protected.startswith(_MAGIC):
                raise ValueError()
            raw = self._unprotect(protected[len(_MAGIC):])
            if len(raw) > _MAX_STORE:
                raise ValueError()
            record = json.loads(raw, object_pairs_hook=_unique_object)
            if record.get("version") != 1:
                raise ValueError()
            host_id = record.get("host_id")
            if not isinstance(host_id, str) or not host_id.startswith("urn:uuid:"):
                raise ValueError()
            parsed_uuid = uuid.UUID(host_id[9:])
            if parsed_uuid.version != 4 or host_id != "urn:uuid:" + str(parsed_uuid):
                raise ValueError()
            registration = record.get("registration")
            if registration is not None:
                if (not isinstance(registration, dict) or registration.get("issuer") != ISSUER
                        or not _text(registration.get("subject"), 512)
                        or not _text(registration.get("client_id"), 512)
                        or registration["client_id"] == "dynamic_agent_client"):
                    raise ValueError()
            tokens = record.get("tokens")
            if tokens is not None:
                if registration is None or not isinstance(tokens, dict):
                    raise ValueError()
                if any(not _text(tokens.get(name)) for name in ("access_token", "id_token", "nonce")):
                    raise ValueError()
                if tokens.get("refresh_token") != "" and not _text(tokens.get("refresh_token")):
                    raise ValueError()
                if (not _number(tokens.get("expires_at")) or not _number(tokens.get("earliest_refresh_at", 0))
                        or not isinstance(tokens.get("scopes"), list)
                        or any(not _text(scope, 128) for scope in tokens["scopes"])):
                    raise ValueError()
                tokens = _Tokens(tokens["access_token"], tokens["refresh_token"], tokens["id_token"],
                                 tokens["expires_at"], tuple(tokens["scopes"]), tokens["nonce"],
                                 tokens.get("earliest_refresh_at", 0))
            self._host_id, self._registration, self._tokens = host_id, registration, tokens
            self._refresh_blocked = record.get("refresh_blocked", False) is True
        except ChatGPTError:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
            raise ChatGPTError("credential_store", "The saved ChatGPT connection could not be read securely.") from None

    def _save(self, registration, tokens, *, refresh_blocked=False):
        record = {"version": 1, "host_id": self._host_id, "registration": registration,
                  "tokens": asdict(tokens) if tokens else None, "refresh_blocked": refresh_blocked}
        try:
            raw = json.dumps(record, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            protected = self._protect(raw)
            atomic_replace_bytes(self.settings_path, _MAGIC + protected, preserve_previous=False)
        except ChatGPTError:
            raise
        except (OSError, ValueError, TypeError):
            raise ChatGPTError("credential_store", "The ChatGPT connection could not be saved securely.") from None

    def _check(self, cancel_event, deadline=None):
        if cancel_event.is_set():
            raise ChatGPTError("cancelled", "The ChatGPT operation was cancelled.")
        if deadline is not None and self._monotonic() >= deadline:
            raise ChatGPTError("sign_in_timeout", "ChatGPT sign-in timed out. Start a new sign-in when ready.")

    def _timeout(self, deadline=None):
        if deadline is None:
            return 15
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            raise ChatGPTError("sign_in_timeout", "ChatGPT sign-in timed out. Start a new sign-in when ready.")
        return min(15, remaining)

    def _identity(self, id_token, client_id, nonce, *, deadline=None, refresh=False):
        try:
            if not _text(id_token) or id_token.count(".") != 2:
                raise ValueError()
            encoded_header, encoded_claims, encoded_signature = id_token.split(".")
            header = json.loads(_decode(encoded_header), object_pairs_hook=_unique_object)
            claims = json.loads(_decode(encoded_claims), object_pairs_hook=_unique_object)
            signature = _decode(encoded_signature)
            if (not isinstance(header, dict) or not isinstance(claims, dict)
                    or header.get("alg") != "RS256" or not _text(header.get("kid"), 256)
                    or "crit" in header):
                raise ValueError()
            kid = header["kid"]
            cached = self._jwks is not None and self._jwks_expires > self._clock()
            for attempt in range(2 if cached else 1):
                if not cached or attempt:
                    document = request_json(self._http, "GET", JWKS_URL, timeout=self._timeout(deadline))
                    if not isinstance(document.get("keys"), list) or len(document["keys"]) > 100:
                        raise ValueError()
                    self._jwks = document["keys"]
                    self._jwks_expires = self._clock() + 3600
                matching = [key for key in self._jwks if isinstance(key, dict) and key.get("kid") == kid]
                if matching:
                    break
            if len(matching) != 1:
                raise ValueError()
            key = matching[0]
            if (key.get("kty") != "RSA" or key.get("alg", "RS256") != "RS256"
                    or key.get("use", "sig") != "sig"
                    or "key_ops" in key and (not isinstance(key["key_ops"], list)
                                               or "verify" not in key["key_ops"])):
                raise ValueError()
            modulus, exponent = _decode(key.get("n")), _decode(key.get("e"))
            if not self._verify_signature(modulus, exponent,
                                          (encoded_header + "." + encoded_claims).encode("ascii"), signature):
                raise ValueError()
            now = self._clock()
            audience = claims.get("aud")
            valid_audience = audience == client_id or (isinstance(audience, list) and client_id in audience
                                                       and all(isinstance(item, str) for item in audience))
            if (claims.get("iss") != ISSUER or not valid_audience
                    or isinstance(audience, list) and len(audience) > 1 and claims.get("azp") != client_id
                    or not _text(claims.get("sub"), 512)
                    or not _number(claims.get("exp")) or claims["exp"] <= now
                    or not _number(claims.get("iat")) or claims["iat"] > now + 5
                    or "nbf" in claims and (not _number(claims["nbf"]) or claims["nbf"] > now + 5)):
                raise ValueError()
            if (not refresh or "nonce" in claims) and claims.get("nonce") != nonce:
                raise ValueError()
            return claims
        except ChatGPTError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
            raise ChatGPTError("invalid_identity", "The ChatGPT identity could not be verified. The saved connection was kept.") from None

    def _token_set(self, response, client_id, nonce, *, deadline=None, previous=None):
        try:
            if (not _text(response.get("access_token")) or response.get("token_type", "").casefold() != "bearer"
                    or not _number(response.get("expires_in")) or not 0 < response["expires_in"] <= 86400):
                raise ValueError()
            refresh_token = response.get("refresh_token", "")
            if refresh_token != "" and not _text(refresh_token):
                raise ValueError()
            # A refresh must return its replacement, never retain a rotated old token.
            if previous is not None and not refresh_token:
                raise ValueError()
            scope = response.get("scope", "")
            if not isinstance(scope, str) or len(scope) > 4096:
                raise ValueError()
            scopes = tuple(sorted(set(scope.split())))
            if any(not _text(item, 128) for item in scopes):
                raise ValueError()
            if "offline_access" in scopes and not refresh_token:
                raise ValueError()
            id_token = response.get("id_token")
            if id_token is None and previous is not None:
                id_token = previous.id_token
                identity = self._registration
            else:
                identity = self._identity(id_token, client_id, nonce, deadline=deadline, refresh=previous is not None)
            if self._registration is not None and identity.get("sub", identity.get("subject")) != self._registration["subject"]:
                raise ChatGPTError("identity_mismatch", "ChatGPT returned a different account. The saved connection was kept.")
            earliest = response.get("earliest_refresh_at", 0)
            if not _number(earliest) or earliest < 0:
                raise ValueError()
            registration = {"issuer": ISSUER, "subject": identity.get("sub", identity.get("subject")),
                            "client_id": client_id, "email": _label(identity.get("email")),
                            "plan_permission": "chatgpt.tokens.use.direct" in scopes}
            tokens = _Tokens(response["access_token"], refresh_token, id_token,
                             self._clock() + response["expires_in"], scopes, nonce, earliest)
            return registration, tokens
        except ChatGPTError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ChatGPTError("invalid_response", "ChatGPT returned an incomplete token response. Start a new sign-in.") from None

    def sign_in(self, cancel_event):
        with self._lock:
            deadline = self._monotonic() + 180
            self._check(cancel_event, deadline)
            # Save the host identifier before first browser registration.
            self._save(self._registration, self._tokens, refresh_blocked=self._refresh_blocked)
            state, nonce, verifier = self._random(), self._random(), self._random()
            client_id = self._registration["client_id"] if self._registration else self._pending_client_id
            with self._listener_factory() as listener:
                params = {"client_id": client_id or "dynamic_agent_client", "ext_agent_host_id": self._host_id,
                          "response_type": "code", "redirect_uri": listener.redirect_uri, "scope": SCOPES,
                          "resource": RESOURCE, "state": state, "nonce": nonce, "code_challenge_method": "S256",
                          "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")}
                if client_id is None:
                    params["agent_name_hint"] = "Context Palette"
                elif self._tokens:
                    params["id_token_hint"] = self._tokens.id_token
                    params["login_hint"] = self._registration["email"]
                if self._registration is not None and not self._registration.get(
                        "plan_permission", self._tokens is not None and "chatgpt.tokens.use.direct" in self._tokens.scopes):
                    # This method is called only for an explicit Continue action.
                    params["prompt"] = "consent"
                try:
                    if not self._browser_open(AUTHORIZE_URL + "?" + urlencode(params)):
                        raise ChatGPTError("browser", "The sign-in browser could not be opened.")
                except ChatGPTError:
                    raise
                except Exception:
                    raise ChatGPTError("browser", "The sign-in browser could not be opened.") from None
                callback = listener.wait(cancel_event, deadline)
            self._check(cancel_event, deadline)
            code, issued_client_id = validate_callback(callback, state, client_id)
            try:
                response = request_json(self._http, "POST", TOKEN_URL,
                                        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                                        body=urlencode({"grant_type": "authorization_code", "client_id": issued_client_id,
                                                        "code": code, "code_verifier": verifier,
                                                        "redirect_uri": listener.redirect_uri, "resource": RESOURCE}).encode("ascii"),
                                        timeout=self._timeout(deadline))
            except ChatGPTError as failure:
                if failure.code == "invalid_grant" and self._registration is None:
                    self._pending_client_id = issued_client_id
                raise
            registration, tokens = self._token_set(response, issued_client_id, nonce, deadline=deadline)
            self._check(cancel_event, deadline)
            self._save(registration, tokens)
            self._registration, self._tokens, self._refresh_blocked = registration, tokens, False
            self._pending_client_id = None
            return self.account

    def _clear_tokens(self):
        # Stop local use even if the atomic write itself fails.
        self._tokens = None
        self._refresh_blocked = False
        self._save(self._registration, None)

    def access_token(self, cancel_event):
        with self._lock:
            self._check(cancel_event)
            if self._tokens is None:
                raise ChatGPTError("sign_in_required", "Continue with ChatGPT before sending a message.")
            if "chatgpt.tokens.use.direct" not in self._tokens.scopes:
                raise ChatGPTError("permission", "ChatGPT plan usage is disabled for this connection. Continue with ChatGPT to review permission.")
            now = self._clock()
            if self._tokens.expires_at > now + 60:
                return self._tokens.access_token
            if self._refresh_blocked:
                raise ChatGPTError("refresh_uncertain", "Session renewal was not confirmed. Continue with ChatGPT before sending again.")
            if not self._tokens.refresh_token:
                raise ChatGPTError("sign_in_required", "This ChatGPT session expired. Continue with ChatGPT again.")
            if now < self._tokens.earliest_refresh_at:
                if self._tokens.expires_at > now:
                    return self._tokens.access_token
                raise ChatGPTError("refresh_not_ready", "ChatGPT has not permitted session renewal yet. Try again later.")
            previous = self._tokens
            try:
                response = request_json(self._http, "POST", TOKEN_URL,
                                        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                                        body=urlencode({"grant_type": "refresh_token", "client_id": self._registration["client_id"],
                                                        "refresh_token": previous.refresh_token, "resource": RESOURCE}).encode("ascii"))
                registration, tokens = self._token_set(response, self._registration["client_id"], previous.nonce, previous=previous)
                # Always persist a received rotation, including when the user cancelled during transport.
                self._save(registration, tokens)
                self._registration, self._tokens = registration, tokens
            except ChatGPTError as failure:
                if failure.code in _TERMINAL_REFRESH:
                    self._clear_tokens()
                else:
                    # A timeout/malformed response/save failure may follow a successful rotation.
                    # Keep the record but prevent blindly replaying that refresh token.
                    self._refresh_blocked = True
                    try:
                        self._save(self._registration, self._tokens, refresh_blocked=True)
                    except ChatGPTError:
                        self._tokens = None
                raise
            self._check(cancel_event)
            if "chatgpt.tokens.use.direct" not in self._tokens.scopes:
                raise ChatGPTError("permission", "ChatGPT plan usage permission is missing. Continue with ChatGPT to review permission.")
            return self._tokens.access_token

    def sign_out(self):
        """Forget tokens locally; ChatGPT's registered grant is not revoked."""
        with self._lock:
            self._clear_tokens()
