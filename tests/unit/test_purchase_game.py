"""Unit tests for the payment_service purchase flow (DB and gRPC are mocked).

The endpoint is exercised by calling the router function directly instead of
through the ASGI app: importing ``payment_service.main`` alongside
``auth_service.main`` would register duplicate Prometheus timeseries in the
single test process.
"""

import uuid
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import jwt as pyjwt
import pytest
from fastapi import HTTPException

import payment_service.router as payment_router
from payment_service.schemas import PurchaseGame
from payment_service.jwt_utils import settings as payment_settings

Row = namedtuple("Row", ["appid", "name", "price"])


def _access_token(jti: str, username: str = "alice") -> str:
    return pyjwt.encode(
        {
            "sub": username,
            "jti": jti,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        payment_settings.secret_key,
        algorithm=payment_settings.algorithm,
    )


async def _purchase(csrf: str | None, appid: int, access_token):
    purchase = PurchaseGame(appid=appid)
    return await payment_router.purchase_game(
        purchase, csrf=csrf, access_token=access_token
    )


@pytest.fixture
def mocks(monkeypatch):
    """Replace all external dependencies of the purchase endpoint."""
    has_game = AsyncMock(return_value=False)
    get_price = AsyncMock(return_value=Row(appid=42, name="Some Game", price="9.99"))
    make_payment = AsyncMock(
        return_value={"payment_id": "pay-1", "confirmation_url": "https://pay"}
    )
    add_game = AsyncMock(return_value={"message": "added the game", "appid": 42})
    monkeypatch.setattr(payment_router, "has_game", has_game)
    monkeypatch.setattr(payment_router, "get_price", get_price)
    monkeypatch.setattr(payment_router, "make_payment", make_payment)
    monkeypatch.setattr(payment_router, "add_game", add_game)
    return {
        "has_game": has_game,
        "get_price": get_price,
        "make_payment": make_payment,
        "add_game": add_game,
    }


async def test_purchase_requires_access_token_cookie(mocks):
    with pytest.raises(HTTPException) as exc_info:
        await _purchase("x", 42, None)
    assert exc_info.value.status_code == 401


async def test_purchase_rejects_invalid_token(mocks):
    with pytest.raises(HTTPException) as exc_info:
        await _purchase("x", 42, "not.a.jwt")
    assert exc_info.value.status_code == 401
    mocks["has_game"].assert_not_awaited()


async def test_purchase_rejects_expired_token(mocks):
    expired = pyjwt.encode(
        {
            "sub": "alice",
            "jti": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        payment_settings.secret_key,
        algorithm=payment_settings.algorithm,
    )
    with pytest.raises(HTTPException) as exc_info:
        await _purchase("whatever", 42, expired)
    assert exc_info.value.status_code == 401


async def test_purchase_rejects_missing_csrf_header(mocks):
    token = _access_token(str(uuid.uuid4()))
    with pytest.raises(HTTPException) as exc_info:
        await _purchase(None, 42, token)
    assert exc_info.value.status_code == 401
    mocks["has_game"].assert_not_awaited()


async def test_purchase_rejects_csrf_mismatch(mocks):
    token = _access_token(str(uuid.uuid4()))
    with pytest.raises(HTTPException) as exc_info:
        await _purchase("wrong-csrf", 42, token)
    assert exc_info.value.status_code == 401
    mocks["has_game"].assert_not_awaited()


async def test_purchase_rejects_already_owned_game(mocks):
    jti = str(uuid.uuid4())
    mocks["has_game"].return_value = True
    with pytest.raises(HTTPException) as exc_info:
        await _purchase(jti, 42, _access_token(jti))
    assert exc_info.value.status_code == 409
    mocks["get_price"].assert_not_awaited()


async def test_purchase_unknown_appid_returns_404(mocks):
    jti = str(uuid.uuid4())
    mocks["get_price"].return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await _purchase(jti, 404404, _access_token(jti))
    assert exc_info.value.status_code == 404
    mocks["make_payment"].assert_not_awaited()
    mocks["add_game"].assert_not_awaited()


async def test_purchase_paid_game_starts_payment(mocks):
    jti = str(uuid.uuid4())
    result = await _purchase(jti, 42, _access_token(jti))
    assert result == {"payment_id": "pay-1", "confirmation_url": "https://pay"}
    mocks["make_payment"].assert_awaited_once()
    mocks["add_game"].assert_not_awaited()


async def test_purchase_free_game_grants_ownership(mocks):
    jti = str(uuid.uuid4())
    mocks["get_price"].return_value = Row(appid=42, name="Free Game", price="0.00")
    result = await _purchase(jti, 42, _access_token(jti))
    assert result == {"message": "added the game", "appid": 42}
    mocks["add_game"].assert_awaited_once()
    mocks["make_payment"].assert_not_awaited()


async def test_purchase_passes_username_and_appid(mocks):
    jti = str(uuid.uuid4())
    await _purchase(jti, 42, _access_token(jti, username="bob"))
    mocks["has_game"].assert_awaited_once_with(username="bob", appid=42)
    mocks["make_payment"].assert_awaited_once_with(username="bob", appid=42, price="9.99")
