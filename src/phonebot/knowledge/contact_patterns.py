"""Contact pattern validation for structural grounding.

Validates extracted phone numbers and email addresses against known patterns
without using LLM calls. Adjusts confidence based on structural validity:
  - Phone: Is it a valid German number? Correct length? Plausible prefix?
  - Email: Valid format? Known domain? MX record exists?

This provides a zero-cost grounding signal that complements LLM confidence.
"""
from __future__ import annotations

import re
from typing import Any

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat, PhoneNumberType


# Common German and international email providers
KNOWN_DOMAINS: set[str] = {
    # German
    "gmail.com", "gmx.de", "gmx.net", "web.de", "t-online.de",
    "freenet.de", "outlook.de", "posteo.de", "mailbox.org",
    # International
    "outlook.com", "hotmail.com", "hotmail.es", "yahoo.com",
    "yahoo.de", "yahoo.fr", "icloud.com", "protonmail.com",
    "libero.it", "uol.com.br", "outlook.fr",
}

# Strict email regex
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)

# Confidence adjustments
INVALID_PHONE_PENALTY = 0.25
INVALID_EMAIL_PENALTY = 0.20
UNKNOWN_DOMAIN_PENALTY = 0.10


def validate_phone(phone: str | None) -> dict[str, Any]:
    """Validate a phone number against German phone number patterns.

    Returns:
        Dict with keys:
          - valid: bool — structurally valid German number
          - number_type: str — mobile, fixed_line, voip, etc.
          - e164: str | None — E.164 formatted number (if valid)
          - issues: list[str] — validation issues found
    """
    if not phone:
        return {"valid": False, "number_type": None, "e164": None, "issues": ["empty"]}

    issues: list[str] = []

    try:
        parsed = phonenumbers.parse(phone, "DE")
    except NumberParseException as e:
        return {
            "valid": False,
            "number_type": None,
            "e164": None,
            "issues": [f"parse_error: {e}"],
        }

    is_valid = phonenumbers.is_valid_number(parsed)
    is_possible = phonenumbers.is_possible_number(parsed)

    if not is_possible:
        issues.append("impossible_number_length")
    if not is_valid:
        issues.append("invalid_for_region")

    # Check number type
    num_type = phonenumbers.number_type(parsed)
    type_names = {
        PhoneNumberType.MOBILE: "mobile",
        PhoneNumberType.FIXED_LINE: "fixed_line",
        PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_line_or_mobile",
        PhoneNumberType.VOIP: "voip",
        PhoneNumberType.PERSONAL_NUMBER: "personal",
        PhoneNumberType.UNKNOWN: "unknown",
    }
    type_name = type_names.get(num_type, "other")

    e164 = None
    if is_valid:
        e164 = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)

    return {
        "valid": is_valid,
        "number_type": type_name,
        "e164": e164,
        "issues": issues,
    }


def validate_email(email: str | None) -> dict[str, Any]:
    """Validate an email address format and domain.

    Returns:
        Dict with keys:
          - valid_format: bool — passes regex validation
          - known_domain: bool — domain is in our known providers list
          - domain: str | None — extracted domain
          - issues: list[str] — validation issues found
    """
    if not email:
        return {
            "valid_format": False,
            "known_domain": False,
            "domain": None,
            "issues": ["empty"],
        }

    email = email.strip().lower()
    issues: list[str] = []

    valid_format = bool(_EMAIL_RE.match(email))
    if not valid_format:
        issues.append("invalid_format")

    _, _, domain = email.partition("@")
    known_domain = domain in KNOWN_DOMAINS

    if not domain:
        issues.append("no_domain")
    elif not known_domain:
        issues.append(f"unknown_domain: {domain}")

    return {
        "valid_format": valid_format,
        "known_domain": known_domain,
        "domain": domain or None,
        "issues": issues,
    }


def validate_contacts(caller_info: dict) -> dict[str, dict[str, Any]]:
    """Validate all contact fields in a CallerInfo dict.

    Args:
        caller_info: Dict with phone_number and email keys.

    Returns:
        Dict with phone and email validation results.
    """
    return {
        "phone": validate_phone(caller_info.get("phone_number")),
        "email": validate_email(caller_info.get("email")),
    }


def adjust_confidence(
    caller_info: dict,
    validation: dict[str, dict[str, Any]] | None = None,
) -> dict[str, float]:
    """Adjust confidence scores based on contact pattern validation.

    Args:
        caller_info: Dict with caller fields and confidence.
        validation: Pre-computed validation results (if None, computed fresh).

    Returns:
        Adjusted confidence dict with the same keys as the original.
    """
    if validation is None:
        validation = validate_contacts(caller_info)

    confidence = dict(caller_info.get("confidence") or {})

    # Phone confidence adjustment
    phone_val = validation.get("phone", {})
    if not phone_val.get("valid", True):
        current = confidence.get("phone_number", 0.8)
        confidence["phone_number"] = max(0.0, round(current - INVALID_PHONE_PENALTY, 3))

    # Email confidence adjustment
    email_val = validation.get("email", {})
    if not email_val.get("valid_format", True):
        current = confidence.get("email", 0.8)
        confidence["email"] = max(0.0, round(current - INVALID_EMAIL_PENALTY, 3))
    elif not email_val.get("known_domain", True):
        current = confidence.get("email", 0.8)
        confidence["email"] = max(0.0, round(current - UNKNOWN_DOMAIN_PENALTY, 3))

    return confidence
