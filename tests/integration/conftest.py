"""Shared integration fixtures for orcarouter-lite.

`authed_client` is the booted app + an authenticated AsyncClient. It lives in
conftest so new route modules don't each reinvent it; test modules that need a
different setup (extra env, a second workspace) still define their own local
fixture, which shadows this one.
"""

from __future__ import annotations

import pytest


@pytest.fixture
async def authed_client(tmp_sqlite_url, monkeypatch, isolated_env):
    """A booted lite app + a TestClient carrying the seeded sk-orca-* key.

    `isolated_env` strips developer-set provider keys from the environment so
    "no provider configured" assertions aren't drowned out by whatever is in
    the developer's `.env`.
    """
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


@pytest.fixture
async def client_no_auth(tmp_sqlite_url, monkeypatch, isolated_env):
    """Same booted app as `authed_client`, but no credential attached — for
    middleware tests, which must see a 401 rather than a route response."""
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
        await seed_initial_state(s)

    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c

    await engine.dispose()
    session_mod._session_factory = None
