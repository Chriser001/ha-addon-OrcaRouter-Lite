"""Aggregated search/fetch surface — provider listing, config and dispatch.

Upstream calls are faked by patching the registry's adapters; the engine's
ordering and failover logic is covered in `tests/unit/test_network_engine.py`.
Here we pin the HTTP contract: shapes, status codes, auth, visibility.
"""

from __future__ import annotations

import dataclasses

import pytest

from app import network_providers as np


async def _fake_search(client, query, *, api_key, max_results, params, timeout):
    """Shape-compatible stand-in for a provider adapter."""
    return [
        {"title": f"{query} {i}", "url": f"https://example.com/{i}", "snippet": "s", "score": None}
        for i in range(min(max_results, 3))
    ]


async def _fake_fetch(client, urls, *, api_key, params, timeout):
    return [{"url": u, "title": "t", "content": "body", "error": ""} for u in urls]


def _patch_exa(monkeypatch, search=None, fetch=None):
    spec = dataclasses.replace(
        np.REGISTRY["exa"],
        search=search or _fake_search,
        fetch=fetch or _fake_fetch,
    )
    monkeypatch.setitem(np.REGISTRY, "exa", spec)


# ── listing ───────────────────────────────────────────────────────────────
async def test_providers_listing_includes_all_seeded_providers(authed_client):
    r = await authed_client.get("/v1/network/providers")
    assert r.status_code == 200, r.text
    body = r.json()
    ids = {p["id"] for p in body["providers"]}
    assert ids == {"exa", "parallel", "firecrawl", "keenable", "tavily", "tinyfish"}
    assert body["defaults"]["strategies"] == ["random", "quota", "latency", "explicit"]


async def test_keyless_providers_listed_as_configured(authed_client):
    r = await authed_client.get("/v1/network/providers")
    by_id = {p["id"]: p for p in r.json()["providers"]}
    assert by_id["exa"]["requires_key"] is False
    assert by_id["exa"]["configured"] is True
    assert by_id["exa"]["is_enabled"] is True


async def test_keyed_providers_require_a_key_and_publish_params(authed_client):
    r = await authed_client.get("/v1/network/providers")
    by_id = {p["id"]: p for p in r.json()["providers"]}
    tav = by_id["tavily"]
    assert tav["requires_key"] is True
    assert tav["configured"] is False
    assert tav["is_enabled"] is False
    # The dashboard renders its form from this — it must always be present.
    names = {p["name"] for p in tav["search"]["params"]}
    assert "search_depth" in names
    assert tav["quota"]["monthly"] == 1000


async def test_capability_filter(authed_client):
    r = await authed_client.get("/v1/network/providers", params={"capability": "search"})
    assert r.status_code == 200
    assert {p["id"] for p in r.json()["providers"]} == {
        "exa", "parallel", "firecrawl", "keenable", "tavily", "tinyfish",
    }

    r2 = await authed_client.get("/v1/network/providers", params={"capability": "bogus"})
    assert r2.status_code == 422


async def test_listing_requires_auth(client_no_auth):
    r = await client_no_auth.get("/v1/network/providers")
    assert r.status_code == 401


