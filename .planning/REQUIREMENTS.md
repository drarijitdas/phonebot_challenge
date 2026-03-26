# Requirements: Phonebot Audio Entity Extraction Pipeline

**Defined:** 2026-03-26
**Core Value:** Accurate extraction of caller contact information from German phone bot recordings

## v1.0 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Transcription

- [ ] **STT-01**: Pipeline transcribes all 30 German WAV recordings via Deepgram Nova-3 with `language="de"`
- [ ] **STT-02**: Pipeline verifies smart_format behavior on German and documents which formatters activate
- [ ] **STT-03**: Transcripts are cached to disk to avoid redundant Deepgram API calls during iteration

### Extraction

- [ ] **EXT-01**: Pipeline extracts first_name, last_name, email, phone_number from each transcript via LLM structured output
- [ ] **EXT-02**: Extraction uses Pydantic BaseModel with class docstring as system prompt and Field descriptions as per-field extraction instructions
- [ ] **EXT-03**: Pipeline is orchestrated via LangGraph with typed state (transcribe -> extract -> validate flow)
- [ ] **EXT-04**: LangGraph retry loop re-prompts LLM on Pydantic validation failure with error context
- [ ] **EXT-05**: Extraction prompt explicitly handles German spoken-form phone numbers and email addresses

### Evaluation

- [ ] **EVAL-01**: Evaluation harness computes per-field accuracy against ground truth for all 30 recordings
- [ ] **EVAL-02**: Evaluation supports multiple acceptable values per field (ground truth arrays)
- [ ] **EVAL-03**: Phone numbers are normalized via `phonenumbers` library (E.164) before comparison
- [ ] **EVAL-04**: Unicode normalization (NFC) and case-insensitive comparison for name/email fields

### Observability

- [ ] **OBS-01**: Arize Phoenix traces all LangGraph pipeline nodes with span-level visibility
- [ ] **OBS-02**: Traces are tagged with prompt version for comparison across iterations

### Model Comparison

- [ ] **AB-01**: Pipeline supports swappable LLM backends (at minimum Claude Sonnet 4.6 + one open-source model)
- [ ] **AB-02**: A/B test results are visible in Phoenix with per-model accuracy comparison

### Prompt Optimization

- [ ] **OPT-01**: GEPA optimizes extraction prompts offline against ground truth with train/validation split
- [ ] **OPT-02**: Optimized prompt is externalized to file and loaded at pipeline startup

### Infrastructure

- [ ] **INFRA-01**: Project uses `uv` for dependency management with Python 3.13
- [ ] **INFRA-02**: Pipeline runs via CLI entrypoint with clear arguments

### Quality

- [ ] **QUAL-01**: Extraction returns `None` (not hallucinated values) when field is not present in transcript
- [ ] **QUAL-02**: Low-confidence extractions are flagged with uncertainty metadata

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
| STT-01 | -- | Pending |
| STT-02 | -- | Pending |
| STT-03 | -- | Pending |
| EXT-01 | -- | Pending |
| EXT-02 | -- | Pending |
| EXT-03 | -- | Pending |
| EXT-04 | -- | Pending |
| EXT-05 | -- | Pending |
| EVAL-01 | -- | Pending |
| EVAL-02 | -- | Pending |
| EVAL-03 | -- | Pending |
| EVAL-04 | -- | Pending |
| OBS-01 | -- | Pending |
| OBS-02 | -- | Pending |
| AB-01 | -- | Pending |
| AB-02 | -- | Pending |
| OPT-01 | -- | Pending |
| OPT-02 | -- | Pending |
| INFRA-01 | -- | Pending |
| INFRA-02 | -- | Pending |
| QUAL-01 | -- | Pending |
| QUAL-02 | -- | Pending |

**Coverage:**

- v1.0 requirements: 22 total
- Mapped to phases: 0
- Unmapped: 22

---
*Requirements defined: 2026-03-26*
*Last updated: 2026-03-26 after initial definition*
