# Phase 3: Extraction Pipeline - Research

**Researched:** 2026-03-27
**Domain:** LangGraph pipeline + LangChain Anthropic structured output + German spoken-form extraction
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Prompt strategy for spoken-form**
- D-01: Expand CallerInfo Field descriptions with exact Deepgram output patterns observed in Phase 2 smart_format analysis (phone digits appear space-separated as "4 9 1 7 6", email spoken as "Name Punkt Name at Domain Punkt com")
- D-02: Patterns go in per-field descriptions (not class docstring) — per Phase 1 D-02/D-11, field descriptions ARE the per-field extraction instructions
- D-03: Reference exact Deepgram output patterns from the 30 transcripts, not general German conventions — maximally grounded in real data
- D-04: Full transcript sent to LLM (no speaker filtering) — diarization is unreliable per Phase 2 finding
- D-05: Extract names as-transcribed — if Deepgram outputs "Gassia" for "García", extract "Gassia". Do not attempt spelling correction. Avoids hallucination.

**LangGraph node design**
- D-06: Graph topology: `START → transcribe → extract → END` with typed `PipelineState`
- D-07: Transcribe node loads cached JSON from `data/transcripts/` — falls back to Deepgram API only on cache miss. Does not re-transcribe by default.
- D-08: Extract node uses LangChain `model.with_structured_output(CallerInfo)` for Pydantic schema → JSON mode automatically
- D-09: One recording per graph invocation — outer loop iterates 30x with async concurrency. Simpler state, easier debugging, natural per-recording tracing for Phoenix in Phase 4.
- D-10: Pydantic validation inline in extract node via `with_structured_output` — no separate validate node. Phase 7 adds retry logic (EXT-04) later.

**Baseline model choice**
- D-11: Claude Sonnet 4.6 only for Phase 3 baseline — use CLI default `--model claude-sonnet-4-6`. Phase 5 introduces open-source model comparison.

**Results output structure**
- D-12: `outputs/results.json` contains: each entry as `{id, caller_info (with confidence), model, timestamp}` plus top-level run metadata `{model, total_recordings, duration}`
- D-13: `run.py` auto-evaluates after extraction — extracts all 30, calls `compute_metrics`, prints Rich accuracy table to console. Single command for full pipeline + results. Matches success criteria.

### Claude's Discretion
- Exact LangGraph state schema field names and types
- Async concurrency implementation details for the outer loop
- How to extract transcript text from cached Deepgram JSON structure
- Rich table formatting for the accuracy report
- Error handling for individual recording failures (skip and continue vs fail fast)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXT-01 | Pipeline extracts first_name, last_name, email, phone_number from each transcript via LLM structured output | `with_structured_output(CallerInfo)` pattern, LangGraph extract node |
| EXT-02 | Extraction uses Pydantic BaseModel with class docstring as system prompt and Field descriptions as per-field extraction instructions | CallerInfo model enhancement, langchain-anthropic `with_structured_output` passes schema via JSON mode |
| EXT-03 | Pipeline is orchestrated via LangGraph with typed state (transcribe -> extract -> validate flow) | StateGraph + TypedDict PipelineState, START/END edges, compile + ainvoke |
| EXT-05 | Extraction prompt explicitly handles German spoken-form phone numbers and email addresses | CallerInfo field description updates grounded in `docs/smart_format_analysis.md` patterns |
| QUAL-01 | Extraction returns `None` (not hallucinated values) when field is not present in transcript | Verified via unit test with synthetic no-field transcript; CallerInfo field descriptions explicitly instruct null return |
</phase_requirements>

---

## Summary

Phase 3 adds three new things to the existing codebase: (1) an `extract.py` module with a LangGraph graph, (2) enhanced CallerInfo field descriptions grounded in real Deepgram output patterns, and (3) a wired `run.py` that runs extraction + evaluation end-to-end. The foundation is already solid — Phase 1 and 2 delivered the CallerInfo schema, evaluation harness, and 30 cached transcripts. Phase 3 is primarily assembly work.

