"""Unit tests for payment_consumer's message handling and reconciliation
(gRPC/YooKassa/DB are mocked)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import grpc
import pytest

import payment_consumer.main as payment_consumer


def _message(payment_id="pay-1", username="alice", appids=None, granted=True):
    return json.dumps(
        {
            "payment_id": payment_id,
            "username": username,
            "appids": appids if appids is not None else [1, 2],
            "granted": granted,
        }
    ).encode()


DLQ_TOPIC = "payment.dead-letters"


@pytest.fixture
def stub():
    return AsyncMock()


@pytest.fixture
def producer():
    return AsyncMock()


async def _handle(raw, stub, producer):
    return await payment_consumer.handle_message(raw, stub, producer, DLQ_TOPIC)


@pytest.fixture
def mocks(monkeypatch):
    capture_payment = AsyncMock()
    cancel_payment = AsyncMock()
    set_status = AsyncMock()
    fetch_reconcilable = AsyncMock(return_value=[])
    monkeypatch.setattr(payment_consumer, "capture_payment", capture_payment)
    monkeypatch.setattr(payment_consumer, "cancel_payment", cancel_payment)
    monkeypatch.setattr(payment_consumer, "set_status", set_status)
    monkeypatch.setattr(payment_consumer, "fetch_reconcilable", fetch_reconcilable)
    return {
        "capture_payment": capture_payment,
        "cancel_payment": cancel_payment,
        "set_status": set_status,
        "fetch_reconcilable": fetch_reconcilable,
    }


# --- handle_message -----------------------------------------------------------


async def test_granted_payment_is_captured_and_cart_rows_removed(stub, producer, mocks):
    await _handle(_message(appids=[1, 2], granted=True), stub, producer)

    mocks["capture_payment"].assert_awaited_once_with("pay-1")
    mocks["cancel_payment"].assert_not_awaited()
    mocks["set_status"].assert_awaited_once_with("pay-1", "captured")
    assert stub.RemoveGameFromCart.await_args_list == [
        call(payment_consumer.us_pb2.RemoveGameFromCartRequest(username="alice", appid=1)),
        call(payment_consumer.us_pb2.RemoveGameFromCartRequest(username="alice", appid=2)),
    ]


async def test_ungranted_payment_is_cancelled_without_touching_the_cart(stub, producer, mocks):
    await _handle(_message(granted=False), stub, producer)

    mocks["cancel_payment"].assert_awaited_once_with("pay-1")
    mocks["capture_payment"].assert_not_awaited()
    mocks["set_status"].assert_awaited_once_with("pay-1", "canceled")
    stub.RemoveGameFromCart.assert_not_awaited()


async def test_cart_strip_failure_does_not_raise(stub, producer, mocks):
    error = grpc.aio.AioRpcError(
        grpc.StatusCode.UNAVAILABLE,
        initial_metadata=None,
        trailing_metadata=None,
        details="users_service down",
    )
    stub.RemoveGameFromCart.side_effect = error

    await _handle(_message(appids=[1], granted=True), stub, producer)

    mocks["capture_payment"].assert_awaited_once_with("pay-1")
    mocks["set_status"].assert_awaited_once_with("pay-1", "captured")


async def test_capture_failure_marks_granted_pending_capture_for_retry(stub, producer, mocks):
    mocks["capture_payment"].side_effect = RuntimeError("yookassa down")

    await _handle(_message(granted=True), stub, producer)

    stub.RemoveGameFromCart.assert_not_awaited()
    mocks["set_status"].assert_awaited_once_with(
        "pay-1", "granted_pending_capture", increment_attempts=True
    )


async def test_cancel_failure_marks_cancel_failed_for_retry(stub, producer, mocks):
    mocks["cancel_payment"].side_effect = RuntimeError("yookassa down")

    await _handle(_message(granted=False), stub, producer)

    mocks["set_status"].assert_awaited_once_with(
        "pay-1", "cancel_failed", increment_attempts=True
    )


async def test_malformed_json_is_sent_to_dlq(stub, producer, mocks):
    await _handle(b"not json", stub, producer)

    mocks["capture_payment"].assert_not_awaited()
    mocks["cancel_payment"].assert_not_awaited()
    topic, body = producer.send_and_wait.await_args.args
    assert topic == DLQ_TOPIC
    assert json.loads(body)["reason"].startswith("json:")


async def test_schema_violation_is_sent_to_dlq(stub, producer, mocks):
    bad = json.dumps({"payment_id": "pay-1", "username": "alice"}).encode()

    await _handle(bad, stub, producer)

    mocks["capture_payment"].assert_not_awaited()
    mocks["cancel_payment"].assert_not_awaited()
    topic, body = producer.send_and_wait.await_args.args
    assert topic == DLQ_TOPIC
    assert json.loads(body)["reason"].startswith("schema:")


# --- reconcile_once ------------------------------------------------------------


def _row(payment_id="pay-1", status="granted_pending_capture", attempts=1):
    return SimpleNamespace(payment_id=payment_id, status=status, attempts=attempts)


async def test_reconcile_retries_capture_and_marks_captured_on_success(mocks):
    mocks["fetch_reconcilable"].return_value = [_row(status="granted_pending_capture")]

    await payment_consumer.reconcile_once(max_attempts=5)

    mocks["capture_payment"].assert_awaited_once_with("pay-1")
    mocks["set_status"].assert_awaited_once_with("pay-1", "captured")


async def test_reconcile_retries_cancel_and_marks_canceled_on_success(mocks):
    mocks["fetch_reconcilable"].return_value = [_row(status="cancel_failed")]

    await payment_consumer.reconcile_once(max_attempts=5)

    mocks["cancel_payment"].assert_awaited_once_with("pay-1")
    mocks["set_status"].assert_awaited_once_with("pay-1", "canceled")


async def test_reconcile_keeps_retrying_capture_under_the_attempt_cap(mocks):
    mocks["capture_payment"].side_effect = RuntimeError("still down")
    mocks["fetch_reconcilable"].return_value = [_row(status="granted_pending_capture", attempts=1)]

    await payment_consumer.reconcile_once(max_attempts=5)

    mocks["set_status"].assert_awaited_once_with(
        "pay-1", "granted_pending_capture", increment_attempts=True
    )


async def test_reconcile_gives_up_on_capture_after_max_attempts(mocks):
    mocks["capture_payment"].side_effect = RuntimeError("still down")
    mocks["fetch_reconcilable"].return_value = [_row(status="granted_pending_capture", attempts=4)]

    await payment_consumer.reconcile_once(max_attempts=5)

    mocks["set_status"].assert_awaited_once_with(
        "pay-1", "capture_failed", increment_attempts=True
    )


async def test_reconcile_gives_up_on_cancel_after_max_attempts(mocks):
    mocks["cancel_payment"].side_effect = RuntimeError("still down")
    mocks["fetch_reconcilable"].return_value = [_row(status="cancel_failed", attempts=4)]

    await payment_consumer.reconcile_once(max_attempts=5)

    mocks["set_status"].assert_awaited_once_with(
        "pay-1", "cancel_failed_permanent", increment_attempts=True
    )
