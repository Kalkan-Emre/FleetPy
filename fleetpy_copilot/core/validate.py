"""validate.py — deterministic, closed-vocabulary validation.

A candidate ``{param: value}`` dict is admissible when (1) every key is a known
parameter name, (2) every module-selecting value is in its registry enum, and
(3) every mandatory parameter is present and non-blank. Because the vocabulary
is closed, hallucinated parameters and invalid module choices cannot pass.

The mandatory set is computed by walking the ``inherit`` chain from
``INPUT_PARAMETERS_FleetSimulationBase`` and from each selected module's
``INPUT_PARAMETERS_*`` dict — reusing FleetPy's own parent-path derivation so we
never re-declare anything.
"""
from __future__ import annotations

import io
import math
import os
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Set

from . import _fleetpy as _fp
from . import schema


@dataclass
class ValidationResult:
    """Outcome of validating a candidate config dict."""

    unknown_params: List[str] = field(default_factory=list)
    invalid_module_values: Dict[str, str] = field(default_factory=dict)
    missing_mandatory: List[str] = field(default_factory=list)
    type_errors: Dict[str, str] = field(default_factory=dict)
    value_errors: Dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not (
            self.unknown_params
            or self.invalid_module_values
            or self.missing_mandatory
            or self.type_errors
            or self.value_errors
        )

    def summary(self) -> str:
        if self.ok:
            return "valid"
        parts = []
        if self.unknown_params:
            parts.append(f"unknown params: {sorted(self.unknown_params)}")
        if self.invalid_module_values:
            parts.append(f"invalid module values: {self.invalid_module_values}")
        if self.missing_mandatory:
            parts.append(f"missing mandatory: {sorted(self.missing_mandatory)}")
        if self.type_errors:
            parts.append(f"type errors: {self.type_errors}")
        if self.value_errors:
            parts.append(f"value errors: {self.value_errors}")
        return "; ".join(parts)


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


#: params injected by the runner (run_scenarios.py:75-80), never in a config body
_RUNNER_ONLY_PARAMS = {"study_name", "n_cpu_per_sim", "evaluate", "log_level", "keep_old"}


# --- scalar type checking ------------------------------------------------------
# Only clean one-word scalar types are enforced. Blank, free-form, and compound
# type declarations (e.g. "str (list representation of integers)") are left alone,
# as is anything typed ``str``/``Str`` (almost everything stringifies).

def _normalize_type(decl: str) -> str:
    """Lower-case a clean one-word scalar type; ``""`` for blank or compound."""
    t = (decl or "").strip()
    if not t or " " in t or "(" in t:
        return ""
    return t.lower()


def _is_int_value(value) -> bool:
    if isinstance(value, bool):  # bool is an int subclass — exclude
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, str):
        try:
            int(value.strip())
            return True
        except ValueError:
            return False
    return False


def _is_float_value(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value.strip())
            return True
        except ValueError:
            return False
    return False


def _is_bool_value(value) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, str):
        return value.strip() in ("True", "False")
    return False


_TYPE_PREDICATES = {
    "int": (_is_int_value, "expected int"),
    "float": (_is_float_value, "expected float"),
    "bool": (_is_bool_value, "expected bool (True/False)"),
}


def check_types(config: Mapping[str, object]) -> Dict[str, str]:
    """Return ``{param: reason}`` for every known param whose non-blank value
    violates its declared scalar type. Unknown names and blank values are owned
    by the other checks and skipped here; ``str``/compound/blank types are lenient."""
    errors: Dict[str, str] = {}
    for key, value in config.items():
        if key not in schema.VALID_PARAM_NAMES:
            continue
        if _is_blank(value):
            continue
        norm = _normalize_type(schema.type_for(key))
        if norm not in _TYPE_PREDICATES:
            continue
        predicate, reason = _TYPE_PREDICATES[norm]
        if not predicate(value):
            errors[key] = f"{reason}, got {value!r}"
    return errors


