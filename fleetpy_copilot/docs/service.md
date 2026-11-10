# Running the Copilot as a Service

The copilot runs as an HTTP service: build it, run it, send a request, and watch a clean
step-by-step trace. The service is a thin adapter over the existing `generate_config` inner
loop — it adds no generation logic, only observability and an HTTP surface. The same trace you
watch on the console is returned in the response and written to a per-request JSON file.

This experience is designed to stay identical as the copilot grows. When the M2.3 outer
conversation loop is added, the build command, the run command, the request shape, and the trace
style are unchanged — the trace simply gains an outer `turn` span (one more indent level).

## Build

The copilot core is stdlib + FleetPy `src` only. The service tier needs FastAPI + uvicorn,
declared in the copilot's single requirements file:

```bash
pip install -r fleetpy_copilot/requirements.txt
```

(`fleetpy_copilot/requirements.txt` is the copilot's one dependency source of truth: pytest,
hypothesis, fastapi, uvicorn, httpx. The repo-root `requirements.txt` / `environment.yml` are not
touched — the core stays importable without any of these.)

## Run

```bash
python -m fleetpy_copilot                       # default: offline MockProvider
COPILOT_PROVIDER=hai python -m fleetpy_copilot  # live local hai proxy
```

On start it prints a readiness line to stderr:

```
[copilot] listening on 127.0.0.1:8750 (provider=MockProvider)
```

## Send a request

`POST /generate` with a JSON body. Only `prompt` is required.

```bash
curl -s localhost:8750/generate -H 'content-type: application/json' \
  -d '{"prompt":"ride-pooling on example_network for 2 hours"}'
```

Request fields (defaults mirror `generate_config`):

| field         | type   | default | meaning                                              |
|---------------|--------|---------|------------------------------------------------------|
| `prompt`      | string | —       | required natural-language request                    |
| `constant`    | object | `{}`    | confirmed `{param: value}` carried across turns       |
| `max_repairs` | int    | `1`     | bounded inner repair budget (≤ 2 LLM calls/turn)      |
| `do_dry_run`  | bool   | `true`  | run the FleetPy dry-run gold gate on a clean config   |

`GET /health` returns `{"ok": true, "provider": "<ProviderName>"}`.

## Response

```json
{
  "request_id": "3324fc86",
  "outcome": {
    "type": "GeneratedConfig",        // or NeedsInput / GenerationFailed / DryRunFailed
    "attempts": 1,
    "config": { "...": "..." },
    "validation": { "ok": true, "summary": "valid", "missing_mandatory": [] },
    "dry_run": { "ok": true, "error": "" }
  },
  "trace": [ { "seq": 0, "step": "attempt", "span": ["request","generate"], "...": "..." } ],
  "prompt_version": "v2"
}
```

The `outcome.type` discriminator tells the client which branch it got:

- `GeneratedConfig` — a validated, dry-run-verified config (done).
- `NeedsInput` — under-specified; `slots` lists what to ask the user for ("ask, don't infer").
  A conversational client merges the user's answers into `constant` and re-submits the same shape.
- `GenerationFailed` — the model could not produce valid output within the repair budget.
- `DryRunFailed` — validated clean but FleetPy could not load it.

## Watching the trace

Every request streams an indented step trace to the service console (stderr), nested
`request > generate`:

```
[req 3324fc86] generate  prompt='ride-pooling on example_network for 2 hours'
    attempt [attempt 1]  1/2
    llm_call [attempt 1]  0 param(s)  candidate_keys=[]
      user_prompt:
        ride-pooling on example_network for 2 hours
      raw_reply:
        {}
    merge [attempt 1]  constant_keys=[] candidate_keys=[]
    validate [attempt 1]  missing mandatory: ['demand_name', 'end_time', ...]  ok=False
    needs_input [attempt 1]  13 slot(s)  slots=["demand_name", "end_time", ...]
    outcome [attempt 1]  type=NeedsInput attempts=1
```

The full rendered system/user prompt and the raw model reply are shown under `llm_call` on every
attempt. A repair shows as `validate` (fail) → `repair` → a second `attempt`.

## Per-request JSON trace file

Each request's full event array is also written to a self-contained file:

```
logs/req-<request_id>.json
```

The directory is `COPILOT_TRACE_DIR` (default `./logs`, relative to where the service runs). The
file's events match the `trace` array in the response exactly. This is a per-request **step
trace** — distinct from the planned day-one data-collection JSONL, which logs NL→config *pairs*.

## Environment variables

| var                | default            | effect                                             |
|--------------------|--------------------|----------------------------------------------------|
| `COPILOT_PROVIDER` | `mock`             | backend: `mock` / `hai` / `openai` / `anthropic`   |
| `COPILOT_HOST`     | `127.0.0.1`        | bind host                                          |
| `COPILOT_PORT`     | `8750`             | bind port                                          |
| `COPILOT_TRACE_DIR`| `./logs`           | directory for per-request JSON trace files         |

Provider-specific vars (`HAI_*`, `OPENAI_*`, `ANTHROPIC_*`) are read by `make_provider()` exactly
as for the CLI entry points.
