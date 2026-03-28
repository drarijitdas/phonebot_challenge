# Phase 4: Observability - Research

**Researched:** 2026-03-27
**Domain:** Arize Phoenix, OpenTelemetry, LangChain/LangGraph auto-instrumentation
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Phoenix setup & lifecycle**
- D-01: Phoenix launches automatically when run.py starts (px.launch_app() or equivalent) — no separate terminal needed
- D-02: Tracing is always-on — every run.py execution traces to Phoenix, no opt-in flag
- D-03: run.py prints Phoenix UI URL (e.g., `http://localhost:6006`) after pipeline completion, alongside the accuracy table
- D-04: Traces persist across runs — Phoenix's local storage accumulates traces, enabling cross-run comparison for Phase 5 A/B testing

**Trace structure & tagging**
- D-05: One trace per recording — each call_XX gets its own trace with child spans for transcribe and extract nodes (aligns with Phase 3 D-09)
- D-06: Prompt version set via `--prompt-version` CLI flag on run.py (e.g., `--prompt-version v1`). Tag attached to every trace as metadata.
- D-07: Additional metadata per trace: model name, recording ID, run timestamp, plus whatever else Claude deems useful for Phoenix filtering and Phase 5 readiness

**Pipeline integration**
- D-08: LangChain auto-instrumentation via Phoenix's instrumentor — minimal code changes, auto-captures LLM calls, chain invocations, and structured output
- D-09: Instrumentation initialization lives in `src/phonebot/observability/` module with an `init_tracing()` function. run.py calls it at startup before pipeline runs.
- D-10: Both LangGraph nodes traced — transcribe node gets a span showing cache load time, extract node auto-traces LLM call. Full pipeline visibility per success criteria.
- D-11: Phoenix project name configurable via `PHOENIX_PROJECT` env var with default `"phonebot-extraction"`

**Phoenix UI workflow**
- D-12: Standard trace list with metadata filters — 30 traces visible, filterable by prompt_version and model. Click a trace to see transcribe/extract spans with LLM latency.
- D-13: Full LLM input/output content captured in traces — transcript text (input) and CallerInfo JSON (output) visible for debugging extraction errors directly in Phoenix
- D-14: Log trace count to console after pipeline completes (e.g., "30 traces sent to Phoenix") as a quick verification that tracing is working

### Claude's Discretion
- Exact Phoenix API usage and configuration details
- Additional trace metadata beyond model, recording_id, prompt_version, timestamp
- How auto-instrumentation interacts with LangGraph's async graph invocation
- Phoenix server port and startup configuration
- Whether transcribe node span needs manual creation or comes from auto-instrumentation

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OBS-01 | Arize Phoenix traces all LangGraph pipeline nodes with span-level visibility | Covered by `openinference-instrumentation-langchain` auto-instrumentation; both transcribe and extract nodes emit spans automatically once PIPELINE.ainvoke() is instrumented |
| OBS-02 | Traces are tagged with prompt version for comparison across iterations | Covered by `using_attributes(prompt_template_version=...)` context manager from `openinference.instrumentation` wrapping run_pipeline() call |
</phase_requirements>

---

## Summary

Arize Phoenix 13.19.0 (released 2026-03-26) is the current version and supports Python 3.10–3.13, making it compatible with this project's Python 3.13.2 environment. The core integration pattern is three packages: `arize-phoenix` (server + UI), `arize-phoenix-otel` (lightweight OTEL wrapper), and `openinference-instrumentation-langchain` (auto-instrumentation hooks into langchain-core). Because the project uses `ChatAnthropic` via `langchain-anthropic` and `StateGraph` via `langgraph`, the LangChain instrumentor captures both LLM calls and graph node spans automatically with zero manual span creation.

