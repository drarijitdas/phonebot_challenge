# Phase 5: Model A/B Testing - Research

**Researched:** 2026-03-27
**Domain:** LangChain multi-provider model registry, ChatOllama structured output, A/B comparison reporting
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Compare Claude Sonnet 4.6 (Anthropic API) vs Llama 3.3 (Ollama local) — user chose Ollama over cloud-hosted alternatives for local control and flexibility
- **D-02:** Llama 3.3 is the default second model, but any Ollama-available model can be used at runtime via the colon-prefix convention
- **D-03:** LangChain native registry pattern — a dict mapping model prefixes/names to LangChain chat model classes (`ChatAnthropic`, `ChatOllama`). No LiteLLM dependency.
- **D-04:** Registry lives in `src/phonebot/models/model_registry.py` — alongside CallerInfo in the models package
- **D-05:** `extract_node()` calls registry's `get_model(name).with_structured_output(CallerInfo)` instead of hardcoded `ChatAnthropic`
- **D-06:** Colon-prefix naming convention: `--model claude-sonnet-4-6` (Anthropic API), `--model ollama:llama3.3` (Ollama local). Registry parses the prefix to determine provider.
- **D-07:** Ollama runs locally — no cloud API key needed for the second model. Only ANTHROPIC_API_KEY required (already in .env).
- **D-08:** Fail fast if provider prerequisites are missing (e.g., Ollama not running, API key not set). Clear error message.
- **D-09:** Separate runs + compare script — run pipeline twice (`--model claude-sonnet-4-6`, `--model ollama:llama3.3`), then a compare script reads both result files and prints comparison
- **D-10:** Model-specific result files: `outputs/results_{model_alias}.json` (e.g., `results_claude-sonnet-4-6.json`, `results_ollama_llama3.3.json`). Compare script globs `outputs/results_*.json`.
- **D-11:** Compare script (new `compare.py` or `--compare` flag) outputs Rich table to console + `outputs/comparison.json` for programmatic use — follows Phase 1 D-08 dual-output pattern
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

### Deferred Ideas (OUT OF SCOPE)
- **Other STT models** — Comparing Deepgram vs Whisper or other speech-to-text providers
- **Actor-critic approaches** — Using one model to extract and another to critique/refine
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AB-01 | Pipeline supports swappable LLM backends (at minimum Claude Sonnet 4.6 + one open-source model) | `langchain-ollama` provides `ChatOllama` with identical `with_structured_output()` interface as `ChatAnthropic`; registry dict pattern cleanly abstracts provider selection |
| AB-02 | A/B test results are visible in Phoenix with per-model accuracy comparison | Existing `using_attributes(metadata={"model": model_name})` tagging already in Phase 4 code naturally separates Claude vs Ollama traces; compare script reads per-model result files and prints Rich comparison table |
</phase_requirements>

---

## Summary

Phase 5 adds multi-provider model support by building a registry that routes model name strings to the correct LangChain chat class, then connecting a compare script that reads per-model result files and prints an accuracy/latency comparison table.

The core implementation is narrow: `extract_node()` already uses an env var for model name — it just needs to call `registry.get_model(name)` instead of hardcoding `ChatAnthropic`. The `run.py` output path needs to be parameterized by model alias. Phoenix trace tagging is already in place from Phase 4 (`using_attributes` with `metadata={"model": model_name}`), so Phoenix side-by-side visibility requires no new instrumentation.

The one significant discovery: **llama3.3:latest (43GB) cannot run on this machine's 36GB M3 Max**. The CONTEXT.md decision says "Llama 3.3 is the default second model, but any Ollama-available model can be used at runtime." The plan must include an `ollama pull` step for a fitting quantization of llama3.3 (e.g., `mannix/llama-3.3:iq3_xs` ~24-26GB community variant) OR establish `llama3.2:3b` (2GB, already pulled) as a proven fallback. Research recommends treating llama3.3 with an IQ3 community quantization as the primary attempt, with llama3.2:3b as documented fallback.

