# Architecture Research

**Domain:** Audio entity extraction pipeline (STT + LLM + prompt optimization + observability)
**Researched:** 2026-03-26
**Confidence:** HIGH (all five components have official documentation; integration patterns verified)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI Entry Point                           │
│                     pipeline/run.py                              │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                   Phoenix Instrumentation Layer                   │
│         register(project_name=..., auto_instrument=True)         │
│   (wraps all LangGraph + LLM calls with OpenTelemetry spans)     │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                    LangGraph Pipeline Graph                       │
│                                                                   │
│   ┌────────────┐   ┌─────────────────┐   ┌───────────────────┐  │
│   │ transcribe │──▶│ extract_entities│──▶│  validate_output  │  │
│   │   _node    │   │     _node       │   │      _node        │  │
│   └────────────┘   └─────────────────┘   └───────────────────┘  │
│        │                   │                       │             │
│   Deepgram Nova-3      LLM (swappable)        Pydantic          │
│   Python SDK           via LangChain          validation         │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                    Pipeline State (TypedDict)                     │
│   audio_path | transcript | raw_extraction | extraction | error  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                      Evaluation Harness                           │
│   ┌─────────────────────────┐   ┌────────────────────────────┐  │
│   │  ground_truth.json diff │   │  Phoenix experiments API   │  │
│   │  per-field accuracy     │   │  A/B model comparison      │  │
│   └─────────────────────────┘   └────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                   GEPA Prompt Optimization                        │
│  optimize_anything(seed_prompt, evaluator=accuracy_fn)           │
│  (offline, train-then-deploy — runs BEFORE production graph)     │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Implementation |
|-----------|----------------|----------------|
| Deepgram Nova-3 | WAV → transcript string with smart_format | `deepgram-sdk`, `ListenRESTOptions(model="nova-3", language="de", smart_format=True)` |
| LangGraph graph | Pipeline orchestration, shared state, node routing | `StateGraph(PipelineState)`, sequential nodes START → transcribe → extract → validate → END |
| Pydantic BaseModel | Schema for extracted output + prompt construction | `CallerInfo(BaseModel)` with docstring as system prompt, `Field(description=...)` as per-field instructions |
| LLM layer | Entity extraction from transcript | LangChain `.with_structured_output(CallerInfo)` — swappable via config |
| Arize Phoenix | Tracing every node/LLM call, A/B experiment datasets | `openinference-instrumentation-langchain`, `register(auto_instrument=True)` |
| GEPA | Offline prompt optimizer against ground truth | `optimize_anything(seed_prompt, evaluator)` — runs before deploying prompt to graph |
| Evaluation harness | Per-field accuracy against `ground_truth.json` | Python script, feeds into Phoenix experiments and GEPA evaluator |

## Recommended Project Structure

```
phonebot_challenge/
├── pipeline/
│   ├── __init__.py
│   ├── run.py               # CLI entry point: iterate over 30 WAVs, collect results
│   ├── graph.py             # LangGraph StateGraph definition and compilation
│   ├── state.py             # PipelineState TypedDict
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── transcribe.py    # Deepgram Nova-3 transcription node
│   │   ├── extract.py       # LLM extraction node using CallerInfo model
│   │   └── validate.py      # Pydantic validation / retry node
│   └── models/
│       ├── __init__.py
│       └── caller_info.py   # CallerInfo Pydantic BaseModel (docstring + Field descriptions)
├── prompts/
│   └── extraction_v1.txt    # Seed prompt for GEPA (system prompt text, externalized)
├── evaluation/
│   ├── __init__.py
│   ├── metrics.py           # Per-field accuracy: exact match + fuzzy match for names
│   ├── compare.py           # Load ground_truth.json, diff against pipeline output
│   └── phoenix_experiments.py  # Upload datasets, run A/B experiment via Phoenix API
├── optimization/
│   ├── __init__.py
│   └── optimize_prompt.py   # GEPA optimize_anything() call, writes best prompt to prompts/
├── observability/
│   ├── __init__.py
│   └── setup.py             # Phoenix register() call — import once in run.py
├── data/
│   ├── recordings/          # call_01.wav ... call_30.wav (provided)
│   └── ground_truth.json    # expected extractions (provided)
├── outputs/
│   └── results.json         # pipeline output for all 30 calls
└── tests/
    ├── test_transcription.py
    ├── test_extraction.py
    └── test_evaluation.py
```

