"""Registry + adapters for the aggregated web search / fetch surface.

Two tiers, both free, with very different failure modes:

  * ``keyless`` — Exa, Parallel, Firecrawl, Keenable. No credential at all;
    they answer anonymous requests. Unmetered but aggressively rate limited,
    so a burst of traffic gets 429s and has to cascade.
  * ``quota``   — Tavily, TinyFish. Free monthly allowance behind an API key.
    Metered and reliable, but the allowance expires at month end whether or
    not it was used.

The point of aggregating them is that the two tiers complement each other:
the `quota` strategy spends the metered allowance first (it would otherwise
expire untouched) while the keyless vendors absorb overflow.

Every adapter returns the SAME normalized shapes so callers never branch on
provider:

  search → ``{"title", "url", "snippet", "score"}`` (score may be None)
  fetch  → ``{"url", "title", "content", "error"}`` (error is "" on success)

Every adapter shares ONE signature so the engine can call them uniformly —
keyless vendors simply ignore ``api_key``:

  search: ``async fn(client, query, *, api_key, max_results, params, timeout)``
  fetch:  ``async fn(client, urls,  *, api_key, params, timeout)``

``timeout`` is seconds, already clamped to the remaining chain budget;
adapters must hand it to httpx rather than inventing their own.

Adapters raise :class:`ProviderError`; ``throttled=True`` additionally puts
the provider on cooldown (rate limits / quota exhaustion). Every upstream
failure triggers failover to the next provider: caller-caused problems are
rejected before the chain starts (empty query, unsafe URL, bad `params`), so
whatever reaches an adapter is vendor-specific — a bad key, an outage, a
payload quirk — and another vendor may well answer it. The chain budget caps
how long a fully-down cascade can run.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

import httpx

# Vendor endpoints ----------------------------------------------------------
EXA_MCP_URL = "https://mcp.exa.ai/mcp"
PARALLEL_MCP_URL = "https://search.parallel.ai/mcp"
FIRECRAWL_API_URL = "https://api.firecrawl.dev"
KEENABLE_API_URL = "https://api.keenable.ai"
TAVILY_API_URL = "https://api.tavily.com"
TINYFISH_SEARCH_URL = "https://api.search.tinyfish.ai/"
TINYFISH_FETCH_URL = "https://api.fetch.tinyfish.ai/"

# Keenable requires an app-title header; it identifies the calling app for
# their public-endpoint rate limiting. Not a secret.
_KEENABLE_TITLE = "orcarouter-lite"

# Random per process: Parallel correlates requests for rate limiting, and a
# stable id would make one Lite install look like a single heavy client.
_SESSION_ID = uuid.uuid4().hex

_USER_AGENT = "orcarouter-lite"

# Free-tier throttling shows up as a grab-bag of wordings across vendors
# (some 429, some 200 with an error body), so it's matched by text.
_RATE_LIMIT_MARKERS = (
    "rate limit", "rate-limit", "ratelimit", "too many requests",
    "429", "quota exceeded", "slow down", "usage limit", "credits",
)

# Hard cap on how much page content one fetch may return. Pages are passed
# straight back to the caller and, for the LLM use case, straight into a
# prompt — an unbounded body is both a memory and a cost problem.
MAX_CONTENT_CHARS = 200_000


class ProviderError(RuntimeError):
    """An upstream network call failed.

    ``throttled`` marks the cases where trying the next provider is the right
    move (rate limit, exhausted free-tier credits). Everything else — bad
    query, malformed payload — would fail identically everywhere, so the
    engine aborts instead of burning every provider's quota on it.
    """

    def __init__(self, message: str, *, throttled: bool = False) -> None:
        super().__init__(message)
        self.throttled = throttled


class ProviderParamError(ValueError):
    """Caller-supplied `params` failed validation against the provider spec."""


def is_throttled(message: str) -> bool:
    lowered = (message or "").lower()
    return any(marker in lowered for marker in _RATE_LIMIT_MARKERS)


# ── Parameter metadata ────────────────────────────────────────────────────
@dataclass(frozen=True)
class ParamSpec:
    """One provider-specific parameter, published by the listing endpoint so
    the dashboard can render a form without hardcoding any vendor.

    `type` is restricted to four literals — the frontend switches on them and
    anything fancier (nested objects, arrays of objects) can't be rendered by
    the simple form builder and isn't needed by any vendor here.
    """

    name: str
    type: str  # "string" | "int" | "bool" | "enum"
    default: Any = None
    required: bool = False
    enum: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    description: str = ""

    def to_dict(self) -> dict:
        out: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "default": self.default,
            "required": self.required,
            "description": self.description,
        }
        if self.enum:
            out["enum"] = list(self.enum)
        if self.minimum is not None:
            out["min"] = self.minimum
        if self.maximum is not None:
            out["max"] = self.maximum
        return out


@dataclass(frozen=True)
class RateLimit:
    """One published free-tier rate limit, per operation.

    Informational (surfaced by the listing endpoint so the operator can see
    why a vendor throttles); enforcement is the vendor's job — when it does
    429, the engine's cooldown takes over. `per` is one of
    minute/hour/day/month so the dashboard can label it without parsing text.
    """

    operation: str  # "search" | "fetch"
    per: str
    limit: int

    def to_dict(self) -> dict:
        return {"operation": self.operation, "per": self.per, "limit": self.limit}


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    tier: str  # "keyless" | "quota"
    capabilities: frozenset[str]  # {"search"} and/or {"fetch"}
    docs_url: str
    requires_key: bool = False
    # Key is accepted but not needed — sending one raises the vendor's
    # anonymous rate limit (Firecrawl).
    optional_key: bool = False
    default_enabled: bool = True
    default_weight: int = 100
    # Free-tier monthly allowance, or None when unmetered/unknown.
    monthly_quota: int | None = None
    max_results: int = 20
    max_urls: int = 10
    search_params: tuple[ParamSpec, ...] = ()
    fetch_params: tuple[ParamSpec, ...] = ()
    # Late-bound so tests can monkeypatch `REGISTRY[id]` adapters directly.
    rate_limits: tuple[RateLimit, ...] = ()
    # Vendors that expose a live balance endpoint. Returning a snapshot lets
    # the operator sync the local `monthly_used` accounting with reality
    # instead of only ever counting our own requests.
    usage: Callable[..., Awaitable[dict]] | None = None
    search: Callable[..., Awaitable[list[dict]]] | None = None
    fetch: Callable[..., Awaitable[list[dict]]] | None = None

    def params_for(self, kind: str) -> tuple[ParamSpec, ...]:
        return self.search_params if kind == "search" else self.fetch_params


# ── Coercion ──────────────────────────────────────────────────────────────
def coerce_params(specs: Iterable[ParamSpec], provided: dict | None) -> dict:
    """Validate caller `params` against a provider's spec.

    Raises :class:`ProviderParamError` for unknown names (a typo'd parameter
    would otherwise be silently dropped and the caller would believe they set
    `search_depth=advanced` when they set `searchDepth`), bad enum values, and
    out-of-range numbers.
    """
    specs = tuple(specs)
    provided = dict(provided or {})
    known = {p.name for p in specs}
    unknown = sorted(set(provided) - known)
    if unknown:
        raise ProviderParamError(f"unknown parameter(s): {', '.join(unknown)}")

    out: dict[str, Any] = {}
    for p in specs:
        if p.name not in provided:
            if p.required:
                raise ProviderParamError(f"missing required parameter: {p.name}")
            if p.default is not None:
                out[p.name] = p.default
            continue

        value = provided[p.name]
        if p.type == "bool":
            if isinstance(value, bool):
                out[p.name] = value
            elif isinstance(value, str) and value.lower() in ("true", "false"):
                out[p.name] = value.lower() == "true"
            else:
                raise ProviderParamError(f"{p.name} must be a boolean")
        elif p.type == "int":
            try:
                num = int(value)
            except (TypeError, ValueError):
                raise ProviderParamError(f"{p.name} must be an integer") from None
            if p.minimum is not None and num < p.minimum:
                raise ProviderParamError(f"{p.name} must be >= {p.minimum}")
            if p.maximum is not None and num > p.maximum:
                raise ProviderParamError(f"{p.name} must be <= {p.maximum}")
            out[p.name] = num
        elif p.type == "enum":
            if value not in p.enum:
                raise ProviderParamError(
                    f"{p.name} must be one of {list(p.enum)}"
                )
            out[p.name] = value
        else:
            out[p.name] = str(value)
    return out


# ── HTTP helpers ──────────────────────────────────────────────────────────
def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    body = (response.text or "")[:300]
    throttled = response.status_code == 429 or is_throttled(body)
    raise ProviderError(f"HTTP {response.status_code}: {body}", throttled=throttled)


def _json(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        raise ProviderError(f"non-JSON response: {(response.text or '')[:200]}") from None
    if not isinstance(payload, dict):
        raise ProviderError("unexpected response shape")
    # Both Tavily and TinyFish answer 200 with an error object on some
    # failures (bad key, over quota) — treat those as upstream errors.
    err = payload.get("error") or payload.get("detail")
    if isinstance(err, dict):
        message = str(err.get("message") or err.get("error") or err)
        raise ProviderError(message, throttled=is_throttled(message))
    if isinstance(err, str):
        raise ProviderError(err, throttled=is_throttled(err))
    return payload


async def _gather_limited(jobs: list[Callable[[], Awaitable[dict]]], limit: int = 4) -> list[dict]:
    """Run per-URL jobs with a concurrency cap.

    Capped rather than unbounded: the free tiers rate-limit per IP, and
    firing 10 simultaneous requests at Keenable is a reliable way to get the
    whole batch throttled.
    """
    sem = asyncio.Semaphore(limit)

    async def _run(job: Callable[[], Awaitable[dict]]) -> dict:
        async with sem:
            try:
                return await job()
            except ProviderError as exc:
                return {"url": "", "title": "", "content": "", "error": str(exc)}
            except Exception as exc:  # noqa: BLE001 — one bad URL must not kill the batch
                return {"url": "", "title": "", "content": "", "error": f"{type(exc).__name__}: {exc}"}

    return list(await asyncio.gather(*(_run(j) for j in jobs)))


def _truncate(text: str | None) -> str:
    text = text or ""
    return text[:MAX_CONTENT_CHARS]


# ── MCP transport (Exa, Parallel) ─────────────────────────────────────────
def _parse_mcp_body(body: str) -> str:
    """First text content item of an MCP ``tools/call`` response.

    Exa streams SSE (``data: {...}`` lines), Parallel returns plain JSON.
    Raises :class:`ProviderError` on JSON-RPC errors and ``isError`` tool
    results — Exa reports its free-tier rate limit as the latter, so treating
    those as a plain "empty result" would silently swallow throttling and
    never fail over.
    """

    def _from_payload(payload: str) -> str | None:
        payload = payload.strip()
        if not payload.startswith("{"):
            return None
        data = json.loads(payload)
        err = data.get("error")
        if err:
            message = str(err.get("message") or err)
            raise ProviderError(message, throttled=is_throttled(message))
        result = data.get("result") or {}
        texts = [c.get("text", "") for c in result.get("content") or [] if isinstance(c, dict)]
        if result.get("isError"):
            message = " ".join(t for t in texts if t) or "MCP tool call failed"
            raise ProviderError(message, throttled=is_throttled(message))
        return next((str(t) for t in texts if t), None)

    stripped = body.strip()
    candidates = [stripped] if stripped.startswith("{") else []
    candidates += [line[len("data: "):] for line in body.splitlines() if line.startswith("data: ")]
    for candidate in candidates:
        try:
            text = _from_payload(candidate)
        except json.JSONDecodeError:
            continue
        if text is not None:
            return text
    raise ProviderError("unrecognized MCP response shape")


async def _mcp_call(
    client: httpx.AsyncClient, url: str, tool: str, arguments: dict, timeout: float
) -> str:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": _USER_AGENT,
    }
    try:
        response = await client.post(url, json=payload, headers=headers, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise ProviderError(f"timeout after {timeout}s", throttled=True) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(f"request failed: {exc}") from exc
    _raise_for_status(response)
    return _parse_mcp_body(response.text)


# ── Exa ───────────────────────────────────────────────────────────────────
_EXA_LABELS = ("Title:", "URL:", "Highlights:", "Published:", "Author:")


def _after(line: str, prefix: str) -> str:
    return line[len(prefix):].strip()


def _parse_exa_search_text(text: str, limit: int) -> list[dict]:
    """Parse Exa's ``---``-separated ``Title:/URL:/Published:/Author:/Highlights:`` blocks."""
    results: list[dict] = []
    for block in text.split("\n---\n"):
        title = url = ""
        highlight_lines: list[str] = []
        in_highlights = False
        for stripped in map(str.strip, block.splitlines()):
            if stripped.startswith("Title:"):
                title = _after(stripped, "Title:")
            elif stripped.startswith("URL:"):
                url = _after(stripped, "URL:")
            elif in_highlights and stripped and not stripped.startswith(_EXA_LABELS):
                highlight_lines.append(stripped)
            # Highlights run until the next labelled field.
            if stripped.startswith(_EXA_LABELS):
                in_highlights = stripped.startswith("Highlights:")
        if url:
            results.append({
                "title": title,
                "url": url,
                "snippet": " ".join(highlight_lines),
                "score": None,
            })
        if limit and len(results) >= limit:
            break
    return results


