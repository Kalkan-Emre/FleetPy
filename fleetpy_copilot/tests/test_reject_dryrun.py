"""REJECT AT LOAD: configs that pass validate() but cannot actually load in
FleetPy are caught by the dry-run gate."""
import os

from src.misc.config import ConstantConfig, ScenarioConfig

from fleetpy_copilot import dryrun, validate
from fleetpy_copilot.tests import _fixtures as fx


def _ir_pair():
    const = dict(ConstantConfig(os.path.join(fx.EXAMPLE, "constant_config_ir.csv")))
    scen = dict(ScenarioConfig(os.path.join(fx.EXAMPLE, "example_ir_only.csv"))[0])
    return const, scen


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
