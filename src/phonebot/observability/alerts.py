"""Quality alerting system for pipeline runs.

Threshold-based checks that run after every pipeline execution to detect
quality, cost, and latency degradation. In production, these would push
to PagerDuty/Slack; for the challenge, they print Rich warnings and log
via structlog.

Configurable thresholds:
  - Overall accuracy minimum
  - Per-field accuracy minimum
  - Cost per recording maximum
  - Latency per recording maximum
  - Escalation rate maximum
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rich.console import Console

from phonebot.observability.logging import get_logger


@dataclass
class AlertThresholds:
    """Configurable alert thresholds."""

    min_overall_accuracy: float = 0.80
    min_field_accuracy: float = 0.60
    max_cost_per_recording: float = 0.50  # USD
    max_latency_per_recording: float = 30.0  # seconds
    max_escalation_rate: float = 0.20  # 20%


@dataclass
class Alert:
    """A triggered quality alert."""

    severity: str  # "warning" or "critical"
    category: str  # "accuracy", "cost", "latency", "escalation"
    message: str
    actual_value: float
    threshold_value: float


def check_alerts(
    metrics: dict[str, Any] | None = None,
    cost_summary: dict[str, Any] | None = None,
    latency_summary: dict[str, Any] | None = None,
    escalation_count: int = 0,
    total_recordings: int = 0,
    thresholds: AlertThresholds | None = None,
) -> list[Alert]:
    """Run all alert checks against pipeline run results.

    Args:
        metrics: Output from compute_metrics() with per_field and overall.
        cost_summary: Output from CostTracker.to_dict().
        latency_summary: Output from LatencyMonitor.to_dict().
        escalation_count: Number of escalated recordings.
        total_recordings: Total recordings processed.
        thresholds: Alert thresholds (uses defaults if None).

    Returns:
        List of triggered alerts (empty if all checks pass).
    """
    t = thresholds or AlertThresholds()
    alerts: list[Alert] = []

    # Accuracy checks
    if metrics:
        overall = metrics.get("overall", 0)
        if overall < t.min_overall_accuracy:
            alerts.append(Alert(
                severity="critical",
                category="accuracy",
                message=f"Overall accuracy {overall:.1%} below minimum {t.min_overall_accuracy:.1%}",
                actual_value=overall,
                threshold_value=t.min_overall_accuracy,
            ))

        for field, acc in metrics.get("per_field", {}).items():
            if acc < t.min_field_accuracy:
                alerts.append(Alert(
                    severity="warning",
                    category="accuracy",
                    message=f"Field '{field}' accuracy {acc:.1%} below minimum {t.min_field_accuracy:.1%}",
                    actual_value=acc,
                    threshold_value=t.min_field_accuracy,
                ))

    # Cost checks
    if cost_summary and total_recordings > 0:
        total_cost = cost_summary.get("total_cost_usd", 0)
        cost_per_rec = total_cost / total_recordings
        if cost_per_rec > t.max_cost_per_recording:
            alerts.append(Alert(
                severity="warning",
                category="cost",
                message=f"Cost/recording ${cost_per_rec:.4f} exceeds ${t.max_cost_per_recording:.2f}",
                actual_value=cost_per_rec,
                threshold_value=t.max_cost_per_recording,
            ))

    # Latency checks
    if latency_summary:
        violations = latency_summary.get("violations", [])
        if violations:
            avg_duration = sum(v["duration"] for v in violations) / len(violations)
            alerts.append(Alert(
                severity="warning",
                category="latency",
                message=f"{len(violations)} SLA violation(s), avg {avg_duration:.1f}s",
                actual_value=avg_duration,
                threshold_value=t.max_latency_per_recording,
            ))

    # Escalation rate check
    if total_recordings > 0 and escalation_count > 0:
        rate = escalation_count / total_recordings
        if rate > t.max_escalation_rate:
            alerts.append(Alert(
                severity="warning",
                category="escalation",
                message=f"Escalation rate {rate:.1%} exceeds {t.max_escalation_rate:.1%}",
                actual_value=rate,
                threshold_value=t.max_escalation_rate,
            ))

    return alerts


def print_alerts(
    alerts: list[Alert],
    console: Console | None = None,
) -> None:
    """Print alerts as Rich warnings."""
    console = console or Console()
    log = get_logger("alerts")

    if not alerts:
        console.print("[green]✓ All quality checks passed[/green]")
        return

    console.print(f"\n[bold yellow]⚠ {len(alerts)} alert(s) triggered:[/bold yellow]")

    for alert in alerts:
        if alert.severity == "critical":
            style = "[bold red]CRITICAL[/bold red]"
        else:
            style = "[yellow]WARNING[/yellow]"

        console.print(f"  {style} [{alert.category}] {alert.message}")

        # Also log via structlog
        log.warning(
            "quality_alert",
            severity=alert.severity,
            category=alert.category,
            message=alert.message,
            actual=alert.actual_value,
            threshold=alert.threshold_value,
        )
