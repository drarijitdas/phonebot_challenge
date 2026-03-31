---
phase: 06-prompt-optimization
plan: "01"
subsystem: prompts, pipeline
tags: [prompt-externalization, dynamic-model, tdd, gepa-foundation]
dependency_graph:
  requires: [05-model-a-b-testing/05-01]
  provides: [06-02/gepa-optimizer]
  affects: [src/phonebot/pipeline/extract.py, src/phonebot/prompts/]
tech_stack:
  added: [pydantic.create_model]
  patterns: [factory-function, hot-swap-injection, tdd-red-green]
key_files:
  created:
    - src/phonebot/prompts/extraction_v1.json
    - tests/test_prompts.py
  modified:
    - src/phonebot/prompts/__init__.py
    - src/phonebot/pipeline/extract.py
    - tests/test_extract.py
decisions:
  - "build_caller_info_model() creates a new class per call (no shared state mutation) — GEPA iterations are fully isolated"
  - "confidence field excluded from JSON optimization surface per D-13 — always injected by factory"
  - "_CALLER_INFO_MODEL lazy-loaded from extraction_v1.json on first extract_node call — avoids module-level I/O at import time"
  - "static CallerInfo import retained in extract.py for existing tests that import it via the module"
metrics:
  duration: "~3 minutes"
  completed_date: "2026-03-28"
  tasks_completed: 2
  files_changed: 5
---

# Phase 06 Plan 01: Externalize Prompts and Wire Dynamic CallerInfo Summary

One-liner: Externalized CallerInfo prompts to extraction_v1.json via JSON prompt loading module and hot-swap injection API in extract_node for GEPA optimization.

## What Was Built

### Task 1: Prompt Loading Module + extraction_v1.json (TDD)

**RED:** Created `tests/test_prompts.py` with 9 tests covering all behavior (commit ca6b724).

**GREEN:** Implemented `src/phonebot/prompts/__init__.py` with three functions:
- `load_prompt(path)`: reads JSON prompt file, returns dict
- `build_caller_info_model(path)`: factory that creates a Pydantic class from JSON — sets `__doc__` to `system_prompt` (LangChain reads this as the structured output system message), wires field descriptions from JSON, always includes `confidence` field with `default_factory`
- `export_v1_prompt(path)`: exports current `CallerInfo` inline prompts to JSON, excluding `confidence`

Generated `src/phonebot/prompts/extraction_v1.json` by calling `export_v1_prompt()` on the existing `CallerInfo` class. (commit f51d3cf)

### Task 2: Dynamic Model Injection in extract_node

Modified `src/phonebot/pipeline/extract.py`:
- Added `_CALLER_INFO_MODEL: type | None = None` module-level state
- Added `set_caller_info_model(model_class)` — GEPA evaluator calls this to inject a candidate
- Added `_get_caller_info_model()` — lazy loader that falls back to `extraction_v1.json` on first call
- Modified `extract_node` to call `_get_caller_info_model()` at call time (not import time)
  - This means one compiled `PIPELINE` serves all GEPA iterations without rebuild

Added `test_extract_node_uses_dynamic_model` to `tests/test_extract.py` verifying that `with_structured_output` receives the injected model's class (not the static `CallerInfo` import). (commit 13b2fe9)

## Verification Results

```
uv run pytest tests/test_prompts.py tests/test_extract.py -x -v
  20 passed, 1 skipped (QUAL-01 requires ANTHROPIC_API_KEY)

uv run pytest tests/ -x
  86 passed, 1 skipped — zero regressions across all 8 test files
```

Acceptance criteria:
- extraction_v1.json exists with system_prompt + 4 fields (no confidence): PASSED
- build_caller_info_model() schema description == system_prompt: PASSED
- extract_node calls _get_caller_info_model() at call time: PASSED
- set_caller_info_model() injection test passes: PASSED
- Full suite: 86 passed, 0 failed

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 RED | ca6b724 | test(06-01): add failing tests for prompt loading module |
| 1 GREEN | f51d3cf | feat(06-01): prompt loading module with extraction_v1.json baseline |
| 2 | 13b2fe9 | feat(06-01): wire extract_node to use dynamic CallerInfo model |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — extraction_v1.json contains the full baseline prompts from the existing CallerInfo class. All data is wired.

## Self-Check: PASSED
