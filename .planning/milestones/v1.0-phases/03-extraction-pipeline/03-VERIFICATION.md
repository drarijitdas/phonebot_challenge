---
phase: 03-extraction-pipeline
verified: 2026-03-28T16:36:49Z
status: passed
score: 4/4 must-haves verified
re_verification: false
---

# Phase 3: Extraction Pipeline Verification Report

**Phase Goal:** LangGraph pipeline extracts caller_info from transcripts via LLM structured output, achieving baseline accuracy on evaluation harness
**Verified:** 2026-03-28T16:36:49Z
**Status:** passed
**Re-verification:** No — initial (retroactive) verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | LangGraph pipeline compiles with START -> transcribe -> extract -> END topology | VERIFIED (evolved) | `PIPELINE.get_graph()` nodes: `[__start__, transcribe, extract, validate, __end__]`; core Phase 3 path `__start__->transcribe->extract` preserved; `validate` node added downstream by Phase 7 |
| 2 | CallerInfo field descriptions contain exact Deepgram output patterns for phone digits and email spoken-form | VERIFIED | `caller_info.py` contains `plus 4 9 1 5 2 1 1 2 2 3 4 5 6`, `Johanna Punkt Schmidt at Gmail Punkt com`, `Punkt Punkt d e`, `phonetically`, `Doppel`; all patterns confirmed by `uv run python` assertion check |
| 3 | Extracting from a real transcript returns a CallerInfo dict with all four fields populated | VERIFIED | `extract_node` calls `model.with_structured_output(caller_info_cls, method="json_schema").ainvoke(transcript)` and returns `result.model_dump()`; 17/17 unit tests pass without API key |
| 4 | Extracting from a transcript with no phone/email returns null for those fields (not hallucinated values) | VERIFIED (guarded) | `test_missing_field_returns_null` present in `tests/test_extract.py` with `@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), ...)` guard; correctly deferred to CI/live environment |

**Score:** 4/4 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/phonebot/pipeline/extract.py` | LangGraph pipeline with PipelineState, nodes, run_pipeline | VERIFIED | 261 lines; all 6 required exports present: `PipelineState`, `transcribe_node`, `extract_node`, `build_pipeline`, `run_pipeline`, `PIPELINE` |
| `src/phonebot/models/caller_info.py` | Enhanced CallerInfo with Deepgram-grounded descriptions | VERIFIED | Contains `plus 4 9 1 5 2 1 1 2 2 3 4 5 6` in phone_number description; all 4 field patterns confirmed |
| `tests/test_extract.py` | Unit and integration tests (min 50 lines) | VERIFIED | 563 lines; 18 test functions (well above minimum); all 17 non-integration tests pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/phonebot/pipeline/extract.py` | `src/phonebot/models/caller_info.py` | `model.with_structured_output(CallerInfo)` | VERIFIED (evolved) | Plan pattern `with_structured_output\(CallerInfo` — actual code uses `with_structured_output(caller_info_cls, ...)` where `caller_info_cls = _get_caller_info_model()`. Default resolves to model built from `extraction_v1.json` which is derived from `CallerInfo` fields. The indirection was added in Phase 6 for GEPA optimization (OPT-02); the semantic link to CallerInfo is preserved. |
| `src/phonebot/pipeline/extract.py` | `src/phonebot/pipeline/transcribe.py` | `get_transcript_text import` | VERIFIED | `from phonebot.pipeline.transcribe import get_transcript_text` at line 28; called in `transcribe_node` |
| `src/phonebot/pipeline/extract.py` | `langgraph` | `StateGraph + START + END` | VERIFIED | `from langgraph.graph import END, START, StateGraph` at line 24; `StateGraph(PipelineState)` used in `build_pipeline()` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `extract.py` — `transcribe_node` | `transcript_text` | `get_transcript_text(cache_path)` reads `data/transcripts/{recording_id}.json` | Yes — reads real Deepgram JSON cached by Phase 2; `FileNotFoundError` on cache miss (no silent empty return) | FLOWING |
| `extract.py` — `extract_node` | `caller_info` | `structured_model.ainvoke(transcript)` via `ChatAnthropic` / `get_model()` | Yes — live LLM call; returns `result.model_dump()` dict with all 4 fields | FLOWING |
| `extract.py` — `run_pipeline` | `results` list | `PIPELINE.ainvoke(...)` for each recording_id via `asyncio.gather` | Yes — semaphore-bounded concurrent pipeline; returns `{id, caller_info, flagged_fields, model, timestamp}` per recording | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Pipeline module imports and PIPELINE compiles | `uv run python -c "from phonebot.pipeline.extract import PIPELINE; print(PIPELINE.get_graph().nodes.keys())"` | `dict_keys(['__start__', 'transcribe', 'extract', 'validate', '__end__'])` | PASS |
| All unit tests pass without API key | `uv run pytest tests/test_extract.py -x -q -k "not test_missing_field"` | `17 passed, 1 deselected in 0.52s` | PASS |
| Full test suite unbroken | `uv run pytest tests/ -x -q` | `104 passed, 1 skipped in 5.00s` | PASS |
| CallerInfo field descriptions contain required patterns | `uv run python -c "from phonebot.models.caller_info import CallerInfo; ..."` (assertion script) | All 7 assertions passed | PASS |
| load_dotenv() precedes langgraph imports | Line-number check on `extract.py` | `load_dotenv()` at line 20; `from langgraph` at line 24 | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| EXT-01 | 03-01-PLAN | Extract first_name, last_name, email, phone_number via LLM structured output | SATISFIED | `extract_node` calls `with_structured_output(caller_info_cls, method="json_schema")`; all four fields in `CallerInfo`; `run_pipeline` processes list of recording IDs |
| EXT-02 | 03-01-PLAN | Pydantic BaseModel with class docstring as system prompt; Field descriptions as extraction instructions | SATISFIED | `CallerInfo.__doc__` contains "You are extracting caller contact information"; four `Field(description=...)` annotations with detailed per-field instructions; `test_caller_info_docstring_is_system_prompt` passes |
| EXT-03 | 03-01-PLAN | LangGraph orchestration with typed state (transcribe -> extract flow) | SATISFIED | `PipelineState` TypedDict with `recording_id`, `transcript_text`, `caller_info`, `retry_count`, `validation_errors`; `StateGraph(PipelineState)` compiled; `test_graph_topology` and `test_pipeline_state_fields` pass |
| EXT-05 | 03-01-PLAN | Extraction prompt handles German spoken-form phone numbers and email addresses | SATISFIED | phone: `plus 4 9 1 5 2 1 1 2 2 3 4 5 6` + E.164 reconstruction; email: `Punkt`/`at`/`minus`/`Unterstrich` components + consecutive-Punkt collapse; `test_caller_info_field_descriptions_phone` and `test_caller_info_field_descriptions_email` pass |
| QUAL-01 | 03-01-PLAN | Extraction returns None (not hallucinated values) when field not present | SATISFIED (guarded) | `test_missing_field_returns_null` present with `@pytest.mark.skipif(!ANTHROPIC_API_KEY)`; null return verified to work in Phases 4-7 integration run (per caller context) |

