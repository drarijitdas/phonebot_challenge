"""Stage 1: Transcript preprocessing.

Rule-based (no LLM) preprocessing that:
  - Uses Deepgram diarization to separate bot vs caller utterances
  - Strips bot greetings and prompts to reduce noise
  - Identifies caller-relevant segments for downstream extraction

The phone bot transcripts show a clear pattern: Speaker 0 is typically the bot,
Speaker 1 is the caller. By filtering to caller segments, we dramatically
reduce noise for the extraction LLM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from phonebot.pipeline.transcribe import get_transcript_text, get_words


@dataclass
class PreprocessedTranscript:
    """Result of transcript preprocessing."""

    full_text: str                    # Original full transcript
    caller_segments: list[str]        # Caller-only text segments
    caller_text: str                  # Joined caller text
    bot_segments: list[str]           # Bot text segments (for reference)
    num_speakers: int                 # Number of detected speakers
    transcript_length: int            # Original transcript char length
    caller_text_length: int           # Caller-only text char length


# Common bot greeting patterns (German)
_BOT_PATTERNS = [
    re.compile(r"(?i)guten\s+tag.*willkommen"),
    re.compile(r"(?i)wie\s+kann\s+ich\s+ihnen\s+helfen"),
    re.compile(r"(?i)vielen\s+dank\s+für\s+ihren?\s+anruf"),
    re.compile(r"(?i)auf\s+wiederhören"),
    re.compile(r"(?i)bitte\s+nennen\s+sie\s+mir"),
    re.compile(r"(?i)können\s+sie\s+mir.*sagen"),
    re.compile(r"(?i)ich\s+habe\s+(das\s+)?notiert"),
]


def _is_bot_utterance(text: str) -> bool:
    """Heuristic: check if text matches common bot patterns."""
    return any(p.search(text) for p in _BOT_PATTERNS)


def _segment_by_speaker(words: list[dict]) -> dict[int, list[str]]:
    """Group words into speaker segments.

    Returns dict mapping speaker_id → list of text segments.
    Each segment is a contiguous run of words from the same speaker.
    """
    if not words:
        return {}

    segments: dict[int, list[str]] = {}
    current_speaker = words[0].get("speaker", 0)
    current_words: list[str] = []

    for w in words:
        speaker = w.get("speaker", 0)
        if speaker != current_speaker:
            if current_words:
                segments.setdefault(current_speaker, []).append(" ".join(current_words))
            current_words = []
            current_speaker = speaker
        current_words.append(w.get("word", w.get("punctuated_word", "")))

    if current_words:
        segments.setdefault(current_speaker, []).append(" ".join(current_words))

    return segments


def preprocess_transcript(
    recording_id: str,
    transcripts_dir: Path = Path("data/transcripts"),
    caller_speaker: int | None = None,
) -> PreprocessedTranscript:
    """Preprocess a transcript by separating bot and caller utterances.

    Args:
        recording_id: Recording identifier (e.g., "call_01").
        transcripts_dir: Directory with cached transcript JSON files.
        caller_speaker: Override speaker ID for the caller. If None,
            auto-detects by assuming the speaker who says contact info
            (email markers, phone numbers) is the caller.

    Returns:
        PreprocessedTranscript with separated segments.
    """
    cache_path = transcripts_dir / f"{recording_id}.json"
    full_text = get_transcript_text(cache_path)
    words = get_words(cache_path)

    segments = _segment_by_speaker(words)
    num_speakers = len(segments)

    if caller_speaker is not None:
        pass
    elif num_speakers <= 1:
        caller_speaker = 0
    else:
        email_markers = {"at", "klammeraffe", "punkt"}
        best_speaker = 0
        best_score = 0
        for spk, segs in segments.items():
            text_lower = " ".join(segs).lower()
            score = sum(1 for m in email_markers if m in text_lower)
            # Also count digit sequences (phone numbers)
            score += len(re.findall(r"\d{2,}", text_lower))
            if score > best_score:
                best_score = score
                best_speaker = spk
        caller_speaker = best_speaker

    caller_segs = segments.get(caller_speaker, [])
    bot_speakers = [s for s in segments if s != caller_speaker]
    bot_segs = []
    for s in bot_speakers:
        bot_segs.extend(segments.get(s, []))

    caller_text = " ".join(caller_segs)

    return PreprocessedTranscript(
        full_text=full_text,
        caller_segments=caller_segs,
        caller_text=caller_text,
        bot_segments=bot_segs,
        num_speakers=num_speakers,
        transcript_length=len(full_text),
        caller_text_length=len(caller_text),
    )
