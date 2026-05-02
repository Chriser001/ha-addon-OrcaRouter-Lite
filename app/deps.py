"""Dependency injection helpers."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from packages.auth.types import KeyContext
from packages.db.session import get_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


def get_key_context(request: Request) -> KeyContext:
    """Pull the auth-middleware-attached KeyContext off scope.state."""
    state = request.scope.get("state") or {}
    if isinstance(state, dict):
        kc = state.get("key_context")
    else:
        kc = getattr(state, "key_context", None)
    if kc is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Authentication required")
    return kc
