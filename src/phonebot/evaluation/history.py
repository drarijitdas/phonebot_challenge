"""Metrics history tracking across pipeline runs.

Appends each run's metrics to a JSONL file, enabling trend analysis and
regression detection over time. Each record captures: timestamp, model,
prompt version, pipeline version, per-field accuracy, overall accuracy,
and git commit hash for reproducibility.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from phonebot.utils import get_git_commit

HISTORY_PATH = Path("outputs/metrics_history.jsonl")


def record_run(
    metrics: dict[str, Any],
    model: str,
    prompt_version: str,
    pipeline: str,
    extra: dict[str, Any] | None = None,
    history_path: Path = HISTORY_PATH,
) -> dict[str, Any]:
    """Append a metrics record to the history file.

    Args:
        metrics: Output from compute_metrics() with per_field and overall keys.
        model: Model identifier used for this run.
        prompt_version: Prompt version tag (v1, v2, etc.).
        pipeline: Pipeline version (v1, v2, v3).
        extra: Optional additional metadata (cost, latency, etc.).
        history_path: Path to JSONL history file.

    Returns:
        The record dict that was written.
    """
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "prompt_version": prompt_version,
        "pipeline": pipeline,
        "per_field": metrics.get("per_field", {}),
        "overall": metrics.get("overall", 0.0),
        "git_commit": get_git_commit(),
    }
    if extra:
        record["extra"] = extra

    history_path.parent.mkdir(parents=True, exist_ok=True)
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    return record


def load_history(history_path: Path = HISTORY_PATH) -> list[dict[str, Any]]:
    """Load all history records from the JSONL file."""
    try:
        f = open(history_path, encoding="utf-8")
    except FileNotFoundError:
        return []
    records = []
    with f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def print_history(
    n: int = 10,
    history_path: Path = HISTORY_PATH,
    console: Console | None = None,
) -> None:
    """Print last N runs as a Rich table.

    Args:
        n: Number of recent runs to display.
        history_path: Path to JSONL history file.
        console: Rich console instance.
    """
    console = console or Console()
    records = load_history(history_path)

    if not records:
        console.print("[dim]No metrics history found.[/dim]")
        return

    recent = records[-n:]

    table = Table(title=f"Metrics History (last {len(recent)} runs)")
    table.add_column("Timestamp", style="dim")
    table.add_column("Model", style="cyan")
    table.add_column("Pipeline")
    table.add_column("Prompt")
    table.add_column("first_name", justify="right")
    table.add_column("last_name", justify="right")
    table.add_column("email", justify="right")
    table.add_column("phone", justify="right")
    table.add_column("Overall", justify="right", style="bold")
    table.add_column("Commit", style="dim")

    for rec in recent:
        pf = rec.get("per_field", {})
        ts = rec.get("timestamp", "")[:19]  # Trim to seconds
        table.add_row(
            ts,
            rec.get("model", "?"),
            rec.get("pipeline", "?"),
            rec.get("prompt_version", "?"),
            f"{pf.get('first_name', 0):.1%}",
            f"{pf.get('last_name', 0):.1%}",
            f"{pf.get('email', 0):.1%}",
            f"{pf.get('phone_number', 0):.1%}",
            f"{rec.get('overall', 0):.1%}",
            rec.get("git_commit", "—"),
        )

    console.print(table)
