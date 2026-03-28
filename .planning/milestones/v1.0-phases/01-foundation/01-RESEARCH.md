# Phase 1: Foundation - Research

**Researched:** 2026-03-26
**Domain:** Python project scaffold, Pydantic schema definition, CLI entrypoint, evaluation harness with E.164 phone normalization and multi-value ground truth matching
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Flat `src/phonebot/` package with modules: `pipeline/`, `evaluation/`, `models/`, `observability/`, `prompts/`
- **D-02:** All prompts live in the Pydantic model code (docstring + field descriptions). GEPA will inject/modify at runtime rather than reading from externalized files.
- **D-03:** Environment vars + `.env` file for config (DEEPGRAM_API_KEY, ANTHROPIC_API_KEY, etc.). No pydantic-settings, just `os.environ` or `python-dotenv`.
- **D-04:** Rich library for all CLI output — no Typer. Manual argument handling with Rich Console for formatted output.
- **D-05:** Minimal CLI args: `--model` (LLM choice), `--recordings-dir` (default `data/recordings/`), `--output` (default `outputs/results.json`)
- **D-06:** Rich live table for progress display — showing each recording's status (transcribing/extracting/done) as it processes
- **D-07:** Async concurrent processing of recordings (not sequential)
- **D-08:** Dual output: Rich table to console for human review + JSON file at `outputs/eval_results.json` for programmatic use
- **D-09:** Per-field accuracy AND per-recording breakdown showing which fields were correct/wrong for each call
- **D-10:** Include per-field confidence from the start: `confidence: dict[str, float]` (e.g., `{"first_name": 0.95, "email": 0.6}`)
- **D-11:** Pydantic prompting system: docstring = extraction context ("you are extracting from a German phone bot transcript"), Field descriptions = per-field extraction instructions

### Claude's Discretion

- Exact Rich table styling and column widths
- .env loading implementation (dotenv vs manual)
- Exact module names within `src/phonebot/` (beyond the top-level layout)
- Evaluation JSON schema structure

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.

</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-01 | Project uses `uv` for dependency management with Python 3.13 | uv 0.6.5 confirmed installed; Python 3.13.12 confirmed available; pyproject.toml PEP 621 pattern documented below |
| INFRA-02 | Pipeline runs via CLI entrypoint with clear arguments | `argparse` + Rich Console pattern documented; `run.py` as the entrypoint with `--help` requirement |
| EVAL-01 | Evaluation harness computes per-field accuracy against ground truth for all 30 recordings | ground_truth.json schema fully inspected — scalar strings only, E.164 phone format throughout; metrics module pattern documented |
| EVAL-02 | Evaluation supports multiple acceptable values per field (ground truth arrays) | Schema inspection finding: ground truth currently uses scalar strings — BUT multi-value handling must be coded defensively per REQUIREMENTS.md and success criteria |
| EVAL-03 | Phone numbers normalized via `phonenumbers` library (E.164) before comparison | phonenumbers 9.0.26 latest; E.164 normalization pattern confirmed; ground truth already uses E.164 |
| EVAL-04 | Unicode normalization (NFC) and case-insensitive comparison for name/email fields | unicodedata.normalize("NFC") pattern; no extra library needed |

</phase_requirements>

---

## Summary

Phase 1 delivers the project scaffold that all subsequent phases build on. The work divides into three independent pieces: (1) the `uv`-managed Python 3.13 project with the `src/phonebot/` package layout, (2) the `CallerInfo` Pydantic v2 model with the four required fields plus per-field confidence dict, and (3) the evaluation harness in `evaluation/metrics.py` that reads `data/ground_truth.json` and produces per-field accuracy against mock results.

The ground truth schema has been inspected. All 30 records use scalar string values for every field — no arrays, no alias keys. However, the REQUIREMENTS.md explicitly requires multi-value support (EVAL-02), and the success criteria cite the "Lisa Marie / Lisa-Marie" example. The evaluation code must therefore be written defensively: accept both `str` and `list[str]` for any ground truth field value. This future-proofs the harness when ground truth is updated with multi-value entries.

