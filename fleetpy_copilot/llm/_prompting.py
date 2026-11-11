"""_prompting.py — shared prompt construction + reply parsing for real providers.

A real LLM must (1) be told it may use only FleetPy's closed vocabulary and
return JSON, (2) receive any validation ``correction`` from a prior attempt, and
(3) have its free-text reply parsed back into a ``{param: value}`` dict. Both the
OpenAI-compatible and Anthropic providers share this, so prompt wording and JSON
extraction live in one place (and can be unit-tested without a network).

The deterministic validator remains the authority — this module only *shapes* the
request and *extracts* the dict; it never judges correctness.
"""
from __future__ import annotations

import json
import re
from typing import Dict, Mapping, Optional

from fleetpy_copilot.core import schema

#: Version of the prompt surface (system + user builders below). Bump whenever the
#: wording or grounding changes, and add a PROMPT_CHANGELOG.md entry, so a scoreboard
#: can be attributed to the exact prompt that produced it (M2.5).
PROMPT_VERSION = "v2"

_SYSTEM = (
    "You translate a natural-language Mobility-on-Demand simulation request into a "
    "FleetPy scenario configuration. Return ONLY a single JSON object mapping "
    "parameter names to values — no prose, no explanation, no markdown fences. "
    "Use ONLY parameter names and module values from the provided schema; never "
    "invent a name or a module value. For a module-selecting parameter you MUST "
    "choose one of its listed valid values verbatim. If you are unsure of a "
    "parameter, OMIT it rather than guessing — a missing value will be asked for, "
    "but a wrong value is a mistake."
)


def build_system_prompt(schema_hint: Optional[Mapping[str, object]] = None) -> str:
    """Compose the system prompt, grounding the model in the closed vocabulary.

    ``schema_hint`` may override the default (e.g. a trimmed, task-relevant slice);
    when absent we attach the module-selecting params and their enums, which is the
    part a model most needs and most often gets wrong.
    """
    if schema_hint and "text" in schema_hint:
        return str(schema_hint["text"])
    enums = schema.module_enums()
    enum_lines = "\n".join(f"  {p}: {vals}" for p, vals in sorted(enums.items()))
    # v2: list ALL valid parameter names, not just the count. Finding A from the
    # first live baseline: the model invented plausible-but-invalid names
    # (number_of_vehicles, simulation_time_steps) which validation then dropped.
    # Giving it the real closed name-set lets it pick correct names (e.g.
    # op_fleet_composition, start_time/end_time) instead of inventing them.
    all_names = ", ".join(sorted(schema.VALID_PARAM_NAMES))
    return (
        f"{_SYSTEM}\n\n"
        f"Module-selecting parameters and their ONLY valid values:\n{enum_lines}\n\n"
        f"The ONLY valid parameter names ({len(schema.VALID_PARAM_NAMES)} total) are:\n"
        f"{all_names}\n\n"
        f"Use a name from this list verbatim or omit it; any other name is invalid "
        f"and will be discarded."
    )


def build_user_prompt(prompt: str, correction: Optional[str] = None) -> str:
    """The user turn: the request, plus any correction from a prior failed attempt."""
    if correction:
        return (
            f"{prompt}\n\n"
            f"Your previous attempt was invalid. Fix exactly these problems and "
            f"return corrected JSON:\n{correction}"
        )
    return prompt


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def parse_reply(text: str) -> Dict[str, object]:
    """Extract the ``{param: value}`` dict from a model's text reply.

    Tolerates markdown code fences and leading/trailing prose by falling back to
    the first balanced ``{...}`` span. Raises ``ValueError`` if no JSON object can
    be recovered — the caller (a provider) turns that into a correction/retry.
    """
    if text is None:
        raise ValueError("empty reply")
    candidate = text.strip()

    fenced = _FENCE_RE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()

    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"no JSON object found in reply: {text[:200]!r}")
        obj = json.loads(candidate[start : end + 1])

    if not isinstance(obj, dict):
        raise ValueError(f"reply JSON is not an object: {type(obj).__name__}")
    return obj
