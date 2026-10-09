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


class GameMessage(BaseModel):
    payment_id: str = Field(min_length=1)
    username: str = Field(min_length=1)
    appids: list[int] = Field(min_length=1)
    model_config = {"extra": "forbid"}


async def handle_message(
    raw: bytes,
    stub: us_pb2_grpc.UserServiceStub,
    producer: AIOKafkaProducer,
    results_topic: str,
) -> None:
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as e:
        logger.error("payload is not valid JSON, dropping: %s", e)
        return

    try:
        payload = GameMessage.model_validate(data)
    except ValidationError as e:
        logger.error("payload failed schema validation, dropping: %s", e.errors())
        return

    request = us_pb2.AddGamesIfNoneOwnedRequest(
        username=payload.username,
        appids=payload.appids,
    )
    try:
        response = await stub.AddGamesIfNoneOwned(request)
    except grpc.aio.AioRpcError as e:
        logger.error(
            "users_service call failed, dropping: %s %s", e.code(), e.details()
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


async def consume():
    settings = Settings()

    consumer = AIOKafkaConsumer(
        settings.grant_requests_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        auto_offset_reset="latest",
    )
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
    channel = grpc.aio.insecure_channel(settings.users_service_addr)
    stub = us_pb2_grpc.UserServiceStub(channel)

    await producer.start()
    await consumer.start()
    try:
        async for msg in consumer:
            await handle_message(msg.value, stub, producer, settings.grant_results_topic)
    finally:
        await channel.close()
        await consumer.stop()
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(consume())
