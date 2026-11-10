## Context

The copilot's inner loop (`generate_config`: provider → merge → validate → repair → dry-run) is
built, tested (313 passing, 2 skipped), and silent — no `logging`, no prints in the core. It is a
library plus two `python -m` CLIs; there is no service. This change adds (1) a cross-cutting
observability event seam and (2) a runnable HTTP service over the unchanged core, so the operator
can build/run the service, send a request, and watch a clean step trace — with the guarantee that
the M2.3 outer conversation loop can later plug in without changing that experience.

**Constraints:** FleetPy `src/` stays read-only (dry-run uses `load_simulation_environment`, never
`.run()`). The core stays env-agnostic (stdlib + pytest, importable under both conda and pip). The
service tier introduces FastAPI + uvicorn — the copilot's first third-party runtime deps — confined
to `service.py` and declared in a single consolidated `fleetpy_copilot/requirements.txt`
(superseding `requirements-test.txt`); root `requirements.txt` / `environment.yml` untouched.
Local-only workflow: never push; commit only tested checkpoints on `copilot`.

## Module impact

- **`trace.py` (NEW)** — the event seam: `Event` (frozen dataclass), `Tracer` protocol
  (`emit(step, *, attempt, message, **payload)`), a `span(name)` context manager on a base tracer,
  and tracers `NULL_TRACER` / `ConsoleTracer` / `JsonFileTracer` / `CollectingTracer` /
  `CompositeTracer`. Pure stdlib. Imports nothing from the rest of the package.
- **`generate.py` (MODIFIED, additive)** — `generate_config` gains `tracer: Tracer = NULL_TRACER`,
  wraps its body in `span("generate")`, and emits at its existing branch points
  (`attempt`→`llm_call`→`merge`→`validate`→`repair`|`needs_input`→`dry_run`→`outcome`). Positional
  signature and return types unchanged.
- **`provider.py` (MODIFIED, additive)** — add `GenerationCall` (config + system_prompt +
  user_prompt + raw_reply) and an OPTIONAL `generate_verbose` to the protocol; implement on
  `MockProvider`. `generate()` and the `{param:value}` contract unchanged; provider stays stateless
  and never imports `trace.py`.
- **`providers.py` (MODIFIED, additive)** — implement `generate_verbose` on `OpenAICompatProvider`
  and `AnthropicProvider`, reusing `_prompting.build_system_prompt`/`build_user_prompt` and
  returning the raw reply text they already receive.
- **`service.py` + `__main__.py` (NEW)** — FastAPI app (`POST /generate`, `GET /health`), a
  socket-free `handle_generate(request, provider) -> response`, `serialize_outcome`, `make_app`,
  `main` (uvicorn). `__main__.py` is a shim to `service.main()`.
- **`requirements.txt` (NEW, consolidated)**; **`docs/service.md` (NEW)**; **`tests/test_trace.py`
  + `tests/test_service.py` (NEW)**.

This sits entirely in the copilot layer; the FleetPy seam is unchanged.

## Goals / Non-Goals

**Goals:**
- A single observability seam every loop emits into; emitting decoupled from rendering.
- A runnable service exposing the inner loop, with live console trace + JSON file + response trace.
- Instrumentation is additive and no-op by default — existing callers/tests unaffected.
- Forward compatibility: the M2.3 outer loop plugs in by adding one span, no interface change.
- Full prompt + raw reply visible in the trace, without coupling the provider to the tracer.

**Non-Goals:**
- Building the M2.3 outer conversation loop, three-tier state, or change-awareness (specified only).
- The day-one data-collection JSONL (the NL→config *pair* corpus) — a separate artifact; not here.
- Authentication, rate limiting, or production hardening of the HTTP surface.
- Any UI (doc 06). Local-model/promptfoo/CI (M3).

## Decisions

### 1. Bespoke event seam, not stdlib `logging`

A tiny typed `Event` + one-method `Tracer` yields both the clean indented console trace AND the
structured trace returned in the API response from one source. The seam mirrors the existing
`Provider` protocol style (one method, `@runtime_checkable`) so it is idiomatic here.

**Alternatives considered:**
- *stdlib `logging`:* rebuilding a per-request structured payload from `LogRecord`/`extra=` is more
  code and coupling, and its process-global state fights per-request isolation and deterministic
  test assertions. A `LoggingTracer` can be added later as a drop-in renderer if operators want it.
- *contextvars ambient tracer:* hidden state; each request thread needs its own tracer with
  set/reset in tests — no benefit for a loop this small.

