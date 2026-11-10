"""fleetpy_copilot.eval — baseline harness / scoreboard (M2.2).

Measures the copilot end to end: for each config in the **verified solver-free**
corpus, derive a natural-language prompt (a fixed, reproducible field-template),
run it through ``generate_config``, and score the result on two DISTINCT signals —
``validate``-clean and dry-run-pass — plus per-parameter precision/recall against
the seed config.

The default pytest path uses ``MockProvider`` (deterministic, offline). The full
live run against a real provider (hai) is an opt-in entry point (``run.py``), never
part of the default suite. The harness MEASURES; it never relaxes the validator or
the dry-run gate.
"""
from .corpus import CorpusEntry, build_corpus
from .prompts import PROMPT_TEMPLATE_VERSION, derive_prompt
from .scorer import ParamScore, score_params
from .harness import ScoreRow, Scoreboard, run_harness

__all__ = [
    "CorpusEntry", "build_corpus",
    "PROMPT_TEMPLATE_VERSION", "derive_prompt",
    "ParamScore", "score_params",
    "ScoreRow", "Scoreboard", "run_harness",
]
