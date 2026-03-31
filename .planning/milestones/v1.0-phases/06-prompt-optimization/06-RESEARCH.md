# Phase 6: Prompt Optimization - Research

**Researched:** 2026-03-27
**Domain:** GEPA prompt optimization, Pydantic dynamic model construction, LiteLLM model naming
**Confidence:** MEDIUM — GEPA 0.1.1 released 2026-03-16, API verified from source. DefaultAdapter multi-slot behavior partially inferred.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Use `gepa.optimize()` with DefaultAdapter for system prompt optimization. GEPA library installed via `pip install gepa[full]`.
- **D-02:** Task LLM: `anthropic/claude-sonnet-4-6` (same model the pipeline uses). Reflection LLM: `anthropic/claude-opus-4-6` (stronger model for diagnosing failures and proposing prompt improvements).
- **D-03:** Evaluator provides per-recording diffs as Actionable Side Information (ASI): for each failed recording, log which fields were wrong, predicted vs expected values, and the relevant transcript excerpt. Maximizes signal for GEPA's reflection step.
- **D-04:** Standalone `optimize.py` script at project root (like `compare.py`). Run: `uv run python optimize.py`. Keeps optimization separate from the extraction pipeline.
- **D-05:** Evaluator invokes pipeline via direct function call — imports `run_pipeline()` and `compute_metrics()` in-process. No subprocess overhead, full access to per-recording diagnostics.
- **D-06:** GEPA optimization traces integrated with Phoenix — tag optimization-step traces with `prompt_version='gepa_opt_N'` so all GEPA exploration is visible in the dashboard.
- **D-07:** JSON file with full prompt slots: `{"system_prompt": "...", "fields": {"first_name": "...", "last_name": "...", "email": "...", "phone_number": "..."}}`. System prompt = CallerInfo docstring, field keys = field descriptions.
- **D-08:** File lives at `src/phonebot/prompts/extraction_v1.json` (inside the package). GEPA-optimized version saved as `extraction_v2.json` (or higher).
- **D-09:** Dynamic CallerInfo rebuild via factory function (e.g., `build_caller_info_model(prompt_path)`) that reads JSON and creates a CallerInfo class with updated docstring and field descriptions. `extract_node` uses this dynamic model with `with_structured_output()`.
- **D-10:** Export current inline CallerInfo prompts as `extraction_v1.json` (baseline) as the first step. This becomes both the GEPA seed candidate AND the baseline for accuracy comparison. Pipeline then loads from file by default.
- **D-11:** Fixed seed random split: `seed=42`, 20 recordings for training, 10 for validation. Reproducible across runs.
- **D-12:** Split hardcoded in `optimize.py`. Train/val recording IDs documented in the optimization report output.
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

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.

</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OPT-01 | GEPA optimizes extraction prompts offline against ground truth with train/validation split | GEPA 0.1.1 API verified: `gepa.optimize()` with DefaultAdapter, `trainset`/`valset` params, `max_metric_calls=150`. DefaultAdapter evaluator interface documented. Multi-slot candidate structure clarified. |
| OPT-02 | Optimized prompt is externalized to file and loaded at pipeline startup | `pydantic.create_model()` confirmed to produce JSON schema with `description` from `__doc__`. Factory function pattern verified in-venv. `extraction_v1.json` → `extraction_v2.json` file structure defined. `extract_node` dynamic model injection approach identified. |

</phase_requirements>

---

## Summary

Phase 6 adds two capabilities: (1) extracting current inline prompts to a JSON file that the pipeline loads at startup, and (2) running GEPA offline to produce an optimized prompt file. Both capabilities hinge on a `build_caller_info_model(prompt_path)` factory function that reads JSON and calls `pydantic.create_model()` to produce a CallerInfo class with the updated `__doc__` and field descriptions — verified in-venv to produce correct JSON schema.

GEPA 0.1.1 (released 2026-03-16) provides `gepa.optimize()` with DefaultAdapter. The library has **no base dependencies** (`dependencies = []` in pyproject.toml). LiteLLM, required by DefaultAdapter for API calls, lives in the `[full]` extra. Install is `pip install "gepa[full]"`. The optimize() API takes `seed_candidate: dict[str, str]`, `trainset`, `valset`, `task_lm`, `reflection_lm`, and `max_metric_calls`. GEPA automatically creates a DefaultAdapter when `task_lm` is provided and no custom adapter is passed.

