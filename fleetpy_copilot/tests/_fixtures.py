"""Shared fixtures and canonical config sets for the M1 test campaign.

A plain importable module (not conftest fixtures) so pytest.mark.parametrize can
use these lists at collection time. All classifications below were verified by
running FleetPy's real loaders against the configs in this repo/.venv.
"""
import os

from src.misc.config import ConstantConfig, ScenarioConfig

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXAMPLE = os.path.join(REPO_ROOT, "studies", "example_study", "scenarios")
MODULE_TESTS = os.path.join(REPO_ROOT, "studies", "module_tests", "scenarios")


def _path(name: str) -> str:
    """Resolve a bare scenario filename under EXAMPLE, or pass through an abs path."""
    return name if os.path.isabs(name) else os.path.join(EXAMPLE, name)


def list_rows(scenario_name: str) -> list:
    """All scenario rows as dicts (FleetPy's ScenarioConfig skips #-commented rows)."""
    return [dict(c) for c in ScenarioConfig(_path(scenario_name))]


def n_rows(scenario_name: str) -> int:
    return len(list_rows(scenario_name))


def load_merged(const_name: str, scenario_name: str, row: int = 0) -> dict:
    """Constant + one scenario row, blanks stripped — exactly how FleetPy merges."""
    const = dict(ConstantConfig(_path(const_name)))
    scen = dict(ScenarioConfig(_path(scenario_name))[row])
    merged = {**const, **scen}
    return {k: v for k, v in merged.items() if not (v is None or v == "")}


# --- canonical, ground-truth-verified config sets ------------------------------

#: validate() -> ok on row 0 (genuinely solver-free; row 0 selects PoolingIRSOnly).
#: Note: example_depot / example_charge have LATER rows using
#: PoolingIRSAssignmentBatchOptimization, which the validator correctly flags as
#: missing op_rp_batch_optimizer (a mandatory module those fleet controls declare,
#: which FleetPy only silently defaults to AlonsoMora at runtime).
CLEAN_ACCEPT_PAIRS = [
    ("constant_config_ir.csv", "example_ir_only.csv"),
    ("constant_config_depot.csv", "example_depot.csv"),
    ("constant_config_charge.csv", "example_charge.csv"),
]

#: pairs whose EVERY row validates clean (all rows are PoolingIRSOnly)
ALL_ROWS_CLEAN_PAIRS = [
    ("constant_config_ir.csv", "example_ir_only.csv"),
]

#: dry_run().ok against real data on disk (fires the simulation __init__)
SOLVER_FREE_DRYRUN_PAIRS = [
    ("constant_config_ir.csv", "example_ir_only.csv"),
    ("constant_config_depot.csv", "example_depot.csv"),
    ("constant_config_charge.csv", "example_charge.csv"),
    ("constant_config_rpp.csv", "example_rpp.csv"),
]

#: real configs that FAIL validate only on vocabulary gaps (params absent from
#: the 201-name schema) — and are NOT dry-run loadable in this env
KNOWN_VOCAB_GAP_PAIRS = [
    ("constant_config_rpp.csv", "example_rpp.csv"),   # parcel_demand_name, seed
    ("constant_config_sod.csv", "example_sod.csv"),   # pt_* / schedule_file ...
    ("constant_config_ir.csv", "example_im.csv"),     # broker_* / pt_operator_type ...
]

#: configs that default to AlonsoMora (Gurobi) — kept OUT of the dry-run pass set
GUROBI_PAIRS = [
    ("constant_config_pool.csv", "example_pool.csv"),
    ("constant_config_depot_charge.csv", "example_depot_charge.csv"),
]

#: request files present under data/demand/example_demand/matched/example_network/
EXAMPLE_RQ_FILES = ["example_100.csv", "example_200.csv", "example_400.csv"]


# --- comprehensive enumeration of EVERY config in the repo's study dirs --------
import glob  # noqa: E402

_STUDY_SCENARIO_DIRS = [
    os.path.join(REPO_ROOT, "studies", "example_study", "scenarios"),
    os.path.join(REPO_ROOT, "studies", "module_tests", "scenarios"),
]


def all_config_rows():
    """Yield ``(filename, kind, row_index, config_dict)`` for every config row in
    every study scenario dir — constant configs (vertical, one dict) and scenario
    configs (horizontal, N rows). Blank cells are stripped exactly as FleetPy merges.

    This is the data source for the comprehensive value-check regression guard:
    the hard value checks must never flag any real config, so every row here must
    yield ``check_values(...) == {}``.
    """
    for d in _STUDY_SCENARIO_DIRS:
        for path in sorted(glob.glob(os.path.join(d, "*.csv"))):
            base = os.path.basename(path)
            if base.startswith("constant_config"):
                cfg = {k: v for k, v in dict(ConstantConfig(path)).items()
                       if not (v is None or v == "")}
                yield base, "const", 0, cfg
            else:
                sc = ScenarioConfig(path)
                for i in range(len(sc)):
                    cfg = {k: v for k, v in dict(sc[i]).items()
                           if not (v is None or v == "")}
                    yield base, "scenario", i, cfg

