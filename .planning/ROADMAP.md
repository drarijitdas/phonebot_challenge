# Roadmap: Phonebot Audio Entity Extraction Pipeline

## Overview

Seven phases deliver a production-ready German phone bot entity extraction pipeline from scratch. The build order is dictated by data dependencies: evaluation metrics exist before the first pipeline run so accuracy is measurable from the start; transcription is verified against actual German output before extraction prompts are written; Phoenix tracing is live before A/B tests are run so trace data is available for comparison; GEPA optimizes the best model's prompt before the retry loop adds complexity. Each phase gate prevents building downstream components on a broken foundation.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - Project scaffold, Pydantic schema, and evaluation harness ready before any pipeline run
- [ ] **Phase 2: Transcription** - All 30 German recordings transcribed, cached, and smart_format behavior documented
- [ ] **Phase 3: Extraction Pipeline** - End-to-end extraction baseline with per-field accuracy score established
- [x] **Phase 4: Observability** - Arize Phoenix tracing live across all pipeline nodes (completed 2026-03-27)
- [ ] **Phase 5: Model A/B Testing** - Multi-model comparison with Phoenix trace data per model
- [ ] **Phase 6: Prompt Optimization** - GEPA offline optimization producing externalized, improved extraction prompt
- [ ] **Phase 7: Hardening** - Retry loop, confidence flagging, and final submission artifacts complete

## Phase Details

### Phase 1: Foundation
**Goal**: Project scaffold, CallerInfo schema, and evaluation harness exist so accuracy is measurable from the first pipeline run
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, EVAL-01, EVAL-02, EVAL-03, EVAL-04
**Success Criteria** (what must be TRUE):
  1. `uv run python run.py --help` prints CLI usage with documented arguments
  2. `CallerInfo` Pydantic model has all four fields with `Optional[str] = None` typing and class docstring
  3. Running `uv run python -m evaluation.metrics` against `data/ground_truth.json` prints per-field accuracy for a set of mock results (showing 0% baseline)
  4. Phone numbers in evaluation output are normalized to E.164 via `phonenumbers` before comparison — a correct extraction with different formatting scores as correct
  5. Multi-value ground truth fields (e.g., "Lisa Marie" or "Lisa-Marie") are handled — either acceptable value scores as correct
**Plans:** 1/2 plans executed
Plans:
- [x] 01-01-PLAN.md — Project scaffold, CallerInfo model, and CLI entrypoint
- [x] 01-02-PLAN.md — Evaluation harness with E.164 normalization, multi-value support, and tests

### Phase 2: Transcription
**Goal**: All 30 German WAV recordings are transcribed via Deepgram Nova-3, cached to disk, and smart_format behavior on German spoken-form phone/email tokens is documented
**Depends on**: Phase 1
**Requirements**: STT-01, STT-02, STT-03
**Success Criteria** (what must be TRUE):
  1. `data/transcripts/` contains 30 cached `.txt` or `.json` files, one per recording
  2. Re-running the pipeline does not make Deepgram API calls when transcript cache files exist
  3. At least 5 transcript files have been manually reviewed and a written note exists documenting whether smart_format produced formatted or spoken-form phone/email output
  4. The spoken-form behavior decision (e.g., "null zwei null eins..." vs "0201...") is documented and feeds directly into Phase 3 extraction prompt design
**Plans:** 1/2 plans executed
Plans:
- [x] 02-01-PLAN.md — Install deepgram-sdk, create async transcription module with JSON caching and unit tests
- [x] 02-02-PLAN.md — Run live transcription on 30 recordings, generate smart_format analysis report
**UI hint**: no

### Phase 3: Extraction Pipeline
**Goal**: A working LangGraph pipeline extracts all four fields from transcripts and produces a baseline per-field accuracy score against ground truth
**Depends on**: Phase 2
**Requirements**: EXT-01, EXT-02, EXT-03, EXT-05, QUAL-01
**Success Criteria** (what must be TRUE):
  1. `uv run python run.py` produces `outputs/results.json` with extracted fields for all 30 recordings
  2. LangGraph graph topology is `START → transcribe → extract → END` with typed `PipelineState`
  3. `CallerInfo` field descriptions explicitly handle German spoken-form phone numbers and email addresses (e.g., "null neun null", "punkt", "at")
  4. Fields absent from a transcript return `null` (not a hallucinated value) — verified against at least one recording where a field is known to be missing
  5. Per-field accuracy report prints to console: `first_name: X%, last_name: X%, email: X%, phone_number: X%`
