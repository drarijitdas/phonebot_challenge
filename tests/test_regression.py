"""Tests for the regression testing suite."""
import json

import pytest

from phonebot.evaluation.regression import (
    save_baseline,
    load_baseline,
    check_regression,
    REGRESSION_TOLERANCE,
)


@pytest.fixture
def tmp_baseline(tmp_path):
    return tmp_path / "baseline.json"


class TestRegression:
    def test_save_and_load_baseline(self, tmp_baseline):
        metrics = {
            "per_field": {"first_name": 0.9, "last_name": 0.87, "email": 0.67, "phone_number": 1.0},
            "overall": 0.86,
        }
        save_baseline(metrics, model="claude-sonnet-4-6", baseline_path=tmp_baseline)

        loaded = load_baseline(tmp_baseline)
        assert loaded is not None
        assert loaded["per_field"]["first_name"] == 0.9
        assert loaded["overall"] == 0.86

    def test_no_baseline_passes(self, tmp_baseline):
        metrics = {"per_field": {"first_name": 0.5}, "overall": 0.5}
        result = check_regression(metrics, baseline_path=tmp_baseline)
        assert result["passed"] is True
        assert "No baseline" in result.get("message", "")

    def test_no_regression(self, tmp_baseline):
        baseline = {
            "per_field": {"first_name": 0.9, "last_name": 0.87, "email": 0.67, "phone_number": 1.0},
            "overall": 0.86,
            "per_recording": [],
        }
        save_baseline(baseline, baseline_path=tmp_baseline)

        current = {
            "per_field": {"first_name": 0.93, "last_name": 0.87, "email": 0.70, "phone_number": 1.0},
            "overall": 0.875,
        }
        result = check_regression(current, baseline_path=tmp_baseline)
        assert result["passed"] is True
        assert len(result["regressions"]) == 0

    def test_regression_detected(self, tmp_baseline):
        baseline = {
            "per_field": {"first_name": 0.9, "last_name": 0.87, "email": 0.67, "phone_number": 1.0},
            "overall": 0.86,
            "per_recording": [],
        }
        save_baseline(baseline, baseline_path=tmp_baseline)

        current = {
            "per_field": {"first_name": 0.9, "last_name": 0.87, "email": 0.60, "phone_number": 1.0},
            "overall": 0.8425,
        }
        result = check_regression(current, baseline_path=tmp_baseline)
        assert result["passed"] is False
        assert len(result["regressions"]) == 1
        assert result["regressions"][0]["field"] == "email"

    def test_within_tolerance_passes(self, tmp_baseline):
        baseline = {
            "per_field": {"first_name": 0.9, "last_name": 0.87, "email": 0.67, "phone_number": 1.0},
            "overall": 0.86,
            "per_recording": [],
        }
        save_baseline(baseline, baseline_path=tmp_baseline)

        # Drop email by 1% (within 2% tolerance)
        current = {
            "per_field": {"first_name": 0.9, "last_name": 0.87, "email": 0.66, "phone_number": 1.0},
            "overall": 0.8575,
        }
        result = check_regression(current, baseline_path=tmp_baseline)
        assert result["passed"] is True

    def test_recording_level_regression(self, tmp_baseline):
        baseline = {
            "per_field": {"first_name": 0.9},
            "overall": 0.9,
            "per_recording": [
                {"id": "call_01", "first_name": True},
                {"id": "call_02", "first_name": True},
            ],
        }
        save_baseline(baseline, baseline_path=tmp_baseline)

        current = {
            "per_field": {"first_name": 0.5},
            "overall": 0.5,
        }
        current_per_rec = [
            {"id": "call_01", "first_name": True},
            {"id": "call_02", "first_name": False},  # Regressed!
        ]
        result = check_regression(current, current_per_rec, baseline_path=tmp_baseline)
        assert len(result["recording_regressions"]) == 1
        assert result["recording_regressions"][0]["recording_id"] == "call_02"

    def test_deltas_computed(self, tmp_baseline):
        baseline = {
            "per_field": {"first_name": 0.9, "last_name": 0.87, "email": 0.67, "phone_number": 1.0},
            "overall": 0.86,
            "per_recording": [],
        }
        save_baseline(baseline, baseline_path=tmp_baseline)

        current = {
            "per_field": {"first_name": 0.93, "last_name": 0.87, "email": 0.70, "phone_number": 0.97},
            "overall": 0.8675,
        }
        result = check_regression(current, baseline_path=tmp_baseline)
        assert result["deltas"]["first_name"] > 0  # Improved
        assert result["deltas"]["phone_number"] < 0  # Regressed but within tolerance
