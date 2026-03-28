# Phase 3: Extraction Pipeline - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

A working LangGraph pipeline that extracts CallerInfo (first_name, last_name, email, phone_number) from cached Deepgram transcripts using LLM structured output, and produces a baseline per-field accuracy score against ground truth. Delivers: LangGraph graph with typed PipelineState, enhanced CallerInfo field descriptions grounded in real Deepgram output patterns, integration with existing evaluation harness, and a single `uv run python run.py` command that extracts + evaluates all 30 recordings.

</domain>

<decisions>
## Implementation Decisions

### Prompt strategy for spoken-form
- **D-01:** Expand CallerInfo Field descriptions with exact Deepgram output patterns observed in Phase 2 smart_format analysis (e.g., phone digits appear space-separated as "4 9 1 7 6", email spoken as "Name Punkt Name at Domain Punkt com")
- **D-02:** Patterns go in per-field descriptions (not class docstring) — per Phase 1 D-02/D-11, field descriptions ARE the per-field extraction instructions
- **D-03:** Reference exact Deepgram output patterns from the 30 transcripts, not general German conventions — maximally grounded in real data
- **D-04:** Full transcript sent to LLM (no speaker filtering) — diarization is unreliable per Phase 2 finding
- **D-05:** Extract names as-transcribed — if Deepgram outputs "Gassia" for "García", extract "Gassia". Do not attempt spelling correction. Avoids hallucination.

### LangGraph node design
- **D-06:** Graph topology: `START → transcribe → extract → END` with typed `PipelineState`
- **D-07:** Transcribe node loads cached JSON from `data/transcripts/` — falls back to Deepgram API only on cache miss. Does not re-transcribe by default.
- **D-08:** Extract node uses LangChain `model.with_structured_output(CallerInfo)` for Pydantic schema → JSON mode automatically
- **D-09:** One recording per graph invocation — outer loop iterates 30x with async concurrency. Simpler state, easier debugging, natural per-recording tracing for Phoenix in Phase 4.
- **D-10:** Pydantic validation inline in extract node via `with_structured_output` — no separate validate node. Phase 7 adds retry logic (EXT-04) later.

### Baseline model choice
- **D-11:** Claude Sonnet 4.6 only for Phase 3 baseline — use CLI default `--model claude-sonnet-4-6`. Phase 5 introduces open-source model comparison.

### Results output structure
- **D-12:** `outputs/results.json` contains: each entry as `{id, caller_info (with confidence), model, timestamp}` plus top-level run metadata `{model, total_recordings, duration}`
- **D-13:** `run.py` auto-evaluates after extraction — extracts all 30, calls `compute_metrics`, prints Rich accuracy table to console. Single command for full pipeline + results. Matches success criteria.

### Claude's Discretion
- Exact LangGraph state schema field names and types
- Async concurrency implementation details for the outer loop
- How to extract transcript text from cached Deepgram JSON structure
- Rich table formatting for the accuracy report
- Error handling for individual recording failures (skip and continue vs fail fast)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project requirements
- `.planning/REQUIREMENTS.md` — Phase 3 requirements: EXT-01, EXT-02, EXT-03, EXT-05, QUAL-01
- `.planning/PROJECT.md` — Core value, constraints, key decisions (especially Pydantic BaseModel prompting and LangGraph orchestration)

### Prior phase context
- `.planning/phases/01-foundation/01-CONTEXT.md` — D-01 (package structure), D-02 (prompts in Pydantic), D-05 (CLI args), D-07 (async concurrent), D-11 (Pydantic prompting system)
- `.planning/phases/02-transcription/02-CONTEXT.md` — D-01 (cache format), D-03 (Deepgram config), D-05 (smart_format report)

### Smart format analysis (critical for prompt design)
- `docs/smart_format_analysis.md` — Empirical phone/email patterns from 30 transcripts. Phone: space-separated digits. Email: "Name Punkt Name at Domain Punkt com". Foreign names: phonetic transcription.

### Existing code
- `src/phonebot/models/caller_info.py` — CallerInfo Pydantic model to enhance with detailed patterns
- `src/phonebot/pipeline/transcribe.py` — Existing transcription module with cache layer
- `src/phonebot/evaluation/metrics.py` — Evaluation harness: `compute_metrics`, `load_ground_truth`, normalization functions
- `run.py` — CLI entrypoint (scaffold, needs pipeline integration)
- `data/ground_truth.json` — Expected extractions for all 30 recordings

### Data
- `data/transcripts/call_01.json` through `call_30.json` — Cached Deepgram Nova-3 responses (full JSON with transcript text, word-level data)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `CallerInfo` model (`src/phonebot/models/caller_info.py`) — Pydantic BaseModel with Optional fields and confidence dict. Field descriptions need enhancement with exact Deepgram patterns.
- `transcribe.py` (`src/phonebot/pipeline/transcribe.py`) — Async batch transcription with JSON cache. Transcribe node can reuse cache-loading logic.
- `metrics.py` (`src/phonebot/evaluation/metrics.py`) — `compute_metrics` accepts `[{"id": str, "caller_info": dict}]` and ground truth dict. `load_ground_truth` reads `data/ground_truth.json`. Phone normalization via `phonenumbers`, text via NFC+casefold.
- `run.py` — argparse scaffold with `--model`, `--recordings-dir`, `--output` args. Rich Console initialized. Needs pipeline wiring.

### Established Patterns
- Environment vars via `.env` for API keys (DEEPGRAM_API_KEY, ANTHROPIC_API_KEY)
- `uv` for dependency management with Python 3.13
- Rich Console for CLI output
- Async with `asyncio.Semaphore` for concurrency control
- Pydantic `model_dump()` / `model_dump_json()` for serialization

### Integration Points
- `run.py` — Main entrypoint, needs to import and invoke LangGraph pipeline + evaluation
- `src/phonebot/pipeline/` — New `extract.py` module alongside existing `transcribe.py`
- `src/phonebot/evaluation/metrics.py` — Called after extraction to produce accuracy report
- `outputs/results.json` — New output file with extraction results + metadata

</code_context>

<specifics>
## Specific Ideas

- Field descriptions grounded in exact Deepgram output patterns (not generic German patterns) — user explicitly chose maximum specificity
- Names extracted as-transcribed (no spelling correction) — prevents hallucination, lets evaluation normalization handle comparison
- One-recording-per-graph-invocation pattern — aligns with Phase 4 Phoenix tracing (one trace per recording)
- Auto-evaluate in run.py — single command does extract + eval, prints Rich accuracy table

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-extraction-pipeline*
*Context gathered: 2026-03-27*
