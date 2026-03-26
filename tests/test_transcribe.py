"""Unit tests for transcription module with mocked Deepgram client.

deepgram-sdk v6 (Fern-generated) exposes direct keyword args on
transcribe_file() with no PrerecordedOptions wrapper. Response objects are
Pydantic models; the mock uses model_dump_json() for serialization.
"""
import asyncio
import importlib
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

FAKE_DEEPGRAM_JSON = json.dumps(
    {
        "metadata": {"request_id": "fake"},
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "Hallo, mein Name ist Schmidt.",
                            "confidence": 0.98,
                            "words": [
                                {
                                    "word": "hallo",
                                    "start": 0.08,
                                    "end": 0.32,
                                    "confidence": 0.99,
                                    "speaker": 0,
                                    "speaker_confidence": 0.82,
                                    "punctuated_word": "Hallo,",
                                }
                            ],
                        }
                    ]
                }
            ]
        },
    },
    ensure_ascii=False,
)


def _make_mock_client():
    """Create a mock AsyncDeepgramClient that returns a response with FAKE_DEEPGRAM_JSON.

    In SDK v6 the response is a Pydantic model; we mock model_dump_json() to
    return the fake JSON string.
    """
    mock_response = MagicMock()
    mock_response.model_dump_json.return_value = FAKE_DEEPGRAM_JSON

    mock_transcribe = AsyncMock(return_value=mock_response)

    mock_client = MagicMock()
    mock_client.listen.v1.media.transcribe_file = mock_transcribe

    return mock_client, mock_transcribe


# ---------------------------------------------------------------------------
# Cache skip
# ---------------------------------------------------------------------------


def test_skips_existing_cache(tmp_path):
    """_transcribe_one returns immediately without calling Deepgram if cache exists."""
    from phonebot.pipeline import transcribe

    # Pre-create a fake cache file
    cache_file = tmp_path / "call_01.json"
    cache_file.write_text(FAKE_DEEPGRAM_JSON, encoding="utf-8")

    mock_client, mock_transcribe = _make_mock_client()
    semaphore = asyncio.Semaphore(5)

    wav_path = tmp_path / "call_01.wav"
    wav_path.write_bytes(b"fake-wav-data")

    with patch.object(transcribe, "TRANSCRIPT_DIR", tmp_path):
        result = asyncio.run(
            transcribe._transcribe_one(mock_client, wav_path, semaphore)
        )

    mock_transcribe.assert_not_called()
    recording_id, returned_path = result
    assert recording_id == "call_01"
    assert returned_path == cache_file


# ---------------------------------------------------------------------------
# Deepgram API call with correct options
# ---------------------------------------------------------------------------


def test_calls_deepgram_when_no_cache(tmp_path):
    """_transcribe_one calls Deepgram transcribe_file when no cache exists.

    SDK v6 passes options as direct keyword args (no PrerecordedOptions wrapper).
    """
    from phonebot.pipeline import transcribe

    mock_client, mock_transcribe = _make_mock_client()
    semaphore = asyncio.Semaphore(5)

    wav_path = tmp_path / "call_02.wav"
    wav_path.write_bytes(b"fake-wav-data")

    with patch.object(transcribe, "TRANSCRIPT_DIR", tmp_path):
        asyncio.run(transcribe._transcribe_one(mock_client, wav_path, semaphore))

    mock_transcribe.assert_called_once()
    call_kwargs = mock_transcribe.call_args.kwargs

    assert call_kwargs["model"] == "nova-3"
    assert call_kwargs["language"] == "de"
    assert call_kwargs["smart_format"] is True
    assert call_kwargs["punctuate"] is True
    assert call_kwargs["diarize"] is True
    assert call_kwargs["paragraphs"] is True


# ---------------------------------------------------------------------------
# Cache JSON structure
# ---------------------------------------------------------------------------