async def _exa_search(client, query: str, *, api_key, max_results: int, params: dict, timeout: float) -> list[dict]:
    text = await _mcp_call(
        client,
        EXA_MCP_URL,
        "web_search_exa",
        {"query": query, "numResults": max(1, int(max_results))},
        timeout,
    )
    return _parse_exa_search_text(text, max_results)


async def _exa_fetch(client, urls: list[str], *, api_key, params: dict, timeout: float) -> list[dict]:
    # The tool takes one URL per call and returns ONE combined text payload.
    async def _one(url: str) -> dict:
        text = await _mcp_call(client, EXA_MCP_URL, "web_fetch_exa", {"urls": [url]}, timeout)
        titles = (
            _after(s, "# " if s.startswith("# ") else "Title:")
            for s in map(str.strip, text.splitlines())
            if s.startswith(("# ", "Title:"))
        )
        return {"url": url, "title": next(titles, ""), "content": _truncate(text), "error": ""}

    return await _gather_limited([(lambda u=url: _one(u)) for url in urls])


# ── Parallel ──────────────────────────────────────────────────────────────
async def _parallel_search(client, query: str, *, api_key, max_results: int, params: dict, timeout: float) -> list[dict]:
    text = await _mcp_call(
        client,
        PARALLEL_MCP_URL,
        "web_search",
        {"objective": query, "search_queries": [query], "session_id": _SESSION_ID},
        timeout,
    )
    try:
        results = (json.loads(text).get("results") or [])[:max_results]
    except (json.JSONDecodeError, AttributeError) as exc:
        raise ProviderError(f"unexpected payload: {exc}") from exc
    return [
        {
            "title": r.get("title") or "",
            "url": r.get("url") or "",
            "snippet": " ".join(r.get("excerpts") or []),
            "score": None,
        }
        for r in results
        if r.get("url")
    ]


