---
phase: 05-model-a-b-testing
plan: "01"
subsystem: model-registry
tags: [model-registry, langchain-ollama, ab-testing, extract-pipeline, cli]
dependency_graph:
  requires: [03-extraction-pipeline, 04-observability]
  provides: [model-registry, model-alias, parameterized-output-path]
  affects: [extract-pipeline, run-cli, compare-script]
tech_stack:
  added: [langchain-ollama==1.0.1]
  patterns: [model-registry-dict, colon-prefix-routing, filesystem-safe-alias]
key_files:
  created:
    - src/phonebot/models/model_registry.py
    - tests/test_model_registry.py
  modified:
    - src/phonebot/models/__init__.py
    - src/phonebot/pipeline/extract.py
    - run.py
    - tests/test_extract.py
    - tests/test_cli.py
    - pyproject.toml
    - uv.lock
decisions:
  - "model_registry.py uses colon-prefix routing: claude-* -> ChatAnthropic, ollama:<model> -> ChatOllama"
  - "ChatOllama created with validate_model_on_init=False to avoid live Ollama checks on instantiation"
  - "--output argument removed from run.py; output path derived from model_alias(args.model)"
  - "avg_latency_per_recording added to result payload for per-model latency comparison in D-13"
metrics:
  duration: "6m 10s"
  completed: "2026-03-27"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 7
---

# Phase 5 Plan 1: Model Registry and Pipeline Wiring Summary

**One-liner:** LangChain model registry routing `claude-*` to `ChatAnthropic` and `ollama:<model>` to `ChatOllama`, wired into `extract_node()` and `run.py` with model-specific output files.

## What Was Built

A model registry (`src/phonebot/models/model_registry.py`) that translates model name strings to the correct LangChain chat model class, enabling `extract_node()` to work with any registered provider without code changes.

**Registry routing logic:**
- `claude-*` prefix -> `ChatAnthropic(model=name)` (validates `ANTHROPIC_API_KEY` before instantiation)
- `ollama:<model>` prefix -> `ChatOllama(model=stripped_name, temperature=0, validate_model_on_init=False)` (strips `ollama:` prefix before passing to ChatOllama)
- Any other string -> `ValueError` with clear message showing supported prefixes

**Pipeline changes:**
- `extract.py`: replaced `ChatAnthropic(model=os.getenv(...))` with `get_model(os.getenv(...))` — 2-line diff, all else unchanged (PIPELINE singleton preserved, `method="json_schema"` preserved)
- `run.py`: removed `--output` arg, computes `outputs/results_{alias}.json` from `model_alias(args.model)`, adds `avg_latency_per_recording` to result payload

**`model_alias()` conversion:**
- `"ollama:llama3.2:3b"` -> `"ollama_llama3.2_3b"` (colons -> underscores)
- `"claude-sonnet-4-6"` -> `"claude-sonnet-4-6"` (unchanged)

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| `validate_model_on_init=False` for ChatOllama | Prevents live HTTP to Ollama server on model object creation; validates at inference time instead |
| Remove `--output` from CLI | Prevents accidental result overwrite when running multiple models; path derived deterministically from model name |
| Add `avg_latency_per_recording` to payload | Enables D-13 latency comparison in compare.py without Phoenix trace parsing |
| Mock `ainvoke` on `MagicMock` (not `AsyncMock`) for structured model | `with_structured_output()` returns a non-async wrapper whose `ainvoke` must be set as `AsyncMock` explicitly |

## Test Coverage

| Test File | Tests Added | Coverage |
|-----------|-------------|----------|
| `tests/test_model_registry.py` | 7 new | All registry paths: Claude routing, Ollama routing, prefix stripping, unknown prefix ValueError, missing API key ValueError, alias with colons, alias without colons |
| `tests/test_extract.py` | 1 new | `test_extract_node_uses_registry` — mocks `get_model`, verifies called with env var value |
| `tests/test_cli.py` | 1 new, 1 updated | `test_model_alias_in_output_path` added; `test_build_parser_has_all_args` updated to assert `--output` absent |

**Full suite result:** 68 passed, 1 skipped (live LLM test requires `ANTHROPIC_API_KEY`)

## Commits

| Hash | Task | Description |
|------|------|-------------|
| `706f191` | Task 1 | Install langchain-ollama and create model registry with tests |
| `dba2a3d` | Task 2 | Wire extract.py to registry and parameterize run.py output path |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed AsyncMock setup for structured model test**
- **Found during:** Task 2 verification
- **Issue:** Test `test_extract_node_uses_registry` failed with `TypeError: 'coroutine' object is not subscriptable` — `with_structured_output().ainvoke()` was set as `AsyncMock` at the wrong level (on the `MagicMock()` directly rather than on its `.ainvoke` attribute)
- **Fix:** Changed `mock_structured = AsyncMock(return_value=mock_caller_info)` to `mock_structured = MagicMock(); mock_structured.ainvoke = AsyncMock(return_value=mock_caller_info)` — correctly models the chain: `model.with_structured_output(...)` returns a sync object whose `ainvoke()` is async
- **Files modified:** `tests/test_extract.py`
- **Commit:** `dba2a3d`

## Known Stubs

None — all functionality is fully implemented and wired.

## Verification

```
uv run pytest tests/ -x -q
# 68 passed, 1 skipped

grep "get_model" src/phonebot/pipeline/extract.py
# from phonebot.models.model_registry import get_model
# model = get_model(os.getenv("PHONEBOT_MODEL", "claude-sonnet-4-6"))

grep "results_" run.py
# output_path = Path(f"outputs/results_{alias}.json")

grep "langchain-ollama" pyproject.toml
# "langchain-ollama>=1.0.1",

python -c "from phonebot.models.model_registry import get_model, model_alias; print('OK')"
# OK
```

## Self-Check: PASSED
