"""Tests for title detection, absorption, and stripping."""
import pytest
from titles import find_titles, strip_title
from ensemble_recognizer import absorb_titles, NormalizedResult


def r(start, end, entity_type, score, source="test"):
    return NormalizedResult(
        entity_type=entity_type,
        start=start,
        end=end,
        score=score,
        source=source,
    )


class TestFindTitles:

    def test_finds_dr(self):
        positions = find_titles("Dr. Hans Müller")
        assert (0, 3) in positions

    def test_finds_ppa(self):
        positions = find_titles("Ppa. Niels Wiederanders")
        assert (0, 4) in positions

    def test_finds_prof_dr_compound(self):
        """Longer compound title matches over shorter."""
        positions = find_titles("Prof. Dr. Hans Müller")
        starts = {s for s, e in positions}
        assert 0 in starts  # "Prof. Dr." at 0

    def test_finds_mr(self):
        positions = find_titles("Mr. Smith called Mrs. Jones")
        starts = {s for s, e in positions}
        assert 0 in starts     # Mr.
        assert 17 in starts    # Mrs.

    def test_no_match_mid_word(self):
        """Titles must be preceded by whitespace or start of text."""
        positions = find_titles("aMr. Smith")
        assert len(positions) == 0

    def test_finds_herr_frau(self):
        positions = find_titles("Herr Müller und Frau Schmidt")
        starts = {s for s, e in positions}
        assert 0 in starts    # Herr
        assert 16 in starts   # Frau

    def test_finds_title_at_line_start(self):
        positions = find_titles("Grüße\nDr. Hans Müller")
        assert any(s == 6 for s, _ in positions)

    def test_no_match_without_space_after(self):
        """Title must be followed by whitespace."""
        # "Dr.Hans" without space — should not match
        positions = find_titles("Dr.Hans Müller")
        assert len(positions) == 0


class TestStripTitle:

    def test_strip_dr(self):
        assert strip_title("Dr. Max Mustermann") == "Max Mustermann"

    def test_strip_prof_dr(self):
        assert strip_title("Prof. Dr. Max Mustermann") == "Max Mustermann"

    def test_strip_herr(self):
        assert strip_title("Herr Müller") == "Müller"

    def test_strip_mrs(self):
        assert strip_title("Mrs. Jones") == "Jones"

    def test_no_title(self):
        assert strip_title("Max Mustermann") == "Max Mustermann"

    def test_title_only_kept(self):
        """If stripping would leave nothing, keep the original."""
        assert strip_title("Dr.") == "Dr."

    def test_title_with_only_whitespace_after(self):
        assert strip_title("Prof.  ") == "Prof.  "

    def test_ceo_stripped(self):
        assert strip_title("CEO John Smith") == "John Smith"

    def test_dipl_ing_stripped(self):
        assert strip_title("Dipl.-Ing. Werner") == "Werner"


class TestAbsorbTitles:

    def test_title_absorbed_into_person(self):
        """'Dr. Hans' with PERSON at 'Hans' -> span expands to include 'Dr.'"""
        text = "Dr. Hans Müller"
        results = [r(4, 15, "PERSON", 0.90)]
        absorb_titles(results, text)
        assert results[0].start == 0
        assert results[0].end == 15

    def test_ppa_with_undetected_first_name(self):
        """'Ppa. Niels Wiederanders' with PERSON only at 'Wiederanders'."""
        text = "Ppa. Niels Wiederanders"
        results = [r(11, 23, "PERSON", 0.95)]
        absorb_titles(results, text)
        # Should absorb "Ppa. Niels " into the entity
        assert results[0].start == 0
        assert results[0].end == 23

    def test_title_not_absorbed_without_person(self):
        """'B.Sc. Wirtschaftsinformatik' — no PERSON entity, title stays."""
        text = "B.Sc. Wirtschaftsinformatik"
        results = []  # No entities
        absorb_titles(results, text)
        assert results == []

    def test_title_not_absorbed_into_non_person(self):
        """Title before a LOCATION entity should not absorb."""
        text = "Hr. Berlin ist schön"
        results = [r(4, 10, "LOCATION", 0.90)]
        absorb_titles(results, text)
        assert results[0].start == 4  # Unchanged

    def test_multiple_titles_same_name(self):
        """'Prof. Dr. Hans Müller' — Prof. and Dr. both absorbed."""
        text = "Prof. Dr. Hans Müller"
        results = [r(10, 21, "PERSON", 0.90)]
        absorb_titles(results, text)
        # "Prof. Dr." should be absorbed (longest match at pos 0)
        assert results[0].start == 0

    def test_title_already_inside_entity(self):
        """Title already within entity span — no change."""
        text = "Dr. Hans Müller"
        # Entity already spans from 0 (includes Dr.)
        results = [r(0, 15, "PERSON", 0.90)]
        absorb_titles(results, text)
        assert results[0].start == 0
        assert results[0].end == 15

    def test_non_capitalized_gap_blocks_absorption(self):
        """Title with lowercase words between it and name — no absorption."""
        text = "Dr. und dann Hans Müller"
        results = [r(14, 24, "PERSON", 0.90)]
        absorb_titles(results, text)
        # "und" and "dann" are lowercase — gap check fails
        assert results[0].start == 14  # Unchanged

    def test_herr_absorbed(self):
        text = "Herr Müller ist hier"
        results = [r(5, 11, "PERSON", 0.90)]
        absorb_titles(results, text)
        assert results[0].start == 0

    def test_mrs_absorbed(self):
        text = "Mrs. Jones called"
        results = [r(5, 10, "PERSON", 0.90)]
        absorb_titles(results, text)
        assert results[0].start == 0

    def test_ceo_absorbed(self):
        text = "CEO John Smith announced"
        results = [r(4, 14, "PERSON", 0.90)]
        absorb_titles(results, text)
        assert results[0].start == 0

    def test_no_entities_no_crash(self):
        text = "Dr. somebody"
        results = []
        absorb_titles(results, text)
        assert results == []

    def test_title_too_far_from_entity(self):
        """Title more than 50 chars from entity — no absorption."""
        text = "Dr. " + "x" * 60 + " Hans Müller"
        results = [r(65, 76, "PERSON", 0.90)]
        absorb_titles(results, text)
        assert results[0].start == 65  # Unchanged
