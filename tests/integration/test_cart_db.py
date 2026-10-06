"""Integration tests for the cart against real PostgreSQL.

Covers the users_service servicer RPCs (storage semantics, checkout_key
lifecycle) and the payment_service GET /payment/cart SQL (owned/free filtering).
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from sqlalchemy.exc import IntegrityError
from users_proto.users_service_pb2 import (
    AddGameToCartRequest,
    ClearCartRequest,
    GetCartRequest,
    RemoveGameFromCartRequest,
)

import payment_service.router as payment_router
from payment_service.jwt_utils import settings as payment_settings
from users_service.main import Settings, UsersServiceServicer


@pytest.fixture
def servicer(db):
    return UsersServiceServicer(Settings())


@pytest.fixture
def context():
    return None  # the servicer never uses the ServicerContext


def _token(username: str) -> str:
    return pyjwt.encode(
        {
            "sub": username,
            "jti": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        payment_settings.secret_key,
        algorithm=payment_settings.algorithm,
    )


async def test_add_then_get_cart_returns_appids_and_checkout_key(
    servicer, context, seed_user, seed_game
):
    username = await seed_user(username="alice")
    appid = await seed_game(name="Carted Game")

    added = await servicer.AddGameToCart(
        AddGameToCartRequest(username=username, appid=appid), context
    )
    assert added.appid == appid
    assert added.added is True

    cart = await servicer.GetCart(GetCartRequest(username=username), context)
    assert list(cart.appids) == [appid]
    # the backend-generated key for the whole cart is a valid UUID
    uuid.UUID(cart.checkout_key)


async def test_adding_the_same_game_twice_is_idempotent(
    servicer, context, seed_user, seed_game
):
    username = await seed_user(username="alice")
    appid = await seed_game(name="Carted Game")

    first = await servicer.AddGameToCart(
        AddGameToCartRequest(username=username, appid=appid), context
    )
    second = await servicer.AddGameToCart(
        AddGameToCartRequest(username=username, appid=appid), context
    )

    assert first.added is True
    assert second.added is False

    cart = await servicer.GetCart(GetCartRequest(username=username), context)
    assert list(cart.appids) == [appid]


async def test_second_game_reuses_the_cart_checkout_key(
    servicer, context, seed_user, seed_game
):
    username = await seed_user(username="alice")
    first_appid = await seed_game(name="First Game")
    second_appid = await seed_game(name="Second Game")

    await servicer.AddGameToCart(
        AddGameToCartRequest(username=username, appid=first_appid), context
    )
    key_after_first = (
        await servicer.GetCart(GetCartRequest(username=username), context)
    ).checkout_key

    await servicer.AddGameToCart(
        AddGameToCartRequest(username=username, appid=second_appid), context
    )
    cart = await servicer.GetCart(GetCartRequest(username=username), context)

    assert sorted(cart.appids) == sorted([first_appid, second_appid])
    # one cart = one Idempotence-Key until the cart is emptied
    assert cart.checkout_key == key_after_first


async def test_remove_from_cart_is_idempotent(
    servicer, context, seed_user, seed_game
):
    username = await seed_user(username="alice")
    appid = await seed_game(name="Carted Game")

    await servicer.AddGameToCart(
        AddGameToCartRequest(username=username, appid=appid), context
    )

    first = await servicer.RemoveGameFromCart(
        RemoveGameFromCartRequest(username=username, appid=appid), context
    )
    second = await servicer.RemoveGameFromCart(
        RemoveGameFromCartRequest(username=username, appid=appid), context
    )

    assert first.removed is True
    assert second.removed is False

    cart = await servicer.GetCart(GetCartRequest(username=username), context)
    assert list(cart.appids) == []
    assert cart.checkout_key == ""


async def test_clear_cart_empties_the_cart(
    servicer, context, seed_user, seed_game
):
    username = await seed_user(username="alice")
    first_appid = await seed_game(name="First Game")
    second_appid = await seed_game(name="Second Game")

    await servicer.AddGameToCart(
        AddGameToCartRequest(username=username, appid=first_appid), context
    )
    await servicer.AddGameToCart(
        AddGameToCartRequest(username=username, appid=second_appid), context
    )

    cleared = await servicer.ClearCart(ClearCartRequest(username=username), context)
    assert cleared.removed == 2

    cart = await servicer.GetCart(GetCartRequest(username=username), context)
    assert list(cart.appids) == []


async def test_cart_requires_existing_user_and_game(
    servicer, context, seed_user, seed_game
):
    username = await seed_user(username="alice")
    appid = await seed_game(name="Carted Game")

    with pytest.raises(IntegrityError):
        await servicer.AddGameToCart(
            AddGameToCartRequest(username="ghost", appid=appid), context
        )
    with pytest.raises(IntegrityError):
        await servicer.AddGameToCart(
            AddGameToCartRequest(username=username, appid=999_999), context
        )


# --- payment_service GET /payment/cart against the real database --------------


async def test_get_cart_returns_paid_unowned_games_only(
    monkeypatch, seed_user, seed_game
):
    await seed_user(username="alice")
    paid = await seed_game(name="Paid Game", price="9.99")
    owned = await seed_game(name="Owned Game", price="4.99")
    free = await seed_game(name="Free Game", price="0.00")

    async def fake_get_user_cart(username):
        assert username == "alice"
        return [paid, owned, free], "cart-key"

    async def fake_get_owned_games(username):
        assert username == "alice"
        return [owned]

    monkeypatch.setattr(payment_router, "get_user_cart", fake_get_user_cart)
    monkeypatch.setattr(payment_router, "get_owned_games", fake_get_owned_games)

    result = await payment_router.get_cart(access_token=_token("alice"))

    appids = [row["appid"] for row in result["results"]]
    # owned and free games never show up in a cart
    assert appids == [paid]


async def test_get_cart_with_empty_cart_hits_no_database(monkeypatch):
    async def fake_get_user_cart(username):
        return [], ""

    monkeypatch.setattr(payment_router, "get_user_cart", fake_get_user_cart)

    original = payment_router.engine
    sentinel = object()
    payment_router.engine = sentinel
    try:
        result = await payment_router.get_cart(access_token=_token("alice"))
    finally:
        payment_router.engine = original

    assert result == {"results": []}
