## Why

The copilot's inner pipeline is built and unit-tested (295/2), but it has **never been proven end-to-end against a real LLM**, and there is **no measurement** of how often a natural-language request actually becomes a loadable config. Before investing further, we must (a) confirm the as-built code and tests actually match the documented design and cover every node/edge of the inner-loop diagram, and (b) produce the first real scoreboard so prompt work stops being blind. This advances the copilot from "wired" to "measured and verified on a live model."

## Intent Source

Plain-text input (this session). Follows the design decisions recorded for M2.1/M2.2/M2.5 and the conversation/state design already written into `../docs/copilot/`.

## Milestone

**M2.1** (prompt v1 tuning) + **M2.2** (baseline harness / scoreboard) + **M2.5** (prompt versioning), gated by a **Phase-0 audit** of the M2.0 as-built state. M2.3 (conversation loop) is explicitly out of scope this cycle.

## What Changes

**Phase 0 — Audit (HARD GATE, no code changes).** Verify implementation-vs-docs alignment and that tests cover every node and edge of the doc-05 mermaid inner loop:
- nodes: `provider.generate` · merge `constant→scenario` · `validate` (5 checks) · `serialize` · `dryrun`;
- branches/edges: missing-mandatory → `NeedsInput` (no retry); bad value/enum/type → correction → re-ask (bounded); clean → dry-run; dry-run ok/fail;
- outcomes: `GeneratedConfig` · `NeedsInput` · `GenerationFailed` · `DryRunFailed`;
- the repair bound itself.
Confirm the suspected **false-skip** in `tests/test_providers.py::_hai_reachable()` (unauthenticated probe vs a proxy that returns 401 without auth). **If material gaps are found, STOP and report before any M2.x work.**

**M2.1 — prompt tuning + determinism + repair cap:**
- Tune the system/user prompts in `_prompting.py` (grounding in the closed vocabulary).
- Add `temperature=0` to the providers for reproducible output. **BREAKING (internal):** provider constructors gain a `temperature` field and send it in the request body — within the stateless `Provider` contract; the `{param:value}` return shape is unchanged.
- Lower the inner repair cap to **max 2 LLM calls/turn** (`generate_config` default `max_repairs` 2 → 1) and fix the "budget exhausted" test.

**M2.2 — baseline harness / scoreboard (new):**
- Reverse-engineer one NL prompt per **solver-free** config among the 47 `studies/*/scenarios/*.csv` seeds.
- Run each through `generate_config`, record **dry-run pass/fail** + **per-param precision/recall**, emit a scoreboard.
- **Run mode (Option 2):** the everyday pytest suite stays deterministic/offline on `MockProvider`; the full live run against **hai** is an **opt-in** entry point (not CI). Goal: prove we can call the real LLM and drive the inner loop end-to-end.

**M2.5 — prompt versioning:**
- Add a `PROMPT_VERSION` tag in `_prompting.py` + a short prompt changelog, so a scoreboard can be attributed to a prompt version. promptfoo stays deferred.

## Capabilities

### New Capabilities
- `inner-loop-audit` — the Phase-0 verification: alignment + per-node/edge test coverage + the hai-reachability fix. (Gate; may itself add/repair tests.)
- `prompt-tuning` — tuned prompts, provider determinism (`temperature=0`), prompt versioning (M2.1 + M2.5 share the prompt surface).
- `repair-cap` — the inner repair loop bounded to max 2 LLM calls/turn (M2.1 behavior change).
- `baseline-harness` — the NL→config scoreboard over the solver-free seed configs, with an opt-in live-hai mode (M2.2).

### Modified Capabilities
<!-- None: openspec/specs/ is empty (first change). The audit may repair existing tests, but changes no requirement contracts. -->

## Scope & Impact

**Modules touched (all under `fleetpy_copilot/`):** `_prompting.py` (prompts + `PROMPT_VERSION`), `providers.py` (temperature), `provider.py` (protocol signature if temperature is threaded), `generate.py` (`max_repairs` default), `tests/` (coverage repairs + new harness tests), a new harness module + an opt-in live runner, and a prompt changelog file. New docs/report go under a temp md file for the loop and, if numbers land, a note in `../docs/copilot/05`.

**Invariants preserved:**
- **FleetPy `src/` stays untouched** (read-only import only).
- **Hallucination-proof closed-vocabulary validation** remains the authority; the harness measures, it does not relax validation.
- **Provider stays stateless**, returns a plain `{param:value}` dict.
- **Dry-run gold gate** (`load_simulation_environment`, never `.run()`).
- **Env-agnostic:** target is **no new dependency** (stdlib + pytest). If one proves unavoidable it MUST be declared in all three manifests (`requirements.txt`, `environment.yml` pip:, `fleetpy_copilot/requirements-test.txt`).
- **Local-only workflow** (`WORKFLOW.md`): never push; commit only tested checkpoints on `copilot`.
