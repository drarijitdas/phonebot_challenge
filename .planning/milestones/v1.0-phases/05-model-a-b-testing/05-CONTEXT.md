# Phase 5: Model A/B Testing - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Pipeline supports swappable LLM backends via a model registry with a colon-prefix naming convention. Claude Sonnet 4.6 (API) and Llama 3.3 via Ollama (local) are the two A/B test models. Phoenix shows side-by-side traces tagged by model name. A separate compare script reads per-model result files and prints a Rich comparison table with per-field accuracy, latency, per-recording diffs, and overall winner summary.

</domain>

<decisions>
## Implementation Decisions

### Second model choice
- **D-01:** Compare Claude Sonnet 4.6 (Anthropic API) vs Llama 3.3 (Ollama local) — user chose Ollama over cloud-hosted alternatives for local control and flexibility
- **D-02:** Llama 3.3 is the default second model, but any Ollama-available model can be used at runtime via the colon-prefix convention

### Model registry & routing
- **D-03:** LangChain native registry pattern — a dict mapping model prefixes/names to LangChain chat model classes (`ChatAnthropic`, `ChatOllama`). No LiteLLM dependency.
- **D-04:** Registry lives in `src/phonebot/models/model_registry.py` — alongside CallerInfo in the models package
- **D-05:** `extract_node()` calls registry's `get_model(name).with_structured_output(CallerInfo)` instead of hardcoded `ChatAnthropic`
- **D-06:** Colon-prefix naming convention: `--model claude-sonnet-4-6` (Anthropic API), `--model ollama:llama3.3` (Ollama local). Registry parses the prefix to determine provider.

### Hosting & API keys
- **D-07:** Ollama runs locally — no cloud API key needed for the second model. Only ANTHROPIC_API_KEY required (already in .env).
- **D-08:** Fail fast if provider prerequisites are missing (e.g., Ollama not running, API key not set). Clear error message.

### Comparison workflow
- **D-09:** Separate runs + compare script — run pipeline twice (`--model claude-sonnet-4-6`, `--model ollama:llama3.3`), then a compare script reads both result files and prints comparison
- **D-10:** Model-specific result files: `outputs/results_{model_alias}.json` (e.g., `results_claude-sonnet-4-6.json`, `results_ollama_llama3.3.json`). Compare script globs `outputs/results_*.json`.
- **D-11:** Compare script (new `compare.py` or `--compare` flag) outputs Rich table to console + `outputs/comparison.json` for programmatic use — follows Phase 1 D-08 dual-output pattern

### Comparison metrics
- **D-12:** Per-field accuracy per model (first_name, last_name, email, phone_number) — core comparison
- **D-13:** Latency per model — average extraction time per recording, shows speed/accuracy tradeoff
- **D-14:** Per-recording diff — which specific recordings each model got right/wrong differently, highlights model strengths
- **D-15:** Overall winner summary — bold line declaring which model wins with overall accuracy percentage

### Claude's Discretion
- Exact model registry implementation details (dict structure, error handling)
- How ChatOllama handles structured output (JSON mode vs function calling)
- Compare script CLI design (standalone compare.py vs flag on run.py)
- Rich table layout and styling for comparison output
- How to extract latency from Phoenix traces or pipeline timing
- Whether to add `langchain-ollama` or `langchain-community` for ChatOllama

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project requirements
- `.planning/REQUIREMENTS.md` — Phase 5 requirements: AB-01, AB-02
- `.planning/PROJECT.md` — Core value, constraints, key decisions (LLM range: open-source through Claude Sonnet 4.6)

### Prior phase context
- `.planning/phases/01-foundation/01-CONTEXT.md` — D-01 (package structure), D-03 (env vars via .env), D-04 (Rich Console), D-07 (async concurrent), D-08 (dual output: console + JSON)
- `.planning/phases/03-extraction-pipeline/03-CONTEXT.md` — D-08 (with_structured_output), D-09 (one recording per graph invocation), D-11 (Claude Sonnet 4.6 baseline), D-12 (results.json structure)
- `.planning/phases/04-observability/04-CONTEXT.md` — D-04 (traces persist across runs), D-05 (one trace per recording), D-06 (--prompt-version tag), D-07 (model name in trace metadata), D-12 (Phoenix filterable by model)

### Existing code (critical — must read before implementing)
- `src/phonebot/pipeline/extract.py` — Current hardcoded ChatAnthropic in extract_node(), PHONEBOT_MODEL env var, run_pipeline() with model_name param
- `run.py` — CLI entrypoint with --model flag, writes outputs/results.json (currently overwritten each run)
- `src/phonebot/models/caller_info.py` — CallerInfo Pydantic model used with with_structured_output()
- `src/phonebot/observability/__init__.py` — Phoenix tracing init, already tags traces with model name

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `extract_node()` in `extract.py` — already reads model name from env var, just needs to swap `ChatAnthropic` for registry lookup
- `run_pipeline()` — already accepts `model_name` parameter and passes it to trace metadata
- `run.py --model` flag — already exists, just needs the registry to honor non-Anthropic values
- `compute_metrics()` in `metrics.py` — reusable for per-model evaluation in compare script
- Rich Console and Table patterns — established in run.py for accuracy output

### Established Patterns
- Environment vars via `.env` for API keys (ANTHROPIC_API_KEY) — Ollama needs no key, just a running server
- `with_structured_output(CallerInfo)` for typed extraction — must verify ChatOllama supports this
- `using_attributes()` for per-trace metadata — already tags model name, will naturally separate Claude vs Ollama traces in Phoenix
- Dual output (Rich console + JSON file) per Phase 1 D-08

### Integration Points
- `src/phonebot/models/model_registry.py` — NEW module: model factory/registry
- `src/phonebot/pipeline/extract.py` — Replace `ChatAnthropic` with registry call
- `run.py` — Change results output path to `outputs/results_{model}.json`
- `compare.py` (or run.py --compare) — NEW script: reads result files, computes comparison
- `pyproject.toml` — Add `langchain-ollama` (or `langchain-community`) dependency

</code_context>

<specifics>
## Specific Ideas

- User explicitly chose Ollama over Gemini/cloud providers — values local control and flexibility to try any model
- Colon-prefix convention (`ollama:llama3.3`) — allows ad-hoc model testing without registry changes
- Full comparison metrics (accuracy + latency + per-recording diff + winner) — user wants a comprehensive comparison for the technical discussion
- Separate runs + compare pattern — clean separation, each run is independent and produces its own result file

</specifics>

<deferred>
## Deferred Ideas

- **Other STT models** — Comparing Deepgram vs Whisper or other speech-to-text providers. Mentioned by user but outside Phase 5 scope (extraction LLM comparison, not STT). Could be a future phase.
- **Actor-critic approaches** — Using one model to extract and another to critique/refine for accuracy improvement. Overlaps with Phase 6 (GEPA optimization) or Phase 7 (hardening). Noted for roadmap backlog.

</deferred>

---

*Phase: 05-model-a-b-testing*
*Context gathered: 2026-03-27*