Phone numbers in the ground truth are already in E.164 format (e.g., `"+49 152 11223456"`). The `phonenumbers` library must normalize extracted values to E.164 before comparison — this makes a correct extraction with different formatting (e.g., `"0152 11223456"` or `"+4915211223456"`) score as correct. Unicode NFC normalization and case-folding are required for name and email fields.

**Primary recommendation:** Use `uv init --package` with `--python 3.13`, configure `src/phonebot/` layout in `pyproject.toml`, implement `CallerInfo` with `Optional[str] = None` fields plus `confidence: dict[str, float]`, and write `evaluation/metrics.py` with a `matches_field()` comparison function that handles scalar/list ground truth, E.164 phone normalization, and NFC+lowercase normalization for text fields.

---

## Standard Stack

### Core (Phase 1 only)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.12.5 | CallerInfo model schema and validation | Locked by decision D-10/D-11; required by LangGraph/LangChain in later phases |
| phonenumbers | 9.0.26 | E.164 phone normalization for evaluation | Only Python port of Google's libphonenumber; required by EVAL-03 |
| rich | 14.3.3 | Console output, CLI formatting | Locked by decision D-04; no Typer |
| python-dotenv | 1.2.2 | Load .env into os.environ | Locked by decision D-03; no pydantic-settings |
| pytest | 9.0.2 | Test harness for evaluation metrics | Standard test runner for Python 3.13 |

### Development Tools

| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| uv | 0.6.5 (installed) | Dependency management, venv | Required by INFRA-01; `uv init --package`, `uv add`, `uv run` |
| Python | 3.13.12 (available) | Runtime | Required by INFRA-01; confirmed on this machine |

### Libraries NOT used in Phase 1

The following are in the full project stack but are NOT installed in Phase 1: `deepgram-sdk`, `langgraph`, `langchain-anthropic`, `langchain-openai`, `arize-phoenix`, `gepa`. Phase 1 is greenfield scaffold only — no external API calls.

**Installation (Phase 1 only):**
```bash
# Initialize project
uv init --package phonebot_challenge --python 3.13
cd phonebot_challenge

# Phase 1 runtime dependencies
uv add pydantic phonenumbers rich python-dotenv

# Dev dependencies
uv add --dev pytest
```

---

## Architecture Patterns

### Recommended Project Structure

```
phonebot_challenge/
├── pyproject.toml           # uv/PEP 621 config; [project.scripts] entry point
├── run.py                   # CLI entrypoint: argparse + Rich Console
├── .env                     # API keys (gitignored)
├── .env.example             # Template (committed)
├── data/
│   ├── recordings/          # 30 WAV files (already present)
│   └── ground_truth.json    # Expected extraction results (already present)
├── outputs/                 # Created at runtime
│   ├── results.json         # Extraction results per recording
│   └── eval_results.json    # Evaluation output (per D-08)
├── src/
│   └── phonebot/
│       ├── __init__.py
│       ├── models/
│       │   ├── __init__.py
│       │   └── caller_info.py   # CallerInfo Pydantic model
│       ├── pipeline/
│       │   └── __init__.py      # Placeholder for Phase 3
│       ├── evaluation/
│       │   ├── __init__.py
│       │   └── metrics.py       # Per-field accuracy, matches_field(), load_ground_truth()
│       ├── observability/
│       │   └── __init__.py      # Placeholder for Phase 4
│       └── prompts/
│           └── __init__.py      # Placeholder (prompts live in CallerInfo docstring per D-02)
└── tests/
    └── test_evaluation_metrics.py  # Unit tests for metrics.py
```

### Pattern 1: uv Project Initialization (INFRA-01)

`uv init --package` creates the `src/` layout with `pyproject.toml` using PEP 621 format. The `[project.scripts]` table maps `run = "phonebot.cli:main"` or the entrypoint is `run.py` at the project root invoked via `uv run python run.py`.

