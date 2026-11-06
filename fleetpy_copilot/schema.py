"""schema.py — the closed vocabulary, derived live from FleetPy.

Nothing here is hand-maintained. Valid parameter names come from
``Input_Parameters.md`` (parsed by FleetPy's own ``scenario_creator``); valid
module values come from FleetPy's registry loaders. Because the vocabulary is a
closed set read from the simulator itself, it can never drift, and a parameter
or module value that FleetPy does not know is simply not a member of these sets.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict, List, Optional

from . import _fleetpy as _fp

#: every valid parameter name (the closed name vocabulary)
VALID_PARAM_NAMES: frozenset = frozenset(_fp.parameter_types.keys())

#: the parameters that select a module (and therefore have an enum of valid values)
MODULE_PARAMS: frozenset = frozenset(_fp.MODULE_PARAM_TO_DICT_LOAD.keys())


@lru_cache(maxsize=1)
def module_enums() -> Dict[str, List[str]]:
    """Map each module-selecting parameter (e.g. ``op_module``) to the sorted
    list of valid string keys, loaded live from FleetPy's registry functions."""
    enums: Dict[str, List[str]] = {}
    for param, loader in _fp.MODULE_PARAM_TO_DICT_LOAD.items():
        enums[param] = sorted(loader().keys())
    return enums


def valid_values_for(param: str) -> List[str]:
    """Valid values for a module-selecting parameter; ``[]`` if ``param`` is not
    module-selecting (i.e. free-valued)."""
    return module_enums().get(param, [])


def is_known_param(name: str) -> bool:
    return name in VALID_PARAM_NAMES


def default_for(name: str) -> Optional[object]:
    return _fp.parameter_defaults.get(name)


def doc_for(name: str) -> str:
    return _fp.parameter_docs.get(name, "")


def type_for(name: str) -> str:
    """Declared Type-column string for a param (``""`` if blank/unknown)."""
    return _fp.parameter_types.get(name, "") or ""
