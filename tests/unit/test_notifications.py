"""Unit tests for the YooKassa webhook endpoint (Kafka producer is mocked)."""

import json
from unittest.mock import AsyncMock

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
        "app": AppStub(),
    }
    return Request(scope, receive)


class AppStub:
    def __init__(self):
        self.state = StateStub()


class StateStub:
    def __init__(self):
        self.producer = AsyncMock()


def _waiting_for_capture(
    payment_id="pay-1", username="alice", appids="42"
) -> bytes:
    metadata = {}
    if username is not None:
        metadata["username"] = username
    if appids is not None:
        metadata["appids"] = appids
    return json.dumps(
        {
            "event": "payment.waiting_for_capture",
            "object": {"id": payment_id, "metadata": metadata},
        }
    ).encode()


def _producer_of(request: Request) -> AsyncMock:
    return request.scope["app"].state.producer


@pytest.fixture(autouse=True)
def mark_grant_requested(monkeypatch):
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(payment_router, "mark_grant_requested", mock)
    return mock


async def test_waiting_for_capture_publishes_a_grant_request():
    request = _request(_waiting_for_capture())
    response = await payment_router.notifications(request)

    assert response == {"status": "OK"}
    producer = _producer_of(request)
    producer.send_and_wait.assert_awaited_once()
    topic, body = producer.send_and_wait.await_args.args
    assert topic == payment_router.get_payment_settings().grant_requests_topic
    assert json.loads(body) == {
        "payment_id": "pay-1",
        "username": "alice",
        "appids": [42],
    }


async def test_cart_payment_publishes_every_appid():
    request = _request(_waiting_for_capture(appids="1,2,3"))
    response = await payment_router.notifications(request)

    assert response == {"status": "OK"}
    _, body = _producer_of(request).send_and_wait.await_args.args
    assert json.loads(body)["appids"] == [1, 2, 3]


async def test_other_events_are_ignored():
    payload = json.dumps(
        {
            "event": "payment.canceled",
            "object": {"id": "pay-1", "metadata": {"username": "alice", "appids": "42"}},
        }
    ).encode()
    request = _request(payload)
    response = await payment_router.notifications(request)

    assert response == {"status": "OK"}
    _producer_of(request).send_and_wait.assert_not_awaited()


async def test_missing_metadata_is_ignored():
    payload = json.dumps(
        {"event": "payment.waiting_for_capture", "object": {"id": "pay-1"}}
    ).encode()
    request = _request(payload)
    response = await payment_router.notifications(request)

    assert response == {"status": "OK"}
    _producer_of(request).send_and_wait.assert_not_awaited()


async def test_missing_username_is_ignored():
    request = _request(_waiting_for_capture(username=None))
    response = await payment_router.notifications(request)

    assert response == {"status": "OK"}
    _producer_of(request).send_and_wait.assert_not_awaited()


async def test_non_integer_appids_are_dropped_individually():
    request = _request(_waiting_for_capture(appids="1,not-a-number,3"))
    response = await payment_router.notifications(request)

    assert response == {"status": "OK"}
    _, body = _producer_of(request).send_and_wait.await_args.args
    assert json.loads(body)["appids"] == [1, 3]


async def test_all_invalid_appids_are_ignored():
    request = _request(_waiting_for_capture(appids="not,numbers"))
    response = await payment_router.notifications(request)

    assert response == {"status": "OK"}
    _producer_of(request).send_and_wait.assert_not_awaited()


async def test_malformed_body_is_accepted():
    request = _request(b"not json")
    response = await payment_router.notifications(request)

    assert response == {"status": "OK"}
    _producer_of(request).send_and_wait.assert_not_awaited()


async def test_redelivered_webhook_is_not_republished(mark_grant_requested):
    # a payment already past `pending` (grant already requested, or unknown)
    # means this is a YooKassa retry of a webhook already handled once
    mark_grant_requested.return_value = False

    request = _request(_waiting_for_capture())
    response = await payment_router.notifications(request)

    assert response == {"status": "OK"}
    mark_grant_requested.assert_awaited_once_with("pay-1")
    _producer_of(request).send_and_wait.assert_not_awaited()
