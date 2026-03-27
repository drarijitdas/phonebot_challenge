# Phonebot Audio Entity Extraction Pipeline

## What This Is

A post-processing pipeline that transcribes German AI phone bot recordings and extracts structured caller information (first name, last name, email, phone number). Built as a technical challenge submission demonstrating production-ready AI engineering with observability, prompt optimization, and multi-model A/B testing.

## Core Value

Accurate extraction of caller contact information from German phone bot recordings — every field correct, every time.

## Current Milestone: v1.0 Audio Entity Extraction Pipeline

**Goal:** Build the full end-to-end extraction pipeline with production-ready observability and prompt optimization.

**Target features:**
- Deepgram Nova-3 transcription of German audio recordings
- LangGraph-orchestrated extraction pipeline with structured Pydantic output
- Pydantic BaseModel-based prompting system (docstrings as system prompts, field descriptions as variable-specific prompts)
- Multi-model support (open-source through Claude Sonnet 4.6) for A/B comparison
- GEPA prompt optimization for tuning extraction prompts
- Arize Phoenix integration for observability, tracing, and A/B testing
- Evaluation harness comparing extractions against ground truth

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- [x] Pydantic BaseModel prompting system — Validated in Phase 1: Foundation
- [x] Evaluation against ground truth with per-entity accuracy — Validated in Phase 1: Foundation
- [x] Transcribe 30 German WAV recordings via Deepgram Nova-3 — Validated in Phase 2: Transcription
- [x] Extract first_name, last_name, email, phone_number from transcripts — Validated in Phase 3: Extraction Pipeline (82% baseline)
- [x] LangGraph pipeline orchestration — Validated in Phase 3: Extraction Pipeline
- [x] Arize Phoenix observability and tracing — Validated in Phase 4: Observability (30 traces with span-level visibility)
- [x] Multi-model support for A/B comparison — Validated in Phase 5: Model A/B Testing (Claude + Ollama registry, compare.py with Rich tables, Claude 83% winner)

### Active

<!-- Current scope. Building toward these. -->
- [ ] GEPA prompt optimization

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Real-time/streaming transcription — challenge uses pre-recorded files only
- Web UI or API server — CLI pipeline is sufficient for the challenge
- Multi-language support beyond German — all recordings are German

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

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Deepgram Nova-3 for STT | Strong German support, smart_format for phones/emails, simple API | smart_format does NOT normalize German phone/email — spoken-form only (Phase 2 finding) |
| LangGraph for orchestration | Graph-based pipeline enables modular steps, retries, branching | -- Pending |
| Pydantic BaseModel prompting | Docstrings as system prompts, field descriptions as extraction prompts — self-documenting and type-safe | -- Pending |
| GEPA for prompt optimization | Automated prompt tuning against ground truth | -- Pending |
| Arize Phoenix for observability | Tracing, A/B testing, prompt engineering dashboard | Live — 30 traces with transcribe+extract spans, prompt_version tagging, persistent SQLite (Phase 4) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-27 after Phase 5 (Model A/B Testing) completion — model registry routes claude-*/ollama:* to LangChain backends, compare.py produces Rich comparison tables, Claude Sonnet 4.6 wins at 83% overall accuracy. Phoenix trace tagging pending human visual verification.*
