"""Aggregated web search / fetch surface (the "network" category).

Pools the free and free-tier vendors behind one request shape so a caller
never has to know which upstream answered:

    POST /v1/network/search  {"query": "...", "strategy": "quota"}
    POST /v1/network/fetch   {"urls": [...], "provider": "tavily"}

Selection is a single `provider` parameter (not one parameter per vendor);
vendor-specific knobs go in `params` and are validated against the schema the
listing endpoint publishes, so a typo 422s instead of being silently dropped.

`is_enabled` is the only per-provider switch: it drops a provider from the
automatic pool and rejects a pinned call. There is deliberately no separate
"hide" — an earlier build had one, and hiding a row also hid the only button
that could bring it back.
"""

from __future__ import annotations

import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import network_engine, network_providers
from app.config import get_settings
from app.deps import get_db, get_key_context
from packages.auth.encryption import decrypt_credential, encrypt_credential
from packages.auth.types import KeyContext
from packages.db.models.network_provider import NetworkProvider

router = APIRouter(prefix="/v1/network", tags=["network"])

_PROVIDER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,49}$")


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=512)
    # random | quota | latency | explicit
    strategy: str | None = None
    # Pin a specific provider. Requires strategy="explicit" — or just send
    # this field, which implies it.
    provider: str | None = None
    max_results: int = Field(default=network_providers.DEFAULT_MAX_RESULTS, ge=1, le=50)
    # Provider-specific knobs, validated per provider by the engine.
    params: dict | None = None
    timeout_ms: int = Field(default=network_providers.DEFAULT_TIMEOUT_MS, ge=1000, le=30_000)


class FetchRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=10)
    strategy: str | None = None
    provider: str | None = None
    params: dict | None = None
    timeout_ms: int = Field(default=network_providers.DEFAULT_TIMEOUT_MS, ge=1000, le=30_000)


class UpdateNetworkProvider(BaseModel):
    # Omitted = leave alone. "" = clear the credential.
    api_key: str | None = None
    is_enabled: bool | None = None
    weight: int | None = Field(default=None, ge=0, le=10_000)
    monthly_quota: int | None = Field(default=None, ge=0)


def _mask_key(api_key: str) -> str:
    """Display-safe prefix. Mirrors the LLM provider listing so both pages
    show the same shape of hint and neither leaks enough to be usable."""
    if len(api_key) > 12:
        return api_key[:8] + "..." + api_key[-4:]
    if len(api_key) > 4:
        return api_key[:2] + "..." + api_key[-2:]
    return "..."


def _normalize_provider_id(raw: str) -> str:
    provider = (raw or "").strip().lower()
    if not _PROVIDER_ID_RE.match(provider):
        raise HTTPException(
            status_code=422,
            detail="Provider id must be 1-50 characters of lowercase letters, digits, '.', '_' or '-'.",
        )
    return provider


async def _load_rows(db: AsyncSession) -> list[NetworkProvider]:
    return list(
        (
            await db.execute(
                select(NetworkProvider).where(NetworkProvider.is_deleted == 0)
            )
        ).scalars().all()
    )


def _row_key(row: NetworkProvider | None) -> str | None:
    if row is None or row.encrypted_key is None:
        return None
    try:
        return decrypt_credential(row.encrypted_key) or None
    except Exception:  # noqa: BLE001 — a rotated key shows as "not configured"
        return None


def _provider_out(row: NetworkProvider | None, env_keys: dict[str, str]) -> dict:
    """Render one provider: registry metadata + persisted config + live stats."""
    spec = network_providers.get_spec(row.provider)
    if spec is None:
        return None

    db_key = _row_key(row)
    env_key = env_keys.get(spec.id)
    effective_key = db_key or env_key

    quota_used = row.monthly_used or 0
    quota_monthly = row.monthly_quota
    remaining = None
    if quota_monthly:
        remaining = round(max(0.0, (quota_monthly - quota_used) / quota_monthly), 4)

    # "configured" answers "can this serve traffic right now", which for a
    # keyless vendor is yes by definition. `has_key` is the narrower question
    # the dashboard asks when rendering the credential column.
    return {
        "id": spec.id,
        "label": spec.label,
        "tier": spec.tier,
        "requires_key": spec.requires_key,
        "optional_key": spec.optional_key,
        "capabilities": sorted(spec.capabilities),
        "docs_url": spec.docs_url,
        "configured": (not spec.requires_key) or bool(effective_key),
        "has_key": bool(effective_key),
        # Whether a live balance can be pulled from the vendor (Tavily /usage).
        "supports_usage": spec.usage is not None,
        "limits": [limit.to_dict() for limit in spec.rate_limits],
        # "db" | "env" | None — which source is actually authenticating.
        "key_source": "db" if db_key else ("env" if env_key else None),
        "key_prefix": _mask_key(effective_key) if effective_key else None,
        "is_enabled": row.is_enabled,
        "weight": row.weight,
        "quota": {
            "monthly": quota_monthly,
            "used": quota_used,
            "remaining": remaining,
            "resets_at": row.quota_reset_at.isoformat() if row.quota_reset_at else None,
        },
        "avg_latency_ms": row.avg_latency_ms,
        "success_count": row.success_count or 0,
        "failure_count": row.failure_count or 0,
        "cooldown_until": row.cooldown_until.isoformat() if row.cooldown_until else None,
        "last_error": row.last_error,
        "search": {
            "params": [p.to_dict() for p in spec.search_params],
            "max_results": spec.max_results,
        },
        "fetch": {
            "params": [p.to_dict() for p in spec.fetch_params],
            "max_urls": spec.max_urls,
        },
    }


