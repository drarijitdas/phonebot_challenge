"""Tests for the knowledge grounding layer."""
import pytest

from phonebot.knowledge.name_lookup import (
    lookup_name,
    ground_name,
    ground_caller_info,
    get_first_names,
    get_last_names,
    GROUNDING_THRESHOLD,
)
from phonebot.knowledge.contact_patterns import (
    validate_phone,
    validate_email,
    validate_contacts,
    adjust_confidence,
)


class TestNameLookup:
    def test_load_names(self):
        first_names = get_first_names()
        last_names = get_last_names()
        assert len(first_names) > 100
        assert len(last_names) > 100

    def test_exact_match(self):
        matches = lookup_name("Johanna", get_first_names())
        assert len(matches) > 0
        assert matches[0]["name"] == "Johanna"
        assert matches[0]["grounded"] is True

    def test_close_match(self):
        matches = lookup_name("Johanaa", get_first_names(), threshold=70)
        assert len(matches) > 0
        assert matches[0]["score"] >= 70

    def test_no_match(self):
        matches = lookup_name("Xyzzyplugh", get_first_names(), threshold=80)
        assert len(matches) == 0

    def test_ground_name_found(self):
        result = ground_name("Johanna", "first_name", 0.9)
        assert result["grounded"] is True
        assert result["confidence"] == 0.9  # Not penalized

    def test_ground_name_not_found(self):
        result = ground_name("Xyzzyplugh", "first_name", 0.9)
        assert result["grounded"] is False
        assert result["confidence"] < 0.9  # Penalized

    def test_ground_none(self):
        result = ground_name(None, "first_name", 0.8)
        assert result["grounded"] is False

    def test_ground_caller_info(self):
        caller_info = {
            "first_name": "Johanna",
            "last_name": "Schmidt",
            "confidence": {"first_name": 0.95, "last_name": 0.92},
        }
        results = ground_caller_info(caller_info)
        assert "first_name" in results
        assert "last_name" in results
        assert results["first_name"]["grounded"] is True


class TestContactPatterns:
    def test_valid_german_mobile(self):
        result = validate_phone("+4915211223456")
        assert result["valid"] is True
        assert result["number_type"] == "mobile"
        assert result["e164"] == "+4915211223456"

    def test_valid_german_landline(self):
        result = validate_phone("+493054783219")
        assert result["valid"] is True

    def test_invalid_phone(self):
        result = validate_phone("+491234")
        assert result["valid"] is False
        assert len(result["issues"]) > 0

    def test_empty_phone(self):
        result = validate_phone(None)
        assert result["valid"] is False

    def test_valid_email(self):
        result = validate_email("johanna.schmidt@gmail.com")
        assert result["valid_format"] is True
        assert result["known_domain"] is True

    def test_unknown_domain(self):
        result = validate_email("user@obscure-provider.xyz")
        assert result["valid_format"] is True
        assert result["known_domain"] is False

    def test_invalid_email(self):
        result = validate_email("not-an-email")
        assert result["valid_format"] is False

    def test_empty_email(self):
        result = validate_email(None)
        assert result["valid_format"] is False

    def test_validate_contacts(self):
        caller_info = {
            "phone_number": "+4915211223456",
            "email": "test@gmail.com",
        }
        result = validate_contacts(caller_info)
        assert "phone" in result
        assert "email" in result

    def test_adjust_confidence_valid(self):
        caller_info = {
            "phone_number": "+4915211223456",
            "email": "test@gmail.com",
            "confidence": {"phone_number": 0.9, "email": 0.85},
        }
        adjusted = adjust_confidence(caller_info)
        assert adjusted["phone_number"] == 0.9  # No penalty
        assert adjusted["email"] == 0.85  # No penalty

    def test_adjust_confidence_invalid_phone(self):
        caller_info = {
            "phone_number": "+491",
            "email": "test@gmail.com",
            "confidence": {"phone_number": 0.9, "email": 0.85},
        }
        adjusted = adjust_confidence(caller_info)
        assert adjusted["phone_number"] < 0.9  # Penalized
