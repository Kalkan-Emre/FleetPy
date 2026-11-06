"""Unit tests for the scalar type-checker in validate.py."""
import pytest

from fleetpy_copilot import validate


@pytest.mark.parametrize("v", [5, "5", "-3", "0", "  7  "])
def test_int_predicate_accepts(v):
    assert validate._is_int_value(v)


@pytest.mark.parametrize("v", [True, False, 5.0, "5.0", "abc", None, [1]])
def test_int_predicate_rejects(v):
    assert not validate._is_int_value(v)


@pytest.mark.parametrize("v", [5, 5.0, "5", "5.5", "-1e3"])
def test_float_predicate_accepts(v):
    assert validate._is_float_value(v)


@pytest.mark.parametrize("v", [True, "x", None, [1]])
def test_float_predicate_rejects(v):
    assert not validate._is_float_value(v)


@pytest.mark.parametrize("v", [True, False, "True", "False"])
def test_bool_predicate_accepts(v):
    assert validate._is_bool_value(v)


@pytest.mark.parametrize("v", [1, 0, "true", "yes", "maybe", None])
def test_bool_predicate_rejects(v):
    assert not validate._is_bool_value(v)


def test_normalize_type():
    assert validate._normalize_type("int") == "int"
    assert validate._normalize_type("Str") == "str"
    assert validate._normalize_type("") == ""
    assert validate._normalize_type("str (list representation of integers)") == ""


def test_blank_type_param_never_rejected():
    # scenario_name has an empty Type column -> any value is fine
    assert "scenario_name" not in validate.check_types({"scenario_name": 12345})


def test_str_and_Str_types_lenient():
    # op_fleet_composition is typed 'Str'; a dict/list value must not be rejected
    assert validate.check_types({"op_fleet_composition": {"default_vehtype": 5}}) == {}
    assert validate.check_types({"op_fleet_composition": [1, 2]}) == {}


def test_compound_type_lenient():
    # op_repo_horizons is typed 'str (list representation of integers)'
    assert validate.check_types({"op_repo_horizons": "0;900;1800"}) == {}


def test_unknown_param_not_type_checked():
    # unknown names are owned by unknown_params, not type_errors
    assert validate.check_types({"totally_made_up_param": object()}) == {}


def test_merged_decoded_int_passes():
    assert validate.check_types({"time_step": 60}) == {}


def test_handbuilt_string_int_passes():
    assert validate.check_types({"time_step": "60"}) == {}


def test_bool_not_treated_as_int():
    # nr_mod_operators is int-typed; a Python bool must be flagged
    assert "nr_mod_operators" in validate.check_types({"nr_mod_operators": True})


def test_wrong_scalar_values_flagged():
    errs = validate.check_types({"time_step": "sixty", "random_seed": "abc"})
    assert "time_step" in errs and "random_seed" in errs