The key technical insight from Phase 2 is that Deepgram's `smart_format` for German does NOT pre-normalize phone numbers or email addresses. All 30 transcripts contain phone numbers as space-separated individual digit characters (`plus 4 9 1 5 2 1 1 2 2 3 4 5 6`) and email addresses as spoken components (`Johanna Punkt Schmidt at Gmail Punkt com`). Every Field description in CallerInfo must address this unconditionally — the LLM must do the full normalization.

The QUAL-01 requirement (null not hallucinated) is verified via a unit test that sends a synthetic transcript with no phone/email and asserts null return. All 30 actual recordings contain all four fields, so QUAL-01 cannot be verified against live data — a unit test is the right approach.

**Primary recommendation:** Install `langgraph>=1.1.3` and `langchain-anthropic>=1.4.0`, add an `extract.py` module alongside `transcribe.py`, enhance CallerInfo field descriptions with exact transcript patterns, and wire `run.py` to invoke the graph 30x concurrently with `asyncio.Semaphore`.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langgraph | 1.1.3 (latest) | Graph orchestration: StateGraph, START, END, compile, ainvoke | Locked by project constraint (EXT-03) |
| langchain-anthropic | 1.4.0 (latest) | ChatAnthropic + `with_structured_output(CallerInfo)` | Locked by project (D-08, D-11) |
| langchain-core | 1.2.22 (latest) | HumanMessage, SystemMessage types used by langchain-anthropic | Pulled as transitive dep of langchain-anthropic |
| pydantic | 2.12.5 (already installed) | CallerInfo BaseModel + validation | Already in project |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio (stdlib) | built-in | Semaphore-bounded concurrency for 30 graph invocations | Outer loop in run.py |
| python-dotenv | 1.2.2 (already installed) | Load ANTHROPIC_API_KEY from .env | Already in project |
| rich | 14.3.3 (already installed) | Rich Table for accuracy report to console | Already in project |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| langchain-anthropic | anthropic SDK directly | anthropic SDK has no `with_structured_output`; would require manual prompt building and JSON parsing |
| TypedDict for PipelineState | Pydantic BaseModel for state | TypedDict is lighter, no runtime overhead, partial dict returns work naturally in LangGraph nodes — recommended for internal state |

**Installation:**
```bash
uv add langgraph>=1.1.3 langchain-anthropic>=1.4.0
```

**Version verification (performed 2026-03-27):**
```
langgraph:           1.1.3  (PyPI latest)
langchain-anthropic: 1.4.0  (PyPI latest)
langchain-core:      1.2.22 (transitive dep)
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/phonebot/
├── models/
│   └── caller_info.py      # MODIFY: enhance field descriptions with Deepgram patterns
├── pipeline/
│   ├── transcribe.py       # EXISTING: cache-loading already has get_transcript_text()
│   └── extract.py          # NEW: LangGraph graph + PipelineState + extract node
├── evaluation/
│   └── metrics.py          # EXISTING: compute_metrics, load_ground_truth unchanged
run.py                      # MODIFY: wire pipeline + evaluation, print Rich table
outputs/
└── results.json            # NEW: created at runtime by run.py
```

### Pattern 1: LangGraph StateGraph with TypedDict

The PipelineState TypedDict holds exactly what one recording's processing needs.
One graph invocation per recording — outer loop handles the 30x iteration.

```python
# Source: https://docs.langchain.com/oss/python/langgraph/graph-api
from typing import Optional
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

class PipelineState(TypedDict):
    recording_id: str               # e.g. "call_01"
    transcript_path: str            # path to cached JSON
    transcript_text: Optional[str]  # filled by transcribe node
    caller_info: Optional[dict]     # filled by extract node (CallerInfo.model_dump())

builder = StateGraph(PipelineState)
builder.add_node("transcribe", transcribe_node)
builder.add_node("extract", extract_node)
builder.add_edge(START, "transcribe")
builder.add_edge("transcribe", "extract")
builder.add_edge("extract", END)
pipeline = builder.compile()
```

