"""Actor-Critic LangGraph extraction pipeline (v2).

Extends the v1 pipeline with an actor-critic inner loop. After Pydantic validation
passes, a critic LLM evaluates the extraction against the transcript and provides
specific feedback. The actor then refines its extraction based on critic feedback.
This catches semantic errors (wrong name, miscounted digits) that schema validation
cannot detect.

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

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from typing_extensions import TypedDict

from dotenv import load_dotenv

load_dotenv()  # Must precede langchain/langgraph imports (Pitfall 2)

from pydantic import BaseModel, Field, ValidationError  # noqa: E402
from phonebot.models.model_registry import get_model  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402
from openinference.instrumentation import using_attributes  # noqa: E402

from phonebot.pipeline.extract import (  # noqa: E402
    transcribe_node,
    _get_caller_info_model,
    set_caller_info_model,
    compute_flagged_fields,
    CONFIDENCE_THRESHOLD,
    EXTRACT_CONCURRENCY,
    TRANSCRIPT_DIR,
)
from phonebot.prompts import load_prompt  # noqa: E402

# ---------------------------------------------------------------------------
# Critic prompt — loaded once from JSON
# ---------------------------------------------------------------------------
_CRITIC_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "critic_prompt.json"
_CRITIC_SYSTEM_PROMPT: str | None = None


def _get_critic_system_prompt() -> str:
    """Load critic system prompt from JSON (cached after first call)."""
    global _CRITIC_SYSTEM_PROMPT
    if _CRITIC_SYSTEM_PROMPT is None:
        data = load_prompt(_CRITIC_PROMPT_PATH)
        _CRITIC_SYSTEM_PROMPT = data["system_prompt"]
    return _CRITIC_SYSTEM_PROMPT


# Re-export for external callers (optimize.py, run.py)
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

class ActorCriticState(TypedDict):
    # Core fields (same semantics as v1 PipelineState)
    recording_id: str
    transcript_text: Optional[str]
    caller_info: Optional[dict]
    retry_count: int
    validation_errors: Optional[list[str]]

    # Actor-critic loop tracking
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
    """Initial extraction — identical logic to v1 extract_node.

    On retry (validation_errors present), injects error context per D-02:
    includes transcript and Pydantic error messages, but NOT the previous
    failed output (avoids anchoring).
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


async def pydantic_validate_node(state: ActorCriticState) -> dict:
    """Validate extracted CallerInfo using Pydantic (same as v1 validate_node)."""
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
    """Validate refined extraction using Pydantic (same logic, distinct node for graph clarity)."""
    caller_info_cls = _get_caller_info_model()

    if state.get("caller_info") is None:
        return {
            "validation_errors": ["refine_node returned no output"],
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
) -> list[dict]:
    """Run actor-critic extraction pipeline concurrently.

    Same interface and output format as v1 run_pipeline, with additional
    max_ac_iterations param. Output is compatible with compare.py and
    compute_metrics() — same keys: id, caller_info, flagged_fields, model, timestamp.

    Adds 'ac_iterations_used' and 'ac_history' keys for observability.
    """
    os.environ["PHONEBOT_MODEL"] = model_name
    effective_concurrency = int(os.getenv("EXTRACT_CONCURRENCY", str(concurrency)))
    semaphore = asyncio.Semaphore(effective_concurrency)

    async def process_one(recording_id: str) -> dict:
        async with semaphore:
            with using_attributes(
                metadata={
                    "recording_id": recording_id,
                    "model": model_name,
                    "prompt_version": prompt_version,
                    "pipeline": "v2_actor_critic",
                    "max_ac_iterations": max_ac_iterations,
                    "run_timestamp": datetime.now(timezone.utc).isoformat(),
                },
                prompt_template_version=prompt_version,
            ):
                final_state = await PIPELINE_V2.ainvoke(
                    {
                        "recording_id": recording_id,
                        "transcript_text": None,
                        "caller_info": None,
                        "retry_count": 0,
                        "validation_errors": None,
                        "ac_iteration": 0,
                        "ac_max_iterations": max_ac_iterations,
                        "critic_approved": False,
                        "critic_feedback": None,
                        "critic_field_verdicts": None,
                        "ac_history": [],
                    }
                )

        flagged = compute_flagged_fields(final_state.get("caller_info") or {})
        return {
            "id": recording_id,
            "caller_info": final_state["caller_info"],
            "flagged_fields": flagged,
            "model": model_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            # v2-specific observability fields
            "ac_iterations_used": final_state.get("ac_iteration", 0),
            "critic_approved": final_state.get("critic_approved", False),
            "ac_history": final_state.get("ac_history", []),
        }

    tasks = [process_one(rid) for rid in recording_ids]
    return list(await asyncio.gather(*tasks))
