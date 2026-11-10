"""prompts.py — deterministic NL-prompt derivation for the baseline harness.

For a fair, reproducible baseline we need one natural-language prompt per seed
config, produced the same way every run so the scoreboard is comparable across
prompt-version changes. We therefore derive the prompt as a FIXED FUNCTION of the
seed config's own fields (a template), not by hand and not via another LLM call.
The bias this introduces is at least uniform across the corpus.

The template intentionally describes the scenario in user terms (what a person
would say) and does NOT leak exact parameter names/values the copilot is supposed
to infer — it names the *intent* (immediate-response ride-pooling, N vehicles, a
duration), letting the closed-vocabulary mapping remain the copilot's job.
"""
from __future__ import annotations

from typing import Mapping

#: Bump when the template wording changes (separate from the copilot's PROMPT_VERSION).
PROMPT_TEMPLATE_VERSION = "t1"

#: Human phrasing for the sim_env values we actually exercise.
_SIM_ENV_PHRASE = {
    "ImmediateDecisionsSimulation": "immediate-response",
    "BatchOfferSimulation": "batch-offer",
}


def _fleet_size(cfg: Mapping[str, object]) -> object:
    """Pull a vehicle count out of op_fleet_composition ({'default_vehtype': 5})
    or return None if not expressible."""
    comp = cfg.get("op_fleet_composition")
    if isinstance(comp, Mapping):
        total = 0
        for v in comp.values():
            try:
                total += int(v)
            except (TypeError, ValueError):
                return None
        return total or None
    return None


def derive_prompt(seed_config: Mapping[str, object]) -> str:
    """A deterministic natural-language request describing ``seed_config``.

    Keys off intent-level fields (sim decision mode, network, duration, fleet size,
    operator count); omits anything not present so the sentence stays truthful.
    """
    parts = []

    mode = _SIM_ENV_PHRASE.get(str(seed_config.get("sim_env", "")), "")
    parts.append(f"Set up a{' ' + mode if mode else 'n'} ride-pooling simulation")

    net = seed_config.get("network_name")
    if net:
        parts.append(f"on the {net} network")

    start, end = seed_config.get("start_time"), seed_config.get("end_time")
    if isinstance(start, (int, float)) and isinstance(end, (int, float)):
        hours = (end - start) / 3600.0
        if hours and hours == int(hours):
            parts.append(f"for {int(hours)} hour{'s' if hours != 1 else ''}")
        else:
            parts.append(f"from {int(start)} to {int(end)} seconds")

    fleet = _fleet_size(seed_config)
    if fleet:
        parts.append(f"with {fleet} vehicles")

    n_ops = seed_config.get("nr_mod_operators")
    if isinstance(n_ops, (int, float)) and int(n_ops) == 1:
        parts.append("and a single operator")
    elif isinstance(n_ops, (int, float)):
        parts.append(f"and {int(n_ops)} operators")

    demand = seed_config.get("demand_name")
    if demand:
        parts.append(f"using the {demand} demand")

    return " ".join(parts) + "."
