"""Structured logging for the phonebot pipeline.

Provides JSON-formatted event logging alongside Phoenix OTEL traces.
Phoenix captures LLM call-level traces; this module captures application-level
events (extraction start/complete, validation failures, escalation triggers).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

import structlog


_configured = False


def configure_logging(
    log_level: str = "INFO",
    json_output: bool = True,
    log_file: str | None = None,
) -> None:
    """Configure structlog for JSON-formatted structured logging.

    Args:
        log_level: Standard logging level name.
        json_output: If True, render as JSON lines. If False, use console renderer.
        log_file: Optional file path for log output. Logs to stderr if None.
    """
    global _configured
    if _configured:
        return

    level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure standard library logging
    handlers: list[logging.Handler] = []

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    else:
        handlers.append(logging.StreamHandler(sys.stderr))

    logging.basicConfig(
        format="%(message)s",
        level=level,
        handlers=handlers,
        force=True,
    )

    # Configure structlog
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _configured = True


def get_logger(name: str = "phonebot", **initial_context: Any) -> structlog.stdlib.BoundLogger:
    """Get a structured logger with optional initial context.

    Args:
        name: Logger name (appears in log events).
        **initial_context: Key-value pairs bound to all events from this logger.

    Returns:
        Bound structlog logger.

    Example:
        log = get_logger("pipeline", model="claude-sonnet-4-6")
        log.info("extraction_start", recording_id="call_01")
        # {"event": "extraction_start", "recording_id": "call_01",
        #  "model": "claude-sonnet-4-6", "logger": "pipeline", ...}
    """
    if not _configured:
        configure_logging(
            log_level=os.getenv("PHONEBOT_LOG_LEVEL", "INFO"),
            json_output=os.getenv("PHONEBOT_LOG_FORMAT", "json") == "json",
            log_file=os.getenv("PHONEBOT_LOG_FILE"),
        )

    logger = structlog.get_logger(name)
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger


# Convenience: pre-defined event loggers for common pipeline events

def log_extraction_start(
    recording_id: str,
    model: str,
    pipeline: str,
    prompt_version: str,
) -> None:
    """Log the start of an extraction for a recording."""
    get_logger("pipeline").info(
        "extraction_start",
        recording_id=recording_id,
        model=model,
        pipeline=pipeline,
        prompt_version=prompt_version,
    )


def log_extraction_complete(
    recording_id: str,
    model: str,
    duration_seconds: float,
    flagged_fields: list[str] | None = None,
    cost_usd: float | None = None,
) -> None:
    """Log successful extraction completion."""
    get_logger("pipeline").info(
        "extraction_complete",
        recording_id=recording_id,
        model=model,
        duration_seconds=round(duration_seconds, 3),
        flagged_fields=flagged_fields or [],
        cost_usd=round(cost_usd, 6) if cost_usd else None,
    )


def log_validation_failure(
    recording_id: str,
    retry_count: int,
    errors: list[str],
) -> None:
    """Log a Pydantic validation failure triggering retry."""
    get_logger("pipeline").warning(
        "validation_failure",
        recording_id=recording_id,
        retry_count=retry_count,
        errors=errors,
    )


def log_critic_verdict(
    recording_id: str,
    iteration: int,
    approved: bool,
    feedback: str | None = None,
) -> None:
    """Log actor-critic verdict."""
    get_logger("pipeline").info(
        "critic_verdict",
        recording_id=recording_id,
        iteration=iteration,
        approved=approved,
        feedback=feedback,
    )


def log_escalation(
    recording_id: str,
    reason: str,
    confidence: float | None = None,
    flagged_fields: list[str] | None = None,
) -> None:
    """Log escalation to human review queue."""
    get_logger("pipeline").warning(
        "escalation_triggered",
        recording_id=recording_id,
        reason=reason,
        confidence=confidence,
        flagged_fields=flagged_fields or [],
    )


def log_retry(
    recording_id: str,
    node: str,
    attempt: int,
    max_attempts: int,
) -> None:
    """Log a retry attempt."""
    get_logger("pipeline").info(
        "retry_triggered",
        recording_id=recording_id,
        node=node,
        attempt=attempt,
        max_attempts=max_attempts,
    )
