"""Phonebot pipeline CLI entrypoint."""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from phonebot.models.model_registry import model_alias

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
    return parser


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Validate model name early — fail fast with clean error before any heavy init
    from phonebot.models.model_registry import get_model

    try:
        get_model(args.model)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    # Compute model-specific output path (D-10: results_{alias}.json)
    alias = model_alias(args.model)
    output_path = Path(f"outputs/results_{alias}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize tracing BEFORE pipeline import (RESEARCH Pitfall 2 — instrumentation
    # must be registered before LangChain modules are imported/executed).
    from phonebot.observability import init_tracing, shutdown_tracing

    phoenix_url = init_tracing()

    project_name = os.getenv("PHOENIX_PROJECT", "phonebot-extraction")

    console.print("[bold green]Phonebot pipeline starting...[/bold green]")
    console.print(f"Model: {args.model}")
    console.print(f"Prompt version: {args.prompt_version}")
    console.print(f"Recordings: {args.recordings_dir}")
    console.print(f"Output: outputs/results_{alias}.json")
    console.print(f"[green]Tracing initialized -- project: {project_name}[/green]")

    # Discover recording IDs from cached transcripts
    transcript_dir = Path("data/transcripts")
    recording_ids = sorted(p.stem for p in transcript_dir.glob("call_*.json"))

    if not recording_ids:
        console.print("[red]No transcripts found in data/transcripts/. Run transcription first.[/red]")
        sys.exit(1)

    console.print(f"\n[bold]Extracting from {len(recording_ids)} recordings...[/bold]")

    # Run extraction pipeline (D-09: one graph invocation per recording, concurrent)
    # Lazy import here — after init_tracing() — ensures OTEL patches are applied first.
    from phonebot.pipeline.extract import run_pipeline

    t0 = time.monotonic()
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

    # Print trace count and Phoenix URL (D-03, D-14, UI-SPEC step 5)
    console.print(f"\n[green]{len(results)} traces sent to Phoenix[/green]")
    console.print(f"[green]Phoenix UI: {phoenix_url}[/green]")

    # Flush all spans before process exit (RESEARCH Open Question 3)
    shutdown_tracing()


if __name__ == "__main__":
    asyncio.run(main())
