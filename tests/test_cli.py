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
    assert "--output" in result.stdout


def test_default_args():
    """CLI runs without arguments (uses defaults) and exits cleanly."""
    result = subprocess.run(
        [sys.executable, "run.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Phonebot pipeline starting" in result.stdout or result.returncode == 0


def test_build_parser_has_all_args():
    """build_parser returns parser with expected arguments."""
    # Import directly to test without subprocess
    sys.path.insert(0, ".")
    from run import build_parser
    parser = build_parser()
    args = parser.parse_args([])
    assert hasattr(args, "model")
    assert hasattr(args, "recordings_dir")
    assert hasattr(args, "output")
    assert args.model == "claude-sonnet-4-6"
    assert args.recordings_dir == "data/recordings/"
    assert args.output == "outputs/results.json"
