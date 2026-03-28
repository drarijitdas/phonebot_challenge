# Phase 7: Hardening - Research

**Researched:** 2026-03-28
**Domain:** LangGraph retry loops, Pydantic validation error handling, confidence flagging, final submission packaging
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Conditional edge in LangGraph graph — add a `validate` node after `extract` with a conditional edge: pass → END, fail → back to `extract` with error context injected into state. Max 2 retries (3 total attempts). If retries exhausted, proceed to END with partial/null result.
- **D-02:** Error context on retry = Pydantic validation error messages + original transcript text re-sent. Do NOT include the previous failed attempt output (avoids anchoring on bad extractions).
- **D-03:** Per-field confidence flagging at threshold 0.7. Fields with `confidence[field_name] < 0.7` are flagged. Each result in `results.json` gets a `flagged_fields` list (e.g., `["email", "phone_number"]`). Console prints a warning per flagged field during the run. No per-record aggregation needed.
- **D-04:** Extend existing `run.py` with a `--final` flag. Uses best model (Claude Sonnet 4.6) + best prompt (`extraction_v2.json`). Writes to `outputs/`:
  - `results.json` — per-recording extractions with `flagged_fields`
  - `scores.json` — per-field and overall accuracy
  - `comparison.json` — v1 vs v2 prompt accuracy, model comparison table, confidence distribution
- **D-05:** Console prints a summary table after the final run: overall accuracy, per-field accuracy, number of flagged fields, v1→v2 improvement delta.

### Claude's Discretion

- Exact validation error message formatting for retry prompt
- PipelineState field names for retry tracking (`retry_count`, `validation_errors`, etc.)
- Comparison report format details beyond the data points specified
- Whether `validate` node uses try/except or explicit Pydantic `model_validate`

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXT-04 | LangGraph retry loop re-prompts LLM on Pydantic validation failure with error context | LangGraph `add_conditional_edges` confirmed working for cyclic topology; `validate` node catches errors and routes back to `extract` |
| QUAL-02 | Low-confidence extractions are flagged with uncertainty metadata | `CallerInfo.confidence` dict field already in schema; flagging reads scores at 0.7 threshold; critical finding: LLM currently returns empty confidence dicts — confidence field description needs strengthening |

</phase_requirements>

## Summary

Phase 7 adds three capabilities to the existing pipeline: a LangGraph retry loop for Pydantic validation failures (EXT-04), per-field confidence flagging (QUAL-02), and a final submission run via `run.py --final`. All three build directly on existing infrastructure without requiring new dependencies.

The LangGraph conditional edge API is confirmed working for cyclic graphs in v1.1.3 (installed). The topology `START → transcribe → extract → validate → (pass: END | fail: extract)` compiles cleanly. `PipelineState` needs two new fields: `retry_count: int` and `validation_errors: Optional[list[str]]`. The `validate` node catches errors from LLM invocation, stores them in state, and the conditional edge routes back to `extract` which injects them into the prompt on retry.

**Critical finding:** The LLM is currently returning empty `confidence: {}` dicts in all 30 existing results (verified against `outputs/results_claude-sonnet-4-6.json`). The current description says "Omit keys for fields not attempted" — the LLM interprets this as permission to omit all keys. The confidence field description in `build_caller_info_model()` must be strengthened to require scores for all attempted fields. This is the only prerequisite not mentioned in CONTEXT.md that the plan must address.

**Primary recommendation:** Implement in two plans — Plan 01 adds retry loop + confidence flagging to `extract.py`, Plan 02 adds `--final` flag to `run.py` with submission artifacts.

## Standard Stack

### Core (already installed — no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langgraph | 1.1.3 | LangGraph graph topology, conditional edges, cyclic graph support | Already in project; `add_conditional_edges` confirmed working |
| pydantic | >=2.12.5 | ValidationError capture for retry trigger | Already in project; `ValidationError.errors()` provides structured error messages |
| rich | >=14.3.3 | Console warning output for flagged fields | Already in project; used in `run.py` |

### No new installations required

All dependencies are already present. Phase 7 is pure code changes.

**Installation:** None required.

**Version verification (confirmed with `uv pip show`):**
- langgraph: 1.1.3 (matches `pyproject.toml` constraint `>=1.1.3`)
- pydantic: >=2.12.5 (installed, `ValidationError` API stable across 2.x)

## Architecture Patterns

### Recommended Project Structure

No new files required for Plan 01. Plan 02 adds no new modules — all changes are in existing files:

