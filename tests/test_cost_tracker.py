"""Tests for the cost tracker observability module."""
import pytest

from phonebot.observability.cost_tracker import CostTracker, TokenRecord, _resolve_pricing


class TestTokenRecord:
    def test_cost_calculation(self):
        rec = TokenRecord(
            recording_id="call_01",
            node="extract",
            model="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=500,
            latency_seconds=1.5,
        )
        # $3/1M input + $15/1M output
        expected = 1000 * 3.0 / 1_000_000 + 500 * 15.0 / 1_000_000
        assert abs(rec.cost_usd - expected) < 1e-9

    def test_ollama_zero_cost(self):
        rec = TokenRecord(
            recording_id="call_01",
            node="extract",
            model="ollama:llama3.2:3b",
            input_tokens=5000,
            output_tokens=2000,
            latency_seconds=3.0,
        )
        assert rec.cost_usd == 0.0


class TestPricingResolution:
    def test_known_model(self):
        p = _resolve_pricing("claude-sonnet-4-6")
        assert p["input"] == 3.0
        assert p["output"] == 15.0

    def test_ollama_prefix(self):
        p = _resolve_pricing("ollama:anything")
        assert p["input"] == 0.0

    def test_unknown_falls_back_to_sonnet(self):
        p = _resolve_pricing("unknown-model-xyz")
        assert p["input"] == 3.0  # Conservative default


class TestCostTracker:
    def test_record_and_totals(self):
        tracker = CostTracker()
        tracker.record("call_01", "extract", "claude-sonnet-4-6", 1000, 500, 1.5)
        tracker.record("call_02", "extract", "claude-sonnet-4-6", 800, 400, 1.2)

        assert len(tracker.records) == 2
        assert tracker.total_input_tokens == 1800
        assert tracker.total_output_tokens == 900
        assert tracker.total_cost > 0

    def test_cost_by_recording(self):
        tracker = CostTracker()
        tracker.record("call_01", "extract", "claude-sonnet-4-6", 1000, 500, 1.5)
        tracker.record("call_01", "critic", "claude-sonnet-4-6", 600, 200, 1.0)
        tracker.record("call_02", "extract", "claude-sonnet-4-6", 800, 400, 1.2)

        by_rec = tracker.cost_by_recording()
        assert "call_01" in by_rec
        assert "call_02" in by_rec
        assert by_rec["call_01"] > by_rec["call_02"]

    def test_cost_by_node(self):
        tracker = CostTracker()
        tracker.record("call_01", "extract", "claude-sonnet-4-6", 1000, 500, 1.5)
        tracker.record("call_01", "critic", "claude-sonnet-4-6", 600, 200, 1.0)

        by_node = tracker.cost_by_node()
        assert "extract" in by_node
        assert "critic" in by_node

    def test_to_dict(self):
        tracker = CostTracker()
        tracker.record("call_01", "extract", "claude-sonnet-4-6", 1000, 500, 1.5)

        d = tracker.to_dict()
        assert "total_cost_usd" in d
        assert "cost_by_recording" in d
        assert "cost_by_node" in d
        assert d["num_invocations"] == 1

    def test_record_from_response_metadata(self):
        tracker = CostTracker()
        metadata = {"usage": {"input_tokens": 1200, "output_tokens": 350}}
        tracker.record_from_response_metadata(
            "call_01", "extract", "claude-sonnet-4-6", metadata, 2.0
        )
        assert tracker.total_input_tokens == 1200
        assert tracker.total_output_tokens == 350

    def test_empty_tracker(self):
        tracker = CostTracker()
        assert tracker.total_cost == 0.0
        assert tracker.cost_by_recording() == {}
        assert tracker.cost_by_node() == {}
