"""Tests for ensemble merge logic."""
import pytest
from ensemble_recognizer import merge_results, merge_address_blocks, suppress_contained_entities, NormalizedResult


# --- Helper to build test results ---

def r(start, end, entity_type, score, source="test"):
    return NormalizedResult(
        entity_type=entity_type,
        start=start,
        end=end,
        score=score,
        source=source,
    )


class TestOverlapDetection:
    """Two detections overlap when intersection/union > 0.7."""

    def test_identical_spans_same_type_boost_score(self):
        """Rule 1: Same span, same type -> boost score."""
        results = merge_results([
            r(0, 5, "PERSON", 0.85, "nerguard"),
            r(0, 5, "PERSON", 0.80, "gliner"),
        ])
        assert len(results) == 1
        assert results[0].entity_type == "PERSON"
        # Boosted: min(max(0.85, 0.80) * 1.2, 1.0) = 1.0 (capped)
        assert results[0].score == pytest.approx(1.0)

    def test_identical_spans_compatible_types_merge(self):
        """Rule 2: Same span, compatible types -> merge into most specific."""
        results = merge_results([
            r(0, 14, "LOCATION", 0.90, "gliner"),
            r(0, 14, "ADDRESS", 0.80, "nerguard"),
        ])
        assert len(results) == 1
        assert results[0].entity_type == "ADDRESS"  # More specific
        assert results[0].score > 0.90  # Boosted

    def test_identical_spans_conflicting_types_keep_both(self):
        """Rule 3: Same span, conflicting types -> keep both."""
        results = merge_results([
            r(0, 5, "PERSON", 0.85, "nerguard"),
            r(0, 5, "LOCATION", 0.80, "gliner"),
        ])
        assert len(results) == 2

    def test_partial_overlap_same_type_keep_longer(self):
        """Rule 4: Partial overlap, same type -> keep longer span, boost."""
        results = merge_results([
            r(0, 11, "PERSON", 0.90, "gliner"),    # "Robin Smith"
            r(6, 11, "PERSON", 0.85, "nerguard"),  # "Smith"
        ])
        # PERSON and PERSON are compatible -> merge into longer span
        assert len(results) == 1
        assert results[0].start == 0
        assert results[0].end == 11
        assert results[0].score > 0.90

    def test_no_overlap_keep_both(self):
        """Rule 5: No overlap -> keep both at original scores."""
        results = merge_results([
            r(0, 5, "PERSON", 0.85, "nerguard"),
            r(20, 30, "EMAIL_ADDRESS", 0.95, "gliner"),
        ])
        assert len(results) == 2
        assert results[0].score == pytest.approx(0.85)
        assert results[1].score == pytest.approx(0.95)

    def test_both_models_agree_boost(self):
        """Both models find the same entity -> boost score."""
        results = merge_results([
            r(0, 5, "PERSON", 0.80, "nerguard"),
            r(0, 5, "PERSON", 0.85, "gliner"),
        ])
        assert len(results) == 1
        assert results[0].entity_type == "PERSON"
        assert results[0].score == pytest.approx(1.0)  # Capped

    def test_compatible_address_types_pick_most_specific(self):
        """ADDRESS vs LOCATION -> pick more specific (ADDRESS)."""
        results = merge_results([
            r(0, 14, "LOCATION", 0.90, "nerguard"),
            r(0, 14, "ZIP_CODE", 0.70, "gliner"),
        ])
        assert len(results) == 1
        # Both are in ADDRESS group, ZIP_CODE is more specific
        assert results[0].entity_type == "ZIP_CODE"


class TestEdgeCases:

    def test_empty_input(self):
        assert merge_results([]) == []

    def test_single_result_passes_through(self):
        results = merge_results([r(0, 5, "PERSON", 0.85, "nerguard")])
        assert len(results) == 1
        assert results[0].score == pytest.approx(0.85)

    def test_sorted_by_start_position(self):
        results = merge_results([
            r(20, 30, "EMAIL_ADDRESS", 0.95, "nerguard"),
            r(0, 5, "PERSON", 0.85, "nerguard"),
        ])
        assert results[0].start == 0
        assert results[1].start == 20


class TestMergeAddressBlocks:
    """Adjacent address components separated by whitespace → single ADDRESS."""

    def test_full_address_block(self):
        """ORGANIZATION + ADDRESS + ZIP_CODE + LOCATION → one ADDRESS."""
        text = "SYSTAG GmbH\nGutenbergstrasse 47\nD-72555 Metzingen"
        #       0         11 12                 31 32     39 40      49
        results = merge_address_blocks([
            r(0, 11, "ORGANIZATION", 0.75),    # SYSTAG GmbH
            r(12, 31, "ADDRESS", 0.99),         # Gutenbergstrasse 47
            r(32, 39, "ZIP_CODE", 0.98),        # D-72555
            r(40, 49, "LOCATION", 0.99),        # Metzingen
        ], text)
        assert len(results) == 1
        assert results[0].entity_type == "ADDRESS"
        assert results[0].start == 0
        assert results[0].end == 49
        assert results[0].score == pytest.approx(0.99)

    def test_non_address_entities_pass_through(self):
        text = "Robin at SYSTAG GmbH\nBerlinstr 5"
        results = merge_address_blocks([
            r(0, 5, "PERSON", 0.95),
            r(9, 20, "ORGANIZATION", 0.80),
            r(21, 32, "ADDRESS", 0.90),
        ], text)
        # PERSON stays separate, ORG + ADDRESS merge
        assert len(results) == 2
        assert results[0].entity_type == "PERSON"
        assert results[1].entity_type == "ADDRESS"
        assert results[1].start == 9
        assert results[1].end == 32

    def test_non_whitespace_gap_breaks_block(self):
        """Address entities with text between them stay separate."""
        text = "Berliner Str 5 near D-72555 Metzingen"
        results = merge_address_blocks([
            r(0, 14, "ADDRESS", 0.90),       # Berliner Str 5
            r(20, 27, "ZIP_CODE", 0.85),     # D-72555
            r(28, 37, "LOCATION", 0.88),     # Metzingen
        ], text)
        # "near" between ADDRESS and ZIP_CODE breaks the block
        assert len(results) == 2
        assert results[0].entity_type == "ADDRESS"
        assert results[0].end == 14
        assert results[1].entity_type == "ADDRESS"  # ZIP + LOCATION merged
        assert results[1].start == 20
        assert results[1].end == 37

    def test_single_address_entity_unchanged(self):
        text = "Visit Berlin sometime"
        results = merge_address_blocks([
            r(6, 12, "LOCATION", 0.90),
        ], text)
        assert len(results) == 1
        assert results[0].entity_type == "LOCATION"

    def test_empty_input(self):
        assert merge_address_blocks([], "") == []


