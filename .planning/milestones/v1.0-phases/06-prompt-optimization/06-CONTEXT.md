# Phase 6: Prompt Optimization - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

GEPA optimizes the extraction system prompt and field descriptions offline against ground truth, using the DefaultAdapter API with Claude Opus 4.6 for reflection. The optimized prompt is saved as a JSON file that the pipeline loads at startup via a dynamic CallerInfo model rebuild. A standalone optimize.py script orchestrates the process with a 20/10 train/val split and documents accuracy deltas in an optimization report.

</domain>

<decisions>
## Implementation Decisions

### GEPA integration approach
- **D-01:** Use `gepa.optimize()` with DefaultAdapter for system prompt optimization. GEPA library installed via `pip install gepa`.
- **D-02:** Task LLM: `anthropic/claude-sonnet-4-6` (same model the pipeline uses). Reflection LLM: `anthropic/claude-opus-4-6` (stronger model for diagnosing failures and proposing prompt improvements).
- **D-03:** Evaluator provides per-recording diffs as Actionable Side Information (ASI): for each failed recording, log which fields were wrong, predicted vs expected values, and the relevant transcript excerpt. Maximizes signal for GEPA's reflection step.
- **D-04:** Standalone `optimize.py` script at project root (like `compare.py`). Run: `uv run python optimize.py`. Keeps optimization separate from the extraction pipeline.
- **D-05:** Evaluator invokes pipeline via direct function call — imports `run_pipeline()` and `compute_metrics()` in-process. No subprocess overhead, full access to per-recording diagnostics.
- **D-06:** GEPA optimization traces integrated with Phoenix — tag optimization-step traces with `prompt_version='gepa_opt_N'` so all GEPA exploration is visible in the dashboard.

### Prompt externalization
- **D-07:** JSON file with full prompt slots: `{"system_prompt": "...", "fields": {"first_name": "...", "last_name": "...", "email": "...", "phone_number": "..."}}`. System prompt = CallerInfo docstring, field keys = field descriptions.
- **D-08:** File lives at `src/phonebot/prompts/extraction_v1.json` (inside the package). GEPA-optimized version saved as `extraction_v2.json` (or higher).
- **D-09:** Dynamic CallerInfo rebuild via factory function (e.g., `build_caller_info_model(prompt_path)`) that reads JSON and creates a CallerInfo class with updated docstring and field descriptions. `extract_node` uses this dynamic model with `with_structured_output()`.
- **D-10:** Export current inline CallerInfo prompts as `extraction_v1.json` (baseline) as the first step. This becomes both the GEPA seed candidate AND the baseline for accuracy comparison. Pipeline then loads from file by default.

### Train/validation split
- **D-11:** Fixed seed random split: `seed=42`, 20 recordings for training, 10 for validation. Reproducible across runs.
- **D-12:** Split hardcoded in `optimize.py`. Train/val recording IDs documented in the optimization report output.

### Optimization target & budget
- **D-13:** GEPA optimizes ALL 5 prompt slots: system prompt (docstring) + 4 field descriptions (first_name, last_name, email, phone_number). Maximum optimization surface.
- **D-14:** Metric: weighted per-field accuracy — weight harder fields (email, last_name historically lower) higher to focus GEPA's attention on the biggest improvement opportunities. Weights derived from Phase 3/5 baseline accuracy (lower accuracy = higher weight).
- **D-15:** Budget: 150 `max_metric_calls`. Each call = extraction on 20 training recordings = ~3,000 total LLM calls to Claude Sonnet. Estimated cost: ~$3-10.
- **D-16:** Optimization report written to `outputs/optimization_report.json` with: baseline accuracy, optimized accuracy, delta per field, GEPA evolution history summary, path to optimized prompt file. Plus Rich console summary.

### Claude's Discretion
- Exact GEPA DefaultAdapter configuration and parameter tuning
- How to dynamically create Pydantic models with updated docstrings/field descriptions (create_model vs class mutation)
- Weighted accuracy formula (exact weight derivation from baseline)
- GEPA seed_candidate dict structure mapping to DefaultAdapter expectations
- Rich table layout for optimization report console output
- How to handle GEPA failures or early stopping
- Confidence field handling in the dynamic CallerInfo model

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project requirements
- `.planning/REQUIREMENTS.md` -- Phase 6 requirements: OPT-01, OPT-02
- `.planning/PROJECT.md` -- Core value, constraints, key decisions (GEPA for prompt optimization)