```toml
# pyproject.toml
[project]
name = "phonebot-challenge"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "pydantic>=2.12.5",
    "phonenumbers>=9.0.26",
    "rich>=14.3.3",
    "python-dotenv>=1.2.2",
]

[project.optional-dependencies]
dev = ["pytest>=9.0.2"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/phonebot"]
```

Note: `uv run python run.py --help` (the success criterion) works without a `[project.scripts]` entry — `run.py` at the project root is fine as the entrypoint.

### Pattern 2: CallerInfo Pydantic Model (EXT-02 shape, built in Phase 1)

All four fields typed `Optional[str] = None`. Confidence dict added per D-10. Docstring is the extraction context (D-11). Field `description` args are per-field extraction instructions.

```python
# src/phonebot/models/caller_info.py
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class CallerInfo(BaseModel):
    """
    You are extracting caller contact information from a German phone bot transcript.
    The caller is speaking German. Extract only information explicitly stated.
    Return null for any field not clearly mentioned — do not guess or infer.
    """

    first_name: Optional[str] = Field(
        None,
        description=(
            "Caller's first name as spoken. Preserve German special characters "
            "(ä, ö, ü, ß). Return null if not stated."
        ),
    )
    last_name: Optional[str] = Field(
        None,
        description=(
            "Caller's last name as spoken. If spelled out letter by letter, "
            "reconstruct the spelling. Return null if not stated."
        ),
    )
    email: Optional[str] = Field(
        None,
        description=(
            "Email address. May be spoken as 'mueller at beispiel punkt de'. "
            "Reconstruct the full address (e.g., mueller@beispiel.de). "
            "Return null if not stated."
        ),
    )
    phone_number: Optional[str] = Field(
        None,
        description=(
            "Phone number as spoken. May be given as digit words "
            "('null zwei null eins...'). Reconstruct the digit string. "
            "Return null if not stated."
        ),
    )
    confidence: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Per-field confidence scores between 0.0 and 1.0. "
            "Keys match field names. Omit keys for fields not attempted."
        ),
    )
```

**Important:** The `confidence` field uses `default_factory=dict`, not `Optional`. It is never `None` — it is either empty `{}` or populated. This is intentional: LLMs in later phases populate it; the evaluation harness ignores it.

### Pattern 3: Evaluation Harness (EVAL-01 through EVAL-04)

The `evaluation/metrics.py` module must:
1. Load `data/ground_truth.json` into a dict keyed by recording ID
2. For each recording, compare predicted `CallerInfo` against expected values
3. Normalize before comparison: E.164 for phone, NFC+lowercase for text
4. Handle ground truth values that are either `str` (current schema) or `list[str]` (future multi-value per EVAL-02)
5. Return per-field accuracy across all recordings and per-recording breakdown