async def _parallel_fetch(client, urls: list[str], *, api_key, params: dict, timeout: float) -> list[dict]:
    text = await _mcp_call(
        client,
        PARALLEL_MCP_URL,
        "web_fetch",
        {"urls": list(urls), "objective": "Full page content", "session_id": _SESSION_ID},
        timeout,
    )
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"unexpected payload: {exc}") from exc

    out = [
        {
            "url": r.get("url") or "",
            "title": r.get("title") or "",
            "content": _truncate(
                r.get("full_content") or r.get("content") or "\n\n".join(r.get("excerpts") or [])
            ),
            "error": "",
        }
        for r in data.get("results") or []
    ]
    for error in data.get("errors") or []:
        out.append({
            "url": error.get("url") or "",
            "title": "",
            "content": "",
            "error": str(error.get("content") or error.get("error_type") or "extraction failed"),
        })
    # URLs the endpoint silently dropped still get an entry — the per-URL
    # contract means the caller can zip results back to their input list.
    seen = {r["url"] for r in out}
    out.extend(
        {"url": u, "title": "", "content": "", "error": "no content returned"}
        for u in urls
        if u not in seen
    )
    return out


# ── Firecrawl ─────────────────────────────────────────────────────────────
def _firecrawl_headers(api_key: str | None) -> dict:
    headers = {"Content-Type": "application/json", "User-Agent": _USER_AGENT}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


