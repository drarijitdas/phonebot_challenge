# Feature Research

**Domain:** Audio entity extraction pipeline — German phone bot recordings, structured caller information extraction
**Researched:** 2026-03-26
**Confidence:** HIGH (core pipeline features), MEDIUM (German-specific STT nuances), HIGH (evaluation and observability)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features the evaluators assume exist. Missing these means the submission feels incomplete and will not pass the technical discussion.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| End-to-end transcription of all 30 WAV files | The core task. No transcription = nothing works downstream | LOW | Deepgram Nova-3 batch API; single-call per file |
| Extraction of all four fields: first_name, last_name, email, phone_number | Directly specified in the challenge brief | MEDIUM | LLM with Pydantic structured output; all four must be present, even if null |
| Null/missing field handling | Not every caller provides every field; extracting garbage is worse than returning null | LOW | Pydantic Optional fields with explicit None semantics; LLM must not hallucinate |
| Evaluation against ground truth | Challenge explicitly evaluates accuracy against 30 known-answer recordings | MEDIUM | Per-field exact-match scoring; aggregate accuracy metric; must be reproducible |
| Per-field accuracy reporting | Evaluators need to see which fields succeed and which fail, not just overall accuracy | LOW | Breakdown by field (first_name, last_name, email, phone_number) across all 30 files |
| Deterministic, reproducible runs | Technical discussion will involve re-running and explaining results | LOW | Fixed LLM temperature (0 or low); seeded where possible; idempotent pipeline |
| Structured output with type safety | Industry standard for LLM extraction pipelines; Pydantic is the expected tool | LOW | Pydantic BaseModel with Optional fields and field-level descriptions |
| Documented pipeline structure | Evaluators will read the code; undocumented pipelines fail the "future-proofing" criterion | LOW | LangGraph graph structure serves as living documentation of flow |

### Differentiators (Competitive Advantage)

Features that set this submission apart from a naive transcript-then-prompt approach.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Pydantic BaseModel as prompt specification | Docstrings as system prompts, field descriptions as per-field extraction instructions — self-documenting, prompt logic lives in the schema | MEDIUM | Demonstrates "prompt as code" thinking; field descriptions drive targeted extraction; directly improves accuracy for ambiguous fields |
| LangGraph graph-based orchestration | Graph topology makes pipeline stages explicit, testable, and swappable; retry/branching logic is structural, not ad-hoc | MEDIUM | Enables validation nodes, retry edges on extraction failure, conditional skip if transcript empty |
| LangGraph retry loop on validation failure | If Pydantic validation fails (wrong type, failed regex), graph re-prompts with error context rather than silently failing | MEDIUM | LangGraph has built-in RetryPolicy; conditional edges loop back to extraction node with validation error in state |
| Multi-model A/B testing | Running the same recordings through multiple LLMs and comparing accuracy demonstrates engineering maturity and model awareness | HIGH | Arize Phoenix traces tag model name; aggregate accuracy by model; surfaces cost/accuracy tradeoff |
| GEPA prompt optimization | Automated prompt evolution against ground truth; 20+ percentage point accuracy gains documented in DSPy structured extraction tasks with small datasets (~34 examples) | HIGH | DSPy GEPA or DeepEval GEPA; needs train/validation split from the 30 recordings; ICLR 2026 accepted paper |
| Arize Phoenix observability | Full span-level tracing of every pipeline run; STT latency, LLM call latency, model used, extracted values, ground truth delta — all queryable | MEDIUM | OpenTelemetry-native; LangChain/LangGraph auto-instrumentation available; prompt management module for versioning |
| Post-normalization step for German entities | German phone numbers spoken as digit sequences ("null zwei null eins..."); emails spoken as "Müller at Beispiel Punkt de" — raw transcript needs inverse text normalization before or during extraction | HIGH | smart_format on Deepgram Nova-3 does NOT format phones/emails for German (only punctuation + paragraphs); LLM must handle spoken-form normalization or a pre-processing step is needed |
| Confidence/uncertainty signaling | Returning `None` with a low-confidence flag is more honest and actionable than a hallucinated value | MEDIUM | Add confidence field to Pydantic model or use Phoenix span annotations to flag low-confidence extractions |
| Ground truth tolerance for multi-value fields | Challenge notes some fields accept multiple values (e.g., "Lisa Marie" or "Lisa-Marie"); exact-match without normalization will under-count accuracy | MEDIUM | Normalize both prediction and ground truth before comparison: lowercase, strip punctuation, sort alternative spellings |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Regex-based extraction of phone/email from raw transcript | Seems fast and deterministic | German phone numbers come out as written words ("null zwei..."), not digit strings; email domains as separate spoken words ("Punkt de"); regex has near-zero recall on raw German ASR output | Use LLM extraction with explicit field descriptions explaining spoken-form input; or add inverse text normalization before regex |
| Streaming/real-time transcription | Sounds more impressive than batch | Challenge uses pre-recorded files; streaming adds latency, complexity, and cost with zero benefit | Deepgram batch API with `prerecorded` endpoint; simpler, faster, cheaper for fixed files |
| Web UI or API server | Makes it "more product-like" | Scope creep; evaluators will run via CLI; server adds deployment complexity that isn't evaluated | Clean CLI entrypoint with clear arguments; focus engineering time on accuracy and observability |
| Confidence thresholding with rejection | Seems rigorous | With only 30 files and a ground truth, rejecting extractions hides failures rather than surfacing them; evaluators want to see all extractions | Always produce an extraction (possibly None); report per-field accuracy transparently; use confidence as metadata, not a gate |
| Fine-tuning an LLM on the 30 recordings | Would maximize accuracy on the test set | Overfitting to a 30-sample dataset; not generalizable; obscures whether the approach works on new data; violates the spirit of prompt engineering evaluation | Use GEPA prompt optimization which generalizes better and requires only the same small dataset |
| Ensemble voting across many models | Higher theoretical accuracy ceiling | With 30 recordings and 4 fields, variance reduction from ensembling is marginal; cost is high; complexity hides errors | A/B test two or three models; pick the best one; report the comparison transparently |
| Custom German NER model (spaCy, Hugging Face) | Feels like "proper NLP" | LLM-based extraction outperforms classical NER for this task (few-shot, handles spoken-form input); classical NER requires labeled training data; maintenance overhead | Use LLM with Pydantic field descriptions; classical NER is an anti-feature here, not a feature |

