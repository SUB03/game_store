"""Unit tests for grant_game_consumer's per-message handling (gRPC/Kafka mocked)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import grpc
import pytest

import grant_game_consumer.main as grant_game_consumer
from grant_game_consumer.main import handle_message

RESULTS_TOPIC = "payment.grant-results"
DLQ_TOPIC = "payment.dead-letters"


def _message(payment_id="pay-1", username="alice", appids=None):
    return json.dumps(
        {
            "payment_id": payment_id,
            "username": username,
            "appids": appids if appids is not None else [1, 2, 3],
        }
    ).encode()


@pytest.fixture
def stub():
    return AsyncMock()


@pytest.fixture
def producer():
    return AsyncMock()


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    # the transient-gRPC-retry backoff would otherwise really sleep in tests
    monkeypatch.setattr(grant_game_consumer.asyncio, "sleep", AsyncMock())


async def _handle(raw, stub, producer, results_topic=RESULTS_TOPIC, dlq_topic=DLQ_TOPIC):
    return await handle_message(raw, stub, producer, results_topic, dlq_topic)


async def test_valid_message_grants_games_and_publishes_granted_true(stub, producer):
    stub.AddGamesIfNoneOwned.return_value = SimpleNamespace(already_owned=[])

    await _handle(_message(appids=[1, 2]), stub, producer)

    stub.AddGamesIfNoneOwned.assert_awaited_once()
    request = stub.AddGamesIfNoneOwned.await_args.args[0]
    assert request.username == "alice"
    assert list(request.appids) == [1, 2]

    producer.send_and_wait.assert_awaited_once()
    topic, body = producer.send_and_wait.await_args.args
    assert topic == RESULTS_TOPIC
    assert json.loads(body) == {
        "payment_id": "pay-1",
        "username": "alice",
        "appids": [1, 2],
        "granted": True,
    }


async def test_already_owned_games_publish_granted_false(stub, producer):
    stub.AddGamesIfNoneOwned.return_value = SimpleNamespace(already_owned=[1])

    await _handle(_message(appids=[1, 2]), stub, producer)

    _, body = producer.send_and_wait.await_args.args
    assert json.loads(body)["granted"] is False


async def test_malformed_json_is_sent_to_dlq(stub, producer):
    await _handle(b"not json", stub, producer)

    stub.AddGamesIfNoneOwned.assert_not_awaited()
    topic, body = producer.send_and_wait.await_args.args
    assert topic == DLQ_TOPIC
    assert json.loads(body)["reason"].startswith("json:")


async def test_schema_violation_is_sent_to_dlq(stub, producer):
    # missing required "appids"
    bad = json.dumps({"payment_id": "pay-1", "username": "alice"}).encode()

    await _handle(bad, stub, producer)

    stub.AddGamesIfNoneOwned.assert_not_awaited()
    topic, body = producer.send_and_wait.await_args.args
    assert topic == DLQ_TOPIC
    assert json.loads(body)["reason"].startswith("schema:")


async def test_transient_grpc_failure_is_retried_then_succeeds(stub, producer):
    error = grpc.aio.AioRpcError(
        grpc.StatusCode.UNAVAILABLE,
        initial_metadata=None,
        trailing_metadata=None,
        details="users_service down",
    )
    stub.AddGamesIfNoneOwned.side_effect = [
        error,
        SimpleNamespace(already_owned=[]),
    ]

    await _handle(_message(), stub, producer)

    assert stub.AddGamesIfNoneOwned.await_count == 2
    topic, _ = producer.send_and_wait.await_args.args
    assert topic == RESULTS_TOPIC


async def test_transient_grpc_failure_gives_up_after_max_retries(stub, producer):
    error = grpc.aio.AioRpcError(
        grpc.StatusCode.UNAVAILABLE,
        initial_metadata=None,
        trailing_metadata=None,
        details="users_service down",
    )
    stub.AddGamesIfNoneOwned.side_effect = error

    await _handle(_message(), stub, producer)

    assert stub.AddGamesIfNoneOwned.await_count == grant_game_consumer.MAX_GRPC_RETRIES
    producer.send_and_wait.assert_not_awaited()


async def test_permanent_grpc_failure_is_not_retried(stub, producer):
    error = grpc.aio.AioRpcError(
        grpc.StatusCode.INVALID_ARGUMENT,
        initial_metadata=None,
        trailing_metadata=None,
        details="bad request",
    )
    stub.AddGamesIfNoneOwned.side_effect = error

    await _handle(_message(), stub, producer)

    stub.AddGamesIfNoneOwned.assert_awaited_once()
    producer.send_and_wait.assert_not_awaited()
