"""serialize.py — turn a ``{param: value}`` dict into FleetPy's two CSV files.

Output mirrors ``studies/example_study/scenarios/`` exactly:

- constant config: ``Input_Parameter_Name,Parameter_Value`` header, then one
  ``key,value`` row per parameter (vertical).
- scenario config: parameter names as the header row, one row per scenario
  (horizontal). Scenario values override constant values at merge time.

``encode_value`` is the deliberate inverse of
``src/misc/config.py::decode_config_str`` for the value shapes real configs use.
The round-trip tests (load original -> write -> reload -> assert equal) are the
contract; we never compare against raw file text.
"""
from __future__ import annotations

import csv
import os
from typing import Dict, List, Mapping


def encode_value(value) -> str:
    """Encode a Python value into FleetPy's legacy config-string format.

    - ``dict``        -> ``k:v;k:v``
    - ``list``        -> ``;``-joined (nested lists -> ``|``-joined)
    - ``bool``        -> ``True`` / ``False``
    - ``None``/``""`` -> empty string
    - scalar          -> ``str(value)``
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, dict):
        return ";".join(f"{encode_value(k)}:{encode_value(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple)):
        if value and all(isinstance(x, (list, tuple)) for x in value):
            return "|".join(";".join(encode_value(x) for x in sub) for sub in value)
        return ";".join(encode_value(x) for x in value)
    return str(value)


def write_constant_config(config: Mapping[str, object], path: str) -> None:
    """Write a vertical constant-config CSV."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Input_Parameter_Name", "Parameter_Value"])
        for key, value in config.items():
            writer.writerow([key, encode_value(value)])


def write_scenario_config(scenarios: List[Mapping[str, object]], path: str) -> None:
    """Write a horizontal scenario CSV (one row per scenario).

    Columns are the union of keys across scenarios, in first-seen order.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    columns: List[str] = []
    for sc in scenarios:
        for key in sc:
            if key not in columns:
                columns.append(key)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for sc in scenarios:
            writer.writerow([encode_value(sc.get(col)) for col in columns])


def write_config_pair(
    constant_config: Mapping[str, object],
    scenarios: List[Mapping[str, object]],
    out_dir: str,
    tag: str = "config",
) -> Dict[str, str]:
    """Write both files under ``out_dir`` and return their paths."""
    const_path = os.path.join(out_dir, f"constant_config_{tag}.csv")
    scen_path = os.path.join(out_dir, f"{tag}.csv")
    write_constant_config(constant_config, const_path)
    write_scenario_config(scenarios, scen_path)
    return {"constant_config": const_path, "scenario_config": scen_path}
