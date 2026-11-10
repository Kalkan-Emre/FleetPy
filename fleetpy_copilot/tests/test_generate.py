"""Tests for the generate.py orchestration loop, driven by MockProvider.

Uses a real solver-free merged config (constant_config_ir / example_ir_only) as
the "known good" response so the happy path also clears the dry-run functional
gate. The repair and slot-filling paths are exercised with minimal hand-built
responses.
"""
import pytest

from fleetpy_copilot import generate, schema
from fleetpy_copilot.generate import (
    DryRunFailed, GeneratedConfig, GenerationFailed, NeedsInput, generate_config,
)
from fleetpy_copilot.provider import MockProvider, Provider
from fleetpy_copilot.tests import _fixtures


@pytest.fixture
def good_config():
    return _fixtures.load_merged("constant_config_ir.csv", "example_ir_only.csv", 0)


# --- happy path ----------------------------------------------------------------

def test_known_good_returns_generated_config(good_config):
    provider = MockProvider([good_config])
    out = generate_config("ir-only on example network", provider, do_dry_run=False)
    assert isinstance(out, GeneratedConfig)
    assert out.validation.ok
    assert out.attempts == 1


def test_known_good_passes_dry_run(good_config):
    provider = MockProvider([good_config])
    out = generate_config("ir-only on example network", provider, do_dry_run=True)
    assert isinstance(out, GeneratedConfig)
    assert out.dry_run is not None and out.dry_run.ok, (
        None if out.dry_run is None else out.dry_run.error
    )


# --- ask, don't infer ----------------------------------------------------------

def test_missing_mandatory_returns_needs_input(good_config):
    # drop a mandatory param -> must be asked for, not inferred
    broken = dict(good_config)
    broken.pop("sim_env")
    provider = MockProvider([broken])
    out = generate_config("under-specified request", provider, do_dry_run=False)
    assert isinstance(out, NeedsInput)
    assert any(s.name == "sim_env" for s in out.slots)
    # module-selecting slot carries its enum so the caller can offer choices
    sim_env_slot = next(s for s in out.slots if s.name == "sim_env")
    assert sim_env_slot.valid_values == schema.valid_values_for("sim_env")


def test_needs_input_surfaces_other_errors(good_config):
    # BOTH missing mandatory AND a bad value -> NeedsInput, but the bad value must
    # be surfaced in other_errors (not silently hidden until slots are filled).
    broken = dict(good_config)
    broken.pop("sim_env")          # missing mandatory
    broken["time_step"] = 0        # value error
    broken["op_module"] = "Nope"   # invalid module value
    out = generate_config("mixed problems", MockProvider([broken]), do_dry_run=False)
    assert isinstance(out, NeedsInput)
    assert "time_step" in out.other_errors
    assert "op_module" in out.other_errors


# --- repair loop ---------------------------------------------------------------

def test_repair_converges_on_retry(good_config):
    bad = dict(good_config)
    bad["op_module"] = "NotARealFleetControl"   # invalid module value
    provider = MockProvider([bad, good_config])  # fixes itself on 2nd call
    out = generate_config("fix me", provider, max_repairs=2, do_dry_run=False)
    assert isinstance(out, GeneratedConfig)
    assert out.attempts == 2
    # the 2nd call received a correction message naming the valid enum
    second_correction = provider.calls[1]["correction"]
    assert second_correction is not None
    assert "op_module" in second_correction


def test_repair_budget_exhausted_returns_failure(good_config):
    bad = dict(good_config)
    bad["op_module"] = "StillWrong"
    provider = MockProvider([bad])  # never fixes -> repeats the bad response
    out = generate_config("never fixed", provider, max_repairs=2, do_dry_run=False)
    assert isinstance(out, GenerationFailed)
    assert out.attempts == 3  # 1 initial + 2 repairs
    assert "op_module" in out.validation.invalid_module_values


def test_default_repair_cap_is_two_calls(good_config):
    # M2.1: the DEFAULT max_repairs is 1, so a never-fixing provider must make
    # exactly TWO provider calls (1 initial + 1 repair) before GenerationFailed.
    # This pins the default (the test above passes max_repairs explicitly).
    bad = dict(good_config)
    bad["op_module"] = "StillWrong"
    provider = MockProvider([bad])
    out = generate_config("never fixed", provider, do_dry_run=False)  # no max_repairs
    assert isinstance(out, GenerationFailed)
    assert out.attempts == 2
    assert len(provider.calls) == 2