### Structure Rationale

- **pipeline/nodes/:** Each LangGraph node is isolated — swap transcription or extraction without touching the graph definition.
- **pipeline/models/:** `CallerInfo` lives alone — it is the contract between the LLM and the evaluation harness. GEPA targets the text wrapped around this schema, not the schema itself.
- **prompts/:** Externalizing prompt text from Python code lets GEPA write improved candidates back to disk without code changes. The extraction node reads from this file at runtime.
- **evaluation/:** Decoupled from the pipeline so it can run standalone (ground truth diff) or feed into Phoenix experiments and GEPA scoring.
- **optimization/:** GEPA runs offline (train-then-deploy), not during pipeline execution. Separating it makes this boundary explicit.
- **observability/:** Single `setup.py` called once in `run.py` before compiling the graph. Phoenix `auto_instrument=True` then captures all downstream activity automatically.

## Architectural Patterns

### Pattern 1: Train-Then-Deploy for Prompt Optimization

**What:** GEPA optimizes the extraction system prompt offline using `ground_truth.json` as training data. The optimized prompt is written to `prompts/extraction_v1.txt`. The LangGraph extraction node reads this file at startup — not at optimization time.

**When to use:** Any time prompt quality is the primary accuracy lever, which it is here. The 30 WAVs are a fixed evaluation set, so optimizing against a subset as training and holding out the rest for validation is straightforward.

**Trade-offs:** Optimized prompt may overfit the 30-call set. Mitigate by using 20 calls as training, 10 as held-out validation in GEPA's `valset`.

**Pattern sketch:**
```python
# optimization/optimize_prompt.py
import gepa.optimize_anything as oa
from evaluation.metrics import field_accuracy

def evaluator(candidate_prompt: str) -> tuple[float, dict]:
    # Run extraction pipeline with candidate_prompt on training subset
    results = run_pipeline_with_prompt(candidate_prompt, train_calls)
    score = field_accuracy(results, ground_truth_subset)
    failures = [r for r in results if not r["all_correct"]]
    return score, {"Failed_cases": str(failures[:3])}

result = oa.optimize_anything(
    seed_candidate=open("prompts/extraction_v1.txt").read(),
    evaluator=evaluator,
)
open("prompts/extraction_v1.txt", "w").write(result.best_candidate)
```

### Pattern 2: Pydantic-as-Prompt (Docstring + Field Descriptions)

**What:** `CallerInfo`'s class docstring becomes the system prompt. Each `Field(description=...)` becomes the per-field extraction instruction. LangChain's `.with_structured_output(CallerInfo)` serializes this to the LLM's structured output schema automatically.

**When to use:** Always for this project. The model generates JSON that maps directly to `CallerInfo` fields — no parsing step needed, and Pydantic validates types immediately.

**Trade-offs:** The system prompt and field descriptions are embedded in Python, which makes GEPA optimization harder. Resolution: externalize the system prompt text to `prompts/extraction_v1.txt`; keep field descriptions in the Pydantic model as ground truth for schema semantics. GEPA targets the system prompt only.

**Pattern sketch:**
```python
# pipeline/models/caller_info.py
from pydantic import BaseModel, Field
from typing import Optional

class CallerInfo(BaseModel):
    """Extract the caller's contact information from this German phone call transcript.
    Return only information explicitly stated by the caller. Use null for any field
    not mentioned. German names and email addresses are common — preserve original spelling."""

    first_name: Optional[str] = Field(
        None,
        description="Caller's first name as stated. Accept compound names like 'Lisa Marie'."
    )
    last_name: Optional[str] = Field(
        None,
        description="Caller's family name. Preserve German umlauts (ä, ö, ü)."
    )
    email: Optional[str] = Field(
        None,
        description="Email address. smart_format will have normalized it — return as-is."
    )
    phone_number: Optional[str] = Field(
        None,
        description="Phone number as spoken. Include country code if stated."
    )
```

