"""Tests for evaluation metrics module."""
import pytest
from pathlib import Path
from phonebot.evaluation.metrics import (
    FIELDS,
    load_ground_truth,
    normalize_phone,
    normalize_text,
    normalize_value,
    matches_field,
    compute_metrics,
)


class TestNormalizePhone:
    def test_e164_with_spaces(self):
        assert normalize_phone("+49 152 11223456") == "+4915211223456"

    def test_e164_without_spaces(self):
        assert normalize_phone("+4915211223456") == "+4915211223456"

    def test_local_format(self):
        assert normalize_phone("015211223456") == "+4915211223456"

    def test_none_returns_none(self):
        assert normalize_phone(None) is None

    def test_invalid_passthrough(self):
        assert normalize_phone("not a number") == "not a number"


class TestNormalizeText:
    def test_lowercase(self):
        assert normalize_text("MUELLER") == "mueller"

    def test_strip_whitespace(self):
        assert normalize_text("  Julia  ") == "julia"

    def test_none_returns_none(self):
        assert normalize_text(None) is None

    def test_german_umlaut_preserved(self):
        # NFC normalization preserves composed characters
        assert normalize_text("Schroeder") == "schroeder"
        assert normalize_text("Mueller") == "mueller"

    def test_casefold_eszett(self):
        # German sharp-s folds to "ss"
        assert normalize_text("Strasse") == "strasse"
        # casefold converts eszett to ss
        result = normalize_text("Stra\u00dfe")
        assert result == "strasse"


class TestMatchesField:
    def test_exact_match_case_insensitive(self):
        assert matches_field("first_name", "julia", "Julia") is True

    def test_both_none(self):
        assert matches_field("first_name", None, None) is True

    def test_predicted_none_gt_not_none(self):
        assert matches_field("first_name", None, "Julia") is False

    def test_predicted_not_none_gt_none(self):
        assert matches_field("first_name", "Julia", None) is False

    def test_multi_value_match_first(self):
        assert matches_field("first_name", "Lisa Marie", ["Lisa Marie", "Lisa-Marie"]) is True

    def test_multi_value_match_second(self):
        assert matches_field("first_name", "Lisa-Marie", ["Lisa Marie", "Lisa-Marie"]) is True

    def test_multi_value_no_match(self):
        assert matches_field("first_name", "Wrong", ["Lisa Marie", "Lisa-Marie"]) is False

    def test_phone_e164_normalization(self):
        assert matches_field("phone_number", "015211223456", "+49 152 11223456") is True

    def test_phone_both_e164(self):
        assert matches_field("phone_number", "+4915211223456", "+49 152 11223456") is True

    def test_email_case_insensitive(self):
        assert matches_field("email", "Julia@Example.COM", "julia@example.com") is True


class TestLoadGroundTruth:
    def test_loads_all_30_recordings(self):
        gt = load_ground_truth(Path("data/ground_truth.json"))
        assert len(gt) == 30

    def test_first_recording_has_expected_fields(self):
        gt = load_ground_truth(Path("data/ground_truth.json"))
        assert "call_01" in gt
        expected = gt["call_01"]
        assert "first_name" in expected
        assert "last_name" in expected
        assert "email" in expected
        assert "phone_number" in expected


class TestComputeMetrics:
    def test_all_empty_returns_zero_accuracy(self):
        gt = load_ground_truth(Path("data/ground_truth.json"))
        mock_results = [{"id": rec_id, "caller_info": {}} for rec_id in gt]
        metrics = compute_metrics(mock_results, gt)
        for field in FIELDS:
            assert metrics["per_field"][field] == 0.0

    def test_perfect_results_return_full_accuracy(self):
        gt = load_ground_truth(Path("data/ground_truth.json"))
        perfect_results = [
            {"id": rec_id, "caller_info": expected}
            for rec_id, expected in gt.items()
        ]
        metrics = compute_metrics(perfect_results, gt)
        for field in FIELDS:
            assert metrics["per_field"][field] == 1.0
        assert metrics["overall"] == 1.0

    def test_per_recording_breakdown_has_booleans(self):
        gt = load_ground_truth(Path("data/ground_truth.json"))
        mock_results = [{"id": rec_id, "caller_info": {}} for rec_id in gt]
        metrics = compute_metrics(mock_results, gt)
        assert len(metrics["per_recording"]) == 30
        for row in metrics["per_recording"]:
            assert "id" in row
            for field in FIELDS:
                assert isinstance(row[field], bool)

    def test_accepts_caller_info_object(self):
        """compute_metrics handles CallerInfo objects via model_dump()."""
        from phonebot.models.caller_info import CallerInfo
        gt = load_ground_truth(Path("data/ground_truth.json"))
        # Use just one recording for simplicity
        rec_id = "call_01"
        info = CallerInfo(
            first_name=gt[rec_id]["first_name"],
            last_name=gt[rec_id]["last_name"],
            email=gt[rec_id]["email"],
            phone_number=gt[rec_id]["phone_number"],
        )
        metrics = compute_metrics(
            [{"id": rec_id, "caller_info": info}],
            {rec_id: gt[rec_id]},
        )
        for field in FIELDS:
            assert metrics["per_field"][field] == 1.0

    def test_overall_is_average_of_field_accuracies(self):
        gt = load_ground_truth(Path("data/ground_truth.json"))
        mock_results = [{"id": rec_id, "caller_info": {}} for rec_id in gt]
        metrics = compute_metrics(mock_results, gt)
        expected_overall = sum(metrics["per_field"].values()) / len(FIELDS)
        assert metrics["overall"] == expected_overall