The critical complexity in this phase is the evaluator interface and the GEPA-to-pipeline integration. DefaultAdapter's built-in evaluator only does substring matching; we must provide a custom `Evaluator` that calls `run_pipeline()` in-process and returns weighted accuracy. The evaluator also needs to produce per-recording failure diagnostics as Actionable Side Information (ASI) for GEPA's reflection LM. This requires understanding how DefaultAdapter's custom evaluator signature works and how to encode ASI into the `EvaluationResult` feedback string.

**Primary recommendation:** Use `gepa.optimize()` with DefaultAdapter + custom `Evaluator`, a `seed_candidate` dict with 5 keys (system_prompt + 4 field names), and asyncio in the evaluator to call `run_pipeline()`. Externalize prompt loading before wiring GEPA — that enables the evaluator to hot-swap prompts between calls.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| gepa | 0.1.1 | Prompt optimization via LLM reflection + Pareto search | Mandated by project (D-01). Only framework with GEPA algorithm. |
| pydantic | >=2.12.5 (already installed) | Dynamic CallerInfo model via `create_model()` | Already in pyproject.toml. `create_model()` with `__doc__` injection confirmed working. |
| rich | >=14.3.3 (already installed) | Optimization report console output | Project pattern from run.py / compare.py. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| litellm | >=1.64.0 (via gepa[full]) | HTTP calls to Anthropic API inside DefaultAdapter | Pulled in automatically by `gepa[full]` extra. Not called directly. |
| python-dotenv | >=1.2.2 (already installed) | Load ANTHROPIC_API_KEY for both task and reflection LLMs | Already loaded via `load_dotenv()` in extract.py |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `gepa.optimize()` | `gepa.optimize_anything()` | `optimize_anything` treats candidate as a plain string and uses `oa.log()` for ASI. Better for single-artifact optimization; weaker fit for structured 5-key prompt dict. `optimize()` + DefaultAdapter is the right API for structured candidate dicts. |
| `pydantic.create_model()` | class-level mutation (`CallerInfo.__doc__ = ...`) | Mutation is fragile — modifies shared class state, breaks tests that import CallerInfo directly. `create_model()` produces a new class each time with no side effects. |

**Installation:**
```bash
uv add "gepa[full]"
```

Adds `gepa[full]` to pyproject.toml dependencies. LiteLLM (>=1.64.0 for Python 3.13) is pulled transitively.

**Version verification (as of 2026-03-27):**
- `gepa`: 0.1.1 (released 2026-03-16) — confirmed via PyPI
- `litellm` (via gepa[full]): >=1.64.0 for Python < 3.14. Python 3.13 is in use.

---

## Architecture Patterns

### Recommended Project Structure

```
src/phonebot/prompts/
├── __init__.py           # load_prompt(path) + build_caller_info_model(path)
├── extraction_v1.json    # baseline: current CallerInfo inline prompts
└── extraction_v2.json    # GEPA-optimized output (created by optimize.py)

optimize.py               # standalone GEPA optimization script (project root)
outputs/
└── optimization_report.json  # accuracy delta report
```

### Pattern 1: Dynamic CallerInfo via create_model()

**What:** Factory function reads JSON prompt file and returns a new CallerInfo Pydantic class with updated docstring and field descriptions.

**When to use:** Any time the pipeline needs to load a non-inline prompt version. Also used by GEPA evaluator to hot-swap prompts between optimization iterations.

**Verified:** Tested in-venv. `create_model()` sets `__doc__` = JSON schema `description`. Field descriptions appear in `model_fields[name].description`. `with_structured_output(model, method='json_schema')` reads both correctly.

```python
# Source: verified in-venv with pydantic 2.12.5
from pydantic import create_model, Field
from typing import Optional
import json
from pathlib import Path

def build_caller_info_model(prompt_path: Path) -> type:
    """Read prompt JSON and return a CallerInfo class with updated prompts."""
    data = json.loads(prompt_path.read_text(encoding="utf-8"))
    system_prompt: str = data["system_prompt"]
    field_descs: dict[str, str] = data["fields"]

    fields = {
        name: (Optional[str], Field(default=None, description=desc))
        for name, desc in field_descs.items()
    }
    # confidence field must match original CallerInfo contract
    fields["confidence"] = (
        dict,
        Field(default_factory=dict, description="Per-field confidence scores between 0.0 and 1.0.")
    )
    Model = create_model("CallerInfo", **fields)
    Model.__doc__ = system_prompt
    return Model
```

**JSON schema result:** `description` = system_prompt, each property `description` = field description. Confirmed matching original CallerInfo structure.

