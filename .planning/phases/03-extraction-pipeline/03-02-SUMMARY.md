---
phase: 03-extraction-pipeline
plan: "02"
subsystem: extraction-pipeline
tags: [run-py, results-json, rich-table, auto-evaluation, end-to-end]
dependency_graph:
  requires:
    - 03-01 (LangGraph extraction pipeline, run_pipeline function)
    - 01-foundation (evaluation harness: compute_metrics, load_ground_truth)
  provides:
    - Wired async run.py entrypoint invoking full extraction + evaluation
    - outputs/results.json with 30 entries and run metadata
    - Rich per-field accuracy table printed to console
  affects:
    - Phase 04 Phoenix tracing (will instrument the same run.py entrypoint)
    - Phase 05 A/B testing (--model flag already wired)
tech_stack:
  patterns:
    - async def main() with asyncio.run() at module level (Pitfall 3 prevention)
    - Lazy import of run_pipeline inside main() to avoid import-time side effects
    - Rich Table for per-field accuracy display
key_files:
  modified:
    - run.py (rewritten from scaffold to async pipeline entrypoint)
  runtime_output:
    - outputs/results.json (30 entries with caller_info, model metadata)
decisions:
  - "run.py discovers recording IDs from data/transcripts/call_*.json glob, not from recordings dir"
  - "Lazy import of run_pipeline inside main() avoids load_dotenv/langchain import-time issues"
  - "compute_metrics receives list[dict] directly from run_pipeline output — no transformation needed"
metrics:
  duration: "~4m (including 32s LLM extraction time)"
  completed: "2026-03-27"
  tasks: 2
  files: 1
  baseline_accuracy:
    first_name: "90%"
    last_name: "77%"
    email: "67%"
    phone_number: "97%"
    overall: "82%"
---

# Phase 03 Plan 02: Wire run.py End-to-End Summary

Wired `run.py` as async entrypoint that runs the LangGraph extraction pipeline on all 30 recordings, writes `outputs/results.json` with metadata, and auto-evaluates with a Rich per-field accuracy table. First baseline accuracy: **82% overall**.

## What Was Built

### Task 1: Wire run.py with async pipeline invocation and auto-evaluation

Rewrote `run.py` from sync scaffold to async entrypoint:

- `async def main()` with `asyncio.run(main())` at module level
- Discovers recording IDs from `data/transcripts/call_*.json` glob
- Invokes `await run_pipeline(recording_ids, model_name=args.model)` with concurrency=5
- Writes `outputs/results.json` with payload: `{model, total_recordings, duration_seconds, timestamp, results}`
- Auto-evaluates via `compute_metrics(results, ground_truth)` and prints Rich accuracy table

### Task 2: End-to-end verification (human checkpoint)

Ran `uv run python run.py` — extracted all 30 recordings in 31.9s via Claude Sonnet 4.6:

| Field | Accuracy |
|-------|----------|
| first_name | 90% |
| last_name | 77% |
| email | 67% |
| phone_number | 97% |
| **Overall** | **82%** |

User approved the baseline. QUAL-01 note: all 30 ground truth entries have both phone and email, so null-field handling was not exercised in this dataset (implementation handles nulls correctly per code review).

## Decisions Made

1. **Recording ID discovery from transcripts dir**: Uses `data/transcripts/call_*.json` glob rather than WAV files in recordings dir — transcripts are the actual input to the pipeline.

2. **Lazy import**: `from phonebot.pipeline.extract import run_pipeline` inside `main()` to avoid import-time `load_dotenv()`/langchain issues.

3. **Direct list[dict] to compute_metrics**: run_pipeline output format matches compute_metrics input — no transformation step needed.

## Deviations from Plan

None — plan executed as written.

## Known Stubs

None.

## Self-Check: PASSED

Files exist:
- run.py: FOUND (modified)
- outputs/results.json: FOUND (30 entries)

Commits exist:
- fb1fdfd: feat(03-02): wire run.py with async pipeline invocation and auto-evaluation
