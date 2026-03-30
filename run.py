"""Phonebot pipeline CLI entrypoint."""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # Load .env before any API key checks

from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

from phonebot.models.model_registry import model_alias  # noqa: E402

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phonebot",
        description="Extract caller info from German phone bot recordings.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="LLM model identifier for extraction",
    )
    parser.add_argument(
        "--recordings-dir",
        default="data/recordings/",
        help="Directory containing WAV recording files",
    )
    parser.add_argument(
        "--prompt-version",
        default="v1",
        help="Prompt version tag attached to every Phoenix trace",
    )
    parser.add_argument(
        "--pipeline",
        default="v1",
        choices=["v1", "v2"],
        help="Pipeline version: v1 (simple extract) or v2 (actor-critic)",
    )
    parser.add_argument(
        "--max-ac-iterations",
        type=int,
        default=3,
        help="Max actor-critic iterations (v2 pipeline only)",
    )
    parser.add_argument(
        "--final",
        action="store_true",
        default=False,
        help=(
            "Final submission run: uses best model (claude-sonnet-4-6) + optimized prompt (v2), "
            "writes outputs/results.json, outputs/scores.json, outputs/comparison.json"
        ),
    )
    return parser


# ---------------------------------------------------------------------------
# Helper functions for --final output payloads (testable standalone)
# ---------------------------------------------------------------------------


def build_final_results_payload(
    results: list[dict],
    model: str,
    prompt_version: str,
    duration: float,
) -> dict:
    """Build the results.json payload for final submission (D-04).

    Includes flagged_fields per result record for D-03 compliance.
    """
    return {
        "model": model,
        "prompt_version": prompt_version,
        "total_recordings": len(results),
        "duration_seconds": round(duration, 2),
        "avg_latency_per_recording": round(duration / len(results), 2) if results else 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }


