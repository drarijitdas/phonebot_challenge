---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 05-01-PLAN.md — model registry and pipeline wiring
last_updated: "2026-03-27T20:34:25.685Z"
last_activity: 2026-03-27
progress:
  total_phases: 7
  completed_phases: 4
  total_plans: 10
  completed_plans: 9
  percent: 57
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-26)

**Core value:** Accurate extraction of caller contact information from German phone bot recordings
**Current focus:** Phase 05 — model-a-b-testing

## Current Position

Phase: 05 (model-a-b-testing) — EXECUTING
Plan: 2 of 2
Status: Ready to execute
Last activity: 2026-03-27

Progress: [████████░░] 57%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: --
- Total execution time: --

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

*Updated after each plan completion*
| Phase 01-foundation P01 | 3 | 2 tasks | 13 files |
| Phase 01-foundation P02 | 2 | 2 tasks | 3 files |
| Phase 02-transcription P01 | 15m | 1 tasks | 5 files |
| Phase 02-transcription P02 | prior session + checkpoint approval | 2 tasks | 32 files |
| Phase 03-extraction-pipeline P01 | 3m | 3 tasks | 5 files |
| Phase 03-extraction-pipeline P02 | ~4m | 2 tasks | 1 file |
| Phase 04-observability P01 | 7m | 2 tasks | 8 files |
| Phase 04-observability P02 | 10m | 2 tasks | 0 files |
| Phase 05-model-a-b-testing P01 | 6m 10s | 2 tasks | 9 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Pre-roadmap: Evaluation harness placed in Phase 1 (before transcription) so accuracy is measurable from the first pipeline run — avoids silent multi-value comparison bugs corrupting GEPA signal later
- Pre-roadmap: EXT-04 (retry loop) deferred to Phase 7 — validates prompt quality with a clean graph before adding retry complexity
- Pre-roadmap: GEPA (Phase 6) runs on best-performing model from A/B test (Phase 5) — optimize the winner, not the first model tried
- [Phase 01-foundation]: argparse + Rich Console for CLI (no Typer) per D-04; CallerInfo docstring is the LLM system prompt per D-11
- [Phase 01-foundation]: Both sides normalized in matches_field to prevent asymmetric phone comparison bugs
- [Phase 01-foundation]: casefold() over lower() for German eszett handling in normalize_text
- [Phase 01-foundation]: compute_metrics accepts CallerInfo objects via model_dump() check for forward-compatibility
- [Phase 02-transcription]: deepgram-sdk v6 uses direct kwargs on transcribe_file() with no PrerecordedOptions; response.model_dump_json() replaces response.to_json()
- [Phase 02-transcription]: smart_format for German (language=de) activates punctuation/paragraphs only — phone numeral conversion and email assembly are English-only features; extraction prompts must handle spoken-form unconditionally
- [Phase 02-transcription]: Diarization unreliable in sampled recordings — single speaker label returned for all 8 sampled calls; extraction prompts must not rely on speaker labels
- [Phase 03-extraction-pipeline]: PIPELINE constant: StateGraph compiled once at import time, not rebuilt per recording
- [Phase 03-extraction-pipeline]: transcribe_node raises FileNotFoundError on cache miss; no API fallback in Phase 3
- [Phase 03-extraction-pipeline]: asyncio_mode=auto added to pytest config for transparent pytest-asyncio async test execution
- [Phase 03-extraction-pipeline]: run.py discovers recordings from data/transcripts/call_*.json glob, not WAV files
- [Phase 03-extraction-pipeline]: Lazy import of run_pipeline inside main() avoids load_dotenv/langchain import-time issues
- [Phase 03-extraction-pipeline]: Baseline accuracy: 82% overall (90% first_name, 77% last_name, 67% email, 97% phone_number)
- [Phase 04-observability]: Patch phoenix.otel.register at source in tests so importlib.reload picks up mock — patch location matters when module re-executes 'from X import Y' on reload
- [Phase 04-observability]: using_attributes() placed inside process_one() not outer run_pipeline() scope — anchors concurrent asyncio.gather tasks to individual OTel contexts, prevents span bleed
- [Phase 04-observability]: Phoenix tracing confirmed working end-to-end: 30 traces, correct spans, prompt_version tag — Phase 4 gate passed
- [Phase 05-model-a-b-testing]: model_registry.py routes claude-* to ChatAnthropic and ollama:<model> to ChatOllama with colon-prefix convention
- [Phase 05-model-a-b-testing]: ChatOllama uses validate_model_on_init=False to avoid live Ollama HTTP check on model object creation
- [Phase 05-model-a-b-testing]: run.py output path now derived as outputs/results_{model_alias}.json for per-model result isolation

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 2 gate: smart_format German phone/email behavior cannot be resolved from documentation alone — must empirically verify on real recordings before writing extraction prompts
- Phase 6 risk: No reference implementation for GEPA + LangGraph adapter exists — budget 1-2 days; GEPA docs may lag code
- Phase 6 risk: GEPA API cost estimation needed before running (100-500 evaluations x 20 recordings x LLM calls)
- Phase 1 dependency: Ground truth schema format in `data/ground_truth.json` (scalar vs list vs aliases field) must be inspected before writing evaluation harness

## Session Continuity

Last session: 2026-03-27T20:34:25.682Z
Stopped at: Completed 05-01-PLAN.md — model registry and pipeline wiring
Resume file: None