```
src/phonebot/pipeline/extract.py    # Add validate_node, PipelineState fields, retry logic
run.py                              # Add --final flag, comparison logic, scores.json
tests/test_extract.py               # Update topology test + add retry unit tests
tests/test_cli.py                   # Add --final flag tests
outputs/                            # results.json, scores.json, comparison.json (generated)
```

### Pattern 1: LangGraph Cyclic Retry Topology

**What:** `validate` node after `extract` with conditional edge routing back on failure.
**When to use:** Any LangGraph workflow needing bounded retries on node failure.

```python
# Source: verified against langgraph 1.1.3 in project virtualenv
def build_pipeline() -> object:
    builder = StateGraph(PipelineState)
    builder.add_node("transcribe", transcribe_node)
    builder.add_node("extract", extract_node)
    builder.add_node("validate", validate_node)
    builder.add_edge(START, "transcribe")
    builder.add_edge("transcribe", "extract")
    builder.add_edge("extract", "validate")
    builder.add_conditional_edges(
        "validate",
        route_after_validate,
        {"end": END, "retry": "extract"},
    )
    return builder.compile()

def route_after_validate(state: PipelineState) -> str:
    """Route to END on pass or retry limit; route to 'extract' on validation failure."""
    if not state.get("validation_errors") or state.get("retry_count", 0) >= 2:
        return "end"
    return "retry"
```

Confirmed compiling: `add_conditional_edges("validate", fn, {"end": END, "retry": "extract"})` creates edges `validate->__end__` and `validate->extract`.

### Pattern 2: PipelineState Extension for Retry Tracking

**What:** Add two fields to the `PipelineState` TypedDict.
**When to use:** Any state that needs to track iteration-level context across retry cycles.

```python
class PipelineState(TypedDict):
    recording_id: str
    transcript_text: Optional[str]
    caller_info: Optional[dict]
    retry_count: int                          # new: 0-indexed, incremented by validate_node
    validation_errors: Optional[list[str]]    # new: populated by validate_node on failure
```

The `PIPELINE.ainvoke()` call in `process_one()` must seed these fields:

```python
final_state = await PIPELINE.ainvoke({
    "recording_id": recording_id,
    "transcript_text": None,
    "caller_info": None,
    "retry_count": 0,
    "validation_errors": None,
})
```

### Pattern 3: Validate Node with Error Context

**What:** `validate_node` checks the `caller_info` dict for Pydantic validity and populates error state.
**When to use:** After any LLM structured output node where validation failures are possible.

```python
async def validate_node(state: PipelineState) -> dict:
    """Validate extracted CallerInfo. On failure, store errors for retry context."""
    caller_info_cls = _get_caller_info_model()
    try:
        caller_info_cls.model_validate(state["caller_info"])
        # Pass: clear errors
        return {"validation_errors": None}
    except ValidationError as e:
        errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
        return {
            "validation_errors": errors,
            "retry_count": state.get("retry_count", 0) + 1,
        }
```

Note: `caller_info` is stored as `dict` (via `model_dump()`), so `model_validate` receives a dict — this is the correct call pattern.

### Pattern 4: Retry-Aware extract_node

**What:** `extract_node` injects validation error context into the LLM prompt on retry attempts.
**When to use:** Any extract node that participates in a retry loop.

```python
async def extract_node(state: PipelineState) -> dict:
    model = get_model(os.getenv("PHONEBOT_MODEL", "claude-sonnet-4-6"))
    caller_info_cls = _get_caller_info_model()
    structured_model = model.with_structured_output(caller_info_cls, method="json_schema")

    transcript = state["transcript_text"]
    validation_errors = state.get("validation_errors")

    if validation_errors:
        # D-02: error context = errors + original transcript, no previous failed output
        errors_text = "\n".join(f"- {e}" for e in validation_errors)
        prompt = (
            f"{transcript}\n\n"
            f"Previous extraction attempt returned invalid output. Validation errors:\n"
            f"{errors_text}\n"
            f"Re-extract carefully, ensuring all fields match their required types."
        )
    else:
        prompt = transcript

    result = await structured_model.ainvoke(prompt)
    return {"caller_info": result.model_dump()}
```

### Pattern 5: Confidence Flagging in process_one()

**What:** After pipeline returns, check each field's confidence score against 0.7 threshold.
**When to use:** Post-pipeline, before writing to `results.json`.

