from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
import threading
import time
from typing import BinaryIO, Callable, Iterator, Sequence

from .chatgpt_http import ChatGPTError, HTTPSClient


MODELS_URL = "https://api.openai.com/v1/models"
RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_INSTRUCTIONS = (
    "You are a helpful assistant in Context Palette. Lead with the answer or recommendation. "
    "Use familiar words and short paragraphs with one idea each. Use at most five bullets "
    "when they help scanning. Keep routine answers brief while preserving important facts, "
    "uncertainty and risks; expand when the user needs detail. "
    "Use only the text the user provides; you have no access to their computer or files."
)
MAX_MESSAGES = 40
MAX_MESSAGE_CHARS = 32768
MAX_INPUT_CHARS = 65536
MAX_OUTPUT_CHARS = 65536
# The account catalogue includes large metadata/instruction fields that are
# deliberately ignored. The observed valid catalogue exceeded 256 KiB.
MAX_MODEL_BYTES = 2 * 1024 * 1024
MAX_MODELS = 256
MAX_SSE_EVENT_BYTES = 1048576
MAX_STREAM_BYTES = 4194304
MAX_STREAM_EVENTS = 20000
HTTP_TIMEOUT_SECONDS = 15
RESPONSE_TIMEOUT_SECONDS = 180
READ_CHUNK_BYTES = 4096

_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_USAGE_CODES = {
    "subscription_sharing_usage_limit_exceeded",
    "subscription_sharing_usage_unavailable",
}
_MESSAGES = {
    "cancelled": "Stopped waiting for this reply. ChatGPT may still have processed the request.",
    "timeout": "Waiting for ChatGPT timed out. The request may still have been processed; it was not retried.",
    "network": "The ChatGPT connection was interrupted. No completed reply was received; the request was not retried.",
    "invalid_stream": "ChatGPT returned an invalid reply stream. No completed reply was accepted.",
    "stream_limit": "The ChatGPT reply exceeded the trial's stream size limit. No completed reply was accepted.",
    "output_limit": "The ChatGPT reply exceeded the trial's 65,536-character limit. No completed reply was accepted.",
    "incomplete": "ChatGPT did not complete the reply. No completed reply was accepted.",
    "failed": "ChatGPT could not complete the reply. No completed reply was accepted.",
    "usage_limit": "ChatGPT plan usage is currently unavailable or its limit has been reached. No completed reply was accepted.",
    "unsupported_output": "ChatGPT returned content this text-only trial cannot accept. No completed reply was accepted.",
    "empty_output": "ChatGPT completed without a text reply.",
    "invalid_catalog": "ChatGPT returned an invalid model list. Refresh the models before trying again.",
    "catalog_limit": "ChatGPT's model list exceeds this trial's size or model-count limit. No models were loaded.",
    "invalid_token": "Sign in to ChatGPT again before sending a request.",
    "invalid_model": "Choose a model from the current ChatGPT account's model list.",
    "invalid_input": "Send a non-empty user message with only user and assistant text history.",
    "input_limit": "This trial accepts at most 40 messages, 32,768 characters per message and 65,536 characters of history. Start a new chat or shorten the text.",
    "callback": "The reply could not be displayed. No completed reply was accepted.",
}


def _error(code: str) -> ChatGPTError:
    return ChatGPTError(code, _MESSAGES[code])


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    text: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ChatGPTModel:
    slug: str
    display_name: str


