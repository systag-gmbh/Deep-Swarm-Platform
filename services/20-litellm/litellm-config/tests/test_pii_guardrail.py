"""Tests for PII guardrail: chat completions, legacy completions, and Responses API."""

import asyncio
import copy
import pathlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock litellm before importing the guardrail module (litellm not installed in dev)
_MockCustomGuardrail = type("CustomGuardrail", (), {})
_mock_cg_module = MagicMock()
_mock_cg_module.CustomGuardrail = _MockCustomGuardrail
sys.modules.setdefault("litellm", MagicMock())
sys.modules.setdefault("litellm.integrations", MagicMock())
sys.modules.setdefault("litellm.integrations.custom_guardrail", _mock_cg_module)

# Add litellm-config to path so we can import pii_guardrail
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from pii_guardrail import PiiGuardrail, _deanonymize, _mapping_cache


# --- Fixtures ---

ENTITY_MAPPING = {
    "<PERSON_1>": "Robin Smith",
    "<EMAIL_ADDRESS_1>": "robin@example.com",
}


@pytest.fixture
def guardrail():
    return PiiGuardrail()


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear mapping cache between tests."""
    _mapping_cache.clear()
    yield
    _mapping_cache.clear()


@pytest.fixture(autouse=True)
def mock_cache_response():
    """Prevent actual HTTP calls from fire-and-forget cache tasks."""
    with patch("pii_guardrail._cache_response_async", new_callable=AsyncMock):
        yield


def _store_mapping(request_id, session_id="test-session"):
    _mapping_cache.set(
        request_id,
        {"entity_mapping": ENTITY_MAPPING, "session_id": session_id},
        expire=300,
    )


# --- Helpers for streaming tests ---


async def _collect_chunks(async_gen):
    """Collect all chunks from an async generator into a list."""
    chunks = []
    async for chunk in async_gen:
        chunks.append(chunk)
    return chunks


# --- Unit: _deanonymize ---


class TestDeanonymize:
    def test_replaces_all_placeholders(self):
        text = "Hello <PERSON_1>, your email is <EMAIL_ADDRESS_1>"
        result = _deanonymize(text, ENTITY_MAPPING)
        assert result == "Hello Robin Smith, your email is robin@example.com"

    def test_no_placeholders_unchanged(self):
        assert _deanonymize("no placeholders", ENTITY_MAPPING) == "no placeholders"

    def test_empty_mapping(self):
        assert _deanonymize("<PERSON_1>", {}) == "<PERSON_1>"


# --- Pre-call: async_pre_call_hook ---


class TestPreCallChat:
    """Pre-call hook with standard chat messages."""

    @pytest.mark.asyncio
    async def test_masks_chat_messages(self, guardrail):
        data = {
            "messages": [
                {"role": "user", "content": "Hi, I'm Robin Smith, email robin@example.com"}
            ],
            "litellm_call_id": "req-chat-1",
        }
        presidio_resp = {
            "messages": [
                {"role": "user", "content": "Hi, I'm <PERSON_1>, email <EMAIL_ADDRESS_1>"}
            ],
            "entity_mapping": ENTITY_MAPPING,
        }
        with patch("pii_guardrail._presidio_post", return_value=presidio_resp):
            result = await guardrail.async_pre_call_hook({}, None, data, "completion")

        assert result["messages"][0]["content"] == "Hi, I'm <PERSON_1>, email <EMAIL_ADDRESS_1>"
        cached = _mapping_cache.get("req-chat-1")
        assert cached["entity_mapping"] == ENTITY_MAPPING

    @pytest.mark.asyncio
    async def test_no_messages_passthrough(self, guardrail):
        data = {"litellm_call_id": "req-empty"}
        result = await guardrail.async_pre_call_hook({}, None, data, "completion")
        assert result == data


class TestPreCallLegacyCompletions:
    """Pre-call hook with /v1/completions prompt format."""

    @pytest.mark.asyncio
    async def test_string_prompt(self, guardrail):
        data = {
            "prompt": "Hi, I'm Robin Smith",
            "litellm_call_id": "req-prompt-str",
        }
        presidio_resp = {
            "messages": [{"role": "user", "content": "Hi, I'm <PERSON_1>"}],
            "entity_mapping": ENTITY_MAPPING,
        }
        with patch("pii_guardrail._presidio_post", return_value=presidio_resp):
            result = await guardrail.async_pre_call_hook({}, None, data, "completion")

        assert result["prompt"] == "Hi, I'm <PERSON_1>"
        assert "_pii_prompt_mode" not in result

    @pytest.mark.asyncio
    async def test_list_prompt(self, guardrail):
        data = {
            "prompt": ["prompt one by Robin Smith", "prompt two by Robin Smith"],
            "litellm_call_id": "req-prompt-list",
        }
        presidio_resp = {
            "messages": [
                {"role": "user", "content": "prompt one by <PERSON_1>"},
                {"role": "user", "content": "prompt two by <PERSON_1>"},
            ],
            "entity_mapping": ENTITY_MAPPING,
        }
        with patch("pii_guardrail._presidio_post", return_value=presidio_resp):
            result = await guardrail.async_pre_call_hook({}, None, data, "completion")

        assert result["prompt"] == ["prompt one by <PERSON_1>", "prompt two by <PERSON_1>"]


# --- Post-call non-streaming: async_post_call_success_hook ---


class TestPostCallChat:
    """Non-streaming deanonymization for chat completions."""

    @pytest.mark.asyncio
    async def test_deanonymizes_message_content(self, guardrail):
        _store_mapping("req-post-chat")
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content="Hello <PERSON_1>"))
            ]
        )
        data = {"litellm_call_id": "req-post-chat"}
        result = await guardrail.async_post_call_success_hook(data, {}, response)
        assert result.choices[0].message.content == "Hello Robin Smith"

    @pytest.mark.asyncio
    async def test_no_mapping_passthrough(self, guardrail):
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content="Hello <PERSON_1>"))
            ]
        )
        data = {"litellm_call_id": "req-no-mapping"}
        result = await guardrail.async_post_call_success_hook(data, {}, response)
        assert result.choices[0].message.content == "Hello <PERSON_1>"


class TestPostCallLegacyCompletions:
    """Non-streaming deanonymization for /v1/completions (choice.text)."""

    @pytest.mark.asyncio
    async def test_deanonymizes_choice_text(self, guardrail):
        _store_mapping("req-post-legacy")
        # choice.text without choice.message — simulates legacy completions response
        response = SimpleNamespace(
            choices=[SimpleNamespace(text="Hello <PERSON_1>")]
        )
        data = {"litellm_call_id": "req-post-legacy"}
        result = await guardrail.async_post_call_success_hook(data, {}, response)
        assert result.choices[0].text == "Hello Robin Smith"


class TestPostCallResponsesAPI:
    """Non-streaming deanonymization for /v1/responses format."""

    @pytest.mark.asyncio
    async def test_deanonymizes_output_text(self, guardrail):
        _store_mapping("req-post-responses")
        response = SimpleNamespace(
            output=[
                SimpleNamespace(
                    content=[
                        SimpleNamespace(type="output_text", text="Hello <PERSON_1>"),
                    ]
                )
            ]
        )
        data = {"litellm_call_id": "req-post-responses"}
        result = await guardrail.async_post_call_success_hook(data, {}, response)
        assert result.output[0].content[0].text == "Hello Robin Smith"

    @pytest.mark.asyncio
    async def test_skips_non_text_parts(self, guardrail):
        _store_mapping("req-post-resp-mixed")
        response = SimpleNamespace(
            output=[
                SimpleNamespace(
                    content=[
                        SimpleNamespace(type="image", text=None),
                        SimpleNamespace(type="output_text", text="<EMAIL_ADDRESS_1>"),
                    ]
                )
            ]
        )
        data = {"litellm_call_id": "req-post-resp-mixed"}
        result = await guardrail.async_post_call_success_hook(data, {}, response)
        assert result.output[0].content[1].text == "robin@example.com"


# --- Post-call streaming: async_post_call_streaming_iterator_hook ---


class TestStreamingChat:
    """Streaming deanonymization for chat completions (delta.content)."""

    @pytest.mark.asyncio
    async def test_deanonymizes_across_chunks(self, guardrail):
        _store_mapping("req-stream-chat")

        async def mock_stream():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="Hello <PER"))]
            )
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="SON_1>!"))]
            )

        data = {"litellm_call_id": "req-stream-chat"}
        gen = guardrail.async_post_call_streaming_iterator_hook(
            {}, mock_stream(), data
        )
        chunks = await _collect_chunks(gen)

        full_text = ""
        for c in chunks:
            delta = getattr(c.choices[0], "delta", None)
            if delta and hasattr(delta, "content") and delta.content:
                full_text += delta.content

        assert "Robin Smith" in full_text
        assert "<PERSON_1>" not in full_text

    @pytest.mark.asyncio
    async def test_no_mapping_streams_through(self, guardrail):
        async def mock_stream():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="Hello there"))]
            )

        data = {"litellm_call_id": "req-stream-nomatch"}
        gen = guardrail.async_post_call_streaming_iterator_hook(
            {}, mock_stream(), data
        )
        chunks = await _collect_chunks(gen)
        assert chunks[0].choices[0].delta.content == "Hello there"


class TestStreamingLegacyCompletions:
    """Streaming deanonymization for /v1/completions (choice.text)."""

    @pytest.mark.asyncio
    async def test_deanonymizes_choice_text_stream(self, guardrail):
        _store_mapping("req-stream-legacy")

        async def mock_stream():
            yield SimpleNamespace(choices=[SimpleNamespace(text="Hello <PER")])
            yield SimpleNamespace(choices=[SimpleNamespace(text="SON_1>!")])

        data = {"litellm_call_id": "req-stream-legacy"}
        gen = guardrail.async_post_call_streaming_iterator_hook(
            {}, mock_stream(), data
        )
        chunks = await _collect_chunks(gen)

        full_text = ""
        for c in chunks:
            for choice in c.choices:
                if hasattr(choice, "text") and choice.text:
                    full_text += choice.text

        assert "Robin Smith" in full_text
        assert "<PERSON_1>" not in full_text


class TestStreamingResponsesAPI:
    """Streaming deanonymization for Responses API events."""

    @pytest.mark.asyncio
    async def test_deanonymizes_delta_events(self, guardrail):
        _store_mapping("req-stream-resp")

        async def mock_stream():
            yield SimpleNamespace(type="response.output_text.delta", delta="Hello <PER")
            yield SimpleNamespace(type="response.output_text.delta", delta="SON_1>!")

        data = {"litellm_call_id": "req-stream-resp"}
        gen = guardrail.async_post_call_streaming_iterator_hook(
            {}, mock_stream(), data
        )
        chunks = await _collect_chunks(gen)

        full_text = ""
        for c in chunks:
            d = getattr(c, "delta", None)
            if isinstance(d, str):
                full_text += d

        assert "Robin Smith" in full_text
        assert "<PERSON_1>" not in full_text

    @pytest.mark.asyncio
    async def test_deanonymizes_done_event(self, guardrail):
        _store_mapping("req-stream-done")

        async def mock_stream():
            yield SimpleNamespace(
                type="response.output_text.done",
                text="Hello <PERSON_1>",
            )

        data = {"litellm_call_id": "req-stream-done"}
        gen = guardrail.async_post_call_streaming_iterator_hook(
            {}, mock_stream(), data
        )
        chunks = await _collect_chunks(gen)
        assert chunks[0].text == "Hello Robin Smith"

    @pytest.mark.asyncio
    async def test_deanonymizes_completed_event(self, guardrail):
        _store_mapping("req-stream-completed")

        async def mock_stream():
            yield SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(
                    output=[
                        SimpleNamespace(
                            content=[
                                SimpleNamespace(
                                    type="output_text", text="Hello <PERSON_1>"
                                )
                            ]
                        )
                    ]
                ),
            )

        data = {"litellm_call_id": "req-stream-completed"}
        gen = guardrail.async_post_call_streaming_iterator_hook(
            {}, mock_stream(), data
        )
        chunks = await _collect_chunks(gen)
        assert chunks[0].response.output[0].content[0].text == "Hello Robin Smith"

    @pytest.mark.asyncio
    async def test_passthrough_non_text_events(self, guardrail):
        _store_mapping("req-stream-passthru")

        async def mock_stream():
            yield SimpleNamespace(type="response.created", response=None)
            yield SimpleNamespace(type="response.in_progress", response=None)

        data = {"litellm_call_id": "req-stream-passthru"}
        gen = guardrail.async_post_call_streaming_iterator_hook(
            {}, mock_stream(), data
        )
        chunks = await _collect_chunks(gen)
        assert len(chunks) == 2
        assert chunks[0].type == "response.created"
        assert chunks[1].type == "response.in_progress"
