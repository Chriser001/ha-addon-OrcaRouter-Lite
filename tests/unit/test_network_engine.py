"""Strategy ordering + failover for the aggregated network engine.

These are pure-function tests (no HTTP, no DB write paths): `resolve_order`
and `resolve_chain` are where the selection policy lives, and getting the
ordering wrong is the failure mode that silently wastes a free-tier
allowance, so it's worth pinning down exhaustively.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from app import network_engine as ne
from app.network_providers import REGISTRY, ProviderSpec
from packages.db.models.network_provider import NetworkProvider


def _row(provider: str, **kw) -> NetworkProvider:
    """An ORM instance with the fields the engine reads. No session needed."""
    row = NetworkProvider(provider=provider)
    for key, value in ({
        "encrypted_key": None,
        "key_prefix": "",
        "is_enabled": True,
        "weight": 100,
        "monthly_quota": None,
        "monthly_used": 0,
        "avg_latency_ms": None,
        "success_count": 0,
        "failure_count": 0,
        "cooldown_until": None,
        "is_deleted": 0,
    } | kw).items():
        setattr(row, key, value)
    return row


def _spec(provider: str, **kw) -> ProviderSpec:
    return dataclasses.replace(REGISTRY[provider], **kw)


def _cand(provider: str, **kw) -> ne.Candidate:
    fields = {
        "api_key": None,
        "weight": 100,
        "monthly_quota": None,
        "monthly_used": 0,
        "avg_latency_ms": None,
        "success_count": 0,
        "failure_count": 0,
    }
    fields.update(kw)
    return ne.Candidate(spec=REGISTRY[provider], **fields)


NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


# ── build_candidates ──────────────────────────────────────────────────────
def test_keyless_providers_are_candidates_without_config():
    rows = [_row(p) for p in ("exa", "parallel", "firecrawl", "keenable")]
    cands = ne.build_candidates(kind="search", rows=rows, env_keys={}, now=NOW)
    assert {c.id for c in cands} == {"exa", "parallel", "firecrawl", "keenable"}


def test_keyed_providers_need_a_credential():
    rows = [_row("tavily", is_enabled=True)]
    assert ne.build_candidates(kind="search", rows=rows, env_keys={}, now=NOW) == []

    env = {"tavily": "tvly-test"}
    assert [c.id for c in ne.build_candidates(kind="search", rows=rows, env_keys=env, now=NOW)] == ["tavily"]


def test_disabled_providers_never_appear():
    rows = [_row("exa", is_enabled=False)]
    assert ne.build_candidates(kind="search", rows=rows, env_keys={}, now=NOW) == []


def test_cooled_down_providers_are_skipped():
    rows = [_row("exa", cooldown_until=NOW + timedelta(seconds=30))]
    assert ne.build_candidates(kind="search", rows=rows, env_keys={}, now=NOW) == []

    lapsed = [_row("exa", cooldown_until=NOW - timedelta(seconds=1))]
    assert len(ne.build_candidates(kind="search", rows=lapsed, env_keys={}, now=NOW)) == 1


def test_unknown_rows_are_ignored():
    # A row for a provider this build doesn't know about (downgrade) must not
    # be selected — but it also must not crash the resolver.
    rows = [_row("defunct-vendor")]
    assert ne.build_candidates(kind="search", rows=rows, env_keys={}, now=NOW) == []


# ── resolve_order ─────────────────────────────────────────────────────────
def test_quota_strategy_spends_metered_allowance_first():
    cands = [
        _cand("exa"),                                              # unmetered
        _cand("tavily", monthly_quota=1000, monthly_used=900),     # 10% left
        _cand("tinyfish", monthly_quota=500, monthly_used=0),      # 100% left
    ]
    order = [c.id for c in ne.resolve_order(cands, "quota")]
    assert order == ["tinyfish", "tavily", "exa"]


def test_quota_strategy_sorts_unmetered_last_even_when_exhausted():
    # A metered provider at 0% still outranks an unmetered one: the metered
    # vendor will 432 and cascade, but the point of the strategy is to try to
    # spend the allowance that expires at month end.
    cands = [
        _cand("exa"),
        _cand("tavily", monthly_quota=1000, monthly_used=1000),
    ]
    assert [c.id for c in ne.resolve_order(cands, "quota")] == ["tavily", "exa"]


def test_latency_strategy_puts_unproven_last():
    cands = [
        _cand("exa"),                          # no sample
        _cand("parallel", avg_latency_ms=900),
        _cand("keenable", avg_latency_ms=200),
    ]
    assert [c.id for c in ne.resolve_order(cands, "latency")] == ["keenable", "parallel", "exa"]


def test_latency_tiebreak_prefers_higher_success_rate():
    cands = [
        _cand("exa", avg_latency_ms=300, success_count=1, failure_count=9),
        _cand("parallel", avg_latency_ms=300, success_count=9, failure_count=1),
    ]
    assert [c.id for c in ne.resolve_order(cands, "latency")] == ["parallel", "exa"]


def test_random_strategy_is_a_permutation():
    cands = [_cand(p) for p in ("exa", "parallel", "firecrawl", "keenable")]
    order = [c.id for c in ne.resolve_order(cands, "random")]
    assert sorted(order) == sorted(c.id for c in cands)


def test_random_strategy_favours_higher_weight():
    heavy = _cand("exa", weight=1000)
    light = _cand("parallel", weight=1)
    wins = sum(
        1 for _ in range(300)
        if ne.resolve_order([heavy, light], "random")[0].id == "exa"
    )
    # Not a strict assertion — weighted random is stochastic — but a 1000:1
    # weight must win the overwhelming majority of draws.
    assert wins > 270


def test_zero_weight_stays_in_the_failover_tail():
    zero = _cand("exa", weight=0)
    normal = _cand("parallel", weight=100)
    order = [c.id for c in ne.resolve_order([zero, normal], "random")]
    assert len(order) == 2  # floored to 1, never dropped


def test_empty_pool():
    assert ne.resolve_order([], "quota") == []


# ── resolve_chain ─────────────────────────────────────────────────────────
def test_explicit_pin_goes_first_with_a_tail():
    rows = [_row(p) for p in ("exa", "parallel", "firecrawl", "keenable")]
    order, strategy = ne.resolve_chain(
        kind="search", rows=rows, env_keys={}, strategy=None, provider="keenable", now=NOW
    )
    assert strategy == "explicit"
    assert order[0].id == "keenable"
    assert len(order) == 4  # the tail is insurance, not an empty list


def test_disabled_provider_cannot_be_pinned():
    rows = [_row("exa", is_enabled=False)]
    with pytest.raises(ne.NetworkRequestError, match="disabled"):
        ne.resolve_chain(kind="search", rows=rows, env_keys={}, strategy=None, provider="exa", now=NOW)


def test_pin_without_credential_is_a_caller_error():
    rows = [_row("tavily")]
    with pytest.raises(ne.NetworkRequestError, match="requires an API key"):
        ne.resolve_chain(kind="search", rows=rows, env_keys={}, strategy=None, provider="tavily", now=NOW)


def test_unknown_provider_is_a_caller_error():
    with pytest.raises(ne.NetworkRequestError, match="unknown provider"):
        ne.resolve_chain(kind="search", rows=[], env_keys={}, strategy=None, provider="nope", now=NOW)


def test_explicit_strategy_without_provider_is_rejected():
    rows = [_row("exa")]
    with pytest.raises(ne.NetworkRequestError, match="requires a provider"):
        ne.resolve_chain(kind="search", rows=rows, env_keys={}, strategy="explicit", provider=None, now=NOW)


def test_unknown_strategy_is_rejected():
    rows = [_row("exa")]
    with pytest.raises(ne.NetworkRequestError, match="strategy must be one of"):
        ne.resolve_chain(kind="search", rows=rows, env_keys={}, strategy="vibes", provider=None, now=NOW)


def test_empty_pool_is_unavailable_not_a_crash():
    with pytest.raises(ne.NetworkUnavailable):
        ne.resolve_chain(kind="search", rows=[], env_keys={}, strategy="random", provider=None, now=NOW)


def test_default_strategy_applies_when_omitted():
    rows = [_row("exa")]
    order, strategy = ne.resolve_chain(
        kind="search", rows=rows, env_keys={}, strategy=None, provider=None, now=NOW
    )
    assert strategy == "random"
    assert [c.id for c in order] == ["exa"]


# ── validate_params ───────────────────────────────────────────────────────
def test_validate_params_is_strict_for_the_chain_head():
    # A bad value must 400 up front rather than silently disabling the provider.
    order = [_cand("tavily", api_key="k"), _cand("exa")]
    with pytest.raises(ne.NetworkRequestError, match="tavily"):
        ne.validate_params(order, "search", {"search_depth": "nope"})


def test_validate_params_forwards_only_known_params_to_the_tail():
    # Pinning tavily with tavily-only params must not 400 just because exa is
    # in the failover tail and doesn't declare search_depth.
    order = [_cand("tavily", api_key="k"), _cand("exa")]
    out = ne.validate_params(order, "search", {"search_depth": "advanced"})
    assert out["tavily"]["search_depth"] == "advanced"
    assert out["exa"] == {}


def test_validate_params_applies_declared_defaults():
    # Keyless vendors declare no params; Tavily's defaults are filled in so the
    # upstream always receives an explicit value for every field.
    order = [_cand("exa"), _cand("tavily", api_key="k")]
    out = ne.validate_params(order, "search", None)
    assert out["exa"] == {}
    assert out["tavily"]["search_depth"] == "basic"
    assert out["tavily"]["topic"] == "general"


# ── helpers ───────────────────────────────────────────────────────────────
def test_success_rate_is_neutral_without_history():
    assert _cand("exa").success_rate == 0.5
    assert _cand("exa", success_count=3, failure_count=1).success_rate == 0.75


def test_quota_remaining():
    assert _cand("exa").quota_remaining is None
    assert _cand("tavily", monthly_quota=1000, monthly_used=250).quota_remaining == 0.75


def test_next_month_start_rolls_over_december():
    assert ne._next_month_start(datetime(2026, 12, 15, tzinfo=timezone.utc)) == datetime(
        2027, 1, 1, tzinfo=timezone.utc
    )


def test_specs_are_replaceable_for_tests():
    # Tests monkeypatch adapters via dataclasses.replace — assert that stays
    # possible (ProviderSpec must remain a frozen dataclass).
    patched = _spec("exa", label="Exa (patched)")
    assert patched.label == "Exa (patched)"
    assert REGISTRY["exa"].label == "Exa"