The critical design challenge is Phoenix server lifecycle: `px.launch_app()` is documented for notebook environments and officially discouraged for scripts. The recommended non-notebook approach is `phoenix serve` as a CLI command. However, D-01 requires auto-start from `run.py`. The practical resolution is `px.launch_app(use_temp_dir=False)` called in a background thread — this works in scripts and satisfies D-04 (persistent storage) when combined with `PHOENIX_WORKING_DIR`. Alternatively, the function can detect whether Phoenix is already running and skip launch if it is, which avoids the "discouraged in scripts" pattern for repeated runs.

The second critical challenge is async context propagation. Concurrent `PIPELINE.ainvoke()` calls via `asyncio.gather` can produce ungrouped/out-of-order spans in LangGraph unless the OpenTelemetry asyncio context is correctly propagated. The fix is to wrap each `ainvoke()` call inside a `using_attributes(...)` context manager that sets recording_id and prompt_version — this anchors each concurrent trace to its own context, preventing span contamination across the 30 concurrent invocations.

**Primary recommendation:** Install `arize-phoenix`, `arize-phoenix-otel`, `openinference-instrumentation-langchain`. Initialize with `px.launch_app(use_temp_dir=False)` + `register(project_name=..., auto_instrument=True)`. Wrap each `ainvoke()` in `using_attributes(metadata={"recording_id": ..., "prompt_version": ..., "model": ...})` to tag and isolate concurrent traces.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| arize-phoenix | 13.19.0 | Phoenix server, UI, SQLite storage, trace ingestion | The official Phoenix platform package — includes the server process, web UI at port 6006, and all storage |
| arize-phoenix-otel | 0.15.0 | `register()` function, OTEL tracer provider setup | Lightweight wrapper (~20KB) that configures OTEL with Phoenix-aware defaults; `register(project_name=..., auto_instrument=True)` is the canonical init |
| openinference-instrumentation-langchain | 0.1.61 | LangChain + LangGraph auto-instrumentation | Hooks into `langchain-core` (shared by all LangChain packages); auto-captures `ChatAnthropic` LLM calls and `StateGraph` node invocations |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| openinference-instrumentation (transitively installed) | — | `using_attributes()`, `using_metadata()` context managers | Required for prompt_version tagging and per-trace metadata injection |
| opentelemetry-sdk | — | Tracer provider base, span lifecycle | Installed transitively by arize-phoenix-otel; no direct import needed |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| arize-phoenix (full) | arize-phoenix-otel + separate phoenix server | Full package is simpler — includes server; otel-only is lightweight but requires phoenix running separately |
| px.launch_app() | subprocess `phoenix serve` | launch_app() keeps server in same process/thread; subprocess is cleaner separation but requires shell PATH setup |
| using_attributes() per ainvoke | Manual OTEL span creation | using_attributes() is idiomatic OpenInference; manual spans require tracer handle and add boilerplate |

**Installation:**

```bash
uv add arize-phoenix arize-phoenix-otel openinference-instrumentation-langchain
```

**Version verification (confirmed 2026-03-27):**
- `arize-phoenix`: 13.19.0 (released 2026-03-26)
- `arize-phoenix-otel`: 0.15.0 (released 2026-03-02)
- `openinference-instrumentation-langchain`: 0.1.61 (released 2026-02-26)

---

## Architecture Patterns

### Recommended Project Structure

```
src/phonebot/
├── observability/
│   └── __init__.py        # init_tracing() function — all Phoenix setup here
├── pipeline/
│   └── extract.py         # Unchanged — auto-instrumented by LangChain instrumentor
run.py                     # calls init_tracing() at startup, wraps run_pipeline() with using_attributes()
.env                       # PHOENIX_PROJECT, PHOENIX_WORKING_DIR vars
```

### Pattern 1: Phoenix Initialization in init_tracing()

**What:** Single `init_tracing()` function in `src/phonebot/observability/__init__.py` that (1) starts the Phoenix server, (2) registers the OTEL tracer provider, (3) returns the session URL.