async def _firecrawl_search(client, query: str, *, api_key, max_results: int, params: dict, timeout: float) -> list[dict]:
    response = await client.post(
        f"{FIRECRAWL_API_URL}/v2/search",
        json={"query": query, "limit": max(1, int(max_results))},
        headers=_firecrawl_headers(api_key),
        timeout=timeout,
    )
    _raise_for_status(response)
    data = _json(response).get("data") or []
    return [
        {
            "title": r.get("title") or "",
            "url": r.get("url") or "",
            "snippet": r.get("description") or r.get("markdown") or "",
            "score": None,
        }
        for r in data
        if r.get("url")
    ]


async def _firecrawl_fetch(client, urls: list[str], *, api_key, params: dict, timeout: float) -> list[dict]:
    async def _one(url: str) -> dict:
        response = await client.post(
            f"{FIRECRAWL_API_URL}/v2/scrape",
            json={"url": url, "formats": ["markdown"]},
            headers=_firecrawl_headers(api_key),
            timeout=timeout,
        )
        _raise_for_status(response)
        payload = _json(response).get("data") or _json(response)
        metadata = payload.get("metadata") or {}
        return {
            "url": url,
            "title": (metadata.get("title") if isinstance(metadata, dict) else None) or "",
            "content": _truncate(payload.get("markdown") or payload.get("html") or ""),
            "error": "",
        }

    return await _gather_limited([(lambda u=url: _one(u)) for url in urls])


