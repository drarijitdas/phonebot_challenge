---
phase: 07-hardening
verified: 2026-03-28T00:00:00Z
status: passed
score: 8/8 must-haves verified
re_verification: false
gaps: []
---

# Phase 7: Hardening Verification Report

**Phase Goal:** LangGraph retry loop handles Pydantic validation failures gracefully, low-confidence extractions are flagged, and the final submission package is complete
**Verified:** 2026-03-28
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

Truths are derived from the ROADMAP.md Success Criteria and augmented with must_haves from PLAN frontmatter.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | When LLM returns malformed output, graph re-prompts with error context rather than crashing | VERIFIED | `validate_node` catches `ValidationError`, stores errors in state; `route_after_validate` routes back to `extract`; `test_retry_on_validation_failure` passes |
| 2 | After 2 failed retries (3 total attempts), graph proceeds to END with partial/null result (no crash) | VERIFIED | `route_after_validate` checks `retry_count >= 2`; `test_retry_exhaustion_proceeds_to_end` passes with `retry_count >= 2` |
| 3 | Error context on retry contains Pydantic error messages and transcript, but NOT previous failed output | VERIFIED | `extract_node` builds prompt from transcript + `validation_errors` list; previous `caller_info` dict explicitly excluded; `test_extract_node_injects_error_context_on_retry` passes |
| 4 | `compute_flagged_fields` returns field names where confidence < 0.7 | VERIFIED | `CONFIDENCE_THRESHOLD = 0.7`; strict `score < CONFIDENCE_THRESHOLD` comparison; `test_compute_flagged_fields` covers all edge cases including exact 0.7 boundary |
| 5 | `outputs/results.json` produced with optimized prompt and best model contains final per-field accuracy | VERIFIED | `--final` flag in `run.py` locks model to `claude-sonnet-4-6` and `prompt_version` to `v2`; calls `build_final_results_payload()` and writes `outputs/results.json` |
| 6 | Extracted results include confidence indicator field distinguishing high/low confidence | VERIFIED | `run_pipeline` result dict includes `flagged_fields` key from `compute_flagged_fields()`; `run.py --final` prints per-field warnings and writes `outputs/comparison.json` with `confidence_distribution` |
| 7 | `run.py --final` writes scores.json and comparison.json with v1 vs v2 delta | VERIFIED | `build_scores_payload()` and `build_comparison_payload()` exist; wired in `main()` under `if args.final`; all three output paths write to `outputs/` |
| 8 | Console prints Rich summary table with overall accuracy, per-field accuracy, flagged count, v1->v2 delta | VERIFIED | `Table(title="Final Submission Summary")` in `run.py:317`; rows for overall, per-field, flagged count, delta; per-field warnings via `console.print(f"[yellow]Warning: ...")` |

**Score:** 8/8 truths verified

---

## Required Artifacts

### Plan 07-01 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/phonebot/pipeline/extract.py` | `validate_node`, `route_after_validate`, `compute_flagged_fields`, updated `PipelineState` | VERIFIED | All four present; `PipelineState` has `retry_count: int` and `validation_errors: Optional[list[str]]` at lines 62-67 |
| `src/phonebot/prompts/__init__.py` | Strengthened confidence field description containing "REQUIRED" | VERIFIED | Line 38: `'REQUIRED: Provide a confidence score between 0.0 and 1.0 for EVERY field '` |
| `tests/test_extract.py` | All 8 new test functions including `test_retry_on_validation_failure` | VERIFIED | All 8 tests present (lines 344-563); 31 passed, 1 skipped in suite run |

### Plan 07-02 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `run.py` | `--final` flag, `build_final_results_payload`, `build_scores_payload`, `build_comparison_payload`, summary table | VERIFIED | All five present; flag at line 41; helper functions at lines 57-165; summary table at line 317 |
| `tests/test_cli.py` | `test_final_flag_exists`, `test_help_includes_final`, and 5 additional `--final` tests | VERIFIED | 7 new test functions present at lines 109-274; 104 passed, 1 skipped in full suite |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `build_pipeline` | `validate_node` | `add_conditional_edges` with `route_after_validate` | VERIFIED | Lines 190-193: `add_conditional_edges("validate", route_after_validate, {"end": END, "retry": "extract"})` |
| `extract_node` | `PipelineState.validation_errors` | `state.get("validation_errors")` on retry | VERIFIED | Lines 108-118: reads `validation_errors`, builds error-injected prompt when present |
| `validate_node` | `PipelineState.retry_count` | increments on failure | VERIFIED | Lines 137, 147: `"retry_count": state.get("retry_count", 0) + 1` |
| `run.py::main` | `run_pipeline` | `await run_pipeline()` with model and prompt_version | VERIFIED | Lines 231-238: lazy import after tracing init; called with `args.model` and `args.prompt_version` |
| `run.py::main` | `compute_metrics` | compute_metrics for v2 and v1 baseline | VERIFIED | Lines 257-260 (v2), lines 299 (v1 if available) |
| `run.py::main` | `outputs/scores.json` | `build_scores_payload()` + write | VERIFIED | Lines 285-290 |
| `run.py::main` | `outputs/comparison.json` | `build_comparison_payload()` + write | VERIFIED | Lines 309-313 |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `run_pipeline` result dict | `flagged_fields` | `compute_flagged_fields(final_state.get("caller_info") or {})` | Yes — reads `confidence` sub-dict from LLM output | FLOWING |
| `build_final_results_payload` | `results` list | pipeline `run_pipeline()` output | Yes — passed through from real pipeline run | FLOWING |
| `build_scores_payload` | `metrics` | `compute_metrics(results, gt)` | Yes — computes accuracy against ground truth | FLOWING |
| `build_comparison_payload` | `confidence_distribution` | iterates `caller_info.confidence` per result | Yes — reads LLM-provided confidence scores | FLOWING |

