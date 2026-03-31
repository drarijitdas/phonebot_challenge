"""Tests for the latency monitor observability module."""
import time

import pytest

from phonebot.observability.latency import LatencyMonitor, LatencyRecord, DEFAULT_BUDGETS


class TestLatencyRecord:
    def test_within_budget(self):
        rec = LatencyRecord(recording_id="call_01", node="extract", duration_seconds=5.0, budget_seconds=10.0)
        assert rec.within_budget is True
        assert rec.overage_pct is None

    def test_over_budget(self):
        rec = LatencyRecord(recording_id="call_01", node="extract", duration_seconds=15.0, budget_seconds=10.0)
        assert rec.within_budget is False
        assert rec.overage_pct == 50.0

    def test_no_budget(self):
        rec = LatencyRecord(recording_id="call_01", node="custom", duration_seconds=100.0)
        assert rec.within_budget is True


class TestLatencyMonitor:
    def test_manual_record(self):
        monitor = LatencyMonitor()
        monitor.record("call_01", "extract", 5.0)
        assert len(monitor.records) == 1
        assert monitor.records[0].duration_seconds == 5.0

    def test_context_manager(self):
        monitor = LatencyMonitor()
        with monitor.track("call_01", "validate"):
            time.sleep(0.01)
        assert len(monitor.records) == 1
        assert monitor.records[0].duration_seconds >= 0.01

    def test_violations(self):
        monitor = LatencyMonitor(budgets={"extract": 5.0})
        monitor.record("call_01", "extract", 3.0)
        monitor.record("call_02", "extract", 8.0)
        assert len(monitor.violations) == 1
        assert monitor.violations[0].recording_id == "call_02"

    def test_avg_by_node(self):
        monitor = LatencyMonitor()
        monitor.record("call_01", "extract", 4.0)
        monitor.record("call_02", "extract", 6.0)
        avg = monitor.avg_by_node()
        assert abs(avg["extract"] - 5.0) < 0.001

    def test_p95_by_node(self):
        monitor = LatencyMonitor()
        for i in range(20):
            monitor.record(f"call_{i:02d}", "extract", float(i))
        p95 = monitor.p95_by_node()
        assert p95["extract"] >= 18.0  # 95th percentile of 0-19

    def test_to_dict(self):
        monitor = LatencyMonitor(budgets={"extract": 5.0})
        monitor.record("call_01", "extract", 8.0)
        d = monitor.to_dict()
        assert "avg_by_node" in d
        assert "p95_by_node" in d
        assert len(d["violations"]) == 1

    def test_default_budgets_exist(self):
        assert "end_to_end" in DEFAULT_BUDGETS
        assert "extract" in DEFAULT_BUDGETS
        assert "validate" in DEFAULT_BUDGETS
