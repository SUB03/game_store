"""Unit tests for payment_service's stuck-payment reconciliation sweep
(DB/Kafka/gRPC all mocked)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import payment_service.reconcile as reconcile

GRANT_REQUESTS_TOPIC = "payment.grant-requests"


def _row(payment_id="pay-1", username="alice", appids=None, status="grant_requested", attempts=0):
    return SimpleNamespace(
        payment_id=payment_id,
        username=username,
        appids=appids if appids is not None else [1, 2],
        status=status,
        attempts=attempts,
    )


@pytest.fixture
def producer():
    return AsyncMock()


@pytest.fixture
def mocks(monkeypatch):
    fetch_stuck = AsyncMock(return_value=[])
    bump_attempts = AsyncMock()
    mark_granted_pending_capture = AsyncMock()
    get_owned_games = AsyncMock(return_value=[])
    monkeypatch.setattr(reconcile, "fetch_stuck", fetch_stuck)
    monkeypatch.setattr(reconcile, "bump_attempts", bump_attempts)
    monkeypatch.setattr(
        reconcile, "mark_granted_pending_capture", mark_granted_pending_capture
    )
    monkeypatch.setattr(reconcile, "get_owned_games", get_owned_games)
    return {
        "fetch_stuck": fetch_stuck,
        "bump_attempts": bump_attempts,
        "mark_granted_pending_capture": mark_granted_pending_capture,
        "get_owned_games": get_owned_games,
    }


async def test_grant_requested_is_republished_when_not_yet_owned(producer, mocks):
    mocks["fetch_stuck"].return_value = [_row(appids=[1, 2])]
    mocks["get_owned_games"].return_value = []

    await reconcile.sweep_once(producer, GRANT_REQUESTS_TOPIC, 600, 10)

    producer.send_and_wait.assert_awaited_once()
    topic, body = producer.send_and_wait.await_args.args
    assert topic == GRANT_REQUESTS_TOPIC
    assert json.loads(body) == {"payment_id": "pay-1", "username": "alice", "appids": [1, 2]}
    mocks["bump_attempts"].assert_awaited_once_with("pay-1")
    mocks["mark_granted_pending_capture"].assert_not_awaited()


async def test_grant_requested_skips_to_capture_when_already_owned(producer, mocks):
    mocks["fetch_stuck"].return_value = [_row(appids=[1, 2])]
    mocks["get_owned_games"].return_value = [1, 2, 3]

    await reconcile.sweep_once(producer, GRANT_REQUESTS_TOPIC, 600, 10)

    producer.send_and_wait.assert_not_awaited()
    mocks["mark_granted_pending_capture"].assert_awaited_once_with("pay-1")


async def test_grant_requested_republishes_when_only_partially_owned(producer, mocks):
    mocks["fetch_stuck"].return_value = [_row(appids=[1, 2])]
    mocks["get_owned_games"].return_value = [1]

    await reconcile.sweep_once(producer, GRANT_REQUESTS_TOPIC, 600, 10)

    producer.send_and_wait.assert_awaited_once()
    mocks["mark_granted_pending_capture"].assert_not_awaited()


async def test_pending_row_is_only_logged_and_bumped(producer, mocks):
    mocks["fetch_stuck"].return_value = [_row(status="pending")]

    await reconcile.sweep_once(producer, GRANT_REQUESTS_TOPIC, 600, 10)

    producer.send_and_wait.assert_not_awaited()
    mocks["get_owned_games"].assert_not_awaited()
    mocks["bump_attempts"].assert_awaited_once_with("pay-1")
