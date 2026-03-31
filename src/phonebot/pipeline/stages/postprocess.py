"""Stage 4: Post-processing with rule-based normalization and knowledge grounding.

Rule-based (no LLM) normalization and validation:
  - Phone: E.164 normalization via phonenumbers library
  - Email: Lowercase, format validation
  - Names: Unicode NFC normalization
  - Cross-reference: Does the name match the email local part?
  - Knowledge grounding: Name dictionary lookup, contact pattern validation

This stage enriches the extraction with grounding signals that help
downstream consumers assess data quality.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any

from phonebot.knowledge.contact_patterns import validate_contacts, adjust_confidence
from phonebot.knowledge.name_lookup import ground_caller_info
from phonebot.utils import normalize_phone_e164


@dataclass
class PostprocessResult:
    """Result of post-processing a CallerInfo extraction."""

    caller_info: dict[str, Any]                 # Normalized CallerInfo dict (includes confidence)
    grounding: dict[str, Any]                   # Knowledge grounding results
    contact_validation: dict[str, Any]          # Contact pattern validation
    cross_reference: dict[str, Any]             # Name↔email consistency
    normalizations_applied: list[str]           # Log of what was normalized


def _normalize_phone(phone: str | None) -> tuple[str | None, bool]:
    """Normalize phone to E.164. Returns (normalized, was_changed)."""
    if not phone:
        return phone, False
    normalized = normalize_phone_e164(phone)
    return normalized, normalized != phone


def _normalize_email(email: str | None) -> tuple[str | None, bool]:
    """Normalize email to lowercase. Returns (normalized, was_changed)."""
    if not email:
        return email, False
    normalized = email.strip().lower()
    return normalized, normalized != email


def _normalize_name(name: str | None) -> tuple[str | None, bool]:
    """NFC normalize a name. Returns (normalized, was_changed)."""
    if not name:
        return name, False
    normalized = unicodedata.normalize("NFC", name).strip()
    return normalized, normalized != name


def _cross_reference_check(caller_info: dict) -> dict[str, Any]:
    """Check if extracted name is consistent with email local part.

    E.g., first_name="Johanna", email="johanna.schmidt@..." → consistent.
    """
    first_name = (caller_info.get("first_name") or "").lower().strip()
    last_name = (caller_info.get("last_name") or "").lower().strip()
    email = (caller_info.get("email") or "").lower().strip()

    if not email or not (first_name or last_name):
        return {"consistent": None, "detail": "insufficient data"}

    local_part = email.split("@")[0] if "@" in email else ""

    # Check various email naming patterns
    checks = {
        "first_in_email": first_name and first_name in local_part,
        "last_in_email": last_name and last_name in local_part,
        "first_initial": first_name and local_part.startswith(first_name[0]),
        "full_name_pattern": (
            first_name and last_name and
            (f"{first_name}.{last_name}" == local_part or
             f"{first_name}_{last_name}" == local_part or
             f"{first_name}-{last_name}" == local_part or
             f"{first_name[0]}.{last_name}" == local_part)
        ),
    }

    consistent = any(checks.values())
    return {
        "consistent": consistent,
        "checks": checks,
        "detail": "name matches email pattern" if consistent else "name does not match email local part",
    }


def postprocess(
    caller_info: dict[str, Any],
) -> PostprocessResult:
    """Run full post-processing pipeline on a CallerInfo extraction.

    Args:
        caller_info: Raw CallerInfo dict from extraction stage.

    Returns:
        PostprocessResult with normalized data and grounding signals.
    """
    normalizations: list[str] = []
    info = dict(caller_info)

    phone, phone_changed = _normalize_phone(info.get("phone_number"))
    if phone_changed:
        info["phone_number"] = phone
        normalizations.append("phone_e164")

    email, email_changed = _normalize_email(info.get("email"))
    if email_changed:
        info["email"] = email
        normalizations.append("email_lowercase")

    for name_field in ("first_name", "last_name"):
        name, name_changed = _normalize_name(info.get(name_field))
        if name_changed:
            info[name_field] = name
            normalizations.append(f"{name_field}_nfc")

    contact_validation = validate_contacts(info)
    grounding = ground_caller_info(info)
    cross_ref = _cross_reference_check(info)
    adjusted_confidence = adjust_confidence(info, contact_validation)

    for name_field in ("first_name", "last_name"):
        ground_result = grounding.get(name_field, {})
        if ground_result:
            adjusted_confidence[name_field] = ground_result.get(
                "confidence",
                adjusted_confidence.get(name_field, 0.8),
            )

    if cross_ref.get("consistent") is False:
        for f in ("first_name", "last_name"):
            current = adjusted_confidence.get(f, 0.8)
            adjusted_confidence[f] = max(0.0, round(current - 0.05, 3))

    info["confidence"] = adjusted_confidence

    return PostprocessResult(
        caller_info=info,
        grounding=grounding,
        contact_validation=contact_validation,
        cross_reference=cross_ref,
        normalizations_applied=normalizations,
    )
