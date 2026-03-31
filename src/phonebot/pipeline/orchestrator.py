"""Pipeline orchestrator — LangGraph StateGraph composing the full extraction pipeline.

Each graph invocation processes ONE recording through:
  classify → [few-shot retrieve] → extract (V1|V2) → [postprocess] → [escalation]

Batch concurrency is handled externally via run_pipeline_concurrent().

Graph topology:
  START -> classify -> route_after_classify
    "need_few_shot" -> few_shot_retrieve -> extract
    "skip"          -> extract

  extract -> route_after_extract
    "postprocess" -> postprocess -> route_after_postprocess
    "escalation"  -> escalation -> END
    "end"         -> END

  route_after_postprocess:
    "escalation" -> escalation -> END
    "end"        -> END
"""
from __future__ import annotations

import functools
import threading
from pathlib import Path
from typing import Any, Optional

from typing_extensions import TypedDict
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from phonebot.pipeline.shared import (
    PipelineVersion,
    base_initial_state,
    base_result,
    run_pipeline_concurrent,
)


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

class _OrchestratorRequired(TypedDict):
    """Required keys — always present in initial state."""

    recording_id: str


class OrchestratorState(_OrchestratorRequired, total=False):
    """Full state for one recording flowing through the orchestrator graph."""

    # Input (set by initial_state_factory)
    pipeline_version: str
    max_ac_iterations: int

    # Config flags (drive conditional edges)
    enable_few_shot: bool
    enable_postprocess: bool
    enable_escalation: bool

    # Classification (set by classify_node)
    classification_tier: Optional[str]
    classification_score: Optional[int]
    use_few_shot_recommended: Optional[bool]
    transcript_text: Optional[str]

    # Few-shot (set by few_shot_retrieve_node)
    few_shot_prefix: Optional[str]

    # Extraction (set by extract_node)
    caller_info: Optional[dict]
    flagged_fields: Optional[list[str]]
    extraction_metadata: Optional[dict]

    # Post-processing (set by postprocess_node)
    postprocess_result: Optional[dict]

    # Escalation (set by escalation_node)
    escalation_item: Optional[dict]
    escalated: bool


# ---------------------------------------------------------------------------
# Module-level singleton for ExampleStore (ChromaDB client is not serializable)
# ---------------------------------------------------------------------------

_example_store: Any = None
_example_store_lock = threading.Lock()


def _get_example_store() -> Any:
    """Lazy-init ExampleStore singleton, indexing ground truth on first call.

    Uses double-checked locking — safe under concurrent graph invocations
    because ChromaDB PersistentClient is not serializable through state.
    """
    global _example_store
    if _example_store is None:
        with _example_store_lock:
            if _example_store is None:
                from phonebot.knowledge.example_store import ExampleStore
                from phonebot.evaluation.metrics import load_ground_truth

                store = ExampleStore()
                if store.count == 0:
                    gt = load_ground_truth(Path("data/ground_truth.json"))
                    store.index_ground_truth(gt)
                _example_store = store
    return _example_store


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def classify_node(state: OrchestratorState) -> dict:
    """Classify transcript difficulty and load transcript text for downstream reuse."""
    from phonebot.pipeline.classifier import classify_transcript
    from phonebot.pipeline.transcribe import get_transcript_text, TRANSCRIPT_DIR

    recording_id = state["recording_id"]
    cls_result = classify_transcript(recording_id)

    cache_path = TRANSCRIPT_DIR / f"{recording_id}.json"
    transcript_text = get_transcript_text(cache_path) if cache_path.exists() else None

    return {
        "classification_tier": cls_result.tier.value,
        "classification_score": cls_result.score,
        "use_few_shot_recommended": cls_result.use_few_shot,
        "transcript_text": transcript_text,
    }


async def few_shot_retrieve_node(state: OrchestratorState) -> dict:
    """Retrieve few-shot examples via ChromaDB similarity search."""
    store = _get_example_store()
    recording_id = state["recording_id"]
    transcript_text = state.get("transcript_text") or ""

    examples = store.retrieve(transcript_text, k=2, exclude_id=recording_id)
    few_shot_prefix = store.format_few_shot_prompt(examples)
    return {"few_shot_prefix": few_shot_prefix}


