"""Tests for Actor-Critic LangGraph extraction pipeline (v2).

Covers:
- Graph topology verification (all nodes, edges, conditional routing)
- ActorCriticState fields
- CriticOutput / CriticVerdict schemas
- Routing logic (pydantic, critic, refined)
- Iteration cap enforcement
- Output format compatibility with v1 (for compare.py)
"""
import typing
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Graph topology
# ---------------------------------------------------------------------------


def test_graph_topology_nodes():
    """PIPELINE_V2 graph contains all expected nodes."""
    from phonebot.pipeline.extract_v2 import PIPELINE_V2

    g = PIPELINE_V2.get_graph()
    node_names = [n.name for n in g.nodes.values()]

    assert "transcribe" in node_names
    assert "actor_extract" in node_names
    assert "pydantic_validate" in node_names
    assert "critic_evaluate" in node_names
    assert "actor_refine" in node_names
    assert "pydantic_validate_refined" in node_names
    assert "__start__" in node_names
    assert "__end__" in node_names


def test_graph_topology_edges():
    """PIPELINE_V2 graph has correct edge structure."""
    from phonebot.pipeline.extract_v2 import PIPELINE_V2

    g = PIPELINE_V2.get_graph()
    edge_pairs = [(e.source, e.target) for e in g.edges]

    # Linear edges
    assert ("__start__", "transcribe") in edge_pairs
    assert ("transcribe", "actor_extract") in edge_pairs
    assert ("actor_extract", "pydantic_validate") in edge_pairs
    assert ("actor_refine", "pydantic_validate_refined") in edge_pairs

    # Conditional edges from pydantic_validate
    assert ("pydantic_validate", "critic_evaluate") in edge_pairs, "Missing: pydantic_validate -> critic_evaluate"
    assert ("pydantic_validate", "actor_extract") in edge_pairs, "Missing: pydantic_validate -> actor_extract (retry)"
    assert ("pydantic_validate", "__end__") in edge_pairs, "Missing: pydantic_validate -> __end__"

    # Conditional edges from critic_evaluate
    assert ("critic_evaluate", "__end__") in edge_pairs, "Missing: critic_evaluate -> __end__ (approved)"
    assert ("critic_evaluate", "actor_refine") in edge_pairs, "Missing: critic_evaluate -> actor_refine"

    # Conditional edges from pydantic_validate_refined
    assert ("pydantic_validate_refined", "critic_evaluate") in edge_pairs, "Missing: validate_refined -> critic"
    assert ("pydantic_validate_refined", "actor_refine") in edge_pairs, "Missing: validate_refined -> actor_refine (retry)"
    assert ("pydantic_validate_refined", "__end__") in edge_pairs, "Missing: validate_refined -> __end__"


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------


def test_actor_critic_state_fields():
    """ActorCriticState TypedDict has all required fields."""
    from phonebot.pipeline.extract_v2 import ActorCriticState

    hints = typing.get_type_hints(ActorCriticState)

    # v1 fields
    assert "recording_id" in hints
    assert "transcript_text" in hints
    assert "caller_info" in hints
    assert "retry_count" in hints
    assert "validation_errors" in hints

    # Actor-critic fields
    assert "ac_iteration" in hints
    assert "ac_max_iterations" in hints
    assert "critic_approved" in hints
    assert "critic_feedback" in hints
    assert "critic_field_verdicts" in hints
    assert "ac_history" in hints


# ---------------------------------------------------------------------------
# Critic models
# ---------------------------------------------------------------------------


def test_critic_verdict_schema():
    """CriticVerdict accepts valid data."""
    from phonebot.pipeline.extract_v2 import CriticVerdict

    v = CriticVerdict(
        field_name="email",
        status="needs_fix",
        issue="Missing dot before 'de'",
        evidence="Punkt d e",
    )
    assert v.status == "needs_fix"
    assert v.field_name == "email"


def test_critic_verdict_correct():
    """CriticVerdict accepts 'correct' status with no issue."""
    from phonebot.pipeline.extract_v2 import CriticVerdict

    v = CriticVerdict(field_name="first_name", status="correct")
    assert v.status == "correct"
    assert v.issue is None


def test_critic_output_schema():
    """CriticOutput accepts valid structured data."""
    from phonebot.pipeline.extract_v2 import CriticOutput, CriticVerdict

    output = CriticOutput(
        overall_approved=False,
        field_verdicts=[
            CriticVerdict(field_name="first_name", status="correct"),
            CriticVerdict(field_name="last_name", status="needs_fix", issue="Wrong spelling"),
        ],
        summary_feedback="Last name needs correction based on email evidence.",
    )
    assert not output.overall_approved
    assert len(output.field_verdicts) == 2


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------


