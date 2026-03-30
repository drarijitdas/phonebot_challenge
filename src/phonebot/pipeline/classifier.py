"""Transcript difficulty classifier for intelligent pipeline routing.

Rule-based (zero LLM cost) classifier that scores transcript difficulty
before extraction begins. Used by the orchestrator to route recordings to
the appropriate pipeline:
  - EASY → v1 pipeline (fast, cheap)
  - MEDIUM → v2 with 1 critic iteration
  - HARD → v2 with 3 iterations + few-shot retrieval

Signals analyzed:
  - Presence of phone/email spoken markers
  - Transcript length and complexity
  - Speaker diarization quality
  - Foreign name indicators
  - Email complexity (hyphens, digits, foreign domains)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from phonebot.pipeline.transcribe import get_transcript_text, get_words
from phonebot.pipeline.shared import PipelineVersion


class DifficultyTier(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


# Scoring thresholds — derived from the scoring function below which assigns
# 0-2 points per signal (transcript length, speakers, foreign markers, etc.).
# A "typical" German-name, single-speaker, short transcript scores 0-3.
# International names with background noise or multiple speakers score 4-6.
# Worst-case transcripts (foreign name + low confidence + long) score 7+.
_EASY_MAX = 3       # Difficulty score 0-3 → EASY
_MEDIUM_MAX = 6     # Difficulty score 4-6 → MEDIUM
                    # Score 7+ → HARD

# German phone bot email markers
_EMAIL_MARKERS = {"at", "klammeraffe", "punkt", "bindestrich", "unterstrich"}

# German phone markers
_PHONE_MARKERS = {"plus", "null"}

# Common German first/last names (overlap with ground truth calls 1-15)
_COMMON_GERMAN_NAMES = {
    "schmidt", "müller", "weber", "fischer", "meyer", "wagner",
    "becker", "schulz", "hoffmann", "schröder", "neumann",
    "zimmermann", "koch", "richter", "krause",
}

# Indicators of non-German/foreign names
_FOREIGN_INDICATORS = {
    "buchstabieren", "buchstabiert",  # "to spell" — indicates unusual name
    "nochmal", "wiederholen",         # "again", "repeat" — difficulty indicator
}


@dataclass
class DifficultySignals:
    """Individual difficulty signals used for classification."""

    transcript_length: int = 0
    num_speakers: int = 0
    has_email_markers: bool = False
    has_phone_markers: bool = False
    email_complexity: int = 0  # 0=simple, 1=hyphen/digit, 2=foreign domain
    spelling_detected: bool = False  # Name spelled letter-by-letter
    foreign_name_indicators: int = 0
    low_confidence_words: int = 0  # Words with Deepgram confidence < 0.7
    total_words: int = 0


@dataclass
class ClassificationResult:
    """Result of transcript difficulty classification."""

    tier: DifficultyTier
    score: int  # Raw difficulty score (0-10+)
    signals: DifficultySignals
    recommended_pipeline: PipelineVersion
    recommended_ac_iterations: int  # 0 for v1, 1-3 for v2/v3
    use_few_shot: bool  # Whether to enable retrieval


def _count_speakers(words: list[dict]) -> int:
    """Count unique speakers from Deepgram word data."""
    speakers = set()
    for w in words:
        if "speaker" in w:
            speakers.add(w["speaker"])
    return len(speakers)


def _detect_spelling(transcript: str) -> bool:
    """Detect if someone is spelling a name letter-by-letter.

    Pattern: consecutive single letters separated by spaces, e.g., "M A T T H I A S"
    """
    return bool(re.search(r"(?:[A-ZÄÖÜ]\s){3,}", transcript))


def _detect_email_complexity(transcript_lower: str) -> int:
    """Score email complexity from transcript content."""
    score = 0
    if "bindestrich" in transcript_lower or "minus" in transcript_lower:
        score += 1  # Hyphenated email
    if any(f" {d} " in transcript_lower for d in "0123456789"):
        score += 1  # Digits in email
    # Foreign domain indicators
    foreign_tlds = [".fr", ".it", ".br", ".es", ".com.br"]
    if any(tld in transcript_lower for tld in foreign_tlds):
        score += 1
    return score


def classify_transcript(
    recording_id: str,
    transcripts_dir: Path = Path("data/transcripts"),
) -> ClassificationResult:
    """Classify a transcript's extraction difficulty.

    Args:
        recording_id: Recording identifier (e.g., "call_01").
        transcripts_dir: Directory with cached transcript JSON files.

    Returns:
        ClassificationResult with tier, score, signals, and routing recommendation.
    """
    cache_path = transcripts_dir / f"{recording_id}.json"

    # Load transcript data
    transcript = get_transcript_text(cache_path)
    words = get_words(cache_path)
    transcript_lower = transcript.lower()

    # Compute signals
    signals = DifficultySignals(
        transcript_length=len(transcript),
        num_speakers=_count_speakers(words),
        has_email_markers=any(m in transcript_lower for m in _EMAIL_MARKERS),
        has_phone_markers=any(m in transcript_lower for m in _PHONE_MARKERS),
        email_complexity=_detect_email_complexity(transcript_lower),
        spelling_detected=_detect_spelling(transcript),
        foreign_name_indicators=sum(1 for ind in _FOREIGN_INDICATORS if ind in transcript_lower),
        low_confidence_words=sum(1 for w in words if w.get("confidence", 1.0) < 0.7),
        total_words=len(words),
    )

    # Score computation
    score = 0

    # Long transcripts are harder (more noise, more irrelevant utterances).
    # 2000 chars ≈ 90s of speech; 4000 chars ≈ 3min — typical calls are 30-60s.
    if signals.transcript_length > 2000:
        score += 1
    if signals.transcript_length > 4000:
        score += 1

    # Email complexity
    score += signals.email_complexity

    # Spelling detection means foreign/unusual name
    if signals.spelling_detected:
        score += 2

    # Foreign name indicators
    score += signals.foreign_name_indicators

    # Low confidence words (Deepgram word.confidence < 0.7) indicate poor
    # audio quality or unusual speech patterns. >10% is notable; >20% is severe.
    low_conf_ratio = signals.low_confidence_words / max(signals.total_words, 1)
    if low_conf_ratio > 0.1:
        score += 1
    if low_conf_ratio > 0.2:
        score += 2

    # Missing markers — harder to locate information
    if not signals.has_email_markers:
        score += 1

    # Determine tier
    if score <= _EASY_MAX:
        tier = DifficultyTier.EASY
        pipeline = PipelineVersion.V1
        ac_iterations = 0
        use_few_shot = False
    elif score <= _MEDIUM_MAX:
        tier = DifficultyTier.MEDIUM
        pipeline = PipelineVersion.V2
        ac_iterations = 1
        use_few_shot = False
    else:
        tier = DifficultyTier.HARD
        pipeline = PipelineVersion.V2
        ac_iterations = 3
        use_few_shot = True

    return ClassificationResult(
        tier=tier,
        score=score,
        signals=signals,
        recommended_pipeline=pipeline,
        recommended_ac_iterations=ac_iterations,
        use_few_shot=use_few_shot,
    )


def classify_batch(
    recording_ids: list[str],
    transcripts_dir: Path = Path("data/transcripts"),
) -> dict[str, ClassificationResult]:
    """Classify all recordings and return tier distribution.

    Args:
        recording_ids: List of recording IDs to classify.
        transcripts_dir: Directory with cached transcript JSON files.

    Returns:
        Dict mapping recording_id to ClassificationResult.
    """
    return {
        rid: classify_transcript(rid, transcripts_dir)
        for rid in recording_ids
    }
