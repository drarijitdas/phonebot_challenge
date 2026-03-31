"""Regression testing suite for extraction accuracy.

Compares current run results against a stored baseline and flags regressions
that exceed a configurable tolerance. Reports which specific recordings and
fields regressed, enabling targeted investigation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from phonebot.evaluation.metrics import FIELDS
from phonebot.utils import write_json

BASELINE_PATH = Path("outputs/baseline_scores.json")
REGRESSION_TOLERANCE = 0.02  # 2% per-field tolerance


def save_baseline(
    metrics: dict[str, Any],
    per_recording: list[dict[str, Any]] | None = None,
    model: str = "",
    prompt_version: str = "",
    pipeline: str = "",
    baseline_path: Path = BASELINE_PATH,
) -> None:
    """Snapshot current metrics as the regression baseline.

    Args:
        metrics: Output from compute_metrics().
        per_recording: Per-recording breakdown for field-level regression detection.
        model: Model used for this baseline.
        prompt_version: Prompt version for this baseline.
        pipeline: Pipeline version for this baseline.
        baseline_path: Where to write the baseline JSON.
    """
    baseline = {
        "per_field": metrics["per_field"],
        "overall": metrics["overall"],
        "model": model,
        "prompt_version": prompt_version,
        "pipeline": pipeline,
        "per_recording": per_recording or metrics.get("per_recording", []),
    }
    write_json(baseline_path, baseline)


def load_baseline(baseline_path: Path = BASELINE_PATH) -> dict[str, Any] | None:
    """Load the stored baseline, or None if not found."""
    try:
        return json.loads(baseline_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def check_regression(
    current_metrics: dict[str, Any],
    current_per_recording: list[dict[str, Any]] | None = None,
    tolerance: float = REGRESSION_TOLERANCE,
    baseline_path: Path = BASELINE_PATH,
) -> dict[str, Any]:
    """Compare current metrics against baseline and detect regressions.

    Args:
        current_metrics: Output from compute_metrics() for the current run.
        current_per_recording: Per-recording breakdown for current run.
        tolerance: Maximum allowed accuracy drop per field before flagging.
        baseline_path: Path to baseline JSON.

    Returns:
        Dict with:
          - passed: bool — True if no regressions exceed tolerance
          - regressions: list of per-field regressions
          - recording_regressions: list of specific recording/field regressions
          - deltas: per-field accuracy deltas (positive = improvement)
    """
    baseline = load_baseline(baseline_path)
    if baseline is None:
        return {
            "passed": True,
            "message": "No baseline found — skipping regression check.",
            "regressions": [],
            "recording_regressions": [],
            "deltas": {},
        }

    baseline_pf = baseline["per_field"]
    current_pf = current_metrics["per_field"]

    deltas: dict[str, float] = {}
    regressions: list[dict[str, Any]] = []

    for field in FIELDS:
        baseline_val = baseline_pf.get(field, 0.0)
        current_val = current_pf.get(field, 0.0)
        delta = current_val - baseline_val
        deltas[field] = round(delta, 4)

        if delta < -tolerance:
            regressions.append({
                "field": field,
                "baseline": round(baseline_val, 4),
                "current": round(current_val, 4),
                "delta": round(delta, 4),
            })

    # Per-recording regression detection
    recording_regressions: list[dict[str, Any]] = []
    baseline_per_rec = {
        r["id"]: r for r in baseline.get("per_recording", [])
    }
    for rec in (current_per_recording or current_metrics.get("per_recording", [])):
        rec_id = rec["id"]
        baseline_rec = baseline_per_rec.get(rec_id)
        if not baseline_rec:
            continue
        for field in FIELDS:
            was_correct = baseline_rec.get(field, False)
            is_correct = rec.get(field, False)
            if was_correct and not is_correct:
                recording_regressions.append({
                    "recording_id": rec_id,
                    "field": field,
                    "was_correct": True,
                    "is_correct": False,
                })

    overall_delta = current_metrics["overall"] - baseline.get("overall", 0.0)

    return {
        "passed": len(regressions) == 0,
        "regressions": regressions,
        "recording_regressions": recording_regressions,
        "deltas": deltas,
        "overall_delta": round(overall_delta, 4),
    }


def print_regression_report(
    result: dict[str, Any],
    console: Console | None = None,
) -> None:
    """Print regression check results as Rich tables."""
    console = console or Console()

    if result.get("message"):
        console.print(f"[dim]{result['message']}[/dim]")
        return

    # Delta table
    deltas = result.get("deltas", {})
    table = Table(title="Accuracy Deltas vs Baseline")
    table.add_column("Field", style="cyan")
    table.add_column("Delta", justify="right")
    table.add_column("Status", justify="center")

    for field, delta in deltas.items():
        if delta > 0:
            style = "[green]+{:.1%}[/green]"
            status = "✓ improved"
        elif delta < -REGRESSION_TOLERANCE:
            style = "[red]{:.1%}[/red]"
            status = "[red]✗ REGRESSION[/red]"
        else:
            style = "{:.1%}"
            status = "✓ stable"
        table.add_row(field, style.format(delta), status)

    overall = result.get("overall_delta", 0)
    overall_style = "[green]+{:.1%}[/green]" if overall >= 0 else "[red]{:.1%}[/red]"
    table.add_row("[bold]Overall[/bold]", overall_style.format(overall), "")
    console.print(table)

    # Recording-level regressions
    rec_regs = result.get("recording_regressions", [])
    if rec_regs:
        console.print(f"\n[yellow]⚠ {len(rec_regs)} recording-level regression(s):[/yellow]")
        for rr in rec_regs[:10]:
            console.print(
                f"  {rr['recording_id']}/{rr['field']}: "
                f"was correct → now incorrect"
            )

    if result["passed"]:
        console.print("\n[green]✓ Regression check passed[/green]")
    else:
        console.print(f"\n[red]✗ {len(result['regressions'])} field(s) regressed beyond tolerance[/red]")
