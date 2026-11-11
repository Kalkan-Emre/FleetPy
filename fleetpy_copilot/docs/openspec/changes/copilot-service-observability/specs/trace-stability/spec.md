# trace-stability

The forward-compatibility contract: the user's experience of the service MUST NOT change when the
copilot grows. Today there is one loop (the inner repair loop = one `generate_config` call).
Later the M2.3 outer conversation loop will drive successive `generate_config` calls across turns,
carrying the `confirmed` dict forward via `constant=`. When that lands, the build command, the run
command, the request shape, and the trace STYLE must stay identical — the trace simply gains an
outer `turn` span and a few outer-loop step names. This capability specifies that guarantee so it
is enforced structurally, not left as a hope.

## ADDED Requirements

### Requirement: Inner-loop emit sites are unchanged when an outer loop is added

Adding an outer loop SHALL require NO edit to the inner loop's emit sites. Because span nesting is
structural (the tracer stamps the current span stack, not a hard-coded path), the M2.3 outer loop
SHALL add observability solely by wrapping each turn in an additional `span("turn")` around its
`generate_config` call.

#### Scenario: Outer span added without touching inner emits
- **WHEN** an outer loop wraps a `generate_config` call in `span("turn")` (itself inside `span("request")`)
- **THEN** the inner loop's events SHALL carry the span path `("request", "turn", "generate")` with no change to the inner emit call sites, and the only visible difference SHALL be one added indent level in the console trace

#### Scenario: Single-loop path is a prefix of the multi-loop path
- **WHEN** the same inner loop runs today under `("request", "generate")` and later under `("request", "turn", "generate")`
- **THEN** the inner event `step` names and payload shapes SHALL be identical across both; only the span prefix SHALL differ

### Requirement: One event taxonomy spans both loops

The event vocabulary SHALL be defined once and shared. Inner-loop steps SHALL be: `attempt`,
`llm_call`, `merge`, `validate`, `repair`, `needs_input`, `dry_run`, `outcome`. Outer-loop steps
(added by M2.3, not built in this change) SHALL extend — never redefine — this vocabulary with
turn-level steps such as a turn boundary, a slot question, a merge of the user's reply into the
`confirmed` dict, and a change-awareness flag. The outer loop SHALL NOT rename or repurpose any
inner step.

#### Scenario: Outer loop extends, does not redefine
- **WHEN** the M2.3 outer loop is later implemented
- **THEN** it SHALL emit new turn-level step names through the same seam and SHALL leave the meaning of every inner step (`attempt`/`llm_call`/`validate`/`repair`/`needs_input`/`dry_run`/`outcome`) unchanged

#### Scenario: Every return path emits a terminal outcome event
- **WHEN** the inner loop returns any terminal outcome (`GeneratedConfig`, `NeedsInput`, `GenerationFailed`, `DryRunFailed`)
- **THEN** exactly one `outcome` event carrying the outcome `type` and `attempts` SHALL be emitted before the return, so the trace never diverges silently from the control flow

### Requirement: The request/response surface already carries the conversation state

The HTTP surface SHALL be forward-compatible with the M2.3 conversation loop without a new
endpoint or a changed request shape. The request's `constant` field SHALL be the `confirmed` dict
that the outer loop carries across turns; the response's `slots` (on `NeedsInput`) SHALL be what a
conversational client asks the user about. A multi-turn client SHALL therefore reuse the same
`POST /generate` surface by passing the accumulated `confirmed` dict as `constant` on each turn.

#### Scenario: Confirmed state round-trips via constant
- **WHEN** a first turn returns `NeedsInput` with slots, and a client re-submits with those answers merged into `constant`
- **THEN** the service SHALL accept the same request shape, pass `constant` straight to `generate_config`, and (the candidate overriding the constant) carry the prior answers forward — no new field or endpoint required

#### Scenario: No interface change across the inner→outer transition
- **WHEN** the M2.3 outer loop is added on top of this service
- **THEN** the build command, the run command (`python -m fleetpy_copilot`), the `POST /generate` request body, and the response schema SHALL be unchanged; only the trace depth SHALL grow

### Requirement: The trace stays faithful to the real control flow

The trace SHALL reflect what the loop actually did, not a parallel narration that can drift. Step
events SHALL be emitted at the loop's real decision points (the branch the loop actually took),
and narration SHALL go only through the seam — no stray `print` in the core generation or service
request paths.

#### Scenario: Branch taken matches the event emitted
- **WHEN** validation finds missing-mandatory and the loop returns `NeedsInput` (no repair)
- **THEN** the trace SHALL show the `needs_input` branch and SHALL NOT show a `repair`/subsequent `attempt`; conversely a present-but-invalid value SHALL show `repair` then a further `attempt`

#### Scenario: Trace is the only narration
- **WHEN** the core generation path or the service request path runs
- **THEN** all step narration SHALL be emitted via the tracer, and there SHALL be no `print(` used for step narration in those paths
