# Design — copilot-m21-m22-m25 (audit-gated M2.1 + M2.2 + M2.5)

## Context

The inner pipeline (`provider → validate → serialize → dryrun` with a bounded repair loop) is built and unit-tested (295/2) but never proven against a live model and never measured. This change adds a hard-gate audit, then tunes prompts, makes provider output deterministic, caps the repair loop, versions the prompt, and builds a scoreboard harness. Constraints: FleetPy `src/` stays read-only; the package stays env-agnostic (stdlib + pytest; a new dep → all three manifests); local-only per `WORKFLOW.md`. `MockProvider` remains the deterministic CI path; hai is the live provider on this laptop (verified: HTTP 200 with `Bearer $ANTHROPIC_AUTH_TOKEN` on `/litellm/v1/chat/completions`).

## Execution model — the implementation loop

Each milestone is implemented as an independent **plan → build → run → test → observe → report** cycle, logged to a temp md file (`fleetpy_copilot/.sdd-loop/<milestone>.md`, gitignored). Each stage is verified on its own evidence (command output, test results), with the model acting as its own harsh critic — no stage is declared done on assertion alone. The audit (Phase 0) is a hard gate: material gaps stop M2.x until closed or waived.

## Module impact (all under `fleetpy_copilot/`)

| Module | Change | Milestone |
|--------|--------|-----------|
| `tests/test_providers.py` | Fix `_hai_reachable()` to probe the actual chat endpoint / treat 401 as reachable | Audit |
| `tests/` (various) | Add any missing node/edge/outcome coverage found by the audit | Audit |
| `_prompting.py` | Tune system/user prompts; add `PROMPT_VERSION`; add a prompt changelog file alongside | M2.1 + M2.5 |
| `providers.py` | Add `temperature` (default `0`) to `OpenAICompatProvider` and send in body; `AnthropicProvider` does NOT send temperature by default (would 400) | M2.1 |
| `provider.py` | Keep `Provider` protocol unchanged — temperature is a constructor detail of concrete providers, not a `generate()` param | M2.1 |
| `generate.py` | `max_repairs` default `2 → 1` | M2.1 |
| `tests/test_generate.py` | Update the "budget exhausted" case to the two-call cap | M2.1 |
| `eval/` (new) | Harness: prompt derivation, runner, scorer (per-param P/R), scoreboard; opt-in live entry point | M2.2 |
| `tests/test_eval_*.py` (new) | Deterministic MockProvider tests for the harness | M2.2 |

Nothing in `src/` changes. Nothing in the pipeline's shape changes except the repair bound.

## Goals / Non-Goals

**Goals:** prove the inner loop end-to-end on hai; produce the first real NL→dry-run-pass scoreboard; make provider output reproducible; keep prompts traceable by version; keep the default suite deterministic/offline.

**Non-Goals:** the outer conversation loop / slot-filling (M2.3); the full eval harness with a committed dataset + CI (M3); local-model comparison; promptfoo; any UI; adding a runtime dependency (target: none).

## Decisions

