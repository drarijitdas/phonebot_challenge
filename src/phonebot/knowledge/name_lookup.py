"""German name dictionary for grounding confidence adjustment.

Provides fuzzy matching against a curated set of common German and
international first/last names. Used post-extraction to adjust confidence
scores — NOT to override extractions. If the extracted name closely matches
a known name, confidence stays high. If no match is found, confidence is
lowered and the field is flagged for review.

This is a knowledge grounding layer, not a correction layer.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

NAMES_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "knowledge" / "german_names.json"

# Minimum fuzzy match score (0-100) to consider a name "grounded"
GROUNDING_THRESHOLD = 75

# Confidence penalty when name is NOT grounded
UNGROUNDED_PENALTY = 0.15


@lru_cache(maxsize=1)
def _load_names() -> dict[str, list[str]]:
    """Load the name dictionary. Returns {"first_names": [...], "last_names": [...]}."""
    if not NAMES_PATH.exists():
        return {"first_names": [], "last_names": []}
    return json.loads(NAMES_PATH.read_text(encoding="utf-8"))


def get_first_names() -> list[str]:
    """Return list of known first names."""
    return _load_names().get("first_names", [])


def get_last_names() -> list[str]:
    """Return list of known last names."""
    return _load_names().get("last_names", [])


def lookup_name(
    name: str,
    name_list: list[str],
    threshold: int = GROUNDING_THRESHOLD,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Fuzzy match a name against a list of known names.

    Args:
        name: The extracted name to look up.
        name_list: List of known names to match against.
        threshold: Minimum similarity score (0-100).
        limit: Maximum number of matches to return.

    Returns:
        List of dicts with keys: name, score, grounded.
        Empty list if name_list is empty or name is None.
    """
    if not name or not name_list:
        return []

    matches = process.extract(
        name.strip(),
        name_list,
        scorer=fuzz.ratio,
        limit=limit,
        score_cutoff=threshold,
    )

    return [
        {"name": match[0], "score": match[1], "grounded": match[1] >= threshold}
        for match in matches
    ]


def ground_name(
    extracted_name: str | None,
    field: str,
    current_confidence: float = 1.0,
) -> dict[str, Any]:
    """Check an extracted name against the knowledge base and adjust confidence.

    Args:
        extracted_name: The name extracted by the LLM.
        field: "first_name" or "last_name".
        current_confidence: Current confidence score for this field (0.0-1.0).

    Returns:
        Dict with keys:
          - grounded: bool — whether the name matched a known name
          - confidence: float — adjusted confidence score
          - matches: list — top fuzzy matches from the dictionary
          - original_confidence: float — the input confidence
    """
    if not extracted_name:
        return {
            "grounded": False,
            "confidence": current_confidence,
            "matches": [],
            "original_confidence": current_confidence,
        }

    name_list = get_first_names() if field == "first_name" else get_last_names()
    matches = lookup_name(extracted_name, name_list)

    grounded = len(matches) > 0 and matches[0]["grounded"]
    adjusted_confidence = current_confidence
    if not grounded:
        adjusted_confidence = max(0.0, current_confidence - UNGROUNDED_PENALTY)

    return {
        "grounded": grounded,
        "confidence": round(adjusted_confidence, 3),
        "matches": matches,
        "original_confidence": current_confidence,
    }


def ground_caller_info(
    caller_info: dict,
) -> dict[str, Any]:
    """Apply name grounding to all name fields in a CallerInfo dict.

    Args:
        caller_info: Dict with first_name, last_name, and confidence keys.

    Returns:
        Dict with grounding results for each name field.
    """
    confidence = caller_info.get("confidence") or {}

    results = {}
    for field in ("first_name", "last_name"):
        extracted = caller_info.get(field)
        current_conf = confidence.get(field, 0.8)
        results[field] = ground_name(extracted, field, current_conf)

    return results
