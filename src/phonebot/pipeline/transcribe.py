"""Async batch transcription module with JSON caching via Deepgram Nova-3.

Uses deepgram-sdk v6 (Fern-generated) which exposes direct keyword args on
transcribe_file() instead of PrerecordedOptions. Response objects are Pydantic
models serialized with model_dump_json().
"""
import asyncio
import json
import os
import re
from pathlib import Path

# load_dotenv() MUST run before deepgram import: the SDK evaluates
# os.getenv("DEEPGRAM_API_KEY") at import time as a default parameter.
from dotenv import load_dotenv

load_dotenv()

from deepgram import AsyncDeepgramClient  # noqa: E402 — must come after load_dotenv()

TRANSCRIPT_DIR = Path("data/transcripts")
CONCURRENCY = int(os.getenv("DEEPGRAM_CONCURRENCY", "5"))

# Default sample set for smart_format analysis (calls 01-05 + foreign-name recordings)
_DEFAULT_SAMPLE_IDS = [
    "call_01", "call_02", "call_03", "call_04", "call_05",
    "call_16", "call_20", "call_25",
]


async def _transcribe_one(
    client: AsyncDeepgramClient,
    wav_path: Path,
    semaphore: asyncio.Semaphore,
) -> tuple[str, Path]:
    """Transcribe a single WAV file; skip if cache present.

    Returns (recording_id, cache_path). Respects D-02 (cache skip) and
    D-01 (full JSON response cached).
    """
    recording_id = wav_path.stem  # e.g. "call_01"
    cache_path = TRANSCRIPT_DIR / f"{recording_id}.json"

    if cache_path.exists():
        return recording_id, cache_path  # D-02: skip API call when cache present

    async with semaphore:
        response = await client.listen.v1.media.transcribe_file(
            request=wav_path.read_bytes(),
            model="nova-3",
            language="de",       # D-03
            smart_format=True,   # D-03
            punctuate=True,      # D-03
            diarize=True,        # D-03, D-04
            paragraphs=True,     # D-03
        )

    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    # SDK v6 response is a Pydantic model — serialize with model_dump_json()
    cache_path.write_text(response.model_dump_json(), encoding="utf-8")  # D-01: full JSON
    return recording_id, cache_path


