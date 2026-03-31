"""Prompt management — externalized JSON prompt loading and dynamic CallerInfo construction."""
import json
from pathlib import Path
from typing import Optional

from pydantic import Field, create_model


def load_prompt(prompt_path: Path) -> dict:
    """Load prompt JSON file. Returns dict with 'system_prompt' and 'fields' keys."""
    return json.loads(prompt_path.read_text(encoding="utf-8"))


def build_caller_info_model(prompt_path: Path) -> type:
    """Read prompt JSON and return a CallerInfo Pydantic class with updated prompts.

    The returned class has:
    - __doc__ set to data["system_prompt"] (used by with_structured_output as system message)
    - 4 Optional[str] fields with descriptions from data["fields"]
    - confidence dict field (not part of optimization surface, always present)

    Per D-09: factory function creates a new class each time (no shared state mutation).
    """
    data = json.loads(prompt_path.read_text(encoding="utf-8"))
    system_prompt: str = data["system_prompt"]
    field_descs: dict[str, str] = data["fields"]

    fields = {
        name: (Optional[str], Field(default=None, description=desc))
        for name, desc in field_descs.items()
    }
    # Pitfall 7: confidence field must always be present (not in optimization surface)
    fields["confidence"] = (
        dict,
        Field(
            default_factory=dict,
            description=(
                'REQUIRED: Provide a confidence score between 0.0 and 1.0 for EVERY field '
                "you extracted (non-null). Keys must match field names exactly. "
                'Example: {"first_name": 0.95, "last_name": 0.8, "email": 0.4}. '
                "Only omit a key if that field's value is null."
            ),
        ),
    )
    Model = create_model("CallerInfo", **fields)
    Model.__doc__ = system_prompt
    return Model


def export_v1_prompt(output_path: Path) -> None:
    """Export current inline CallerInfo prompts to a JSON file.

    Reads CallerInfo.__doc__ and model_fields to produce:
    {"system_prompt": "...", "fields": {"first_name": "...", ...}}

    The confidence field is excluded (not an optimization slot per D-13).
    Per D-10: this becomes both the GEPA seed candidate and the baseline.
    """
    from phonebot.models.caller_info import CallerInfo

    payload = {
        "system_prompt": CallerInfo.__doc__.strip(),
        "fields": {
            name: info.description
            for name, info in CallerInfo.model_fields.items()
            if name != "confidence"
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
