# Phonebot Audio Entity Extraction Pipeline

## What This Is

A production-ready pipeline that transcribes German AI phone bot recordings and extracts structured caller information (first name, last name, email, phone number) with 84% accuracy. Features retry-resilient LangGraph extraction, GEPA-optimized prompts, multi-model A/B testing, and full Arize Phoenix observability. Built as a technical challenge submission demonstrating production-ready AI engineering.

## Core Value

Accurate extraction of caller contact information from German phone bot recordings — every field correct, every time.

## Current State

**v1.0 shipped** (2026-03-28) — all 7 phases complete, 22/22 requirements satisfied.

- 4,528 lines of Python across 137 files
- 104 tests passing, 1 skipped (live API gate)
- 84% overall extraction accuracy (90% first_name, 87% last_name, 67% email, 97% phone_number)
- Tech stack: Python 3.13, LangGraph, Pydantic, Deepgram Nova-3, Arize Phoenix, GEPA, Claude Sonnet 4.6

## Requirements

### Validated (v1.0)

- [x] Pydantic BaseModel prompting system — v1.0
- [x] Evaluation against ground truth with per-entity accuracy — v1.0
- [x] Transcribe 30 German WAV recordings via Deepgram Nova-3 — v1.0
- [x] Extract first_name, last_name, email, phone_number from transcripts — v1.0 (82% baseline)
- [x] LangGraph pipeline orchestration — v1.0
- [x] Arize Phoenix observability and tracing — v1.0
- [x] Multi-model support for A/B comparison — v1.0 (Claude 83% vs Ollama)
- [x] GEPA prompt optimization — v1.0 (+2% via cross-reference spelling)
- [x] Retry loop for validation failures — v1.0 (max 2 retries)
- [x] Confidence flagging — v1.0 (threshold 0.7)
- [x] Final submission package — v1.0 (--final flag)

### Active

(none — no next milestone planned)

### Out of Scope

- Real-time/streaming transcription — challenge uses pre-recorded files only
- Web UI or API server — CLI pipeline is sufficient for the challenge
- Multi-language support beyond German — all recordings are German
- Fine-tuning an LLM on 30 recordings — overfitting risk
- Ensemble voting across models — marginal benefit with 30 files

## Context

- Technical challenge for Phonebot AI Engineer position
- 30 WAV audio files in `data/recordings/` (call_01.wav through call_30.wav)
- Ground truth in `data/ground_truth.json` with expected extractions per recording
- Some fields accept multiple values (e.g., "Lisa Marie" or "Lisa-Marie")
- Recordings are in German; German proficiency not required
- Evaluated on: accuracy, AI engineering approach, future-proofing/controllability, code quality
- Must be prepared for 1-hour technical discussion

## Constraints

- **Tech stack**: Python, LangGraph, Pydantic, Deepgram Nova-3, Arize Phoenix, GEPA
- **LLM range**: Open-source models through Claude Sonnet 4.6
- **Data**: 30 fixed recordings with known ground truth
- **Audio format**: WAV files, German language

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Deepgram Nova-3 for STT | Strong German support, smart_format, simple API | smart_format does NOT normalize German phone/email — spoken-form only |
| LangGraph for orchestration | Graph-based pipeline enables modular steps, retries, branching | Validated — START->transcribe->extract->validate->(END\|extract) topology |
| Pydantic BaseModel prompting | Docstrings as system prompts, field descriptions as extraction prompts | Validated — self-documenting, type-safe, GEPA-optimizable |
| GEPA for prompt optimization | Automated prompt tuning against ground truth | Validated — +2% accuracy, +10% last_name via cross-reference spelling |
| Arize Phoenix for observability | Tracing, A/B testing, prompt engineering dashboard | Validated — 30 traces with span-level visibility, persistent SQLite |
| Claude Sonnet 4.6 as primary model | Best accuracy in A/B test (83% vs Ollama) | Validated — locked as --final default |
| Retry with error context, not previous output | Prevents error amplification on retry (D-02) | Validated — clean re-extraction on each retry |
| Confidence threshold 0.7 | Balance between flagging noise and catching uncertain extractions | Validated — compute_flagged_fields < 0.7 |

---
*Last updated: 2026-03-28 after v1.0 milestone completion*
