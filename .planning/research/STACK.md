# Stack Research

**Domain:** Audio entity extraction pipeline (German STT + LLM structured output)
**Researched:** 2026-03-26
**Confidence:** HIGH (all versions verified via PyPI and official docs)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| deepgram-sdk | 6.0.1 | German speech-to-text transcription of WAV files | Nova-3 has dedicated German support (added Sep 2025); smart_format applies available formatters including numerals/punctuation; simple synchronous file API |
| langgraph | 1.1.3 | Pipeline orchestration as a typed state graph | Stateful graph model maps directly to the pipeline stages (transcribe → extract → validate); nodes are pure functions; native Phoenix tracing support via LangChain instrumentor |
| pydantic | 2.12.5 | Structured output schema and runtime validation | LangGraph nodes use Pydantic state; `with_structured_output()` on any LangChain chat model accepts a Pydantic model and returns a validated instance |
| langchain-anthropic | 1.4.0 | Claude Sonnet 4.6 as the extraction LLM | Primary model for the challenge; `with_structured_output()` maps directly to Anthropic's tool-use structured output |
| langchain-openai | 1.1.10 | OpenAI models for A/B comparison | Secondary model track; identical `with_structured_output()` interface as langchain-anthropic, so model swapping is a one-line change |
| gepa | 0.1.1 | Automated prompt optimization against ground truth | Reflective evolutionary optimizer; evaluator function maps directly to per-entity accuracy against ground_truth.json; works with any LLM provider via API |
| arize-phoenix | 13.19.0 | Observability, tracing, A/B experiment dashboard | OpenTelemetry-native; one `register(auto_instrument=True)` call traces all LangGraph nodes, LLM calls, and spans; self-hosted, no cloud dependency |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| arize-phoenix-otel | 0.15.0 | Lightweight Phoenix OTEL tracer setup | Always — provides the `register()` call that bootstraps tracing before graph execution |
| openinference-instrumentation-langchain | 0.1.61 | Automatic span creation for LangGraph nodes | Always — `auto_instrument=True` picks this up; captures node transitions, LLM inputs/outputs, and graph metadata (langgraph_node, langgraph_step) |
| python-dotenv | >=1.0.0 | Load DEEPGRAM_API_KEY, ANTHROPIC_API_KEY from .env | During development; use environment variables directly in CI/CD |
| pytest | >=8.0 | Run the evaluation harness against ground truth | All evaluation code; pytest fixtures make it easy to parametrize over all 30 recordings |
| pytest-asyncio | >=0.23 | Async test support | If any pipeline nodes are async (Deepgram SDK supports async mode) |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Dependency management and virtual environment | Faster than pip/poetry; `uv sync` installs from uv.lock; standard pyproject.toml format (PEP 621) |
| Python 3.11 | Runtime | All packages in this stack support 3.10–3.13; 3.11 is the safest intersection; arize-phoenix caps at <3.14, gepa caps at <3.15 |

## Installation

```bash
# Core pipeline
uv add deepgram-sdk langgraph pydantic langchain-anthropic langchain-openai

# Observability
uv add arize-phoenix arize-phoenix-otel openinference-instrumentation-langchain

# Prompt optimization
uv add gepa

# Dev / evaluation
uv add --dev pytest pytest-asyncio python-dotenv
```

Or with pip:

```bash
pip install deepgram-sdk==6.0.1 langgraph==1.1.3 pydantic==2.12.5 \
    langchain-anthropic==1.4.0 langchain-openai==1.1.10 gepa==0.1.1 \
    arize-phoenix==13.19.0 arize-phoenix-otel==0.15.0 \
    openinference-instrumentation-langchain==0.1.61
```

## Integration Points

This is the load-bearing section — how the components wire together.

### 1. Deepgram → LangGraph State

Deepgram produces a raw transcript string. The LangGraph pipeline starts by calling Deepgram in the first node and writing the result into the typed state:

```python
from deepgram import DeepgramClient, PrerecordedOptions

client = DeepgramClient()  # reads DEEPGRAM_API_KEY from env

with open("call_01.wav", "rb") as f:
    response = client.listen.v1.media.transcribe_file(
        {"buffer": f.read(), "mimetype": "audio/wav"},
        PrerecordedOptions(model="nova-3", language="de", smart_format=True),
    )

transcript = response.results.channels[0].alternatives[0].transcript
```

