"""Provider keys CRUD — BYOK credentials for upstream LLM providers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_key_context
from packages.auth.encryption import encrypt_credential
from packages.auth.types import KeyContext
from packages.db.models.provider_key import ProviderKey

router = APIRouter(prefix="/v1/providers", tags=["providers"])


class SetProviderKey(BaseModel):
    api_key: str
    label: str = "default"


class ProviderKeyOut(BaseModel):
    provider: str
    label: str
    key_prefix: str
    is_enabled: bool


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
    return {
        "providers": [
            ProviderKeyOut(
                provider=r.provider,
                label=r.label,
                key_prefix=r.key_prefix,
                is_enabled=r.is_enabled,
            ).model_dump()
            for r in rows
        ]
    }


@router.put("/{provider}")
async def set_provider_key(
    provider: str,
    body: SetProviderKey,
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not body.api_key.strip():
        raise HTTPException(status_code=422, detail="api_key cannot be empty")

    existing = (
        await db.execute(
            select(ProviderKey).where(
                ProviderKey.provider == provider,
                ProviderKey.is_deleted == 0,
            )
        )
    ).scalar_one_or_none()

    encrypted = encrypt_credential(body.api_key)
    prefix_visible = body.api_key[:8] + "..." + body.api_key[-4:] if len(body.api_key) > 12 else "..."

    if existing is not None:
        existing.encrypted_key = encrypted
        existing.key_prefix = prefix_visible
        existing.label = body.label
        existing.is_enabled = True
    else:
        existing = ProviderKey(
            provider=provider,
            encrypted_key=encrypted,
            key_prefix=prefix_visible,
            label=body.label,
        )
        db.add(existing)

    await db.commit()

    return ProviderKeyOut(
        provider=existing.provider,
        label=existing.label,
        key_prefix=existing.key_prefix,
        is_enabled=existing.is_enabled,
    ).model_dump()


@router.delete("/{provider}", status_code=204)
async def delete_provider_key(
    provider: str,
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> Response:
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

    row.is_deleted = 1
    await db.commit()
    return Response(status_code=204)
