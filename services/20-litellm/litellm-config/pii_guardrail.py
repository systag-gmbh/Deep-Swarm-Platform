"""
LiteLLM guardrail for PII masking and deanonymization.

Pre-call: sends all messages to /anonymize_conversation, stores entity_mapping in DiskCache.
Post-call: pops entity_mapping from DiskCache, replaces placeholders in LLM response.
"""

import asyncio
import copy
import json
import logging
import os
import urllib.request
from typing import Any, AsyncGenerator, Optional, Union
from uuid import uuid4

from diskcache import Cache
from litellm.integrations.custom_guardrail import CustomGuardrail

logger = logging.getLogger("pii-guardrail")

PRESIDIO_API = os.getenv("PRESIDIO_ANALYZER_API_BASE", "http://presidio-analyzer:5002")

# DiskCache for deanonymization mappings (cross-process safe)
_mapping_cache = Cache("/tmp/pii_cache/mappings")
_MAPPING_TTL = 300  # 5 minutes


def _get_request_id(data: dict) -> str:
    """Extract a stable request identifier present in both pre_call and post_call."""
    for value in [
        data.get("litellm_call_id"),
        data.get("metadata", {}).get("litellm_call_id"),
        getattr(data.get("litellm_logging_obj"), "litellm_call_id", None),
        data.get("metadata", {}).get("request_id"),
    ]:
        if value:
            return str(value)
    return "unknown"


def _get_session_id(data: dict) -> str:
    """Resolve session ID from LiteLLM params, falling back to a generated UUID.

    Priority chain (modeled after LiteLLM's ChatGPT utils):
    1. litellm_session_id (explicit session)
    2. session_id (explicit)
    3. metadata.session_id (current approach)
    4. litellm_trace_id (auto-generated, stable if client passes it)
    5. metadata.litellm_trace_id
    6. Fallback: uuid4() (per-request, within-request dedup only)
    """
    metadata = data.get("metadata", {})
    for value in [
        data.get("litellm_session_id"),
        data.get("session_id"),
        metadata.get("session_id"),
        data.get("litellm_trace_id"),
        metadata.get("litellm_trace_id"),
    ]:
        if value:
            return str(value)
    return str(uuid4())


def _presidio_post(endpoint: str, payload: dict) -> Any:
    """Synchronous HTTP POST to Presidio analyzer."""
    url = f"{PRESIDIO_API}{endpoint}"
    raw = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _deanonymize(text: str, entity_mapping: dict) -> str:
    """Replace placeholders with original values."""
    for placeholder, original in entity_mapping.items():
        text = text.replace(placeholder, original)
    return text


async def _cache_response_async(
    session_id: str,
    deanonymized_text: str,
    masked_text: str,
    entity_mapping: dict,
) -> None:
    """Fire-and-forget: cache masked response for next-turn cache hits."""
    try:
        await asyncio.to_thread(
            _presidio_post,
            "/cache_response",
            {
                "session_id": session_id,
                "deanonymized_text": deanonymized_text,
                "masked_text": masked_text,
                "entity_mapping": entity_mapping,
            },
        )
    except Exception:
        logger.warning("[PII-CACHE] Failed to cache response, will re-analyze next turn")


