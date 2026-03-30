"""Shared pipeline infrastructure used by v1 and v2 extraction pipelines.

Consolidates duplicated logic that was previously copy-pasted between
extract.py (v1) and extract_v2.py (v2). Each pipeline module retains its
own thin wrapper functions as LangGraph node names, delegating to the
shared implementations here.

Shared components:
  - validate_caller_info: Pydantic validation with retry counting
  - extract_caller_info: LLM structured output extraction with retry context
  - run_pipeline_concurrent: Concurrent pipeline runner with tracing
"""
from __future__ import annotations

import asyncio
import os
import time as _time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from typing_extensions import TypedDict
from pydantic import ValidationError
from openinference.instrumentation import using_attributes

from phonebot.models.model_registry import get_model


# ---------------------------------------------------------------------------
# Module-level observability singletons (populated by init_observability)
# ---------------------------------------------------------------------------

_latency_monitor: Any = None


def init_observability() -> Any:
    """Create and store a module-level LatencyMonitor for pipeline timing.

    Returns the LatencyMonitor instance so run.py can read results after the run.
    """
    global _latency_monitor
    from phonebot.observability.latency import LatencyMonitor
    _latency_monitor = LatencyMonitor()
    return _latency_monitor


# ---------------------------------------------------------------------------
# Pipeline version enum — used by classifier, orchestrator, and runners
# ---------------------------------------------------------------------------

class PipelineVersion(str, Enum):
    """Extraction pipeline version identifiers."""

    V1 = "v1"
    V2 = "v2"


# ---------------------------------------------------------------------------
# State TypedDict hierarchy — formalizes the shared fields between v1 and v2
# ---------------------------------------------------------------------------

class BasePipelineState(TypedDict, total=False):
    """Base state fields shared by all pipeline versions.

    Both PipelineState (v1) and ActorCriticState (v2) extend this base,
    making the shared contract explicit and enabling shared node functions
    to accept either state type.
    """

    recording_id: str
    transcript_text: Optional[str]
    caller_info: Optional[dict]
    retry_count: int
    validation_errors: Optional[list[str]]
    few_shot_prefix: Optional[str]


async def validate_caller_info(state: dict, caller_info_cls: type) -> dict:
    """Validate extracted CallerInfo using Pydantic.

    Shared implementation for all validation nodes across v1 and v2 pipelines.
    On success, clears validation_errors. On failure, stores error details and
    increments retry_count so routing functions can enforce retry limits.

    Args:
        state: Pipeline state dict containing 'caller_info' and 'retry_count'.
        caller_info_cls: The dynamic CallerInfo Pydantic model class to validate against.

    Returns:
        Dict with 'validation_errors' (None on success, list[str] on failure)
        and optionally 'retry_count' (incremented on failure).
    """
    if state.get("caller_info") is None:
        return {
            "validation_errors": ["extract_node returned no output"],
            "retry_count": state.get("retry_count", 0) + 1,
        }

    try:
        caller_info_cls.model_validate(state["caller_info"])
        return {"validation_errors": None}
    except ValidationError as e:
        errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
        return {
            "validation_errors": errors,
            "retry_count": state.get("retry_count", 0) + 1,
        }


async def extract_caller_info(state: dict, caller_info_cls: type) -> dict:
    """Extract CallerInfo from transcript text using LLM structured output.

    Shared implementation for the initial extraction node in both v1 and v2
    pipelines. On retry (validation_errors present), injects error context
    into the prompt — includes the transcript and Pydantic error messages,
    but NOT the previous failed output (avoids anchoring the LLM to invalid data).

    Args:
        state: Pipeline state dict containing 'transcript_text' and optionally
            'validation_errors' from a previous failed attempt.
        caller_info_cls: The dynamic CallerInfo Pydantic model class for
            structured output extraction.

    Returns:
        Dict with 'caller_info' as a plain dict (model_dump()).
    """
    model = get_model(os.getenv("PHONEBOT_MODEL", "claude-sonnet-4-6"))
    structured_model = model.with_structured_output(caller_info_cls, method="json_schema")

    transcript = state["transcript_text"]
    few_shot_prefix = state.get("few_shot_prefix")
    if few_shot_prefix:
        transcript = few_shot_prefix + transcript
    validation_errors = state.get("validation_errors")

    if validation_errors:
        errors_text = "\n".join(f"- {e}" for e in validation_errors)
        prompt = (
            f"{transcript}\n\n"
            f"Previous extraction attempt returned invalid output. "
            f"Validation errors:\n"
            f"{errors_text}\n"
            f"Re-extract carefully, ensuring all fields match their required types."
        )
    else:
        prompt = transcript

    result = await structured_model.ainvoke(prompt)
    return {"caller_info": result.model_dump()}


