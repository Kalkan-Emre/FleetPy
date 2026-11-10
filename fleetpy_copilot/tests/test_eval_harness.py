"""Tests for the eval baseline harness (M2.2). Deterministic + offline: MockProvider
only, no network. The full live run against hai is an opt-in step (eval/run.py),
never exercised here.
"""
from fleetpy_copilot.eval import (
    build_corpus, derive_prompt, score_params, run_harness,
)
from fleetpy_copilot.eval.corpus import excluded_pairs
from fleetpy_copilot.eval.harness import Scoreboard
from fleetpy_copilot.provider import MockProvider
from fleetpy_copilot.tests import _fixtures as fx


# --- corpus --------------------------------------------------------------------

def test_corpus_is_verified_solver_free_set():
    corpus = build_corpus()
    tags = {e.scenario_name for e in corpus}
    # exactly the verified solver-free dry-run pairs
    assert tags == {scen for _, scen in fx.SOLVER_FREE_DRYRUN_PAIRS}
    # every entry carries a non-empty merged ground-truth config
    assert all(e.seed_config for e in corpus)


def test_corpus_excludes_solver_and_vocab_gap_pairs():
    excl = excluded_pairs()
    # Gurobi pairs are surfaced as excluded, not silently dropped
    assert set(excl["needs_solver_gurobi"]) == {s for _, s in fx.GUROBI_PAIRS}
    # none of the excluded gurobi scenarios appear in the corpus
    corpus_scenarios = {e.scenario_name for e in build_corpus()}
    assert corpus_scenarios.isdisjoint(excl["needs_solver_gurobi"])


def test_rpp_flagged_as_vocab_gap():
    # rpp dry-run-loads AND is a vocab gap -> must be flagged, not hidden
    rpp = next(e for e in build_corpus() if e.tag == "rpp")
    assert rpp.known_vocab_gap is True


# --- prompt template (deterministic) -------------------------------------------

def test_prompt_derivation_is_deterministic():
    cfg = {"sim_env": "ImmediateDecisionsSimulation", "network_name": "example_network",
           "start_time": 0, "end_time": 7200, "op_fleet_composition": {"default_vehtype": 5},
           "nr_mod_operators": 1}
    assert derive_prompt(cfg) == derive_prompt(cfg)  # same input -> same output
    p = derive_prompt(cfg)
    assert "example_network" in p and "2 hour" in p and "5 vehicles" in p


# --- scorer --------------------------------------------------------------------

def test_scorer_precision_recall():
    seed = {"a": 1, "b": "x", "c": 3}
    gen = {"a": 1, "b": "WRONG", "d": 9}   # a correct; b wrong; d spurious; c missing
    s = score_params(gen, seed)
    assert s.true_positives == 1
    assert s.precision == 1 / 3            # 1 of 3 produced
    assert s.recall == 1 / 3               # 1 of 3 expected


def test_scorer_int_float_equal():
    assert score_params({"n": 5}, {"n": 5.0}).true_positives == 1


def test_scorer_treats_two_nans_as_equal():
    # Blank cells decode to float('nan'); nan != nan in IEEE would otherwise count
    # an identical blank as a mismatch (scoring artifact, not a real difference).
    nan = float("nan")
    assert score_params({"x": nan}, {"x": nan}).true_positives == 1
    # but a nan vs a real value is still a mismatch
    assert score_params({"x": nan}, {"x": 5}).true_positives == 0


# --- harness orchestration (MockProvider) --------------------------------------

def test_harness_row_shape_and_perfect_match():
    corpus = build_corpus()
    ir = next(e for e in corpus if e.tag == "ir_only")
    # provider returns the exact seed config -> validate clean, perfect P/R
    provider = MockProvider([ir.seed_config])
    board = run_harness(provider, do_dry_run=False, corpus=[ir])
    assert isinstance(board, Scoreboard)
    row = board.rows[0]
    assert row.tag == "ir_only"
    assert row.validate_clean is True
    assert row.param_score.precision == 1.0 and row.param_score.recall == 1.0
    assert board.prompt_version and board.template_version


def test_harness_distinguishes_validate_from_dryrun(monkeypatch):
    # A config that validates clean but fails the dry-run gate -> validate_clean True,
    # dry_run_pass False. Proves the two signals are scored distinctly.
    from fleetpy_copilot import generate as gen
    from fleetpy_copilot.dryrun import DryRunResult

    corpus = build_corpus()
    ir = next(e for e in corpus if e.tag == "ir_only")
    monkeypatch.setattr(gen, "dry_run_tmp",
                        lambda base, cand: DryRunResult(ok=False, error="boom"))
    board = run_harness(MockProvider([ir.seed_config]), do_dry_run=True, corpus=[ir])
    row = board.rows[0]
    assert row.validate_clean is True
    assert row.dry_run_pass is False
    assert row.outcome == "DryRunFailed"


def test_harness_records_underspecified_without_bypass():
    corpus = build_corpus()
    ir = next(e for e in corpus if e.tag == "ir_only")
    broken = dict(ir.seed_config)
    broken.pop("sim_env")  # drop a mandatory -> NeedsInput, not a clean config
    board = run_harness(MockProvider([broken]), do_dry_run=False, corpus=[ir])
    row = board.rows[0]
    assert row.validate_clean is False       # harness did NOT relax the validator
    assert row.outcome == "NeedsInput"


def test_harness_captures_provider_error_and_continues():
    class _Raising:
        def generate(self, prompt, *, correction=None, schema_hint=None):
            raise RuntimeError("upstream down")

    corpus = build_corpus()[:2]
    board = run_harness(_Raising(), do_dry_run=False, corpus=corpus)
    assert len(board.rows) == len(corpus)         # did not abort
    assert all(r.outcome == "Error" for r in board.rows)
    assert all("upstream down" in r.error for r in board.rows)