**When to use:** Called once at `main()` startup before pipeline runs.

```python
# Source: arize-phoenix session.py + phoenix.otel register() API
import os
import phoenix as px
from phoenix.otel import register

def init_tracing() -> str:
    """Start Phoenix server and configure OTEL instrumentation. Returns UI URL."""
    project_name = os.getenv("PHOENIX_PROJECT", "phonebot-extraction")
    working_dir = os.getenv("PHOENIX_WORKING_DIR", ".phoenix")

    # Ensure working directory exists for persistent storage (D-04)
    os.makedirs(working_dir, exist_ok=True)
    os.environ["PHOENIX_WORKING_DIR"] = working_dir

    # Start Phoenix server in background thread (D-01)
    # use_temp_dir=False enables persistent SQLite storage across runs
    session = px.active_session()
    if session is None:
        session = px.launch_app(use_temp_dir=False)

    # Register OTEL tracer provider with auto-instrumentation (D-08)
    # auto_instrument=True discovers and activates all installed OpenInference instrumentors
    register(
        project_name=project_name,
        auto_instrument=True,
    )

    return session.url if session else "http://localhost:6006"
```

### Pattern 2: Per-Trace Metadata via using_attributes()

**What:** Wrap each `PIPELINE.ainvoke()` call with `using_attributes()` to inject recording_id, prompt_version, and model name into every span of that invocation.

**When to use:** In `process_one()` inside `run_pipeline()`, wrapping the `ainvoke()` call. This is the correct anchor point because it scopes attributes to a single concurrent trace.

```python
# Source: arize.com/docs/phoenix/tracing/how-to-tracing/add-metadata/customize-spans
from openinference.instrumentation import using_attributes

async def process_one(recording_id: str) -> dict:
    async with semaphore:
        with using_attributes(
            metadata={
                "recording_id": recording_id,
                "model": model_name,
                "prompt_version": prompt_version,
                "run_timestamp": datetime.now(timezone.utc).isoformat(),
            },
            prompt_template_version=prompt_version,
        ):
            final_state = await PIPELINE.ainvoke({
                "recording_id": recording_id,
                "transcript_text": None,
                "caller_info": None,
            })
    return {
        "id": recording_id,
        "caller_info": final_state["caller_info"],
        "model": model_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
```

### Pattern 3: run.py Integration Points

**What:** run.py calls `init_tracing()` at startup, passes `prompt_version` to `run_pipeline()`, and prints Phoenix URL + trace count after completion.

```python
# In build_parser():
parser.add_argument("--prompt-version", default="v1", help="Prompt version tag for Phoenix traces")

# In main():
from phonebot.observability import init_tracing
phoenix_url = init_tracing()

# ... run pipeline with prompt_version=args.prompt_version ...

console.print(f"[dim]Phoenix UI: {phoenix_url}[/dim]")
console.print(f"[dim]30 traces sent to Phoenix[/dim]")
```

### Pattern 4: run_pipeline() Signature Extension

**What:** `run_pipeline()` in `extract.py` needs a `prompt_version` parameter passed through to `using_attributes()`. The function signature changes minimally.

```python
async def run_pipeline(
    recording_ids: list[str],
    model_name: str = "claude-sonnet-4-6",
    concurrency: int = 5,
    prompt_version: str = "v1",          # NEW: passed from run.py CLI arg
) -> list[dict]:
    ...
```

### Anti-Patterns to Avoid

