"""Unit tests for auth_service user/token helpers (DB access is mocked)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from auth_service.routers.users import users_utils
from auth_service.schemas.users import UserDB
from auth_service.utils.hash_password import get_password_hash


def _user(password: str = "pw") -> UserDB:
    return UserDB(username="alice", hashed_password=get_password_hash(password))


# --- verify_user ------------------------------------------------------------

def test_verify_user_with_unknown_user_returns_false(monkeypatch):
    # must still run the dummy hash to keep timing consistent
    dummy = MagicMock()
    monkeypatch.setattr(users_utils, "verify_dummy", dummy)
    assert users_utils.verify_user(None, "whatever") is False
    dummy.assert_called_once_with("whatever")


def test_verify_user_with_wrong_password_returns_false():
    assert users_utils.verify_user(_user("correct"), "wrong") is False


def test_verify_user_with_correct_password_returns_user():
    user = _user("correct")
    assert users_utils.verify_user(user, "correct") is user


# --- get_user_from_jwt ------------------------------------------------------

def _valid_jwt(username: str = "alice") -> str:
    return users_utils.create_jwt_token(
        {"sub": username, "jti": "d9e3c2b1-0000-4000-8000-000000000000",
         "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}
    )


async def test_get_user_from_jwt_rejects_deleted_user(monkeypatch):
    monkeypatch.setattr(users_utils, "get_user", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc_info:
        await users_utils.get_user_from_jwt(_valid_jwt())
    assert exc_info.value.status_code == 401


async def test_get_user_from_jwt_rejects_expired_token(monkeypatch):
    expired = users_utils.create_jwt_token(
        {"sub": "alice", "jti": "d9e3c2b1-0000-4000-8000-000000000000",
         "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}
    )
    with pytest.raises(HTTPException) as exc_info:
        await users_utils.get_user_from_jwt(expired)
    assert exc_info.value.status_code == 401


async def test_get_user_from_jwt_returns_user_without_a_whitelist_check(monkeypatch):
    # access tokens are stateless - no DB check beyond signature/expiry,
    # even for a jti that was never stored or was since revoked.
    user = _user()
    get_user = AsyncMock(return_value=user)
    monkeypatch.setattr(users_utils, "get_user", get_user)

    result = await users_utils.get_user_from_jwt(_valid_jwt("alice"))

    assert result is user
    get_user.assert_awaited_once_with("alice")


# --- expire times -----------------------------------------------------------

def test_token_expire_constants():
    assert users_utils.ACCESS_TOKEN_EXPIRE_MINUTES == 15
    assert users_utils.REFRESH_TOKEN_EXPIRE_MINUTES == 31 * 24 * 60