"""Prompt version registry for reproducibility.

Tracks each prompt's content via SHA256 hash, enabling exact reproducibility:
"which prompt content produced 84% accuracy?" Each registration captures
the content hash, timestamp, git commit, and associated accuracy metrics.

This solves a common production issue: prompt filenames stay the same but
contents change. The registry tracks content hashes for exact versioning.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from phonebot.utils import get_git_commit, write_json

REGISTRY_PATH = Path("outputs/prompt_registry.json")


def _hash_content(content: str) -> str:
    """SHA256 hash of prompt content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _load_registry(registry_path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Load existing registry or create empty one."""
    try:
        return json.loads(registry_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"prompts": {}}


def register_prompt(
    prompt_path: Path,
    prompt_version: str,
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, Any]:
    """Register a prompt file with its content hash.

    Args:
        prompt_path: Path to the prompt JSON file.
        prompt_version: Version label (v1, v2, etc.).
        registry_path: Path to the registry JSON file.

    Returns:
        Registration record dict.
    """
    content = prompt_path.read_text(encoding="utf-8")
    content_hash = _hash_content(content)

    record = {
        "prompt_version": prompt_version,
        "file_path": str(prompt_path),
        "content_hash": content_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": get_git_commit(),
        "accuracy": None,  # Updated after run completes
    }

    registry = _load_registry(registry_path)
    registry["prompts"][content_hash] = record
    write_json(registry_path, registry)

    return record


def update_accuracy(
    content_hash: str,
    accuracy: dict[str, Any],
    registry_path: Path = REGISTRY_PATH,
) -> None:
    """Attach accuracy metrics to a registered prompt.

    Args:
        content_hash: The prompt's content hash from registration.
        accuracy: Metrics dict with per_field and overall keys.
        registry_path: Path to the registry JSON file.
    """
    registry = _load_registry(registry_path)
    if content_hash in registry["prompts"]:
        registry["prompts"][content_hash]["accuracy"] = accuracy
        write_json(registry_path, registry)


def get_prompt_history(
    registry_path: Path = REGISTRY_PATH,
) -> list[dict[str, Any]]:
    """Return all registered prompts sorted by timestamp.

    Returns:
        List of registration records, newest first.
    """
    registry = _load_registry(registry_path)
    records = list(registry.get("prompts", {}).values())
    records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return records


def print_prompt_history(
    registry_path: Path = REGISTRY_PATH,
    console: Console | None = None,
) -> None:
    """Print prompt version history as a Rich table."""
    console = console or Console()
    records = get_prompt_history(registry_path)

    if not records:
        console.print("[dim]No prompts registered yet.[/dim]")
        return

    table = Table(title="Prompt Version Registry")
    table.add_column("Hash", style="cyan")
    table.add_column("Version")
    table.add_column("Timestamp", style="dim")
    table.add_column("Git Commit", style="dim")
    table.add_column("Overall Acc", justify="right", style="bold")

    for rec in records:
        acc = rec.get("accuracy")
        overall_str = f"{acc['overall']:.1%}" if acc and "overall" in acc else "—"
        table.add_row(
            rec.get("content_hash", "?"),
            rec.get("prompt_version", "?"),
            rec.get("timestamp", "")[:19],
            rec.get("git_commit", "—"),
            overall_str,
        )

    console.print(table)
