"""provider.py — the single swappable LLM seam (M2).

Everything that could be an LLM sits behind one tiny interface: given a natural
-language prompt (and optionally a correction hint from a prior validation), return
a candidate ``{param: value}`` config dict. The orchestration in ``generate.py``
never imports a vendor SDK — it talks only to this ``Provider`` protocol, so a
mock today and a real Claude/GPT adapter later are drop-in interchangeable.

``MockProvider`` is deterministic (no API key, no network): it returns pre-seeded
responses keyed by call order, which is all the orchestration/repair loop needs to
be exercised in tests.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Protocol, runtime_checkable


@dataclass
class GenerationCall:
    """Richer return of one provider call, so the loop can surface the full rendered
    prompt and the raw model reply into the observability trace WITHOUT the provider
    importing ``trace.py``.

    Only ``config`` (the ``{param: value}`` dict) is load-bearing for the pipeline —
    it is exactly what ``generate()`` returns. The prompt/reply fields are optional
    observability extras; a provider that does not implement ``generate_verbose``
    leaves them empty and the loop still works.
    """

    config: Dict[str, object] = field(default_factory=dict)
    system_prompt: str = ""
    user_prompt: str = ""
    raw_reply: Optional[str] = None


@runtime_checkable
class Provider(Protocol):
    """The LLM seam. One method; no vendor types leak through it."""

    def generate(
        self,
        prompt: str,
        *,
        correction: Optional[str] = None,
        schema_hint: Optional[Mapping[str, object]] = None,
    ) -> Dict[str, object]:
        """Return a candidate ``{param: value}`` config dict for ``prompt``.

        ``correction`` carries a validation-failure message from a prior attempt
        (the repair loop); ``schema_hint`` may carry enum/doc context. A real
        adapter would render these into its prompt. Implementations must return a
        plain dict — validation is the caller's job, never the provider's.
        """
        ...

    # OPTIONAL. A provider MAY also implement ``generate_verbose`` to surface the
    # rendered prompts + raw reply into the observability trace. ``generate_config``
    # calls it when present and otherwise falls back to ``generate``. This is purely
    # for observability — the ``config`` it returns is exactly what ``generate`` would.
    # (Declared as an optional method: not all Providers implement it, so it is not
    # part of the runtime-checkable isinstance contract.)


class MockProvider:
    """Deterministic ``Provider`` for tests and offline wiring.

    Seed it with an ordered list of responses; each ``generate`` call pops the
    next one. This lets a test script a sequence like "bad response, then good
    response on retry" to exercise the repair loop without any real model. If the
    list is exhausted, the last response is repeated (so a provider that never
    fixes its output drives the loop to its retry budget deterministically).
    """

    def __init__(self, responses: Optional[List[Mapping[str, object]]] = None):
        self._responses: List[Mapping[str, object]] = list(responses or [{}])
        self.calls: List[Dict[str, object]] = []  # recorded (prompt, correction) per call

    def describe(self) -> Dict[str, object]:
        """Small descriptor for the observability trace."""
        return {"provider": "mock", "model": "mock", "endpoint": "(offline)"}

    def generate(
        self,
        prompt: str,
        *,
        correction: Optional[str] = None,
        schema_hint: Optional[Mapping[str, object]] = None,
    ) -> Dict[str, object]:
        self.calls.append({"prompt": prompt, "correction": correction})
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        return dict(self._responses[idx])

    def generate_verbose(
        self,
        prompt: str,
        *,
        correction: Optional[str] = None,
        schema_hint: Optional[Mapping[str, object]] = None,
    ) -> GenerationCall:
        """Same result as ``generate``, plus observability extras. The mock has no
        real rendered prompt, so it echoes the request/correction and dumps its
        chosen response as the ``raw_reply`` (JSON) so the trace shows something
        concrete offline."""
        config = self.generate(prompt, correction=correction, schema_hint=schema_hint)
        return GenerationCall(
            config=config,
            user_prompt=prompt if not correction else f"{prompt}\n[correction] {correction}",
            raw_reply=json.dumps(config),
        )
