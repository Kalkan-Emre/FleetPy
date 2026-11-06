"""Tests for the swappable real-provider layer: reply parsing, the prompt builder,
the factory switch, and skip-if-unavailable contract tests for the live backends.

The factory + parsing are covered deterministically with NO network. Live backends
(hai proxy / Anthropic / OpenAI) are only exercised when actually reachable, so the
suite stays green on every machine and in CI.
"""
import os

import pytest

from fleetpy_copilot import _prompting, providers
from fleetpy_copilot.provider import MockProvider, Provider
from fleetpy_copilot.providers import (
    AnthropicProvider, OpenAICompatProvider, make_provider,
)


# --- reply parsing -------------------------------------------------------------

def test_parse_plain_json():
    assert _prompting.parse_reply('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_parse_fenced_json():
    assert _prompting.parse_reply('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_with_surrounding_prose():
    text = 'Here is your config:\n{"sim_env": "X"}\nHope that helps!'
    assert _prompting.parse_reply(text) == {"sim_env": "X"}


def test_parse_rejects_non_object():
    with pytest.raises(ValueError):
        _prompting.parse_reply("[1, 2, 3]")


def test_parse_rejects_garbage():
    with pytest.raises(ValueError):
        _prompting.parse_reply("no json here at all")


# --- prompt builder ------------------------------------------------------------

def test_system_prompt_mentions_module_enums():
    sp = _prompting.build_system_prompt()
    assert "op_module" in sp and "sim_env" in sp  # enums are grounded


def test_system_prompt_override():
    assert _prompting.build_system_prompt({"text": "CUSTOM"}) == "CUSTOM"


def test_user_prompt_includes_correction():
    up = _prompting.build_user_prompt("make an IR scenario", correction="bad op_module")
    assert "make an IR scenario" in up and "bad op_module" in up


# --- factory switch ------------------------------------------------------------

def test_factory_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("COPILOT_PROVIDER", raising=False)
    assert isinstance(make_provider(), MockProvider)


def test_factory_mock_explicit():
    assert isinstance(make_provider("mock"), MockProvider)


def test_factory_hai_builds_openai_compat(monkeypatch):
    monkeypatch.setenv("HAI_BASE_URL", "http://localhost:6655")
    p = make_provider("hai")
    assert isinstance(p, OpenAICompatProvider)
    assert p.chat_path == "/litellm/v1/chat/completions"


def test_factory_anthropic_requires_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError):
        make_provider("anthropic")


def test_factory_openai_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        make_provider("openai")


def test_factory_unknown_name_fails_loudly():
    with pytest.raises(ValueError) as exc:
        make_provider("gemini")
    assert "gemini" in str(exc.value)


def test_factory_reads_env(monkeypatch):
    monkeypatch.setenv("COPILOT_PROVIDER", "mock")
    assert isinstance(make_provider(), MockProvider)


def test_all_providers_satisfy_protocol():
    # structural check: the mock and a constructed anthropic both are Providers
    assert isinstance(MockProvider(), Provider)
    assert isinstance(AnthropicProvider(api_key="dummy"), Provider)
    assert isinstance(
        OpenAICompatProvider(base_url="http://x", model="m"), Provider
    )


# --- live contract tests (skip unless reachable) -------------------------------

def _hai_reachable() -> bool:
    import urllib.error
    import urllib.request
    base = os.environ.get("HAI_BASE_URL", "http://localhost:6655")
    try:
        urllib.request.urlopen(base, timeout=2)
        return True
    except urllib.error.HTTPError:
        return True  # reachable, just not a 200 on /
    except Exception:
        return False


@pytest.mark.skipif(not _hai_reachable(), reason="hai proxy not reachable")
def test_hai_live_roundtrip():
    p = make_provider("hai")
    out = p.generate(
        "Return a JSON object with one key sim_env set to ImmediateDecisionsSimulation."
    )
    assert isinstance(out, dict)


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="no ANTHROPIC_API_KEY")
def test_anthropic_live_roundtrip():
    p = make_provider("anthropic")
    out = p.generate("Return a JSON object: {\"sim_env\": \"ImmediateDecisionsSimulation\"}")
    assert isinstance(out, dict)


@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="no OPENAI_API_KEY")
def test_openai_live_roundtrip():
    p = make_provider("openai")
    out = p.generate("Return a JSON object: {\"sim_env\": \"ImmediateDecisionsSimulation\"}")
    assert isinstance(out, dict)