```python
CONFIDENCE_THRESHOLD = 0.7

def compute_flagged_fields(caller_info: dict) -> list[str]:
    """Return list of field names with confidence < threshold."""
    confidence = caller_info.get("confidence", {})
    return [
        field for field, score in confidence.items()
        if score < CONFIDENCE_THRESHOLD
    ]
```

Result record shape (D-03, D-04):
```python
{
    "id": recording_id,
    "caller_info": final_state["caller_info"],
    "flagged_fields": flagged_fields,     # new field
    "model": model_name,
    "timestamp": ...,
}
```

### Anti-Patterns to Avoid

- **Rebuilding PIPELINE per retry:** The existing `PIPELINE = build_pipeline()` at import time serves all recordings including retries. Do not add `build_pipeline()` calls inside `run_pipeline()` or retry logic.
- **Including previous failed output in retry prompt (D-02 violation):** Only send errors + original transcript. The failed extraction dict anchors the LLM on wrong values.
- **Re-raising ValidationError from validate_node:** The validate node stores errors in state and returns normally — LangGraph routes based on state, not exceptions.
- **Using state-level exception handling:** LangGraph graphs do not have try/except at the graph level. All error handling must be inside nodes.
- **Modifying PIPELINE after import:** The graph is compiled once. Retry logic lives in node code and state, not graph structure changes at runtime.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cyclic retry graph | Custom while loop around `run_pipeline()` | LangGraph `add_conditional_edges` with back-edge to `extract` | State persistence, Phoenix tracing per-node, clean termination condition |
| Structured error messages | String parsing of `ValidationError.__str__()` | `ValidationError.errors()` list → `err['loc']`, `err['msg']` | Stable structured format; `__str__` format changes between Pydantic versions |
| Confidence threshold logic | Custom percentile/z-score calculation | Read `CallerInfo.confidence` dict directly at 0.7 | Scores already provided by LLM; computing them again adds no information |
| Comparison report logic | New comparison engine | Extend existing `build_comparison()` in `compare.py` | Already handles N models, diffs, winner declaration |
| Accuracy computation | Custom field-level scoring | `compute_metrics()` from `phonebot.evaluation.metrics` | Already handles multi-value GT, E.164 normalization, casefold |

## Common Pitfalls

### Pitfall 1: Empty confidence dict (CRITICAL — currently broken)

**What goes wrong:** The LLM returns `confidence: {}` for all 30 recordings, making QUAL-02 flagging a no-op. Every result gets `flagged_fields: []` regardless of extraction difficulty.

**Why it happens:** The current confidence field description says "Omit keys for fields not attempted." Claude interprets this broadly and omits all keys. Verified: 0 of 30 existing records have non-empty confidence values.

**How to avoid:** Strengthen the confidence field description in `build_caller_info_model()` to require scores for all attempted fields. Example: "REQUIRED: Provide a confidence score for every extracted field. Example: `{"first_name": 0.9, "email": 0.4}`. Only omit a key if you did not attempt extraction for that field."

**Warning signs:** `flagged_fields: []` on all records even after Phase 7 changes. Check `caller_info["confidence"]` on the first result after a fresh run.

### Pitfall 2: validate_node receives None caller_info

**What goes wrong:** On the first graph invocation, `state["caller_info"]` is `None` (seeded as `None`). If `validate_node` tries to call `model_validate(None)` it raises `TypeError`, not `ValidationError`.

**Why it happens:** `extract_node` normally sets `caller_info`, but if `extract_node` raises an exception (e.g., API error), `validate_node` may receive the uninitialized `None`.

**How to avoid:** Guard in `validate_node`: `if state.get("caller_info") is None: return {"validation_errors": ["extract_node returned no output"], "retry_count": state.get("retry_count", 0) + 1}`.

### Pitfall 3: test_graph_topology breaks after validate node added

**What goes wrong:** The existing test asserts `("extract", "__end__") in edge_pairs`. After Phase 7, `extract` connects to `validate`, not directly to `__end__`. The test fails immediately on import.

**Why it happens:** Test was written for the Phase 3 topology and must be updated for Phase 7.

**How to avoid:** Update `test_graph_topology` to:
- Add assertion: `"validate" in node_names`
- Remove: `assert ("extract", "__end__") in edge_pairs`
- Add: `assert ("extract", "validate") in edge_pairs`
- Add: `assert ("validate", "__end__") in edge_pairs`
- Add: `assert ("validate", "extract") in edge_pairs` (back-edge for retry)
Also update `test_pipeline_state_fields` to assert `retry_count` and `validation_errors` present.

### Pitfall 4: Retry count not reset between recordings

