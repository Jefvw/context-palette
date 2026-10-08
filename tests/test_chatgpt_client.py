from __future__ import annotations

from contextlib import contextmanager
import io
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.chatgpt_client import (
    ChatGPTClient,
    ChatGPTModel,
    ChatMessage,
    DEFAULT_INSTRUCTIONS,
    HTTP_TIMEOUT_SECONDS,
    MAX_INPUT_CHARS,
    MAX_MESSAGE_CHARS,
    MAX_MESSAGES,
    MAX_MODEL_BYTES,
    MAX_MODELS,
    MODELS_URL,
    RESPONSES_URL,
)
from context_palette.chatgpt_http import ChatGPTError


TOKEN = "fake-token-for-tests"
MODEL = "example-chat-model"


def catalog(*models: dict[str, object]) -> bytes:
    choices = models or ({"slug": MODEL, "display_name": "Example Chat", "visibility": "list"},)
    return json.dumps({"models": choices}).encode("utf-8")


def event(kind: str, sequence: int, **fields: object) -> dict[str, object]:
    return {"type": kind, "sequence_number": sequence, **fields}


def created(response_id: str = "resp_example") -> dict[str, object]:
    return event("response.created", 0, response={"id": response_id, "status": "in_progress"})


def delta(text: str, sequence: int = 1, **fields: object) -> dict[str, object]:
    return event(
        "response.output_text.delta", sequence,
        **{"delta": text, "item_id": "msg_example", "output_index": 0, "content_index": 0, **fields},
    )


def completed(text: str, sequence: int = 2, response_id: str = "resp_example") -> dict[str, object]:
    return event("response.completed", sequence, response={
        "id": response_id, "status": "completed", "error": None,
        "incomplete_details": None,
        "output": [{
            "id": "msg_example", "type": "message", "role": "assistant",
            "status": "completed", "content": [{"type": "output_text", "text": text}],
        }],
    })


def sse(*events: dict[str, object], newline: bytes = b"\n") -> bytes:
    return b"".join(
        b"event: " + str(value["type"]).encode() + newline
        + b"data: " + json.dumps(value, ensure_ascii=False).encode("utf-8")
        + newline + newline
        for value in events
    )


def compact_lifecycle(text: str, *, reasoning=False) -> list[dict[str, object]]:
    """Observed lifecycle: finalized item, then completed with output=[]."""
    response_id = "resp_example"
    events = [created(response_id), event("response.in_progress", 1,
                                         response={"id": response_id, "status": "in_progress"})]
    output_index = int(reasoning)
    if reasoning:
        item = {"id": "rs_example", "type": "reasoning", "summary": [],
                "encrypted_content": "Synthetic opaque data; never used as instructions"}
        events.append(event("response.output_item.added", len(events), output_index=0, item=item))
        events.append(event("response.output_item.done", len(events), output_index=0, item=item))
    message = {"id": "msg_example", "type": "message", "role": "assistant", "status": "in_progress", "content": []}
    events.append(event("response.output_item.added", len(events), output_index=output_index, item=message))
    events.append(event("response.content_part.added", len(events), output_index=output_index,
                        content_index=0, item_id="msg_example", part={"type": "output_text", "text": ""}))
    events.append(delta(text, len(events), output_index=output_index))
    events.append(event("response.output_text.done", len(events), output_index=output_index,
                        content_index=0, item_id="msg_example", text=text))
    events.append(event("response.content_part.done", len(events), output_index=output_index,
                        content_index=0, item_id="msg_example", part={"type": "output_text", "text": text}))
    item = completed(text)["response"]["output"][0]
    events.append(event("response.output_item.done", len(events), output_index=output_index, item=item))
    events.append(event("response.completed", len(events), response={
        "id": response_id, "status": "completed", "error": None, "incomplete_details": None, "output": []}))
    return events


