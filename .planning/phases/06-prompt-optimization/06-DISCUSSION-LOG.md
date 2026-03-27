# Phase 6: Prompt Optimization - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md -- this log preserves the alternatives considered.

**Date:** 2026-03-27
**Phase:** 06-prompt-optimization
**Areas discussed:** GEPA integration approach, Prompt externalization, Train/validation split, Optimization target & budget

---

## GEPA Integration Approach

### Q1: What is GEPA?

| Option | Description | Selected |
|--------|-------------|----------|
| Specific library/package | Named Python package or tool | |
| DSPy-based optimization | DSPy prompt optimization, GEPA as placeholder | |
| Custom optimization loop | Build custom prompt optimization loop | |
| LangChain/LangSmith hub | LangChain's prompt optimization tooling | |

**User's choice:** Other -- provided link to https://github.com/gepa-ai/gepa (specific library)
**Notes:** GEPA is a real library: Genetic-Pareto framework for optimizing text parameters through LLM-based reflection and evolutionary search.

### Q2: Which GEPA API?

| Option | Description | Selected |
|--------|-------------|----------|
| optimize_anything | Most flexible, seed string + evaluator function | |
| gepa.optimize with DefaultAdapter | Higher-level API for system prompt optimization | ✓ |
| DSPy integration (dspy.GEPA) | Full DSPy pipeline with dspy.GEPA optimizer | |

**User's choice:** gepa.optimize with DefaultAdapter
**Notes:** None

### Q3: Reflection LLM?

| Option | Description | Selected |
|--------|-------------|----------|
| Claude Sonnet 4.6 (same as task) | Same model for both, simpler setup | |
| Claude Opus 4.6 (stronger reflector) | Stronger model for reflection, higher cost | ✓ |
| You decide | Let Claude pick | |

**User's choice:** Claude Opus 4.6 (stronger reflector)
**Notes:** None

### Q4: Diagnostic feedback to GEPA?

| Option | Description | Selected |
|--------|-------------|----------|
| Per-recording diffs | Log failed fields, predicted vs expected, transcript excerpt | ✓ |
| Aggregate metrics only | Just return overall + per-field accuracy | |
| You decide | Let Claude design | |

**User's choice:** Per-recording diffs
**Notes:** None

### Q5: Standalone script or subcommand?

| Option | Description | Selected |
|--------|-------------|----------|
| Standalone script | New optimize.py at project root | ✓ |
| Subcommand on run.py | --optimize flag on run.py | |
| Module entrypoint | uv run python -m phonebot.optimization | |

**User's choice:** Standalone script
**Notes:** None

### Q6: How evaluator invokes pipeline?

| Option | Description | Selected |
|--------|-------------|----------|
| Direct function call | Import run_pipeline() + compute_metrics() in-process | ✓ |
| Subprocess invocation | Shell out to uv run python run.py | |
| You decide | Let Claude pick | |

**User's choice:** Direct function call
**Notes:** None

### Q7: GEPA tracing integration?

| Option | Description | Selected |
|--------|-------------|----------|
| Separate logging | Console/file only, Phoenix stays for pipeline traces | |
| Phoenix integration | Tag GEPA traces in Phoenix with prompt_version | ✓ |
| You decide | Let Claude pick | |

**User's choice:** Phoenix integration
**Notes:** None

---

## Prompt Externalization

### Q8: What should the prompt JSON contain?

| Option | Description | Selected |
|--------|-------------|----------|
| Full prompt slots | system_prompt + per-field descriptions | ✓ |
| System prompt only | Just the class docstring text | |
| CallerInfo model_json_schema | Full Pydantic JSON schema with descriptions | |

**User's choice:** Full prompt slots
**Notes:** User had earlier stated "I want the optimized prompt to still follow the same pydantic model, but we should be able to just load the optimized json file in the pydantic base model."

### Q9: Where should the prompt JSON live?