async def extract_node(state: OrchestratorState) -> dict:
    """Run V1 or V2 extraction graph, mapping state in and out."""
    from phonebot.pipeline.extract import PIPELINE, compute_flagged_fields
    from phonebot.pipeline.extract_v2 import PIPELINE_V2

    recording_id = state["recording_id"]
    pipeline_version = state.get("pipeline_version", "v1")

    inner_state = base_initial_state(recording_id)

    few_shot_prefix = state.get("few_shot_prefix")
    if few_shot_prefix:
        inner_state["few_shot_prefix"] = few_shot_prefix

    if PipelineVersion(pipeline_version) == PipelineVersion.V2:
        max_ac = state.get("max_ac_iterations", 3)
        inner_state.update({
            "ac_iteration": 0,
            "ac_max_iterations": max_ac,
            "critic_approved": False,
            "critic_feedback": None,
            "critic_field_verdicts": None,
            "ac_history": [],
        })
        final_state = await PIPELINE_V2.ainvoke(inner_state)
        extraction_metadata = {
            "ac_iterations_used": final_state.get("ac_iteration", 0),
            "critic_approved": final_state.get("critic_approved", False),
            "ac_history": final_state.get("ac_history", []),
        }
    else:
        final_state = await PIPELINE.ainvoke(inner_state)
        extraction_metadata = {}

    caller_info = final_state.get("caller_info")
    flagged_fields = compute_flagged_fields(caller_info or {})

    return {
        "caller_info": caller_info,
        "flagged_fields": flagged_fields,
        "extraction_metadata": extraction_metadata,
    }


async def postprocess_node(state: OrchestratorState) -> dict:
    """Run post-processing: normalization + knowledge grounding."""
    from phonebot.pipeline.stages.postprocess import postprocess
    from phonebot.pipeline.extract import compute_flagged_fields

    caller_info = state.get("caller_info") or {}
    pp_result = postprocess(caller_info)

    return {
        "caller_info": pp_result.caller_info,
        "flagged_fields": compute_flagged_fields(pp_result.caller_info),
        "postprocess_result": {
            "grounding": pp_result.grounding,
            "contact_validation": pp_result.contact_validation,
            "cross_reference": pp_result.cross_reference,
            "normalizations": pp_result.normalizations_applied,
        },
    }


async def escalation_node(state: OrchestratorState) -> dict:
    """Check whether extraction should be escalated for human review."""
    from phonebot.pipeline.escalation import check_escalation

    caller_info = state.get("caller_info") or {}
    flagged_fields: list[str] = state.get("flagged_fields") or []
    recording_id = state["recording_id"]
    transcript_text = state.get("transcript_text")
    contact_validation = (state.get("postprocess_result") or {}).get(
        "contact_validation"
    )

    item = check_escalation(
        recording_id=recording_id,
        caller_info=caller_info,
        flagged_fields=flagged_fields,
        transcript_text=transcript_text,
        contact_validation=contact_validation,
    )

    if item:
        return {"escalation_item": item.to_dict(), "escalated": True}
    return {"escalation_item": None, "escalated": False}


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def route_after_classify(state: OrchestratorState) -> str:
    """Route to few-shot retrieval if enabled AND classifier recommends it."""
    if state.get("enable_few_shot") and state.get("use_few_shot_recommended"):
        return "need_few_shot"
    return "skip"


def route_after_extract(state: OrchestratorState) -> str:
    """Route to postprocess if enabled, else escalation, else end."""
    if state.get("enable_postprocess"):
        return "postprocess"
    if state.get("enable_escalation"):
        return "escalation"
    return "end"


