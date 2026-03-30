"""Model registry for LangChain chat model routing (Phase 5).

Naming convention (per D-06):
    claude-*          -> ChatAnthropic(model=name)
    ollama:<model>    -> ChatOllama(model=<model>, temperature=0)

Usage:
    from phonebot.models.model_registry import get_model, model_alias
    llm = get_model("ollama:llama3.2:3b")
    alias = model_alias("ollama:llama3.2:3b")  # "ollama_llama3.2_3b"
"""
import os

from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama


def get_model(name: str):
    """Return a LangChain chat model for the given model name string.

    Per D-03: dict-style registry using LangChain native classes.
    Per D-06: colon-prefix convention for provider routing.
    Per D-08: fail fast with clear error on missing prerequisites.

    Args:
        name: Model identifier. "claude-sonnet-4-6" for Anthropic,
              "ollama:llama3.2:3b" for Ollama local.

    Returns:
        A LangChain BaseChatModel instance.

    Raises:
        ValueError: On unrecognized prefix or missing API key.
    """
    if name.startswith("claude"):
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise ValueError(
                "ANTHROPIC_API_KEY not set. Required for Claude models. "
                "Add it to your .env file."
            )
        return ChatAnthropic(
            model=name,
            timeout=60,
            max_retries=2,
        )
    elif name.startswith("ollama:"):
        ollama_model = name[len("ollama:"):]
        return ChatOllama(
            model=ollama_model,
            temperature=0,
            validate_model_on_init=False,
        )
    else:
        raise ValueError(
            f"Unrecognized model '{name}'. "
            "Supported prefixes: 'claude-*' (Anthropic), 'ollama:<model>' (Ollama local). "
            "Example: --model ollama:llama3.2:3b"
        )


def model_alias(model_name: str) -> str:
    """Convert model name to filesystem-safe alias (per D-10, Pattern 3).

    Replaces colons with underscores:
        "ollama:llama3.2:3b" -> "ollama_llama3.2_3b"
        "claude-sonnet-4-6"  -> "claude-sonnet-4-6" (unchanged)
    """
    return model_name.replace(":", "_")
