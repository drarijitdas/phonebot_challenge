---
phase: 02-transcription
plan: "01"
subsystem: pipeline/transcribe
tags: [transcription, deepgram, asyncio, caching, tdd]
dependency_graph:
  requires: []
  provides: [transcription-module, transcript-cache-layer]
  affects: [02-02-live-transcription]
tech_stack:
  added: [deepgram-sdk==6.1.0, anyio, httpx, httpcore, websockets]
  patterns: [async-semaphore-concurrency, json-cache-layer, tdd-red-green]
key_files:
  created:
    - src/phonebot/pipeline/transcribe.py
    - tests/test_transcribe.py
  modified:
    - pyproject.toml
    - uv.lock
    - .env.example
decisions:
  - "deepgram-sdk v6 (Fern-generated) uses direct kwargs on transcribe_file(), not PrerecordedOptions — research doc described older SDK API"
  - "response.to_json() does not exist in SDK v6; use Pydantic response.model_dump_json() for JSON serialization"
  - "Cache skip uses Path.exists() check before any API call per D-02"
  - "CONCURRENCY module constant read at import time; tests use importlib.reload() to pick up env var changes"
metrics:
  duration: "~15 minutes"
  completed: "2026-03-27"
  tasks_completed: 1
  files_created: 2
  files_modified: 3
---

# Phase 02 Plan 01: Install deepgram-sdk and Transcription Module Summary

**One-liner:** Async batch transcription module with JSON cache layer using deepgram-sdk v6 Pydantic API, tested fully with mocks.

## What Was Built

- `src/phonebot/pipeline/transcribe.py` — async batch transcription module (84 lines)
  - `_transcribe_one`: cache-skip + Deepgram API call with Nova-3/de/smart_format/punctuate/diarize/paragraphs
  - `transcribe_all`: asyncio.gather dispatch with semaphore-bounded concurrency
  - `get_transcript_text`: extracts plain transcript from cached JSON
  - `get_words`: extracts word-level data from cached JSON
  - Module constants: `TRANSCRIPT_DIR`, `CONCURRENCY` (env-configurable)
- `tests/test_transcribe.py` — 8 unit tests, all passing with mocked Deepgram client
- `pyproject.toml` / `uv.lock` — deepgram-sdk==6.1.0 added as dependency
- `.env.example` — `DEEPGRAM_CONCURRENCY=5` added

## Test Results

- New transcription tests: **8/8 passed**
- Full suite: **38/38 passed** (30 existing + 8 new)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] deepgram-sdk v6 has incompatible API vs research doc**
- **Found during:** Step 3 (writing implementation, GREEN phase)
- **Issue:** Research doc (02-RESEARCH.md) documented the API for the older deepgram-python-sdk. The installed `deepgram-sdk==6.1.0` is a Fern-generated SDK with completely different API:
  - No `PrerecordedOptions` class exists — options are direct kwargs on `transcribe_file()`
  - `response.to_json()` does not exist — SDK returns Pydantic models with `.model_dump_json()`
  - Import path: `from deepgram import AsyncDeepgramClient` (no `PrerecordedOptions`)
- **Fix:** Updated `transcribe.py` to use direct kwargs: `transcribe_file(request=..., model="nova-3", language="de", smart_format=True, ...)` and `response.model_dump_json()` for serialization
- **Tests updated:** Mock uses `mock_response.model_dump_json.return_value = FAKE_DEEPGRAM_JSON`. `test_calls_deepgram_when_no_cache` asserts `call_kwargs["model"] == "nova-3"` instead of asserting on `PrerecordedOptions` fields.
- **Files modified:** `src/phonebot/pipeline/transcribe.py`, `tests/test_transcribe.py`
- **Commits:** a28614d

**2. [Rule 1 - Bug] test_concurrency_default/env_override used wrong module import pattern for reload()**
- **Found during:** GREEN phase test run
- **Issue:** Using `from phonebot.pipeline import transcribe as t` then deleting `sys.modules["phonebot.pipeline.transcribe"]` before `importlib.reload(t)` caused `ImportError: module not in sys.modules`
- **Fix:** Changed to `import phonebot.pipeline.transcribe as t` (direct absolute import that keeps module in sys.modules before reload call) and used `sys.modules.pop()` instead of `del`
- **Files modified:** `tests/test_transcribe.py`
- **Commits:** a28614d

### Plan Acceptance Criteria Compliance

All acceptance criteria met, with adaptations for SDK v6 API:
- `deepgram-sdk` in `pyproject.toml` — YES
- `async def _transcribe_one(` — YES
- `async def transcribe_all(` — YES
- `def get_transcript_text(` — YES
- `def get_words(` — YES
- `model="nova-3"` — YES (as direct kwarg, not PrerecordedOptions field)
- `language="de"` — YES
- `smart_format=True` — YES
- `diarize=True` — YES
- `DEEPGRAM_CONCURRENCY` — YES
- `cache_path.exists()` — YES
- `response.to_json()` — **replaced by `response.model_dump_json()`** (SDK v6 Pydantic API)
- `encoding="utf-8"` — YES
- All test functions present — YES
- `.env.example` contains `DEEPGRAM_CONCURRENCY` — YES
- `uv run pytest tests/test_transcribe.py -x` — PASSES (8/8)
- `uv run pytest -x` — PASSES (38/38)

Note: `response.to_json()` acceptance criterion cannot be met as the method does not exist in deepgram-sdk v6. The equivalent `response.model_dump_json()` achieves identical behavior (full JSON serialization of the response). The cache layer behavior (D-01) is preserved.

## Known Stubs

None — all functions are fully wired. `transcribe_all` calls `_transcribe_one` which calls the live Deepgram API (mocked in tests). `get_transcript_text` and `get_words` read real JSON from disk.

## Self-Check: PASSED

Files:
- FOUND: src/phonebot/pipeline/transcribe.py
- FOUND: tests/test_transcribe.py

Commits:
- bbdb838 — RED phase (failing tests)
- a28614d — GREEN phase (implementation + passing tests)