def route_after_postprocess(state: OrchestratorState) -> str:
    """Route to escalation if enabled, else end."""
    if state.get("enable_escalation"):
        return "escalation"
    return "end"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_orchestrator_graph() -> CompiledStateGraph:
    """Build and compile the orchestrator LangGraph pipeline."""
    builder = StateGraph(OrchestratorState)

    builder.add_node("classify", classify_node)
    builder.add_node("few_shot_retrieve", few_shot_retrieve_node)
    builder.add_node("extract", extract_node)
    builder.add_node("postprocess", postprocess_node)
    builder.add_node("escalation", escalation_node)

    builder.add_edge(START, "classify")
    builder.add_conditional_edges(
        "classify",
        route_after_classify,
        {"need_few_shot": "few_shot_retrieve", "skip": "extract"},
    )
    builder.add_edge("few_shot_retrieve", "extract")
    builder.add_conditional_edges(
        "extract",
        route_after_extract,
        {"postprocess": "postprocess", "escalation": "escalation", "end": END},
    )
    builder.add_conditional_edges(
        "postprocess",
        route_after_postprocess,
        {"escalation": "escalation", "end": END},
    )
    builder.add_edge("escalation", END)

    return builder.compile()


ORCHESTRATOR_GRAPH = build_orchestrator_graph()


# ---------------------------------------------------------------------------
# Initial state factory and result builder
# ---------------------------------------------------------------------------

def _orchestrator_initial_state(
    recording_id: str,
    *,
    pipeline_version: str = "v1",
    max_ac_iterations: int = 3,
    enable_few_shot: bool = False,
    enable_postprocess: bool = True,
    enable_escalation: bool = True,
) -> dict:
    """Build initial OrchestratorState for a single recording."""
    return {
        "recording_id": recording_id,
        "pipeline_version": pipeline_version,
        "max_ac_iterations": max_ac_iterations,
        "enable_few_shot": enable_few_shot,
        "enable_postprocess": enable_postprocess,
        "enable_escalation": enable_escalation,
        "escalated": False,
    }


def _orchestrator_result_builder(
    recording_id: str,
    final_state: dict,
    model_name: str,
) -> dict:
    """Build result dict from final OrchestratorState."""
    result = base_result(recording_id, final_state, model_name)

    if final_state.get("postprocess_result"):
        result["postprocess"] = final_state["postprocess_result"]

    result["escalated"] = final_state.get("escalated", False)
    result["_escalation_item"] = final_state.get("escalation_item")

    if final_state.get("classification_tier"):
        result["difficulty_tier"] = final_state["classification_tier"]
        result["difficulty_score"] = final_state["classification_score"]

    extraction_meta = final_state.get("extraction_metadata") or {}
    if extraction_meta:
        result.update(extraction_meta)

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_orchestrator_pipeline(
    recording_ids: list[str],
    *,
    model_name: str = "claude-sonnet-4-6",
    pipeline: str = PipelineVersion.V1,
    prompt_version: str = "v1",
    max_ac_iterations: int = 3,
    enable_few_shot: bool = False,
    enable_postprocess: bool = True,
    enable_escalation: bool = True,
) -> list[dict]:
    """Run the orchestrator graph concurrently over a batch of recordings.

    Drop-in replacement for the old run_extraction_pipeline(). Each recording
    flows through: classify -> [few-shot] -> extract -> [postprocess] ->
    [escalation]. Batch-level escalation queue writing happens after all
    per-item graphs complete.
    """
    initial_state_factory = functools.partial(
        _orchestrator_initial_state,
        pipeline_version=pipeline,
        max_ac_iterations=max_ac_iterations,
        enable_few_shot=enable_few_shot,
        enable_postprocess=enable_postprocess,
        enable_escalation=enable_escalation,
    )

    results = await run_pipeline_concurrent(
        pipeline_graph=ORCHESTRATOR_GRAPH,
        recording_ids=recording_ids,
        model_name=model_name,
        concurrency=5,
        prompt_version=prompt_version,
        initial_state_factory=initial_state_factory,
        result_builder=_orchestrator_result_builder,
    )

    # Collect and strip internal escalation data in a single pass
    escalation_dicts = []
    for r in results:
        item = r.pop("_escalation_item", None)
        if item is not None:
            escalation_dicts.append(item)

    if enable_escalation and escalation_dicts:
        from phonebot.pipeline.escalation import write_escalation_queue, EscalationItem

        write_escalation_queue([EscalationItem(**d) for d in escalation_dicts])

    return results


# Backward-compat alias
run_extraction_pipeline = run_orchestrator_pipeline
