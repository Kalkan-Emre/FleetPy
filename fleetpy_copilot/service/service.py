"""service.py — the copilot as a runnable HTTP service.

The operator builds it, runs it (``python -m fleetpy_copilot``), sends a request, and
watches a clean step trace on the console while the same trace is returned in the
response and written to a per-request JSON file. The service is a **thin adapter**: it
holds no generation logic — it parses a request, builds a tracer + provider, calls the
unchanged ``generate_config``, and serializes the typed outcome.

Dependency boundary: the FastAPI/uvicorn import is confined to this module. Importing
the copilot core (generate/trace/provider(s)/validate/dryrun) never imports FastAPI, so
the core stays env-agnostic; only running the service needs the dependency.

``handle_generate`` and ``serialize_outcome`` are PURE STDLIB (dict in, dict out) so the
adapter is fully testable without a socket and without the web framework.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
import time
import uuid
from typing import Dict, Mapping, Optional

from fleetpy_copilot.llm import _prompting
from fleetpy_copilot.pipeline.generate import (
    DryRunFailed,
    GeneratedConfig,
    GenerationFailed,
    NeedsInput,
    generate_config,
)
from fleetpy_copilot.llm.provider import Provider
from fleetpy_copilot.llm.providers import make_provider
from fleetpy_copilot.pipeline.trace import CollectingTracer, CompositeTracer, ConsoleTracer, JsonFileTracer

DEFAULT_HOST = os.environ.get("COPILOT_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("COPILOT_PORT", "8750"))


# The request model is defined at module level (not inside make_app) so FastAPI
# resolves it as a body model reliably. Guarded so that importing this module's pure
# helpers (handle_generate / serialize_outcome) does not hard-require pydantic.
try:
    from pydantic import BaseModel, Field
    from typing import Any as _Any

    class GenerateRequest(BaseModel):
        prompt: str = Field(..., min_length=1)
        constant: Optional[Dict[str, _Any]] = None
        max_repairs: int = 1
        do_dry_run: bool = True
except ImportError:  # pragma: no cover - pydantic ships with fastapi
    GenerateRequest = None  # type: ignore[assignment]


# --- serialization (pure stdlib) ----------------------------------------------

def serialize_outcome(outcome) -> Dict[str, object]:
    """Serialize a terminal outcome to a JSON-able dict.

    The four outcomes are dataclasses, so ``dataclasses.asdict`` recurses into the
    nested ``ValidationResult`` / ``DryRunResult`` / ``Slot`` automatically. We then
    inject a ``type`` discriminator (the class name) and the live ``validation.ok`` /
    ``validation.summary()`` (a property + method, which ``asdict`` omits).
    """
    d = dataclasses.asdict(outcome)
    d["type"] = type(outcome).__name__
    d["attempts"] = getattr(outcome, "attempts", None)
    validation = getattr(outcome, "validation", None)
    if validation is not None and isinstance(d.get("validation"), dict):
        d["validation"]["ok"] = validation.ok
        d["validation"]["summary"] = validation.summary()
    # json round-trip with a safety net for any non-standard config value
    return json.loads(json.dumps(d, default=str))


def _trace_to_json(tracer: CollectingTracer):
    return [e.to_json() for e in tracer.events]


# --- the thin adapter (pure stdlib, socket-free, framework-free) --------------

def handle_generate(
    request: Mapping[str, object],
    provider: Provider,
    *,
    trace_dir: Optional[str] = None,
) -> Dict[str, object]:
    """Run one generation request. ``request`` is a plain dict; returns a plain dict.

    This is the testable core of the service — no socket, no FastAPI. The FastAPI route
    is a shell that validates the body and calls this.
    """
    prompt = request.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("'prompt' is required and must be a non-empty string")
    constant = request.get("constant") or None
    max_repairs = int(request.get("max_repairs", 1))
    do_dry_run = bool(request.get("do_dry_run", True))

    request_id = uuid.uuid4().hex[:8]
    collector = CollectingTracer()
    tracers = [ConsoleTracer(stream=sys.stderr), collector]
    if trace_dir is not None:
        tracers.append(JsonFileTracer(trace_dir, request_id=request_id))
    tracer = CompositeTracer(tracers)

    print(f"[req {request_id}] generate  prompt={prompt!r}", file=sys.stderr)
    started = time.monotonic()
    with tracer.span("request"):
        outcome = generate_config(
            prompt,
            provider,
            constant=constant,
            max_repairs=max_repairs,
            do_dry_run=do_dry_run,
            tracer=tracer,
        )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    _print_summary(request_id, outcome, provider, elapsed_ms)

    return {
        "request_id": request_id,
        "outcome": serialize_outcome(outcome),
        "trace": _trace_to_json(collector),
        "prompt_version": _prompting.PROMPT_VERSION,
    }


def _print_summary(request_id: str, outcome, provider, elapsed_ms: int) -> None:
    """One compact per-request footer to the console: outcome, attempts, latency,
    provider/model, and (for NeedsInput) the slots still needed."""
    kind = type(outcome).__name__
    attempts = getattr(outcome, "attempts", "?")
    desc = getattr(provider, "describe", lambda: {})()
    prov = f"{desc.get('provider', type(provider).__name__)}/{desc.get('model', '?')}"
    print(f"[req {request_id}] done  outcome={kind}  attempts={attempts}  "
          f"{elapsed_ms}ms  provider={prov}", file=sys.stderr)
    if kind == "NeedsInput":
        names = [s.name for s in getattr(outcome, "slots", [])]
        print(f"[req {request_id}]   need: {', '.join(names)}", file=sys.stderr)
    elif kind == "GenerationFailed":
        val = getattr(outcome, "validation", None)
        if val is not None:
            print(f"[req {request_id}]   last error: {val.summary()}", file=sys.stderr)
    elif kind == "DryRunFailed":
        dr = getattr(outcome, "dry_run", None)
        if dr is not None:
            print(f"[req {request_id}]   dry-run error: {dr.error}", file=sys.stderr)
    sys.stderr.flush()


# --- the FastAPI shell (dependency confined here) -----------------------------

def make_app(provider: Optional[Provider] = None, *, trace_dir: Optional[str] = None):
    """Build the FastAPI app. Imports FastAPI lazily so the core stays importable
    without it. ``provider`` defaults to the ``$COPILOT_PROVIDER`` selection."""
    from fastapi import Body, FastAPI, HTTPException

    prov = provider if provider is not None else make_provider()
    tdir = trace_dir if trace_dir is not None else os.environ.get("COPILOT_TRACE_DIR", "./logs")

    app = FastAPI(title="FleetPy Config Copilot", version="0.1.0")

    @app.get("/health")
    def health() -> Dict[str, object]:
        return {"ok": True, "provider": type(prov).__name__}

    @app.post("/generate")
    def generate(req: GenerateRequest = Body(...)) -> Dict[str, object]:
        try:
            return handle_generate(req.model_dump(), prov, trace_dir=tdir)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    return app


def main() -> None:
    """Entry point: ``python -m fleetpy_copilot`` / ``-m fleetpy_copilot.service``."""
    import uvicorn

    provider = make_provider()
    print(
        f"[copilot] listening on {DEFAULT_HOST}:{DEFAULT_PORT} "
        f"(provider={type(provider).__name__})",
        file=sys.stderr,
    )
    uvicorn.run(make_app(provider), host=DEFAULT_HOST, port=DEFAULT_PORT, log_level="warning")


if __name__ == "__main__":  # pragma: no cover
    main()
