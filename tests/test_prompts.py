"""Tests for prompt loading module and dynamic CallerInfo construction.

Covers:
- OPT-02: Externalized prompt JSON with system_prompt and fields keys
- OPT-02: build_caller_info_model() factory produces correct Pydantic model
- OPT-02: load_prompt() returns dict with expected structure
- OPT-02: export_v1_prompt() writes valid JSON matching CallerInfo inline prompts
"""
import json
from pathlib import Path

import pytest

from phonebot.prompts import build_caller_info_model, export_v1_prompt, load_prompt
from phonebot.models.caller_info import CallerInfo


# ---------------------------------------------------------------------------
# export_v1_prompt: produces valid JSON with correct structure
# ---------------------------------------------------------------------------


def test_export_v1_creates_valid_json(tmp_path):
    """export_v1_prompt() writes JSON with 'system_prompt' and 'fields' keys.

    'fields' has exactly 4 keys (first_name, last_name, email, phone_number).
    'confidence' is excluded from the optimization surface.
    """
    output_path = tmp_path / "test_v1.json"
    export_v1_prompt(output_path)

    assert output_path.exists(), "export_v1_prompt() did not create the output file"

    with output_path.open(encoding="utf-8") as f:
        data = json.load(f)

    assert set(data.keys()) == {"system_prompt", "fields"}, (
        f"Expected keys {{'system_prompt', 'fields'}}, got {set(data.keys())}"
    )
    assert set(data["fields"].keys()) == {"first_name", "last_name", "email", "phone_number"}, (
        f"Expected 4 extraction field keys, got {set(data['fields'].keys())}"
    )
    assert "confidence" not in data["fields"], (
        "confidence should be excluded from the optimization surface in fields"
    )


def test_v1_system_prompt_matches_caller_info(tmp_path):
    """Exported system_prompt matches CallerInfo.__doc__.strip()."""
    output_path = tmp_path / "test_v1.json"
    export_v1_prompt(output_path)

    with output_path.open(encoding="utf-8") as f:
        data = json.load(f)

    expected = CallerInfo.__doc__.strip()
    assert data["system_prompt"] == expected, (
        f"system_prompt mismatch.\nExpected: {expected!r}\nGot: {data['system_prompt']!r}"
    )


def test_v1_field_descriptions_match(tmp_path):
    """Each field description in exported JSON matches CallerInfo.model_fields[name].description."""
    output_path = tmp_path / "test_v1.json"
    export_v1_prompt(output_path)

    with output_path.open(encoding="utf-8") as f:
        data = json.load(f)

    for name in ("first_name", "last_name", "email", "phone_number"):
        expected = CallerInfo.model_fields[name].description
        actual = data["fields"][name]
        assert actual == expected, (
            f"Field '{name}' description mismatch.\n"
            f"Expected: {expected!r}\nGot: {actual!r}"
        )


# ---------------------------------------------------------------------------
# build_caller_info_model: produces model with correct doc and fields
# ---------------------------------------------------------------------------

_MINIMAL_PROMPT = {
    "system_prompt": "You are a test extraction assistant.",
    "fields": {
        "first_name": "Caller's first name.",
        "last_name": "Caller's last name.",
        "email": "Caller's email address.",
        "phone_number": "Caller's phone number.",
    },
}


def _write_prompt(tmp_path: Path, payload: dict) -> Path:
    """Helper: write a prompt dict to a temp JSON file and return the path."""
    p = tmp_path / "prompt.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def test_build_caller_info_model_doc(tmp_path):
    """build_caller_info_model(path).__doc__ == data['system_prompt'] from the JSON."""
    path = _write_prompt(tmp_path, _MINIMAL_PROMPT)
    Model = build_caller_info_model(path)
    assert Model.__doc__ == _MINIMAL_PROMPT["system_prompt"], (
        f"Model.__doc__ mismatch.\nExpected: {_MINIMAL_PROMPT['system_prompt']!r}\n"
        f"Got: {Model.__doc__!r}"
    )