### Pattern 2: Async Node Functions

Both nodes are async to support ainvoke. Transcribe node uses existing
`get_transcript_text()` from `transcribe.py` — no new logic needed.

```python
# Source: docs.langchain.com/oss/python/langgraph/graph-api
async def transcribe_node(state: PipelineState) -> dict:
    """Load transcript text from cache (or call Deepgram API on miss)."""
    from phonebot.pipeline.transcribe import get_transcript_text
    from pathlib import Path
    cache_path = Path("data/transcripts") / f"{state['recording_id']}.json"
    if not cache_path.exists():
        # Fallback: transcribe via API (D-07)
        # ... call Deepgram async API ...
        pass
    text = get_transcript_text(cache_path)
    return {"transcript_text": text}

async def extract_node(state: PipelineState) -> dict:
    """Extract CallerInfo from transcript text using LLM structured output."""
    from langchain_anthropic import ChatAnthropic
    from phonebot.models.caller_info import CallerInfo
    model = ChatAnthropic(model="claude-sonnet-4-6")
    structured_model = model.with_structured_output(CallerInfo)
    result: CallerInfo = await structured_model.ainvoke(state["transcript_text"])
    return {"caller_info": result.model_dump()}
```

### Pattern 3: with_structured_output for Pydantic

LangChain passes the Pydantic schema to Anthropic's native structured output feature.
The class docstring becomes the system-level extraction context; Field descriptions
become per-field extraction instructions. This is exactly what D-08 and EXT-02 require.

```python
# Source: https://docs.langchain.com/oss/python/integrations/chat/anthropic
from langchain_anthropic import ChatAnthropic
from phonebot.models.caller_info import CallerInfo

model = ChatAnthropic(model="claude-sonnet-4-6")
structured_model = model.with_structured_output(CallerInfo)

# Synchronous:
result = structured_model.invoke("transcript text here")
# Async:
result = await structured_model.ainvoke("transcript text here")
# Returns a CallerInfo instance directly (not a dict)
```

**Note on `method` parameter:** langchain-anthropic 1.4.0 supports `method="json_schema"` for
Anthropic's native structured output. However, the default (without specifying `method`) also
works and produces valid CallerInfo objects. The `method="json_schema"` flag is worth specifying
explicitly for robustness as it forces schema compliance.

### Pattern 4: Concurrent Outer Loop with Semaphore

Run 30 graph invocations concurrently, bounded by Semaphore to avoid API rate limits.
Follows the existing pattern from `transcribe.py` (CONCURRENCY env var).

```python
# Pattern mirrors existing transcribe.py concurrency pattern
import asyncio
from datetime import datetime

EXTRACT_CONCURRENCY = int(os.getenv("EXTRACT_CONCURRENCY", "5"))

async def run_pipeline(recording_ids: list[str], model: str) -> list[dict]:
    semaphore = asyncio.Semaphore(EXTRACT_CONCURRENCY)
    start_time = datetime.utcnow()

    async def process_one(recording_id: str) -> dict:
        async with semaphore:
            state = await pipeline.ainvoke({
                "recording_id": recording_id,
                "transcript_path": f"data/transcripts/{recording_id}.json",
                "transcript_text": None,
                "caller_info": None,
            })
        return {
            "id": recording_id,
            "caller_info": state["caller_info"],
            "model": model,
            "timestamp": datetime.utcnow().isoformat(),
        }

    results = await asyncio.gather(*[process_one(rid) for rid in recording_ids])
    return list(results)
```

### Pattern 5: CallerInfo Field Description Enhancement

The Phase 2 `smart_format_analysis.md` provides the exact Deepgram output patterns to embed.
Field descriptions must be self-contained extraction instructions grounded in these real patterns.

