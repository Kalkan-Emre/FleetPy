"""harness.py — drive the corpus through generate_config and build the scoreboard.

For each corpus entry: derive the NL prompt (fixed template), run the full inner
loop via ``generate_config`` (provider -> validate -> repair -> dry-run), and record
TWO DISTINCT signals plus per-param precision/recall:

- ``validate_clean`` — the copilot produced a config that passed the 5-check validator
- ``dry_run_pass``   — that config also loaded in FleetPy (the gold gate)

These are distinct on purpose: a config can validate clean yet fail dry-run, and
(for a vocab-gap seed) the ground truth itself wouldn't validate. The harness
MEASURES; it never relaxes the validator or the gate. A transient provider failure
on one entry is recorded and the run continues.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from fleetpy_copilot import _prompting
from fleetpy_copilot.generate import (
    DryRunFailed, GeneratedConfig, GenerationFailed, NeedsInput, generate_config,
)
from fleetpy_copilot.provider import Provider

from .corpus import CorpusEntry, build_corpus, excluded_pairs
from .prompts import PROMPT_TEMPLATE_VERSION, derive_prompt
from .scorer import ParamScore, score_params


@dataclass
class ScoreRow:
    tag: str
    outcome: str                     # GeneratedConfig / NeedsInput / GenerationFailed / DryRunFailed / Error
    validate_clean: bool
    dry_run_pass: bool
    param_score: Optional[ParamScore] = None
    known_vocab_gap: bool = False
    error: str = ""                  # transient provider/transport failure, if any


@dataclass
class Scoreboard:
    rows: List[ScoreRow] = field(default_factory=list)
    prompt_version: str = _prompting.PROMPT_VERSION
    template_version: str = PROMPT_TEMPLATE_VERSION
    excluded: dict = field(default_factory=excluded_pairs)

    @property
    def dry_run_pass_rate(self) -> float:
        return (sum(r.dry_run_pass for r in self.rows) / len(self.rows)) if self.rows else 0.0

    @property
    def validate_clean_rate(self) -> float:
        return (sum(r.validate_clean for r in self.rows) / len(self.rows)) if self.rows else 0.0

    def render(self) -> str:
        head = (
            f"Scoreboard (prompt={self.prompt_version}, template={self.template_version})\n"
            f"{'tag':<14}{'outcome':<18}{'valid':<7}{'dryrun':<8}{'P':<6}{'R':<6}{'F1':<6}\n"
            f"{'-' * 65}\n"
        )
        lines = []
        for r in self.rows:
            ps = r.param_score
            p = f"{ps.precision:.2f}" if ps else "-"
            rc = f"{ps.recall:.2f}" if ps else "-"
            f1 = f"{ps.f1:.2f}" if ps else "-"
            flag = " (vocab-gap)" if r.known_vocab_gap else ""
            err = f"  !{r.error[:40]}" if r.error else ""
            lines.append(
                f"{r.tag:<14}{r.outcome:<18}{str(r.validate_clean):<7}"
                f"{str(r.dry_run_pass):<8}{p:<6}{rc:<6}{f1:<6}{flag}{err}"
            )
        summary = (
            f"\n{'-' * 65}\n"
            f"validate-clean rate: {self.validate_clean_rate:.2f}   "
            f"dry-run-pass rate: {self.dry_run_pass_rate:.2f}   "
            f"(n={len(self.rows)})\n"
            f"excluded: {self.excluded}\n"
        )
        return head + "\n".join(lines) + summary


def _score_one(entry: CorpusEntry, provider: Provider, *, do_dry_run: bool) -> ScoreRow:
    prompt = derive_prompt(entry.seed_config)
    try:
        result = generate_config(prompt, provider, do_dry_run=do_dry_run)
    except Exception as exc:  # transient provider/transport failure -> record, continue
        return ScoreRow(
            tag=entry.tag, outcome="Error", validate_clean=False, dry_run_pass=False,
            known_vocab_gap=entry.known_vocab_gap, error=f"{type(exc).__name__}: {exc}",
        )

    outcome = type(result).__name__
    if isinstance(result, GeneratedConfig):
        validate_clean = True
        dry_run_pass = (result.dry_run is None) or result.dry_run.ok
        generated = result.config
    elif isinstance(result, DryRunFailed):
        validate_clean = True          # validated clean, but the gate failed
        dry_run_pass = False
        generated = result.config
    elif isinstance(result, NeedsInput):
        validate_clean = False         # under-specified: no clean config produced
        dry_run_pass = False
        generated = result.candidate
    elif isinstance(result, GenerationFailed):
        validate_clean = False
        dry_run_pass = False
        generated = result.candidate
    else:  # pragma: no cover - generate_config is exhaustively typed
        validate_clean = dry_run_pass = False
        generated = {}

    return ScoreRow(
        tag=entry.tag, outcome=outcome,
        validate_clean=validate_clean, dry_run_pass=dry_run_pass,
        param_score=score_params(generated, entry.seed_config),
        known_vocab_gap=entry.known_vocab_gap,
    )


def run_harness(provider: Provider, *, do_dry_run: bool = True,
                corpus: Optional[List[CorpusEntry]] = None) -> Scoreboard:
    """Run the whole corpus through ``provider`` and return a ``Scoreboard``.

    ``do_dry_run`` is threaded to ``generate_config`` (offline MockProvider tests may
    set it False to stay fast). A per-entry exception is captured, not raised.
    """
    entries = corpus if corpus is not None else build_corpus()
    board = Scoreboard()
    for entry in entries:
        board.rows.append(_score_one(entry, provider, do_dry_run=do_dry_run))
    return board
