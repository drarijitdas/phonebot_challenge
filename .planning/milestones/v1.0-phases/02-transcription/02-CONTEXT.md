# Phase 2: Transcription - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

All 30 German WAV recordings transcribed via Deepgram Nova-3, cached to disk as JSON, and smart_format behavior on German spoken-form phone/email tokens empirically verified and documented. Delivers: transcription module with async concurrent processing, JSON cache layer, and a markdown analysis report feeding Phase 3 prompt design.

</domain>

<decisions>
## Implementation Decisions

### Cache format
- **D-01:** Full Deepgram JSON response cached per recording at `data/transcripts/call_XX.json` — preserves transcript text, word-level confidence, timings, alternatives, and metadata
- **D-02:** Cache check on file existence — re-running the pipeline skips Deepgram API calls when JSON cache files exist

### Deepgram configuration
- **D-03:** `language="de"` with all four formatting features enabled: `smart_format=True`, `punctuate=True`, `diarize=True`, `paragraphs=True`
- **D-04:** Diarization enabled for speaker separation (bot vs caller) — may aid extraction by isolating caller speech

### smart_format documentation
- **D-05:** Dedicated markdown report at `docs/smart_format_analysis.md` with comparison tables showing spoken-form input vs Deepgram output for phone numbers and emails across 5+ recordings
- **D-06:** Report includes a conclusion section stating whether smart_format reliably converts German spoken-form tokens, feeding directly into Phase 3 extraction prompt design

### Concurrency
- **D-07:** `asyncio.Semaphore` with configurable limit via `DEEPGRAM_CONCURRENCY` env var (default 5). All 30 recordings dispatched via `asyncio.gather` with semaphore-bounded concurrency.

### Claude's Discretion
- Exact Deepgram SDK API usage and response parsing
- Cache file naming convention details (call_01.json vs other schemes)
- Internal module structure within `src/phonebot/`
- Which 5+ recordings to sample for the smart_format analysis

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project requirements
- `.planning/REQUIREMENTS.md` — Phase 2 requirements: STT-01, STT-02, STT-03
- `.planning/PROJECT.md` — Core value, constraints, Deepgram Nova-3 decision

### Prior phase context
- `.planning/phases/01-foundation/01-CONTEXT.md` — D-01 (package structure), D-03 (env vars), D-07 (async concurrent), D-11 (Pydantic prompting system)

### Research
- `.planning/research/STACK.md` — Deepgram SDK v6 API shape and integration patterns
- `.planning/research/PITFALLS.md` — Pitfall 4 (phone format normalization)

### Data
- `data/recordings/` — 30 WAV files (call_01.wav through call_30.wav)
- `data/ground_truth.json` — Expected extractions for verification during smart_format analysis

### Existing code
- `src/phonebot/models/caller_info.py` — CallerInfo model with spoken-form phone/email handling in field descriptions

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `CallerInfo` model (`src/phonebot/models/caller_info.py`) — field descriptions already handle spoken-form German (D-11 from Phase 1)
- `src/phonebot/pipeline/` module exists (placeholder) — transcription code fits here or in a sibling module

### Established Patterns
- Environment vars via `.env` for API keys (D-03 from Phase 1)
- `uv` for dependency management with Python 3.13
- Rich Console for CLI output (D-04 from Phase 1)

### Integration Points
- `data/transcripts/` — new directory for cached JSON transcripts, consumed by Phase 3 extraction
- `docs/smart_format_analysis.md` — new file, consumed by Phase 3 prompt design
- `src/phonebot/pipeline/` — transcription code connects here, Phase 3 adds extraction nodes to the same pipeline module

</code_context>

<specifics>
## Specific Ideas

- Full JSON cache (not just text) — user chose this to preserve word-level confidence and timing data for downstream use
- All four Deepgram features (smart_format + punctuation + diarize + paragraphs) — maximize transcript quality
- Semaphore-bounded concurrency with env-var-configurable limit — balances speed with rate-limit safety
- Markdown report with comparison tables — structured deliverable that directly feeds Phase 3 prompt decisions

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-transcription*
*Context gathered: 2026-03-26*
