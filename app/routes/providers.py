"""Provider keys CRUD — BYOK credentials for upstream LLM providers.

Single-tenant invariant: at most ONE active key per provider. Two
sources, both honored by the runtime router with DB taking precedence:

  1. DB rows in `provider_keys` (set via dashboard PUT, encrypted at rest).
  2. Environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.)
     loaded by `Settings` and exposed via `settings.env_provider_keys()`.

The list endpoint surfaces BOTH so operators can see what's actually
configured. Without that, an operator who set keys in `.env` would see
an empty providers page in the dashboard, assume nothing is wired up,
and either re-set keys (creating a confusing duplicate) or worry that
their `auto` chats are silently failing — when in reality the env-sourced
key is serving traffic just fine.

Env-sourced rows carry `source: "env"`. Editing an env entry from the
dashboard writes a new DB row (which then takes precedence — matches
the runtime resolver in `router_cache.py:58`). Deleting the DB row
falls back to the env value transparently. Env entries themselves
aren't deletable from this API; the operator must edit `.env` and
restart to remove an env-set key (12-factor: env config lives in env).

Delete is a HARD delete, not a soft tombstone. Reasoning:
  - BYOK keys aren't user data; there's no audit/recovery story.
  - Soft-delete + new-PUT historically created ghost rows: query
    filtered `is_deleted=0`, missed the tombstone, INSERT'd a new
    row, leaving N tombstones piled up forever.
  - Hard delete keeps the table at most 1 row per provider, matching
    the single-tenant 1-key-per-provider invariant.

Migration note: existing dev DBs may carry tombstones from before this
change. The PUT path opportunistically wipes them when an operator
sets a new key for the same provider.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cache_invalidation_bus, model_discovery
from app.config import get_settings
from app.deps import get_db, get_key_context
from app.router_cache import resolve_protocol, usable_providers_from_db
from packages.auth.encryption import decrypt_credential, encrypt_credential
from packages.auth.types import KeyContext
from packages.db.models.provider_key import ProviderKey
from packages.litellm_adapter.catalog import (
    models_for_provider,
    sync_custom_provider_models,
)

router = APIRouter(prefix="/v1/providers", tags=["providers"])


class SetProviderKey(BaseModel):
    api_key: str
    # Custom endpoint. Omitted = leave as-is; null / "" = clear (fall back to
    # the vendor's public endpoint). This distinction matters: an older client
    # that only ever sent `api_key` must not silently wipe a configured base.
    api_base: str | None = None
    # Wire protocol for that endpoint ("openai" for virtually every
    # OpenAI-compatible gateway). Omitted = leave as-is; null = clear.
    custom_llm_provider: str | None = None


class ProviderKeyOut(BaseModel):
    provider: str
    key_prefix: str
    is_enabled: bool
    # "db" = stored in provider_keys table (editable + deletable from dashboard)
    # "env" = loaded from .env / process env (read-only here; edit .env to change)
    source: str = "db"
    # Custom endpoint, or None when this provider uses the vendor's public URL
    # and its models come from litellm's catalog.
    api_base: str | None = None


# Sentinel for "the client did not send this field", distinct from None
# ("clear it"). Without it, a PUT from an older client that only knows
# `api_key` would wipe an endpoint the operator configured earlier.
_UNSET = object()

# Operator-supplied provider ids are now free text (that's the point of custom
# endpoints), so they get validated rather than trusted: ids end up inside
# litellm model strings, so slashes, spaces and quotes would produce model
# names no client can address.
_PROVIDER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,49}$")


def _normalize_provider_id(raw: str) -> str:
    """Lowercase + validate a provider id. Raises 422 on anything unusable."""
    provider = (raw or "").strip().lower()
    if not _PROVIDER_ID_RE.match(provider):
        raise HTTPException(
            status_code=422,
            detail=(
                "Provider id must be 1-50 characters of lowercase letters, "
                "digits, '.', '_' or '-' (e.g. 'openai', 'my-gateway')."
            ),
        )
    return provider


def _clean_base(raw: str | None) -> str | None:
    """Normalize and validate a base URL. Returns None for "not set".

    Rejects anything that isn't http(s) because a bare hostname here produces
    a URL that fails somewhere deep in litellm with an error that names
    neither the provider nor the field the operator actually got wrong.
    """
    if raw is None:
        return None
    value = raw.strip().rstrip("/")
    if not value:
        return None
    if not value.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=422,
            detail="api_base must start with http:// or https://",
        )
    return value


def _mask_key(api_key: str) -> str:
    """Display-safe key prefix. Long keys show first 8 + last 4; short
    keys show 2 + 2 to give the operator some hint of which account
    they're looking at without exposing enough to be useful as a credential."""
    if len(api_key) > 12:
        return api_key[:8] + "..." + api_key[-4:]
    if len(api_key) > 4:
        return api_key[:2] + "..." + api_key[-2:]
    return "..."