**Primary recommendation:** Use `langchain-ollama` (not `langchain-community`) for `ChatOllama`. The `with_structured_output(CallerInfo, method="json_schema")` call is identical to the existing `ChatAnthropic` usage — no schema adaptation needed.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langchain-ollama | 1.0.1 | `ChatOllama` class for local Ollama models | Dedicated Ollama package, maintained alongside langchain-anthropic; NOT langchain-community |
| langchain-anthropic | 1.4.0 (installed) | `ChatAnthropic` — already in use | No change needed |
| rich | 14.3.3 (installed) | Rich console + Table for compare output | Already established in project |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| langchain-community | 0.4.1 | Legacy `ChatOllama` (deprecated path) | Do NOT use — langchain-ollama is the current package |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| langchain-ollama ChatOllama | langchain-community ChatOllama | langchain-community's ChatOllama is the old location; langchain-ollama is the current dedicated package (D-03 excludes LiteLLM) |

**Installation:**
```bash
uv add langchain-ollama
```

**Version verification (2026-03-27):**
- `langchain-ollama`: 1.0.1 (PyPI confirmed)
- `langchain-community`: 0.4.1 (not needed)

---

## Architecture Patterns

### Recommended Project Structure
```
src/phonebot/
├── models/
│   ├── caller_info.py       # existing
│   └── model_registry.py    # NEW: provider dict + get_model()
├── pipeline/
│   └── extract.py           # MODIFY: replace ChatAnthropic with registry call
└── ...

run.py                       # MODIFY: parameterize output path to results_{alias}.json
compare.py                   # NEW: reads outputs/results_*.json, prints Rich table
```

### Pattern 1: Model Registry Dict
**What:** A dict mapping string prefixes/names to a factory function. `get_model(name)` parses the name, selects the right class, instantiates it.
**When to use:** When the set of supported providers is known and small (2-3 entries). Avoids plugin machinery overhead.

```python
# src/phonebot/models/model_registry.py
# Source: LangChain official docs (ChatOllama, ChatAnthropic)
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama

_REGISTRY: dict = {}

def get_model(name: str):
    """Return a LangChain chat model for the given name.

    Naming convention:
        "claude-*"        -> ChatAnthropic(model=name)
        "ollama:<model>"  -> ChatOllama(model=<model>)

    Fails fast with ValueError on unrecognized prefix.
    """
    if name.startswith("ollama:"):
        ollama_model = name[len("ollama:"):]
        return ChatOllama(model=ollama_model, temperature=0)
    elif name.startswith("claude"):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set — required for Claude models")
        return ChatAnthropic(model=name)
    else:
        raise ValueError(
            f"Unknown model '{name}'. "
            "Use 'claude-sonnet-4-6' for Anthropic or 'ollama:<model>' for Ollama."
        )
```

### Pattern 2: Structured Output — ChatOllama Method
**What:** `ChatOllama.with_structured_output()` uses `method="json_schema"` by default (since langchain-ollama 0.3.0), which uses Ollama's native structured output API. This is the same method parameter the existing codebase uses for `ChatAnthropic`.
**When to use:** Always — `json_schema` is most reliable for Ollama models. `function_calling` and `json_mode` exist but are less reliable.

```python
# Source: https://reference.langchain.com/python/langchain-ollama/chat_models/ChatOllama/with_structured_output
from langchain_ollama import ChatOllama
from phonebot.models.caller_info import CallerInfo

model = ChatOllama(model="llama3.2:3b", temperature=0)
# method="json_schema" is the default — Ollama native structured output API
structured_model = model.with_structured_output(CallerInfo, method="json_schema")
```

The existing `extract_node()` call:
```python
model = ChatAnthropic(model=os.getenv("PHONEBOT_MODEL", "claude-sonnet-4-6"))
structured_model = model.with_structured_output(CallerInfo, method="json_schema")
result: CallerInfo = await structured_model.ainvoke(state["transcript_text"])
```

Replace with:
```python
from phonebot.models.model_registry import get_model

model = get_model(os.getenv("PHONEBOT_MODEL", "claude-sonnet-4-6"))
structured_model = model.with_structured_output(CallerInfo, method="json_schema")
result: CallerInfo = await structured_model.ainvoke(state["transcript_text"])
```