### Pattern 2: extract_node with dynamic model injection

**What:** `extract_node` reads from a module-level variable `_CALLER_INFO_MODEL` (default: load from `prompts/extraction_v1.json`) instead of the hardcoded `from phonebot.models.caller_info import CallerInfo`. A `set_caller_info_model(model_class)` setter allows the evaluator to inject a candidate model before calling `run_pipeline()`.

**When to use:** Whenever the pipeline needs to be run with a non-default prompt version. This is the mechanism GEPA's evaluator uses to test each candidate.

```python
# In src/phonebot/pipeline/extract.py (modified)
# Module-level state: set once per optimize.py run, read by extract_node
_CALLER_INFO_MODEL: type = None  # set at startup from prompt file

def set_caller_info_model(model_class: type) -> None:
    """Inject a dynamic CallerInfo model for GEPA optimization iterations."""
    global _CALLER_INFO_MODEL
    _CALLER_INFO_MODEL = model_class

async def extract_node(state: PipelineState) -> dict:
    model = get_model(os.getenv("PHONEBOT_MODEL", "claude-sonnet-4-6"))
    caller_info_cls = _CALLER_INFO_MODEL or CallerInfo  # fallback to static
    structured_model = model.with_structured_output(caller_info_cls, method="json_schema")
    result = await structured_model.ainvoke(state["transcript_text"])
    return {"caller_info": result.model_dump()}
```

**Important note:** The LangGraph `PIPELINE` object is compiled at import time. Fortunately, the PIPELINE graph topology (nodes and edges) does not change between prompt versions — only the CallerInfo class used inside `extract_node` changes. Since `extract_node` reads `_CALLER_INFO_MODEL` at call time (not compile time), the single compiled PIPELINE can be reused across all GEPA iterations.

### Pattern 3: GEPA DefaultAdapter custom evaluator

**What:** Custom `Evaluator` class implementing the `(data: DefaultDataInst, response: str) -> EvaluationResult` protocol. For the phonebot use case, the evaluator receives the transcript as `data["input"]` and the raw LLM JSON response as `response`, parses the JSON into CallerInfo fields, and scores against ground truth.

**When to use:** DefaultAdapter's built-in `ContainsAnswerEvaluator` only does substring match — useless for structured extraction. Custom evaluator is required.

**ASI strategy:** The evaluator's `EvaluationResult` includes a `feedback` string. Populate it with per-field failure details: field name, predicted value, expected value. This is what GEPA's reflection LM reads to generate targeted prompt improvements.

```python
# Source: inferred from DefaultAdapter source + EvaluationResult structure
from gepa.adapters.default_adapter import Evaluator, EvaluationResult
from phonebot.evaluation.metrics import matches_field, FIELDS

class PhonebotEvaluator:
    """Weighted per-field accuracy evaluator with ASI feedback."""

    def __init__(self, ground_truth: dict, field_weights: dict[str, float]):
        self.ground_truth = ground_truth
        self.field_weights = field_weights  # e.g., {"email": 0.35, "last_name": 0.30, ...}

    def __call__(self, data: "DefaultDataInst", response: str) -> "EvaluationResult":
        recording_id = data["additional_context"]["recording_id"]
        expected = self.ground_truth.get(recording_id, {})

        # Parse LLM response into CallerInfo fields
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            feedback = f"JSON parse error. Raw response: {response[:200]}"
            return EvaluationResult(score=0.0, feedback=feedback)

        # Weighted accuracy + ASI feedback
        weighted_score = 0.0
        failures = []
        for field in FIELDS:
            predicted = parsed.get(field)
            gt_val = expected.get(field)
            correct = matches_field(field, predicted, gt_val)
            w = self.field_weights.get(field, 0.25)
            if correct:
                weighted_score += w
            else:
                failures.append(
                    f"  {field}: predicted={predicted!r}, expected={gt_val!r}"
                )

        feedback = "OK" if not failures else "Failures:\n" + "\n".join(failures)
        return EvaluationResult(score=weighted_score, feedback=feedback)
```

### Pattern 4: GEPA optimize() call structure

**What:** The main `gepa.optimize()` call used in optimize.py. Uses DefaultAdapter automatically when `task_lm` is provided.

**Critical:** DefaultAdapter's `evaluate()` uses `next(iter(candidate.values()))` as the system message — it takes the **first value** of the seed_candidate dict. This means multi-slot optimization (5 keys) requires a **custom GEPAAdapter** or a different approach.

