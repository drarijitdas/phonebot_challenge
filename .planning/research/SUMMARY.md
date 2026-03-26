# Project Research Summary

**Project:** phonebot_challenge — German Phone Bot Audio Entity Extraction
**Domain:** Audio pipeline (German STT + LLM structured extraction + prompt optimization + observability)
**Researched:** 2026-03-26
**Confidence:** HIGH

## Executive Summary

This project is a batch audio entity extraction pipeline: 30 pre-recorded German phone bot WAV files must be transcribed with Deepgram Nova-3, then have four fields (first_name, last_name, email, phone_number) extracted via an LLM and evaluated against ground truth. The recommended approach combines LangGraph for typed pipeline orchestration, Pydantic BaseModel as both the extraction schema and per-field prompt specification, Arize Phoenix for full span-level observability, and GEPA for offline prompt optimization against ground truth. All components integrate cleanly and are designed to be evaluated on accuracy, observability, and prompt engineering maturity — not just raw output correctness.

The primary technical risk is the gap between Deepgram's documented smart_format behavior (English-first) and actual German output. Phone numbers will arrive as spoken digit words ("null zwei null eins...") and email addresses as spoken tokens ("mueller at beispiel punkt de") — the LLM extraction prompt must be explicitly designed to handle both normalized and un-normalized spoken-form input. A secondary risk is evaluation integrity: the ground truth schema supports multiple acceptable values per field, and exact-match comparison without normalization will silently under-report accuracy, corrupting the GEPA optimization signal.

The architecture is a 7-phase build sequence with a clear dependency chain: foundation types and evaluation metrics first, then transcription (with smart_format verification), then extraction pipeline, then observability, then multi-model A/B testing, then GEPA optimization, then hardening. GEPA requires a working evaluation harness before it can run. Arize Phoenix must be initialized before the LangGraph graph is compiled. Each phase has a concrete deliverable and a go/no-go checkpoint that prevents building on bad data. The overall complexity is medium — all components are well-documented — but the German language-specific edge cases require intentional design at every stage.

## Key Findings

### Recommended Stack

The stack centers on five well-integrated packages. Deepgram's `nova-3` model with `language="de"` provides the best available German ASR. LangGraph 1.1.3 provides typed stateful pipeline orchestration where nodes are pure functions that read and write to a `TypedDict` state — the graph topology documents the pipeline structure. Pydantic 2.12.5 doubles as the schema definition and the prompt: a `CallerInfo(BaseModel)` with docstring as system prompt and `Field(description=...)` per field gets passed directly to `llm.with_structured_output(CallerInfo)`, eliminating a parsing step and enabling Anthropic's native tool-use mechanism. Arize Phoenix 13.19.0 instruments all LangGraph nodes automatically via a single `register(auto_instrument=True)` call — no per-node span management needed. GEPA 0.1.1 optimizes the externalized system prompt offline using the evaluation harness as its scoring function.

**Core technologies:**
- `deepgram-sdk 6.0.1`: German STT via Nova-3 — only model with dedicated German support; `PrerecordedOptions` API is v6-breaking from v3/v4
- `langgraph 1.1.3`: Pipeline orchestration — stateful graph maps directly to transcribe/extract/validate stages; native Phoenix tracing
- `pydantic 2.12.5`: Extraction schema and runtime validation — `with_structured_output()` uses it as both JSON schema and prompt
- `langchain-anthropic 1.4.0`: Claude Sonnet 4.6 as primary extraction LLM — identical `with_structured_output()` interface to `langchain-openai` for model swap
- `arize-phoenix 13.19.0` + `openinference-instrumentation-langchain 0.1.61`: Full observability — one call instruments everything
- `gepa 0.1.1`: Automated prompt evolution — ICLR 2026 accepted; outperforms DSPy MIPROv2 by 10%+ on small structured extraction datasets
- `uv` + Python 3.11: Dependency management — 3.11 is the safe intersection for all packages (arize-phoenix caps at <3.14)

See `.planning/research/STACK.md` for integration code patterns and alternatives analysis.

### Expected Features

