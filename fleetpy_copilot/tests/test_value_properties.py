"""Property-based tests for the value checker (hypothesis).

These assert *invariants* over random inputs rather than enumerated examples:

  - the checker never raises, whatever junk it is handed;
  - an in-range value is NEVER flagged (no false positives) — the property that
    protects legitimate research sweeps;
  - an out-of-range value IS flagged (no false negatives) for the hard checks.

Hypothesis explores the numeric edges (0, -0.0, tiny epsilons, huge magnitudes,
subnormals) far more aggressively than hand-written cases.
"""
import math

import pytest
from hypothesis import given, strategies as st

from fleetpy_copilot import validate


# strategy: finite floats, plus the awkward specials the loader/LLM can produce
_finite = st.floats(allow_nan=False, allow_infinity=False, width=64)
_any_float = st.floats()  # includes nan / inf
_scalars = st.one_of(
    _any_float,
    st.integers(min_value=-10**9, max_value=10**9),
    st.text(max_size=12),
    st.booleans(),
    st.none(),
)


@given(value=_scalars)
def test_check_values_never_raises_on_any_scalar(value):
    # whatever lands in a numeric-constrained param, check_values must not crash
    for param in ("time_step", "start_time", "op_min_soc_after_planstop"):
        validate.check_values({param: value})


@given(value=st.one_of(_scalars, st.lists(st.integers(), max_size=4), st.dictionaries(
    st.text(max_size=5), st.integers(), max_size=4)))
def test_fleet_composition_never_raises(value):
    validate.check_values({"op_fleet_composition": value})


# --- no false positives: an in-range value is never flagged --------------------

@given(n=_finite.filter(lambda x: x > 0))
def test_strictly_positive_accepts_all_positive(n):
    assert "time_step" not in validate.check_values({"time_step": n})


@given(n=_finite.filter(lambda x: x >= 0))
def test_non_negative_accepts_all_non_negative(n):
    assert "start_time" not in validate.check_values({"start_time": n})


@given(n=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
def test_fraction_accepts_all_in_unit_interval(n):
    assert "op_min_soc_after_planstop" not in validate.check_values(
        {"op_min_soc_after_planstop": n}
    )


# --- no false negatives: an out-of-range value is always flagged ---------------

@given(n=_finite.filter(lambda x: x <= 0))
def test_strictly_positive_rejects_all_non_positive(n):
    assert "time_step" in validate.check_values({"time_step": n})


# strictly-negative strategy: exclude -0.0, which IS zero (not negative) and is
# correctly treated as non-negative by the checker. `x < 0` alone lets -0.0 leak
# through under hypothesis's float generation, so guard it explicitly.
_strictly_negative = _finite.filter(lambda x: x < 0 and not (x == 0.0))


@given(n=_strictly_negative)
def test_non_negative_rejects_all_negative(n):
    assert "start_time" in validate.check_values({"start_time": n})


@given(n=_strictly_negative)
def test_strictly_positive_rejects_all_negative_too(n):
    assert "time_step" in validate.check_values({"time_step": n})


@given(n=_finite.filter(lambda x: x < 0.0 or x > 1.0))
def test_fraction_rejects_all_outside_unit_interval(n):
    assert "op_min_soc_after_planstop" in validate.check_values(
        {"op_min_soc_after_planstop": n}
    )


# --- ordering relation holds for all finite pairs ------------------------------

@given(a=_finite, b=_finite)
def test_ordering_flagged_iff_end_le_start(a, b):
    errs = validate.check_values({"start_time": a, "end_time": b})
    # start_time may itself be flagged if negative; isolate the ordering key.
    # ordering error present  <=>  end <= start (both finite here)
    assert ("end_time" in errs and "must be > start_time" in errs.get("end_time", "")) == (b <= a)


# --- nan is always treated as missing (never flagged), inf always flagged ------

@given(param=st.sampled_from(["time_step", "start_time", "op_min_soc_after_planstop"]))
def test_nan_never_flagged(param):
    assert param not in validate.check_values({param: float("nan")})


@given(param=st.sampled_from(["time_step", "start_time", "op_min_soc_after_planstop"]),
       sign=st.sampled_from([1.0, -1.0]))
def test_inf_always_flagged(param, sign):
    assert param in validate.check_values({param: sign * float("inf")})
