"""REJECT: the validator flags hallucinated names, invalid module values,
missing mandatory params, and wrong-type values."""
import pytest

from fleetpy_copilot import validate
from fleetpy_copilot.tests import _fixtures as fx

_BASE = fx.CLEAN_ACCEPT_PAIRS[0]  # the clean IR config to corrupt

HALLUCINATED = [
    ("op_max_waiting_time", 1),   # real: op_max_wait_time
    ("fleet_size", 10),           # real: op_fleet_composition
    ("simulation_env", "x"),      # real: sim_env
    ("op_batch_optimizer", "y"),  # real: op_rp_batch_optimizer
]
INVALID_MODULE = [
    ("op_module", "NotARealFleetControl"),
    ("op_rp_batch_optimizer", "Gurobi"),
    ("sim_env", "OnlineSimulation"),
    ("network_type", "NetworkFast"),
    ("rq_type", "StandardRequest"),
]
MANDATORY_DROP = [
    "network_name", "demand_name", "op_module",
    "sim_env", "rq_type", "start_time", "end_time",
]
WRONG_TYPE = [
    ("time_step", "sixty"),
    ("random_seed", "abc"),
    ("route_output_flag", "maybe"),
]


@pytest.mark.parametrize("name,val", HALLUCINATED, ids=[n for n, _ in HALLUCINATED])
def test_hallucinated_name_rejected(name, val):
    cfg = fx.load_merged(*_BASE)
    cfg[name] = val
    r = validate.validate(cfg)
    assert not r.ok
    assert name in r.unknown_params


@pytest.mark.parametrize("param,val", INVALID_MODULE, ids=[p for p, _ in INVALID_MODULE])
def test_invalid_module_value_rejected(param, val):
    cfg = fx.load_merged(*_BASE)
    cfg[param] = val
    r = validate.validate(cfg)
    assert not r.ok
    assert param in r.invalid_module_values


@pytest.mark.parametrize("param", MANDATORY_DROP, ids=MANDATORY_DROP)
def test_missing_mandatory_rejected(param):
    cfg = fx.load_merged(*_BASE)
    cfg.pop(param, None)
    r = validate.validate(cfg)
    assert not r.ok
    assert param in r.missing_mandatory


@pytest.mark.parametrize("param,val", WRONG_TYPE, ids=[p for p, _ in WRONG_TYPE])
def test_wrong_type_rejected(param, val):
    cfg = fx.load_merged(*_BASE)
    cfg[param] = val
    r = validate.validate(cfg)
    assert not r.ok
    assert param in r.type_errors


def test_multiple_errors_at_once():
    cfg = fx.load_merged(*_BASE)
    cfg["fleet_size"] = 1                      # hallucinated
    cfg["op_module"] = "NotARealFleetControl"  # invalid module
    cfg["time_step"] = "sixty"                 # wrong type
    cfg.pop("start_time", None)                # missing mandatory
    r = validate.validate(cfg)
    assert not r.ok
    assert r.unknown_params and r.invalid_module_values
    assert r.type_errors and r.missing_mandatory