---

## Feature Dependencies

```
[Deepgram Nova-3 Transcription]
    └──produces──> [Raw German Transcript]
                       └──required by──> [LLM Extraction Node]
                                             └──required by──> [Pydantic Validation]
                                                                   └──required by──> [Evaluation Harness]

[German Spoken-Form Normalization]
    └──enhances──> [LLM Extraction Node]
    (spoken phone/email in words → structured values)

[Pydantic BaseModel Schema]
    └──drives──> [LLM Extraction Node] (field descriptions = per-field prompts)
    └──drives──> [Pydantic Validation] (type enforcement)

[LangGraph Graph Topology]
    └──wraps──> [Transcription Node]
    └──wraps──> [Extraction Node]
    └──wraps──> [Validation Node]
    └──enables──> [Retry Loop on Validation Failure]

[Arize Phoenix Tracing]
    └──instruments──> [All LangGraph Nodes]
    └──enables──> [Multi-model A/B comparison]
    └──enables──> [Prompt version tracking]

[GEPA Prompt Optimization]
    └──requires──> [Evaluation Harness] (needs ground truth metric to optimize against)
    └──requires──> [Pydantic BaseModel Schema] (optimizes the field descriptions / system prompt)
    └──produces──> [Optimized Extraction Prompts]
                       └──feeds back into──> [LLM Extraction Node]

[Multi-model A/B Testing]
    └──requires──> [Arize Phoenix Tracing] (traces must tag model identity)
    └──requires──> [Evaluation Harness] (to compare accuracy per model)

[Evaluation Harness]
    └──requires──> [Ground Truth JSON]
    └──requires──> [Extracted Output per Recording]
    └──requires──> [Multi-value field normalization logic]
```

### Dependency Notes

- **Transcription must precede extraction:** The LLM extraction node consumes raw transcript text; there is no extraction without it. Transcription failures propagate as null extractions, not pipeline errors.
- **Pydantic schema drives both extraction and validation:** The same BaseModel that structures the LLM output also validates it. Field descriptions in the schema serve dual duty as extraction prompts — changing one changes both.
- **GEPA requires a working evaluation harness first:** GEPA optimizes prompts by measuring a metric against ground truth. The evaluation harness (exact match scoring with multi-value normalization) must exist and be correct before GEPA can optimize anything.
- **Arize Phoenix must be instrumented before multi-model testing:** Without Phoenix tracing, A/B results are unobservable — just two accuracy numbers with no trace data. Phoenix should be the first observability layer added after the basic pipeline works.
- **German spoken-form normalization is a prerequisite for reliable extraction:** Deepgram's smart_format does NOT normalize German phone numbers or emails (only punctuation/paragraphs for German). The LLM must handle "null zwei null eins Bindestrich drei vier" → "0201-34" internally, or a normalization step must precede extraction. This is the highest-risk accuracy dependency in the pipeline.