def test_cache_json_structure(tmp_path):
    """Cache written by _transcribe_one contains the expected Deepgram JSON path."""
    from phonebot.pipeline import transcribe

    mock_client, _ = _make_mock_client()
    semaphore = asyncio.Semaphore(5)

    wav_path = tmp_path / "call_03.wav"
    wav_path.write_bytes(b"fake-wav-data")

    with patch.object(transcribe, "TRANSCRIPT_DIR", tmp_path):
        asyncio.run(transcribe._transcribe_one(mock_client, wav_path, semaphore))

    cache_file = tmp_path / "call_03.json"
    assert cache_file.exists(), "Cache file was not written"

    data = json.loads(cache_file.read_text(encoding="utf-8"))
    transcript = data["results"]["channels"][0]["alternatives"][0]["transcript"]
    assert transcript == "Hallo, mein Name ist Schmidt."


# ---------------------------------------------------------------------------
# get_transcript_text
# ---------------------------------------------------------------------------


def test_get_transcript_text(tmp_path):
    """get_transcript_text extracts plain transcript string from cached JSON."""
    from phonebot.pipeline.transcribe import get_transcript_text

    cache_file = tmp_path / "call_04.json"
    cache_file.write_text(FAKE_DEEPGRAM_JSON, encoding="utf-8")

    result = get_transcript_text(cache_file)
    assert result == "Hallo, mein Name ist Schmidt."


# ---------------------------------------------------------------------------
# get_words
# ---------------------------------------------------------------------------


def test_get_words(tmp_path):
    """get_words extracts word-level list from cached JSON."""
    from phonebot.pipeline.transcribe import get_words

    cache_file = tmp_path / "call_05.json"
    cache_file.write_text(FAKE_DEEPGRAM_JSON, encoding="utf-8")

    words = get_words(cache_file)
    assert isinstance(words, list)
    assert len(words) == 1
    assert words[0]["word"] == "hallo"


# ---------------------------------------------------------------------------
# transcribe_all concurrency
# ---------------------------------------------------------------------------


def test_transcribe_all_dispatches_concurrently(tmp_path):
    """transcribe_all dispatches all WAV files via asyncio.gather."""
    from phonebot.pipeline import transcribe

    mock_client, mock_transcribe = _make_mock_client()

    # Create 3 fake WAV files
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir()
    for i in range(1, 4):
        wav = recordings_dir / f"call_{i:02d}.wav"
        wav.write_bytes(b"fake-wav-data")

    transcripts_dir = tmp_path / "transcripts"

    with (
        patch.object(transcribe, "TRANSCRIPT_DIR", transcripts_dir),
        patch("phonebot.pipeline.transcribe.AsyncDeepgramClient", return_value=mock_client),
    ):
        result = asyncio.run(transcribe.transcribe_all(recordings_dir=recordings_dir))

    assert isinstance(result, dict)
    assert len(result) == 3
    assert mock_transcribe.call_count == 3


# ---------------------------------------------------------------------------
# Concurrency configuration
# ---------------------------------------------------------------------------


def test_concurrency_default():
    """Default DEEPGRAM_CONCURRENCY is 5 when env var is not set."""
    import os

    # Ensure env var is absent then reimport
    original = os.environ.pop("DEEPGRAM_CONCURRENCY", None)
    try:
        # Remove cached module so it re-evaluates CONCURRENCY
        sys.modules.pop("phonebot.pipeline.transcribe", None)
        import phonebot.pipeline.transcribe as t  # noqa: PLC0415

        # Reload to pick up the env change
        importlib.reload(t)
        assert t.CONCURRENCY == 5
    finally:
        if original is not None:
            os.environ["DEEPGRAM_CONCURRENCY"] = original
        sys.modules.pop("phonebot.pipeline.transcribe", None)


def test_concurrency_env_override(monkeypatch):
    """Setting DEEPGRAM_CONCURRENCY=10 changes the semaphore limit."""
    monkeypatch.setenv("DEEPGRAM_CONCURRENCY", "10")

    sys.modules.pop("phonebot.pipeline.transcribe", None)
    import phonebot.pipeline.transcribe as t  # noqa: PLC0415

    importlib.reload(t)
    assert t.CONCURRENCY == 10

    # Cleanup for other tests
    sys.modules.pop("phonebot.pipeline.transcribe", None)