def test_missing_mandatory_makes_exactly_one_call(good_config):
    # Under-specification must short-circuit with NO repair re-ask.
    broken = dict(good_config)
    broken.pop("sim_env")
    provider = MockProvider([broken])
    out = generate_config("under-specified", provider, do_dry_run=False)
    assert isinstance(out, NeedsInput)
    assert len(provider.calls) == 1


# --- value-error (Part A) drives repair, not a crash ---------------------------

def test_value_error_routes_to_repair(good_config):
    bad = dict(good_config)
    bad["time_step"] = 0          # Part A value check -> not ok, not missing-mandatory
    provider = MockProvider([bad, good_config])
    out = generate_config("bad timestep", provider, max_repairs=1, do_dry_run=False)
    assert isinstance(out, GeneratedConfig)
    assert out.attempts == 2
    assert "time_step" in provider.calls[1]["correction"]


# --- constant merge order ------------------------------------------------------

def test_constant_merged_under_candidate():
    # constant provides a base; provider's dict overrides on conflict
    provider = MockProvider([{"end_time": 3600}])
    out = generate_config(
        "x", provider, constant={"end_time": 7200, "start_time": 0}, do_dry_run=False
    )
    # not asserting ok (sparse config); just that the merge/override happened
    cand = out.candidate if isinstance(out, NeedsInput) else (
        out.config if isinstance(out, GeneratedConfig) else out.candidate
    )
    assert cand["end_time"] == 3600   # candidate overrides constant
    assert cand["start_time"] == 0    # constant-only key preserved


# --- dry-run gating (behavior fix) ---------------------------------------------

def test_dry_run_failure_returns_dry_run_failed(good_config, monkeypatch):
    # a config can validate clean yet fail FleetPy init. The loop must surface that
    # as DryRunFailed, NOT a GeneratedConfig carrying a failed dry_run in the field.
    from fleetpy_copilot import generate as gen
    from fleetpy_copilot.dryrun import DryRunResult

    monkeypatch.setattr(
        gen, "dry_run_tmp",
        lambda base, cand: DryRunResult(ok=False, error="SimulatedInitError: boom"),
    )
    out = generate_config("x", MockProvider([good_config]), do_dry_run=True)
    assert isinstance(out, DryRunFailed)
    assert out.validation.ok            # validation passed...
    assert not out.dry_run.ok           # ...but the functional gate did not
    assert "boom" in out.dry_run.error


def test_generated_config_dry_run_is_always_ok_when_present(good_config, monkeypatch):
    # the invariant: a GeneratedConfig with a non-None dry_run always has dry_run.ok
    from fleetpy_copilot import generate as gen
    from fleetpy_copilot.dryrun import DryRunResult

    monkeypatch.setattr(gen, "dry_run_tmp", lambda base, cand: DryRunResult(ok=True))
    out = generate_config("x", MockProvider([good_config]), do_dry_run=True)
    assert isinstance(out, GeneratedConfig)
    assert out.dry_run is not None and out.dry_run.ok


# --- provider contract hardening -----------------------------------------------

class _BadProvider:
    """A provider that returns a non-dict (hostile/buggy adapter)."""
    def generate(self, prompt, *, correction=None, schema_hint=None):
        return ["not", "a", "dict"]


class _RaisingProvider:
    def generate(self, prompt, *, correction=None, schema_hint=None):
        raise RuntimeError("upstream API down")


def test_non_dict_provider_raises_typeerror():
    with pytest.raises(TypeError, match="must return a dict"):
        generate_config("x", _BadProvider(), do_dry_run=False)


def test_raising_provider_propagates():
    # a provider exception is not swallowed (caller must see the upstream failure)
    with pytest.raises(RuntimeError, match="upstream API down"):
        generate_config("x", _RaisingProvider(), do_dry_run=False)


def test_mockprovider_satisfies_protocol():
    assert isinstance(MockProvider([{}]), Provider)
