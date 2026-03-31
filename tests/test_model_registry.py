"""Tests for model registry routing and error handling (Phase 5 AB-01).

Covers:
- AB-01: Registry routes 'claude-*' to ChatAnthropic
- AB-01: Registry routes 'ollama:<model>' to ChatOllama with stripped prefix
- AB-01: Registry raises ValueError on unrecognized model prefix
- AB-01: Claude registry raises ValueError on missing ANTHROPIC_API_KEY
- AB-01: model_alias() converts colons to underscores for filesystem-safe filenames
"""
import os
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# AB-01: get_model routes claude-* to ChatAnthropic
# ---------------------------------------------------------------------------


def test_get_model_claude_returns_chat_anthropic():
    """get_model('claude-sonnet-4-6') returns a ChatAnthropic instance with the correct model."""
    from langchain_anthropic import ChatAnthropic

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-fake"}):
        from phonebot.models.model_registry import get_model

        result = get_model("claude-sonnet-4-6")

    assert isinstance(result, ChatAnthropic), (
        f"Expected ChatAnthropic, got {type(result)}"
    )
    assert result.model == "claude-sonnet-4-6", (
        f"Expected model='claude-sonnet-4-6', got '{result.model}'"
    )


# ---------------------------------------------------------------------------
# AB-01: get_model routes ollama:* to ChatOllama
# ---------------------------------------------------------------------------


def test_get_model_ollama_returns_chat_ollama():
    """get_model('ollama:llama3.2:3b') returns a ChatOllama instance with temperature=0."""
    from langchain_ollama import ChatOllama

    from phonebot.models.model_registry import get_model

    result = get_model("ollama:llama3.2:3b")

    assert isinstance(result, ChatOllama), (
        f"Expected ChatOllama, got {type(result)}"
    )
    assert result.temperature == 0, (
        f"Expected temperature=0, got {result.temperature}"
    )


# ---------------------------------------------------------------------------
# AB-01: ollama: prefix is stripped before passing to ChatOllama
# ---------------------------------------------------------------------------


def test_get_model_ollama_strips_prefix():
    """ChatOllama instance from get_model('ollama:llama3.2:3b') has .model == 'llama3.2:3b'."""
    from phonebot.models.model_registry import get_model

    result = get_model("ollama:llama3.2:3b")

    assert result.model == "llama3.2:3b", (
        f"Expected model='llama3.2:3b' (prefix stripped), got '{result.model}'"
    )


# ---------------------------------------------------------------------------
# AB-01: Registry raises ValueError on unrecognized prefix
# ---------------------------------------------------------------------------


def test_get_model_unknown_prefix_raises():
    """get_model('gpt-4') raises ValueError with message containing 'Unrecognized model'."""
    from phonebot.models.model_registry import get_model

    with pytest.raises(ValueError, match="Unrecognized model"):
        get_model("gpt-4")


# ---------------------------------------------------------------------------
# AB-01: Claude registry raises on missing ANTHROPIC_API_KEY
# ---------------------------------------------------------------------------


def test_get_model_claude_missing_api_key_raises():
    """get_model('claude-sonnet-4-6') raises ValueError when ANTHROPIC_API_KEY is not set."""
    from phonebot.models.model_registry import get_model

    # Remove the key if it exists
    env_without_key = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    with patch.dict(os.environ, env_without_key, clear=True):
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            get_model("claude-sonnet-4-6")


# ---------------------------------------------------------------------------
# AB-01: model_alias replaces colons with underscores
# ---------------------------------------------------------------------------


def test_model_alias_colon():
    """model_alias('ollama:llama3.2:3b') returns 'ollama_llama3.2_3b'."""
    from phonebot.models.model_registry import model_alias

    result = model_alias("ollama:llama3.2:3b")
    assert result == "ollama_llama3.2_3b", (
        f"Expected 'ollama_llama3.2_3b', got '{result}'"
    )


def test_model_alias_no_colon():
    """model_alias('claude-sonnet-4-6') returns 'claude-sonnet-4-6' unchanged."""
    from phonebot.models.model_registry import model_alias

    result = model_alias("claude-sonnet-4-6")
    assert result == "claude-sonnet-4-6", (
        f"Expected 'claude-sonnet-4-6' unchanged, got '{result}'"
    )