**Observed patterns from 30 transcripts:**
- Phone: always `plus X X X X X...` space-separated individual digits, e.g., `plus 4 9 1 5 2 1 1 2 2 3 4 5 6`
- Email: `[Name] Punkt [Name] at [Domain] Punkt [tld]`, e.g., `Johanna Punkt Schmidt at Gmail Punkt com`
- Email with hyphen: `h 4 7 minus Herbst at Web Punkt d e`
- Email with uppercase spelling: `SANDRA minus WEBER at t minus online Punkt d e`
- Foreign names (calls 16-30): transcribed phonetically — García → "Gassia", Lefevre → "Le Faivre", Hassan → "Armet Hassan"
- Names sometimes spelled out: `MATTHIAS` spelled letter-by-letter in transcript

**Updated field description model** (what the descriptions must convey):

```python
phone_number: Optional[str] = Field(
    None,
    description=(
        "Phone number. In these transcripts, Deepgram outputs digits one-by-one "
        "separated by spaces, preceded by 'plus': e.g., 'plus 4 9 1 5 2 1 1 2 2 3 4 5 6'. "
        "Reconstruct as E.164 format: '+4915211223456'. "
        "German mobile prefixes: 015x, 016x, 017x. Landline: 030 (Berlin), etc. "
        "Return null if no phone number is spoken."
    ),
)

email: Optional[str] = Field(
    None,
    description=(
        "Email address. In these transcripts, Deepgram does NOT assemble email addresses — "
        "they appear as spoken German: 'at' = @, 'Punkt' = '.', 'minus' = '-', "
        "'Unterstrich' = '_'. "
        "Example: 'Johanna Punkt Schmidt at Gmail Punkt com' → johanna.schmidt@gmail.com. "
        "Example: 'h 4 7 minus Herbst at Web Punkt d e' → h47-herbst@web.de. "
        "Example: 'SANDRA minus WEBER at t minus online Punkt d e' → sandra-weber@t-online.de. "
        "Return null if no email address is spoken."
    ),
)

first_name: Optional[str] = Field(
    None,
    description=(
        "Caller's first name as transcribed by Deepgram. Extract exactly as it appears "
        "in the transcript — do not attempt spelling correction. "
        "Foreign names may be phonetically approximated: García may appear as 'Gassia'. "
        "If the name is spelled out letter-by-letter (e.g., 'M A T T H I A S'), reconstruct it. "
        "Return null if no first name is spoken."
    ),
)

last_name: Optional[str] = Field(
    None,
    description=(
        "Caller's last name as transcribed by Deepgram. Extract exactly as it appears. "
        "Foreign names may be phonetically approximated: Lefevre may appear as 'Le Faivre'. "
        "If spelled out letter-by-letter, reconstruct it. "
        "Return null if no last name is spoken."
    ),
)
```

### Anti-Patterns to Avoid

- **Sending only the 'caller' speaker turns to the LLM:** Diarization is unreliable — all 8 sampled recordings returned a single speaker label. Use the full transcript (D-04).
- **Attempting name spelling correction in the prompt:** Instructs the LLM to guess what the "real" spelling is, introducing hallucinations. Extract as-transcribed (D-05). Evaluation normalization handles comparison.
- **Using a separate validate node in Phase 3:** `with_structured_output` handles Pydantic validation inline. Phase 7 adds the retry loop (EXT-04). Adding a validate node now would be premature.
- **Constructing multiple StateGraph instances per run:** Build the graph once at module import time or at `run.py` startup, then invoke it 30x. Rebuilding per recording is unnecessary overhead.
- **Calling `model.invoke()` instead of `model.ainvoke()` inside an async node:** Blocks the event loop. Always use `ainvoke` inside async nodes.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured JSON output from LLM | Custom JSON parsing + prompt engineering | `model.with_structured_output(CallerInfo)` | langchain-anthropic passes schema to Anthropic's native structured output; guaranteed schema compliance |
| Graph topology and execution | Custom pipeline class | `StateGraph` + `compile()` + `ainvoke()` | LangGraph handles state merging, node dispatch, async lifecycle; Phase 4 tracing hooks in without code changes |
| Pydantic schema → LLM instructions | Custom serialization of field descriptions | LangChain's `with_structured_output` | Automatically serializes Pydantic schema (including field descriptions) into the structured output request |
| Phone number normalization | Custom regex | `phonenumbers.parse(raw, "DE")` | Already in `metrics.py`; handles E.164 conversion, German region defaults, format variants |
| Concurrent API calls | Manual thread pool | `asyncio.Semaphore` + `asyncio.gather` | Existing pattern from `transcribe.py`; avoids rate limit errors |

