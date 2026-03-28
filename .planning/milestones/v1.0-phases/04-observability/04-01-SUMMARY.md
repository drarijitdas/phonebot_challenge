---
phase: 04-observability
plan: 01
subsystem: observability
tags: [phoenix, otel, tracing, langchain, instrumentation]
dependency_graph:
  requires:
    - 03-extraction-pipeline/03-02 (run_pipeline, extract.py, run.py)
  provides:
    - init_tracing() with persistent Phoenix server auto-start
    - shutdown_tracing() for pre-exit span flush
    - using_attributes() per-trace metadata tagging
    - --prompt-version CLI arg for A/B readiness
  affects:
    - 04-02 (live Phoenix verification uses init_tracing from this plan)
    - 05-ab-testing (prompt_version tag enables cross-run comparison in Phoenix)
tech_stack:
  added:
    - arize-phoenix 13.19.0
    - arize-phoenix-otel 0.15.0
    - openinference-instrumentation-langchain 0.1.61
  patterns:
    - Phoenix auto-start via px.launch_app(use_temp_dir=False) with active_session() idempotency guard
    - register(project_name=..., auto_instrument=True, batch=False) for CLI script span export
    - using_attributes() inside process_one() to anchor concurrent traces (prevents context bleed)
key_files:
  created:
    - tests/test_observability.py (9 unit tests, mock-based)
  modified:
    - src/phonebot/observability/__init__.py (init_tracing, shutdown_tracing)
    - run.py (init_tracing call, --prompt-version arg, trace count/URL output)
    - src/phonebot/pipeline/extract.py (prompt_version param, using_attributes wrap)
    - pyproject.toml (3 Phoenix dependencies added)
    - uv.lock (updated)
    - .env.example (PHOENIX_PROJECT added)
    - .gitignore (.phoenix/ added)
    - tests/test_cli.py (3 new --prompt-version tests)
decisions:
  - "Patch phoenix.otel.register at source (not import location) in tests — ensures importlib.reload picks up mock via 'from phoenix.otel import register'"
  - "module-level _tracer_provider global in observability/__init__.py stores register() return value for shutdown_tracing() to call force_flush()"
  - "using_attributes() placed inside process_one() not run_pipeline() scope per RESEARCH Pitfall 3 — prevents span context bleed across concurrent asyncio.gather tasks"
metrics:
  duration: ~7 minutes
  completed: 2026-03-27
  tasks: 2
  files: 8
---

# Phase 04 Plan 01: Phoenix Observability Integration Summary

**One-liner:** Arize Phoenix auto-start with LangChain auto-instrumentation, per-trace metadata tagging via using_attributes(), and --prompt-version CLI flag for A/B testing readiness.

## What Was Built

Installed three Phoenix packages (arize-phoenix, arize-phoenix-otel, openinference-instrumentation-langchain) and implemented the full observability layer:

1. **`src/phonebot/observability/__init__.py`**: `init_tracing()` starts Phoenix with persistent SQLite storage (`use_temp_dir=False`), is idempotent (checks `px.active_session()` before launch), reads `PHOENIX_PROJECT` env var for project name, calls `register(auto_instrument=True, batch=False)` for CLI-safe synchronous span export, and returns the session URL. `shutdown_tracing()` calls `force_flush()` on the stored tracer provider.

2. **`run.py`**: Added `--prompt-version` CLI arg (default `"v1"`). Calls `init_tracing()` before the lazy `run_pipeline` import (satisfies OTEL registration-before-import ordering). Prints prompt version in config echo, tracing initialized confirmation, trace count, and Phoenix URL after pipeline completion. Calls `shutdown_tracing()` before exit.

3. **`src/phonebot/pipeline/extract.py`**: Added `prompt_version: str = "v1"` to `run_pipeline()`. Imported `using_attributes` from `openinference.instrumentation`. Each `PIPELINE.ainvoke()` call inside `process_one()` is wrapped with `using_attributes(metadata={"recording_id", "model", "prompt_version", "run_timestamp"}, prompt_template_version=prompt_version)`.

## Test Results

- 9 unit tests in `tests/test_observability.py` — all mock-based, no live Phoenix server needed
- 3 new tests in `tests/test_cli.py` for `--prompt-version` argument
- Full test suite: **59 passed, 1 skipped** (skipped = live LLM integration test requiring API key)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed mock patch path for phoenix.otel.register**
- **Found during:** Task 1 TDD GREEN phase
- **Issue:** The plan's suggested patch path `"phoenix.otel.register"` needed to be used at source level (not `"phonebot.observability.register"`) because `importlib.reload()` re-executes `from phoenix.otel import register`, overwriting any `phonebot.observability.register` patch applied before reload.
- **Fix:** Structured tests to patch `"phoenix.otel.register"` at source, then call `importlib.reload(obs_module)` inside the patch context so the reloaded module picks up the mock via its `from phoenix.otel import register` import.
- **Files modified:** `tests/test_observability.py`
- **Commit:** 7cea2ab

**2. [Rule 2 - Missing critical functionality] TestShutdownTracingFlushes test fix**
- **Found during:** Task 1 TDD GREEN phase
- **Issue:** Test incorrectly passed `mock_tracer_provider` as the mock_register function itself, but `register()` is *called* to return the tracer provider — so the test needed `mock_register=MagicMock(return_value=mock_tracer_provider)`.
- **Fix:** Updated `_patched_obs` helper to accept a `mock_register` argument that is the callable mock (not the return value), and fixed `TestShutdownTracingFlushes` to create both the mock register callable and its return value.
- **Files modified:** `tests/test_observability.py`
- **Commit:** 7cea2ab

## Self-Check: PASSED

- FOUND: src/phonebot/observability/__init__.py
- FOUND: tests/test_observability.py
- FOUND: tests/test_cli.py
- FOUND: run.py
- FOUND: src/phonebot/pipeline/extract.py
- FOUND commit 7cea2ab: feat(04-01): install Phoenix deps
- FOUND commit 87bcf74: feat(04-01): wire run.py and extract.py
