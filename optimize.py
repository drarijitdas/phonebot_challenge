"""GEPA prompt optimization script (Phase 6, OPT-01).

Runs GEPA offline optimization on the extraction system prompt and field descriptions.
Uses a custom GEPAAdapter for 5-slot candidate optimization (D-13).
Produces extraction_v2.json (optimized prompt) and optimization_report.json (accuracy deltas).

Usage:
    uv run python optimize.py
    uv run python optimize.py --max-calls 150  # smoke test (~5 iterations, ~$1-2)
"""
import argparse
import asyncio
import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from dotenv import load_dotenv

load_dotenv()

from rich.console import Console
from rich.table import Table

import gepa
from gepa import GEPAAdapter, EvaluationBatch

from phonebot.evaluation.metrics import (
    FIELDS, compute_metrics, load_ground_truth, matches_field,
)
from phonebot.observability import init_tracing, shutdown_tracing
from phonebot.pipeline.extract import run_pipeline, set_caller_info_model
from phonebot.pipeline.transcribe import get_transcript_text
from phonebot.prompts import build_caller_info_model, load_prompt

console = Console()

# ---------- Constants ----------

V1_PATH = Path("src/phonebot/prompts/extraction_v1.json")
V2_PATH = Path("src/phonebot/prompts/extraction_v2.json")
REPORT_PATH = Path("outputs/optimization_report.json")
GT_PATH = Path("data/ground_truth.json")
TRANSCRIPT_DIR = Path("data/transcripts")

# Phase 5 baseline accuracy (D-14: used for weight derivation)
BASELINE_ACCURACY = {
    "first_name": 0.90,
    "last_name": 0.767,
    "email": 0.667,
    "phone_number": 1.00,
}

WEIGHT_FLOOR = 0.05  # Minimum weight so phone_number regressions are detected


# ---------- Helper functions ----------

def compute_field_weights(baseline: dict[str, float]) -> dict[str, float]:
    """Compute inverse-accuracy field weights with a floor (D-14).

    Formula: weight(f) = max(1 - baseline(f), WEIGHT_FLOOR) / sum(...)
    """
    raw = {f: max(1.0 - acc, WEIGHT_FLOOR) for f, acc in baseline.items()}
    total = sum(raw.values())
    return {f: w / total for f, w in raw.items()}


def build_seed_candidate(prompt_path: Path) -> dict[str, str]:
    """Build GEPA seed_candidate dict from prompt JSON (D-13).

    Returns a dict with 5 keys: system_prompt + 4 field description slots.
    This is the optimization surface GEPA will evolve.
    """
    data = json.loads(prompt_path.read_text(encoding="utf-8"))
    return {
        "system_prompt": data["system_prompt"],
        **data["fields"],
    }


