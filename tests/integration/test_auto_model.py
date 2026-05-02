"""End-to-end test: model="auto" resolves to a real model before routing."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
async def auto_client(tmp_sqlite_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", tmp_sqlite_url)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

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

    from app import router_cache
    router_cache.invalidate_router()

    captured: dict = {}

    async def _acompletion(**kwargs):
        captured["model"] = kwargs.get("model")
        return {
            "id": "x", "model": kwargs.get("model"),
            "object": "chat.completion", "created": int(time.time()),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "_orca_meta": {"provider": "openai", "latency_ms": 1},
        }

    fake = AsyncMock()
    fake.acompletion = AsyncMock(side_effect=_acompletion)
    # Expose the deployments so the resolver knows what's deployable
    fake._deployments = []

    async def _fake_get_router(_session):
        return fake

    monkeypatch.setattr(router_cache, "get_router", _fake_get_router)

    # Provide a real-ish list of deployments for the auto resolver.
    from packages.litellm_adapter.catalog import models_for_provider
    from packages.litellm_adapter.types import ProviderDeployment

    fake._deployments = [
        ProviderDeployment(
            model_name=m.id, litellm_model=f"{m.litellm_prefix}{m.id}",
            api_key="sk-test", provider="openai",
        )
        for m in models_for_provider("openai")
    ]

    from app.main import create_app
    app = create_app()

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://t",
        headers={"Authorization": f"Bearer {seed.api_key}"},
    ) as c:
        yield c, captured

    await engine.dispose()
    session_mod._session_factory = None


async def test_auto_resolves_to_a_real_model(auto_client):
    client, captured = auto_client
    r = await client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert r.status_code == 200
    # The resolver picked a concrete model from the OpenAI catalog
    assert captured["model"] != "auto"
    assert isinstance(captured["model"], str)
    assert captured["model"].startswith(("gpt-", "o1", "o3", "o4"))


async def test_auto_picks_vision_capable_for_image_input(auto_client):
    client, captured = auto_client
    await client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBOR..."}},
                ],
            }],
        },
    )
    # The model the resolver picks must support vision.
    from packages.litellm_adapter.catalog import CATALOG_BY_ID

    chosen = CATALOG_BY_ID.get(captured["model"])
    assert chosen is not None
    assert chosen.supports_vision is True


async def test_auto_response_reports_resolved_model_to_caller(auto_client):
    """The user-facing response shows what model "auto" resolved to."""
    client, captured = auto_client
    r = await client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert r.status_code == 200
    # The resolved model is exposed via OrcaRouter's `x-orca-resolved-model`
    # header so SDKs can log/display it without parsing the body.
    assert r.headers.get("x-orca-resolved-model") == captured["model"]


async def test_auto_returns_422_when_no_capable_model_is_deployable(tmp_sqlite_url, monkeypatch):
    """If no provider keys cover the required capabilities, surface a clear 422."""
    monkeypatch.setenv("DATABASE_URL", tmp_sqlite_url)
    # No OPENAI_API_KEY, no provider keys at all → nothing deployable.
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

    from app import router_cache
    router_cache.invalidate_router()
    fake = AsyncMock()
    fake.acompletion = AsyncMock()
    fake._deployments = []  # nothing deployable

    async def _fake_get_router(_session):
        return fake

    monkeypatch.setattr(router_cache, "get_router", _fake_get_router)

    from app.main import create_app
    app = create_app()

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://t",
        headers={"Authorization": f"Bearer {seed.api_key}"},
    ) as c:
        r = await c.post(
            "/v1/chat/completions",
            json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert r.status_code == 422
    assert "no deployable" in r.text.lower() or "no model" in r.text.lower()
    fake.acompletion.assert_not_awaited()

    await engine.dispose()
    session_mod._session_factory = None