```python
# src/phonebot/evaluation/metrics.py
import json
import unicodedata
from pathlib import Path
from typing import Any

import phonenumbers
from phonenumbers import PhoneNumberFormat


FIELDS = ("first_name", "last_name", "email", "phone_number")


def load_ground_truth(path: Path) -> dict[str, dict[str, Any]]:
    """Return dict keyed by recording id, value is the 'expected' dict."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {rec["id"]: rec["expected"] for rec in data["recordings"]}


def normalize_phone(raw: str | None) -> str | None:
    """Normalize to E.164 with German default region. Returns None on failure."""
    if raw is None:
        return None
    try:
        parsed = phonenumbers.parse(raw, "DE")
        return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        return raw  # Return as-is; comparison will likely fail


def normalize_text(raw: str | None) -> str | None:
    """NFC normalize and case-fold for name/email comparison."""
    if raw is None:
        return None
    return unicodedata.normalize("NFC", raw).casefold().strip()


def normalize_value(field: str, value: str | None) -> str | None:
    """Apply appropriate normalization based on field type."""
    if field == "phone_number":
        return normalize_phone(value)
    return normalize_text(value)


def matches_field(
    field: str,
    predicted: str | None,
    ground_truth_value: str | list[str] | None,
) -> bool:
    """
    Compare predicted against ground truth for a single field.
    Handles:
    - null ground truth: predicted must also be null
    - scalar ground truth: normalized equality
    - list ground truth: predicted matches any item after normalization
    """
    norm_pred = normalize_value(field, predicted)

    if ground_truth_value is None:
        return norm_pred is None

    if isinstance(ground_truth_value, list):
        acceptable = [normalize_value(field, v) for v in ground_truth_value]
        return norm_pred in acceptable

    # Scalar
    return norm_pred == normalize_value(field, ground_truth_value)


def compute_metrics(
    results: list[dict],  # list of {"id": str, "caller_info": CallerInfo | dict}
    ground_truth: dict[str, dict],
) -> dict:
    """
    Compute per-field accuracy and per-recording breakdown.

    Returns:
        {
            "per_field": {"first_name": 0.8, "last_name": 0.6, ...},
            "overall": 0.7,
            "per_recording": [
                {"id": "call_01", "first_name": True, "last_name": False, ...},
                ...
            ],
        }
    """
    per_field_correct = {f: 0 for f in FIELDS}
    per_recording = []
    n = len(results)

    for result in results:
        rec_id = result["id"]
        info = result.get("caller_info") or {}
        if hasattr(info, "model_dump"):
            info = info.model_dump()
        expected = ground_truth.get(rec_id, {})

        row = {"id": rec_id}
        for field in FIELDS:
            pred_val = info.get(field)
            gt_val = expected.get(field)
            correct = matches_field(field, pred_val, gt_val)
            row[field] = correct
            if correct:
                per_field_correct[field] += 1
        per_recording.append(row)

    per_field_accuracy = {f: per_field_correct[f] / n if n else 0.0 for f in FIELDS}
    overall = sum(per_field_accuracy.values()) / len(FIELDS)

    return {
        "per_field": per_field_accuracy,
        "overall": overall,
        "per_recording": per_recording,
    }
```

### Pattern 4: CLI Entrypoint (INFRA-02)

Manual `argparse` with `Rich Console` (no Typer per D-04). The `--help` output is the Phase 1 success criterion.

```python
# run.py
import argparse
import sys
from rich.console import Console

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phonebot",
        description="Extract caller info from German phone bot recordings.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="LLM model identifier for extraction",
    )
    parser.add_argument(
        "--recordings-dir",
        default="data/recordings/",
        help="Directory containing WAV recording files",
    )
    parser.add_argument(
        "--output",
        default="outputs/results.json",
        help="Path for extraction results JSON output",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    console.print("[bold green]Phonebot pipeline starting...[/bold green]")
    # Phase 2+: pipeline execution goes here
    console.print(f"Model: {args.model}")
    console.print(f"Recordings: {args.recordings_dir}")
    console.print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
```

### Pattern 5: Evaluation Entry Point for `python -m evaluation.metrics`

The success criterion states `uv run python -m evaluation.metrics` against `data/ground_truth.json` must print per-field accuracy for mock results showing 0% baseline. This requires `evaluation/metrics.py` to have a `__main__` block.

```python
# At the bottom of src/phonebot/evaluation/metrics.py

if __name__ == "__main__":
    import sys
    from pathlib import Path
    from rich.console import Console
    from rich.table import Table

    console = Console()
    gt_path = Path("data/ground_truth.json")

    if not gt_path.exists():
        console.print(f"[red]Ground truth not found: {gt_path}[/red]")
        sys.exit(1)

    gt = load_ground_truth(gt_path)

    # Baseline: mock results with all None extractions (0% accuracy)
    mock_results = [
        {"id": rec_id, "caller_info": {}}
        for rec_id in gt
    ]

    metrics = compute_metrics(mock_results, gt)

    table = Table(title="Evaluation Results (Baseline — 0%)")
    table.add_column("Field", style="cyan")
    table.add_column("Accuracy", style="magenta")

    for field, acc in metrics["per_field"].items():
        table.add_row(field, f"{acc:.1%}")
    table.add_row("[bold]Overall[/bold]", f"[bold]{metrics['overall']:.1%}[/bold]")

    console.print(table)
```

