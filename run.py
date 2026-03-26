"""Phonebot pipeline CLI entrypoint."""
import argparse
import sys
from pathlib import Path

from rich.console import Console

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


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Ensure output directory exists (Pitfall 4 prevention)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    console.print("[bold green]Phonebot pipeline starting...[/bold green]")
    console.print(f"Model: {args.model}")
    console.print(f"Recordings: {args.recordings_dir}")
    console.print(f"Output: {args.output}")
    # Phase 2+: pipeline execution goes here


if __name__ == "__main__":
    main()
