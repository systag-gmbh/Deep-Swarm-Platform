"""Tests for anonymize overlap handling."""
import pytest
from anonymize import remove_overlapping, anonymize_text


class TestRemoveOverlapping:

    def test_identical_spans_keep_highest(self):
        results = remove_overlapping([
            {"start": 6, "end": 11, "entity_type": "PERSON", "score": 0.95},
            {"start": 6, "end": 11, "entity_type": "PERSON", "score": 0.85},
        ])
        assert len(results) == 1
        assert results[0]["entity_type"] == "PERSON"

    def test_partial_overlap_keep_highest(self):
        results = remove_overlapping([
            {"start": 5, "end": 23, "entity_type": "PERSON", "score": 0.92},
            {"start": 11, "end": 24, "entity_type": "PERSON", "score": 0.91},
        ])
        assert len(results) == 1
        assert results[0]["entity_type"] == "PERSON"

    def test_non_overlapping_both_kept(self):
        results = remove_overlapping([
            {"start": 0, "end": 5, "entity_type": "PERSON", "score": 0.95},
            {"start": 15, "end": 19, "entity_type": "PERSON", "score": 0.90},
        ])
        assert len(results) == 2

    def test_triple_overlap_one_survives(self):
        results = remove_overlapping([
            {"start": 6, "end": 27, "entity_type": "PHONE_NUMBER", "score": 0.99},
            {"start": 6, "end": 20, "entity_type": "PHONE_NUMBER", "score": 0.92},
            {"start": 12, "end": 27, "entity_type": "PHONE_NUMBER", "score": 0.98},
        ])
        assert len(results) == 1
        assert results[0]["score"] == 0.99

    def test_adjacent_not_overlapping(self):
        """Entities touching at a boundary (end == start) are NOT overlapping."""
        results = remove_overlapping([
            {"start": 0, "end": 5, "entity_type": "PERSON", "score": 0.90},
            {"start": 5, "end": 10, "entity_type": "PERSON", "score": 0.85},
        ])
        assert len(results) == 2

    def test_empty_input(self):
        assert remove_overlapping([]) == []


class TestAnonymizeText:

    def test_basic_replacement(self):
        text = "Hello Robin, how are you?"
        results = [
            {"start": 6, "end": 11, "entity_type": "PERSON", "score": 0.95},
        ]
        result_text, items, mapping = anonymize_text(text, results)
        assert result_text == "Hello <PERSON_1>, how are you?"
        assert mapping["<PERSON_1>"] == "Robin"

    def test_overlapping_entities_no_corruption(self):
        text = "Hello Robin, how are you?"
        results = [
            {"start": 6, "end": 11, "entity_type": "PERSON", "score": 0.95},
            {"start": 6, "end": 11, "entity_type": "PERSON", "score": 0.85},
        ]
        result_text, items, mapping = anonymize_text(text, results)
        assert result_text == "Hello <PERSON_1>, how are you?"
        # No garbled angle brackets
        clean = result_text.replace("<PERSON_1>", "X")
        assert ">" not in clean
        assert "<" not in clean

    def test_signature_block_no_corruption(self):
        """Regression: overlapping name spans must not garble text."""
        text = "Ppa. Niels Wiederanders\nB.Sc. Wirtschaftsinformatik"
        results = [
            {"start": 5, "end": 23, "entity_type": "PERSON", "score": 0.92},
            {"start": 11, "end": 24, "entity_type": "PERSON", "score": 0.91},
        ]
        result_text, items, mapping = anonymize_text(text, results)
        # Only one placeholder, no garbled overlap
        assert result_text == "Ppa. <PERSON_1>\nB.Sc. Wirtschaftsinformatik"
        assert result_text.count("PERSON") == 1

    def test_phone_number_triple_overlap_clean(self):
        """Regression: Tel.: <PHONE_NUMBER_1>_NUMBER_2>BER_3>"""
        text = "Tel.: +49 7123 / 92 02"
        results = [
            {"start": 6, "end": 22, "entity_type": "PHONE_NUMBER", "score": 0.99},
            {"start": 6, "end": 16, "entity_type": "PHONE_NUMBER", "score": 0.92},
            {"start": 10, "end": 22, "entity_type": "PHONE_NUMBER", "score": 0.98},
        ]
        result_text, items, mapping = anonymize_text(text, results)
        assert result_text == "Tel.: <PHONE_NUMBER_1>"
        assert result_text.count("PHONE_NUMBER") == 1

    def test_empty_results(self):
        text, items, mapping = anonymize_text("Hello world", [])
        assert text == "Hello world"
        assert items == []
        assert mapping == {}

    def test_same_entity_repeated_gets_same_index(self):
        text = "Robin told Robin to go"
        results = [
            {"start": 0, "end": 5, "entity_type": "PERSON", "score": 0.95},
            {"start": 11, "end": 16, "entity_type": "PERSON", "score": 0.95},
        ]
        result_text, items, mapping = anonymize_text(text, results)
        assert result_text == "<PERSON_1> told <PERSON_1> to go"
