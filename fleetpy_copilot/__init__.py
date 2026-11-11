"""fleetpy_copilot — a deterministic layer on top of FleetPy.

M1 scope: reuse FleetPy's own parameter schema and module vocabulary to validate
configurations and emit the two CSV files FleetPy consumes, verified by loading
them in the simulator. No LLM — that is M2.

Imports FleetPy read-only; never modifies anything under ``src/``.
"""
import sys

__version__ = "0.1.0"

# Re-export sub-package modules under their original flat names so that both
# ``from fleetpy_copilot import X`` and ``from fleetpy_copilot.X import Y``
# paths continue to work unchanged.  Setting sys.modules aliases makes the
# dotted paths (e.g. fleetpy_copilot.generate) resolvable at import time.
from fleetpy_copilot.core import schema, validate, serialize, dryrun
from fleetpy_copilot.llm import provider, providers, _prompting
from fleetpy_copilot.pipeline import generate, trace
from fleetpy_copilot import service

sys.modules.setdefault("fleetpy_copilot.schema", schema)
sys.modules.setdefault("fleetpy_copilot.validate", validate)
sys.modules.setdefault("fleetpy_copilot.serialize", serialize)
sys.modules.setdefault("fleetpy_copilot.dryrun", dryrun)
sys.modules.setdefault("fleetpy_copilot.provider", provider)
sys.modules.setdefault("fleetpy_copilot.providers", providers)
sys.modules.setdefault("fleetpy_copilot._prompting", _prompting)
sys.modules.setdefault("fleetpy_copilot.generate", generate)
sys.modules.setdefault("fleetpy_copilot.trace", trace)
