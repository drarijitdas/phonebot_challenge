"""Shared utilities used across phonebot modules."""
from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

import phonenumbers
from phonenumbers import PhoneNumberFormat


@lru_cache(maxsize=1)
def get_git_commit() -> str | None:
    """Return current short git commit hash, or None if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def write_json(path: Path, data: Any) -> None:
    """Write data as formatted JSON to path, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def normalize_phone_e164(raw: str | None) -> str | None:
    """Normalize a phone number to E.164 format with German default region.

    Uses phonenumbers library with "DE" as the default region for parsing.
    Returns the E.164 formatted string on success, the original value on
    parse failure, or None if input is None.

    Args:
        raw: Raw phone number string, or None.

    Returns:
        E.164 formatted phone number, original string on parse failure, or None.
    """
    if raw is None:
        return None
    try:
        parsed = phonenumbers.parse(raw, "DE")
        return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        return raw
