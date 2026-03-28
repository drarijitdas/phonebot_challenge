# Phase 4: Observability - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-27
**Phase:** 04-observability
**Areas discussed:** Phoenix setup & lifecycle, Trace structure & tagging, Pipeline integration points, Phoenix UI workflow

---

## Phoenix Setup & Lifecycle

| Option | Description | Selected |
|--------|-------------|----------|
| Local server, auto-start | Phoenix launches automatically when run.py starts. No separate terminal needed. Traces viewable at localhost:6006 after run completes. | ✓ |
| Local server, manual start | User starts Phoenix separately. Pipeline connects to it. More control but extra step. | |
| Arize cloud hosted | Traces sent to Arize's hosted Phoenix platform. Requires API key. Persistent traces across sessions. | |

**User's choice:** Local server, auto-start
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Always-on | Every run.py execution traces to Phoenix. Minimal overhead, consistent data. | ✓ |
| Opt-in via --trace flag | Add --trace flag to run.py. Only traces when explicitly requested. | |
| Opt-out via --no-trace flag | Tracing on by default but can be disabled. | |

**User's choice:** Always-on
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, print URL | After accuracy table, show Phoenix URL. Easy to click. | ✓ |
| No, keep output clean | User knows where Phoenix is. Don't clutter CLI. | |
| You decide | Claude picks. | |

**User's choice:** Yes, print URL
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Persist across runs | Traces accumulate in Phoenix's local storage. Compare different runs over time. | ✓ |
| Fresh each run | Each invocation clears prior traces. Clean slate. | |
| You decide | Claude picks based on Phoenix defaults. | |

**User's choice:** Persist across runs
**Notes:** None

---

## Trace Structure & Tagging

| Option | Description | Selected |
|--------|-------------|----------|
| One trace per recording | Each call_XX gets its own trace with child spans for transcribe and extract nodes. | ✓ |
| One trace per full run | Single trace for the entire 30-recording batch, with each recording as a child span. | |
| You decide | Claude picks based on auto-instrumentation behavior. | |

**User's choice:** One trace per recording
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| CLI flag --prompt-version | Add --prompt-version to run.py. Tag gets attached to every trace as metadata. | ✓ |
| Auto-hash from prompt content | Compute short hash from CallerInfo docstring/field descriptions. Auto-changes when prompts change. | |
| Timestamp-based run ID | Each run gets a unique timestamp ID. Less semantic. | |

**User's choice:** CLI flag --prompt-version
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Model name | Which LLM was used. Essential for Phase 5 A/B comparison. | ✓ |
| Recording ID | Which call file was processed. Enables per-recording drill-down. | ✓ |
| Run timestamp | When this run was executed. Useful for chronological comparison. | ✓ |
| You decide the rest | Claude adds whatever makes sense for Phoenix filtering and Phase 5 readiness. | ✓ |

**User's choice:** All options selected (model name, recording ID, run timestamp, Claude's discretion for additional)
**Notes:** None

---

## Pipeline Integration Points

| Option | Description | Selected |
|--------|-------------|----------|
| LangChain auto-instrumentation | Phoenix's LangChain instrumentor auto-captures LLM calls, chains, and structured output. Minimal code changes. | ✓ |
| Manual OpenTelemetry spans | Manually create spans around each node. Full control but more boilerplate. | |
| LangGraph callbacks | Use LangGraph's callback system to emit trace events via callback handler. | |

**User's choice:** LangChain auto-instrumentation
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| observability/ module | init_tracing() function in src/phonebot/observability/. run.py calls at startup. | ✓ |
| Inline in run.py | Phoenix setup directly in run.py's main(). Simpler but mixes concerns. | |
| You decide | Claude picks cleanest integration point. | |

**User's choice:** observability/ module
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Both nodes traced | Transcribe node gets span showing cache load time, extract node auto-traces LLM call. | ✓ |
| Extract node only | Only LLM extraction call is traced. Transcribe is just a cache read. | |
| You decide | Claude picks based on auto-instrumentation defaults. | |

**User's choice:** Both nodes traced
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Configurable via env var | PHOENIX_PROJECT env var with default 'phonebot-extraction'. | ✓ |
| Hardcoded 'phonebot-extraction' | Matches success criteria. Simple. | |
| You decide | Claude picks. | |

**User's choice:** Configurable via env var
**Notes:** User chose flexibility over simplicity despite this being a challenge project

---

## Phoenix UI Workflow

| Option | Description | Selected |
|--------|-------------|----------|
| Trace list with metadata filters | 30 traces visible, filterable by prompt_version and model. Standard Phoenix workflow. | ✓ |
| Custom experiment view | Use Phoenix's experiment/dataset features for structured comparison view. | |
| You decide | Claude picks based on auto-instrumentation output. | |

**User's choice:** Trace list with metadata filters
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Full content captured | Transcript text (input) and CallerInfo JSON (output) visible in each trace. | ✓ |
| Metadata only | Only timing, token counts, model name. Lighter traces. | |
| You decide | Claude picks based on auto-instrumentor defaults. | |

**User's choice:** Full content captured
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Log trace count at end | After pipeline completes, log '30 traces sent to Phoenix'. Quick confidence check. | ✓ |
| No verification | Trust the instrumentation. | |
| You decide | Claude picks. | |

**User's choice:** Log trace count at end
**Notes:** None

---

## Claude's Discretion

- Exact Phoenix API usage and configuration details
- Additional trace metadata beyond model, recording_id, prompt_version, timestamp
- How auto-instrumentation interacts with LangGraph's async graph invocation
- Phoenix server port and startup configuration
- Whether transcribe node span needs manual creation or comes from auto-instrumentation

## Deferred Ideas

None — discussion stayed within phase scope