**What goes wrong:** `PIPELINE` is compiled once and shared across all 30 concurrent `ainvoke()` calls. If `retry_count` bleeds between recordings, recordings processed after an error may skip retries.

**Why it happens:** State is per-invocation in LangGraph (each `ainvoke()` gets its own state dict). This is NOT a problem — verifying: `PIPELINE.ainvoke({"retry_count": 0, ...})` creates fresh state per call.

**How to avoid:** Seed `retry_count: 0` explicitly in the initial state dict passed to `ainvoke()`. This is already the correct pattern.

### Pitfall 5: With_structured_output does not raise ValidationError directly

**What goes wrong:** `with_structured_output(method="json_schema")` may raise `langchain_core.exceptions.OutputParserException` (wrapping the underlying Pydantic error) rather than `ValidationError` directly. If `validate_node` only catches `ValidationError`, it misses parser-level failures.

**Why it happens:** LangChain wraps raw LLM responses; JSON parsing failures are `OutputParserException`, while Pydantic type validation failures may be either.

**How to avoid:** The `validate_node` approach (validating the `caller_info` dict after extraction via `model_validate`) avoids this entirely — it catches `ValidationError` at the validation step, not at the LLM call step. The extract_node itself can remain unchanged (let LLM errors propagate naturally); the validate node performs the Pydantic check on the output dict.

**Alternative:** If the goal is to catch LLM call failures, wrap `extract_node`'s `ainvoke()` in `try: ... except (ValidationError, OutputParserException)` and store errors directly. However, this conflates LLM call errors with validation errors. The two-node approach (extract + validate) is cleaner per D-01.

### Pitfall 6: comparison.json v1 data source

**What goes wrong:** `--final` must produce a comparison of v1 vs v2 prompts. If v1 results are stale or missing from `outputs/`, the comparison will be incorrect or fail.

**Why it happens:** `outputs/results_claude-sonnet-4-6.json` was written with `prompt_version: v1`. The `--final` flag runs v2. The comparison needs both.

**How to avoid:** `--final` should load v1 results from `outputs/results_claude-sonnet-4-6.json` (prompt_version: v1) for comparison. If not present, re-run v1 first (or skip that section of comparison.json with a note). Do not assume v1 results always exist — add a guard.

### Pitfall 7: scores.json duplicates existing eval output

**What goes wrong:** `outputs/eval_results.json` (written by `metrics.py --main`) has the same structure as the proposed `scores.json`. If `--final` writes `scores.json` separately, there are two accuracy files with potentially different values.

**Why it happens:** `run.py` already computes metrics via `compute_metrics()` and prints them in a table. The `--final` flag adds a `scores.json` file write.

**How to avoid:** `scores.json` is the canonical final output (D-04). It should contain: `per_field`, `overall`, `prompt_version`, `model`, `timestamp`. `eval_results.json` is a development artifact; `scores.json` is the submission artifact. They can coexist.

## Code Examples

### LangGraph cyclic graph compilation (verified)

```python
# Source: verified in langgraph 1.1.3 virtualenv
from langgraph.graph import StateGraph, END, START

builder = StateGraph(PipelineState)
builder.add_node("transcribe", transcribe_node)
builder.add_node("extract", extract_node)
builder.add_node("validate", validate_node)
builder.add_edge(START, "transcribe")
builder.add_edge("transcribe", "extract")
builder.add_edge("extract", "validate")
builder.add_conditional_edges(
    "validate",
    route_after_validate,
    {"end": END, "retry": "extract"},
)
g = builder.compile()
# Confirms: edges include (validate, __end__) and (validate, extract)
```

### Pydantic ValidationError structured errors (verified)

```python
# Source: verified against pydantic >=2.12.5
from pydantic import ValidationError
try:
    CallerInfoModel.model_validate(state["caller_info"])
    return {"validation_errors": None}
except ValidationError as e:
    # e.errors() returns list of dicts with 'loc', 'msg', 'type' keys
    errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
    return {"validation_errors": errors, "retry_count": state["retry_count"] + 1}
```

### Confidence flagging (verified)

```python
# Source: developed from CallerInfo.confidence field structure
CONFIDENCE_THRESHOLD = 0.7

flagged_fields = [
    field
    for field, score in (caller_info.get("confidence") or {}).items()
    if score < CONFIDENCE_THRESHOLD
]
# Result: e.g. ["last_name", "email"] when those fields < 0.7
```

### Forced-failure test pattern

