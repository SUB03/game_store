"""Unit tests for the YooKassa webhook endpoint (gRPC / DB are mocked)."""

import json
from unittest.mock import AsyncMock, call

import pytest
from starlette.requests import Request

import payment_service.router as payment_router


def _request(payload: bytes) -> Request:
    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/payment/notifications",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 1),
    }
    return Request(scope, receive)


@pytest.fixture
def mocks(monkeypatch):
    has_game = AsyncMock(return_value=False)
    add_game = AsyncMock(return_value={"message": "added the game", "appid": 42})
    remove_game_from_cart = AsyncMock(return_value={"appid": 42, "removed": True})
    monkeypatch.setattr(payment_router, "has_game", has_game)
    monkeypatch.setattr(payment_router, "add_game", add_game)
    monkeypatch.setattr(payment_router, "remove_game_from_cart", remove_game_from_cart)
    return {
        "has_game": has_game,
        "add_game": add_game,
        "remove_game_from_cart": remove_game_from_cart,
    }


def _succeeded(username="alice", appid="42", appids=None) -> bytes:
    metadata = {"username": username}
    if appids is not None:
        metadata["appids"] = appids
    if appid is not None:
        metadata["appid"] = appid
    return json.dumps(
        {
            "event": "payment.succeeded",
            "object": {"metadata": metadata},
        }
    ).encode()


async def test_succeeded_payment_grants_the_game(mocks):
    response = await payment_router.notifications(_request(_succeeded()))
    assert response == {"status": "OK"}
    mocks["has_game"].assert_awaited_once_with(username="alice", appid=42)
    mocks["add_game"].assert_awaited_once_with(username="alice", appid=42)


async def test_succeeded_payment_is_idempotent(mocks):
    mocks["has_game"].return_value = True
    response = await payment_router.notifications(_request(_succeeded()))
    assert response == {"status": "OK"}
    mocks["add_game"].assert_not_awaited()


async def test_other_events_are_ignored(mocks):
    payload = json.dumps(
        {
            "event": "payment.canceled",
            "object": {"metadata": {"username": "alice", "appid": "42"}},
        }
    ).encode()
    response = await payment_router.notifications(_request(payload))
    assert response == {"status": "OK"}
    mocks["has_game"].assert_not_awaited()
    mocks["add_game"].assert_not_awaited()


async def test_missing_metadata_is_ignored(mocks):
    payload = json.dumps({"event": "payment.succeeded", "object": {}}).encode()
    response = await payment_router.notifications(_request(payload))
    assert response == {"status": "OK"}
    mocks["has_game"].assert_not_awaited()
    mocks["add_game"].assert_not_awaited()


async def test_non_integer_appid_is_ignored(mocks):
    response = await payment_router.notifications(
        _request(_succeeded(appid="not-a-number"))
    )
    assert response == {"status": "OK"}
    mocks["has_game"].assert_not_awaited()
    mocks["add_game"].assert_not_awaited()


async def test_malformed_body_is_accepted(mocks):
    response = await payment_router.notifications(_request(b"not json"))
    assert response == {"status": "OK"}
    mocks["has_game"].assert_not_awaited()
    mocks["add_game"].assert_not_awaited()


# --- cart (multi-game) payments ----------------------------------------------


async def test_cart_payment_grants_every_game_in_appids_metadata(mocks):
    response = await payment_router.notifications(
        _request(_succeeded(appid=None, appids="1,2,3"))
    )

    assert response == {"status": "OK"}
    assert mocks["has_game"].await_args_list == [
        call(username="alice", appid=1),
        call(username="alice", appid=2),
        call(username="alice", appid=3),
    ]
    assert mocks["add_game"].await_args_list == [
        call(username="alice", appid=1),
        call(username="alice", appid=2),
        call(username="alice", appid=3),
    ]
    # every paid game is stripped from the cart once granted
    assert mocks["remove_game_from_cart"].await_args_list == [
        call(username="alice", appid=1),
        call(username="alice", appid=2),
        call(username="alice", appid=3),
    ]


async def test_cart_payment_strips_rows_even_when_already_owned(mocks):
    mocks["has_game"].return_value = True

    response = await payment_router.notifications(
        _request(_succeeded(appid=None, appids="1,2"))
    )

    assert response == {"status": "OK"}
    mocks["add_game"].assert_not_awaited()
    assert mocks["remove_game_from_cart"].await_args_list == [
        call(username="alice", appid=1),
        call(username="alice", appid=2),
    ]


async def test_cart_strip_failure_never_fails_the_webhook(mocks):
    mocks["remove_game_from_cart"].side_effect = RuntimeError("users_service down")

    response = await payment_router.notifications(
        _request(_succeeded(appid=None, appids="1,2"))
    )

    # the games were granted; cart cleanup is best effort so YooKassa's
    # retry storm cannot be triggered by a cleanup hiccup
    assert response == {"status": "OK"}
    assert mocks["add_game"].await_count == 2


async def test_invalid_appids_metadata_is_ignored(mocks):
    response = await payment_router.notifications(
        _request(_succeeded(appid=None, appids="not,numbers"))
    )

    assert response == {"status": "OK"}
    mocks["has_game"].assert_not_awaited()
    mocks["add_game"].assert_not_awaited()
    mocks["remove_game_from_cart"].assert_not_awaited()