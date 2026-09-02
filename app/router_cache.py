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
from packages.litellm_adapter.catalog import models_for_provider
from packages.litellm_adapter.hosted_catalog import (
    HOSTED_MODEL_ALIASES,
    HOSTED_MODELS,
)
from packages.litellm_adapter.types import ProviderDeployment

if TYPE_CHECKING:
    from app.config import Settings
    from packages.db.models.provider_key import ProviderKey


HOSTED_PROVIDER_NAME = "orcarouter"

# Wire protocol assumed for an endpoint whose provider litellm has never heard
# of. "OpenAI-compatible" is what effectively every third-party gateway,
# self-hosted runtime and regional mirror implements, so it is both the
# highest-hit-rate guess and the one an operator can override with
# `custom_llm_provider` when it's wrong.
_DEFAULT_CUSTOM_PROTOCOL = "openai/"


class CustomEndpoint:
    """A provider routed to a non-default base URL, with its resolved key."""

    __slots__ = ("provider", "api_base", "protocol", "api_key")

    def __init__(
        self, provider: str, api_base: str, protocol: str | None, api_key: str
    ) -> None:
        self.provider = provider
        self.api_base = api_base
        # None = "derive it" (catalog prefix if known, else openai/).
        self.protocol = protocol
        self.api_key = api_key


def _normalize_protocol(protocol: str) -> str:
    """`openai` → `openai/`; `anthropic/` → `anthropic/`."""
    return protocol if protocol.endswith("/") else protocol + "/"


def resolve_protocol(
    provider: str, hint: str | None, catalog_models: list
) -> str:
    """Decide the litellm wire prefix for a provider's models.

    Precedence: explicit `custom_llm_provider` > the provider's catalog prefix
    (a known vendor keeps speaking its own protocol even through a proxy) >
    `openai/` for anything unknown.
    """
    if hint:
        return _normalize_protocol(hint)
    if catalog_models:
        return catalog_models[0].litellm_prefix
    return _DEFAULT_CUSTOM_PROTOCOL


def custom_endpoints(
    *,
    env_keys: dict[str, str],
    db_keys: list["ProviderKey"],
    settings: "Settings",
) -> dict[str, CustomEndpoint]:
    """Collect providers that point at a custom base URL.

    A provider qualifies when it resolved a key (DB > env) AND has an
    `api_base` from either a DB row or `<PROVIDER>_API_BASE` in env. DB
    wins over env on both key and base, mirroring the key precedence that
    every other part of the resolver uses.

    The hosted upstream is excluded: it has its own dedicated branch in
    `build_deployments` and its own setting, and letting a generic base
    override fork its configuration would silently change what "hosted
    fallback" means.
    """
    out: dict[str, CustomEndpoint] = {}

    for row in db_keys:
        if not row.is_enabled or row.is_deleted:
            continue
        if row.provider == HOSTED_PROVIDER_NAME:
            continue
        base = (getattr(row, "api_base", None) or "").strip()
        if not base:
            continue
        try:
            key = decrypt_credential(row.encrypted_key)
        except Exception:
            continue
        out[row.provider] = CustomEndpoint(
            provider=row.provider,
            api_base=base,
            protocol=getattr(row, "custom_llm_provider", None),
            api_key=key,
        )

    for provider, base in settings.env_provider_bases().items():
        if provider in out or provider == HOSTED_PROVIDER_NAME:
            continue
        key = env_keys.get(provider)
        if not key:
            # A base with no key is inert — nothing to authenticate with.
            continue
        out[provider] = CustomEndpoint(
            provider=provider, api_base=base, protocol=None, api_key=key
        )

    return out