def test_route_after_pydantic_passes():
    """Validation pass routes to critic."""
    from phonebot.pipeline.extract_v2 import route_after_pydantic

    state = {"validation_errors": None, "retry_count": 0}
    assert route_after_pydantic(state) == "critic"


def test_route_after_pydantic_retries():
    """Validation failure with retries remaining routes to retry."""
    from phonebot.pipeline.extract_v2 import route_after_pydantic

    state = {"validation_errors": ["some error"], "retry_count": 1}
    assert route_after_pydantic(state) == "retry"


def test_route_after_pydantic_exhausted():
    """Validation failure with retries exhausted routes to end."""
    from phonebot.pipeline.extract_v2 import route_after_pydantic

    state = {"validation_errors": ["some error"], "retry_count": 2}
    assert route_after_pydantic(state) == "end"


def test_route_after_critic_approved():
    """Critic approval routes to end."""
    from phonebot.pipeline.extract_v2 import route_after_critic

    state = {"critic_approved": True, "ac_iteration": 1, "ac_max_iterations": 3}
    assert route_after_critic(state) == "approved"


def test_route_after_critic_rejects():
    """Critic rejection with iterations remaining routes to refine."""
    from phonebot.pipeline.extract_v2 import route_after_critic

    state = {"critic_approved": False, "ac_iteration": 1, "ac_max_iterations": 3}
    assert route_after_critic(state) == "refine"


def test_route_after_critic_cap_reached():
    """Iteration cap reached routes to approved (accept best effort)."""
    from phonebot.pipeline.extract_v2 import route_after_critic

    state = {"critic_approved": False, "ac_iteration": 3, "ac_max_iterations": 3}
    assert route_after_critic(state) == "approved"


def test_route_after_refined_passes():
    """Refined extraction passing validation routes back to critic."""
    from phonebot.pipeline.extract_v2 import route_after_refined

    state = {"validation_errors": None, "retry_count": 0}
    assert route_after_refined(state) == "critic"


def test_route_after_refined_retries():
    """Refined extraction failing validation with retries routes to retry."""
    from phonebot.pipeline.extract_v2 import route_after_refined

    state = {"validation_errors": ["type error"], "retry_count": 1}
    assert route_after_refined(state) == "retry"


def test_route_after_refined_exhausted():
    """Refined extraction failing with retries exhausted routes to end."""
    from phonebot.pipeline.extract_v2 import route_after_refined

    state = {"validation_errors": ["type error"], "retry_count": 2}
    assert route_after_refined(state) == "end"


# ---------------------------------------------------------------------------
# Critic prompt loading
# ---------------------------------------------------------------------------


def test_critic_prompt_loads():
    """Critic system prompt loads from JSON without error."""
    from phonebot.pipeline.extract_v2 import _get_critic_system_prompt

    prompt = _get_critic_system_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 100
    assert "quality reviewer" in prompt.lower()


# ---------------------------------------------------------------------------
# Output format compatibility with v1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_output_format_has_required_keys():
    """run_pipeline_v2 output records have all keys needed by compare.py."""
    from phonebot.pipeline.extract_v2 import run_pipeline_v2, PIPELINE_V2

    # Mock the pipeline to avoid LLM calls
    mock_state = {
        "recording_id": "call_01",
        "caller_info": {
            "first_name": "Max",
            "last_name": "Mueller",
            "email": "max@test.de",
            "phone_number": "+491234567890",
            "confidence": {"first_name": 0.9, "last_name": 0.8, "email": 0.7, "phone_number": 0.95},
        },
        "ac_iteration": 1,
        "critic_approved": True,
        "ac_history": [],
    }

    with patch.object(PIPELINE_V2, "ainvoke", new_callable=AsyncMock, return_value=mock_state):
        results = await run_pipeline_v2(["call_01"], model_name="test-model", prompt_version="v1")

    assert len(results) == 1
    r = results[0]

    # Keys required by compare.py / compute_metrics
    assert "id" in r
    assert "caller_info" in r
    assert "flagged_fields" in r
    assert "model" in r
    assert "timestamp" in r

    # v2-specific keys
    assert "ac_iterations_used" in r
    assert "critic_approved" in r
    assert "ac_history" in r
