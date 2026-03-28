---
phase: 01-foundation
plan: 02
subsystem: evaluation
tags: [python, phonenumbers, unicodedata, pydantic, rich, pytest, tdd, e164, normalization]

# Dependency graph
requires:
  - 01-01 (src/phonebot/ package structure, CallerInfo model, uv project)
provides:
  - src/phonebot/evaluation/metrics.py with load_ground_truth, normalize_phone, normalize_text, normalize_value, matches_field, compute_metrics, FIELDS, __main__ entry point
  - tests/test_evaluation_metrics.py with 27 unit tests covering all public functions
  - tests/test_cli.py with 3 CLI smoke tests
  - outputs/eval_results.json (generated at runtime by __main__)
affects:
  - 02 (transcription phase outputs will be evaluated using compute_metrics)
  - 03 (pipeline phase will call compute_metrics in evaluation step)
  - 05 (A/B testing uses per_field accuracy from compute_metrics)
  - 06 (GEPA optimization uses compute_metrics as objective function)

# Tech tracking
tech-stack:
  added:
    - phonenumbers (E.164 normalization with DE region default — already installed in Plan 01)
    - unicodedata (stdlib NFC normalization)
  patterns:
    - TDD: test file written first (RED), implementation written second (GREEN), all 27 tests pass
    - Both-sides normalization: normalize_value called on both predicted and ground_truth in matches_field (prevents asymmetric comparison bugs)
    - casefold() over lower() for German eszett handling (Strasse == Straße after casefold)
    - Multi-value ground truth: isinstance(ground_truth_value, list) check enables accepting any acceptable spelling
    - model_dump() compatibility: hasattr(info, "model_dump") check handles CallerInfo objects and dicts uniformly
    - __main__ entry point writes outputs/eval_results.json with ensure_ascii=False for German umlaut preservation

key-files:
  created:
    - src/phonebot/evaluation/metrics.py
    - tests/test_evaluation_metrics.py
    - tests/test_cli.py
  modified: []

key-decisions:
  - "Both sides normalized in matches_field: normalize_value(field, predicted) AND normalize_value(field, gt_val) — prevents +49 152 11223456 vs +4915211223456 mismatch (Pitfall 2 from RESEARCH.md)"
  - "normalize_text uses casefold() not lower() — handles German eszett correctly (Straße -> strasse)"
  - "normalize_phone passes raw string through on NumberParseException — comparison will fail naturally without crashing"
  - "compute_metrics accepts both CallerInfo objects (via model_dump()) and plain dicts — forward-compatible with pipeline output"

patterns-established:
  - "Pattern 4: Evaluation harness — compute_metrics(results, ground_truth) -> {per_field, overall, per_recording}"
  - "Pattern 5: __main__ entry point — uv run python -m phonebot.evaluation.metrics shows baseline then writes JSON"
  - "Pattern 6: Both-sides normalization — normalize_value applied to both sides of comparison in matches_field"

requirements-completed: [EVAL-01, EVAL-02, EVAL-03, EVAL-04]

# Metrics
duration: 2min
completed: 2026-03-26
---

# Phase 1 Plan 2: Evaluation Harness Summary

**Evaluation harness with E.164 phone normalization, NFC+casefold text normalization, and multi-value ground truth support; 30 tests passing, 0% baseline confirmed**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-26T21:55:05Z
- **Completed:** 2026-03-26T21:57:22Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Built evaluation harness in `src/phonebot/evaluation/metrics.py` with 6 public functions: load_ground_truth, normalize_phone, normalize_text, normalize_value, matches_field, compute_metrics, plus FIELDS constant and `__main__` entry point
- E.164 phone normalization via `phonenumbers.parse(raw, "DE")` — handles "+49 152 11223456", "+4915211223456", and "015211223456" all normalizing to the same E.164 form
- Unicode NFC + casefold normalization for name/email — handles German umlauts, eszett, and international names (Garcia, Martinez, Schroeder, Mueller)
- Multi-value ground truth support — `isinstance(ground_truth_value, list)` enables any acceptable spelling to score as correct
- Both sides normalized in matches_field — prevents asymmetric comparison bugs (Pitfall 2)
- `__main__` entry point prints Rich table showing 0% baseline and writes `outputs/eval_results.json` with `ensure_ascii=False`
- Added CLI smoke tests verifying `run.py --help` output and `build_parser()` default values
- Full test suite: 30 tests passing (27 evaluation + 3 CLI)

## Task Commits

Each task was committed atomically:

1. **Task 1: Build evaluation metrics module with __main__ entry point** - `d0c8c12` (feat)
2. **Task 2: Add CLI smoke tests** - `0606b2b` (feat)

## Files Created/Modified

- `src/phonebot/evaluation/metrics.py` — Evaluation harness: load_ground_truth loads all 30 records, normalize_phone uses phonenumbers library with DE region, normalize_text uses NFC + casefold, matches_field handles scalar/list/null ground truth, compute_metrics returns per_field/overall/per_recording, __main__ prints Rich table
- `tests/test_evaluation_metrics.py` — 27 unit tests across 5 test classes: TestNormalizePhone, TestNormalizeText, TestMatchesField, TestLoadGroundTruth, TestComputeMetrics
- `tests/test_cli.py` — 3 CLI smoke tests: test_help_exits_zero, test_default_args, test_build_parser_has_all_args

## Decisions Made

- Both sides normalized in matches_field: normalize_value applied to both predicted and ground_truth_value — prevents asymmetric comparison where "+49 152 11223456" would not match "+4915211223456"
- casefold() chosen over lower() specifically for German eszett handling (Straße -> strasse, Strasse -> strasse, both equal)
- normalize_phone uses passthrough on NumberParseException — graceful degradation without crashing; comparison will fail naturally
- compute_metrics accepts CallerInfo objects via `hasattr(info, "model_dump")` check — forward-compatible with Phase 3 pipeline output

## Deviations from Plan

None — plan executed exactly as written. TDD flow followed: test file written first (RED: import error), implementation written second (GREEN: all 27 tests pass).

## Known Stubs

None — evaluation harness is fully functional with no placeholder values. The `__main__` entry point intentionally uses empty mock results to show 0% baseline; this is the designed behavior, not a stub.

## Self-Check: PASSED

- src/phonebot/evaluation/metrics.py: FOUND
- tests/test_evaluation_metrics.py: FOUND
- tests/test_cli.py: FOUND
- Commit d0c8c12: FOUND
- Commit 0606b2b: FOUND

---
*Phase: 01-foundation*
*Completed: 2026-03-26*