No other changes to `extract_node()` required.

### Pattern 3: Model Alias for File Naming
**What:** Convert model name to filesystem-safe alias for output filenames. `ollama:llama3.3` -> `ollama_llama3.3`, `claude-sonnet-4-6` -> `claude-sonnet-4-6`.
**When to use:** When writing `outputs/results_{alias}.json` to avoid overwriting results across runs.

```python
def model_alias(model_name: str) -> str:
    """Convert model name to filesystem-safe alias."""
    return model_name.replace(":", "_")

# In run.py:
alias = model_alias(args.model)
output_path = Path(f"outputs/results_{alias}.json")
```

### Pattern 4: Per-Model Latency from run_pipeline Timing
**What:** `run.py` already measures `duration = time.monotonic() - t0` for the full pipeline run. Include `duration_seconds` in the results file. Compare script reads this from each file.
**When to use:** For the latency comparison column in D-13. No Phoenix trace parsing needed — pipeline-level wall clock is sufficient for this use case.

Latency per recording: `duration_seconds / total_recordings` gives average per-recording time. Include both in `outputs/results_{alias}.json`.

### Pattern 5: Compare Script Structure
**What:** Standalone `compare.py` (not a flag on `run.py`) reads `outputs/results_*.json`, computes per-model metrics, prints Rich tables.
**Recommendation:** Standalone `compare.py` — cleaner separation, easier to re-run without re-running the pipeline, and follows the "separate runs + compare" decision (D-09).

```python
# compare.py — high-level structure
import glob, json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from phonebot.evaluation.metrics import compute_metrics, load_ground_truth

# 1. Glob result files
# 2. For each file: load results, compute metrics, record model + latency
# 3. Print Rich table: per-field accuracy side-by-side per model
# 4. Print per-recording diff table
# 5. Print winner summary
# 6. Write outputs/comparison.json
```

### Anti-Patterns to Avoid
- **Using `langchain-community` for ChatOllama:** The `langchain_community.chat_models.ChatOllama` is the legacy path. `langchain-ollama` is the current dedicated package. Using community would add an unneeded dependency.
- **Rebuilding PIPELINE per model:** The existing code builds PIPELINE once at import time (`PIPELINE = build_pipeline()`). This is correct — the graph is model-agnostic; the model is instantiated inside `extract_node()` via env var. Do not change this.
- **Setting `validate_model_on_init=True` in tests:** `ChatOllama(model=..., validate_model_on_init=True)` makes a live call to Ollama on initialization. Tests must use `validate_model_on_init=False` or mock the registry.
- **Passing `ollama:` prefix to ChatOllama directly:** ChatOllama's `model` parameter expects the native Ollama model name (e.g., `"llama3.2:3b"`) — the `ollama:` prefix is for the registry parser only. Registry must strip `"ollama:"` before passing to `ChatOllama(model=...)`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured JSON extraction from Ollama | Custom JSON parsing + retry logic | `ChatOllama.with_structured_output(CallerInfo, method="json_schema")` | Ollama's native JSON schema API (v0.5+) enforces schema at the model layer — far more reliable than prompt-based JSON extraction |
| Model routing | `if/elif` tree spread across codebase | `model_registry.py` get_model() | Centralizes routing; callers don't need to know which class to instantiate |
| Filesystem-safe model name | Custom sanitization regex | `model_name.replace(":", "_")` | The only special char in the naming convention is `:` — simple replacement is sufficient |

**Key insight:** The `with_structured_output()` interface is the same across ChatAnthropic and ChatOllama — this is by design in LangChain's provider abstraction. The registry pattern exploits this to make the swap zero-cost in `extract_node()`.

---

## Runtime State Inventory