---

## MVP Definition

### Launch With (v1)

Minimum viable submission — what's needed to demonstrate the pipeline end-to-end.

- [ ] Deepgram Nova-3 batch transcription of all 30 WAV files — without this there is nothing else
- [ ] LangGraph pipeline: Transcription node → Extraction node → Validation node — structural foundation for everything downstream
- [ ] Pydantic BaseModel with docstring system prompt and field descriptions as extraction prompts — the differentiating design choice
- [ ] LLM extraction of all four fields (first_name, last_name, email, phone_number) with Optional/null semantics — correctness on the core task
- [ ] Evaluation harness: per-field exact-match accuracy against ground truth, with multi-value normalization — required to measure any improvement
- [ ] Arize Phoenix tracing on all nodes — evaluators specifically look for observability; traces must be visible before the technical discussion

### Add After Validation (v1.x)

Add once the basic pipeline produces valid extractions on most recordings.

- [ ] Multi-model A/B testing (at least 2 models: e.g., GPT-4o-mini + Claude Sonnet 4.6) — trigger: baseline pipeline works and Phoenix traces are live
- [ ] GEPA prompt optimization pass — trigger: evaluation harness produces a stable baseline accuracy number; GEPA needs a metric to improve
- [ ] LangGraph retry loop on Pydantic validation failure — trigger: first analysis of failure cases shows repeated format errors (likely for phone/email)
- [ ] Confidence annotation on extracted fields — trigger: after GEPA, surface cases where the optimized prompt is still uncertain

### Future Consideration (v2+)

Defer beyond the challenge scope.

- [ ] Streaming transcription support — no pre-recorded use case exists in this challenge; adds complexity for zero benefit
- [ ] Active learning loop (flag low-confidence extractions for human review) — requires production traffic; overkill for 30-file evaluation
- [ ] Multilingual extension beyond German — out of scope per PROJECT.md; different STT model needed

---

## Feature Prioritization Matrix

| Feature | Evaluator Value | Implementation Cost | Priority |
|---------|----------------|---------------------|----------|
| Deepgram Nova-3 transcription | HIGH | LOW | P1 |
| Pydantic BaseModel extraction schema | HIGH | LOW | P1 |
| LangGraph pipeline structure | HIGH | MEDIUM | P1 |
| Evaluation harness (per-field accuracy) | HIGH | MEDIUM | P1 |
| Arize Phoenix tracing | HIGH | MEDIUM | P1 |
| Multi-value field normalization in eval | HIGH | LOW | P1 |
| Multi-model A/B testing | HIGH | MEDIUM | P2 |
| GEPA prompt optimization | HIGH | MEDIUM | P2 |
| LangGraph retry loop on validation failure | MEDIUM | MEDIUM | P2 |
| German spoken-form handling in extraction prompt | HIGH | LOW | P1 |
| Confidence/uncertainty signaling | MEDIUM | LOW | P2 |
| Prompt version tracking in Phoenix | MEDIUM | LOW | P2 |

**Priority key:**
- P1: Must have for launch — missing these means failing the challenge criteria
- P2: Should have, add when possible — differentiates from a naive submission
- P3: Nice to have, future consideration — no P3 items given the bounded scope

---

## Domain-Specific Accuracy Challenges

These are not features per se, but known accuracy problems this pipeline must address. Each requires intentional design choices, not just "run the LLM."

### German STT Output Format

Deepgram Nova-3's smart_format does NOT format phone numbers or emails for German. Only punctuation and paragraphs are applied. Raw transcript output will contain:

- Phone numbers as spoken digit sequences: "null zwei null eins zwölf sechsundvierzig fünfundvierzig zweiundvierzig"
- Email addresses as spoken words: "Müller ät Beispiel Punkt de" or "Müller at Beispiel Punkt de"
- Names with German pronunciation variants: "Müller", "Mueller", diacritics may or may not appear depending on ASR model behavior

**Required design response:** LLM extraction prompt must explicitly instruct the model to recognize and normalize spoken-form German phone numbers and email addresses. Field descriptions on the Pydantic model should include examples of spoken-form input.