The evaluation judges on three axes: accuracy against ground truth, observability (Phoenix traces), and engineering maturity (prompt optimization, A/B model comparison). Missing any P1 feature means failing at least one evaluation criterion.

**Must have (table stakes):**
- Deepgram Nova-3 batch transcription of all 30 WAV files — the entire pipeline depends on this
- LangGraph pipeline: transcription node → extraction node → validation node — structural backbone
- Pydantic `CallerInfo` with `Optional` fields and explicit null semantics — prevents hallucination and enforces type safety
- LLM extraction of all four fields with German spoken-form handling in field descriptions — core accuracy dependency
- Evaluation harness with per-field accuracy and multi-value normalization — required to measure any improvement
- Arize Phoenix tracing on all nodes before submission — evaluators explicitly assess observability

**Should have (competitive):**
- Multi-model A/B testing (Claude Sonnet 4.6 + at least one other) — demonstrates model awareness; Phoenix tags runs by model
- GEPA prompt optimization (20-call train / 10-call held-out split) — documented 20+ pp improvement on similar structured extraction tasks
- LangGraph retry loop on Pydantic validation failure — handles phone/email format errors gracefully
- `phonenumbers` library normalization for phone comparison — prevents correct extractions from scoring as wrong due to format differences
- `json.dumps(ensure_ascii=False)` + NFC normalization throughout — prevents umlaut round-trip failures

**Defer (v2+):**
- Streaming/real-time transcription — pre-recorded files only; adds complexity with zero benefit
- Active learning / human review loop — requires production traffic
- Multilingual extension — out of scope; different STT model needed

See `.planning/research/FEATURES.md` for full feature dependency tree and prioritization matrix.

### Architecture Approach

The architecture separates concerns across five distinct layers: CLI entry point (`run.py`) → Phoenix instrumentation layer → LangGraph pipeline graph → typed pipeline state → evaluation/optimization harness. GEPA is offline-only: it runs before production execution, writes the optimized prompt to `prompts/extraction_v1.txt`, and the pipeline reads that file at startup. One `graph.invoke(state)` call per WAV file — not one batch call — ensures 30 independent traces in Phoenix and isolated error recovery. The LLM is injected into the extraction node factory (`make_extract_node(llm)`) rather than hardcoded, enabling clean model swapping for A/B comparison.

**Major components:**
1. `pipeline/nodes/transcribe.py` — Deepgram Nova-3 call; writes transcript string to state
2. `pipeline/nodes/extract.py` — LLM + `with_structured_output(CallerInfo)`; reads transcript, writes `CallerInfo` instance
3. `pipeline/nodes/validate.py` — additional checks post-extraction (null completeness, format anomalies)
4. `pipeline/models/caller_info.py` — `CallerInfo` Pydantic model; the contract between LLM and evaluation
5. `evaluation/metrics.py` — per-field accuracy with multi-value normalization; shared by both standalone eval and GEPA evaluator
6. `observability/setup.py` — single `register(auto_instrument=True)` call; must run before graph compilation
7. `optimization/optimize_prompt.py` — GEPA offline run; reads training subset, writes `prompts/extraction_v1.txt`

See `.planning/research/ARCHITECTURE.md` for recommended project structure, all anti-patterns, and the full 7-phase build order.

### Critical Pitfalls

1. **smart_format does not normalize German phone/email** — Deepgram's documentation for this feature is English-first. German output will contain spoken tokens ("punkt", "at", "null neun null..."), not formatted strings. LLM field descriptions must explicitly handle both normalized and un-normalized forms. Verify transcript output on 5 recordings before building the extraction layer.

2. **Evaluation exact-match will under-report accuracy** — Ground truth supports multiple acceptable values per field (e.g., "Lisa Marie" or "Lisa-Marie"). An `==` comparison fails silently on correct extractions. Design a `matches_ground_truth()` function that handles scalar, list, and null ground truth values before writing any evaluation code. This also corrupts the GEPA optimization signal if not fixed first.

3. **LLM confabulates fields not present in transcript** — Without explicit null instructions and `Optional[str] = None` Pydantic typing, the LLM fills missing fields with plausible German surnames or generic email domains. Add "return null if not clearly stated" to both system prompt and per-field descriptions. Set `temperature=0`.