def save_optimized_prompt(candidate: dict[str, str], output_path: Path) -> None:
    """Save GEPA-optimized candidate as prompt JSON file."""
    payload = {
        "system_prompt": candidate["system_prompt"],
        "fields": {k: v for k, v in candidate.items() if k != "system_prompt"},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def make_train_val_split(
    all_ids: list[str], n_train: int = 20, seed: int = 42
) -> tuple[list[str], list[str]]:
    """Fixed-seed random split (D-11)."""
    rng = random.Random(seed)
    shuffled = list(all_ids)
    rng.shuffle(shuffled)
    return shuffled[:n_train], shuffled[n_train:]


def build_dataset(recording_ids: list[str]) -> list[dict]:
    """Build GEPA dataset from recording IDs + cached transcripts.

    Each item is a dict with:
    - input: transcript text
    - additional_context: {"recording_id": "call_XX"}
    - answer: "" (unused with custom evaluator)
    """
    dataset = []
    for rec_id in recording_ids:
        transcript = get_transcript_text(TRANSCRIPT_DIR / f"{rec_id}.json")
        dataset.append({
            "input": transcript,
            "additional_context": {"recording_id": rec_id},
            "answer": "",
        })
    return dataset


# ---------- Trajectory type for ASI ----------

class RecordingTrajectory:
    """Per-recording trajectory data for GEPA reflection.

    Stores the transcript, predicted extraction, ground truth, and per-field failure details.
    Used by make_reflective_dataset() to build ASI feedback for the reflection LM.
    """
    def __init__(
        self,
        recording_id: str,
        transcript: str,
        predicted: dict[str, Any],
        expected: dict[str, Any],
        failures: list[dict[str, str]],
        score: float,
        feedback: str,
    ) -> None:
        self.recording_id = recording_id
        self.transcript = transcript
        self.predicted = predicted
        self.expected = expected
        self.failures = failures
        self.score = score
        self.feedback = feedback


# ---------- Custom GEPA Adapter ----------

class PhonebotAdapter:
    """Custom GEPAAdapter for the phonebot extraction pipeline.

    Implements the GEPAAdapter protocol:
    - evaluate(): runs run_pipeline() in-process, scores with weighted per-field accuracy,
      returns per-recording ASI feedback (D-03, D-05, D-06)
    - make_reflective_dataset(): formats trajectories for GEPA's reflection LM

    Candidate structure (5 slots, D-13):
    - "system_prompt": CallerInfo.__doc__ (LangChain structured output system message)
    - "first_name": field description for first_name
    - "last_name": field description for last_name
    - "email": field description for email
    - "phone_number": field description for phone_number
    """

    # Tell GEPA to use its default reflection_lm proposer (not a custom one)
    propose_new_texts = None

    def __init__(
        self,
        ground_truth: dict[str, dict[str, Any]],
        field_weights: dict[str, float],
        train_ids: list[str],
    ) -> None:
        self.ground_truth = ground_truth
        self.field_weights = field_weights
        self.train_ids = train_ids
        self._iteration = 0

    def _candidate_to_prompt_json(self, candidate: dict[str, str]) -> dict:
        """Convert GEPA candidate dict to prompt JSON structure."""
        return {
            "system_prompt": candidate["system_prompt"],
            "fields": {k: v for k, v in candidate.items() if k != "system_prompt"},
        }

    def _run_pipeline_sync(
        self,
        recording_ids: list[str],
        prompt_version: str,
        candidate: dict[str, str],
    ) -> list[dict]:
        """Run the extraction pipeline synchronously with the given candidate.

        1. Write candidate to a temp prompt file
        2. Build dynamic CallerInfo model from it
        3. Inject via set_caller_info_model()
        4. Call asyncio.run(run_pipeline(...))
        """
        import tempfile
        prompt_data = self._candidate_to_prompt_json(candidate)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(prompt_data, f, ensure_ascii=False, indent=2)
            tmp_path = Path(f.name)

        try:
            model_class = build_caller_info_model(tmp_path)
            set_caller_info_model(model_class)
            # Tag Phoenix traces with the optimization iteration (D-06)
            os.environ["PHOENIX_PROJECT"] = "phonebot-extraction"
            results = asyncio.run(
                run_pipeline(
                    recording_ids,
                    model_name="claude-sonnet-4-6",
                    prompt_version=prompt_version,
                )
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        return results

    def evaluate(
        self,
        batch: list[dict],
        candidate: dict[str, str],
        capture_traces: bool = False,
    ) -> EvaluationBatch:
        """Evaluate candidate on a batch of recordings.

        Args:
            batch: List of dicts with 'input', 'additional_context', 'answer'.
            candidate: 5-key dict with system_prompt + field descriptions.
            capture_traces: When True, populate trajectories for make_reflective_dataset.

        Returns:
            EvaluationBatch with per-recording scores and optional trajectories.
        """
        self._iteration += 1
        prompt_version = f"gepa_opt_{self._iteration}"

        # Extract recording IDs from batch
        recording_ids = [item["additional_context"]["recording_id"] for item in batch]

        # Run pipeline synchronously
        try:
            results = self._run_pipeline_sync(recording_ids, prompt_version, candidate)
        except Exception as e:
            console.print(f"[red]Pipeline error in iteration {self._iteration}: {e}[/red]")
            # Return zero scores for all examples on systemic failure
            n = len(batch)
            return EvaluationBatch(
                outputs=[None] * n,
                scores=[0.0] * n,
                trajectories=([None] * n if capture_traces else None),
            )

        # Score each recording with weighted per-field accuracy (D-14)
        outputs = []
        scores = []
        trajectories = [] if capture_traces else None

        # Index results by recording ID
        results_by_id = {r["id"]: r for r in results}

        for item in batch:
            rec_id = item["additional_context"]["recording_id"]
            result = results_by_id.get(rec_id)

            if result is None:
                outputs.append(None)
                scores.append(0.0)
                if trajectories is not None:
                    trajectories.append(None)
                continue

            caller_info = result.get("caller_info") or {}
            if hasattr(caller_info, "model_dump"):
                caller_info = caller_info.model_dump()

            expected = self.ground_truth.get(rec_id, {})

            # Compute weighted score and collect failures for ASI (D-03)
            weighted_score = 0.0
            failures = []

            for field in FIELDS:
                predicted_val = caller_info.get(field)
                expected_val = expected.get(field)
                correct = matches_field(field, predicted_val, expected_val)
                weight = self.field_weights.get(field, 0.25)

                if correct:
                    weighted_score += weight
                else:
                    failures.append({
                        "field": field,
                        "predicted": str(predicted_val),
                        "expected": str(expected_val),
                    })

            # Build ASI feedback string for GEPA reflection (D-03)
            if not failures:
                feedback = "All fields correct."
            else:
                failure_lines = [
                    f"  {f['field']}: predicted={f['predicted']!r}, expected={f['expected']!r}"
                    for f in failures
                ]
                feedback = "Extraction failures:\n" + "\n".join(failure_lines)
                # Add transcript excerpt (first 200 chars) for context
                transcript = item.get("input", "")[:200]
                if transcript:
                    feedback += f"\n\nTranscript excerpt:\n{transcript}..."

            outputs.append(caller_info)
            scores.append(weighted_score)

            if trajectories is not None:
                trajectories.append(
                    RecordingTrajectory(
                        recording_id=rec_id,
                        transcript=item.get("input", ""),
                        predicted=caller_info,
                        expected=expected,
                        failures=failures,
                        score=weighted_score,
                        feedback=feedback,
                    )
                )

        return EvaluationBatch(
            outputs=outputs,
            scores=scores,
            trajectories=trajectories,
        )

    def make_reflective_dataset(
        self,
        candidate: dict[str, str],
        eval_batch: EvaluationBatch,
        components_to_update: list[str],
    ) -> Mapping[str, Sequence[Mapping[str, Any]]]:
        """Build reflective dataset for GEPA's reflection LM.

        For each component to update (e.g., "system_prompt", "email"), generates
        a list of records with Inputs, Generated Outputs, and Feedback.
        This drives GEPA's proposal of improved prompt text.
        """
        trajectories = eval_batch.trajectories
        assert trajectories is not None, "Trajectories must be populated (capture_traces=True)"

        ret: dict[str, list[Mapping[str, Any]]] = {}

        for comp in components_to_update:
            records = []
            for traj in trajectories:
                if traj is None:
                    continue
                # For each component, provide transcript + extraction failure context
                record: dict[str, Any] = {
                    "Inputs": {
                        "transcript": traj.transcript[:500],
                        "recording_id": traj.recording_id,
                    },
                    "Generated Outputs": {
                        field: str(traj.predicted.get(field))
                        for field in FIELDS
                    },
                    "Feedback": traj.feedback,
                }
                # For field-specific components, include expected value context
                if comp in FIELDS:
                    record["Component Focus"] = comp
                    record["Expected Value"] = str(traj.expected.get(comp))
                    record["Predicted Value"] = str(traj.predicted.get(comp))
                records.append(record)

            if not records:
                raise Exception(f"No valid trajectories found for component {comp!r}.")
            ret[comp] = records

        return ret


# ---------- Main ----------

def main() -> None:
    """Entry point: run GEPA optimization and write results."""
    parser = argparse.ArgumentParser(
        prog="optimize",
        description="GEPA prompt optimization for extraction pipeline",
    )
    parser.add_argument(
        "--max-calls", type=int, default=300,
        help="Maximum GEPA metric evaluations counted per-example (D-15). "
             "Each iteration evaluates ~30 examples (20 train + 10 val). "
             "Use 150 for ~5 iterations, 300 for ~10.",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for train/val split and GEPA",
    )
    args = parser.parse_args()

    if args.max_calls < 60:
        n_iter = max(0, args.max_calls // 30 - 1)
        console.print(
            f"[yellow]⚠ --max-calls {args.max_calls} is low. "
            f"GEPA counts per-example (~30/iteration for 20 train + 10 val). "
            f"Budget allows ~{n_iter} optimization iteration(s). "
            "Use --max-calls 150+ for meaningful results.[/yellow]"
        )

    # Initialize Phoenix tracing (D-06)
    phoenix_url = init_tracing()
    console.print(f"[green]Phoenix tracing: {phoenix_url}[/green]")

    # Load ground truth
    gt = load_ground_truth(GT_PATH)
    all_ids = sorted(gt.keys())

    # Train/val split (D-11, D-12)
    train_ids, val_ids = make_train_val_split(all_ids, n_train=20, seed=args.seed)
    console.print(f"Train: {len(train_ids)} recordings, Val: {len(val_ids)} recordings")

    # Build datasets
    trainset = build_dataset(train_ids)
    valset = build_dataset(val_ids)

    # Build seed candidate from v1 (D-10)
    seed_candidate = build_seed_candidate(V1_PATH)
    console.print(f"Seed candidate: {len(seed_candidate)} slots")

    # Compute field weights (D-14)
    weights = compute_field_weights(BASELINE_ACCURACY)
    console.print("Field weights:")
    for f, w in weights.items():
        console.print(f"  {f}: {w:.3f}")

    # Compute baseline accuracy on train set
    console.print("\n[bold]Computing baseline accuracy on train set...[/bold]")
    v1_model = build_caller_info_model(V1_PATH)
    set_caller_info_model(v1_model)
    train_results = asyncio.run(run_pipeline(
        train_ids, model_name="claude-sonnet-4-6", prompt_version="v1_baseline",
    ))
    train_gt = {rid: gt[rid] for rid in train_ids}
    baseline_metrics = compute_metrics(train_results, train_gt)
    console.print(f"Baseline train accuracy: {baseline_metrics['overall']:.1%}")

    # Create custom adapter
    adapter = PhonebotAdapter(
        ground_truth=gt,
        field_weights=weights,
        train_ids=train_ids,
    )

    # Run GEPA optimization (D-01, D-02, D-15)
    console.print(f"\n[bold]Starting GEPA optimization (max_calls={args.max_calls})...[/bold]")
    t0 = time.monotonic()

    result = gepa.optimize(
        seed_candidate=seed_candidate,
        trainset=trainset,
        valset=valset,
        adapter=adapter,
        reflection_lm="anthropic/claude-opus-4-6",
        max_metric_calls=args.max_calls,
        seed=args.seed,
        run_dir="outputs/gepa_run/",
    )

    duration = time.monotonic() - t0
    console.print(f"[green]Optimization complete in {duration:.0f}s[/green]")

    # Save optimized prompt (D-08)
    optimized_candidate = result.best_candidate
    save_optimized_prompt(optimized_candidate, V2_PATH)
    console.print(f"Optimized prompt saved to {V2_PATH}")

    # Compute optimized accuracy on validation set
    console.print("\n[bold]Evaluating optimized prompt on validation set...[/bold]")
    opt_model = build_caller_info_model(V2_PATH)
    set_caller_info_model(opt_model)
    val_results = asyncio.run(run_pipeline(
        val_ids, model_name="claude-sonnet-4-6", prompt_version="v2_optimized",
    ))
    val_gt = {rid: gt[rid] for rid in val_ids}
    optimized_metrics = compute_metrics(val_results, val_gt)

    # Compute baseline on val set for fair comparison
    v1_model = build_caller_info_model(V1_PATH)
    set_caller_info_model(v1_model)
    val_baseline_results = asyncio.run(run_pipeline(
        val_ids, model_name="claude-sonnet-4-6", prompt_version="v1_baseline_val",
    ))
    val_baseline_metrics = compute_metrics(val_baseline_results, val_gt)

    # Build and write optimization report (D-16)
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(duration, 1),
        "max_metric_calls": args.max_calls,
        "seed": args.seed,
        "train_ids": train_ids,
        "val_ids": val_ids,
        "field_weights": weights,
        "baseline_accuracy": {
            "train": baseline_metrics["per_field"],
            "train_overall": baseline_metrics["overall"],
            "val": val_baseline_metrics["per_field"],
            "val_overall": val_baseline_metrics["overall"],
        },
        "optimized_accuracy": {
            "val": optimized_metrics["per_field"],
            "val_overall": optimized_metrics["overall"],
        },
        "delta": {
            field: round(
                optimized_metrics["per_field"][field] - val_baseline_metrics["per_field"][field], 4
            )
            for field in FIELDS
        },
        "delta_overall": round(
            optimized_metrics["overall"] - val_baseline_metrics["overall"], 4
        ),
        "optimized_prompt_path": str(V2_PATH),
        "gepa_run_dir": "outputs/gepa_run/",
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Print Rich summary table (D-16)
    table = Table(title="Optimization Results (Validation Set)")
    table.add_column("Field", style="cyan")
    table.add_column("Baseline", style="yellow")
    table.add_column("Optimized", style="green")
    table.add_column("Delta", style="magenta")

    for field in FIELDS:
        bl = val_baseline_metrics["per_field"][field]
        opt = optimized_metrics["per_field"][field]
        delta = opt - bl
        delta_str = f"{delta:+.0%}"
        table.add_row(field, f"{bl:.0%}", f"{opt:.0%}", delta_str)

    bl_overall = val_baseline_metrics["overall"]
    opt_overall = optimized_metrics["overall"]
    delta_overall = opt_overall - bl_overall
    table.add_row(
        "[bold]Overall[/bold]",
        f"[bold]{bl_overall:.0%}[/bold]",
        f"[bold]{opt_overall:.0%}[/bold]",
        f"[bold]{delta_overall:+.0%}[/bold]",
    )
    console.print(table)

    console.print(f"\nReport: {REPORT_PATH}")
    console.print(f"Optimized prompt: {V2_PATH}")
    console.print(f"Phoenix traces: {phoenix_url}")

    shutdown_tracing()


if __name__ == "__main__":
    main()
