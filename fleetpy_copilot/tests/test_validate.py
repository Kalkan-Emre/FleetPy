"""Tests for the deterministic validator and the inherit-chain resolver."""
import os

from src.misc.config import ConstantConfig, ScenarioConfig

from fleetpy_copilot import validate

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXAMPLE_SCENARIOS = os.path.join(REPO_ROOT, "studies", "example_study", "scenarios")


def _merged_ir_config():
    """The real IR config as FleetPy would see it: constant + first scenario row,
    blanks stripped."""
    const = ConstantConfig(os.path.join(EXAMPLE_SCENARIOS, "constant_config_ir.csv"))
    scen = ScenarioConfig(os.path.join(EXAMPLE_SCENARIOS, "example_ir_only.csv"))[0]
    merged = dict(const + scen)
    return {k: v for k, v in merged.items() if not (v is None or v == "")}


def test_accepts_real_config():
    result = validate.validate(_merged_ir_config())
    assert result.ok, result.summary()


def test_flags_hallucinated_param():
    cfg = _merged_ir_config()
    cfg["op_totally_made_up_param"] = 1
    result = validate.validate(cfg)
    assert not result.ok
    assert "op_totally_made_up_param" in result.unknown_params


def test_flags_invalid_module_value():
    cfg = _merged_ir_config()
    cfg["op_module"] = "NotARealFleetControl"
    result = validate.validate(cfg)
    assert not result.ok
    assert "op_module" in result.invalid_module_values


def test_flags_missing_mandatory():
    cfg = _merged_ir_config()
    del cfg["network_name"]
    result = validate.validate(cfg)
    assert not result.ok
    assert "network_name" in result.missing_mandatory


def test_summary_renders_every_error_channel():
    """summary() must mention each populated error channel (closes the
    unknown-params / type-errors / value-errors summary branches)."""
    r = validate.ValidationResult(
        unknown_params=["bogus_param"],
        invalid_module_values={"op_module": "Nope"},
        missing_mandatory=["network_name"],
        type_errors={"time_step": "expected int"},
        value_errors={"end_time": "must be > start_time"},
    )
    s = r.summary()
    assert not r.ok
    assert "unknown params" in s and "bogus_param" in s
    assert "invalid module values" in s
    assert "missing mandatory" in s
    assert "type errors" in s
    assert "value errors" in s


def test_summary_valid_when_clean():
    assert validate.ValidationResult().summary() == "valid"


def test_resolver_walks_inherit_chain():
    """The resolver must include both the base mandatory params AND the ones
    inherited from FleetControlBase via PoolingIRSOnly's two-link chain."""
    mandatory = validate.resolve_mandatory_params(_merged_ir_config())
    # base FleetSimulationBase mandatory set
    for name in (
        "scenario_name", "start_time", "end_time", "nr_mod_operators",
        "random_seed", "network_name", "demand_name", "rq_file", "user_max_decision_time",
    ):
        assert name in mandatory, f"missing base mandatory {name}"
    # inherited from the fleet-control chain (FleetControlBase)
    assert "op_fleet_composition" in mandatory
    assert "op_vr_control_func_dict" in mandatory
    # runner-supplied param must be excluded
    assert "study_name" not in mandatory
