---
phase: 05-model-a-b-testing
plan: "02"
subsystem: compare-script
tags: [compare-script, rich-tables, ab-testing, per-field-accuracy, per-recording-diff]
dependency_graph:
  requires: [05-01]
  provides: [compare-script, comparison-json, ab-results-display]
  affects: [run-cli, outputs]
tech_stack:
  added: []
  patterns: [standalone-compare-script, rich-comparison-tables, glob-result-files]
key_files:
  created:
    - compare.py
    - tests/test_compare.py
  modified: []
decisions:
  - "compare.py is standalone (not a flag on run.py) per D-09 — clean separation between pipeline runs and comparison display"
  - "build_comparison() handles N models (not hardcoded to 2) — Pitfall 6 from RESEARCH.md avoided"
  - "Winner determined by rounded percentage to avoid floating-point tie false negatives"
metrics:
  duration: "~5m"
  completed: "2026-03-27"
  tasks_completed: 1
  tasks_total: 2
  files_created: 2
  files_modified: 0
status: checkpoint
checkpoint_task: 2
---

# Phase 5 Plan 2: Compare Script and A/B Verification Summary

**One-liner:** Standalone `compare.py` script with `load_result_files()`, `build_comparison()`, and `print_comparison()` rendering Rich per-field accuracy and per-recording diff tables with winner summary, all unit-tested.

**Status: Paused at Task 2 checkpoint (human-verify).**

## What Was Built

A standalone comparison script (`compare.py`) that reads per-model result files from `outputs/results_*.json`, computes side-by-side accuracy and latency metrics, prints Rich comparison tables to console, and writes `outputs/comparison.json`.

**Three public functions:**
- `load_result_files(pattern)` — globs and parses result files, returns sorted payloads list
- `build_comparison(payloads, ground_truth)` — computes per-model accuracy via `compute_metrics()`, builds per-recording diff table, determines winner (handles ties and N models)
- `print_comparison(comparison, con)` — renders Table 1 (per-field accuracy with green-bold best values), Table 2 (per-recording diffs with `[dim]null[/dim]`), and winner/tie summary line per UI-SPEC contract

**Error handling:**
- Fewer than 2 result files: prints red error and `sys.exit(1)`
- N models: fully supported — tables dynamically add columns per model

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Standalone `compare.py` (not `--compare` flag on run.py) | D-09 — clean separation between pipeline execution and results analysis |
| N-model support in `build_comparison()` | Research Pitfall 6 — hardcoding to exactly 2 models would break if 3+ result files exist |
| Winner uses `round(overall * 100)` for tie detection | Float comparison of raw accuracy can produce false non-ties; rounding to integer pct matches user-visible output |

## Test Coverage

| Test File | Tests Added | Coverage |
|-----------|-------------|----------|
| `tests/test_compare.py` | 8 new | load_result_files, per_field_accuracy, declares_winner, tie, per_recording_diff, writes_json, fewer_than_two_files_errors, handles_n_models |

**Full suite result:** 76 passed, 1 skipped

## Commits

| Hash | Task | Description |
|------|------|-------------|
| `77e2081` | Task 1 | feat(05-02): create compare.py comparison script with unit tests |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed N-model test assertion for tie case**
- **Found during:** Task 1 test run (GREEN phase)
- **Issue:** Test `test_compare_handles_n_models` asserted `winner["model"] in ("claude-sonnet-4-6", "third_model")` — but models A and C are tied at 87.5% so winner string is `"claude-sonnet-4-6 and third_model"` which is not in the tuple
- **Fix:** Changed assertion to check that both model names appear `in` the winner string, and that the losing model is excluded
- **Files modified:** `tests/test_compare.py`
- **Commit:** `77e2081`

## Checkpoint: Task 2 Awaiting

**Task 2:** Verify full A/B workflow end-to-end

This task requires running both model pipelines (`claude-sonnet-4-6` and `ollama:llama3.2:3b`) against live services, then verifying Phoenix traces. It cannot be automated — requires:
1. Active Anthropic API connection to run `uv run python run.py --model claude-sonnet-4-6`
2. Ollama server running at localhost:11434 to run `uv run python run.py --model ollama:llama3.2:3b`
3. Human visual verification of Phoenix UI at http://localhost:6006

See checkpoint details in SUMMARY for what to verify.

## Known Stubs

None — `compare.py` is fully implemented. The `outputs/comparison.json` is generated at runtime and is not a stub.

## Self-Check: PASSED

- [x] `compare.py` exists at project root
- [x] `tests/test_compare.py` exists with 8 test functions
- [x] Commit `77e2081` exists in git log
- [x] Full test suite: 76 passed, 1 skipped
