"""Tests for the closed-vocabulary schema."""
from fleetpy_copilot import schema


def test_schema_has_all_params():
    assert len(schema.VALID_PARAM_NAMES) > 150
    for name in ("scenario_name", "start_time", "end_time", "network_name"):
        assert name in schema.VALID_PARAM_NAMES


def test_module_enums_populated():
    enums = schema.module_enums()
    assert "op_module" in enums
    assert "sim_env" in enums
    assert "PoolingIRSOnly" in enums["op_module"]
    assert "ImmediateDecisionsSimulation" in enums["sim_env"]
    # every module-selecting param resolves to a non-empty enum
    for param in schema.MODULE_PARAMS:
        assert schema.valid_values_for(param), f"empty enum for {param}"


def test_valid_values_for_non_module_param():
    assert schema.valid_values_for("start_time") == []


def test_helpers():
    assert schema.is_known_param("network_name")
    assert not schema.is_known_param("totally_made_up")
    assert isinstance(schema.doc_for("network_name"), str)
