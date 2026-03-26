"""Evaluation metrics for comparing extraction results against ground truth."""
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

import phonenumbers
from phonenumbers import PhoneNumberFormat


FIELDS = ("first_name", "last_name", "email", "phone_number")


def load_ground_truth(path: Path) -> dict[str, dict[str, Any]]:
    """Return dict keyed by recording id, value is the 'expected' dict."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {rec["id"]: rec["expected"] for rec in data["recordings"]}


def normalize_phone(raw: str | None) -> str | None:
    """Normalize to E.164 with German default region. Returns raw on failure."""
    if raw is None:
        return None
    try:
        parsed = phonenumbers.parse(raw, "DE")
        return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        return raw  # Return as-is; comparison will likely fail


def normalize_text(raw: str | None) -> str | None:
    """NFC normalize and case-fold for name/email comparison."""
    if raw is None:
        return None
    return unicodedata.normalize("NFC", raw).casefold().strip()


def normalize_value(field: str, value: str | None) -> str | None:
    """Apply appropriate normalization based on field type."""
    if field == "phone_number":
        return normalize_phone(value)
    return normalize_text(value)


def matches_field(
    field: str,
    predicted: str | None,
    ground_truth_value: str | list[str] | None,
) -> bool:
    """
    Compare predicted against ground truth for a single field.
    Handles:
    - null ground truth: predicted must also be null
    - scalar ground truth: normalized equality
    - list ground truth: predicted matches any item after normalization
    """
    norm_pred = normalize_value(field, predicted)

    if ground_truth_value is None:
        return norm_pred is None

    if isinstance(ground_truth_value, list):
        acceptable = [normalize_value(field, v) for v in ground_truth_value]
        return norm_pred in acceptable

    # Scalar
    return norm_pred == normalize_value(field, ground_truth_value)


def compute_metrics(
    results: list[dict],
    ground_truth: dict[str, dict],
) -> dict:
    """
    Compute per-field accuracy and per-recording breakdown.

    Args:
        results: list of {"id": str, "caller_info": CallerInfo | dict}
        ground_truth: dict keyed by recording id with expected values

    Returns:
        {
            "per_field": {"first_name": 0.8, ...},
            "overall": 0.7,
            "per_recording": [{"id": "call_01", "first_name": True, ...}, ...],
        }
    """
    per_field_correct = {f: 0 for f in FIELDS}
    per_recording = []
    n = len(results)

    for result in results:
        rec_id = result["id"]
        info = result.get("caller_info") or {}
        if hasattr(info, "model_dump"):
            info = info.model_dump()
        expected = ground_truth.get(rec_id, {})

        row: dict[str, Any] = {"id": rec_id}
        for field in FIELDS:
            pred_val = info.get(field)
            gt_val = expected.get(field)
            correct = matches_field(field, pred_val, gt_val)
            row[field] = correct
            if correct:
                per_field_correct[field] += 1
        per_recording.append(row)

    per_field_accuracy = {f: per_field_correct[f] / n if n else 0.0 for f in FIELDS}
    overall = sum(per_field_accuracy.values()) / len(FIELDS)

    return {
        "per_field": per_field_accuracy,
        "overall": overall,
        "per_recording": per_recording,
    }


if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table

    console = Console()
    gt_path = Path("data/ground_truth.json")

    if not gt_path.exists():
        console.print(f"[red]Ground truth not found: {gt_path}[/red]")
        sys.exit(1)

    gt = load_ground_truth(gt_path)

    # Baseline: mock results with all None extractions (0% accuracy)
    mock_results = [
        {"id": rec_id, "caller_info": {}}
        for rec_id in gt
    ]

    metrics = compute_metrics(mock_results, gt)

    table = Table(title="Evaluation Results (Baseline - 0%)")
    table.add_column("Field", style="cyan")
    table.add_column("Accuracy", style="magenta")

    for field, acc in metrics["per_field"].items():
        table.add_row(field, f"{acc:.1%}")
    table.add_row("[bold]Overall[/bold]", f"[bold]{metrics['overall']:.1%}[/bold]")

    console.print(table)

    # Also write JSON output per D-08
    import json as json_mod
    output_path = Path("outputs/eval_results.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json_mod.dumps(metrics, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    console.print(f"\n[dim]Results written to {output_path}[/dim]")
