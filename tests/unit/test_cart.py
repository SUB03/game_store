"""Unit tests for the payment cart / library / checkout endpoints (DB and gRPC mocked).

The endpoints are exercised by calling the router functions directly instead of
through the ASGI app: importing payment_service.main alongside auth_service.main
would register duplicate Prometheus timeseries in the single test process.
"""

import uuid
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import jwt as pyjwt
import pytest
from fastapi import HTTPException

import payment_service.router as payment_router
from payment_service.schemas import CartItem, CheckoutRequest, LibraryGame
from payment_service.jwt_utils import settings as payment_settings

VALID_IDEMPOTENCY_KEY = "12345678-1234-5678-1234-567812345678"

PriceRow = namedtuple("PriceRow", ["appid", "name", "price"])


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


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def mappings(self):
        return SimpleNamespace(all=lambda: self._rows)

    def fetchall(self):
        return self._rows


class _FakeEngine:
    """Stands in for store_service.engine; records executed statements."""

    def __init__(self, rows=()):
        self.rows = list(rows)
        self.statements = []

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _Result(self.rows)


@pytest.fixture
def fake_engine():
    original = payment_router.engine
    engine = _FakeEngine()
    payment_router.engine = engine
    yield engine
    payment_router.engine = original


@pytest.fixture
def mocks(monkeypatch):
    """Replace every external dependency of the cart endpoints."""
    get_price = AsyncMock(
        return_value=PriceRow(appid=42, name="Some Game", price="9.99")
    )
    has_game = AsyncMock(return_value=False)
    add_game = AsyncMock(return_value={"message": "added the game", "appid": 42})
    add_game_to_cart = AsyncMock(return_value={"appid": 42, "added": True})
    remove_game_from_cart = AsyncMock(
        return_value={"appid": 42, "removed": True}
    )
    get_user_cart = AsyncMock(return_value=[])
    clear_user_cart = AsyncMock(return_value=0)
    make_payment_cart = AsyncMock(
        return_value={"payment_id": "pay-1", "confirmation_url": "https://pay"}
    )
    get_owned_games = AsyncMock(return_value=[])
    create_payment = AsyncMock(return_value=None)
    replacements = {
        "get_price": get_price,
        "has_game": has_game,
        "add_game": add_game,
        "add_game_to_cart": add_game_to_cart,
        "remove_game_from_cart": remove_game_from_cart,
        "get_user_cart": get_user_cart,
        "clear_user_cart": clear_user_cart,
        "make_payment_cart": make_payment_cart,
        "get_owned_games": get_owned_games,
        "create_payment": create_payment,
    }
    for name, mock in replacements.items():
        monkeypatch.setattr(payment_router, name, mock)
    return replacements


async def _get_cart(access_token):
    return await payment_router.get_cart(access_token=access_token)


# --- GET /store/cart ----------------------------------------------------------


async def test_get_cart_requires_access_token_cookie(mocks):
    with pytest.raises(HTTPException) as exc_info:
        await _get_cart(None)
    assert exc_info.value.status_code == 401
    mocks["get_user_cart"].assert_not_awaited()


async def test_get_cart_rejects_invalid_token(mocks):
    with pytest.raises(HTTPException) as exc_info:
        await _get_cart("not.a.jwt")
    assert exc_info.value.status_code == 401
    mocks["get_user_cart"].assert_not_awaited()


async def test_get_cart_rejects_expired_token(mocks):
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
        await _get_cart(expired)
    assert exc_info.value.status_code == 401



async def test_empty_cart_skips_all_lookups(mocks, fake_engine):
    result = await _get_cart(_access_token(str(uuid.uuid4())))

    assert result == {"results": []}
    assert fake_engine.statements == []
    mocks["get_owned_games"].assert_not_awaited()


async def test_cart_with_only_owned_games_skips_database(mocks, fake_engine):
    mocks["get_user_cart"].return_value = [42]
    mocks["get_owned_games"].return_value = [42]

    result = await _get_cart(_access_token(str(uuid.uuid4())))

    assert result == {"results": []}
    assert fake_engine.statements == []


