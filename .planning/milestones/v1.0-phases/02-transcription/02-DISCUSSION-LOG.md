# Phase 2: Transcription - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-26
**Phase:** 02-transcription
**Areas discussed:** Cache format, Deepgram features, smart_format docs, Concurrency

---

## Cache format

| Option | Description | Selected |
|--------|-------------|----------|
| JSON (full response) | Save entire Deepgram response (transcript text + word-level confidence, timings, alternatives). Enables richer extraction prompts and debugging. | ✓ |
| Text only (.txt) | Save just the transcript string. Simple to inspect and grep. Loses confidence/timing data. | |
| Both (.json + .txt) | Save full JSON for programmatic use + plain text for quick inspection. | |

**User's choice:** JSON (full response)
**Notes:** Recommended option selected. Preserves all Deepgram metadata for downstream phases.

---

## Deepgram features

| Option | Description | Selected |
|--------|-------------|----------|
| smart_format | Auto-formats numbers, dates, URLs. Key question: does it convert spoken German phone numbers to digits? | ✓ |
| punctuation | Adds periods, commas, question marks. Helps LLM parse sentence boundaries. | ✓ |
| diarize | Speaker separation (bot vs caller). Could help isolate caller speech. | ✓ |
| paragraphs | Groups transcript into paragraph blocks. Adds structure. | ✓ |

**User's choice:** All four features enabled
**Notes:** User selected all available features to maximize transcript quality.

---

## smart_format docs

| Option | Description | Selected |
|--------|-------------|----------|
| Markdown report | Dedicated docs/smart_format_analysis.md with comparison tables showing spoken-form vs Deepgram output for 5+ recordings. | ✓ |
| Inline code comments | Document findings as comments in the transcription module. | |
| You decide | Claude picks the most practical format. | |

**User's choice:** Markdown report
**Notes:** Structured deliverable with comparison tables, directly feeding Phase 3 prompt design.

---

## Concurrency

| Option | Description | Selected |
|--------|-------------|----------|
| Semaphore-bounded | asyncio.Semaphore with configurable limit (default 5). Respects rate limits while being fast. | ✓ |
| Fire all 30 | Launch all 30 simultaneously. Fastest but risks 429 errors. | |
| Sequential | One at a time. Slowest but simplest. | |

**User's choice:** Semaphore-bounded
**Notes:** Configurable via DEEPGRAM_CONCURRENCY env var. Default 5 concurrent calls.

---

## Claude's Discretion

- Exact Deepgram SDK API usage and response parsing
- Cache file naming convention details
- Internal module structure within src/phonebot/
- Which 5+ recordings to sample for smart_format analysis

## Deferred Ideas

None — discussion stayed within phase scope
