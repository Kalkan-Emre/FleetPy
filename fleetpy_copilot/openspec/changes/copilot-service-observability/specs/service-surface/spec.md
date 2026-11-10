# service-surface

A runnable HTTP service that wraps the existing `generate_config` inner loop. The operator builds
it, runs it, sends a request, and watches a clean step trace on the console while the same trace
is returned in the response and written to a per-request JSON file. The service is a thin adapter:
it holds no generation logic — it parses a request, builds a tracer and a provider, calls the
unchanged `generate_config`, and serializes the typed outcome. The provider is selected by the
existing `COPILOT_PROVIDER` env var, defaulting to the offline `mock`, so the service runs with no
network and no API key out of the box.

## ADDED Requirements

### Requirement: Runnable service entry point

The package SHALL expose a runnable service via `python -m fleetpy_copilot` (and an explicit
`python -m fleetpy_copilot.service`). Starting it SHALL print a one-line readiness message naming
the bound address and the selected provider. The existing entry points (`-m
fleetpy_copilot.eval.run`, `hai_smoke`) SHALL remain unchanged.

#### Scenario: Service starts with the default offline provider
- **WHEN** the operator runs `python -m fleetpy_copilot` with no `COPILOT_PROVIDER` set
- **THEN** the service SHALL start using `MockProvider`, make no network calls, and report that it is listening and which provider is active

#### Scenario: Provider is selected by env var
- **WHEN** the operator runs the service with `COPILOT_PROVIDER=hai`
- **THEN** the service SHALL build the provider via the existing `make_provider()` factory and route requests through it, with no change to the request/response shape

### Requirement: POST /generate runs the inner loop and returns outcome + trace

The service SHALL expose `POST /generate` accepting a JSON body with a required `prompt` string
and optional `constant` (object), `max_repairs` (int), and `do_dry_run` (bool), with defaults that
mirror `generate_config`. The response SHALL contain the serialized terminal outcome, the ordered
event trace for that request, the `prompt_version`, and a request id. The service SHALL expose
`GET /health` returning a simple ok status.

#### Scenario: Successful generation
- **WHEN** a `POST /generate` request yields a `GeneratedConfig`
- **THEN** the response `outcome.type` SHALL be `"GeneratedConfig"`, `outcome.config` SHALL be present, `outcome.attempts` SHALL be the real attempt count, and `trace` SHALL be a non-empty ordered array of events for that request

#### Scenario: Under-specified request surfaces slots
- **WHEN** a request is under-specified and the loop returns `NeedsInput`
- **THEN** the response `outcome.type` SHALL be `"NeedsInput"` and SHALL carry the `slots` (with their valid values) and any `other_errors`, so a conversational client can ask the user — consistent with "ask, don't infer"

#### Scenario: Defaults mirror the core
- **WHEN** a request omits `constant`, `max_repairs`, or `do_dry_run`
- **THEN** the service SHALL apply the same defaults as `generate_config` (empty constant, the core's default repair cap, dry-run enabled)

#### Scenario: Health check
- **WHEN** `GET /health` is called
- **THEN** the service SHALL respond with an ok status without running the loop

### Requirement: The service is a thin adapter over the unchanged core

The service SHALL NOT contain generation, validation, repair, or dry-run logic. It SHALL delegate
entirely to `generate_config`, which remains the single source of that behavior. A pure
in-process handler (request dict → response dict) SHALL exist so the adapter is testable without
opening a socket.

#### Scenario: Core is the only generation path
- **WHEN** the service handles a request
- **THEN** it SHALL call `generate_config(prompt, provider, tracer=..., constant=..., max_repairs=..., do_dry_run=...)` and SHALL NOT re-implement any pipeline step

#### Scenario: Handler is socket-free testable
- **WHEN** a test drives the in-process handler with a request dict and a `MockProvider`
- **THEN** it SHALL receive a response dict with `outcome` and `trace` without binding a network port

### Requirement: Typed outcomes serialize losslessly to JSON

The service SHALL serialize each terminal outcome (`GeneratedConfig`, `NeedsInput`,
`GenerationFailed`, `DryRunFailed`) to JSON including a `type` discriminator equal to the class
name, the nested `validation` (with its `ok` and `summary`), and the nested `dry_run` when
present. Serialization SHALL round-trip through `json.dumps` for every outcome type.

#### Scenario: Discriminator identifies the outcome
- **WHEN** any terminal outcome is serialized
- **THEN** the result SHALL include `type` set to the outcome's class name, so the client can branch without guessing

#### Scenario: Nested validation and dry-run are included
- **WHEN** an outcome carrying a `ValidationResult` (and possibly a `DryRunResult`) is serialized
- **THEN** the JSON SHALL include the validation's `ok` and human `summary`, and the dry-run's `ok`/`error` when a dry-run was performed

#### Scenario: Every outcome is JSON-safe
- **WHEN** each of the four outcome types is serialized
- **THEN** `json.dumps` SHALL succeed for all of them (using a `default=str` fallback for non-standard config values), with no outcome type raising

### Requirement: Per-request console trace and JSON file

For each request the service SHALL stream the human-readable indented trace to the server console
(so the operator watches steps live) AND persist the request's full event array to a
self-contained JSON file named by request id. The persisted events SHALL match the events returned
in the response.

#### Scenario: Live console trace
- **WHEN** a request is processed
- **THEN** the service console SHALL show the indented step trace for that request (attempt, llm_call, validate, repair/needs_input, dry_run, outcome) as it happens

#### Scenario: JSON file matches the response trace
- **WHEN** a request completes
- **THEN** a JSON file for that request id SHALL contain the same ordered events returned in the response body's `trace`

### Requirement: The service introduces no core dependency and preserves invariants

The HTTP framework dependency SHALL be confined to the service module: importing the copilot core
(`generate`, `trace`, `provider(s)`, `validate`, `dryrun`) SHALL NOT require the framework. The
service SHALL preserve all copilot invariants — FleetPy `src/` untouched, closed-vocabulary
validation as the authority, stateless provider, dry-run gold gate.

#### Scenario: Core imports without the web framework
- **WHEN** the core modules are imported in an environment where the web framework is not installed
- **THEN** the import SHALL succeed; only importing/running the service module SHALL require the framework

#### Scenario: Service does not relax the oracle
- **WHEN** a request produces a config that fails validation or dry-run
- **THEN** the service SHALL report that failure truthfully in the outcome and SHALL NOT alter the config or the validator to make it pass
