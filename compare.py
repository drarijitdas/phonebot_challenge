"""A/B model comparison script (Phase 5, AB-02).

Reads per-model result files from outputs/results_*.json, computes accuracy
and latency metrics, prints Rich comparison tables, and writes
outputs/comparison.json.

Usage:
    uv run python compare.py
"""
import glob
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from phonebot.evaluation.metrics import FIELDS, compute_metrics, load_ground_truth

console = Console()


_PROMPT_TO_PIPELINE: dict[str, str] = {
    "v1": "v1",
    "v2": "v1",        # GEPA-optimized prompt, still v1 pipeline
    "v2_ac": "v2-ac",  # actor-critic pipeline
}


def _label_from_payload(data: dict, path: str) -> str:
    """Build a descriptive label from result payload metadata.

    Combines pipeline variant and prompt version so the comparison table
    clearly shows *what configuration* produced each result, not just the
    model name.

    Example: 'v1 pipeline + v2 prompt (GEPA)'
    """
    prompt_ver = data.get("prompt_version", "")
    pipeline = _PROMPT_TO_PIPELINE.get(prompt_ver, "v1")
    parts = [f"{pipeline} pipeline", f"{prompt_ver} prompt"]
    if prompt_ver.startswith("v2") and prompt_ver != "v2_ac":
        parts.append("(GEPA)")
    return " + ".join(parts)


def load_result_files(pattern: str = "outputs/results_*.json") -> list[dict]:
    """Load all result JSON files matching the glob pattern.

    Returns list of parsed JSON payloads sorted by file name.
    Each payload gets a '_label' key derived from its filename (unique per file).
    """
    paths = sorted(glob.glob(pattern))
    payloads = []
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        data["_source_path"] = p
        data["_label"] = _label_from_payload(data, p)
        payloads.append(data)
    return payloads


def build_comparison(
    payloads: list[dict],
    ground_truth: dict,
) -> dict:
    """Compute per-model metrics and per-recording diffs.

    Args:
        payloads: List of result file payloads (each has "model", "results",
                  "duration_seconds", "avg_latency_per_recording", etc.)
        ground_truth: Dict keyed by recording id -> expected dict.

    Returns:
        {
            "models": {
                "claude-sonnet-4-6": {"per_field": {...}, "overall": 0.82, "avg_latency": 1.5},
                "ollama_llama3.2_3b": {"per_field": {...}, "overall": 0.65, "avg_latency": 3.2},
            },
            "diffs": [
                {"recording": "call_03", "field": "first_name",
                 "model_values": {"claude-sonnet-4-6": "Max", "ollama_llama3.2_3b": "Macs"},
                 "ground_truth": "Max"},
                ...
            ],
            "winner": {"model": "claude-sonnet-4-6", "overall_pct": 82, "is_tie": False},
        }
    """
    model_metrics: dict[str, dict] = {}
    model_per_recording: dict[str, dict[str, dict]] = {}

    for payload in payloads:
        label = payload.get("_label") or payload["model"]
        metrics = compute_metrics(payload["results"], ground_truth)
        avg_latency = payload.get("avg_latency_per_recording", 0)
        model_metrics[label] = {
            "per_field": metrics["per_field"],
            "overall": metrics["overall"],
            "avg_latency": avg_latency,
        }
        # Index per-recording results by recording_id -> field values dict
        per_rec: dict[str, dict] = {}
        for r in payload["results"]:
            info = r.get("caller_info") or {}
            per_rec[r["id"]] = info
        model_per_recording[label] = per_rec

    # Build per-recording diffs (D-14): show where any two models disagree
    model_names = list(model_metrics.keys())
    all_recording_ids: set[str] = set()
    for payload in payloads:
        for r in payload["results"]:
            all_recording_ids.add(r["id"])

    diffs = []
    for rec_id in sorted(all_recording_ids):
        for field in FIELDS:
            values: dict[str, object] = {}
            for mn in model_names:
                info = model_per_recording.get(mn, {}).get(rec_id, {})
                values[mn] = info.get(field)

            # Check if any two models disagree on this field
            unique_values = set(str(v) for v in values.values())
            if len(unique_values) > 1:
                gt_val = ground_truth.get(rec_id, {}).get(field)
                diffs.append(
                    {
                        "recording": rec_id,
                        "field": field,
                        "model_values": values,
                        "ground_truth": gt_val,
                    }
                )

    # Determine winner (D-15)
    best_overall = max(model_metrics.values(), key=lambda m: m["overall"])
    best_pct = round(best_overall["overall"] * 100)
    winners = [
        mn
        for mn, m in model_metrics.items()
        if round(m["overall"] * 100) == best_pct
    ]
    is_tie = len(winners) > 1

    winner_info = {
        "model": winners[0] if not is_tie else " and ".join(winners),
        "overall_pct": best_pct,
        "is_tie": is_tie,
    }

    return {
        "models": model_metrics,
        "diffs": diffs,
        "winner": winner_info,
    }