### Prior phase context
- `.planning/phases/01-foundation/01-CONTEXT.md` -- D-01 (package structure: src/phonebot/prompts/), D-02 (prompts live in Pydantic model), D-11 (Pydantic prompting system: docstring=system prompt, field descriptions=per-field instructions)
- `.planning/phases/03-extraction-pipeline/03-CONTEXT.md` -- D-01-D-05 (prompt strategy grounded in exact Deepgram patterns), D-08 (with_structured_output), D-11 (Claude Sonnet 4.6 baseline), D-12 (results.json structure)
- `.planning/phases/05-model-a-b-testing/05-CONTEXT.md` -- D-03 (model registry), D-05 (extract_node uses registry), D-09 (separate runs + compare pattern)

### GEPA library
- `https://github.com/gepa-ai/gepa` -- GEPA library documentation, DefaultAdapter API, optimize() function signature, Actionable Side Information concept

### Existing code (critical -- must read before implementing)
- `src/phonebot/models/caller_info.py` -- Current CallerInfo with inline prompts (docstring + field descriptions) -- this becomes extraction_v1.json seed
- `src/phonebot/pipeline/extract.py` -- extract_node using get_model() + with_structured_output(CallerInfo), run_pipeline() function for evaluator
- `src/phonebot/evaluation/metrics.py` -- compute_metrics() for evaluator scoring, matches_field() for per-recording diagnostics
- `src/phonebot/prompts/__init__.py` -- Currently empty; prompt loading logic goes here
- `run.py` -- CLI entrypoint with --prompt-version flag (already exists)
- `compare.py` -- Reference for standalone script pattern

### Data
- `data/ground_truth.json` -- Expected extractions for all 30 recordings (evaluator comparison target)
- `data/transcripts/call_*.json` -- Cached Deepgram transcripts (evaluator runs extraction against these)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `CallerInfo` model (`src/phonebot/models/caller_info.py`) -- Current inline prompts become the v1 seed candidate for GEPA
- `run_pipeline()` (`src/phonebot/pipeline/extract.py`) -- Direct import for evaluator; runs extraction on a list of recording IDs with model_name and prompt_version params
- `compute_metrics()` (`src/phonebot/evaluation/metrics.py`) -- Returns per-field accuracy and per-recording breakdown; per_recording data feeds GEPA's ASI diagnostics
- `matches_field()` (`src/phonebot/evaluation/metrics.py`) -- Per-field comparison with normalization; used to generate per-recording diff logs for GEPA
- `model_alias()` and `get_model()` (`src/phonebot/models/model_registry.py`) -- Model routing; evaluator uses `claude-sonnet-4-6`
- `init_tracing()` / `shutdown_tracing()` (`src/phonebot/observability/`) -- Phoenix integration; GEPA traces tagged with optimization step metadata
- Rich Console + Table patterns -- Established in run.py and compare.py; reuse for optimization report

### Established Patterns
- Standalone scripts at project root (run.py, compare.py) -- optimize.py follows same pattern
- Dual output: Rich console + JSON file (Phase 1 D-08) -- optimization report follows same pattern
- Environment vars via `.env` for API keys (ANTHROPIC_API_KEY needed for both task and reflection LLMs)
- `--prompt-version` flag on run.py already exists -- pipeline can load different prompt versions
- `using_attributes()` for Phoenix trace metadata -- tag GEPA optimization steps

### Integration Points
- `src/phonebot/prompts/extraction_v1.json` -- NEW: baseline prompt export (from current CallerInfo)
- `src/phonebot/prompts/extraction_v2.json` -- NEW: GEPA-optimized prompt output
- `src/phonebot/prompts/` -- NEW: prompt loading + CallerInfo factory function
- `optimize.py` -- NEW: standalone GEPA optimization script
- `src/phonebot/pipeline/extract.py` -- MODIFY: extract_node uses dynamic CallerInfo from prompt file instead of static import
- `outputs/optimization_report.json` -- NEW: optimization results with accuracy deltas
- `pyproject.toml` -- ADD: `gepa` dependency

</code_context>

<specifics>
## Specific Ideas

- User explicitly wants optimized prompt to follow the same Pydantic model structure -- load from JSON, rebuild CallerInfo dynamically, not a separate text-only prompt
- GEPA with DefaultAdapter (not DSPy or optimize_anything) -- higher-level API designed for system prompt optimization
- Opus for reflection, Sonnet for task execution -- invest in quality reflection to get better prompt mutations
- Phoenix integration for GEPA traces -- full visibility into the optimization process, not a black box
- Weighted per-field accuracy -- focus GEPA on improving the hardest fields (email, last_name) rather than overall average that might ignore weak spots

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 06-prompt-optimization*
*Context gathered: 2026-03-27*
