# Phase 2: Transcription - Research

**Researched:** 2026-03-26
**Domain:** Deepgram Nova-3 Python SDK v6 — German pre-recorded batch transcription with full JSON caching
**Confidence:** HIGH (SDK API verified via official docs + PyPI; smart_format German limitation confirmed via official Deepgram discussion #541)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Full Deepgram JSON response cached per recording at `data/transcripts/call_XX.json` — preserves transcript text, word-level confidence, timings, alternatives, and metadata
- **D-02:** Cache check on file existence — re-running the pipeline skips Deepgram API calls when JSON cache files exist
- **D-03:** `language="de"` with all four formatting features enabled: `smart_format=True`, `punctuate=True`, `diarize=True`, `paragraphs=True`
- **D-04:** Diarization enabled for speaker separation (bot vs caller) — may aid extraction by isolating caller speech
- **D-05:** Dedicated markdown report at `docs/smart_format_analysis.md` with comparison tables showing spoken-form input vs Deepgram output for phone numbers and emails across 5+ recordings
- **D-06:** Report includes a conclusion section stating whether smart_format reliably converts German spoken-form tokens, feeding directly into Phase 3 extraction prompt design
- **D-07:** `asyncio.Semaphore` with configurable limit via `DEEPGRAM_CONCURRENCY` env var (default 5). All 30 recordings dispatched via `asyncio.gather` with semaphore-bounded concurrency.

### Claude's Discretion
- Exact Deepgram SDK API usage and response parsing
- Cache file naming convention details (call_01.json vs other schemes)
- Internal module structure within `src/phonebot/`
- Which 5+ recordings to sample for the smart_format analysis

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STT-01 | Pipeline transcribes all 30 German WAV recordings via Deepgram Nova-3 with `language="de"` | SDK v6 async batch pattern documented; `AsyncDeepgramClient` with `asyncio.Semaphore` enables all 30 concurrently |
| STT-02 | Pipeline verifies smart_format behavior on German and documents which formatters activate | **Empirically confirmed:** smart_format for German activates punctuation + paragraphs only — phone/email formatting is English-only; numerals NOT active for German (Deepgram discussion #541) |
| STT-03 | Transcripts are cached to disk to avoid redundant Deepgram API calls during iteration | `response.to_json()` on SDK response object serializes full JSON; `Path.exists()` check before API call |
</phase_requirements>

---

## Summary

Phase 2 adds the transcription module to an existing project scaffold. Phase 1 delivered `src/phonebot/`, `CallerInfo` model, evaluation harness, CLI, and 30 passing tests. The pipeline directory (`src/phonebot/pipeline/__init__.py`) is a placeholder stub with a single docstring — it is ready to receive the transcription module.

The most consequential research finding is a **confirmed limitation of smart_format for German**: Deepgram's official response in community discussion #541 states that for German, smart_format activates punctuation and paragraphs only — phone number and numeral formatting are not supported. A German caller saying "null zwei null eins" will produce those spoken words verbatim in the transcript, not "0201". This is expected behavior, not a bug. The smart_format analysis report (STT-02 deliverable) should document this conclusively across 5+ recordings. Phase 3 extraction prompts must handle spoken-form phone/email tokens unconditionally — they cannot rely on smart_format to pre-normalize these.

**Ground truth inspection reveals that calls 16–30 all have non-German names** (Anderson, García, Chen, Tanaka, O'Brien, Martínez, etc.). Nova-3 may transcribe these phonetically into German sound patterns. All phone numbers in ground truth are E.164 (`+49 XXX XXXXXXXX`). The transcription module itself does not need to normalize phones — that is the evaluation harness's job — but the smart_format analysis report should document what the raw transcript produces for phone tokens across at least 5 recordings.

**Primary recommendation:** Place the transcription module at `src/phonebot/pipeline/transcribe.py`. Use `AsyncDeepgramClient` with `asyncio.Semaphore(int(os.getenv("DEEPGRAM_CONCURRENCY", "5")))`. Cache `response.to_json()` directly to `data/transcripts/call_XX.json`. Read the transcript text from `response.results.channels[0].alternatives[0].transcript` for the smart_format analysis.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| deepgram-sdk | 6.1.0 (latest as of 2026-03-26) | German speech-to-text via Nova-3 | Official SDK; v6 introduces `AsyncDeepgramClient`; verified on PyPI |
| asyncio (stdlib) | Python 3.13 stdlib | Concurrent batch transcription | No additional install; `asyncio.Semaphore` + `asyncio.gather` is the idiomatic Python pattern |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dotenv | >=1.2.2 (already installed) | Load `DEEPGRAM_API_KEY` and `DEEPGRAM_CONCURRENCY` from `.env` | Already in pyproject.toml; call `load_dotenv()` at module top |
| pathlib (stdlib) | Python 3.13 stdlib | Cache path construction and existence check | Already used throughout project |
| json (stdlib) | Python 3.13 stdlib | Parse cached JSON; `ensure_ascii=False` for umlaut safety | Already used in evaluation module |

### Installation

`deepgram-sdk` is the only new dependency for this phase:

```bash
uv add deepgram-sdk
```

Verify current version first:
```bash
uv run python -c "import deepgram; print(deepgram.__version__)"
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/phonebot/
├── pipeline/
│   ├── __init__.py          # existing placeholder stub
│   └── transcribe.py        # NEW: async batch transcription module (Phase 2)
├── models/
│   └── caller_info.py       # existing: CallerInfo Pydantic model
├── evaluation/
│   └── metrics.py           # existing: evaluation harness
├── observability/            # placeholder for Phase 4
└── prompts/                  # placeholder for Phase 6

data/
└── transcripts/             # NEW directory: 30 call_XX.json files

docs/
└── smart_format_analysis.md  # NEW: smart_format behavior report (STT-02 deliverable)
```

### Pattern 1: Async Batch Transcription with Semaphore

**What:** Use `AsyncDeepgramClient` + `asyncio.Semaphore` to dispatch all 30 recordings concurrently, bounded by `DEEPGRAM_CONCURRENCY` (default 5) to avoid rate-limit bursts.

**When to use:** Anytime you process multiple pre-recorded files and want speed without hitting Deepgram rate limits.

```python
# src/phonebot/pipeline/transcribe.py
import asyncio
import json
import os
from pathlib import Path

from deepgram import AsyncDeepgramClient, PrerecordedOptions
from dotenv import load_dotenv

load_dotenv()

TRANSCRIPT_DIR = Path("data/transcripts")
CONCURRENCY = int(os.getenv("DEEPGRAM_CONCURRENCY", "5"))


async def transcribe_one(
    client: AsyncDeepgramClient,
    wav_path: Path,
    semaphore: asyncio.Semaphore,
) -> Path:
    """Transcribe a single WAV file; skip if cache exists. Returns cache path."""
    cache_path = TRANSCRIPT_DIR / f"{wav_path.stem}.json"
    if cache_path.exists():
        return cache_path  # D-02: skip API call when cache present

    options = PrerecordedOptions(
        model="nova-3",
        language="de",         # D-03
        smart_format=True,     # D-03
        punctuate=True,        # D-03
        diarize=True,          # D-03, D-04
        paragraphs=True,       # D-03
    )

    async with semaphore:
        audio_bytes = wav_path.read_bytes()
        response = await client.listen.v1.media.transcribe_file(
            request=audio_bytes,
            options=options,
        )

    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(response.to_json(), encoding="utf-8")  # D-01: full JSON
    return cache_path


async def transcribe_all(recordings_dir: Path = Path("data/recordings")) -> list[Path]:
    """Transcribe all WAV files in recordings_dir with semaphore-bounded concurrency."""
    client = AsyncDeepgramClient()  # reads DEEPGRAM_API_KEY from env
    semaphore = asyncio.Semaphore(CONCURRENCY)
    wav_files = sorted(recordings_dir.glob("*.wav"))

    tasks = [transcribe_one(client, wav, semaphore) for wav in wav_files]
    return await asyncio.gather(*tasks)
```

**Note on API path:** Two equivalent paths exist in SDK v6:
- `client.listen.v1.media.transcribe_file(request=..., options=...)` — documented in official Deepgram docs
- `client.listen.rest.v("1").transcribe_file(payload, options)` — appears in some community examples

Use `client.listen.v1.media.transcribe_file(request=..., options=...)` as it matches the official documentation pattern (HIGH confidence).

### Pattern 2: Cache Read — Extract Transcript Text

**What:** When downstream code (LangGraph extraction, smart_format analysis) needs the transcript string, read from cached JSON rather than re-calling Deepgram.

```python
def load_transcript(cache_path: Path) -> dict:
    """Load full Deepgram JSON response from cache."""
    return json.loads(cache_path.read_text(encoding="utf-8"))

def get_transcript_text(cache_path: Path) -> str:
    """Extract plain transcript string from cached JSON."""
    data = load_transcript(cache_path)
    return data["results"]["channels"][0]["alternatives"][0]["transcript"]
```

### Pattern 3: smart_format Analysis Report

**What:** After transcription, open 5+ cached JSON files, extract the raw transcript text, and manually compare expected phone/email tokens against what Deepgram actually produced.

**Structure for `docs/smart_format_analysis.md`:**

```markdown
# Smart Format Analysis — German Phone/Email Behavior

## Method
- Nova-3, language="de", smart_format=True, punctuate=True, diarize=True, paragraphs=True
- 30 recordings transcribed; 8 recordings sampled covering names, phones, emails

## Phone Number Observations

| Recording | Spoken Input (expected) | Deepgram Output | Formatted? |
|-----------|------------------------|-----------------|------------|
| call_01   | "null eins fünf zwei..." | "null eins fünf zwei..." | No |
| ...       | ...                    | ...             | ... |

## Email Observations

| Recording | Spoken Input (expected) | Deepgram Output | Formatted? |
|-----------|------------------------|-----------------|------------|
| call_01   | "johanna punkt schmidt at gmail punkt com" | "johanna punkt schmidt at gmail punkt com" | No |
| ...       | ...                    | ...             | ... |

## Conclusion

smart_format German behavior: punctuation and paragraph formatting only.
Phone numbers: spoken-form digits are NOT converted to numerals.
Emails: spoken-form components are NOT assembled into address strings.

**Implication for Phase 3:** LLM extraction prompts MUST handle spoken-form unconditionally.
```

### Anti-Patterns to Avoid

- **Passing options as keyword args to `transcribe_file`:** The docs show `request=audio_file.read(), model="nova-3"` as keyword args, but `PrerecordedOptions` object is the correct typed pattern and future-proof. Use `PrerecordedOptions` and pass as `options=` parameter.
- **Caching only the transcript text:** D-01 explicitly requires full JSON response. Caching only the text string loses word-level confidence, timings, speaker info, and alternatives.
- **Synchronous transcription in a loop:** 30 files at ~3-8s each is 90-240s sequential. Async with semaphore reduces to ~20-50s wall time.
- **Calling `response.to_json()` without checking return type:** The SDK response object has a `to_json()` method that returns a JSON string. Write it with `Path.write_text(..., encoding="utf-8")` to ensure umlaut safety.
- **Creating `AsyncDeepgramClient` per-file inside `transcribe_one`:** Create once, share across all coroutines to reuse the HTTP connection pool.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| German speech-to-text | Custom Whisper wrapper | `deepgram-sdk` + Nova-3 | Nova-3 has dedicated German model with compound word support; Deepgram API handles audio encoding, chunking, transport |
| Concurrent HTTP requests with rate limit safety | Manual `threading.Semaphore` + `requests` | `asyncio.Semaphore` + `AsyncDeepgramClient` | SDK handles HTTP/2 connection pooling, auth headers, retries; semaphore is the only concurrency control needed |
| JSON serialization of Deepgram response | Custom dict extraction + `json.dumps` | `response.to_json()` | SDK response object serializes the full, validated response schema; DIY risks missing nested fields |
| Phone/email normalization in transcripts | Regex replacement of "punkt" → "." | Do not do this at transcription layer | smart_format already applies what it can; further normalization belongs in Phase 3 extraction prompts, not here |

**Key insight:** The transcription module's job is to produce and cache the raw Deepgram output. Normalization, extraction, and formatting correction all belong downstream.

---

## Common Pitfalls

### Pitfall 1: smart_format Does Not Format German Phone Numbers or Emails

**What goes wrong:** Assuming `smart_format=True` will convert "null zwei null eins..." to "0201..." or assemble "mueller at beispiel punkt de" into `mueller@beispiel.de` for German audio. It will not. The transcript contains the spoken German words verbatim.

**Why it happens:** Deepgram marketing copy describes smart_format capabilities in English-first terms. The API accepts the parameter without error for German, giving false confidence.

**How to avoid:** The smart_format analysis report (STT-02) must empirically confirm this across 5+ recordings and document it as the authoritative finding feeding Phase 3.

**Warning signs:** Transcripts contain "punkt", "at", "Klammeraffe", "Bindestrich" as words; phone tokens appear as "null", "eins", "zwei" sequences rather than digit strings.

**Confirmed source:** Deepgram community discussion #541 — "On non-English models, Smart Format will apply all available formatters for that language. For the majority of languages, this is currently limited to Punctuation and Paragraphs."

---

### Pitfall 2: Non-German Names in Calls 16–30

**What goes wrong:** Ground truth calls 16–30 have non-German names: Anderson, Dubois, García, Kowalski, Chen, Tanaka, O'Brien, Martínez, etc. Nova-3 may transcribe these into German phonetic approximations (e.g., "García" → "Garsia", "O'Brien" → "O Brien").

**Why it happens:** Nova-3 is trained on German speech data. Foreign proper nouns have no German text reference, so the decoder picks the most probable German near-homophone.

**How to avoid:** The smart_format analysis report should note any ASR transcription anomalies on foreign-name recordings (calls 16–30). Phase 3 extraction prompts must instruct the LLM to extract the name as transcribed, not as a German word.

**Warning signs:** Transcripts for calls 16–30 show German-looking approximations of non-German names.

---

### Pitfall 3: Response Serialization Drops Umlauts

**What goes wrong:** If the cached JSON is written without `encoding="utf-8"` or if a `json.dumps` somewhere uses `ensure_ascii=True` (the Python default), German characters like ä, ö, ü, ß are escaped as `\u00e4`, etc. Downstream string comparison fails.

**Why it happens:** Python's `json.dumps` defaults to `ensure_ascii=True`. The SDK's `response.to_json()` returns a Python string — writing it with `Path.write_text()` requires explicit `encoding="utf-8"`.

**How to avoid:** Always `Path.write_text(response.to_json(), encoding="utf-8")`. When re-loading: `json.loads(path.read_text(encoding="utf-8"))`. The evaluation harness already uses `ensure_ascii=False` (confirmed in `metrics.py`).

---

### Pitfall 4: asyncio.Semaphore Scope — Create Once, Not Per-File

**What goes wrong:** Creating a new `asyncio.Semaphore` inside the per-file coroutine means each file gets its own semaphore — no shared limit. All 30 files hit the API simultaneously.

**Why it happens:** Misplacing the semaphore instantiation.

**How to avoid:** Create the semaphore in `transcribe_all` and pass it as a parameter to each `transcribe_one` call. See code example in Pattern 1 above.

---

### Pitfall 5: Deepgram Rate Limits with 30 Concurrent Requests

**What goes wrong:** With `DEEPGRAM_CONCURRENCY=30`, all requests hit the API simultaneously and may return 429 errors.

**Why it happens:** Deepgram free/pay-as-you-go tiers have concurrency limits (typically 20-25 simultaneous requests for most plans).

**How to avoid:** Default `DEEPGRAM_CONCURRENCY=5` is conservative and safe across all Deepgram tiers. The env var allows tuning upward if the account supports it. The SDK does not auto-retry 429s in v6 — implement a short backoff wrapper if needed.

---

## Code Examples

### Full Transcription Module (verified against official docs)

```python
# src/phonebot/pipeline/transcribe.py
import asyncio
import json
import os
from pathlib import Path

from deepgram import AsyncDeepgramClient, PrerecordedOptions
from dotenv import load_dotenv

load_dotenv()

TRANSCRIPT_DIR = Path("data/transcripts")
CONCURRENCY = int(os.getenv("DEEPGRAM_CONCURRENCY", "5"))


async def _transcribe_one(
    client: AsyncDeepgramClient,
    wav_path: Path,
    semaphore: asyncio.Semaphore,
) -> tuple[str, Path]:
    """Transcribe single WAV; skip if cache present. Returns (recording_id, cache_path)."""
    recording_id = wav_path.stem  # "call_01"
    cache_path = TRANSCRIPT_DIR / f"{recording_id}.json"

    if cache_path.exists():
        return recording_id, cache_path

    options = PrerecordedOptions(
        model="nova-3",
        language="de",
        smart_format=True,
        punctuate=True,
        diarize=True,
        paragraphs=True,
    )

    async with semaphore:
        response = await client.listen.v1.media.transcribe_file(
            request=wav_path.read_bytes(),
            options=options,
        )

    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(response.to_json(), encoding="utf-8")
    return recording_id, cache_path


async def transcribe_all(
    recordings_dir: Path = Path("data/recordings"),
) -> dict[str, Path]:
    """
    Transcribe all WAV files. Returns dict of {recording_id: cache_path}.
    Skips recordings with existing cache (D-02).
    """
    client = AsyncDeepgramClient()  # reads DEEPGRAM_API_KEY from env
    semaphore = asyncio.Semaphore(CONCURRENCY)
    wav_files = sorted(recordings_dir.glob("call_*.wav"))

    results = await asyncio.gather(
        *[_transcribe_one(client, wav, semaphore) for wav in wav_files]
    )
    return dict(results)


def get_transcript_text(cache_path: Path) -> str:
    """Extract plain transcript string from cached Deepgram JSON."""
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    return data["results"]["channels"][0]["alternatives"][0]["transcript"]


def get_words(cache_path: Path) -> list[dict]:
    """Extract word-level data (timing, confidence, speaker) from cached JSON."""
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    return data["results"]["channels"][0]["alternatives"][0]["words"]
```

### Deepgram Response JSON Structure (confirmed via official docs)

```json
{
  "metadata": {...},
  "results": {
    "channels": [
      {
        "alternatives": [
          {
            "transcript": "...",
            "confidence": 0.99,
            "words": [
              {
                "word": "hallo",
                "start": 0.08,
                "end": 0.32,
                "confidence": 0.9991,
                "speaker": 0,
                "speaker_confidence": 0.82,
                "punctuated_word": "Hallo,"
              }
            ],
            "paragraphs": {...}
          }
        ]
      }
    ],
    "utterances": [...]
  }
}
```

---

## Ground Truth Inspection

Inspected `data/ground_truth.json` (30 recordings):

- **Schema:** `{"recordings": [{"id": "call_01", "file": "call_01.wav", "expected": {"first_name": ..., "last_name": ..., "email": ..., "phone_number": ...}}]}`
- **Multi-value entries:** None — all 30 recordings have scalar expected values
- **Null fields:** None — all 30 recordings have all four fields populated
- **Phone format:** All 30 use E.164 format (`+49 XXX XXXXXXXX` with spaces) — evaluation harness normalizes via `phonenumbers` before comparison (already implemented in Phase 1)
- **Foreign names (calls 16–30):** Anderson, Dubois, García, Kowalski, Chen, Silva, Andersson, Tanaka, Martínez, O'Brien — these will stress Nova-3 German ASR on foreign phonetics
- **German-domain emails:** Many use `web.de`, `gmx.de`, `gmx.net`, `t-online.de`, `freenet.de` — the bot will have spelled these out in German ("t bindestrich online punkt de")

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Deepgram v3/v4 `transcription.prerecorded()` dict-based API | v6 `AsyncDeepgramClient` + `PrerecordedOptions` dataclass | Feb 2026 (v6 release) | Breaking change — old code fails with v6 |
| `PrerecordedOptions` passed as second positional arg | `options=` keyword arg to `transcribe_file` | v6 | Correct pattern per official docs |
| `smart_format` for German phones/emails | Use LLM extraction for spoken-form tokens | N/A (always true) | Phase 3 extraction prompts must handle spoken German unconditionally |

**Deprecated/outdated:**
- `deepgram.listen.prerecorded.v("1")`: Legacy path still works but docs now show `listen.v1.media`
- `deepgram.transcription.prerecorded()`: Pre-v3 API — completely removed

---

## Open Questions

1. **Which API path is canonical in v6: `listen.v1.media` vs `listen.rest.v("1")`?**
   - What we know: Official docs show `listen.v1.media.transcribe_file(request=..., ...)`. Community examples show `listen.rest.v("1").transcribe_file(payload, options)`.
   - What's unclear: Whether these are equivalent aliases or one is newer.
   - Recommendation: Use `listen.v1.media` (matches official docs). If it raises an `AttributeError` at runtime, fall back to `listen.rest.v("1")`.

2. **Does `response.to_json()` return a valid JSON string for all 30 recordings?**
   - What we know: SDK v6 response objects have a `to_json()` method confirmed in docs.
   - What's unclear: Whether it handles edge cases (empty transcript, diarization failure).
   - Recommendation: Wrap the cache-write in `try/except` and log failures without crashing the batch.

3. **Does diarize=True reliably separate bot vs caller in all 30 recordings?**
   - What we know: Diarization is language-agnostic per Deepgram docs. Works with German.
   - What's unclear: Whether all 30 recordings have clear audio quality sufficient for speaker separation.
   - Recommendation: The smart_format analysis report should note diarization quality on a sample of 5 recordings (e.g., whether speaker 0 = bot and speaker 1 = caller consistently).

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 | All code | Yes | 3.13 (project spec) | — |
| deepgram-sdk | STT-01 | Not yet installed | 6.1.0 on PyPI | — (required) |
| DEEPGRAM_API_KEY | API calls | Unknown (in .env) | — | Blocks transcription; must be set |
| WAV files `data/recordings/call_01.wav` through `call_30.wav` | STT-01 | Yes (confirmed) | — | — |
| `data/transcripts/` directory | STT-03 cache | Not yet created | — | Created by `mkdir(parents=True, exist_ok=True)` |
| `docs/` directory | STT-02 report | Not yet confirmed | — | Created by `mkdir(parents=True, exist_ok=True)` |

**Missing dependencies with no fallback:**
- `DEEPGRAM_API_KEY` must be set in `.env` before any transcription task can execute.

**Missing dependencies with fallback:**
- `data/transcripts/` and `docs/`: auto-created by code; no manual step needed.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 (already installed, `tests/` in pyproject.toml) |
| Config file | `[tool.pytest.ini_options]` in `pyproject.toml` — `testpaths = ["tests"]` |
| Quick run command | `uv run pytest tests/test_transcribe.py -x` |
| Full suite command | `uv run pytest -x` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STT-01 | `transcribe_all()` calls Deepgram for files without cache | unit (mock) | `uv run pytest tests/test_transcribe.py::test_calls_deepgram_when_no_cache -x` | No — Wave 0 |
| STT-01 | `transcribe_all()` returns 30 cache paths for 30 WAV files | integration (live API) | `uv run pytest tests/test_transcribe.py::test_transcribes_all_30 -x` | No — Wave 0 |
| STT-02 | `docs/smart_format_analysis.md` exists after transcription run | smoke | `uv run pytest tests/test_transcribe.py::test_analysis_report_exists -x` | No — Wave 0 |
| STT-03 | Second run skips Deepgram API calls when cache exists | unit (mock) | `uv run pytest tests/test_transcribe.py::test_skips_existing_cache -x` | No — Wave 0 |
| STT-03 | Cache JSON contains `results.channels[0].alternatives[0].transcript` key | unit | `uv run pytest tests/test_transcribe.py::test_cache_json_structure -x` | No — Wave 0 |

**Note:** STT-01 integration test requires `DEEPGRAM_API_KEY` and live API access. It should be skipped in CI unless the key is present. Use `pytest.mark.skipif(not os.getenv("DEEPGRAM_API_KEY"), ...)` or a separate `tests/integration/` directory.

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_transcribe.py -x` (unit/mock tests only, no API key needed)
- **Per wave merge:** `uv run pytest -x` (full suite including evaluation harness)
- **Phase gate:** Full suite green + `data/transcripts/` contains 30 JSON files + `docs/smart_format_analysis.md` exists

### Wave 0 Gaps

- [ ] `tests/test_transcribe.py` — covers STT-01 (mock Deepgram), STT-02 (report exists), STT-03 (cache skip logic)
- [ ] `data/transcripts/` directory — auto-created at runtime; no pre-creation needed
- [ ] `docs/` directory — auto-created at runtime

---

## Sources

### Primary (HIGH confidence)
- PyPI: `pypi.org/project/deepgram-sdk/` — version 6.1.0, published 2026-03-26
- Deepgram pre-recorded audio docs: `developers.deepgram.com/docs/pre-recorded-audio` — `client.listen.v1.media.transcribe_file(request=..., model=...)` pattern
- Deepgram smart_format docs: `developers.deepgram.com/docs/smart-format` — "On non-English models, Smart Format will apply all available formatters for that language. This will always include punctuation and paragraphs."
- Deepgram feature overview: `developers.deepgram.com/docs/stt-pre-recorded-feature-overview` — diarize and punctuate support "All available" languages including German

### Secondary (MEDIUM confidence)
- Deepgram GitHub discussion #541: `github.com/orgs/deepgram/discussions/541` — official Deepgram collaborator confirms German smart_format = punctuation + paragraphs only; numerals NOT supported
- Deepgram GitHub SDK README: `github.com/deepgram/deepgram-python-sdk` — `AsyncDeepgramClient` async pattern confirmed for v6

### Tertiary (LOW confidence — flag for validation at runtime)
- Community examples showing `listen.rest.v("1")` path: may be an alias; validate against `listen.v1.media` at runtime

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — deepgram-sdk v6.1.0 verified on PyPI 2026-03-26
- Architecture: HIGH — AsyncDeepgramClient + Semaphore pattern confirmed via official docs; PrerecordedOptions pattern confirmed
- smart_format German behavior: HIGH — confirmed via official Deepgram response in community discussion #541
- Diarization with German: HIGH — Deepgram documents diarization as "language agnostic"
- Exact API path (`listen.v1.media` vs `listen.rest.v1`): MEDIUM — docs show `listen.v1.media`; community shows both; treat as open question

**Research date:** 2026-03-26
**Valid until:** 2026-04-25 (stable SDK; smart_format German behavior unlikely to change without announcement)
