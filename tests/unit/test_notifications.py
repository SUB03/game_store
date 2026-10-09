"""Unit tests for the YooKassa webhook endpoint (Kafka producer is mocked)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

import payment_service.router as payment_router


def _request(payload: bytes, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/payment/notifications",
        "headers": headers or [],
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


def _waiting_for_capture(payment_id="pay-1", metadata: dict | None = None) -> bytes:
    return json.dumps(
        {
            "event": "payment.waiting_for_capture",
            "object": {"id": payment_id, "metadata": metadata or {}},
        }
    ).encode()


def _producer_of(request: Request) -> AsyncMock:
    return request.scope["app"].state.producer


@pytest.fixture(autouse=True)
def mark_grant_requested(monkeypatch):
    mock = AsyncMock(
        return_value=SimpleNamespace(username="alice", appids=[42])
    )
    monkeypatch.setattr(payment_router, "mark_grant_requested", mock)
    return mock


async def test_waiting_for_capture_publishes_using_the_trusted_db_row(
    mark_grant_requested,
):
    # the request body carries no metadata at all - it no longer matters,
    # since username/appids come from the DB row mark_grant_requested returns.
    request = _request(_waiting_for_capture())
    response = await payment_router.notifications(request)

    assert response == {"status": "OK"}
    mark_grant_requested.assert_awaited_once_with("pay-1")
    producer = _producer_of(request)
    producer.send_and_wait.assert_awaited_once()
    topic, body = producer.send_and_wait.await_args.args
    assert topic == payment_router.get_payment_settings().grant_requests_topic
    assert json.loads(body) == {
        "payment_id": "pay-1",
        "username": "alice",
        "appids": [42],
    }


async def test_forged_metadata_is_ignored_in_favor_of_the_trusted_db_row(
    mark_grant_requested,
):
    # the webhook endpoint is public - this body claims a different user and
    # every paid appid in the catalog. The DB row (what was actually paid
    # for at checkout) must win, not this attacker-controlled metadata.
    request = _request(
        _waiting_for_capture(
            metadata={"username": "attacker", "appids": "1,2,3,4,5"}
        )
    )
    response = await payment_router.notifications(request)

    assert response == {"status": "OK"}
    _, body = _producer_of(request).send_and_wait.await_args.args
    assert json.loads(body) == {
        "payment_id": "pay-1",
        "username": "alice",
        "appids": [42],
    }


async def test_other_events_are_ignored(mark_grant_requested):
    payload = json.dumps(
        {"event": "payment.canceled", "object": {"id": "pay-1", "metadata": {}}}
    ).encode()
    request = _request(payload)
    response = await payment_router.notifications(request)

    assert response == {"status": "OK"}
    mark_grant_requested.assert_not_awaited()
    _producer_of(request).send_and_wait.assert_not_awaited()


async def test_missing_payment_id_is_ignored(mark_grant_requested):
    payload = json.dumps(
        {"event": "payment.waiting_for_capture", "object": {"metadata": {}}}
    ).encode()
    request = _request(payload)
    response = await payment_router.notifications(request)

    assert response == {"status": "OK"}
    mark_grant_requested.assert_not_awaited()
    _producer_of(request).send_and_wait.assert_not_awaited()


async def test_malformed_body_is_accepted(mark_grant_requested):
    request = _request(b"not json")
    response = await payment_router.notifications(request)

    assert response == {"status": "OK"}
    mark_grant_requested.assert_not_awaited()
    _producer_of(request).send_and_wait.assert_not_awaited()


async def test_redelivered_webhook_is_not_republished(mark_grant_requested):
    # a payment already past `pending` (grant already requested, or unknown)
    # means this is a YooKassa retry of a webhook already handled once
    mark_grant_requested.return_value = None

    request = _request(_waiting_for_capture())
    response = await payment_router.notifications(request)

    assert response == {"status": "OK"}
    mark_grant_requested.assert_awaited_once_with("pay-1")
    _producer_of(request).send_and_wait.assert_not_awaited()


# --- IP allowlist --------------------------------------------------------------


def _settings_requiring_ip_verification():
    return SimpleNamespace(
        verify_webhook_ip=True,
        yookassa_notification_cidrs=["185.71.76.0/27"],
        grant_requests_topic="payment.grant-requests",
    )


async def test_unallowlisted_ip_is_ignored_when_verification_enabled(
    monkeypatch, mark_grant_requested
):
    monkeypatch.setattr(
        payment_router, "get_payment_settings", _settings_requiring_ip_verification
    )
    request = _request(
        _waiting_for_capture(),
        headers=[(b"x-forwarded-for", b"8.8.8.8")],
    )
    response = await payment_router.notifications(request)

    assert response == {"status": "OK"}
    mark_grant_requested.assert_not_awaited()
    _producer_of(request).send_and_wait.assert_not_awaited()


async def test_allowlisted_ip_is_accepted_when_verification_enabled(
    monkeypatch, mark_grant_requested
):
    monkeypatch.setattr(
        payment_router, "get_payment_settings", _settings_requiring_ip_verification
    )
    request = _request(
        _waiting_for_capture(),
        headers=[(b"x-forwarded-for", b"185.71.76.5")],
    )
    response = await payment_router.notifications(request)

    assert response == {"status": "OK"}
    mark_grant_requested.assert_awaited_once_with("pay-1")
    _producer_of(request).send_and_wait.assert_awaited_once()