@router.get("")
async def list_providers(
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            select(ProviderKey).where(ProviderKey.is_deleted == 0)
        )
    ).scalars().all()

    # The runtime resolver (`router_cache.build_deployments`) only honors
    # a DB row when it's BOTH `is_enabled` AND its `encrypted_key` decrypts.
    # `usable_providers_from_db` already encodes that contract — reuse it
    # here so the listing's notion of "DB row authoritative" stays in
    # lockstep with what actually serves traffic. Without this, a disabled
    # row or one with corrupt ciphertext (e.g. after a
    # CREDENTIAL_ENCRYPTION_KEY rotation) would suppress the env entry
    # in the dashboard while the runtime quietly falls back to env —
    # operators would see a "DB" source label but the env key is what's
    # actually authenticating their requests.
    usable_db = usable_providers_from_db(rows)

    out: list[dict] = []
    for r in rows:
        # Render every non-deleted DB row so operators still see disabled /
        # broken rows and can fix them. is_enabled flag tells the dashboard
        # to render appropriately; the env-suppression check below is the
        # part that depends on USABILITY, not just presence.
        out.append(
            ProviderKeyOut(
                provider=r.provider,
                key_prefix=r.key_prefix,
                is_enabled=r.is_enabled,
                source="db",
                api_base=r.api_base,
            ).model_dump()
        )

    env_bases = get_settings().env_provider_bases()

    # Surface env-configured keys the runtime is already using. DB takes
    # precedence ONLY when usable — matches the runtime resolver in
    # `router_cache.py:build_deployments` which silently skips disabled or
    # undecryptable rows and falls back to env. Suppressing env here based
    # on a non-usable DB row would lie to the operator about which
    # credential is actually authenticating their requests.
    for prov, raw_key in get_settings().env_provider_keys().items():
        if prov in usable_db:
            continue
        out.append(
            ProviderKeyOut(
                provider=prov,
                key_prefix=_mask_key(raw_key),
                is_enabled=True,
                source="env",
                api_base=env_bases.get(prov),
            ).model_dump()
        )

    return {"providers": out}


