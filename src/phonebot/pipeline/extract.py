"""LangGraph extraction pipeline (v1) for CallerInfo from German phone bot transcripts.

Implements a START -> transcribe -> extract -> validate -> (END | extract) graph
that takes a recording ID, loads its cached transcript, and extracts CallerInfo
via LLM structured output. On Pydantic validation failure, the graph retries up
to 2 times (3 total attempts) with error context injected into the prompt.

Core extraction and validation logic is shared with v2 via pipeline.shared.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# load_dotenv() must precede langchain/langgraph imports so that API keys
# and Phoenix config are available when those libraries initialize (Pitfall 2).
load_dotenv()

from langgraph.graph import END, START, StateGraph  # noqa: E402

from phonebot.pipeline.transcribe import get_transcript_text  # noqa: E402
from phonebot.pipeline.shared import (  # noqa: E402
    BasePipelineState,
    validate_caller_info,
    extract_caller_info,
    run_pipeline_concurrent,
    base_initial_state,
    base_result,
)
from phonebot.prompts import build_caller_info_model  # noqa: E402

EXTRACT_CONCURRENCY = int(os.getenv("EXTRACT_CONCURRENCY", "10"))
TRANSCRIPT_DIR = Path("data/transcripts")
CONFIDENCE_THRESHOLD = 0.7

# Dynamic CallerInfo model — loaded from prompt JSON file at startup.
# GEPA evaluator swaps this via set_caller_info_model() between optimization iterations.
# extract_node reads this at call time (not import time), so one compiled PIPELINE
# serves all iterations.
_CALLER_INFO_MODEL: type | None = None


def set_caller_info_model(model_class: type) -> None:
    """Inject a dynamic CallerInfo model for GEPA optimization iterations.

    Called by optimize.py before each run_pipeline() call to swap the prompt.
    Called by run.py at startup to load from the --prompt-version file.
    """
    global _CALLER_INFO_MODEL
    _CALLER_INFO_MODEL = model_class


def _get_caller_info_model() -> type:
    """Return the active CallerInfo Pydantic model for structured extraction.

    The model is swappable at runtime for two use cases:
      1. optimize.py calls set_caller_info_model() before each GEPA iteration
         to hot-swap prompt candidates without rebuilding the LangGraph pipeline.
      2. run.py calls set_caller_info_model() at startup to load from the
         --prompt-version file (v1, v2, or v2_ac).

    If no model has been set, loads the default from extraction_v1.json.
    """
    global _CALLER_INFO_MODEL
    if _CALLER_INFO_MODEL is None:
        default_path = (
            Path(__file__).resolve().parent.parent / "prompts" / "extraction_v1.json"
        )
        _CALLER_INFO_MODEL = build_caller_info_model(default_path)
    return _CALLER_INFO_MODEL


async def transcribe_node(state: BasePipelineState) -> dict:
    """Load transcript text from cache.

    Phase 2 ensures all 30 recordings are cached. If cache file does not exist,
    raises FileNotFoundError -- API fallback is not needed in Phase 3.
    """
    cache_path = TRANSCRIPT_DIR / f"{state['recording_id']}.json"
    if not cache_path.exists():
        raise FileNotFoundError(
            f"Transcript cache not found: {cache_path}. "
            "Run transcription pipeline first (Phase 2)."
        )
    text = get_transcript_text(cache_path)
    return {"transcript_text": text}


async def extract_node(state: BasePipelineState) -> dict:
    """Extract CallerInfo from transcript via LLM structured output.

    Delegates to shared.extract_caller_info(). The dynamic CallerInfo model
    allows GEPA's evaluator to hot-swap prompt candidates without rebuilding
    the pipeline.
    """
    return await extract_caller_info(state, _get_caller_info_model())


async def validate_node(state: BasePipelineState) -> dict:
    """Validate extracted CallerInfo using Pydantic.

    Delegates to shared.validate_caller_info(). On failure, stores error
    details and increments retry_count for the routing function.
    """
    return await validate_caller_info(state, _get_caller_info_model())


def route_after_validate(state: BasePipelineState) -> str:
    """Route to END on pass or retry limit; back to extract on failure."""
    if not state.get("validation_errors") or state.get("retry_count", 0) >= 2:
        return "end"
    return "retry"


def compute_flagged_fields(caller_info: dict) -> list[str]:
    """Return field names with confidence below CONFIDENCE_THRESHOLD."""
    confidence = caller_info.get("confidence") or {}
    return [
        field for field, score in confidence.items()
        if score < CONFIDENCE_THRESHOLD
    ]


def build_pipeline() -> object:
    """Build and compile the v1 LangGraph pipeline.

    Topology: START -> transcribe -> extract -> validate -> (END | extract)
    """
    builder = StateGraph(BasePipelineState)
    builder.add_node("transcribe", transcribe_node)
    builder.add_node("extract", extract_node)
    builder.add_node("validate", validate_node)

    builder.add_edge(START, "transcribe")
    builder.add_edge("transcribe", "extract")
    builder.add_edge("extract", "validate")
    builder.add_conditional_edges(
        "validate",
        route_after_validate,
        {"end": END, "retry": "extract"},
    )
    return builder.compile()


PIPELINE = build_pipeline()


async def run_pipeline(
    recording_ids: list[str],
    model_name: str = "claude-sonnet-4-6",
    concurrency: int = 5,
    prompt_version: str = "v1",
    initial_state_override: object = None,
) -> list[dict]:
    """Run extraction pipeline concurrently over a list of recording IDs.

    Args:
        recording_ids: List of recording IDs (e.g. ["call_01", "call_02", ...])
        model_name: Anthropic model name to use for extraction.
        concurrency: Max concurrent pipeline invocations.
        prompt_version: Prompt version tag attached to every Phoenix trace.
        initial_state_override: Optional callable(recording_id) -> dict to
            replace base_initial_state. Used by run.py to inject few-shot context.

    Returns:
        List of dicts with keys: id, caller_info, flagged_fields, model, timestamp.
    """
    return await run_pipeline_concurrent(
        pipeline_graph=PIPELINE,
        recording_ids=recording_ids,
        model_name=model_name,
        concurrency=concurrency,
        prompt_version=prompt_version,
        initial_state_factory=initial_state_override or base_initial_state,
        result_builder=base_result,
    )
