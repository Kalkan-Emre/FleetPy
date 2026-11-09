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

### Requirement: Providers emit deterministic output where the backend allows it

Provider output SHALL be made reproducible by sending a sampling temperature of `0` **only on backends that accept it**. This is provider-specific and MUST NOT be applied uniformly:

- The **OpenAI-compatible provider** (hai proxy + OpenAI `/chat/completions`) SHALL include `temperature` (default `0`) in its request body. Verified: the hai proxy returns HTTP 200 and produces identical output across repeated calls at `temperature=0`.
- The **Anthropic provider** (native Messages API `/v1/messages`) SHALL NOT send `temperature` by default, because current Claude models reject `temperature`/`top_p`/`top_k` with a **400** (API version 2026-10-21). If a temperature is ever threaded to it, it MUST be omitted from the body unless explicitly enabled for a model known to accept it.

The temperature field is an internal provider detail within the stateless `Provider` contract; the return value remains a plain `{param:value}` dict. Since **hai is the only live provider on this laptop and is OpenAI-compatible**, M2.1 determinism is delivered through the OpenAI-compatible path.

#### Scenario: OpenAI-compatible body carries temperature zero by default
- **WHEN** an `OpenAICompatProvider` is constructed without specifying a temperature
- **THEN** the request body sent to the endpoint SHALL include `temperature` equal to `0`

#### Scenario: OpenAI-compatible temperature is overridable
- **WHEN** an `OpenAICompatProvider` is constructed with an explicit temperature
- **THEN** that value SHALL be sent instead

#### Scenario: Anthropic body omits temperature by default
- **WHEN** an `AnthropicProvider` issues a request with default settings
- **THEN** the request body SHALL NOT contain a `temperature` key (avoiding the 400 on current Claude models)

#### Scenario: Live hai determinism holds
- **WHEN** the same prompt is sent twice through the hai provider at `temperature=0`
- **THEN** the two returned `{param:value}` dicts SHALL be identical (verified behavior)

#### Scenario: Return contract unchanged
- **WHEN** a provider with the temperature field completes a `generate` call
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
