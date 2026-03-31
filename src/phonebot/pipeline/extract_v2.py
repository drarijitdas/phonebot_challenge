"""Actor-Critic LangGraph extraction pipeline (v2).

Extends the v1 pipeline with an actor-critic inner loop. After Pydantic validation
passes, a critic LLM evaluates the extraction against the transcript and provides
specific feedback. The actor then refines its extraction based on critic feedback.
This catches semantic errors (wrong name, miscounted digits) that schema validation
cannot detect.

Core extraction and validation logic is shared with v1 via pipeline.shared
to eliminate duplication. This module provides the v2-specific actor-critic
graph topology, critic evaluation, and runner configuration.

Graph topology:
  START -> transcribe -> actor_extract -> pydantic_validate -> route_pydantic
    route_pydantic:
      "retry"  -> actor_extract           (Pydantic fail, retries < 2)
      "critic" -> critic_evaluate         (Pydantic pass)
      "end"    -> END                     (retries exhausted)

    critic_evaluate -> route_critic
      "approved" -> END                   (critic approves OR iteration cap)
      "refine"   -> actor_refine          (critic rejects)

    actor_refine -> pydantic_validate_refined -> route_refined
      "critic" -> critic_evaluate         (Pydantic pass -> back to critic)
      "retry"  -> actor_refine            (Pydantic fail, retries left)
      "end"    -> END                     (retries exhausted)
"""
from __future__ import annotations

import functools
import json
import os
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv

# load_dotenv() must precede langchain/langgraph imports so that API keys
# and Phoenix config are available when those libraries initialize (Pitfall 2).
load_dotenv()

from pydantic import BaseModel, Field  # noqa: E402
from phonebot.models.model_registry import get_model  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402

from phonebot.pipeline.extract import (  # noqa: E402
    transcribe_node,
    _get_caller_info_model,
    set_caller_info_model,
)
from phonebot.pipeline.shared import (  # noqa: E402
    BasePipelineState,
    validate_caller_info,
    extract_caller_info,
    run_pipeline_concurrent,
    base_initial_state,
    base_result,
)
from phonebot.prompts import load_prompt  # noqa: E402

# ---------------------------------------------------------------------------
# Critic prompt — loaded once from JSON via lru_cache
# ---------------------------------------------------------------------------
_CRITIC_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "critic_prompt.json"


@functools.lru_cache(maxsize=1)
def _get_critic_system_prompt() -> str:
    """Load and cache the critic system prompt from JSON.

    Uses lru_cache for thread-safe caching. The prompt is read from disk
    on first call and cached for all subsequent calls.
    """
    data = load_prompt(_CRITIC_PROMPT_PATH)
    return data["system_prompt"]


__all__ = ["run_pipeline_v2", "set_caller_info_model", "PIPELINE_V2"]


# ---------------------------------------------------------------------------
# Critic structured output models
# ---------------------------------------------------------------------------

class CriticVerdict(BaseModel):
    """Verdict for a single extracted field."""

    field_name: str = Field(description="Name of the field being evaluated: first_name, last_name, email, or phone_number.")
    status: Literal["correct", "needs_fix"] = Field(description="'correct' if the extraction is accurate, 'needs_fix' if it has an error.")
    issue: Optional[str] = Field(default=None, description="If needs_fix: specific description of what is wrong and how to fix it.")
    evidence: Optional[str] = Field(default=None, description="Quote from the transcript that supports or contradicts the extraction.")


class CriticOutput(BaseModel):
    """Evaluation of an extraction attempt against the transcript."""

    overall_approved: bool = Field(
        description=(
            "True if all fields are correctly extracted or correctly null. "
            "False if any field needs fixing."
        )
    )
    field_verdicts: list[CriticVerdict] = Field(
        description="One verdict per extracted field (first_name, last_name, email, phone_number)."
    )
    summary_feedback: str = Field(
        description=(
            "One-paragraph summary of what is wrong and specific guidance for re-extraction. "
            "If approved, briefly state why the extraction is correct."
        )
    )


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

class ActorCriticState(BasePipelineState):
    """v2 pipeline state — extends BasePipelineState with actor-critic fields.

    Inherits from BasePipelineState:
      recording_id, transcript_text, caller_info, retry_count, validation_errors

    Additional fields for actor-critic loop:
    """

    ac_iteration: int               # current iteration (0-indexed)
    ac_max_iterations: int          # configurable cap
    critic_approved: bool           # True when critic accepts extraction
    critic_feedback: Optional[str]  # textual summary from critic
    critic_field_verdicts: Optional[list[dict]]  # per-field verdicts as dicts
    ac_history: list[dict]          # audit trail: [{iteration, caller_info, feedback, approved}]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def actor_extract_node(state: ActorCriticState) -> dict:
    """Initial extraction — delegates to shared.extract_caller_info().

    On retry (validation_errors present), injects error context per D-02:
    includes transcript and Pydantic error messages, but NOT the previous
    failed output (avoids anchoring).
    """
    return await extract_caller_info(state, _get_caller_info_model())


