"""providers.py — concrete real-LLM backends + the one-switch factory.

The LLM backend is **config-selected and swappable**: the same ``Provider``
protocol (``provider.py``) is satisfied by several implementations, and
``make_provider()`` picks one from the ``COPILOT_PROVIDER`` environment variable.
Swapping dev ↔ real deployment is one env var, no code change:

    COPILOT_PROVIDER=mock        -> MockProvider          (deterministic, CI/offline)
    COPILOT_PROVIDER=hai         -> OpenAICompatProvider   (local hai dev proxy, no API key)
    COPILOT_PROVIDER=openai      -> OpenAICompatProvider   (api.openai.com, OPENAI_API_KEY)
    COPILOT_PROVIDER=anthropic   -> AnthropicProvider      (api.anthropic.com, ANTHROPIC_API_KEY)

hai and OpenAI share one client because the hai proxy is OpenAI-compatible
(``/v1/chat/completions``); only the base URL + auth differ. Anthropic's Messages
API has a different shape, so it is its own small adapter. All are stdlib-only
(urllib via ``_http``) — no vendor SDK, so the copilot stays env-agnostic.

Every provider returns a plain ``{param: value}`` dict; validation is always the
caller's job (``generate.py`` + ``validate.py``), never the provider's.
"""
from __future__ import annotations

import os
from typing import Dict, Mapping, Optional

from . import _http, _prompting
from .provider import GenerationCall, MockProvider, Provider


class OpenAICompatProvider:
    """A ``Provider`` for any OpenAI-compatible ``/chat/completions`` endpoint.

    Covers both the local ``hai`` proxy (no/opaque key) and OpenAI proper
    (``OPENAI_API_KEY``). ``base_url`` is the endpoint root; the chat path is
    appended. A missing token is allowed (the hai proxy may not need one); a real
    OpenAI call without a key will simply get an auth error surfaced as
    ``ProviderHTTPError``.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        token: str = "",
        chat_path: str = "/v1/chat/completions",
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.token = token
        self.chat_path = chat_path
        self.max_tokens = max_tokens
        self.temperature = temperature

    def describe(self) -> Dict[str, object]:
        """Small, non-secret descriptor for the observability trace (never the token)."""
        return {"provider": "openai-compatible", "model": self.model,
                "endpoint": f"{self.base_url}{self.chat_path}"}

    def generate(
        self,
        prompt: str,
        *,
        correction: Optional[str] = None,
        schema_hint: Optional[Mapping[str, object]] = None,
    ) -> Dict[str, object]:
        return self.generate_verbose(
            prompt, correction=correction, schema_hint=schema_hint
        ).config

    def generate_verbose(
        self,
        prompt: str,
        *,
        correction: Optional[str] = None,
        schema_hint: Optional[Mapping[str, object]] = None,
    ) -> GenerationCall:
        system_prompt = _prompting.build_system_prompt(schema_hint)
        user_prompt = _prompting.build_user_prompt(prompt, correction)
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            # temperature=0 by default for reproducible output. Safe on this path:
            # the OpenAI /chat/completions schema and the hai proxy both accept it
            # (verified). NOT added to AnthropicProvider — the native Messages API
            # rejects temperature with a 400 on current Claude models.
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        data = _http.post_json(f"{self.base_url}{self.chat_path}", body, headers=headers)
        text = data["choices"][0]["message"]["content"]
        return GenerationCall(
            config=_prompting.parse_reply(text),
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            raw_reply=text,
        )


class AnthropicProvider:
    """A ``Provider`` for Anthropic's Messages API (``/v1/messages``).

    Different wire shape from OpenAI: ``x-api-key`` header, ``anthropic-version``,
    a top-level ``system`` field, and content returned as a list of blocks.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "claude-haiku-4-5",
        base_url: str = "https://api.anthropic.com",
        version: str = "2023-06-01",
        max_tokens: int = 1024,
    ):
        if not api_key:
            raise ValueError(
                "AnthropicProvider needs an API key (set ANTHROPIC_API_KEY, "
                "or use COPILOT_PROVIDER=mock)."
            )
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.version = version
        self.max_tokens = max_tokens

    def describe(self) -> Dict[str, object]:
        """Small, non-secret descriptor for the observability trace (never the key)."""
        return {"provider": "anthropic", "model": self.model,
                "endpoint": f"{self.base_url}/v1/messages"}

    def generate(
        self,
        prompt: str,
        *,
        correction: Optional[str] = None,
        schema_hint: Optional[Mapping[str, object]] = None,
    ) -> Dict[str, object]:
        return self.generate_verbose(
            prompt, correction=correction, schema_hint=schema_hint
        ).config

    def generate_verbose(
        self,
        prompt: str,
        *,
        correction: Optional[str] = None,
        schema_hint: Optional[Mapping[str, object]] = None,
    ) -> GenerationCall:
        system_prompt = _prompting.build_system_prompt(schema_hint)
        user_prompt = _prompting.build_user_prompt(prompt, correction)
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.version,
        }
        data = _http.post_json(f"{self.base_url}/v1/messages", body, headers=headers)
        # content is a list of blocks; concatenate the text blocks.
        blocks = data.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict))
        return GenerationCall(
            config=_prompting.parse_reply(text),
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            raw_reply=text,
        )


# --- the one-switch factory ----------------------------------------------------

def _hai_provider() -> OpenAICompatProvider:
    return OpenAICompatProvider(
        base_url=os.environ.get("HAI_BASE_URL", "http://localhost:6655"),
        token=os.environ.get("HAI_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN", ""),
        model=os.environ.get("HAI_MODEL", "claude-haiku-4-5"),
        chat_path="/litellm/v1/chat/completions",
    )


def _openai_provider() -> OpenAICompatProvider:
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise ValueError(
            "COPILOT_PROVIDER=openai needs OPENAI_API_KEY (or use COPILOT_PROVIDER=mock)."
        )
    return OpenAICompatProvider(
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com"),
        token=key,
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
    )


def _anthropic_provider() -> AnthropicProvider:
    return AnthropicProvider(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        model=os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5"),
    )


#: name -> builder. Add a backend here and it is selectable by COPILOT_PROVIDER.
_REGISTRY = {
    "mock": lambda: MockProvider(),
    "hai": _hai_provider,
    "openai": _openai_provider,
    "anthropic": _anthropic_provider,
}


def make_provider(name: Optional[str] = None) -> Provider:
    """Return the ``Provider`` selected by ``name`` (default: ``$COPILOT_PROVIDER``,
    falling back to ``mock``). Raises ``ValueError`` for an unknown name, listing
    the valid choices — a wrong switch fails loudly, never silently falls back."""
    choice = (name or os.environ.get("COPILOT_PROVIDER", "mock")).strip().lower()
    if choice not in _REGISTRY:
        raise ValueError(
            f"unknown COPILOT_PROVIDER {choice!r}; choose one of {sorted(_REGISTRY)}"
        )
    return _REGISTRY[choice]()
