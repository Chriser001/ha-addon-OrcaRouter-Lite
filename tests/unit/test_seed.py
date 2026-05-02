"""Tests for first-run seed (workspace + API key bootstrap)."""

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


async def test_seed_creates_workspace_and_api_key(db_session):
    """First call creates one Workspace(id='default') and one sk-orca-* ApiKey."""
    from app.seed import seed_initial_state
    from packages.db.models.api_key import ApiKey
    from packages.db.models.workspace import Workspace

    result = await seed_initial_state(db_session)

    assert result.workspace_id == "default"
    assert result.api_key.startswith("sk-orca-")
    assert len(result.api_key) >= 32
    assert result.created is True

    ws_count = (await db_session.execute(select(Workspace))).scalars().all()
    assert len(ws_count) == 1
    assert ws_count[0].id == "default"

    keys = (await db_session.execute(select(ApiKey))).scalars().all()
    assert len(keys) == 1
    assert keys[0].workspace_id == "default"
    # The DB only stores the hash; the plaintext is returned to the caller once.
    assert not keys[0].key_hash.startswith("sk-orca-")


async def test_seed_is_idempotent(db_session):
    """Calling seed twice is safe — no duplicate workspace, no new key."""
    from app.seed import seed_initial_state
    from packages.db.models.api_key import ApiKey
    from packages.db.models.workspace import Workspace

    first = await seed_initial_state(db_session)
    second = await seed_initial_state(db_session)

    assert first.created is True
    assert second.created is False
    assert second.api_key is None  # plaintext only returned on first creation

    workspaces = (await db_session.execute(select(Workspace))).scalars().all()
    keys = (await db_session.execute(select(ApiKey))).scalars().all()

    assert len(workspaces) == 1
    assert len(keys) == 1


async def test_seed_creates_default_routing_config(db_session):
    """A RoutingConfig row is created alongside the workspace."""
    from app.seed import seed_initial_state
    from packages.db.models.routing_config import RoutingConfig

    await seed_initial_state(db_session)

    cfg = (await db_session.execute(select(RoutingConfig))).scalars().all()
    assert len(cfg) == 1
    assert cfg[0].workspace_id == "default"
    assert cfg[0].strategy == "balanced"