**Key insight:** The hard problems (structured output, phone normalization, evaluation) are already solved. Phase 3 is assembly — connect the graph wiring to the existing modules.

---

## Common Pitfalls

### Pitfall 1: `with_structured_output` returns CallerInfo, not a dict

**What goes wrong:** Code calls `state["caller_info"].get("first_name")` after `ainvoke` returns, but `caller_info` is a `CallerInfo` instance with attribute access, not a dict.
**Why it happens:** `with_structured_output(CallerInfo)` returns an instance of the schema type directly.
**How to avoid:** Call `.model_dump()` on the CallerInfo before storing in state, or store the object and call `.model_dump()` at serialization time. The extract node should return `{"caller_info": result.model_dump()}` so state always holds a plain dict.
**Warning signs:** `AttributeError: 'CallerInfo' object has no attribute 'get'`

### Pitfall 2: ANTHROPIC_API_KEY not loaded before langchain-anthropic import

**What goes wrong:** `ChatAnthropic()` fails at instantiation with authentication error, or reads a stale env value.
**Why it happens:** Same as the Deepgram SDK pattern already documented — SDK reads the API key at import time or constructor time; `load_dotenv()` must run first.
**How to avoid:** `load_dotenv()` at the top of `extract.py` before any LangChain imports, mirroring the pattern in `transcribe.py`.
**Warning signs:** `AuthenticationError` or `Could not find ANTHROPIC_API_KEY`

### Pitfall 3: `asyncio.run()` vs `asyncio.gather()` nesting

**What goes wrong:** Calling `asyncio.run(run_pipeline(...))` inside a function that is already inside an async context raises `RuntimeError: This event loop is already running`.
**Why it happens:** `run.py` uses `asyncio.run(main())` at the bottom; the pipeline's async outer loop must be `await`ed inside the async main, not wrapped in a nested `asyncio.run()`.
**How to avoid:** Structure `run.py` with a top-level `async def main()` that `await`s the pipeline, and calls `asyncio.run(main())` once at the module level.
**Warning signs:** `RuntimeError: This event loop is already running`

### Pitfall 4: Email extraction — "Punkt" ambiguity

**What goes wrong:** LLM extracts `annika.becker@gmx..de` (double dot) from `Annika Punkt Becker at gmx Punkt Punkt d e` (call_03 transcript shows this pattern).
**Why it happens:** The transcript for call_03 contains `gmx Punkt Punkt d e` — Deepgram may duplicate "Punkt" near domain boundaries. The extraction prompt must handle this.
**How to avoid:** The email field description should note that consecutive "Punkt" tokens collapse to a single `.` — e.g., `Punkt Punkt d e` → `.de` not `..de`.
**Warning signs:** Emails with `..` in them in `outputs/results.json`

### Pitfall 5: QUAL-01 cannot be verified against live data

**What goes wrong:** All 30 recordings in `data/ground_truth.json` have all four fields populated. Verifying that `null` is returned (not hallucinated) when a field is absent cannot be done against the real recordings.
**Why it happens:** The dataset was designed with complete records.
**How to avoid:** QUAL-01 is verified via a unit test that passes a synthetic transcript (containing no phone or email) to the extract node and asserts `phone_number is None` and `email is None`. This is the correct approach.
**Warning signs:** Claiming QUAL-01 is verified by running the full 30-recording pipeline — it is not; all 30 have all fields.