> Included because this phase modifies how results files are written (new naming scheme).

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `outputs/results.json` — single result file from prior runs | No migration needed; new runs write to `results_{alias}.json`. Old file can be left or deleted. |
| Live service config | Ollama server running at `localhost:11434` — confirmed running with models: llama3.2:1b, llama3.2:3b, llama3.2:latest, marco-o1:latest | Need `ollama pull` for llama3.3 variant if using 3.3; llama3.2:3b is immediately available |
| OS-registered state | None | None |
| Secrets/env vars | `ANTHROPIC_API_KEY` in `.env` — already present from Phase 3. Ollama needs no API key. | None |
| Build artifacts | None — no compiled artifacts | None |

**Ollama model availability finding (CRITICAL):**
- `llama3.3:latest` = 43GB — **does not fit** in 36GB M3 Max unified memory
- `llama3.2:3b` (2GB) and `llama3.2:1b` (1.3GB) are already pulled and immediately usable
- Community quantization `mannix/llama-3.3:iq3_xs` (~24-26GB) may fit — requires `ollama pull mannix/llama-3.3:iq3_xs` and empirical verification
- **Recommended plan approach:** Use `llama3.2:3b` as the default second model for initial plan execution (already available, zero pull time, works with structured output). Document `ollama:llama3.3` path as "pull required + may exceed memory" in compare script README/comments.

---

## Common Pitfalls

### Pitfall 1: llama3.3 Does Not Fit in 36GB Unified Memory
**What goes wrong:** `ollama run llama3.3` or `ollama pull llama3.3` installs a 43GB model that cannot be loaded into the 36GB M3 Max — Ollama will OOM or thrash swap.
**Why it happens:** `llama3.3:latest` defaults to Q4_K_M at 43GB. Apple M3 Max has 36GB unified memory shared between CPU and GPU.
**How to avoid:** Use `llama3.2:3b` (already available, 2GB) for testing. For llama3.3 specifically, investigate `mannix/llama-3.3:iq3_xs` community variant before pulling. Verify with `ollama list` before running.
**Warning signs:** `ollama pull` takes longer than expected; pipeline hangs on first Ollama invocation; system swap usage spikes.

### Pitfall 2: Passing `ollama:` Prefix to ChatOllama
**What goes wrong:** `ChatOllama(model="ollama:llama3.2:3b")` — Ollama doesn't recognize the `ollama:` prefix, fails at model lookup.
**Why it happens:** The `ollama:` prefix is a registry routing convention only. ChatOllama expects native model names like `"llama3.2:3b"`.
**How to avoid:** Registry's `get_model()` must strip `"ollama:"` before constructing `ChatOllama(model=stripped_name)`.
**Warning signs:** Ollama API returns 404 for model name; `ChatOllama` raises `ResponseError` with "model not found".

### Pitfall 3: ChatOllama validate_model_on_init in Tests
**What goes wrong:** `ChatOllama(model="llama3.2:3b")` makes a live HTTP call to `localhost:11434` on `__init__`, causing test failures when Ollama isn't running in CI or test environments.
**Why it happens:** `validate_model_on_init` defaults to `True` in langchain-ollama; it checks Ollama server on instantiation.
**How to avoid:** In test fixtures that mock the registry, always pass `validate_model_on_init=False`. Better: mock `get_model()` entirely in registry tests.
**Warning signs:** Tests pass locally but fail in environments where Ollama is not running; `httpx.ConnectError` in test output.

### Pitfall 4: PIPELINE Module-Level Singleton with Registry
**What goes wrong:** `PIPELINE = build_pipeline()` is compiled at import time. The pipeline is model-agnostic (model selected inside `extract_node()` at runtime via env var). If someone tries to inject the model at graph-build time, they'll need to rebuild the pipeline per run.
**Why it happens:** Misunderstanding of where the model is instantiated.
**How to avoid:** Keep the current pattern — env var `PHONEBOT_MODEL` is set by `run_pipeline()` before `PIPELINE.ainvoke()`. `extract_node()` reads it at invocation time. Do not change `build_pipeline()` to accept a model parameter.
**Warning signs:** Proposal to rebuild `PIPELINE` inside `run_pipeline()` per model name.

