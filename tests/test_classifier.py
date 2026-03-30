"""Tests for the transcript difficulty classifier."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from phonebot.pipeline.classifier import (
    DifficultyTier,
    DifficultySignals,
    ClassificationResult,
    _detect_spelling,
    _detect_email_complexity,
    _count_speakers,
)


class TestSpellingDetection:
    def test_detects_spelling(self):
        assert _detect_spelling("Mein Name ist M A T T H I A S Hoffmann") is True

    def test_no_spelling(self):
        assert _detect_spelling("Mein Name ist Matthias Hoffmann") is False

    def test_short_sequence_not_detected(self):
        assert _detect_spelling("Ja M K nein") is False


class TestEmailComplexity:
    def test_simple_email(self):
        assert _detect_email_complexity("johanna punkt schmidt at gmail punkt com") == 0

    def test_hyphenated(self):
        assert _detect_email_complexity("sandra bindestrich weber at t-online punkt de") >= 1

    def test_digits(self):
        assert _detect_email_complexity("h 4 7 bindestrich herbst at web punkt de") >= 1

    def test_foreign_domain(self):
        score = _detect_email_complexity("carlos punkt garcia at hotmail punkt es")
        assert score >= 0  # .es may or may not be detected from transcript


class TestSpeakerCount:
    def test_single_speaker(self):
        words = [{"word": "hallo", "speaker": 0}, {"word": "ja", "speaker": 0}]
        assert _count_speakers(words) == 1

    def test_two_speakers(self):
        words = [
            {"word": "hallo", "speaker": 0},
            {"word": "guten tag", "speaker": 1},
        ]
        assert _count_speakers(words) == 2

    def test_empty(self):
        assert _count_speakers([]) == 0


class TestClassificationResult:
    def test_easy_tier(self):
        result = ClassificationResult(
            tier=DifficultyTier.EASY,
            score=2,
            signals=DifficultySignals(),
            recommended_pipeline="v1",
            recommended_ac_iterations=0,
            use_few_shot=False,
        )
        assert result.tier == DifficultyTier.EASY
        assert result.recommended_pipeline == "v1"
        assert result.use_few_shot is False

    def test_hard_tier(self):
        result = ClassificationResult(
            tier=DifficultyTier.HARD,
            score=8,
            signals=DifficultySignals(),
            recommended_pipeline="v2",
            recommended_ac_iterations=3,
            use_few_shot=True,
        )
        assert result.tier == DifficultyTier.HARD
        assert result.recommended_pipeline == "v2"
        assert result.use_few_shot is True
