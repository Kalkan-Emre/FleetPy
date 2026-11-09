<!-- Local-only (WORKFLOW.md): NO manifest.yaml, NO per-component branches, NO PRs/push.
     Each loop stage is logged to fleetpy_copilot/.sdd-loop/<milestone>.md (gitignored).
     A group is "done" only when its tests are written AND the full suite passes:
       .venv/bin/python -m pytest fleetpy_copilot/tests -q   (the commit gate). -->

## 0. audit — HARD GATE (ref: inner-loop-audit)

- [ ] 0.1 Enumerate existing tests against the doc-05 inner-loop nodes/edges/outcomes; produce a coverage matrix in the loop report
- [ ] 0.2 Assert each terminal outcome exists: `GeneratedConfig` / `NeedsInput` / `GenerationFailed` / `DryRunFailed` (add tests for any missing)
- [ ] 0.3 Assert each edge: missing-mandatory→NeedsInput (no repair) · bad-value→correction→re-ask · clean→dry-run · merge order (scenario overrides constant)
- [ ] 0.4 Confirm invariants in code: provider returns plain dict (no validation) · closed-vocab rejects unknowns · dryrun calls `load_simulation_environment`, never `.run()`
- [ ] 0.5 Fix `tests/test_providers.py::_hai_reachable()` to probe the real chat endpoint / treat 401 as reachable; prove `test_hai_live_roundtrip` RUNS (not skips) against the up proxy
- [ ] 0.6 Run full suite; record result. **If material gaps found → STOP and report before M2.x**

## 1. prompt-tuning — M2.1 + M2.5 (ref: prompt-tuning)

- [ ] 1.1 Add `PROMPT_VERSION` to `_prompting.py` + create a prompt changelog file (seed with the current/baseline version)
- [ ] 1.2 Tune `build_system_prompt` / `build_user_prompt` wording + vocabulary grounding; bump `PROMPT_VERSION`; add changelog entry
- [ ] 1.3 Unit tests: system prompt carries module enums + JSON-only instruction; correction carried on repair turn; out-of-vocab name still rejected by `validate`

## 2. providers — determinism — M2.1 (ref: prompt-tuning)

- [ ] 2.1 Add `temperature` field (default `0`) to `OpenAICompatProvider` and `AnthropicProvider`; include it in the request body
- [ ] 2.2 Decide/keep `Provider` protocol as constructor-only for temperature (resolve the design open question); keep return = plain dict
- [ ] 2.3 Provider contract tests: body includes `temperature=0` by default; overridable; MockProvider unaffected; dict-return unchanged

## 3. generate/orchestration — repair cap — M2.1 (ref: repair-cap)

- [ ] 3.1 Change `generate_config` default `max_repairs` 2 → 1
- [ ] 3.2 Update `tests/test_generate.py`: budget-exhausted → `GenerationFailed` after exactly two provider calls; one-repair-converges still holds; missing-mandatory makes exactly one call
- [ ] 3.3 Run full suite; green checkpoint → commit M2.1+M2.5

## 4. eval/baseline-harness — M2.2 (ref: baseline-harness)

- [ ] 4.1 Fix the NL-prompt derivation rule per seed config (template); record it in the loop report for reproducibility
- [ ] 4.2 Build `eval/` harness: select solver-free seeds, derive prompt, run `generate_config`, score dry-run pass + per-param precision/recall, emit scoreboard (including `PROMPT_VERSION`)
- [ ] 4.3 Add opt-in live entry point (runs only when invoked; default suite stays MockProvider/offline)
- [ ] 4.4 Harness tests (MockProvider): per-config row shape · solver-free filtering visible · no validation/dry-run bypass
- [ ] 4.5 Run full suite (offline) → green checkpoint

## 5. observe — live end-to-end on hai (ref: baseline-harness)

- [ ] 5.1 Run the opt-in live harness against hai; capture the real scoreboard in the loop report
- [ ] 5.2 Confirm ≥1 seed completes the full inner loop (provider → validate → dry-run) on the live model; record NL→dry-run-pass rate
- [ ] 5.3 Report: observed vs intended behavior, surprises, next-prompt-iteration ideas; decide whether to iterate M2.1 wording again

## 6. tests — final gate

- [ ] 6.1 Full suite green under the project `.venv`; confirm no new runtime dependency added (env-agnostic); if any dep added, declare in all three manifests
- [ ] 6.2 Final local commit on `copilot` (never push); update `../docs/copilot/05` with the measured scoreboard note if numbers landed