4. **German phone number format ambiguity** — Callers say "+49 30..." or "null dreißig..." producing different canonical forms. Use `phonenumbers.parse(raw, "DE")` and normalize to E.164 in both extraction output and evaluation comparison — not just one side.

5. **Umlaut round-trip encoding** — `json.dumps` with default `ensure_ascii=True` escapes `ü` as `\u00fc`. Always use `ensure_ascii=False` and `unicodedata.normalize("NFC", value)` in evaluation comparison. Test with a Jürgen/Müller recording before declaring the pipeline functional.

6. **GEPA requires a correctly wired evaluation function** — GEPA has no built-in LangGraph adapter. A custom `GEPAAdapter` wrapper is required. If the evaluation function uses too-strict or too-lenient matching, GEPA converges on prompts that game the metric. Budget 1-2 days for the adapter and evaluation function validation.

See `.planning/research/PITFALLS.md` for recovery strategies, integration gotchas, and the "looks done but isn't" checklist.

## Implications for Roadmap

Based on the build order from ARCHITECTURE.md, the dependency chain from FEATURES.md, and the phase-mapped pitfalls from PITFALLS.md, a 7-phase structure is recommended. Each phase has a go/no-go checkpoint that prevents building downstream components on bad data.

### Phase 1: Foundation (Types, Schema, Evaluation Metrics)
**Rationale:** Evaluation metrics must exist before the first pipeline run so accuracy is measurable from the start. Pydantic schema must be defined before any node can reference it. These have zero external dependencies and can be validated with unit tests alone.
**Delivers:** `PipelineState` TypedDict, `CallerInfo` Pydantic model with null-safe fields, `evaluation/metrics.py` with multi-value normalization, `evaluation/compare.py` reading `ground_truth.json`. Zero accuracy baseline confirmed.
**Addresses:** Table stakes — structured output, null handling, per-field accuracy reporting
**Avoids:** Pitfall 2 (evaluation exact-match) and Pitfall 3 (LLM confabulation) — both must be designed in from the start, not retrofitted

### Phase 2: Transcription + Smart Format Verification
**Rationale:** All downstream components depend on transcript quality. German spoken-form normalization requirements can only be assessed from actual Deepgram output. Must verify smart_format behavior on real recordings before writing extraction prompts.
**Delivers:** 30 transcript strings cached to disk; manual review of 3-5 transcripts confirming phone/email format; determination of whether a post-transcription normalization layer is needed
**Addresses:** End-to-end transcription of all 30 WAVs
**Avoids:** Pitfall 1 (smart_format unreliable) and Pitfall 6 (umlaut encoding) — catch both before extraction is built on top

### Phase 3: Extraction Pipeline (End-to-End Accuracy Baseline)
**Rationale:** With transcripts cached and evaluation metrics ready, the first end-to-end run establishes the baseline accuracy number. This is the anchor all subsequent improvements are measured against. Start with a fast/cheap model (GPT-4o-mini or Claude Haiku) to iterate prompt quickly.
**Delivers:** Working LangGraph graph (START → transcribe → extract → END), first `outputs/results.json`, baseline per-field accuracy score, identification of hard cases (spoken phone formats, multi-value names)
**Uses:** `deepgram-sdk`, `langgraph`, `langchain-anthropic` or `langchain-openai`, `pydantic`
**Avoids:** Pitfall 4 (phone number format) — `phonenumbers` normalization added in evaluation harness here

### Phase 4: Observability (Arize Phoenix)
**Rationale:** Evaluators specifically assess observability. Phoenix must be live before multi-model A/B testing — without it, A/B results are just two accuracy numbers with no trace data. Initialize Phoenix before graph compilation.
**Delivers:** Phoenix project "phonebot-extraction" with 30 independent traces per model run; node-level span visibility; STT and LLM latency visible; re-run of Phase 3 pipeline with tracing active
**Implements:** `observability/setup.py`, `register(auto_instrument=True)` in `run.py` before `build_graph()`
**Avoids:** Arize Phoenix span context pitfall — Phoenix must be initialized before LangGraph event loop starts

