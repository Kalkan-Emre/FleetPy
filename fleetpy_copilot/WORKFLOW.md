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

## 4. Branch

- Work happens on the local **`copilot`** branch.
- `copilot` is branched from **`main`** — always branch from `main`, never from
  `emre-onboarding` or other feature branches.
- Do not merge into or push `copilot` without explicit human instruction.

---

**Summary:** Commit early and often for *tested, working* steps — locally.
Never push to remote.
