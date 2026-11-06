"""fleetpy_copilot — a deterministic layer on top of FleetPy.

M1 scope: reuse FleetPy's own parameter schema and module vocabulary to validate
configurations and emit the two CSV files FleetPy consumes, verified by loading
them in the simulator. No LLM — that is M2.

Imports FleetPy read-only; never modifies anything under ``src/``.
"""

__version__ = "0.1.0"
