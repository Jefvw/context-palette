"""Small, bounded HTTPS transport for the attended ChatGPT integration.

Credentials and server-provided diagnostic text must never become exception
messages. Only documented error codes and a constrained request ID cross this
boundary. Redirects are deliberately refused, including same-host redirects.
"""
from __future__ import annotations

from contextlib import contextmanager
from http.client import HTTPException
import json
import re
import socket
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener


class ChatGPTError(Exception):
    """An error containing application-owned text, never raw remote diagnostics."""

    def __init__(self, code: str, message: str, *, status=None, request_id=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.request_id = request_id


_ERRORS = {
    "subscription_sharing_usage_limit_exceeded": ("usage_limit", "This app's ChatGPT usage limit was reached. Review ChatGPT Settings → Usage."),
    "subscription_sharing_user_not_eligible": ("ineligible", "ChatGPT plan usage is unavailable for this account or workspace."),
    "subscription_sharing_unsupported_capability": ("unsupported", "This request uses a capability that ChatGPT plan sharing does not support."),
    "subscription_sharing_route_not_supported": ("unsupported", "This request route does not support ChatGPT plan sharing."),
    "chatpass_v2_scope_not_authorized": ("permission", "This connection does not authorize ChatGPT plan usage."),
    "chatpass_v2_invalid_authorization_context": ("permission", "ChatGPT could not verify this connection's plan permission."),
    "subscription_sharing_invalid_user": ("unauthorized", "ChatGPT could not verify this connection. Sign in again if it was disconnected."),
    "subscription_sharing_usage_unavailable": ("unavailable", "ChatGPT usage information is temporarily unavailable. Try again later."),
    "subscription_sharing_user_unavailable": ("unavailable", "ChatGPT account information is temporarily unavailable. Try again later."),
}
_TERMINAL_REFRESH = frozenset({"invalid_grant", "invalid_refresh_token", "token_expired", "refresh_token_expired", "refresh_token_invalidated", "refresh_token_reused"})


def classify_http_error(status: int, payload=None, headers=None) -> ChatGPTError:
    """Classify bounded JSON without surfacing error.message, detail or raw codes."""
    remote_code = None
    if isinstance(payload, dict):
        error = payload.get("error")
        remote_code = error.get("code") if isinstance(error, dict) else error
    if not isinstance(remote_code, str):
        remote_code = None
    if remote_code in _ERRORS:
        code, message = _ERRORS[remote_code]
    elif remote_code in _TERMINAL_REFRESH:
        code, message = remote_code, "This ChatGPT session cannot be renewed. Sign in again."
    elif remote_code == "invalid_client":
        code, message = "invalid_client", "ChatGPT rejected this app's registration. Sign in again."
    elif status == 401:
        code, message = "unauthorized", "ChatGPT did not accept this connection. Check the account and sign in again."
    elif status == 403:
        code, message = "permission", "ChatGPT declined this request because of a permission or policy restriction."
    elif status == 429:
        code, message = "usage_limit", "ChatGPT declined this request because of a usage limit. Review ChatGPT Settings → Usage."
    elif status >= 500:
        code, message = "unavailable", "ChatGPT is temporarily unavailable. Try again later."
    elif 300 <= status < 400:
        code, message = "redirect", "ChatGPT returned an unexpected redirect. The request was stopped."
    else:
        code, message = "http_error", "ChatGPT could not complete this request."
    request_id = None
    if headers is not None:
        candidate = headers.get("x-request-id") or headers.get("openai-request-id")
        # Only the conventional request identifier form is retained.
        if isinstance(candidate, str) and re.fullmatch(r"req_[A-Za-z0-9_-]{1,100}", candidate):
            request_id = candidate
    return ChatGPTError(code, message, status=status, request_id=request_id)


def read_json(response, *, max_bytes: int = 262144, timeout: float = 15) -> dict:
    try:
        deadline = time.monotonic() + timeout
        # read1 returns available bytes without waiting for the entire body.
        # A socket timeout alone does not bound a peer that keeps dripping data.
        reader = getattr(response, "read1", None) or response.read
        chunks, size = [], 0
        while True:
            if time.monotonic() >= deadline:
                raise ChatGPTError("timeout", "The ChatGPT connection timed out.")
            chunk = reader(min(16384, max_bytes + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise ChatGPTError("response_too_large", "ChatGPT returned a response larger than this app permits.")
            chunks.append(chunk)
        raw = b"".join(chunks)
        result = json.loads(raw.decode("utf-8"))
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except ChatGPTError:
        raise
    except (socket.timeout, TimeoutError):
        raise ChatGPTError("timeout", "The ChatGPT connection timed out.") from None
    except (ValueError, UnicodeError, RecursionError):
        raise ChatGPTError("invalid_response", "ChatGPT returned an invalid response.") from None
    except (OSError, URLError, HTTPException):
        raise ChatGPTError("connection", "The ChatGPT connection was interrupted.") from None


def request_json(http, method: str, url: str, *, headers=None, body=None,
                 timeout=15, max_bytes=262144) -> dict:
    deadline = time.monotonic() + timeout
    with http.open(method, url, headers=headers, body=body, timeout=timeout) as response:
        return read_json(response, max_bytes=max_bytes, timeout=deadline - time.monotonic())


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HTTPSClient:
    """TLS-verified, no-redirect transport restricted to the official hosts."""

    def __init__(self, *, opener=None):
        self._opener = opener or build_opener(
            ProxyHandler(), HTTPSHandler(context=ssl.create_default_context()), _NoRedirects())

    @contextmanager
    def open(self, method, url, *, headers=None, body=None, timeout=15):
        try:
            parts = urlsplit(url)
            valid = (parts.scheme == "https" and parts.hostname in {"auth.openai.com", "api.openai.com"}
                     and parts.port in (None, 443) and parts.username is None
                     and parts.password is None and not parts.fragment)
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise ChatGPTError("invalid_endpoint", "This app refused an untrusted ChatGPT endpoint.")
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 30:
            raise ChatGPTError("invalid_timeout", "The ChatGPT request timeout is invalid.")
        response = None
        try:
            request = Request(url, data=body, headers=headers or {}, method=method)
            response = self._opener.open(request, timeout=timeout)
            status = getattr(response, "status", 200)
            if status < 200 or status >= 300:
                raise classify_http_error(status)
            yield response
        except HTTPError as failure:
            try:
                payload = read_json(failure, max_bytes=65536)
            except ChatGPTError:
                payload = None
            finally:
                failure.close()
            raise classify_http_error(failure.code, payload, failure.headers) from None
        except ChatGPTError:
            raise
        except (socket.timeout, TimeoutError):
            raise ChatGPTError("timeout", "The ChatGPT connection timed out.") from None
        except (OSError, URLError, ssl.SSLError, HTTPException):
            raise ChatGPTError("connection", "The ChatGPT connection could not be completed.") from None
        except (ValueError, UnicodeError):
            raise ChatGPTError("invalid_request", "The ChatGPT request could not be prepared.") from None
        finally:
            if response is not None:
                try:
                    response.close()
                except (OSError, HTTPException):
                    pass
