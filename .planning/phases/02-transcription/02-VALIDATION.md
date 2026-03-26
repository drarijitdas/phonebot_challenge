---
phase: 2
slug: transcription
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-26
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 (already installed, `tests/` in pyproject.toml) |
| **Config file** | `[tool.pytest.ini_options]` in `pyproject.toml` — `testpaths = ["tests"]` |
| **Quick run command** | `uv run pytest tests/test_transcribe.py -x` |
| **Full suite command** | `uv run pytest -x` |
| **Estimated runtime** | ~5 seconds (unit/mock tests only; integration tests with live API ~60s) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_transcribe.py -x`
- **After every plan wave:** Run `uv run pytest -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | STT-01 | unit (mock) | `uv run pytest tests/test_transcribe.py::test_calls_deepgram_when_no_cache -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | STT-03 | unit (mock) | `uv run pytest tests/test_transcribe.py::test_skips_existing_cache -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | STT-03 | unit | `uv run pytest tests/test_transcribe.py::test_cache_json_structure -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | STT-01 | integration | `uv run pytest tests/test_transcribe.py::test_transcribes_all_30 -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 2 | STT-02 | smoke | `uv run pytest tests/test_transcribe.py::test_analysis_report_exists -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_transcribe.py` — stubs for STT-01 (mock Deepgram calls), STT-02 (report exists), STT-03 (cache skip, JSON structure)
- [ ] Fixtures for mocking `AsyncDeepgramClient` and Deepgram response objects

*Existing `tests/conftest.py` and pytest infrastructure from Phase 1 covers framework setup.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| smart_format analysis accuracy | STT-02 | Requires human review of 5+ transcript outputs vs spoken-form expectations | Open `docs/smart_format_analysis.md`, verify comparison tables reflect actual Deepgram output |
| Diarization quality | STT-02 (informational) | Speaker assignment quality requires listening to audio | Spot-check 3 recordings: verify speaker 0/1 assignment is consistent |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
