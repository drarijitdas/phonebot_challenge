---
phase: 02-transcription
plan: "02"
subsystem: pipeline/transcribe + docs
tags: [transcription, deepgram, smart_format, german, analysis, caching]
dependency_graph:
  requires: [02-01-transcription-module]
  provides: [transcript-cache-30-recordings, smart-format-analysis-report]
  affects: [03-extraction-prompts]
tech_stack:
  added: []
  patterns: [json-cache-layer, transcript-sampling, phone-email-regex-analysis]
key_files:
  created:
    - data/transcripts/call_01.json (through call_30.json — 30 files)
    - docs/smart_format_analysis.md
  modified:
    - src/phonebot/pipeline/transcribe.py
decisions:
  - "smart_format for German (language=de) activates punctuation/paragraphs only — phone numeral conversion and email assembly are English-only features"
  - "All 30 recordings produce single-speaker diarization labels — bot/caller separation is unreliable; extraction prompts must not rely on speaker labels"
  - "Non-German names (calls 16-30) transcribed as phonetic German approximations — extraction must handle phonetic variants"
metrics:
  duration: "prior session"
  completed: "2026-03-27"
  tasks_completed: 2
  files_created: 31
  files_modified: 1
---

# Phase 02 Plan 02: Live Transcription and smart_format Analysis Summary

**One-liner:** 30 German phone bot recordings transcribed via Deepgram Nova-3 and cached to disk; empirical smart_format analysis confirms German spoken-form phone/email tokens are NEVER pre-normalized by the SDK.

## What Was Built

- **30 cached Deepgram JSON files** (`data/transcripts/call_01.json` through `call_30.json`) — each contains the full Pydantic-serialized Nova-3 response with results, word-level timing, confidence scores, and diarization labels
- **`docs/smart_format_analysis.md`** — 8-recording analysis report comparing expected phone/email values from `data/ground_truth.json` against actual Deepgram transcript output, with phone/email/diarization/foreign-name observation tables and a conclusion section
- **`src/phonebot/pipeline/transcribe.py`** — extended with:
  - `generate_smart_format_report(sample_ids)` — report generation function with phone/email/name/diarization analysis helpers
  - `_find_phone_in_transcript`, `_find_email_in_transcript`, `_get_speaker_info` — internal analysis helpers
  - `if __name__ == "__main__"` CLI runner that transcribes all 30 recordings then generates the analysis report

## Verification Results

- `ls data/transcripts/*.json | wc -l` → **30**
- `get_transcript_text(Path('data/transcripts/call_01.json'))` → 250 chars of German text (no error)
- `docs/smart_format_analysis.md` contains `## Phone Number Observations`, `## Email Observations`, `## Conclusion`, `Phase 3`
- `uv run pytest -x` → **38/38 passed**
- Cache skip verified: second run of `uv run python -m phonebot.pipeline.transcribe` completes in under 2 seconds (no Deepgram API calls)

## Key Findings (smart_format Analysis)

**Phone numbers (8/8 recordings):** smart_format does NOT convert German spoken-form digits to numerals. Transcripts contain digit-by-digit individual characters separated by spaces (e.g., "plus 4 9 1 5 2 1 1 2 2 3 4 5 6") rather than grouped E.164 notation. Formatted? = No for all 8 sampled recordings.

**Emails (8/8 recordings):** smart_format does NOT assemble German spoken-form email components. Transcripts contain spoken-form tokens (e.g., "Johanna Punkt Schmidt at Gmail Punkt com") rather than assembled addresses. Formatted? = No for all 8 sampled recordings.

**Diarization (8/8 recordings):** Single speaker detected in all sampled recordings (1 speaker label returned). Bot/caller separation is unreliable with the current setup; extraction prompts cannot depend on speaker labels.

**Foreign names (calls 16-30, 3 sampled):** Partially accurate — first names recognized, last names may differ (e.g., "García" → "Gassia", "Lefevre" → "Le Faivre"). Extraction prompts must handle phonetic variants.

## Implication for Phase 3

LLM extraction prompts MUST handle spoken-form phone numbers and emails unconditionally. The extraction LLM must convert sequences like "null eins fünf zwei ein eins zwei zwei drei vier fünf sechs" into "+49 152 11223456" entirely by its own reasoning. smart_format provides NO pre-normalization for German.

## Deviations from Plan

None — plan executed exactly as written. Task 1 was completed in the previous agent session (commit d295f57). Task 2 is a human-verify checkpoint that was approved by the user.

## Human Verification

The user reviewed `docs/smart_format_analysis.md` and approved it (response: "approved"), confirming:
- Phone/email comparison tables reflect actual Deepgram output
- Conclusion correctly identifies smart_format limitations for German
- Transcript quality is sufficient for Phase 3 extraction

## Known Stubs

None — all 30 cache files contain real Deepgram API responses. The analysis report is populated with actual transcript data, not placeholders.

## Self-Check: PASSED

Files:
- FOUND: data/transcripts/call_01.json
- FOUND: data/transcripts/call_30.json
- FOUND: docs/smart_format_analysis.md
- FOUND: src/phonebot/pipeline/transcribe.py

Commits:
- d295f57 — feat(02-02): transcribe 30 recordings and generate smart_format analysis report
