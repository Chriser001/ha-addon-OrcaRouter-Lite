"""Custom-endpoint providers — routing a provider to an operator-supplied URL.

The contract these tests pin is the whole point of the feature: adding a
third-party gateway is CONFIG, not code. A provider row carrying `api_base`
must (a) produce deployments aimed at that URL and (b) take its model list
from what the endpoint actually serves, because litellm has never heard of it.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.router_cache import build_deployments, custom_endpoints, resolve_protocol
from packages.auth.encryption import encrypt_credential
from packages.db.models.provider_key import ProviderKey
from packages.litellm_adapter.catalog import CatalogModel


def _row(
    provider: str,
    key: str = "sk-x",
    *,
    base: str | None = None,
    protocol: str | None = None,
    enabled: bool = True,
) -> ProviderKey:
    return ProviderKey(
        provider=provider,
        encrypted_key=encrypt_credential(key),
        key_prefix="sk-...",
        label="default",
        is_enabled=enabled,
        api_base=base,
        custom_llm_provider=protocol,
    )


def test_custom_endpoint_uses_discovered_models():
    """An unknown provider's only model list is the one its endpoint served."""
    s = Settings(_env_file=None)
    row = _row("mygateway", base="https://gw.example.com/v1")

    deps = build_deployments(
        env_keys={},
        db_keys=[row],
        settings=s,
        custom_models={"mygateway": ["gpt-4o-mini", "llama-3"]},
    )

    assert {d.model_name for d in deps} == {"gpt-4o-mini", "llama-3"}
    for d in deps:
        assert d.api_base == "https://gw.example.com/v1"
        assert d.api_key == "sk-x"
        assert d.provider == "mygateway"
        # OpenAI-compatible is the default wire protocol for a gateway litellm
        # has never heard of.
        assert d.custom_llm_provider == "openai"
        assert d.litellm_model.startswith("openai/")


def test_custom_endpoint_without_discovery_result_deploys_nothing():
    """Discovery failed → provider serves nothing, but nothing else breaks.

    A dead gateway must not manufacture deployments from a stale or guessed
    model list, and it must not raise out of the router build.
    """
    s = Settings(_env_file=None)
    row = _row("mygateway", base="https://gw.example.com/v1")
    assert build_deployments(env_keys={}, db_keys=[row], settings=s) == []


def test_known_provider_with_custom_base_keeps_its_catalog_models(monkeypatch):
    """Proxying a known vendor must preserve its model list.

    Pointing `openai` at a corporate gateway is about WHERE requests go, not
    WHAT they can ask for — the models stay the same.
    """
    from packages.litellm_adapter.catalog import models_for_provider

    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    s = Settings(_env_file=None)
    row = _row("openai", "sk-db", base="https://proxy.internal/v1")

    deps = build_deployments(env_keys=s.env_provider_keys(), db_keys=[row], settings=s)

    expected = {m.id for m in models_for_provider("openai")}
    assert {d.model_name for d in deps} == expected
    assert all(d.api_base == "https://proxy.internal/v1" for d in deps)
    assert all(d.litellm_model.startswith("openai/") for d in deps)
    # DB key still beats env, custom endpoint or not.
    assert all(d.api_key == "sk-db" for d in deps)


def test_explicit_protocol_overrides_the_openai_default():
    """A gateway speaking Anthropic's wire format gets an anthropic/ prefix."""
    s = Settings(_env_file=None)
    row = _row("mygw", base="https://gw.example.com/v1", protocol="anthropic")

    deps = build_deployments(
        env_keys={},
        db_keys=[row],
        settings=s,
        custom_models={"mygw": ["claude-x"]},
    )

    assert deps[0].litellm_model == "anthropic/claude-x"
    assert deps[0].custom_llm_provider == "anthropic"


def test_env_api_base_points_a_known_provider_at_a_custom_host(monkeypatch):
    """`<PROVIDER>_API_BASE` works without any DB row (12-factor path)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.setenv("OPENAI_API_BASE", "https://proxy.internal/v1")
    s = Settings(_env_file=None)

    deps = build_deployments(env_keys=s.env_provider_keys(), db_keys=[], settings=s)

    assert deps
    assert all(d.api_base == "https://proxy.internal/v1" for d in deps)
    assert all(d.api_key == "sk-env" for d in deps)


def test_env_provider_bases_reads_any_provider_name(monkeypatch):
    """Providers this codebase has never heard of still work from env.

    Membership (not equality) so an unrelated `*_API_BASE` in the developer's
    shell can't flake the test.
    """
    monkeypatch.setenv("STEPFUN_API_BASE", "https://api.stepfun.com/v1")
    monkeypatch.setenv("ORCAROUTER_API_BASE", "https://ignored.example/v1")
    s = Settings(_env_file=None)

    bases = s.env_provider_bases()
    assert bases["stepfun"] == "https://api.stepfun.com/v1"
    # The hosted upstream has its own setting; a generic base must not fork it.
    assert "orcarouter" not in bases


def test_base_url_without_a_key_is_inert(monkeypatch):
    """A base address alone can't authenticate — no key, no endpoint."""
    monkeypatch.setenv("STEPFUN_API_BASE", "https://api.stepfun.com/v1")
    s = Settings(_env_file=None)
    assert "stepfun" not in custom_endpoints(env_keys={}, db_keys=[], settings=s)


def test_orcarouter_is_excluded_from_custom_endpoints():
    """Hosted upstream keeps its dedicated branch + setting."""
    s = Settings(_env_file=None)
    row = _row("orcarouter", base="https://attacker.example/v1")
    assert "orcarouter" not in custom_endpoints(env_keys={}, db_keys=[row], settings=s)


def test_disabled_or_undecryptable_row_yields_no_endpoint():
    s = Settings(_env_file=None)
    disabled = _row("gw1", base="https://gw.example.com/v1", enabled=False)
    corrupt = _row("gw2", base="https://gw.example.com/v1")
    corrupt.encrypted_key = b"not-valid-aesgcm-ciphertext"

    assert custom_endpoints(env_keys={}, db_keys=[disabled, corrupt], settings=s) == {}


def test_resolve_protocol_precedence():
    """Explicit hint > catalog prefix > openai/ fallback."""
    assert resolve_protocol("anything", None, []) == "openai/"
    assert resolve_protocol("openai", "anthropic", []) == "anthropic/"
    # Trailing slash tolerated either way.
    assert resolve_protocol("openai", "anthropic/", []) == "anthropic/"

    google = CatalogModel(id="gemini-1.5-pro", provider="google", litellm_prefix="gemini/")
    assert resolve_protocol("google", None, [google]) == "gemini/"
    # An explicit hint still wins over the catalog prefix.
    assert resolve_protocol("google", "openai", [google]) == "openai/"


@pytest.mark.parametrize("base", ["https://gw.example.com/v1", "http://10.0.0.5:11434/v1"])
def test_custom_endpoint_accepts_http_and_https(base):
    """Private-network gateways are usually plain http — both must work."""
    s = Settings(_env_file=None)
    row = _row("gw", base=base)

    deps = build_deployments(
        env_keys={}, db_keys=[row], settings=s, custom_models={"gw": ["m1"]}
    )
    assert deps[0].api_base == base