async def pydantic_validate_node(state: ActorCriticState) -> dict:
    """Validate extracted CallerInfo using Pydantic.

    Delegates to shared.validate_caller_info() — same logic as v1 validate_node.
    """
    return await validate_caller_info(state, _get_caller_info_model())


async def critic_evaluate_node(state: ActorCriticState) -> dict:
    """Evaluate extraction quality using LLM critic.

    Sends transcript + caller_info to critic LLM with CriticOutput structured output.
    Appends to ac_history for observability. Increments ac_iteration.
    """
    model = get_model(os.getenv("PHONEBOT_MODEL", "claude-sonnet-4-6"))
    structured_model = model.with_structured_output(CriticOutput, method="json_schema")

    transcript = state["transcript_text"]
    caller_info = state["caller_info"]
    system_prompt = _get_critic_system_prompt()

    # Format caller_info for the critic (exclude confidence for cleaner review)
    display_info = {k: v for k, v in caller_info.items() if k != "confidence"}

    prompt = (
        f"{system_prompt}\n\n"
        f"--- TRANSCRIPT ---\n{transcript}\n\n"
        f"--- EXTRACTION TO EVALUATE ---\n{json.dumps(display_info, ensure_ascii=False, indent=2)}"
    )

    result: CriticOutput = await structured_model.ainvoke(prompt)

    # Build history entry
    iteration = state.get("ac_iteration", 0)
    history_entry = {
        "iteration": iteration,
        "caller_info": caller_info,
        "feedback": result.summary_feedback,
        "approved": result.overall_approved,
        "field_verdicts": [v.model_dump() for v in result.field_verdicts],
    }
    ac_history = list(state.get("ac_history") or [])
    ac_history.append(history_entry)

    return {
        "critic_approved": result.overall_approved,
        "critic_feedback": result.summary_feedback,
        "critic_field_verdicts": [v.model_dump() for v in result.field_verdicts],
        "ac_iteration": iteration + 1,
        "ac_history": ac_history,
    }


async def actor_refine_node(state: ActorCriticState) -> dict:
    """Refine extraction incorporating critic feedback.

    Unlike v1's retry (which discards previous output to avoid anchoring),
    this deliberately includes the previous extraction + critic feedback.
    Anchoring to correct fields is desirable; only broken fields should change.
    """
    model = get_model(os.getenv("PHONEBOT_MODEL", "claude-sonnet-4-6"))
    caller_info_cls = _get_caller_info_model()
    structured_model = model.with_structured_output(caller_info_cls, method="json_schema")

    transcript = state["transcript_text"]
    caller_info = state["caller_info"]
    feedback = state.get("critic_feedback", "")
    field_verdicts = state.get("critic_field_verdicts") or []

    # Format field verdicts for the actor
    verdict_lines = []
    for v in field_verdicts:
        line = f"- {v['field_name']}: {v['status']}"
        if v.get("issue"):
            line += f" — {v['issue']}"
        if v.get("evidence"):
            line += f" (evidence: \"{v['evidence']}\")"
        verdict_lines.append(line)
    verdicts_text = "\n".join(verdict_lines)

    # Format previous extraction (exclude confidence)
    display_info = {k: v for k, v in caller_info.items() if k != "confidence"}

    prompt = (
        f"<transcript>\n{transcript}\n</transcript>\n\n"
        f"<previous_extraction>\n{json.dumps(display_info, ensure_ascii=False, indent=2)}\n</previous_extraction>\n\n"
        f"<critic_feedback>\n{feedback}\n\nField-level verdicts:\n{verdicts_text}\n</critic_feedback>\n\n"
        f"Re-extract caller information from the transcript.\n"
        f"Fix ONLY the fields marked 'needs_fix' above.\n"
        f"Preserve fields marked 'correct' exactly as they were.\n"
        f"Pay careful attention to the critic's evidence quotes from the transcript."
    )

    result = await structured_model.ainvoke(prompt)
    return {"caller_info": result.model_dump()}


