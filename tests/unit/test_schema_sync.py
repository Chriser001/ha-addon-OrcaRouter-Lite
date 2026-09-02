"""Additive schema sync for databases created before a column existed.

Lite has no migration runner: `create_all` creates missing tables but never
ALTERs an existing one. Without `ensure_schema`, an operator upgrading onto an
existing `orca.db` would hit "no such column: provider_keys.api_base" on the
first request that reads provider rows — long after startup, which is the
worst possible time to discover it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text

from packages.db.engine import build_engine
from packages.db.schema_sync import ensure_schema

# Minimal stand-in for the real table: only what's needed to prove the
# ALTER path adds the new columns and leaves existing data alone.
_CREATE_LEGACY = """
CREATE TABLE provider_keys (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    encrypted_key BLOB NOT NULL
)
"""


@pytest.fixture
async def legacy_db(tmp_sqlite_url):
    """A database in the shape an older release would have left behind."""
    engine = build_engine(tmp_sqlite_url)
    async with engine.begin() as conn:
        await conn.execute(text(_CREATE_LEGACY))
        await conn.execute(
            text("INSERT INTO provider_keys (id, provider, encrypted_key) "
                 "VALUES ('1', 'openai', X'00')")
        )
    yield engine
    await engine.dispose()


async def _columns(engine, table="provider_keys") -> set[str]:
    async with engine.begin() as conn:
        return await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns(table)}
        )


async def test_adds_missing_columns_to_an_existing_table(legacy_db):
    assert not {"api_base", "custom_llm_provider"} & await _columns(legacy_db)

    await ensure_schema(legacy_db)

    assert {"api_base", "custom_llm_provider"} <= await _columns(legacy_db)


async def test_preserves_existing_rows(legacy_db):
    """Schema sync is additive — it must never cost anyone their keys."""
    await ensure_schema(legacy_db)

    async with legacy_db.begin() as conn:
        rows = await conn.execute(text("SELECT provider FROM provider_keys"))
    assert [r[0] for r in rows] == ["openai"]


async def test_is_idempotent(legacy_db):
    await ensure_schema(legacy_db)
    await ensure_schema(legacy_db)
    assert {"api_base", "custom_llm_provider"} <= await _columns(legacy_db)


async def test_missing_table_is_not_fatal(tmp_sqlite_url):
    """A brand-new database: create_all hasn't run yet. Must not raise, and
    must not invent tables — that's create_all's job."""
    engine = build_engine(tmp_sqlite_url)
    try:
        await ensure_schema(engine)

        async with engine.begin() as conn:
            tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
        assert tables == set()
    finally:
        await engine.dispose()


async def test_noop_on_an_up_to_date_schema(tmp_sqlite_url):
    """The normal startup path: create_all already made every column."""
    from packages.db.models.base import Base

    engine = build_engine(tmp_sqlite_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        before = await _columns(engine)
        assert {"api_base", "custom_llm_provider"} <= before

        await ensure_schema(engine)
        assert await _columns(engine) == before
    finally:
        await engine.dispose()
