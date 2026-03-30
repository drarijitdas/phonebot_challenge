"""Difficulty-tiered benchmark evaluation.

Segments recordings into meaningful tiers and computes per-tier accuracy,
exposing where the system struggles. Tiers include:
  - Name origin: German (calls 1-15) vs international (calls 16-30)
  - Email complexity: simple, hyphenated, digit-containing, foreign domain
  - Phone format: mobile (015x/016x/017x) vs landline (030/040/089/etc.)

This enables targeted optimization: if accuracy on international names is 70%
vs 95% on German names, prompt tuning should focus on phonetic normalization.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from phonebot.evaluation.metrics import FIELDS, compute_metrics
from phonebot.knowledge.contact_patterns import KNOWN_DOMAINS


# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------

GERMAN_IDS = {f"call_{i:02d}" for i in range(1, 16)}
INTERNATIONAL_IDS = {f"call_{i:02d}" for i in range(16, 31)}

# German mobile prefixes (015x, 016x, 017x)
_MOBILE_RE = re.compile(r"^\+49\s*1[5-7]")
# German landline: starts with +49 followed by area code (2-5 digits, NOT starting with 1)
_LANDLINE_RE = re.compile(r"^\+49\s*[2-9]")


@dataclass
class TierResult:
    """Accuracy result for a single tier."""

    tier_name: str
    tier_value: str
    recording_ids: list[str]
    per_field: dict[str, float]
    overall: float
    count: int


def _classify_email(email: str | None) -> str:
    """Classify email complexity."""
    if not email:
        return "missing"
    local, _, domain = email.partition("@")
    if "-" in local:
        return "hyphenated"
    if re.search(r"\d", local):
        return "digit_containing"
    if domain and domain not in KNOWN_DOMAINS:
        return "foreign_domain"
    return "simple"


def _classify_phone(phone: str | None) -> str:
    """Classify phone as mobile or landline."""
    if not phone:
        return "missing"
    if _MOBILE_RE.match(phone):
        return "mobile"
    if _LANDLINE_RE.match(phone):
        return "landline"
    return "other"


def compute_tiered_benchmarks(
    results: list[dict],
    ground_truth: dict[str, dict],
) -> dict[str, list[TierResult]]:
    """Compute accuracy broken down by multiple tier dimensions.

    Args:
        results: Extraction results (list of {id, caller_info, ...}).
        ground_truth: Dict keyed by recording_id with expected values.

    Returns:
        Dict mapping tier dimension name to list of TierResult.
    """
    # Build lookup: recording_id -> result
    results_by_id = {r["id"]: r for r in results}

    tiers: dict[str, list[TierResult]] = {}

    # --- Tier 1: Name Origin ---
    tiers["name_origin"] = _compute_tier(
        results, ground_truth,
        "name_origin",
        lambda rid, _gt: "german" if rid in GERMAN_IDS else "international",
    )

    # --- Tier 2: Email Complexity ---
    tiers["email_complexity"] = _compute_tier(
        results, ground_truth,
        "email_complexity",
        lambda _rid, gt: _classify_email(gt.get("email")),
    )

    # --- Tier 3: Phone Format ---
    tiers["phone_format"] = _compute_tier(
        results, ground_truth,
        "phone_format",
        lambda _rid, gt: _classify_phone(gt.get("phone_number")),
    )

    return tiers


def _compute_tier(
    results: list[dict],
    ground_truth: dict[str, dict],
    tier_name: str,
    classify_fn,
) -> list[TierResult]:
    """Group recordings by a classification function and compute per-group metrics."""
    groups: dict[str, list[dict]] = {}
    for r in results:
        gt = ground_truth.get(r["id"], {})
        tier_value = classify_fn(r["id"], gt)
        groups.setdefault(tier_value, []).append(r)

    tier_results = []
    for tier_value, group_results in sorted(groups.items()):
        group_gt = {r["id"]: ground_truth[r["id"]] for r in group_results if r["id"] in ground_truth}
        metrics = compute_metrics(group_results, group_gt)
        tier_results.append(TierResult(
            tier_name=tier_name,
            tier_value=tier_value,
            recording_ids=[r["id"] for r in group_results],
            per_field=metrics["per_field"],
            overall=metrics["overall"],
            count=len(group_results),
        ))

    return tier_results


def print_benchmark_report(
    tiers: dict[str, list[TierResult]],
    console: Console | None = None,
) -> None:
    """Print tiered benchmark results as Rich tables."""
    console = console or Console()

    for dimension, tier_results in tiers.items():
        table = Table(title=f"Benchmark: {dimension}")
        table.add_column("Tier", style="cyan")
        table.add_column("Count", justify="right")
        table.add_column("first_name", justify="right")
        table.add_column("last_name", justify="right")
        table.add_column("email", justify="right")
        table.add_column("phone", justify="right")
        table.add_column("Overall", justify="right", style="bold")

        for tr in tier_results:
            table.add_row(
                tr.tier_value,
                str(tr.count),
                f"{tr.per_field.get('first_name', 0):.0%}",
                f"{tr.per_field.get('last_name', 0):.0%}",
                f"{tr.per_field.get('email', 0):.0%}",
                f"{tr.per_field.get('phone_number', 0):.0%}",
                f"{tr.overall:.0%}",
            )

        console.print(table)
        console.print()


def save_benchmark_report(
    tiers: dict[str, list[TierResult]],
    output_path: Path = Path("outputs/benchmark_report.json"),
) -> None:
    """Save benchmark results to JSON."""
    serializable = {}
    for dimension, tier_results in tiers.items():
        serializable[dimension] = [
            {
                "tier_value": tr.tier_value,
                "count": tr.count,
                "per_field": {k: round(v, 4) for k, v in tr.per_field.items()},
                "overall": round(tr.overall, 4),
                "recording_ids": tr.recording_ids,
            }
            for tr in tier_results
        ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
