"""Analytics routes — recent requests, spend by model, latency by provider."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_key_context
from packages.auth.types import KeyContext
from packages.db.models.request_log import RequestLog

router = APIRouter(prefix="/v1/analytics", tags=["analytics"])


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
    must be a known catalog model (default: gpt-4o, the typical "I'd
    just use GPT-4o" comparison).
    """
    from packages.litellm_adapter.catalog import CATALOG_BY_ID

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
            )
            .where(
                RequestLog.is_deleted == 0,
                RequestLog.created_at >= cutoff,
                RequestLog.status_code < 400,
            )
        )
    ).all()

    actual_microcents = sum(int(c or 0) for _i, _o, c in rows)
    # Per-token pricing in litellm is USD/token; convert to microcents
    # (1 USD = 1,000,000 microcents).
    baseline_microcents = sum(
        int(
            (i or 0) * baseline_model.input_cost_per_token * 1_000_000
            + (o or 0) * baseline_model.output_cost_per_token * 1_000_000
        )
        for i, o, _c in rows
    )
    saved = max(0, baseline_microcents - actual_microcents)
    pct = (
        round(100 * saved / baseline_microcents, 1)
        if baseline_microcents
        else 0
    )

    return {
        "baseline_model": baseline,
        "request_count": len(rows),
        "actual_microcents": actual_microcents,
        "baseline_microcents": baseline_microcents,
        "saved_microcents": saved,
        "savings_percent": pct,
        "days": days,
    }