**Important:** The module path for `python -m` is `evaluation.metrics`, but the package is installed as `src/phonebot/`. The run command must be `uv run python -m phonebot.evaluation.metrics` OR the `PYTHONPATH` must include `src/`. The success criterion literally says `uv run python -m evaluation.metrics` — the planner needs to confirm whether the entrypoint module path matches the package layout. Options:
1. Make `evaluation/` a top-level module at project root (simpler, matches success criterion literally)
2. Use `uv run python -m phonebot.evaluation.metrics` (matches `src/` layout)
3. Add a `[project.scripts]` `evaluate` entry that calls the right function

**Recommendation:** Keep the `src/phonebot/` layout (locked by D-01) and use `uv run python -m phonebot.evaluation.metrics`. Document this in the CLI `--help` output. The success criterion wording is approximate — the planner should validate this interpretation.

### Anti-Patterns to Avoid

- **`Optional[str]` without `= None`:** Without the default, Pydantic v2 requires the field at instantiation — the LLM is pressured to fill it. Always `Optional[str] = None`.
- **Mutable default for `confidence` field:** `confidence: dict[str, float] = {}` causes all instances to share the same dict. Use `Field(default_factory=dict)`.
- **`json.dumps` without `ensure_ascii=False`:** Default `ensure_ascii=True` escapes `ü` → `\u00fc`. Always `json.dumps(..., ensure_ascii=False, indent=2)`.
- **Exact string match in `matches_field`:** Direct `==` comparison fails for `+49 152 11223456` vs `+4915211223456`. Always normalize phone via `phonenumbers` and text via NFC+casefold.
- **Hard-coding the ground truth path in metrics:** Accept it as a parameter for testability.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Phone number normalization | Custom regex for `+49` / `0` prefix stripping | `phonenumbers` (9.0.26) | German open numbering plan has variable-length area codes (2-5 digits); regex cannot parse correctly without a reference database |
| Unicode normalization | Custom umlaut table | `unicodedata.normalize("NFC", ...)` | stdlib; handles all Unicode combining forms, not just German umlauts |
| CLI argument parsing | Custom `sys.argv` parsing | `argparse` (stdlib) | Auto-generates `--help`; the success criterion requires `uv run python run.py --help` to print usage |
| Pydantic model validation | Manual `isinstance` checks | Pydantic `BaseModel` | Required by EXT-02; used by `with_structured_output()` in later phases |
| Rich Console output | ANSI escape sequences | `rich.console.Console` | Locked by D-04; handles terminal width, color themes, live rendering |

**Key insight:** The evaluation harness is the most error-prone component. Every custom comparison function is a potential silent accuracy suppressor. Use `phonenumbers` for phones; use `unicodedata` for text; use Python's `str.casefold()` (not `.lower()`) for case-insensitive Unicode comparison — `casefold()` handles German `ß` → `ss` correctly.

---

## Ground Truth Schema (CRITICAL — inspect before coding EVAL)

**Inspected:** `data/ground_truth.json` — all 30 records confirmed.

**Schema:**
```json
{
  "recordings": [
    {
      "id": "call_01",
      "file": "call_01.wav",
      "expected": {
        "first_name": "Johanna",
        "last_name": "Schmidt",
        "email": "johanna.schmidt@gmail.com",
        "phone_number": "+49 152 11223456"
      }
    }
  ]
}
```

