"""Pure anonymization logic — no heavy dependencies."""


def remove_overlapping(analyzer_results):
    """Remove overlapping entities, keeping the highest-scoring one per span."""
    by_score = sorted(analyzer_results, key=lambda r: r["score"], reverse=True)
    accepted = []
    for r in by_score:
        if not any(r["start"] < a["end"] and r["end"] > a["start"] for a in accepted):
            accepted.append(r)
    return accepted


def anonymize_text(text, analyzer_results):
    """Anonymize text with indexed placeholders.

    Returns (result_text, items, entity_mapping).
    """
    if not analyzer_results:
        return text, [], {}

    # Pass 0: remove overlapping entities (keep highest score)
    analyzer_results = remove_overlapping(analyzer_results)

    # Pass 1: left-to-right — assign indexed placeholders in reading order
    counters = {}       # {"FIRST_NAME": 2, "EMAIL_ADDRESS": 1}
    seen = {}           # {("FIRST_NAME", "robin"): "<FIRST_NAME_1>"}
    entity_mapping = {} # {"<FIRST_NAME_1>": "Robin"}
    assignments = []    # [(result, placeholder), ...]

    sorted_by_start = sorted(analyzer_results, key=lambda r: r["start"])

    for result in sorted_by_start:
        entity_type = result["entity_type"]
        original = text[result["start"]:result["end"]]
        key = (entity_type, original.lower())

        if key not in seen:
            counter = counters.get(entity_type, 0) + 1
            counters[entity_type] = counter
            placeholder = f"<{entity_type}_{counter}>"
            seen[key] = placeholder
            entity_mapping[placeholder] = original

        assignments.append((result, seen[key]))

    # Pass 2: right-to-left — perform string replacements
    sorted_by_start_desc = sorted(assignments, key=lambda a: a[0]["start"], reverse=True)

    result_text = text
    for result, placeholder in sorted_by_start_desc:
        result_text = result_text[:result["start"]] + placeholder + result_text[result["end"]:]

    # Build items with positions in the ORIGINAL text.
    # LiteLLM uses these positions to extract original PII values from the
    # input text for its in-memory deanonymization mapping.
    items = []
    for result, placeholder in sorted(assignments, key=lambda a: a[0]["start"]):
        items.append({
            "start": result["start"],
            "end": result["end"],
            "entity_type": result["entity_type"],
            "operator": "replace",
            "text": placeholder,
        })

    return result_text, items, entity_mapping