class PiiGuardrail(CustomGuardrail):
    """PII masking guardrail using conversation-aware Presidio endpoint."""

    async def async_pre_call_hook(
        self,
        user_api_key_dict: dict,
        cache: Any,
        data: dict,
        call_type: str,
        **kwargs,
    ) -> Optional[Union[Exception, str, dict]]:
        """Mask PII in all input messages via single /anonymize_conversation call."""
        messages = data.get("messages")

        # Legacy completions: convert prompt to messages for Presidio
        prompt = data.get("prompt")
        if not messages and prompt:
            if isinstance(prompt, str):
                prompt = [prompt]
            messages = [{"role": "user", "content": p} for p in prompt]
            data["_pii_prompt_mode"] = True  # flag for writing back

        if not messages:
            return data

        # Resolve session_id from multiple LiteLLM sources
        session_id = _get_session_id(data)

        # Build payload — only send role + content
        payload = {"session_id": session_id, "messages": []}
        for msg in messages:
            payload["messages"].append({
                "role": msg.get("role", "user"),
                "content": msg.get("content"),
            })

        result = _presidio_post("/anonymize_conversation", payload)

        # Replace message contents with masked versions
        for i, masked_msg in enumerate(result["messages"]):
            if i < len(messages) and masked_msg["content"] is not None:
                messages[i]["content"] = masked_msg["content"]

        # Legacy completions: write masked text back to prompt
        if data.pop("_pii_prompt_mode", False):
            masked_prompts = [m["content"] for m in messages]
            data["prompt"] = masked_prompts[0] if len(masked_prompts) == 1 else masked_prompts

        # Store entity mapping for deanonymization
        entity_mapping = result.get("entity_mapping", {})
        request_id = _get_request_id(data)
        if entity_mapping:
            _mapping_cache.set(
                request_id,
                {"entity_mapping": entity_mapping, "session_id": session_id},
                expire=_MAPPING_TTL,
            )
            logger.error(
                f"[PII-MASK] req={request_id} entities={list(entity_mapping.keys())}"
            )

        return data

    async def async_post_call_success_hook(
        self,
        data: dict,
        user_api_key_dict: dict,
        response: Any,
        **kwargs,
    ) -> Any:
        """Deanonymize the LLM response (non-streaming) and cache masked version."""
        request_id = _get_request_id(data)
        cached = _mapping_cache.pop(request_id, {})

        entity_mapping = cached.get("entity_mapping", {}) if isinstance(cached, dict) else cached
        session_id = cached.get("session_id") if isinstance(cached, dict) else None

        if not entity_mapping:
            return response

        # Chat/legacy completions: response.choices[].message.content or .text
        if hasattr(response, "choices") and response.choices:
            for choice in response.choices:
                if (
                    hasattr(choice, "message")
                    and hasattr(choice.message, "content")
                    and isinstance(choice.message.content, str)
                ):
                    masked_text = choice.message.content
                    choice.message.content = _deanonymize(
                        choice.message.content, entity_mapping
                    )
                    if session_id:
                        asyncio.create_task(
                            _cache_response_async(
                                session_id, choice.message.content,
                                masked_text, entity_mapping,
                            )
                        )
                elif hasattr(choice, "text") and isinstance(choice.text, str):
                    masked_text = choice.text
                    choice.text = _deanonymize(choice.text, entity_mapping)
                    if session_id:
                        asyncio.create_task(
                            _cache_response_async(
                                session_id, choice.text,
                                masked_text, entity_mapping,
                            )
                        )

        # Responses API format: response.output[].content[].text
        elif hasattr(response, "output") and response.output:
            masked_parts = []
            for output_item in response.output:
                content_list = getattr(output_item, "content", None)
                if not content_list:
                    continue
                for part in content_list:
                    part_type = getattr(part, "type", None)
                    text = getattr(part, "text", None)
                    if part_type == "output_text" and isinstance(text, str):
                        masked_parts.append(text)
                        part.text = _deanonymize(text, entity_mapping)
            if session_id and masked_parts:
                masked_text = "".join(masked_parts)
                deanonymized_text = _deanonymize(masked_text, entity_mapping)
                asyncio.create_task(
                    _cache_response_async(
                        session_id, deanonymized_text,
                        masked_text, entity_mapping,
                    )
                )

        logger.error(f"[PII-UNMASK] req={request_id} deanonymized")
        return response

    async def async_post_call_streaming_iterator_hook(
        self,
        user_api_key_dict: dict,
        response: AsyncGenerator,
        request_data: dict,
        **kwargs,
    ) -> AsyncGenerator:
        """Deanonymize streaming LLM response and cache masked version."""
        request_id = _get_request_id(request_data)
        cached = _mapping_cache.pop(request_id, {})

        entity_mapping = cached.get("entity_mapping", {}) if isinstance(cached, dict) else cached
        session_id = cached.get("session_id") if isinstance(cached, dict) else None

        if not entity_mapping:
            async for chunk in response:
                yield chunk
            return

        buffer = ""
        masked_buffer = ""  # Track full masked response for caching
        last_chunk = None
        is_responses_api = False

        async for chunk in response:
            content = None

            # Chat/legacy completions: chunk.choices[].delta.content or .text
            if hasattr(chunk, "choices") and chunk.choices:
                for choice in chunk.choices:
                    delta = getattr(choice, "delta", None)
                    if delta and hasattr(delta, "content") and delta.content:
                        content = delta.content
                    elif hasattr(choice, "text") and choice.text:
                        content = choice.text

            # Responses API format: OutputTextDeltaEvent with .delta str
            elif getattr(chunk, "type", None) == "response.output_text.delta":
                content = getattr(chunk, "delta", None)
                is_responses_api = True

            # Responses API: deanonymize the done/completed summary events
            elif getattr(chunk, "type", None) == "response.output_text.done":
                text = getattr(chunk, "text", None)
                if isinstance(text, str) and entity_mapping:
                    chunk_copy = copy.deepcopy(chunk)
                    chunk_copy.text = _deanonymize(text, entity_mapping)
                    yield chunk_copy
                    continue
                yield chunk
                continue

            elif getattr(chunk, "type", None) == "response.completed":
                chunk_copy = copy.deepcopy(chunk)
                resp = getattr(chunk_copy, "response", None)
                if resp and hasattr(resp, "output"):
                    for output_item in resp.output:
                        content_list = getattr(output_item, "content", None)
                        if not content_list:
                            continue
                        for part in content_list:
                            if getattr(part, "type", None) == "output_text":
                                text = getattr(part, "text", None)
                                if isinstance(text, str):
                                    part.text = _deanonymize(text, entity_mapping)
                yield chunk_copy
                continue

            if content is None:
                yield chunk
                continue

            last_chunk = chunk
            buffer += content
            masked_buffer += content

            for placeholder, original in entity_mapping.items():
                buffer = buffer.replace(placeholder, original)

            last_open = buffer.rfind("<")
            if last_open >= 0 and ">" not in buffer[last_open:]:
                emit = buffer[:last_open]
                buffer = buffer[last_open:]
            else:
                emit = buffer
                buffer = ""

            if emit:
                chunk_copy = copy.deepcopy(chunk)
                if is_responses_api:
                    chunk_copy.delta = emit
                else:
                    for choice in chunk_copy.choices:
                        delta = getattr(choice, "delta", None)
                        if delta and hasattr(delta, "content") and delta.content:
                            delta.content = emit
                        elif hasattr(choice, "text"):
                            choice.text = emit
                yield chunk_copy

        if buffer and last_chunk:
            for placeholder, original in entity_mapping.items():
                buffer = buffer.replace(placeholder, original)
            chunk_copy = copy.deepcopy(last_chunk)
            if is_responses_api:
                chunk_copy.delta = buffer
            else:
                for choice in chunk_copy.choices:
                    delta = getattr(choice, "delta", None)
                    if delta and hasattr(delta, "content"):
                        delta.content = buffer
                    elif hasattr(choice, "text"):
                        choice.text = buffer
            yield chunk_copy

        # Cache the full masked response for next-turn cache hits
        if session_id and masked_buffer:
            deanonymized_full = _deanonymize(masked_buffer, entity_mapping)
            asyncio.create_task(
                _cache_response_async(
                    session_id, deanonymized_full,
                    masked_buffer, entity_mapping,
                )
            )

        logger.error(f"[PII-UNMASK] req={request_id} deanonymized (streaming)")
