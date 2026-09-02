"""GET /v1/models — model listing.

One path, two protocols. The OpenAI envelope is the default; a request
carrying `anthropic-version` (which the official Anthropic SDK and Claude
Code always send, and no OpenAI client sends) gets the Anthropic envelope
instead, so `client.models.list()` works against the same base URL the
native /v1/messages surface lives on. The Gemini surface has its own
listing at GET /v1beta/models.

Both envelopes list **deployed** models — what this instance can actually
serve — rather than the full built-in catalog. Advertising 600+ models the
operator has no key for is how dashboards fill up with 503s on models that
were never reachable; what we serve IS what's deployed.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_key_context
from packages.auth.types import KeyContext
from packages.litellm_adapter.catalog import CatalogModel, find_model

router = APIRouter(prefix="/v1", tags=["models"])

# Anthropic's ModelInfo.created_at is an RFC 3339 release date. We don't
# track release dates, and the API documents the epoch as the value to
# use when the date is unknown.
_UNKNOWN_RELEASE = "1970-01-01T00:00:00Z"


async def deployed_models(db: AsyncSession) -> list[CatalogModel]:
    """One entry per model_group in the live router — the servable set.

    Derived from the router's deployments rather than the static catalog so
    the listing can't drift from reality in either direction:

      - a provider the operator never configured contributes nothing (its
        catalog models would only produce 503s), and
      - models discovered from a custom endpoint are listed even though no
        built-in catalog knows them.

    Uses the cached router, so on a steady-state instance this is a dict
    walk; on the first call after a config change it triggers the rebuild
    (and, for custom endpoints, discovery) — the same work a chat request
    would do anyway.
    """
    from app import router_cache

    client = await router_cache.get_router(db)
    out: list[CatalogModel] = []
    seen: set[str] = set()
    for d in getattr(client, "_deployments", []) or []:
        if d.model_name in seen:
            continue
        seen.add(d.model_name)
        m = find_model(d.model_name)
        if m is None:
            # Routable but metadata-less (a custom endpoint whose model list
            # changed between discovery and this call). Still listed — it IS
            # servable; capabilities/pricing are simply unknown.
            m = CatalogModel(id=d.model_name, provider=d.provider, litellm_prefix="")
        out.append(m)
    return out


def _anthropic_listing(models: list[CatalogModel]) -> dict:
    data = [
        {
            "type": "model",
            "id": m.id,
            "display_name": m.id,
            "created_at": _UNKNOWN_RELEASE,
        }
        for m in models
    ]
    return {
        "data": data,
        # The whole catalog is returned in one page, so pagination is a
        # constant: nothing follows this page.
        "has_more": False,
        "first_id": data[0]["id"] if data else None,
        "last_id": data[-1]["id"] if data else None,
    }


@router.get("/models")
async def list_models(
    request: Request,
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    models = await deployed_models(db)

    if "anthropic-version" in request.headers:
        return _anthropic_listing(models)

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
            for m in models
        ],
    }
