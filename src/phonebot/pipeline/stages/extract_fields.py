"""Stage 3: Per-field extraction with specialized prompts.

Receives entity segments from Stage 2 and runs focused extraction for each
field with specialized prompts. Each field gets its own prompt tuned for
that specific extraction task (name rules, email assembly, phone concatenation).

The four extractions can run in parallel via asyncio.gather, reducing latency.
Each call operates on a small text segment rather than the full transcript.
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

from pydantic import BaseModel, Field

from phonebot.models.model_registry import get_model
from phonebot.pipeline.stages.entity_recognition import EntitySegment


# Per-field extraction prompts — specialized for each entity type
FIELD_PROMPTS: dict[str, str] = {
    "first_name": """\
Extract the caller's first (given) name from the following transcript segment.
Rules:
- If the name is spelled letter-by-letter (e.g., "M A T T H I A S"), reconstruct it as "Matthias"
- Preserve German umlauts (ä, ö, ü) and ß
- For foreign names, prefer the spelling used in the email address if available
- Return null if you cannot determine the first name
Return ONLY the extracted first name as a JSON string, or null.""",

    "last_name": """\
Extract the caller's last (family) name from the following transcript segment.
Rules:
- If the name is spelled letter-by-letter, reconstruct it fully
- Preserve German umlauts (ä, ö, ü), ß, and accents (é, í, ñ)
- Preserve apostrophes in names like O'Brien
- For foreign names, prefer the spelling used in the email address if available
- Return null if you cannot determine the last name
Return ONLY the extracted last name as a JSON string, or null.""",

    "email": """\
Extract and assemble the caller's email address from the following transcript segment.
Rules:
- "at" or "Klammeraffe" → @
- "Punkt" → . (consecutive "Punkt" tokens collapse to a single dot)
- "Bindestrich" or "minus" → -
- "Unterstrich" → _
- Assemble all components into a valid email: local@domain.tld
- Return null if you cannot determine the email
Return ONLY the assembled email address as a JSON string, or null.""",

    "phone_number": """\
Extract and reconstruct the caller's phone number from the following transcript segment.
Rules:
- "plus" → + (international prefix)
- Concatenate all spoken digits: "vier neun" → "49", "null eins fünf zwei" → "0152"
- Format as E.164: +49XXXXXXXXX (no spaces, no dashes)
- German country code is +49
- Common prefixes: 015x/016x/017x (mobile), 030/040/089 etc. (landline)
- Return null if you cannot determine the phone number
Return ONLY the phone number in E.164 format as a JSON string, or null.""",
}


class FieldExtraction(BaseModel):
    """Extraction result for a single field."""

    value: Optional[str] = Field(None, description="Extracted value, or null if not found")
    confidence: float = Field(
        description="Confidence in the extraction (0.0-1.0)",
        ge=0.0,
        le=1.0,
    )


async def extract_single_field(
    field: str,
    segment: EntitySegment,
    full_transcript: str | None = None,
    model_name: str | None = None,
) -> tuple[str, FieldExtraction]:
    """Extract a single field from its located segment.

    Args:
        field: Field name (first_name, last_name, email, phone_number).
        segment: Located entity segment from Stage 2.
        full_transcript: Optional full transcript for additional context.
        model_name: LLM model to use.

    Returns:
        Tuple of (field_name, FieldExtraction).
    """
    model_name = model_name or os.getenv("PHONEBOT_MODEL", "claude-sonnet-4-6")
    model = get_model(model_name)
    structured_model = model.with_structured_output(FieldExtraction, method="json_schema")

    prompt_template = FIELD_PROMPTS.get(field, "Extract the value from this text segment.")
    prompt = f"{prompt_template}\n\nSegment: {segment.text_segment}"
    if segment.context:
        prompt += f"\nContext: {segment.context}"
    if full_transcript:
        prompt += f"\n\nFull transcript (for reference):\n{full_transcript[:1000]}"

    result: FieldExtraction = await structured_model.ainvoke(prompt)
    return field, result


async def extract_all_fields(
    segments: list[EntitySegment],
    full_transcript: str | None = None,
    model_name: str | None = None,
) -> dict[str, FieldExtraction]:
    """Extract all fields in parallel from their located segments.

    Args:
        segments: Entity segments from Stage 2.
        full_transcript: Optional full transcript for context.
        model_name: LLM model to use.

    Returns:
        Dict mapping field_name to FieldExtraction.
    """
    tasks = []
    for seg in segments:
        tasks.append(extract_single_field(
            field=seg.field,
            segment=seg,
            full_transcript=full_transcript,
            model_name=model_name,
        ))

    results = await asyncio.gather(*tasks)
    return dict(results)
