---
phase: 05-model-a-b-testing
verified: 2026-03-27T21:30:35Z
status: human_needed
score: 11/12 must-haves verified
human_verification:
  - test: "Open Phoenix UI at http://localhost:6006 and filter traces by project"
    expected: "Two distinct sets of 30 traces each, one tagged model=claude-sonnet-4-6 and one tagged model=ollama:llama3.2:3b, visually distinguishable by model name in the span metadata panel"
    why_human: "Phoenix is an external UI — trace visibility and tag display require human eyes on the dashboard"
---

# Phase 5: Model A/B Testing Verification Report

**Phase Goal:** Pipeline supports swappable LLM backends and Phoenix shows side-by-side accuracy and trace data per model
**Verified:** 2026-03-27T21:30:35Z
**Status:** human_needed (all automated checks passed; one item requires visual Phoenix verification)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Running `uv run python run.py --model claude-sonnet-4-6` completes extraction using ChatAnthropic | VERIFIED | `extract.py` calls `get_model(os.getenv("PHONEBOT_MODEL"))` which routes `claude-*` to `ChatAnthropic`; `outputs/results_claude-sonnet-4-6.json` exists with 30 results |
| 2 | Running `uv run python run.py --model ollama:llama3.2:3b` completes extraction using ChatOllama | VERIFIED | Same registry routing path; `outputs/results_ollama_llama3.2_3b.json` exists with 30 results, model field = `ollama:llama3.2:3b` |
| 3 | An unrecognized model prefix raises ValueError with clear message | VERIFIED | `get_model("gpt-4")` raises `ValueError("Unrecognized model 'gpt-4'...")` — confirmed by spot-check |
| 4 | Each model run writes to a distinct output file (`results_{alias}.json`) | VERIFIED | `run.py` computes `alias = model_alias(args.model)`, writes `outputs/results_{alias}.json`; both files exist in `outputs/` |
| 5 | Missing ANTHROPIC_API_KEY for Claude models produces clear error | VERIFIED | Registry checks `os.getenv("ANTHROPIC_API_KEY")` and raises `ValueError("ANTHROPIC_API_KEY not set...")` before instantiation |
| 6 | `uv run python compare.py` with 2+ result files prints Rich per-field accuracy comparison table | VERIFIED | `compare.py` exists with `load_result_files()`, `build_comparison()`, `print_comparison()`; confirmed via `load_result_files("outputs/results_*.json")` returns 2 payloads with real 30-recording data |
| 7 | The comparison table highlights the best value per field in green bold | VERIFIED | `compare.py` line 161: `f"[green bold]{pct}[/green bold]"` applied when `values[mn] == best_val` |
| 8 | A per-recording differences table shows where models disagreed | VERIFIED | `build_comparison()` builds `diffs` list; `print_comparison()` renders "Per-Recording Differences" table; live comparison produced 120 diff rows |
| 9 | A winner summary line declares which model won with overall accuracy percentage | VERIFIED | `compare.py` line 220: `f"[bold green]Winner: {winner['model']} ({winner['overall_pct']}% overall accuracy)[/bold green]"`; live data shows Claude winner at 83% |
| 10 | `outputs/comparison.json` is written with programmatic comparison data | VERIFIED | File exists; contains `models`, `diffs`, `winner` keys with real data for both models |
| 11 | Running `compare.py` with fewer than 2 result files prints red error and exits 1 | VERIFIED | Guard at `compare.py` line 227-232: `sys.exit(1)` with red error message; spot-check confirmed |
| 12 | Phoenix shows two sets of 30 traces tagged by model name from both pipeline runs | ? HUMAN NEEDED | `using_attributes(metadata={"model": model_name, ...})` is wired in `extract.py` `process_one()` — code path is correct. Visual verification of Phoenix dashboard required |

