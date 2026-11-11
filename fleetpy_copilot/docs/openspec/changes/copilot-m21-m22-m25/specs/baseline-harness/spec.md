# baseline-harness

A measurement harness that turns the **verified solver-free** seed configs into a scoreboard: for each, a reverse-engineered NL prompt is run through `generate_config`, and the result is scored on dry-run pass/fail and per-parameter precision/recall. The everyday test suite stays deterministic and offline; the full live run against a real provider is opt-in.

## ADDED Requirements

### Requirement: Eval corpus is the verified solver-free set, not the raw 47 CSVs

The "47 `studies/*/scenarios/*.csv`" figure is a **raw CSV count** across two study dirs; most are solver-based or use parameters outside the 201-name schema and are NOT valid NL→config eval cases in this environment. The harness SHALL build its corpus from the **verified solver-free, dry-run-loadable** configs already enumerated in `fleetpy_copilot/tests/_fixtures.py` (`SOLVER_FREE_DRYRUN_PAIRS`, cross-checked with `CLEAN_ACCEPT_PAIRS` / `ALL_ROWS_CLEAN_PAIRS`), and SHALL reuse `_fixtures.load_merged(const, scenario, row)` for the constant+scenario merge. "Solver-free" is determined by the **fleet-control module value** (e.g. `PoolingIRSOnly`), NOT by string-searching for "gurobi" (no seed mentions it).

#### Scenario: Corpus excludes solver-based and vocab-gap configs
- **WHEN** the harness assembles its eval set
- **THEN** it SHALL include the verified solver-free pairs and SHALL exclude `GUROBI_PAIRS` (need AlonsoMora/Gurobi) and configs whose params are absent from the 201-name schema (`KNOWN_VOCAB_GAP_PAIRS`), and the exclusions SHALL be visible in the output

#### Scenario: Merge uses the FleetPy-faithful helper
- **WHEN** a seed pair is loaded
- **THEN** the harness SHALL merge constant + one scenario row with blanks stripped exactly as `_fixtures.load_merged` does (mirroring FleetPy's own merge), not an ad-hoc merge

### Requirement: Dry-run pass and validate-clean are scored as distinct signals

A config may dry-run-load yet fail `validate()` on vocabulary gaps (e.g. the `rpp` pair is in **both** `SOLVER_FREE_DRYRUN_PAIRS` and `KNOWN_VOCAB_GAP_PAIRS`). The scoreboard SHALL therefore report **validate-clean** and **dry-run-pass** as separate columns and SHALL NOT conflate them.

#### Scenario: Both gates reported per config
- **WHEN** the harness scores one generated config
- **THEN** the row SHALL carry both whether it validated clean and whether it passed the dry-run gate, as distinct fields

#### Scenario: Row-level clean-ness is respected
- **WHEN** a seed scenario has multiple rows and only some validate clean (e.g. later rows select `PoolingIRSAssignmentBatchOptimization`, which the validator flags)
- **THEN** the harness SHALL score against a row known to be clean (row 0 for the IR pair) rather than assuming every row validates

### Requirement: Scoreboard over the solver-free seed configs

The harness SHALL, for each config in the eval corpus, derive one natural-language prompt, run it through `generate_config`, and record (a) whether the generated config passes the dry-run gold gate, (b) whether it validates clean, and (c) per-parameter precision and recall against the seed config. It SHALL emit a scoreboard aggregating these, tagged with the `PROMPT_VERSION` that produced it.

#### Scenario: Per-config row
- **WHEN** the harness processes one seed config
- **THEN** the scoreboard SHALL contain a row with its tag, validate-clean, dry-run pass/fail, and per-param precision/recall

#### Scenario: Dry-run is the gold signal
- **WHEN** a generated config is scored for functional success
- **THEN** "functional success" SHALL mean it passes `dryrun` (`load_simulation_environment`, never `.run()`), not merely that it validates

### Requirement: Deterministic offline suite, opt-in live run

The harness SHALL be runnable in two modes. The default pytest path SHALL use `MockProvider` (deterministic, offline, no network) so CI stays reproducible. A full run against a live provider (hai) SHALL be an explicit opt-in entry point, never triggered by the default suite.

#### Scenario: Default suite uses MockProvider
- **WHEN** the pytest suite runs with no live-mode flag/env
- **THEN** the harness tests SHALL use `MockProvider` and make no network calls

#### Scenario: Live run is explicit
- **WHEN** the operator invokes the opt-in live entry point with `COPILOT_PROVIDER=hai`
- **THEN** the harness SHALL run the eval corpus against the live hai provider and print the scoreboard, and this SHALL NOT run as part of the default suite

#### Scenario: Live run proves the end-to-end inner loop
- **WHEN** the opt-in live run executes against a reachable hai proxy
- **THEN** at least one seed SHALL complete the full inner loop (provider → validate → dry-run) and the scoreboard SHALL report a real dry-run pass rate

#### Scenario: Transient live failure does not abort the run
- **WHEN** one seed's live call fails transiently (timeout, rate limit, transport error)
- **THEN** the harness SHALL record that seed as failed and continue the remaining seeds, rather than aborting the whole scoreboard

### Requirement: Harness measures but does not relax validation

The harness SHALL treat the deterministic validator and dry-run gate as the oracle; it SHALL NOT weaken, bypass, or short-circuit either in order to improve scores.

#### Scenario: No validation bypass
- **WHEN** a generated config fails validation or dry-run
- **THEN** the harness SHALL record the failure truthfully and SHALL NOT alter the config or the validator to make it pass

