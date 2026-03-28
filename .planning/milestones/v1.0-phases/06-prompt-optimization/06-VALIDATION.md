---
phase: 6
slug: prompt-optimization
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-28
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 0.25.0 |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_prompts.py tests/test_optimize.py -x` |
| **Full suite command** | `uv run pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_prompts.py tests/test_extract.py -x`
- **After every plan wave:** Run `uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | OPT-02 | unit | `uv run pytest tests/test_prompts.py::test_build_caller_info_model -x` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | OPT-02 | unit | `uv run pytest tests/test_prompts.py::test_caller_info_json_schema -x` | ❌ W0 | ⬜ pending |
| 06-01-03 | 01 | 1 | OPT-02 | smoke | `uv run pytest tests/test_prompts.py::test_v1_prompt_file_exists -x` | ❌ W0 | ⬜ pending |
| 06-01-04 | 01 | 1 | OPT-02 | unit | `uv run pytest tests/test_extract.py::test_extract_node_uses_dynamic_model -x` | ❌ W0 | ⬜ pending |
| 06-02-01 | 02 | 2 | OPT-01 | integration | `uv run pytest tests/test_optimize.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_prompts.py` — stubs for OPT-02: `build_caller_info_model`, JSON schema, v1 file exists
- [ ] `tests/test_extract.py::test_extract_node_uses_dynamic_model` — add to existing file
- [ ] `tests/test_optimize.py` — smoke test for optimize.py plumbing (can mock gepa.optimize)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| GEPA optimization produces measurable accuracy delta | OPT-01 | Requires live LLM calls + ground truth comparison | Run `uv run python optimize.py`, compare v1 vs v2 accuracy in output report |
| Phoenix shows GEPA optimization traces | OPT-01 | Visual dashboard verification | Open Phoenix UI, check for `prompt_version=gepa_opt_N` tagged traces |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
