---
phase: 07-hardening
plan: 01
subsystem: extraction-pipeline
tags: [langgraph, retry-loop, validation, confidence-flagging, pydantic, tdd]
dependency_graph:
  requires: [06-02]
  provides: [validate_node, route_after_validate, compute_flagged_fields, retry_loop]
  affects: [run_pipeline, PipelineState, extract_node, prompts_confidence_description]
tech_stack:
  added: []
  patterns: [langgraph-conditional-edges, tdd-red-green, pydantic-validation-retry]
key_files:
  created: []
  modified:
    - src/phonebot/pipeline/extract.py
    - src/phonebot/prompts/__init__.py
    - src/phonebot/models/caller_info.py
    - tests/test_extract.py
decisions:
  - "validate_node uses try/except around model_validate() — catches Pydantic ValidationError to store error list in state"
  - "route_after_validate returns 'end' on pass OR retry_count >= 2 (3 total attempts max)"
  - "Error context on retry: transcript + validation error messages; previous failed output excluded (D-02)"
  - "CONFIDENCE_THRESHOLD = 0.7 — strict less-than comparison; 0.7 itself is not flagged"
  - "compute_flagged_fields operates on caller_info dict directly (reads confidence sub-dict)"
  - "run_pipeline seeds retry_count=0 and validation_errors=None in initial state"
metrics:
  duration: "~8 minutes"
  completed: "2026-03-28"
  tasks_completed: 1
  files_modified: 4
---

# Phase 07 Plan 01: Retry Loop and Confidence Flagging Summary

**One-liner:** LangGraph retry loop with Pydantic validate node (max 2 retries) and per-field confidence flagging at 0.7 threshold.

## What Was Built

Added EXT-04 (retry loop) and QUAL-02 (confidence flagging) to the extraction pipeline.

The graph topology changed from `START -> transcribe -> extract -> END` to `START -> transcribe -> extract -> validate -> (END | extract)`. The validate node catches Pydantic ValidationError and routes back to extract with error context (transcript + error messages) injected into state, up to 2 retries (3 total attempts). On retry exhaustion, the graph proceeds to END with partial/null caller_info without crashing.

`compute_flagged_fields()` reads the LLM-provided `confidence` dict from caller_info and returns field names where score < 0.7. The `run_pipeline()` result dict now includes a `flagged_fields` key.

The confidence field description in both `prompts/__init__.py` and `caller_info.py` was strengthened from "Omit keys for fields not attempted" to "REQUIRED: Provide a confidence score for EVERY field you extracted (non-null)" with a concrete example — fixing the root cause of empty confidence dicts observed in all 30 recordings.

## Commits

| Hash | Type | Description |
|------|------|-------------|
| f5eb80a | test | RED phase: 8 new failing tests for retry loop, exhaustion, validate node, flagged fields |
| 56629c8 | feat | GREEN phase: validate node, route_after_validate, compute_flagged_fields, updated extract_node and build_pipeline |

## Tasks

| Task | Name | Status | Commit |
|------|------|--------|--------|
| 1 | Add retry loop and confidence flagging to extract.py, fix confidence description | Complete | 56629c8 |

## Decisions Made

- `validate_node` uses `_get_caller_info_model().model_validate(state["caller_info"])` in try/except — consistent with the existing dynamic model injection pattern
- `route_after_validate` applies exit condition `retry_count >= 2` regardless of validation_errors — avoids infinite loop on repeated failure
- Error context prompt format: `{transcript}\n\nPrevious extraction attempt returned invalid output. Validation errors:\n- {error}\nRe-extract carefully...` — does NOT include previous caller_info dict (D-02)
- `CONFIDENCE_THRESHOLD = 0.7` is a module-level constant — easily tunable without code change

## Deviations from Plan

None — plan executed exactly as written.

## Acceptance Criteria Verified

- [x] `tests/test_extract.py` contains `def test_retry_on_validation_failure`
- [x] `tests/test_extract.py` contains `def test_retry_exhaustion_proceeds_to_end`
- [x] `tests/test_extract.py` contains `def test_validate_node_passes_valid_data`
- [x] `tests/test_extract.py` contains `def test_validate_node_handles_none_caller_info`
- [x] `tests/test_extract.py` contains `def test_compute_flagged_fields`
- [x] `tests/test_extract.py` contains `def test_extract_node_injects_error_context_on_retry`
- [x] `src/phonebot/pipeline/extract.py` contains `async def validate_node`
- [x] `src/phonebot/pipeline/extract.py` contains `def route_after_validate`
- [x] `src/phonebot/pipeline/extract.py` contains `def compute_flagged_fields`
- [x] `src/phonebot/pipeline/extract.py` contains `CONFIDENCE_THRESHOLD = 0.7`
- [x] `src/phonebot/pipeline/extract.py` contains `retry_count: int`
- [x] `src/phonebot/pipeline/extract.py` contains `validation_errors: Optional[list[str]]`
- [x] `src/phonebot/pipeline/extract.py` contains `add_conditional_edges`
- [x] `src/phonebot/pipeline/extract.py` contains `"retry": "extract"`
- [x] `src/phonebot/pipeline/extract.py` contains `flagged_fields`
- [x] `src/phonebot/prompts/__init__.py` contains `REQUIRED: Provide a confidence score`
- [x] `uv run python -m pytest tests/test_extract.py -x -q` exits 0 (17 passed, 1 skipped)
- [x] `uv run python -m pytest -q` exits 0 (97 passed, 1 skipped)

## Known Stubs

None — all functionality is wired to real data flow.

## Self-Check: PASSED