### Pitfall 6: `outputs/results.json` schema vs `compute_metrics` input format

**What goes wrong:** `compute_metrics` expects `[{"id": str, "caller_info": dict}]` but `results.json` also stores `model` and `timestamp` per entry. Passing the raw `results.json` entries to `compute_metrics` works because it only uses `id` and `caller_info` keys — but any schema drift would break it silently.
**How to avoid:** Document that entries in `results.json` are a superset of what `compute_metrics` needs. The `caller_info` dict must include all four field keys (with `null` for absent fields, not omitted keys).
**Warning signs:** Metrics show 0% for a field that should have data — check that `caller_info` dict contains the key with `None` rather than omitting the key entirely.

---

## Code Examples

### Complete extract.py Module Skeleton

```python
# Source: langchain-anthropic 1.4.0 docs + LangGraph 1.1.3 docs
"""LangGraph extraction pipeline for CallerInfo from German phone bot transcripts."""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
from typing import Optional
from typing_extensions import TypedDict

from dotenv import load_dotenv
load_dotenv()  # Must precede langchain imports

from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, START, END

from phonebot.models.caller_info import CallerInfo
from phonebot.pipeline.transcribe import get_transcript_text


class PipelineState(TypedDict):
    recording_id: str
    transcript_text: Optional[str]
    caller_info: Optional[dict]


async def transcribe_node(state: PipelineState) -> dict:
    cache_path = Path("data/transcripts") / f"{state['recording_id']}.json"
    if cache_path.exists():
        text = get_transcript_text(cache_path)
    else:
        # Fallback to API — Phase 2 transcribe_all() handles this
        from phonebot.pipeline.transcribe import transcribe_all
        await transcribe_all()  # transcribes and caches
        text = get_transcript_text(cache_path)
    return {"transcript_text": text}


async def extract_node(state: PipelineState) -> dict:
    model = ChatAnthropic(model=os.getenv("PHONEBOT_MODEL", "claude-sonnet-4-6"))
    structured_model = model.with_structured_output(CallerInfo, method="json_schema")
    result: CallerInfo = await structured_model.ainvoke(state["transcript_text"])
    return {"caller_info": result.model_dump()}


def build_pipeline() -> object:
    builder = StateGraph(PipelineState)
    builder.add_node("transcribe", transcribe_node)
    builder.add_node("extract", extract_node)
    builder.add_edge(START, "transcribe")
    builder.add_edge("transcribe", "extract")
    builder.add_edge("extract", END)
    return builder.compile()


PIPELINE = build_pipeline()  # Build once at import time


async def run_pipeline(
    recording_ids: list[str],
    model_name: str = "claude-sonnet-4-6",
    concurrency: int = 5,
) -> list[dict]:
    from datetime import datetime, timezone
    semaphore = asyncio.Semaphore(concurrency)

    async def process_one(recording_id: str) -> dict:
        async with semaphore:
            state = await PIPELINE.ainvoke({
                "recording_id": recording_id,
                "transcript_text": None,
                "caller_info": None,
            })
        return {
            "id": recording_id,
            "caller_info": state["caller_info"],
            "model": model_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return list(await asyncio.gather(*[process_one(rid) for rid in recording_ids]))
```

### run.py Wiring (async main pattern)