**Plans:** 2/2 plans executed
Plans:
- [x] 03-01-PLAN.md — Install deps, enhance CallerInfo field descriptions, create LangGraph extract module and tests
- [x] 03-02-PLAN.md — Wire run.py with pipeline invocation, auto-evaluation, and Rich accuracy table

### Phase 4: Observability
**Goal**: Arize Phoenix is live and traces all 30 pipeline runs with span-level visibility for every LangGraph node
**Depends on**: Phase 3
**Requirements**: OBS-01, OBS-02
**Success Criteria** (what must be TRUE):
  1. Phoenix UI shows a "phonebot-extraction" project with 30 independent traces after a full pipeline run
  2. Each trace has distinct spans for the transcription node and the extraction node, with LLM latency visible
  3. Traces are tagged with a prompt version identifier — re-running with a different prompt produces traces with a different version tag
**Plans:** 2/2 plans complete
Plans:
- [x] 04-01-PLAN.md — Install Phoenix deps, create observability module, wire run.py and extract.py with tracing
- [x] 04-02-PLAN.md — Run full pipeline and verify 30 traces in Phoenix UI (checkpoint)
**UI hint**: yes

### Phase 5: Model A/B Testing
**Goal**: Pipeline supports swappable LLM backends and Phoenix shows side-by-side accuracy and trace data per model
**Depends on**: Phase 4
**Requirements**: AB-01, AB-02
**Success Criteria** (what must be TRUE):
  1. Running `uv run python run.py --model claude` and `uv run python run.py --model <other>` each complete without code changes
  2. Phoenix shows two sets of 30 traces tagged by model name, visually distinguishable in the dashboard
  3. A per-model accuracy comparison table is printed to console (or written to `outputs/`) showing which model performs better per field
**Plans:** 1/2 plans executed
Plans:
- [x] 05-01-PLAN.md — Model registry, extract.py wiring, and run.py output path parameterization
- [ ] 05-02-PLAN.md — Comparison script with Rich tables and live A/B verification checkpoint

### Phase 6: Prompt Optimization
**Goal**: GEPA optimizes the extraction system prompt offline against ground truth and writes an improved prompt to disk that the pipeline loads at startup
**Depends on**: Phase 5
**Requirements**: OPT-01, OPT-02
**Success Criteria** (what must be TRUE):
  1. `prompts/extraction_v1.txt` exists and the pipeline loads it at startup instead of an inline string
  2. GEPA runs on a 20-recording training subset with a 10-recording held-out validation set
  3. Running the pipeline with the GEPA-optimized prompt produces a measurably different (ideally higher) accuracy score than the Phase 3 baseline — delta is documented
**Plans**: TBD

### Phase 7: Hardening
**Goal**: LangGraph retry loop handles Pydantic validation failures gracefully, low-confidence extractions are flagged, and the final submission package is complete
**Depends on**: Phase 6
**Requirements**: EXT-04, QUAL-02
**Success Criteria** (what must be TRUE):
  1. When the LLM returns malformed structured output, the LangGraph graph re-prompts with error context rather than crashing — observable via a forced-failure test
  2. Extracted results include an uncertainty or confidence indicator field distinguishing high-confidence from low-confidence extractions
  3. `outputs/results.json` produced with the optimized prompt and best-performing model contains final per-field accuracy scores
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 2/2 | Complete |  |
| 2. Transcription | 2/2 | Complete |  |
| 3. Extraction Pipeline | 2/2 | Complete |  |
| 4. Observability | 2/2 | Complete   | 2026-03-27 |
| 5. Model A/B Testing | 1/2 | In Progress|  |
| 6. Prompt Optimization | 0/TBD | Not started | - |
| 7. Hardening | 0/TBD | Not started | - |
