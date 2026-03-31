---
phase: 5
slug: model-a-b-testing
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 0.25.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_model_registry.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_model_registry.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | AB-01 | unit | `uv run pytest tests/test_model_registry.py::test_registry_routes_claude -x` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | AB-01 | unit | `uv run pytest tests/test_model_registry.py::test_registry_routes_ollama -x` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | AB-01 | unit | `uv run pytest tests/test_model_registry.py::test_registry_strips_ollama_prefix -x` | ❌ W0 | ⬜ pending |
| 05-01-04 | 01 | 1 | AB-01 | unit | `uv run pytest tests/test_model_registry.py::test_registry_unknown_model_raises -x` | ❌ W0 | ⬜ pending |
| 05-01-05 | 01 | 1 | AB-01 | unit | `uv run pytest tests/test_extract.py::test_extract_node_uses_registry -x` | ❌ W0 | ⬜ pending |
| 05-01-06 | 01 | 1 | AB-01 | unit | `uv run pytest tests/test_cli.py::test_output_path_uses_model_alias -x` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 2 | AB-02 | unit | `uv run pytest tests/test_compare.py::test_compare_loads_two_files -x` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 2 | AB-02 | unit | `uv run pytest tests/test_compare.py::test_compare_declares_winner -x` | ❌ W0 | ⬜ pending |
| 05-02-03 | 02 | 2 | AB-02 | unit | `uv run pytest tests/test_compare.py::test_compare_writes_json -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_model_registry.py` — stubs for AB-01 registry routing, prefix stripping, error handling
- [ ] `tests/test_compare.py` — stubs for AB-02 compare script logic (load files, compute metrics, write JSON)
- [ ] `tests/test_extract.py` — add `test_extract_node_uses_registry` (mock `get_model`, verify it's called)
- [ ] `tests/test_cli.py` — add `test_output_path_uses_model_alias`

*Existing test infrastructure: pytest + pytest-asyncio already configured in pyproject.toml — no framework install needed*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Phoenix shows two sets of 30 traces tagged by model name | AB-02 | Requires live Phoenix UI inspection | Run pipeline with two models, open Phoenix UI, filter by model name, verify two distinct trace sets |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
