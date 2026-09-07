"""First-run seed: create the single workspace + API key.

Idempotent — calling twice is a no-op on the second invocation.

Also seeds one `network_providers` row per aggregated search provider (see
`seed_network_providers`). That part runs on EVERY boot, not just first run:
providers added by a newer build have to appear in an existing install, and
the rows carry operator-mutable state (visibility / weight / enabled) that
must not be clobbered once set.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.auth.hashing import generate_api_key
from packages.db.models.api_key import ApiKey
from packages.db.models.network_provider import NetworkProvider
from packages.db.models.routing_config import RoutingConfig
from packages.db.models.workspace import Workspace

DEFAULT_WORKSPACE_ID = "default"


def _next_month_start(now: datetime) -> datetime:
    """First instant of the month after `now` (UTC) — the quota rollover marker."""
    year = now.year + (now.month // 12)
    month = now.month % 12 + 1
    return datetime(year, month, 1, tzinfo=timezone.utc)


@dataclass
class SeedResult:
    workspace_id: str
    api_key: str | None  # plaintext, returned once on first creation
    created: bool        # False if seed was a no-op (already initialised)


async def seed_network_providers(session: AsyncSession) -> int:
    """Ensure every registered network provider has a config row.

    Insert-only: an existing row is never touched, so an operator's
    visibility / weight / key survives restarts and upgrades. Rows for
    providers this build no longer knows about are left alone too — their
    config would come back if the operator ever downgrades.

    Returns the number of rows created.
    """
    # Imported lazily: the registry pulls in the provider adapters, which is
    # heavier than the first-run path needs when it's only creating a key.
    from app.network_providers import REGISTRY

    existing = {
        row[0]
        for row in (
            await session.execute(select(NetworkProvider.provider))
        ).all()
    }

    created = 0
    for spec in REGISTRY.values():
        if spec.id in existing:
            continue
        session.add(
            NetworkProvider(
                provider=spec.id,
                encrypted_key=None,
                key_prefix="",
                # Keyed providers start disabled: without a credential every
                # call would 401, so they must not be in the automatic pool.
                # Keyless ones are usable the moment the server boots.
                is_enabled=not spec.requires_key,
                weight=spec.default_weight,
                monthly_quota=spec.monthly_quota,
                monthly_used=0,
                # Set for every provider, metered or not: `monthly_used` is a
                # rolling monthly counter used by the network analytics page,
                # and it needs a reset marker to roll against.
                quota_reset_at=_next_month_start(datetime.now(timezone.utc)),
                success_count=0,
                failure_count=0,
            )
        )
        created += 1

    if created:
        await session.commit()
    return created


async def seed_initial_state(session: AsyncSession) -> SeedResult:
    """Ensure exactly one Workspace + RoutingConfig + ApiKey exist."""
    existing = await session.execute(
        select(Workspace).where(Workspace.id == DEFAULT_WORKSPACE_ID)
    )
    workspace = existing.scalar_one_or_none()

    if workspace is not None:
        # Workspace already seeded, but a provider added by a newer build
        # still needs its row — hence the unconditional call above.
        await seed_network_providers(session)
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
    await seed_network_providers(session)

    return SeedResult(
        workspace_id=DEFAULT_WORKSPACE_ID,
        api_key=full_key,
        created=True,
    )
