"""ACCEPT: real config files validate (or fail only on documented vocab gaps)."""
import os

import pytest

from fleetpy_copilot import validate
from fleetpy_copilot.tests import _fixtures as fx

_CLEAN_IDS = [s for _, s in fx.CLEAN_ACCEPT_PAIRS]
_GAP_IDS = [s for _, s in fx.KNOWN_VOCAB_GAP_PAIRS]


@pytest.mark.parametrize("const,scen", fx.CLEAN_ACCEPT_PAIRS, ids=_CLEAN_IDS)
def test_clean_real_config_validates(const, scen):
    r = validate.validate(fx.load_merged(const, scen))
    assert r.ok, r.summary()


@pytest.mark.parametrize("const,scen", fx.ALL_ROWS_CLEAN_PAIRS,
                         ids=[s for _, s in fx.ALL_ROWS_CLEAN_PAIRS])
def test_all_rows_validate(const, scen):
    for i in range(fx.n_rows(scen)):
        r = validate.validate(fx.load_merged(const, scen, row=i))
        assert r.ok, f"row {i}: {r.summary()}"


@pytest.mark.parametrize("const,scen", fx.KNOWN_VOCAB_GAP_PAIRS, ids=_GAP_IDS)
def test_known_vocab_gap_flags_unknowns_not_types(const, scen):
    """Advanced real configs fail only because they use params outside the
    201-name schema — the type-checker must not raise spurious type_errors."""
    r = validate.validate(fx.load_merged(const, scen))
    assert not r.ok
    assert r.unknown_params, "expected a real vocabulary gap"
    assert not r.type_errors, f"unexpected type errors: {r.type_errors}"


def test_batch_optimization_row_requires_optimizer():
    """example_depot row 1 uses PoolingIRSAssignmentBatchOptimization and omits
    op_rp_batch_optimizer — the validator correctly flags it (FleetPy would only
    silently default it to AlonsoMora at runtime). Supplying it makes it clean."""
    merged = fx.load_merged("constant_config_depot.csv", "example_depot.csv", row=1)
    r = validate.validate(merged)
    assert not r.ok
    assert "op_rp_batch_optimizer" in r.missing_mandatory

    merged["op_rp_batch_optimizer"] = "InsertionHeuristic"
    assert validate.validate(merged).ok


def test_module_tests_config_validates_once_complete():
    """studies/module_tests uses RidePoolingBatchAssignmentFleetcontrol. It needs
    op_rp_batch_optimizer supplied (declared mandatory); the n_cpu_per_sim
    runner-only quirk no longer blocks it."""
    merged = fx.load_merged(
        os.path.join(fx.MODULE_TESTS, "constant_config.csv"),
        os.path.join(fx.MODULE_TESTS, "sc_config_routing.csv"),
    )
    merged["op_rp_batch_optimizer"] = "InsertionHeuristic"
    r = validate.validate(merged)
    assert r.ok, r.summary()
    assert "n_cpu_per_sim" not in r.missing_mandatory
