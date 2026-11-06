#!/usr/bin/env python3
"""hai_smoke.py — a tiny client + smoke test for the Hyperspace LLM Proxy.

Proves the local proxy (default ``http://localhost:6655``, served by the `hai` CLI
or the Hyperspace Desktop App) is reachable, the auth token works, and the model
answers — by making one real chat call and printing the reply. Internal proxies
have auth/model-name/path quirks that only surface at runtime, so this does a live
round-trip rather than merely constructing a client.

Stdlib only (``urllib``) — no ``openai``/``anthropic`` SDK — to stay within the
copilot's env-agnostic constraint (runs under both conda and pip).

Config comes from the environment with sensible fallbacks:
    HAI_BASE_URL      base URL             (default http://localhost:6655)
    HAI_API_KEY       bearer token         (falls back to ANTHROPIC_AUTH_TOKEN)
    HAI_MODEL         model id             (default claude-haiku-4-5; argv[1] wins)

Usage:
    python fleetpy_copilot/hai_smoke.py
    python fleetpy_copilot/hai_smoke.py claude-sonnet-4-6
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Optional

DEFAULT_BASE_URL = "http://localhost:6655"
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_PROMPT = "Reply with exactly: HAI OK"
TIMEOUT_S = 30


def chat(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    token: str = "",
    max_tokens: int = 64,
    timeout: int = TIMEOUT_S,
) -> dict:
    """Send one chat request to the proxy's OpenAI-compatible LiteLLM endpoint.

    Returns the parsed JSON response dict. Raises urllib errors on failure; the
    caller is responsible for turning those into a friendly message.
    """
    url = f"{base_url.rstrip('/')}/litellm/v1/chat/completions"
    body = json.dumps(
        {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (local proxy)
        return json.loads(resp.read().decode("utf-8"))


def _reply_text(data: dict) -> Optional[str]:
    """Pull the assistant text out of an OpenAI-shaped chat response."""
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None


def main(argv: Optional[list] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    base_url = os.environ.get("HAI_BASE_URL", DEFAULT_BASE_URL)
    token = os.environ.get("HAI_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    model = (argv[0] if argv else "") or os.environ.get("HAI_MODEL", DEFAULT_MODEL)

    print(f"hai smoke test -> {base_url}/litellm/v1/chat/completions")
    print(f"  model: {model}")
    print(f"  auth : {'present' if token else 'MISSING (no HAI_API_KEY / ANTHROPIC_AUTH_TOKEN)'}")

    try:
        data = chat(DEFAULT_PROMPT, model=model, base_url=base_url, token=token)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")
        except Exception:  # pragma: no cover - best-effort error body
            pass
        print(f"\nFAIL: HTTP {e.code} {e.reason}\n{detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(
            f"\nFAIL: cannot reach proxy at {base_url} ({e.reason}).\n"
            "Is the hai proxy / Hyperspace Desktop App running?",
            file=sys.stderr,
        )
        return 1
    except TimeoutError:
        print(f"\nFAIL: request timed out after {TIMEOUT_S}s.", file=sys.stderr)
        return 1

    reply = _reply_text(data)
    if reply is None:
        print(f"\nFAIL: unexpected response shape:\n{json.dumps(data, indent=2)}", file=sys.stderr)
        return 1

    usage = data.get("usage") or {}
    print("\nOK — proxy answered.")
    print(f"  served model: {data.get('model', '?')}")
    print(f"  reply       : {reply!r}")
    if usage:
        print(
            "  tokens      : "
            f"prompt={usage.get('prompt_tokens', '?')} "
            f"completion={usage.get('completion_tokens', '?')} "
            f"total={usage.get('total_tokens', '?')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
