---
phase: 3
slug: extraction-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| 03-01-01 | 01 | 0 | EXT-01 | unit | `uv run pytest tests/test_pipeline.py -k test_pipeline_state` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | EXT-02 | unit | `uv run pytest tests/test_pipeline.py -k test_extract_node` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 1 | EXT-03 | unit | `uv run pytest tests/test_pipeline.py -k test_german_phone` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 1 | EXT-05 | integration | `uv run pytest tests/test_pipeline.py -k test_null_fields` | ❌ W0 | ⬜ pending |
| 03-01-05 | 01 | 2 | QUAL-01 | integration | `uv run python run.py && uv run pytest tests/test_pipeline.py -k test_accuracy` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_pipeline.py` — stubs for EXT-01, EXT-02, EXT-03, EXT-05, QUAL-01
- [ ] `tests/conftest.py` — shared fixtures (if not already present)
- [ ] pytest installed — verify via `uv run pytest --version`

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| German spoken-form accuracy | EXT-03 | Requires listening to audio and comparing transcript interpretation | Spot-check 3 recordings with German phone numbers against extracted values |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
