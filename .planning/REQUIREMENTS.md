# Requirements: Phonebot Audio Entity Extraction Pipeline

**Defined:** 2026-03-26
**Core Value:** Accurate extraction of caller contact information from German phone bot recordings

## v1.0 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Transcription

- [x] **STT-01**: Pipeline transcribes all 30 German WAV recordings via Deepgram Nova-3 with `language="de"`
- [x] **STT-02**: Pipeline verifies smart_format behavior on German and documents which formatters activate
- [x] **STT-03**: Transcripts are cached to disk to avoid redundant Deepgram API calls during iteration

### Extraction

- [x] **EXT-01**: Pipeline extracts first_name, last_name, email, phone_number from each transcript via LLM structured output
- [x] **EXT-02**: Extraction uses Pydantic BaseModel with class docstring as system prompt and Field descriptions as per-field extraction instructions
- [x] **EXT-03**: Pipeline is orchestrated via LangGraph with typed state (transcribe -> extract -> validate flow)
- [x] **EXT-04**: LangGraph retry loop re-prompts LLM on Pydantic validation failure with error context
- [x] **EXT-05**: Extraction prompt explicitly handles German spoken-form phone numbers and email addresses

### Evaluation

- [x] **EVAL-01**: Evaluation harness computes per-field accuracy against ground truth for all 30 recordings
- [x] **EVAL-02**: Evaluation supports multiple acceptable values per field (ground truth arrays)
- [x] **EVAL-03**: Phone numbers are normalized via `phonenumbers` library (E.164) before comparison
- [x] **EVAL-04**: Unicode normalization (NFC) and case-insensitive comparison for name/email fields

### Observability

- [x] **OBS-01**: Arize Phoenix traces all LangGraph pipeline nodes with span-level visibility
- [x] **OBS-02**: Traces are tagged with prompt version for comparison across iterations

### Model Comparison

- [x] **AB-01**: Pipeline supports swappable LLM backends (at minimum Claude Sonnet 4.6 + one open-source model)
- [x] **AB-02**: A/B test results are visible in Phoenix with per-model accuracy comparison

### Prompt Optimization

- [x] **OPT-01**: GEPA optimizes extraction prompts offline against ground truth with train/validation split
- [x] **OPT-02**: Optimized prompt is externalized to file and loaded at pipeline startup

### Infrastructure

- [x] **INFRA-01**: Project uses `uv` for dependency management with Python 3.13
- [x] **INFRA-02**: Pipeline runs via CLI entrypoint with clear arguments

### Quality

- [x] **QUAL-01**: Extraction returns `None` (not hallucinated values) when field is not present in transcript
- [x] **QUAL-02**: Low-confidence extractions are flagged with uncertainty metadata

## Future Requirements

Deferred beyond this milestone.

### Streaming

- **STREAM-01**: Real-time transcription support for live phone calls

### Extensibility

- **EXTEND-01**: Support for additional entity types (address, company name)
- **EXTEND-02**: Multilingual support beyond German

### Production

- **PROD-01**: Active learning loop for flagging low-confidence extractions for human review
- **PROD-02**: API server endpoint for on-demand extraction

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Real-time/streaming transcription | Challenge uses pre-recorded files only; adds complexity with zero benefit |
| Web UI or API server | CLI pipeline is sufficient; evaluators run via terminal |
| Fine-tuning an LLM on 30 recordings | Overfitting risk; violates prompt engineering evaluation spirit |
| Custom German NER model (spaCy/HF) | LLM extraction outperforms classical NER for spoken-form input |
| Ensemble voting across models | Marginal benefit with 30 files; cost/complexity hides errors |
| Multilingual extension | All recordings are German; different STT model needed |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Complete |
| INFRA-02 | Phase 1 | Complete |
| EVAL-01 | Phase 1 | Complete |
| EVAL-02 | Phase 1 | Complete |
| EVAL-03 | Phase 1 | Complete |
| EVAL-04 | Phase 1 | Complete |
| STT-01 | Phase 2 | Complete |
| STT-02 | Phase 2 | Complete |
| STT-03 | Phase 2 | Complete |
| EXT-01 | Phase 3 | Complete |
| EXT-02 | Phase 3 | Complete |
| EXT-03 | Phase 3 | Complete |
| EXT-05 | Phase 3 | Complete |
| QUAL-01 | Phase 3 | Complete |
| OBS-01 | Phase 4 | Complete |
| OBS-02 | Phase 4 | Complete |
| AB-01 | Phase 5 | Complete |
| AB-02 | Phase 5 | Complete |
| OPT-01 | Phase 6 | Complete |
| OPT-02 | Phase 6 | Complete |
| EXT-04 | Phase 7 | Complete |
| QUAL-02 | Phase 7 | Complete |

**Coverage:**

- v1.0 requirements: 22 total
- Mapped to phases: 22
- Unmapped: 0

---
*Requirements defined: 2026-03-26*
*Last updated: 2026-03-28 after gap closure — all 22 requirements complete*
