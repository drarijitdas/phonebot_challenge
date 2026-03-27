"""Tests for LangGraph extraction pipeline and CallerInfo field descriptions.

Covers:
- EXT-03: Graph topology (START -> transcribe -> extract -> END)
- EXT-02: CallerInfo docstring as system prompt; field descriptions as extraction instructions
- EXT-05: Field descriptions handle German spoken-form phone/email patterns
- QUAL-01: Absent fields return null, not hallucinated values (integration, requires ANTHROPIC_API_KEY)
"""
import asyncio
import json
import os
import typing
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# EXT-03: Graph topology
# ---------------------------------------------------------------------------


def test_graph_topology():
    """PIPELINE graph has START -> transcribe -> extract -> END topology."""
    from phonebot.pipeline.extract import PIPELINE

    g = PIPELINE.get_graph()
    node_names = [n.name for n in g.nodes.values()]

    assert "transcribe" in node_names, "transcribe node missing from graph"
    assert "extract" in node_names, "extract node missing from graph"
    assert "__start__" in node_names, "__start__ node missing from graph"
    assert "__end__" in node_names, "__end__ node missing from graph"

    # Check edges: START -> transcribe -> extract -> END
    edge_pairs = [(e.source, e.target) for e in g.edges]
    assert ("__start__", "transcribe") in edge_pairs, "Missing edge: __start__ -> transcribe"
    assert ("transcribe", "extract") in edge_pairs, "Missing edge: transcribe -> extract"
    assert ("extract", "__end__") in edge_pairs, "Missing edge: extract -> __end__"


# ---------------------------------------------------------------------------
# EXT-03: PipelineState fields
# ---------------------------------------------------------------------------


def test_pipeline_state_fields():
    """PipelineState TypedDict has correct field names and types."""
    from phonebot.pipeline.extract import PipelineState

    hints = typing.get_type_hints(PipelineState)

    assert "recording_id" in hints, "PipelineState missing recording_id"
    assert "transcript_text" in hints, "PipelineState missing transcript_text"
    assert "caller_info" in hints, "PipelineState missing caller_info"

    # recording_id should be str (not Optional)
    assert hints["recording_id"] is str, f"recording_id type should be str, got {hints['recording_id']}"


# ---------------------------------------------------------------------------
# EXT-05: CallerInfo field descriptions contain Deepgram output patterns
# ---------------------------------------------------------------------------


def test_caller_info_field_descriptions_phone():
    """CallerInfo phone_number description contains exact Deepgram digit-by-digit pattern."""
    from phonebot.models.caller_info import CallerInfo

    desc = CallerInfo.model_fields["phone_number"].description
    assert "plus 4 9" in desc, "phone_number description missing 'plus 4 9' Deepgram pattern"
    assert "E.164" in desc, "phone_number description missing E.164 format instruction"


def test_caller_info_field_descriptions_email():
    """CallerInfo email description contains German spoken-form email components."""
    from phonebot.models.caller_info import CallerInfo

    desc = CallerInfo.model_fields["email"].description
    assert "Punkt" in desc, "email description missing 'Punkt' (spoken-form dot)"
    assert "at" in desc, "email description missing 'at' (spoken-form @)"
    assert "minus" in desc, "email description missing 'minus' (spoken-form hyphen)"


def test_caller_info_field_descriptions_first_name():
    """CallerInfo first_name description mentions phonetic approximation and null return."""
    from phonebot.models.caller_info import CallerInfo

    desc = CallerInfo.model_fields["first_name"].description
    assert "phonetically" in desc, "first_name description missing phonetic approximation note"
    assert "null" in desc.lower(), "first_name description missing 'return null' instruction"


def test_caller_info_field_descriptions_last_name():
    """CallerInfo last_name description mentions Doppel prefix convention."""
    from phonebot.models.caller_info import CallerInfo

    desc = CallerInfo.model_fields["last_name"].description
    assert "Doppel" in desc, "last_name description missing 'Doppel' prefix convention"