def test_build_caller_info_model_fields(tmp_path):
    """Built model has all 5 fields (4 extraction + confidence).

    Each extraction field description matches the JSON.
    """
    path = _write_prompt(tmp_path, _MINIMAL_PROMPT)
    Model = build_caller_info_model(path)

    for name in ("first_name", "last_name", "email", "phone_number"):
        assert name in Model.model_fields, f"Built model missing field '{name}'"
        actual_desc = Model.model_fields[name].description
        expected_desc = _MINIMAL_PROMPT["fields"][name]
        assert actual_desc == expected_desc, (
            f"Field '{name}' description mismatch in built model.\n"
            f"Expected: {expected_desc!r}\nGot: {actual_desc!r}"
        )

    assert "confidence" in Model.model_fields, "Built model missing 'confidence' field"


def test_build_caller_info_model_json_schema(tmp_path):
    """Built model's JSON schema has 'description' equal to system_prompt.

    This verifies with_structured_output compatibility (LangChain reads 'description'
    from the model's schema to construct the system message).
    """
    path = _write_prompt(tmp_path, _MINIMAL_PROMPT)
    Model = build_caller_info_model(path)
    schema = Model.model_json_schema()
    assert schema.get("description") == _MINIMAL_PROMPT["system_prompt"], (
        f"JSON schema 'description' field mismatch.\n"
        f"Expected: {_MINIMAL_PROMPT['system_prompt']!r}\n"
        f"Got: {schema.get('description')!r}"
    )


def test_build_caller_info_model_confidence_field(tmp_path):
    """Built model has confidence field with type dict and default_factory."""
    path = _write_prompt(tmp_path, _MINIMAL_PROMPT)
    Model = build_caller_info_model(path)

    assert "confidence" in Model.model_fields, "Built model missing 'confidence' field"
    confidence_field = Model.model_fields["confidence"]
    # Verify annotation includes dict
    import typing
    annotation = confidence_field.annotation
    # annotation should be dict or a dict-based type
    origin = getattr(annotation, "__origin__", annotation)
    assert origin is dict or annotation is dict, (
        f"confidence field annotation should be dict-based, got {annotation!r}"
    )
    # Verify default_factory is set (not a static default)
    assert confidence_field.default_factory is not None, (
        "confidence field should have default_factory, not a static default"
    )


# ---------------------------------------------------------------------------
# load_prompt: returns dict with expected structure
# ---------------------------------------------------------------------------


def test_load_prompt_returns_dict(tmp_path):
    """load_prompt(path) returns dict with 'system_prompt' and 'fields' keys."""
    path = _write_prompt(tmp_path, _MINIMAL_PROMPT)
    result = load_prompt(path)

    assert isinstance(result, dict), f"load_prompt should return dict, got {type(result)}"
    assert "system_prompt" in result, "load_prompt result missing 'system_prompt' key"
    assert "fields" in result, "load_prompt result missing 'fields' key"
    assert result["system_prompt"] == _MINIMAL_PROMPT["system_prompt"]
    assert result["fields"] == _MINIMAL_PROMPT["fields"]


# ---------------------------------------------------------------------------
# extraction_v1.json: file exists on disk after export
# ---------------------------------------------------------------------------


def test_v1_prompt_file_exists():
    """src/phonebot/prompts/extraction_v1.json exists on disk.

    This test verifies that extraction_v1.json was generated and committed
    alongside the prompts module. It does NOT generate the file — it just
    checks existence. Run export_v1_prompt() to create it if missing.
    """
    # Resolve relative to this test file's location
    prompts_dir = Path(__file__).resolve().parent.parent / "src" / "phonebot" / "prompts"
    v1_path = prompts_dir / "extraction_v1.json"
    assert v1_path.exists(), (
        f"extraction_v1.json not found at {v1_path}. "
        "Run: uv run python -c \"from phonebot.prompts import export_v1_prompt; "
        "from pathlib import Path; export_v1_prompt(Path('src/phonebot/prompts/extraction_v1.json'))\""
    )

    # Also verify it's valid JSON with correct top-level keys
    with v1_path.open(encoding="utf-8") as f:
        data = json.load(f)
    assert "system_prompt" in data, "extraction_v1.json missing 'system_prompt' key"
    assert "fields" in data, "extraction_v1.json missing 'fields' key"