### Pattern 3: Phoenix Instrumentation at Graph Boundary

**What:** Call `phoenix.otel.register(auto_instrument=True)` once before compiling or running the LangGraph graph. The `openinference-instrumentation-langchain` instrumentor intercepts all LangChain/LangGraph activity and emits OpenTelemetry spans to the Phoenix server automatically. No per-node instrumentation code needed.

**When to use:** Always. The single registration call captures the full execution trace — transcription node timings, LLM calls with token counts, validation outcomes — without any manual span management.

**Trade-offs:** `auto_instrument=True` captures everything, which can produce noisy traces. For A/B experiments, use Phoenix's Datasets & Experiments API explicitly to tag runs by model variant.

**Pattern sketch:**
```python
# observability/setup.py
from phoenix.otel import register

def init_phoenix(project_name: str = "phonebot-extraction"):
    register(project_name=project_name, auto_instrument=True)
```

### Pattern 4: Multi-Model A/B via LangChain Swappable LLM

**What:** The extraction node receives the LLM instance from configuration, not from a hardcoded import. `run.py` constructs the LLM (e.g., `ChatAnthropic`, `ChatOpenAI`, a local Ollama model) and passes it into the graph at compile time.

**When to use:** Whenever comparing model quality against ground truth. Phoenix traces each run with a project or experiment tag identifying the model variant. The evaluation harness then computes per-field accuracy per variant.

**Trade-offs:** Running all 30 calls per model multiplies API costs. For the challenge this is fine (30 calls * N models). At scale, use Phoenix's "replay traces through new model" feature instead of re-running.

**Pattern sketch:**
```python
# pipeline/graph.py
def build_graph(llm) -> CompiledGraph:
    graph = StateGraph(PipelineState)
    graph.add_node("transcribe", transcribe_node)
    graph.add_node("extract", make_extract_node(llm))  # llm injected here
    graph.add_node("validate", validate_node)
    graph.add_edge(START, "transcribe")
    graph.add_edge("transcribe", "extract")
    graph.add_edge("extract", "validate")
    graph.add_edge("validate", END)
    return graph.compile()
```

## Data Flow

### WAV to JSON Output

```
data/recordings/call_01.wav
    │
    ▼ transcribe_node
    │  deepgram.listen.v1.media.transcribe_file(
    │      audio_bytes, model="nova-3", language="de", smart_format=True
    │  )
    │  → response.results.channels[0].alternatives[0].transcript
    │
    ▼  PipelineState.transcript = "Mein Name ist Hans Müller..."
    │
    ▼ extract_node
    │  llm.with_structured_output(CallerInfo).invoke(
    │      [SystemMessage(prompt_text), HumanMessage(transcript)]
    │  )
    │
    ▼  PipelineState.extraction = CallerInfo(
    │      first_name="Hans", last_name="Müller",
    │      email="hans@example.de", phone_number="+49 30 12345678"
    │  )
    │
    ▼ validate_node
    │  Pydantic validation already done by .with_structured_output()
    │  Additional: check for None fields that seemed present in transcript
    │
    ▼  outputs/results.json ← {call_id: extraction.model_dump()}
    │
    ▼ evaluation/compare.py
       diff results.json vs data/ground_truth.json
       → per-field accuracy, per-call accuracy, overall score
```

### GEPA Optimization Flow (offline, runs before pipeline)

```
data/ground_truth.json (20 training calls)
    │
    ▼ optimization/optimize_prompt.py
    │  for each GEPA iteration:
    │    candidate_prompt → run_pipeline_with_prompt(calls_subset)
    │    → field_accuracy(results, ground_truth) → float score
    │    → failure diagnostics → GEPA reflection LLM reads failures
    │    → GEPA proposes improved prompt candidate
    │
    ▼ prompts/extraction_v1.txt ← result.best_candidate
    │
    ▼ pipeline production run reads from prompts/extraction_v1.txt
```