# ── Keenable ──────────────────────────────────────────────────────────────
async def _keenable_search(client, query: str, *, api_key, max_results: int, params: dict, timeout: float) -> list[dict]:
    response = await client.post(
        f"{KEENABLE_API_URL}/v1/search/public",
        json={"query": query, "max_results": max(1, int(max_results))},
        headers={"X-Keenable-Title": _KEENABLE_TITLE, "Content-Type": "application/json"},
        timeout=timeout,
    )
    _raise_for_status(response)
    data = _json(response)
    return [
        {
            "title": r.get("title") or "",
            "url": r.get("url") or "",
            "snippet": r.get("snippet") or r.get("description") or "",
            "score": None,
        }
        for r in data.get("results") or []
        if r.get("url")
    ]


async def _keenable_fetch(client, urls: list[str], *, api_key, params: dict, timeout: float) -> list[dict]:
    async def _one(url: str) -> dict:
        response = await client.get(
            f"{KEENABLE_API_URL}/v1/fetch/public",
            params={"url": url},
            headers={"X-Keenable-Title": _KEENABLE_TITLE},
            timeout=timeout,
        )
        _raise_for_status(response)
        data = _json(response)
        return {
            "url": url,
            "title": data.get("title") or "",
            "content": _truncate(data.get("content")),
            "error": "",
        }

    return await _gather_limited([(lambda u=url: _one(u)) for url in urls])


# ── Tavily ────────────────────────────────────────────────────────────────
async def _tavily_search(client, query: str, *, api_key, max_results: int, params: dict, timeout: float) -> list[dict]:
    body: dict[str, Any] = {"query": query, "max_results": max(0, min(int(max_results), 20))}
    body.update(params)
    response = await client.post(
        f"{TAVILY_API_URL}/search",
        json=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=timeout,
    )
    _raise_for_status(response)
    data = _json(response)
    return [
        {
            "title": r.get("title") or "",
            "url": r.get("url") or "",
            "snippet": r.get("content") or "",
            "score": r.get("score"),
        }
        for r in data.get("results") or []
        if r.get("url")
    ]


async def _tavily_fetch(client, urls: list[str], *, api_key, params: dict, timeout: float) -> list[dict]:
    body: dict[str, Any] = {"urls": list(urls)}
    body.update(params)
    response = await client.post(
        f"{TAVILY_API_URL}/extract",
        json=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=timeout,
    )
    _raise_for_status(response)
    data = _json(response)

    out = [
        {
            "url": r.get("url") or "",
            "title": "",
            "content": _truncate(r.get("raw_content") or r.get("content")),
            "error": "",
        }
        for r in data.get("results") or []
    ]
    for failed in data.get("failed_results") or []:
        out.append({
            "url": failed.get("url") or "",
            "title": "",
            "content": "",
            "error": str(failed.get("error") or "extraction failed"),
        })
    seen = {r["url"] for r in out}
    out.extend(
        {"url": u, "title": "", "content": "", "error": "no content returned"}
        for u in urls
        if u not in seen
    )
    return out


