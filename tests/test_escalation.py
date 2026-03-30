"""Tests for the escalation path."""
import json

import pytest

from phonebot.pipeline.escalation import (
    check_escalation,
    write_escalation_queue,
    load_escalation_queue,
    EscalationItem,
    MIN_OVERALL_CONFIDENCE,
)


class TestEscalationCheck:
    def test_no_escalation_high_confidence(self):
        caller_info = {
            "first_name": "Johanna",
            "last_name": "Schmidt",
            "confidence": {"first_name": 0.95, "last_name": 0.92, "email": 0.88, "phone_number": 0.99},
        }
        result = check_escalation("call_01", caller_info, flagged_fields=[])
        assert result is None

    def test_escalation_low_confidence(self):
        caller_info = {
            "first_name": "??",
            "confidence": {"first_name": 0.2, "last_name": 0.3, "email": 0.1, "phone_number": 0.4},
        }
        result = check_escalation("call_01", caller_info, flagged_fields=["first_name", "email", "phone_number"])
        assert result is not None
        assert "low_overall_confidence" in result.reason

    def test_escalation_too_many_flagged(self):
        caller_info = {
            "confidence": {"first_name": 0.5, "last_name": 0.5, "email": 0.5, "phone_number": 0.5},
        }
        result = check_escalation(
            "call_01", caller_info,
            flagged_fields=["first_name", "last_name", "email"],
            max_flagged=2,
        )
        assert result is not None
        assert "too_many_flagged" in result.reason

    def test_escalation_invalid_phone(self):
        caller_info = {
            "phone_number": "+491",
            "confidence": {"phone_number": 0.8},
        }
        contact_validation = {"phone": {"valid": False}, "email": {"valid_format": True}}
        result = check_escalation(
            "call_01", caller_info,
            flagged_fields=[],
            contact_validation=contact_validation,
        )
        assert result is not None
        assert "invalid_phone" in result.reason

    def test_escalation_item_to_dict(self):
        item = EscalationItem(
            recording_id="call_01",
            reason="test",
            caller_info={"first_name": "Test"},
            confidence={"first_name": 0.5},
            flagged_fields=["first_name"],
            transcript_excerpt="...",
            overall_confidence=0.5,
            timestamp="2026-01-01T00:00:00Z",
        )
        d = item.to_dict()
        assert d["recording_id"] == "call_01"
        assert d["reason"] == "test"


class TestEscalationQueue:
    def test_write_and_load(self, tmp_path):
        queue_path = tmp_path / "queue.json"
        items = [
            EscalationItem(
                recording_id="call_01",
                reason="low_confidence",
                caller_info={},
                confidence={},
                flagged_fields=[],
                transcript_excerpt="test",
                overall_confidence=0.3,
                timestamp="2026-01-01T00:00:00Z",
            ),
        ]
        write_escalation_queue(items, queue_path)

        loaded = load_escalation_queue(queue_path)
        assert len(loaded) == 1
        assert loaded[0]["recording_id"] == "call_01"

    def test_empty_queue_not_written(self, tmp_path):
        queue_path = tmp_path / "queue.json"
        write_escalation_queue([], queue_path)
        assert not queue_path.exists()
