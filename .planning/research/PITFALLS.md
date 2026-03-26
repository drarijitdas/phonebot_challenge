# Pitfalls Research

**Domain:** German audio entity extraction pipeline (ASR + LLM structured extraction)
**Researched:** 2026-03-26
**Confidence:** HIGH (stack-specific findings from official docs and community issues) / MEDIUM (German ASR error patterns from research literature)

---

## Critical Pitfalls

### Pitfall 1: Treating smart_format as a Reliable Entity Normalizer for German

**What goes wrong:**
`smart_format=true` was designed with English-first coverage. For German audio, the feature applies "all available formatters for that language" — but Deepgram does not document which formatters are active for German, and email/phone formatting behavior differs from English. In English, smart_format reliably produces `user@example.com` from a spelled-out address; in German, the behavior is undocumented and inconsistently tested. Relying on it means the LLM receives raw spoken tokens ("mueller at example punkt de") instead of a normalized email string — and the LLM then has to perform normalization in addition to extraction.

**Why it happens:**
Developers see "smart_format detects emails and phone numbers" in Deepgram marketing copy (which is written for English) and assume German works identically. The API accepts the parameter without error regardless of language.

**How to avoid:**
- Test `smart_format=true` against all 30 recordings and log the raw transcript for every call.
- Implement a post-transcription normalization layer that handles German spoken forms regardless of whether smart_format fires: `"punkt"` → `.`, `"at"` or `"ät"` → `@`, `"Bindestrich"` → `-`, `"Unterstrich"` → `_`.
- Treat smart_format output as a best-effort hint, not a guarantee. The LLM prompt must explicitly instruct handling of both normalized (`user@example.com`) and un-normalized (`user at example punkt de`) email forms.

**Warning signs:**
- Transcripts contain the literal words "punkt", "at", "Klammeraffe", or "Unterstrich" rather than punctuation characters.
- Phone numbers appear as digit words ("null neun null...") rather than numeric strings.
- Email fields extracted by the LLM have low accuracy on the first pass.

**Phase to address:** Transcription phase (Phase 1) — verify smart_format behavior before building the extraction layer on top of it.

---

### Pitfall 2: International Names Transcribed Phonetically into German Sound Patterns

