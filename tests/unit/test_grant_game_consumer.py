"""Unit tests for grant_game_consumer's per-message handling (gRPC/Kafka mocked)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import grpc
import pytest

from grant_game_consumer.main import handle_message

RESULTS_TOPIC = "payment.grant-results"


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


async def test_valid_message_grants_games_and_publishes_granted_true(stub, producer):
    stub.AddGamesIfNoneOwned.return_value = SimpleNamespace(already_owned=[])

    await handle_message(_message(appids=[1, 2]), stub, producer, RESULTS_TOPIC)

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

    await handle_message(_message(appids=[1, 2]), stub, producer, RESULTS_TOPIC)

    _, body = producer.send_and_wait.await_args.args
    assert json.loads(body)["granted"] is False


async def test_malformed_json_is_dropped_without_raising(stub, producer):
    await handle_message(b"not json", stub, producer, RESULTS_TOPIC)

    stub.AddGamesIfNoneOwned.assert_not_awaited()
    producer.send_and_wait.assert_not_awaited()


async def test_schema_violation_is_dropped_without_raising(stub, producer):
    # missing required "appids"
    bad = json.dumps({"payment_id": "pay-1", "username": "alice"}).encode()

    await handle_message(bad, stub, producer, RESULTS_TOPIC)

    stub.AddGamesIfNoneOwned.assert_not_awaited()
    producer.send_and_wait.assert_not_awaited()


async def test_grpc_failure_is_dropped_without_raising(stub, producer):
    error = grpc.aio.AioRpcError(
        grpc.StatusCode.UNAVAILABLE,
        initial_metadata=None,
        trailing_metadata=None,
        details="users_service down",
    )
    stub.AddGamesIfNoneOwned.side_effect = error

    await handle_message(_message(), stub, producer, RESULTS_TOPIC)

    producer.send_and_wait.assert_not_awaited()