- **Audit before build, as a hard gate.** Measuring/tuning on top of an unverified base wastes effort; the audit also fixes the live-test gate so later live runs are trustworthy. Rationale: the stated goal is *verified* end-to-end behavior, which presupposes trustworthy tests.
- **`temperature=0` as a provider field — OpenAI-compatible path only, verified live.** Determinism is a property of the model call, so it belongs in the provider. **Verified 2026-11-09:** the hai proxy accepts `temperature=0` (HTTP 200) and is deterministic (identical output across repeated calls). **Critical asymmetry:** the native Anthropic Messages API rejects `temperature`/`top_p`/`top_k` with a **400** on current Claude models (API version 2026-10-21), so `AnthropicProvider` MUST NOT send `temperature` by default. Since hai (OpenAI-compatible) is the only live provider on this laptop, M2.1 determinism is delivered through `OpenAICompatProvider`; the Anthropic adapter simply omits it. Alternative rejected: add it uniformly to both providers — would 400 the Anthropic path.
- **Repair cap via `max_repairs` default `1` (two calls).** A behavior change with its own spec (`repair-cap`) because it is independently observable (call counts, `GenerationFailed`). Keeping it a default (not hardcoded) preserves caller control. Note: the existing budget-exhausted test passes `max_repairs=2` explicitly, so it does NOT cover the default — task 3.2 must add a default-cap test.
- **Harness corpus = the verified solver-free set, not the raw 47 CSVs.** The 47 figure is a raw CSV count; most are solver-based (`GUROBI_PAIRS`) or use out-of-schema params (`KNOWN_VOCAB_GAP_PAIRS`). The harness builds from `_fixtures.SOLVER_FREE_DRYRUN_PAIRS` and reuses `_fixtures.load_merged`. "Solver-free" keys off the fleet-control **module value**, not a "gurobi" string search (0 seeds match). Dry-run-pass and validate-clean are scored as **distinct** signals because `rpp` dry-run-loads but fails validate on vocab gaps. Alternative rejected: run all 47 — a garbage scoreboard dominated by environment/corpus artifacts.
- **Per-param precision/recall, dry-run as gold.** Matches the metric design already in doc 05; exact-match is too brittle. The validator + dry-run remain the oracle; the harness never relaxes them.
- **Harness as a new `eval/` subpackage, two run modes (Option 2).** Default pytest path uses `MockProvider` (deterministic, offline). The live-hai run over the corpus is an explicit opt-in entry point, never in CI — so the suite stays reproducible while real numbers are available on demand. Alternative rejected: live-in-CI (slow, non-deterministic, proxy-dependent).
- **Prompt versioning in-repo (`PROMPT_VERSION` + changelog).** Lightweight, no tooling; lets a scoreboard be attributed to a prompt. promptfoo deferred (doc 01).

## Risks / Trade-offs

- [Live LLM is non-deterministic even at `temperature=0`] → keep the default suite on MockProvider; treat live scoreboard numbers as indicative, run more than once when a delta looks marginal. (Verified: hai was deterministic across 2 runs at temp 0, but don't assume it always is.)
- [`temperature` on the Anthropic body would 400 on current Claude models] → `AnthropicProvider` omits `temperature` by default; a provider contract test asserts the Anthropic body has no `temperature` key while the OpenAI-compatible body does. Verified live that hai accepts and is deterministic at `temperature=0`.
- [Reverse-engineered NL prompts bias the scoreboard] → derive them mechanically/consistently from the seed config fields; record the derivation so results are reproducible and the bias is at least uniform.
- [hai rate limits / latency during the live run] → opt-in only; the harness records transient per-config failures and continues rather than aborting the whole run.
- [Audit tempts "fix code to match docs"] → audit reports divergence; code changes only happen in the named milestones, not silently in Phase 0.

## Test & verification plan

- **Audit:** enumerate tests against the doc-05 node/edge/outcome list; add missing coverage; fix `_hai_reachable`; prove the live roundtrip actually runs against the up proxy. Gate: full suite green + each outcome/edge asserted.
- **M2.1:** unit tests for prompt builders (vocabulary present, correction carried); provider contract test (`temperature=0` in body, overridable, dict return); `test_generate.py` budget-exhausted updated to two calls. Gate: full suite green.
- **M2.2:** MockProvider harness tests (per-config row shape, solver-free filtering, no validation bypass); then the **opt-in live hai run** during "observe" — real scoreboard with ≥1 seed completing provider→validate→dry-run. Gate: deterministic tests green + a live scoreboard captured in the report.
- **Env-agnostic:** suite must collect under both conda and pip; no new dependency is the target. If one is unavoidable, declare in all three manifests before committing.
- **Commit discipline:** commit only at a green checkpoint on `copilot`; never push.

## Open Questions

- Exact NL-prompt derivation rule per seed config (template vs. light paraphrase) — to be fixed at the start of M2.2's plan stage and recorded for reproducibility.

## Resolved (during careful spec pass, 2026-11-09)

- **`Provider` protocol stays unchanged** — `temperature` is a constructor detail of concrete providers, not a `generate()` parameter; the protocol is about `generate`, not construction. (Was an open question.)
- **`temperature` is OpenAI-compatible-only** — verified the hai proxy accepts `temperature=0` (HTTP 200, deterministic) while the native Anthropic Messages API 400s on it for current models. `AnthropicProvider` omits it. (Was the naive "add to both providers" plan.)
- **Eval corpus is the verified solver-free set** from `_fixtures.py`, not the raw 47 CSVs; dry-run-pass and validate-clean scored distinctly. (Was "the 47 seeds".)