# ── provider config ───────────────────────────────────────────────────────
async def test_set_key_enables_a_keyed_provider(authed_client, isolated_env):
    r = await authed_client.put("/v1/network/providers/tavily", json={"api_key": "tvly-abc123456789"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["configured"] is True
    assert body["key_prefix"].startswith("tvly-")
    assert body["is_enabled"] is True
    assert body["key_source"] == "db"


async def test_unknown_provider_is_404(authed_client):
    r = await authed_client.put("/v1/network/providers/notreal", json={"api_key": "x"})
    assert r.status_code == 404


async def test_clear_key_disables_a_keyed_provider(authed_client, isolated_env):
    await authed_client.put("/v1/network/providers/tavily", json={"api_key": "tvly-abc123456789"})
    r = await authed_client.put("/v1/network/providers/tavily", json={"api_key": ""})
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["is_enabled"] is False


async def test_weight_is_persisted(authed_client):
    r = await authed_client.put("/v1/network/providers/keenable", json={"weight": 33})
    assert r.status_code == 200
    assert r.json()["weight"] == 33

    listed = await authed_client.get("/v1/network/providers")
    keenable = next(p for p in listed.json()["providers"] if p["id"] == "keenable")
    assert keenable["weight"] == 33


async def test_reset_provider_clears_key(authed_client, isolated_env):
    await authed_client.put("/v1/network/providers/tavily", json={"api_key": "tvly-abc123456789"})
    r = await authed_client.delete("/v1/network/providers/tavily")
    assert r.status_code == 204

    listed = await authed_client.get("/v1/network/providers")
    tav = next(p for p in listed.json()["providers"] if p["id"] == "tavily")
    assert tav["configured"] is False
    assert tav["is_enabled"] is False


async def test_enabling_keyless_never_needs_a_key(authed_client):
    r = await authed_client.put("/v1/network/providers/exa", json={"is_enabled": False})
    assert r.status_code == 200
    r2 = await authed_client.put("/v1/network/providers/exa", json={"is_enabled": True})
    assert r2.status_code == 200
    assert r2.json()["is_enabled"] is True


# ── search ────────────────────────────────────────────────────────────────
async def test_search_through_a_pinned_provider(authed_client, monkeypatch):
    _patch_exa(monkeypatch)
    r = await authed_client.post(
        "/v1/network/search",
        json={"query": "orcarouter", "provider": "exa", "max_results": 2},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "exa"
    assert body["strategy"] == "explicit"
    assert body["requested_provider"] == "exa"
    assert body["count"] == 2
    assert body["results"][0]["url"].startswith("https://example.com/")
    assert body["failover_from"] == []


async def test_search_fails_over_when_the_head_is_throttled(authed_client, monkeypatch):
    async def throttled(client, query, *, api_key, max_results, params, timeout):
        raise np.ProviderError("HTTP 429: too many requests", throttled=True)

    _patch_exa(monkeypatch, search=throttled)
    spec = dataclasses.replace(np.REGISTRY["parallel"], search=_fake_search)
    monkeypatch.setitem(np.REGISTRY, "parallel", spec)

    r = await authed_client.post(
        "/v1/network/search",
        json={"query": "orcarouter", "provider": "exa"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # The tail is a weighted-random shuffle, so the failing head is the only
    # entry whose position is guaranteed.
    assert body["provider"] == "parallel"
    assert "exa" in body["failover_from"]
    assert body["errors"]["exa"].startswith("HTTP 429")


def _err_detail(resp) -> str:
    """The app's global exception handler rewrites HTTPException into
    ``{"error": {"message": ...}}`` — never the FastAPI ``{"detail": ...}``
    shape, so tests must read the message through this helper."""
    return resp.json()["error"]["message"]


async def test_search_cascades_on_any_upstream_error(authed_client, monkeypatch):
    """Non-throttled upstream errors still cascade.

    Inputs are validated before the chain starts, so whatever reaches an
    adapter is vendor-specific (bad key, outage) — another vendor may answer
    it. A fully-down cascade is bounded by the chain budget, not by guesswork
    about which errors are "hopeless".
    """
    async def broken(client, query, *, api_key, max_results, params, timeout):
        raise np.ProviderError("HTTP 500: internal", throttled=False)

    _patch_exa(monkeypatch, search=broken)
    monkeypatch.setitem(np.REGISTRY, "parallel", dataclasses.replace(np.REGISTRY["parallel"], search=_fake_search))

    r = await authed_client.post("/v1/network/search", json={"query": "x", "provider": "exa"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "parallel"
    assert "exa" in body["failover_from"]


async def test_search_all_providers_down_is_502(authed_client, monkeypatch):
    async def down(client, query, *, api_key, max_results, params, timeout):
        raise np.ProviderError("HTTP 429: slow down", throttled=True)

    for prov in ("exa", "parallel", "firecrawl", "keenable"):
        monkeypatch.setitem(
            np.REGISTRY, prov, dataclasses.replace(np.REGISTRY[prov], search=down)
        )

    r = await authed_client.post("/v1/network/search", json={"query": "x"})
    assert r.status_code == 502
    assert "tried:" in _err_detail(r)


async def test_empty_query_is_400(authed_client):
    r = await authed_client.post("/v1/network/search", json={"query": "   "})
    assert r.status_code == 400


async def test_bad_params_are_400(authed_client, monkeypatch):
    _patch_exa(monkeypatch)
    r = await authed_client.post(
        "/v1/network/search", json={"query": "x", "provider": "exa", "params": {"nope": 1}}
    )
    assert r.status_code == 400
    assert "unknown parameter" in _err_detail(r)


async def test_rate_limit_records_a_cooldown(authed_client, monkeypatch):
    """A 429 puts the provider on cooldown for the AUTOMATIC pool.

    Pinned calls still reach it on purpose: the caller asked for that vendor
    by name, and "prefer" was never a promise to second-guess. The automatic
    side of that contract is covered by
    `tests/unit/test_network_engine.py::test_cooled_down_providers_are_skipped`.
    """
    async def throttled(client, query, *, api_key, max_results, params, timeout):
        raise np.ProviderError("HTTP 429: too many requests", throttled=True)

    _patch_exa(monkeypatch, search=throttled)
    monkeypatch.setitem(np.REGISTRY, "parallel", dataclasses.replace(np.REGISTRY["parallel"], search=_fake_search))

    r1 = await authed_client.post("/v1/network/search", json={"query": "x", "provider": "exa"})
    assert r1.status_code == 200  # served by the tail
    assert r1.json()["provider"] == "parallel"
    assert "exa" in r1.json()["failover_from"]

    listed = await authed_client.get("/v1/network/providers")
    exa = next(p for p in listed.json()["providers"] if p["id"] == "exa")
    assert exa["cooldown_until"] is not None
    assert "429" in (exa["last_error"] or "")

    # A pinned call is still honoured despite the cooldown...
    r2 = await authed_client.post("/v1/network/search", json={"query": "x", "provider": "exa"})
    assert r2.status_code == 200
    assert r2.json()["provider"] == "parallel"
    # ...but it was the pinned head that got tried, not a pool pick.
    assert "exa" in r2.json()["failover_from"]


# ── fetch ─────────────────────────────────────────────────────────────────
async def test_fetch_returns_per_url_results(authed_client, monkeypatch):
    _patch_exa(monkeypatch)
    r = await authed_client.post(
        "/v1/network/fetch", json={"urls": ["https://example.com/a", "https://example.com/b"]}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url_count"] == 2
    assert body["count"] == 2
    assert [x["url"] for x in body["results"]] == [
        "https://example.com/a", "https://example.com/b",
    ]


async def test_fetch_blocks_private_targets(authed_client, monkeypatch):
    _patch_exa(monkeypatch)
    r = await authed_client.post("/v1/network/fetch", json={"urls": ["http://169.254.169.254/"]})
    assert r.status_code == 400
    assert "private_address" in _err_detail(r)


async def test_fetch_rejects_too_many_urls(authed_client):
    r = await authed_client.post(
        "/v1/network/fetch", json={"urls": [f"https://example.com/{i}" for i in range(11)]}
    )
    assert r.status_code == 422  # model-level cap (max_length=10)


async def test_fetch_requires_urls(authed_client):
    r = await authed_client.post("/v1/network/fetch", json={"urls": []})
    assert r.status_code == 422


# ── fixtures ──────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _no_real_vendors(monkeypatch):
    """Point every adapter at a stub that refuses to run.

    Autouse, because a test that only patches the provider it is asserting on
    leaves the rest of the failover tail pointed at real free-tier endpoints —
    which would both flake the suite and spend real quota on every run.
    """
    async def _blocked(*_a, **_kw):
        raise AssertionError("test tried to call a real network provider")

    for prov, spec in np.REGISTRY.items():
        monkeypatch.setitem(
            np.REGISTRY, prov, dataclasses.replace(spec, search=_blocked, fetch=_blocked)
        )


# ── live quota refresh (Tavily /usage) ────────────────────────────────────
async def _fake_usage(client, *, api_key, timeout):
    return {
        "monthly": 1000,
        "used": 150,
        "remaining": 850,
        "remaining_percent": 85.0,
        "plan": "Bootstrap",
        "breakdown": {"search_usage": 100, "extract_usage": 25},
        "raw": {"key": {"usage": 150, "limit": 1000}},
    }


async def test_listing_publishes_limits_and_usage_capability(authed_client):
    r = await authed_client.get("/v1/network/providers")
    by_id = {p["id"]: p for p in r.json()["providers"]}

    tav = by_id["tavily"]
    assert tav["supports_usage"] is True
    assert tav["limits"] == []

    tiny = by_id["tinyfish"]
    assert tiny["supports_usage"] is False
    assert {(x["operation"], x["per"], x["limit"]) for x in tiny["limits"]} == {
        ("search", "minute", 30),
        ("search", "hour", 500),
        ("fetch", "minute", 150),
        ("fetch", "day", 1000),
    }
    # Keyless vendors publish no limits — their throttle is opaque.
    assert by_id["exa"]["limits"] == []


async def test_refresh_quota_adopts_vendor_balance(authed_client, monkeypatch, isolated_env):
    monkeypatch.setitem(
        np.REGISTRY,
        "tavily",
        dataclasses.replace(np.REGISTRY["tavily"], usage=_fake_usage),
    )
    await authed_client.put("/v1/network/providers/tavily", json={"api_key": "tvly-abc123456789"})

    r = await authed_client.post("/v1/network/providers/tavily/refresh-quota")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["quota"]["monthly"] == 1000
    assert body["quota"]["used"] == 150
    assert body["plan"] == "Bootstrap"

    # The snapshot must be persisted, not just echoed — the `quota` strategy
    # and the analytics page read it from the row.
    listed = await authed_client.get("/v1/network/providers")
    tav = next(p for p in listed.json()["providers"] if p["id"] == "tavily")
    assert tav["quota"]["monthly"] == 1000
    assert tav["quota"]["used"] == 150


async def test_refresh_quota_rejects_unsupported_vendor(authed_client):
    r = await authed_client.post("/v1/network/providers/exa/refresh-quota")
    assert r.status_code == 409
    assert "balance" in r.json()["error"]["message"]


async def test_refresh_quota_requires_a_key(authed_client, isolated_env):
    r = await authed_client.post("/v1/network/providers/tavily/refresh-quota")
    assert r.status_code == 409
    assert "API key" in r.json()["error"]["message"]