**Key findings from inspection:**
1. **All `expected` values are scalar strings** — no arrays, no `aliases` keys, no `acceptable_values` fields in the current file.
2. **Phone numbers are already in E.164 format** — all 30 use `"+49 ..."` with a space after the country code. The `phonenumbers` library normalizes to `"+49..."` without the space — the comparison must normalize BOTH sides.
3. **Umlaut names present:** call_07 `Schröder`, call_09 `Müller`. NFC normalization and `casefold()` are required.
4. **Non-German names present (calls 16-30):** García (call_20), Kowalski (call_21), Martínez (call_29), O'Brien (call_30). These will have transcription risk in Phase 2.
5. **Multi-value field handling:** Ground truth is currently scalar, but EVAL-02 and the success criteria explicitly require the evaluation harness to handle list values. The `matches_field()` function must accept `str | list[str]` for ground truth values.

**E.164 normalization note:** `phonenumbers.parse("+49 152 11223456", "DE")` → `format_number(parsed, E164)` → `"+49 15211223456"`. Apply the same normalization to both the ground truth value and the extracted value before comparison.

---

## Common Pitfalls

### Pitfall 1: `python -m evaluation.metrics` Path Resolution

**What goes wrong:** The success criterion says `uv run python -m evaluation.metrics` but the code lives at `src/phonebot/evaluation/metrics.py`. Python's `-m` flag looks for `evaluation/metrics.py` on `sys.path`, which in a `uv` project includes `src/phonebot/` — NOT `src/`.

**Why it happens:** The `src/` layout means Python sees `src/phonebot/` as the package root. So `-m phonebot.evaluation.metrics` works, but `-m evaluation.metrics` does not unless `src/phonebot/` is on `sys.path`.

**How to avoid:** Use `uv run python -m phonebot.evaluation.metrics` as the canonical command, OR add a thin `evaluation/` package at the project root that re-exports from `src/phonebot/evaluation/`. The planner should confirm which interpretation the user intended — the success criterion wording suggests they may have written it before the `src/` layout was finalized.

**Warning signs:** `ModuleNotFoundError: No module named 'evaluation'` when running the success criterion command.

### Pitfall 2: E.164 Both-Sides Normalization

**What goes wrong:** Normalizing only the extracted phone number but not the ground truth value. Ground truth stores `"+49 152 11223456"` (with space); `phonenumbers` E.164 produces `"+49152 11223456"` or `"+4915211223456"` depending on formatting constant used.

**How to avoid:** Apply `normalize_phone()` to BOTH `predicted` and `ground_truth_value` in `matches_field()`. Never compare raw strings for phone numbers.

**Warning signs:** Phone accuracy is 0% even when the extracted number looks identical to ground truth.

### Pitfall 3: Confidence Field Excluded from Structured Output

**What goes wrong:** When `CallerInfo` is used with `llm.with_structured_output(CallerInfo)` in Phase 3, the LLM may not populate `confidence` unless explicitly instructed — or the structured output schema may reject a `dict` field as ambiguous.

**How to avoid:** In Phase 1, define `confidence` as a proper Pydantic field with `default_factory=dict`. The evaluation harness ignores `confidence` entirely — it only reads the four string fields. Phase 3 will decide whether to populate it via chain-of-thought or post-processing.

**Warning signs:** `ValidationError` on `CallerInfo` instantiation because `confidence` has no default.

### Pitfall 4: Missing `outputs/` Directory at Runtime

**What goes wrong:** `run.py` writes to `outputs/results.json` but the directory doesn't exist. `open()` raises `FileNotFoundError`.

**How to avoid:** Use `Path("outputs").mkdir(parents=True, exist_ok=True)` before writing output files.

**Warning signs:** Pipeline runs but produces no output file with a silent error.

---

## Code Examples

### E.164 Normalization (Both Sides)

```python
# Source: phonenumbers library docs (official)
import phonenumbers
from phonenumbers import PhoneNumberFormat

def normalize_phone(raw: str | None) -> str | None:
    if raw is None:
        return None
    try:
        parsed = phonenumbers.parse(raw, "DE")
        return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        return raw
```

Calling `normalize_phone("+49 152 11223456")` → `"+4915211223456"`
Calling `normalize_phone("+4915211223456")` → `"+4915211223456"`
Calling `normalize_phone("015211223456")` → `"+4915211223456"`

All three normalize to the same value — this is why both sides must be normalized.

