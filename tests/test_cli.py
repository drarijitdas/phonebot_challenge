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