- **Re-calling `register()` on every run.py execution without checking for active session:** If Phoenix is already running (e.g., user runs run.py twice), a second `px.launch_app()` call conflicts. The `px.active_session()` guard handles this.
- **Calling `init_tracing()` after importing langchain modules:** OTEL instrumentation must be registered before any LangChain code is imported/executed. `run.py` already uses lazy import of `run_pipeline` inside `main()`, which preserves this ordering requirement.
- **Placing `using_attributes()` outside the concurrent task:** If `using_attributes()` is called in the outer `run_pipeline()` scope rather than inside `process_one()`, all 30 concurrent tasks share one context and attributes bleed across traces.
- **`use_temp_dir=True` (default):** The default uses a temp directory wiped on each OS restart. D-04 requires persistent traces for Phase 5 A/B comparison — always use `use_temp_dir=False`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LLM call tracing | Custom callback handlers logging to file | `openinference-instrumentation-langchain` | Auto-instruments `ChatAnthropic`, captures input/output tokens, latency, structured output — all in one registration call |
| Span metadata propagation | Thread-local storage or passing trace IDs manually | `using_attributes()` context manager | OpenInference context managers propagate through async/await boundaries automatically via contextvars |
| Trace storage | SQLite schema + queries for trace history | Phoenix built-in SQLite via `PHOENIX_WORKING_DIR` | Phoenix manages schema, migrations, and indexing; exposes query via gRPC collector |
| UI for trace visualization | Custom HTML dashboard | Phoenix web UI at localhost:6006 | Interactive trace waterfall, metadata filtering, LLM I/O display — zero code |
| Prompt version comparisons | Custom tag query scripts | Phoenix project filters | Phoenix UI allows filtering by any metadata key (prompt_version, model) natively |

**Key insight:** The entire observability layer is configuration, not code. The instrumentor does the heavy lifting; the implementation is `init_tracing()` + `using_attributes()` wrappers.

---

## Common Pitfalls

### Pitfall 1: Auto-instrumentation Not Activating

**What goes wrong:** `register(auto_instrument=True)` is called but no spans appear in Phoenix.
**Why it happens:** `auto_instrument=True` only activates OpenInference instrumentors that are actually installed. If `openinference-instrumentation-langchain` is not in the venv, Phoenix silently receives no spans.
**How to avoid:** Verify `openinference-instrumentation-langchain` is in `pyproject.toml` dependencies. Test by running `uv run python -c "from openinference.instrumentation.langchain import LangChainInstrumentor; print('ok')"`.
**Warning signs:** Phoenix UI opens but shows 0 traces after a full run.

### Pitfall 2: register() Called After LangChain Imports

**What goes wrong:** LangGraph spans are not captured; only some LLM calls appear.
**Why it happens:** OpenTelemetry patching must occur before the target library is imported. If `from langchain_anthropic import ChatAnthropic` executes before `register()`, the instrumentor misses patching.
**How to avoid:** `init_tracing()` must be called before the lazy import of `run_pipeline` in `main()`. The current `run.py` pattern (lazy import inside `main()`) supports this correctly — keep it.
**Warning signs:** Spans appear for LLM calls but not for graph node execution.

### Pitfall 3: Concurrent Traces Bleed Into Each Other

**What goes wrong:** 30 recordings produce traces where recording_id metadata appears on the wrong trace, or spans from call_01 appear under call_02's trace.
**Why it happens:** OpenTelemetry context propagation uses Python contextvars. `asyncio.gather` spawns coroutines that share the parent context unless each task creates its own context snapshot. `using_attributes()` must be called inside the coroutine, not outside it.
**How to avoid:** Always place `using_attributes(...)` inside `process_one()`, not in the outer `run_pipeline()` scope.
**Warning signs:** Phoenix shows < 30 traces, or some traces have merged spans.

### Pitfall 4: px.launch_app() Fails Silently in Scripts

**What goes wrong:** `px.launch_app()` returns `None` and the rest of the code proceeds without a Phoenix server; traces are silently dropped.
**Why it happens:** In non-notebook environments, `launch_app()` can fail without raising an exception. The official docs recommend `phoenix serve` CLI for scripts.
**How to avoid:** Check `session is None` after calling `launch_app()`. If None, fall back to printing `http://localhost:6006` (user should run `phoenix serve` manually). Add a brief startup wait or poll `http://localhost:6006/health` before sending traces.
**Warning signs:** `session.url` raises `AttributeError` (NoneType has no attribute 'url').