### Phoenix Observability Flow

```
run.py: init_phoenix()  ← single call instruments everything below

graph.invoke(state)
    │  [span: LangGraph node "transcribe"]
    │  [span: LangGraph node "extract"]
    │      [child span: LLM call — model, tokens, latency, prompt, response]
    │  [span: LangGraph node "validate"]
    │
    ▼ Phoenix server (local or cloud)
       → Trace viewer: full execution timeline
       → Experiments: upload results.json as dataset
         → re-run with different LLM → compare accuracy metrics
         → tag by model variant for A/B dashboard
```

### Key Data Flows

1. **Transcript normalization:** Deepgram `smart_format=True` normalizes phone numbers (e.g., "null vier null" → "+49 40...") and emails before the transcript reaches the LLM. This reduces hallucination surface area — the LLM only needs to locate and copy, not reformat.

2. **State threading:** LangGraph `TypedDict` state carries `audio_path`, `transcript`, `extraction`, and `error` fields. Each node reads the state it needs and returns only the fields it updates. Nodes never call each other directly — all communication is through state.

3. **Multi-value field handling:** The ground truth allows multiple valid values for some fields (e.g., "Lisa Marie" or "Lisa-Marie"). The evaluation `metrics.py` must implement fuzzy matching at the field level, not just exact string equality.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 30 files (current) | Sequential loop in run.py, single process. No parallelism needed. |
| 300 files | Add `asyncio` + async Deepgram client. LangGraph supports async nodes natively. |
| 3,000+ files | Batch Deepgram API calls (file queuing), parallel LangGraph invocations with bounded concurrency. |

### Scaling Priorities

1. **First bottleneck:** Deepgram API latency per file. Each WAV is a synchronous HTTP call. At 30 files this is fine; beyond 100, switch to async `deepgram.listen.asyncrest`.
2. **Second bottleneck:** LLM cost per extraction. At 30 calls this is negligible. GEPA optimization runs consume more tokens than production (it iterates many candidates) — budget for it.

## Anti-Patterns

### Anti-Pattern 1: Running GEPA Inside the LangGraph Graph at Runtime

**What people do:** Wire GEPA as a LangGraph node that optimizes the prompt on every pipeline run, or on the first run, then caches.

**Why it's wrong:** GEPA needs a scoring function over many examples. A single call provides no optimization signal. Running it at runtime makes the pipeline slow, unpredictable, and conflates optimization with inference.

**Do this instead:** Run GEPA offline via `optimization/optimize_prompt.py` before the pipeline. Write the optimized prompt to disk. The pipeline reads a static file — fast and deterministic.

### Anti-Pattern 2: Hardcoding the LLM in the Extraction Node

**What people do:** `from langchain_anthropic import ChatAnthropic; llm = ChatAnthropic(...)` inside the extraction node function.

**Why it's wrong:** Blocks A/B testing between models. Every model swap requires a code change. Cannot run multiple models in the same script for comparison.

**Do this instead:** Inject `llm` as a parameter into the node factory function (`make_extract_node(llm)`). Build graphs for each model variant in `run.py` and compare via Phoenix experiments.

### Anti-Pattern 3: Embedding System Prompt Text Inside the Pydantic Model

**What people do:** Put all extraction instructions directly in the `CallerInfo` docstring and `Field(description=...)` strings.

**Why it's wrong:** GEPA cannot target these strings without Python AST manipulation. Prompt iteration requires code edits, re-imports, and test reruns.

**Do this instead:** Keep the Pydantic model for schema semantics (field names, types, short descriptions). Put the main extraction system prompt in `prompts/extraction_v1.txt`. The extraction node reads this file and passes it as the `SystemMessage`. GEPA targets the file.

### Anti-Pattern 4: Using Phoenix as the Only Accuracy Metric

**What people do:** Rely solely on Phoenix's built-in LLM-as-judge evaluators for measuring extraction quality.

