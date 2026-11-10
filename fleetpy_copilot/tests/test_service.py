"""Tests for the service adapter (service.py).

The pure, framework-free core — handle_generate + serialize_outcome — is tested
without a socket and without FastAPI. The FastAPI route layer is tested via
TestClient but SKIPPED if fastapi/httpx are not installed, so the core suite still
runs under a bare env (mirrors the live-provider skip pattern).
"""
import json

import pytest

from fleetpy_copilot import service
from fleetpy_copilot.generate import (
    DryRunFailed,
    GeneratedConfig,
    GenerationFailed,
    NeedsInput,
    generate_config,
)
from fleetpy_copilot.provider import MockProvider
from fleetpy_copilot.tests import _fixtures


@pytest.fixture
def good_config():
    return _fixtures.load_merged("constant_config_ir.csv", "example_ir_only.csv", 0)


# --- handle_generate: socket-free, framework-free ------------------------------

def test_handle_generate_success(good_config):
    resp = service.handle_generate(
        {"prompt": "ir-only", "do_dry_run": False}, MockProvider([good_config])
    )
    assert resp["outcome"]["type"] == "GeneratedConfig"
    assert resp["outcome"]["attempts"] == 1
    assert resp["trace"] and resp["trace"][-1]["step"] == "outcome"
    assert resp["prompt_version"] == "v2"
    assert "request_id" in resp


def test_handle_generate_needs_input(good_config):
    broken = dict(good_config)
    broken.pop("sim_env")
    resp = service.handle_generate(
        {"prompt": "under-specified", "do_dry_run": False}, MockProvider([broken])
    )
    assert resp["outcome"]["type"] == "NeedsInput"
    assert any(s["name"] == "sim_env" for s in resp["outcome"]["slots"])


def test_handle_generate_requires_prompt(good_config):
    with pytest.raises(ValueError, match="prompt"):
        service.handle_generate({"prompt": "   "}, MockProvider([good_config]))


def test_handle_generate_passes_constant(good_config):
    resp = service.handle_generate(
        {"prompt": "x", "constant": {"end_time": 7200}, "do_dry_run": False},
        MockProvider([{"end_time": 3600}]),
    )
    # candidate overrides constant; both keys present in the serialized config
    cfg = resp["outcome"].get("config") or resp["outcome"].get("candidate")
    assert cfg["end_time"] == 3600


# --- serialize_outcome: every outcome round-trips through json -----------------

def _make_outcomes(good_config):
    broken = dict(good_config); broken.pop("sim_env")
    bad = dict(good_config); bad["op_module"] = "Nope"
    return [
        generate_config("x", MockProvider([good_config]), do_dry_run=False),   # GeneratedConfig
        generate_config("x", MockProvider([broken]), do_dry_run=False),        # NeedsInput
        generate_config("x", MockProvider([bad]), max_repairs=1, do_dry_run=False),  # GenerationFailed
    ]


def test_serialize_outcome_round_trips(good_config):
    for outcome in _make_outcomes(good_config):
        d = service.serialize_outcome(outcome)
        assert d["type"] == type(outcome).__name__
        assert d["validation"]["ok"] == outcome.validation.ok
        assert "summary" in d["validation"]
        # must be json-dumpable without raising
        json.dumps(d)


def test_serialize_dry_run_failed(good_config, monkeypatch):
    from fleetpy_copilot import generate as gen
    from fleetpy_copilot.dryrun import DryRunResult
    monkeypatch.setattr(gen, "dry_run_tmp",
                        lambda base, cand: DryRunResult(ok=False, error="boom"))
    out = generate_config("x", MockProvider([good_config]), do_dry_run=True)
    assert isinstance(out, DryRunFailed)
    d = service.serialize_outcome(out)
    assert d["type"] == "DryRunFailed"
    assert d["dry_run"]["ok"] is False and "boom" in d["dry_run"]["error"]
    json.dumps(d)


# --- JSON file sink ------------------------------------------------------------

def test_json_file_matches_response_trace(good_config, tmp_path):
    resp = service.handle_generate(
        {"prompt": "ir-only", "do_dry_run": False},
        MockProvider([good_config]),
        trace_dir=str(tmp_path),
    )
    files = list(tmp_path.glob("req-*.json"))
    assert len(files) == 1
    on_disk = json.loads(files[0].read_text())
    assert isinstance(on_disk, list)
    assert [e["step"] for e in on_disk] == [e["step"] for e in resp["trace"]]


# --- core stays importable without the web framework ---------------------------

def test_core_modules_do_not_import_service():
    import fleetpy_copilot.generate as gen
    import fleetpy_copilot.trace as tr
    import fleetpy_copilot.provider as prov
    for mod in (gen, tr, prov):
        src = open(mod.__file__).read()
        assert "import fastapi" not in src
        assert "fleetpy_copilot.service" not in src
        assert "from .service" not in src


def test_importing_core_does_not_load_fastapi():
    # stronger than source grep: importing the core in a fresh subprocess must not
    # pull fastapi/uvicorn into sys.modules (the env-agnostic-core invariant).
    import subprocess
    import sys

    code = (
        "import sys;"
        "import fleetpy_copilot.generate, fleetpy_copilot.trace,"
        " fleetpy_copilot.provider, fleetpy_copilot.providers;"
        "assert 'fastapi' not in sys.modules;"
        "assert 'uvicorn' not in sys.modules;"
        "print('ok')"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout


# --- FastAPI route layer (skip if fastapi/httpx unavailable) -------------------

fastapi_client = pytest.importorskip  # alias for readability


def _test_client(good_config):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    app = service.make_app(MockProvider([good_config]))
    return TestClient(app)


def test_route_health(good_config):
    client = _test_client(good_config)
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_route_generate(good_config):
    client = _test_client(good_config)
    r = client.post("/generate", json={"prompt": "ir-only", "do_dry_run": False})
    assert r.status_code == 200
    body = r.json()
    assert body["outcome"]["type"] == "GeneratedConfig"
    assert body["trace"]


def test_route_missing_prompt_rejected(good_config):
    client = _test_client(good_config)
    r = client.post("/generate", json={"do_dry_run": False})
    assert r.status_code == 422
