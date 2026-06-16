"""Tests for post-processing validation rules."""
import pytest
from ensemble_recognizer import validate_results, NormalizedResult


def r(start, end, entity_type, score, text_value):
    return NormalizedResult(
        entity_type=entity_type, start=start, end=end,
        score=score, source="test",
    ), text_value


class TestValidation:

    def test_email_without_at_rejected(self):
        """'.com' should not pass as EMAIL_ADDRESS."""
        result, text = r(0, 4, "EMAIL_ADDRESS", 0.96, ".com")
        assert validate_results([result], ".com") == []

    def test_valid_email_passes(self):
        result, text = r(0, 17, "EMAIL_ADDRESS", 0.95, "robin@systag.com")
        kept = validate_results([result], "robin@systag.com")
        assert len(kept) == 1

    def test_short_name_rejected(self):
        result, text = r(0, 1, "PERSON", 0.90, "R")
        assert validate_results([result], "R") == []

    def test_valid_name_passes(self):
        result, text = r(0, 5, "PERSON", 0.90, "Robin")
        kept = validate_results([result], "Robin")
        assert len(kept) == 1

    def test_short_phone_rejected(self):
        result, text = r(0, 3, "PHONE_NUMBER", 0.90, "123")
        assert validate_results([result], "123") == []

    def test_short_credit_card_rejected(self):
        result, text = r(0, 8, "CREDIT_CARD", 0.90, "41111111")
        assert validate_results([result], "41111111") == []

    def test_unknown_type_passes_through(self):
        """Entity types without validation rules pass through."""
        result, text = r(0, 11, "CUSTOM_TYPE", 0.90, "hello world")
        kept = validate_results([result], "hello world")
        assert len(kept) == 1

    def test_placeholder_rejected_as_person(self):
        """Indexed placeholders should not be re-detected as PII."""
        text = "Hello <PERSON_1>"
        result = NormalizedResult("PERSON", 6, 16, 0.69, "nerguard")
        assert validate_results([result], text) == []

    def test_placeholder_rejected_as_organization(self):
        text = "works at <ORGANIZATION_1>"
        result = NormalizedResult("ORGANIZATION", 9, 25, 0.39, "gliner")
        assert validate_results([result], text) == []

    def test_placeholder_rejected_various_types(self):
        """All placeholder types should be filtered."""
        for placeholder in ["<EMAIL_ADDRESS_1>", "<PHONE_NUMBER_2>", "<ADDRESS_1>"]:
            text = placeholder
            result = NormalizedResult("PERSON", 0, len(text), 0.5, "test")
            assert validate_results([result], text) == [], f"{placeholder} should be filtered"

    def test_partial_placeholder_without_closing_bracket(self):
        """NER models sometimes detect partial spans like '<PERSON_1' without '>'."""
        text = "Hello <PERSON_1>"
        result = NormalizedResult("PERSON", 6, 15, 0.39, "nerguard")  # <PERSON_1 without >
        assert validate_results([result], text) == []

    def test_partial_placeholder_without_opening_bracket(self):
        text = "Hello <PERSON_1>"
        result = NormalizedResult("PERSON", 7, 16, 0.39, "nerguard")  # PERSON_1>
        assert validate_results([result], text) == []

    # --- ZIP_CODE validation ---

    def test_single_char_zipcode_rejected(self):
        """Single character 'M' should not be a ZIP_CODE."""
        result, _ = r(0, 1, "ZIP_CODE", 0.465, "M")
        assert validate_results([result], "M") == []

    def test_single_digit_zipcode_rejected(self):
        """Single digit '3' should not be a ZIP_CODE."""
        result, _ = r(0, 1, "ZIP_CODE", 0.333, "3")
        assert validate_results([result], "3") == []

    def test_zipcode_without_digits_rejected(self):
        """Letters-only string should not be a ZIP_CODE."""
        result, _ = r(0, 3, "ZIP_CODE", 0.80, "ABC")
        assert validate_results([result], "ABC") == []

    def test_valid_zipcode_passes(self):
        result, _ = r(0, 5, "ZIP_CODE", 0.90, "10115")
        kept = validate_results([result], "10115")
        assert len(kept) == 1

    def test_alphanumeric_zipcode_passes(self):
        """UK-style postcodes like 'SW1A' should pass."""
        result, _ = r(0, 4, "ZIP_CODE", 0.85, "SW1A")
        kept = validate_results([result], "SW1A")
        assert len(kept) == 1

    # --- USERNAME validation ---

    def test_short_username_rejected(self):
        """'IAM' (3 chars) should not be a USERNAME."""
        result, _ = r(0, 3, "USERNAME", 0.305, "IAM")
        assert validate_results([result], "IAM") == []

    def test_valid_username_passes(self):
        result, _ = r(0, 7, "USERNAME", 0.80, "robin.s")
        kept = validate_results([result], "robin.s")
        assert len(kept) == 1

    # --- ORGANIZATION validation (length + score) ---

    def test_short_organization_rejected(self):
        """2-char string should not be an ORGANIZATION."""
        result, _ = r(0, 2, "ORGANIZATION", 0.90, "AB")
        assert validate_results([result], "AB") == []

    def test_low_score_organization_rejected(self):
        """'Team' at 0.503 should be filtered by MIN_SCORE."""
        result, _ = r(0, 4, "ORGANIZATION", 0.503, "Team")
        assert validate_results([result], "Team") == []

    def test_low_score_organization_telko_rejected(self):
        """'TelKo' at 0.655 should be filtered by MIN_SCORE."""
        result, _ = r(0, 5, "ORGANIZATION", 0.655, "TelKo")
        assert validate_results([result], "TelKo") == []

    def test_high_score_organization_passes(self):
        result, _ = r(0, 6, "ORGANIZATION", 0.85, "Systag")
        kept = validate_results([result], "Systag")
        assert len(kept) == 1

    # --- IP_ADDRESS validation ---

    def test_invalid_ip_rejected(self):
        result, _ = r(0, 5, "IP_ADDRESS", 0.80, "1.2.3")
        assert validate_results([result], "1.2.3") == []

    def test_valid_ip_passes(self):
        result, _ = r(0, 11, "IP_ADDRESS", 0.90, "192.168.1.1")
        kept = validate_results([result], "192.168.1.1")
        assert len(kept) == 1

    # --- IBAN_CODE validation ---

    def test_short_iban_rejected(self):
        result, _ = r(0, 10, "IBAN_CODE", 0.80, "DE12345678")
        assert validate_results([result], "DE12345678") == []

    def test_valid_iban_passes(self):
        iban = "DE89370400440532013000"
        result, _ = r(0, len(iban), "IBAN_CODE", 0.90, iban)
        kept = validate_results([result], iban)
        assert len(kept) == 1