**Score:** 11/12 truths verified (1 requires human)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/phonebot/models/model_registry.py` | Model factory routing model name strings to LangChain chat model classes | VERIFIED | 65 lines; exports `get_model` and `model_alias`; `ChatAnthropic`, `ChatOllama`, `validate_model_on_init=False`, `temperature=0` all present |
| `src/phonebot/pipeline/extract.py` | Extract node using registry instead of hardcoded ChatAnthropic | VERIFIED | Line 20: `from phonebot.models.model_registry import get_model`; line 63: `model = get_model(os.getenv("PHONEBOT_MODEL", "claude-sonnet-4-6"))` — direct `ChatAnthropic` import absent |
| `run.py` | CLI entrypoint writing model-specific result files | VERIFIED | Line 14: `from phonebot.models.model_registry import model_alias`; lines 57-58: `alias = model_alias(args.model)` / `Path(f"outputs/results_{alias}.json")`; `avg_latency_per_recording` in payload |
| `tests/test_model_registry.py` | Unit tests for model registry routing and error handling | VERIFIED | 7 test functions (meets min_lines: 40 at 126 lines); covers all routing paths and error cases |
| `compare.py` | Standalone comparison script reading `outputs/results_*.json` | VERIFIED | 248 lines (exceeds min 80); all three public functions present; Rich table titles, winner/tie strings, sys.exit(1) guard all confirmed |
| `tests/test_compare.py` | Unit tests for comparison logic | VERIFIED | 8 test functions (exceeds min 60 at 335 lines); covers all 8 behaviors from plan |
| `outputs/comparison.json` | Programmatic comparison output (generated at runtime) | VERIFIED | File exists; `models`, `diffs`, `winner` keys present with data for both Claude and Ollama |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/phonebot/pipeline/extract.py` | `src/phonebot/models/model_registry.py` | `get_model()` call in `extract_node()` | WIRED | Line 20 imports `get_model`; line 63 calls `get_model(os.getenv("PHONEBOT_MODEL", ...))` — pattern `get_model(os.getenv` confirmed |
| `run.py` | `src/phonebot/models/model_registry.py` | `model_alias()` for output path | WIRED | Line 14 imports `model_alias`; line 57 calls `alias = model_alias(args.model)`; used at lines 58 and 73 |
| `compare.py` | `src/phonebot/evaluation/metrics.py` | `compute_metrics()` and `load_ground_truth()` imports | WIRED | Line 18: `from phonebot.evaluation.metrics import FIELDS, compute_metrics, load_ground_truth`; all three used in `build_comparison()` and `main()` |
| `compare.py` | `outputs/results_*.json` | glob pattern for result files | WIRED | Line 23: default parameter `pattern: str = "outputs/results_*.json"`; line 28: `paths = sorted(glob.glob(pattern))`; live test confirmed 2 files loaded with 30 records each |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `compare.py` — `print_comparison()` | `comparison["models"]` | `build_comparison()` via `compute_metrics(payload["results"], ground_truth)` | Yes — live `outputs/results_*.json` files contain 30 real extraction results each; `comparison.json` shows `diffs: 120` rows | FLOWING |
| `run.py` — result table | `results` list | `run_pipeline()` in `extract.py` via `PIPELINE.ainvoke()` | Yes — `outputs/results_claude-sonnet-4-6.json` and `outputs/results_ollama_llama3.2_3b.json` each contain 30 non-empty records | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Unknown model prefix raises ValueError | `get_model("gpt-4")` raises with "Unrecognized model" | Confirmed via Python import check | PASS |
| `model_alias` converts colons | `model_alias("ollama:llama3.2:3b")` returns `"ollama_llama3.2_3b"` | Confirmed via import spot-check | PASS |
| compare loads real result files | `load_result_files("outputs/results_*.json")` returns 2 payloads, 30 recordings each | Confirmed — models: `claude-sonnet-4-6`, `ollama:llama3.2:3b` | PASS |
| compare exits 1 with < 2 files | `sys.exit(1)` guard triggered | Confirmed by direct simulation | PASS |
| compare produces winner | `build_comparison()` against live data returns `winner: {model: "claude-sonnet-4-6", overall_pct: 83, is_tie: false}` | Confirmed | PASS |
| Full test suite passes | `uv run pytest tests/ -q` | 76 passed, 1 skipped | PASS |
| Phoenix trace tagging wired | `using_attributes(metadata={"model": model_name})` in `process_one()` | Code present and wired at `extract.py` line 117 | PASS (code only; dashboard is human) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| AB-01 | 05-01-PLAN.md | Pipeline supports swappable LLM backends (Claude Sonnet 4.6 + one open-source model) | SATISFIED | `model_registry.py` routes `claude-*` to `ChatAnthropic` and `ollama:*` to `ChatOllama`; `extract.py` uses registry; both model result files exist with 30 records each; full test suite passes |
| AB-02 | 05-02-PLAN.md | A/B test results visible in Phoenix with per-model accuracy comparison | PARTIAL — code satisfied, Phoenix visual pending | `compare.py` fully implemented with Rich tables and `outputs/comparison.json`; Phoenix trace tagging is wired in code; actual dashboard display requires human verification |

**Note on REQUIREMENTS.md status:** `AB-01` is marked `[x]` (Complete) in REQUIREMENTS.md. `AB-02` is marked `[ ]` (Pending) — correctly reflecting that the human-gate checkpoint (05-02 Task 2) was not completed before this verification.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | None found |

No TODO/FIXME/placeholder/stub anti-patterns found in any phase file.

### Human Verification Required

#### 1. Phoenix Traces Tagged by Model Name

**Test:** After running both model pipelines (`uv run python run.py --model claude-sonnet-4-6` and `uv run python run.py --model ollama:llama3.2:3b`), open Phoenix at http://localhost:6006.

**Expected:**
- Two distinct groups of ~30 traces each, one per model run
- Each trace's metadata panel shows `model: claude-sonnet-4-6` or `model: ollama:llama3.2:3b` respectively
- Traces are visually filterable or sortable by model name in the Phoenix UI

**Why human:** Phoenix is an external observability UI. The `using_attributes(metadata={"model": model_name})` instrumentation is confirmed present in code, but whether the tags actually appear in the Phoenix dashboard and are rendered as distinguishable sets requires visual inspection of the live service.

### Gaps Summary

No automated gaps. All code artifacts exist, are substantive, and are wired. Both model pipelines produced real output files (30 recordings each). The comparison script reads and processes them correctly. The full test suite passes at 76 tests.

The single pending item is visual confirmation that Phoenix renders traces from both model runs with distinct model-name tags — this was always classified as a human-gate checkpoint in 05-02 Task 2 and cannot be programmatically verified.

---

_Verified: 2026-03-27T21:30:35Z_
_Verifier: Claude (gsd-verifier)_
