"""Model discovery for custom-endpoint providers.

When an operator points a provider at a custom `api_base` (self-hosted
gateway, regional mirror, OpenAI-compatible third party), we have no
`litellm.model_cost` entry for it and therefore no model list. Rather than
making them hand-maintain a model list — or worse, edit code — we ask the
endpoint itself: `GET {api_base}/models`.

Two properties matter more than cleverness here:

1. **Discovery must never break routing.** It runs on the router-build path,
   where an exception would turn "provider temporarily unreachable" into a
   503 for every model, including the ones that were already working. So
   every failure (DNS, timeout, 401, HTML error page, empty list) degrades to
   `[]` plus a warning — the router still boots, other providers still route.

2. **No key material in cache keys.** Results are cached per
   (provider, base_url) — never per key — so key rotation doesn't leak
   anything through the cache and doesn't need a flush.

The response parsing is deliberately permissive: `/models` is the one endpoint
every OpenAI-compatible gateway implements, but the *envelope* varies. We
reuse `orcarouter_models._extract_ids`, which already tolerates the shapes we
see in the wild.
"""

from __future__ import annotations

import time

import httpx
import structlog

# Private-ish import on purpose: the parser there already handles the eight
# response shapes we've hit in production ({"data": [...]}, bare lists,
# {"models": [...]}, name/model_id alternates, ...). Duplicating it would
# guarantee the two callers drift apart.
from app.orcarouter_models import _extract_ids

logger = structlog.get_logger()

_CACHE_TTL_SECONDS = 60 * 60  # 1 hour
_FETCH_TIMEOUT_SECONDS = 5.0

# Process-wide cache keyed by (provider, base_url).
_cache: dict[tuple[str, str], tuple[float, list[str]]] = {}


def _models_url(base_url: str) -> str:
    """`https://x.ai/v1` → `https://x.ai/v1/models`.

    Tolerates a trailing slash and a base with no version segment at all
    (`https://x.ai` -> `https://x.ai/models`) — both are common, and emitting
    a double slash (`/v1//models`) makes some gateways 404.
    """
    return f"{base_url.rstrip('/')}/models"


async def fetch_models(*, base_url: str, api_key: str) -> list[str]:
    """Fetch model IDs from an OpenAI-compatible endpoint. Raises on failure.

    Callers that want "never break routing" semantics should use
    `discover_provider_models` instead, which wraps this in a cache + a
    catch-all.

    Redirects are followed: gateways routinely canonicalize `host` →
    `host/` or `/v1` → `/v1/`, and `httpx` raises on 3xx by default — an
    endpoint that is perfectly healthy would look dead.
    """
    url = _models_url(base_url)
    async with httpx.AsyncClient(
        timeout=_FETCH_TIMEOUT_SECONDS, follow_redirects=True
    ) as client:
        resp = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )
        resp.raise_for_status()
        ids = _extract_ids(_parse_json(resp.text))
    # Deterministic + deduped: the deployment list is compared by tests and
    # an unstable order would rebuild an identical router on every restart.
    return sorted({i for i in ids if i})


def _parse_json(text: str):
    try:
        import json

        return json.loads(text or "")
    except Exception:
        return []


async def discover_provider_models(
    *, provider: str, base_url: str, api_key: str, force_refresh: bool = False
) -> list[str]:
    """Cached, failure-tolerant model discovery for one custom endpoint.

    Returns [] on any error so the router can still be built with every other
    provider intact. An operator whose gateway is down gets "this provider
    serves nothing right now" rather than "nothing works".
    """
    key = (provider, base_url)
    now = time.monotonic()

    if not force_refresh:
        cached = _cache.get(key)
        if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1]

    try:
        ids = await fetch_models(base_url=base_url, api_key=api_key)
        if not ids:
            raise ValueError("empty model list from endpoint")
    except Exception as exc:
        logger.warning(
            "custom_provider_model_discovery_failed",
            provider=provider,
            base_url=base_url,
            error=str(exc),
        )
        # Cache the negative result too: a dead endpoint would otherwise be
        # re-probed on every router rebuild, adding its full timeout to the
        # first request after each invalidation.
        _cache[key] = (time.monotonic(), [])
        return []

    _cache[key] = (time.monotonic(), ids)
    logger.info(
        "custom_provider_models_discovered",
        provider=provider,
        base_url=base_url,
        model_count=len(ids),
    )
    return ids


def prime_cache(provider: str, base_url: str, ids: list[str]) -> None:
    """Store a discovery result we already fetched, without re-requesting.

    Used by the explicit refresh endpoint, which fetches through
    `fetch_models` (so it can report *why* a gateway failed) and then wants
    the router build to reuse that answer instead of asking again.
    """
    _cache[(provider, base_url)] = (time.monotonic(), list(ids))


def reset_cache() -> None:
    """Test hook — wipe the in-process discovery cache."""
    _cache.clear()
