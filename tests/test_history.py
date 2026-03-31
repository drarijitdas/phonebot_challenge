"""Tests for the metrics history tracking module."""
import json

import pytest

from phonebot.evaluation.history import record_run, load_history, HISTORY_PATH


@pytest.fixture
def tmp_history(tmp_path):
    return tmp_path / "test_history.jsonl"


class TestMetricsHistory:
    def test_record_run(self, tmp_history):
        metrics = {
            "per_field": {"first_name": 0.9, "last_name": 0.87, "email": 0.67, "phone_number": 1.0},
            "overall": 0.86,
        }
        record = record_run(
            metrics, "claude-sonnet-4-6", "v2", "v1",
            history_path=tmp_history,
        )
        assert record["model"] == "claude-sonnet-4-6"
        assert record["overall"] == 0.86
        assert "timestamp" in record

    def test_load_history(self, tmp_history):
        metrics = {"per_field": {"first_name": 0.9}, "overall": 0.9}
        record_run(metrics, "model1", "v1", "v1", history_path=tmp_history)
        record_run(metrics, "model2", "v2", "v2", history_path=tmp_history)

        records = load_history(tmp_history)
        assert len(records) == 2
        assert records[0]["model"] == "model1"
        assert records[1]["model"] == "model2"

    def test_load_empty_history(self, tmp_history):
        records = load_history(tmp_history)
        assert records == []

    def test_extra_metadata(self, tmp_history):
        metrics = {"per_field": {}, "overall": 0.5}
        record = record_run(
            metrics, "m", "v1", "v1",
            extra={"cost_usd": 0.05, "latency": 2.3},
            history_path=tmp_history,
        )
        assert record["extra"]["cost_usd"] == 0.05

    def test_appends_not_overwrites(self, tmp_history):
        metrics = {"per_field": {}, "overall": 0.5}
        record_run(metrics, "m1", "v1", "v1", history_path=tmp_history)
        record_run(metrics, "m2", "v1", "v1", history_path=tmp_history)
        record_run(metrics, "m3", "v1", "v1", history_path=tmp_history)

        records = load_history(tmp_history)
        assert len(records) == 3