| Option | Description | Selected |
|--------|-------------|----------|
| prompts/extraction_v1.json (project root) | Per ROADMAP success criteria | |
| src/phonebot/prompts/extraction_v1.json | Inside the package | ✓ |
| data/prompts/extraction_v1.json | In data directory | |

**User's choice:** src/phonebot/prompts/extraction_v1.json
**Notes:** None

### Q10: How to load prompt at startup?

| Option | Description | Selected |
|--------|-------------|----------|
| Dynamic CallerInfo rebuild | Factory function reads JSON, creates CallerInfo with updated prompts | ✓ |
| Template CallerInfo + override | Patches model's __doc__ and field descriptions at import time | |
| You decide | Let Claude pick | |

**User's choice:** Dynamic CallerInfo rebuild
**Notes:** None

### Q11: Export current inline prompts as v1?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, export as v1 | Step 1: export current prompts to extraction_v1.json as baseline/seed | ✓ |
| No, keep inline as fallback | v1 only created by GEPA, fallback to inline | |
| You decide | Let Claude handle | |

**User's choice:** Yes, export as v1
**Notes:** None

---

## Train/Validation Split

### Q12: How to split 30 recordings?

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed seed random split | seed=42, reproducible | ✓ |
| Difficulty-stratified split | Stratify by Phase 3/5 accuracy | |
| Hardest 10 as validation | Lowest accuracy recordings in validation | |
| You decide | Let Claude pick based on accuracy distribution | |

**User's choice:** Fixed seed random split
**Notes:** None

### Q13: Configurable or hardcoded?

| Option | Description | Selected |
|--------|-------------|----------|
| Hardcoded in optimize.py | Fixed seed=42, 20/10, documented in output | ✓ |
| Configurable via CLI flags | --train-size, --seed flags | |
| Split file on disk | train_ids.json and val_ids.json | |

**User's choice:** Hardcoded in optimize.py
**Notes:** None

---

## Optimization Target & Budget

### Q14: What should GEPA optimize?

| Option | Description | Selected |
|--------|-------------|----------|
| Both system + fields | All 5 prompt slots (docstring + 4 field descriptions) | ✓ |
| System prompt only | Only CallerInfo docstring, field descriptions stay fixed | |
| Field descriptions only | Keep system prompt fixed, optimize 4 fields | |

**User's choice:** Both system + fields
**Notes:** None

### Q15: Optimization metric?

| Option | Description | Selected |
|--------|-------------|----------|
| Overall accuracy | Average of per-field accuracies | |
| Weighted per-field accuracy | Weight harder fields higher | ✓ |
| Minimum field accuracy | Optimize worst-performing field | |
| You decide | Let Claude pick based on distribution | |

**User's choice:** Weighted per-field accuracy
**Notes:** None

### Q16: max_metric_calls budget?

| Option | Description | Selected |
|--------|-------------|----------|
| 150 calls | Default, ~3,000 LLM calls, ~$3-10 | ✓ |
| 100 calls (conservative) | ~2,000 LLM calls, ~$2-7 | |
| 250 calls (thorough) | ~5,000 LLM calls, ~$5-15 | |
| You decide | Configurable --max-calls flag | |

**User's choice:** 150 calls
**Notes:** None

### Q17: How to document results?

| Option | Description | Selected |
|--------|-------------|----------|
| Optimization report file | outputs/optimization_report.json + Rich console | ✓ |
| Console output only | Rich tables only, no persistent file | |
| You decide | Let Claude design | |

**User's choice:** Optimization report file
**Notes:** None

---

## Claude's Discretion

- Exact GEPA DefaultAdapter configuration and parameter tuning
- Dynamic Pydantic model creation approach (create_model vs class mutation)
- Weighted accuracy formula derivation
- GEPA seed_candidate dict structure
- Rich table layout for optimization report
- GEPA failure/early stopping handling
- Confidence field handling in dynamic CallerInfo

## Deferred Ideas

None -- discussion stayed within phase scope
