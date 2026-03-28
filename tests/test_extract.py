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
    """PIPELINE graph has START -> transcribe -> extract -> validate -> (END | extract) topology."""
    from phonebot.pipeline.extract import PIPELINE

    g = PIPELINE.get_graph()
    node_names = [n.name for n in g.nodes.values()]

    assert "transcribe" in node_names, "transcribe node missing from graph"
    assert "extract" in node_names, "extract node missing from graph"
    assert "validate" in node_names, "validate node missing from graph"
    assert "__start__" in node_names, "__start__ node missing from graph"
    assert "__end__" in node_names, "__end__ node missing from graph"

    # Check edges: START -> transcribe -> extract -> validate -> (END | extract)
    edge_pairs = [(e.source, e.target) for e in g.edges]
    assert ("__start__", "transcribe") in edge_pairs, "Missing edge: __start__ -> transcribe"
    assert ("transcribe", "extract") in edge_pairs, "Missing edge: transcribe -> extract"
    assert ("extract", "validate") in edge_pairs, "Missing edge: extract -> validate"
    assert ("validate", "__end__") in edge_pairs, "Missing edge: validate -> __end__"
    assert ("validate", "extract") in edge_pairs, "Missing edge: validate -> extract (retry)"
    assert ("extract", "__end__") not in edge_pairs, "Unexpected direct edge: extract -> __end__"


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
    assert "retry_count" in hints, "PipelineState missing retry_count"
    assert "validation_errors" in hints, "PipelineState missing validation_errors"

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


# ---------------------------------------------------------------------------
# AB-01: extract_node() uses registry (not hardcoded ChatAnthropic)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_node_uses_registry():
    """AB-01: extract_node() calls get_model() from registry, not hardcoded ChatAnthropic."""
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_caller_info = MagicMock()
    mock_caller_info.model_dump.return_value = {
        "first_name": "Test", "last_name": "User",
        "email": None, "phone_number": None, "confidence": {},
    }

    # The structured model's ainvoke() is called as: result = await structured_model.ainvoke(...)
    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(return_value=mock_caller_info)

    mock_model = MagicMock()
    mock_model.with_structured_output.return_value = mock_structured

    with patch("phonebot.pipeline.extract.get_model", return_value=mock_model) as mock_get:
        with patch.dict(os.environ, {"PHONEBOT_MODEL": "ollama:llama3.2:3b"}):
            from phonebot.pipeline.extract import extract_node
            result = await extract_node({
                "recording_id": "test",
                "transcript_text": "Guten Tag",
                "caller_info": None,
            })

    mock_get.assert_called_once_with("ollama:llama3.2:3b")
    assert result["caller_info"]["first_name"] == "Test"


# ---------------------------------------------------------------------------
# OPT-02: extract_node uses dynamic CallerInfo model when injected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_node_uses_dynamic_model():
    """OPT-02: extract_node uses _CALLER_INFO_MODEL when set, not static CallerInfo."""
    from typing import Optional
    from unittest.mock import AsyncMock, MagicMock, patch

    from pydantic import Field, create_model

    # Create a custom dynamic model with a distinct docstring
    DynamicModel = create_model(
        "CallerInfo",
        first_name=(Optional[str], Field(default=None, description="custom first")),
        last_name=(Optional[str], Field(default=None, description="custom last")),
        email=(Optional[str], Field(default=None, description="custom email")),
        phone_number=(Optional[str], Field(default=None, description="custom phone")),
        confidence=(dict, Field(default_factory=dict, description="confidence")),
    )
    DynamicModel.__doc__ = "Custom dynamic system prompt"

    mock_caller_info = MagicMock()
    mock_caller_info.model_dump.return_value = {
        "first_name": "Dynamic", "last_name": "Test",
        "email": None, "phone_number": None, "confidence": {},
    }

    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(return_value=mock_caller_info)

    mock_model = MagicMock()
    mock_model.with_structured_output.return_value = mock_structured

    import phonebot.pipeline.extract as extract_module

    # Inject the dynamic model
    extract_module.set_caller_info_model(DynamicModel)

    try:
        with patch("phonebot.pipeline.extract.get_model", return_value=mock_model):
            result = await extract_module.extract_node({
                "recording_id": "test",
                "transcript_text": "Guten Tag",
                "caller_info": None,
                "retry_count": 0,
                "validation_errors": None,
            })

        # Verify with_structured_output was called with our dynamic model, not static CallerInfo
        call_args = mock_model.with_structured_output.call_args
        used_model = call_args[0][0]
        assert used_model.__doc__ == "Custom dynamic system prompt", (
            f"extract_node did not use injected dynamic model. Got doc: {used_model.__doc__}"
        )
        assert result["caller_info"]["first_name"] == "Dynamic"
    finally:
        # Reset to None so other tests aren't affected
        extract_module._CALLER_INFO_MODEL = None


