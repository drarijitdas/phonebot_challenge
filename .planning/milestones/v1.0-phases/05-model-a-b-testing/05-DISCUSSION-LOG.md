# Phase 5: Model A/B Testing - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-27
**Phase:** 05-model-a-b-testing
**Areas discussed:** Second model choice, Model routing, Open-source hosting, Comparison output

---

## Second Model Choice

| Option | Description | Selected |
|--------|-------------|----------|
| Llama 3.3 70B | Meta's best open model. Strong multilingual, good structured output. Available on Groq/Together.ai. | |
| Mistral Large / Mixtral | Good European language support. Lighter weight. | |
| Gemini Flash | Google's fast model. Free tier. Strong multilingual and structured output. | (initially) |
| Multiple models | Test 2-3 models for richer comparison. | |

**User's initial choice:** Gemini Flash
**Revised choice:** Llama 3.3 via Ollama (local) — user later changed to Ollama-hosted models for local control
**Notes:** User explicitly switched from Gemini to Ollama after discussing hosting, preferring local execution and flexibility to try any Ollama model.

### Follow-up: Extensibility

| Option | Description | Selected |
|--------|-------------|----------|
| Two models is enough | Hardcode Claude + second model. Simpler. | |
| Registry pattern | Model registry/factory mapping --model names to LangChain classes. | ✓ |

**User's choice:** Registry pattern

---

## Model Routing

| Option | Description | Selected |
|--------|-------------|----------|
| LangChain native | Dict mapping model aliases to LangChain classes. No extra deps. | ✓ |
| LiteLLM proxy | Universal proxy, 100+ models, one interface. Extra dependency. | |
| You decide | Claude picks simplest approach. | |

**User's choice:** LangChain native

### Follow-up: Registry location

| Option | Description | Selected |
|--------|-------------|----------|
| src/phonebot/models/ | New model_registry.py in models package. | ✓ |
| src/phonebot/pipeline/ | Alongside extract.py. | |
| You decide | Claude picks natural location. | |

**User's choice:** src/phonebot/models/

---

## Open-source Hosting

### Initial discussion (Gemini-era):

| Option | Description | Selected |
|--------|-------------|----------|
| GOOGLE_API_KEY in .env | Same pattern as existing keys. | (initially) |
| You decide | Follow established pattern. | |

| Option | Description | Selected |
|--------|-------------|----------|
| Fail fast | Exit with clear error on missing key. | ✓ |
| Warn and skip | Print warning and skip model. | |

**Revised:** User changed from Gemini (API) to Ollama (local). No cloud API key needed.

### Revised hosting (Ollama):

| Option | Description | Selected |
|--------|-------------|----------|
| llama3.3 | Meta's latest, strong multilingual, good structured output. | ✓ |
| mistral | Good European language support, lighter. | |
| qwen2.5 | Strong structured output, good multilingual. | |
| You decide | Claude picks best default for German extraction. | |

**User's choice:** llama3.3 as default

### Naming convention:

| Option | Description | Selected |
|--------|-------------|----------|
| Prefix convention | --model ollama:llama3.3, --model claude-sonnet-4-6. Colon prefix. | ✓ |
| Alias mapping | Short aliases (claude, llama). | |
| Both | Aliases + explicit format. | |

**User's choice:** Prefix convention

---

## Comparison Output

### Workflow:

| Option | Description | Selected |
|--------|-------------|----------|
| Separate runs + compare script | Run twice, compare script reads both outputs. | ✓ |
| Single run, multiple models | One invocation runs both models. | |
| You decide | Claude picks best fit. | |

**User's choice:** Separate runs + compare script

### Metrics (multi-select):

| Option | Description | Selected |
|--------|-------------|----------|
| Per-field accuracy | Core comparison per model. | ✓ |
| Latency | Average extraction time per recording. | ✓ |
| Per-recording diff | Which recordings differ between models. | ✓ |
| Overall winner | Bold summary declaring winner. | ✓ |

**User's choice:** All four metrics

### Output format:

| Option | Description | Selected |
|--------|-------------|----------|
| Console + JSON | Rich table + outputs/comparison.json. | ✓ |
| Console only | Just print Rich table. | |
| You decide | Follow established pattern. | |

**User's choice:** Console + JSON

### File naming:

| Option | Description | Selected |
|--------|-------------|----------|
| outputs/results_{model}.json | Model-specific files. Compare globs results_*.json. | ✓ |
| outputs/{model}/results.json | Separate directories per model. | |
| You decide | Simplest naming scheme. | |

**User's choice:** outputs/results_{model}.json

---

## Claude's Discretion

- Exact model registry dict structure and error handling
- How ChatOllama handles structured output
- Compare script CLI design (standalone vs flag)
- Rich table layout for comparison
- Latency extraction approach
- langchain-ollama vs langchain-community dependency choice

## Deferred Ideas

- **Other STT models** — Comparing Deepgram vs Whisper (outside Phase 5 scope — extraction LLM, not STT)
- **Actor-critic approaches** — One model extracts, another critiques. Overlaps Phase 6/7. Noted for backlog.
