# Retrospective

## Milestone: v1.0 — Audio Entity Extraction Pipeline

**Shipped:** 2026-03-28
**Phases:** 7 | **Plans:** 14 | **Timeline:** 3 days

### What Was Built

- Evaluation harness with E.164 phone normalization and multi-value ground truth support
- 30 German recordings transcribed via Deepgram Nova-3 with smart_format behavior documented
- LangGraph extraction pipeline achieving 82% baseline, 84% after optimization
- Arize Phoenix observability with 30 traces and span-level visibility
- Multi-model A/B testing: Claude Sonnet 83% vs Ollama with Rich comparison tables
- GEPA prompt optimization producing +2% accuracy improvement
- Retry loop with validation node, confidence flagging, and --final submission CLI

### What Worked

- **Data dependency ordering**: Building evaluation before extraction meant accuracy was measurable from the first pipeline run — caught comparison bugs early
- **Empirical verification before prompt writing**: Phase 2's smart_format analysis revealed spoken-form-only behavior, preventing invalid extraction prompt assumptions
- **Externalized prompts**: Moving from inline strings to JSON files (Phase 6) enabled GEPA optimization without touching pipeline code
- **TDD approach in Phase 7**: Writing failing tests first for retry loop caught edge cases (exact 0.7 boundary, None caller_info) that would have been missed

### What Was Inefficient

- **Missing VERIFICATION.md for Phase 3 and 6**: These had to be generated retroactively during milestone audit — should have been part of execute-phase workflow
- **SUMMARY.md one-liner field often empty**: Many summaries didn't populate the `one_liner` frontmatter field, making auto-extraction for MILESTONES.md unreliable
- **GEPA cost estimation**: No upfront cost estimate was done before running 17 optimization iterations with live API calls

### Patterns Established

- `CallerInfo.confidence` dict maps field names to float scores — reusable pattern for any structured extraction
- `build_caller_info_model()` factory creates dynamic Pydantic models from JSON — enables prompt versioning without code changes
- `model_registry.py` with prefix routing (`claude-*` -> ChatAnthropic, `ollama:*` -> ChatOllama) — extensible to new providers
- `compute_flagged_fields()` with configurable threshold — generic confidence flagging utility

### Key Lessons

- smart_format is language-dependent: German activates punctuation/paragraphs only, not phone/email formatting
- Diarization was unreliable for these recordings (single speaker label for all) — extraction prompts should not rely on speaker labels
- `with_structured_output(method="json_schema")` is more reliable than default method for complex Pydantic models
- `using_attributes()` must wrap individual `ainvoke()` calls (not outer scope) to prevent span context bleed in concurrent execution

### Cost Observations

- Model mix: ~90% Sonnet (executor/verifier agents), ~10% Opus (orchestration)
- Notable: Parallel executor agents in worktrees kept orchestrator context lean

---

## Cross-Milestone Trends

| Metric | v1.0 |
|--------|------|
| Phases | 7 |
| Plans | 14 |
| Timeline | 3 days |
| Requirements | 22/22 |
| Test count | 104 |
| Python LOC | 4,528 |
