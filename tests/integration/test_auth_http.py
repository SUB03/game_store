"""Integration tests for auth_service HTTP flows against real PostgreSQL."""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def auth_app(auth_db):
    from auth_service.main import api

    return api


@pytest.fixture
async def client(auth_app):
    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://testserver") as c:
        yield c


async def _register(client, username="alice", email="alice@example.com", password="s3cret-pw"):
    return await client.post(
        "/users/registrate",
        json={"username": username, "email": email, "password": password},
    )


# --- registration -----------------------------------------------------------

async def test_register_sets_cookies_and_returns_csrf(client):
    response = await _register(client)
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "authorized"
    assert body["CSRF"]
    assert client.cookies.get("access_token")
    assert client.cookies.get("refresh_token")
    # CSRF cookie mirrors the body value and is JS-readable for the header
    assert client.cookies.get("CSRF") == body["CSRF"]


async def test_register_duplicate_username_returns_409(client):
    assert (await _register(client)).status_code == 200
    response = await _register(client, email="other@example.com")
    assert response.status_code == 409


async def test_register_duplicate_email_returns_409(client):
    assert (await _register(client)).status_code == 200
    response = await _register(client, username="bob")
    assert response.status_code == 409


# --- login ------------------------------------------------------------------

async def test_login_with_correct_password(client):
    await _register(client)
    await client.post("/users/logout")

    response = await client.post(
        "/users/login", data={"username": "alice", "password": "s3cret-pw"}
    )
    assert response.status_code == 200
    assert client.cookies.get("access_token")
    assert client.cookies.get("refresh_token")
    assert client.cookies.get("CSRF") == response.json()["CSRF"]


async def test_login_with_wrong_password_returns_400(client):
    await _register(client)
    response = await client.post(
        "/users/login", data={"username": "alice", "password": "wrong"}
    )
    assert response.status_code == 400


async def test_login_for_unknown_user_returns_400(client):
    response = await client.post(
        "/users/login", data={"username": "ghost", "password": "whatever"}
    )
    assert response.status_code == 400


# --- /users/me --------------------------------------------------------------

async def test_me_returns_user_for_valid_session(client):
    await _register(client, username="alice")
    response = await client.get("/users/me")
    assert response.status_code == 200
    assert response.json() == {"username": "alice"}


async def test_me_requires_authentication(auth_app):
    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://testserver") as anon:
        response = await anon.get("/users/me")
    assert response.status_code == 401


async def test_me_accepts_a_structurally_valid_token_never_whitelisted(client, auth_app):
    # access tokens are stateless: signature + expiry is enough, even for a
    # jti that was never stored (whitelisting only ever gates /users/refresh)
    await _register(client, username="alice")

    from auth_service.routers.users.users_utils import create_jwt_token
    from datetime import datetime, timedelta, timezone
    import uuid as uuid_module

    token = create_jwt_token(
        {
            "sub": "alice",
            "jti": str(uuid_module.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        }
    )
    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url="http://testserver",
        cookies={"access_token": token},
    ) as unwhitelisted:
        response = await unwhitelisted.get("/users/me")
    assert response.status_code == 200


# --- refresh ----------------------------------------------------------------

async def test_refresh_rotates_tokens_and_revokes_old_refresh_token(client, auth_app):
    await _register(client, username="alice")
    old_access = client.cookies.get("access_token")
    old_refresh = client.cookies.get("refresh_token")

    response = await client.post("/users/refresh")
    assert response.status_code == 200
    new_csrf = response.json()["CSRF"]
    assert new_csrf

    new_access = client.cookies.get("access_token")
    new_refresh = client.cookies.get("refresh_token")
    assert new_access != old_access
    assert new_refresh != old_refresh
    # the CSRF cookie rotates together with the access token
    assert client.cookies.get("CSRF") == new_csrf

    # new session still works
    me = await client.get("/users/me")
    assert me.status_code == 200

    # the old refresh token's jti was removed from the whitelist by this
    # refresh - trying to reuse it must now fail (this is the one place
    # revocation actually takes effect; the old access token itself stays
    # valid until it naturally expires, since it's stateless)
    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url="http://testserver",
        cookies={"refresh_token": old_refresh},
    ) as stale:
        stale_response = await stale.post("/users/refresh")
    assert stale_response.status_code == 401


async def test_refresh_without_cookie_returns_401(auth_app):
    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://testserver") as anon:
        response = await anon.post("/users/refresh")
    assert response.status_code == 401


# --- logout -----------------------------------------------------------------

async def test_logout_clears_cookies_and_revokes_the_refresh_token(client, auth_app):
    await _register(client, username="alice")
    old_refresh = client.cookies.get("refresh_token")

    response = await client.post("/users/logout")
    assert response.status_code == 200
    assert client.cookies.get("access_token") is None
    assert client.cookies.get("refresh_token") is None
    assert client.cookies.get("CSRF") is None

    # logout deletes the jti from the whitelist, so the old refresh token
    # can no longer be used to mint a new session
    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url="http://testserver",
        cookies={"refresh_token": old_refresh},
    ) as stale:
        stale_response = await stale.post("/users/refresh")
    assert stale_response.status_code == 401
