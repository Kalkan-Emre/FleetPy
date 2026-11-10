# trace-seam

A single, cross-cutting observability seam for the copilot. Loop code emits named step events
with structured payloads through a one-method `Tracer`; how those events are rendered (indented
console text, JSON file, API-response array) is decoupled from where they are emitted. A no-op
default tracer preserves existing behavior exactly, so instrumentation is additive. The seam
exists so that any loop — the inner repair loop today, the M2.3 outer conversation loop later —
emits the same shape of trace with no change at the emit sites.

## ADDED Requirements

### Requirement: Event is the single unit crossing the seam

The seam SHALL define one structured `Event` type carrying at minimum: a `step` name (string),
a `span` path (ordered tuple of span names giving the nesting), a monotonic `seq` (ordering
within a request), an optional `attempt` number, a JSON-serializable `payload` mapping, and a
short human `message`. One `Event` SHALL be renderable both as a human line and as a JSON object
without a second model — the payload is the source for both.

#### Scenario: Event carries structured, JSON-able payload
- **WHEN** a step emits an event with a payload (e.g. a validation summary, candidate keys)
- **THEN** the event SHALL expose that payload as a mapping that `json.dumps` can serialize (with a `default=str` safety net for odd config values), AND the event SHALL also expose a short human message

#### Scenario: seq orders events within a request
- **WHEN** multiple events are emitted during one request
- **THEN** each event SHALL carry a strictly increasing `seq` assigned by the tracer, so consumers can reconstruct emission order independent of transport

### Requirement: Tracer is a one-method protocol mirroring the Provider seam

The seam SHALL define a `Tracer` as a small protocol with a single `emit` method
(`emit(step, *, attempt=None, message="", **payload)`), analogous to the existing one-method
`Provider` protocol. The tracer SHALL assign `seq` and stamp the current span path; emit sites
SHALL NOT compute `seq` or name their parent span.

#### Scenario: Emit site names only its own step
- **WHEN** the inner loop emits a `validate` event
- **THEN** the call SHALL pass only the step name, attempt, message, and payload — NOT the enclosing span path — and the tracer SHALL supply the full span path from its current stack

### Requirement: Structural nesting via a span context manager

The tracer SHALL provide a `span(name)` context manager that pushes a name on entry and pops it
on exit (including on exception unwind). The span path stamped onto each event SHALL be the
current stack at emit time. This is what makes a new outer loop invisible to inner-loop emit
sites: wrapping the inner loop in an additional span adds one path element and one indent level,
with no edit to the inner emit sites.

#### Scenario: Nested spans compose the path
- **WHEN** code emits an event inside `span("request")` wrapping `span("generate")`
- **THEN** the event's span path SHALL be `("request", "generate")`

#### Scenario: Spans stay balanced on exception
- **WHEN** an exception propagates out of a `span(...)` block (e.g. a provider raises)
- **THEN** the span SHALL be popped during unwind so the tracer's stack is left balanced and subsequent events are well-formed

### Requirement: Emitting is decoupled from rendering

The seam SHALL separate event production from event rendering. Concrete tracers SHALL include at
least: a no-op `NULL_TRACER`; a `ConsoleTracer` writing one indented human line per event (indent
derived from span depth); a `CollectingTracer` retaining every `Event` in an accessible list; and
a `CompositeTracer` that fans one emit out to several tracers in a single pass. The same emitted
event stream SHALL be renderable to console, to a structured sink, and to an API-response array
without the emit sites knowing which renderer is attached.

#### Scenario: One emit, multiple renderings
- **WHEN** a `CompositeTracer([ConsoleTracer(), CollectingTracer()])` receives an emit
- **THEN** the event SHALL be written to the console AND retained in the collecting tracer's list, from the single emit call

#### Scenario: Collecting tracer is the test and API substrate
- **WHEN** a request runs with a `CollectingTracer`
- **THEN** the complete ordered list of `Event`s SHALL be available afterward for assertions (tests) and for serialization into the response body (service)

### Requirement: No-op default preserves existing behavior

`generate_config` SHALL accept the tracer as an OPTIONAL keyword argument defaulting to
`NULL_TRACER`, and SHALL NOT change its positional signature or return types. With the default
tracer, the loop SHALL behave identically to before instrumentation (no output, no new side
effects), so every existing caller and test is unaffected.

#### Scenario: Default call is unchanged
- **WHEN** `generate_config(prompt, provider, ...)` is called with no tracer
- **THEN** it SHALL use `NULL_TRACER`, emit nothing observable, and return the same outcome type it returned before this change

#### Scenario: Instrumentation does not alter outcomes
- **WHEN** the same prompt + provider is run once with `NULL_TRACER` and once with a `CollectingTracer`
- **THEN** the returned outcome (type, config, attempts) SHALL be identical; only the presence of collected events SHALL differ

### Requirement: The trace does not weaken the copilot's invariants

The seam SHALL be purely observational. It SHALL NOT modify the candidate config, relax or bypass
any of the validator's checks, alter the dry-run gold gate, or make the provider stateful. The
provider SHALL NOT import the trace module.

#### Scenario: Provider stays decoupled from the tracer
- **WHEN** full prompt text and the raw model reply are surfaced into the trace
- **THEN** that data SHALL reach the trace via data the loop already holds or an optional provider accessor — NOT by the provider importing or calling the tracer

#### Scenario: Observation never changes the oracle
- **WHEN** a generated config fails validation or dry-run while a tracer is attached
- **THEN** the recorded outcome SHALL be the same failure that occurs with `NULL_TRACER`; tracing SHALL NOT cause a config to pass that would otherwise fail