The `PrerecordedOptions` dataclass (not keyword args) is the correct SDK v6 pattern. `language="de"` selects Nova-3 German. `smart_format=True` applies available German formatters (numerals, punctuation — phone/email formatting is English-only per Deepgram docs; extraction handles those downstream via LLM).

### 2. Pydantic Model as Both Schema and Prompt

The extraction schema doubles as the prompt. Docstring becomes the system context; field `description` args become the per-field extraction instruction:

```python
from pydantic import BaseModel, Field

class CallerInfo(BaseModel):
    """
    You are extracting caller contact information from a German phone bot transcript.
    Extract only what is explicitly stated. Use null for any field not mentioned.
    """

    first_name: str | None = Field(
        None,
        description="Caller's first name as spoken, in original German form.",
    )
    last_name: str | None = Field(
        None,
        description="Caller's last name as spoken.",
    )
    email: str | None = Field(
        None,
        description="Email address, spelled out letter by letter in German. Reconstruct the full address.",
    )
    phone_number: str | None = Field(
        None,
        description="Phone number as spoken, digits only.",
    )
```

### 3. LangGraph Node → LLM → Pydantic Output

```python
from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, START, END

llm = ChatAnthropic(model="claude-sonnet-4-6")
structured_llm = llm.with_structured_output(CallerInfo)

def extract_node(state: PipelineState) -> dict:
    result = structured_llm.invoke(state["transcript"])
    return {"caller_info": result}
```

`with_structured_output(CallerInfo)` passes the Pydantic schema to Anthropic's tool-use mechanism and returns a validated `CallerInfo` instance. Swap `ChatAnthropic` for `ChatOpenAI` for A/B model comparison — the node code is identical.

### 4. Arize Phoenix Tracing

Phoenix must be initialized before graph compilation. The `auto_instrument=True` flag discovers and activates the installed `openinference-instrumentation-langchain`, which covers all LangGraph nodes automatically:

```python
from phoenix.otel import register

tracer_provider = register(
    project_name="phonebot-extraction",
    auto_instrument=True,
)

# Build and run graph after registration
graph = build_pipeline().compile()
```

Phoenix runs a local server at `http://localhost:6006`. All LLM calls, node transitions, and LangGraph metadata (node name, step index) appear as spans in the UI. A/B comparison between models is done by tagging runs with different `project_name` values and comparing trace metrics in the dashboard.

### 5. GEPA Prompt Optimization

GEPA optimizes the docstring + field descriptions in `CallerInfo` against the ground truth. The evaluator function must return a scalar score and optional trace for reflection:

```python
import gepa

def evaluate_prompt(candidate_prompt: str) -> float:
    # Rebuild CallerInfo with candidate_prompt as docstring
    # Run all 30 recordings through the pipeline
    # Return per-entity F1 or exact-match accuracy against ground_truth.json
    ...

result = gepa.optimize(
    seed_candidate=CallerInfo.__doc__,
    evaluator=evaluate_prompt,
    task_lm="claude-sonnet-4-6",
    reflection_lm="claude-sonnet-4-6",
    budget=50,  # number of evaluations
)
```

GEPA reads full execution traces (not just scalar scores) to diagnose which fields fail and why, then proposes targeted prompt mutations.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| deepgram-sdk 6.x | openai-whisper | When no internet access is required; Whisper runs fully local but is slower and lacks smart_format |
| langgraph 1.x | raw Python functions | For a single-shot script without retries, branching, or observability hooks; LangGraph adds overhead only worth it for multi-step pipelines |
| langchain-anthropic | anthropic (raw SDK) | When you don't need LangGraph or Phoenix integration; raw SDK has less abstraction overhead |
| arize-phoenix | langsmith | When you're already in the LangChain cloud ecosystem; Phoenix is self-hosted and free for local use |
| gepa | dspy.BootstrapFewShot | When you have abundant labeled examples and want few-shot prompting rather than system-prompt mutation |
| uv | pip + venv | When the deployment target requires vanilla pip; uv is a drop-in for pip install commands |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| langchain (core meta-package) | In 2026, `langchain` splits into partner packages; importing from the monolith pulls stale code and creates version conflicts | Use `langchain-anthropic`, `langchain-openai` directly |
| deepgram-sdk 3.x or 4.x | The v6 SDK (released Feb 2026) has a breaking API change; `PrerecordedOptions` replaces keyword arg passing | `deepgram-sdk>=6.0.0` |
| openai (direct SDK) for primary extraction | Adds a second LLM dependency without the `with_structured_output` interface parity; increases surface area | `langchain-openai` which wraps the openai SDK correctly |
| pydantic v1 | LangGraph 1.x and all LangChain 1.x partner packages require Pydantic v2; mixing v1 and v2 causes import errors | `pydantic>=2.0` |
| streaming transcription | The challenge uses pre-recorded files; streaming adds async complexity with no benefit | Synchronous `transcribe_file()` |

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| langgraph==1.1.3 | Python >=3.10 | Hard lower bound — do not use 3.9 |
| arize-phoenix==13.19.0 | Python <3.14, >=3.10 | Python 3.11 is the safe intersection with all other packages |
| gepa==0.1.1 | Python <3.15, >=3.10 | Matches langgraph and phoenix range |
| deepgram-sdk==6.0.1 | Python >=3.8 | Most permissive; no conflict |
| pydantic==2.12.5 | Python >=3.9 | Works across entire range |
| langchain-anthropic==1.4.0 | Python <4.0, >=3.10 | Matches langgraph lower bound |
| openinference-instrumentation-langchain==0.1.61 | langchain>=1.0.0 OR langchain-classic>=1.0.0 | Uses langchain-core as shared base |

