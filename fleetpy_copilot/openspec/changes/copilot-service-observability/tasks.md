<!-- Local-only (WORKFLOW.md): NO manifest.yaml, NO per-component branches, NO PRs/push.
     A group is "done" when code + tests are written AND the suite passes:
       .venv/bin/python -m pytest fleetpy_copilot/tests -q   (the commit gate).
     Dependency decision (overrides the generic 3-manifest rule): the copilot's deps are
     consolidated into a SINGLE fleetpy_copilot/requirements.txt; root requirements.txt and
     environment.yml are NOT touched (service tier is copilot-local; core stays stdlib-only).
     Groups map to the 4 approved rollout steps; each group is one tested commit. -->

## 1. trace — the event seam (rollout step 1)

- [x] 1.1 Add `fleetpy_copilot/trace.py`: `Event` frozen dataclass (`step`, `span` tuple, `seq`, `attempt`, `payload`, `message`) (ref: Requirement "Event is the single unit crossing the seam")
- [x] 1.2 Add the `Tracer` protocol (`@runtime_checkable`, one `emit` method) mirroring the `Provider` seam (ref: Requirement "Tracer is a one-method protocol mirroring the Provider seam")
- [x] 1.3 Add a base tracer with the `span(name)` context manager (push on enter, pop on exit incl. exception unwind) and `seq` assignment (ref: Requirement "Structural nesting via a span context manager")
- [x] 1.4 Add concrete tracers: `NULL_TRACER` (no-op singleton), `ConsoleTracer` (indent = span depth, to stderr), `CollectingTracer` (`self.events`), `CompositeTracer` (fan-out) (ref: Requirement "Emitting is decoupled from rendering")

## 2. generate — thread the seam through the inner loop (rollout step 1, depends on §1)

- [x] 2.1 Add `tracer: Tracer = NULL_TRACER` kwarg to `generate_config`; wrap the loop body in `with tracer.span("generate")` — no positional/return change (ref: Requirement "No-op default preserves existing behavior")
- [x] 2.2 Emit at existing branch points: `attempt` (top of loop), `llm_call` (after provider), `merge`, `validate`, `repair`|`needs_input`, `dry_run`, and an `outcome` event before EVERY return (ref: Requirement "Every return path emits a terminal outcome event")
- [x] 2.3 Keep emit sites naming only their own step (tracer supplies span path) (ref: Requirement "Emit site names only its own step")

## 3. tests — prove step 1

- [x] 3.1 Add `tests/test_trace.py`: with `CollectingTracer`, assert step sequence + key payload fields for every outcome path (good / needs-input / repair-converges / repair-exhausted / dry-run-failed), reusing `test_generate.py` fixtures (ref: Requirement "Branch taken matches the event emitted")
- [x] 3.2 Assert outcomes are identical with `NULL_TRACER` vs `CollectingTracer` (ref: Requirement "Instrumentation does not alter outcomes")
- [x] 3.3 Assert spans stay balanced and events well-formed when a provider raises (ref: Requirement "Spans stay balanced on exception")
- [x] 3.4 Assert no `print(` used for narration in `generate.py` (ref: Requirement "Trace is the only narration")
- [x] 3.5 Verify suite green: `.venv/bin/python -m pytest fleetpy_copilot/tests -q` → **commit step 1**

## 4. service — FastAPI entry point (rollout step 2, depends on §1–§2)

- [x] 4.1 Consolidate deps into `fleetpy_copilot/requirements.txt` (pytest, hypothesis, fastapi, uvicorn); remove `requirements-test.txt`. Do NOT touch root `requirements.txt`/`environment.yml` (ref: proposal "Dependency declaration")
- [x] 4.2 Add `service.py`: `handle_generate(request_dict, provider) -> response_dict` (socket-free core), building a tracer and calling `generate_config` only — no pipeline logic (ref: Requirement "The service is a thin adapter over the unchanged core")
- [x] 4.3 Add `serialize_outcome(outcome)`: `dataclasses.asdict` + `type` discriminator + injected `validation.ok`/`summary()` + `json.dumps(default=str)` safety net (ref: Requirement "Typed outcomes serialize losslessly to JSON")
- [x] 4.4 Add the FastAPI app: `POST /generate` (Pydantic request: `prompt` required; `constant`/`max_repairs`/`do_dry_run` optional, defaults mirror core) + `GET /health`; `make_app`, `main` (uvicorn), one-line readiness log (ref: Requirement "POST /generate runs the inner loop and returns outcome + trace", "Runnable service entry point")
- [x] 4.5 Add `__main__.py` shim → `service.main()`; confirm `-m fleetpy_copilot.eval.run` / `hai_smoke` still work (ref: Requirement "Runnable service entry point")
- [x] 4.6 Keep the FastAPI import confined to `service.py` (lazy if needed) so the core imports without it (ref: Requirement "The service introduces no core dependency and preserves invariants")

