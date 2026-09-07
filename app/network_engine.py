"""Selection + execution engine for the aggregated network surface.

Two responsibilities, kept out of the HTTP layer:

  1. `resolve_chain` — turn registry + DB config + strategy into an ordered
     fallback chain (pure, no I/O, exhaustively unit-testable).
  2. `run_search` / `run_fetch` — walk that chain, call upstreams serially,
     record per-provider stats and append a request log.

Serial failover is deliberate. Firing every provider at once and taking the
first answer would be faster, but these are free tiers: one search would burn
a credit at all six vendors, which defeats the point of pooling them.

Strategy semantics (exact sort keys in `resolve_order`):
  random   — weighted shuffle; spreads load across vendors over time.
  quota    — most remaining monthly allowance first; unmetered vendors last.
  latency  — lowest EWMA latency first; unproven vendors last.
  explicit — pinned provider first, then a weighted-random tail as insurance.
"""

from __future__ import annotations

import random
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
import structlog
from sqlalchemy import Integer, case, cast, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import network_providers, url_safety
from app.network_providers import (
    DEFAULT_MAX_RESULTS,
    DEFAULT_STRATEGY,
    DEFAULT_TIMEOUT_MS,
    STRATEGIES,
    ProviderError,
    ProviderParamError,
    ProviderSpec,
    coerce_params,
    get_spec,
)
from packages.db.models.network_provider import NetworkProvider
from packages.db.models.network_request_log import NetworkRequestLog

logger = structlog.get_logger()

# Total wall-clock budget for one aggregated call. Individual providers get
# `timeout_ms`; the budget stops a long chain from serialising five 8s
# timeouts into a 40-second request.
TOTAL_BUDGET_MS = 20_000

# How long a provider stays out of the automatic pool after a rate limit.
# Skipping only the current request isn't enough — the next one would walk
# straight back into the same 429.
COOLDOWN_SECONDS = 60

# EWMA weight for the newest latency sample: low enough that one slow call
# doesn't dominate, high enough to react within a handful of requests.
_LATENCY_ALPHA = 0.2

# Arbitrary-large stand-in for "no latency sample yet" so unproven providers
# sort last without needing a separate pass.
_UNKNOWN_LATENCY_MS = 10**9

MAX_QUERY_LEN = 512


class NetworkRequestError(ValueError):
    """The caller's request is unusable (bad params, unsafe URL, unknown provider).

    Surfaces as 4xx — trying another provider cannot help.
    """


class NetworkUnavailable(RuntimeError):
    """Every candidate provider failed, or none was eligible. Surfaces as 502."""

    def __init__(self, message: str, attempts: list[str]) -> None:
        super().__init__(message)
        self.attempts = attempts


