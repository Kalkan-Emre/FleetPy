"""Round-trip tests for the serializer, using FleetPy's own loaders as the oracle."""
import os

from src.misc.config import ConstantConfig, ScenarioConfig

from fleetpy_copilot import serialize

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXAMPLE_SCENARIOS = os.path.join(REPO_ROOT, "studies", "example_study", "scenarios")


def test_constant_config_roundtrip(tmp_path):
    original = dict(ConstantConfig(os.path.join(EXAMPLE_SCENARIOS, "constant_config_ir.csv")))
    out = str(tmp_path / "constant_config_rt.csv")
    serialize.write_constant_config(original, out)
    reloaded = dict(ConstantConfig(out))
    assert reloaded == original


def test_scenario_config_roundtrip(tmp_path):
    original = [dict(c) for c in ScenarioConfig(os.path.join(EXAMPLE_SCENARIOS, "example_ir_only.csv"))]
    out = str(tmp_path / "scenario_rt.csv")
    serialize.write_scenario_config(original, out)
    reloaded = [dict(c) for c in ScenarioConfig(out)]
    assert reloaded == original


def test_hand_constructed_dict_and_list_survive(tmp_path):
    # A hand-built scenario whose values are Python dicts, not strings.
    scenario = {
        "op_module": "PoolingIRSOnly",
        "scenario_name": "handbuilt_sc_1",
        "rq_file": "example_100.csv",
        "op_fleet_composition": {"default_vehtype": 5},
        "op_vr_control_func_dict": {"func_key": "distance_and_user_times_with_walk", "vot": 0.45},
    }
    out = str(tmp_path / "handbuilt.csv")
    serialize.write_scenario_config([scenario], out)
    reloaded = dict(ScenarioConfig(out)[0])
    assert reloaded["op_vr_control_func_dict"] == {
        "func_key": "distance_and_user_times_with_walk",
        "vot": 0.45,
    }
    assert reloaded["op_fleet_composition"] == {"default_vehtype": 5}
    assert reloaded["scenario_name"] == "handbuilt_sc_1"


def test_encode_value_shapes():
    assert serialize.encode_value(None) == ""
    assert serialize.encode_value(True) == "True"
    assert serialize.encode_value(5) == "5"
    assert serialize.encode_value([1, 2, 3]) == "1;2;3"
    assert serialize.encode_value([[1, 2], [3, 4]]) == "1;2|3;4"
    assert serialize.encode_value({"a": 1, "b": 2}) == "a:1;b:2"
