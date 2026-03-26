"""Async batch transcription module with JSON caching via Deepgram Nova-3.

Uses deepgram-sdk v6 (Fern-generated) which exposes direct keyword args on
transcribe_file() instead of PrerecordedOptions. Response objects are Pydantic
models serialized with model_dump_json().
"""
import asyncio
import json
import os
from pathlib import Path

from deepgram import AsyncDeepgramClient
from dotenv import load_dotenv

load_dotenv()

TRANSCRIPT_DIR = Path("data/transcripts")
CONCURRENCY = int(os.getenv("DEEPGRAM_CONCURRENCY", "5"))


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