async def test_get_cart_returns_joined_game_rows(mocks, fake_engine):
    mocks["get_user_cart"].return_value = [42]
    mocks["get_owned_games"].return_value = []
    rows = [{"appid": 42, "name": "Some Game", "price": "9.99", "tags": ["Action"]}]
    fake_engine.rows = rows

    result = await _get_cart(_access_token(str(uuid.uuid4()), username="bob"))

    assert result == {"results": rows}
    assert len(fake_engine.statements) == 1
    mocks["get_user_cart"].assert_awaited_once_with(username="bob")


async def _add_to_cart(csrf, appid, access_token):
    return await payment_router.add_to_cart(
        CartItem(appid=appid), csrf=csrf, access_token=access_token
    )


# --- POST /store/cart ---------------------------------------------------------


async def test_add_to_cart_requires_access_token(mocks):
    with pytest.raises(HTTPException) as exc_info:
        await _add_to_cart("csrf", 42, None)
    assert exc_info.value.status_code == 401


async def test_add_to_cart_rejects_missing_csrf_header(mocks):
    jti = str(uuid.uuid4())
    with pytest.raises(HTTPException) as exc_info:
        await _add_to_cart(None, 42, _access_token(jti))
    assert exc_info.value.status_code == 401
    mocks["add_game_to_cart"].assert_not_awaited()


async def test_add_to_cart_rejects_csrf_mismatch(mocks):
    jti = str(uuid.uuid4())
    with pytest.raises(HTTPException) as exc_info:
        await _add_to_cart("wrong-csrf", 42, _access_token(jti))
    assert exc_info.value.status_code == 401
    mocks["add_game_to_cart"].assert_not_awaited()


async def test_add_to_cart_unknown_appid_returns_404(mocks):
    jti = str(uuid.uuid4())
    mocks["get_price"].return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await _add_to_cart(jti, 404404, _access_token(jti))
    assert exc_info.value.status_code == 404
    mocks["add_game_to_cart"].assert_not_awaited()


async def test_add_to_cart_rejects_free_game(mocks):
    jti = str(uuid.uuid4())
    mocks["get_price"].return_value = PriceRow(
        appid=7, name="Free Game", price="0.00"
    )
    with pytest.raises(HTTPException) as exc_info:
        await _add_to_cart(jti, 7, _access_token(jti))
    assert exc_info.value.status_code == 400
    mocks["add_game_to_cart"].assert_not_awaited()


async def test_add_to_cart_rejects_owned_game(mocks):
    jti = str(uuid.uuid4())
    mocks["has_game"].return_value = True
    with pytest.raises(HTTPException) as exc_info:
        await _add_to_cart(jti, 42, _access_token(jti))
    assert exc_info.value.status_code == 409
    mocks["add_game_to_cart"].assert_not_awaited()


async def test_add_to_cart_passes_username_and_appid(mocks):
    jti = str(uuid.uuid4())
    result = await _add_to_cart(jti, 42, _access_token(jti, username="bob"))

    assert result == {"appid": 42, "added": True}
    mocks["has_game"].assert_awaited_once_with(username="bob", appid=42)
    mocks["add_game_to_cart"].assert_awaited_once_with(username="bob", appid=42)


async def test_add_to_cart_is_idempotent_passthrough(mocks):
    # users_service reports added=False when the game is already carted;
    # the endpoint just relays that no-op instead of failing.
    mocks["add_game_to_cart"].return_value = {"appid": 42, "added": False}
    jti = str(uuid.uuid4())
    result = await _add_to_cart(jti, 42, _access_token(jti))

    assert result == {"appid": 42, "added": False}


async def _add_to_library(csrf, appid, access_token):
    return await payment_router.add_to_library(
        LibraryGame(appid=appid), csrf=csrf, access_token=access_token
    )


# --- POST /store/library ------------------------------------------------------


async def test_add_to_library_requires_csrf(mocks):
    jti = str(uuid.uuid4())
    with pytest.raises(HTTPException) as exc_info:
        await _add_to_library(None, 7, _access_token(jti))
    assert exc_info.value.status_code == 401
    mocks["add_game"].assert_not_awaited()