### Pitfall 5: Temporary Directory Wiped Between Sessions

**What goes wrong:** Traces from run 1 are gone when run.py is executed again, breaking D-04 (persistent traces for Phase 5).
**Why it happens:** `px.launch_app(use_temp_dir=True)` (the default) stores traces in `/tmp` or equivalent, which is cleared on OS restart.
**How to avoid:** Always call `px.launch_app(use_temp_dir=False)` and set `PHOENIX_WORKING_DIR=.phoenix` (relative to project root, inside `.gitignore`).
**Warning signs:** Phoenix shows fresh 0-trace state at each run despite previous runs completing.

### Pitfall 6: PHOENIX_PROJECT vs PHOENIX_PROJECT_NAME env var

**What goes wrong:** Project name defaults to "default" in Phoenix UI despite setting `PHOENIX_PROJECT` in `.env`.
**Why it happens:** The Phoenix env var is `PHOENIX_PROJECT_NAME`, not `PHOENIX_PROJECT`. The CONTEXT.md D-11 says "PHOENIX_PROJECT" — this is the project's internal name for the env var; the value is passed to `register(project_name=...)` explicitly in code.
**How to avoid:** Read `PHOENIX_PROJECT` from `.env` in code, then pass its value to `register(project_name=value)`. Do not rely on Phoenix auto-reading `PHOENIX_PROJECT` from the environment.
**Warning signs:** Phoenix UI shows project named "default" despite having set the env var.

---

## Code Examples

Verified patterns from official sources:

### Context Managers for Span Metadata

```python
# Source: arize.com/docs/phoenix/tracing/how-to-tracing/add-metadata/customize-spans
from openinference.instrumentation import using_attributes

with using_attributes(
    metadata={
        "recording_id": "call_01",
        "model": "claude-sonnet-4-6",
        "prompt_version": "v1",
        "run_timestamp": "2026-03-27T12:00:00Z",
    },
    prompt_template_version="v1",
):
    result = await PIPELINE.ainvoke(initial_state)
```

### Phoenix Server Launch (Script Pattern)

```python
# Source: github.com/Arize-ai/phoenix session.py
import phoenix as px
from phoenix.otel import register

# Check if already running (idempotent)
session = px.active_session()
if session is None:
    session = px.launch_app(use_temp_dir=False)  # persistent SQLite

# Register instrumentation
register(project_name="phonebot-extraction", auto_instrument=True)

url = session.url if session else "http://localhost:6006"
```

### register() Full Signature

```python
# Source: arize.com/docs/phoenix/tracing/how-to-tracing/setup-tracing/setup-using-phoenix-otel
from phoenix.otel import register

tracer_provider = register(
    project_name="my-llm-app",   # ties spans to Phoenix project
    auto_instrument=True,         # discovers all installed OpenInference instrumentors
    batch=False,                  # synchronous export (better for short-lived scripts)
    endpoint=None,                # default: http://localhost:6006 gRPC
    protocol="grpc",              # or "http/protobuf"
    headers={},                   # empty for local server
)
```

**Note on `batch=False`:** For a CLI script that exits after completion, `batch=False` ensures all spans are exported before the process exits. `batch=True` (default) uses a background thread with buffering that may not flush if the process exits too quickly.

### Project Name via register() (Not env var)

