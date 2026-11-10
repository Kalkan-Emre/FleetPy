"""Tests for the observability seam (trace.py) and its wiring into generate_config.

These assert the STEP TRACE, not the pipeline behavior (that is test_generate.py's
job). We use a CollectingTracer to capture events and assert the sequence + key
payload fields for every outcome path, reusing the same MockProvider fixtures.
"""
import io

import pytest

from fleetpy_copilot import schema
from fleetpy_copilot.generate import generate_config
from fleetpy_copilot.provider import MockProvider
from fleetpy_copilot.tests import _fixtures
from fleetpy_copilot.trace import (
    NULL_TRACER,
    CollectingTracer,
    CompositeTracer,
    ConsoleTracer,
    Event,
    Tracer,
)


@pytest.fixture
def good_config():
    return _fixtures.load_merged("constant_config_ir.csv", "example_ir_only.csv", 0)


def _steps(tracer: CollectingTracer):
    return [e.step for e in tracer.events]


def _first(tracer: CollectingTracer, step: str) -> Event:
    return next(e for e in tracer.events if e.step == step)


# --- seam basics ---------------------------------------------------------------

def test_collecting_tracer_satisfies_protocol():
    assert isinstance(CollectingTracer(), Tracer)
    assert isinstance(NULL_TRACER, Tracer)


def test_span_stamps_nesting_path():
    t = CollectingTracer()
    with t.span("request"):
        with t.span("generate"):
            t.emit("validate", ok=True)
    assert t.events[0].span == ("request", "generate")


def test_seq_is_monotonic():
    t = CollectingTracer()
    for i in range(4):
        t.emit("x", n=i)
    assert [e.seq for e in t.events] == [0, 1, 2, 3]


def test_emit_site_does_not_name_parent_span():
    # the emit call passes only its own step; the tracer supplies the path
    t = CollectingTracer()
    with t.span("generate"):
        t.emit("attempt", attempt=1)
    ev = t.events[0]
    assert ev.step == "attempt" and ev.span == ("generate",)


def test_span_balanced_on_exception():
    t = CollectingTracer()
    with pytest.raises(RuntimeError):
        with t.span("generate"):
            t.emit("attempt", attempt=1)
            raise RuntimeError("boom")
    # stack popped on unwind -> a subsequent emit is at top level, well-formed
    t.emit("after")
    assert t.events[0].span == ("generate",)
    assert t.events[1].span == ()


# --- happy path trace ----------------------------------------------------------

def test_good_path_emits_expected_steps(good_config):
    t = CollectingTracer()
    out = generate_config("ir-only", MockProvider([good_config]), do_dry_run=False, tracer=t)
    steps = _steps(t)
    assert steps == ["attempt", "provider_request", "llm_call", "merge", "validate", "outcome"]
    assert _first(t, "validate").payload["ok"] is True
    oc = _first(t, "outcome")
    assert oc.payload["type"] == "GeneratedConfig"
    assert oc.payload["attempts"] == out.attempts == 1
    # every event under generate() carries the generate span
    assert all(e.span == ("generate",) for e in t.events)


def test_good_path_dry_run_emits_dry_run_step(good_config):
    t = CollectingTracer()
    generate_config("ir-only", MockProvider([good_config]), do_dry_run=True, tracer=t)
    assert "dry_run" in _steps(t)
    assert _first(t, "dry_run").payload["ok"] is True


# --- needs-input trace ---------------------------------------------------------

def test_needs_input_emits_needs_input_then_outcome(good_config):
    broken = dict(good_config)
    broken.pop("sim_env")
    t = CollectingTracer()
    generate_config("under-specified", MockProvider([broken]), do_dry_run=False, tracer=t)
    steps = _steps(t)
    assert "needs_input" in steps
    assert "repair" not in steps  # ask, don't retry
    assert "sim_env" in _first(t, "needs_input").payload["slots"]
    assert _first(t, "outcome").payload["type"] == "NeedsInput"


# --- repair trace --------------------------------------------------------------

def test_repair_converges_trace(good_config):
    bad = dict(good_config)
    bad["op_module"] = "NotReal"
    t = CollectingTracer()
    generate_config("fix me", MockProvider([bad, good_config]),
                    max_repairs=2, do_dry_run=False, tracer=t)
    steps = _steps(t)
    # attempt1 -> validate(fail) -> repair -> attempt2 -> validate(ok) -> outcome
    assert steps.count("attempt") == 2
    assert steps.count("repair") == 1
    assert "op_module" in _first(t, "repair").payload["correction"]
    assert _first(t, "outcome").payload["type"] == "GeneratedConfig"


def test_repair_exhausted_trace(good_config):
    bad = dict(good_config)
    bad["op_module"] = "StillWrong"
    t = CollectingTracer()
    generate_config("never fixed", MockProvider([bad]),
                    max_repairs=2, do_dry_run=False, tracer=t)
    steps = _steps(t)
    assert steps.count("attempt") == 3
    assert steps[-1] == "outcome"
    assert _first(t, "outcome").payload["type"] == "GenerationFailed"


def test_dry_run_failed_trace(good_config, monkeypatch):
    from fleetpy_copilot import generate as gen
    from fleetpy_copilot.dryrun import DryRunResult
    monkeypatch.setattr(gen, "dry_run_tmp",
                        lambda base, cand: DryRunResult(ok=False, error="boom"))
    t = CollectingTracer()
    generate_config("x", MockProvider([good_config]), do_dry_run=True, tracer=t)
    assert _first(t, "dry_run").payload["ok"] is False
    assert _first(t, "outcome").payload["type"] == "DryRunFailed"


# --- instrumentation is observational only -------------------------------------

