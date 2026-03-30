"""Tests for the difficulty-tiered benchmark module."""
import pytest

from phonebot.evaluation.benchmark import (
    GERMAN_IDS,
    INTERNATIONAL_IDS,
    _classify_email,
    _classify_phone,
    compute_tiered_benchmarks,
    TierResult,
)


class TestEmailClassification:
    def test_simple(self):
        assert _classify_email("johanna.schmidt@gmail.com") == "simple"

    def test_hyphenated(self):
        assert _classify_email("sandra-weber@t-online.de") == "hyphenated"

    def test_digit_containing(self):
        assert _classify_email("h47-herbst@web.de") == "hyphenated"  # hyphen takes priority

    def test_foreign_domain(self):
        assert _classify_email("user@obscure-provider.xyz") == "foreign_domain"

    def test_missing(self):
        assert _classify_email(None) == "missing"


class TestPhoneClassification:
    def test_mobile(self):
        assert _classify_phone("+49 152 11223456") == "mobile"
        assert _classify_phone("+49 172 44556677") == "mobile"

    def test_landline(self):
        assert _classify_phone("+49 30 54783219") == "landline"
        assert _classify_phone("+49 89 77234561") == "landline"

    def test_missing(self):
        assert _classify_phone(None) == "missing"


class TestTierSets:
    def test_german_ids(self):
        assert len(GERMAN_IDS) == 15
        assert "call_01" in GERMAN_IDS
        assert "call_15" in GERMAN_IDS
        assert "call_16" not in GERMAN_IDS

    def test_international_ids(self):
        assert len(INTERNATIONAL_IDS) == 15
        assert "call_16" in INTERNATIONAL_IDS
        assert "call_30" in INTERNATIONAL_IDS
        assert "call_15" not in INTERNATIONAL_IDS


class TestTieredBenchmarks:
    def test_name_origin_tiers(self):
        # Minimal test data
        results = [
            {"id": "call_01", "caller_info": {"first_name": "Johanna", "last_name": "Schmidt",
                                               "email": "johanna.schmidt@gmail.com", "phone_number": "+4915211223456"}},
            {"id": "call_16", "caller_info": {"first_name": "James", "last_name": "Anderson",
                                               "email": "james.anderson@gmail.com", "phone_number": "+4916055123456"}},
        ]
        ground_truth = {
            "call_01": {"first_name": "Johanna", "last_name": "Schmidt",
                        "email": "johanna.schmidt@gmail.com", "phone_number": "+49 152 11223456"},
            "call_16": {"first_name": "James", "last_name": "Anderson",
                        "email": "james.anderson@gmail.com", "phone_number": "+49 160 55123456"},
        }

        tiers = compute_tiered_benchmarks(results, ground_truth)
        assert "name_origin" in tiers
        assert "email_complexity" in tiers
        assert "phone_format" in tiers

        # Both should have 100% accuracy
        for tr in tiers["name_origin"]:
            assert tr.overall == 1.0
