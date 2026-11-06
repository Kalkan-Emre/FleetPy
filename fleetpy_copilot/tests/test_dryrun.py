"""Functional dry-run gate tests against the real example_study data."""
import os

from src.misc.config import ConstantConfig, ScenarioConfig

from fleetpy_copilot import dryrun

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXAMPLE_SCENARIOS = os.path.join(REPO_ROOT, "studies", "example_study", "scenarios")


def _real_ir_pair():
    const = dict(ConstantConfig(os.path.join(EXAMPLE_SCENARIOS, "constant_config_ir.csv")))
    scen = dict(ScenarioConfig(os.path.join(EXAMPLE_SCENARIOS, "example_ir_only.csv"))[0])
    return const, scen


def test_dryrun_passes_on_real_ir_config(tmp_path):
    const, scen = _real_ir_pair()
    result = dryrun.dry_run(const, scen, str(tmp_path))
    assert result.ok, result.error


def test_dryrun_passes_on_hand_constructed_config(tmp_path):
    # A minimal solver-free IR config built from scratch in Python.
    const = {
        "sim_env": "ImmediateDecisionsSimulation",
        "network_type": "NetworkBasicWithStore",
        "network_name": "example_network",
        "demand_name": "example_demand",
        "random_seed": 0,
        "start_time": 0,
        "end_time": 3600,
        "time_step": 60,
        "nr_mod_operators": 1,
        "rq_type": "BasicRequest",
        "user_max_decision_time": 0,
        "op_const_boarding_time": 30,
        "op_vr_control_func_dict": {"func_key": "distance_and_user_times_with_walk", "vot": 0.45},
    }
    scen = {
        "op_module": "PoolingIRSOnly",
        "scenario_name": "handbuilt_sc_1",
        "rq_file": "example_100.csv",
        "op_fleet_composition": {"default_vehtype": 5},
    }
    result = dryrun.dry_run(const, scen, str(tmp_path))
    assert result.ok, result.error


def test_dryrun_fails_on_invalid_module(tmp_path):
    const, scen = _real_ir_pair()
    scen["op_module"] = "NotARealFleetControl"
    result = dryrun.dry_run(const, scen, str(tmp_path))
    assert not result.ok


def test_dryrun_leaves_no_study_dir(tmp_path):
    const, scen = _real_ir_pair()
    dryrun.dry_run(const, scen, str(tmp_path))
    leftover = os.path.join(REPO_ROOT, "studies", "copilot_dryrun")
    assert not os.path.exists(leftover), "dry-run left its throwaway study dir behind"
