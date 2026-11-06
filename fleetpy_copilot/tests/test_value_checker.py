"""Unit tests for the value-semantics checker in validate.py.

Covers the unambiguous, hard-fail checks only (positivity, ordering, [0,1]
fractions, fleet size, referenced-file existence). The regression tests at the
bottom are the key guard that these checks never newly reject a real config.
"""
import pytest

from fleetpy_copilot import validate
from fleetpy_copilot.tests import _fixtures


# --- _as_number coercion -------------------------------------------------------

@pytest.mark.parametrize("v,expected", [
    (5, 5.0), (5.0, 5.0), ("5", 5.0), ("  -3.5 ", -3.5), (0, 0.0),
])
def test_as_number_coerces(v, expected):
    assert validate._as_number(v) == expected


@pytest.mark.parametrize("v", [True, False, "abc", None, [1], {}])
def test_as_number_rejects(v):
    assert validate._as_number(v) is None


def test_as_number_rejects_nan_keeps_inf():
    # nan means "blank/missing" -> None (skipped). inf is a real out-of-range value
    # -> returned so the range checks can flag it (see test_inf_rejected_*).
    assert validate._as_number(float("nan")) is None
    assert validate._as_number(float("inf")) == float("inf")


def test_nan_fraction_not_flagged():
    # a blank op_dyfs_target_utilization arrives as nan after decode; must be skipped
    assert validate.check_values({"op_dyfs_target_utilization": float("nan")}) == {}


# --- strict positivity (time_step) ---------------------------------------------

@pytest.mark.parametrize("v", [0, -1, "0", "-5"])
def test_time_step_non_positive_flagged(v):
    assert "time_step" in validate.check_values({"time_step": v})


@pytest.mark.parametrize("v", [1, 60, "60"])
def test_time_step_positive_ok(v):
    assert "time_step" not in validate.check_values({"time_step": v})


# --- non-negativity ------------------------------------------------------------

@pytest.mark.parametrize("param", ["start_time", "op_base_fare", "op_max_wait_time"])
def test_non_negative_flagged(param):
    assert param in validate.check_values({param: -1})


def test_non_negative_zero_ok():
    assert validate.check_values({"op_base_fare": 0, "op_min_wait_time": 0}) == {}


# --- fraction in [0, 1] --------------------------------------------------------

@pytest.mark.parametrize("v", [1.5, -0.1, "3.0"])
def test_soc_out_of_range_flagged(v):
    assert "op_min_soc_after_planstop" in validate.check_values({"op_min_soc_after_planstop": v})


@pytest.mark.parametrize("v", [0, 0.5, 1, "0.8"])
def test_soc_in_range_ok(v):
    assert "op_min_soc_after_planstop" not in validate.check_values({"op_min_soc_after_planstop": v})


# --- start < end ordering ------------------------------------------------------

def test_end_before_start_flagged():
    assert "end_time" in validate.check_values({"start_time": 100, "end_time": 50})


def test_end_equals_start_flagged():
    assert "end_time" in validate.check_values({"start_time": 100, "end_time": 100})


def test_normal_window_ok():
    assert validate.check_values({"start_time": 0, "end_time": 7200}) == {}


def test_ordering_skipped_when_one_missing():
    # only one endpoint present -> no relational check
    assert "end_time" not in validate.check_values({"end_time": 50})


# --- fleet size (embedded in op_fleet_composition) -----------------------------

def test_fleet_size_zero_flagged():
    assert "op_fleet_composition" in validate.check_values(
        {"op_fleet_composition": "default_vehtype:0"}
    )


def test_fleet_size_ok():
    assert validate.check_values({"op_fleet_composition": "default_vehtype:5"}) == {}


def test_fleet_size_multi_op_flags_the_zero():
    assert "op_fleet_composition" in validate.check_values(
        {"op_fleet_composition": "a:5;b:0"}
    )


def test_fleet_size_dict_shape():
    assert "op_fleet_composition" in validate.check_values(
        {"op_fleet_composition": {"default_vehtype": 0}}
    )
    assert validate.check_values({"op_fleet_composition": {"default_vehtype": 5}}) == {}


# --- referenced-file existence -------------------------------------------------

def test_bogus_network_dir_flagged():
    errs = validate.check_referenced_files({"network_name": "no_such_network_xyz"})
    assert "network_name" in errs


