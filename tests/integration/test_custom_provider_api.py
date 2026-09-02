"""Custom-endpoint providers over HTTP — the operator-facing contract.

Unit tests cover deployment assembly; these cover what an operator actually
does: paste a base URL, save, rescan, and expect the models to show up in
`GET /v1/models`.
"""

from __future__ import annotations

import pytest


@pytest.fixture
async def authed_client(tmp_sqlite_url, monkeypatch, isolated_env):
    """Booted lite app + client carrying the seeded API key."""
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
        yield c

    await engine.dispose()
    session_mod._session_factory = None


async def test_put_with_api_base_round_trips(authed_client):
    r = await authed_client.put(
        "/v1/providers/mygateway",
        json={"api_key": "sk-gw-12345", "api_base": "https://gw.example.com/v1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["api_base"] == "https://gw.example.com/v1"

    listing = await authed_client.get("/v1/providers")
    assert listing.json()["providers"][0]["api_base"] == "https://gw.example.com/v1"


async def test_arbitrary_provider_id_is_accepted(authed_client):
    """This is the point of the feature: no code change to add a provider."""
    r = await authed_client.put(
        "/v1/providers/sensenova",
        json={"api_key": "sk-x", "api_base": "https://api.sensenova.cn/v1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "sensenova"


async def test_api_base_is_normalized(authed_client):
    """Trailing slashes are stripped so litellm never sees `//models`."""
    r = await authed_client.put(
        "/v1/providers/gw",
        json={"api_key": "sk-x", "api_base": "  https://gw.example.com/v1/  "},
    )
    assert r.status_code == 200, r.text
    assert r.json()["api_base"] == "https://gw.example.com/v1"


async def test_rejects_non_http_api_base(authed_client):
    r = await authed_client.put(
        "/v1/providers/gw",
        json={"api_key": "sk-x", "api_base": "gw.example.com/v1"},
    )
    assert r.status_code == 422
    # OpenAI-style error envelope, same as every other route in this app.
    assert "http" in r.json()["error"]["message"]


async def test_rejects_malformed_provider_id(authed_client):
    """Provider ids end up inside litellm model strings, so characters that
    would produce an unaddressable model name are refused up front."""
    r = await authed_client.put("/v1/providers/bad!name", json={"api_key": "sk-x"})
    assert r.status_code == 422
    assert "lowercase" in r.json()["error"]["message"]


async def test_accepts_dashes_and_digits_in_provider_id(authed_client):
    await authed_client.put("/v1/providers/my-gateway-2", json={"api_key": "sk-x"})
    listing = await authed_client.get("/v1/providers")
    assert [p["provider"] for p in listing.json()["providers"]] == ["my-gateway-2"]


async def test_provider_id_is_lowercased(authed_client):
    """"OpenAI" and "openai" must not become two rows."""
    await authed_client.put("/v1/providers/OpenAI", json={"api_key": "sk-x"})
    listing = await authed_client.get("/v1/providers")
    assert [p["provider"] for p in listing.json()["providers"]] == ["openai"]


async def test_omitted_api_base_leaves_existing_value_untouched(authed_client):
    """A client that only knows `api_key` must not wipe a configured endpoint."""
    await authed_client.put(
        "/v1/providers/gw",
        json={"api_key": "sk-1", "api_base": "https://gw.example.com/v1"},
    )
    r = await authed_client.put("/v1/providers/gw", json={"api_key": "sk-2"})
    assert r.status_code == 200, r.text
    assert r.json()["api_base"] == "https://gw.example.com/v1"


async def test_explicit_null_clears_api_base(authed_client):
    """...while an explicit null is how you go back to the vendor default."""
    await authed_client.put(
        "/v1/providers/gw",
        json={"api_key": "sk-1", "api_base": "https://gw.example.com/v1"},
    )
    r = await authed_client.put(
        "/v1/providers/gw", json={"api_key": "sk-2", "api_base": None}
    )
    assert r.status_code == 200, r.text
    assert r.json()["api_base"] is None


async def test_refresh_requires_a_custom_base(authed_client):
    """A catalog-driven provider has nothing to scan."""
    await authed_client.put("/v1/providers/openai", json={"api_key": "sk-x"})
    r = await authed_client.post("/v1/providers/openai/refresh-models")
    assert r.status_code == 409


async def test_refresh_reports_a_failing_gateway(authed_client, monkeypatch):
    from app import model_discovery

    async def _boom(*, base_url, api_key):
        raise RuntimeError("connect timeout")

    # Patched at the module: both the refresh endpoint and the router build's
    # discovery resolve fetch_models there.
    monkeypatch.setattr(model_discovery, "fetch_models", _boom)

    await authed_client.put(
        "/v1/providers/gw",
        json={"api_key": "sk-x", "api_base": "https://gw.example.com/v1"},
    )
    r = await authed_client.post("/v1/providers/gw/refresh-models")
    assert r.status_code == 502
    assert "connect timeout" in r.json()["error"]["message"]


async def test_refresh_publishes_discovered_models(authed_client, monkeypatch):
    """A successful scan shows up in the client-facing model list — and is
    the ONLY thing there: the listing is deployed models, and nothing else
    is configured in this test's workspace."""
    from app import model_discovery

    async def _fake(*, base_url, api_key):
        return ["gw-model-a", "gw-model-b"]

    monkeypatch.setattr(model_discovery, "fetch_models", _fake)

    await authed_client.put(
        "/v1/providers/gw",
        json={"api_key": "sk-x", "api_base": "https://gw.example.com/v1"},
    )
    r = await authed_client.post("/v1/providers/gw/refresh-models")
    assert r.status_code == 200, r.text
    assert r.json() == {
        "provider": "gw",
        "api_base": "https://gw.example.com/v1",
        "models": ["gw-model-a", "gw-model-b"],
        "count": 2,
    }

    listing = await authed_client.get("/v1/models")
    data = listing.json()["data"]
    ids = {m["id"] for m in data}
    assert ids == {"gw-model-a", "gw-model-b"}
    # And they're attributed to the gateway, not to some vendor.
    owned = {m["id"]: m["owned_by"] for m in data}
    assert owned["gw-model-a"] == "gw"


async def test_refresh_unknown_provider_is_404(authed_client):
    r = await authed_client.post("/v1/providers/nope/refresh-models")
    assert r.status_code == 404