@router.put("/{provider}")
async def set_provider_key(
    provider: str,
    body: SetProviderKey,
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Custom providers mean the id is operator-supplied, not one of a fixed
    # set, so it gets validated instead of trusted. Lowercased for the same
    # reason env bases are: "OpenAI" and "openai" must not become two rows
    # that resolve to different deployments.
    provider = _normalize_provider_id(provider)
    if not body.api_key.strip():
        raise HTTPException(status_code=422, detail="api_key cannot be empty")

    # Omitted vs explicit-null matters: only touch the endpoint fields when
    # the client actually sent them, so a client that only knows `api_key`
    # can't wipe a configured base URL.
    if "api_base" in body.model_fields_set:
        api_base = _clean_base(body.api_base)
    else:
        api_base = _UNSET
    if "custom_llm_provider" in body.model_fields_set:
        protocol = (body.custom_llm_provider or "").strip() or None
    else:
        protocol = _UNSET

    # Wipe any soft-deleted ghost rows for this provider before upsert.
    # Migration aid: pre-PR dev DBs might carry tombstones from old soft-delete
    # behavior. Without this cleanup, the upsert query below — which filters
    # `is_deleted=0` — would miss the ghost and INSERT a new row, leaving
    # the tombstone piled up. After this PR, DELETE is a hard delete so no
    # new tombstones can form, but old ones still need scrubbing.
    await db.execute(
        sql_delete(ProviderKey).where(
            ProviderKey.provider == provider,
            ProviderKey.is_deleted == 1,
        )
    )

    existing = (
        await db.execute(
            select(ProviderKey).where(
                ProviderKey.provider == provider,
                ProviderKey.is_deleted == 0,
            )
        )
    ).scalar_one_or_none()

    encrypted = encrypt_credential(body.api_key)
    prefix_visible = _mask_key(body.api_key)

    if existing is not None:
        existing.encrypted_key = encrypted
        existing.key_prefix = prefix_visible
        existing.is_enabled = True
        if api_base is not _UNSET:
            existing.api_base = api_base
        if protocol is not _UNSET:
            existing.custom_llm_provider = protocol
    else:
        existing = ProviderKey(
            provider=provider,
            encrypted_key=encrypted,
            key_prefix=prefix_visible,
            api_base=None if api_base is _UNSET else api_base,
            custom_llm_provider=None if protocol is _UNSET else protocol,
        )
        db.add(existing)

    await db.commit()
    await cache_invalidation_bus.broadcast_router_cache_invalidation()

    return ProviderKeyOut(
        provider=existing.provider,
        key_prefix=existing.key_prefix,
        is_enabled=existing.is_enabled,
        source="db",
        api_base=existing.api_base,
    ).model_dump()


@router.delete("/{provider}", status_code=204)
async def delete_provider_key(
    provider: str,
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Hard-delete the DB row for this provider. After this, runtime
    resolution falls back to the env value (if `.env` has one) or
    treats the provider as unconfigured.

    Returns 204 even if no DB row existed — the operator's intent
    ('no DB-managed key for this provider') is satisfied either way.
    Removing an env-only entry isn't supported here: edit `.env` and
    restart the server (env config is file-managed by design).
    """
    provider = _normalize_provider_id(provider)
    result = await db.execute(
        sql_delete(ProviderKey).where(ProviderKey.provider == provider)
    )
    await db.commit()
    if result.rowcount == 0:
        # No DB row, but the operator may have meant the env-sourced one.
        # Surface the situation explicitly instead of silently 204'ing —
        # otherwise a dashboard "Remove" click on an env row appears to
        # succeed yet the key remains active on next page load.
        if provider in get_settings().env_provider_keys():
            raise HTTPException(
                status_code=409,
                detail=(
                    f"'{provider}' is configured via environment variable "
                    f"({provider.upper()}_API_KEY). Remove it from your .env "
                    f"and restart the server to deconfigure."
                ),
            )
        raise HTTPException(status_code=404, detail="Provider key not found")
    await cache_invalidation_bus.broadcast_router_cache_invalidation()
    return Response(status_code=204)


@router.post("/{provider}/refresh-models")
async def refresh_provider_models(
    provider: str,
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Re-list models from a custom endpoint and adopt the result.

    Discovery is lazy (it happens when the router is built), which means a
    gateway that was added while its own model catalog was still starting up
    would otherwise stay empty until the next router rebuild. This gives the
    dashboard a "Rescan" button — and, more importantly, reports *why* a scan
    fails (401, wrong URL, not OpenAI-compatible) instead of leaving the
    operator staring at an empty model list.
    """
    provider = _normalize_provider_id(provider)

    row = (
        await db.execute(
            select(ProviderKey).where(
                ProviderKey.provider == provider,
                ProviderKey.is_deleted == 0,
            )
        )
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="Provider key not found")
    if not row.api_base:
        raise HTTPException(
            status_code=409,
            detail=(
                f"'{provider}' has no custom base URL — its models come from "
                f"the built-in litellm catalog, so there is nothing to scan. "
                f"Set api_base to scan a custom endpoint."
            ),
        )

    try:
        api_key = decrypt_credential(row.encrypted_key)
    except Exception:
        raise HTTPException(
            status_code=422,
            detail="Stored key cannot be decrypted (encryption key rotated?)",
        ) from None

    try:
        ids = await model_discovery.fetch_models(base_url=row.api_base, api_key=api_key)
    except Exception as exc:
        # 502, not 503: this endpoint is reachable and answered — it just
        # didn't give us a model list we could trust.
        raise HTTPException(
            status_code=502,
            detail=f"Could not list models from {row.api_base}: {exc}",
        ) from exc

    prefix = resolve_protocol(
        provider, row.custom_llm_provider, models_for_provider(provider)
    )
    sync_custom_provider_models(provider, ids, litellm_prefix=prefix)
    # Reuse what we just fetched on the next router build.
    model_discovery.prime_cache(provider, row.api_base, ids)
    await cache_invalidation_bus.broadcast_router_cache_invalidation()

    return {
        "provider": provider,
        "api_base": row.api_base,
        "models": ids,
        "count": len(ids),
    }
