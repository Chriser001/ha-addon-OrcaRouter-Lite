"""Idempotent schema additions for databases created before a column existed.

Lite has no Alembic: `Base.metadata.create_all` in the lifespan handler is the
only schema bootstrap, and `create_all` creates *missing tables* but never
ALTERs an existing one. So every column added to a shipped model needs a
matching entry here, or an operator upgrading on an existing `orca.db` gets
`OperationalError: no such column: provider_keys.api_base` the moment the
router reads provider rows — i.e. on the very first chat request, not at
startup, which is the worst time to find out.

The rule this module enforces: **new columns on shipped tables are declared
twice** — once on the ORM model (for fresh databases) and once in
`_EXTRA_COLUMNS` below (for existing ones). Both are additive and nullable, so
running this against an up-to-date database is a no-op.

Deliberately not a general migration framework: lite is single-tenant and
additive-only. A real migration tool earns its keep when you need destructive
or data-transforming changes, which this project hasn't needed.
"""

from __future__ import annotations

import structlog
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.get_logger()

# (table, column, DDL type) for every column added after initial release.
# The DDL type must stay in sync with the ORM column — a mismatch here produces
# a database whose schema diverges from what the mapper expects on the next
# `create_all` of a fresh install.
_EXTRA_COLUMNS: tuple[tuple[str, str, str], ...] = (
    # Custom-endpoint support: route a provider to a self-hosted /
    # OpenAI-compatible base URL and discover its models at runtime, so adding
    # a third-party provider is configuration instead of a code change.
    ("provider_keys", "api_base", "VARCHAR(500)"),
    ("provider_keys", "custom_llm_provider", "VARCHAR(50)"),
)


def _sync(conn) -> None:
    """Add any missing columns. Runs inside `engine.begin()` (sync context)."""
    insp = inspect(conn)
    tables = set(insp.get_table_names())
    for table, column, ddl in _EXTRA_COLUMNS:
        if table not in tables:
            # Fresh database: create_all hasn't run yet, or the table is
            # managed elsewhere. Nothing to backfill.
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        if column in existing:
            continue
        # Literals only — `_EXTRA_COLUMNS` is a module constant, never
        # operator input, so there is no injection surface here.
        conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}'))
        logger.info("schema_column_added", table=table, column=column)


async def ensure_schema(engine: AsyncEngine) -> None:
    """Bring an existing database up to date with additive model changes.

    Safe to call on every startup: it inspects before altering and adds only
    columns that are absent. Must run AFTER `create_all` so that a brand-new
    database is a pure no-op (its tables already have every column).
    """
    async with engine.begin() as conn:
        await conn.run_sync(_sync)