**What goes wrong:**
Nova-3 is trained predominantly on German speech corpora. When a caller with a non-German name (García, O'Brien, Tanaka, Kowalski) spells or pronounces their name, the ASR forces it into the closest German phonetic equivalent. Examples:
- "García" → "Garzia" or "Garsia"
- "O'Brien" → "O Brien" (apostrophe lost) or "Obrien" (merged)
- "Tanaka" → "Tanaka" (often fine) but accent marks and unusual clusters can produce "Tannaka" or "Tanacker"
- Names with `ñ`, `ç`, `ø` will consistently lose the diacritic

This produces a transcript that is phonetically plausible in German but orthographically wrong. The LLM then extracts the wrong spelling as if it were ground truth.

**Why it happens:**
ASR models resolve acoustic ambiguity using a language model trained on native-language text. Foreign proper nouns have no reference in German text corpora, so the decoder picks the highest-probability German near-homophone.

**How to avoid:**
- Use Deepgram's keyterm prompting feature (Nova-3 specific) to pre-supply caller names if known from context (e.g., CRM lookup by phone number). Even without prior knowledge, the feature supports up to 100 keyterms — a list of expected name variants can be injected per-call.
- In the LLM prompt, explicitly state: "The caller may have a non-German name. Extract the name as spelled or spoken, not as a German word. If the name was spelled out letter by letter, reconstruct the spelling." Include examples in the prompt.
- In the evaluation harness, normalize comparison by checking phonetic similarity (using `jellyfish` Metaphone or Soundex) in addition to exact string match for name fields.

**Warning signs:**
- Ground truth contains names with non-ASCII characters (`é`, `ñ`, `ç`) but transcripts never do.
- The LLM produces German-looking names for obviously non-German callers.
- Name field accuracy is systematically lower than email/phone accuracy.

**Phase to address:** Transcription phase (Phase 1) for keyterm setup; extraction prompt design (Phase 2) for LLM instruction; evaluation phase (Phase 3) for phonetic matching fallback.

---

### Pitfall 3: German Phone Number Format Ambiguity in Extraction

**What goes wrong:**
German phone numbers have three valid spoken/written forms:
- International: `+49 30 12345678`
- National with leading zero: `030 12345678`
- Mixed: `+49 (0)30 12345678`

When a caller speaks their number, they may say "null dreißig..." (national) or "plus neun und vierzig..." (international). smart_format may or may not normalize this. The LLM may extract `+4930 12345678`, `030 12345678`, or `+49 30 12345678` — all representing the same number. If the ground truth stores one canonical form and the extraction produces another, exact-match evaluation will mark a correct extraction as wrong.

Additionally, Germany uses an open numbering plan: area codes range from 2 to 5 digits, making it impossible to parse boundaries from the digit string alone without a reference database.

**Why it happens:**
Neither the transcription nor the LLM knows which canonical form the ground truth expects. Without an explicit normalization target in the prompt and evaluation harness, each component makes independent format choices.

**How to avoid:**
- Inspect the ground truth file to determine which format it uses. Write the LLM field description to produce exactly that format.
- Regardless of ground truth format, normalize the extracted number using `phonenumbers` library (Google's libphonenumber port for Python) before comparison: `phonenumbers.parse(raw, "DE")` → `phonenumbers.format_number(parsed, PhoneNumberFormat.E164)`.
- Apply the same normalization to ground truth values before comparison so evaluation is format-agnostic.

**Warning signs:**
- Phone number accuracy is low even when the number sounds correct in the audio.
- Different recordings extract numbers in different formats despite identical audio patterns.
- Ground truth shows `+49...` but extractions show `0...` (or vice versa).

**Phase to address:** Extraction prompt design (Phase 2) for canonical format instruction; evaluation harness (Phase 3) for normalized comparison.

---

### Pitfall 4: LLM Confabulates Fields Not Present in the Transcript

**What goes wrong:**
When the transcript is ambiguous, partial, or the ASR badly garbled a section, an LLM instructed to extract `first_name`, `last_name`, `email`, `phone_number` will often produce a plausible-sounding value rather than `null`. This is especially dangerous for names: if the caller's last name is inaudible, the LLM may "complete" it from context (German common surnames, names heard earlier in the conversation, or phonetically similar words).

For structured Pydantic output, this manifests as every field being populated with seemingly valid data, making it hard to detect without comparing against ground truth.

**Why it happens:**
LLMs are trained to be helpful and produce complete outputs. Without explicit instruction to return `null` for missing/uncertain fields, the model defaults to best-guess completion. Pydantic fields without `Optional[str] = None` typing will also pressure the model to fill every field.

**How to avoid:**
- Type all Pydantic fields as `Optional[str] = None`.
- Add explicit instruction in both the system prompt (docstring) and per-field descriptions: "If this field is not clearly stated in the transcript, return null. Do not infer or guess."
- Add a confidence field or a `reasoning` field (stripped before output) so the model's chain-of-thought reveals uncertainty before committing to a value.
- Set `temperature=0` on extraction models to minimize creative completion.

**Warning signs:**
- Zero `null` values in any extraction run across 30 calls (statistically implausible if any recordings have bad audio).
- Last names that look like common German words or surnames but don't appear in the transcript text.
- Email domains that are generic (`gmail.com`, `web.de`) when the actual domain wasn't clearly stated.

**Phase to address:** Extraction prompt design (Phase 2) — build `null`-safety in from the first prompt draft.

---

### Pitfall 5: GEPA Optimization Requires a Correctly Wired Evaluation Function

**What goes wrong:**
GEPA optimizes against a metric returned by a user-defined evaluation function. If that function is too lenient (partial credit for wrong format), too strict (exact string match penalizes `+49 30 123` vs `+4930123`), or silently errors on edge cases, GEPA converges on prompts that game the metric rather than improving real extraction quality. Since GEPA is a relatively new tool (ICLR 2026 acceptance), there is limited production experience and sparse documentation on integration gotchas.

A secondary issue: GEPA has no native LangGraph adapter. The documented integrations are DSPy, MLflow, Comet ML, Pydantic AI, and OpenAI. Connecting it to a LangGraph pipeline requires implementing the `GEPAAdapter` interface manually.

**Why it happens:**
Developers focus on getting GEPA to run at all and write a quick evaluation function. The evaluation function is the most critical component but receives the least design attention. LangGraph integration requires custom adapter code that has no reference implementation to copy from.

**How to avoid:**
- Design the evaluation function before writing GEPA integration code. It must: normalize both predicted and ground truth values (phone format, case, whitespace), handle `null` correctly (predicting `null` for a field that is `null` in ground truth is a true positive, not a miss), and return a score on [0, 1] that correlates with what "correct" actually means.
- Use per-field accuracy scores (not a single composite score) so GEPA can diagnose which field type is failing.
- Write the LangGraph-to-GEPA adapter as a thin wrapper: the adapter calls the LangGraph graph with a given prompt configuration and returns the evaluation score. Keep this adapter stateless and testable independently of LangGraph.
- Budget 100–500 evaluation calls for GEPA runs; with 30 recordings this means 3–17 full pipeline passes per GEPA iteration — validate API cost before running.

**Warning signs:**
- GEPA reports improving scores but manual inspection shows no improvement in name/email extraction.
- GEPA adapter raises errors on calls where the LLM returned `null` fields.
- Optimization plateau reached after very few iterations (evaluation function ceiling, not genuine convergence).

**Phase to address:** Prompt optimization phase (Phase 4) — but evaluation function must be designed during Phase 3 (evaluation harness) since GEPA reuses it.

---

### Pitfall 6: Umlaut and Special Character Round-Tripping Between ASR, LLM, and JSON

**What goes wrong:**
German text involves `ä`, `ö`, `ü`, `ß`. Three distinct failure points exist in the pipeline:
1. **ASR output**: Nova-3 may transcribe "Müller" correctly with the umlaut, or it may produce "Mueller" (expanded form) or "Muller" (stripped) depending on training data distribution for that name.
2. **LLM processing**: Most modern LLMs handle Unicode correctly, but if the LLM prompt or system is misconfigured for encoding, umlauts can become mojibake (`\u00fc` rendered literally or as `?`).
3. **Pydantic/JSON serialization**: Python's `json.dumps` with `ensure_ascii=True` (the default) will escape umlauts as `\u00fc`. If ground truth comparison uses string equality on JSON-serialized values, `"M\u00fcller"` != `"Müller"` despite representing the same string.

**Why it happens:**
Each component handles encoding independently. Developers test with ASCII-safe names in development, then encounter encoding issues with real German names only in final evaluation.

**How to avoid:**
- Always use `json.dumps(..., ensure_ascii=False)` when serializing output.
- Normalize all string comparisons in the evaluation harness using `unicodedata.normalize("NFC", value)` on both predicted and ground truth values before comparison.
- In the LLM prompt, explicitly note: "Preserve German special characters (ä, ö, ü, ß) exactly as they appear in the transcript."
- Test with a recording known to contain an umlaut name (e.g., "Jürgen") before declaring the pipeline functional.

**Warning signs:**
- Extracted names contain backslash-u sequences (`\u00e4`) in stored output.
- Evaluation reports near-zero accuracy for German names with umlauts while ASCII names score correctly.
- Names like "Müller" appear as "Muller" in all extractions.

**Phase to address:** Transcription phase (Phase 1) for ASR output verification; extraction output (Phase 2) for serialization config; evaluation phase (Phase 3) for normalization.

---

### Pitfall 7: Evaluation Harness Uses Exact String Match Without Handling Multiple Acceptable Values

**What goes wrong:**
The project notes that some ground truth fields have multiple acceptable values (e.g., "Lisa Marie" or "Lisa-Marie"). An exact-match evaluator will mark "Lisa Marie" as wrong when ground truth is `["Lisa-Marie", "Lisa Marie"]` if the comparison logic doesn't check all acceptable variants. This silently suppresses accuracy metrics, making the pipeline look worse than it is — and causes GEPA to optimize toward the wrong target.

**Why it happens:**
Developers write the simplest possible comparison: `predicted == ground_truth`. Handling list-valued ground truth requires reading the ground truth schema carefully and writing set-membership or any-match logic.

**How to avoid:**
- Inspect `data/ground_truth.json` before writing a single line of evaluation code. Determine the exact schema: is `acceptable_values` a list field, or is it a separate `aliases` field?
- Write a `matches_ground_truth(predicted, ground_truth_entry)` function that:
  - Handles scalar ground truth (exact match after normalization)
  - Handles list ground truth (any-match after normalization)
  - Handles `null` ground truth (predicted `null` is correct; any non-null value is wrong)
- Apply this function consistently in both the standalone evaluation harness and the GEPA evaluation function.

**Warning signs:**
- Accuracy metrics are surprisingly low for fields that sound correct when listening to recordings.
- Manual spot-checking reveals correct extractions being scored as wrong.
- The evaluation code uses `==` directly on ground truth values without checking their type.

**Phase to address:** Evaluation harness (Phase 3) — design this before running any model comparisons.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Exact string match in evaluation | Fast to implement | Penalizes correct extractions with format differences; breaks GEPA optimization | Never — normalization is cheap |
| Single system prompt for all fields | Simpler prompt management | Phone number extraction prompts need different instructions than name extraction | Never — use Pydantic field descriptions per-field |
| Trusting smart_format for all normalization | Less post-processing code | Undocumented German behavior causes silent failures | Never for production; acceptable as experiment baseline only |
| Hardcoding `temperature=0` without testing | Deterministic output | Some models require slight temperature for valid JSON generation | Acceptable as default; validate per-model |
| Skipping `Optional[str]` typing on Pydantic fields | Fewer null checks downstream | LLM pressured to fill fields it shouldn't; no null signal for missing data | Never |
| One Arize Phoenix project for all A/B runs | Less setup overhead | Can't cleanly compare model runs if traces are commingled | Acceptable for early runs; separate projects for final comparison |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Deepgram Nova-3 + German | Using `model=nova-3` assuming it equals `nova-3-german`; the base model may select the wrong language variant | Explicitly pass `language="de"` parameter to force German language model |
| Deepgram keyterms + German | Keyterms for non-English languages were in limited rollout; Nova-3 keyterm support for German may require the `nova-3` (not `nova-3-multi`) endpoint | Test keyterm behavior with a known name and verify it appears correctly before relying on it |
| Arize Phoenix + LangGraph | Instrumentor initializes but traces show span ID `0000000000000000` if Phoenix is started after LangGraph's event loop is already running | Initialize Phoenix and call `LangChainInstrumentor().instrument()` before constructing the LangGraph graph |
| GEPA + LangGraph | No built-in adapter exists; developers try to call GEPA directly on a LangGraph compiled graph | Implement `GEPAAdapter.evaluate()` as a function that invokes `graph.invoke({"transcript": t})` and returns a float score |
| Pydantic structured output + open-source models | Open-source models (Mistral, Llama) often ignore JSON schema constraints; `with_structured_output()` fails silently with some providers | Test each model's schema adherence before including it in A/B comparison; use `instructor` library as fallback if native structured output is unreliable |
| `phonenumbers` library + spoken German numbers | `phonenumbers.parse("null dreißig...")` fails — the library expects digit strings, not spoken words | Apply spoken-number-to-digit normalization before passing to phonenumbers; Deepgram smart_format should handle this, but verify |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Sequential per-recording API calls to Deepgram | 30 recordings take 30x the time of one | Use `asyncio.gather` or `concurrent.futures.ThreadPoolExecutor` for batch transcription | Immediately — even 30 calls at ~5s each is 150s sequential vs ~10s parallel |
| Regenerating all transcriptions on every run | Slow iteration during extraction/evaluation development | Cache transcription results to disk (JSON files per recording); only re-transcribe when forced | On the second run — any iteration loop will re-pay the transcription cost |
| Running GEPA with full 30-recording eval set | 500 GEPA iterations × 30 recordings × LLM call = 15,000 API calls | Use a representative 10–15 recording training split for GEPA; validate on held-out set | First GEPA run — costs spiral immediately |
| Storing full LangGraph state including transcript text | State bloat in checkpointer; large traces in Phoenix | Store transcript as a reference key, not inline in state; load from cache when needed | At Arize Phoenix trace storage limits or local disk limits |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Logging full transcripts to Arize Phoenix without redaction | PII (caller names, emails, phone numbers) persists in observability platform indefinitely | Tag spans with metadata (call ID, model version) but redact or hash PII fields in logged attributes; use Phoenix's span attribute filtering |
| Storing API keys in code or config files committed to repo | Credential exposure | Use environment variables + `.env` file listed in `.gitignore`; validate `.env.example` is committed instead |
| Passing raw ground truth (with real caller data) as examples in LLM prompts | Ground truth PII sent to external LLM providers | Ground truth is synthetic challenge data — document this assumption; if real PII is ever used, mask before sending to LLM |

---

## "Looks Done But Isn't" Checklist

- [ ] **Transcription pipeline:** Verify smart_format output for umlaut names specifically — not just that the API returned 200 OK.
- [ ] **Email extraction:** Test with a recording where the email uses a non-obvious German domain (`web.de`, `gmx.de`, `t-online.de`) spelled out in German; verify the reconstruction logic handles all spoken domain components.
- [ ] **Phone extraction:** Confirm the pipeline handles both `+49` prefix and `0` prefix forms; run `phonenumbers.parse()` on every extracted phone to validate it parses without error.
- [ ] **Null handling:** Confirm at least one recording produces a `null` for one field (either audio is unclear or field not mentioned) and that evaluation correctly scores this as correct, not as a miss.
- [ ] **Multi-model support:** Run extraction with at least two models before claiming A/B capability; verify both produce valid Pydantic output, not just that the second model is wired in.
- [ ] **GEPA optimization:** Verify GEPA actually changes the prompt between iterations (not stuck at initial); run baseline score, optimized score, and verify they differ.
- [ ] **Arize Phoenix traces:** Open the Phoenix UI and confirm you can see individual node spans within a LangGraph trace, not just a single root span.
- [ ] **Evaluation harness:** Run the evaluator on a deliberately wrong extraction and confirm it scores below 1.0; run it on a known-correct extraction and confirm it scores 1.0.
- [ ] **Ground truth schema:** Handle the multiple-acceptable-values case before running any real evaluation; spot-check 3–5 ground truth entries manually.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| smart_format failed to normalize emails/phones | LOW | Add post-transcription normalization function; re-run extraction only (no re-transcription needed if transcripts are cached) |
| Name transcribed incorrectly by ASR | MEDIUM | Add keyterms to Deepgram request for known name patterns; may require re-transcription of affected recordings |
| GEPA optimizing against wrong metric | MEDIUM | Rewrite evaluation function; restart GEPA optimization run; previous GEPA iterations are discarded |
| LLM confabulating missing fields | LOW | Add null-forcing instruction to prompt; re-run extraction only |
| Phone number format mismatch in evaluation | LOW | Add `phonenumbers` normalization to evaluation harness; no re-extraction needed |
| Umlaut encoding corrupted in output | LOW | Fix `ensure_ascii=False` and NFC normalization; re-run extraction only |
| GEPA/LangGraph adapter broken | HIGH | Requires custom adapter implementation; no reference code exists — budget 1–2 days for investigation and testing |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| smart_format unreliable for German | Phase 1: Transcription | Manual review of 5 transcripts for email/phone normalization before proceeding |
| International names transcribed phonetically | Phase 1 (keyterms) + Phase 2 (prompt) | Name field accuracy on recordings with non-German names specifically |
| German phone number format ambiguity | Phase 2: Extraction prompts + Phase 3: Evaluation | `phonenumbers.parse()` succeeds on all extracted phone numbers |
| LLM confabulates missing fields | Phase 2: Extraction prompts | At least one recording returns a `null` field; confirm it's scored correctly |
| GEPA needs correct evaluation function | Phase 3: Evaluation harness (design), Phase 4: Optimization (run) | GEPA score improves across iterations on held-out split |
| Umlaut round-trip encoding | Phase 1 (verify) + Phase 2 (serialization) | Jürgen/Müller test case passes end-to-end |
| Exact match ignores multiple acceptable values | Phase 3: Evaluation harness | Evaluator correctly scores "Lisa Marie" as correct when ground truth is `["Lisa-Marie", "Lisa Marie"]` |
| Arize Phoenix span context not propagating | Phase 2: Observability setup | Phoenix UI shows per-node spans within a single trace for one complete pipeline run |

---

## Sources

- Deepgram Smart Format docs: https://developers.deepgram.com/docs/smart-format
- Deepgram Keyterm Prompting docs: https://developers.deepgram.com/docs/keyterm
- Deepgram community discussion — smart_format numeral edge case: https://github.com/orgs/deepgram/discussions/1168
- Deepgram community discussion — keyterms vs keywords best practices: https://github.com/orgs/deepgram/discussions/1118
- Deepgram community discussion — Nova-3 language-specific issues: https://github.com/orgs/deepgram/discussions/1192
- GEPA GitHub repository (integration requirements): https://github.com/gepa-ai/gepa
- GEPA DSPy documentation: https://dspy.ai/api/optimizers/GEPA/overview/
- Arize Phoenix LangGraph tracing docs: https://arize.com/docs/phoenix/integrations/python/langgraph/langgraph-tracing
- Arize Phoenix span context discussion: https://github.com/Arize-ai/phoenix/discussions/4800
- German phone numbering plan (variable-length area codes): https://en.wikipedia.org/wiki/Telephone_numbers_in_Germany
- Telekom phonenumber-normalizer (German E.164): https://github.com/telekom/phonenumber-normalizer
- ASR in German: A Detailed Error Analysis (Wirth & Peinl, 2022): https://arxiv.org/abs/2204.05617
- LLM normalization best practices for extraction outputs: https://llms.reducto.ai/normalization-for-llms
- Microsoft Q&A — punctuation/symbol issues in Dutch & German STT: https://learn.microsoft.com/en-us/answers/questions/5601802/how-to-fix-issues-with-punctuations-symbols-number

---
*Pitfalls research for: German audio entity extraction pipeline*
*Researched: 2026-03-26*
