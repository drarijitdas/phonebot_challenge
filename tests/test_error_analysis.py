"""Tests for the error analysis pipeline."""
import pytest

from phonebot.evaluation.error_analysis import (
    ErrorType,
    analyze_errors,
    error_distribution,
    error_distribution_by_field,
)


class TestErrorClassification:
    def test_correct_extraction_no_error(self):
        results = [{"id": "call_01", "caller_info": {
            "first_name": "Johanna", "last_name": "Schmidt",
            "email": "johanna.schmidt@gmail.com", "phone_number": "+4915211223456",
        }}]
        gt = {"call_01": {
            "first_name": "Johanna", "last_name": "Schmidt",
            "email": "johanna.schmidt@gmail.com", "phone_number": "+49 152 11223456",
        }}
        errors = analyze_errors(results, gt)
        assert len(errors) == 0

    def test_name_omission(self):
        results = [{"id": "call_01", "caller_info": {"first_name": None, "last_name": "Schmidt"}}]
        gt = {"call_01": {"first_name": "Johanna", "last_name": "Schmidt"}}
        errors = analyze_errors(results, gt)
        assert len(errors) == 1
        assert errors[0].error_type == ErrorType.OMISSION
        assert errors[0].field == "first_name"

    def test_name_spelling_variant(self):
        results = [{"id": "call_01", "caller_info": {"last_name": "Andersson"}}]
        gt = {"call_01": {"last_name": "Anderson"}}
        errors = analyze_errors(results, gt)
        assert len(errors) == 1
        assert errors[0].error_type == ErrorType.NAME_SPELLING_VARIANT

    def test_email_domain_error(self):
        results = [{"id": "call_01", "caller_info": {"email": "johanna@gmail.com"}}]
        gt = {"call_01": {"email": "johanna@gmx.de"}}
        errors = analyze_errors(results, gt)
        assert len(errors) == 1
        assert errors[0].error_type == ErrorType.EMAIL_DOMAIN_ERROR

    def test_email_assembly_error(self):
        results = [{"id": "call_01", "caller_info": {"email": "johana.schmidt@gmail.com"}}]
        gt = {"call_01": {"email": "johanna.schmidt@gmail.com"}}
        errors = analyze_errors(results, gt)
        assert len(errors) == 1
        assert errors[0].error_type == ErrorType.EMAIL_ASSEMBLY_ERROR

    def test_phone_digit_error(self):
        results = [{"id": "call_01", "caller_info": {"phone_number": "+4915211223457"}}]
        gt = {"call_01": {"phone_number": "+4915211223456"}}
        errors = analyze_errors(results, gt)
        assert len(errors) == 1
        assert errors[0].error_type == ErrorType.PHONE_DIGIT_ERROR


class TestErrorDistribution:
    def test_distribution_counts(self):
        results = [
            {"id": "call_01", "caller_info": {"first_name": None, "email": "wrong@wrong.com"}},
            {"id": "call_02", "caller_info": {"first_name": None, "email": None}},
        ]
        gt = {
            "call_01": {"first_name": "A", "email": "right@gmail.com"},
            "call_02": {"first_name": "B", "email": "test@web.de"},
        }
        errors = analyze_errors(results, gt)
        dist = error_distribution(errors)

        assert ErrorType.OMISSION.value in dist
        assert dist[ErrorType.OMISSION.value] >= 2  # At least 2 omissions

    def test_distribution_by_field(self):
        results = [
            {"id": "call_01", "caller_info": {"first_name": None, "email": None}},
        ]
        gt = {"call_01": {"first_name": "A", "email": "a@b.com"}}
        errors = analyze_errors(results, gt)
        by_field = error_distribution_by_field(errors)

        assert "first_name" in by_field
        assert "email" in by_field
