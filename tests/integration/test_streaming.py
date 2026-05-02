"""Streaming chat completions — SSE format.

The OpenAI streaming protocol is `text/event-stream` with each chunk
encoded as `data: {json}\\n\\n` and a terminal `data: [DONE]\\n\\n`.
LiteLLM yields chunk objects; the lite chat handler must:
  - return StreamingResponse with the right content-type
  - serialize each chunk as SSE
  - emit the [DONE] sentinel
  - write the RequestLog AFTER the stream finishes (not before)
  - sum the streamed token usage onto the log row
"""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock

import pytest


def _chunks_from_sse(text: str) -> list[dict]:
    """Parse `data: {...}\\n\\n` SSE frames into a list of dicts (skipping [DONE])."""
    out = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: ") :]
        if payload.strip() == "[DONE]":
            continue
        out.append(json.loads(payload))
    return out


async def _stream_iter(chunks: list[dict]):
    """Async generator returning a sequence of chunk dicts, mimicking litellm."""
    for c in chunks:
        yield c


@pytest.fixture
async def stream_client(tmp_sqlite_url, monkeypatch):
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

    chunks = [
        {
            "id": "chatcmpl-1",
            "object": "chat.completion.chunk",
            "model": "gpt-4o-mini",
            "created": int(time.time()),
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": "Hello"},
                "finish_reason": None,
            }],
        },
        {
            "id": "chatcmpl-1",
            "object": "chat.completion.chunk",
            "model": "gpt-4o-mini",
            "created": int(time.time()),
            "choices": [{
                "index": 0,
                "delta": {"content": " world"},
                "finish_reason": None,
            }],
        },
        {
            "id": "chatcmpl-1",
            "object": "chat.completion.chunk",
            "model": "gpt-4o-mini",
            "created": int(time.time()),
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
            "_orca_meta": {"provider": "openai", "latency_ms": 12},
        },
    ]

    fake_client = AsyncMock()

    async def _acompletion_router(**kwargs):
        if kwargs.get("stream"):
            return _stream_iter(chunks)
        return {
            "id": "chatcmpl-1",
            "model": "gpt-4o-mini",
            "object": "chat.completion",
            "created": int(time.time()),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello world"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
            "_orca_meta": {"provider": "openai", "latency_ms": 12},
        }

    fake_client.acompletion = AsyncMock(side_effect=_acompletion_router)

    async def _fake_get_router(_session):
        return fake_client

    monkeypatch.setattr(router_cache, "get_router", _fake_get_router)

    from app.main import create_app
    app = create_app()

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://t",
        headers={"Authorization": f"Bearer {seed.api_key}"},
    ) as c:
        yield c, fake_client

    await engine.dispose()
    session_mod._session_factory = None


# ── tests ──

async def test_streaming_returns_sse_content_type(stream_client):
    client, _ = stream_client
    r = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")


async def test_streaming_emits_chunks_and_done_sentinel(stream_client):
    client, _ = stream_client
    r = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )
    body = r.text
    assert "data: [DONE]" in body
    chunks = _chunks_from_sse(body)
    assert len(chunks) == 3
    # Concatenated content matches non-streaming path
    deltas = [c["choices"][0].get("delta", {}).get("content", "") for c in chunks]
    assert "".join(d for d in deltas if d) == "Hello world"
    # Internal _orca_meta must NOT be exposed in the SSE stream
    assert "_orca_meta" not in body


async def test_streaming_writes_request_log_with_usage(stream_client):
    client, _ = stream_client
    r = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )
    # Drain the body so the streaming finally-block runs.
    _ = r.text

    from sqlalchemy import select

    from packages.db import session as session_mod
    from packages.db.models.request_log import RequestLog

    async with session_mod._session_factory() as s:
        rows = (await s.execute(select(RequestLog))).scalars().all()
    assert len(rows) == 1
    log = rows[0]
    assert log.is_streaming is True
    assert log.input_tokens == 4
    assert log.output_tokens == 2
    assert log.provider == "openai"
    assert log.status_code == 200


async def test_non_streaming_still_works_unchanged(stream_client):
    """Don't regress slice 7."""
    client, _ = stream_client
    r = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["choices"][0]["message"]["content"] == "Hello world"