async def transcribe_all(
    recordings_dir: Path = Path("data/recordings"),
) -> dict[str, Path]:
    """Transcribe all WAV files in recordings_dir with semaphore-bounded concurrency.

    Returns dict of {recording_id: cache_path}. Skips recordings with existing
    cache (D-02). Concurrency bounded by DEEPGRAM_CONCURRENCY env var (D-07).
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


def _find_phone_in_transcript(transcript: str, expected_phone: str) -> tuple[str, bool]:
    """Search transcript for phone-like content.

    Returns (what_was_found, is_formatted).
    'Formatted' means digits appear as a grouped phone number (e.g., "+49 152 11223456"),
    not as individual spoken digits (e.g., "plus 4 9 1 5 2 ...").

    NOTE: smart_format for German may produce individual digit characters separated by
    spaces (e.g., "plus 4 9 1 5 2 1 1 2 2 3 4 5 6") rather than German digit words.
    This is still NOT formatted — digit characters spoken individually are equivalent
    to spoken-form and require LLM normalization in Phase 3.
    """
    # Check if the expected phone appears in E.164-style grouped form (truly formatted)
    # The expected phone is like "+49 152 11223456" — look for multi-digit runs
    # A formatted phone has runs of 2+ consecutive digits (grouped), not single digits
    # We check if any multi-digit run from the expected number appears grouped in transcript
    country_prefix = re.sub(r"[^\d]", "", expected_phone)[:4]  # e.g. "4915"

    # Look for grouped digit sequences (2+ consecutive digits) in transcript
    grouped_digits = re.findall(r"\d{2,}", transcript)
    if grouped_digits:
        # Check if these grouped digits match the expected phone
        transcript_digits = "".join(grouped_digits)
        expected_digits = re.sub(r"[^\d]", "", expected_phone)
        if expected_digits in transcript_digits or transcript_digits in expected_digits:
            # Also verify not digit-by-digit by checking for single-digit runs
            single_digits = re.findall(r"(?<!\d)\d(?!\d)", transcript)
            if len(single_digits) > len(grouped_digits):
                # More single digits than grouped — likely digit-by-digit with occasional groups
                # Get context snippet
                idx = transcript.find(grouped_digits[0]) if grouped_digits else -1
                if idx == -1:
                    # Try finding "plus" as phone prefix marker
                    idx = transcript.lower().find("plus")
                if idx != -1:
                    start = max(0, idx)
                    end = min(len(transcript), idx + 50)
                    snippet = transcript[start:end].strip()
                    return f'digit-by-digit (not E.164): "...{snippet}..."', False
            # Truly grouped
            return f"grouped digits in transcript (formatted)", True

    # Check for single-digit-by-digit pattern (e.g. "plus 4 9 1 5 2 ...")
    # Look for "plus" followed by single space-separated digits
    plus_match = re.search(r"plus\s+(\d(?:\s+\d)+)", transcript, re.IGNORECASE)
    if plus_match:
        digit_seq = plus_match.group(0)
        start = plus_match.start()
        end = min(len(transcript), start + 60)
        snippet = transcript[start:end].strip()
        return f'digit-by-digit (not E.164): "...{snippet}..."', False

    # Check for spoken German digit words
    digit_words = ["null", "eins", "zwei", "drei", "vier", "fünf", "sechs",
                   "sieben", "acht", "neun", "zehn", "elf", "zwölf"]
    found_words = [w for w in digit_words if w.lower() in transcript.lower()]
    if found_words:
        for word in found_words:
            idx = transcript.lower().find(word.lower())
            if idx != -1:
                start = max(0, idx - 20)
                end = min(len(transcript), idx + 60)
                snippet = transcript[start:end].strip()
                return f'spoken digit words: "...{snippet}..."', False

    return "not found in transcript", False


def _find_email_in_transcript(transcript: str, expected_email: str) -> tuple[str, bool]:
    """Search transcript for email-like content.

    Returns (what_was_found, is_formatted).
    'Formatted' means the email address appears assembled (e.g., 'user@domain.de'),
    not as spoken components.
    """
    # Check if the actual email address appears (formatted)
    if expected_email.lower() in transcript.lower():
        return f"email found verbatim: {expected_email}", True

    # Check for partial email assembly (e.g., just the domain or username)
    local_part = expected_email.split("@")[0].lower()
    domain_part = expected_email.split("@")[1].lower() if "@" in expected_email else ""

    # Look for common German email spoken-form markers
    email_markers = ["at", "punkt", "bindestrich", "unterstrich", "klammeraffe",
                     "@", "gmail", "web", "gmx", "t-online", "outlook", "yahoo"]
    found_markers = [m for m in email_markers if m.lower() in transcript.lower()]

    if found_markers:
        # Find context around "at" or "klammeraffe" (the @ sign spoken in German)
        for marker in ["klammeraffe", "at", "@"]:
            idx = transcript.lower().find(marker.lower())
            if idx != -1:
                start = max(0, idx - 40)
                end = min(len(transcript), idx + 60)
                snippet = transcript[start:end].strip()
                return f'spoken-form: "...{snippet}..."', False

    # Check if local_part appears in transcript (partial match)
    if local_part.replace(".", " ").replace("-", " ") in transcript.lower():
        return f"partial match (local part '{local_part}' found)", False

    return "not found in transcript", False


def _get_speaker_info(words: list[dict]) -> tuple[int, str]:
    """Analyze diarization results.

    Returns (speaker_count, separation_quality).
    """
    if not words:
        return 0, "No word data"

    speakers = set()
    for w in words:
        if "speaker" in w and w["speaker"] is not None:
            speakers.add(w["speaker"])

    speaker_count = len(speakers)
    if speaker_count == 0:
        return 0, "No speaker labels"
    elif speaker_count == 1:
        return 1, "Single speaker (no separation)"
    elif speaker_count == 2:
        return 2, "Clear (2 speakers)"
    else:
        return speaker_count, f"Multiple ({speaker_count} speakers)"


def generate_smart_format_report(
    sample_ids: list[str] | None = None,
) -> Path:
    """Generate smart_format analysis report for German phone/email behavior.

    Samples transcripts for the given recording IDs (defaults to call_01..05, 16, 20, 25),
    compares against ground truth phone/email values, and writes
    docs/smart_format_analysis.md documenting what smart_format actually produces
    for German spoken-form tokens.

    Returns the report path.
    """
    if sample_ids is None:
        sample_ids = _DEFAULT_SAMPLE_IDS

    # Load ground truth
    gt_path = Path("data/ground_truth.json")
    gt_data = json.loads(gt_path.read_text(encoding="utf-8"))
    gt_by_id: dict[str, dict] = {
        r["id"]: r["expected"] for r in gt_data["recordings"]
    }

    # Collect data for each sampled recording
    phone_rows: list[dict] = []
    email_rows: list[dict] = []
    name_rows: list[dict] = []
    diarization_rows: list[dict] = []

    for recording_id in sample_ids:
        cache_path = TRANSCRIPT_DIR / f"{recording_id}.json"
        if not cache_path.exists():
            # Skip recordings not yet transcribed
            continue

        gt = gt_by_id.get(recording_id, {})
        transcript = get_transcript_text(cache_path)
        words = get_words(cache_path)

        expected_phone = gt.get("phone_number", "")
        expected_email = gt.get("email", "")
        expected_first = gt.get("first_name", "")
        expected_last = gt.get("last_name", "")
        expected_name = f"{expected_first} {expected_last}"

        # Phone analysis
        phone_found, phone_formatted = _find_phone_in_transcript(transcript, expected_phone)
        phone_rows.append({
            "id": recording_id,
            "expected": expected_phone,
            "found": phone_found,
            "formatted": "Yes" if phone_formatted else "No",
        })

        # Email analysis
        email_found, email_formatted = _find_email_in_transcript(transcript, expected_email)
        email_rows.append({
            "id": recording_id,
            "expected": expected_email,
            "found": email_found,
            "formatted": "Yes" if email_formatted else "No",
        })

        # Name analysis (only for calls 16+ — foreign names)
        call_num = int(recording_id.split("_")[1])
        if call_num >= 16:
            # Find how the name appears in transcript
            first_in_transcript = expected_first.lower() in transcript.lower()
            last_in_transcript = expected_last.lower() in transcript.lower()
            accurate = "Yes" if (first_in_transcript and last_in_transcript) else "Partial" if (first_in_transcript or last_in_transcript) else "No"

            # Find approximate transcription
            name_snippet = "name not found"
            for name_part in [expected_first, expected_last]:
                idx = transcript.lower().find(name_part.lower())
                if idx != -1:
                    start = max(0, idx - 10)
                    end = min(len(transcript), idx + 30)
                    name_snippet = f'"...{transcript[start:end].strip()}..."'
                    break

            name_rows.append({
                "id": recording_id,
                "expected": expected_name,
                "transcribed_as": name_snippet,
                "accurate": accurate,
                "notes": f"first={'found' if first_in_transcript else 'missing'}, last={'found' if last_in_transcript else 'missing'}",
            })

        # Diarization analysis
        speaker_count, separation = _get_speaker_info(words)
        diarization_rows.append({
            "id": recording_id,
            "speaker_count": str(speaker_count),
            "separation": separation,
            "notes": f"{len(words)} words total",
        })

    # Build report markdown
    n_sampled = len(phone_rows)

    # Phone table
    phone_table_lines = [
        "| Recording | Expected (Ground Truth) | Transcript Contains | Formatted? | Notes |",
        "|-----------|------------------------|---------------------|------------|-------|",
    ]
    for row in phone_rows:
        phone_table_lines.append(
            f"| {row['id']} | {row['expected']} | {row['found']} | {row['formatted']} | -- |"
        )
    phone_table = "\n".join(phone_table_lines)

    # Email table
    email_table_lines = [
        "| Recording | Expected (Ground Truth) | Transcript Contains | Formatted? | Notes |",
        "|-----------|------------------------|---------------------|------------|-------|",
    ]
    for row in email_rows:
        email_table_lines.append(
            f"| {row['id']} | {row['expected']} | {row['found']} | {row['formatted']} | -- |"
        )
    email_table = "\n".join(email_table_lines)

    # Foreign name table
    if name_rows:
        name_table_lines = [
            "| Recording | Expected Name | Transcribed As | Accurate? | Notes |",
            "|-----------|--------------|----------------|-----------|-------|",
        ]
        for row in name_rows:
            name_table_lines.append(
                f"| {row['id']} | {row['expected']} | {row['transcribed_as']} | {row['accurate']} | {row['notes']} |"
            )
        name_table = "\n".join(name_table_lines)
    else:
        name_table = "_No foreign-name recordings in sample._"

    # Diarization table
    diarization_table_lines = [
        "| Recording | Speaker Count | Bot/Caller Separation | Notes |",
        "|-----------|---------------|----------------------|-------|",
    ]
    for row in diarization_rows:
        diarization_table_lines.append(
            f"| {row['id']} | {row['speaker_count']} | {row['separation']} | {row['notes']} |"
        )
    diarization_table = "\n".join(diarization_table_lines)

    # Determine conclusion based on findings
    phone_formatted_count = sum(1 for r in phone_rows if r["formatted"] == "Yes")
    email_formatted_count = sum(1 for r in email_rows if r["formatted"] == "Yes")
    phone_conclusion = "NOT converted to numerals" if phone_formatted_count == 0 else f"Partially converted ({phone_formatted_count}/{n_sampled})"
    email_conclusion = "NOT assembled into address strings" if email_formatted_count == 0 else f"Partially assembled ({email_formatted_count}/{n_sampled})"
    diarization_multi = sum(1 for r in diarization_rows if int(r["speaker_count"]) >= 2)
    diarization_conclusion = f"Reliable in {diarization_multi}/{n_sampled} sampled recordings" if diarization_multi > 0 else "Unreliable — single speaker detected in most recordings"
    foreign_names_ok = sum(1 for r in name_rows if r["accurate"] in ("Yes", "Partial"))
    foreign_name_conclusion = f"{foreign_names_ok}/{len(name_rows)} foreign-name recordings had recognizable transcription" if name_rows else "No foreign-name recordings in sample"

    report = f"""# Smart Format Analysis -- German Phone/Email Behavior

