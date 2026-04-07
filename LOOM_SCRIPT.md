# Loom Video Script — Phonebot Challenge Demo (~3-4 min)

---

## 1. Problem & What I Built (30s)

**Show:** README.md in editor

- "The challenge: extract caller info — first name, last name, email, phone number — from 30 German phone bot recordings."
- "All recordings are in German. Callers spell out emails letter by letter, say phone digits verbally — 'plus vier neun eins sieben zwei...' — so the LLM has to reconstruct structured data from spoken form."
- "I built a full production-grade extraction pipeline with two pipeline variants, automated prompt optimization, observability, and knowledge grounding."

---

## 2. Architecture Walkthrough (40s)

**Show:** README mermaid diagram (scroll to "System Overview"), then briefly open `src/phonebot/pipeline/orchestrator.py`

- "Here's the full system. Audio goes through Deepgram Nova-3 for German transcription with diarization. Transcripts are cached as JSON so we never re-call the API."
- "The orchestrator is a LangGraph StateGraph. First, a zero-cost rule-based classifier scores each transcript on 7 difficulty signals — length, foreign names, spelling indicators, Deepgram confidence — and routes it:"
  - "EASY recordings go to V1 — a single LLM call with Pydantic structured output"
  - "HARD recordings go to V2 — an actor-critic loop where a second LLM cross-checks each field against the transcript"
- "After extraction, rule-based post-processing normalizes phone numbers to E.164, lowercases emails, applies Unicode NFC to names — all deterministic, zero latency."
- "Prompts are externalized as JSON files, not hardcoded. The Pydantic model is built dynamically from the prompt file — so I can swap prompts at runtime without touching code."

---

## 3. Results & What Actor-Critic Fixes (40s)

**Show:** Terminal output from `uv run python run.py --final` (or a saved screenshot), then the accuracy table from README

- "V1 with the baseline prompt: 83% overall. V1 with the GEPA-optimized prompt: 93%. That's the best result."
- "The actor-critic V2 pipeline hits 89%. It's lower overall because it ran fewer GEPA iterations, but it catches errors V1 can't:"
  - "Letter/digit confusion in emails — the LLM writes `julia.schr0der` with a zero instead of an O. The critic spots this because it checks against the transcript where they spelled 'O wie Otto'."
  - "Phonetic mismatches in international names — 'Chen' transcribed as 'Xen', 'Ahmed' as 'Armet'. The critic cross-references the transcript and catches these."
- "The remaining 8 errors are name spelling variants — Kowalsky vs Kowalski — where Deepgram's phonetic output is ambiguous. That's at the ASR boundary."
- "Phone number extraction: 100% across all configurations."

---

## 4. Phoenix Observability (50s)

**Show:** Phoenix UI at localhost:6006 — this is the main demo section

- "Every pipeline run produces OTEL traces in Phoenix. Let me show you."

**Click into a trace (e.g., call_07):**
- "Each recording gets a full trace — transcribe, extract, validate, postprocess. For V2 recordings you also see critic_evaluate and actor_refine spans."
- "I can see the exact prompt sent to Claude, the structured output response, token counts, and latency per span."

**Show the project view / trace list:**
- "All runs are tagged with session ID, pipeline version, and prompt version. So I can filter by 'v1 pipeline, v2 prompt' and see exactly those traces."

**Mention (don't need to show all):**
- "Beyond traces, the system tracks:"
  - "Latency per node with SLA budgets — 30s per recording, extract gets 10s. Violations are flagged."
  - "Cost per recording — Claude Sonnet at $3/M input tokens, tracked per node."
  - "Quality alerts fire if accuracy drops below 80%, per-field below 60%, or escalation rate exceeds 20%."
  - "A prompt registry hashes prompt content with SHA256 and maps each hash to its accuracy — so I always know which exact prompt produced which score."

---

## 5. A/B Testing & Prompt Optimization (30s)

**Show:** Terminal output from `uv run python compare.py`, then briefly mention `optimize.py`

- "For A/B testing: `compare.py` loads all result files, computes per-field accuracy for each configuration, and shows a diff table — exactly which recordings each variant gets right or wrong. The winner here is `v1 pipeline + v2 prompt (GEPA)` at 92%."
- "For prompt optimization: GEPA treats the prompt as 5 evolvable slots — system prompt plus 4 field descriptions. It runs the pipeline on 20 training recordings, a reflection LLM analyzes failures and proposes improvements, then validates on 10 held-out recordings."
- "Field weights are inverse-accuracy — email had the lowest baseline at 67%, so it gets 47% of the optimization budget. This is how email accuracy jumped from 67% to 90%."

---

## 6. Knowledge Layer & Production Readiness (30s)

**Show:** Briefly show `knowledge/example_store.py` and `pipeline/escalation.py`

- "Two knowledge layers:"
  - "Pre-extraction: ChromaDB stores all 30 transcript-to-ground-truth pairs. For HARD recordings, it retrieves the 2 most similar solved examples as few-shot context. This is what helps with foreign names like 'Garcia' that Deepgram transcribes as 'Gassia'."
  - "Post-extraction: fuzzy name matching against a German name dictionary via rapidfuzz, phone validation via the phonenumbers library, email domain checking. These adjust confidence scores — they never override the LLM."
- "Low-confidence results (< 0.5) or recordings with more than 2 flagged fields get routed to an escalation queue for human review."
- "The system also has regression detection — each run is compared against a saved baseline with 2% tolerance per field. If any field drops, it flags it."

---

## 7. Wrap-up (10s)

- "To summarize: two pipeline variants with intelligent routing, GEPA-optimized prompts, full OTEL observability in Phoenix, A/B testing, knowledge grounding, and production-ready monitoring. 93% overall accuracy on 30 German recordings. Thanks for watching."

---

## Pre-Recording Checklist

- [ ] Phoenix running (`uv run phoenix serve` or it auto-starts with `run.py`)
- [ ] Have a completed run's traces in Phoenix (run `uv run python run.py --final` beforehand)
- [ ] Terminal ready with `compare.py` output (run beforehand and keep visible)
- [ ] Editor open to README.md (for architecture diagram) and `orchestrator.py`
- [ ] Phoenix UI open at http://localhost:6006 with a trace already clicked into

## Screen Layout Suggestion

- Left half: Editor / Terminal
- Right half: Phoenix UI (switch as needed)
- Start on README, move to terminal for results, then Phoenix for traces, back to terminal for compare.py

## Key Numbers to Remember

| Metric | Value |
|--------|-------|
| Best overall accuracy | 93% (V1 + GEPA v2 prompt) |
| V2 actor-critic accuracy | 89% |
| Phone accuracy | 100% (all configs) |
| Email improvement | 67% -> 90% (GEPA) |
| Recordings | 30 (German) |
| GEPA iterations | 51 (V1 prompt) |
| Remaining errors | 8 name spelling variants |
| SLA budget | 30s per recording |
