"""Tests for /v1/models, /v1/keys (rotate), /v1/routing (strategy)."""

from __future__ import annotations

import pytest


@pytest.fixture
async def lite_client(tmp_sqlite_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", tmp_sqlite_url)
    from app import config as cfg
    cfg.get_settings.cache_clear()

    from packages.db.engine import build_engine
    from packages.db.models.base import Base

    engine = build_engine(tmp_sqlite_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from packages.db import session as session_mod
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session_mod._session_factory = factory

    from app.seed import seed_initial_state
    async with factory() as s:
        seed = await seed_initial_state(s)

    from app.main import create_app
    app = create_app()

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://t",
        headers={"Authorization": f"Bearer {seed.api_key}"},
    ) as c:
        yield c, seed.api_key

    await engine.dispose()
    session_mod._session_factory = None


# ── /v1/models ────────────────────────────────────────────────────────
#
# The listing is DEPLOYED models only — what this instance can actually
# serve. A bare install (no provider keys) therefore lists nothing, so the
# models tests run against a client with one provider configured.


@pytest.fixture
async def configured_client(lite_client):
    client, _ = lite_client
    r = await client.put("/v1/providers/openai", json={"api_key": "sk-test-12345678"})
    assert r.status_code == 200, r.text
    return client


async def test_models_lists_only_deployed_providers(configured_client):
    """A configured provider's models are listed; an unconfigured one's are
    not — advertising servable-and-nothing-else is what stops clients from
    copying a catalog id and eating a 503."""
    r = await configured_client.get("/v1/models")
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "list"
    ids = {m["id"] for m in body["data"]}
    assert ids, "configured openai key must deploy its catalog models"
    assert any(i.startswith("gpt-") for i in ids)
    # anthropic has no key here — its models must not be advertised.
    assert not any(i.startswith("claude-") for i in ids)
    sample = body["data"][0]
    assert sample["object"] == "model"
    assert "id" in sample
    assert "owned_by" in sample


async def test_models_empty_when_nothing_configured(lite_client):
    """No keys → nothing is servable → nothing is advertised. The old
    behavior (list the full catalog regardless) sent clients chasing
    models that could only ever 503."""
    client, _ = lite_client
    r = await client.get("/v1/models")
    assert r.status_code == 200
    assert r.json()["data"] == []


async def test_models_returns_anthropic_format_for_anthropic_clients(configured_client):
    """The native /v1/messages surface lives on the same base URL, so
    `client.models.list()` from the Anthropic SDK hits this path too. It
    always sends `anthropic-version` (no OpenAI client does), which is
    what selects the Anthropic envelope."""
    r = await configured_client.get("/v1/models", headers={"anthropic-version": "2023-06-01"})
    assert r.status_code == 200
    body = r.json()
    assert "object" not in body  # not the OpenAI envelope
    assert body["has_more"] is False
    assert body["first_id"] == body["data"][0]["id"]
    assert body["last_id"] == body["data"][-1]["id"]
    sample = body["data"][0]
    assert sample["type"] == "model"
    assert sample["id"] and sample["display_name"]
    # RFC 3339, per ModelInfo.created_at
    assert sample["created_at"].endswith("Z")


async def test_models_without_anthropic_header_stays_openai_shaped(configured_client):
    """Regression guard: adding the Anthropic envelope must not change the
    default shape every OpenAI client depends on."""
    r = await configured_client.get("/v1/models", headers={"user-agent": "openai-python/1.0"})
    assert r.json()["object"] == "list"


# ── /v1/keys ──────────────────────────────────────────────────────────

async def test_list_keys_shows_seeded_key(lite_client):
    client, _ = lite_client
    r = await client.get("/v1/keys")
    assert r.status_code == 200
    body = r.json()
    assert len(body["keys"]) == 1
    assert body["keys"][0]["name"] == "default"
    assert "key_hash" not in body["keys"][0]


async def test_create_new_key_returns_plaintext_once(lite_client):
    client, _ = lite_client
    r = await client.post("/v1/keys", json={"name": "ci-runner"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["api_key"].startswith("sk-orca-")
    assert body["name"] == "ci-runner"

    listing = await client.get("/v1/keys")
    names = {k["name"] for k in listing.json()["keys"]}
    assert names == {"default", "ci-runner"}


async def test_revoke_key_blocks_reauth(lite_client):
    client, _ = lite_client
    created = (await client.post("/v1/keys", json={"name": "to-revoke"})).json()
    new_key = created["api_key"]
    new_id = created["id"]

    r = await client.delete(f"/v1/keys/{new_id}")
    assert r.status_code == 204

    from httpx import AsyncClient
    transport = client._transport
    async with AsyncClient(transport=transport, base_url="http://t",
                           headers={"Authorization": f"Bearer {new_key}"}) as fresh:
        r2 = await fresh.get("/v1/keys")
    assert r2.status_code == 401


# ── /v1/routing ───────────────────────────────────────────────────────

async def test_get_routing_returns_default_strategy(lite_client):
    client, _ = lite_client
    r = await client.get("/v1/routing")
    assert r.status_code == 200
    body = r.json()
    assert body["strategy"] == "balanced"


async def test_put_routing_updates_strategy(lite_client):
    client, _ = lite_client
    r = await client.put("/v1/routing", json={"strategy": "cheapest"})
    assert r.status_code == 200
    assert r.json()["strategy"] == "cheapest"

    fetched = await client.get("/v1/routing")
    assert fetched.json()["strategy"] == "cheapest"


async def test_put_routing_rejects_unknown_strategy(lite_client):
    client, _ = lite_client
    r = await client.put("/v1/routing", json={"strategy": "magic-sauce"})
    assert r.status_code == 422


async def test_put_routing_invalidates_cached_router(lite_client, monkeypatch):
    """Changing the strategy must drop the cached client so the next request
    rebuilds it with the new `routing_strategy`."""
    client, _ = lite_client
    from app import router_cache

    sentinel = object()
    router_cache._cached_client = sentinel
    assert router_cache._cached_client is sentinel

    r = await client.put("/v1/routing", json={"strategy": "cheapest"})
    assert r.status_code == 200
    assert router_cache._cached_client is None