async def _tavily_usage(client, *, api_key, timeout: float) -> dict:
    """Live credit balance from Tavily's `/usage` endpoint.

    Returns the key-level numbers (what actually gates API calls on the free
    plan) plus the account-level block verbatim, so the dashboard can show
    which plan the allowance came from without us re-shaping it.
    """
    response = await client.get(
        f"{TAVILY_API_URL}/usage",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout,
    )
    _raise_for_status(response)
    data = _json(response)
    key = data.get("key") or {}
    limit = key.get("limit")
    used = key.get("usage")
    if not isinstance(limit, int) or not isinstance(used, int):
        raise ProviderError("unexpected usage payload: missing key.usage/key.limit")
    remaining = max(0, limit - used)
    return {
        "monthly": limit,
        "used": used,
        "remaining": remaining,
        "remaining_percent": round(100 * remaining / limit, 1) if limit else None,
        # Tavily's allowance resets monthly; we don't get a reset date, so the
        # rolling marker stays whatever the local counter was tracking.
        "plan": (data.get("account") or {}).get("current_plan"),
        "breakdown": {
            k: key.get(k)
            for k in ("search_usage", "extract_usage", "crawl_usage", "map_usage", "research_usage")
        },
        "raw": data,
    }


# ── TinyFish ──────────────────────────────────────────────────────────────
async def _tinyfish_search(client, query: str, *, api_key, max_results: int, params: dict, timeout: float) -> list[dict]:
    query_params: dict[str, Any] = {"query": query}
    query_params.update(params)
    response = await client.get(
        TINYFISH_SEARCH_URL,
        params={k: v for k, v in query_params.items() if v is not None},
        headers={"X-API-Key": api_key},
        timeout=timeout,
    )
    _raise_for_status(response)
    data = _json(response)
    return [
        {
            "title": r.get("title") or "",
            "url": r.get("url") or "",
            "snippet": r.get("snippet") or "",
            "score": None,
        }
        for r in (data.get("results") or [])[:max_results]
        if r.get("url")
    ]


async def _tinyfish_fetch(client, urls: list[str], *, api_key, params: dict, timeout: float) -> list[dict]:
    body: dict[str, Any] = {"urls": list(urls)}
    body.update(params)
    response = await client.post(
        TINYFISH_FETCH_URL,
        json=body,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        timeout=timeout,
    )
    _raise_for_status(response)
    data = _json(response)

    out = [
        {
            "url": r.get("url") or "",
            "title": r.get("title") or "",
            "content": _truncate(r.get("text") or r.get("content")),
            "error": "",
        }
        for r in data.get("results") or []
    ]
    for error in data.get("errors") or []:
        out.append({
            "url": error.get("url") or "",
            "title": "",
            "content": "",
            "error": str(error.get("error") or "extraction failed"),
        })
    seen = {r["url"] for r in out}
    out.extend(
        {"url": u, "title": "", "content": "", "error": "no content returned"}
        for u in urls
        if u not in seen
    )
    return out


# ── Registry ──────────────────────────────────────────────────────────────
def _spec(**kwargs: Any) -> ProviderSpec:
    return ProviderSpec(**kwargs)


