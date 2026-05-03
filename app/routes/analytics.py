"""Analytics routes — recent requests, spend, latency, savings, unreachable models."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import get_db, get_key_context
from app.router_cache import HOSTED_PROVIDER_NAME, hosted_key_source, usable_providers_from_db
from packages.auth.types import KeyContext
from packages.db.models.provider_key import ProviderKey
from packages.db.models.request_log import RequestLog

router = APIRouter(prefix="/v1/analytics", tags=["analytics"])

# Curated "promote me" list for the unreachable-models tile. The full catalog
# is 100+ models; surfacing all of them buries the conversion message. These
# are the flagship/popular IDs developers actually wish they had keys for.
# Order matters — first one in this list that's unreachable is shown first.
_PROMOTED_MODEL_IDS: tuple[str, ...] = (
    "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-latest",
    "claude-3-opus-latest",
    "gpt-4o",
    "gpt-4o-mini",
    "o1",
    "o1-mini",
    "o3-mini",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "deepseek-chat",
    "deepseek-reasoner",
    "mistral-large-latest",
    "command-r-plus",
    "llama-3.1-405b-instruct",
    "llama-3.3-70b-versatile",
    "grok-2-latest",
)


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(round((len(s) - 1) * pct))))
    return s[idx]


@router.get("/recent")
async def recent_requests(
    limit: int = Query(100, ge=1, le=1000),
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            select(RequestLog)
            .where(RequestLog.is_deleted == 0)
            .order_by(desc(RequestLog.created_at))
            .limit(limit)
        )
    ).scalars().all()

    items = [
        {
            "trace_id": r.trace_id,
            "model_requested": r.model_requested,
            "model_resolved": r.model_resolved,
            "provider": r.provider,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cost_microcents": r.cost_microcents,
            "latency_ms": r.latency_ms,
            "status_code": r.status_code,
            "error_type": r.error_type,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return {"count": len(items), "items": items}


@router.get("/spend")
async def spend_by_model(
    days: int = Query(7, ge=1, le=365),
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await db.execute(
            select(
                RequestLog.model_resolved,
                func.sum(RequestLog.cost_microcents).label("cost"),
                func.count().label("count"),
            )
            .where(RequestLog.is_deleted == 0, RequestLog.created_at >= cutoff)
            .group_by(RequestLog.model_resolved)
            .order_by(desc("cost"))
        )
    ).all()

    by_model = [
        {"model": model, "cost_microcents": int(cost or 0), "request_count": count}
        for model, cost, count in rows
    ]
    total = sum(row["cost_microcents"] for row in by_model)
    return {"total_microcents": total, "by_model": by_model, "days": days}


@router.get("/latency")
async def latency_by_provider(
    days: int = Query(7, ge=1, le=365),
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await db.execute(
            select(RequestLog.provider, RequestLog.latency_ms)
            .where(RequestLog.is_deleted == 0, RequestLog.created_at >= cutoff)
        )
    ).all()

    bucket: dict[str, list[int]] = {}
    for prov, lat in rows:
        bucket.setdefault(prov, []).append(int(lat))

    result = [
        {
            "provider": prov,
            "request_count": len(samples),
            "p50_ms": _percentile(samples, 0.5),
            "p99_ms": _percentile(samples, 0.99),
        }
        for prov, samples in bucket.items()
    ]
    result.sort(key=lambda r: -r["request_count"])
    return {"by_provider": result, "days": days}


@router.get("/savings")
async def savings_vs_baseline(
    days: int = Query(7, ge=1, le=365),
    baseline: str = Query("gpt-4o"),
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """What would these requests have cost on `baseline` instead?

    Powers the dashboard's "you saved $X by routing" tile. The baseline
    must be a known catalog model (default: gpt-4o).

    Also returns a `hosted_auto` row: per-request, what would the cheapest
    catalog model with the *same capability set* as the resolved model have
    cost? That's the upper bound on additional savings the hosted-auto
    router could unlock by reaching models the user has no local key for.
    Conservative — assumes the resolved model's capabilities are required.
    """
    from packages.litellm_adapter.catalog import CATALOG, CATALOG_BY_ID

    baseline_model = CATALOG_BY_ID.get(baseline)
    if baseline_model is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown baseline model: {baseline}",
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await db.execute(
            select(
                RequestLog.input_tokens,
                RequestLog.output_tokens,
                RequestLog.cost_microcents,
                RequestLog.model_resolved,
            )
            .where(
                RequestLog.is_deleted == 0,
                RequestLog.created_at >= cutoff,
                RequestLog.status_code < 400,
            )
        )
    ).all()

    actual_microcents = sum(int(c or 0) for _i, _o, c, _m in rows)
    # Per-token pricing in litellm is USD/token; convert to microcents
    # (1 USD = 1,000,000 microcents).
    baseline_microcents = sum(
        int(
            (i or 0) * baseline_model.input_cost_per_token * 1_000_000
            + (o or 0) * baseline_model.output_cost_per_token * 1_000_000
        )
        for i, o, _c, _m in rows
    )
    saved = max(0, baseline_microcents - actual_microcents)
    pct = (
        round(100 * saved / baseline_microcents, 1)
        if baseline_microcents
        else 0
    )

    hosted_auto = _hosted_auto_savings(rows, CATALOG, CATALOG_BY_ID)

    return {
        "baseline_model": baseline,
        "request_count": len(rows),
        "actual_microcents": actual_microcents,
        "baseline_microcents": baseline_microcents,
        "saved_microcents": saved,
        "savings_percent": pct,
        "hosted_auto": hosted_auto,
        "days": days,
    }


def _hosted_auto_savings(rows, catalog: list, catalog_by_id: dict) -> dict:
    """For each request, find the cheapest catalog model that meets the
    resolved model's capability set, and sum what it would have cost.

    Excludes rows whose resolved model isn't in the catalog (can't compare
    capabilities) and zero-priced catalog entries (likely placeholders).
    Savings are computed against the actual spend on COMPARABLE rows only —
    summing non-catalog spend into the baseline would falsely inflate the
    saved figure shown on the dashboard.
    """
    cheapest_cache: dict[str, object | None] = {}

    def _cheapest_for(actual_id: str):
        if actual_id in cheapest_cache:
            return cheapest_cache[actual_id]
        actual = catalog_by_id.get(actual_id)
        if actual is None:
            cheapest_cache[actual_id] = None
            return None
        eligible = [
            m for m in catalog
            if (not actual.supports_tools or m.supports_tools)
            and (not actual.supports_vision or m.supports_vision)
            and (not actual.supports_json_mode or m.supports_json_mode)
            and (m.input_cost_per_token + m.output_cost_per_token) > 0
        ]
        if not eligible:
            cheapest_cache[actual_id] = None
            return None
        # Same blended cost weighting used by app.auto_routing.choose_auto_model.
        chosen = min(
            eligible,
            key=lambda m: 0.3 * m.input_cost_per_token + 0.7 * m.output_cost_per_token,
        )
        cheapest_cache[actual_id] = chosen
        return chosen

    hosted_microcents = 0
    actual_comparable_microcents = 0
    counted = 0
    for i, o, c, model_resolved in rows:
        cheapest = _cheapest_for(model_resolved)
        if cheapest is None:
            continue
        actual_comparable_microcents += int(c or 0)
        hosted_microcents += int(
            (i or 0) * cheapest.input_cost_per_token * 1_000_000
            + (o or 0) * cheapest.output_cost_per_token * 1_000_000
        )
        counted += 1

    saved = max(0, actual_comparable_microcents - hosted_microcents)
    pct = (
        round(100 * saved / actual_comparable_microcents, 1)
        if actual_comparable_microcents
        else 0
    )
    return {
        "actual_microcents": hosted_microcents,
        "saved_microcents": saved,
        "savings_percent": pct,
        "comparable_request_count": counted,
    }


@router.get("/unreachable")
async def unreachable_models(
    limit: int = Query(10, ge=1, le=50),
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Flagship catalog models the user can't currently route to.

    A model is "unreachable" when neither (a) the user has a provider key
    for its provider, nor (b) hosted upstream is configured. Powers the
    dashboard's conversion tile that nudges Lite users to enable hosted
    fallback for free $5 credit.

    Returns the curated list intersected with what's actually unreachable,
    capped at `limit`. When hosted is configured, the list is empty —
    everything in the catalog is reachable via hosted.
    """
    from packages.litellm_adapter.catalog import CATALOG_BY_ID

    settings = get_settings()
    rows = (
        await db.execute(
            select(ProviderKey).where(ProviderKey.is_deleted == 0)
        )
    ).scalars().all()

    hosted = hosted_key_source(
        env_key=settings.orcarouter_api_key,
        db_keys=list(rows),
    )
    # Filter DB-set providers through the same decrypt check build_deployments
    # uses, so a corrupt encrypted_key doesn't falsely suppress models from
    # the unreachable list while the router still can't reach them.
    configured_providers: set[str] = {
        p for p in usable_providers_from_db(list(rows))
        if p != HOSTED_PROVIDER_NAME
    }
    for provider, key in settings.env_provider_keys().items():
        if key:
            configured_providers.add(provider)

    if hosted is not None:
        return {
            "hosted_configured": True,
            "configured_providers": sorted(configured_providers),
            "unreachable": [],
        }

    unreachable: list[dict] = []
    for model_id in _PROMOTED_MODEL_IDS:
        m = CATALOG_BY_ID.get(model_id)
        if m is None:
            continue
        if m.provider in configured_providers:
            continue
        unreachable.append(
            {
                "id": m.id,
                "provider": m.provider,
                "input_cost_per_token": m.input_cost_per_token,
                "output_cost_per_token": m.output_cost_per_token,
                "supports_tools": m.supports_tools,
                "supports_vision": m.supports_vision,
                "supports_json_mode": m.supports_json_mode,
            }
        )
        if len(unreachable) >= limit:
            break

    return {
        "hosted_configured": False,
        "configured_providers": sorted(configured_providers),
        "unreachable": unreachable,
    }
