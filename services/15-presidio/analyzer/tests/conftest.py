"""Shared fixtures for analyzer tests."""
import pytest


def _mock_analyze(text):
    """Simple mock that detects names and emails via basic heuristics.

    For unit tests only — real tests use the actual Presidio engine.
    """
    import re
    results = []

    # Detect emails
    for m in re.finditer(r'\b[\w.+-]+@[\w-]+\.[\w.]+\b', text):
        results.append({
            "entity_type": "EMAIL_ADDRESS",
            "start": m.start(), "end": m.end(), "score": 0.99,
        })

    # Detect capitalized words as PERSON (very naive, but sufficient for unit tests)
    # Find individual words first, filter skip words, then merge consecutive ones
    email_ranges = [(m.start(), m.end()) for m in re.finditer(r'\b[\w.+-]+@[\w-]+\.[\w.]+\b', text)]
    skip_words = {"Hi", "I'm", "My", "What", "Tell", "Hello", "The", "I", "A",
                  "And", "Or", "But", "Is", "It", "To", "In", "On", "At", "Of",
                  "For", "With", "About", "Dear", "Best", "Regards"}

    name_words = []
    for m in re.finditer(r'\b([A-Z][a-z]+)\b', text):
        if any(m.start() < ee and m.end() > es for es, ee in email_ranges):
            continue
        if m.group() in skip_words:
            continue
        name_words.append((m.start(), m.end()))

    # Merge consecutive words separated by exactly one space
    i = 0
    while i < len(name_words):
        start = name_words[i][0]
        end = name_words[i][1]
        while i + 1 < len(name_words) and name_words[i + 1][0] == end + 1:
            i += 1
            end = name_words[i][1]
        results.append({
            "entity_type": "PERSON",
            "start": start, "end": end, "score": 0.95,
        })
        i += 1

    return results


@pytest.fixture(autouse=True)
def patch_analyze_fn(monkeypatch):
    """Inject mock analyze_fn into conversation module."""
    import conversation
    original = conversation.anonymize_conversation

    def patched(messages, session_id=None, analyze_fn=None):
        if analyze_fn is None:
            analyze_fn = _mock_analyze
        return original(messages, session_id=session_id, analyze_fn=analyze_fn)

    monkeypatch.setattr(conversation, "anonymize_conversation", patched)
