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
            "Caller's first name as transcribed by Deepgram. Extract exactly as it appears "
            "in the transcript -- do not attempt spelling correction. "
            "Foreign names may be phonetically approximated (e.g., Garcia may appear as 'Gassia'). "
            "If the name is spelled out letter-by-letter (e.g., 'M A T T H I A S'), reconstruct it as 'Matthias'. "
            "Return null if no first name is spoken."
        ),
    )
    last_name: Optional[str] = Field(
        None,
        description=(
            "Caller's last name as transcribed by Deepgram. Extract exactly as it appears. "
            "Foreign names may be phonetically approximated (e.g., Lefevre may appear as 'Le Faivre'). "
            "If spelled out letter-by-letter, reconstruct it. "
            "Names with 'Doppel' prefix mean doubled letter (e.g., 'Doppel-f' = 'ff'). "
            "Return null if no last name is spoken."
        ),
    )
    email: Optional[str] = Field(
        None,
        description=(
            "Email address. In these transcripts, Deepgram does NOT assemble email addresses -- "
            "they appear as spoken German components: 'at' = @, 'Punkt' = '.', 'minus' = '-', "
            "'Unterstrich' = '_'. "
            "Example: 'Johanna Punkt Schmidt at Gmail Punkt com' -> johanna.schmidt@gmail.com. "
            "Example: 'h 4 7 minus Herbst at Web Punkt d e' -> h47-herbst@web.de. "
            "Example: 'SANDRA minus WEBER at t minus online Punkt d e' -> sandra-weber@t-online.de. "
            "Consecutive 'Punkt' tokens collapse to a single dot (e.g., 'Punkt Punkt d e' -> '.de' not '..de'). "
            "Lowercase the entire email address. "
            "Return null if no email address is spoken."
        ),
    )
    phone_number: Optional[str] = Field(
        None,
        description=(
            "Phone number. In these transcripts, Deepgram outputs individual digits separated by spaces, "
            "preceded by 'plus': e.g., 'plus 4 9 1 5 2 1 1 2 2 3 4 5 6'. "
            "Reconstruct as E.164 format by concatenating: '+4915211223456'. "
            "German mobile prefixes: 015x, 016x, 017x. Landline examples: 030 (Berlin), 040 (Hamburg). "
            "Return null if no phone number is spoken."
        ),
    )
    confidence: dict[str, float] = Field(
        default_factory=dict,
        description=(
            'REQUIRED: Provide a confidence score between 0.0 and 1.0 for EVERY field '
            "you extracted (non-null). Keys must match field names exactly. "
            'Example: {"first_name": 0.95, "last_name": 0.8, "email": 0.4}. '
            "Only omit a key if that field's value is null."
        ),
    )