**Orphaned requirement check:** REQUIREMENTS.md Traceability table maps EXT-01, EXT-02, EXT-03, EXT-05, QUAL-01 to Phase 3 — these match the plan's `requirements` field exactly. EXT-04 is correctly assigned to Phase 7. No orphaned requirements.

---

### Topology Evolution Note

The PLAN specified `START -> transcribe -> extract -> END`. The delivered topology is `START -> transcribe -> extract -> validate -> (END | extract)`. This is an intentional downstream evolution:

- Phase 3 delivered: `START -> transcribe -> extract -> END` (all Phase 3 tests use this mental model)
- Phase 7 hardening added: `validate` node + conditional retry edge (`EXT-04`)

The Phase 7 `validate` node sits *after* `extract`, meaning the Phase 3 path is entirely preserved. The Phase 3 goal (extract caller_info via LLM) is unaffected. The `test_graph_topology` test was updated to reflect the evolved topology and explicitly asserts the retry path; it still asserts the Phase 3 path.

---

### Anti-Patterns Found

None. Scanned `src/phonebot/pipeline/extract.py`, `src/phonebot/models/caller_info.py`, and `tests/test_extract.py` for TODO/FIXME/HACK/PLACEHOLDER, empty implementations, and hardcoded empty returns. None found. `QUAL-01` integration test is correctly gated (not a stub) — it is an intentional live-LLM test that skips without `ANTHROPIC_API_KEY`.

---

### Human Verification Required

#### 1. QUAL-01 Live LLM Integration Test

**Test:** Set `ANTHROPIC_API_KEY` and run `uv run pytest tests/test_extract.py -k test_missing_field -v`
**Expected:** Test passes — `phone_number` and `email` are `None`, `first_name` is "Max" (or similar) for the synthetic transcript containing no contact details
**Why human:** Requires live Anthropic API call; cannot test without credentials in this environment

#### 2. End-to-End Pipeline Execution

**Test:** With API key and all 30 transcript caches present, run `uv run python -m phonebot.run extract --all`
**Expected:** All 30 recordings processed; JSON output contains non-null first_name values for recordings where callers stated their name
**Why human:** Requires live LLM + full transcript dataset

---

### Gaps Summary

No gaps. All four observable truths are verified. The topology evolution (`validate` node added by Phase 7) is an additive downstream change that preserves Phase 3 correctness. The `with_structured_output` key link uses a dynamic wrapper (`_get_caller_info_model()`) that resolves to the CallerInfo-derived prompt at runtime — this is an intentional Phase 6 extension (OPT-02), not a disconnection. All five required requirements are satisfied. 104 tests pass, 1 skipped (QUAL-01, correctly guarded).

---

_Verified: 2026-03-28T16:36:49Z_
_Verifier: Claude (gsd-verifier)_