### Phase 5: Multi-Model A/B Testing
**Rationale:** Model comparison with Phoenix traces demonstrates engineering maturity. Refactor the extraction node to accept an injected LLM (eliminates the hardcoded LLM anti-pattern). Run at minimum Claude Sonnet 4.6 and one alternative (GPT-4o-mini). Phoenix experiments tag runs by model for dashboard comparison.
**Delivers:** Per-model accuracy comparison table; identification of best baseline model for GEPA optimization; Phoenix experiments with A/B model tagging
**Addresses:** Multi-model A/B testing differentiator feature

### Phase 6: GEPA Prompt Optimization
**Rationale:** GEPA requires a stable baseline accuracy score and a working evaluation harness (both from Phase 3) to optimize against. Externalize the system prompt to `prompts/extraction_v1.txt` first. Run GEPA on 20-call training subset, validate on 10-call held-out set to avoid overfitting the 30-file set.
**Delivers:** Optimized `prompts/extraction_v1.txt`; accuracy delta vs Phase 3 baseline; demonstration of automated prompt improvement
**Avoids:** Pitfall 5 (GEPA evaluation function) — the `field_accuracy()` function from Phase 1/3 is reused by the GEPA evaluator; normalization must match

### Phase 7: Validation, Hardening, Final Submission
**Rationale:** Add the validation node (retry loop on Pydantic failure), write tests, run the full eval with optimized prompt across all models, produce final `outputs/results.json`.
**Delivers:** `validate_node` with conditional retry edge; test suite for transcription/extraction/evaluation; final accuracy report; Phoenix dashboard screenshot; submission artifacts
**Addresses:** LangGraph retry loop, confidence/uncertainty signaling, documented pipeline structure

### Phase Ordering Rationale

- Evaluation metrics before transcription: catching an incorrect multi-value comparison on run 1 costs nothing; discovering it after 500 GEPA iterations is expensive
- Transcription before extraction: spoken-form behavior of smart_format on German is unknown until tested; extraction prompt design depends on knowing what the LLM will receive
- Baseline accuracy before Phoenix: ensures the first round of traces reflects a working pipeline, not a debugging artifact
- A/B comparison before GEPA: GEPA should optimize the best-performing model's prompt, not the first model tried
- GEPA before hardening: the retry loop and validation node add complexity; validate prompt quality first with a clean graph

### Research Flags

Phases needing deeper research or careful validation during planning:
- **Phase 2 (Transcription):** smart_format behavior for German is under-documented. Cannot finalize extraction prompt field descriptions until real transcript samples are analyzed. Must test with actual recordings, not documentation.
- **Phase 6 (GEPA):** No reference implementation for LangGraph + GEPA adapter exists. Budget 1-2 days for the custom `GEPAAdapter` wrapper. GEPA documentation may lag the code (MEDIUM confidence per STACK.md).
- **Phase 6 (GEPA):** GEPA API budget estimation needed before running: 100-500 evaluations × 20 recordings × LLM calls = significant API cost. Validate cost before committing.

Phases with standard, well-documented patterns (can skip `/gsd:research-phase`):
- **Phase 1 (Foundation):** Pydantic models and TypedDict state are standard LangGraph patterns with official documentation.
- **Phase 4 (Phoenix):** Single `register(auto_instrument=True)` call; official integration docs cover LangGraph explicitly.
- **Phase 5 (A/B):** LangChain model swap is a one-line change; Phoenix experiments API is documented.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified via PyPI; integration patterns confirmed against official docs; GEPA docs rated MEDIUM but core API is clear |
| Features | HIGH (core), MEDIUM (German STT nuances) | Core pipeline features well-understood; German smart_format behavior is under-documented and must be empirically tested |
| Architecture | HIGH | All five components have official documentation; integration patterns verified; build order confirmed by dependency analysis |
| Pitfalls | HIGH (stack-specific), MEDIUM (German ASR errors) | Stack integration pitfalls confirmed via official docs and community issues; German ASR error patterns from research literature |

