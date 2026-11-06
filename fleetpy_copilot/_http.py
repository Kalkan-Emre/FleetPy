"""_http.py — tiny stdlib HTTP helper for the real LLM providers.

Stdlib only (``urllib``), no vendor SDK, so the copilot stays env-agnostic (runs
under both conda and pip with nothing extra to install). Both the OpenAI-compatible
path (OpenAI proper and the local ``hai`` proxy) and the Anthropic Messages path
are plain JSON POSTs; this module owns the request/parse/error plumbing so each
provider is just "build body, read reply".
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict, Mapping, Optional

DEFAULT_TIMEOUT_S = 60


class ProviderHTTPError(RuntimeError):
    """A provider's HTTP call failed (non-2xx, unreachable, or timeout).

    Carries a human-readable message; the orchestration layer lets it propagate
    (a transport failure is not a model mistake to repair)."""


def post_json(
    url: str,
    body: Mapping[str, object],
    *,
    headers: Optional[Mapping[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT_S,
) -> Dict[str, object]:
    """POST ``body`` as JSON to ``url`` and return the parsed JSON response.

    Raises :class:`ProviderHTTPError` on any transport/HTTP failure, with the
    response body included when the server sent one (API errors are usually in it).
    """
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")
        except Exception:  # pragma: no cover - best-effort error body
            pass
        raise ProviderHTTPError(f"HTTP {exc.code} {exc.reason}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ProviderHTTPError(f"cannot reach {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ProviderHTTPError(f"request to {url} timed out after {timeout}s") from exc
