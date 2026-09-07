"""Registry + parameter metadata for the aggregated network surface."""

import json

import pytest

from app import network_providers as np
from app.network_providers import _tavily_usage

EXPECTED_IDS = {"exa", "parallel", "firecrawl", "keenable", "tavily", "tinyfish"}


def test_registry_covers_expected_providers():
    assert set(np.REGISTRY) == EXPECTED_IDS


def test_ids_are_lowercase_and_match_keys():
    for key, spec in np.REGISTRY.items():
        assert spec.id == key
        assert spec.id == spec.id.lower()


def test_every_provider_supports_at_least_one_operation():
    for spec in np.REGISTRY.values():
        assert spec.capabilities & {"search", "fetch"}, spec.id


def test_adapters_present_for_declared_capabilities():
    # A capability without an adapter would make the engine raise mid-chain.
    for spec in np.REGISTRY.values():
        if "search" in spec.capabilities:
            assert callable(spec.search), spec.id
        if "fetch" in spec.capabilities:
            assert callable(spec.fetch), spec.id


def test_keyed_providers_start_disabled_and_keyless_enabled():
    for spec in np.REGISTRY.values():
        # Keyless vendors are usable the moment the server boots; keyed ones
        # would 401 on every call until a credential exists.
        assert spec.default_enabled is (not spec.requires_key), spec.id


def test_metered_providers_require_a_key():
    for spec in np.REGISTRY.values():
        if spec.tier == "quota":
            assert spec.requires_key, spec.id


def test_metered_providers_that_publish_an_allowance_seed_it():
    # `monthly_quota` drives the `quota` strategy. Vendors whose free tier is
    # documented get a default; the rest ship None ("unmetered") and the
    # operator can set the real figure from the dashboard.
    seeded = {
        spec.id: spec.monthly_quota
        for spec in np.REGISTRY.values()
        if spec.tier == "quota"
    }
    assert seeded["tavily"] == 1000
    assert seeded["tinyfish"] is None


def test_keyless_providers_are_unmetered():
    for spec in np.REGISTRY.values():
        if spec.tier == "keyless":
            assert spec.monthly_quota is None, spec.id


def test_param_types_are_renderable_by_the_dashboard():
    allowed = {"string", "int", "bool", "enum"}
    for spec in np.REGISTRY.values():
        for param in (*spec.search_params, *spec.fetch_params):
            assert param.type in allowed, (spec.id, param.name)
            if param.type == "enum":
                assert param.enum, (spec.id, param.name)
            if param.minimum is not None and param.maximum is not None:
                assert param.minimum <= param.maximum


def test_param_defaults_are_valid_values():
    for spec in np.REGISTRY.values():
        for param in (*spec.search_params, *spec.fetch_params):
            if param.default is None:
                continue
            if param.type == "enum":
                assert param.default in param.enum, (spec.id, param.name)
            if param.type == "int":
                assert isinstance(param.default, int), (spec.id, param.name)


def test_param_names_are_unique_per_operation():
    for spec in np.REGISTRY.values():
        for kind in ("search", "fetch"):
            names = [p.name for p in spec.params_for(kind)]
            assert len(names) == len(set(names)), (spec.id, kind)


def test_to_dict_shape():
    param = np.ParamSpec("topic", "enum", default="general", enum=("general", "news"), description="d")
    assert param.to_dict() == {
        "name": "topic",
        "type": "enum",
        "default": "general",
        "required": False,
        "description": "d",
        "enum": ["general", "news"],
    }


# ── coerce_params ─────────────────────────────────────────────────────────
def _specs():
    return (
        np.ParamSpec("topic", "enum", default="general", enum=("general", "news")),
        np.ParamSpec("depth", "int", minimum=1, maximum=5),
        np.ParamSpec("raw", "bool", default=False),
        np.ParamSpec("note", "string"),
    )


def test_coerce_applies_defaults():
    out = np.coerce_params(_specs(), {})
    assert out == {"topic": "general", "raw": False}


def test_coerce_accepts_explicit_values():
    out = np.coerce_params(_specs(), {"topic": "news", "depth": 3, "raw": True, "note": "x"})
    assert out == {"topic": "news", "depth": 3, "raw": True, "note": "x"}


def test_coerce_rejects_unknown_name():
    # Silently dropping a typo'd parameter is how callers end up believing
    # they set something they didn't.
    with pytest.raises(np.ProviderParamError, match="unknown parameter"):
        np.coerce_params(_specs(), {"searchDepth": "advanced"})


def test_coerce_rejects_bad_enum():
    with pytest.raises(np.ProviderParamError, match="must be one of"):
        np.coerce_params(_specs(), {"topic": "finance"})


