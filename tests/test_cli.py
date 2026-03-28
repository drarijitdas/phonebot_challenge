"""CLI smoke tests."""
import subprocess
import sys


def test_help_exits_zero():
    """uv run python run.py --help exits 0 and prints usage."""
    result = subprocess.run(
        [sys.executable, "run.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--model" in result.stdout
    assert "--recordings-dir" in result.stdout


def test_default_args():
    """CLI runs without arguments (uses defaults) and exits cleanly.

    Without ANTHROPIC_API_KEY, the early model validation rejects the default
    claude model with a clear error (not a traceback). With the key, it starts
    the pipeline normally.
    """
    import os

    result = subprocess.run(
        [sys.executable, "run.py"],
        capture_output=True,
        text=True,
    )
    if os.getenv("ANTHROPIC_API_KEY"):
        assert result.returncode == 0
        assert "Phonebot pipeline starting" in result.stdout
    else:
        assert result.returncode == 1
        assert "ANTHROPIC_API_KEY" in result.stdout


def test_build_parser_has_all_args():
    """build_parser returns parser with expected arguments."""
    # Import directly to test without subprocess
    sys.path.insert(0, ".")
    from run import build_parser
    parser = build_parser()
    args = parser.parse_args([])
    assert hasattr(args, "model")
    assert hasattr(args, "recordings_dir")
    # --output is no longer an argument (AB-01: path computed from model alias)
    assert not hasattr(args, "output"), "--output should not exist; path computed from model alias"
    assert args.model == "claude-sonnet-4-6"
    assert args.recordings_dir == "data/recordings/"


# ---------------------------------------------------------------------------
# OBS-02: --prompt-version CLI argument (Phase 4)
# ---------------------------------------------------------------------------


def test_prompt_version_arg():
    """build_parser() returns parser that accepts --prompt-version with default 'v1'."""
    sys.path.insert(0, ".")
    from run import build_parser

    parser = build_parser()
    args = parser.parse_args([])
    assert hasattr(args, "prompt_version"), "--prompt-version arg missing from parser"
    assert args.prompt_version == "v1", f"Expected default 'v1', got '{args.prompt_version}'"


def test_prompt_version_arg_custom():
    """build_parser().parse_args(['--prompt-version', 'v2']) has prompt_version='v2'."""
    sys.path.insert(0, ".")
    from run import build_parser

    parser = build_parser()
    args = parser.parse_args(["--prompt-version", "v2"])
    assert args.prompt_version == "v2", f"Expected 'v2', got '{args.prompt_version}'"


def test_help_includes_prompt_version():
    """--prompt-version appears in --help output."""
    result = subprocess.run(
        [sys.executable, "run.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--prompt-version" in result.stdout, "--prompt-version not found in --help output"


# ---------------------------------------------------------------------------
# AB-01: model_alias in output path
# ---------------------------------------------------------------------------


def test_model_alias_in_output_path():
    """AB-01: run.py uses model_alias to compute output path."""
    from phonebot.models.model_registry import model_alias
    assert model_alias("claude-sonnet-4-6") == "claude-sonnet-4-6"
    assert model_alias("ollama:llama3.2:3b") == "ollama_llama3.2_3b"


# ---------------------------------------------------------------------------
# 07-02: --final flag (Phase 7 hardening, EXT-04, QUAL-02)
# ---------------------------------------------------------------------------


def test_final_flag_exists():
    """build_parser() accepts --final flag; default is False."""
    sys.path.insert(0, ".")
    from run import build_parser
    parser = build_parser()
    args = parser.parse_args(["--final"])
    assert args.final is True
    args2 = parser.parse_args([])
    assert args2.final is False


def test_help_includes_final():
    """--final appears in --help output."""
    result = subprocess.run(
        [sys.executable, "run.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--final" in result.stdout, "--final not found in --help output"


def test_final_sets_defaults():
    """--final flag parses without other args; final attribute is True."""
    sys.path.insert(0, ".")
    from run import build_parser
    parser = build_parser()
    args = parser.parse_args(["--final"])
    assert args.final is True


def test_final_results_json_has_flagged_fields():
    """build_final_results_payload() produces results list with flagged_fields key."""
    sys.path.insert(0, ".")
    from run import build_final_results_payload
    from datetime import timezone, datetime

    mock_results = [
        {
            "id": "call_01",
            "caller_info": {
                "first_name": "Max",
                "last_name": "Mustermann",
                "email": None,
                "phone_number": "+491234567890",
                "confidence": {"first_name": 0.95, "last_name": 0.85, "phone_number": 0.9},
            },
            "flagged_fields": ["email"],
            "model": "claude-sonnet-4-6",
            "timestamp": "2026-03-28T00:00:00Z",
        }
    ]
    payload = build_final_results_payload(mock_results, "claude-sonnet-4-6", "v2", 10.5)
    assert "results" in payload
    assert len(payload["results"]) == 1
    assert "flagged_fields" in payload["results"][0]
    assert payload["model"] == "claude-sonnet-4-6"
    assert payload["prompt_version"] == "v2"


def test_final_scores_json_format():
    """build_scores_payload() returns dict with required keys."""
    sys.path.insert(0, ".")
    from run import build_scores_payload

    metrics = {
        "per_field": {
            "first_name": 0.9,
            "last_name": 0.8,
            "email": 0.7,
            "phone_number": 0.95,
        },
        "overall": 0.84,
        "per_recording": [],
    }
    payload = build_scores_payload(metrics, "claude-sonnet-4-6", "v2")
    assert "model" in payload
    assert "prompt_version" in payload
    assert "per_field" in payload
    assert "overall" in payload
    assert "timestamp" in payload
    assert payload["model"] == "claude-sonnet-4-6"
    assert payload["prompt_version"] == "v2"
    assert payload["overall"] == 0.84


def test_final_comparison_json_format():
    """build_comparison_payload() returns dict with prompt_comparison and confidence_distribution."""
    sys.path.insert(0, ".")
    from run import build_comparison_payload

    v2_metrics = {
        "per_field": {
            "first_name": 0.9,
            "last_name": 0.8,
            "email": 0.7,
            "phone_number": 0.95,
        },
        "overall": 0.84,
        "per_recording": [],
    }
    v1_metrics = {
        "per_field": {
            "first_name": 0.87,
            "last_name": 0.75,
            "email": 0.65,
            "phone_number": 0.93,
        },
        "overall": 0.80,
        "per_recording": [],
    }
    results = [
        {
            "id": "call_01",
            "caller_info": {
                "first_name": "Max",
                "last_name": "Mustermann",
                "email": None,
                "phone_number": "+491234567890",
                "confidence": {"first_name": 0.95, "last_name": 0.85, "phone_number": 0.9},
            },
            "flagged_fields": [],
        }
    ]
    payload = build_comparison_payload(v2_metrics, v1_metrics, results, "claude-sonnet-4-6")
    assert "prompt_comparison" in payload
    pc = payload["prompt_comparison"]
    assert "v1" in pc
    assert "v2" in pc
    assert "delta" in pc
    assert "overall_v1" in pc
    assert "overall_v2" in pc
    assert "overall_delta" in pc
    assert "confidence_distribution" in payload
    cd = payload["confidence_distribution"]
    assert "high_confidence" in cd
    assert "low_confidence" in cd
    assert "no_confidence" in cd
    assert "total_fields" in cd
    assert payload["model"] == "claude-sonnet-4-6"
    assert "timestamp" in payload


def test_final_comparison_payload_no_v1():
    """build_comparison_payload() handles missing v1_metrics (v1 results not available)."""
    sys.path.insert(0, ".")
    from run import build_comparison_payload

    v2_metrics = {
        "per_field": {
            "first_name": 0.9,
            "last_name": 0.8,
            "email": 0.7,
            "phone_number": 0.95,
        },
        "overall": 0.84,
        "per_recording": [],
    }
    results = []
    payload = build_comparison_payload(v2_metrics, None, results, "claude-sonnet-4-6")
    assert "prompt_comparison" in payload
    pc = payload["prompt_comparison"]
    assert pc["v1"] is None
    assert pc["delta"] is None
    assert pc["overall_v1"] is None
    assert pc["overall_delta"] is None
