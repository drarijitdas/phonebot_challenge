"""Smoke tests for optimize.py plumbing (OPT-01).

Tests verify the structural correctness of the optimizer without making
real GEPA/LLM calls. The full integration test requires ANTHROPIC_API_KEY
and is run via `uv run python optimize.py` directly.
"""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def test_field_weights_sum_to_one():
    """Weighted per-field accuracy weights sum to ~1.0 (D-14)."""
    from optimize import compute_field_weights

    # Phase 5 baseline accuracy
    baseline = {
        "first_name": 0.90,
        "last_name": 0.767,
        "email": 0.667,
        "phone_number": 1.00,
    }
    weights = compute_field_weights(baseline)
    assert abs(sum(weights.values()) - 1.0) < 0.01, f"Weights don't sum to 1.0: {weights}"
    # All weights positive (floor applied to phone_number)
    for field, w in weights.items():
        assert w > 0, f"Weight for {field} is zero — floor not applied"


def test_field_weights_email_highest():
    """Email has highest weight (lowest baseline accuracy of non-perfect fields)."""
    from optimize import compute_field_weights

    baseline = {
        "first_name": 0.90,
        "last_name": 0.767,
        "email": 0.667,
        "phone_number": 1.00,
    }
    weights = compute_field_weights(baseline)
    assert weights["email"] > weights["last_name"] > weights["first_name"], (
        f"Expected email > last_name > first_name, got {weights}"
    )


def test_build_seed_candidate_has_five_keys():
    """Seed candidate for GEPA has 5 keys: system_prompt + 4 fields (D-13)."""
    from optimize import build_seed_candidate

    # Use actual extraction_v1.json
    v1_path = Path("src/phonebot/prompts/extraction_v1.json")
    if not v1_path.exists():
        pytest.skip("extraction_v1.json not found — run Plan 01 first")

    candidate = build_seed_candidate(v1_path)
    assert set(candidate.keys()) == {
        "system_prompt", "first_name", "last_name", "email", "phone_number"
    }
    # All values are non-empty strings
    for k, v in candidate.items():
        assert isinstance(v, str) and len(v) > 0, f"Empty or non-string value for {k}"


def test_save_optimized_prompt_roundtrips(tmp_path):
    """save_optimized_prompt writes valid JSON that load_prompt can read."""
    from optimize import save_optimized_prompt
    from phonebot.prompts import load_prompt

    candidate = {
        "system_prompt": "Test system prompt",
        "first_name": "Test first desc",
        "last_name": "Test last desc",
        "email": "Test email desc",
        "phone_number": "Test phone desc",
    }
    out_path = tmp_path / "test_opt.json"
    save_optimized_prompt(candidate, out_path)

    loaded = load_prompt(out_path)
    assert loaded["system_prompt"] == "Test system prompt"
    assert loaded["fields"]["first_name"] == "Test first desc"
    assert len(loaded["fields"]) == 4


def test_make_train_val_split_deterministic():
    """Train/val split with seed=42 is reproducible (D-11)."""
    from optimize import make_train_val_split

    ids = [f"call_{i:02d}" for i in range(1, 31)]
    train1, val1 = make_train_val_split(ids, n_train=20, seed=42)
    train2, val2 = make_train_val_split(ids, n_train=20, seed=42)

    assert train1 == train2, "Train split not deterministic"
    assert val1 == val2, "Val split not deterministic"
    assert len(train1) == 20
    assert len(val1) == 10
    assert set(train1) | set(val1) == set(ids), "Split doesn't cover all IDs"
