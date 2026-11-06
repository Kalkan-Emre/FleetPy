# Development Workflow Rules — FleetPy Copilot

These rules govern **all** version-control activity for the FleetPy Copilot work.
Every agent and contributor working in this repo MUST follow them.

## 1. Never push to remote

- **Do not `git push`** — under any circumstances, to any remote, on any branch.
- All version-control activity stays **local only**.
- If a push seems necessary, stop and ask the human first. Do not push on your own judgment.

## 2. Commit meaningful, tested steps

- Keep **every meaningful development step logged** in the local branch history.
- Commit **only when the current step is fully tested and working** and we are ready
  to move on to the next step. A commit marks a known-good checkpoint.
- Do **not** commit broken, untested, or half-finished work.
- Before committing, confirm the step works (e.g. the relevant tests pass:
  `.venv/bin/python -m pytest fleetpy_copilot/tests -q`).

## 3. Scope

- Restrict modifications to the `docs/` and `fleetpy_copilot/` (copilot) folders.
- Do **not** touch core `src/`, configs, or existing tests outside the copilot package.
  Revert any accidental change outside scope immediately.
- **Dependency exception.** If the copilot gains a genuine new dependency (runtime or
  test), you *may* update the shared dependency manifests (`environment.yml` for conda,
  `requirements.txt` for local pip) so both the conda and pip environments can run the
  suite. This is the **only** sanctioned reason to edit a file outside `docs/`/`fleetpy_copilot/`.
  Before doing so, confirm the dependency is **really needed** — e.g. a test module
  imports it at collection time, so omitting it would break
  `.venv/bin/python -m pytest fleetpy_copilot/tests -q` on an environment that lacks it.
  Prefer declaring it in `fleetpy_copilot/requirements-test.txt` (in scope) as well, and
  keep the manifest edit minimal (just the new line).

## 4. Branch

- Work happens on the local **`copilot`** branch.
- `copilot` is branched from **`main`** — always branch from `main`, never from
  `emre-onboarding` or other feature branches.
- Do not merge into or push `copilot` without explicit human instruction.

---

**Summary:** Commit early and often for *tested, working* steps — locally.
Never push to remote.