async def test_add_to_library_unknown_appid_returns_404(mocks):
    jti = str(uuid.uuid4())
    mocks["get_price"].return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await _add_to_library(jti, 404404, _access_token(jti))
    assert exc_info.value.status_code == 404
    mocks["add_game"].assert_not_awaited()


async def test_add_to_library_rejects_paid_game(mocks):
    jti = str(uuid.uuid4())
    with pytest.raises(HTTPException) as exc_info:
        await _add_to_library(jti, 42, _access_token(jti))  # price 9.99
    assert exc_info.value.status_code == 400
    mocks["add_game"].assert_not_awaited()


async def test_add_to_library_grants_free_game(mocks):
    jti = str(uuid.uuid4())
    mocks["get_price"].return_value = PriceRow(
        appid=7, name="Free Game", price="0.00"
    )
    result = await _add_to_library(jti, 7, _access_token(jti, username="bob"))

    assert result == {"appid": 42, "added": True}
    mocks["add_game"].assert_awaited_once_with(username="bob", appid=7)


async def test_add_to_library_is_idempotent_for_owned_game(mocks):
    jti = str(uuid.uuid4())
    mocks["get_price"].return_value = PriceRow(
        appid=7, name="Free Game", price="0.00"
    )
    mocks["has_game"].return_value = True

    result = await _add_to_library(jti, 7, _access_token(jti))

    assert result == {"appid": 7, "added": False}
    mocks["add_game"].assert_not_awaited()


async def _remove_from_cart(csrf, appid, access_token):
    return await payment_router.remove_from_cart(
        appid=appid, csrf=csrf, access_token=access_token
    )


async def _clear_cart(csrf, access_token):
    return await payment_router.clear_cart(csrf=csrf, access_token=access_token)


# --- DELETE /store/cart -------------------------------------------------------


async def test_remove_from_cart_requires_csrf(mocks):
    jti = str(uuid.uuid4())
    with pytest.raises(HTTPException) as exc_info:
        await _remove_from_cart(None, 42, _access_token(jti))
    assert exc_info.value.status_code == 401
    mocks["remove_game_from_cart"].assert_not_awaited()


async def test_remove_from_cart_passes_username_and_appid(mocks):
    jti = str(uuid.uuid4())
    result = await _remove_from_cart(jti, 42, _access_token(jti, username="bob"))

    assert result == {"appid": 42, "removed": True}
    mocks["remove_game_from_cart"].assert_awaited_once_with(
        username="bob", appid=42
    )


async def test_remove_from_cart_relays_missing_row(mocks):
    mocks["remove_game_from_cart"].return_value = {"appid": 42, "removed": False}
    jti = str(uuid.uuid4())
    result = await _remove_from_cart(jti, 42, _access_token(jti))

    assert result == {"appid": 42, "removed": False}


async def test_clear_cart_requires_access_token(mocks):
    with pytest.raises(HTTPException) as exc_info:
        await _clear_cart("csrf", None)
    assert exc_info.value.status_code == 401


async def test_clear_cart_returns_removed_count(mocks):
    mocks["clear_user_cart"].return_value = 3
    jti = str(uuid.uuid4())
    result = await _clear_cart(jti, _access_token(jti, username="bob"))

    assert result == {"removed": 3}
    mocks["clear_user_cart"].assert_awaited_once_with(username="bob")


async def _checkout(csrf, access_token, idempotency_key=VALID_IDEMPOTENCY_KEY):
    return await payment_router.checkout(
        CheckoutRequest(idempotency_key=idempotency_key),
        csrf=csrf,
        access_token=access_token,
    )


# --- POST /store/checkout -----------------------------------------------------


async def test_checkout_requires_csrf(mocks):
    jti = str(uuid.uuid4())
    with pytest.raises(HTTPException) as exc_info:
        await _checkout(None, _access_token(jti))
    assert exc_info.value.status_code == 401
    mocks["make_payment_cart"].assert_not_awaited()


async def test_checkout_empty_cart_returns_400(mocks):
    jti = str(uuid.uuid4())
    with pytest.raises(HTTPException) as exc_info:
        await _checkout(jti, _access_token(jti))
    assert exc_info.value.status_code == 400
    mocks["get_owned_games"].assert_not_awaited()
    mocks["make_payment_cart"].assert_not_awaited()


