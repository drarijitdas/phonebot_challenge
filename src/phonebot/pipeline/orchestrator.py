"""Pipeline orchestrator — composes classification, extraction, post-processing, and escalation.

Matches the System Overview architecture:
  Cache → Classifier → [V1|V2] → Post-processing → Escalation
"""
from __future__ import annotations

from pathlib import Path

from phonebot.pipeline.shared import PipelineVersion, base_initial_state
from phonebot.pipeline.transcribe import TRANSCRIPT_DIR


async def run_extraction_pipeline(
    recording_ids: list[str],
    *,
    model_name: str = "claude-sonnet-4-6",
    pipeline: str = PipelineVersion.V1,
    prompt_version: str = "v1",
    max_ac_iterations: int = 3,
    enable_few_shot: bool = False,
    enable_postprocess: bool = True,
    enable_escalation: bool = True,
) -> list[dict]:
    """Run the complete extraction pipeline over a list of recordings.

    Orchestrates: classification → few-shot retrieval → V1/V2 extraction →
    post-processing → escalation check. Returns enriched result dicts.
    """
    # --- 1. Optional: classify + few-shot RAG retrieval ---
    few_shot_map: dict[str, str] = {}
    transcript_cache: dict[str, str] = {}
    classifications: dict = {}
    if enable_few_shot:
        from phonebot.pipeline.classifier import classify_batch
        from phonebot.pipeline.transcribe import get_transcript_text
        from phonebot.knowledge.example_store import ExampleStore

        classifications = classify_batch(recording_ids)

        store = ExampleStore()
        if store.count == 0:
            from phonebot.evaluation.metrics import load_ground_truth

            gt = load_ground_truth(Path("data/ground_truth.json"))
            store.index_ground_truth(gt)

        for rid, cls_result in classifications.items():
            if cls_result.use_few_shot:
                cache_path = TRANSCRIPT_DIR / f"{rid}.json"
                transcript_text = get_transcript_text(cache_path)
                transcript_cache[rid] = transcript_text
                examples = store.retrieve(transcript_text, k=2, exclude_id=rid)
                few_shot_map[rid] = store.format_few_shot_prompt(examples)

    # --- 2. Build initial state factory with optional few-shot injection ---
    initial_state_override = None
    if few_shot_map:

        def _enhanced_initial_state(recording_id: str) -> dict:
            state = base_initial_state(recording_id)
            if recording_id in few_shot_map:
                state["few_shot_prefix"] = few_shot_map[recording_id]
            return state

        initial_state_override = _enhanced_initial_state

    # --- 3. Run V1 or V2 extraction pipeline ---
    if PipelineVersion(pipeline) == PipelineVersion.V2:
        from phonebot.pipeline.extract_v2 import run_pipeline_v2

        results = await run_pipeline_v2(
            recording_ids,
            model_name=model_name,
            prompt_version=prompt_version,
            max_ac_iterations=max_ac_iterations,
            initial_state_override=initial_state_override,
        )
    else:
        from phonebot.pipeline.extract import run_pipeline

        results = await run_pipeline(
            recording_ids,
            model_name=model_name,
            prompt_version=prompt_version,
            initial_state_override=initial_state_override,
        )

    # --- 4. Optional: post-processing (normalization + knowledge grounding) ---
    if enable_postprocess:
        from phonebot.pipeline.stages.postprocess import postprocess
        from phonebot.pipeline.extract import compute_flagged_fields

        for i, result in enumerate(results):
            caller_info = result.get("caller_info") or {}
            pp_result = postprocess(caller_info)
            results[i]["caller_info"] = pp_result.caller_info
            results[i]["flagged_fields"] = compute_flagged_fields(pp_result.caller_info)
            results[i]["postprocess"] = {
                "grounding": pp_result.grounding,
                "contact_validation": pp_result.contact_validation,
                "cross_reference": pp_result.cross_reference,
                "normalizations": pp_result.normalizations_applied,
            }

    # --- 5. Optional: escalation check ---
    if enable_escalation:
        from phonebot.pipeline.escalation import (
            check_escalation,
            write_escalation_queue,
            EscalationItem,
        )
        from phonebot.pipeline.transcribe import get_transcript_text as _get_transcript

        escalation_items: list[EscalationItem] = []
        for result in results:
            caller_info = result.get("caller_info") or {}
            flagged = result.get("flagged_fields", [])
            rid = result["id"]
            transcript_text = transcript_cache.get(rid)
            if transcript_text is None:
                tp = TRANSCRIPT_DIR / f"{rid}.json"
                if tp.exists():
                    transcript_text = _get_transcript(tp)
            contact_validation = (result.get("postprocess") or {}).get(
                "contact_validation"
            )
            item = check_escalation(
                recording_id=result["id"],
                caller_info=caller_info,
                flagged_fields=flagged,
                transcript_text=transcript_text,
                contact_validation=contact_validation,
            )
            if item:
                escalation_items.append(item)
                result["escalated"] = True
            else:
                result["escalated"] = False

        if escalation_items:
            write_escalation_queue(escalation_items)

    # --- 6. Add classification metadata to results ---
    if classifications:
        for result in results:
            cls = classifications.get(result["id"])
            if cls:
                result["difficulty_tier"] = cls.tier.value
                result["difficulty_score"] = cls.score

    return results