class ChatGPTClient:
    """Bounded, text-only OAuth inference; callbacks contain provisional text.

    Only the returned value is a completed answer suitable for history or output.
    No request is retried. Cancellation is observed between bounded HTTP reads;
    closing the connection does not prove cancellation at the service.
    """

    def __init__(self, http: HTTPSClient | None = None) -> None:
        self._http = http if http is not None else HTTPSClient()
        self._catalog_token_digest: bytes | None = None
        self._models: tuple[ChatGPTModel, ...] = ()

    def list_models(
        self, access_token: str, cancel_event: threading.Event
    ) -> tuple[ChatGPTModel, ...]:
        _validate_token(access_token)
        _check_wait(cancel_event)
        # Failed refreshes must never leave a formerly valid picker authoritative.
        self._catalog_token_digest = None
        self._models = ()
        try:
            with self._http.open(
                "GET", MODELS_URL, headers=_headers(access_token),
                timeout=HTTP_TIMEOUT_SECONDS,
            ) as response:
                raw = _read_bounded(response, MAX_MODEL_BYTES, cancel_event)
            data = _load_json(raw, "invalid_catalog")
            if not isinstance(data, dict) or not isinstance(data.get("models"), list):
                raise _error("invalid_catalog")
            if len(data["models"]) > MAX_MODELS:
                raise _error("catalog_limit")
            models: list[ChatGPTModel] = []
            seen: set[str] = set()
            for item in data["models"]:
                if not isinstance(item, dict):
                    raise _error("invalid_catalog")
                if item.get("visibility") != "list":
                    continue
                slug, name = item.get("slug"), item.get("display_name")
                if not _valid_slug(slug) or not _valid_label(name):
                    raise _error("invalid_catalog")
                if slug not in seen:
                    seen.add(slug)
                    models.append(ChatGPTModel(slug, name))
            _check_wait(cancel_event)
            self._models = tuple(models)
            self._catalog_token_digest = _token_digest(access_token)
            return self._models
        except ChatGPTError:
            _check_wait(cancel_event)
            raise
        except TimeoutError:
            raise _error("timeout") from None
        except Exception:
            raise _error("network") from None

    def respond(
        self,
        access_token: str,
        model: str | ChatGPTModel,
        messages: Sequence[ChatMessage],
        on_delta: Callable[[str], None],
        cancel_event: threading.Event,
    ) -> str:
        _validate_token(access_token)
        _check_wait(cancel_event)
        slug = model.slug if isinstance(model, ChatGPTModel) else model
        if not _valid_slug(slug):
            raise _error("invalid_model")
        inputs = _validate_messages(messages)
        if not callable(on_delta):
            raise _error("invalid_input")
        if self._catalog_token_digest != _token_digest(access_token):
            self.list_models(access_token, cancel_event)
        if slug not in {choice.slug for choice in self._models}:
            raise _error("invalid_model")
        payload = {
            "model": slug,
            "input": inputs,
            "instructions": DEFAULT_INSTRUCTIONS,
            "store": False,
            "stream": True,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        deadline = time.monotonic() + RESPONSE_TIMEOUT_SECONDS
        _check_wait(cancel_event, deadline)
        try:
            with self._http.open(
                "POST", RESPONSES_URL,
                headers=_headers(access_token, streaming=True), body=body,
                timeout=HTTP_TIMEOUT_SECONDS,
            ) as response:
                return _consume_reply(response, on_delta, cancel_event, deadline)
        except ChatGPTError as exc:
            _check_wait(cancel_event)
            if exc.code == "timeout":
                raise _error("timeout") from None
            if exc.code in {"connection", "network"}:
                raise _error("network") from None
            raise
        except TimeoutError:
            _check_wait(cancel_event)
            raise _error("timeout") from None
        except Exception:
            _check_wait(cancel_event)
            raise _error("network") from None


def _headers(token: str, *, streaming: bool = False) -> dict[str, str]:
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    if streaming:
        headers.update({"Content-Type": "application/json", "Accept": "text/event-stream"})
    return headers


def _validate_token(token: str) -> None:
    if (
        not isinstance(token, str) or not token or len(token) > 16384
        or any(ord(char) < 33 or ord(char) > 126 for char in token)
    ):
        raise _error("invalid_token")


def _token_digest(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()


def _valid_slug(value: object) -> bool:
    return isinstance(value, str) and _SLUG.fullmatch(value) is not None


def _valid_label(value: object) -> bool:
    return (
        isinstance(value, str) and bool(value.strip()) and len(value) <= 128
        and all(ord(char) >= 32 and ord(char) != 127 for char in value)
    )


def _validate_messages(messages: Sequence[ChatMessage]) -> list[dict[str, str]]:
    if not isinstance(messages, (list, tuple)) or not messages:
        raise _error("invalid_input")
    if len(messages) > MAX_MESSAGES:
        raise _error("input_limit")
    total = 0
    inputs = []
    for index, message in enumerate(messages):
        if (
            not isinstance(message, ChatMessage)
            or message.role != ("user" if index % 2 == 0 else "assistant")
            or not isinstance(message.text, str) or not message.text.strip()
            or "\x00" in message.text
        ):
            raise _error("invalid_input")
        total += len(message.text)
        if len(message.text) > MAX_MESSAGE_CHARS or total > MAX_INPUT_CHARS:
            raise _error("input_limit")
        try:
            message.text.encode("utf-8")
        except UnicodeError:
            raise _error("invalid_input") from None
        inputs.append({"role": message.role, "content": message.text})
    if messages[-1].role != "user":
        raise _error("invalid_input")
    return inputs


def _check_wait(cancel_event: threading.Event, deadline: float | None = None) -> None:
    if cancel_event.is_set():
        raise _error("cancelled")
    if deadline is not None and time.monotonic() >= deadline:
        raise _error("timeout")


def _read_chunk(response: BinaryIO) -> bytes:
    # HTTPResponse.read1 returns available data, avoiding a full-size read stall.
    reader = getattr(response, "read1", response.read)
    chunk = reader(READ_CHUNK_BYTES)
    if not isinstance(chunk, bytes):
        raise _error("invalid_stream")
    return chunk


def _read_bounded(response: BinaryIO, limit: int, cancel_event: threading.Event) -> bytes:
    deadline = time.monotonic() + HTTP_TIMEOUT_SECONDS
    result = bytearray()
    while True:
        _check_wait(cancel_event, deadline)
        chunk = _read_chunk(response)
        _check_wait(cancel_event, deadline)
        if not chunk:
            return bytes(result)
        result.extend(chunk)
        if len(result) > limit:
            raise _error("catalog_limit")


def _load_json(raw: bytes, error_code: str) -> object:
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, RecursionError):
        raise _error(error_code) from None


def _sse_events(
    response: BinaryIO, cancel_event: threading.Event, deadline: float
) -> Iterator[dict[str, object]]:
    buffer = bytearray()
    fields: list[bytes] = []
    event_name: str | None = None
    event_bytes = total_bytes = event_count = 0
    eof = False
    while not eof:
        _check_wait(cancel_event, deadline)
        chunk = _read_chunk(response)
        _check_wait(cancel_event, deadline)
        eof = not chunk
        total_bytes += len(chunk)
        if total_bytes > MAX_STREAM_BYTES:
            raise _error("stream_limit")
        buffer.extend(chunk)
        while buffer:
            positions = [pos for pos in (buffer.find(b"\n"), buffer.find(b"\r")) if pos >= 0]
            if not positions:
                break
            end = min(positions)
            if buffer[end] == 13 and end == len(buffer) - 1 and not eof:
                break
            width = 2 if buffer[end:end + 2] == b"\r\n" else 1
            line = bytes(buffer[:end])
            del buffer[:end + width]
            event_bytes += len(line) + width
            if event_bytes > MAX_SSE_EVENT_BYTES:
                raise _error("stream_limit")
            if not line:
                if fields:
                    event_count += 1
                    if event_count > MAX_STREAM_EVENTS:
                        raise _error("stream_limit")
                    data = _load_json(b"\n".join(fields), "invalid_stream")
                    if not isinstance(data, dict) or not isinstance(data.get("type"), str):
                        raise _error("invalid_stream")
                    if event_name is not None and data["type"] != event_name:
                        raise _error("invalid_stream")
                    yield data
                fields = []
                event_name = None
                event_bytes = 0
                continue
            if line.startswith(b":"):
                continue
            field_name, _, value = line.partition(b":")
            if value.startswith(b" "):
                value = value[1:]
            if field_name == b"data":
                fields.append(value)
            elif field_name == b"event":
                try:
                    name = value.decode("utf-8")
                except UnicodeError:
                    raise _error("invalid_stream") from None
                if event_name is not None or not name or len(name) > 128:
                    raise _error("invalid_stream")
                event_name = name
            # id/retry and unrecognised SSE fields carry no inference authority.
        if event_bytes + len(buffer) > MAX_SSE_EVENT_BYTES:
            raise _error("stream_limit")
    # A final event must be terminated by its blank line. EOF is never completion.
    if fields or buffer or event_name is not None:
        raise _error("invalid_stream")


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise _error("invalid_stream")
    return value


def _part_key(event: dict[str, object]) -> tuple[int, int, str]:
    output_index, content_index = event.get("output_index"), event.get("content_index")
    if (
        type(output_index) is not int or type(content_index) is not int
        or not 0 <= output_index < MAX_MESSAGES or not 0 <= content_index < MAX_MESSAGES
    ):
        raise _error("invalid_stream")
    return output_index, content_index, _identifier(event.get("item_id"))


def _item_key(event: dict[str, object]) -> tuple[int, dict[str, object]]:
    index, item = event.get("output_index"), event.get("item")
    if type(index) is not int or not 0 <= index < MAX_MESSAGES or not isinstance(item, dict):
        raise _error("invalid_stream")
    _identifier(item.get("id"))
    _identifier(item.get("type"))
    return index, item


def _item_core(item: object) -> tuple:
    """Compare authoritative text/identity without treating metadata as instructions."""
    if not isinstance(item, dict):
        raise _error("invalid_stream")
    identity = _identifier(item.get("id")), _identifier(item.get("type"))
    if item.get("type") != "message":
        return identity
    content = item.get("content")
    if not isinstance(content, list):
        raise _error("invalid_stream")
    parts = []
    for part in content:
        if not isinstance(part, dict):
            raise _error("invalid_stream")
        kind = part.get("type")
        if kind not in {"output_text", "refusal"}:
            raise _error("unsupported_output")
        text = _validate_output_text(part.get("text" if kind == "output_text" else "refusal"))
        parts.append((kind, text))
    return identity + (item.get("role"), item.get("status"), tuple(parts))


def _completion_output(response: dict[str, object], finalized: dict[int, dict[str, object]],
                       added: dict[int, tuple[str, str]]) -> list:
    output = response.get("output")
    if not isinstance(output, list) or len(output) > MAX_MESSAGES:
        raise _error("invalid_stream")
    if not output and finalized:
        # Observed OAuth streams use an empty terminal output summary. Only
        # finalized, contiguous snapshots can fill it; the terminal response
        # remains the sole completion authority and all delta checks still run.
        indexes = sorted(finalized)
        if indexes != list(range(len(indexes))) or set(added) - set(finalized):
            raise _error("invalid_stream")
        output = [finalized[index] for index in indexes]
    for index, identity in added.items():
        if index >= len(output) or not isinstance(output[index], dict):
            raise _error("invalid_stream")
        if (output[index].get("id"), output[index].get("type")) != identity:
            raise _error("invalid_stream")
    for index, item in finalized.items():
        if index >= len(output) or _item_core(item) != _item_core(output[index]):
            raise _error("invalid_stream")
    return output


def _failed_error(code: object) -> ChatGPTError:
    return _error("usage_limit" if isinstance(code, str) and code in _USAGE_CODES else "failed")


def _validate_output_text(text: object) -> str:
    if not isinstance(text, str) or "\x00" in text:
        raise _error("invalid_stream")
    try:
        text.encode("utf-8")
    except UnicodeError:
        raise _error("invalid_stream") from None
    return text


def _consume_reply(
    response: BinaryIO, on_delta: Callable[[str], None],
    cancel_event: threading.Event, deadline: float,
) -> str:
    response_id: str | None = None
    parts: dict[tuple[int, int, str], list[str]] = {}
    done_parts: set[tuple[int, int, str]] = set()
    streamed_text: list[str] = []
    output_chars = 0
    sequence = -1
    added_items: dict[int, tuple[str, str]] = {}
    finalized_items: dict[int, dict[str, object]] = {}
    finalized_ids: set[str] = set()
    for event in _sse_events(response, cancel_event, deadline):
        _check_wait(cancel_event, deadline)
        kind = event["type"]
        number = event.get("sequence_number")
        if type(number) is not int or number <= sequence:
            raise _error("invalid_stream")
        sequence = number
        if kind == "error":
            raise _failed_error(event.get("code"))
        # A service can reject the request before creating any output.
        if kind == "response.failed" and response_id is None:
            current = event.get("response")
            error = current.get("error") if isinstance(current, dict) else None
            raise _failed_error(error.get("code") if isinstance(error, dict) else None)
        if kind == "response.created":
            if response_id is not None or not isinstance(event.get("response"), dict):
                raise _error("invalid_stream")
            response_id = _identifier(event["response"].get("id"))
        elif response_id is None:
            raise _error("invalid_stream")
        if "response_id" in event and event["response_id"] != response_id:
            raise _error("invalid_stream")
        if kind in {"response.created", "response.in_progress", "response.completed", "response.failed", "response.incomplete"}:
            current = event.get("response")
            if not isinstance(current, dict) or current.get("id") != response_id:
                raise _error("invalid_stream")
            if kind == "response.failed":
                error = current.get("error")
                code = error.get("code") if isinstance(error, dict) else None
                raise _failed_error(code)
            if kind == "response.incomplete":
                raise _error("incomplete")
            if kind == "response.completed":
                output = _completion_output(current, finalized_items, added_items)
                result = _completed_text(dict(current, output=output), parts)
                if result != "".join(streamed_text):
                    raise _error("invalid_stream")
                _check_wait(cancel_event, deadline)
                return result
        if kind == "response.output_item.added":
            index, item = _item_key(event)
            identity = item["id"], item["type"]
            if index in added_items or index in finalized_items or identity[0] in {value[0] for value in added_items.values()}:
                raise _error("invalid_stream")
            added_items[index] = identity
        elif kind == "response.output_item.done":
            index, item = _item_key(event)
            identity = item["id"], item["type"]
            if (index in finalized_items or identity[0] in finalized_ids
                    or index in added_items and added_items[index] != identity):
                raise _error("invalid_stream")
            finalized_items[index] = item
            finalized_ids.add(identity[0])
        if kind in {"response.output_text.delta", "response.refusal.delta"}:
            key = _part_key(event)
            if (key[0] in finalized_items or key[0] in added_items
                    and added_items[key[0]] != (key[2], "message")):
                raise _error("invalid_stream")
            delta = _validate_output_text(event.get("delta"))
            if key in done_parts:
                raise _error("invalid_stream")
            output_chars += len(delta)
            if output_chars > MAX_OUTPUT_CHARS:
                raise _error("output_limit")
            parts.setdefault(key, []).append(delta)
            streamed_text.append(delta)
            try:
                on_delta(delta)
            except Exception:
                raise _error("callback") from None
        elif kind in {"response.output_text.done", "response.refusal.done"}:
            key = _part_key(event)
            text = _validate_output_text(event.get("text") if kind == "response.output_text.done" else event.get("refusal"))
            if key in done_parts or text != "".join(parts.get(key, [])):
                raise _error("invalid_stream")
            done_parts.add(key)
    raise _error("incomplete")


def _completed_text(
    response: dict[str, object], parts: dict[tuple[int, int, str], list[str]]
) -> str:
    if (
        response.get("status") != "completed" or response.get("error") is not None
        or response.get("incomplete_details") is not None
        or not isinstance(response.get("output"), list)
    ):
        raise _error("invalid_stream")
    seen: set[tuple[int, int, str]] = set()
    item_ids: set[str] = set()
    text_parts: list[str] = []
    length = 0
    for output_index, item in enumerate(response["output"]):
        if not isinstance(item, dict):
            raise _error("invalid_stream")
        item_id = _identifier(item.get("id"))
        if item_id in item_ids:
            raise _error("invalid_stream")
        item_ids.add(item_id)
        if item.get("type") == "reasoning":
            continue
        if item.get("type") != "message" or item.get("role") != "assistant":
            raise _error("unsupported_output")
        if item.get("status") != "completed" or not isinstance(item.get("content"), list):
            raise _error("invalid_stream")
        for content_index, content in enumerate(item["content"]):
            if not isinstance(content, dict):
                raise _error("invalid_stream")
            if content.get("type") == "output_text":
                text = content.get("text")
            elif content.get("type") == "refusal":
                text = content.get("refusal")
            else:
                raise _error("unsupported_output")
            text = _validate_output_text(text)
            length += len(text)
            if length > MAX_OUTPUT_CHARS:
                raise _error("output_limit")
            key = output_index, content_index, item_id
            if text != "".join(parts.get(key, [])):
                raise _error("invalid_stream")
            seen.add(key)
            text_parts.append(text)
    if set(parts) - seen:
        raise _error("invalid_stream")
    result = "".join(text_parts)
    if not result.strip():
        raise _error("empty_output")
    return result