```python
# Source: project test patterns in tests/test_extract.py
@pytest.mark.asyncio
async def test_retry_on_validation_failure():
    """EXT-04: graph re-prompts with error context on Pydantic validation failure."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from pydantic import ValidationError

    call_count = 0

    async def mock_ainvoke(prompt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First attempt: return invalid dict (missing required structure)
            mock = MagicMock()
            mock.model_dump.return_value = {
                "first_name": 123,  # invalid type
                "last_name": None, "email": None, "phone_number": None, "confidence": {}
            }
            return mock
        # Second attempt: valid result
        mock = MagicMock()
        mock.model_dump.return_value = {
            "first_name": "Max", "last_name": None,
            "email": None, "phone_number": None, "confidence": {"first_name": 0.9}
        }
        return mock
    ...
```

Note: The forced-failure test works cleanest by mocking at the `validate_node` level — patch `_get_caller_info_model()` to return a model that rejects the first `model_validate()` call, then accepts the second. This tests the graph routing without mocking LLM internals.

### scores.json format (D-04)

```python
scores_payload = {
    "model": args.model,
    "prompt_version": "v2",
    "per_field": metrics["per_field"],      # {"first_name": 0.9, ...}
    "overall": metrics["overall"],           # 0.84
    "timestamp": datetime.now(timezone.utc).isoformat(),
}
Path("outputs/scores.json").write_text(
    json.dumps(scores_payload, ensure_ascii=False, indent=2), encoding="utf-8"
)
```

### comparison.json format (D-04)

```python
comparison_payload = {
    "prompt_comparison": {
        "v1": v1_metrics["per_field"],
        "v2": v2_metrics["per_field"],
        "delta": {
            field: v2_metrics["per_field"][field] - v1_metrics["per_field"][field]
            for field in FIELDS
        },
        "overall_v1": v1_metrics["overall"],
        "overall_v2": v2_metrics["overall"],
        "overall_delta": v2_metrics["overall"] - v1_metrics["overall"],
    },
    "model": args.model,
    "confidence_distribution": {
        "high_confidence": n_high,   # fields with confidence >= 0.7
        "low_confidence": n_low,     # fields with confidence < 0.7
        "no_confidence": n_empty,    # fields with empty confidence dict
        "total_fields": total,
    },
    "timestamp": datetime.now(timezone.utc).isoformat(),
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LangGraph linear graph only | LangGraph supports cyclic graphs via `add_conditional_edges` with back-edges | langgraph >=0.1.x | Retry loops are native graph topology, not external while loops |
| Pydantic v1 `ValidationError.messages` | Pydantic v2 `ValidationError.errors()` list with structured dicts | pydantic 2.0 | `errors()` provides `loc`, `msg`, `type`, `url` per error; use `errors()` not `str(e)` |

**Deprecated/outdated:**
- `StateGraph.add_edge(node, END)` for ALL terminal transitions: In Phase 7, `extract` no longer routes directly to `END` — the terminal edge moves to `validate`. The old `builder.add_edge("extract", END)` line must be removed.

## Open Questions

1. **Will the LLM actually populate confidence scores with improved description?**
   - What we know: 0 of 30 current results have non-empty confidence dicts; the current description says "Omit keys for fields not attempted"
   - What's unclear: Whether strengthening the description to "REQUIRED: provide scores for all extracted fields" is sufficient, or whether the json_schema method makes the LLM reliably fill dict fields
   - Recommendation: Plan 01 includes a confidence description fix. If the integration test still shows empty confidence after the fix, add an example to the description (e.g., `"Example output: {\"first_name\": 0.95, \"email\": 0.4}"`). This is a prompt engineering problem, not a code problem.

2. **Where does v1 results data come from for comparison.json?**
   - What we know: `outputs/results_claude-sonnet-4-6.json` exists with `prompt_version: v1`; it will be overwritten if `--final` writes to the same path
   - What's unclear: Whether `--final` writes to `outputs/results.json` (canonical final) or still to `outputs/results_claude-sonnet-4-6.json`
   - Recommendation: `--final` writes to `outputs/results.json` (not model-alias path). Before running v2, load existing `outputs/results_claude-sonnet-4-6.json` as the v1 baseline for comparison. If v1 file missing, emit a warning and omit the delta section from `comparison.json`.

## Environment Availability

All dependencies already installed. No external services required for Phase 7 beyond what prior phases use.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| langgraph | Retry graph topology | Yes | 1.1.3 | — |
| pydantic | ValidationError capture | Yes | >=2.12.5 | — |
| rich | Confidence warning console output | Yes | >=14.3.3 | — |
| ANTHROPIC_API_KEY | `--final` run | Env var required at runtime | — | Skip live run; unit tests mock LLM |
| outputs/results_claude-sonnet-4-6.json | v1 baseline for comparison.json | Yes (exists) | prompt_version: v1 | Warn and omit delta section |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 0.25.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`) |
| Quick run command | `uv run python -m pytest tests/test_extract.py tests/test_cli.py -x -q` |
| Full suite command | `uv run python -m pytest -q` |