**Why it's wrong:** LLM-as-judge is non-deterministic and expensive. For entity extraction against known ground truth, exact/fuzzy string matching is faster, cheaper, and more reliable.

**Do this instead:** Compute ground-truth accuracy in `evaluation/metrics.py` using deterministic code. Upload those scores to Phoenix as custom experiment metadata so they appear in dashboards alongside traces. Use LLM-as-judge only for edge cases (e.g., "is this an acceptable name variant?").

### Anti-Pattern 5: One Graph Invocation for All 30 Files

**What people do:** Design a LangGraph graph with a "batch processing" node that loops over all WAV files internally.

**Why it's wrong:** Phoenix traces one "session" rather than 30 independent traces. Error isolation fails — one bad file corrupts graph state. Cannot replay a single call.

**Do this instead:** Invoke `graph.invoke(state)` once per file in a Python loop in `run.py`. Each invocation produces one trace in Phoenix, independently replayable and inspectable.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Deepgram Nova-3 | `deepgram-sdk` pre-recorded REST API, synchronous | Requires `DEEPGRAM_API_KEY` env var. Use `language="de"` explicitly — do not rely on auto-detect for German. |
| Arize Phoenix | `openinference-instrumentation-langchain` + `phoenix.otel.register()` | Can run Phoenix server locally (`phoenix serve`) or use Arize cloud. Local is sufficient for 30-file challenge. |
| Anthropic / OpenAI / Ollama | LangChain chat model wrappers | `ChatAnthropic`, `ChatOpenAI`, `ChatOllama`. All support `.with_structured_output(CallerInfo)`. Swap via config, not code. |
| GEPA | `gepa` Python package (`optimize_anything` API) | Does not require DSPy. Standalone usage: provide `evaluator` function returning `(float, dict)`. Reads/writes plain text prompt files. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| run.py ↔ graph.py | Python function call: `build_graph(llm).invoke(initial_state)` | LLM instance constructed in `run.py`, injected into graph factory. |
| transcribe_node ↔ extract_node | LangGraph state: `state["transcript"]` | Nodes never call each other. State is the only interface. |
| extraction node ↔ CallerInfo model | `.with_structured_output(CallerInfo)` | LangChain handles JSON schema generation and response parsing. |
| pipeline ↔ GEPA | File system: `prompts/extraction_v1.txt` | GEPA writes best prompt; pipeline reads it at startup. Clean decoupling. |
| pipeline ↔ Phoenix | OpenTelemetry auto-instrumentation | No explicit span creation needed in node code. Phoenix captures automatically via `auto_instrument=True`. |
| evaluation ↔ Phoenix | Phoenix Python client: upload dataset, create experiment | `px.Client().upload_dataset(df)` + `run_experiment()` for A/B model comparison. |
| GEPA evaluator ↔ evaluation/metrics.py | Direct Python import | `from evaluation.metrics import field_accuracy`. GEPA evaluator reuses the same accuracy function as the main evaluation harness. |

## Build Order

Build order is determined by dependencies: each phase produces artifacts the next phase requires.

### Phase 1: Foundation (no external dependencies)
1. Define `PipelineState` TypedDict (`state.py`)
2. Define `CallerInfo` Pydantic model (`models/caller_info.py`)
3. Write `evaluation/metrics.py` with per-field accuracy (deterministic, testable against ground truth immediately)
4. Write `evaluation/compare.py` reading `ground_truth.json`

**Deliverable:** Run `compare.py` against an empty `results.json` — 0% accuracy. Baseline established.

### Phase 2: Transcription
5. Implement `transcribe_node` using Deepgram SDK
6. Run all 30 WAVs through transcription only, save transcripts to disk
7. Manually inspect 3-5 transcripts for German accuracy and smart_format behavior on phones/emails

**Deliverable:** 30 transcript strings. Spot-check quality. No LLM yet.

