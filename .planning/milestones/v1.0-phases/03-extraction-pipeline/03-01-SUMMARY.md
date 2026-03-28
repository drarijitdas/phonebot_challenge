---
phase: 03-extraction-pipeline
plan: "01"
subsystem: extraction-pipeline
tags: [langgraph, langchain-anthropic, pydantic, extraction, caller-info]
dependency_graph:
  requires:
    - 02-transcription (cached transcript JSON files in data/transcripts/)
    - 01-foundation (CallerInfo model, evaluation harness)
  provides:
    - LangGraph extraction pipeline (extract.py)
    - Enhanced CallerInfo field descriptions grounded in Deepgram output patterns
    - Unit + integration tests for extraction pipeline
  affects:
    - run.py (Phase 03-02 will wire run_pipeline into CLI)
    - Phase 04 Phoenix tracing (hooks into PIPELINE.ainvoke)
tech_stack:
  added:
    - langgraph==1.1.3
    - langchain-anthropic==1.4.0
    - langchain-core==1.2.22 (transitive)
    - pytest-asyncio==1.3.0 (dev)
  patterns:
    - LangGraph StateGraph with TypedDict state
    - ChatAnthropic.with_structured_output(CallerInfo, method="json_schema")
    - asyncio.Semaphore for bounded concurrency
    - load_dotenv() before langchain imports (Pitfall 2 prevention)
    - result.model_dump() in extract_node (Pitfall 1 prevention)
key_files:
  created:
    - src/phonebot/pipeline/extract.py
    - tests/test_extract.py
  modified:
    - src/phonebot/models/caller_info.py (field descriptions)
    - pyproject.toml (langgraph, langchain-anthropic, pytest-asyncio, asyncio_mode)
    - uv.lock (dependency lock)
decisions:
  - "LangGraph StateGraph compiled once at import time (PIPELINE constant) — not rebuilt per recording"
  - "transcribe_node raises FileNotFoundError on cache miss — no API fallback in Phase 3 (Phase 2 ensures all 30 are cached)"
  - "extract_node sets PHONEBOT_MODEL via os.environ so env var is picked up at ChatAnthropic instantiation"
  - "asyncio_mode=auto in pytest config for transparent async test execution"
metrics:
  duration: "3m"
  completed: "2026-03-27"
  tasks: 3
  files: 5
---

# Phase 03 Plan 01: LangGraph Extraction Pipeline Summary

LangGraph pipeline (START -> transcribe -> extract -> END) with ChatAnthropic structured output and enhanced CallerInfo field descriptions grounded in real Deepgram spoken-form patterns from 30 German phone recordings.

## What Was Built

### Task 1: Install dependencies and enhance CallerInfo field descriptions

Installed `langgraph>=1.1.3`, `langchain-anthropic>=1.4.0` (project deps) and `pytest-asyncio>=0.25.0` (dev dep). Updated all four field descriptions in `CallerInfo` with exact Deepgram output patterns observed in the Phase 2 smart_format analysis:

- **phone_number**: exact `plus 4 9 1 5 2 1 1 2 2 3 4 5 6` pattern, E.164 reconstruction instruction
- **email**: `Punkt`/`at`/`minus` spoken-form components, consecutive Punkt collapse rule, lowercase instruction
- **first_name**: phonetic approximation note (e.g., García -> Gassia), letter-by-letter reconstruction
- **last_name**: Doppel prefix convention (Doppel-f = ff), letter-by-letter reconstruction

Class docstring unchanged (system prompt per D-11).

### Task 2: Create LangGraph extraction pipeline module

Created `src/phonebot/pipeline/extract.py` with:

- `PipelineState` TypedDict: `recording_id: str`, `transcript_text: Optional[str]`, `caller_info: Optional[dict]`
- `transcribe_node`: loads cached transcript via `get_transcript_text()`; raises `FileNotFoundError` on cache miss
- `extract_node`: `ChatAnthropic(model=os.getenv("PHONEBOT_MODEL", "claude-sonnet-4-6")).with_structured_output(CallerInfo, method="json_schema")`; returns `result.model_dump()`
- `build_pipeline()`: `START -> transcribe -> extract -> END` topology
- `PIPELINE = build_pipeline()`: module-level constant, built once at import
- `run_pipeline()`: async, semaphore-bounded (EXTRACT_CONCURRENCY env var), returns list of `{id, caller_info, model, timestamp}`

### Task 3: Create extraction pipeline tests

Created `tests/test_extract.py` with 9 tests (8 unit, 1 integration):

| Test | Requirement | Status |
|------|-------------|--------|
| test_graph_topology | EXT-03 | PASS |
| test_pipeline_state_fields | EXT-03 | PASS |
| test_caller_info_field_descriptions_phone | EXT-05 | PASS |
| test_caller_info_field_descriptions_email | EXT-05 | PASS |
| test_caller_info_field_descriptions_first_name | EXT-05 | PASS |
| test_caller_info_field_descriptions_last_name | EXT-05 | PASS |
| test_caller_info_docstring_is_system_prompt | EXT-02 | PASS |
| test_transcribe_node_loads_cached_transcript | Unit | PASS |
| test_transcribe_node_raises_on_missing_cache | Unit | PASS |
| test_missing_field_returns_null | QUAL-01 | SKIPPED (no API key) |

Full suite: 47 passed, 1 skipped (QUAL-01 integration test).

## Decisions Made

1. **PIPELINE constant**: StateGraph compiled once at module import time, not rebuilt per recording. Anti-pattern recommendation from research.

2. **transcribe_node raises on cache miss**: No Deepgram API fallback in Phase 3. Phase 2 guarantees all 30 recordings are cached. Simpler, more explicit error handling.

3. **PHONEBOT_MODEL env var**: `run_pipeline()` sets `os.environ["PHONEBOT_MODEL"]` before invoking so `extract_node` picks it up at `ChatAnthropic()` instantiation time.

4. **asyncio_mode = auto**: Added to `[tool.pytest.ini_options]` in pyproject.toml for transparent pytest-asyncio operation.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all code paths are fully implemented. QUAL-01 integration test is correctly guarded with `@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), ...)` and is not a stub — it is an intentional gated test.

## Self-Check: PASSED

Files exist:
- src/phonebot/pipeline/extract.py: FOUND
- src/phonebot/models/caller_info.py: FOUND (modified)
- tests/test_extract.py: FOUND
- pyproject.toml: FOUND (modified)

Commits exist:
- 7a7276b: feat(03-01): install langgraph/langchain-anthropic and update CallerInfo field descriptions
- 08e7063: feat(03-01): create LangGraph extraction pipeline module
- 4bd363e: test(03-01): create extraction pipeline unit and integration tests
