---
phase: 07-hardening
plan: 02
subsystem: cli
tags: [cli, final-mode, submission, output-files, rich-table, tdd]
dependency_graph:
  requires: [07-01]
  provides: [--final flag, build_final_results_payload, build_scores_payload, build_comparison_payload]
  affects: [run.py, tests/test_cli.py]
tech_stack:
  added: []
  patterns: [argparse-flag, rich-summary-table, json-output-files, tdd-red-green]
key_files:
  created: []
  modified:
    - run.py
    - tests/test_cli.py
decisions:
  - "--final locks model to claude-sonnet-4-6 and prompt_version to v2 by overriding args at parse time"
  - "Three helper functions (build_final_results_payload, build_scores_payload, build_comparison_payload) extracted from main() for testability"
  - "v1 baseline lookup checks prompt_version field — only uses baseline if it was actually a v1 run"
  - "Prompt file loading moved to before run_pipeline() call in main() — applies to all runs, not just --final"
metrics:
  duration: "~3 minutes"
  completed: "2026-03-28"
  tasks_completed: 1
  files_modified: 2
---

# Phase 07 Plan 02: Final Submission Flag Summary

**One-liner:** --final CLI flag writes results.json, scores.json, and comparison.json with v1/v2 delta and confidence distribution, plus a Rich summary table.

## What Was Built

Added `--final` flag to `run.py` that produces the complete final submission package (D-04, D-05).

When `--final` is passed:
1. Model is locked to `claude-sonnet-4-6` and prompt to `v2` (extraction_v2.json)
2. Pipeline runs normally, writes `outputs/results_{alias}.json` as before
3. Additionally writes three submission-specific output files:
   - `outputs/results.json` — canonical final results with `flagged_fields` per record
   - `outputs/scores.json` — per-field and overall accuracy with model, prompt_version, timestamp
   - `outputs/comparison.json` — v1 vs v2 prompt delta and confidence distribution across all fields
4. Prints a Rich `Final Submission Summary` table: model, prompt, overall accuracy, per-field accuracy, flagged count, v1→v2 delta
5. Prints per-field confidence warnings for each flagged field (D-03)

Three testable helper functions were extracted from `main()`:
- `build_final_results_payload()` — produces results.json payload
- `build_scores_payload()` — produces scores.json payload
- `build_comparison_payload()` — produces comparison.json payload with prompt comparison and confidence distribution

Prompt file loading was also added to `main()` before the `run_pipeline()` call — this ensures `--prompt-version v2` correctly loads `extraction_v2.json` prompts (for all runs, not just --final).

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 95bd63f | test | RED phase: failing tests for --final flag, output helpers, and payload builders |
| 2eaa5d3 | feat | GREEN phase: --final flag with results.json, scores.json, comparison.json and summary table |

## Tasks

| Task | Name | Status | Commit |
|------|------|--------|--------|
| 1 | Add --final flag to run.py with submission output files and summary table | Complete | 2eaa5d3 |

## Decisions Made

- `--final` overrides `args.model` and `args.prompt_version` immediately after parse — downstream code is unaware of --final, simplifying the logic
- Three helper functions were extracted for testability — this also makes the output formats independently verifiable without running the pipeline
- `build_comparison_payload()` returns `v1: None, delta: None` when v1 baseline is unavailable — graceful degradation per plan spec
- Prompt file loading added unconditionally to `main()` (not just in --final block) — allows any `--prompt-version` value to load the corresponding JSON file

## Deviations from Plan

### Auto-added improvements

**1. [Rule 2 - Missing Functionality] Prompt file loading added for all runs**
- **Found during:** Task 1, Step 3
- **Issue:** Plan Step 3 noted that current `main()` does not load the prompt JSON file. Without this, `--prompt-version v2` would be a tag string only, not actually loading the optimized prompts.
- **Fix:** Added prompt file loading block (using `build_caller_info_model` + `set_caller_info_model`) before `run_pipeline()` call, applicable to all runs.
- **Files modified:** run.py
- **Commit:** 2eaa5d3

## Acceptance Criteria Verified

- [x] run.py contains `"--final"`
- [x] run.py contains `action="store_true"`
- [x] run.py contains `scores.json`
- [x] run.py contains `comparison.json`
- [x] run.py contains `outputs/results.json`
- [x] run.py contains `prompt_comparison`
- [x] run.py contains `confidence_distribution`
- [x] run.py contains `Final Submission Summary`
- [x] run.py contains `flagged_fields`
- [x] run.py contains `Warning:`
- [x] tests/test_cli.py contains `def test_final_flag_exists`
- [x] tests/test_cli.py contains `def test_help_includes_final`
- [x] tests/test_cli.py contains `--final`
- [x] `uv run python -m pytest tests/test_cli.py -x -q` exits 0 (14 passed)
- [x] `uv run python -m pytest -q` exits 0 (104 passed, 1 skipped)

## Known Stubs

None — all output file writing is fully wired. Helper functions produce real payloads with correct structure.

## Self-Check: PASSED