def test_null_tracer_vs_collecting_same_outcome(good_config):
    bad = dict(good_config)
    bad["op_module"] = "NotReal"
    o1 = generate_config("fix", MockProvider([bad, good_config]),
                         max_repairs=2, do_dry_run=False, tracer=NULL_TRACER)
    o2 = generate_config("fix", MockProvider([bad, good_config]),
                         max_repairs=2, do_dry_run=False, tracer=CollectingTracer())
    assert type(o1) is type(o2)
    assert o1.config == o2.config and o1.attempts == o2.attempts


def test_outcome_event_on_every_return_path(good_config):
    # each terminal path emits exactly one outcome event
    broken = dict(good_config); broken.pop("sim_env")
    bad = dict(good_config); bad["op_module"] = "Nope"
    cases = [
        (MockProvider([good_config]), {}),                      # GeneratedConfig
        (MockProvider([broken]), {}),                           # NeedsInput
        (MockProvider([bad]), {"max_repairs": 1}),              # GenerationFailed
    ]
    for provider, kw in cases:
        t = CollectingTracer()
        generate_config("x", provider, do_dry_run=False, tracer=t, **kw)
        assert _steps(t).count("outcome") == 1


# --- renderers -----------------------------------------------------------------

def test_console_tracer_writes_indented(good_config):
    buf = io.StringIO()
    t = ConsoleTracer(stream=buf)
    with t.span("request"):
        with t.span("generate"):
            t.emit("validate", ok=True, message="valid")
    out = buf.getvalue()
    assert "validate" in out
    assert out.startswith("    ")  # two spans deep -> 4-space indent


def test_composite_fans_out(good_config):
    collect = CollectingTracer()
    buf = io.StringIO()
    comp = CompositeTracer([ConsoleTracer(stream=buf), collect])
    generate_config("ir", MockProvider([good_config]), do_dry_run=False, tracer=comp)
    assert len(collect.events) > 0          # collected
    assert "outcome" in buf.getvalue()      # and rendered to console
    # composite preserves span path for children
    assert collect.events[0].span == ("generate",)


# --- trace is the only narration -----------------------------------------------

def test_no_print_in_generate_source():
    import fleetpy_copilot.generate as gen
    src = open(gen.__file__).read()
    assert "print(" not in src


# --- full prompt + raw reply into the trace (step 3) ---------------------------

def test_llm_call_carries_full_prompt_and_reply_with_verbose_mock(good_config):
    # MockProvider.generate_verbose fills user_prompt + raw_reply
    t = CollectingTracer()
    generate_config("ir-only here", MockProvider([good_config]), do_dry_run=False, tracer=t)
    llm = _first(t, "llm_call")
    assert "ir-only here" in llm.payload["user_prompt"]
    assert llm.payload["raw_reply"]  # json dump of the chosen response
    assert "sim_env" in llm.payload["raw_reply"]


class _PlainProvider:
    """A Provider with only generate() — no generate_verbose. The loop must fall
    back gracefully (empty prompt fields, no crash)."""

    def __init__(self, response):
        self._r = dict(response)

    def generate(self, prompt, *, correction=None, schema_hint=None):
        return dict(self._r)


def test_llm_call_graceful_fallback_without_verbose(good_config):
    t = CollectingTracer()
    out = generate_config("x", _PlainProvider(good_config), do_dry_run=False, tracer=t)
    llm = _first(t, "llm_call")
    # no verbose method -> empty prompt fields, raw_reply None, but candidate_keys present
    assert llm.payload["system_prompt"] == ""
    assert llm.payload["user_prompt"] == ""
    assert llm.payload["raw_reply"] is None
    assert llm.payload["candidate_keys"]  # the loop still saw the config
    # and the outcome is unaffected
    assert _first(t, "outcome").payload["type"] == "GeneratedConfig"


def test_verbose_and_plain_produce_same_outcome(good_config):
    o_plain = generate_config("x", _PlainProvider(good_config), do_dry_run=False)
    o_verbose = generate_config("x", MockProvider([good_config]), do_dry_run=False)
    assert type(o_plain) is type(o_verbose)
    assert o_plain.config == o_verbose.config


# --- richer live-call visibility (provider_request / timing / error) -----------

def test_provider_request_emitted_before_llm_call(good_config):
    t = CollectingTracer()
    generate_config("x", MockProvider([good_config]), do_dry_run=False, tracer=t)
    steps = _steps(t)
    assert steps.index("provider_request") < steps.index("llm_call")
    pr = _first(t, "provider_request")
    assert pr.payload["provider"] == "mock"
    assert "model" in pr.payload and "endpoint" in pr.payload


def test_llm_call_carries_latency(good_config):
    t = CollectingTracer()
    generate_config("x", MockProvider([good_config]), do_dry_run=False, tracer=t)
    assert "elapsed_ms" in _first(t, "llm_call").payload


class _RaisingProvider:
    def generate(self, prompt, *, correction=None, schema_hint=None):
        raise RuntimeError("upstream API down")


def test_provider_error_event_then_reraise():
    t = CollectingTracer()
    with pytest.raises(RuntimeError, match="upstream API down"):
        generate_config("x", _RaisingProvider(), do_dry_run=False, tracer=t)
    steps = _steps(t)
    assert "provider_error" in steps
    assert "upstream API down" in _first(t, "provider_error").payload["error"]
    # a terminal outcome event is still emitted on the error path
    assert _first(t, "outcome").payload["type"] == "ProviderError"


def test_provider_descriptor_has_no_secret():
    # describe() must never leak the token/key
    from fleetpy_copilot.providers import OpenAICompatProvider
    p = OpenAICompatProvider(base_url="http://x", model="m", token="SECRET")
    d = p.describe()
    assert "SECRET" not in str(d)