```python
# Source: arize.com/docs/phoenix/tracing/how-to-tracing/setup-tracing/setup-projects
# CORRECT: pass to register() explicitly
register(project_name=os.getenv("PHOENIX_PROJECT", "phonebot-extraction"), auto_instrument=True)

# WRONG: PHOENIX_PROJECT env var is NOT read by Phoenix automatically
# (only PHOENIX_PROJECT_NAME is, and only in notebook environments)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `LangChainCallbackHandler` manual callbacks | `openinference-instrumentation-langchain` auto-instrumentation | 2024 (Phoenix v3+) | No callback code in application; instrumentor patches langchain-core at import time |
| `px.log_traces()` push-based | OTEL gRPC collector pull-based | 2023-2024 | Traces push to collector endpoint; works with any OTEL-compatible backend, not just Phoenix |
| Notebook-only `px.launch_app()` | `phoenix serve` CLI for scripts | Ongoing | Official recommendation: CLI for scripts; `launch_app()` still works with caveats |
| Per-span manual attribute setting | `using_attributes()` / `using_metadata()` context managers | 2024 | Idiomatic OpenInference pattern; propagates through async call chain without manual span handles |

**Deprecated/outdated:**
- `arize` package (the original paid Arize platform SDK): Do not confuse with `arize-phoenix`. This project uses `arize-phoenix` (open-source).
- `OpenInferenceMimeType` manual span construction: Superseded by context manager API.

---

## Open Questions

1. **px.launch_app() reliability in Python scripts**
   - What we know: Officially documented for notebooks; discouraged for scripts per GitHub issue #2711; `run_in_thread=True` (default) spawns a ThreadSession, which should work in scripts.
   - What's unclear: Whether Python 3.13 introduces any threading incompatibilities with Phoenix's server startup.
   - Recommendation: Implement `px.launch_app(use_temp_dir=False)` with a fallback message. If the session returns None, print a message instructing the user to run `phoenix serve` in a separate terminal. Validate empirically on first run.

2. **Transcribe node span visibility**
   - What we know: `openinference-instrumentation-langchain` instruments LangChain/LangGraph nodes. `transcribe_node` performs only file I/O (no LLM call).
   - What's unclear: Whether pure Python async functions in a StateGraph get auto-instrumented spans, or only nodes that invoke LangChain primitives.
   - Recommendation: Run a test trace after implementation. If `transcribe` span is absent, add a manual `tracer.start_as_current_span("transcribe")` context manager inside `transcribe_node`. D-10 requires this span to be visible.

3. **Span flushing before process exit**
   - What we know: `batch=False` in `register()` uses synchronous export. Phoenix client may buffer spans.
   - What's unclear: Whether all 30 spans reliably flush before `asyncio.run(main())` returns.
   - Recommendation: Call `tracer_provider.force_flush()` after pipeline completes and before printing the trace count message. Store the `tracer_provider` returned by `register()` for this.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 | All | ✓ | 3.13.2 | — |
| arize-phoenix | Phoenix server + UI | ✗ (not yet installed) | — | Must install via `uv add` |
| arize-phoenix-otel | OTEL registration | ✗ (not yet installed) | — | Must install via `uv add` |
| openinference-instrumentation-langchain | Auto-instrumentation | ✗ (not yet installed) | — | Must install via `uv add` |
| phoenix CLI (`phoenix serve`) | Alternative server start | ✗ (not in PATH) | — | px.launch_app() in-process |
| Port 6006 | Phoenix UI | Unknown | — | Configurable via PHOENIX_PORT env var |

**Missing dependencies with no fallback:**
- All three Phoenix packages must be installed before any implementation task can execute.

**Missing dependencies with fallback:**
- `phoenix serve` CLI: `px.launch_app()` serves as the in-process fallback (per D-01 decision).

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 0.25.0 |
| Config file | `pyproject.toml` → `[tool.pytest.ini_options]` (asyncio_mode = "auto") |
| Quick run command | `uv run pytest tests/test_observability.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OBS-01 | `init_tracing()` returns a URL string | unit | `uv run pytest tests/test_observability.py::test_init_tracing_returns_url -x` | ❌ Wave 0 |
| OBS-01 | `register()` is called with auto_instrument=True | unit (mock) | `uv run pytest tests/test_observability.py::test_register_called_with_auto_instrument -x` | ❌ Wave 0 |
| OBS-01 | `run_pipeline()` accepts prompt_version parameter | unit | `uv run pytest tests/test_observability.py::test_run_pipeline_accepts_prompt_version -x` | ❌ Wave 0 |
| OBS-01 | transcribe node span visible in trace | manual | Phoenix UI inspection after `uv run python run.py --prompt-version v1` | — |
| OBS-02 | `using_attributes()` wraps each `ainvoke()` call | unit (mock) | `uv run pytest tests/test_observability.py::test_using_attributes_wraps_ainvoke -x` | ❌ Wave 0 |
| OBS-02 | `--prompt-version` CLI arg added to run.py | unit | `uv run pytest tests/test_cli.py::test_prompt_version_arg -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_observability.py tests/test_cli.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_observability.py` — covers OBS-01, OBS-02 (unit + mock-based)
- [ ] `tests/test_cli.py` needs new test: `test_prompt_version_arg` — covers `--prompt-version` argparse addition (OBS-02)

