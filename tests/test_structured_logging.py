"""Tests for the structured logging module."""
import pytest

from phonebot.observability.logging import (
    configure_logging,
    get_logger,
    log_extraction_start,
    log_extraction_complete,
    log_validation_failure,
    log_critic_verdict,
    log_escalation,
    log_retry,
)


class TestStructuredLogging:
    def test_get_logger(self):
        log = get_logger("test_module")
        assert log is not None

    def test_get_logger_with_context(self):
        log = get_logger("test_module", model="claude-sonnet-4-6")
        assert log is not None

    def test_configure_idempotent(self):
        configure_logging(log_level="DEBUG", json_output=False)
        configure_logging(log_level="INFO", json_output=True)
        # Should not raise — second call is a no-op

    def test_convenience_functions_dont_raise(self):
        """All convenience log functions should not raise."""
        log_extraction_start("call_01", "claude-sonnet-4-6", "v1", "v1")
        log_extraction_complete("call_01", "claude-sonnet-4-6", 1.5, ["email"], 0.001)
        log_validation_failure("call_01", 1, ["field error"])
        log_critic_verdict("call_01", 0, True, "all correct")
        log_escalation("call_01", "low confidence", 0.3, ["email", "phone"])
        log_retry("call_01", "extract", 1, 3)