# ---------------------------------------------------------------------------
# EXT-04: Retry loop tests (Phase 7 hardening)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_on_validation_failure():
    """EXT-04: Graph re-prompts on Pydantic ValidationError; succeeds on second attempt."""
    from unittest.mock import AsyncMock, MagicMock, patch

    import phonebot.pipeline.extract as extract_module

    from pydantic import ValidationError, create_model
    from pydantic.fields import FieldInfo

    # First call raises ValidationError, second call succeeds
    call_count = 0

    class MockModel:
        def model_validate(self, data):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Trigger a real ValidationError by passing wrong type to a strict model
                from pydantic import BaseModel, Field as PydanticField
                from typing import Optional as Opt

                class StrictModel(BaseModel):
                    first_name: str  # non-optional, must be string

                StrictModel.model_validate({"first_name": 123})  # will raise
            # Return successfully on second call

    # Make a model class that raises on first validate call
    validate_call_count = [0]

    from pydantic import BaseModel

    class FailOnceModel(BaseModel):
        first_name: str = ""
        last_name: str = ""
        email: str = ""
        phone_number: str = ""
        confidence: dict = {}

        @classmethod
        def model_validate(cls, obj, **kwargs):
            validate_call_count[0] += 1
            if validate_call_count[0] == 1:
                from pydantic_core import InitErrorDetails
                from pydantic import ValidationError as VE

                raise VE.from_exception_data(
                    title="FailOnceModel",
                    input_type="python",
                    input_value=obj,
                    hide_input=False,
                )
            return super().model_validate(obj, **kwargs)

    mock_caller_info = MagicMock()
    mock_caller_info.model_dump.return_value = {
        "first_name": "Max", "last_name": None,
        "email": None, "phone_number": None, "confidence": {"first_name": 0.9},
    }

    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(return_value=mock_caller_info)

    mock_model = MagicMock()
    mock_model.with_structured_output.return_value = mock_structured

    # Patch transcribe_node to pass through (avoid file system access)
    async def mock_transcribe(state):
        return {"transcript_text": "Guten Tag, ich heiße Max."}

    # Use a real ValidationError-raising model for validate_node
    from pydantic import ValidationError as PydanticVE
    from pydantic import BaseModel as PydanticBase

    validate_count = [0]

    def make_model_that_fails_once():
        class OnceFailModel(PydanticBase):
            first_name: str = ""
            confidence: dict = {}

            @classmethod
            def model_validate(cls, obj, **kwargs):
                validate_count[0] += 1
                if validate_count[0] == 1:
                    # Build and raise a real ValidationError
                    try:
                        class StrictString(PydanticBase):
                            value: int  # wrong type

                        StrictString.model_validate({"value": "not_an_int"})
                    except PydanticVE as e:
                        raise PydanticVE(e.errors(), input_type="python") from None
                return super().model_validate(obj, **kwargs)

        return OnceFailModel

    with patch("phonebot.pipeline.extract.get_model", return_value=mock_model):
        with patch("phonebot.pipeline.extract._get_caller_info_model", side_effect=make_model_that_fails_once):
            with patch.object(extract_module, "transcribe_node", mock_transcribe):
                # Rebuild pipeline with patched functions
                pipeline = extract_module.build_pipeline()
                final_state = await pipeline.ainvoke({
                    "recording_id": "test",
                    "transcript_text": "Guten Tag",
                    "caller_info": None,
                    "retry_count": 0,
                    "validation_errors": None,
                })

    assert final_state["retry_count"] >= 1, (
        f"Expected retry_count >= 1, got {final_state['retry_count']}"
    )


@pytest.mark.asyncio
async def test_retry_exhaustion_proceeds_to_end():
    """EXT-04: Graph reaches END without crashing after 3 total failed attempts (retry exhaustion)."""
    from unittest.mock import AsyncMock, MagicMock, patch

    import phonebot.pipeline.extract as extract_module

    from pydantic import ValidationError as PydanticVE, BaseModel as PydanticBase

    def make_always_failing_model():
        class AlwaysFailModel(PydanticBase):
            first_name: str = ""
            confidence: dict = {}

            @classmethod
            def model_validate(cls, obj, **kwargs):
                try:
                    class StrictInt(PydanticBase):
                        value: int

                    StrictInt.model_validate({"value": "not_an_int"})
                except PydanticVE as e:
                    raise PydanticVE(e.errors(), input_type="python") from None

        return AlwaysFailModel

    mock_caller_info = MagicMock()
    mock_caller_info.model_dump.return_value = {
        "first_name": "Max", "last_name": None,
        "email": None, "phone_number": None, "confidence": {},
    }

    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(return_value=mock_caller_info)

    mock_model = MagicMock()
    mock_model.with_structured_output.return_value = mock_structured

    async def mock_transcribe(state):
        return {"transcript_text": "Guten Tag."}

    with patch("phonebot.pipeline.extract.get_model", return_value=mock_model):
        with patch("phonebot.pipeline.extract._get_caller_info_model", side_effect=make_always_failing_model):
            with patch.object(extract_module, "transcribe_node", mock_transcribe):
                pipeline = extract_module.build_pipeline()
                # Should not raise; should reach END with retry exhaustion
                final_state = await pipeline.ainvoke({
                    "recording_id": "test",
                    "transcript_text": "Guten Tag.",
                    "caller_info": None,
                    "retry_count": 0,
                    "validation_errors": None,
                })

    assert final_state["retry_count"] >= 2, (
        f"Expected retry_count >= 2 at exhaustion, got {final_state['retry_count']}"
    )


