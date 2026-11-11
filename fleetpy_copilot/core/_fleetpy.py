"""_fleetpy.py — the single bridge to FleetPy's internals.

Importing FleetPy's ``scenario_creator`` is expensive and side-effectful: it
reads ``Input_Parameters.md`` and instantiates all module registries at import
time. We do that once, here, and re-export the handful of assets the rest of the
package needs. Every other module imports from ``_fleetpy`` so the sys.path
handling and the one eager import live in exactly one place.

Nothing here mutates FleetPy; everything is read-only.
"""
from __future__ import annotations

import os
import sys

#: repo root (two levels up from this file: fleetpy_copilot/_fleetpy.py -> repo)
REPO_ROOT: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# --- schema + module vocabulary, parsed live from Input_Parameters.md ----------
from src.scenario_gui.scenario_creator import (  # noqa: E402
    parameter_types,
    parameter_defaults,
    parameter_docs,
    MODULE_PARAM_TO_DICT_LOAD,
    CLASS_NAME_TO_STR_KEY,
    load_module_parameters,
)

# --- canonical mandatory/optional sets for the base simulation class -----------
from src.FleetSimulationBase import INPUT_PARAMETERS_FleetSimulationBase  # noqa: E402

__all__ = [
    "REPO_ROOT",
    "parameter_types",
    "parameter_defaults",
    "parameter_docs",
    "MODULE_PARAM_TO_DICT_LOAD",
    "CLASS_NAME_TO_STR_KEY",
    "load_module_parameters",
    "INPUT_PARAMETERS_FleetSimulationBase",
]
