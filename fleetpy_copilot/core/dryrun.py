"""dryrun.py — the functional-correctness gate.

A config is "runnable" if FleetPy can merge it and initialize the simulation
environment without error. We replicate ``run_scenarios`` up to — but NOT
including — ``.run()``: write the config to CSVs, reload through FleetPy's own
``ConstantConfig``/``ScenarioConfig`` (so every value is decoded exactly as in a
real run), merge, inject the runner-only params, and call
``load_simulation_environment`` (the full ``__init__`` — loads network + demand).
We stop before the time loop.

Output-directory isolation: FleetPy's ``get_directory_dict`` ALWAYS derives the
output path as ``studies/{study_name}/results/{scenario_name}`` and ignores any
injected ``G_DIR_OUTPUT``. So we force a throwaway ``study_name``/``scenario_name``
and delete that study directory afterwards. Network/demand dirs are always
repo-relative, so the gate reuses the real ``example_study`` data.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Dict, Mapping

from . import _fleetpy as _fp
from . import serialize

_DRYRUN_STUDY = "copilot_dryrun"
_DRYRUN_SCENARIO = "dryrun_sc"


@dataclass
class DryRunResult:
    ok: bool
    error: str = ""


def _reload_merged(constant: Mapping[str, object], scenario: Mapping[str, object], tmp: str) -> Dict[str, object]:
    """Serialize the candidate and reload it through FleetPy's loaders, then merge
    (scenario overrides constant). Guarantees values are decoded exactly as in a run."""
    from src.misc.config import ConstantConfig, ScenarioConfig

    paths = serialize.write_config_pair(constant, [scenario], tmp, tag="dryrun")
    const_cfg = ConstantConfig(paths["constant_config"])
    scen_cfg = ScenarioConfig(paths["scenario_config"])[0]
    return dict(const_cfg + scen_cfg)


def dry_run(
    constant_config: Mapping[str, object],
    scenario: Mapping[str, object],
    work_dir: str,
) -> DryRunResult:
    """Attempt to load+initialize the config in FleetPy. Returns ok/error.

    Never calls ``.run()``. ``work_dir`` holds the intermediate CSVs. FleetPy's
    own output lands under ``studies/copilot_dryrun/`` (unavoidable) and is
    removed afterwards.
    """
    from src.misc.globals import G_STUDY_NAME, G_SCENARIO_NAME
    from src.misc.init_modules import load_simulation_environment

    params = _reload_merged(constant_config, scenario, work_dir)
    params = {k: v for k, v in params.items() if not (v is None or v == "")}

    # throwaway study/scenario so FleetPy writes to a known, disposable location
    params[G_STUDY_NAME] = _DRYRUN_STUDY
    params[G_SCENARIO_NAME] = _DRYRUN_SCENARIO
    # runner-only params injected by run_scenarios.py:77-80 (not config-file params)
    params.setdefault("n_cpu_per_sim", 1)
    params.setdefault("evaluate", 0)
    params.setdefault("log_level", "warning")
    params.setdefault("keep_old", False)

    study_output = os.path.join(_fp.REPO_ROOT, "studies", _DRYRUN_STUDY)
    try:
        load_simulation_environment(params)  # runs __init__; never .run()
        return DryRunResult(ok=True)
    except Exception as exc:  # noqa: BLE001 — any init failure means not-runnable
        return DryRunResult(ok=False, error=f"{type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(study_output, ignore_errors=True)


def dry_run_tmp(constant_config: Mapping[str, object], scenario: Mapping[str, object]) -> DryRunResult:
    """Convenience wrapper that supplies its own temp dir for the intermediate CSVs."""
    with tempfile.TemporaryDirectory() as tmp:
        return dry_run(constant_config, scenario, tmp)
