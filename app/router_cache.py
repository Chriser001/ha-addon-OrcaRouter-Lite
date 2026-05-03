"""Router cache — single-workspace, single-router edition.

Replaces the SaaS edition's per-workspace LRU + Redis pub/sub invalidation with
a single cached `OrcaLiteLLMClient`. Rebuilt on demand when provider keys
change (callers invoke `invalidate_router()`).

`build_deployments()` is split out as pure-Python so it can be tested without
instantiating litellm.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from packages.auth.encryption import decrypt_credential
from packages.litellm_adapter.catalog import all_model_ids, models_for_provider
from packages.litellm_adapter.types import ProviderDeployment

if TYPE_CHECKING:
    from app.config import Settings
    from packages.db.models.provider_key import ProviderKey


HOSTED_PROVIDER_NAME = "orcarouter"


def build_deployments(
    *,
    env_keys: dict[str, str],
    db_keys: list["ProviderKey"],
    settings: "Settings",
) -> list[ProviderDeployment]:
    """Assemble the deployment list from env vars + DB rows + hosted upstream.

    Precedence:
      1. DB provider keys (UI-edited, authoritative; encrypted at rest)
      2. Env vars for providers not present in DB
      3. Hosted-as-upstream (one entry per known model) when ORCAROUTER_API_KEY set
    """
    deployments: list[ProviderDeployment] = []
    db_provider_keys: dict[str, str] = {}

    for row in db_keys:
        if not row.is_enabled or row.is_deleted:
            continue
        try:
            db_provider_keys[row.provider] = decrypt_credential(row.encrypted_key)
        except Exception:
            continue

    # Step 1+2: provider keys (DB > env)
    for provider, models in (
        (p, models_for_provider(p)) for p in {*db_provider_keys, *env_keys}
    ):
        api_key = db_provider_keys.get(provider) or env_keys.get(provider)
        if not api_key:
            continue
        for model in models:
            deployments.append(
                ProviderDeployment(
                    model_name=model.id,
                    litellm_model=f"{model.litellm_prefix}{model.id}",
                    api_key=api_key,
                    provider=provider,
                )
            )

    # Step 3: hosted-as-upstream
    if settings.orcarouter_api_key:
        for model_id in all_model_ids():
            deployments.append(
                ProviderDeployment(
                    model_name=model_id,
                    litellm_model=f"openai/{model_id}",
                    api_key=settings.orcarouter_api_key,
                    api_base=settings.orcarouter_base_url,
                    provider=HOSTED_PROVIDER_NAME,
                )
            )

    return deployments


# ── Cached router instance ────────────────────────────────────────────────

_cached_client: object | None = None
_cache_lock = asyncio.Lock()


async def get_router(session) -> object:
    """Return the cached OrcaLiteLLMClient, building it on first call.

    Imports `OrcaLiteLLMClient` lazily so unit tests of `build_deployments`
    don't drag in litellm.
    """
    global _cached_client
    if _cached_client is not None:
        return _cached_client
    async with _cache_lock:
        if _cached_client is not None:
            return _cached_client

        from sqlalchemy import select

        from app.auto_routing import litellm_routing_strategy
        from app.config import get_settings
        from app.seed import DEFAULT_WORKSPACE_ID
        from packages.db.models.provider_key import ProviderKey
        from packages.db.models.routing_config import RoutingConfig
        from packages.litellm_adapter.client import OrcaLiteLLMClient

        settings = get_settings()
        rows = (
            await session.execute(
                select(ProviderKey).where(ProviderKey.is_deleted == 0)
            )
        ).scalars().all()
        deployments = build_deployments(
            env_keys=settings.env_provider_keys(),
            db_keys=list(rows),
            settings=settings,
        )

        routing_row = (
            await session.execute(
                select(RoutingConfig).where(
                    RoutingConfig.workspace_id == DEFAULT_WORKSPACE_ID,
                    RoutingConfig.is_deleted == 0,
                )
            )
        ).scalar_one_or_none()
        strategy = routing_row.strategy if routing_row else "balanced"
        preferred_models = (
            list(routing_row.preferred_models or []) if routing_row else []
        )

        _cached_client = OrcaLiteLLMClient(
            deployments=deployments,
            strategy=strategy,
            preferred_models=preferred_models,
            litellm_routing_strategy=litellm_routing_strategy(strategy),
        )
        return _cached_client


def invalidate_router() -> None:
    """Drop the cached router so the next request rebuilds it."""
    global _cached_client
    _cached_client = None