## 5. tests — prove step 2

- [x] 5.1 Add `tests/test_service.py`: drive `handle_generate` in-process with `MockProvider` — assert `outcome.type`, `attempts`, non-empty `trace` (ref: Requirement "Handler is socket-free testable")
- [x] 5.2 Assert `serialize_outcome` round-trips every outcome type (`GeneratedConfig`/`NeedsInput`/`GenerationFailed`/`DryRunFailed`) through `json.dumps` (ref: Requirement "Every outcome is JSON-safe")
- [x] 5.3 Assert the core imports without the web framework on the import path (core modules do not import `service`) (ref: Requirement "Core imports without the web framework")
- [x] 5.4 Verify suite green under the `.venv` → **commit step 2**

## 6. providers — full prompt + raw reply into the trace (rollout step 3, depends on §1–§2)

- [x] 6.1 Add `GenerationCall` dataclass (`config`, `system_prompt`, `user_prompt`, `raw_reply`) and OPTIONAL `generate_verbose` to the `Provider` protocol; implement on `MockProvider` (fill `raw_reply` from its dict) (ref: Requirement "Provider stays decoupled from the tracer")
- [x] 6.2 Implement `generate_verbose` on `OpenAICompatProvider` and `AnthropicProvider`, reusing `_prompting.build_system_prompt`/`build_user_prompt` and the raw reply text (pure addition; `generate()` unchanged) (ref: Requirement "Provider stays decoupled from the tracer")
- [x] 6.3 In `generate_config`, prefer `generate_verbose` when present (else wrap `generate()` with empty prompt fields); enrich the `llm_call` event with full system/user prompt + raw reply (ref: Requirement "The trace does not weaken the copilot's invariants")

## 7. tests — prove step 3

- [x] 7.1 Extend `test_trace.py`: `llm_call` carries full `system_prompt`/`user_prompt`/`raw_reply` with a verbose mock; graceful fallback (empty fields, no crash) with a plain provider (ref: Requirement "Emitting is decoupled from rendering")
- [x] 7.2 Confirm `test_providers.py` unchanged and green (method only added) → **commit step 3**

## 8. json sink + docs (rollout step 4, depends on §1, §4)

- [x] 8.1 Add `JsonFileTracer` writing `logs/req-<id>.json` (dir via `COPILOT_TRACE_DIR`, default `./logs`); wire into the service's `CompositeTracer` alongside console + collecting (ref: Requirement "Per-request console trace and JSON file")
- [x] 8.2 Test (to `tmp_path`): the JSON file is a valid array of the same events returned in the response `trace` (ref: Requirement "JSON file matches the response trace")
- [x] 8.3 Add `logs/` to the copilot `.gitignore` if present
- [x] 8.4 Add `docs/service.md`: build (`pip install -r fleetpy_copilot/requirements.txt`), run (`python -m fleetpy_copilot`), request/response shapes, env vars (`COPILOT_PROVIDER`, `COPILOT_TRACE_DIR`), a sample console trace
- [x] 8.5 Verify suite green under the `.venv` → **commit step 4**

## 9. end-to-end verification

- [x] 9.1 Offline smoke: start `python -m fleetpy_copilot` (mock), `POST /generate` a prompt, confirm response has `outcome.type` + populated `trace`, console shows the indented live trace, and `logs/req-<id>.json` matches
- [x] 9.2 Opt-in live check: `COPILOT_PROVIDER=hai python -m fleetpy_copilot`, send a prompt, confirm `llm_call` shows full prompts + raw reply and any repair shows `validate → repair → attempt`
- [x] 9.3 Confirm env-agnostic: in an env without fastapi, `python -c "import fleetpy_copilot.generate"` succeeds; only importing `service` needs fastapi
