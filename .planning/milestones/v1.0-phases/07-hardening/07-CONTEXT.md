# Phase 7: Hardening - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Add LangGraph retry loop that re-prompts the LLM on Pydantic validation failure with error context (EXT-04). Flag low-confidence extractions with uncertainty metadata (QUAL-02). Produce final submission run with comparison report via extended `run.py --final`.

</domain>

<decisions>
## Implementation Decisions

### Retry loop design
- **D-01:** Conditional edge in LangGraph graph — add a `validate` node after `extract` with a conditional edge: pass → END, fail → back to `extract` with error context injected into state. Max 2 retries (3 total attempts). If retries exhausted, proceed to END with partial/null result.
- **D-02:** Error context on retry = Pydantic validation error messages + original transcript text re-sent. Do NOT include the previous failed attempt output (avoids anchoring on bad extractions).

### Confidence flagging
- **D-03:** Per-field confidence flagging at threshold 0.7. Fields with `confidence[field_name] < 0.7` are flagged. Each result in `results.json` gets a `flagged_fields` list (e.g., `["email", "phone_number"]`). Console prints a warning per flagged field during the run. No per-record aggregation needed.

### Final submission run
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

</decisions>

<specifics>
## Specific Ideas

- Retry graph topology: `START → transcribe → extract → validate → (pass: END | fail: extract)` — the validate node is the decision point
- The existing `CallerInfo.confidence` dict field already provides per-field scores from the LLM — flagging reads these, doesn't compute them
- `with_structured_output(CallerInfo, method="json_schema")` is the current extraction method — retry wraps around this

</specifics>

<canonical_refs>
## Canonical References

### Pipeline architecture
- `src/phonebot/pipeline/extract.py` — Current graph topology, `extract_node`, `run_pipeline()`, `PipelineState` TypedDict
- `src/phonebot/models/caller_info.py` — CallerInfo schema with confidence dict field
- `src/phonebot/prompts/__init__.py` — `build_caller_info_model()` dynamic model construction

### Prompt versions
- `src/phonebot/prompts/extraction_v1.json` — Baseline prompt (exported from inline CallerInfo)
- `src/phonebot/prompts/extraction_v2.json` — GEPA-optimized prompt (+2% over v1)

### Prior phase decisions
- `.planning/phases/03-extraction-pipeline/03-CONTEXT.md` — D-06 graph topology, D-10 retry deferred to Phase 7
- `.planning/phases/06-prompt-optimization/06-CONTEXT.md` — GEPA optimization decisions, prompt versioning

### Requirements
- `.planning/REQUIREMENTS.md` — EXT-04 (retry loop), QUAL-02 (confidence flagging)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `PipelineState` TypedDict: Extend with `retry_count: int`, `validation_errors: Optional[list[str]]` for retry tracking
- `build_pipeline()`: Modify to add `validate` node and conditional edge
- `_get_caller_info_model()`: Already supports dynamic model swapping — retry uses the same model
- `CallerInfo.confidence` dict: Already populated by LLM — flagging reads from this

### Established Patterns
- Dynamic model injection via `set_caller_info_model()` / `_get_caller_info_model()` — retry doesn't change this
- `using_attributes()` trace tagging in `process_one()` — retry attempts should be visible in Phoenix traces
- `PIPELINE = build_pipeline()` at import time — single compiled graph serves all recordings

### Integration Points
- `extract_node`: Needs to accept optional error context from state (for retry attempts)
- `run_pipeline()`: No changes needed — retry is internal to the graph
- `run.py`: Add `--final` flag, comparison report logic, confidence flagging output
- `outputs/` directory: New target for final submission artifacts

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-hardening*
*Context gathered: 2026-03-28*
