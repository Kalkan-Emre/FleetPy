<!-- Group tasks by AREA within the single package (no component repos).
     e.g. prompting · providers · generate/orchestration · validate · serialize · dryrun · tests · docs
     Local-only (WORKFLOW.md): NO manifest.yaml, NO per-component branches, NO PRs/push.
     A group is "done" when code + tests are written AND the suite passes:
       .venv/bin/python -m pytest fleetpy_copilot/tests -q   (the commit gate). -->

## 1. <area> — <brief description>

- [ ] 1.1 Task description (ref: Requirement <name>)
- [ ] 1.2 Task description

## 2. tests — prove it

- [ ] 2.1 Add/extend tests for the above (unit / hypothesis property / dry-run as fits)
- [ ] 2.2 Verify suite passes under the project `.venv` (and, if deps changed, under conda)