**Multi-slot reality check:** DefaultAdapter is designed for single-slot system prompt optimization (`{"system_prompt": "..."}` — one key). For 5-slot optimization (system_prompt + 4 field descriptions), we have two options:

1. **Serialize all 5 slots into one string candidate** and deserialize in the evaluator (workaround, loses per-slot guidance for reflection)
2. **Write a custom GEPAAdapter** subclassing `GEPAAdapter` that handles the multi-slot dict, invokes the LLM with system_prompt and structured field descriptions, and returns per-recording `EvaluationBatch`. This gives GEPA's reflection LM visibility into which specific slot caused a failure.

Option 2 (custom adapter) is the correct approach for D-13 (optimize all 5 slots). The custom adapter overrides `evaluate()` to:
- Build a dynamic CallerInfo model from the candidate dict
- Call `run_pipeline()` on the trainset recordings
- Score with weighted per-field accuracy
- Return `EvaluationBatch` with per-recording scores and trajectory feedback

```python
# Source: inferred from GEPAAdapter Protocol and DefaultAdapter source
import gepa
from gepa import GEPAAdapter, EvaluationBatch

# seed_candidate structure for 5-slot optimization (D-13)
seed_candidate = {
    "system_prompt": "<current CallerInfo.__doc__>",
    "first_name": "<current first_name Field description>",
    "last_name": "<current last_name Field description>",
    "email": "<current email Field description>",
    "phone_number": "<current phone_number Field description>",
}

result = gepa.optimize(
    seed_candidate=seed_candidate,
    trainset=train_data,   # list of DefaultDataInst
    valset=val_data,       # list of DefaultDataInst
    adapter=PhonebotAdapter(ground_truth=gt, field_weights=weights),  # custom adapter
    reflection_lm="claude-opus-4-6",  # LiteLLM model name
    max_metric_calls=150,
    seed=42,
    run_dir="outputs/gepa_run/",
)

optimized_candidate = result.best_candidate
# optimized_candidate is a dict[str, str] with same keys as seed_candidate
```

### Pattern 5: Weighted field accuracy formula

**What:** Derives field weights from Phase 5 baseline accuracy. Harder fields get higher weight.

**Baseline (Phase 5, Claude Sonnet 4.6, 30 recordings):**
- first_name: 90% → weight inversely proportional
- last_name: 77% → medium-high weight
- email: 67% → highest weight (most room to improve)
- phone_number: 100% → minimal weight (already perfect)

**Formula:** `weight(field) = (1 - baseline_accuracy(field)) / sum(1 - baseline_accuracy(f) for f in FIELDS)`

```python
# Baseline from Phase 5
BASELINE = {
    "first_name": 0.90,
    "last_name": 0.767,
    "email": 0.667,
    "phone_number": 1.00,
}

raw_weights = {f: 1.0 - acc for f, acc in BASELINE.items()}
total = sum(raw_weights.values())
FIELD_WEIGHTS = {f: w / total for f, w in raw_weights.items()}
# Result: phone_number=0.0, email~0.42, last_name~0.30, first_name~0.13
# But phone_number=0 means no signal -- consider a floor of 0.05
```

**Note:** phone_number at 100% accuracy produces weight=0. Consider a minimum floor (e.g., 0.05) so GEPA doesn't completely ignore phone_number fields in its reflection.

### Pattern 6: DefaultDataInst structure

**What:** The data format DefaultAdapter (and custom adapters extending it) expect for each training/validation example.

**Structure (from DefaultAdapter source):**

```python
class DefaultDataInst(TypedDict):
    input: str              # transcript text
    additional_context: dict[str, str]  # arbitrary metadata
    answer: str             # used by ContainsAnswerEvaluator (not needed for custom)
```

For phonebot: `input` = transcript text, `additional_context` = `{"recording_id": "call_01"}`, `answer` = ignored (custom evaluator overrides it).

```python
# Build trainset from recording IDs + cached transcripts
from phonebot.pipeline.transcribe import get_transcript_text
from pathlib import Path

def build_dataset(recording_ids: list[str]) -> list[dict]:
    dataset = []
    for rec_id in recording_ids:
        transcript = get_transcript_text(Path(f"data/transcripts/{rec_id}.json"))
        dataset.append({
            "input": transcript,
            "additional_context": {"recording_id": rec_id},
            "answer": "",  # unused with custom evaluator
        })
    return dataset
```

### Anti-Patterns to Avoid