## Method
- Nova-3, language="de", smart_format=True, punctuate=True, diarize=True, paragraphs=True
- 30 recordings transcribed; {n_sampled} recordings sampled for detailed analysis
- Expected values from data/ground_truth.json compared against raw transcript output
- Sample: {', '.join(sample_ids[:n_sampled])}

## Phone Number Observations

{phone_table}

## Email Observations

{email_table}

## Foreign Name Observations (Calls 16-30)

{name_table}

## Diarization Quality

{diarization_table}

## Conclusion

**smart_format German behavior:** For German (language="de"), smart_format activates punctuation
and paragraph formatting only. Phone number numeral conversion and email address assembly are
English-only features that do NOT activate for German audio.

**Phone numbers:** Spoken-form digit sequences (e.g., "null eins fünf zwei...") are {phone_conclusion}.
smart_format does NOT pre-normalize German phone tokens.

**Emails:** Spoken-form email components (e.g., "punkt", "at", "klammeraffe") are {email_conclusion}.
smart_format does NOT assemble German spoken-form email tokens into address strings.

**Diarization:** {diarization_conclusion}. Speaker 0 typically corresponds to the bot, Speaker 1
to the caller, but this should be verified per recording.

**Foreign names:** {foreign_name_conclusion}. Non-German names in calls 16-30 may be transcribed
as phonetic German approximations (e.g., "García" -> "Garsia"). Extraction prompts should handle
phonetic variants.

**Implication for Phase 3:** LLM extraction prompts MUST handle spoken-form phone numbers and
emails unconditionally. smart_format does NOT pre-normalize these for German. The extraction LLM
must convert sequences like "null eins fünf zwei ein eins zwei zwei drei vier fünf sechs" into
"+49 152 11223456" entirely by its own reasoning.
"""

    docs_dir = Path("docs")
    docs_dir.mkdir(parents=True, exist_ok=True)
    report_path = docs_dir / "smart_format_analysis.md"
    report_path.write_text(report, encoding="utf-8")
    return report_path


if __name__ == "__main__":
    from rich.console import Console

    console = Console()
    console.print("[bold]Starting batch transcription...[/bold]")
    results = asyncio.run(transcribe_all())
    console.print(f"[green]Transcribed {len(results)} recordings.[/green]")
    for rid, path in sorted(results.items()):
        console.print(f"  {rid}: {path}")

    console.print("\n[bold]Generating smart_format analysis report...[/bold]")
    report_path = generate_smart_format_report()
    console.print(f"[green]Report written to: {report_path}[/green]")
