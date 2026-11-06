"""Multi-row scenario sweeps: each row validates, comments are skipped, and the
whole file round-trips through the serializer."""
import pytest

from src.misc.config import ScenarioConfig

from fleetpy_copilot import serialize, validate
from fleetpy_copilot.tests import _fixtures as fx


def test_sod_seven_rows_consistent_vocab_gap():
    assert fx.n_rows("example_sod.csv") == 7
    for i in range(7):
        r = validate.validate(fx.load_merged("constant_config_sod.csv", "example_sod.csv", i))
        # every row fails the same way (pt_* vocab gap), never on a spurious type error
        assert r.unknown_params
        assert not r.type_errors


def test_im_four_rows_all_pooling_irsonly():
    rows = fx.list_rows("example_im.csv")
    assert len(rows) == 4
    assert all(row.get("op_module") == "PoolingIRSOnly" for row in rows)


def test_depot_charge_commented_row_skipped():
    rows = fx.list_rows("example_depot_charge.csv")
    assert len(rows) == 1
    assert rows[0]["op_module"] == "PoolingIRSAssignmentBatchOptimization"


@pytest.mark.parametrize("scen", ["example_sod.csv", "example_im.csv"], ids=["sod", "im"])
def test_multirow_serialize_roundtrip(scen, tmp_path):
    original = fx.list_rows(scen)
    out = str(tmp_path / "rt.csv")
    serialize.write_scenario_config(original, out)
    reloaded = [dict(c) for c in ScenarioConfig(out)]
    assert len(reloaded) == len(original)
    for orig_row, new_row in zip(original, reloaded):
        assert orig_row.keys() == new_row.keys()
        for key in orig_row:
            a, b = orig_row[key], new_row[key]
            # empty cells decode to NaN (float), which never compares equal to itself
            if _both_nan(a, b):
                continue
            assert a == b, f"{scen} key {key}: {a!r} != {b!r}"


def _both_nan(a, b) -> bool:
    import math
    try:
        return math.isnan(a) and math.isnan(b)
    except (TypeError, ValueError):
        return False