*(Existing `tests/test_cli.py` and `tests/test_extract.py` already exist — extend, don't replace)*

---

## Sources

### Primary (HIGH confidence)
- [arize-phoenix 13.19.0 on PyPI](https://pypi.org/project/arize-phoenix/) — version, Python 3.13 support, release date
- [arize-phoenix-otel 0.15.0 on PyPI](https://pypi.org/project/arize-phoenix-otel/) — version, register() function
- [openinference-instrumentation-langchain 0.1.61 on PyPI](https://pypi.org/project/openinference-instrumentation-langchain/) — version, release date, langchain-core hooks
- [Phoenix session.py source (GitHub)](https://github.com/Arize-ai/phoenix/blob/main/src/phoenix/session/session.py) — launch_app() signature, session.url property, active_session() function
- [Phoenix customize-spans docs](https://arize.com/docs/phoenix/tracing/how-to-tracing/add-metadata/customize-spans) — using_attributes(), using_metadata() code examples
- [Phoenix setup-projects docs](https://arize.com/docs/phoenix/tracing/how-to-tracing/setup-tracing/setup-projects) — project_name parameter, PHOENIX_PROJECT_NAME env var behavior
- [Phoenix OTEL setup docs](https://arize.com/docs/phoenix/tracing/how-to-tracing/setup-tracing/setup-using-phoenix-otel) — register() full signature, environment variables

### Secondary (MEDIUM confidence)
- [LangGraph Tracing docs](https://arize.com/docs/phoenix/integrations/python/langgraph/langgraph-tracing) — LangChainInstrumentor covers LangGraph; verified by instrumentor PyPI description
- [LangChain Tracing docs](https://arize.com/docs/phoenix/integrations/python/langchain/langchain-tracing) — register(project_name=..., auto_instrument=True) pattern
- [Phoenix environments docs](https://arize.com/docs/phoenix/environments) — px.launch_app() for scripts, `phoenix serve` CLI recommendation
- [GitHub: bibekku/langgraph_with_phoenix](https://github.com/bibekku/langgraph_with_phoenix) — confirmed PHOENIX_PROJECT_NAME + openinference-instrumentation-langchain working pattern

### Tertiary (LOW confidence)
- [GitHub issue #2190 (openinference)](https://github.com/Arize-ai/openinference/issues/2190) — async ainvoke context propagation issue; using_attributes() inside process_one() as mitigation; issue marked open/unresolved as of reporting date

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all package versions verified against PyPI 2026-03-27
- Architecture: HIGH — register() + using_attributes() patterns from official Phoenix docs; session.py launch_app() from source
- Pitfalls: HIGH (pitfalls 1-5) / MEDIUM (pitfall 6 env var naming) — based on official docs + GitHub issue
- Async context propagation: MEDIUM — known issue documented, using_attributes() workaround unconfirmed as fully resolved for concurrent asyncio.gather

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (arize-phoenix releases frequently; verify versions before install)
