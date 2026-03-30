"""Lifecycle orchestrator composing the full extraction pipeline.

Top-level LangGraph that manages the complete pipeline lifecycle:
  START → transcribe → classify → route → [v1|v2] → postprocess → escalation_check → store → END

Uses conditional edges after classification to dispatch each recording to
the appropriate sub-pipeline based on difficulty. Pipeline dispatch uses a
registry pattern (OCP) — adding a new pipeline version requires only a
register_pipeline_runner() call, not modification of the dispatch function.
"""
from __future__ import annotations

import asyncio
import functools
import os
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from typing_extensions import TypedDict

from dotenv import load_dotenv

# load_dotenv() must precede langchain/langgraph imports so that API keys
# and Phoenix config are available when those libraries initialize (Pitfall 2).
load_dotenv()

from langgraph.graph import END, START, StateGraph  # noqa: E402
from openinference.instrumentation import using_attributes  # noqa: E402

from phonebot.pipeline.transcribe import get_transcript_text  # noqa: E402
from phonebot.pipeline.classifier import classify_transcript  # noqa: E402
from phonebot.pipeline.extract import (  # noqa: E402
    PIPELINE,
    compute_flagged_fields,
    TRANSCRIPT_DIR,
)
from phonebot.pipeline.escalation import check_escalation  # noqa: E402
from phonebot.pipeline.stages.postprocess import postprocess  # noqa: E402
from phonebot.pipeline.shared import PipelineVersion  # noqa: E402
from phonebot.observability.logging import (  # noqa: E402
    log_extraction_start,
    log_extraction_complete,
    log_escalation,
)


# ---------------------------------------------------------------------------
# Pipeline dispatch registry (OCP: extend by registration, not modification)
# ---------------------------------------------------------------------------

PipelineRunner = Callable[["OrchestratorState"], Coroutine[Any, Any, dict]]
_PIPELINE_RUNNERS: dict[PipelineVersion, PipelineRunner] = {}


def register_pipeline_runner(
    version: PipelineVersion, runner: PipelineRunner,
) -> None:
    """Register a pipeline runner for orchestrator dispatch."""
    _PIPELINE_RUNNERS[version] = runner


class OrchestratorState(TypedDict):
    recording_id: str
    transcript_text: str | None
    difficulty_tier: str | None
    difficulty_score: int | None
    recommended_pipeline: str | None
    use_few_shot: bool | None
    few_shot_context: str | None
    caller_info: dict | None
    flagged_fields: list[str] | None
    postprocess_result: dict | None
    escalation: dict | None
    model: str | None
    pipeline_used: str | None
    timestamp: str | None


# ---------------------------------------------------------------------------
# Orchestrator nodes
# ---------------------------------------------------------------------------

async def orch_transcribe_node(state: OrchestratorState) -> dict:
    """Load transcript text from cache (reuses existing transcribe logic)."""
    cache_path = TRANSCRIPT_DIR / f"{state['recording_id']}.json"
    text = get_transcript_text(cache_path)
    return {"transcript_text": text}


async def classify_node(state: OrchestratorState) -> dict:
    """Classify transcript difficulty for routing."""
    result = classify_transcript(state["recording_id"])
    return {
        "difficulty_tier": result.tier.value,
        "difficulty_score": result.score,
        "recommended_pipeline": result.recommended_pipeline,
        "use_few_shot": result.use_few_shot,
    }


async def retrieve_examples_node(state: OrchestratorState) -> dict:
    """Retrieve few-shot examples if recommended by classifier."""
    if not state.get("use_few_shot"):
        return {"few_shot_context": None}

    try:
        from phonebot.knowledge.example_store import ExampleStore
        store = ExampleStore()
        if store.count == 0:
            return {"few_shot_context": None}

        examples = store.retrieve(
            state["transcript_text"],
            k=2,
            exclude_id=state["recording_id"],
        )
        context = store.format_few_shot_prompt(examples)
        return {"few_shot_context": context}
    except (ImportError, FileNotFoundError, ValueError) as exc:
        from phonebot.observability.logging import get_logger
        get_logger("orchestrator").warning(
            "few_shot_retrieval_failed", error=str(exc),
        )
        return {"few_shot_context": None}


async def _run_v1(state: OrchestratorState) -> dict:
    """Run v1 extraction pipeline with optional few-shot context."""
    transcript = state["transcript_text"] or ""
    if state.get("few_shot_context"):
        transcript = state["few_shot_context"] + transcript
    return await PIPELINE.ainvoke({
        "recording_id": state["recording_id"],
        "transcript_text": transcript,
        "caller_info": None,
        "retry_count": 0,
        "validation_errors": None,
    })


async def _run_v2(state: OrchestratorState) -> dict:
    """Run v2 actor-critic extraction pipeline."""
    from phonebot.pipeline.extract_v2 import PIPELINE_V2
    ac_iterations = 3 if state.get("difficulty_tier") == "hard" else 1
    return await PIPELINE_V2.ainvoke({
        "recording_id": state["recording_id"],
        "transcript_text": state["transcript_text"],
        "caller_info": None,
        "retry_count": 0,
        "validation_errors": None,
        "ac_iteration": 0,
        "ac_max_iterations": ac_iterations,
        "critic_approved": False,
        "critic_feedback": None,
        "critic_field_verdicts": None,
        "ac_history": [],
    })


register_pipeline_runner(PipelineVersion.V1, _run_v1)
register_pipeline_runner(PipelineVersion.V2, _run_v2)


