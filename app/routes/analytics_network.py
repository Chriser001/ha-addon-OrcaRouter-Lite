"""Network analytics — the search/fetch fork of `/v1/analytics/*`.

Same shape as the LLM analytics (percentiles from raw samples, per-provider
buckets, a recent-requests table) but over `network_requests_log`: no tokens,
no cost, and an extra axis the LLM side has no equivalent of — which provider
actually served each request, and how much of each free-tier allowance is
left.

`_percentile` is imported from the LLM analytics rather than copied: the
dashboard re-implements the same nearest-rank + banker's-rounding algorithm
client-side, and a second divergent copy here would make the two pages
disagree about the same number.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app._time_util import iso_utc
from app.config import get_settings
from app.deps import get_db, get_key_context
from app.routes.analytics import _percentile
from packages.auth.types import KeyContext
from packages.db.models.network_provider import NetworkProvider
from packages.db.models.network_request_log import NetworkRequestLog

router = APIRouter(prefix="/v1/analytics/network", tags=["network-analytics"])


def _cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _validate_kind(kind: str | None) -> str | None:
    if kind is None:
        return None
    kind = kind.strip().lower()
    if kind not in ("search", "fetch"):
        raise HTTPException(status_code=422, detail="kind must be 'search' or 'fetch'")
    return kind


@router.get("/summary")
async def network_summary(
    days: int = Query(7, ge=1, le=365),
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Headline numbers for the network analytics page."""
    cutoff = _cutoff(days)
    rows = (
        await db.execute(
            select(
                NetworkRequestLog.kind,
                NetworkRequestLog.latency_ms,
                NetworkRequestLog.status_code,
                NetworkRequestLog.provider,
            ).where(
                NetworkRequestLog.is_deleted == 0,
                NetworkRequestLog.created_at >= cutoff,
            )
        )
    ).all()

    total = len(rows)
    ok = sum(1 for r in rows if (r.status_code or 0) < 400)
    samples = [int(r.latency_ms or 0) for r in rows]
    by_kind: dict[str, dict] = {}
    for r in rows:
        bucket = by_kind.setdefault(
            r.kind, {"kind": r.kind, "request_count": 0, "success_count": 0, "latencies": []}
        )
        bucket["request_count"] += 1
        if (r.status_code or 0) < 400:
            bucket["success_count"] += 1
        bucket["latencies"].append(int(r.latency_ms or 0))

    return {
        "days": days,
        "request_count": total,
        "success_count": ok,
        "error_count": total - ok,
        "success_percent": round(100 * ok / total, 1) if total else 0,
        "p50_ms": _percentile(samples, 0.5),
        "p99_ms": _percentile(samples, 0.99),
        "active_providers": len({r.provider for r in rows if r.provider != "none"}),
        "by_kind": [
            {
                "kind": k,
                "request_count": v["request_count"],
                "success_count": v["success_count"],
                "p50_ms": _percentile(v["latencies"], 0.5),
            }
            for k, v in sorted(by_kind.items())
        ],
    }


@router.get("/recent")
async def network_recent(
    limit: int = Query(50, ge=1, le=500),
    kind: str | None = Query(None),
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    kind = _validate_kind(kind)
    stmt = select(NetworkRequestLog).where(NetworkRequestLog.is_deleted == 0)
    if kind:
        stmt = stmt.where(NetworkRequestLog.kind == kind)
    rows = (
        await db.execute(stmt.order_by(desc(NetworkRequestLog.created_at)).limit(limit))
    ).scalars().all()

    return {
        "count": len(rows),
        "items": [
            {
                "kind": r.kind,
                "provider": r.provider,
                "provider_requested": r.provider_requested,
                "strategy": r.strategy,
                # Fetch calls record only a host + count, never a body.
                "query": r.query,
                "url_count": r.url_count,
                "result_count": r.result_count,
                "latency_ms": r.latency_ms,
                "status_code": r.status_code,
                "error_type": r.error_type,
                "failover_from": r.failover_from,
                "created_at": iso_utc(r.created_at),
            }
            for r in rows
        ],
    }


@router.get("/usage")
async def network_usage(
    days: int = Query(7, ge=1, le=365),
    kind: str | None = Query(None),
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Per-provider request counts, success rate and latency percentiles."""
    kind = _validate_kind(kind)
    cutoff = _cutoff(days)
    stmt = select(
        NetworkRequestLog.provider,
        NetworkRequestLog.latency_ms,
        NetworkRequestLog.status_code,
    ).where(
        NetworkRequestLog.is_deleted == 0,
        NetworkRequestLog.created_at >= cutoff,
    )
    if kind:
        stmt = stmt.where(NetworkRequestLog.kind == kind)

    rows = (await db.execute(stmt)).all()

    buckets: dict[str, list[tuple[int, int]]] = {}
    for prov, lat, status in rows:
        buckets.setdefault(prov or "none", []).append((int(lat or 0), int(status or 0)))

    by_provider = []
    for prov, samples in buckets.items():
        lats = [lat for lat, _ in samples]
        ok = sum(1 for _lat, status in samples if status < 400)
        by_provider.append(
            {
                "provider": prov,
                "request_count": len(samples),
                "success_count": ok,
                "success_percent": round(100 * ok / len(samples), 1) if samples else 0,
                "p50_ms": _percentile(lats, 0.5),
                "p99_ms": _percentile(lats, 0.99),
            }
        )
    by_provider.sort(key=lambda r: -r["request_count"])
    return {"by_provider": by_provider, "days": days}


@router.get("/quota")
async def network_quota(
    _kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remaining free-tier allowance per provider.

    `remaining` is the fraction tracked locally from our own request log —
    none of these vendors expose a balance endpoint on the free tier, so this
    is our accounting, not theirs. Unmetered providers report `monthly: null`.
    """
    env_keys = get_settings().env_search_provider_keys()
    rows = (
        await db.execute(
            select(NetworkProvider).where(NetworkProvider.is_deleted == 0)
        )
    ).scalars().all()

    out = []
    for row in sorted(rows, key=lambda r: r.provider):
        monthly = row.monthly_quota
        used = row.monthly_used or 0
        out.append(
            {
                "provider": row.provider,
                "monthly": monthly,
                "used": used,
                "remaining": max(0, monthly - used) if monthly else None,
                "remaining_percent": (
                    round(100 * max(0, monthly - used) / monthly, 1) if monthly else None
                ),
                "resets_at": iso_utc(row.quota_reset_at),
                "is_enabled": row.is_enabled,
                # Env-set keys are read-only here — same rule as the LLM
                # provider list: env config lives in env.
                "key_source": "env" if (env_keys.get(row.provider) and not row.encrypted_key) else ("db" if row.encrypted_key else None),
            }
        )
    return {"providers": out}
