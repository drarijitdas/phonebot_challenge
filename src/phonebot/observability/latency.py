"""Latency monitoring with SLA budget tracking.

Defines per-node SLA budgets and records actual durations. Reports violations
after each pipeline run, enabling latency regression detection.
"""
from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator

from rich.console import Console
from rich.table import Table


# SLA budgets in seconds
DEFAULT_BUDGETS: dict[str, float] = {
    "end_to_end": 30.0,       # Max seconds per recording total
    "transcribe": 5.0,        # Transcript cache load (should be <1s)
    "extract": 10.0,          # Single LLM extraction call
    "validate": 1.0,          # Pydantic validation
    "critic_evaluate": 10.0,  # Critic LLM call (v2)
    "actor_refine": 10.0,     # Actor refinement LLM call (v2)
    "retrieve_examples": 2.0, # Few-shot retrieval (Gap 1A)
    "preprocess": 1.0,        # Transcript preprocessing
    "postprocess": 2.0,       # Post-processing + knowledge grounding
    "classify": 0.5,          # Difficulty classification
}


@dataclass
class LatencyRecord:
    """Single node execution timing."""

    recording_id: str
    node: str
    duration_seconds: float
    budget_seconds: float | None = None
    timestamp: float = field(default_factory=time.time)

    @property
    def within_budget(self) -> bool:
        if self.budget_seconds is None:
            return True
        return self.duration_seconds <= self.budget_seconds

    @property
    def overage_pct(self) -> float | None:
        """Percentage over budget, or None if within budget."""
        if self.budget_seconds is None or self.within_budget:
            return None
        return ((self.duration_seconds - self.budget_seconds) / self.budget_seconds) * 100


class LatencyMonitor:
    """Records per-node latencies and checks against SLA budgets.

    Usage:
        monitor = LatencyMonitor()

        with monitor.track("call_01", "extract"):
            result = await llm.ainvoke(prompt)

        monitor.print_summary()
    """

    def __init__(self, budgets: dict[str, float] | None = None) -> None:
        self.budgets = budgets or DEFAULT_BUDGETS
        self._records: list[LatencyRecord] = []

    @property
    def records(self) -> tuple[LatencyRecord, ...]:
        """Immutable view of recorded latency measurements."""
        return tuple(self._records)

    @contextmanager
    def track(self, recording_id: str, node: str) -> Generator[None, None, None]:
        """Context manager to time a node execution."""
        start = time.monotonic()
        yield
        duration = time.monotonic() - start
        self.record(recording_id, node, duration)

    def record(self, recording_id: str, node: str, duration_seconds: float) -> LatencyRecord:
        """Manually record a latency measurement."""
        rec = LatencyRecord(
            recording_id=recording_id,
            node=node,
            duration_seconds=round(duration_seconds, 3),
            budget_seconds=self.budgets.get(node),
        )
        self._records.append(rec)
        return rec

    @property
    def violations(self) -> list[LatencyRecord]:
        """All records that exceeded their SLA budget."""
        return [r for r in self._records if not r.within_budget]

    def avg_by_node(self) -> dict[str, float]:
        """Average duration per node across all recordings."""
        sums: dict[str, float] = {}
        counts: dict[str, int] = {}
        for r in self._records:
            sums[r.node] = sums.get(r.node, 0.0) + r.duration_seconds
            counts[r.node] = counts.get(r.node, 0) + 1
        return {node: sums[node] / counts[node] for node in sums}

    def p95_by_node(self) -> dict[str, float]:
        """95th percentile duration per node."""
        by_node: dict[str, list[float]] = defaultdict(list)
        for r in self._records:
            by_node[r.node].append(r.duration_seconds)

        result = {}
        for node, durations in by_node.items():
            durations.sort()
            idx = max(0, int(len(durations) * 0.95) - 1)
            result[node] = durations[idx]
        return result

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "avg_by_node": {k: round(v, 3) for k, v in self.avg_by_node().items()},
            "p95_by_node": {k: round(v, 3) for k, v in self.p95_by_node().items()},
            "violations": [
                {
                    "recording_id": r.recording_id,
                    "node": r.node,
                    "duration": r.duration_seconds,
                    "budget": r.budget_seconds,
                    "overage_pct": round(r.overage_pct, 1) if r.overage_pct else None,
                }
                for r in self.violations
            ],
            "total_records": len(self._records),
        }

    def print_summary(self, console: Console | None = None) -> None:
        """Print Rich latency summary with SLA violations."""
        console = console or Console()

        avg = self.avg_by_node()
        p95 = self.p95_by_node()

        table = Table(title="Latency Summary (per node)")
        table.add_column("Node", style="cyan")
        table.add_column("Avg (s)", justify="right")
        table.add_column("P95 (s)", justify="right")
        table.add_column("Budget (s)", justify="right")
        table.add_column("Status", justify="center")

        for node in sorted(avg.keys()):
            budget = self.budgets.get(node)
            budget_str = f"{budget:.1f}" if budget else "—"
            p95_val = p95.get(node, 0)
            status = "✓" if (budget is None or p95_val <= budget) else "[red]✗ VIOLATION[/red]"
            table.add_row(
                node,
                f"{avg[node]:.3f}",
                f"{p95_val:.3f}",
                budget_str,
                status,
            )

        console.print(table)

        violations = self.violations
        if violations:
            console.print(f"\n[yellow]⚠ {len(violations)} SLA violation(s) detected[/yellow]")
            for v in violations[:5]:  # Show first 5
                console.print(
                    f"  {v.recording_id}/{v.node}: "
                    f"{v.duration_seconds:.2f}s (budget: {v.budget_seconds:.1f}s, "
                    f"+{v.overage_pct:.0f}%)"
                )