### Multi-Value Match with NFC Normalization

```python
# Source: project pattern
import unicodedata

def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    return unicodedata.normalize("NFC", value).casefold().strip()

def matches_field(field: str, predicted, ground_truth_value) -> bool:
    norm_pred = normalize_phone(predicted) if field == "phone_number" \
                else normalize_text(predicted)
    if ground_truth_value is None:
        return norm_pred is None
    if isinstance(ground_truth_value, list):
        return norm_pred in [
            normalize_phone(v) if field == "phone_number" else normalize_text(v)
            for v in ground_truth_value
        ]
    gt_norm = normalize_phone(ground_truth_value) if field == "phone_number" \
              else normalize_text(ground_truth_value)
    return norm_pred == gt_norm
```

### Pydantic v2 Optional Fields

```python
# Source: Pydantic v2 docs — Optional fields require explicit default
from typing import Optional
from pydantic import BaseModel, Field

class CallerInfo(BaseModel):
    first_name: Optional[str] = None          # Field not required at instantiation
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    confidence: dict[str, float] = Field(default_factory=dict)
```

Note: `Optional[str]` without `= None` will fail in Pydantic v2 — the field is required. This is a common v1→v2 migration gotcha.

### uv pyproject.toml with src layout

```toml
[project]
name = "phonebot-challenge"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "pydantic>=2.12.5",
    "phonenumbers>=9.0.26",
    "rich>=14.3.3",
    "python-dotenv>=1.2.2",
]

[project.optional-dependencies]
dev = ["pytest>=9.0.2"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/phonebot"]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `Optional[str]` means nullable only in Pydantic v1 | Pydantic v2: `Optional[str]` still means `str | None` but requires explicit `= None` default | Pydantic v2.0 (2023) | Must add `= None` to every nullable field or Pydantic raises validation errors |
| `str.lower()` for case-insensitive comparison | `str.casefold()` for Unicode-safe folding | Python 3.3+ | `"ß".casefold()` → `"ss"` which is the correct comparison for German; `.lower()` leaves `ß` unchanged |
| `phonenumbers` 8.x | `phonenumbers` 9.x (major bump) | 2025 | API unchanged for `parse()` and `format_number()` — no migration needed; 9.x adds updated phone number databases |
| `json.dumps` defaults (`ensure_ascii=True`) | `json.dumps(..., ensure_ascii=False)` | N/A (always been available) | German umlauts in output JSON are human-readable, not `\u00fc` escape sequences |

---

## Open Questions

1. **Module path for `python -m evaluation.metrics`**
   - What we know: Code lives at `src/phonebot/evaluation/metrics.py`; decision D-01 locks the `src/phonebot/` layout
   - What's unclear: Whether success criterion `uv run python -m evaluation.metrics` means a top-level `evaluation/` module or whether `phonebot.evaluation.metrics` is acceptable
   - Recommendation: Use `uv run python -m phonebot.evaluation.metrics` as the implementation; the planner should document this as the canonical command and note the discrepancy in the task plan

2. **`confidence` field interaction with `with_structured_output`**
   - What we know: Phase 1 defines `confidence: dict[str, float]` on CallerInfo; Phase 3 uses `llm.with_structured_output(CallerInfo)`
   - What's unclear: Whether LangChain/Anthropic's tool-use mechanism will pass the `confidence` dict schema to the LLM and how the LLM is expected to populate it
   - Recommendation: Define `confidence` in Phase 1 as specified; validate in Phase 3 that it doesn't break structured output. Consider marking it `exclude=True` from schema export if needed.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | INFRA-01 | Yes | 0.6.5 | — |
| Python 3.13 | INFRA-01 | Yes | 3.13.12 | — |
| phonenumbers | EVAL-03 | Via pip/uv install | 9.0.26 (PyPI) | None — required by EVAL-03 |
| rich | D-04 | Via pip/uv install | 14.3.3 (PyPI) | None — locked decision |
| data/ground_truth.json | EVAL-01 | Yes | Confirmed present | — |
| data/recordings/ | INFRA-02 (referenced) | Yes | 30 WAV files present | — |

**Missing dependencies with no fallback:** None — all required packages install via `uv add`.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | None — Wave 0 task creates `pyproject.toml` with `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_evaluation_metrics.py -x` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | `uv run python run.py --help` exits 0 with usage text | smoke | `uv run python run.py --help` | Wave 0 creates `run.py` |
| INFRA-02 | CLI args `--model`, `--recordings-dir`, `--output` parsed correctly | unit | `uv run pytest tests/test_cli.py -x` | Wave 0 creates test |
| EVAL-01 | `compute_metrics()` returns per-field accuracy dict for 30 recordings | unit | `uv run pytest tests/test_evaluation_metrics.py::test_compute_metrics -x` | Wave 0 creates test |
| EVAL-02 | `matches_field()` returns True when predicted matches any item in list | unit | `uv run pytest tests/test_evaluation_metrics.py::test_multi_value_match -x` | Wave 0 creates test |
| EVAL-03 | `normalize_phone()` normalizes `"015211223456"` to same E.164 as `"+49 152 11223456"` | unit | `uv run pytest tests/test_evaluation_metrics.py::test_phone_normalization -x` | Wave 0 creates test |
| EVAL-04 | `normalize_text()` makes `"Schröder"` == `"schroder"` after NFC+casefold | unit | `uv run pytest tests/test_evaluation_metrics.py::test_text_normalization -x` | Wave 0 creates test |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_evaluation_metrics.py -x`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before transitioning to Phase 2

