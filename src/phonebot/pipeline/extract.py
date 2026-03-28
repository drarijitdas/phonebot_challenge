"""LangGraph extraction pipeline for CallerInfo from German phone bot transcripts.

Implements a START -> transcribe -> extract -> validate -> (END | extract) graph
that takes a recording ID, loads its cached transcript, and extracts CallerInfo
via LLM structured output. On Pydantic validation failure, the graph retries up
to 2 times (3 total attempts) with error context injected into the prompt.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from typing_extensions import TypedDict

from dotenv import load_dotenv

load_dotenv()  # Must precede langchain/langgraph imports (Pitfall 2)

from pydantic import ValidationError  # noqa: E402
from phonebot.models.model_registry import get_model  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402
from openinference.instrumentation import using_attributes  # noqa: E402

from phonebot.models.caller_info import CallerInfo  # noqa: E402
from phonebot.pipeline.transcribe import get_transcript_text  # noqa: E402
from phonebot.prompts import build_caller_info_model  # noqa: E402

EXTRACT_CONCURRENCY = int(os.getenv("EXTRACT_CONCURRENCY", "5"))
TRANSCRIPT_DIR = Path("data/transcripts")
CONFIDENCE_THRESHOLD = 0.7

# Dynamic CallerInfo model — loaded from prompt JSON file at startup.
# GEPA evaluator swaps this via set_caller_info_model() between optimization iterations.
# extract_node reads this at call time (not import time), so one compiled PIPELINE serves all iterations.
# Per Pitfall 3: do NOT use `from phonebot.models.caller_info import CallerInfo` inside extract_node.
_CALLER_INFO_MODEL: type | None = None


def set_caller_info_model(model_class: type) -> None:
    """Inject a dynamic CallerInfo model for GEPA optimization iterations.

    Called by optimize.py before each run_pipeline() call to swap the prompt.
    Called by run.py at startup to load from the --prompt-version file.
    """
    global _CALLER_INFO_MODEL
    _CALLER_INFO_MODEL = model_class


def _get_caller_info_model() -> type:
    """Return the active CallerInfo model, loading default if not set."""
    global _CALLER_INFO_MODEL
    if _CALLER_INFO_MODEL is None:
        # Load default from extraction_v1.json (per D-10)
        default_path = Path(__file__).resolve().parent.parent / "prompts" / "extraction_v1.json"
        _CALLER_INFO_MODEL = build_caller_info_model(default_path)
    return _CALLER_INFO_MODEL


class PipelineState(TypedDict):
    recording_id: str                           # e.g. "call_01"
    transcript_text: Optional[str]              # filled by transcribe node
    caller_info: Optional[dict]                 # filled by extract node (CallerInfo.model_dump())
    retry_count: int                            # 0-indexed; incremented by validate_node on failure
    validation_errors: Optional[list[str]]      # populated by validate_node on failure; None on pass


async def transcribe_node(state: PipelineState) -> dict:
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


async def extract_node(state: PipelineState) -> dict:
    """Extract CallerInfo from transcript text using LLM structured output.

    Uses the dynamic CallerInfo model from _get_caller_info_model() instead of
    the static CallerInfo import. This allows GEPA's evaluator to hot-swap
    prompt candidates without rebuilding the LangGraph pipeline (Pitfall 3).

    Model name is read from the PHONEBOT_MODEL env var (set by run_pipeline before
    invocation). Supports both ChatAnthropic (claude-*) and ChatOllama (ollama:<model>)
    via the registry.

    On retry (validation_errors present in state), injects error context per D-02:
    includes original transcript and Pydantic error messages, but NOT the previous
    failed output (avoids anchoring the LLM to invalid data).

    Returns CallerInfo as a plain dict (model_dump()) to avoid Pitfall 1.
    """
    model = get_model(os.getenv("PHONEBOT_MODEL", "claude-sonnet-4-6"))
    caller_info_cls = _get_caller_info_model()
    structured_model = model.with_structured_output(caller_info_cls, method="json_schema")

    transcript = state["transcript_text"]
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


async def validate_node(state: PipelineState) -> dict:
    """Validate extracted CallerInfo using Pydantic. On failure, store errors for retry context.

    Returns validation_errors=None on success. On failure, returns the error list and
    increments retry_count so route_after_validate can enforce the max-retry limit.
    """
    caller_info_cls = _get_caller_info_model()

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


def route_after_validate(state: PipelineState) -> str:
    """Route to END on pass or retry limit; route to 'extract' on validation failure.

    Returns "end" when validation passes (no errors) or when retry_count >= 2
    (3 total attempts exhausted). Returns "retry" to loop back to extract_node.
    """
    if not state.get("validation_errors") or state.get("retry_count", 0) >= 2:
        return "end"
    return "retry"


def compute_flagged_fields(caller_info: dict) -> list[str]:
    """Return list of field names with confidence below CONFIDENCE_THRESHOLD (D-03, QUAL-02).

    Args:
        caller_info: Dict with a "confidence" key mapping field names to float scores.

    Returns:
        List of field names where score < CONFIDENCE_THRESHOLD. Empty list if no
        confidence data is present.
    """
    confidence = caller_info.get("confidence") or {}
    return [field for field, score in confidence.items() if score < CONFIDENCE_THRESHOLD]


def build_pipeline() -> object:
    """Build and compile LangGraph pipeline.

    Topology: START -> transcribe -> extract -> validate -> (END | extract)
    Conditional edge from validate: routes to END on pass or retry exhaustion,
    routes back to extract on validation failure (up to 2 retries).
    """
    builder = StateGraph(PipelineState)
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


PIPELINE = build_pipeline()  # Build once at import time (anti-pattern: don't rebuild per recording)


async def run_pipeline(
    recording_ids: list[str],
    model_name: str = "claude-sonnet-4-6",
    concurrency: int = 5,
    prompt_version: str = "v1",
) -> list[dict]:
    """Run extraction pipeline concurrently over a list of recording IDs.

    Sets PHONEBOT_MODEL env var so extract_node picks up the model name.
    Bounded concurrency via asyncio.Semaphore (also respects EXTRACT_CONCURRENCY env var).
    Each ainvoke() is wrapped with using_attributes() inside process_one() to tag
    concurrent traces with recording_id, model, prompt_version, and run_timestamp
    (RESEARCH Pattern 2, Pitfall 3 — prevents context bleed across concurrent traces).

    Args:
        recording_ids: List of recording IDs (e.g. ["call_01", "call_02", ...])
        model_name: Anthropic model name to use for extraction.
        concurrency: Max concurrent pipeline invocations.
        prompt_version: Prompt version tag attached to every Phoenix trace.

    Returns:
        List of dicts with keys: id, caller_info, model, timestamp.
    """
    os.environ["PHONEBOT_MODEL"] = model_name
    effective_concurrency = int(os.getenv("EXTRACT_CONCURRENCY", str(concurrency)))
    semaphore = asyncio.Semaphore(effective_concurrency)

    async def process_one(recording_id: str) -> dict:
        async with semaphore:
            # using_attributes() MUST be inside process_one(), not at outer scope
            # (RESEARCH Pitfall 3 — prevents context bleed across concurrent ainvoke() calls)
            with using_attributes(
                metadata={
                    "recording_id": recording_id,
                    "model": model_name,
                    "prompt_version": prompt_version,
                    "run_timestamp": datetime.now(timezone.utc).isoformat(),
                },
                prompt_template_version=prompt_version,
            ):
                final_state = await PIPELINE.ainvoke(
                    {
                        "recording_id": recording_id,
                        "transcript_text": None,
                        "caller_info": None,
                        "retry_count": 0,
                        "validation_errors": None,
                    }
                )
        flagged = compute_flagged_fields(final_state.get("caller_info") or {})
        return {
            "id": recording_id,
            "caller_info": final_state["caller_info"],
            "flagged_fields": flagged,
            "model": model_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    tasks = [process_one(rid) for rid in recording_ids]
    return list(await asyncio.gather(*tasks))