### 2. Explicit optional `tracer=` kwarg (not ambient)

Threading the tracer as a defaulted keyword touches exactly one signature, keeps data flow visible,
gives each request its own tracer (no cross-request bleed), and makes tests trivial (pass a
`CollectingTracer`, assert `.events`). The outer loop later passes the *same* tracer down and nests
via `span("turn")`.

### 3. Structural spans carry nesting (the stability mechanism)

Emit sites name only their own step; the tracer stamps the current span stack. So the inner loop's
emit sites are identical whether the path is `("request","generate")` today or
`("request","turn","generate")` under M2.3. This is what makes "no interface change as it grows"
structural rather than aspirational, satisfying the `trace-stability` spec.

### 4. Provider stays pure; `generate_verbose` surfaces prompts/reply

To show the full rendered prompt and raw reply without the provider importing `trace.py`, the
provider optionally returns richer data it already computes (`GenerationCall`). `generate_config`
prefers `generate_verbose` when present, else wraps `generate()` with empty prompt fields. Keeps the
stateless-provider invariant and the one-method core contract intact.

### 5. FastAPI for the service, confined to `service.py`

User-approved. FastAPI gives request validation (a Pydantic request model) and a clean `POST`
surface. It is isolated: importing the core never imports FastAPI, so the env-agnostic core is
preserved and only running the service needs the dep. Default provider is `mock` so the service runs
offline out of the box.

### 6. Outcome serialization via `dataclasses.asdict` + discriminator

The four outcomes are dataclasses, so `asdict` recurses into nested `ValidationResult` / `DryRunResult`
/ `Slot` automatically. We then inject `type` = class name and the live `validation.ok` /
`validation.summary()` (a property/method `asdict` omits), and `json.dumps(..., default=str)` as a
safety net for odd config values.

### 7. Per-request JSON file, one file per request

Each request's full event array is written to `logs/req-<id>.json` (self-contained; dir via
`COPILOT_TRACE_DIR`, default `./logs`). Chosen over a shared append-only `.jsonl` so each request's
trace is isolated and easy to inspect. This is distinct from the planned data-collection pair-log.

## Risks / Trade-offs

- [Risk: trace drifts from real control flow over time] → Emit at the loop's real branch points;
  require an `outcome` event on *every* return path; a test asserts each outcome type emits a
  terminal `outcome`, and a test asserts no `print(` narration in `generate.py`/`service.py`.
- [Risk: spans desync on exception] → `span()` is a context manager (pop on unwind); a test runs a
  raising provider and asserts the exception still propagates and the event stream is well-formed.
- [Risk: FastAPI dep breaks the env-agnostic core] → Lazy import confined to `service.py`; a test/
  check imports the core in an env without FastAPI; core tests never import the service.
- [Risk: over-asserting full payloads makes tests brittle] → Tests assert presence of steps + key
  fields, not full payload equality.
- [Risk: always-full prompt dumps are noisy] → Accepted per user decision (always full); the JSON
  file absorbs volume; console remains the live view.
- [Trade-off: two JSON artifacts later (trace file vs. data-collection pair-log)] → Kept separate by
  design; a future change can derive the pair-log from the same event stream.

## Test & verification plan

- **Unit (offline, MockProvider):** `test_trace.py` asserts the step sequence + key payload fields
  for every outcome path (good / needs-input / repair-converges / repair-exhausted / dry-run-failed),
  reusing `test_generate.py` fixtures; asserts `NULL_TRACER` leaves outcomes identical; asserts spans
  balanced on a raising provider; asserts `llm_call` carries full prompts with a verbose mock and
  degrades gracefully without one.
- **Service (socket-free):** `test_service.py` drives `handle_generate(request, MockProvider)` —
  asserts `outcome.type`, `attempts`, non-empty `trace`, and `serialize_outcome` round-trips every
  outcome through `json.dumps`; asserts `JsonFileTracer` writes a valid JSON array matching the
  response trace (to `tmp_path`).
- **Invariant checks:** a test imports the core without FastAPI installed-path (or asserts the core
  modules do not import `service`); existing `test_providers.py` stays green (method only added).
- **Both environments:** the full suite must collect and pass under both conda and pip
  (`python -m pytest fleetpy_copilot/tests -q`), per WORKFLOW; each rollout step commits only when green.

## Open Questions

- Default bind host/port for the service (proposed `127.0.0.1:8750`) — confirm at implementation.
- Whether to add a `COPILOT_TRACE=compact|verbose` toggle later (default is always-full per user);
  not required for this change.
