# Phase 1: Foundation - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Project scaffold, CallerInfo Pydantic schema, and evaluation harness ready before any pipeline run. Delivers: uv project setup (Python 3.13), CLI entrypoint, CallerInfo model with prompting system, and evaluation metrics with multi-value normalization and phone number E.164 comparison.

</domain>

<decisions>
## Implementation Decisions

### Project structure
- **D-01:** Flat `src/phonebot/` package with modules: `pipeline/`, `evaluation/`, `models/`, `observability/`, `prompts/`
- **D-02:** All prompts live in the Pydantic model code (docstring + field descriptions). GEPA will inject/modify at runtime rather than reading from externalized files.
- **D-03:** Environment vars + `.env` file for config (DEEPGRAM_API_KEY, ANTHROPIC_API_KEY, etc.). No pydantic-settings, just `os.environ` or `python-dotenv`.

### CLI design
- **D-04:** Rich library for all CLI output — no Typer. Manual argument handling with Rich Console for formatted output.
- **D-05:** Minimal CLI args: `--model` (LLM choice), `--recordings-dir` (default `data/recordings/`), `--output` (default `outputs/results.json`)
- **D-06:** Rich live table for progress display — showing each recording's status (transcribing/extracting/done) as it processes
- **D-07:** Async concurrent processing of recordings (not sequential)

### Evaluation reporting
- **D-08:** Dual output: Rich table to console for human review + JSON file at `outputs/eval_results.json` for programmatic use
- **D-09:** Per-field accuracy AND per-recording breakdown showing which fields were correct/wrong for each call

### CallerInfo model shape
- **D-10:** Include per-field confidence from the start: `confidence: dict[str, float]` (e.g., `{"first_name": 0.95, "email": 0.6}`)
- **D-11:** Pydantic prompting system: docstring = extraction context ("you are extracting from a German phone bot transcript"), Field descriptions = per-field extraction instructions (how to find and format each specific field)

### Claude's Discretion
- Exact Rich table styling and column widths
- .env loading implementation (dotenv vs manual)
- Exact module names within `src/phonebot/` (beyond the top-level layout)
- Evaluation JSON schema structure

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project requirements
- `.planning/REQUIREMENTS.md` -- Phase 1 requirements: INFRA-01, INFRA-02, EVAL-01, EVAL-02, EVAL-03, EVAL-04
- `.planning/PROJECT.md` -- Core value, constraints, key decisions

### Research
- `.planning/research/STACK.md` -- Package versions, integration patterns, Deepgram SDK v6 API shape
- `.planning/research/FEATURES.md` -- Table stakes features, evaluation requirements
- `.planning/research/PITFALLS.md` -- Pitfall 2 (eval exact-match), Pitfall 3 (LLM confabulation), Pitfall 4 (phone format)
- `.planning/research/SUMMARY.md` -- Synthesis of all research with roadmap implications

### Ground truth
- `data/ground_truth.json` -- Expected extraction results; inspect schema for multi-value field format before writing evaluation code

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None (greenfield project)

### Established Patterns
- None yet -- Phase 1 establishes the foundational patterns

### Integration Points
- `data/recordings/` -- 30 WAV files that the pipeline will process in Phase 2+
- `data/ground_truth.json` -- Evaluation harness reads this for comparison
- `src/phonebot/models/` -- CallerInfo model will be imported by pipeline nodes in Phase 3

</code_context>

<specifics>
## Specific Ideas

- Rich live table for progress (user explicitly chose this over progress bar or log lines)
- Async concurrent processing from the start (not deferred to later optimization)
- Confidence as per-field dict, not single overall score -- enables granular A/B comparison in Phase 5
- All prompts in Pydantic model code, not externalized -- GEPA adapts at runtime

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-03-26*
