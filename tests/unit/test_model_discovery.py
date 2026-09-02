"""Model discovery against a custom endpoint's `/models`.

The property that matters most: discovery runs on the router-build path, so it
must never take routing down with it. These tests pin both halves — correct
parsing when the gateway behaves, and a silent degrade to `[]` when it doesn't.
"""

from __future__ import annotations

import json

import pytest

from app import model_discovery


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    """Stands in for httpx.AsyncClient; records the URL it was asked for."""

    last_url: str | None = None
    last_headers: dict | None = None
    payload = "{}"
    status_code = 200

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, headers=None):
        _FakeClient.last_url = url
        _FakeClient.last_headers = headers
        return _FakeResponse(_FakeClient.payload, _FakeClient.status_code)


@pytest.fixture(autouse=True)
def _fake_httpx(monkeypatch):
    monkeypatch.setattr(model_discovery.httpx, "AsyncClient", _FakeClient)
    _FakeClient.last_url = None
    _FakeClient.last_headers = None
    _FakeClient.payload = "{}"
    _FakeClient.status_code = 200
    model_discovery.reset_cache()
    yield


def _openai_payload(*ids: str) -> str:
    return json.dumps({"object": "list", "data": [{"id": i} for i in ids]})


async def test_parses_openai_model_envelope():
    _FakeClient.payload = _openai_payload("gpt-4o", "llama-3")
    ids = await model_discovery.fetch_models(
        base_url="https://gw.example.com/v1", api_key="sk-x"
    )
    assert ids == ["gpt-4o", "llama-3"]
    assert _FakeClient.last_url == "https://gw.example.com/v1/models"


async def test_authorization_header_carries_the_key():
    _FakeClient.payload = _openai_payload("m1")
    await model_discovery.fetch_models(base_url="https://gw/v1", api_key="sk-secret")
    assert _FakeClient.last_headers["Authorization"] == "Bearer sk-secret"


async def test_trailing_slash_does_not_produce_a_double_slash():
    """`/v1/` + `/models` must not become `/v1//models` — some gateways 404."""
    _FakeClient.payload = _openai_payload("m1")
    await model_discovery.fetch_models(base_url="https://gw.example.com/v1/", api_key="k")
    assert _FakeClient.last_url == "https://gw.example.com/v1/models"


async def test_base_without_version_segment_still_works():
    _FakeClient.payload = _openai_payload("m1")
    await model_discovery.fetch_models(base_url="https://gw.example.com", api_key="k")
    assert _FakeClient.last_url == "https://gw.example.com/models"


async def test_dedupes_and_sorts():
    _FakeClient.payload = _openai_payload("b", "a", "b")
    ids = await model_discovery.fetch_models(base_url="https://gw/v1", api_key="k")
    assert ids == ["a", "b"]


async def test_http_error_propagates_from_fetch():
    """`fetch_models` reports failure; the tolerant wrapper below swallows it."""
    _FakeClient.status_code = 401
    with pytest.raises(RuntimeError, match="401"):
        await model_discovery.fetch_models(base_url="https://gw/v1", api_key="bad")


async def test_discover_degrades_to_empty_on_failure():
    _FakeClient.status_code = 500
    ids = await model_discovery.discover_provider_models(
        provider="gw", base_url="https://gw/v1", api_key="k"
    )
    assert ids == []


async def test_discover_treats_empty_list_as_failure():
    _FakeClient.payload = _openai_payload()  # zero models
    ids = await model_discovery.discover_provider_models(
        provider="gw", base_url="https://gw/v1", api_key="k"
    )
    assert ids == []


async def test_discover_caches_success(monkeypatch):
    _FakeClient.payload = _openai_payload("m1", "m2")
    calls = {"n": 0}

    real_get = _FakeClient.get

    async def counting_get(self, url, headers=None):
        calls["n"] += 1
        return await real_get(self, url, headers=headers)

    monkeypatch.setattr(_FakeClient, "get", counting_get)

    first = await model_discovery.discover_provider_models(
        provider="gw", base_url="https://gw/v1", api_key="k"
    )
    second = await model_discovery.discover_provider_models(
        provider="gw", base_url="https://gw/v1", api_key="k"
    )

    assert first == second == ["m1", "m2"]
    assert calls["n"] == 1  # second call served from cache


async def test_discover_caches_negative_result(monkeypatch):
    """A dead gateway mustn't be re-probed on every router rebuild — that
    would add its timeout to the first request after each invalidation."""
    _FakeClient.status_code = 500
    calls = {"n": 0}

    real_get = _FakeClient.get

    async def counting_get(self, url, headers=None):
        calls["n"] += 1
        return await real_get(self, url, headers=headers)

    monkeypatch.setattr(_FakeClient, "get", counting_get)

    for _ in range(3):
        assert (
            await model_discovery.discover_provider_models(
                provider="gw", base_url="https://gw/v1", api_key="k"
            )
            == []
        )
    assert calls["n"] == 1


async def test_force_refresh_bypasses_cache():
    _FakeClient.payload = _openai_payload("m1")
    await model_discovery.discover_provider_models(
        provider="gw", base_url="https://gw/v1", api_key="k"
    )
    _FakeClient.payload = _openai_payload("m1", "m2")
    ids = await model_discovery.discover_provider_models(
        provider="gw", base_url="https://gw/v1", api_key="k", force_refresh=True
    )
    assert ids == ["m1", "m2"]


async def test_prime_cache_reuses_an_already_fetched_result():
    """The refresh endpoint fetches once (so it can report *why* a scan
    failed) and primes the cache so the router build doesn't ask again."""
    model_discovery.prime_cache("gw", "https://gw/v1", ["m1", "m2"])

    # Anything served now would be different — the primed value must win.
    _FakeClient.payload = _openai_payload("something-else")
    ids = await model_discovery.discover_provider_models(
        provider="gw", base_url="https://gw/v1", api_key="k"
    )
    assert ids == ["m1", "m2"]