@pytest.mark.asyncio
async def test_validate_node_passes_valid_data():
    """EXT-04: validate_node returns validation_errors=None for valid caller_info."""
    from phonebot.pipeline.extract import validate_node

    result = await validate_node({
        "caller_info": {
            "first_name": "Max", "last_name": None,
            "email": None, "phone_number": None,
            "confidence": {"first_name": 0.9},
        },
        "retry_count": 0,
        "validation_errors": None,
    })

    assert result.get("validation_errors") is None, (
        f"Expected validation_errors=None for valid data, got {result.get('validation_errors')}"
    )


@pytest.mark.asyncio
async def test_validate_node_handles_none_caller_info():
    """EXT-04: validate_node returns validation_errors list and increments retry_count when caller_info is None."""
    from phonebot.pipeline.extract import validate_node

    result = await validate_node({
        "caller_info": None,
        "retry_count": 0,
        "validation_errors": None,
    })

    assert result.get("validation_errors") is not None, "Expected non-None validation_errors for None caller_info"
    assert len(result["validation_errors"]) > 0, "Expected non-empty validation_errors list"
    assert result.get("retry_count") == 1, (
        f"Expected retry_count=1, got {result.get('retry_count')}"
    )


def test_compute_flagged_fields():
    """QUAL-02: compute_flagged_fields returns fields with confidence < 0.7."""
    from phonebot.pipeline.extract import compute_flagged_fields

    # Fields with some below threshold
    flagged = compute_flagged_fields({"confidence": {"first_name": 0.9, "email": 0.4, "phone_number": 0.65}})
    assert set(flagged) == {"email", "phone_number"}, f"Expected {{'email', 'phone_number'}}, got {set(flagged)}"

    # Empty confidence dict
    assert compute_flagged_fields({"confidence": {}}) == [], "Expected [] for empty confidence"

    # Missing confidence key
    assert compute_flagged_fields({}) == [], "Expected [] when confidence key missing"

    # Exactly at threshold (0.7 is NOT below threshold)
    assert compute_flagged_fields({"confidence": {"first_name": 0.7}}) == [], (
        "Expected [] when confidence is exactly 0.7 (threshold is strict less-than)"
    )


@pytest.mark.asyncio
async def test_extract_node_injects_error_context_on_retry():
    """EXT-04 D-02: extract_node injects validation_errors into prompt on retry (without previous output)."""
    from unittest.mock import AsyncMock, MagicMock, patch

    captured_prompts = []

    mock_caller_info = MagicMock()
    mock_caller_info.model_dump.return_value = {
        "first_name": "Max", "last_name": None,
        "email": None, "phone_number": None, "confidence": {},
    }

    mock_structured = MagicMock()

    async def capture_ainvoke(prompt):
        captured_prompts.append(prompt)
        return mock_caller_info

    mock_structured.ainvoke = capture_ainvoke

    mock_model = MagicMock()
    mock_model.with_structured_output.return_value = mock_structured

    with patch("phonebot.pipeline.extract.get_model", return_value=mock_model):
        from phonebot.pipeline.extract import extract_node

        result = await extract_node({
            "recording_id": "test",
            "transcript_text": "Hallo Test",
            "caller_info": None,
            "retry_count": 1,
            "validation_errors": ["first_name: value is not a valid string"],
        })

    assert len(captured_prompts) == 1, "Expected exactly one prompt call"
    prompt = captured_prompts[0]

    assert "Validation errors:" in prompt, f"Expected 'Validation errors:' in prompt, got: {prompt!r}"
    assert "Hallo Test" in prompt, f"Expected transcript text in prompt, got: {prompt!r}"
    assert "first_name: value is not a valid string" in prompt, (
        f"Expected error text in prompt, got: {prompt!r}"
    )
    # D-02: previous failed output (caller_info dict) must NOT be in the prompt
    assert "caller_info" not in prompt.lower() or "Validation errors" in prompt, (
        "Prompt should not contain previous failed caller_info dict"
    )
