"""Stage 2: Entity recognition.

A focused LLM call that ONLY identifies WHERE in the transcript each entity
appears. Returns text segments containing each field, with confidence scores.
This is cheaper than full extraction because the model just scans and quotes,
without reasoning about normalization rules.

Separates "finding" from "extracting" — a key architectural improvement
over the monolithic extract_node.
"""
from __future__ import annotations

import os
from typing import Optional

from pydantic import BaseModel, Field

from phonebot.models.model_registry import get_model


class EntitySegment(BaseModel):
    """A located entity segment in the transcript."""

    field: str = Field(
        description="Field name: first_name, last_name, email, or phone_number"
    )
    text_segment: str = Field(description="The exact transcript text containing this entity")
    confidence: float = Field(
        description="Confidence that this segment contains the entity (0.0-1.0)",
        ge=0.0,
        le=1.0,
    )
    context: Optional[str] = Field(
        None,
        description="Brief context about how the entity appears (e.g., 'spelled letter-by-letter', 'spoken as digits')",
    )


class EntitySegments(BaseModel):
    """Collection of identified entity segments from a transcript."""

    segments: list[EntitySegment] = Field(
        description="List of identified entity segments, one per field found"
    )
    notes: Optional[str] = Field(
        None,
        description="Any observations about the transcript that may affect extraction accuracy",
    )


_ENTITY_RECOGNITION_PROMPT = """\
You are analyzing a German phone bot transcript to LOCATE where contact information appears.
Your task is to identify the text segments containing each of these fields:
- first_name: The caller's first/given name
- last_name: The caller's family/surname
- email: The caller's email address
- phone_number: The caller's phone number

For each field found, quote the EXACT transcript text that contains it.
Do NOT extract or normalize values — just locate them.

Important:
- Include enough surrounding context to be unambiguous
- If a name is spelled letter-by-letter (e.g., "M A T T H I A S"), include the full spelling
- If an email is spoken component-by-component (at, Punkt, Bindestrich), include all components
- If a phone number is spoken digit-by-digit, include all digits
- Set confidence based on how clearly the entity appears
- If a field is not mentioned in the transcript, do not include it
"""


async def recognize_entities(
    transcript_text: str,
    model_name: str | None = None,
) -> EntitySegments:
    """Run entity recognition on a transcript.

    Args:
        transcript_text: The transcript text to scan (ideally caller-only from Stage 1).
        model_name: LLM model to use. Defaults to PHONEBOT_MODEL env var.

    Returns:
        EntitySegments with located fields.
    """
    model_name = model_name or os.getenv("PHONEBOT_MODEL", "claude-sonnet-4-6")
    model = get_model(model_name)
    structured_model = model.with_structured_output(EntitySegments, method="json_schema")

    prompt = f"{_ENTITY_RECOGNITION_PROMPT}\n\nTranscript:\n{transcript_text}"
    result = await structured_model.ainvoke(prompt)
    return result
