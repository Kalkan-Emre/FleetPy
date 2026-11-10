"""scorer.py — per-parameter precision/recall of a generated config vs a seed.

Definitions (standard, per-parameter, exact-value match on shared keys):

- A generated key is a **true positive** if it is present in the seed AND its value
  equals the seed's value.
- **precision** = TP / (number of params the model produced)   — "of what it output,
  how much was right"
- **recall**    = TP / (number of params in the seed)           — "of what was needed,
  how much it got"

Exact whole-file match is deliberately NOT used (too brittle: ordering, defaults).
Value equality is compared on the DECODED values (ints, floats, dicts, strings) as
FleetPy's loaders produce them, so ``{'default_vehtype': 5}`` compares structurally.
The scorer never mutates either config.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass
class ParamScore:
    true_positives: int
    produced: int          # params the model output
    expected: int          # params in the seed
    precision: float
    recall: float

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r / (p + r)) if (p + r) else 0.0


def _values_equal(a: object, b: object) -> bool:
    """Structural equality tolerant of int/float (5 == 5.0) but nothing looser.

    Treats two NaNs as equal: blank cells decode to float('nan'), and ``nan != nan``
    in IEEE would otherwise count an identical blank as a mismatch (a scoring
    artifact, not a real difference)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or a == b
    a_nan = isinstance(a, float) and a != a
    b_nan = isinstance(b, float) and b != b
    if a_nan or b_nan:
        return a_nan and b_nan
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return a == b


def score_params(generated: Mapping[str, object], seed: Mapping[str, object]) -> ParamScore:
    """Per-parameter precision/recall of ``generated`` against ground-truth ``seed``."""
    tp = sum(
        1 for k, v in generated.items()
        if k in seed and _values_equal(v, seed[k])
    )
    produced = len(generated)
    expected = len(seed)
    precision = tp / produced if produced else 0.0
    recall = tp / expected if expected else 0.0
    return ParamScore(
        true_positives=tp, produced=produced, expected=expected,
        precision=precision, recall=recall,
    )
