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
            "(ae, oe, ue, ss). Return null if not stated."
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