async def test_checkout_rejects_invalid_idempotency_key(mocks):
    jti = str(uuid.uuid4())
    with pytest.raises(HTTPException) as exc_info:
        await _checkout(jti, _access_token(jti), idempotency_key="not-a-uuid")
    assert exc_info.value.status_code == 400
    mocks["get_user_cart"].assert_not_awaited()
    mocks["make_payment_cart"].assert_not_awaited()


async def test_checkout_strips_owned_rows_then_rejects(mocks):
    jti = str(uuid.uuid4())
    mocks["get_user_cart"].return_value = [1, 2]
    mocks["get_owned_games"].return_value = [1, 2]

    with pytest.raises(HTTPException) as exc_info:
        await _checkout(jti, _access_token(jti))

    assert exc_info.value.status_code == 400
    assert mocks["remove_game_from_cart"].await_args_list == [
        call(username="alice", appid=1),
        call(username="alice", appid=2),
    ]
    mocks["make_payment_cart"].assert_not_awaited()


async def test_checkout_starts_one_payment_for_the_whole_cart(
    mocks, fake_engine
):
    jti = str(uuid.uuid4())
    mocks["get_user_cart"].return_value = [42, 43]
    fake_engine.rows = [
        SimpleNamespace(appid=42, price=Decimal("9.99")),
        SimpleNamespace(appid=43, price=Decimal("5.00")),
    ]

    result = await _checkout(jti, _access_token(jti, username="bob"))

    assert result == {
        "payment_id": "pay-1",
        "confirmation_url": "https://pay",
    }
    mocks["make_payment_cart"].assert_awaited_once_with(
        username="bob",
        appids=[42, 43],
        price="14.99",
        idempotency_key=uuid.UUID(VALID_IDEMPOTENCY_KEY),
    )
    mocks["create_payment"].assert_awaited_once_with(
        payment_id="pay-1",
        username="bob",
        appids=[42, 43],
        idempotency_key=VALID_IDEMPOTENCY_KEY,
    )
    # paid rows stay in the cart until the webhook grants them
    mocks["remove_game_from_cart"].assert_not_awaited()
    mocks["add_game"].assert_not_awaited()


async def test_checkout_strips_owned_rows_and_pays_the_rest(mocks, fake_engine):
    jti = str(uuid.uuid4())
    mocks["get_user_cart"].return_value = [42, 43]
    mocks["get_owned_games"].return_value = [42]
    fake_engine.rows = [SimpleNamespace(appid=43, price=Decimal("5.00"))]

    result = await _checkout(jti, _access_token(jti))

    assert result["confirmation_url"] == "https://pay"
    mocks["remove_game_from_cart"].assert_awaited_once_with(
        username="alice", appid=42
    )
    mocks["make_payment_cart"].assert_awaited_once_with(
        username="alice",
        appids=[43],
        price="5.00",
        idempotency_key=uuid.UUID(VALID_IDEMPOTENCY_KEY),
    )


async def test_checkout_grants_free_rows_without_payment(mocks, fake_engine):
    jti = str(uuid.uuid4())
    mocks["get_user_cart"].return_value = [7]
    fake_engine.rows = [SimpleNamespace(appid=7, price=Decimal("0.00"))]

    result = await _checkout(jti, _access_token(jti))

    assert result == {"message": "added the games", "appids": [7]}
    mocks["add_game"].assert_awaited_once_with(username="alice", appid=7)
    mocks["remove_game_from_cart"].assert_awaited_once_with(
        username="alice", appid=7
    )
    mocks["make_payment_cart"].assert_not_awaited()


async def test_checkout_drops_rows_missing_from_the_catalog(mocks, fake_engine):
    jti = str(uuid.uuid4())
    mocks["get_user_cart"].return_value = [7]
    fake_engine.rows = []  # game no longer exists

    with pytest.raises(HTTPException) as exc_info:
        await _checkout(jti, _access_token(jti))

    assert exc_info.value.status_code == 400
    mocks["remove_game_from_cart"].assert_awaited_once_with(
        username="alice", appid=7
    )
    mocks["make_payment_cart"].assert_not_awaited()
    mocks["add_game"].assert_not_awaited()

