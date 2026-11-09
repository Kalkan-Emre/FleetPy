# repair-cap

The inner repair loop is bounded to at most 2 LLM calls per turn (one initial attempt plus one repair), reducing cost and latency while preserving the "ask, don't infer" stance for under-specification.

## ADDED Requirements

### Requirement: Inner repair loop is bounded to two LLM calls per turn

`generate_config` SHALL default `max_repairs` to `1`, so a single turn performs at most two provider calls (one initial attempt + one repair). The bound is explicit and configurable by the caller.

#### Scenario: Clean first attempt makes one call
- **WHEN** the provider's first candidate validates clean
- **THEN** exactly one provider call SHALL be made and a `GeneratedConfig` (or `DryRunFailed`) returned

#### Scenario: One repair on a fixable mistake
- **WHEN** the first candidate has a bad value/enum/type and the second candidate is clean
- **THEN** exactly two provider calls SHALL be made and a `GeneratedConfig` returned

#### Scenario: Budget exhausted after two calls
- **WHEN** both the first and the single repaired candidate remain invalid with the default budget
- **THEN** exactly two provider calls SHALL be made and `GenerationFailed` returned

#### Scenario: Missing mandatory never consumes a repair
- **WHEN** the first candidate is missing a mandatory parameter
- **THEN** `generate_config` SHALL return `NeedsInput` after exactly one provider call, with no repair re-ask

### Requirement: Repair-cap change is reflected in tests

The existing orchestration tests SHALL be updated so the "budget exhausted" case reflects the new default bound (two calls), and no test SHALL assume the old three-call budget.

#### Scenario: Budget-exhausted test matches the new cap
- **WHEN** the orchestration test suite runs with the default `max_repairs`
- **THEN** the budget-exhausted test SHALL assert `GenerationFailed` after two provider calls, and the full suite SHALL pass