### Pitfall 5: Structured Output Method Compatibility
**What goes wrong:** Using `method="function_calling"` for Ollama models — some smaller models (llama3.2:3b) have weak tool-calling support and may produce malformed responses.
**Why it happens:** `function_calling` passes schema via Ollama's tool API which is less universally supported than the JSON schema API.
**How to avoid:** Always use `method="json_schema"` (the default in langchain-ollama 0.3.0+) for both ChatAnthropic and ChatOllama. Do not override the method parameter in `get_model()`.
**Warning signs:** Extraction returns empty dicts or `None` for all fields on Ollama model; `langchain_core.output_parsers.pydantic.PydanticOutputParser` raises parse errors.

### Pitfall 6: Compare Script Assumes Exactly Two Result Files
**What goes wrong:** Hardcoded comparison for exactly 2 models. If a user runs 3 models, compare script crashes or produces incorrect output.
**Why it happens:** Designing for "Claude vs Llama" specifically instead of N models.
**How to avoid:** Compare script globs all `outputs/results_*.json` (D-10), iterates over all found files. Per-field accuracy table has one column per model. Winner declared by highest overall accuracy.
**Warning signs:** `outputs/results_*.json` glob returns > 2 files and script fails.

---

## Code Examples

Verified patterns from official sources:

### ChatOllama import and constructor
```python
# Source: https://reference.langchain.com/python/langchain-ollama/chat_models/ChatOllama
from langchain_ollama import ChatOllama

# For production use (validate that model exists on Ollama server):
model = ChatOllama(model="llama3.2:3b", temperature=0)

# For tests (skip live Ollama validation):
model = ChatOllama(model="llama3.2:3b", temperature=0, validate_model_on_init=False)
```

### with_structured_output — same interface as ChatAnthropic
```python
# Source: https://reference.langchain.com/python/langchain-ollama/chat_models/ChatOllama/with_structured_output
# method="json_schema" is the default since langchain-ollama 0.3.0
structured_model = ChatOllama(model="llama3.2:3b").with_structured_output(
    CallerInfo, method="json_schema"
)
result: CallerInfo = await structured_model.ainvoke(transcript_text)
```

### Full model registry
```python
# src/phonebot/models/model_registry.py
import os
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama


def get_model(name: str):
    """Return a LangChain chat model for the given model name string.

    Naming convention:
      claude-*          -> ChatAnthropic(model=name)
      ollama:<model>    -> ChatOllama(model=<model>)

    Raises ValueError with a clear message on unrecognized prefix.
    """
    if name.startswith("claude"):
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise ValueError(
                "ANTHROPIC_API_KEY not set. Required for Claude models. "
                "Add it to your .env file."
            )
        return ChatAnthropic(model=name)
    elif name.startswith("ollama:"):
        ollama_model = name[len("ollama:"):]
        return ChatOllama(model=ollama_model, temperature=0)
    else:
        raise ValueError(
            f"Unrecognized model '{name}'. "
            "Supported prefixes: 'claude-*' (Anthropic), 'ollama:<model>' (Ollama local). "
            "Example: --model ollama:llama3.2:3b"
        )
```

### extract_node() modification (minimal diff)
```python
# Before (Phase 3):
model = ChatAnthropic(model=os.getenv("PHONEBOT_MODEL", "claude-sonnet-4-6"))
structured_model = model.with_structured_output(CallerInfo, method="json_schema")

# After (Phase 5) — only two lines change:
from phonebot.models.model_registry import get_model
model = get_model(os.getenv("PHONEBOT_MODEL", "claude-sonnet-4-6"))
structured_model = model.with_structured_output(CallerInfo, method="json_schema")
```

### run.py output path parameterization
```python
# Model alias: make colon filesystem-safe
alias = args.model.replace(":", "_")
output_path = Path(f"outputs/results_{alias}.json")
# Examples:
#   --model claude-sonnet-4-6  -> outputs/results_claude-sonnet-4-6.json
#   --model ollama:llama3.2:3b -> outputs/results_ollama_llama3.2_3b.json
```

