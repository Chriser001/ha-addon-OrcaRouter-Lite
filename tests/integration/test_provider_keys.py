"""Provider keys CRUD — set/list/delete with at-rest encryption."""

import pytest


@pytest.fixture
async def authed_client(tmp_sqlite_url, monkeypatch):
    """A booted lite app + a TestClient with the seeded API key in its headers."""
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


async def test_list_returns_empty_initially(authed_client):
    r = await authed_client.get("/v1/providers")
    assert r.status_code == 200
    assert r.json() == {"providers": []}


async def test_set_provider_key_then_list(authed_client):
    r = await authed_client.put(
        "/v1/providers/openai",
        json={"api_key": "sk-test-12345"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "openai"
    assert r.json()["key_prefix"].startswith("sk-test-")
    # Plaintext must NOT round-trip through the response
    assert "sk-test-12345" not in r.text

    listing = await authed_client.get("/v1/providers")
    assert listing.status_code == 200
    rows = listing.json()["providers"]
    assert len(rows) == 1
    assert rows[0]["provider"] == "openai"
    assert rows[0]["is_enabled"] is True
    assert "encrypted_key" not in rows[0]
    assert "api_key" not in rows[0]


async def test_delete_provider_key(authed_client):
    await authed_client.put("/v1/providers/openai", json={"api_key": "sk-test"})

    r = await authed_client.delete("/v1/providers/openai")
    assert r.status_code == 204

    listing = await authed_client.get("/v1/providers")
    assert listing.json()["providers"] == []


async def test_overwrite_existing_key(authed_client):
    await authed_client.put("/v1/providers/openai", json={"api_key": "sk-old"})
    r = await authed_client.put("/v1/providers/openai", json={"api_key": "sk-new"})
    assert r.status_code == 200

    listing = await authed_client.get("/v1/providers")
    assert len(listing.json()["providers"]) == 1


async def test_provider_key_is_encrypted_at_rest(authed_client, tmp_sqlite_url):
    await authed_client.put("/v1/providers/openai", json={"api_key": "sk-secret-99"})

    # Read the raw row back through ORM and verify ciphertext != plaintext.
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from packages.auth.encryption import decrypt_credential
    from packages.db.engine import build_engine
    from packages.db.models.provider_key import ProviderKey

    engine = build_engine(tmp_sqlite_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        rows = (await s.execute(select(ProviderKey))).scalars().all()

    assert len(rows) == 1
    blob = rows[0].encrypted_key
    assert isinstance(blob, bytes)
    assert b"sk-secret-99" not in blob
    assert decrypt_credential(blob) == "sk-secret-99"
    await engine.dispose()
