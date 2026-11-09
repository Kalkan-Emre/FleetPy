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
| `providers.py` | Add `temperature` field (default `0`) to both providers; send it in the request body | M2.1 |
| `provider.py` | Thread `temperature` only if needed by the protocol; keep the return contract a plain dict | M2.1 |
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
- **`temperature=0` as a provider field, default-on.** Determinism is a property of the model call, so it belongs in the provider, not the harness. Default `0` so every path (including existing live tests) is reproducible without opt-in. Kept overridable for future exploration. Alternative rejected: per-call temperature plumbed through `generate_config` — more surface, no current need.
- **Repair cap via `max_repairs` default `1` (two calls).** A behavior change with its own spec (`repair-cap`) because it is independently observable (call counts, `GenerationFailed`). Keeping it a default (not hardcoded) preserves caller control.
- **Harness as a new `eval/` subpackage, two modes.** Default pytest path uses `MockProvider` (deterministic, offline). The 47-config live-hai run is an explicit opt-in entry point — Option 2 — so CI stays reproducible while we still get real numbers on demand. Alternative rejected: live-in-CI (slow, non-deterministic, proxy-dependent).
- **Per-param precision/recall, dry-run as gold.** Matches the metric design already in doc 05; exact-match is too brittle. The validator + dry-run remain the oracle; the harness never relaxes them.
- **Prompt versioning in-repo (`PROMPT_VERSION` + changelog).** Lightweight, no tooling; lets a scoreboard be attributed to a prompt. promptfoo deferred (doc 01).

## Risks / Trade-offs

- [Live LLM is non-deterministic even at `temperature=0`] → keep the default suite on MockProvider; treat live scoreboard numbers as indicative, run more than once when a delta looks marginal.
- [Reverse-engineered NL prompts bias the scoreboard] → derive them mechanically/consistently from the seed config fields; record the derivation so results are reproducible and the bias is at least uniform.
- [hai rate limits / latency during a 47-config run] → opt-in only; the harness tolerates transient per-config failures (records them) rather than aborting the whole run.
- [`temperature` field breaks a provider's request shape] → covered by a provider contract test asserting the body includes `temperature`; MockProvider unaffected (no network).
- [Audit tempts "fix code to match docs"] → audit reports divergence; code changes only happen in the named milestones, not silently in Phase 0.

## Test & verification plan

- **Audit:** enumerate tests against the doc-05 node/edge/outcome list; add missing coverage; fix `_hai_reachable`; prove the live roundtrip actually runs against the up proxy. Gate: full suite green + each outcome/edge asserted.
- **M2.1:** unit tests for prompt builders (vocabulary present, correction carried); provider contract test (`temperature=0` in body, overridable, dict return); `test_generate.py` budget-exhausted updated to two calls. Gate: full suite green.
- **M2.2:** MockProvider harness tests (per-config row shape, solver-free filtering, no validation bypass); then the **opt-in live hai run** during "observe" — real scoreboard with ≥1 seed completing provider→validate→dry-run. Gate: deterministic tests green + a live scoreboard captured in the report.
- **Env-agnostic:** suite must collect under both conda and pip; no new dependency is the target. If one is unavoidable, declare in all three manifests before committing.
- **Commit discipline:** commit only at a green checkpoint on `copilot`; never push.

## Open Questions

- Exact NL-prompt derivation rule per seed config (template vs. light paraphrase) — to be fixed at the start of M2.2's plan stage and recorded for reproducibility.
- Whether `provider.py`'s `Provider` protocol signature needs `temperature` at all, or whether it stays provider-constructor-only (leaning constructor-only, since the protocol is about `generate`, not construction).
