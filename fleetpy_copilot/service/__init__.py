"""service — FastAPI HTTP adapter that wires the pipeline into a runnable service."""
from fleetpy_copilot.service.service import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    serialize_outcome,
    handle_generate,
    make_app,
    main,
)

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "serialize_outcome",
    "handle_generate",
    "make_app",
    "main",
]
