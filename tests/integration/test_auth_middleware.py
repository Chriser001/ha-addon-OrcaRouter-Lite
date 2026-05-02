"""Auth middleware integration tests.

We mount the middleware on a tiny FastAPI app and exercise it end-to-end via
the TestClient. This catches scope/state plumbing bugs that pure-unit tests
of `validate_api_key` would miss.
"""

import pytest


@pytest.fixture
async def app_with_auth(db_session, monkeypatch):
    """A FastAPI app with the lite auth middleware and one /v1/protected route."""
    monkeypatch.setenv("DATABASE_URL", str(db_session.bind.url))
    from fastapi import FastAPI, Request

    # The middleware imports get_session at module load — patch the binding it
    # actually uses (app.middleware.auth.get_session), not packages.db.session.
    from app.middleware import auth as auth_mod
    from app.middleware.auth import AuthMiddleware

    async def _get_session_override():
        yield db_session

    monkeypatch.setattr(auth_mod, "get_session", _get_session_override)

    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/v1/protected")
    async def protected(request: Request):
        # The middleware writes to scope["state"] as a dict; FastAPI's
        # Request.state may be a Starlette State, so read from scope directly.
        state = request.scope.get("state") or {}
        kc = state.get("key_context") if isinstance(state, dict) else getattr(state, "key_context", None)
        return {"workspace_id": kc.workspace_id if kc else None}

    @app.get("/health")
    async def health():
        return {"ok": True}

    return app


async def test_health_skips_auth(app_with_auth):
    """/health is on the public allowlist."""
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app_with_auth), base_url="http://t") as c:
        r = await c.get("/health")
    assert r.status_code == 200


async def test_protected_without_bearer_returns_401(app_with_auth):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app_with_auth), base_url="http://t") as c:
        r = await c.get("/v1/protected")
    assert r.status_code == 401
    body = r.json()
    assert body["error"]["type"] == "auth_error"


async def test_protected_with_invalid_key_returns_401(app_with_auth):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app_with_auth), base_url="http://t") as c:
        r = await c.get("/v1/protected", headers={"Authorization": "Bearer sk-orca-bogus"})
    assert r.status_code == 401


async def test_protected_with_valid_key_returns_200(app_with_auth, db_session):
    """A seeded key authenticates and KeyContext is attached to scope.state."""
    from httpx import ASGITransport, AsyncClient

    from app.seed import seed_initial_state

    seed = await seed_initial_state(db_session)
    assert seed.api_key is not None

    async with AsyncClient(transport=ASGITransport(app=app_with_auth), base_url="http://t") as c:
        r = await c.get("/v1/protected", headers={"Authorization": f"Bearer {seed.api_key}"})
    assert r.status_code == 200
    assert r.json() == {"workspace_id": "default"}
