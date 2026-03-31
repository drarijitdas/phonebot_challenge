"""Post-processing stage for extraction results.

Provides rule-based normalization, knowledge grounding, and contact
validation applied after LLM extraction. See postprocess.py for the
full pipeline: phone E.164 normalization, email lowercasing, name NFC
normalization, cross-reference checking, and confidence adjustment.
"""