def build_deployments(
    *,
    env_keys: dict[str, str],
    db_keys: list["ProviderKey"],
    settings: "Settings",
    custom_models: dict[str, list[str]] | None = None,
) -> list[ProviderDeployment]:
    """Assemble the deployment list from env vars + DB rows + hosted upstream.

    Precedence:
      1. DB provider keys (UI-edited, authoritative; encrypted at rest)
      2. Env vars for providers not present in DB
      3. Hosted-as-upstream (one entry per catalog model) — DB key > env key

    `custom_models` carries model IDs discovered from providers that point at
    a custom `api_base` (see `discover_custom_models`). It is injected rather
    than fetched here because discovery is async + network-bound, and this
    function's value is that it stays pure, synchronous, and cheap to test
    against a fixed deployment list.
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

    endpoints = custom_endpoints(
        env_keys=env_keys, db_keys=db_keys, settings=settings
    )
    custom_models = custom_models or {}

    # Step 1+2: provider keys (DB > env). The hosted "orcarouter" provider
    # has no rows in `models_for_provider`, so it's silently skipped here and
    # picked up in step 3.
    for provider, models in (
        (p, models_for_provider(p)) for p in {*db_provider_keys, *env_keys}
    ):
        api_key = db_provider_keys.get(provider) or env_keys.get(provider)
        if not api_key:
            continue

        endpoint = endpoints.get(provider)
        if endpoint is not None:
            prefix = resolve_protocol(provider, endpoint.protocol, models)
            # A custom endpoint either proxies a vendor we already know
            # (keep its catalog models — the whole point of proxying
            # "openai" is to keep serving the same model ids) or it's an
            # endpoint litellm has never heard of, in which case the only
            # model list that exists is the one we discovered from it.
            model_ids = [m.id for m in models] if models else custom_models.get(provider, [])
            for model_id in model_ids:
                deployments.append(
                    ProviderDeployment(
                        model_name=model_id,
                        litellm_model=f"{prefix}{model_id}",
                        api_key=api_key,
                        provider=provider,
                        api_base=endpoint.api_base,
                        custom_llm_provider=prefix.rstrip("/"),
                    )
                )
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

    # Step 3: hosted-as-upstream. DB-stored "orcarouter" key (set via the
    # dashboard's Hosted fallback CTA) overrides the env key, mirroring step
    # 1+2 precedence. Either source enables every catalog model as a hosted
    # deployment so the long tail of providers never errors with "no key."
    hosted_key = db_provider_keys.get(HOSTED_PROVIDER_NAME) or settings.orcarouter_api_key
    if hosted_key:
        for provider, bare_id in HOSTED_MODELS:
            wire_id = f"{provider}/{bare_id}"
            model_groups = [bare_id]
            if wire_id in HOSTED_MODEL_ALIASES:
                model_groups.append(wire_id)
            for model_group in model_groups:
                deployments.append(
                    ProviderDeployment(
                        model_name=model_group,
                        litellm_model=wire_id,
                        api_key=hosted_key,
                        api_base=settings.orcarouter_base_url,
                        provider=HOSTED_PROVIDER_NAME,
                        custom_llm_provider="openai",
                        extra_headers={"X-OrcaRouter-beta-usd": "response"},
                        # Both spellings are ONE upstream. LiteLLM derives a
                        # deployment id per entry, so without pinning it the
                        # two names carry independent cooldown/allowed-fails
                        # state: a dead upstream would be probed (and paid
                        # for) once per alias before each cooled down.
                        deployment_id=f"hosted::{wire_id}",
                    )
                )

    return deployments


async def discover_custom_models(
    *,
    env_keys: dict[str, str],
    db_keys: list["ProviderKey"],
    settings: "Settings",
    force_refresh: bool = False,
) -> dict[str, list[str]]:
    """Ask every custom endpoint what models it serves, and publish the answer.

    Only endpoints litellm has no catalog entry for need this: a proxy in
    front of a *known* vendor (say `openai` pointed at a corporate gateway)
    already has a model list and shouldn't pay a network round-trip for one.

    Side effect: publishes into `catalog.CUSTOM_CATALOG` so `GET /v1/models`
    lists what these endpoints actually serve. Kept out of `build_deployments`
    to preserve that function's purity.

    Never raises: a dead gateway yields no models for that provider while
    every other provider still routes.
    """
    from app.model_discovery import discover_provider_models
    from packages.litellm_adapter.catalog import (
        models_for_provider,
        sync_custom_provider_models,
    )

    endpoints = custom_endpoints(
        env_keys=env_keys, db_keys=db_keys, settings=settings
    )
    out: dict[str, list[str]] = {}

    for provider, endpoint in endpoints.items():
        prefix = resolve_protocol(provider, endpoint.protocol, [])
        if models_for_provider(provider):
            continue
        ids = await discover_provider_models(
            provider=provider,
            base_url=endpoint.api_base,
            api_key=endpoint.api_key,
            force_refresh=force_refresh,
        )
        # Publish the truthful list — including empty, so a gateway that went
        # away stops advertising models clients can no longer reach.
        sync_custom_provider_models(provider, ids, litellm_prefix=prefix)
        if ids:
            out[provider] = ids

    return out


def hosted_key_source(
    *, env_key: str | None, db_keys: list["ProviderKey"]
) -> str | None:
    """Return where the hosted upstream key came from, or None if unconfigured.

    Mirrors the precedence used by `build_deployments`: a DB row beats env,
    BUT only if the row's encrypted_key actually decrypts. A row whose
    ciphertext is corrupt (post-rotation, DB tampering) is silently dropped
    by `build_deployments`, so reporting it as "configured" here would tell
    the dashboard "Active" while requests still 503 on hosted models.
    """
    if HOSTED_PROVIDER_NAME in usable_providers_from_db(db_keys):
        return "dashboard"
    if env_key:
        return "env"
    return None


def usable_providers_from_db(db_keys: list["ProviderKey"]) -> set[str]:
    """Set of provider names whose DB-stored key actually decrypts.

    Single source of truth for "is this provider deployable from a DB row?"
    Used by `hosted_key_source` and `/v1/analytics/unreachable` so the
    dashboard's "configured providers" view stays in lockstep with what
    `build_deployments` will actually wire up. Without this, an
    undecryptable row (after `CREDENTIAL_ENCRYPTION_KEY` rotation) would
    falsely suppress models from the unreachable list while the router
    can't reach them either.
    """
    out: set[str] = set()
    for row in db_keys:
        if not row.is_enabled or row.is_deleted:
            continue
        try:
            decrypt_credential(row.encrypted_key)
        except Exception:
            continue
        out.add(row.provider)
    return out


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
        env_keys = settings.env_provider_keys()
        # Discover custom-endpoint model lists BEFORE assembling deployments:
        # the deployment list for an unknown provider IS its discovery result.
        custom_models = await discover_custom_models(
            env_keys=env_keys, db_keys=list(rows), settings=settings
        )
        deployments = build_deployments(
            env_keys=env_keys,
            db_keys=list(rows),
            settings=settings,
            custom_models=custom_models,
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
            # Wire LiteLLM Router built-ins from settings so a deployment
            # that 404s once stays cooled down (no immediate re-pick), and
            # the cascade engine has policy for which errors fail fast.
            cooldown_time=float(settings.router_cooldown_seconds),
            allowed_fails=settings.router_allowed_fails,
            enable_pre_call_checks=settings.router_pre_call_checks,
            num_retries=settings.router_num_retries_default,
        )
        return _cached_client


def invalidate_router() -> None:
    """Drop the cached router so the next request rebuilds it."""
    global _cached_client
    _cached_client = None