- **Rebuilding PIPELINE per GEPA iteration:** PIPELINE compilation is expensive and happens at import time. The module-level `_CALLER_INFO_MODEL` approach avoids this — keep one compiled PIPELINE, swap the model class via setter before each `run_pipeline()` call.
- **Using subprocess for evaluator:** `run_pipeline()` is importable. Direct function call avoids cold-start overhead and enables in-process per-recording diagnostics.
- **Multi-slot optimization via DefaultAdapter's `task_lm` path:** DefaultAdapter only passes the first candidate value as system prompt. It cannot handle 5-slot dicts correctly. Use a custom adapter class.
- **Forgetting `asyncio.run()` in the evaluator:** `run_pipeline()` is async. The GEPA evaluator is called synchronously by GEPA's engine. Wrap with `asyncio.run()` or `asyncio.get_event_loop().run_until_complete()`.
- **Hardcoding weight=0 for phone_number:** Perfect baseline accuracy → zero weight → GEPA ignores phone_number entirely, missing regressions. Use a floor weight.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Prompt reflection + mutation loop | Custom gradient-free optimizer | `gepa.optimize()` | GEPA handles Pareto frontier tracking, minibatch sampling, reflection LM prompting, early stopping — 500+ lines of optimization machinery |
| LLM API batching in evaluator | Manual asyncio batch execution | DefaultAdapter's `batch_complete()` or direct `run_pipeline()` | `run_pipeline()` already has semaphore-bounded concurrency (EXTRACT_CONCURRENCY env var) |
| Prompt versioning file format | Custom YAML/TOML prompt store | JSON with 5 keys (D-07) | Minimal, human-readable, trivially parseable with `json.loads()` |
| Tracking optimization progress | Custom metrics logger | GEPA's `run_dir` parameter | GEPA writes iteration history to `run_dir` automatically when specified |

**Key insight:** GEPA's value is in the reflection loop — reading full execution traces and proposing targeted text improvements. Don't reduce it to a scalar optimizer. Feed it rich ASI (per-field failure strings) to get useful reflections.

---

## Runtime State Inventory

> Phase 6 is greenfield (new files, modified extract.py). No rename/refactor involved.

Not applicable — no runtime state migration required.

---

## Common Pitfalls

### Pitfall 1: DefaultAdapter only uses first candidate value

**What goes wrong:** Calling `gepa.optimize()` with `task_lm="..."` and a 5-slot seed_candidate produces a DefaultAdapter that passes only `next(iter(candidate.values()))` as the system prompt. The 4 field description slots are ignored.

**Why it happens:** DefaultAdapter was designed for single-slot system prompt optimization. Its `evaluate()` method does `system_content = next(iter(candidate.values()))`.

**How to avoid:** Use a custom GEPAAdapter subclass for 5-slot optimization. The custom adapter builds a dynamic CallerInfo model from the full candidate dict before running extraction.

**Warning signs:** GEPA only mutates the `system_prompt` key; field description keys remain unchanged across iterations.

### Pitfall 2: asyncio conflict between GEPA and run_pipeline()

**What goes wrong:** `run_pipeline()` uses `asyncio.gather()` internally. If called from within a synchronous function that GEPA invokes, `asyncio.run()` creates a new event loop — which conflicts if an outer event loop is already running.

**Why it happens:** GEPA's engine calls the evaluator synchronously. If optimize.py itself uses `asyncio.run(gepa.optimize(...))`, there's a nested loop problem.

**How to avoid:** Structure optimize.py as a synchronous script — `gepa.optimize()` is called synchronously (it is not a coroutine). The evaluator wraps `run_pipeline()` with `asyncio.run()`. Since `gepa.optimize()` is not inside an outer event loop, this is safe.

**Warning signs:** `RuntimeError: This event loop is already running` at evaluation time.

### Pitfall 3: Stale PIPELINE after CallerInfo model swap

**What goes wrong:** `PIPELINE` is compiled once at import time. If `extract_node` imports `CallerInfo` at function scope using `from phonebot.models.caller_info import CallerInfo`, swapping `_CALLER_INFO_MODEL` won't help because the function re-imports the static class each call.

**Why it happens:** Python's import caching — `from X import Y` binds the name at import time only.

**How to avoid:** `extract_node` must read `_CALLER_INFO_MODEL` via the module-level global, not via a local `from ... import CallerInfo`. Use `phonebot.pipeline.extract._CALLER_INFO_MODEL` as the injection point.

**Warning signs:** All GEPA iterations produce identical accuracy despite different candidate prompts.

### Pitfall 4: LiteLLM model name mismatch