Current baseline: 91 passed, 1 skipped. All tests pass in 4.44s.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXT-04 | Graph topology includes validate node and retry back-edge | unit | `uv run python -m pytest tests/test_extract.py::test_graph_topology -x` | Yes — UPDATE REQUIRED |
| EXT-04 | PipelineState includes retry_count and validation_errors | unit | `uv run python -m pytest tests/test_extract.py::test_pipeline_state_fields -x` | Yes — UPDATE REQUIRED |
| EXT-04 | Forced failure: graph re-prompts with error context, doesn't crash | unit | `uv run python -m pytest tests/test_extract.py::test_retry_on_validation_failure -x` | No — Wave 0 |
| EXT-04 | Retry exhaustion: after 2 retries proceeds to END with partial result | unit | `uv run python -m pytest tests/test_extract.py::test_retry_exhaustion_proceeds_to_end -x` | No — Wave 0 |
| QUAL-02 | compute_flagged_fields returns fields below 0.7 threshold | unit | `uv run python -m pytest tests/test_extract.py::test_compute_flagged_fields -x` | No — Wave 0 |
| QUAL-02 | results.json records include flagged_fields key | unit | `uv run python -m pytest tests/test_extract.py::test_result_includes_flagged_fields -x` | No — Wave 0 |
| D-04 | `--final` flag exists on CLI parser | unit | `uv run python -m pytest tests/test_cli.py::test_final_flag_exists -x` | No — Wave 0 |
| D-04 | `run.py --final` writes results.json, scores.json, comparison.json | integration (mocked) | `uv run python -m pytest tests/test_cli.py::test_final_writes_output_files -x` | No — Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run python -m pytest tests/test_extract.py tests/test_cli.py -x -q`
- **Per wave merge:** `uv run python -m pytest -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_extract.py` — update `test_graph_topology` (remove `extract->__end__` edge assertion, add `validate` node + edges)
- [ ] `tests/test_extract.py` — update `test_pipeline_state_fields` (add `retry_count`, `validation_errors`)
- [ ] `tests/test_extract.py` — add `test_retry_on_validation_failure` — covers EXT-04 forced failure
- [ ] `tests/test_extract.py` — add `test_retry_exhaustion_proceeds_to_end` — covers EXT-04 max retries
- [ ] `tests/test_extract.py` — add `test_compute_flagged_fields` — covers QUAL-02 threshold logic
- [ ] `tests/test_extract.py` — add `test_result_includes_flagged_fields` — covers QUAL-02 output shape
- [ ] `tests/test_cli.py` — add `test_final_flag_exists` — covers D-04 CLI argument
- [ ] `tests/test_cli.py` — add `test_final_writes_output_files` — covers D-04 file outputs (mocked pipeline)

## Sources

### Primary (HIGH confidence)

- Direct code inspection of `src/phonebot/pipeline/extract.py` — current graph topology, `PipelineState`, `extract_node`, `build_pipeline()`
- Direct code inspection of `src/phonebot/models/caller_info.py` — `CallerInfo.confidence` field structure
- Direct code inspection of `src/phonebot/prompts/__init__.py` — `build_caller_info_model()` factory
- Verified LangGraph 1.1.3 API in project virtualenv — `add_conditional_edges` with cyclic back-edge compiles correctly
- Verified Pydantic 2.x `ValidationError.errors()` API — structured error format
- Verified existing test suite — 91 tests pass baseline before Phase 7 changes
- Verified `outputs/results_claude-sonnet-4-6.json` — 0 of 30 records have non-empty confidence (critical finding)

### Secondary (MEDIUM confidence)

- LangGraph docs pattern for conditional routing (consistent with observed API behavior in verified tests)

### Tertiary (LOW confidence)

- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries installed and verified by import/execution in project virtualenv
- Architecture: HIGH — patterns verified by running code against actual installed versions
- Pitfalls: HIGH — critical empty confidence finding verified empirically; other pitfalls derived from code inspection and test behavior

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable deps, no breaking changes expected in this 30-day window)