def print_comparison(comparison: dict, con: Console) -> None:
    """Print Rich comparison tables per UI-SPEC contract.

    Table 1: Model Comparison -- Per-Field Accuracy (per UI-SPEC Table 1)
    Table 2: Per-Recording Differences (per UI-SPEC Table 2)
    Winner/Tie summary line (per UI-SPEC Copywriting Contract)
    """
    models = comparison["models"]
    model_names = list(models.keys())
    diffs = comparison["diffs"]
    winner = comparison["winner"]

    con.print(f"\n[bold]Comparing {len(model_names)} model result files...[/bold]\n")

    # Table 1: Per-field accuracy (UI-SPEC Table 1)
    table = Table(title="Model Comparison -- Per-Field Accuracy")
    table.add_column("Field", style="cyan")
    for mn in model_names:
        table.add_column(mn)
    table.add_column("Avg Latency (s/rec)")

    for field in FIELDS:
        row: list[str] = [field]
        values = {mn: models[mn]["per_field"][field] for mn in model_names}
        best_val = max(values.values())
        for mn in model_names:
            pct = f"{values[mn]:.0%}"
            if values[mn] == best_val:
                row.append(f"[green bold]{pct}[/green bold]")
            else:
                row.append(pct)
        row.append("")  # latency only on Overall row
        table.add_row(*row)

    # Overall row
    overall_row: list[str] = ["[bold]Overall[/bold]"]
    overall_values = {mn: models[mn]["overall"] for mn in model_names}
    best_overall = max(overall_values.values())
    for mn in model_names:
        pct = f"{overall_values[mn]:.0%}"
        if overall_values[mn] == best_overall:
            overall_row.append(f"[green bold]{pct}[/green bold]")
        else:
            overall_row.append(pct)
    # Latency for each model on the overall row (slash-separated)
    latencies = [f"{models[mn]['avg_latency']:.2f}s" for mn in model_names]
    overall_row.append(" / ".join(latencies))
    table.add_row(*overall_row)

    con.print(table)

    # Table 2: Per-recording differences (UI-SPEC Table 2)
    con.print()
    if diffs:
        diff_table = Table(title="Per-Recording Differences")
        diff_table.add_column("Recording", style="cyan")
        diff_table.add_column("Field", style="cyan")
        for mn in model_names:
            diff_table.add_column(mn)
        diff_table.add_column("Ground Truth", style="cyan")

        for d in diffs:
            row = [d["recording"], d["field"]]
            for mn in model_names:
                val = d["model_values"].get(mn)
                row.append("[dim]null[/dim]" if val is None else str(val))
            gt_val = d["ground_truth"]
            row.append(
                "[dim]null[/dim]"
                if gt_val is None
                else str(gt_val)
                if not isinstance(gt_val, list)
                else " | ".join(str(v) for v in gt_val)
            )
            diff_table.add_row(*row)
        con.print(diff_table)
    else:
        con.print("[green]Models agreed on all recordings.[/green]")

    # Winner summary (UI-SPEC Copywriting Contract)
    con.print()
    if winner["is_tie"]:
        con.print(
            f"[bold]Tie: {winner['model']} both achieved {winner['overall_pct']}% overall accuracy[/bold]"
        )
    else:
        con.print(
            f"[bold green]Winner: {winner['model']} ({winner['overall_pct']}% overall accuracy)[/bold green]"
        )


def main() -> None:
    """Entry point: load results, compare, print, write JSON."""
    payloads = load_result_files()
    if len(payloads) < 2:
        console.print(
            "[red]Need at least 2 result files in outputs/ to compare. "
            "Run: uv run python run.py --model <name>[/red]"
        )
        sys.exit(1)

    gt = load_ground_truth(Path("data/ground_truth.json"))
    comparison = build_comparison(payloads, gt)
    print_comparison(comparison, console)

    # Write comparison.json (D-11: dual output)
    output_path = Path("outputs/comparison.json")
    output_path.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    console.print(f"\nComparison written to {output_path}")


if __name__ == "__main__":
    main()
