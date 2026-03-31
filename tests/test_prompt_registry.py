"""Tests for the prompt version registry."""
import json
from pathlib import Path

import pytest

from phonebot.observability.prompt_registry import (
    register_prompt,
    update_accuracy,
    get_prompt_history,
    _hash_content,
)


@pytest.fixture
def tmp_registry(tmp_path):
    return tmp_path / "registry.json"


@pytest.fixture
def tmp_prompt(tmp_path):
    prompt_path = tmp_path / "test_prompt.json"
    prompt_path.write_text(json.dumps({
        "system_prompt": "Extract contact info",
        "fields": {"first_name": "The first name"},
    }))
    return prompt_path


class TestPromptRegistry:
    def test_hash_deterministic(self):
        h1 = _hash_content("hello world")
        h2 = _hash_content("hello world")
        assert h1 == h2

    def test_hash_different_content(self):
        h1 = _hash_content("version 1")
        h2 = _hash_content("version 2")
        assert h1 != h2

    def test_register_prompt(self, tmp_prompt, tmp_registry):
        record = register_prompt(tmp_prompt, "v1", tmp_registry)
        assert record["prompt_version"] == "v1"
        assert record["content_hash"] is not None
        assert record["accuracy"] is None

    def test_update_accuracy(self, tmp_prompt, tmp_registry):
        record = register_prompt(tmp_prompt, "v1", tmp_registry)
        content_hash = record["content_hash"]

        accuracy = {"per_field": {"first_name": 0.9}, "overall": 0.9}
        update_accuracy(content_hash, accuracy, tmp_registry)

        history = get_prompt_history(tmp_registry)
        assert history[0]["accuracy"]["overall"] == 0.9

    def test_get_prompt_history(self, tmp_prompt, tmp_registry):
        register_prompt(tmp_prompt, "v1", tmp_registry)

        # Modify and register again
        tmp_prompt.write_text(json.dumps({
            "system_prompt": "Updated prompt",
            "fields": {"first_name": "Updated"},
        }))
        register_prompt(tmp_prompt, "v2", tmp_registry)

        history = get_prompt_history(tmp_registry)
        assert len(history) == 2

    def test_empty_history(self, tmp_registry):
        history = get_prompt_history(tmp_registry)
        assert history == []

    def test_deduplication_by_content(self, tmp_prompt, tmp_registry):
        register_prompt(tmp_prompt, "v1", tmp_registry)
        register_prompt(tmp_prompt, "v1", tmp_registry)  # Same content

        history = get_prompt_history(tmp_registry)
        assert len(history) == 1  # Deduplicated by hash
