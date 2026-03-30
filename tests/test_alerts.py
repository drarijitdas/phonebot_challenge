"""Tests for the quality alerting system."""
import pytest

from phonebot.observability.alerts import (
    check_alerts,
    AlertThresholds,
    Alert,
)


class TestAlerts:
    def test_no_alerts_good_metrics(self):
        metrics = {
            "per_field": {"first_name": 0.9, "last_name": 0.87, "email": 0.67, "phone_number": 1.0},
            "overall": 0.86,
        }
        alerts = check_alerts(metrics=metrics)
        assert len(alerts) == 0

    def test_overall_accuracy_alert(self):
        metrics = {
            "per_field": {"first_name": 0.7, "last_name": 0.7, "email": 0.5, "phone_number": 0.8},
            "overall": 0.675,
        }
        alerts = check_alerts(metrics=metrics)
        assert any(a.category == "accuracy" and a.severity == "critical" for a in alerts)

    def test_field_accuracy_alert(self):
        metrics = {
            "per_field": {"first_name": 0.9, "last_name": 0.87, "email": 0.50, "phone_number": 1.0},
            "overall": 0.8175,
        }
        alerts = check_alerts(metrics=metrics)
        field_alerts = [a for a in alerts if "email" in a.message]
        assert len(field_alerts) == 1

    def test_cost_alert(self):
        cost_summary = {"total_cost_usd": 30.0}
        alerts = check_alerts(cost_summary=cost_summary, total_recordings=30)
        cost_alerts = [a for a in alerts if a.category == "cost"]
        assert len(cost_alerts) == 1

    def test_latency_alert(self):
        latency_summary = {
            "violations": [
                {"recording_id": "call_01", "node": "extract", "duration": 35.0, "budget": 30.0}
            ]
        }
        alerts = check_alerts(latency_summary=latency_summary)
        assert any(a.category == "latency" for a in alerts)

    def test_escalation_rate_alert(self):
        alerts = check_alerts(escalation_count=10, total_recordings=30)
        assert any(a.category == "escalation" for a in alerts)

    def test_custom_thresholds(self):
        metrics = {"per_field": {"first_name": 0.9}, "overall": 0.9}
        thresholds = AlertThresholds(min_overall_accuracy=0.95)
        alerts = check_alerts(metrics=metrics, thresholds=thresholds)
        assert any(a.category == "accuracy" for a in alerts)

    def test_no_data_no_alerts(self):
        alerts = check_alerts()
        assert len(alerts) == 0
