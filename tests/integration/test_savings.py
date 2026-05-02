"""Cost savings — what would these requests have cost on always-GPT-4?

The "you saved $X by routing" tile is the screenshotable, viral-friendly
output of the analytics pipeline. The math is simple — for each request,
multiply its actual tokens by the GPT-4 reference price, sum the deltas.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture
async def savings_client(tmp_sqlite_url, monkeypatch):
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

    # Seed 3 RequestLog rows with known token counts and known actual costs.
    # gpt-4o-mini → cheap, gpt-4o → mid, gemini-2.5-flash → cheaper than gpt-4o-mini
    from packages.db.models.request_log import RequestLog
    rows = [
        RequestLog(
            workspace_id="default", api_key_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            model_requested="auto", model_resolved="gpt-4o-mini",
            provider="openai", routing_strategy="balanced",
            input_tokens=1000, output_tokens=500,
            cost_microcents=int((1000 * 1.5e-7 + 500 * 6e-7) * 1_000_000),
            latency_ms=100, status_code=200,
        ),
        RequestLog(
            workspace_id="default", api_key_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            model_requested="auto", model_resolved="claude-3-5-haiku-latest",
            provider="anthropic", routing_strategy="balanced",
            input_tokens=2000, output_tokens=1000,
            cost_microcents=int((2000 * 8e-7 + 1000 * 4e-6) * 1_000_000),
            latency_ms=200, status_code=200,
        ),
        # Failed request — should be excluded from savings math.
        RequestLog(
            workspace_id="default", api_key_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            model_requested="auto", model_resolved="gpt-4o-mini",
            provider="openai", routing_strategy="balanced",
            input_tokens=0, output_tokens=0, cost_microcents=0,
            latency_ms=50, status_code=503, error_type="upstream_error",
        ),
    ]
    async with factory() as s:
        for r in rows:
            s.add(r)
        await s.commit()

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


async def test_savings_endpoint_returns_total_and_baseline(savings_client):
    r = await savings_client.get("/v1/analytics/savings?days=30&baseline=gpt-4o")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["baseline_model"] == "gpt-4o"
    assert "actual_microcents" in body
    assert "baseline_microcents" in body
    assert "saved_microcents" in body
    assert body["request_count"] == 2  # the failed row is excluded
    assert body["saved_microcents"] >= 0
    # Saved == baseline - actual; with cheap models routed against GPT-4o
    # baseline, savings must be substantial.
    assert body["saved_microcents"] == body["baseline_microcents"] - body["actual_microcents"]
    assert body["savings_percent"] > 50  # GPT-4o-mini is ~16x cheaper than GPT-4o


async def test_savings_endpoint_default_baseline_is_gpt_4o(savings_client):
    r = await savings_client.get("/v1/analytics/savings?days=30")
    assert r.status_code == 200
    assert r.json()["baseline_model"] == "gpt-4o"


async def test_savings_endpoint_rejects_unknown_baseline(savings_client):
    r = await savings_client.get("/v1/analytics/savings?days=30&baseline=not-a-model")
    assert r.status_code == 422


async def test_savings_endpoint_excludes_failed_requests(savings_client):
    """Failed requests had no real token usage; they shouldn't pad the savings."""
    r = await savings_client.get("/v1/analytics/savings?days=30")
    body = r.json()
    assert body["request_count"] == 2  # the 503 row excluded


async def test_savings_endpoint_handles_empty_history(tmp_sqlite_url, monkeypatch):
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
        r = await c.get("/v1/analytics/savings?days=30")

    assert r.status_code == 200
    body = r.json()
    assert body["request_count"] == 0
    assert body["saved_microcents"] == 0
    assert body["actual_microcents"] == 0
    assert body["savings_percent"] == 0

    await engine.dispose()
    session_mod._session_factory = None