### Multi-Value Ground Truth Fields

The challenge notes some fields accept multiple valid values (e.g., "Lisa Marie" or "Lisa-Marie"). Exact string match without normalization will under-report accuracy.

**Required design response:** Evaluation harness must normalize both prediction and ground truth before comparison: lowercase, strip punctuation, handle hyphenated vs space-separated variants. Consider set membership: prediction is correct if it matches any accepted value in the ground truth alternatives list.

### Hallucination vs Null

LLMs tend to generate plausible values rather than return null when information is absent or unclear. A confidently wrong extraction is worse than an honest null for downstream use.

**Required design response:** Pydantic field descriptions must explicitly instruct the model to return null when the information is not present in the transcript. Evaluate null precision separately: a null prediction when ground truth is null is correct; a hallucinated value when ground truth is null is a false positive.

---

## Competitor Feature Analysis

The "competitors" here are other ways one could approach this challenge — useful to show awareness of alternatives and the rationale for the chosen approach.

| Feature | Naive Approach | Classical NER Approach | Chosen Approach |
|---------|---------------|------------------------|-----------------|
| Extraction method | Direct regex on transcript | spaCy German NER pipeline | LLM with Pydantic-described schema |
| Handles spoken-form input | No — regex fails on German digit words | Partially — trained on written text, not ASR output | Yes — LLM handles language variation naturally |
| Field-level prompt control | None | Requires labeled training data per entity type | Field descriptions in Pydantic model per field |
| Prompt iteration speed | Manual regex editing | Retraining required | Schema edit → instant, GEPA → automated |
| Observability | None | None | Arize Phoenix spans per run |
| Multi-model comparison | N/A | N/A | Swappable LLM node in LangGraph |
| Accuracy on small dataset | Low | Low (needs large labeled corpus) | High (few-shot + GEPA optimization) |

---

## Sources

- [Deepgram Smart Format Documentation](https://developers.deepgram.com/docs/smart-format) — confirms German smart_format limited to punctuation/paragraphs only, not phone/email formatting (HIGH confidence, official docs)
- [Deepgram Nova-3 German Expansion](https://deepgram.com/learn/deepgram-expands-nova-3-with-german-dutch-swedish-and-danish-support) — German monolingual model available, up to 11.4% WER improvement (HIGH confidence, official announcement)
- [DSPy GEPA Structured Extraction Tutorial](https://dspy.ai/tutorials/gepa_facilitysupportanalyzer/) — 20+ percentage point improvement on enterprise structured extraction with 34-example dataset (HIGH confidence, official DSPy docs)
- [GEPA Research Paper — ICLR 2026 Oral](https://arxiv.org/abs/2507.19457) — outperforms GRPO by 6% avg, MIPROv2 by 10%+; uses Pareto frontier of prompt candidates (HIGH confidence, peer-reviewed)
- [LangGraph Extraction with Retries](https://langchain-ai.github.io/langgraph/tutorials/extraction/retries/) — official pattern for structured extraction with validation retry loops (HIGH confidence, official docs)
- [Arize Phoenix GitHub](https://github.com/Arize-ai/phoenix) — OpenTelemetry-based, LangGraph auto-instrumentation, prompt management, open-source self-hostable (HIGH confidence, official source)
- [NER Evaluation Metrics — Entity Level](https://www.davidsbatista.net/blog/2018/05/09/Named_Entity_Evaluation/) — strict vs partial match, precision/recall/F1 at entity level vs token level (MEDIUM confidence, well-cited practitioner reference)
- [Information Extraction from Conversation Transcripts: Neuro-Symbolic vs. LLM](https://arxiv.org/html/2510.12023) — LLMs outperform classical NER for IE from noisy speech transcripts (MEDIUM confidence, arXiv 2025)
- [German Phone Number Normalization](https://github.com/telekom/phonenumber-normalizer) — Telekom's library for German phone number E164 normalization; confirms complexity of German number formats (MEDIUM confidence, official Deutsche Telekom open-source)
- [smart_format German limitation — Deepgram community discussion](https://github.com/orgs/deepgram/discussions/541) — confirms smart_format numerals not supported for German as of Nova-2 era; Nova-3 docs confirm same limitation (MEDIUM confidence, verified against official docs)

---

*Feature research for: German audio entity extraction pipeline (phonebot challenge)*
*Researched: 2026-03-26*
