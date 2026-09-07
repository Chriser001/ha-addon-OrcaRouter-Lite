"""Network analytics — aggregation over `network_requests_log`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from packages.db.models.network_request_log import NetworkRequestLog


async def _seed_log(authed_client, rows: list[dict]) -> None:
    """Insert log rows directly — the analytics endpoints must be exercised
    against a known history, not whatever a live search happened to produce.

    Provider rows already exist (startup seeds one per registry entry), so
    quota tests UPDATE those rather than inserting a second row for the same
    provider id.
    """

    from packages.db import session as session_mod

    async with session_mod._session_factory() as s:
        for r in rows:
            s.add(NetworkRequestLog(**r))
        await s.commit()


async def _set_quota(authed_client, provider: str, **values) -> None:
    from sqlalchemy import select

    from packages.db import session as session_mod
    from packages.db.models.network_provider import NetworkProvider

    async with session_mod._session_factory() as s:
        row = (
            await s.execute(
                select(NetworkProvider).where(NetworkProvider.provider == provider)
            )
        ).scalar_one()
        for k, v in values.items():
            setattr(row, k, v)
        await s.commit()


def _log_row(**kw) -> dict:
    base = {
        "workspace_id": "default",
        "api_key_id": "k1",
        "kind": "search",
        "provider": "exa",
        "provider_requested": None,
        "strategy": "random",
        "query": "test",
        "url_count": 0,
        "result_count": 3,
        "latency_ms": 100,
        "status_code": 200,
        "error_type": None,
        "failover_from": None,
    }
    base.update(kw)
    return base


async def test_summary_aggregates_requests(authed_client):
    await _seed_log(
        authed_client,
        [
            _log_row(provider="exa", latency_ms=100, status_code=200),
            _log_row(provider="exa", latency_ms=300, status_code=200),
            _log_row(provider="exa", latency_ms=200, status_code=502, error_type="upstream_error"),
            _log_row(kind="fetch", provider="tavily", url_count=2, result_count=2, latency_ms=400),
        ],
    )
    r = await authed_client.get("/v1/analytics/network/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["request_count"] == 4
    assert body["success_count"] == 3
    assert body["error_count"] == 1
    assert body["success_percent"] == 75.0
    assert body["active_providers"] == 2
    assert body["p50_ms"] > 0

    kinds = {k["kind"]: k for k in body["by_kind"]}
    assert kinds["search"]["request_count"] == 3
    assert kinds["fetch"]["request_count"] == 1


async def test_summary_of_an_empty_window(authed_client):
    r = await authed_client.get("/v1/analytics/network/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["request_count"] == 0
    assert body["success_percent"] == 0
    assert body["p50_ms"] == 0


async def test_recent_supports_a_kind_filter(authed_client):
    await _seed_log(
        authed_client,
        [
            _log_row(kind="search", provider="exa"),
            # A fetch row carries no query — only a URL count.
            _log_row(kind="fetch", provider="tavily", url_count=1, result_count=1, query=None),
        ],
    )
    all_rows = (await authed_client.get("/v1/analytics/network/recent")).json()
    assert all_rows["count"] == 2

    fetch_only = (
        await authed_client.get("/v1/analytics/network/recent", params={"kind": "fetch"})
    ).json()
    assert fetch_only["count"] == 1
    assert fetch_only["items"][0]["kind"] == "fetch"
    # A fetch row must not carry a search query — bodies are never persisted.
    assert fetch_only["items"][0]["query"] is None

    bad = await authed_client.get("/v1/analytics/network/recent", params={"kind": "nope"})
    assert bad.status_code == 422


async def test_recent_surfaces_failover(authed_client):
    await _seed_log(
        authed_client,
        [_log_row(provider="parallel", provider_requested="exa",
                  failover_from="exa", strategy="explicit")],
    )
    items = (await authed_client.get("/v1/analytics/network/recent")).json()["items"]
    assert items[0]["failover_from"] == "exa"
    assert items[0]["provider_requested"] == "exa"


async def test_usage_buckets_by_provider(authed_client):
    await _seed_log(
        authed_client,
        [
            _log_row(provider="exa", latency_ms=100, status_code=200),
            _log_row(provider="exa", latency_ms=300, status_code=200),
            _log_row(provider="tavily", latency_ms=900, status_code=502),
        ],
    )
    r = await authed_client.get("/v1/analytics/network/usage")
    assert r.status_code == 200, r.text
    by_provider = {p["provider"]: p for p in r.json()["by_provider"]}
    assert by_provider["exa"]["request_count"] == 2
    assert by_provider["exa"]["success_percent"] == 100.0
    assert by_provider["exa"]["p50_ms"] == 100
    assert by_provider["tavily"]["success_percent"] == 0.0
    # Sorted by volume, descending — the busiest provider leads.
    assert r.json()["by_provider"][0]["provider"] == "exa"


async def test_usage_kind_filter(authed_client):
    await _seed_log(
        authed_client,
        [
            _log_row(kind="search", provider="exa"),
            _log_row(kind="fetch", provider="tavily", url_count=1),
        ],
    )
    r = await authed_client.get("/v1/analytics/network/usage", params={"kind": "search"})
    by_provider = {p["provider"] for p in r.json()["by_provider"]}
    assert by_provider == {"exa"}


async def test_quota_reports_local_accounting(authed_client):
    await _set_quota(authed_client, "tavily", monthly_quota=1000, monthly_used=137)
    await _set_quota(authed_client, "exa", monthly_quota=None, monthly_used=42)
    r = await authed_client.get("/v1/analytics/network/quota")
    assert r.status_code == 200, r.text
    by_provider = {p["provider"]: p for p in r.json()["providers"]}

    tav = by_provider["tavily"]
    assert tav["monthly"] == 1000
    assert tav["used"] == 137
    assert tav["remaining"] == 863
    assert tav["remaining_percent"] == 86.3

    # Unmetered (keyless) providers report nulls rather than a fake number.
    assert by_provider["exa"]["monthly"] is None
    assert by_provider["exa"]["remaining"] is None


async def test_analytics_requires_auth(client_no_auth):
    r = await client_no_auth.get("/v1/analytics/network/summary")
    assert r.status_code == 401


async def test_old_rows_are_excluded_from_the_window(authed_client):
    stale = _log_row(provider="exa")
    stale["created_at"] = datetime.now(timezone.utc) - timedelta(days=30)
    await _seed_log(authed_client, [stale])

    r = await authed_client.get("/v1/analytics/network/summary", params={"days": 7})
    assert r.json()["request_count"] == 0

    r2 = await authed_client.get("/v1/analytics/network/summary", params={"days": 60})
    assert r2.json()["request_count"] == 1