### Phase 3: Extraction Pipeline
8. Write `CallerInfo` extraction node with a single hardcoded LLM (start with GPT-4o-mini or Claude Haiku for speed)
9. Wire `graph.py` with START → transcribe → extract → END
10. Run `run.py` over all 30 files, write `outputs/results.json`
11. Run `evaluation/compare.py` — get baseline accuracy score

**Deliverable:** First end-to-end accuracy number. Identifies hard cases (multi-value names, tricky phone formats).

### Phase 4: Observability
12. Add `observability/setup.py` with Phoenix `register()`
13. Add `init_phoenix()` call to `run.py` before graph compilation
14. Re-run pipeline, verify traces appear in Phoenix UI
15. Identify slow nodes, high-token calls, or failed extractions from trace data

**Deliverable:** Full traceability. Phoenix project "phonebot-extraction" populated with 30 traces.

### Phase 5: Multi-Model A/B
16. Refactor extraction node to accept injected LLM (`make_extract_node(llm)`)
17. Add model configuration to `run.py` (read from env or CLI arg)
18. Run pipeline with 2-3 model variants (e.g., Claude Haiku, Claude Sonnet 4.6, GPT-4o-mini)
19. Upload results as Phoenix experiments, compare accuracy per model

**Deliverable:** Model comparison table. Identifies best baseline model for GEPA optimization.

### Phase 6: Prompt Optimization
20. Externalize system prompt to `prompts/extraction_v1.txt`
21. Implement `optimization/optimize_prompt.py` with GEPA `optimize_anything()`
22. GEPA evaluator calls pipeline on 20-call training subset, scores with `field_accuracy()`
23. GEPA writes optimized prompt to `prompts/extraction_v1.txt`
24. Re-run full pipeline with optimized prompt, compare accuracy to Phase 3 baseline

**Deliverable:** Accuracy delta from GEPA optimization. Demonstrates prompt optimization value.

### Phase 7: Validation and Hardening
25. Add `validate_node` for edge cases (missing fields, format anomalies)
26. Write tests for transcription, extraction, and evaluation
27. Run full eval: Phoenix experiments across all model variants + optimized prompt
28. Write final `outputs/results.json` for submission

**Deliverable:** Final results file + Phoenix dashboard screenshot for challenge submission.

## Sources

- [Arize Phoenix LangGraph Tracing](https://arize.com/docs/phoenix/integrations/python/langgraph/langgraph-tracing) — official integration docs, verified
- [GEPA gepa-ai/gepa GitHub](https://github.com/gepa-ai/gepa) — `optimize_anything` API reference
- [GEPA optimize_anything blog post](https://gepa-ai.github.io/gepa/blog/2026/02/18/introducing-optimize-anything/) — evaluator function pattern
- [LangGraph sequential workflows](https://medium.com/@ameejais0999/sequential-workflows-in-langgraph-a-practical-approach-a6e66ff2a980) — state TypedDict pipeline pattern
- [LangGraph State with Pydantic BaseModel](https://medium.com/fundamentals-of-artificial-intelligence/langgraph-state-with-pydantic-basemodel-023a2158ab00) — structured output in nodes
- [Deepgram pre-recorded audio Python SDK](https://developers.deepgram.com/docs/pre-recorded-audio) — transcribe_file() API and response structure
- [Deepgram Nova-3 German support](https://deepgram.com/learn/deepgram-expands-nova-3-with-german-dutch-swedish-and-danish-support) — language="de" verified
- [GEPA + LangGraph reference implementation](https://www.rajapatnaik.com/blog/2025/10/23/langgraph-dspy-gepa-researcher) — train-then-deploy pattern
- [Phoenix experiments and A/B testing](https://arize.com/docs/phoenix) — datasets, experiments, model comparison API
- [Pydantic for LLM prompting](https://pydantic.dev/articles/llm-intro) — docstring + Field(description) pattern
- [GEPA ICLR 2026 paper](https://arxiv.org/abs/2507.19457) — reflective prompt evolution algorithm

---
*Architecture research for: German audio entity extraction pipeline (Deepgram + LangGraph + Pydantic + GEPA + Arize Phoenix)*
*Researched: 2026-03-26*
