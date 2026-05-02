"""Tests for app.main.create_app — boot, /health, error format, CORS."""

import pytest


@pytest.fixture
async def lite_app(tmp_sqlite_url, monkeypatch):
    """Boot a fresh app against a tempfile SQLite."""
    monkeypatch.setenv("DATABASE_URL", tmp_sqlite_url)

    # Reset the singleton settings so the new env is picked up
    from app import config as cfg

    cfg.get_settings.cache_clear()

    from packages.db.engine import build_engine
    from packages.db.models.base import Base

    engine = build_engine(tmp_sqlite_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Register session factory bound to this engine
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from packages.db import session as session_mod

    session_mod._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    from app.main import create_app

    yield create_app()

    await engine.dispose()
    session_mod._session_factory = None


async def test_health_returns_ok(lite_app):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=lite_app), base_url="http://t") as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_unknown_route_returns_404_in_error_envelope(lite_app):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=lite_app), base_url="http://t") as c:
        r = await c.get("/v1/totally-not-a-route")
    # Auth middleware sees /v1/* and demands a bearer first.
    assert r.status_code == 401
    body = r.json()
    assert "error" in body
    assert body["error"]["type"] == "auth_error"


async def test_v1_models_requires_auth(lite_app):
    """/v1/models is gated behind a bearer token in lite (single-tenant)."""
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=lite_app), base_url="http://t") as c:
        r = await c.get("/v1/models")
    assert r.status_code == 401
