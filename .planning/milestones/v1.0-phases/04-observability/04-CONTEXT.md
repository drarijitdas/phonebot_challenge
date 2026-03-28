# Phase 4: Observability - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Arize Phoenix tracing live across all 30 pipeline runs with span-level visibility for every LangGraph node, plus prompt version tagging. Delivers: Phoenix auto-start integration, LangChain auto-instrumentation, per-recording traces with transcribe/extract spans, prompt version and model metadata tagging, and CLI feedback showing trace count and Phoenix UI URL.

</domain>

<decisions>
## Implementation Decisions

### Phoenix setup & lifecycle
- **D-01:** Phoenix launches automatically when run.py starts (px.launch_app() or equivalent) — no separate terminal needed
- **D-02:** Tracing is always-on — every run.py execution traces to Phoenix, no opt-in flag
- **D-03:** run.py prints Phoenix UI URL (e.g., `http://localhost:6006`) after pipeline completion, alongside the accuracy table
- **D-04:** Traces persist across runs — Phoenix's local storage accumulates traces, enabling cross-run comparison for Phase 5 A/B testing

### Trace structure & tagging
- **D-05:** One trace per recording — each call_XX gets its own trace with child spans for transcribe and extract nodes (aligns with Phase 3 D-09)
- **D-06:** Prompt version set via `--prompt-version` CLI flag on run.py (e.g., `--prompt-version v1`). Tag attached to every trace as metadata.
- **D-07:** Additional metadata per trace: model name, recording ID, run timestamp, plus whatever else Claude deems useful for Phoenix filtering and Phase 5 readiness

### Pipeline integration
- **D-08:** LangChain auto-instrumentation via Phoenix's instrumentor — minimal code changes, auto-captures LLM calls, chain invocations, and structured output
- **D-09:** Instrumentation initialization lives in `src/phonebot/observability/` module with an `init_tracing()` function. run.py calls it at startup before pipeline runs.
- **D-10:** Both LangGraph nodes traced — transcribe node gets a span showing cache load time, extract node auto-traces LLM call. Full pipeline visibility per success criteria.
- **D-11:** Phoenix project name configurable via `PHOENIX_PROJECT` env var with default `"phonebot-extraction"`

### Phoenix UI workflow
- **D-12:** Standard trace list with metadata filters — 30 traces visible, filterable by prompt_version and model. Click a trace to see transcribe/extract spans with LLM latency.
- **D-13:** Full LLM input/output content captured in traces — transcript text (input) and CallerInfo JSON (output) visible for debugging extraction errors directly in Phoenix
- **D-14:** Log trace count to console after pipeline completes (e.g., "30 traces sent to Phoenix") as a quick verification that tracing is working

### Claude's Discretion
- Exact Phoenix API usage and configuration details
- Additional trace metadata beyond model, recording_id, prompt_version, timestamp
- How auto-instrumentation interacts with LangGraph's async graph invocation
- Phoenix server port and startup configuration
- Whether transcribe node span needs manual creation or comes from auto-instrumentation

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project requirements
- `.planning/REQUIREMENTS.md` — Phase 4 requirements: OBS-01, OBS-02
- `.planning/PROJECT.md` — Core value, constraints, Arize Phoenix decision

### Prior phase context
- `.planning/phases/01-foundation/01-CONTEXT.md` — D-01 (package structure with observability/), D-03 (env vars via .env), D-04 (Rich Console), D-07 (async concurrent)
- `.planning/phases/02-transcription/02-CONTEXT.md` — D-01 (JSON cache format), D-07 (semaphore concurrency)
- `.planning/phases/03-extraction-pipeline/03-CONTEXT.md` — D-06 (graph topology), D-08 (with_structured_output), D-09 (one recording per graph invocation), D-11 (Claude Sonnet 4.6 baseline)

### Existing code
- `src/phonebot/pipeline/extract.py` — LangGraph pipeline with PIPELINE constant, run_pipeline(), transcribe_node, extract_node
- `src/phonebot/observability/__init__.py` — Placeholder module for Phoenix tracing code
- `run.py` — CLI entrypoint that calls run_pipeline() and prints Rich accuracy table
- `pyproject.toml` — Current dependencies (no Phoenix yet)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/phonebot/observability/` — Placeholder module with Phase 4 docstring, ready for init_tracing() function
- `run.py` main() — Natural place to call init_tracing() at startup and print Phoenix URL at end
- `extract.py` PIPELINE — Compiled StateGraph; auto-instrumentation should capture its .ainvoke() calls
- `ChatAnthropic` in extract_node — LangChain auto-instrumentor captures these LLM calls automatically

### Established Patterns
- Environment vars via `.env` for API keys and config (DEEPGRAM_API_KEY, ANTHROPIC_API_KEY, EXTRACT_CONCURRENCY) — PHOENIX_PROJECT follows same pattern
- `argparse` in run.py for CLI args — --prompt-version fits naturally alongside --model
- Rich Console for CLI output — Phoenix URL and trace count messages use same console
- Async concurrency with asyncio.Semaphore — traces must handle concurrent pipeline invocations

### Integration Points
- `run.py` main() — Call init_tracing() before run_pipeline(), print Phoenix URL + trace count after
- `src/phonebot/observability/` — New init_tracing() function, possibly shutdown_tracing()
- `pyproject.toml` — Add arize-phoenix and opentelemetry dependencies
- `run.py` argparse — Add --prompt-version argument

</code_context>

<specifics>
## Specific Ideas

- Auto-start Phoenix from run.py — zero extra steps for the user, traces just appear
- Always-on tracing — consistent data accumulation, no forgetting to enable
- Persistent traces — enables Phase 5 A/B comparison across runs without data loss
- Configurable project name via env var — user chose this over hardcoded despite being a challenge project
- Full content capture in traces — enables debugging extraction errors directly in Phoenix without cross-referencing results.json
- Trace count logging — quick CLI confirmation that instrumentation is working

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-observability*
*Context gathered: 2026-03-27*