```python
# Pattern to add to existing run.py scaffold
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()

async def main() -> None:
    # ... parse args as before ...
    # Discover recording IDs from transcripts dir
    transcript_dir = Path("data/transcripts")
    recording_ids = sorted(p.stem for p in transcript_dir.glob("call_*.json"))

    console.print(f"[bold]Extracting {len(recording_ids)} recordings...[/bold]")

    from phonebot.pipeline.extract import run_pipeline
    from phonebot.evaluation.metrics import load_ground_truth, compute_metrics
    import time

    t0 = time.monotonic()
    results = await run_pipeline(recording_ids, model_name=args.model)
    duration = time.monotonic() - t0

    # Write results.json (D-12)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": args.model,
        "total_recordings": len(results),
        "duration_seconds": round(duration, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    console.print(f"Results written to {output_path}")

    # Evaluate (D-13)
    gt = load_ground_truth(Path("data/ground_truth.json"))
    metrics = compute_metrics(results, gt)

    table = Table(title="Per-Field Accuracy")
    table.add_column("Field", style="cyan")
    table.add_column("Accuracy", style="green")
    for field, acc in metrics["per_field"].items():
        table.add_row(field, f"{acc:.0%}")
    table.add_row("[bold]Overall[/bold]", f"[bold]{metrics['overall']:.0%}[/bold]")
    console.print(table)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## QUAL-01 Verification Strategy

Since all 30 ground truth records have all four fields present, QUAL-01 ("fields absent from a
transcript return null, not a hallucinated value") is verified via a unit test:

```python
# tests/test_extract.py (new file)
import pytest

@pytest.mark.asyncio
async def test_missing_field_returns_null():
    """QUAL-01: LLM returns null for fields not present in transcript."""
    from phonebot.pipeline.extract import extract_node
    # Transcript with name only — no phone or email
    state = {
        "recording_id": "test_no_contact",
        "transcript_text": (
            "Guten Tag, mein Name ist Max Mustermann. "
            "Ich habe eine rechtliche Frage. Danke."
        ),
        "caller_info": None,
    }
    result = await extract_node(state)
    info = result["caller_info"]
    assert info["phone_number"] is None
    assert info["email"] is None
    assert info["first_name"] is not None  # "Max" should be extracted
```

**Note:** This test makes a live LLM call (ANTHROPIC_API_KEY required). Mark as `@pytest.mark.integration`
or guard with an env var check so it doesn't run in CI without credentials.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | Package management | yes | 0.6.5 | — |
| Python 3.13 | Runtime | yes | 3.13.2 | — |
| ANTHROPIC_API_KEY | ChatAnthropic | yes | Set in .env | — |
| langgraph | Graph orchestration (EXT-03) | no | Not installed | Must add via `uv add` |
| langchain-anthropic | with_structured_output (D-08) | no | Not installed | Must add via `uv add` |
| pydantic 2.x | CallerInfo model | yes | 2.12.5 | — |
| data/transcripts/*.json | Transcribe node cache (D-07) | yes | 30 files present | Deepgram API fallback |
| data/ground_truth.json | compute_metrics | yes | Present | — |

**Missing dependencies with no fallback:**
- `langgraph>=1.1.3` — must install before any pipeline code runs
- `langchain-anthropic>=1.4.0` — must install before any extraction runs

**Missing dependencies with fallback:**
- None (Deepgram transcripts are cached, API key is set)

---

## Validation Architecture

> `workflow.nyquist_validation` is absent from `.planning/config.json` — treated as enabled.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| EXT-01 | Extract 4 fields from transcript | integration | `uv run pytest tests/test_extract.py -x -q` | no — Wave 0 |
| EXT-02 | CallerInfo docstring/Field descriptions used as prompts | unit | `uv run pytest tests/test_extract.py::test_caller_info_schema -x` | no — Wave 0 |
| EXT-03 | Graph topology: START→transcribe→extract→END | unit | `uv run pytest tests/test_extract.py::test_graph_topology -x` | no — Wave 0 |
| EXT-05 | Field descriptions handle German spoken-form | unit | `uv run pytest tests/test_extract.py::test_field_descriptions_contain_patterns -x` | no — Wave 0 |
| QUAL-01 | Absent fields return null | integration | `uv run pytest tests/test_extract.py::test_missing_field_returns_null -x` | no — Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/ -x -q` (38 existing tests + new unit tests, < 5s)
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- `tests/test_extract.py` — covers EXT-01, EXT-02, EXT-03, EXT-05, QUAL-01
  - Unit tests (no LLM): topology check, field description content assertions
  - Integration tests (LLM required): `test_missing_field_returns_null`, `test_extracts_from_real_transcript`
  - Guard integration tests with `@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), ...)`

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LangChain `with_structured_output` with `tool_calling` | `method="json_schema"` with Anthropic native structured output | langchain-anthropic 1.1.0+ | Guaranteed schema compliance; no partial outputs |
| `response.to_json()` in deepgram-sdk | `response.model_dump_json()` | deepgram-sdk v6 | Already handled in transcribe.py |
| LangGraph 0.x `StateGraph` with separate message reducers | LangGraph 1.x `StateGraph` with TypedDict, direct dict returns from nodes | LangGraph 1.0 (Sep 2025) | Cleaner API; nodes return plain dicts, state merged automatically |