**What goes wrong:** Passing `"claude-sonnet-4-6"` (no provider prefix) or `"anthropic/claude-sonnet-4-6"` (wrong casing) to `task_lm` or `reflection_lm` causes LiteLLM to fail with a model-not-found error.

**Why it happens:** LiteLLM model registry uses exact string matching. GEPA passes the `task_lm` / `reflection_lm` strings directly to LiteLLM.

**How to avoid:** LiteLLM's model price file (verified 2026-03-27) contains both `"claude-sonnet-4-6"` and `"claude-opus-4-6"` as valid names (no `anthropic/` prefix needed for direct Anthropic API). Use these exact strings.

**Warning signs:** `litellm.exceptions.BadRequestError` or `LiteLLM.ModelNotFoundError` on first GEPA iteration.

### Pitfall 5: GEPA cost estimation — 150 calls x 20 recordings

**What goes wrong:** Under-budgeting leads to optimization abort mid-run. Over-budgeting wastes ~$10.

**Why it happens:** Each `max_metric_calls` evaluation invokes `run_pipeline()` on 20 recordings, each of which calls Claude Sonnet once. Plus reflection LM (Claude Opus) calls.

**Concrete estimate (D-15):**
- Task LLM (Sonnet) calls: 150 iterations × 20 recordings = 3,000 calls
- Reflection LLM (Opus) calls: ~150 reflection steps (1 per iteration)
- At ~$3 per 1000 Sonnet input tokens (avg transcript ~500 tokens + prompt ~1000): ~$4-6 for Sonnet
- Opus at ~$15/1M input: reflection prompts are longer but fewer → ~$1-3
- **Total estimated: $5-9 for a full 150-iteration run**

**How to avoid:** Run a 5-iteration smoke test first (`max_metric_calls=5`) to verify evaluator works before committing to full budget.

**Warning signs:** No warning — costs accumulate silently. Check Anthropic usage dashboard.

### Pitfall 6: Weighted accuracy with zero-weight field

**What goes wrong:** phone_number has 100% baseline accuracy → weight = 0.0 → GEPA never receives signal about phone_number regressions → an optimized prompt might break phone extraction silently.

**Why it happens:** The inverse-accuracy weighting formula produces 0 for perfect fields.

**How to avoid:** Apply a minimum weight floor (e.g., 0.05). Redistribute: `weight = max(raw_weight, 0.05)` before normalization.

**Warning signs:** Optimized prompt achieves higher overall weighted accuracy but phone_number accuracy drops from 100% to 80%.

### Pitfall 7: Dynamic model confidence field

**What goes wrong:** `build_caller_info_model()` omits the `confidence` field, causing `model_dump()` to miss it. Code that reads `caller_info["confidence"]` breaks.

**Why it happens:** `confidence` is a special field not in the `fields` JSON key — it's not part of the optimization surface.

**How to avoid:** Always add `confidence` field explicitly in `build_caller_info_model()` after building the optimization slots. Its description stays constant.

---

## Code Examples

Verified patterns from in-venv testing and GEPA source analysis:

### Exporting current CallerInfo prompts to extraction_v1.json

```python
# Source: caller_info.py + in-venv verification
import json
from pathlib import Path
from phonebot.models.caller_info import CallerInfo

def export_v1_prompt(output_path: Path) -> None:
    """Export current inline CallerInfo prompts to extraction_v1.json."""
    payload = {
        "system_prompt": CallerInfo.__doc__.strip(),
        "fields": {
            name: info.description
            for name, info in CallerInfo.model_fields.items()
            if name != "confidence"  # confidence is not an optimization slot
        }
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
```

### Building dynamic CallerInfo from JSON

```python
# Source: verified in-venv with pydantic 2.12.5
from pydantic import create_model, Field
from typing import Optional
import json
from pathlib import Path

def build_caller_info_model(prompt_path: Path) -> type:
    data = json.loads(prompt_path.read_text(encoding="utf-8"))
    system_prompt = data["system_prompt"]
    field_descs = data["fields"]

    fields = {
        name: (Optional[str], Field(default=None, description=desc))
        for name, desc in field_descs.items()
    }
    fields["confidence"] = (
        dict,
        Field(
            default_factory=dict,
            description=(
                "Per-field confidence scores between 0.0 and 1.0. "
                "Keys match field names. Omit keys for fields not attempted."
            )
        )
    )
    Model = create_model("CallerInfo", **fields)
    Model.__doc__ = system_prompt
    return Model
```

### seed_candidate construction for 5-slot GEPA

