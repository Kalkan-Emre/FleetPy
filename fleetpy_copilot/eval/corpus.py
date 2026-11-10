"""corpus.py — the eval corpus: the VERIFIED solver-free, dry-run-loadable configs.

The "47 studies/*/scenarios/*.csv" figure is a raw CSV count; most are solver-based
or use parameters outside the 201-name schema and are NOT valid NL->config cases in
this solver-free environment. The ground truth is already enumerated and verified in
``tests/_fixtures.py``; we reuse it rather than re-deriving (and re-making its
mistakes).

- INCLUDE: ``SOLVER_FREE_DRYRUN_PAIRS`` — pairs that actually load in this .venv.
- EXCLUDE: ``GUROBI_PAIRS`` (need AlonsoMora/Gurobi) and ``KNOWN_VOCAB_GAP_PAIRS``
  (params absent from the schema -> fail ``validate``). The exclusions are surfaced
  so the scoreboard is honest about what it did and did not run.

Note: ``rpp`` is in BOTH the solver-free-dryrun set AND the vocab-gap set — it
dry-run-loads but does NOT validate clean. That is exactly why the scoreboard scores
validate-clean and dry-run-pass as DISTINCT signals (see ``harness.py``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from fleetpy_copilot.tests import _fixtures as fx


@dataclass
class CorpusEntry:
    """One eval case: a verified solver-free (const, scenario, row) with its merged
    ground-truth config dict."""
    tag: str                      # human-readable id, e.g. "ir_only"
    const_name: str
    scenario_name: str
    row: int
    seed_config: Dict[str, object] = field(default_factory=dict)  # merged ground truth
    #: True when this pair is also a known vocab-gap (dry-run loads, validate won't pass)
    known_vocab_gap: bool = False


#: Pairs that dry-run-load but do NOT validate clean (vocab gaps) — flagged, not dropped.
_VOCAB_GAP_SCENARIOS = {scen for _, scen in fx.KNOWN_VOCAB_GAP_PAIRS}


def build_corpus() -> List[CorpusEntry]:
    """The verified solver-free eval corpus, built from ``_fixtures`` (reuse, not
    reinvent). Uses ``load_merged`` for the FleetPy-faithful merge. Row 0 is used for
    every pair; the IR pair's every row is clean, the others' row 0 is clean."""
    entries: List[CorpusEntry] = []
    for const_name, scenario_name in fx.SOLVER_FREE_DRYRUN_PAIRS:
        merged = fx.load_merged(const_name, scenario_name, 0)
        tag = scenario_name.replace("example_", "").replace(".csv", "")
        entries.append(CorpusEntry(
            tag=tag,
            const_name=const_name,
            scenario_name=scenario_name,
            row=0,
            seed_config=merged,
            known_vocab_gap=scenario_name in _VOCAB_GAP_SCENARIOS,
        ))
    return entries


def excluded_pairs() -> Dict[str, List[str]]:
    """The pairs deliberately kept OUT of the corpus, by reason — surfaced in output
    so the scoreboard is honest about coverage."""
    return {
        "needs_solver_gurobi": [s for _, s in fx.GUROBI_PAIRS],
        "vocab_gap_not_dryrun_loadable": [
            s for _, s in fx.KNOWN_VOCAB_GAP_PAIRS
            if (any(s == scen for _, scen in fx.KNOWN_VOCAB_GAP_PAIRS)
                and s not in {scen for _, scen in fx.SOLVER_FREE_DRYRUN_PAIRS})
        ],
    }
