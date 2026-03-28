---
phase: 7
slug: hardening
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-28
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 0.25.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`) |
| **Quick run command** | `uv run python -m pytest tests/test_extract.py tests/test_cli.py -x -q` |
| **Full suite command** | `uv run python -m pytest -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run python -m pytest tests/test_extract.py tests/test_cli.py -x -q`
- **After every plan wave:** Run `uv run python -m pytest -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | EXT-04 | unit | `uv run python -m pytest tests/test_extract.py::test_graph_topology -x` | ✅ UPDATE | ⬜ pending |
| 07-01-02 | 01 | 1 | EXT-04 | unit | `uv run python -m pytest tests/test_extract.py::test_pipeline_state_fields -x` | ✅ UPDATE | ⬜ pending |
| 07-01-03 | 01 | 1 | EXT-04 | unit | `uv run python -m pytest tests/test_extract.py::test_retry_on_validation_failure -x` | ❌ W0 | ⬜ pending |
| 07-01-04 | 01 | 1 | EXT-04 | unit | `uv run python -m pytest tests/test_extract.py::test_retry_exhaustion_proceeds_to_end -x` | ❌ W0 | ⬜ pending |
| 07-01-05 | 01 | 1 | QUAL-02 | unit | `uv run python -m pytest tests/test_extract.py::test_compute_flagged_fields -x` | ❌ W0 | ⬜ pending |
| 07-01-06 | 01 | 1 | QUAL-02 | unit | `uv run python -m pytest tests/test_extract.py::test_result_includes_flagged_fields -x` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 2 | D-04 | unit | `uv run python -m pytest tests/test_cli.py::test_final_flag_exists -x` | ❌ W0 | ⬜ pending |
| 07-02-02 | 02 | 2 | D-04 | integration | `uv run python -m pytest tests/test_cli.py::test_final_writes_output_files -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_extract.py` — update `test_graph_topology` (add validate node + retry back-edge assertions)
- [ ] `tests/test_extract.py` — update `test_pipeline_state_fields` (add `retry_count`, `validation_errors`)
- [ ] `tests/test_extract.py` — add `test_retry_on_validation_failure` stub (EXT-04)
- [ ] `tests/test_extract.py` — add `test_retry_exhaustion_proceeds_to_end` stub (EXT-04)
- [ ] `tests/test_extract.py` — add `test_compute_flagged_fields` stub (QUAL-02)
- [ ] `tests/test_extract.py` — add `test_result_includes_flagged_fields` stub (QUAL-02)
- [ ] `tests/test_cli.py` — add `test_final_flag_exists` stub (D-04)
- [ ] `tests/test_cli.py` — add `test_final_writes_output_files` stub (D-04)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Confidence scores populated by LLM | QUAL-02 | LLM output varies; requires live API call | Run `uv run python run.py --model claude-sonnet-4-6` and check `caller_info["confidence"]` is non-empty in first result |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