REGISTRY: dict[str, ProviderSpec] = {
    s.id: s
    for s in (
        _spec(
            id="exa",
            label="Exa",
            tier="keyless",
            capabilities=frozenset({"search", "fetch"}),
            docs_url="https://exa.ai",
            max_results=20,
            max_urls=10,
            search=_exa_search,
            fetch=_exa_fetch,
        ),
        _spec(
            id="parallel",
            label="Parallel",
            tier="keyless",
            capabilities=frozenset({"search", "fetch"}),
            docs_url="https://parallel.ai",
            max_results=20,
            max_urls=10,
            search=_parallel_search,
            fetch=_parallel_fetch,
        ),
        _spec(
            id="firecrawl",
            label="Firecrawl",
            tier="keyless",
            capabilities=frozenset({"search", "fetch"}),
            docs_url="https://firecrawl.dev",
            optional_key=True,
            max_results=20,
            max_urls=10,
            search=_firecrawl_search,
            fetch=_firecrawl_fetch,
        ),
        _spec(
            id="keenable",
            label="Keenable",
            tier="keyless",
            capabilities=frozenset({"search", "fetch"}),
            docs_url="https://keenable.ai",
            max_results=20,
            max_urls=10,
            search=_keenable_search,
            fetch=_keenable_fetch,
        ),
        _spec(
            id="tavily",
            label="Tavily",
            tier="quota",
            capabilities=frozenset({"search", "fetch"}),
            docs_url="https://tavily.com",
            requires_key=True,
            default_enabled=False,
            # Free plan: 1,000 search credits / month.
            monthly_quota=1000,
            max_results=20,
            max_urls=10,
            search_params=(
                ParamSpec("search_depth", "enum", default="basic", enum=("basic", "advanced", "fast", "ultra-fast"),
                          description="Latency vs relevance. 'advanced' costs 2 credits, the rest 1."),
                ParamSpec("topic", "enum", default="general", enum=("general", "news", "finance"),
                          description="Search category."),
                ParamSpec("time_range", "enum", enum=("day", "week", "month", "year"),
                          description="Only results published/updated within this window."),
                ParamSpec("include_answer", "bool", default=False,
                          description="Add an LLM-generated answer to the query."),
                ParamSpec("include_raw_content", "bool", default=False,
                          description="Include cleaned page content for each result."),
                ParamSpec("include_images", "bool", default=False, description="Include image URLs."),
                ParamSpec("country", "string", description="Boost results from a country (e.g. 'united states')."),
            ),
            fetch_params=(
                ParamSpec("extract_depth", "enum", default="basic", enum=("basic", "advanced"),
                          description="'advanced' also pulls tables and embedded content (2 credits / 5 URLs)."),
                ParamSpec("format", "enum", default="markdown", enum=("markdown", "text"),
                          description="Output format for extracted content."),
                ParamSpec("include_images", "bool", default=False, description="Include extracted image URLs."),
                ParamSpec("include_favicon", "bool", default=False, description="Include each page's favicon URL."),
            ),
            search=_tavily_search,
            fetch=_tavily_fetch,
            usage=_tavily_usage,
        ),
        _spec(
            id="tinyfish",
            label="TinyFish",
            tier="quota",
            capabilities=frozenset({"search", "fetch"}),
            docs_url="https://tinyfish.ai",
            requires_key=True,
            default_enabled=False,
            # TinyFish doesn't publish a fixed free-tier number, so no default
            # is seeded: `monthly_quota` stays NULL ("unmetered") until the
            # operator enters their allowance from the dashboard, at which
            # point the `quota` strategy starts accounting for it.
            max_results=20,
            max_urls=10,
            search_params=(
                ParamSpec("purpose", "string",
                          description="Why the search is run — used to rank results against your intent."),
                ParamSpec("domain_type", "enum", default="web", enum=("web", "news", "research_paper"),
                          description="Kind of results to return."),
                ParamSpec("location", "string", description="Country code for geo-targeted results (e.g. 'US')."),
                ParamSpec("language", "string", description="Language code for results (e.g. 'en')."),
                ParamSpec("after_date", "string", description="Only results after this date (YYYY-MM-DD)."),
                ParamSpec("before_date", "string", description="Only results before this date (YYYY-MM-DD)."),
                ParamSpec("recency_minutes", "int", minimum=1, maximum=5_256_000,
                          description="Only results from the past N minutes."),
                ParamSpec("page", "int", default=0, minimum=0, maximum=10, description="Pagination page (0-based)."),
            ),
            fetch_params=(
                ParamSpec("purpose", "string",
                          description="Why these URLs are fetched — tailors extraction to your intent."),
                ParamSpec("format", "enum", default="markdown", enum=("markdown", "html", "json"),
                          description="Output format for extracted content."),
                ParamSpec("links", "bool", default=False, description="Extract outbound links."),
                ParamSpec("image_links", "bool", default=False, description="Extract image URLs."),
                ParamSpec("page_metadata", "bool", default=False,
                          description="Return head metadata (canonical, OG tags, robots, …)."),
                ParamSpec("ttl", "int", default=0, minimum=0,
                          description="Cached-entry freshness tolerance in seconds; 0 prefers a live fetch."),
                ParamSpec("per_url_timeout_ms", "int", default=45000, minimum=1, maximum=110000,
                          description="Per-URL wall-clock budget."),
            ),
            rate_limits=(
                RateLimit("search", "minute", 30),
                RateLimit("search", "hour", 500),
                RateLimit("fetch", "minute", 150),
                RateLimit("fetch", "day", 1000),
            ),
            search=_tinyfish_search,
            fetch=_tinyfish_fetch,
        ),
    )
}

STRATEGIES: tuple[str, ...] = ("random", "quota", "latency", "explicit")
DEFAULT_STRATEGY = "random"
DEFAULT_TIMEOUT_MS = 8000
DEFAULT_MAX_RESULTS = 5


def known_ids() -> list[str]:
    return sorted(REGISTRY)


def get_spec(provider_id: str) -> ProviderSpec | None:
    return REGISTRY.get((provider_id or "").strip().lower())
