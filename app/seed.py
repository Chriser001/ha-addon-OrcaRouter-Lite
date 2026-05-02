"""First-run seed: create the single workspace + API key.

Idempotent — calling twice is a no-op on the second invocation.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.auth.hashing import generate_api_key
from packages.db.models.api_key import ApiKey
from packages.db.models.routing_config import RoutingConfig
from packages.db.models.workspace import Workspace

DEFAULT_WORKSPACE_ID = "default"


@dataclass
class SeedResult:
    workspace_id: str
    api_key: str | None  # plaintext, returned once on first creation
    created: bool        # False if seed was a no-op (already initialised)


async def seed_initial_state(session: AsyncSession) -> SeedResult:
    """Ensure exactly one Workspace + RoutingConfig + ApiKey exist."""
    existing = await session.execute(
        select(Workspace).where(Workspace.id == DEFAULT_WORKSPACE_ID)
    )
    workspace = existing.scalar_one_or_none()

    if workspace is not None:
        return SeedResult(
            workspace_id=DEFAULT_WORKSPACE_ID,
            api_key=None,
            created=False,
        )

    workspace = Workspace(
        id=DEFAULT_WORKSPACE_ID,
        name="Default",
        slug="default",
    )
    session.add(workspace)

    session.add(
        RoutingConfig(
            workspace_id=DEFAULT_WORKSPACE_ID,
            strategy="balanced",
        )
    )

    full_key, key_hash, key_prefix = generate_api_key()
    session.add(
        ApiKey(
            workspace_id=DEFAULT_WORKSPACE_ID,
            name="default",
            key_hash=key_hash,
            key_prefix=key_prefix,
        )
    )

    await session.commit()

    return SeedResult(
        workspace_id=DEFAULT_WORKSPACE_ID,
        api_key=full_key,
        created=True,
    )