class FakeStream(io.BytesIO):
    def __init__(self, data: bytes, *, chunk_size: int = 4096, after_read=None) -> None:
        super().__init__(data)
        self.chunk_size = chunk_size
        self.after_read = after_read

    def read1(self, size: int = -1) -> bytes:
        value = super().read(min(size, self.chunk_size))
        if self.after_read is not None:
            self.after_read()
        return value


class FakeHTTP:
    def __init__(self, *responses: bytes | FakeStream | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []
        self.streams: list[FakeStream] = []

    @contextmanager
    def open(self, method, url, *, headers=None, body=None, timeout=15):
        self.requests.append({
            "method": method, "url": url, "headers": headers, "body": body,
            "timeout": timeout,
        })
        if not self.responses:
            raise AssertionError("Unexpected HTTP request")
        supplied = self.responses.pop(0)
        if isinstance(supplied, Exception):
            raise supplied
        stream = supplied if isinstance(supplied, FakeStream) else FakeStream(supplied)
        self.streams.append(stream)
        try:
            yield stream
        finally:
            stream.close()


class ChatGPTClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cancel = threading.Event()
        self.messages = [ChatMessage("user", "Hello")]
        self.deltas: list[str] = []

    def _client(self, *responses: bytes | FakeStream | Exception) -> tuple[ChatGPTClient, FakeHTTP]:
        http = FakeHTTP(catalog(), *responses)
        client = ChatGPTClient(http=http)
        client.list_models(TOKEN, self.cancel)
        return client, http

    def _reply(self, client: ChatGPTClient, *, model=MODEL, messages=None, callback=None) -> str:
        return client.respond(
            TOKEN, model, self.messages if messages is None else messages,
            self.deltas.append if callback is None else callback, self.cancel,
        )

    def _assert_error(self, code: str, client: ChatGPTClient, **kwargs) -> ChatGPTError:
        with self.assertRaises(ChatGPTError) as caught:
            self._reply(client, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_model_catalog_uses_visible_unique_server_order(self) -> None:
        http = FakeHTTP(catalog(
            {"slug": "z-model", "display_name": "Z Model", "visibility": "list"},
            {"slug": "hidden-model", "visibility": "hidden"},
            {"slug": "a-model", "display_name": "A Model", "visibility": "list"},
            {"slug": "z-model", "display_name": "Duplicate", "visibility": "list"},
        ))
        models = ChatGPTClient(http).list_models(TOKEN, self.cancel)
        self.assertEqual(models, (ChatGPTModel("z-model", "Z Model"), ChatGPTModel("a-model", "A Model")))
        request = http.requests[0]
        self.assertEqual((request["method"], request["url"]), ("GET", MODELS_URL))
        self.assertEqual(request["headers"]["Authorization"], "Bearer " + TOKEN)
        self.assertIsNone(request["body"])
        self.assertEqual(request["timeout"], HTTP_TIMEOUT_SECONDS)

    def test_completed_followup_sends_entire_exact_text_history_and_supported_fields(self) -> None:
        first = sse(created(), delta("First answer"), completed("First answer"))
        second = sse(created("resp_second"), delta("Second answer"), completed("Second answer", response_id="resp_second"))
        client, http = self._client(first, second)
        answer = self._reply(client, model=ChatGPTModel(MODEL, "Example Chat"))
        self.assertEqual(answer, "First answer")
        history = [*self.messages, ChatMessage("assistant", answer), ChatMessage("user", " Follow up\nexactly ")]
        self.assertEqual(self._reply(client, messages=history), "Second answer")
        request = http.requests[-1]
        self.assertEqual((request["method"], request["url"]), ("POST", RESPONSES_URL))
        body = json.loads(request["body"])
        self.assertEqual(set(body), {"model", "input", "instructions", "store", "stream"})
        self.assertEqual(body["input"], [{"role": item.role, "content": item.text} for item in history])
        self.assertEqual(body["instructions"], DEFAULT_INSTRUCTIONS)
        self.assertIs(body["store"], False)
        self.assertIs(body["stream"], True)
        self.assertEqual(request["headers"]["Accept"], "text/event-stream")
        self.assertTrue(all(stream.closed for stream in http.streams))

    def test_initial_catalog_is_fetched_once_when_needed(self) -> None:
        http = FakeHTTP(catalog(), sse(created(), delta("Answer"), completed("Answer")))
        self.assertEqual(self._reply(ChatGPTClient(http)), "Answer")
        self.assertEqual([request["method"] for request in http.requests], ["GET", "POST"])

    def test_account_change_fetches_new_catalog_before_any_inference(self) -> None:
        client, http = self._client(catalog({"slug": "other-model", "display_name": "Other", "visibility": "list"}))
        with self.assertRaises(ChatGPTError) as caught:
            client.respond("other-account-token", MODEL, self.messages, self.deltas.append, self.cancel)
        self.assertEqual(caught.exception.code, "invalid_model")
        self.assertEqual([request["method"] for request in http.requests], ["GET", "GET"])

    def test_invalid_models_fail_before_post(self) -> None:
        client, http = self._client()
        for model in ("missing-model", " model ", "https://evil.example/model", "model\r\nheader: value", None):
            with self.subTest(model=model):
                self._assert_error("invalid_model", client, model=model)
        self.assertEqual(len(http.requests), 1)

    def test_invalid_catalog_is_safe_and_disables_previously_loaded_choices(self) -> None:
        client, http = self._client(b'{"models": [{"visibility": "list", "slug": "bad\nslug", "display_name": "Private response"}]}', catalog())
        with self.assertRaises(ChatGPTError) as caught:
            client.list_models(TOKEN, self.cancel)
        self.assertEqual(caught.exception.code, "invalid_catalog")
        self.assertNotIn("Private response", str(caught.exception))
        # A send must fetch again; a failed refresh did not authorize an old picker.
        http.responses.append(sse(created(), delta("Answer"), completed("Answer")))
        self.assertEqual(self._reply(client), "Answer")
        self.assertEqual([request["method"] for request in http.requests], ["GET", "GET", "GET", "POST"])

    def test_catalog_rejects_wrong_structure_and_excessive_size(self) -> None:
        for data in (b'{"data": []}', b'{"models": [null]}', b'{"models": "wrong"}', b'not-json'):
            with self.subTest(data=data):
                with self.assertRaises(ChatGPTError) as caught:
                    ChatGPTClient(FakeHTTP(data)).list_models(TOKEN, self.cancel)
                self.assertEqual(caught.exception.code, "invalid_catalog")
        with patch("context_palette.chatgpt_client.MAX_MODEL_BYTES", 8):
            with self.assertRaises(ChatGPTError) as caught:
                ChatGPTClient(FakeHTTP(catalog())).list_models(TOKEN, self.cancel)
            self.assertEqual(caught.exception.code, "catalog_limit")

    def test_large_valid_catalog_metadata_is_ignored_without_changing_choices(self) -> None:
        raw = catalog(
            {"slug": "first-model", "display_name": "First", "visibility": "list",
             "base_instructions": "Ignored metadata " + "x" * (360 * 1024),
             "supported_reasoning_levels": [{"reasoning_effort": "high"}]},
            {"slug": "hidden-model", "visibility": "hidden", "description": "Not shown"},
            {"slug": "second-model", "display_name": "Second", "visibility": "list"},
        )
        self.assertGreater(len(raw), 256 * 1024)
        http = FakeHTTP(raw)
        client = ChatGPTClient(http)
        models = client.list_models(TOKEN, self.cancel)
        self.assertEqual(models, (ChatGPTModel("first-model", "First"), ChatGPTModel("second-model", "Second")))
        self.assertEqual([request["method"] for request in http.requests], ["GET"])
        self.assertEqual(self.deltas, [])

    def test_catalog_above_new_byte_limit_stops_and_clears_old_choices(self) -> None:
        client, http = self._client(b"x" * (MAX_MODEL_BYTES + 1))
        with self.assertRaises(ChatGPTError) as caught:
            client.list_models(TOKEN, self.cancel)
        self.assertEqual(caught.exception.code, "catalog_limit")
        self.assertEqual(client._models, ())
        self.assertEqual([request["method"] for request in http.requests], ["GET", "GET"])
        self.assertTrue(http.streams[-1].closed)

    def test_catalog_model_count_limit_is_still_enforced(self) -> None:
        raw = catalog(*({"slug": f"model-{index}", "display_name": f"Model {index}", "visibility": "list"}
                        for index in range(MAX_MODELS + 1)))
        http = FakeHTTP(raw)
        with self.assertRaises(ChatGPTError) as caught:
            ChatGPTClient(http).list_models(TOKEN, self.cancel)
        self.assertEqual(caught.exception.code, "catalog_limit")
        self.assertEqual([request["method"] for request in http.requests], ["GET"])

    def test_compact_terminal_uses_finalized_items_after_real_lifecycle(self) -> None:
        client, http = self._client(sse(*compact_lifecycle("Palette connected.")))
        self.assertEqual(self._reply(client), "Palette connected.")
        self.assertEqual("".join(self.deltas), "Palette connected.")
        self.assertEqual([request["method"] for request in http.requests], ["GET", "POST"])

    def test_compact_terminal_preserves_physical_indexes_after_reasoning(self) -> None:
        client, http = self._client(sse(*compact_lifecycle("Clear reply", reasoning=True)))
        self.assertEqual(self._reply(client), "Clear reply")
        self.assertNotIn("opaque", "".join(self.deltas))

    def test_finalized_item_without_terminal_completion_never_succeeds(self) -> None:
        events = compact_lifecycle("Provisional")[:-1]
        client, _ = self._client(sse(*events))
        self._assert_error("incomplete", client)

    def test_text_done_without_finalized_item_cannot_fill_empty_terminal(self) -> None:
        events = [item for item in compact_lifecycle("Provisional")
                  if item["type"] != "response.output_item.done"]
        client, _ = self._client(sse(*events))
        self._assert_error("invalid_stream", client)

    def test_compact_terminal_still_requires_id_status_and_no_error(self) -> None:
        for change in ({"id": "wrong"}, {"status": "in_progress"}, {"error": {"code": "unknown"}},
                       {"incomplete_details": {"reason": "limit"}}):
            with self.subTest(change=change):
                events = compact_lifecycle("Reply")
                events[-1]["response"].update(change)
                client, _ = self._client(sse(*events))
                self._assert_error("invalid_stream", client)

    def test_compact_snapshot_must_match_text_identity_and_completed_status(self) -> None:
        for field, value in (("id", "wrong"), ("status", "in_progress"), ("role", "user"), ("text", "Altered")):
            with self.subTest(field=field):
                events = compact_lifecycle("Reply")
                item = events[-2]["item"]
                if field == "text":
                    item["content"][0]["text"] = value
                else:
                    item[field] = value
                client, _ = self._client(sse(*events))
                self._assert_error("unsupported_output" if field == "role" else "invalid_stream", client)

    def test_compact_terminal_rejects_sparse_and_duplicate_item_snapshots(self) -> None:
        events = compact_lifecycle("Reply")
        for item in events:
            if "output_index" in item:
                item["output_index"] = 1
        client, _ = self._client(sse(*events))
        self._assert_error("invalid_stream", client)
        events = compact_lifecycle("Reply")
        duplicate = dict(events[-2], sequence_number=events[-1]["sequence_number"])
        events.insert(-1, duplicate)
        events[-1]["sequence_number"] += 1
        client, _ = self._client(sse(*events))
        self._assert_error("invalid_stream", client)

    def test_compact_terminal_rejects_unfinished_observed_item(self) -> None:
        events = compact_lifecycle("Reply")
        events.insert(-1, event("response.output_item.added", events[-1]["sequence_number"], output_index=1,
                               item={"id": "msg_unfinished", "type": "message", "status": "in_progress"}))
        events[-1]["sequence_number"] += 1
        client, _ = self._client(sse(*events))
        self._assert_error("invalid_stream", client)

    def test_delta_after_item_finalization_is_rejected(self) -> None:
        events = compact_lifecycle("Reply")
        events.insert(-1, delta("Late", events[-1]["sequence_number"]))
        events[-1]["sequence_number"] += 1
        client, _ = self._client(sse(*events))
        self._assert_error("invalid_stream", client)
        self.assertEqual(self.deltas, ["Reply"])

    def test_nonempty_terminal_cannot_contradict_finalized_snapshot(self) -> None:
        events = compact_lifecycle("Reply")
        events[-1]["response"]["output"] = completed("Different")["response"]["output"]
        client, _ = self._client(sse(*events))
        self._assert_error("invalid_stream", client)

    def test_nonempty_terminal_ignores_unrelated_item_metadata_differences(self) -> None:
        events = compact_lifecycle("Reply")
        events[-2]["item"]["metadata"] = {"ignored": "first"}
        output = completed("Reply")["response"]["output"]
        output[0]["metadata"] = {"ignored": "second"}
        events[-1]["response"]["output"] = output
        client, _ = self._client(sse(*events))
        self.assertEqual(self._reply(client), "Reply")

    def test_compact_failed_terminal_after_finalized_item_is_not_completion(self) -> None:
        events = compact_lifecycle("Reply")
        events[-1] = event("response.failed", events[-1]["sequence_number"], response={
            "id": "resp_example", "status": "failed", "error": {"code": "subscription_sharing_usage_limit_exceeded"}})
        client, _ = self._client(sse(*events))
        self._assert_error("usage_limit", client)

    def test_usage_limit_after_delta_is_failure_with_no_completed_answer_and_no_retry(self) -> None:
        for code in ("subscription_sharing_usage_limit_exceeded", "subscription_sharing_usage_unavailable"):
            with self.subTest(code=code):
                failed = event("response.failed", 2, response={
                    "id": "resp_example", "status": "failed", "error": {"code": code, "message": "Private server detail"},
                })
                client, http = self._client(sse(created(), delta("Partial"), failed))
                self.deltas.clear()
                error = self._assert_error("usage_limit", client)
                self.assertEqual(self.deltas, ["Partial"])
                self.assertNotIn("Private", str(error))
                self.assertEqual(len(http.requests), 2)
                self.assertTrue(http.streams[-1].closed)

    def test_failed_incomplete_and_explicit_error_are_distinct_from_completion(self) -> None:
        endings = (
            (event("response.failed", 2, response={"id": "resp_example", "error": {"code": "server_error", "message": TOKEN}}), "failed"),
            (event("response.incomplete", 2, response={"id": "resp_example", "incomplete_details": {"reason": "max_output_tokens"}}), "incomplete"),
            (event("error", 2, code="server_error", message=TOKEN), "failed"),
            (event("error", 2, code="subscription_sharing_usage_unavailable", message=TOKEN), "usage_limit"),
        )
        for ending, code in endings:
            with self.subTest(code=code, kind=ending["type"]):
                client, _ = self._client(sse(created(), delta("Partial"), ending))
                error = self._assert_error(code, client)
                self.assertNotIn(TOKEN, str(error))

    def test_usage_limit_before_response_creation_is_still_reported(self) -> None:
        failed = event("response.failed", 0, response={
            "id": "resp_example", "status": "failed", "error": {"code": "subscription_sharing_usage_limit_exceeded"},
        })
        client, _ = self._client(sse(failed))
        self._assert_error("usage_limit", client)
        self.assertEqual(self.deltas, [])

    def test_eof_after_partial_text_or_text_done_is_not_success(self) -> None:
        done = event("response.output_text.done", 2, item_id="msg_example", output_index=0, content_index=0, text="Partial")
        for stream in (sse(created(), delta("Partial")), sse(created(), delta("Partial"), done), b""):
            with self.subTest(stream=stream):
                client, _ = self._client(stream)
                self._assert_error("incomplete", client)

    def test_crlf_multiline_json_comments_and_byte_split_utf8(self) -> None:
        response = completed("café 🙂\nnext")
        encoded = json.dumps(response, ensure_ascii=False, indent=2).encode("utf-8")
        multiline = b"event: response.completed\r\n" + b"\r\n".join(b"data: " + line for line in encoded.splitlines()) + b"\r\n\r\n"
        raw = b": heartbeat\r\n\r\n" + sse(created(), delta("café 🙂\nnext"), newline=b"\r\n") + multiline
        client, _ = self._client(FakeStream(raw, chunk_size=1))
        self.assertEqual(self._reply(client), "café 🙂\nnext")

    def test_lone_carriage_return_sse_line_endings_are_supported(self) -> None:
        client, _ = self._client(FakeStream(sse(created(), delta("Answer"), completed("Answer"), newline=b"\r"), chunk_size=1))
        self.assertEqual(self._reply(client), "Answer")

    def test_malformed_invalid_utf8_and_unterminated_events_are_safe_failures(self) -> None:
        bad_streams = (
            b"data: not-json\n\n",
            b'data: {"type": "response.created", "private": "\xff"}\n\n',
            sse(created()) + b'data: {"type":"response.completed"}',
            b'event: wrong\ndata: {"type":"response.created"}\n\n',
            b'data: []\n\n',
            b'data: [DONE]\n\n',
        )
        for stream in bad_streams:
            with self.subTest(stream=stream):
                client, http = self._client(stream)
                error = self._assert_error("invalid_stream", client)
                self.assertNotIn("private", str(error))
                self.assertEqual(len(http.requests), 2)

    def test_escaped_invalid_unicode_and_null_text_are_rejected_before_display(self) -> None:
        for text in ("\ud800", "a\x00b"):
            with self.subTest(text=repr(text)):
                # JSON may encode a surrogate that is not a valid Unicode character.
                encoded = json.dumps(delta(text)).encode("ascii")
                client, _ = self._client(sse(created()) + b"data: " + encoded + b"\n\n")
                self._assert_error("invalid_stream", client)
                self.assertEqual(self.deltas, [])

    def test_event_total_and_event_count_bounds(self) -> None:
        for setting, limit, raw in (
            ("MAX_SSE_EVENT_BYTES", 32, b":" + b"x" * 40),
            ("MAX_STREAM_BYTES", 64, sse(created(), delta("Answer"), completed("Answer"))),
            ("MAX_STREAM_EVENTS", 1, sse(created(), delta("Answer"), completed("Answer"))),
        ):
            with self.subTest(setting=setting), patch("context_palette.chatgpt_client." + setting, limit):
                client, _ = self._client(raw)
                self._assert_error("stream_limit", client)

    def test_output_limit_before_oversized_delta_reaches_callback(self) -> None:
        client, _ = self._client(sse(created(), delta("12345"), completed("12345")))
        with patch("context_palette.chatgpt_client.MAX_OUTPUT_CHARS", 4):
            self._assert_error("output_limit", client)
        self.assertEqual(self.deltas, [])

    def test_response_ids_item_ids_deltas_order_and_terminal_snapshot_must_agree(self) -> None:
        wrong_item = completed("Answer")
        wrong_item["response"]["output"][0]["id"] = "other-message"
        wrong_status = completed("Answer")
        wrong_status["response"]["status"] = "in_progress"
        streams = (
            sse(created(), delta("Answer"), completed("Answer", response_id="resp_other")),
            sse(created(), delta("Answer", response_id="resp_other"), completed("Answer")),
            sse(created(), delta("Partial"), completed("Different")),
            sse(created(), delta("Answer"), wrong_item),
            sse(created(), delta("Answer"), wrong_status),
            sse(delta("Answer"), completed("Answer")),
            sse(created(), created(), delta("Answer"), completed("Answer")),
            sse(created(), delta("Answer"), completed("Answer", sequence=1)),
        )
        for stream in streams:
            with self.subTest(stream=stream):
                client, _ = self._client(stream)
                self._assert_error("invalid_stream", client)

    def test_text_done_must_match_and_no_later_delta_can_append_to_done_part(self) -> None:
        done = event("response.output_text.done", 2, item_id="msg_example", output_index=0, content_index=0, text="Answer")
        for ending in (
            event("response.output_text.done", 2, item_id="msg_example", output_index=0, content_index=0, text="Wrong"),
            delta(" extra", sequence=3),
        ):
            stream = sse(created(), delta("Answer"), ending) if ending["type"].endswith("done") else sse(created(), delta("Answer"), done, ending)
            client, _ = self._client(stream)
            self._assert_error("invalid_stream", client)

    def test_reasoning_can_precede_text_but_its_content_is_not_returned(self) -> None:
        answer = completed("Answer")
        answer["response"]["output"].insert(0, {"id": "reason_example", "type": "reasoning", "summary": []})
        streamed = delta("Answer")
        streamed["output_index"] = 1
        client, _ = self._client(sse(created(), streamed, answer))
        self.assertEqual(self._reply(client), "Answer")

    def test_completed_refusal_is_supported_text(self) -> None:
        streamed = event("response.refusal.delta", 1, item_id="msg_example", output_index=0, content_index=0, delta="I cannot help with that.")
        answer = completed("unused")
        answer["response"]["output"][0]["content"] = [{"type": "refusal", "refusal": "I cannot help with that."}]
        client, _ = self._client(sse(created(), streamed, answer))
        self.assertEqual(self._reply(client), "I cannot help with that.")

    def test_empty_nontext_and_tool_output_are_never_success(self) -> None:
        tool = completed("Answer")
        tool["response"]["output"].append({"type": "function_call", "id": "call_example"})
        nontext = completed("Answer")
        nontext["response"]["output"][0]["content"].append({"type": "output_audio"})
        empty = completed("")
        for ending, code in ((tool, "unsupported_output"), (nontext, "unsupported_output"), (empty, "empty_output")):
            with self.subTest(code=code):
                client, _ = self._client(sse(created(), delta("" if code == "empty_output" else "Answer"), ending))
                self._assert_error(code, client)

    def test_invalid_input_and_size_limits_fail_before_network(self) -> None:
        client, http = self._client()
        invalid = (
            [], [ChatMessage("system", "Secret")], [ChatMessage("user", " ")],
            [ChatMessage("assistant", "Wrong first role")], [ChatMessage("user", "A"), ChatMessage("assistant", "A")],
            [ChatMessage("user", "A"), ChatMessage("user", "B")],
            [ChatMessage("user", "\x00")], [ChatMessage("user", "\ud800")],
        )
        for messages in invalid:
            with self.subTest(messages=messages):
                self._assert_error("invalid_input", client, messages=messages)
        overlong = [ChatMessage("user", "x" * (MAX_MESSAGE_CHARS + 1))]
        many = [ChatMessage("user" if index % 2 == 0 else "assistant", "x") for index in range(MAX_MESSAGES + 1)]
        total = [ChatMessage("user", "x" * MAX_MESSAGE_CHARS), ChatMessage("assistant", "x" * MAX_MESSAGE_CHARS), ChatMessage("user", "x")]
        self.assertGreater(sum(len(message.text) for message in total), MAX_INPUT_CHARS)
        for messages in (overlong, many, total):
            self._assert_error("input_limit", client, messages=messages)
        self.assertEqual(len(http.requests), 1)

    def test_pre_cancelled_request_opens_no_connection(self) -> None:
        http = FakeHTTP()
        self.cancel.set()
        self._assert_error("cancelled", ChatGPTClient(http))
        self.assertEqual(http.requests, [])

    def test_cancellation_after_delta_prevents_success_and_closes_stream(self) -> None:
        client, http = self._client(sse(created(), delta("Partial"), completed("Partial")))
        def cancel_after_delta(text: str) -> None:
            self.deltas.append(text)
            self.cancel.set()
        error = self._assert_error("cancelled", client, callback=cancel_after_delta)
        self.assertIn("may still have processed", str(error))
        self.assertEqual(self.deltas, ["Partial"])
        self.assertTrue(http.streams[-1].closed)
        self.assertEqual(len(http.requests), 2)

    def test_cancellation_during_blocked_read_wins_over_timeout(self) -> None:
        class CancelTimeout(FakeStream):
            def read1(inner_self, size=-1):
                self.cancel.set()
                raise TimeoutError(TOKEN)
        client, _ = self._client(CancelTimeout(b""))
        self._assert_error("cancelled", client)

    def test_stream_timeout_and_read_error_are_fixed_and_never_retried(self) -> None:
        for failure, code in ((TimeoutError(TOKEN), "timeout"), (OSError("Private prompt " + TOKEN), "network")):
            with self.subTest(code=code):
                client, http = self._client(failure)
                error = self._assert_error(code, client)
                self.assertNotIn(TOKEN, str(error))
                self.assertNotIn(TOKEN, repr(error))
                self.assertIn("not retried", str(error))
                self.assertEqual(len(http.requests), 2)

    def test_transport_classified_timeout_and_connection_errors_keep_processing_ambiguity(self) -> None:
        for code in ("timeout", "connection"):
            with self.subTest(code=code):
                client, http = self._client(ChatGPTError(code, "A fixed transport error."))
                error = self._assert_error("timeout" if code == "timeout" else "network", client)
                self.assertIn("not retried", str(error))
                self.assertEqual(len(http.requests), 2)

    def test_no_chat_content_or_token_is_logged_on_success_or_failure(self) -> None:
        client, _ = self._client(sse(created(), delta("Private answer"), completed("Private answer")), OSError("Private prompt " + TOKEN))
        with self.assertNoLogs("context_palette", level="DEBUG"):
            self.assertEqual(self._reply(client), "Private answer")
            self._assert_error("network", client)

    def test_wall_clock_deadline_catches_slow_successful_reads(self) -> None:
        client, http = self._client(sse(created(), delta("Answer"), completed("Answer")))
        with patch("context_palette.chatgpt_client.RESPONSE_TIMEOUT_SECONDS", 2), patch("context_palette.chatgpt_client.time.monotonic", side_effect=[0, 0, 0, 3]):
            self._assert_error("timeout", client)
        self.assertTrue(http.streams[-1].closed)

    def test_callback_failure_cannot_leak_prompt_or_become_completed_answer(self) -> None:
        client, _ = self._client(sse(created(), delta("Answer"), completed("Answer")))
        def broken_callback(text: str) -> None:
            raise ValueError("Private prompt " + TOKEN)
        error = self._assert_error("callback", client, callback=broken_callback)
        self.assertNotIn(TOKEN, str(error))

    def test_tokens_and_message_text_are_absent_from_errors_and_message_repr(self) -> None:
        self.assertNotIn("Private prompt", repr(ChatMessage("user", "Private prompt")))
        for token in ("", "token\nPrivate prompt", "token with space", "é"):
            with self.subTest(token=token):
                http = FakeHTTP()
                with self.assertRaises(ChatGPTError) as caught:
                    ChatGPTClient(http).list_models(token, self.cancel)
                self.assertEqual(caught.exception.code, "invalid_token")
                self.assertNotIn("Private prompt", str(caught.exception))
                self.assertEqual(http.requests, [])


if __name__ == "__main__":
    unittest.main()
