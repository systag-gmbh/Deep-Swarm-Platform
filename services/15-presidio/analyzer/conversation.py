"""Conversation-level anonymization with optional session caching."""

import hashlib
import json
import logging
from pathlib import Path

from diskcache import Cache

from anonymize import remove_overlapping
from titles import strip_title

logger = logging.getLogger("conversation")

_CACHE_DIR = Path("/tmp/pii_cache")

# Entity registry: "{session}:{type}:{text_lower}" -> index
_registry_cache = Cache(str(_CACHE_DIR / "registry"))

# Message cache: "{session}:{content_hash}" -> {"masked": ..., "mapping": ...}
_message_cache = Cache(str(_CACHE_DIR / "messages"))

# TTL for all cache entries (1 hour)
_TTL = 3600


def cache_response(
    session_id: str,
    deanonymized_text: str,
    masked_text: str,
    entity_mapping: dict,
) -> None:
    """Cache a masked LLM response keyed by the deanonymized content hash.

    Called by the LiteLLM post-call hook so that on the next turn,
    anonymize_conversation() finds a cache hit and skips NER.
    """
    cache_key = f"{session_id}:{_content_hash(deanonymized_text)}"
    _message_cache.set(
        cache_key,
        {"masked": masked_text, "mapping": entity_mapping},
        expire=_TTL,
    )

    # Rebuild registry entries so indices stay stable across turns
    for placeholder, canonical in entity_mapping.items():
        inner = placeholder.strip("<>")
        parts = inner.rsplit("_", 1)
        if len(parts) == 2:
            etype, idx_str = parts
            try:
                idx = int(idx_str)
                normalized = strip_title(canonical)
                _registry_cache.set(
                    f"{session_id}:{etype}:{normalized.lower()}",
                    (idx, canonical),
                    expire=_TTL,
                )
                # Update counter if needed
                counter_key = f"{session_id}:{etype}:__counter__"
                current = _registry_cache.get(counter_key, 0)
                if idx > current:
                    _registry_cache.set(counter_key, idx, expire=_TTL)
            except ValueError:
                pass


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _get_or_assign_index(
    session_id: str | None,
    entity_type: str,
    original_text: str,
    registry: dict,
    counters: dict,
) -> tuple[int, str]:
    """Get existing index or assign next one. Returns (index, canonical_text).

    Uses strip_title() to normalize the registry key so that
    'Dr. Max Mustermann' and 'Max Mustermann' resolve to the same entry.
    The canonical text is the first-seen original form.
    """
    normalized = strip_title(original_text)
    key = (entity_type, normalized.lower())

    # Check in-memory registry first (always used)
    if key in registry:
        return registry[key]

    # Check DiskCache registry (if session)
    if session_id:
        cache_key = f"{session_id}:{entity_type}:{normalized.lower()}"
        cached = _registry_cache.get(cache_key)
        if cached is not None:
            registry[key] = cached
            return cached

    # Assign new index
    counter_key = entity_type
    count = counters.get(counter_key, 0) + 1
    counters[counter_key] = count

    # Also check DiskCache counter (if session, another turn may have incremented it)
    if session_id:
        dc_counter_key = f"{session_id}:{entity_type}:__counter__"
        dc_count = _registry_cache.get(dc_counter_key, 0)
        if dc_count >= count:
            count = dc_count + 1
            counters[counter_key] = count
        _registry_cache.set(dc_counter_key, count, expire=_TTL)
        _registry_cache.set(
            f"{session_id}:{entity_type}:{normalized.lower()}",
            (count, original_text),
            expire=_TTL,
        )

    entry = (count, original_text)
    registry[key] = entry
    return entry


def _anonymize_single(
    text: str,
    analyzer_results: list,
    registry: dict,
    counters: dict,
    session_id: str | None,
) -> tuple[str, dict]:
    """Anonymize one message using the shared registry. Returns (masked_text, mapping)."""
    if not analyzer_results:
        return text, {}

    analyzer_results = remove_overlapping(analyzer_results)

    entity_mapping = {}
    assignments = []
    sorted_results = sorted(analyzer_results, key=lambda r: r["start"])

    for result in sorted_results:
        entity_type = result["entity_type"]
        original = text[result["start"]:result["end"]]
        idx, canonical = _get_or_assign_index(session_id, entity_type, original, registry, counters)
        placeholder = f"<{entity_type}_{idx}>"
        entity_mapping[placeholder] = canonical
        assignments.append((result, placeholder))

    # Right-to-left replacement
    result_text = text
    for result, placeholder in sorted(assignments, key=lambda a: a[0]["start"], reverse=True):
        result_text = result_text[:result["start"]] + placeholder + result_text[result["end"]:]

    return result_text, entity_mapping


def anonymize_conversation(
    messages: list[dict],
    session_id: str | None = None,
    analyze_fn=None,
) -> dict:
    """Anonymize a list of chat messages with cumulative entity mapping.

    Args:
        messages: List of {"role": str, "content": str} dicts.
        session_id: Optional session ID for caching and stable indices.
        analyze_fn: Callable(text) -> list of analyzer results. Injected by startup.py.
                    If None, returns messages unchanged (for unit testing, use conftest fixture).

    Returns:
        {"messages": [...], "entity_mapping": {...}}
    """
    if not messages:
        return {"messages": [], "entity_mapping": {}}

    # In-memory registry and counters for this request
    # Pre-populated from DiskCache if session exists
    registry = {}   # (entity_type, normalized_lower) -> (index, canonical_text)
    counters = {}   # entity_type -> last assigned index

    # If session, load counters from DiskCache
    if session_id:
        # Scan registry cache for this session's counters
        for key in _registry_cache:
            if isinstance(key, str) and key.startswith(f"{session_id}:") and key.endswith(":__counter__"):
                entity_type = key.split(":")[1]
                counters[entity_type] = _registry_cache[key]

    cumulative_mapping = {}
    masked_messages = []

    for message in messages:
        content = message.get("content")
        if content is None or not isinstance(content, str) or not content.strip():
            masked_messages.append(dict(message))
            continue

        # Check message cache (if session)
        if session_id:
            cache_key = f"{session_id}:{_content_hash(content)}"
            cached = _message_cache.get(cache_key)
            if cached is not None:
                masked_messages.append({**message, "content": cached["masked"]})
                cumulative_mapping.update(cached["mapping"])
                # Rebuild registry from cached mapping
                for placeholder, canonical in cached["mapping"].items():
                    # Parse "<TYPE_N>" to extract type and index
                    inner = placeholder.strip("<>")
                    parts = inner.rsplit("_", 1)
                    if len(parts) == 2:
                        etype, idx_str = parts[0], parts[1]
                        try:
                            normalized = strip_title(canonical)
                            registry[(etype, normalized.lower())] = (int(idx_str), canonical)
                        except ValueError:
                            pass
                continue

        # Analyze (NER)
        if analyze_fn is None:
            masked_messages.append(dict(message))
            continue

        analyzer_results = analyze_fn(content)

        # Anonymize with shared registry
        masked_text, mapping = _anonymize_single(
            content, analyzer_results, registry, counters, session_id
        )

        # Cache result (if session)
        if session_id and mapping:
            cache_key = f"{session_id}:{_content_hash(content)}"
            _message_cache.set(cache_key, {"masked": masked_text, "mapping": mapping}, expire=_TTL)

        masked_messages.append({**message, "content": masked_text})
        cumulative_mapping.update(mapping)

    return {"messages": masked_messages, "entity_mapping": cumulative_mapping}
