# inner-loop-audit

Phase-0 verification (HARD GATE) that the as-built M2.0 implementation matches the documented design and that the test suite exercises every node, edge, and outcome of the doc-05 mermaid inner loop. No production-code behavior changes other than repairing test gaps and the hai-reachability probe.

## ADDED Requirements

### Requirement: Inner-loop test coverage is complete

The test suite SHALL exercise every node, branch, and terminal outcome of the inner `generate_config` loop as drawn in `../docs/copilot/05-approach-and-examples.md`. A coverage gap in any of these is a HARD-GATE failure that MUST stop M2.x work until closed.

#### Scenario: Every terminal outcome is asserted
- **WHEN** the audit enumerates the tests
- **THEN** there SHALL be at least one test asserting each of `GeneratedConfig`, `NeedsInput`, `GenerationFailed`, and `DryRunFailed`

#### Scenario: Every branch edge is asserted
- **WHEN** the audit enumerates the tests
- **THEN** there SHALL be a test for the missing-mandatory edge (returns `NeedsInput` with **no** repair re-ask), the bad-value/enum/type edge (produces a correction and re-asks), and the clean edge (proceeds to dry-run)

#### Scenario: Merge order is asserted
- **WHEN** a `constant` mapping and a provider candidate share a key
- **THEN** a test SHALL assert the candidate (scenario) value overrides the `constant` value, mirroring FleetPy's merge order

#### Scenario: A documented gap halts implementation
- **WHEN** the audit finds any enumerated node/edge/outcome without a covering test
- **THEN** the gap SHALL be reported and M2.1/M2.2/M2.5 work SHALL NOT begin until it is closed (or explicitly waived by the user)

### Requirement: Implementation matches the documented design

The audit SHALL confirm the as-built modules uphold the invariants stated in `../docs/copilot/` and flag any divergence.

#### Scenario: Invariants hold in code
- **WHEN** the audit inspects `provider.py`/`providers.py`, `validate.py`, and `dryrun.py`
- **THEN** it SHALL confirm the provider returns a plain `{param:value}` dict (validation is the caller's job), closed-vocabulary validation rejects unknown names/enums, and the dry-run gate calls `load_simulation_environment` and never `.run()`

#### Scenario: Divergence is reported, not silently fixed
- **WHEN** code behavior diverges from the docs
- **THEN** the audit SHALL report it as a finding (the docs are the current-state authority) rather than quietly changing code to match

### Requirement: hai reachability probe is accurate

The live-test gate SHALL report the hai proxy as reachable if and only if the **chat endpoint actually used by the provider** can be reached, so that a working proxy never causes a false skip and a down proxy never causes a false run.

#### Scenario: Working proxy runs the live test
- **WHEN** the hai proxy is up and authenticates a `Bearer` token on `/litellm/v1/chat/completions`
- **THEN** `test_hai_live_roundtrip` SHALL execute (not skip) and assert a `{param:value}` dict is returned

#### Scenario: Auth-required response still counts as reachable
- **WHEN** the proxy responds to an unauthenticated probe with HTTP 401
- **THEN** the reachability check SHALL treat the proxy as reachable (a 401 proves the endpoint is live), not as unreachable

#### Scenario: Down proxy skips cleanly
- **WHEN** nothing is listening on the configured base URL
- **THEN** the reachability check SHALL return false and the live test SHALL skip with a clear reason
