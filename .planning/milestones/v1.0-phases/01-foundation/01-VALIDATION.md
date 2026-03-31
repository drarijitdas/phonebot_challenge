---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-26
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (Wave 0 creates) |
| **Quick run command** | `uv run pytest tests/test_evaluation_metrics.py -x` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | INFRA-01 | smoke | `uv run python run.py --help` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | INFRA-02 | unit | `uv run pytest tests/test_cli.py -x` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | EVAL-01 | unit | `uv run pytest tests/test_evaluation_metrics.py::test_compute_metrics -x` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 1 | EVAL-02 | unit | `uv run pytest tests/test_evaluation_metrics.py::test_multi_value_match -x` | ❌ W0 | ⬜ pending |
| 01-02-03 | 02 | 1 | EVAL-03 | unit | `uv run pytest tests/test_evaluation_metrics.py::test_phone_normalization -x` | ❌ W0 | ⬜ pending |
| 01-02-04 | 02 | 1 | EVAL-04 | unit | `uv run pytest tests/test_evaluation_metrics.py::test_text_normalization -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/__init__.py` — empty file
- [ ] `tests/test_evaluation_metrics.py` — stubs for EVAL-01, EVAL-02, EVAL-03, EVAL-04
- [ ] `tests/test_cli.py` — stubs for INFRA-02
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` — sets `testpaths = ["tests"]`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CallerInfo has class docstring | EXT-02 (shape only) | Docstring content is semantic | Inspect `src/phonebot/models/caller_info.py` — class has multi-line docstring |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