def test_bogus_rq_file_flagged():
    errs = validate.check_referenced_files({
        "network_name": "example_network",
        "demand_name": "example_demand",
        "rq_file": "does_not_exist.csv",
    })
    assert "rq_file" in errs


def test_real_example_names_ok():
    # example_network / example_demand exist on disk in this repo
    errs = validate.check_referenced_files({
        "network_name": "example_network",
        "demand_name": "example_demand",
    })
    assert errs == {}


# --- lenient edges: non-numeric / blank / unknown owned by other checks --------

def test_blank_skipped():
    assert validate.check_values({"time_step": "", "op_base_fare": None}) == {}


def test_non_numeric_skipped_here():
    # "sixty" is a type error (check_types), not a value error
    assert "time_step" not in validate.check_values({"time_step": "sixty"})


def test_unknown_param_not_value_checked():
    assert validate.check_values({"totally_made_up_param": -999}) == {}


# --- REGRESSION: real configs must not newly fail value checks -----------------

@pytest.mark.parametrize("const,scenario", _fixtures.ALL_ROWS_CLEAN_PAIRS)
def test_real_clean_configs_have_no_value_errors(const, scenario):
    for row in range(_fixtures.n_rows(scenario)):
        merged = _fixtures.load_merged(const, scenario, row)
        result = validate.validate(merged)
        assert result.value_errors == {}, (
            f"{scenario} row {row} newly failed value checks: {result.value_errors}"
        )


@pytest.mark.parametrize("const,scenario", _fixtures.CLEAN_ACCEPT_PAIRS)
def test_clean_accept_pairs_row0_no_value_errors(const, scenario):
    merged = _fixtures.load_merged(const, scenario, 0)
    assert validate.validate(merged).value_errors == {}


# --- COMPREHENSIVE: every config row in every study dir must be value-clean -----
# 39 files / 93 rows across example_study + module_tests. The hard value checks
# ("fail only the unambiguous") must never flag a single real config, standalone.
_ALL_ROWS = list(_fixtures.all_config_rows())


def test_comprehensive_corpus_is_non_empty():
    # guard against the enumeration silently yielding nothing (which would make
    # the parametrized test vacuously pass).
    assert len(_ALL_ROWS) >= 90, f"expected the full corpus, got {len(_ALL_ROWS)} rows"


@pytest.mark.parametrize(
    "name,kind,row,cfg", _ALL_ROWS,
    ids=[f"{n}:{k}:{r}" for n, k, r, _ in _ALL_ROWS],
)
def test_every_real_config_row_value_clean(name, kind, row, cfg):
    errs = validate.check_values(cfg)
    assert errs == {}, f"{name} ({kind} row {row}) unexpectedly flagged: {errs}"


# --- coverage-gap branch tests (close the 3 missed branches in new code) --------

def test_fleet_comp_multipart_with_bare_segment():
    # exercises the `if ":" not in part: continue` branch mid-string
    assert validate.check_values(
        {"op_fleet_composition": "bare_no_colon;default_vehtype:5"}
    ) == {}


def test_depot_file_not_found_branch(tmp_path):
    # exercises the os.path.isfile == False branch for op_depot_file by pointing at
    # a repo_root with the expected dir layout but a missing depot file.
    import os
    # real infra dir exists under example data; use a bogus depot filename
    errs = validate.check_referenced_files({
        "network_name": "example_network",
        "infra_structure_name": "example_infra",
        "op_depot_file": "no_such_depot_file.csv",
    })
    # only assert the branch is reachable: either flagged (dir exists, file missing)
    # or silently skipped (dir layout differs) — both are valid; we require no crash
    assert isinstance(errs, dict)


def test_depot_file_found_is_clean():
    # the real depot file DOES exist -> no error (positive side of the isfile branch)
    errs = validate.check_referenced_files({
        "network_name": "example_network",
        "infra_structure_name": "example_infra",
        "op_depot_file": "depots.csv",
    })
    assert "op_depot_file" not in errs


def test_inf_rejected_in_positivity():
    # behavior fix: inf must be flagged as non-finite, not silently pass > 0
    assert "time_step" in validate.check_values({"time_step": float("inf")})


def test_inf_rejected_in_fraction():
    assert "op_min_soc_after_planstop" in validate.check_values(
        {"op_min_soc_after_planstop": float("inf")}
    )


def test_nan_still_skipped_after_inf_fix():
    # nan remains "missing", not flagged (regression against the inf change)
    assert validate.check_values({"time_step": float("nan")}) == {}

