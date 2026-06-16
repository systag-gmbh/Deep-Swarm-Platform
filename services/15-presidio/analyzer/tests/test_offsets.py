"""Tests for byte-to-char offset conversion and span trimming."""
import pytest
from ensemble_recognizer import _byte_to_char, _byte_to_char_offsets, _trim_entity_span


class TestByteToChar:

    def test_ascii_only(self):
        assert _byte_to_char("hello", 0) == 0
        assert _byte_to_char("hello", 3) == 3
        assert _byte_to_char("hello", 5) == 5

    def test_german_umlaut(self):
        # "müsst" — ü is 2 bytes in UTF-8
        text = "müsst"
        # byte 0 = 'm', bytes 1-2 = 'ü', byte 3 = 's', byte 4 = 's', byte 5 = 't'
        assert _byte_to_char(text, 0) == 0  # 'm'
        assert _byte_to_char(text, 1) == 1  # 'ü' start
        assert _byte_to_char(text, 3) == 2  # 's' after ü (byte 3 = char 2)
        assert _byte_to_char(text, 6) == 5  # end

    def test_multiple_multibyte(self):
        # "Grüße" — ü (2 bytes) + ß (2 bytes)
        text = "Grüße"
        # bytes: G(1) r(1) ü(2) ß(2) e(1) = 7 bytes, 5 chars
        assert _byte_to_char(text, 0) == 0  # 'G'
        assert _byte_to_char(text, 2) == 2  # 'ü' start
        assert _byte_to_char(text, 4) == 3  # 'ß' start
        assert _byte_to_char(text, 6) == 4  # 'e'
        assert _byte_to_char(text, 7) == 5  # end

    def test_offset_beyond_text_clamped(self):
        assert _byte_to_char("hi", 99) == 2


class TestByteToCharOffsets:

    def test_ascii_text_noop(self):
        """Pure ASCII text: byte == char, no conversion needed."""
        assert _byte_to_char_offsets("hello world", 6, 11) == (6, 11)

    def test_umlaut_before_entity(self):
        """Byte offset shifted by 1 extra byte from ü before 'Robin'."""
        text = "Hallo müsst Robin"
        # In bytes: H(1)a(1)l(1)l(1)o(1) (1)m(1)ü(2)s(1)s(1)t(1) (1)R(1)o(1)b(1)i(1)n(1)
        # "Robin" byte offset: 13-18 (char offset: 12-17)
        assert _byte_to_char_offsets(text, 13, 18) == (12, 17)

    def test_growing_drift(self):
        """More multi-byte chars = larger offset drift."""
        text = "ä ö ü Robin"
        # bytes: ä(2) (1) ö(2) (1) ü(2) (1) R(1)o(1)b(1)i(1)n(1) = 14 bytes
        # "Robin" byte offset: 9-14, char offset: 6-11
        assert _byte_to_char_offsets(text, 9, 14) == (6, 11)

    def test_entity_at_start(self):
        """Entity at start of text — no shift."""
        text = "Robin müsst"
        assert _byte_to_char_offsets(text, 0, 5) == (0, 5)

    def test_multibyte_inside_entity(self):
        """Multi-byte chars inside the entity span."""
        text = "hello Grüße world"
        # "Grüße" byte offset: 6-13 (7 bytes), char offset: 6-11 (5 chars)
        assert _byte_to_char_offsets(text, 6, 13) == (6, 11)


class TestTrimEntitySpan:

    def test_no_whitespace(self):
        assert _trim_entity_span("Hello Robin world", 6, 11) == (6, 11)

    def test_leading_space(self):
        """' Berlin' -> 'Berlin'"""
        text = "12.02 in Berlin zu"
        # span includes leading space: " Berlin" at positions 8-15
        assert _trim_entity_span(text, 8, 15) == (9, 15)

    def test_leading_newline(self):
        """'\\nJochen' -> 'Jochen'"""
        text = "KZB:\nJochen, Sprint"
        assert _trim_entity_span(text, 4, 11) == (5, 11)

    def test_trailing_space(self):
        text = "Hello Robin , bye"
        # "Robin " at 6-12
        assert _trim_entity_span(text, 6, 12) == (6, 11)

    def test_both_sides(self):
        text = "say  Robin  now"
        # "  Robin  " at 3-12
        assert _trim_entity_span(text, 3, 12) == (5, 10)

    def test_already_trimmed(self):
        text = "Hello Robin world"
        assert _trim_entity_span(text, 6, 11) == (6, 11)

    def test_all_whitespace_returns_empty_span(self):
        text = "hello   world"
        # span is "   " at 5-8
        start, end = _trim_entity_span(text, 5, 8)
        assert start == end  # empty span