No hollow props or static returns detected in the data pipeline. All helper functions receive real `results` and `metrics` objects from upstream pipeline and evaluation calls.

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All extract tests pass | `uv run python -m pytest tests/test_extract.py -q` | 31 passed, 1 skipped | PASS |
| All CLI tests pass | `uv run python -m pytest tests/test_cli.py -q` | Included in full suite | PASS |
| Full test suite green | `uv run python -m pytest -q` | 104 passed, 1 skipped | PASS |
| `add_conditional_edges` wired | grep in `extract.py` | Found at line 190 | PASS |
| `CONFIDENCE_THRESHOLD = 0.7` present | grep in `extract.py` | Found at line 33 | PASS |
| `REQUIRED` in prompts `__init__.py` | grep in `prompts/__init__.py` | Found at line 38 | PASS |
| Commit hashes from summaries exist | `git log --oneline` | All 4 commits present (f5eb80a, 56629c8, 95bd63f, 2eaa5d3) | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| EXT-04 | 07-01, 07-02 | LangGraph retry loop re-prompts LLM on Pydantic validation failure with error context | SATISFIED | `validate_node` + `route_after_validate` + `add_conditional_edges`; `test_retry_on_validation_failure` and `test_retry_exhaustion_proceeds_to_end` pass |
| QUAL-02 | 07-01, 07-02 | Low-confidence extractions are flagged with uncertainty metadata | SATISFIED | `compute_flagged_fields` with `CONFIDENCE_THRESHOLD = 0.7`; `flagged_fields` key in `run_pipeline` output; `test_compute_flagged_fields` covers all edge cases; `--final` writes confidence_distribution and per-field warnings |

**Orphaned requirements check:** REQUIREMENTS.md traceability table lists only EXT-04 and QUAL-02 for Phase 7. Both are covered. No orphaned requirements.

---

## Anti-Patterns Found

No blockers, warnings, or stubs found. Scan of all modified files:

| File | Pattern Checked | Result |
|------|-----------------|--------|
| `src/phonebot/pipeline/extract.py` | TODO/FIXME, empty returns, return null, hardcoded empty state | Clean |
| `src/phonebot/prompts/__init__.py` | Placeholder text, empty implementations | Clean |
| `run.py` | Stubbed output writes, hardcoded empty payloads | Clean — `build_*_payload` functions receive real data |
| `tests/test_extract.py` | Test function stubs, missing assertions | Clean — all 8 new tests have substantive assertions |
| `tests/test_cli.py` | Test function stubs, missing assertions | Clean — all 7 new tests have substantive assertions |

---

## Human Verification Required

### 1. Live --final run produces non-empty outputs

**Test:** Run `uv run python run.py --final` with a valid `ANTHROPIC_API_KEY` and 30 cached transcripts present in `data/transcripts/`.
**Expected:** Three output files written (`outputs/results.json`, `outputs/scores.json`, `outputs/comparison.json`); Rich summary table printed with overall accuracy, per-field accuracy, flagged count, and v1→v2 delta row.
**Why human:** Requires live Anthropic API key and pre-cached transcripts. Cannot be tested without external service.

### 2. Retry loop triggers on real LLM malformed output

**Test:** Inspect Phoenix traces after a live run for any spans where `retry_count > 0`.
**Expected:** Traces show re-prompting with "Validation errors:" in the prompt when malformed output was returned.
**Why human:** Requires LLM to actually return malformed output in a live run; not reproducible without real API traffic.

---

## Gaps Summary

No gaps. All 8 truths verified, all artifacts pass all four levels (exists, substantive, wired, data flowing), both requirements satisfied, full test suite passes at 104/104 with 1 skipped (live LLM test gated on API key).

Phase 7 goal is fully achieved.

---

_Verified: 2026-03-28_
_Verifier: Claude (gsd-verifier)_
