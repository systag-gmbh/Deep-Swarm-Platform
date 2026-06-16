"""Tests for cache_response and its integration with anonymize_conversation."""
import conversation


class TestCacheResponse:
    """Tests for the cache_response function."""

    def test_cached_response_found_on_next_turn(self):
        """A cached assistant response should be a cache hit in anonymize_conversation."""
        session = "test-cache-resp-1"

        # Simulate: LLM responded with "<PERSON_1>" which was deanonymized to "Robin Smith"
        conversation.cache_response(
            session_id=session,
            deanonymized_text="Hello Robin Smith, nice to meet you!",
            masked_text="Hello <PERSON_1>, nice to meet you!",
            entity_mapping={"<PERSON_1>": "Robin Smith"},
        )

        # Next turn: client sends the deanonymized assistant message back
        messages = [
            {"role": "user", "content": "Hi, I'm Robin Smith"},
            {"role": "assistant", "content": "Hello Robin Smith, nice to meet you!"},
            {"role": "user", "content": "What's the weather?"},
        ]
        result = conversation.anonymize_conversation(messages, session_id=session)

        # Assistant message should use cached masked version
        assert result["messages"][1]["content"] == "Hello <PERSON_1>, nice to meet you!"
        assert result["entity_mapping"]["<PERSON_1>"] == "Robin Smith"

    def test_registry_rebuilt_from_cached_response(self):
        """Indices from cached response must be stable for new messages."""
        session = "test-cache-resp-2"

        conversation.cache_response(
            session_id=session,
            deanonymized_text="Hello Robin Smith!",
            masked_text="Hello <PERSON_1>!",
            entity_mapping={"<PERSON_1>": "Robin Smith"},
        )

        # New message mentions Robin — should get same index
        messages = [
            {"role": "assistant", "content": "Hello Robin Smith!"},
            {"role": "user", "content": "Robin Smith is here"},
        ]
        result = conversation.anonymize_conversation(messages, session_id=session)

        assert "<PERSON_1>" in result["messages"][1]["content"]
        # Only one PERSON entity in the mapping
        person_keys = [k for k in result["entity_mapping"] if "PERSON" in k]
        assert len(person_keys) == 1

    def test_cache_response_without_mapping(self):
        """Caching a response with empty mapping should still cache the text."""
        session = "test-cache-resp-3"

        conversation.cache_response(
            session_id=session,
            deanonymized_text="Sure, I can help with that.",
            masked_text="Sure, I can help with that.",
            entity_mapping={},
        )

        messages = [
            {"role": "assistant", "content": "Sure, I can help with that."},
        ]
        result = conversation.anonymize_conversation(messages, session_id=session)

        assert result["messages"][0]["content"] == "Sure, I can help with that."