def test_coerce_rejects_out_of_range_int():
    with pytest.raises(np.ProviderParamError, match="must be <="):
        np.coerce_params(_specs(), {"depth": 99})
    with pytest.raises(np.ProviderParamError, match="must be >="):
        np.coerce_params(_specs(), {"depth": 0})


def test_coerce_accepts_string_bool():
    assert np.coerce_params(_specs(), {"raw": "true"})["raw"] is True


def test_coerce_requires_marked_params():
    specs = (np.ParamSpec("query", "string", required=True),)
    with pytest.raises(np.ProviderParamError, match="missing required"):
        np.coerce_params(specs, {})


def test_get_spec_is_case_insensitive():
    assert np.get_spec("Tavily").id == "tavily"
    assert np.get_spec(" nope ") is None


def test_is_throttled_markers():
    assert np.is_throttled("Too Many Requests")
    assert np.is_throttled("HTTP 429: slow down")
    assert np.is_throttled("your plan's usage limit reached")
    assert not np.is_throttled("unauthorized: bad key")
    assert not np.is_throttled("internal server error")


# ── published rate limits + live usage ────────────────────────────────────
def test_rate_limits_are_well_formed():
    for spec in np.REGISTRY.values():
        for limit in spec.rate_limits:
            assert limit.operation in spec.capabilities, (spec.id, limit)
            assert limit.per in ("minute", "hour", "day", "month"), (spec.id, limit)
            assert limit.limit > 0, (spec.id, limit)


def test_rate_limits_to_dict_shape():
    limit = np.RateLimit("search", "minute", 30)
    assert limit.to_dict() == {"operation": "search", "per": "minute", "limit": 30}


def test_tinyfish_publishes_its_documented_limits():
    limits = {(x.operation, x.per): x.limit for x in np.REGISTRY["tinyfish"].rate_limits}
    assert limits == {
        ("search", "minute"): 30,
        ("search", "hour"): 500,
        ("fetch", "minute"): 150,
        ("fetch", "day"): 1000,
    }


def test_only_vendors_with_a_balance_endpoint_declare_usage():
    # Declaring `usage` without an adapter would 500 the refresh route.
    for spec in np.REGISTRY.values():
        assert (spec.usage is not None) is (spec.id in ("tavily",)), spec.id


# ── Tavily /usage payload parsing ─────────────────────────────────────────
def _usage(payload):
    """Run `_tavily_usage` against a canned payload (no HTTP)."""
    import asyncio

    class _Resp:
        status_code = 200

        def __init__(self):
            self.text = json.dumps(payload)

        def json(self):
            return payload

    class _Client:
        async def get(self, *a, **k):
            return _Resp()

    return asyncio.run(_tavily_usage(_Client(), api_key="tvly-test", timeout=5.0))


def test_usage_documented_shape():
    out = _usage({
        "key": {"usage": 150, "limit": 1000, "search_usage": 100, "extract_usage": 25},
        "account": {"current_plan": "Bootstrap", "plan_usage": 500, "plan_limit": 15000},
    })
    assert out["used"] == 150
    assert out["monthly"] == 1000
    assert out["remaining"] == 850
    assert out["remaining_percent"] == 85.0
    assert out["plan"] == "Bootstrap"
    assert out["breakdown"]["search_usage"] == 100


def test_usage_renamed_fields():
    # The live endpoint has shipped field names other than the documented
    # example; the parser must survive a rename.
    out = _usage({"key": {"current_usage": 42, "usage_limit": 1000}})
    assert (out["used"], out["monthly"]) == (42, 1000)
    assert out["source"] == "current_usage"


def test_usage_numeric_strings():
    out = _usage({"key": {"usage": "150", "limit": "1,000"}})
    assert (out["used"], out["monthly"]) == (150, 1000)


def test_usage_falls_back_to_account_block():
    out = _usage({"account": {"current_plan": "Bootstrap", "plan_usage": 500, "plan_limit": 15000}})
    assert (out["used"], out["monthly"]) == (500, 15000)
    assert out["source"] == "plan_usage"


def test_usage_flat_shape():
    out = _usage({"usage": 10, "limit": 1000})
    assert (out["used"], out["monthly"]) == (10, 1000)


def test_usage_zero_used_is_not_falsy_bug():
    # `0` is a legitimate reading — a falsy check would drop it and fall
    # through to the account block (or worse, report an error).
    out = _usage({"key": {"usage": 0, "limit": 1000}})
    assert (out["used"], out["monthly"]) == (0, 1000)


def test_usage_unknown_shape_echoes_payload():
    import pytest

    with pytest.raises(np.ProviderError) as exc:
        _usage({"hello": "world", "foo": 1})
    # The error must carry the payload — otherwise a vendor rename is a dead
    # end ("missing key.usage") with nothing to debug from.
    assert '"hello": "world"' in str(exc.value)