**Safe Python version: 3.11** — satisfies all lower bounds, stays below all upper bounds.

## Stack Patterns by Variant

**If running open-source models (Llama, Mistral) for A/B:**
- Use `langchain-ollama` or `langchain-huggingface` as the chat model
- `with_structured_output()` interface is the same; swap the model object only
- GEPA still works — it calls the same evaluator regardless of which LLM executes the prompt

**If smart_format misses phone/email formatting for German:**
- Do not rely on Deepgram to format these fields; the LLM extraction handles raw digit sequences
- Add post-processing normalization in a dedicated LangGraph node after extraction
- Field descriptions in the Pydantic model should instruct the LLM to handle German number pronunciation ("null" = 0, "eins" = 1, etc.)

**If Phoenix dashboard is not needed (CI-only evaluation):**
- Skip `arize-phoenix` and `arize-phoenix-otel`
- Keep `openinference-instrumentation-langchain` for structured span output to stdout/log file
- Evaluation harness can run headlessly with `phoenix.otel.register(endpoint="...")`

## Sources

- [deepgram-sdk PyPI](https://pypi.org/project/deepgram-sdk/) — version 6.0.1 confirmed
- [Deepgram Nova-3 German announcement](https://deepgram.com/learn/deepgram-expands-nova-3-with-german-dutch-swedish-and-danish-support) — language="de", German compound word support
- [Deepgram smart_format docs](https://developers.deepgram.com/docs/smart-format) — English-broadest, German limited to punctuation/numerals (HIGH confidence)
- [langgraph PyPI](https://pypi.org/project/langgraph/) — version 1.1.3 confirmed, Python >=3.10
- [pydantic PyPI](https://pypi.org/project/pydantic/) — version 2.12.5 confirmed
- [langchain-anthropic PyPI](https://pypi.org/project/langchain-anthropic/) — version 1.4.0 confirmed
- [arize-phoenix PyPI](https://pypi.org/project/arize-phoenix/) — version 13.19.0 confirmed, Python <3.14
- [arize-phoenix-otel PyPI](https://pypi.org/project/arize-phoenix-otel/) — version 0.15.0 confirmed
- [openinference-instrumentation-langchain PyPI](https://pypi.org/project/openinference-instrumentation-langchain/) — version 0.1.61, langchain>=1.0.0 support confirmed
- [Phoenix LangGraph tracing docs](https://arize.com/docs/phoenix/integrations/python/langgraph/langgraph-tracing) — LangChainInstrumentor covers LangGraph; auto_instrument=True pattern (HIGH confidence)
- [gepa PyPI](https://pypi.org/project/gepa/) — version 0.1.1, Python <3.15,>=3.10 confirmed
- [GEPA GitHub](https://github.com/gepa-ai/gepa) — custom evaluator pattern, task_lm/reflection_lm separation (HIGH confidence)
- [GEPA docs](https://gepa-ai.github.io/gepa/) — optimize_anything API, trace-based reflection (MEDIUM confidence — documentation may lag code)
- [langchain-openai PyPI](https://pypi.org/project/langchain-openai/) — version 1.1.10 confirmed

---
*Stack research for: German audio entity extraction pipeline*
*Researched: 2026-03-26*
