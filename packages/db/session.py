"""Async session factory.

Yields a session per request — FastAPI Depends-friendly. Tests override
this in conftest with a session bound to a tempfile SQLite engine.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from packages.db.engine import get_engine

_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_session_factory(database_url: str) -> None:
    global _session_factory
    engine = get_engine(database_url)
    _session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if _session_factory is None:
        from app.config import get_settings

        init_session_factory(get_settings().database_url)
    assert _session_factory is not None
    async with _session_factory() as session:
        yield session