async def extract_node(state: OrchestratorState) -> dict:
    """Dispatch to registered pipeline based on classifier recommendation."""
    pipeline = PipelineVersion(state.get("recommended_pipeline", PipelineVersion.V1))
    runner = _PIPELINE_RUNNERS[pipeline]
    final_state = await runner(state)

    caller_info = final_state.get("caller_info") or {}
    return {
        "caller_info": caller_info,
        "flagged_fields": compute_flagged_fields(caller_info),
        "pipeline_used": pipeline,
    }


async def postprocess_node(state: OrchestratorState) -> dict:
    """Run post-processing with normalization and knowledge grounding."""
    caller_info = state.get("caller_info") or {}
    result = postprocess(caller_info)
    return {
        "caller_info": result.caller_info,
        "postprocess_result": {
            "grounding": result.grounding,
            "contact_validation": result.contact_validation,
            "cross_reference": result.cross_reference,
            "normalizations": result.normalizations_applied,
        },
        "flagged_fields": compute_flagged_fields(result.caller_info),
    }


async def escalation_node(state: OrchestratorState) -> dict:
    """Check if extraction needs human review escalation."""
    caller_info = state.get("caller_info") or {}
    flagged = state.get("flagged_fields") or []

    pp = state.get("postprocess_result") or {}
    item = check_escalation(
        recording_id=state["recording_id"],
        caller_info=caller_info,
        flagged_fields=flagged,
        transcript_text=state.get("transcript_text"),
        contact_validation=pp.get("contact_validation"),
    )

    if item:
        log_escalation(
            recording_id=state["recording_id"],
            reason=item.reason,
            confidence=item.overall_confidence,
            flagged_fields=flagged,
        )
        return {"escalation": item.to_dict()}

    return {"escalation": None}


async def finalize_node(state: OrchestratorState) -> dict:
    return {"timestamp": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# Graph construction — lazy via lru_cache to avoid import-time compilation
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _get_orchestrator():
    """Build and cache the orchestrator LangGraph pipeline.

    Uses lru_cache for thread-safe singleton behavior. The graph is compiled
    on first call, not at import time, so module import is fast and side-effect
    free. Subsequent calls return the cached compiled graph.
    """
    builder = StateGraph(OrchestratorState)
    builder.add_node("transcribe", orch_transcribe_node)
    builder.add_node("classify", classify_node)
    builder.add_node("retrieve_examples", retrieve_examples_node)
    builder.add_node("extract", extract_node)
    builder.add_node("postprocess", postprocess_node)
    builder.add_node("escalation_check", escalation_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "transcribe")
    builder.add_edge("transcribe", "classify")
    builder.add_edge("classify", "retrieve_examples")
    builder.add_edge("retrieve_examples", "extract")
    builder.add_edge("extract", "postprocess")
    builder.add_edge("postprocess", "escalation_check")
    builder.add_edge("escalation_check", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile()


async def run_orchestrated_pipeline(
    recording_ids: list[str],
    model_name: str = "claude-sonnet-4-6",
    concurrency: int = 5,
    prompt_version: str = "v1",
) -> list[dict]:
    """Run the full orchestrated pipeline over a list of recordings."""
    os.environ["PHONEBOT_MODEL"] = model_name
    effective_concurrency = int(os.getenv("EXTRACT_CONCURRENCY", str(concurrency)))
    semaphore = asyncio.Semaphore(effective_concurrency)
    orchestrator = _get_orchestrator()

    escalation_items: list[dict] = []

    async def process_one(recording_id: str) -> dict:
        async with semaphore:
            log_extraction_start(recording_id, model_name, "orchestrated", prompt_version)

            with using_attributes(
                metadata={
                    "recording_id": recording_id,
                    "model": model_name,
                    "prompt_version": prompt_version,
                    "pipeline": "orchestrated",
                    "run_timestamp": datetime.now(timezone.utc).isoformat(),
                },
                prompt_template_version=prompt_version,
            ):
                final_state = await orchestrator.ainvoke({
                    "recording_id": recording_id,
                    "transcript_text": None,
                    "difficulty_tier": None,
                    "difficulty_score": None,
                    "recommended_pipeline": None,
                    "use_few_shot": None,
                    "few_shot_context": None,
                    "caller_info": None,
                    "flagged_fields": None,
                    "postprocess_result": None,
                    "escalation": None,
                    "model": model_name,
                    "pipeline_used": None,
                    "timestamp": None,
                })

            if final_state.get("escalation"):
                escalation_items.append(final_state["escalation"])

            log_extraction_complete(
                recording_id=recording_id,
                model=model_name,
                duration_seconds=0,
                flagged_fields=final_state.get("flagged_fields"),
            )

            return {
                "id": recording_id,
                "caller_info": final_state.get("caller_info"),
                "flagged_fields": final_state.get("flagged_fields", []),
                "model": model_name,
                "pipeline_used": final_state.get("pipeline_used", PipelineVersion.V1),
                "difficulty_tier": final_state.get("difficulty_tier"),
                "difficulty_score": final_state.get("difficulty_score"),
                "postprocess": final_state.get("postprocess_result"),
                "escalated": final_state.get("escalation") is not None,
                "timestamp": final_state.get("timestamp"),
            }

    tasks = [process_one(rid) for rid in recording_ids]
    results = list(await asyncio.gather(*tasks))

    if escalation_items:
        from phonebot.pipeline.escalation import write_escalation_queue, EscalationItem
        items = [EscalationItem(**d) for d in escalation_items]
        write_escalation_queue(items)

    return results
