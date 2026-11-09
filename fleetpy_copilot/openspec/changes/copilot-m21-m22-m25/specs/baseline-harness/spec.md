# baseline-harness

A measurement harness that turns the solver-free seed configs into a scoreboard: for each, a reverse-engineered NL prompt is run through `generate_config`, and the result is scored on dry-run pass/fail and per-parameter precision/recall. The everyday test suite stays deterministic and offline; the full live run against a real provider is opt-in.

## ADDED Requirements

### Requirement: Scoreboard over the solver-free seed configs

The harness SHALL, for each solver-free config among the 47 `studies/*/scenarios/*.csv` seeds, derive one natural-language prompt, run it through `generate_config`, and record (a) whether the generated config passes the dry-run gold gate and (b) per-parameter precision and recall against the seed config. It SHALL emit a scoreboard aggregating these.

#### Scenario: Per-config row
- **WHEN** the harness processes one seed config
- **THEN** the scoreboard SHALL contain a row with its tag, dry-run pass/fail, and per-param precision/recall

#### Scenario: Only solver-free configs are included
- **WHEN** the seed corpus contains configs that require an unavailable solver (e.g. Gurobi)
- **THEN** those SHALL be excluded from the baseline run (consistent with the solver-free environment), and the exclusion SHALL be visible in the output

#### Scenario: Dry-run is the gold signal
- **WHEN** a generated config is scored
- **THEN** "functional success" SHALL mean it passes `dryrun` (`load_simulation_environment`, never `.run()`), not merely that it validates

### Requirement: Deterministic offline suite, opt-in live run

The harness SHALL be runnable in two modes. The default pytest path SHALL use `MockProvider` (deterministic, offline, no network) so CI stays reproducible. A full run against a live provider (hai) SHALL be an explicit opt-in entry point, never triggered by the default suite.

#### Scenario: Default suite uses MockProvider
- **WHEN** the pytest suite runs with no live-mode flag/env
- **THEN** the harness tests SHALL use `MockProvider` and make no network calls

#### Scenario: Live run is explicit
- **WHEN** the operator invokes the opt-in live entry point with `COPILOT_PROVIDER=hai`
- **THEN** the harness SHALL run the seeds against the live hai provider and print the scoreboard, and this SHALL NOT run as part of the default suite

#### Scenario: Live run proves the end-to-end inner loop
- **WHEN** the opt-in live run executes against a reachable hai proxy
- **THEN** at least one seed SHALL complete the full inner loop (provider → validate → dry-run) and the scoreboard SHALL report a real dry-run pass rate

### Requirement: Harness measures but does not relax validation

The harness SHALL treat the deterministic validator and dry-run gate as the oracle; it SHALL NOT weaken, bypass, or short-circuit either in order to improve scores.

#### Scenario: No validation bypass
- **WHEN** a generated config fails validation or dry-run
- **THEN** the harness SHALL record the failure truthfully and SHALL NOT alter the config or the validator to make it pass