```python
# Source: derived from D-13 + DefaultDataInst structure
import json
from pathlib import Path

def build_seed_candidate(prompt_path: Path) -> dict[str, str]:
    """Build GEPA seed_candidate from extraction_v1.json."""
    data = json.loads(prompt_path.read_text(encoding="utf-8"))
    return {
        "system_prompt": data["system_prompt"],
        **data["fields"],  # first_name, last_name, email, phone_number
    }
    # Result: {"system_prompt": "...", "first_name": "...", "last_name": "...",
    #          "email": "...", "phone_number": "..."}
```

### Saving optimized candidate to extraction_v2.json

```python
# Source: inverse of export_v1_prompt
def save_optimized_prompt(candidate: dict[str, str], output_path: Path) -> None:
    """Save GEPA-optimized candidate as extraction_v2.json."""
    payload = {
        "system_prompt": candidate["system_prompt"],
        "fields": {
            k: v for k, v in candidate.items() if k != "system_prompt"
        }
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
```

### Fixed train/val split with seed=42

```python
# Source: D-11 + Python random module
import random

def make_train_val_split(
    all_ids: list[str],
    n_train: int = 20,
    seed: int = 42,
) -> tuple[list[str], list[str]]:
    rng = random.Random(seed)
    shuffled = list(all_ids)
    rng.shuffle(shuffled)
    return shuffled[:n_train], shuffled[n_train:]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual prompt iteration | GEPA automated reflection + mutation | 2025-2026 | Replaces human trial-and-error with LLM-guided optimization in 100-500 evals |
| Single-slot prompt optimization | Multi-slot (system + field descriptions) | GEPA 0.1+ | Each slot optimized independently; reflection identifies which slot caused failure |

**Deprecated/outdated:**
- `optimize_anything` API: Works for single-string artifacts. For multi-slot structured candidates, `gepa.optimize()` with a custom GEPAAdapter is the correct path (GEPA 0.1.1+).

---

## Open Questions

1. **Custom GEPAAdapter: make_reflective_dataset() signature**
   - What we know: GEPAAdapter Protocol requires `evaluate()` and `make_reflective_dataset()`. DefaultAdapter's implementation creates records with `"Inputs"`, `"Generated Outputs"`, `"Feedback"` keys.
   - What's unclear: Whether a minimal custom adapter must implement `make_reflective_dataset()` or can inherit it. The Protocol may allow partial implementation.
   - Recommendation: Read `src/gepa/adapters/default_adapter/default_adapter.py` at implementation time. If `make_reflective_dataset()` is required, follow DefaultAdapter's pattern using the trajectory data from `evaluate()`.

2. **GEPAResult evolution history**
   - What we know: `result.best_candidate` is the optimized dict. `run_dir` captures iteration files.
   - What's unclear: Whether `GEPAResult` has a per-iteration history attribute for the optimization report summary (D-16).
   - Recommendation: At implementation time, check `GEPAResult` fields via `dir(result)`. Fall back to reading `run_dir/*.json` files for evolution history.

3. **Phoenix tracing during GEPA optimization (D-06)**
   - What we know: Each evaluator call invokes `run_pipeline()`, which uses `using_attributes()` for Phoenix trace tagging.
   - What's unclear: Whether `init_tracing()` should be called once in optimize.py or deferred. Phoenix's `launch_app()` is idempotent, but multiple `register()` calls may stack tracer providers.
   - Recommendation: Call `init_tracing()` once at the top of optimize.py. Tag each evaluator call with `prompt_version=f"gepa_opt_{iteration_counter}"` via a counter in the adapter class state.

4. **EvaluationResult import path**
   - What we know: The evaluator returns `EvaluationResult` with `score` and `feedback` fields.
   - What's unclear: Exact import path — likely `from gepa.adapters.default_adapter import EvaluationResult` or `from gepa.adapters.default_adapter.default_adapter import EvaluationResult`.
   - Recommendation: At implementation time, `import gepa; print(dir(gepa))` and trace imports from the DefaultAdapter source.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python | Runtime | Yes | 3.13.2 | — |
| uv | Package management | Yes | 0.6.5 | — |
| ANTHROPIC_API_KEY | Task LLM + Reflection LLM | Yes | set in .env | — |
| gepa[full] | OPT-01 | No | 0.1.1 (available on PyPI) | Must install: `uv add "gepa[full]"` |
| litellm | DefaultAdapter HTTP calls | No | >=1.64.0 (via gepa[full]) | Pulled in by gepa[full] |
| data/ground_truth.json | Evaluator ground truth | Yes | 30 recordings | — |
| data/transcripts/call_*.json | Evaluator transcript cache | Yes | 30 files | — |
| src/phonebot/prompts/ | Prompt JSON storage | Yes (empty) | — | — |
| outputs/ | Report output dir | Yes | — | Created by script |

**Missing dependencies with no fallback:**
- `gepa[full]` — must be installed before optimize.py runs. Add to pyproject.toml Wave 0.

**Missing dependencies with fallback:**
- None.

---

## Validation Architecture

`workflow.nyquist_validation` key absent from `.planning/config.json` — treated as enabled.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 0.25.0 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_prompts.py tests/test_optimize.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OPT-02 | `build_caller_info_model()` returns class with correct `__doc__` and field descriptions | unit | `uv run pytest tests/test_prompts.py::test_build_caller_info_model -x` | Wave 0 |
| OPT-02 | `build_caller_info_model()` JSON schema contains system_prompt in `description` | unit | `uv run pytest tests/test_prompts.py::test_caller_info_json_schema -x` | Wave 0 |
| OPT-02 | `extraction_v1.json` exists and pipeline loads it at startup (smoke) | smoke | `uv run pytest tests/test_prompts.py::test_v1_prompt_file_exists -x` | Wave 0 |
| OPT-02 | `extract_node` uses dynamic CallerInfo class when `_CALLER_INFO_MODEL` is set | unit | `uv run pytest tests/test_extract.py::test_extract_node_uses_dynamic_model -x` | Wave 0 |
| OPT-01 | `optimize.py` exits cleanly on 2-iteration smoke run (mock GEPA) | integration | manual/marked skip unless ANTHROPIC_API_KEY | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_prompts.py tests/test_extract.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_prompts.py` — covers OPT-02: `build_caller_info_model`, JSON schema, v1 file
- [ ] `tests/test_extract.py::test_extract_node_uses_dynamic_model` — add to existing file
- [ ] `tests/test_optimize.py` — smoke test for optimize.py plumbing (can mock gepa.optimize)

*(Existing `tests/test_extract.py` exists — add the dynamic model test there. Other test files are new.)*

---

## Project Constraints (from CLAUDE.md)

No CLAUDE.md found in the working directory. No project-level constraints to enumerate.

---

## Sources

### Primary (HIGH confidence)
- GEPA GitHub source `src/gepa/api.py` — complete `optimize()` function signature with all parameters, DefaultAdapter instantiation logic
- GEPA GitHub source `src/gepa/adapters/default_adapter/default_adapter.py` — DefaultDataInst TypedDict, DefaultAdapter.__init__, evaluate() system_content construction, EvaluationBatch structure, make_reflective_dataset() pattern
- GEPA GitHub source `src/gepa/core/adapter.py` — GEPAAdapter Protocol, EvaluationBatch fields
- GEPA pyproject.toml — confirmed `dependencies = []` (no base deps), litellm in `[full]` extra only
- PyPI `gepa` 0.1.1 — version, release date 2026-03-16, Python compatibility
- LiteLLM model_prices_and_context_window.json — confirmed `claude-sonnet-4-6` and `claude-opus-4-6` are valid model names
- Pydantic in-venv test — verified `create_model()` with `__doc__` injection produces correct JSON schema description field

### Secondary (MEDIUM confidence)
- GEPA README.md — `gepa.optimize()` quick start pattern, DefaultAdapter single-slot example
- GEPA examples/aime_math/main.py — dataset format, evaluator structure, result.best_candidate usage
- GEPA pypi.org page — version 0.1.1 publication date, install command

### Tertiary (LOW confidence)
- GEPA documentation site (gepa-ai.github.io) — API overview only, no detailed reference found
- GEPAResult evolution history structure — not verified from source (Open Question 2)
- EvaluationResult exact import path — not verified from source (Open Question 4)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — GEPA version and install command verified from PyPI + source; Pydantic create_model verified in-venv
- Architecture patterns: MEDIUM — DefaultAdapter single-slot behavior verified from source; multi-slot custom adapter approach inferred from Protocol analysis
- Pitfalls: MEDIUM — Pitfalls 1-3 verified from source analysis; Pitfalls 4-7 from known patterns + data inspection
- Test map: HIGH — test framework confirmed from pyproject.toml; test behaviors derived from locked decisions

**Research date:** 2026-03-27
**Valid until:** 2026-04-26 (GEPA is fast-moving; re-verify if install fails or API errors appear)