def build_scores_payload(metrics: dict, model: str, prompt_version: str) -> dict:
    """Build the scores.json payload (D-04).

    Returns model, prompt_version, per_field accuracy, overall accuracy, and timestamp.
    """
    return {
        "model": model,
        "prompt_version": prompt_version,
        "per_field": metrics["per_field"],
        "overall": metrics["overall"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_comparison_payload(
    v2_metrics: dict,
    v1_metrics: dict | None,
    results: list[dict],
    model: str,
) -> dict:
    """Build the comparison.json payload (D-04): v1 vs v2 delta + confidence distribution.

    Args:
        v2_metrics: compute_metrics() output for v2 results.
        v1_metrics: compute_metrics() output for v1 baseline; None if unavailable.
        results: Pipeline results list (each has caller_info with confidence dict).
        model: Model name string.

    Returns:
        Dict with prompt_comparison, confidence_distribution, model, and timestamp.
    """
    from phonebot.evaluation.metrics import FIELDS

    if v1_metrics is not None:
        prompt_comparison = {
            "v1": v1_metrics["per_field"],
            "v2": v2_metrics["per_field"],
            "delta": {
                field: v2_metrics["per_field"][field] - v1_metrics["per_field"][field]
                for field in FIELDS
            },
            "overall_v1": v1_metrics["overall"],
            "overall_v2": v2_metrics["overall"],
            "overall_delta": v2_metrics["overall"] - v1_metrics["overall"],
        }
    else:
        prompt_comparison = {
            "v1": None,
            "v2": v2_metrics["per_field"],
            "delta": None,
            "overall_v1": None,
            "overall_v2": v2_metrics["overall"],
            "overall_delta": None,
        }

    # Compute confidence distribution (D-04)
    from phonebot.pipeline.extract import CONFIDENCE_THRESHOLD

    n_high = n_low = n_empty = 0
    total_fields = 0
    for r in results:
        ci = r.get("caller_info") or {}
        conf = ci.get("confidence") or {}
        extracted_fields = [f for f in FIELDS if ci.get(f) is not None]
        total_fields += len(extracted_fields)
        if not conf:
            n_empty += len(extracted_fields)
        else:
            for f in extracted_fields:
                score = conf.get(f)
                if score is None:
                    n_empty += 1
                elif score >= CONFIDENCE_THRESHOLD:
                    n_high += 1
                else:
                    n_low += 1

    return {
        "prompt_comparison": prompt_comparison,
        "model": model,
        "confidence_distribution": {
            "high_confidence": n_high,
            "low_confidence": n_low,
            "no_confidence": n_empty,
            "total_fields": total_fields,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # --final mode: lock to best model and optimized prompt
    if args.final:
        args.model = "claude-sonnet-4-6"
        args.prompt_version = "v2"
        console.print("[bold yellow]FINAL SUBMISSION RUN[/bold yellow]")
        console.print("Model: claude-sonnet-4-6 (locked)")
        console.print("Prompt: extraction_v2.json (optimized)")

    # Validate model name early — fail fast with clean error before any heavy init
    from phonebot.models.model_registry import get_model

    try:
        get_model(args.model)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    # Compute model-specific output path (D-10: results_{alias}.json)
    alias = model_alias(args.model)
    if args.pipeline == "v2":
        alias = f"{alias}_ac"
    output_path = Path(f"outputs/results_{alias}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize tracing BEFORE pipeline import (RESEARCH Pitfall 2 — instrumentation
    # must be registered before LangChain modules are imported/executed).
    from phonebot.observability import init_tracing, shutdown_tracing

    phoenix_url = init_tracing()

    project_name = os.getenv("PHOENIX_PROJECT", "phonebot-extraction")

    console.print("[bold green]Phonebot pipeline starting...[/bold green]")
    console.print(f"Model: {args.model}")
    console.print(f"Pipeline: {args.pipeline}" + (" (actor-critic)" if args.pipeline == "v2" else ""))
    console.print(f"Prompt version: {args.prompt_version}")
    console.print(f"Recordings: {args.recordings_dir}")
    console.print(f"Output: outputs/results_{alias}.json")
    console.print(f"[green]Tracing initialized -- project: {project_name}[/green]")

    # Load prompt version file (needed for --final to use v2 prompt)
    # Must happen BEFORE the pipeline import so _CALLER_INFO_MODEL is set
    prompt_file = Path(f"src/phonebot/prompts/extraction_{args.prompt_version}.json")
    if prompt_file.exists():
        from phonebot.prompts import build_caller_info_model
        from phonebot.pipeline.extract import set_caller_info_model
        caller_model = build_caller_info_model(prompt_file)
        set_caller_info_model(caller_model)
        console.print(f"Loaded prompt: {prompt_file}")

    # Discover recording IDs from cached transcripts
    transcript_dir = Path("data/transcripts")
    recording_ids = sorted(p.stem for p in transcript_dir.glob("call_*.json"))

    if not recording_ids:
        console.print("[red]No transcripts found in data/transcripts/. Run transcription first.[/red]")
        sys.exit(1)

    console.print(f"\n[bold]Extracting from {len(recording_ids)} recordings...[/bold]")

    # Run extraction pipeline (D-09: one graph invocation per recording, concurrent)
    # Lazy import here — after init_tracing() — ensures OTEL patches are applied first.
    t0 = time.monotonic()
    if args.pipeline == "v2":
        from phonebot.pipeline.extract_v2 import run_pipeline_v2

        results = await run_pipeline_v2(
            recording_ids,
            model_name=args.model,
            prompt_version=args.prompt_version,
            max_ac_iterations=args.max_ac_iterations,
        )
    else:
        from phonebot.pipeline.extract import run_pipeline

        results = await run_pipeline(
            recording_ids,
            model_name=args.model,
            prompt_version=args.prompt_version,
        )
    duration = time.monotonic() - t0

    console.print(f"[green]Extraction complete in {duration:.1f}s[/green]")

    # Write results_{alias}.json (D-10, D-12, D-13)
    payload = {
        "model": args.model,
        "prompt_version": args.prompt_version,
        "total_recordings": len(results),
        "duration_seconds": round(duration, 2),
        "avg_latency_per_recording": round(duration / len(results), 2) if results else 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"Results written to {output_path}")

    # Auto-evaluate (D-13)
    from phonebot.evaluation.metrics import compute_metrics, load_ground_truth

    gt = load_ground_truth(Path("data/ground_truth.json"))
    metrics = compute_metrics(results, gt)

    # Print Rich accuracy table
    table = Table(title="Per-Field Accuracy")
    table.add_column("Field", style="cyan")
    table.add_column("Accuracy", style="green")
    for field, acc in metrics["per_field"].items():
        table.add_row(field, f"{acc:.0%}")
    table.add_row("[bold]Overall[/bold]", f"[bold]{metrics['overall']:.0%}[/bold]")
    console.print(table)

    # --final mode: write submission output files and print summary
    if args.final:
        from phonebot.evaluation.metrics import FIELDS

        # Write outputs/results.json (canonical final output per D-04)
        final_results_path = Path("outputs/results.json")
        final_results_path.parent.mkdir(parents=True, exist_ok=True)
        final_payload = build_final_results_payload(results, args.model, args.prompt_version, duration)
        final_results_path.write_text(
            json.dumps(final_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        console.print(f"[green]Final results written to {final_results_path}[/green]")

        # Write outputs/scores.json (D-04)
        scores_payload = build_scores_payload(metrics, args.model, args.prompt_version)
        scores_path = Path("outputs/scores.json")
        scores_path.write_text(
            json.dumps(scores_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        console.print(f"[green]Scores written to {scores_path}[/green]")

        # Build comparison.json (D-04): v1 vs v2 + confidence distribution
        v1_results_path = Path("outputs/results_claude-sonnet-4-6.json")
        v1_metrics = None
        if v1_results_path.exists():
            v1_data = json.loads(v1_results_path.read_text(encoding="utf-8"))
            # Only use v1 baseline if it was run with v1 prompt
            if v1_data.get("prompt_version") == "v1":
                v1_metrics = compute_metrics(v1_data["results"], gt)
            else:
                console.print(
                    "[yellow]Warning: results_claude-sonnet-4-6.json is not a v1 run — skipping prompt delta[/yellow]"
                )
        else:
            console.print(
                "[yellow]Warning: v1 results not found at outputs/results_claude-sonnet-4-6.json — skipping prompt delta[/yellow]"
            )

        comparison_payload = build_comparison_payload(metrics, v1_metrics, results, args.model)
        comparison_path = Path("outputs/comparison.json")
        comparison_path.write_text(
            json.dumps(comparison_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        console.print(f"[green]Comparison written to {comparison_path}[/green]")

        # Print console summary table (D-05)
        summary_table = Table(title="Final Submission Summary")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")

        summary_table.add_row("Model", args.model)
        summary_table.add_row("Prompt Version", args.prompt_version)
        summary_table.add_row("Overall Accuracy", f"{metrics['overall']:.0%}")
        for field in FIELDS:
            summary_table.add_row(f"  {field}", f"{metrics['per_field'][field]:.0%}")

        # Count total flagged fields across all results
        total_flagged = sum(len(r.get("flagged_fields", [])) for r in results)
        summary_table.add_row("Flagged Fields", str(total_flagged))

        prompt_comparison = comparison_payload["prompt_comparison"]
        if prompt_comparison.get("overall_delta") is not None:
            delta = prompt_comparison["overall_delta"]
            delta_str = f"{delta:+.0%}"
            summary_table.add_row("v1 -> v2 Delta", delta_str)

        console.print(summary_table)

        # Print per-flagged-field warnings (D-03)
        for r in results:
            flagged = r.get("flagged_fields", [])
            if flagged:
                for f in flagged:
                    ci = r.get("caller_info") or {}
                    score = (ci.get("confidence") or {}).get(f, "N/A")
                    console.print(
                        f"[yellow]Warning: {r['id']} field '{f}' flagged "
                        f"(confidence={score})[/yellow]"
                    )

    # Print trace count and Phoenix URL (D-03, D-14, UI-SPEC step 5)
    console.print(f"\n[green]{len(results)} traces sent to Phoenix[/green]")
    console.print(f"[green]Phoenix UI: {phoenix_url}[/green]")

    # Flush all spans before process exit (RESEARCH Open Question 3)
    shutdown_tracing()


if __name__ == "__main__":
    asyncio.run(main())
