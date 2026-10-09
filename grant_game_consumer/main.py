import asyncio
import json
import logging

import grpc
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from pydantic import BaseModel, Field, ValidationError

import users_proto.users_service_pb2_grpc as us_pb2_grpc
import users_proto.users_service_pb2 as us_pb2

from grant_game_consumer.settings import Settings

logger = logging.getLogger("grant_game_consumer")
logging.basicConfig(level=logging.INFO)

TRANSIENT_GRPC_CODES = (
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
    grpc.StatusCode.RESOURCE_EXHAUSTED,
    grpc.StatusCode.ABORTED,
)
MAX_GRPC_RETRIES = 3
GRPC_RETRY_BACKOFF_SECONDS = 0.5


class GameMessage(BaseModel):
    payment_id: str = Field(min_length=1)
    username: str = Field(min_length=1)
    appids: list[int] = Field(min_length=1)
    model_config = {"extra": "forbid"}


async def _send_to_dlq(
    producer: AIOKafkaProducer, dead_letter_topic: str, raw: bytes, reason: str
) -> None:
    dead_letter = {"reason": reason, "raw": raw.decode("utf-8", errors="replace")}
    await producer.send_and_wait(dead_letter_topic, json.dumps(dead_letter).encode("utf-8"))


async def _call_add_games_if_none_owned(
    stub: us_pb2_grpc.UserServiceStub, request
):
    """Retry transient gRPC failures a few times before giving up; a
    payment stuck at `grant_requested` after that is picked up later by
    payment_service's stuck-payment reconciliation sweep."""
    for attempt in range(1, MAX_GRPC_RETRIES + 1):
        try:
            return await stub.AddGamesIfNoneOwned(request)
        except grpc.aio.AioRpcError as e:
            if e.code() not in TRANSIENT_GRPC_CODES or attempt == MAX_GRPC_RETRIES:
                raise
            logger.warning(
                "transient users_service failure (attempt %d/%d), retrying: %s %s",
                attempt, MAX_GRPC_RETRIES, e.code(), e.details(),
            )
            await asyncio.sleep(GRPC_RETRY_BACKOFF_SECONDS * attempt)


async def handle_message(
    raw: bytes,
    stub: us_pb2_grpc.UserServiceStub,
    producer: AIOKafkaProducer,
    results_topic: str,
    dead_letter_topic: str,
) -> None:
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as e:
        logger.error("payload is not valid JSON, sending to DLQ: %s", e)
        await _send_to_dlq(producer, dead_letter_topic, raw, f"json: {e}")
        return

    try:
        payload = GameMessage.model_validate(data)
    except ValidationError as e:
        logger.error("payload failed schema validation, sending to DLQ: %s", e.errors())
        await _send_to_dlq(producer, dead_letter_topic, raw, f"schema: {e.errors()}")
        return

    request = us_pb2.AddGamesIfNoneOwnedRequest(
        username=payload.username,
        appids=payload.appids,
    )
    try:
        response = await _call_add_games_if_none_owned(stub, request)
    except grpc.aio.AioRpcError as e:
        logger.error(
            "users_service call failed after retries, dropping (will be "
            "re-driven by payment_service's reconciliation sweep): %s %s",
            e.code(), e.details(),
        )
        return

    granted = not response.already_owned
    result = {
        "payment_id": payload.payment_id,
        "username": payload.username,
        "appids": payload.appids,
        "granted": granted,
    }
    await producer.send_and_wait(results_topic, json.dumps(result).encode("utf-8"))


async def _consume_loop(
    consumer: AIOKafkaConsumer,
    stub: us_pb2_grpc.UserServiceStub,
    producer: AIOKafkaProducer,
    results_topic: str,
    dead_letter_topic: str,
) -> None:
    async for msg in consumer:
        await handle_message(msg.value, stub, producer, results_topic, dead_letter_topic)
        await consumer.commit()


async def consume():
    settings = Settings()

    consumer = AIOKafkaConsumer(
        settings.grant_requests_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="grant_game_consumer",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
    channel = grpc.aio.insecure_channel(settings.users_service_addr)
    stub = us_pb2_grpc.UserServiceStub(channel)

    await producer.start()
    await consumer.start()
    try:
        await _consume_loop(
            consumer, stub, producer, settings.grant_results_topic, settings.dead_letter_topic
        )
    finally:
        await channel.close()
        await consumer.stop()
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(consume())
