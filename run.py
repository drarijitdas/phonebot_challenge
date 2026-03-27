"""Phonebot pipeline CLI entrypoint."""
import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

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
        "--output",
        default="outputs/results.json",
        help="Path for extraction results JSON output",
    )
    return parser


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Ensure output directory exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    console.print("[bold green]Phonebot pipeline starting...[/bold green]")
    console.print(f"Model: {args.model}")
    console.print(f"Recordings: {args.recordings_dir}")
    console.print(f"Output: {args.output}")

    # Discover recording IDs from cached transcripts
    transcript_dir = Path("data/transcripts")
    recording_ids = sorted(p.stem for p in transcript_dir.glob("call_*.json"))

    if not recording_ids:
        console.print("[red]No transcripts found in data/transcripts/. Run transcription first.[/red]")
        sys.exit(1)

    console.print(f"\n[bold]Extracting from {len(recording_ids)} recordings...[/bold]")

    # Run extraction pipeline (D-09: one graph invocation per recording, concurrent)
    from phonebot.pipeline.extract import run_pipeline

    t0 = time.monotonic()
    results = await run_pipeline(recording_ids, model_name=args.model)
    duration = time.monotonic() - t0

    console.print(f"[green]Extraction complete in {duration:.1f}s[/green]")

    # Write results.json (D-12)
    payload = {
        "model": args.model,
        "total_recordings": len(results),
        "duration_seconds": round(duration, 2),
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


if __name__ == "__main__":
    asyncio.run(main())
