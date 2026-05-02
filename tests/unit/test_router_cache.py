"""Router cache: deployment-list assembly + hosted-as-upstream injection.

These tests pin the contract of `build_deployments` without instantiating
litellm.Router (covered by integration tests). Pure-Python is the right
shape for TDD on this layer.
"""

from __future__ import annotations


def test_no_keys_no_deployments():
    """Empty inputs → empty deployment list."""
    from app.config import Settings
    from app.router_cache import build_deployments

    s = Settings(_env_file=None)
    assert build_deployments(env_keys={}, db_keys=[], settings=s) == []


def test_env_openai_key_creates_deployments_per_openai_model():
    """An env-sourced openai key creates one deployment per OpenAI catalog entry."""
    from app.config import Settings
    from app.router_cache import build_deployments
    from packages.litellm_adapter.catalog import models_for_provider

    s = Settings(_env_file=None)
    deps = build_deployments(env_keys={"openai": "sk-x"}, db_keys=[], settings=s)

    expected = {m.id for m in models_for_provider("openai")}
    actual = {d.model_name for d in deps if d.provider == "openai"}
    assert actual == expected
    for d in deps:
        assert d.api_key == "sk-x"
        assert d.litellm_model.startswith("openai/")


def test_env_keys_for_multiple_providers_combine():
    from app.config import Settings
    from app.router_cache import build_deployments

    s = Settings(_env_file=None)
    deps = build_deployments(
        env_keys={"openai": "sk-o", "anthropic": "sk-a"},
        db_keys=[],
        settings=s,
    )
    providers = {d.provider for d in deps}
    assert providers == {"openai", "anthropic"}


def test_db_provider_key_takes_precedence_over_env():
    """If both env and DB set a provider key, DB wins (UI-edited keys are authoritative)."""
    from app.config import Settings
    from app.router_cache import build_deployments
    from packages.auth.encryption import encrypt_credential
    from packages.db.models.provider_key import ProviderKey

    s = Settings(_env_file=None)
    db_row = ProviderKey(
        provider="openai",
        encrypted_key=encrypt_credential("sk-from-db"),
        key_prefix="sk-from-...",
        label="default",
        is_enabled=True,
    )

    deps = build_deployments(
        env_keys={"openai": "sk-from-env"},
        db_keys=[db_row],
        settings=s,
    )
    openai_deps = [d for d in deps if d.provider == "openai"]
    assert openai_deps  # at least one
    assert all(d.api_key == "sk-from-db" for d in openai_deps)


def test_disabled_db_provider_key_is_skipped():
    from app.config import Settings
    from app.router_cache import build_deployments
    from packages.auth.encryption import encrypt_credential
    from packages.db.models.provider_key import ProviderKey

    s = Settings(_env_file=None)
    db_row = ProviderKey(
        provider="openai",
        encrypted_key=encrypt_credential("sk-disabled"),
        key_prefix="sk-...",
        label="default",
        is_enabled=False,
    )
    deps = build_deployments(env_keys={}, db_keys=[db_row], settings=s)
    assert deps == []


def test_orcarouter_api_key_adds_hosted_upstream_per_model(monkeypatch):
    """When ORCAROUTER_API_KEY is set, every catalog model gets an `orcarouter` deployment.

    This is the headline integration: a lite instance with no provider keys but
    ORCAROUTER_API_KEY set still routes everything via the hosted control plane.
    """
    from app.config import Settings
    from app.router_cache import build_deployments
    from packages.litellm_adapter.catalog import all_model_ids

    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-hosted-xyz")
    s = Settings(_env_file=None)

    deps = build_deployments(env_keys={}, db_keys=[], settings=s)
    orca_deps = [d for d in deps if d.provider == "orcarouter"]
    assert len(orca_deps) == len(all_model_ids())
    for d in orca_deps:
        assert d.api_base == "https://api.orcarouter.ai/v1"
        assert d.api_key == "sk-orca-hosted-xyz"
        # OpenAI-compatible passthrough — `openai/` prefix tells litellm to use the OpenAI SDK
        assert d.litellm_model.startswith("openai/")


def test_orcarouter_upstream_combines_with_local_keys(monkeypatch):
    """Hosted-as-upstream coexists with local provider keys — fallback chain."""
    from app.config import Settings
    from app.router_cache import build_deployments

    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-h")
    s = Settings(_env_file=None)

    deps = build_deployments(env_keys={"openai": "sk-o"}, db_keys=[], settings=s)
    providers = {d.provider for d in deps}
    assert "openai" in providers
    assert "orcarouter" in providers
