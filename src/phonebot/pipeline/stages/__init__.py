"""Multi-stage extraction pipeline (v3).

Decomposes the single-call extraction into four specialized stages:
  1. Preprocess: Rule-based transcript cleaning and speaker separation
  2. Entity Recognition: Focused LLM call to locate entities in transcript
  3. Field Extraction: Per-field parallel LLM calls with specialized prompts
  4. Postprocess: Rule-based normalization and knowledge grounding

This separation of responsibilities enables:
  - Better error isolation (which stage failed?)
  - Parallel field extraction (lower latency)
  - Cheaper entity recognition (scan-only LLM call)
  - Rule-based pre/post processing (zero LLM cost)
"""
