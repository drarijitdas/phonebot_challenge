"""Error analysis pipeline for extraction failures.

Categorizes each extraction failure into a specific error type using string
distance, pattern matching, and structural checks (no LLM calls). Produces
a distribution of error types that enables targeted prompt improvements.

Error categories:
  - NAME_PHONETIC_MISMATCH: Phonetically plausible but wrong (García → Gassia)
  - NAME_SPELLING_VARIANT: Close spelling variant (Andersson → Anderson)
  - EMAIL_ASSEMBLY_ERROR: Email spoken-form reconstruction failure
  - PHONE_DIGIT_ERROR: Wrong digit count or transposition
  - HALLUCINATION: Predicted value has no basis in ground truth
  - OMISSION: Predicted null when ground truth exists
  - NULL_MISMATCH: Predicted a value when ground truth is null
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from phonebot.evaluation.metrics import FIELDS, normalize_value


class ErrorType(str, Enum):
    NAME_PHONETIC_MISMATCH = "NAME_PHONETIC_MISMATCH"
    NAME_SPELLING_VARIANT = "NAME_SPELLING_VARIANT"
    EMAIL_ASSEMBLY_ERROR = "EMAIL_ASSEMBLY_ERROR"
    EMAIL_DOMAIN_ERROR = "EMAIL_DOMAIN_ERROR"
    PHONE_DIGIT_ERROR = "PHONE_DIGIT_ERROR"
    HALLUCINATION = "HALLUCINATION"
    OMISSION = "OMISSION"
    NULL_MISMATCH = "NULL_MISMATCH"
    UNKNOWN = "UNKNOWN"


@dataclass
class ErrorRecord:
    """A single classified extraction error."""

    recording_id: str
    field: str
    error_type: ErrorType
    predicted: str | None
    expected: str | None
    detail: str = ""


def _levenshtein_ratio(a: str, b: str) -> float:
    """Normalized Levenshtein similarity (0.0 to 1.0)."""
    try:
        from rapidfuzz import fuzz
        return fuzz.ratio(a, b) / 100.0
    except ImportError:
        # Fallback: simple character overlap
        if not a or not b:
            return 0.0
        common = set(a.lower()) & set(b.lower())
        return len(common) / max(len(a), len(b))


def _classify_name_error(predicted: str | None, expected: str | None) -> tuple[ErrorType, str]:
    """Classify a name field error."""
    if predicted is None:
        return ErrorType.OMISSION, "Predicted null for existing name"
    if expected is None:
        return ErrorType.NULL_MISMATCH, "Predicted a name when none expected"

    pred_lower = predicted.lower().strip()
    exp_lower = expected.lower().strip()

    similarity = _levenshtein_ratio(pred_lower, exp_lower)

    if similarity >= 0.7:
        return ErrorType.NAME_SPELLING_VARIANT, f"similarity={similarity:.2f}"

    # Check if it could be a phonetic mismatch (different orthography, same-ish sound)
    # Heuristic: first letter matches + similar length
    if pred_lower and exp_lower and pred_lower[0] == exp_lower[0]:
        len_ratio = min(len(pred_lower), len(exp_lower)) / max(len(pred_lower), len(exp_lower))
        if len_ratio > 0.6:
            return ErrorType.NAME_PHONETIC_MISMATCH, f"first-letter match, len_ratio={len_ratio:.2f}"

    return ErrorType.HALLUCINATION, f"low similarity={similarity:.2f}"


def _classify_email_error(predicted: str | None, expected: str | None) -> tuple[ErrorType, str]:
    """Classify an email field error."""
    if predicted is None:
        return ErrorType.OMISSION, "Predicted null for existing email"
    if expected is None:
        return ErrorType.NULL_MISMATCH, "Predicted email when none expected"

    pred_lower = predicted.lower().strip()
    exp_lower = expected.lower().strip()

    pred_local, _, pred_domain = pred_lower.partition("@")
    exp_local, _, exp_domain = exp_lower.partition("@")

    # Domain error
    if pred_domain != exp_domain:
        return ErrorType.EMAIL_DOMAIN_ERROR, f"expected @{exp_domain}, got @{pred_domain}"

    # Local part assembly error (common in spoken German email)
    similarity = _levenshtein_ratio(pred_local, exp_local)
    if similarity >= 0.5:
        return ErrorType.EMAIL_ASSEMBLY_ERROR, f"local part similarity={similarity:.2f}"

    return ErrorType.HALLUCINATION, f"unrelated email, similarity={similarity:.2f}"


def _classify_phone_error(predicted: str | None, expected: str | None) -> tuple[ErrorType, str]:
    """Classify a phone number error."""
    if predicted is None:
        return ErrorType.OMISSION, "Predicted null for existing phone"
    if expected is None:
        return ErrorType.NULL_MISMATCH, "Predicted phone when none expected"

    pred_digits = "".join(c for c in predicted if c.isdigit())
    exp_digits = "".join(c for c in expected if c.isdigit())

    if len(pred_digits) != len(exp_digits):
        return ErrorType.PHONE_DIGIT_ERROR, f"digit count: predicted {len(pred_digits)}, expected {len(exp_digits)}"

    # Same length but wrong digits — transposition or mishearing
    diff_positions = sum(1 for a, b in zip(pred_digits, exp_digits) if a != b)
    if diff_positions <= 3:
        return ErrorType.PHONE_DIGIT_ERROR, f"{diff_positions} digit(s) differ"

    return ErrorType.HALLUCINATION, f"{diff_positions} digits differ (likely wrong number)"


def analyze_errors(
    results: list[dict],
    ground_truth: dict[str, dict],
) -> list[ErrorRecord]:
    """Classify all extraction errors in a result set.

    Args:
        results: Extraction results (list of {id, caller_info, ...}).
        ground_truth: Dict keyed by recording_id with expected values.

    Returns:
        List of ErrorRecord for every incorrect field extraction.
    """
    errors: list[ErrorRecord] = []

    for result in results:
        rec_id = result["id"]
        info = result.get("caller_info") or {}
        if hasattr(info, "model_dump"):
            info = info.model_dump()
        expected = ground_truth.get(rec_id, {})

        for field in FIELDS:
            pred_val = info.get(field)
            gt_val = expected.get(field)

            # Normalize for comparison
            norm_pred = normalize_value(field, pred_val)
            norm_gt = normalize_value(field, gt_val)

            # Handle list ground truth
            if isinstance(gt_val, list):
                normalized_gts = [normalize_value(field, v) for v in gt_val]
                if norm_pred in normalized_gts:
                    continue  # Correct
                gt_val = gt_val[0]  # Use first for error classification
                norm_gt = normalized_gts[0]

            if norm_pred == norm_gt:
                continue  # Correct extraction

            # Classify the error
            if field in ("first_name", "last_name"):
                error_type, detail = _classify_name_error(pred_val, gt_val)
            elif field == "email":
                error_type, detail = _classify_email_error(pred_val, gt_val)
            elif field == "phone_number":
                error_type, detail = _classify_phone_error(pred_val, gt_val)
            else:
                error_type, detail = ErrorType.UNKNOWN, ""

            errors.append(ErrorRecord(
                recording_id=rec_id,
                field=field,
                error_type=error_type,
                predicted=pred_val,
                expected=gt_val if not isinstance(gt_val, list) else str(gt_val),
                detail=detail,
            ))

    return errors


def error_distribution(errors: list[ErrorRecord]) -> dict[str, int]:
    """Count errors by type."""
    dist: dict[str, int] = {}
    for e in errors:
        dist[e.error_type.value] = dist.get(e.error_type.value, 0) + 1
    return dict(sorted(dist.items(), key=lambda x: -x[1]))


def error_distribution_by_field(errors: list[ErrorRecord]) -> dict[str, dict[str, int]]:
    """Count errors by field and type."""
    dist: dict[str, dict[str, int]] = {}
    for e in errors:
        if e.field not in dist:
            dist[e.field] = {}
        dist[e.field][e.error_type.value] = dist[e.field].get(e.error_type.value, 0) + 1
    return dist


def print_error_analysis(
    errors: list[ErrorRecord],
    console: Console | None = None,
) -> None:
    """Print error analysis as Rich tables."""
    console = console or Console()

    if not errors:
        console.print("[green]No extraction errors — perfect accuracy![/green]")
        return

    # Overall distribution
    dist = error_distribution(errors)
    table = Table(title=f"Error Distribution ({len(errors)} total errors)")
    table.add_column("Error Type", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("% of Errors", justify="right")

    for error_type, count in dist.items():
        pct = count / len(errors) * 100
        table.add_row(error_type, str(count), f"{pct:.1f}%")

    console.print(table)

    # Per-field breakdown
    by_field = error_distribution_by_field(errors)
    for field, field_dist in sorted(by_field.items()):
        field_table = Table(title=f"Errors in '{field}'")
        field_table.add_column("Error Type", style="cyan")
        field_table.add_column("Count", justify="right")
        for et, count in sorted(field_dist.items(), key=lambda x: -x[1]):
            field_table.add_row(et, str(count))
        console.print(field_table)

    # Detailed error listing
    console.print(f"\n[bold]Detailed Errors ({len(errors)}):[/bold]")
    for e in errors:
        console.print(
            f"  {e.recording_id}/{e.field}: "
            f"[red]{e.error_type.value}[/red] — "
            f"predicted={e.predicted!r}, expected={e.expected!r}"
            f"{f' ({e.detail})' if e.detail else ''}"
        )


def save_error_analysis(
    errors: list[ErrorRecord],
    output_path: Path = Path("outputs/error_analysis.json"),
) -> None:
    """Save error analysis to JSON."""
    data = {
        "total_errors": len(errors),
        "distribution": error_distribution(errors),
        "by_field": error_distribution_by_field(errors),
        "errors": [
            {
                "recording_id": e.recording_id,
                "field": e.field,
                "error_type": e.error_type.value,
                "predicted": e.predicted,
                "expected": e.expected,
                "detail": e.detail,
            }
            for e in errors
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