**Deprecated/outdated:**
- `PrerecordedOptions` in deepgram-sdk: removed in v6; already handled in transcribe.py
- `langchain` monolith package: split into `langchain-core`, `langchain-anthropic`, etc.; use package-specific installs

---

## Open Questions

1. **Does `with_structured_output` pass the Pydantic docstring as a system message?**
   - What we know: LangChain's `with_structured_output` serializes the Pydantic JSON schema (which includes field descriptions). The class docstring is part of the JSON schema `description` field.
   - What's unclear: Whether langchain-anthropic 1.4.0 specifically passes the class docstring as a separate system prompt or embeds it in the schema description.
   - Recommendation: Verify empirically by calling `model.with_structured_output(CallerInfo).invoke("test")` and checking the Anthropic API request payload. If the docstring is not passed as system prompt, add an explicit `SystemMessage` to the invoke call. This is LOW risk — Anthropic's structured output with schema description should work either way.

2. **`confidence` field in CallerInfo — will `with_structured_output` populate it?**
   - What we know: `CallerInfo` has `confidence: dict[str, float]` with `default_factory=dict`. The LLM might populate it, or return an empty dict.
   - What's unclear: Whether asking the LLM to self-report confidence is reliable enough to be worth including in Phase 3.
   - Recommendation: Keep the field in the schema (it's already there, removing it would be a schema change), but do not require it for Phase 3 success criteria. QUAL-02 (low-confidence flagging) is deferred to Phase 7.

---

## Project Constraints (from CLAUDE.md)

No `CLAUDE.md` was found in the project root. No project-specific constraints to enforce beyond those documented in the CONTEXT.md decisions above.

---

## Sources

### Primary (HIGH confidence)

- LangChain official docs (`https://docs.langchain.com/oss/python/langgraph/graph-api`) — StateGraph, TypedDict state, add_node, add_edge, START, END, compile, ainvoke
- LangChain Anthropic docs (`https://docs.langchain.com/oss/python/integrations/chat/anthropic`) — `with_structured_output` with Pydantic, `method="json_schema"`
- PyPI index — version verification for langgraph 1.1.3, langchain-anthropic 1.4.0, langchain-core 1.2.22 (verified 2026-03-27)
- `docs/smart_format_analysis.md` — Empirical Deepgram output patterns from all 30 recordings (Phase 2 artifact, HIGH confidence)
- Existing codebase inspection — CallerInfo schema, transcribe.py patterns, metrics.py API, run.py scaffold

### Secondary (MEDIUM confidence)

- Ground truth inspection (`data/ground_truth.json`) — confirmed all 30 recordings have all 4 fields non-null; QUAL-01 requires synthetic test

### Tertiary (LOW confidence)

- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified against PyPI index 2026-03-27
- Architecture: HIGH — grounded in existing codebase + official LangGraph/LangChain docs
- CallerInfo field descriptions: HIGH — grounded in empirical `docs/smart_format_analysis.md` (30 recordings)
- Pitfalls: HIGH — derived from existing code inspection and Phase 2 findings
- QUAL-01 strategy: HIGH — verified empirically that all 30 ground truth records have all fields

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (LangGraph/LangChain move fast; re-verify if extending beyond 30 days)
