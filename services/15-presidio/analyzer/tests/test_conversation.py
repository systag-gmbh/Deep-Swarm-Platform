"""Tests for conversation-level anonymization."""
import hashlib
import pytest
import conversation


class TestAnonymizeConversation:
    """Tests without session_id — stateless but cumulative within request."""

    def test_single_message(self):
        messages = [{"role": "user", "content": "Hi, I'm Robin Smith"}]
        result = conversation.anonymize_conversation(messages)
        assert "<PERSON_1>" in result["messages"][0]["content"]
        assert result["entity_mapping"]["<PERSON_1>"] == "Robin Smith"

    def test_cumulative_mapping_across_messages(self):
        """Same entity in different messages gets the same index."""
        messages = [
            {"role": "user", "content": "Hi, I'm Robin Smith"},
            {"role": "assistant", "content": "Hello Robin Smith!"},
        ]
        result = conversation.anonymize_conversation(messages)
        assert result["messages"][0]["content"] == "Hi, I'm <PERSON_1>"
        assert result["messages"][1]["content"] == "Hello <PERSON_1>!"
        assert len(result["entity_mapping"]) == 1

    def test_different_entities_get_different_indices(self):
        messages = [
            {"role": "user", "content": "Robin told Alice to go"},
        ]
        result = conversation.anonymize_conversation(messages)
        mapping = result["entity_mapping"]
        # Two different persons detected
        assert len([k for k in mapping if "PERSON" in k]) == 2

    def test_no_pii_passthrough(self):
        messages = [{"role": "user", "content": "What is the weather today?"}]
        result = conversation.anonymize_conversation(messages)
        assert result["messages"][0]["content"] == "What is the weather today?"
        assert result["entity_mapping"] == {}

    def test_empty_messages(self):
        result = conversation.anonymize_conversation([])
        assert result["messages"] == []
        assert result["entity_mapping"] == {}

    def test_none_content_skipped(self):
        messages = [{"role": "assistant", "content": None}]
        result = conversation.anonymize_conversation(messages)
        assert result["messages"][0]["content"] is None
        assert result["entity_mapping"] == {}


class TestAnonymizeConversationWithSession:
    """Tests with session_id — cached, stable indices across calls."""

    def test_second_call_skips_cached_messages(self):
        """Second call with same session returns same results without re-analyzing."""
        messages = [{"role": "user", "content": "Hi, I'm Robin Smith"}]

        r1 = conversation.anonymize_conversation(messages, session_id="test-session-1")
        # Add a new message
        messages.append({"role": "user", "content": "My email is robin@example.com"})
        r2 = conversation.anonymize_conversation(messages, session_id="test-session-1")

        # First message should be identical (cached)
        assert r1["messages"][0]["content"] == r2["messages"][0]["content"]
        # Robin Smith still PERSON_1 in both calls
        assert r2["entity_mapping"]["<PERSON_1>"] == "Robin Smith"
        # New entity added
        assert "<EMAIL_ADDRESS_1>" in r2["entity_mapping"]

    def test_different_sessions_isolated(self):
        """Different session_ids must not share state."""
        msg = [{"role": "user", "content": "Hi, I'm Robin"}]

        r1 = conversation.anonymize_conversation(msg, session_id="session-a")
        r2 = conversation.anonymize_conversation(msg, session_id="session-b")

        # Both should work independently
        assert "<PERSON_1>" in r1["messages"][0]["content"]
        assert "<PERSON_1>" in r2["messages"][0]["content"]

    def test_stable_indices_across_turns(self):
        """Entity indices must not shift between turns."""
        turn1 = [{"role": "user", "content": "Robin and Alice met"}]
        r1 = conversation.anonymize_conversation(turn1, session_id="test-stable-idx")

        turn2 = turn1 + [
            {"role": "assistant", "content": "Tell me more about Robin"},
            {"role": "user", "content": "Robin works with Bob"},
        ]
        r2 = conversation.anonymize_conversation(turn2, session_id="test-stable-idx")

        # Robin and Alice keep their original indices
        assert r2["entity_mapping"]["<PERSON_1>"] == r1["entity_mapping"]["<PERSON_1>"]
        assert r2["entity_mapping"]["<PERSON_2>"] == r1["entity_mapping"]["<PERSON_2>"]
        # Bob gets the next index
        assert "<PERSON_3>" in r2["entity_mapping"]


