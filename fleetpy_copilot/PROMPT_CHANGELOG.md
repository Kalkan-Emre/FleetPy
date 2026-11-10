# Prompt changelog

Tracks the `PROMPT_VERSION` in `_prompting.py`. Each entry pins the wording/grounding of the
system + user prompt builders so a baseline-harness scoreboard can be attributed to a prompt.

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
