---
phase: 3
slug: extraction-pipeline
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-27
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-03 | 01 | 1 | EXT-03 | unit | `uv run pytest tests/test_extract.py -k test_graph_topology` | tests/test_extract.py | ⬜ pending |
| 03-01-03 | 01 | 1 | EXT-03 | unit | `uv run pytest tests/test_extract.py -k test_pipeline_state_fields` | tests/test_extract.py | ⬜ pending |
| 03-01-03 | 01 | 1 | EXT-05 | unit | `uv run pytest tests/test_extract.py -k test_caller_info_field_descriptions_phone` | tests/test_extract.py | ⬜ pending |
| 03-01-03 | 01 | 1 | EXT-05 | unit | `uv run pytest tests/test_extract.py -k test_caller_info_field_descriptions_email` | tests/test_extract.py | ⬜ pending |
| 03-01-03 | 01 | 1 | EXT-02 | unit | `uv run pytest tests/test_extract.py -k test_caller_info_docstring_is_system_prompt` | tests/test_extract.py | ⬜ pending |
| 03-01-03 | 01 | 1 | QUAL-01 | integration | `uv run pytest tests/test_extract.py -k test_missing_field_returns_null` | tests/test_extract.py | ⬜ pending |
| 03-02-01 | 02 | 2 | EXT-01 | structural | `uv run python run.py --help` | run.py | ⬜ pending |
| 03-02-02 | 02 | 2 | EXT-01, QUAL-01 | e2e | `uv run python run.py` + checkpoint | outputs/results.json | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_extract.py` — created in Plan 03-01, Task 3 with stubs for EXT-01, EXT-02, EXT-03, EXT-05, QUAL-01
- [x] `tests/conftest.py` — already present from Phase 1
- [x] pytest installed — verify via `uv run pytest --version`

*Existing infrastructure covers all phase requirements. Test file is created within Plan 03-01 Task 3 (TDD task).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| German spoken-form accuracy | EXT-03 | Requires listening to audio and comparing transcript interpretation | Spot-check 3 recordings with German phone numbers against extracted values |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready
