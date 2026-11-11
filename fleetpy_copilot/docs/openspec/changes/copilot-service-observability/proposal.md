## Why

The copilot's inner pipeline (NL → provider → validate → repair → dry-run) is built and
unit-tested, but it is **silent**: there is no logging anywhere (zero `import logging`, no
prints in the core), so when a request runs you cannot see which steps executed, what prompt
was sent, what the model returned, what validation found, or why it retried. The copilot also
has **no service surface** — it is a library plus two `python -m` CLIs. The user wants to run
the copilot as a service: build it, run it, send a request, and watch a clean, concise trace
of every important step and intermediate result. Crucially, the way the service is used must
**not change** as the system grows — when the outer conversation loop (M2.3) is added later,
the build/run/request shape and the log style must stay identical; only the trace gains depth.

## Intent Source

Plain-text input (this session). The driving constraint — "when I implement the outer loop I
shouldn't be able to understand the difference as a user" — maps directly onto the already
-designed `NeedsInput`/`Slot` "ask, don't infer" hook for the M2.3 conversation controller.

## Milestone

Primarily **M2.3 enablement** and **M3.5 hardening** (data-collection logging). The outer
conversation loop (M2.3) is not built, but this change makes observability and the service
surface *forward-compatible* with it so the M2.3 controller plugs in without an interface change
— exactly the user's requirement that "when I implement the outer loop I shouldn't be able to
understand the difference as a user." Immediately, it delivers observability + a service entry
point for the existing M2.0/M2.1 inner loop. No milestone's behavior contract changes.

**Relationship to planned day-one data collection (doc 05 "Data collection"; doc 01 "Fine-tuning
posture"):** that is an append-only JSONL of `(NL request → validated, dry-run-passing config)`
*pairs* — the eval/fine-tune corpus, distinct from conversation state. The observability trace
here is a *different artifact*: a per-request **step trace** (what ran, prompts, validation,
retries), not an input→output training pair. This change does NOT implement the data-collection
JSONL; it is kept deliberately separate so the two do not collide. (A later change can derive the
pair-log from the same event stream if desired.)

## What Changes

**New — observability event seam (`trace.py`).** A single cross-cutting tracing abstraction:
an `Event` dataclass, a one-method `Tracer` protocol (mirroring the existing `Provider` seam),
a `span(name)` context manager for structural nesting, and concrete tracers (`NULL_TRACER`
no-op default, `ConsoleTracer`, `JsonFileTracer`, `CollectingTracer`, `CompositeTracer`). Loop
code emits named step events; rendering is decoupled from emitting.

**Modified — `generate_config` gains observability (NON-breaking).** Adds an optional
`tracer: Tracer = NULL_TRACER` keyword argument and emits step events (`attempt`, `llm_call`,
`merge`, `validate`, `repair`, `needs_input`, `dry_run`, `outcome`) at its existing branch
points, wrapped in `span("generate")`. The positional signature, return types, and default
behavior are unchanged — every current caller/test is byte-for-byte unaffected (default no-op).

**Modified — `Provider` protocol gains an OPTIONAL verbose method (NON-breaking).** Adds a
`GenerationCall` dataclass (`config`, `system_prompt`, `user_prompt`, `raw_reply`) and an
optional `generate_verbose(...)` method so the loop can surface the full rendered prompt and
raw reply into the trace WITHOUT the provider importing `trace.py`. The existing `generate()`
method and the `{param:value}` return contract are unchanged; providers without the verbose
method still work (empty prompt fields). The Provider stays **stateless**.

**New — service surface (`service.py` + `__main__.py`).** A runnable service:
`python -m fleetpy_copilot` starts a server exposing `POST /generate` and `GET /health`. It is
a thin adapter over `generate_config` — parse request, build tracer + provider, call the core,
serialize the outcome. Per request the live indented trace streams to the service console, a
self-contained JSON trace is written to `logs/req-<id>.json`, and the same events are returned
in the response body. `make_provider()` selects the backend from `$COPILOT_PROVIDER` (default
`mock`, so it runs offline out of the box).

**BREAKING (environment policy, not code):** the service tier introduces **FastAPI + uvicorn**,
the copilot's first third-party runtime dependencies. This is a deliberate, user-approved
deviation from the stdlib-only rule. It is contained: the **core stays stdlib-only and
importable without FastAPI** (only `service.py` imports it, lazily, when serving). See the open
question in Scope & Impact on how/where the dependency is declared.

## Capabilities

### New Capabilities
- `trace-seam` — the event/tracing abstraction (`Event`, `Tracer`, `span`, the concrete
  tracers) and its contract: emitting is decoupled from rendering; a no-op default preserves
  existing behavior; the same event stream renders to console, JSON file, and API response.
- `service-surface` — the runnable service: entry point, `POST /generate` / `GET /health`,
  request/response JSON shapes, outcome serialization, per-request console + JSON-file trace.
- `trace-stability` — the forward-compatibility contract: structural spans mean the inner-loop
  emit sites are unchanged when the M2.3 outer loop wraps them in `span("turn")`; the event
  taxonomy spans both loops (inner: `attempt`/`llm_call`/`validate`/`repair`/`dry_run`/`outcome`;
  outer, future: `turn`, slot-ask, merge-into-`confirmed`, change-awareness flag); the HTTP
  request/response already carry `constant` (= the `confirmed` dict carried across turns) and
  `slots`, so the M2.3 conversational client reuses the same surface with no interface change.

### Modified Capabilities
<!-- None: openspec/specs/ is empty (no synced baseline specs). generate.py and the Provider
     protocol are extended additively; no existing requirement contract changes. -->

## Scope & Impact

**Modules touched (all under `fleetpy_copilot/`):**
- `trace.py` — NEW (event seam).
- `generate.py` — add optional `tracer` kwarg + `span("generate")` + emit sites (additive).
- `provider.py` — add `GenerationCall` + optional `generate_verbose`; implement on
  `MockProvider` (additive; `generate()` unchanged).
- `providers.py` — implement `generate_verbose` on `OpenAICompatProvider` + `AnthropicProvider`
  (additive; return rendered prompts + raw reply, reusing `_prompting.build_*`).
- `service.py`, `__main__.py` — NEW (FastAPI adapter + run shim).
- `tests/test_trace.py`, `tests/test_service.py` — NEW.
- `docs/service.md` (or an in-package doc) — NEW (build/run, request/response, env vars, trace).
- requirements manifest(s) — add `fastapi`, `uvicorn` (see open question).

**Invariants preserved:**
- **FleetPy `src/` stays untouched** — read-only import only; the dry-run gate
  (`load_simulation_environment`, never `.run()`) is unchanged.
- **Closed-vocabulary validation remains the authority** — the trace observes the pipeline, it
  does not relax any check.
- **Provider stays stateless** and returns a plain `{param:value}` dict; `generate_verbose` is
  an optional, additive accessor over data the provider already computes.
- **Core stays env-agnostic** — `generate_config`/`trace`/`provider(s)`/`validate`/`dryrun`
  import no third-party package and remain importable/testable under bare conda/pip.
- **Local-only workflow** — never push; commit only tested checkpoints on `copilot`.

**Dependency declaration (decided with user):** the copilot's dependencies are consolidated into
a **single** `fleetpy_copilot/requirements.txt` (pytest, hypothesis, fastapi, uvicorn) as the
copilot's one source of truth, superseding the `requirements-test.txt` split. The root
`requirements.txt` and `environment.yml` are **not** touched — the service tier is copilot-local
and the core stays stdlib-only, so the three-manifest policy does not apply to this
copilot-scoped, service-only dependency.