def base_initial_state(recording_id: str) -> dict:
    """Create the base initial state dict shared by all pipeline versions.

    v2 callers extend this with actor-critic fields via dict unpacking:
        {**base_initial_state(rid), "ac_iteration": 0, ...}
    """
    return {
        "recording_id": recording_id,
        "transcript_text": None,
        "caller_info": None,
        "retry_count": 0,
        "validation_errors": None,
    }


def base_result(recording_id: str, final_state: dict, model_name: str) -> dict:
    """Build the base result dict shared by all pipeline versions.

    v2 callers extend this with actor-critic observability fields:
        {**base_result(rid, state, model), "ac_iterations_used": ...}
    """
    from phonebot.pipeline.extract import compute_flagged_fields
    flagged = compute_flagged_fields(final_state.get("caller_info") or {})
    return {
        "id": recording_id,
        "caller_info": final_state["caller_info"],
        "flagged_fields": flagged,
        "model": model_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def run_pipeline_concurrent(
    pipeline_graph: object,
    recording_ids: list[str],
    model_name: str,
    concurrency: int,
    prompt_version: str,
    initial_state_factory: Callable[[str], dict],
    result_builder: Callable[[str, dict, str], dict],
    extra_metadata: dict[str, Any] | None = None,
) -> list[dict]:
    """Run a LangGraph pipeline concurrently over a list of recordings.

    Shared runner used by both v1 run_pipeline() and v2 run_pipeline_v2().
    Handles environment setup, bounded concurrency via asyncio.Semaphore,
    and OpenTelemetry trace attribution via using_attributes().

    Args:
        pipeline_graph: Compiled LangGraph pipeline to invoke.
        recording_ids: List of recording IDs (e.g., ["call_01", "call_02"]).
        model_name: Model identifier (e.g., "claude-sonnet-4-6").
        concurrency: Max concurrent pipeline invocations.
        prompt_version: Prompt version tag for tracing.
        initial_state_factory: Callable that takes a recording_id and returns
            the initial state dict for the pipeline (v1 has 5 fields, v2 has 12).
        result_builder: Callable that takes (recording_id, final_state, model_name)
            and returns the result dict for output.
        extra_metadata: Additional metadata keys for OpenTelemetry traces.

    Returns:
        List of result dicts, one per recording.
    """
    os.environ["PHONEBOT_MODEL"] = model_name
    effective_concurrency = int(os.getenv("EXTRACT_CONCURRENCY", str(concurrency)))
    semaphore = asyncio.Semaphore(effective_concurrency)

    per_recording_timeout = int(os.getenv("EXTRACT_TIMEOUT", "120"))

    async def process_one(recording_id: str) -> dict:
        async with semaphore:
            metadata = {
                "recording_id": recording_id,
                "model": model_name,
                "prompt_version": prompt_version,
                "run_timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if extra_metadata:
                metadata.update(extra_metadata)

            t0 = _time.monotonic()
            try:
                with using_attributes(
                    metadata=metadata,
                    prompt_template_version=prompt_version,
                ):
                    final_state = await asyncio.wait_for(
                        pipeline_graph.ainvoke(
                            initial_state_factory(recording_id)
                        ),
                        timeout=per_recording_timeout,
                    )
            except Exception as exc:
                if not isinstance(exc, asyncio.TimeoutError):
                    from phonebot.observability.logging import get_logger
                    get_logger("pipeline").error(
                        "extraction_failed",
                        recording_id=recording_id,
                        error=str(exc),
                        error_type=type(exc).__name__,
                    )
                final_state = initial_state_factory(recording_id)
                final_state["caller_info"] = None
            duration = _time.monotonic() - t0

            if _latency_monitor:
                _latency_monitor.record(recording_id, "end_to_end", duration)

        return result_builder(recording_id, final_state, model_name)

    tasks = [process_one(rid) for rid in recording_ids]
    return list(await asyncio.gather(*tasks))