@dataclass(frozen=True)
class Candidate:
    """A provider that may serve this request, plus the config driving selection."""

    spec: ProviderSpec
    api_key: str | None
    weight: int
    monthly_quota: int | None
    monthly_used: int
    avg_latency_ms: int | None
    success_count: int
    failure_count: int

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        if not total:
            # No history: neutral rather than 0, so unproven providers don't
            # all tie at the bottom in an order nobody can predict.
            return 0.5
        return self.success_count / total

    @property
    def quota_remaining(self) -> float | None:
        """Fraction of the monthly allowance left, or None when unmetered."""
        if not self.monthly_quota:
            return None
        return max(0.0, (self.monthly_quota - self.monthly_used) / self.monthly_quota)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _next_month_start(now: datetime) -> datetime:
    year = now.year + (now.month // 12)
    month = now.month % 12 + 1
    return datetime(year, month, 1, tzinfo=timezone.utc)


def _candidate_from_row(row: NetworkProvider, spec: ProviderSpec, env_keys: dict[str, str]) -> Candidate:
    return Candidate(
        spec=spec,
        api_key=resolve_api_key(row, env_keys, spec),
        weight=max(0, row.weight),
        monthly_quota=row.monthly_quota,
        monthly_used=row.monthly_used or 0,
        avg_latency_ms=row.avg_latency_ms,
        success_count=row.success_count or 0,
        failure_count=row.failure_count or 0,
    )


def resolve_api_key(row: NetworkProvider | None, env_keys: dict[str, str], spec: ProviderSpec) -> str | None:
    """DB row wins over env — same precedence the LLM resolver uses.

    A row whose ciphertext won't decrypt yields "no key" rather than raising:
    the provider drops out of the pool and shows up as not-configured, instead
    of every search 500ing because of one rotated credential.
    """
    if row is not None and row.encrypted_key is not None:
        try:
            from packages.auth.encryption import decrypt_credential

            key = decrypt_credential(row.encrypted_key)
        except Exception:  # noqa: BLE001 — rotated/garbled key must not stop routing
            logger.warning("network_key_decrypt_failed", provider=spec.id)
            return None
        if key:
            return key
    return env_keys.get(spec.id) or None


def _cooldown_active(row: NetworkProvider, now: datetime) -> bool:
    until = row.cooldown_until
    if until is None:
        return False
    return _as_utc(until) > now


def build_candidates(
    *,
    kind: str,
    rows: Sequence[NetworkProvider],
    env_keys: dict[str, str],
    now: datetime,
) -> list[Candidate]:
    """Every provider that could serve `kind` right now.

    Filters, in order: known to the registry, supports the operation, enabled,
    not cooled down, and — for keyed vendors — actually has a credential.
    """
    by_provider = {r.provider: r for r in rows}
    out: list[Candidate] = []

    for spec_id, spec in sorted(network_providers.REGISTRY.items()):
        if kind not in spec.capabilities:
            continue
        row = by_provider.get(spec_id)
        if row is None or row.is_deleted:
            continue
        if not row.is_enabled:
            continue
        if _cooldown_active(row, now):
            continue

        candidate = _candidate_from_row(row, spec, env_keys)
        if spec.requires_key and not candidate.api_key:
            continue
        out.append(candidate)
    return out


def resolve_order(candidates: list[Candidate], strategy: str) -> list[Candidate]:
    """Order `candidates` into a fallback chain, best first.

    Every strategy returns the FULL list — the tail isn't ranked for its own
    sake, it's what the next attempt uses when the head is throttled.
    """
    if not candidates:
        return []

    if strategy == "quota":
        # Metered vendors first, most-remaining first. Unmetered (keyless)
        # ones sort last so a monthly allowance gets spent before it expires —
        # routing everything at the free-and-unlimited vendors would leave the
        # metered free tier untouched and wasted at month end.
        return sorted(
            candidates,
            key=lambda c: (
                0 if c.quota_remaining is not None else 1,
                -(c.quota_remaining or 0.0),
                -c.weight,
                c.id,
            ),
        )

    if strategy == "latency":
        # Unproven vendors last rather than dropped: with only six providers,
        # strict "must have a latency sample" would empty the pool on a fresh
        # install and fail the very first request.
        return sorted(
            candidates,
            key=lambda c: (
                c.avg_latency_ms if c.avg_latency_ms is not None else _UNKNOWN_LATENCY_MS,
                -c.success_rate,
                c.id,
            ),
        )

    return _weighted_shuffle(candidates)


def _weighted_shuffle(candidates: list[Candidate]) -> list[Candidate]:
    """One weighted draw of the whole pool, producing the fallback order.

    Drawing the full sequence at once (rather than one `random.choices` per
    slot) makes the result a permutation: no provider can be drawn twice, so
    the tail is always "everyone else, weighted".
    """
    remaining = list(range(len(candidates)))
    # A weight of 0 means "never pick automatically" — floor to 1 so those
    # providers still sit in the failover tail instead of becoming unreachable.
    weights = [max(1, c.weight) for c in candidates]
    drawn: list[Candidate] = []
    while remaining:
        pick = random.choices(remaining, weights=weights, k=1)[0]
        idx = remaining.index(pick)
        remaining.pop(idx)
        weights.pop(idx)
        drawn.append(candidates[pick])
    return drawn


def resolve_chain(
    *,
    kind: str,
    rows: Sequence[NetworkProvider],
    env_keys: dict[str, str],
    strategy: str | None,
    provider: str | None,
    now: datetime,
) -> tuple[list[Candidate], str]:
    """Resolve an ordered provider chain, or raise a caller-error.

    A pinned provider is validated strictly (400 on unknown / disabled /
    missing key) and then given a weighted-random tail: free-tier throttling
    is routine, so "pin" means "prefer", not "refuse anything else". The
    switch is reported back in `failover_from` rather than being silent.
    """
    if provider:
        spec = get_spec(provider)
        if spec is None:
            raise NetworkRequestError(f"unknown provider: {provider}")
        if kind not in spec.capabilities:
            raise NetworkRequestError(f"provider '{spec.id}' does not support {kind}")
        row = next((r for r in rows if r.provider == spec.id and not r.is_deleted), None)
        if row is None:
            raise NetworkRequestError(f"provider '{spec.id}' is not configured")
        if not row.is_enabled:
            raise NetworkRequestError(f"provider '{spec.id}' is disabled")
        candidate = _candidate_from_row(row, spec, env_keys)
        if spec.requires_key and not candidate.api_key:
            raise NetworkRequestError(f"provider '{spec.id}' requires an API key")

        tail = [
            c for c in build_candidates(kind=kind, rows=rows, env_keys=env_keys, now=now)
            if c.id != spec.id
        ]
        return [candidate] + _weighted_shuffle(tail), "explicit"

    resolved = (strategy or DEFAULT_STRATEGY).strip().lower()
    if resolved not in STRATEGIES:
        raise NetworkRequestError(f"strategy must be one of {list(STRATEGIES)}")
    if resolved == "explicit":
        raise NetworkRequestError("strategy 'explicit' requires a provider")

    candidates = build_candidates(kind=kind, rows=rows, env_keys=env_keys, now=now)
    if not candidates:
        raise NetworkUnavailable(
            f"no eligible {kind} provider — configure a key or un-hide a provider",
            [],
        )
    return resolve_order(candidates, resolved), resolved


def validate_params(order: list[Candidate], kind: str, params: dict | None) -> dict[str, dict]:
    """Validate caller `params` and fan them out per candidate.

    The HEAD of the chain is validated strictly — a typo'd or out-of-range
    value is a caller error and must 400 immediately.

    The TAIL is validated loosely: each provider only receives the parameters
    it actually declares, and a value it can't accept is dropped rather than
    raised. Otherwise pinning `tavily` with `{"search_depth": "advanced"}`
    would 400 because `exa` — present only as insurance — has never heard of
    `search_depth`, and failover would never get a chance to run.
    """
    provided = dict(params or {})
    out: dict[str, dict] = {}
    for index, cand in enumerate(order):
        specs = cand.spec.params_for(kind)
        scoped = (
            provided
            if index == 0
            else {k: v for k, v in provided.items() if k in {p.name for p in specs}}
        )
        try:
            out[cand.id] = coerce_params(specs, scoped)
        except ProviderParamError as exc:
            if index == 0:
                raise NetworkRequestError(f"{cand.id}: {exc}") from exc
            out[cand.id] = {}
    return out


async def _reset_expired_quotas(
    db: AsyncSession, rows: Sequence[NetworkProvider], now: datetime
) -> None:
    """Zero `monthly_used` for rows whose reset marker has lapsed.

    One statement, no read-modify-write: two concurrent first-requests-of-the-
    month would otherwise both read 0 and both write their own count.
    """
    marker = _next_month_start(now)
    stale = [r for r in rows if r.quota_reset_at is None or _as_utc(r.quota_reset_at) <= now]
    if not stale:
        return
    await db.execute(
        update(NetworkProvider)
        .where(NetworkProvider.id.in_([r.id for r in stale]))
        .values(monthly_used=0, quota_reset_at=marker)
    )
    for r in stale:
        r.monthly_used = 0
        r.quota_reset_at = marker
    await db.commit()


async def _record_outcome(
    db: AsyncSession,
    provider_id: str,
    *,
    ok: bool,
    latency_ms: int | None,
    throttled: bool,
    message: str,
    now: datetime,
) -> None:
    """Update one provider's stats atomically.

    Counters are SQL expressions (`monthly_used + 1`) and the EWMA is a single
    CASE, so concurrent requests can't clobber each other's increments — the
    classic SQLite read-modify-write race.
    """
    values: dict = {
        "monthly_used": NetworkProvider.monthly_used + 1,
        "last_error": None if ok else (message or "")[:300],
    }
    if ok:
        values["success_count"] = NetworkProvider.success_count + 1
        values["cooldown_until"] = None
        if latency_ms is not None:
            values["avg_latency_ms"] = case(
                (NetworkProvider.avg_latency_ms.is_(None), latency_ms),
                else_=cast(
                    NetworkProvider.avg_latency_ms * (1 - _LATENCY_ALPHA)
                    + latency_ms * _LATENCY_ALPHA,
                    Integer,
                ),
            )
    else:
        values["failure_count"] = NetworkProvider.failure_count + 1
        if throttled:
            values["cooldown_until"] = now + timedelta(seconds=COOLDOWN_SECONDS)

    await db.execute(
        update(NetworkProvider)
        .where(NetworkProvider.provider == provider_id)
        .values(**values)
    )
    await db.commit()


@dataclass
class RunResult:
    kind: str
    provider: str
    strategy: str
    requested_provider: str | None
    latency_ms: int
    payload: list[dict]
    # Providers tried and failed, in order.
    attempts: list[str]
    errors: dict[str, str]


async def run_search(
    *,
    db: AsyncSession,
    workspace_id: str,
    api_key_id: str,
    rows: Sequence[NetworkProvider],
    env_keys: dict[str, str],
    query: str,
    strategy: str | None = None,
    provider: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    params: dict | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> RunResult:
    text = (query or "").strip()
    if not text:
        raise NetworkRequestError("query cannot be empty")

    now = _now()
    await _reset_expired_quotas(db, rows, now)
    order, resolved = resolve_chain(
        kind="search", rows=rows, env_keys=env_keys, strategy=strategy, provider=provider, now=now
    )
    per_provider = validate_params(order, "search", params)

    async def _call(client: httpx.AsyncClient, cand: Candidate, deadline: float) -> list[dict]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderError("budget exhausted", throttled=True)
        if cand.spec.search is None:
            raise ProviderError(f"{cand.id} does not support search")
        return await cand.spec.search(
            client,
            text,
            api_key=cand.api_key,
            max_results=max(1, int(max_results)),
            params=per_provider.get(cand.id, {}),
            timeout=max(0.5, min(timeout_ms / 1000, remaining)),
        )

    return await _run_chain(
        kind="search",
        order=order,
        strategy=resolved,
        requested=provider,
        call=_call,
        db=db,
        workspace_id=workspace_id,
        api_key_id=api_key_id,
        timeout_ms=timeout_ms,
        query=text[:MAX_QUERY_LEN],
        url_count=0,
        now=now,
    )


async def run_fetch(
    *,
    db: AsyncSession,
    workspace_id: str,
    api_key_id: str,
    rows: Sequence[NetworkProvider],
    env_keys: dict[str, str],
    urls: Sequence[str],
    strategy: str | None = None,
    provider: str | None = None,
    params: dict | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> RunResult:
    clean = [u.strip() for u in (urls or []) if u and u.strip()]
    if not clean:
        raise NetworkRequestError("urls cannot be empty")

    max_urls = max((s.max_urls or 10) for s in network_providers.REGISTRY.values())
    if len(clean) > max_urls:
        raise NetworkRequestError(f"at most {max_urls} urls per request")

    for url in clean:
        ok, reason = url_safety.is_safe_url(url)
        if not ok:
            # Don't echo the host back: the URL came from an untrusted caller
            # and the reason code alone tells them what to fix.
            raise NetworkRequestError(f"url rejected: {reason}")

    now = _now()
    await _reset_expired_quotas(db, rows, now)
    order, resolved = resolve_chain(
        kind="fetch", rows=rows, env_keys=env_keys, strategy=strategy, provider=provider, now=now
    )
    per_provider = validate_params(order, "fetch", params)

    async def _call(client: httpx.AsyncClient, cand: Candidate, deadline: float) -> list[dict]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderError("budget exhausted", throttled=True)
        if cand.spec.fetch is None:
            raise ProviderError(f"{cand.id} does not support fetch")
        return await cand.spec.fetch(
            client,
            list(clean),
            api_key=cand.api_key,
            params=per_provider.get(cand.id, {}),
            timeout=max(0.5, min(timeout_ms / 1000, remaining)),
        )

    return await _run_chain(
        kind="fetch",
        order=order,
        strategy=resolved,
        requested=provider,
        call=_call,
        db=db,
        workspace_id=workspace_id,
        api_key_id=api_key_id,
        timeout_ms=timeout_ms,
        query=None,
        url_count=len(clean),
        now=now,
    )


async def _run_chain(
    *,
    kind: str,
    order: list[Candidate],
    strategy: str,
    requested: str | None,
    call: Callable[[httpx.AsyncClient, Candidate, float], Awaitable[list[dict]]],
    db: AsyncSession,
    workspace_id: str,
    api_key_id: str,
    timeout_ms: int,
    query: str | None,
    url_count: int,
    now: datetime,
) -> RunResult:
    """Walk the chain until one provider answers, then persist the outcome."""
    attempts: list[str] = []
    errors: dict[str, str] = {}
    started = time.monotonic()
    deadline = started + min(TOTAL_BUDGET_MS, timeout_ms * max(1, len(order))) / 1000

    served: Candidate | None = None
    payload: list[dict] = []
    last_error = "no provider attempted"

    async with httpx.AsyncClient(follow_redirects=False) as client:
        for cand in order:
            call_started = time.monotonic()
            try:
                payload = await call(client, cand, deadline)
            except ProviderError as exc:
                message = str(exc)
                attempts.append(cand.id)
                errors[cand.id] = message
                last_error = f"{cand.id}: {message}"
                logger.info("network_provider_failed", provider=cand.id, kind=kind, error=message)
                await _record_outcome(
                    db, cand.id,
                    ok=False,
                    latency_ms=None,  # a failure must not pollute the EWMA
                    throttled=exc.throttled,
                    message=message,
                    now=now,
                )
                continue
            except Exception as exc:  # noqa: BLE001 — one vendor's bug must not 500 the request
                message = f"{type(exc).__name__}: {exc}"
                attempts.append(cand.id)
                errors[cand.id] = message
                last_error = f"{cand.id}: {message}"
                logger.warning("network_provider_error", provider=cand.id, kind=kind, error=message)
                await _record_outcome(
                    db, cand.id, ok=False, latency_ms=None, throttled=False, message=message, now=now
                )
                continue

            latency_ms = int((time.monotonic() - call_started) * 1000)
            served = cand
            await _record_outcome(
                db, cand.id, ok=True, latency_ms=latency_ms, throttled=False, message="", now=now
            )
            break

    total_ms = int((time.monotonic() - started) * 1000)

    if served is None:
        await _log_request(
            db,
            workspace_id=workspace_id,
            api_key_id=api_key_id,
            kind=kind,
            provider="none",
            requested=requested,
            strategy=strategy,
            query=query,
            url_count=url_count,
            result_count=0,
            latency_ms=total_ms,
            status_code=502,
            error_type="upstream_error",
            failover_from=",".join(attempts) or None,
        )
        raise NetworkUnavailable(last_error, attempts)

    await _log_request(
        db,
        workspace_id=workspace_id,
        api_key_id=api_key_id,
        kind=kind,
        provider=served.id,
        requested=requested,
        strategy=strategy,
        query=query,
        url_count=url_count,
        result_count=len(payload),
        latency_ms=total_ms,
        status_code=200,
        error_type=None,
        failover_from=",".join(attempts) or None,
    )

    return RunResult(
        kind=kind,
        provider=served.id,
        strategy=strategy,
        requested_provider=requested,
        latency_ms=total_ms,
        payload=payload,
        attempts=attempts,
        errors=errors,
    )


async def _log_request(
    db: AsyncSession,
    *,
    workspace_id: str,
    api_key_id: str,
    kind: str,
    provider: str,
    requested: str | None,
    strategy: str,
    query: str | None,
    url_count: int,
    result_count: int,
    latency_ms: int,
    status_code: int,
    error_type: str | None,
    failover_from: str | None,
) -> None:
    db.add(
        NetworkRequestLog(
            workspace_id=workspace_id,
            api_key_id=api_key_id,
            kind=kind,
            provider=provider,
            provider_requested=requested,
            strategy=strategy,
            query=query,
            url_count=url_count,
            result_count=result_count,
            latency_ms=latency_ms,
            status_code=status_code,
            error_type=error_type,
            failover_from=failover_from,
        )
    )
    await db.commit()