# ---------------------------------------------------------------------------
# EXT-02: CallerInfo docstring is the system prompt
# ---------------------------------------------------------------------------


def test_caller_info_docstring_is_system_prompt():
    """CallerInfo class docstring contains system prompt language (EXT-02)."""
    from phonebot.models.caller_info import CallerInfo

    assert CallerInfo.__doc__ is not None, "CallerInfo has no docstring"
    assert "extracting caller contact information" in CallerInfo.__doc__, (
        "CallerInfo docstring does not contain expected system prompt text"
    )


# ---------------------------------------------------------------------------
# Unit: transcribe_node loads cached transcript (mocked)
# ---------------------------------------------------------------------------


def test_transcribe_node_loads_cached_transcript(tmp_path):
    """transcribe_node returns transcript_text from a mock cached Deepgram JSON file."""
    from phonebot.pipeline.extract import transcribe_node

    # Create a fake Deepgram cache file
    fake_transcript = "Guten Tag, mein Name ist Müller."
    fake_json = {
        "metadata": {"request_id": "fake-test"},
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": fake_transcript,
                            "confidence": 0.99,
                            "words": [],
                        }
                    ]
                }
            ]
        },
    }
    cache_file = tmp_path / "call_test.json"
    cache_file.write_text(json.dumps(fake_json, ensure_ascii=False), encoding="utf-8")

    state = {
        "recording_id": "call_test",
        "transcript_text": None,
        "caller_info": None,
    }

    # Patch the TRANSCRIPT_DIR in extract module to use tmp_path
    import phonebot.pipeline.extract as extract_module

    with patch.object(extract_module, "TRANSCRIPT_DIR", tmp_path):
        result = asyncio.run(transcribe_node(state))

    assert "transcript_text" in result, "transcribe_node did not return transcript_text key"
    assert result["transcript_text"] == fake_transcript, (
        f"Expected '{fake_transcript}', got '{result['transcript_text']}'"
    )


# ---------------------------------------------------------------------------
# Unit: transcribe_node raises on missing cache
# ---------------------------------------------------------------------------


def test_transcribe_node_raises_on_missing_cache(tmp_path):
    """transcribe_node raises FileNotFoundError when cache is not present."""
    from phonebot.pipeline.extract import transcribe_node

    import phonebot.pipeline.extract as extract_module

    state = {
        "recording_id": "nonexistent_call",
        "transcript_text": None,
        "caller_info": None,
    }

    with patch.object(extract_module, "TRANSCRIPT_DIR", tmp_path):
        with pytest.raises(FileNotFoundError):
            asyncio.run(transcribe_node(state))


# ---------------------------------------------------------------------------
# QUAL-01: Integration test -- absent fields return null (requires ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set -- skipping live LLM test",
)
async def test_missing_field_returns_null():
    """QUAL-01: LLM returns null for fields not present in transcript (no hallucination).

    Uses a synthetic transcript that contains a name but no phone number or email.
    Verifies that phone_number and email are None (not hallucinated), and that
    first_name is extracted correctly.
    """
    from phonebot.pipeline.extract import extract_node

    state = {
        "recording_id": "test_no_contact",
        "transcript_text": (
            "Guten Tag, mein Name ist Max Mustermann. "
            "Ich habe eine Frage zum Mietrecht. "
            "Vielen Dank und auf Wiederhoren."
        ),
        "caller_info": None,
    }

    result = await extract_node(state)

    assert "caller_info" in result, "extract_node did not return caller_info key"
    info = result["caller_info"]

    assert info["phone_number"] is None, (
        f"Expected phone_number=None for transcript with no phone, got: {info['phone_number']}"
    )
    assert info["email"] is None, (
        f"Expected email=None for transcript with no email, got: {info['email']}"
    )
    assert info["first_name"] is not None, (
        "Expected first_name to be extracted ('Max'), but got None"
    )
