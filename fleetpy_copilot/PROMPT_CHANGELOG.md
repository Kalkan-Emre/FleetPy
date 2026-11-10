# Prompt changelog

Tracks the `PROMPT_VERSION` in `_prompting.py`. Each entry pins the wording/grounding of the
system + user prompt builders so a baseline-harness scoreboard can be attributed to a prompt.

## v2 — 2026-11-10 (M2.1 iteration, from first live baseline)

The first live hai baseline (prompt v1) returned NeedsInput for all 4 solver-free seeds
(validate-clean 0%, recall 0.05-0.11). Diagnosis (Finding A): the model invented
plausible-but-invalid parameter names (`number_of_vehicles`, `simulation_time_steps`) which
validation correctly discarded — v1 grounded only the module *enums*, not the full *name* set.

v2 change: `build_system_prompt` now lists **all 201 valid parameter names verbatim** (~1.2K
tokens) and instructs the model to use a name from the list or omit it. Aim: raise recall and
validate-clean by eliminating invalid-name losses. Does NOT address Finding B (one-line prompts
are structurally under-specified for 28-param configs — that is the M2.3 conversation loop).

## v1 — 2026-11-10 (M2.1)

Baseline tuned prompt. System prompt:
- Return ONLY a single JSON object; no prose, no explanation, no markdown fences.
- Use ONLY schema parameter names and module values; never invent a name or module value.
- For a module-selecting parameter, choose one of its listed valid values **verbatim**.
- **Omit** an uncertain parameter rather than guessing (missing is asked for; wrong is a mistake).
- Grounding appended by `build_system_prompt`: the module-selecting params + their enums
  (`schema.module_enums()`), and the total count of valid names (`schema.VALID_PARAM_NAMES`).

User prompt (`build_user_prompt`): the request, plus — on a repair turn — the correction
instruction naming exactly the problems to fix.

Supersedes the pre-versioning wording ("Omit parameters you are unsure of rather than guessing")
by making enum-verbatim adherence explicit, which is where models most often erred.
