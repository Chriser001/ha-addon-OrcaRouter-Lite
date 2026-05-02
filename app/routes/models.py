"""GET /v1/models — OpenAI-compatible model listing."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from app.deps import get_key_context
from packages.auth.types import KeyContext
from packages.litellm_adapter.catalog import CATALOG

router = APIRouter(prefix="/v1", tags=["models"])


@router.get("/models")
async def list_models(_kc: KeyContext = Depends(get_key_context)) -> dict:
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": m.id,
                "object": "model",
                "created": now,
                "owned_by": m.provider,
                "permission": [],
            }
            for m in CATALOG
        ],
    }