### compare.py skeleton
```python
# compare.py
import glob
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table

from phonebot.evaluation.metrics import compute_metrics, load_ground_truth

console = Console()
gt = load_ground_truth(Path("data/ground_truth.json"))

result_files = sorted(glob.glob("outputs/results_*.json"))
if len(result_files) < 2:
    console.print("[red]Need at least 2 result files in outputs/ to compare.[/red]")
    raise SystemExit(1)

model_metrics = {}
for path in result_files:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    model_name = payload["model"]
    duration = payload.get("duration_seconds", 0)
    total = payload.get("total_recordings", len(payload["results"]))
    metrics = compute_metrics(payload["results"], gt)
    model_metrics[model_name] = {
        "metrics": metrics,
        "avg_latency_s": round(duration / total, 2) if total else 0,
    }

# Print per-field accuracy table (one column per model)
# Print per-recording diff table
# Print overall winner summary
# Write outputs/comparison.json
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `langchain_community.chat_models.ChatOllama` | `langchain_ollama.ChatOllama` | langchain-ollama package split ~mid-2024 | Use `langchain-ollama`, not `langchain-community` |
| Ollama JSON mode (`format="json"`) | Ollama structured output API (`json_schema`) | Ollama v0.5, Dec 2024 | `method="json_schema"` is more reliable than prompt-based JSON; works with virtually all models |
| `method="function_calling"` default in ChatOllama | `method="json_schema"` default | langchain-ollama 0.3.0 | No action needed — default is already the correct choice |

**Deprecated/outdated:**
- `langchain_community.chat_models.ollama.ChatOllama`: Superseded by `langchain_ollama.ChatOllama`. Still works but should not be added as a new dependency.

---

## Open Questions

1. **llama3.3 on 36GB M3 Max**
   - What we know: `llama3.3:latest` = 43GB, exceeds 36GB. Community `mannix/llama-3.3:iq3_xs` may fit (~24-26GB estimated). Llama3.2:3b (2GB) is confirmed available and usable.
   - What's unclear: Whether `mannix/llama-3.3:iq3_xs` actually fits at runtime with OS overhead, and whether it produces usable structured output quality on German text extraction.
   - Recommendation: Plan execution order — (1) run pipeline with `llama3.2:3b` first to prove the registry/structured output path works end-to-end, (2) attempt `mannix/llama-3.3:iq3_xs` as a separate optional wave if the 3.2 run succeeds. Document llama3.2:3b results in comparison output as "llama 3.2 3B" — still valid for demonstrating A/B testing capability.

2. **Latency capture granularity**
   - What we know: `run.py` measures `duration = time.monotonic() - t0` for the full run. This covers all 30 recordings total, not per-recording.
   - What's unclear: Per-recording timing would require timing inside `process_one()`. Is pipeline-level average sufficient for D-13?
   - Recommendation: Add per-recording timing to `process_one()` — record start/end in the returned dict alongside `caller_info`. This enables both per-recording diff and average latency without Phoenix trace parsing. Low-effort change.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Ollama CLI | Ollama model management | Yes | 0.18.2 | — |
| Ollama server | ChatOllama inference | Yes (running at localhost:11434) | 0.18.2 | — |
| llama3.2:3b | A/B test second model (immediate) | Yes (already pulled, 2GB) | Q4_K_M | — |
| llama3.3:latest | A/B test second model (CONTEXT decision) | No (43GB > 36GB M3 Max) | — | llama3.2:3b (available) |
| mannix/llama-3.3:iq3_xs | llama3.3 small-quant variant | Not pulled (needs `ollama pull`) | ~24-26GB est. | llama3.2:3b |
| langchain-ollama | ChatOllama | Not installed (needs `uv add`) | 1.0.1 | — |
| ANTHROPIC_API_KEY | Claude model runs | Yes (in .env from Phase 3) | — | — |

**Missing dependencies with no fallback:**
- `langchain-ollama` — must be installed before implementing model registry (`uv add langchain-ollama`)

**Missing dependencies with fallback:**
- `llama3.3:latest` — too large for machine; use `llama3.2:3b` (already pulled) OR attempt `mannix/llama-3.3:iq3_xs` community variant

---

## Validation Architecture

`workflow.nyquist_validation` is absent from `.planning/config.json` — treating as enabled.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 0.25.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_model_registry.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AB-01 | Registry routes `claude-*` to `ChatAnthropic` | unit | `uv run pytest tests/test_model_registry.py::test_registry_routes_claude -x` | Wave 0 |
| AB-01 | Registry routes `ollama:*` to `ChatOllama` with correct model name | unit | `uv run pytest tests/test_model_registry.py::test_registry_routes_ollama -x` | Wave 0 |
| AB-01 | Registry strips `ollama:` prefix before passing to ChatOllama | unit | `uv run pytest tests/test_model_registry.py::test_registry_strips_ollama_prefix -x` | Wave 0 |
| AB-01 | Registry raises ValueError on unrecognized model name | unit | `uv run pytest tests/test_model_registry.py::test_registry_unknown_model_raises -x` | Wave 0 |
| AB-01 | `extract_node()` uses registry (not hardcoded ChatAnthropic) | unit | `uv run pytest tests/test_extract.py::test_extract_node_uses_registry -x` | Wave 0 |
| AB-01 | run.py writes `results_{alias}.json` not `results.json` | unit | `uv run pytest tests/test_cli.py::test_output_path_uses_model_alias -x` | Wave 0 |
| AB-02 | compare.py loads two result files and computes per-model metrics | unit | `uv run pytest tests/test_compare.py::test_compare_loads_two_files -x` | Wave 0 |
| AB-02 | compare.py declares a winner by overall accuracy | unit | `uv run pytest tests/test_compare.py::test_compare_declares_winner -x` | Wave 0 |
| AB-02 | compare.py writes `outputs/comparison.json` | unit | `uv run pytest tests/test_compare.py::test_compare_writes_json -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_model_registry.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_model_registry.py` — covers AB-01 registry routing, prefix stripping, error handling
- [ ] `tests/test_compare.py` — covers AB-02 compare script logic (load files, compute metrics, write JSON)
- [ ] Tests in `tests/test_extract.py` — add `test_extract_node_uses_registry` (mock `get_model`, verify it's called)
- [ ] Tests in `tests/test_cli.py` — add `test_output_path_uses_model_alias`

*(Existing test infrastructure: pytest + pytest-asyncio already configured in pyproject.toml — no framework install needed)*

---

## Sources

### Primary (HIGH confidence)
- `reference.langchain.com/python/langchain-ollama/chat_models/ChatOllama/with_structured_output` — `with_structured_output` method signature, method options (`json_schema`, `function_calling`, `json_mode`), default changed to `json_schema` in v0.3.0
- `reference.langchain.com/python/langchain-ollama/chat_models/ChatOllama` — Constructor signature, `validate_model_on_init` parameter, model name format
- `pypi.org/pypi/langchain-ollama/json` — Version 1.0.1 confirmed (2026-03-27)
- Local environment probe — Ollama 0.18.2 running, models: llama3.2:1b, llama3.2:3b, llama3.2:latest, marco-o1:latest
- Ollama library page `ollama.com/library/llama3.3/tags` — llama3.3:latest = 43GB

### Secondary (MEDIUM confidence)
- `ollama.com/blog/structured-outputs` — Ollama v0.5 structured output API (Dec 2024); `format=json_schema` in Ollama API maps to `method="json_schema"` in langchain-ollama
- `mannix/llama-3.3` on Ollama hub — IQ3_xs variant for 70B llama3.3 fitting smaller memory budgets (size unconfirmed, estimated 24-26GB)

### Tertiary (LOW confidence)
- Multiple blog posts re: llama3.3 Q4_K_M requiring 42-43GB on M-series hardware — consistent across sources, treated as MEDIUM

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — langchain-ollama 1.0.1 confirmed on PyPI; ChatOllama structured output verified via official reference docs
- Architecture: HIGH — registry pattern is standard Python; ChatOllama interface verified identical to ChatAnthropic
- Pitfalls: HIGH — llama3.3 memory issue confirmed by direct Ollama tags page (43GB); validate_model_on_init confirmed in official reference; prefix stripping is a logical necessity from D-06
- Environment: HIGH — probed directly on target machine

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (langchain-ollama is active; Ollama model sizes stable)
