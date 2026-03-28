# Phase 3: Extraction Pipeline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-27
**Phase:** 03-extraction-pipeline
**Areas discussed:** Prompt strategy for spoken-form, LangGraph node design, Baseline model choice, Results output structure

---

## Prompt Strategy for Spoken-Form

### Q1: How much spoken-form guidance?

| Option | Description | Selected |
|--------|-------------|----------|
| Detailed patterns | Expand field descriptions with specific Deepgram output patterns observed in Phase 2 | ✓ |
| Minimal hints | Keep current CallerInfo descriptions as-is | |
| Few-shot examples | Add 1-2 transcript→extraction examples to the system prompt | |

**User's choice:** Detailed patterns
**Notes:** Grounded in real Deepgram output data from Phase 2.

### Q2: Full transcript or speaker-filtered input?

| Option | Description | Selected |
|--------|-------------|----------|
| Full transcript | Send complete transcript text. Diarization unreliable. | ✓ |
| Attempt speaker filtering | Isolate caller speech using diarization labels | |

**User's choice:** Full transcript
**Notes:** Diarization unreliable per Phase 2 finding.

### Q3: Pattern location — field descriptions or docstring?

| Option | Description | Selected |
|--------|-------------|----------|
| Field descriptions | Each field's description gets its own specific patterns | ✓ |
| Class docstring section | General patterns block in CallerInfo docstring | |
| Both | Docstring gets general context, field descriptions get specifics | |

**User's choice:** Field descriptions
**Notes:** Per Phase 1 D-02/D-11, field descriptions ARE the per-field extraction instructions.

### Q4: Exact Deepgram patterns or general German patterns?

| Option | Description | Selected |
|--------|-------------|----------|
| Exact Deepgram patterns | Reference real output patterns from the 30 transcripts | ✓ |
| General German patterns | Describe German conventions broadly | |
| You decide | Claude picks the right specificity level | |

**User's choice:** Exact Deepgram patterns
**Notes:** Maximally grounded in real data.

### Q5: Foreign name handling?

| Option | Description | Selected |
|--------|-------------|----------|
| Extract as-transcribed | Return what Deepgram produced, don't correct spelling | ✓ |
| Attempt spelling correction | Instruct LLM to infer likely correct spelling | |
| You decide | Claude picks based on ground truth analysis | |

**User's choice:** Extract as-transcribed
**Notes:** Avoids hallucinating corrections. Evaluation normalization handles comparison.

---

## LangGraph Node Design

### Q1: Transcribe node behavior?

| Option | Description | Selected |
|--------|-------------|----------|
| Load from cache | Read cached JSON, fallback to Deepgram API on cache miss | ✓ |
| Always call Deepgram | Always call transcribe module (which checks cache) | |
| Skip transcribe node | Load transcripts before graph, pass as initial state | |

**User's choice:** Load from cache
**Notes:** Fast iteration during development. All 30 already cached.

### Q2: How should extract node call the LLM?

| Option | Description | Selected |
|--------|-------------|----------|
| with_structured_output | LangChain's model.with_structured_output(CallerInfo) | ✓ |
| Raw API + manual parse | Call LLM API directly, parse JSON into CallerInfo manually | |
| You decide | Claude picks best approach for LangGraph integration | |

**User's choice:** with_structured_output
**Notes:** Clean, idiomatic LangChain. Handles Pydantic schema→JSON mode automatically.

### Q3: State scope — one recording or batch?

| Option | Description | Selected |
|--------|-------------|----------|
| One recording per invocation | Graph processes single recording, outer loop iterates 30x | ✓ |
| Batch all 30 | PipelineState holds list of all recordings | |
| You decide | Claude picks based on LangGraph best practices | |

**User's choice:** One recording per invocation
**Notes:** Simpler state, easier debugging, natural per-recording tracing in Phoenix.

### Q4: Separate validate node?

| Option | Description | Selected |
|--------|-------------|----------|
| Inline in extract | with_structured_output handles Pydantic validation | ✓ |
| Separate validate node | Extract returns raw dict, validate node parses CallerInfo | |

**User's choice:** Inline in extract
**Notes:** No separate node needed for Phase 3. Phase 7 adds retry logic.

---

## Baseline Model Choice

### Q1: Which LLM for Phase 3 baseline?

| Option | Description | Selected |
|--------|-------------|----------|
| Claude Sonnet 4.6 only | Use CLI default, strong structured output and German support | ✓ |
| Open-source model only | Start with Llama/Mistral for lower baseline | |
| Both now | Run Claude + open-source, gets A/B data early | |

**User's choice:** Claude Sonnet 4.6 only
**Notes:** Phase 5 adds open-source comparison formally.

---

## Results Output Structure

### Q1: What should results.json contain?

| Option | Description | Selected |
|--------|-------------|----------|
| Extractions + metadata | Each entry: {id, caller_info, model, timestamp} + run metadata | ✓ |
| Minimal extractions only | Just [{id, caller_info}] | |
| Rich with transcript | Include raw transcript text alongside extraction | |

**User's choice:** Extractions + metadata
**Notes:** Useful for Phase 5 A/B comparison.

### Q2: Auto-evaluate or separate step?

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-evaluate after extraction | run.py extracts all 30, then calls compute_metrics, prints Rich table | ✓ |
| Separate evaluation command | run.py only extracts, evaluation run separately | |

**User's choice:** Auto-evaluate after extraction
**Notes:** Single command for full pipeline + results. Matches success criteria.

---

## Claude's Discretion

- Exact LangGraph state schema field names and types
- Async concurrency implementation details for the outer loop
- How to extract transcript text from cached Deepgram JSON structure
- Rich table formatting for the accuracy report
- Error handling for individual recording failures

## Deferred Ideas

None — discussion stayed within phase scope
