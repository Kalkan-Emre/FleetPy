"""REJECT AT LOAD: configs that pass validate() but cannot actually load in
FleetPy are caught by the dry-run gate.

These are the dry-run gate's *reason to exist*: a config whose names, types, and
mandatory params are all admissible AND whose referenced directories exist — so
validate() passes — but which FleetPy cannot initialize. validate() checks the
config as text (and shallow path existence); only dry_run() opens the files.
"""
import os
import shutil

import pytest

from src.misc.config import ConstantConfig, ScenarioConfig

from fleetpy_copilot import dryrun, validate
from fleetpy_copilot.tests import _fixtures as fx


def _ir_pair():
    const = dict(ConstantConfig(os.path.join(fx.EXAMPLE, "constant_config_ir.csv")))
    scen = dict(ScenarioConfig(os.path.join(fx.EXAMPLE, "example_ir_only.csv"))[0])
    return const, scen


@pytest.fixture
def broken_network():
    """A network dir that EXISTS and is complete enough to pass validate()
    (``check_referenced_files`` only checks the dir exists + rq_file resolves),
    but is missing its interior ``base/nodes.csv`` — which FleetPy opens in
    ``__init__``. Yields the new network name; tears down both temp dirs.

    This is the canonical valid-but-unloadable fixture: the gap between shallow
    path-existence validation and what the simulation actually reads at init.
    """
    data = os.path.join(fx.REPO_ROOT, "data")
    name = "copilot_broken_net_probe"
    net = os.path.join(data, "networks", name)
    # rq_file is resolved UNDER the network name, so the matched/ dir must exist
    # for the new name or validate() would (correctly) reject rq_file first.
    real_matched = os.path.join(data, "demand", "example_demand", "matched", "example_network")
    matched = os.path.join(data, "demand", "example_demand", "matched", name)
    try:
        shutil.copytree(os.path.join(data, "networks", "example_network"), net)
        os.remove(os.path.join(net, "base", "nodes.csv"))  # break the interior
        shutil.copytree(real_matched, matched)
        yield name
    finally:
        shutil.rmtree(net, ignore_errors=True)
        shutil.rmtree(matched, ignore_errors=True)


def test_nonexistent_rq_file_fails_dryrun(tmp_path):
    const, scen = _ir_pair()
    scen["rq_file"] = "does_not_exist.csv"
    # validate() can't know the file is missing — it's a valid name/type
    assert validate.validate({**const, **scen}).type_errors == {}
    r = dryrun.dry_run(const, scen, str(tmp_path))
    assert not r.ok
    assert any(tok in r.error for tok in ("FileNotFound", "No such", "does_not_exist"))


def test_invalid_module_fails_dryrun(tmp_path):
    const, scen = _ir_pair()
    scen["op_module"] = "NotARealFleetControl"
    r = dryrun.dry_run(const, scen, str(tmp_path))
    assert not r.ok


def test_existing_network_dir_missing_interior_fails_dryrun(broken_network, tmp_path):
    """The canonical valid-but-unloadable case: network dir exists (validate OK),
    but its interior base/nodes.csv is gone, so FleetPy's __init__ cannot load it.

    This is what dry-run uniquely catches — validate() has no visibility into the
    files FleetPy reads below the directory level.
    """
    const, scen = _ir_pair()
    const["network_name"] = broken_network

    # validate() passes: name/type/mandatory all fine AND the dir + rq_file exist.
    assert validate.validate({**const, **scen}).ok

    # dry-run fails: __init__ opens base/nodes.csv, which is missing.
    r = dryrun.dry_run(const, scen, str(tmp_path))
    assert not r.ok
    assert any(tok in r.error for tok in ("FileNotFound", "No such", "nodes"))