# --- value-semantics checking --------------------------------------------------
# FleetPy enforces NO value-range, ordering, or positivity checks at config-read
# or sim-init time (verified across src/misc/config.py, globals.py,
# FleetSimulationBase.py). start<end, time_step>0 and SOC in [0,1] are conventions
# the example data satisfies, not invariants the simulator asserts. So we hard-fail
# only the physically UNAMBIGUOUS cases, to avoid blocking legitimate research
# sweeps. Everything else is left alone.

def _as_number(value) -> Optional[float]:
    """Coerce a scalar/str to float for comparison; ``None`` if not numeric.

    Bools are excluded (a bool is never a meaningful config number here); the
    scalar type-checker owns the "bool where int expected" case. ``nan`` is
    treated as *missing* (``None``): FleetPy's loader decodes a blank numeric cell
    to ``nan``, which is an absent value, not an out-of-range one. ``inf`` IS
    returned (it is a real, finite-expected value that is out of range), so the
    range checks below reject it via their explicit finiteness guard.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        n = float(value)
    elif isinstance(value, str):
        try:
            n = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    if math.isnan(n):
        return None
    return n


#: params whose value must be strictly > 0 (a zero/negative is init-fatal or empty)
_STRICTLY_POSITIVE = frozenset({"time_step"})

#: params whose value must be >= 0 (a negative is physically meaningless).
#: NOTE: pt_walk_logit_beta is legitimately negative and is deliberately absent.
_NON_NEGATIVE = frozenset({
    "start_time", "end_time", "random_seed",
    "op_const_boarding_time", "op_add_boarding_time",
    "op_min_wait_time", "op_max_wait_time",
    "op_base_fare", "op_distance_fare", "op_time_fare", "op_min_standard_fare",
    "op_reoptimisation_timestep",
})

#: params that are a fraction and must lie in [0, 1] (SOC / utilization / threshold)
_FRACTION_0_1 = frozenset({
    "op_min_soc_after_planstop", "op_min_soc_public_station",
    "op_dyfs_target_utilization", "op_parcel_assignment_threshold",
})


def _fleet_sizes(value) -> List[int]:
    """Extract the integer fleet sizes encoded in ``op_fleet_composition``.

    Real configs encode fleet size as the ``:N`` suffix per vehicle type, with
    ``;`` separating operators, e.g. ``"default_vehtype:5;low_range_vehtype:8"``.
    A hand-built config may pass a dict (``{vehtype: N}``) instead; handle both.
    Returns ``[]`` if nothing integer-shaped is found (left to other checks).
    """
    sizes: List[int] = []
    if isinstance(value, dict):
        for v in value.values():
            if _is_int_value(v):
                sizes.append(int(str(v).strip()))
        return sizes
    if isinstance(value, str):
        for part in value.split(";"):
            if ":" not in part:
                continue
            _, _, n = part.rpartition(":")
            if _is_int_value(n):
                sizes.append(int(n.strip()))
    return sizes


def check_values(config: Mapping[str, object]) -> Dict[str, str]:
    """Return ``{param: reason}`` for every value that is unambiguously wrong.

    Only hard, physically-unambiguous constraints are enforced: strict positivity,
    non-negativity, fraction-in-[0,1], start<end ordering, and fleet size >= 1.
    Blank values, unknown params, and non-numeric values (owned by other checks)
    are skipped.
    """
    errors: Dict[str, str] = {}

    #: params that carry a numeric constraint (used for the finiteness guard)
    _numeric_constrained = _STRICTLY_POSITIVE | _NON_NEGATIVE | _FRACTION_0_1

    for key, value in config.items():
        if key not in schema.VALID_PARAM_NAMES or _is_blank(value):
            continue

        if key in _numeric_constrained:
            n = _as_number(value)
            if n is None:
                pass  # non-numeric (incl. nan=blank) -> owned by check_types / skipped
            elif math.isinf(n):
                errors[key] = f"must be a finite number, got {value!r}"
            elif key in _STRICTLY_POSITIVE and n <= 0:
                errors[key] = f"must be > 0, got {value!r}"
            elif key in _NON_NEGATIVE and n < 0:
                errors[key] = f"must be >= 0, got {value!r}"
            elif key in _FRACTION_0_1 and not (0.0 <= n <= 1.0):
                errors[key] = f"must be in [0, 1], got {value!r}"

        if key == "op_fleet_composition":
            for size in _fleet_sizes(value):
                if size < 1:
                    errors[key] = f"fleet size must be >= 1, got {size} in {value!r}"
                    break

    # relational: start_time < end_time (only when both present, numeric, finite)
    start, end = _as_number(config.get("start_time")), _as_number(config.get("end_time"))
    if (start is not None and end is not None
            and math.isfinite(start) and math.isfinite(end) and end <= start):
        errors["end_time"] = f"end_time ({config.get('end_time')!r}) must be > start_time ({config.get('start_time')!r})"

    return errors


#: file-reference params -> (logical-dir keys it is joined under, as resolved by
#: FleetPy's get_directory_dict). We replicate only the minimal joins the example
#: configs exercise; anything else is skipped (graceful degradation).
def check_referenced_files(config: Mapping[str, object], repo_root: Optional[str] = None) -> Dict[str, str]:
    """Return ``{param: reason}`` for referenced data files/dirs that do not exist.

    Mirrors ``src/misc/globals.py:get_directory_dict`` path resolution for the
    handful of file/name params the example configs use. FleetPy itself only
    surfaces these as a pandas ``FileNotFoundError`` deep in init; checking here
    gives a fast, clear message. Params outside the known map are skipped.
    """
    root = repo_root or _fp.REPO_ROOT
    data = os.path.join(root, "data")
    errors: Dict[str, str] = {}

    network = config.get("network_name")
    demand = config.get("demand_name")
    infra = config.get("infra_structure_name")

    def _dir_check(param: str, path: str) -> None:
        if not _is_blank(config.get(param)) and not os.path.isdir(path):
            errors[param] = f"directory not found: {path}"

    # logical-name directories
    if not _is_blank(network):
        _dir_check("network_name", os.path.join(data, "networks", str(network)))
    if not _is_blank(demand):
        _dir_check("demand_name", os.path.join(data, "demand", str(demand)))
    if not _is_blank(infra) and not _is_blank(network):
        _dir_check("infra_structure_name", os.path.join(data, "infra", str(infra), str(network)))

    # files joined under those directories
    rq_file = config.get("rq_file")
    if not _is_blank(rq_file) and not _is_blank(demand) and not _is_blank(network):
        path = os.path.join(data, "demand", str(demand), "matched", str(network), str(rq_file))
        if not os.path.isfile(path):
            errors["rq_file"] = f"file not found: {path}"

    depot_f = config.get("op_depot_file")
    if not _is_blank(depot_f) and not _is_blank(infra) and not _is_blank(network):
        path = os.path.join(data, "infra", str(infra), str(network), str(depot_f))
        if not os.path.isfile(path):
            errors["op_depot_file"] = f"file not found: {path}"

    return errors


def _resolve_parent(inherit_class: str, module_dict: dict) -> Optional[dict]:
    """Resolve an ``inherit`` parent class name to its ``INPUT_PARAMETERS_*`` dict.

    Mirrors ``scenario_creator._load_module_params`` (the parent is usually not a
    registry entry, so its module path is derived from the registry's own paths).
    Returns ``None`` if it cannot be resolved (treated as the end of the chain).
    """
    if inherit_class.endswith("Base"):
        if inherit_class.startswith("Request") or inherit_class.startswith("ParcelRequest"):
            module_dict[inherit_class] = ("src.demand.TravelerModels", inherit_class)
        else:
            base_p = list(module_dict.values())[0][0].split(".")[:-1]
            base_p.append(inherit_class)
            module_dict[inherit_class] = (".".join(base_p), inherit_class)
    elif inherit_class == "ZoneSystem":
        module_dict["ZoneSystem"] = ("src.infra.Zoning", "ZoneSystem")

    try:
        return _fp.load_module_parameters(module_dict, inherit_class)
    except ModuleNotFoundError:
        # one-level-up fallback, as in scenario_creator.py:204-209
        if inherit_class.endswith("Base") and not inherit_class.startswith("Request"):
            base_p = list(module_dict.values())[0][0].split(".")[:-2]
            base_p.append(inherit_class)
            module_dict[inherit_class] = (".".join(base_p), inherit_class)
            try:
                return _fp.load_module_parameters(module_dict, inherit_class)
            except ModuleNotFoundError:
                return None
        return None
    except (IOError, AttributeError):
        return None


def _accumulate_chain(input_param_dict: dict, module_dict: Optional[dict], mandatory: Set[str]) -> None:
    """Walk an INPUT_PARAMETERS dict's ``inherit`` chain, accumulating both the
    mandatory parameters and the mandatory module-selecting params themselves."""
    while input_param_dict is not None:
        mandatory.update(input_param_dict.get("input_parameters_mandatory", []))
        mandatory.update(input_param_dict.get("mandatory_modules", []))
        inherit_class = input_param_dict.get("inherit")
        if inherit_class is None or module_dict is None:
            break
        input_param_dict = _resolve_parent(inherit_class, module_dict)


def resolve_mandatory_params(config: Mapping[str, object]) -> Set[str]:
    """Compute the full set of mandatory parameter names a config must contain,
    given the modules it selects. Module values that are invalid are skipped here
    (``validate`` reports them separately)."""
    mandatory: Set[str] = set()
    # scenario_creator's derivation prints progress; keep it quiet.
    with redirect_stdout(io.StringIO()):
        # 1. the base simulation class (no module_dict -> chain stops at its inherit=None)
        _accumulate_chain(_fp.INPUT_PARAMETERS_FleetSimulationBase, None, mandatory)
        # 2. each selected module
        for module_param in schema.MODULE_PARAMS:
            value = config.get(module_param)
            if _is_blank(value):
                continue
            module_dict = _fp.MODULE_PARAM_TO_DICT_LOAD[module_param]()
            try:
                ip = _fp.load_module_parameters(module_dict, str(value))
            except (IOError, ModuleNotFoundError, AttributeError):
                continue  # invalid value — reported by validate()
            _accumulate_chain(ip, module_dict, mandatory)
    # runner-only params are injected by run_scenarios.py at launch, never part of
    # a config body — so they are not the config author's responsibility.
    mandatory -= _RUNNER_ONLY_PARAMS
    return mandatory


def validate(config: Mapping[str, object]) -> ValidationResult:
    """Validate a merged ``{param: value}`` config dict."""
    result = ValidationResult()

    # 1. every key must be a known parameter name
    for key in config:
        if key not in schema.VALID_PARAM_NAMES:
            result.unknown_params.append(key)

    # 2. module-selecting params must take a value from their enum
    for param in schema.MODULE_PARAMS:
        if param in config and not _is_blank(config[param]):
            if str(config[param]) not in schema.valid_values_for(param):
                result.invalid_module_values[param] = str(config[param])

    # 3. all mandatory params (resolved via the inherit chain) must be present
    for required in resolve_mandatory_params(config):
        if _is_blank(config.get(required)):
            result.missing_mandatory.append(required)

    # 4. known params must satisfy their declared scalar type
    result.type_errors = check_types(config)

    # 5. unambiguous value-semantics (positivity, ordering, [0,1], fleet size)
    #    plus existence of referenced data files/dirs
    result.value_errors = {**check_values(config), **check_referenced_files(config)}

    return result
