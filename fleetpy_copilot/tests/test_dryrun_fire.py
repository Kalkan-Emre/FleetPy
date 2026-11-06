"""FIRE THE SIMULATION: valid solver-free configs load+initialize in FleetPy
(dry-run = full __init__, never .run()) against the real data on disk."""
import pytest

from src.misc.config import ConstantConfig, ScenarioConfig

from fleetpy_copilot import dryrun
from fleetpy_copilot.tests import _fixtures as fx

_DRYRUN_IDS = [s for _, s in fx.SOLVER_FREE_DRYRUN_PAIRS]
_IR = fx.CLEAN_ACCEPT_PAIRS[0]


def _pair(const_name, scen_name, row=0):
    import os
    const = dict(ConstantConfig(os.path.join(fx.EXAMPLE, const_name)))
    scen = dict(ScenarioConfig(os.path.join(fx.EXAMPLE, scen_name))[row])
    return const, scen


@pytest.mark.parametrize("const,scen", fx.SOLVER_FREE_DRYRUN_PAIRS, ids=_DRYRUN_IDS)
def test_solver_free_config_loads(const, scen, tmp_path):
    c, s = _pair(const, scen)
    r = dryrun.dry_run(c, s, str(tmp_path))
    assert r.ok, r.error


@pytest.mark.parametrize("rq_file", fx.EXAMPLE_RQ_FILES, ids=fx.EXAMPLE_RQ_FILES)
def test_ir_config_loads_across_rq_files(rq_file, tmp_path):
    c, s = _pair(*_IR)
    s["rq_file"] = rq_file
    r = dryrun.dry_run(c, s, str(tmp_path))
    assert r.ok, r.error


def test_gurobi_config_made_solver_free_loads(tmp_path):
    """A normally-AlonsoMora pool config loads once forced to InsertionHeuristic."""
    c, s = _pair("constant_config_pool.csv", "example_pool.csv")
    c["op_rp_batch_optimizer"] = "InsertionHeuristic"
    r = dryrun.dry_run(c, s, str(tmp_path))
    assert r.ok, r.error


def test_dryrun_leaves_no_study_dir(tmp_path):
    import os
    c, s = _pair(*_IR)
    dryrun.dry_run(c, s, str(tmp_path))
    leftover = os.path.join(fx.REPO_ROOT, "studies", "copilot_dryrun")
    assert not os.path.exists(leftover)