### Wave 0 Gaps

- [ ] `tests/test_evaluation_metrics.py` — covers EVAL-01, EVAL-02, EVAL-03, EVAL-04
- [ ] `tests/test_cli.py` — covers INFRA-02
- [ ] `tests/__init__.py` — empty file
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` — sets `testpaths = ["tests"]`

---

## Sources

### Primary (HIGH confidence)

- `data/ground_truth.json` — directly inspected; all 30 records, scalar string values, E.164 phone format confirmed
- [phonenumbers PyPI](https://pypi.org/project/phonenumbers/) — version 9.0.26 confirmed current; `parse()` + `format_number()` API unchanged from 8.x
- [Pydantic v2 docs — Optional fields](https://docs.pydantic.dev/latest/concepts/models/#required-optional-fields) — `Optional[str]` requires `= None` default in v2
- [uv project documentation](https://docs.astral.sh/uv/guides/projects/) — `uv init --package`, `src/` layout, `pyproject.toml` PEP 621 format
- [Rich library docs](https://rich.readthedocs.io/) — `Console`, `Table`, `Live` APIs; version 14.3.3 confirmed current
- [Python unicodedata docs](https://docs.python.org/3/library/unicodedata.html) — `normalize("NFC", ...)` — stdlib, no install needed
- `.planning/research/STACK.md` — verified stack versions, CallerInfo Pydantic pattern
- `.planning/research/PITFALLS.md` — Pitfall 2 (eval exact-match), Pitfall 3 (confabulation typing), Pitfall 4 (phone format), Pitfall 6 (umlaut encoding)

### Secondary (MEDIUM confidence)

- `.planning/research/FEATURES.md` — feature dependency tree and multi-value normalization requirements
- `.planning/research/SUMMARY.md` — Phase 1 scope and deliverables description

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all package versions verified via `pip index versions` on current PyPI
- Ground truth schema: HIGH — directly inspected the file
- Architecture patterns: HIGH — standard Pydantic v2 and uv patterns; no novel integrations in Phase 1
- Pitfalls: HIGH — grounded in direct ground truth inspection and known Pydantic v2 behaviors
- Module path question: LOW — ambiguity in success criterion wording; requires planner to pick an interpretation

**Research date:** 2026-03-26
**Valid until:** 2026-06-26 (stable stack — phonenumbers, pydantic, rich are all mature; uv API is stable)
