"""Escalation path for low-confidence extractions.

Implements human-in-the-loop escalation: after extraction and post-processing,
checks whether the result should be escalated to a human reviewer. Escalated
items are written to a queue file with full context for manual review.

Trigger conditions:
  - Overall confidence below threshold (default 0.5)
  - More than N flagged fields (default 2)
  - Structurally invalid contact info (phone or email fails validation)

In production, this would publish to a message queue (SQS, RabbitMQ).
The file-based approach demonstrates the architectural pattern.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ESCALATION_QUEUE_PATH = Path("outputs/escalation_queue.json")

# Escalation thresholds
MIN_OVERALL_CONFIDENCE = 0.5
MAX_FLAGGED_FIELDS = 2


@dataclass
class EscalationItem:
    """A recording escalated for human review."""

    recording_id: str
    reason: str
    caller_info: dict[str, Any]
    confidence: dict[str, float]
    flagged_fields: list[str]
    transcript_excerpt: str
    overall_confidence: float
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "recording_id": self.recording_id,
            "reason": self.reason,
            "caller_info": self.caller_info,
            "confidence": self.confidence,
            "flagged_fields": self.flagged_fields,
            "transcript_excerpt": self.transcript_excerpt,
            "overall_confidence": round(self.overall_confidence, 3),
            "timestamp": self.timestamp,
        }


def check_escalation(
    recording_id: str,
    caller_info: dict[str, Any],
    flagged_fields: list[str],
    transcript_text: str | None = None,
    contact_validation: dict[str, Any] | None = None,
    min_confidence: float = MIN_OVERALL_CONFIDENCE,
    max_flagged: int = MAX_FLAGGED_FIELDS,
) -> EscalationItem | None:
    """Check whether an extraction should be escalated.

    Args:
        recording_id: Recording identifier.
        caller_info: Extracted CallerInfo dict.
        flagged_fields: Fields below confidence threshold.
        transcript_text: Original transcript (for excerpt in queue).
        contact_validation: Results from contact pattern validation.
        min_confidence: Minimum average confidence to avoid escalation.
        max_flagged: Maximum flagged fields before escalation.

    Returns:
        EscalationItem if escalation is triggered, None otherwise.
    """
    confidence = caller_info.get("confidence") or {}
    conf_values = [v for v in confidence.values() if isinstance(v, (int, float))]
    overall_confidence = sum(conf_values) / len(conf_values) if conf_values else 0.0

    reasons: list[str] = []

    # Check overall confidence
    if overall_confidence < min_confidence:
        reasons.append(f"low_overall_confidence ({overall_confidence:.2f} < {min_confidence})")

    # Check flagged fields count
    if len(flagged_fields) > max_flagged:
        reasons.append(f"too_many_flagged_fields ({len(flagged_fields)} > {max_flagged})")

    # Check contact validation
    if contact_validation:
        phone_val = contact_validation.get("phone", {})
        if not phone_val.get("valid", True) and caller_info.get("phone_number"):
            reasons.append("invalid_phone_number")

        email_val = contact_validation.get("email", {})
        if not email_val.get("valid_format", True) and caller_info.get("email"):
            reasons.append("invalid_email_format")

    if not reasons:
        return None  # No escalation needed

    excerpt = ""
    if transcript_text:
        excerpt = transcript_text[:500] + ("..." if len(transcript_text) > 500 else "")

    return EscalationItem(
        recording_id=recording_id,
        reason="; ".join(reasons),
        caller_info=caller_info,
        confidence=confidence,
        flagged_fields=flagged_fields,
        transcript_excerpt=excerpt,
        overall_confidence=overall_confidence,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def write_escalation_queue(
    items: list[EscalationItem],
    output_path: Path = ESCALATION_QUEUE_PATH,
) -> None:
    """Write escalation queue to JSON file.

    Args:
        items: List of escalated items.
        output_path: Path for the queue file.
    """
    if not items:
        return

    data = {
        "escalation_count": len(items),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "items": [item.to_dict() for item in items],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_escalation_queue(
    input_path: Path = ESCALATION_QUEUE_PATH,
) -> list[dict[str, Any]]:
    """Load the escalation queue from JSON."""
    if not input_path.exists():
        return []
    data = json.loads(input_path.read_text(encoding="utf-8"))
    return data.get("items", [])
