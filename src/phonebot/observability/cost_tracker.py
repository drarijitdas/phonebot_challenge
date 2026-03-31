"""Cost tracking for LLM API usage.

Records token counts per invocation, applies pricing tables, and reports
per-recording and per-node cost breakdowns. Integrates with LangChain's
response_metadata which includes input_tokens and output_tokens.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console
from rich.table import Table


# Pricing per 1M tokens (USD) — update when models change
PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-5-20250514": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
    # Ollama models are local — zero API cost
    "ollama": {"input": 0.0, "output": 0.0},
}


@dataclass
class TokenRecord:
    """Single LLM invocation cost record."""

    recording_id: str
    node: str  # e.g. "extract", "critic_evaluate", "actor_refine"
    model: str
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    timestamp: float = field(default_factory=time.time)

    @property
    def cost_usd(self) -> float:
        """Compute dollar cost for this invocation."""
        pricing = _resolve_pricing(self.model)
        return (
            self.input_tokens * pricing["input"] / 1_000_000
            + self.output_tokens * pricing["output"] / 1_000_000
        )


def _resolve_pricing(model: str) -> dict[str, float]:
    """Look up pricing for a model, falling back to ollama (free) for local models."""
    if model in PRICING:
        return PRICING[model]
    if model.startswith("ollama"):
        return PRICING["ollama"]
    # Unknown model — use Sonnet pricing as conservative default
    return PRICING["claude-sonnet-4-6"]


class CostTracker:
    """Accumulates token usage records across a pipeline run.

    Usage:
        tracker = CostTracker()
        tracker.record("call_01", "extract", "claude-sonnet-4-6", 1200, 350, 1.8)
        tracker.record("call_01", "critic", "claude-sonnet-4-6", 800, 200, 1.2)
        tracker.print_summary()
    """

    def __init__(self) -> None:
        self._records: list[TokenRecord] = []

    @property
    def records(self) -> tuple[TokenRecord, ...]:
        """Immutable view of recorded token usage."""
        return tuple(self._records)

    def record(
        self,
        recording_id: str,
        node: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_seconds: float,
    ) -> TokenRecord:
        """Record a single LLM invocation."""
        rec = TokenRecord(
            recording_id=recording_id,
            node=node,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_seconds=latency_seconds,
        )
        self._records.append(rec)
        return rec

    def record_from_response_metadata(
        self,
        recording_id: str,
        node: str,
        model: str,
        metadata: dict[str, Any],
        latency_seconds: float,
    ) -> TokenRecord:
        """Record from LangChain response_metadata dict.

        LangChain's ChatAnthropic populates response_metadata with:
          - input_tokens (or usage.input_tokens)
          - output_tokens (or usage.output_tokens)
        """
        usage = metadata.get("usage", metadata)
        return self.record(
            recording_id=recording_id,
            node=node,
            model=model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            latency_seconds=latency_seconds,
        )

    @property
    def total_cost(self) -> float:
        return sum(r.cost_usd for r in self._records)

    @property
    def total_input_tokens(self) -> int:
        return sum(r.input_tokens for r in self._records)

    @property
    def total_output_tokens(self) -> int:
        return sum(r.output_tokens for r in self._records)

    def _sum_cost_by(self, attr: str) -> dict[str, float]:
        """Sum cost grouped by a record attribute."""
        costs: dict[str, float] = {}
        for r in self._records:
            key = getattr(r, attr)
            costs[key] = costs.get(key, 0.0) + r.cost_usd
        return costs

    def cost_by_recording(self) -> dict[str, float]:
        """Sum cost per recording_id."""
        return self._sum_cost_by("recording_id")

    def cost_by_node(self) -> dict[str, float]:
        """Sum cost per pipeline node."""
        return self._sum_cost_by("node")

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "total_cost_usd": round(self.total_cost, 6),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "cost_by_recording": {
                k: round(v, 6) for k, v in self.cost_by_recording().items()
            },
            "cost_by_node": {
                k: round(v, 6) for k, v in self.cost_by_node().items()
            },
            "num_invocations": len(self._records),
        }

    def print_summary(self, console: Console | None = None) -> None:
        """Print Rich cost summary table."""
        console = console or Console()

        # Overall summary
        table = Table(title="Cost Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")

        total = self.total_cost
        table.add_row("Total Cost", f"${total:.4f}")
        table.add_row("Input Tokens", f"{self.total_input_tokens:,}")
        table.add_row("Output Tokens", f"{self.total_output_tokens:,}")
        table.add_row("LLM Invocations", str(len(self._records)))
        n_recordings = len(set(r.recording_id for r in self._records))
        if n_recordings:
            table.add_row("Avg Cost/Recording", f"${total / n_recordings:.4f}")
        console.print(table)

        by_node = self.cost_by_node()
        if by_node:
            node_table = Table(title="Cost by Pipeline Node")
            node_table.add_column("Node", style="cyan")
            node_table.add_column("Cost", style="green", justify="right")
            node_table.add_column("% of Total", justify="right")
            for node, cost in sorted(by_node.items(), key=lambda x: -x[1]):
                pct = (cost / total * 100) if total else 0
                node_table.add_row(node, f"${cost:.4f}", f"{pct:.1f}%")
            console.print(node_table)
