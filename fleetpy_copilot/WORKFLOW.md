# Development Workflow Rules — FleetPy Copilot

These rules govern **all** version-control activity for the FleetPy Copilot work.
Every agent and contributor working in this repo MUST follow them.

## 1. Remotes: fork is pushable, upstream is not

The copilot's home is a **fork** of `TUM-VT/FleetPy`. Two remotes:

- **`origin`** → `https://github.com/TUM-VT/FleetPy.git` (upstream). **Pull-only.**
  **Never `git push origin`** under any circumstances — we have no write access and
  must not try. Use it only to `git fetch` / rebase onto upstream `main`.
- **`fork`** → our fork (`<user>/FleetPy`). The `copilot` branch lives here. Pushing
  the `copilot` branch to `fork` is allowed, **but only with explicit human go-ahead** —
  do not push on your own judgment. Never push to any `main`.

If any push seems necessary, stop and ask the human first, and name the remote.
Eventual upstreaming path: open a PR from `fork:copilot` → `TUM-VT/FleetPy` if/when
we get contributor access.

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
  Keep the manifest edit minimal (just the new line). The copilot's own dependency
  manifest is `fleetpy_copilot/requirements.txt` (pytest, hypothesis, fastapi, uvicorn,
  httpx) — declare the dependency there too, in scope.

## 4. Branch

- Work happens on the local **`copilot`** branch.
- `copilot` is branched from **`main`** — always branch from `main`, never from
  `emre-onboarding` or other feature branches.
- Do not merge `copilot` into any `main`. Push it only to the **`fork`** remote, and
  only with explicit human instruction (see §1).

---

**Summary:** Commit early and often for *tested, working* steps. Push `copilot` to the
**`fork`** remote only on explicit human go-ahead — **never** to `origin` (upstream).
