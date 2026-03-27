"""LangGraph extraction pipeline for CallerInfo from German phone bot transcripts.

Implements a START -> transcribe -> extract -> END graph that takes a recording ID,
loads its cached transcript, and extracts CallerInfo via LLM structured output.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from typing_extensions import TypedDict

from dotenv import load_dotenv

load_dotenv()  # Must precede langchain/langgraph imports (Pitfall 2)

from phonebot.models.model_registry import get_model  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402
from openinference.instrumentation import using_attributes  # noqa: E402

from phonebot.models.caller_info import CallerInfo  # noqa: E402
from phonebot.pipeline.transcribe import get_transcript_text  # noqa: E402

EXTRACT_CONCURRENCY = int(os.getenv("EXTRACT_CONCURRENCY", "5"))
TRANSCRIPT_DIR = Path("data/transcripts")


class PipelineState(TypedDict):
    recording_id: str               # e.g. "call_01"
    transcript_text: Optional[str]  # filled by transcribe node
    caller_info: Optional[dict]     # filled by extract node (CallerInfo.model_dump())


async def transcribe_node(state: PipelineState) -> dict:
    """Load transcript text from cache.

    Phase 2 ensures all 30 recordings are cached. If cache file does not exist,
    raises FileNotFoundError -- API fallback is not needed in Phase 3.
    """
    cache_path = TRANSCRIPT_DIR / f"{state['recording_id']}.json"
    if not cache_path.exists():
        raise FileNotFoundError(
            f"Transcript cache not found: {cache_path}. "
            "Run transcription pipeline first (Phase 2)."
        )
    text = get_transcript_text(cache_path)
    return {"transcript_text": text}


async def extract_node(state: PipelineState) -> dict:
    """Extract CallerInfo from transcript text using LLM structured output.

    Uses model registry get_model() with with_structured_output(CallerInfo) to parse
    the transcript into a typed CallerInfo instance. Model name is read from the
    PHONEBOT_MODEL env var (set by run_pipeline before invocation). Supports both
    ChatAnthropic (claude-*) and ChatOllama (ollama:<model>) via the registry.

    Returns CallerInfo as a plain dict (model_dump()) to avoid Pitfall 1.
    """
    model = get_model(os.getenv("PHONEBOT_MODEL", "claude-sonnet-4-6"))
    structured_model = model.with_structured_output(CallerInfo, method="json_schema")
    result: CallerInfo = await structured_model.ainvoke(state["transcript_text"])
    return {"caller_info": result.model_dump()}


def build_pipeline() -> object:
    """Build and compile LangGraph pipeline with START -> transcribe -> extract -> END topology."""
    builder = StateGraph(PipelineState)
    builder.add_node("transcribe", transcribe_node)
    builder.add_node("extract", extract_node)
    builder.add_edge(START, "transcribe")
    builder.add_edge("transcribe", "extract")
    builder.add_edge("extract", END)
    return builder.compile()


PIPELINE = build_pipeline()  # Build once at import time (anti-pattern: don't rebuild per recording)


async def run_pipeline(
    recording_ids: list[str],
    model_name: str = "claude-sonnet-4-6",
    concurrency: int = 5,
    prompt_version: str = "v1",
) -> list[dict]:
    """Run extraction pipeline concurrently over a list of recording IDs.

    Sets PHONEBOT_MODEL env var so extract_node picks up the model name.
    Bounded concurrency via asyncio.Semaphore (also respects EXTRACT_CONCURRENCY env var).
    Each ainvoke() is wrapped with using_attributes() inside process_one() to tag
    concurrent traces with recording_id, model, prompt_version, and run_timestamp
    (RESEARCH Pattern 2, Pitfall 3 — prevents context bleed across concurrent traces).

    Args:
        recording_ids: List of recording IDs (e.g. ["call_01", "call_02", ...])
        model_name: Anthropic model name to use for extraction.
        concurrency: Max concurrent pipeline invocations.
        prompt_version: Prompt version tag attached to every Phoenix trace.

    Returns:
        List of dicts with keys: id, caller_info, model, timestamp.
    """
    os.environ["PHONEBOT_MODEL"] = model_name
    effective_concurrency = int(os.getenv("EXTRACT_CONCURRENCY", str(concurrency)))
    semaphore = asyncio.Semaphore(effective_concurrency)

    async def process_one(recording_id: str) -> dict:
        async with semaphore:
            # using_attributes() MUST be inside process_one(), not at outer scope
            # (RESEARCH Pitfall 3 — prevents context bleed across concurrent ainvoke() calls)
            with using_attributes(
                metadata={
                    "recording_id": recording_id,
                    "model": model_name,
                    "prompt_version": prompt_version,
                    "run_timestamp": datetime.now(timezone.utc).isoformat(),
                },
                prompt_template_version=prompt_version,
            ):
                final_state = await PIPELINE.ainvoke(
                    {
                        "recording_id": recording_id,
                        "transcript_text": None,
                        "caller_info": None,
                    }
                )
        return {
            "id": recording_id,
            "caller_info": final_state["caller_info"],
            "model": model_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    tasks = [process_one(rid) for rid in recording_ids]
    return list(await asyncio.gather(*tasks))