class TestSuppressContainedEntities:
    """Cross-type containment: smaller entities inside a larger entity are dropped."""

    def test_iban_contains_passport_taxid_ssn(self):
        """Real-world bug: IBAN fragments misdetected as PASSPORT/TAX_ID/SSN."""
        results = suppress_contained_entities([
            r(29, 56, "IBAN_CODE", 0.906, "gliner"),
            r(29, 33, "PASSPORT", 0.703, "nerguard"),
            r(34, 38, "TAX_ID", 0.573, "nerguard"),
            r(39, 56, "SSN", 0.938, "nerguard"),
            r(61, 79, "PERSON", 1.000, "gliner"),
        ])
        types = {r.entity_type for r in results}
        assert types == {"IBAN_CODE", "PERSON"}
        assert len(results) == 2

    def test_identical_spans_different_types_keep_higher_score(self):
        """Same span, different types -> keep higher-scored entity."""
        results = suppress_contained_entities([
            r(0, 5, "PERSON", 0.85, "nerguard"),
            r(0, 5, "LOCATION", 0.80, "gliner"),
        ])
        assert len(results) == 1
        assert results[0].entity_type == "PERSON"

    def test_identical_spans_equal_scores_keep_both(self):
        """Same span, different types, equal scores -> keep both (truly ambiguous)."""
        results = suppress_contained_entities([
            r(0, 5, "PERSON", 0.85, "nerguard"),
            r(0, 5, "LOCATION", 0.85, "gliner"),
        ])
        assert len(results) == 2

    def test_credit_card_also_detected_as_ssn(self):
        """Real-world bug: credit card at same span as SSN -> keep CREDIT_CARD (higher score)."""
        results = suppress_contained_entities([
            r(14, 25, "SSN", 0.998, "nerguard"),
            r(33, 52, "SSN", 0.900, "nerguard"),
            r(33, 52, "CREDIT_CARD", 0.949, "gliner"),
            r(75, 87, "IP_ADDRESS", 0.986, "gliner"),
        ])
        types = [(r.entity_type, r.start) for r in results]
        assert ("SSN", 14) in types
        assert ("CREDIT_CARD", 33) in types
        assert ("IP_ADDRESS", 75) in types
        assert ("SSN", 33) not in types
        assert len(results) == 3

    def test_no_overlap_kept(self):
        """Non-overlapping entities are never suppressed."""
        results = suppress_contained_entities([
            r(0, 10, "PERSON", 0.85),
            r(20, 30, "SSN", 0.90),
        ])
        assert len(results) == 2

    def test_partial_overlap_significant_suppresses_shorter(self):
        """Significant partial overlap (>=0.7) of different types drops shorter."""
        # entity B: 5 of 7 chars inside entity A → overlap_ratio = 5/7 ≈ 0.71
        results = suppress_contained_entities([
            r(0, 20, "IBAN_CODE", 0.85),
            r(15, 22, "PASSPORT", 0.70),
        ])
        assert len(results) == 1
        assert results[0].entity_type == "IBAN_CODE"

    def test_partial_overlap_minor_keeps_both(self):
        """Minor partial overlap (<0.7) of different types keeps both."""
        results = suppress_contained_entities([
            r(0, 20, "PERSON", 0.85),
            r(18, 35, "ORGANIZATION", 0.90),  # only 2 of 17 chars overlap
        ])
        assert len(results) == 2

    def test_same_type_not_suppressed(self):
        """Same-type overlap is handled by merge_results, not suppression."""
        results = suppress_contained_entities([
            r(0, 20, "PERSON", 0.85),
            r(5, 15, "PERSON", 0.90),
        ])
        assert len(results) == 2

    def test_compatible_types_not_suppressed(self):
        """Compatible types are handled by merge_results, not suppression."""
        results = suppress_contained_entities([
            r(0, 20, "ADDRESS", 0.85),
            r(5, 15, "LOCATION", 0.90),
        ])
        assert len(results) == 2

    def test_empty_input(self):
        assert suppress_contained_entities([]) == []

    def test_single_input(self):
        results = suppress_contained_entities([r(0, 5, "PERSON", 0.85)])
        assert len(results) == 1