**Overall confidence:** HIGH for the core pipeline approach; MEDIUM for German language-specific behavior (smart_format, umlaut handling, spoken number formats) which must be validated empirically on actual recordings.

### Gaps to Address

- **smart_format German phone/email behavior:** Cannot be resolved from documentation alone. Phase 2 must include empirical testing on real recordings and a go/no-go decision on whether a post-transcription normalization layer is required. If normalization is needed, it gates Phase 3 extraction prompt design.
- **Ground truth schema:** The exact format of multi-value fields in `data/ground_truth.json` (scalar string vs list vs separate aliases field) is unknown until the file is inspected. Phase 1 evaluation harness code depends on this schema. Inspect the file first.
- **GEPA LangGraph adapter:** No reference implementation exists. The adapter is conceptually simple (call `graph.invoke()`, return a float) but integration testing may surface edge cases. Treat as an unknown-unknowns risk area.
- **Keyterm support for German in Nova-3:** Deepgram keyterm prompting for non-English languages was in limited rollout as of research date. Test keyterm behavior for non-German caller names before relying on it for Pitfall 2 mitigation.

## Sources

### Primary (HIGH confidence)
- [Deepgram Nova-3 German announcement](https://deepgram.com/learn/deepgram-expands-nova-3-with-german-dutch-swedish-and-danish-support) — `language="de"` confirmed, compound word support
- [Deepgram smart_format docs](https://developers.deepgram.com/docs/smart-format) — English-first coverage; German limited to punctuation/paragraphs
- [Deepgram pre-recorded audio Python SDK](https://developers.deepgram.com/docs/pre-recorded-audio) — `transcribe_file()` API and response structure
- [langgraph PyPI](https://pypi.org/project/langgraph/) — version 1.1.3, Python >=3.10
- [pydantic PyPI](https://pypi.org/project/pydantic/) — version 2.12.5
- [langchain-anthropic PyPI](https://pypi.org/project/langchain-anthropic/) — version 1.4.0
- [arize-phoenix PyPI](https://pypi.org/project/arize-phoenix/) — version 13.19.0, Python <3.14
- [Phoenix LangGraph tracing docs](https://arize.com/docs/phoenix/integrations/python/langgraph/langgraph-tracing) — `auto_instrument=True` pattern confirmed
- [LangGraph extraction with retries](https://langchain-ai.github.io/langgraph/tutorials/extraction/retries/) — official retry loop pattern
- [Arize Phoenix GitHub](https://github.com/Arize-ai/phoenix) — OpenTelemetry-based, self-hosted
- [GEPA GitHub](https://github.com/gepa-ai/gepa) — `optimize_anything` API, evaluator pattern
- [GEPA ICLR 2026 paper](https://arxiv.org/abs/2507.19457) — reflective prompt evolution; outperforms MIPROv2 by 10%+

### Secondary (MEDIUM confidence)
- [DSPy GEPA structured extraction tutorial](https://dspy.ai/tutorials/gepa_facilitysupportanalyzer/) — 20+ pp improvement with 34-example dataset
- [GEPA docs](https://gepa-ai.github.io/gepa/) — optimize_anything API; may lag code
- [Arize Phoenix span context discussion](https://github.com/Arize-ai/phoenix/discussions/4800) — Phoenix must initialize before LangGraph event loop
- [Deepgram community — smart_format German numeral edge case](https://github.com/orgs/deepgram/discussions/1168) — confirms limitation
- [Telekom phonenumber-normalizer](https://github.com/telekom/phonenumber-normalizer) — German E.164 normalization complexity
- [Information extraction from conversation transcripts (arXiv 2025)](https://arxiv.org/html/2510.12023) — LLMs outperform classical NER for noisy ASR output
- [ASR in German: A Detailed Error Analysis (Wirth & Peinl, 2022)](https://arxiv.org/abs/2204.05617) — phonetic transcription patterns for foreign names

### Tertiary (LOW confidence — validate during implementation)
- Deepgram keyterm support for German (Nova-3) — limited rollout; behavior must be empirically tested
- GEPA LangGraph adapter pattern — no reference implementation; conceptual approach only

---
*Research completed: 2026-03-26*
*Ready for roadmap: yes*