async def pydantic_validate_refined_node(state: ActorCriticState) -> dict:
    """Validate refined extraction using Pydantic.

    Delegates to shared.validate_caller_info() — distinct graph node name
    for topology clarity, but identical validation logic.
    """
    return await validate_caller_info(state, _get_caller_info_model())


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def route_after_pydantic(state: ActorCriticState) -> str:
    """Route after initial Pydantic validation.

    - 'critic': validation passed -> enter actor-critic loop
    - 'retry': validation failed, retries remaining -> retry extraction
    - 'end': validation failed, retries exhausted -> give up
    """
    if not state.get("validation_errors"):
        return "critic"
    if state.get("retry_count", 0) >= 2:
        return "end"
    return "retry"


def route_after_critic(state: ActorCriticState) -> str:
    """Route after critic evaluation.

    - 'approved': critic approves OR iteration cap reached
    - 'refine': critic rejects, iterations remaining
    """
    if state.get("critic_approved"):
        return "approved"
    if state.get("ac_iteration", 0) >= state.get("ac_max_iterations", 3):
        return "approved"  # cap reached, accept best effort
    return "refine"


def route_after_refined(state: ActorCriticState) -> str:
    """Route after Pydantic validation of refined extraction.

    - 'critic': validation passed -> back to critic for re-evaluation
    - 'retry': validation failed, retries remaining
    - 'end': retries exhausted
    """
    if not state.get("validation_errors"):
        return "critic"
    if state.get("retry_count", 0) >= 2:
        return "end"
    return "retry"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_actor_critic_pipeline() -> object:
    """Build and compile the actor-critic LangGraph pipeline."""
    builder = StateGraph(ActorCriticState)

    # Nodes
    builder.add_node("transcribe", transcribe_node)
    builder.add_node("actor_extract", actor_extract_node)
    builder.add_node("pydantic_validate", pydantic_validate_node)
    builder.add_node("critic_evaluate", critic_evaluate_node)
    builder.add_node("actor_refine", actor_refine_node)
    builder.add_node("pydantic_validate_refined", pydantic_validate_refined_node)

    # Edges
    builder.add_edge(START, "transcribe")
    builder.add_edge("transcribe", "actor_extract")
    builder.add_edge("actor_extract", "pydantic_validate")
    builder.add_conditional_edges(
        "pydantic_validate",
        route_after_pydantic,
        {"critic": "critic_evaluate", "retry": "actor_extract", "end": END},
    )
    builder.add_conditional_edges(
        "critic_evaluate",
        route_after_critic,
        {"approved": END, "refine": "actor_refine"},
    )
    builder.add_edge("actor_refine", "pydantic_validate_refined")
    builder.add_conditional_edges(
        "pydantic_validate_refined",
        route_after_refined,
        {"critic": "critic_evaluate", "retry": "actor_refine", "end": END},
    )

    return builder.compile()


PIPELINE_V2 = build_actor_critic_pipeline()


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

async def run_pipeline_v2(
    recording_ids: list[str],
    model_name: str = "claude-sonnet-4-6",
    concurrency: int = 5,
    prompt_version: str = "v1",
    max_ac_iterations: int = 3,
    initial_state_override: object = None,
) -> list[dict]:
    """Run actor-critic extraction pipeline concurrently.

    Delegates to shared.run_pipeline_concurrent() for environment setup,
    bounded concurrency, and OpenTelemetry trace attribution. Provides
    v2-specific initial state factory (with actor-critic fields) and result
    builder (with ac_iterations_used, critic_approved, ac_history).

    Output is compatible with compare.py and compute_metrics() — same core
    keys: id, caller_info, flagged_fields, model, timestamp.
    """

    def _initial_state(recording_id: str) -> dict:
        base = (initial_state_override or base_initial_state)(recording_id)
        return {
            **base,
            "ac_iteration": 0,
            "ac_max_iterations": max_ac_iterations,
            "critic_approved": False,
            "critic_feedback": None,
            "critic_field_verdicts": None,
            "ac_history": [],
        }

    def _build_result(recording_id: str, final_state: dict, model: str) -> dict:
        return {
            **base_result(recording_id, final_state, model),
            "ac_iterations_used": final_state.get("ac_iteration", 0),
            "critic_approved": final_state.get("critic_approved", False),
            "ac_history": final_state.get("ac_history", []),
        }

    return await run_pipeline_concurrent(
        pipeline_graph=PIPELINE_V2,
        recording_ids=recording_ids,
        model_name=model_name,
        concurrency=concurrency,
        prompt_version=prompt_version,
        initial_state_factory=_initial_state,
        result_builder=_build_result,
        extra_metadata={
            "pipeline": "v2_actor_critic",
            "max_ac_iterations": max_ac_iterations,
        },
    )