@router.get("/providers")
async def list_network_providers(
    capability: str | None = Query(None, description="Filter by 'search' or 'fetch'"),
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List every supported search/fetch provider with its parameter schema.

    The `params` arrays are what the dashboard renders its advanced-options
    form from — adding a vendor never requires a frontend change.
    """
    if capability is not None and capability not in ("search", "fetch"):
        raise HTTPException(
            status_code=422, detail="capability must be 'search' or 'fetch'"
        )

    env_keys = get_settings().env_search_provider_keys()
    rows = {r.provider: r for r in await _load_rows(db)}

    out = []
    for spec_id in sorted(network_providers.REGISTRY):
        row = rows.get(spec_id)
        if row is None:
            continue
        if capability and capability not in network_providers.REGISTRY[spec_id].capabilities:
            continue
        rendered = _provider_out(row, env_keys)
        if rendered is not None:
            out.append(rendered)

    return {
        "providers": out,
        "defaults": {
            "strategy": network_providers.DEFAULT_STRATEGY,
            "strategies": list(network_providers.STRATEGIES),
            "timeout_ms": network_providers.DEFAULT_TIMEOUT_MS,
            "max_results": network_providers.DEFAULT_MAX_RESULTS,
        },
    }


@router.put("/providers/{provider}")
async def update_network_provider(
    provider: str,
    body: UpdateNetworkProvider,
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Set a provider's credential and/or its selection settings.

    Omitted fields are left alone, so a client that only knows `api_key` can
    set a credential without resetting the operator's weight or visibility.
    """
    provider = _normalize_provider_id(provider)
    spec = network_providers.get_spec(provider)
    if spec is None:
        raise HTTPException(
            status_code=404,
            detail=f"'{provider}' is not a supported network provider. Known: {', '.join(network_providers.known_ids())}",
        )

    row = (
        await db.execute(
            select(NetworkProvider).where(
                NetworkProvider.provider == provider,
                NetworkProvider.is_deleted == 0,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Network provider not found")

    if "api_key" in body.model_fields_set:
        raw = (body.api_key or "").strip()
        if raw:
            row.encrypted_key = encrypt_credential(raw)
            row.key_prefix = _mask_key(raw)
            # Setting a credential implies you want it used — otherwise the
            # operator sets a key, sees no traffic, and files a bug.
            row.is_enabled = True
        else:
            row.encrypted_key = None
            row.key_prefix = ""
            if spec.requires_key:
                row.is_enabled = False

    if body.is_enabled is not None:
        if body.is_enabled and spec.requires_key and not _row_key(row) and not get_settings().env_search_provider_keys().get(provider):
            raise HTTPException(
                status_code=409,
                detail=f"'{provider}' needs an API key before it can be enabled.",
            )
        row.is_enabled = body.is_enabled
    if body.weight is not None:
        row.weight = body.weight
    if body.monthly_quota is not None:
        row.monthly_quota = body.monthly_quota or None

    await db.commit()
    return _provider_out(row, get_settings().env_search_provider_keys())


@router.post("/providers/{provider}/refresh-quota")
async def refresh_network_provider_quota(
    provider: str,
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Pull the provider's live balance from its vendor and adopt it locally.

    Local `monthly_used` only ever counts what THIS server sent, so it drifts
    the moment the same key is used anywhere else. Vendors that expose a
    balance endpoint (Tavily) can be re-synced here; the rest keep local
    accounting only, and the endpoint says so rather than pretending.
    """
    provider = _normalize_provider_id(provider)
    spec = network_providers.get_spec(provider)
    if spec is None:
        raise HTTPException(status_code=404, detail="Network provider not found")
    if spec.usage is None:
        raise HTTPException(
            status_code=409,
            detail=f"'{provider}' does not expose a live balance endpoint.",
        )

    env_keys = get_settings().env_search_provider_keys()
    row = (
        await db.execute(
            select(NetworkProvider).where(
                NetworkProvider.provider == provider,
                NetworkProvider.is_deleted == 0,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Network provider not found")

    api_key = network_engine.resolve_api_key(row, env_keys, spec)
    if not api_key:
        raise HTTPException(
            status_code=409,
            detail=f"'{provider}' needs an API key before its balance can be fetched.",
        )

    async with httpx.AsyncClient(follow_redirects=False) as client:
        try:
            snapshot = await spec.usage(client, api_key=api_key, timeout=10.0)
        except network_providers.ProviderError as exc:
            raise HTTPException(status_code=502, detail=f"{provider}: {exc}") from exc

    row.monthly_quota = snapshot["monthly"]
    row.monthly_used = snapshot["used"]
    row.last_error = None
    row.cooldown_until = None
    await db.commit()

    return {"provider": provider, "quota": _provider_out(row, env_keys)["quota"], **{
        k: v for k, v in snapshot.items() if k != "monthly"
    }}


@router.delete("/providers/{provider}", status_code=204)
async def reset_network_provider(
    provider: str,
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Clear a provider's stored credential and restore its defaults.

    Not a hard delete: startup re-seeds any missing row, so deleting it would
    just come back on the next restart with the defaults anyway. This makes
    that round-trip explicit and immediate.
    """
    provider = _normalize_provider_id(provider)
    spec = network_providers.get_spec(provider)
    if spec is None:
        raise HTTPException(status_code=404, detail="Network provider not found")

    row = (
        await db.execute(
            select(NetworkProvider).where(
                NetworkProvider.provider == provider,
                NetworkProvider.is_deleted == 0,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Network provider not found")

    row.encrypted_key = None
    row.key_prefix = ""
    row.monthly_used = 0
    row.last_error = None
    row.cooldown_until = None
    # keyed vendors become unusable without a credential, so take them out of
    # the pool; keyless ones stay enabled (they never needed the key).
    row.is_enabled = not spec.requires_key
    await db.commit()
    return Response(status_code=204)


def _unavailable_detail(exc: network_engine.NetworkUnavailable) -> str:
    """502 message naming every provider that was tried.

    Without the list, "all providers failed" is unactionable — the operator
    can't tell a bad query from six separate outages.
    """
    if not exc.attempts:
        return str(exc)
    return f"{exc} (tried: {', '.join(exc.attempts)})"


@router.post("/search")
async def network_search(
    body: SearchRequest,
    kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Search the web through whichever provider the strategy picks.

    `provider` implies strategy `explicit`. Everything else is ordered by the
    strategy and cascaded on failure; the provider that actually answered is
    in the response, along with `failover_from` when it wasn't the first pick.
    """
    strategy = body.strategy or ("explicit" if body.provider else None)
    rows = await _load_rows(db)
    env_keys = get_settings().env_search_provider_keys()

    async def _go():
        return await network_engine.run_search(
            db=db,
            workspace_id=kc.workspace_id,
            api_key_id=kc.key_id,
            rows=rows,
            env_keys=env_keys,
            query=body.query,
            strategy=strategy,
            provider=body.provider,
            max_results=body.max_results,
            params=body.params,
            timeout_ms=body.timeout_ms,
        )

    try:
        result = await _go()
    except network_engine.NetworkRequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except network_engine.NetworkUnavailable as exc:
        raise HTTPException(status_code=502, detail=_unavailable_detail(exc)) from exc

    return {
        "kind": "search",
        "query": body.query,
        "provider": result.provider,
        "strategy": result.strategy,
        "requested_provider": result.requested_provider,
        "failover_from": result.attempts,
        "errors": result.errors,
        "latency_ms": result.latency_ms,
        "count": len(result.payload),
        "results": result.payload,
    }


@router.post("/fetch")
async def network_fetch(
    body: FetchRequest,
    kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch page content for up to 10 URLs.

    Targets are checked against the SSRF blocklist before any upstream sees
    them. Results keep the per-URL contract: there is one entry per input URL,
    carrying either `content` or a non-empty `error`.
    """
    strategy = body.strategy or ("explicit" if body.provider else None)
    rows = await _load_rows(db)
    env_keys = get_settings().env_search_provider_keys()

    try:
        result = await network_engine.run_fetch(
            db=db,
            workspace_id=kc.workspace_id,
            api_key_id=kc.key_id,
            rows=rows,
            env_keys=env_keys,
            urls=body.urls,
            strategy=strategy,
            provider=body.provider,
            params=body.params,
            timeout_ms=body.timeout_ms,
        )
    except network_engine.NetworkRequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except network_engine.NetworkUnavailable as exc:
        raise HTTPException(status_code=502, detail=_unavailable_detail(exc)) from exc

    return {
        "kind": "fetch",
        "url_count": len(body.urls),
        "provider": result.provider,
        "strategy": result.strategy,
        "requested_provider": result.requested_provider,
        "failover_from": result.attempts,
        "errors": result.errors,
        "latency_ms": result.latency_ms,
        "count": len(result.payload),
        "results": result.payload,
    }
