# prompt-tuning

Tuned prompt construction grounded in FleetPy's closed vocabulary, deterministic provider output via `temperature=0`, and a versioned prompt surface so a scoreboard can be attributed to a specific prompt. Covers M2.1 (prompt + determinism) and M2.5 (versioning).

## ADDED Requirements

### Requirement: Prompts ground the model in the closed vocabulary

The prompt builder in `_prompting.py` SHALL instruct the model to return only a JSON `{param:value}` object using FleetPy's real parameter names and module-enum values, and SHALL inject the module-selecting enums. Tuning the wording MUST NOT weaken the deterministic validator, which remains the sole authority on correctness.

#### Scenario: System prompt carries the closed vocabulary
- **WHEN** `build_system_prompt()` is called with no override
- **THEN** the returned text SHALL include the module-selecting parameters and their valid enum values, and SHALL instruct the model to emit only a JSON object with no prose

#### Scenario: Correction is carried on a repair turn
- **WHEN** `build_user_prompt(prompt, correction)` is called with a non-empty correction
- **THEN** the returned text SHALL include both the original request and the correction instruction

#### Scenario: Tuning does not bypass validation
- **WHEN** a tuned prompt is in effect and a model returns an out-of-vocabulary parameter name
- **THEN** `validate()` SHALL still reject it (the closed-vocabulary guarantee is unchanged)

### Requirement: Providers emit deterministic output

Each real provider SHALL send a configurable sampling temperature defaulting to `0`, so repeated runs over the same prompt are reproducible for the baseline harness. This is an internal signature change within the stateless `Provider` contract; the return value remains a plain `{param:value}` dict.

#### Scenario: Temperature defaults to zero
- **WHEN** a provider is constructed without specifying a temperature
- **THEN** the request body sent to the backend SHALL include `temperature` equal to `0`

#### Scenario: Temperature is overridable
- **WHEN** a provider is constructed with an explicit temperature
- **THEN** that value SHALL be sent instead

#### Scenario: Return contract unchanged
- **WHEN** a provider with the new temperature field completes a `generate` call
- **THEN** it SHALL still return a plain `{param:value}` dict and perform no validation

### Requirement: The prompt surface is versioned

`_prompting.py` SHALL expose a `PROMPT_VERSION` identifier, and a prompt changelog SHALL record each version. Any change to the prompt wording or grounding MUST bump `PROMPT_VERSION` and add a changelog entry.

#### Scenario: Version is exposed
- **WHEN** `_prompting` is imported
- **THEN** a `PROMPT_VERSION` string SHALL be available

#### Scenario: Scoreboard records the prompt version
- **WHEN** the baseline harness produces a scoreboard
- **THEN** the scoreboard SHALL include the `PROMPT_VERSION` that produced it

#### Scenario: Wording change bumps the version
- **WHEN** the system or user prompt text is modified
- **THEN** `PROMPT_VERSION` SHALL be incremented and a changelog entry added in the same change