class TestTitleStrippingEntityMerge:
    """Tests that entities with/without titles resolve to the same index."""

    @staticmethod
    def _make_analyzer(detections: dict):
        """Create a mock analyze_fn returning specific detections per text."""
        def analyze(text):
            return detections.get(text, [])
        return analyze

    def test_dr_title_merged(self):
        """'Dr. Max Mustermann' and 'Max Mustermann' get the same index."""
        t1 = "Dr. Max Mustermann called yesterday"
        t2 = "Please forward this to Max Mustermann"
        analyze_fn = self._make_analyzer({
            t1: [{"entity_type": "PERSON", "start": 0, "end": 18, "score": 0.95}],
            t2: [{"entity_type": "PERSON", "start": 23, "end": 37, "score": 0.95}],
        })
        messages = [
            {"role": "user", "content": t1},
            {"role": "user", "content": t2},
        ]
        result = conversation.anonymize_conversation(messages, analyze_fn=analyze_fn)

        assert "<PERSON_1>" in result["messages"][0]["content"]
        assert "<PERSON_1>" in result["messages"][1]["content"]
        assert len([k for k in result["entity_mapping"] if "PERSON" in k]) == 1

    def test_canonical_is_first_seen(self):
        """The entity_mapping stores the first-seen original form."""
        t1 = "Dr. Max Mustermann called"
        t2 = "Forward to Max Mustermann"
        analyze_fn = self._make_analyzer({
            t1: [{"entity_type": "PERSON", "start": 0, "end": 18, "score": 0.95}],
            t2: [{"entity_type": "PERSON", "start": 11, "end": 25, "score": 0.95}],
        })
        messages = [
            {"role": "user", "content": t1},
            {"role": "user", "content": t2},
        ]
        result = conversation.anonymize_conversation(messages, analyze_fn=analyze_fn)

        assert result["entity_mapping"]["<PERSON_1>"] == "Dr. Max Mustermann"

    def test_prof_dr_title_merged(self):
        """'Prof. Dr. Max Mustermann' and 'Max Mustermann' get the same index."""
        t1 = "Prof. Dr. Max Mustermann spoke"
        t2 = "Max Mustermann agreed"
        analyze_fn = self._make_analyzer({
            t1: [{"entity_type": "PERSON", "start": 0, "end": 24, "score": 0.95}],
            t2: [{"entity_type": "PERSON", "start": 0, "end": 14, "score": 0.95}],
        })
        messages = [
            {"role": "user", "content": t1},
            {"role": "user", "content": t2},
        ]
        result = conversation.anonymize_conversation(messages, analyze_fn=analyze_fn)

        assert "<PERSON_1>" in result["messages"][0]["content"]
        assert "<PERSON_1>" in result["messages"][1]["content"]
        assert result["entity_mapping"]["<PERSON_1>"] == "Prof. Dr. Max Mustermann"

    def test_no_title_no_merge(self):
        """Different names without titles stay separate."""
        t1 = "Max Mustermann and Anna Schmidt met"
        analyze_fn = self._make_analyzer({
            t1: [
                {"entity_type": "PERSON", "start": 0, "end": 14, "score": 0.95},
                {"entity_type": "PERSON", "start": 19, "end": 32, "score": 0.95},
            ],
        })
        messages = [{"role": "user", "content": t1}]
        result = conversation.anonymize_conversation(messages, analyze_fn=analyze_fn)

        assert len([k for k in result["entity_mapping"] if "PERSON" in k]) == 2

    def test_reversed_order_title_second(self):
        """Name without title first, then with title — still merges."""
        t1 = "Max Mustermann called"
        t2 = "Dr. Max Mustermann confirmed"
        analyze_fn = self._make_analyzer({
            t1: [{"entity_type": "PERSON", "start": 0, "end": 14, "score": 0.95}],
            t2: [{"entity_type": "PERSON", "start": 0, "end": 18, "score": 0.95}],
        })
        messages = [
            {"role": "user", "content": t1},
            {"role": "user", "content": t2},
        ]
        result = conversation.anonymize_conversation(messages, analyze_fn=analyze_fn)

        assert "<PERSON_1>" in result["messages"][0]["content"]
        assert "<PERSON_1>" in result["messages"][1]["content"]
        # Canonical is first-seen: "Max Mustermann" (no title)
        assert result["entity_mapping"]["<PERSON_1>"] == "Max Mustermann"
