import asyncio
import json
import logging

import grpc
from aiokafka import AIOKafkaConsumer
from pydantic import BaseModel, ValidationError

import users_proto.users_service_pb2_grpc as us_pb2_grpc
import users_proto.users_service_pb2 as us_pb2

from payment_consumer.settings import Settings
from payment_consumer.payment_utils import capture_payment, cancel_payment
from payment_consumer.payments_store import fetch_reconcilable, set_status

logger = logging.getLogger("payment_consumer")
logging.basicConfig(level=logging.INFO)


class GrantResult(BaseModel):
    payment_id: str
    username: str
    appids: list[int]
    granted: bool
    model_config = {"extra": "forbid"}


async def _strip_cart_rows(stub: us_pb2_grpc.UserServiceStub, username: str, appids: list[int]) -> None:
    for appid in appids:
        try:
            await stub.RemoveGameFromCart(
                us_pb2.RemoveGameFromCartRequest(username=username, appid=appid)
            )
        except grpc.aio.AioRpcError as e:
            logger.error(
                "failed to strip appid %s from %s's cart: %s %s",
                appid, username, e.code(), e.details(),
            )


async def handle_message(raw: bytes, stub: us_pb2_grpc.UserServiceStub) -> None:
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as e:
        logger.error("payload is not valid JSON, dropping: %s", e)
        return

    try:
        payload = GrantResult.model_validate(data)
    except ValidationError as e:
        logger.error("payload failed schema validation, dropping: %s", e.errors())
        return

    if payload.granted:
        try:
            await capture_payment(payload.payment_id)
        except Exception as e:
            logger.error(
                "capture failed for %s, will retry via reconciliation: %s",
                payload.payment_id, e,
            )
            await set_status(payload.payment_id, "granted_pending_capture", increment_attempts=True)
            return
        await set_status(payload.payment_id, "captured")
        await _strip_cart_rows(stub, payload.username, payload.appids)
    else:
        try:
            await cancel_payment(payload.payment_id)
        except Exception as e:
            logger.error(
                "cancel failed for %s, will retry via reconciliation: %s",
                payload.payment_id, e,
            )
            await set_status(payload.payment_id, "cancel_failed", increment_attempts=True)
            return
        await set_status(payload.payment_id, "canceled")


async def reconcile_once(max_attempts: int) -> None:
    for row in await fetch_reconcilable(max_attempts):
        next_attempts = row.attempts + 1
        if row.status == "granted_pending_capture":
            try:
                await capture_payment(row.payment_id)
            except Exception as e:
                logger.error("reconcile: capture retry failed for %s: %s", row.payment_id, e)
                status = "capture_failed" if next_attempts >= max_attempts else "granted_pending_capture"
                await set_status(row.payment_id, status, increment_attempts=True)
                continue
            await set_status(row.payment_id, "captured")
        elif row.status == "cancel_failed":
            try:
                await cancel_payment(row.payment_id)
            except Exception as e:
                logger.error("reconcile: cancel retry failed for %s: %s", row.payment_id, e)
                status = "cancel_failed_permanent" if next_attempts >= max_attempts else "cancel_failed"
                await set_status(row.payment_id, status, increment_attempts=True)
                continue
            await set_status(row.payment_id, "canceled")


async def reconcile_loop(interval_seconds: float, max_attempts: int) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await reconcile_once(max_attempts)
        except Exception as e:
            logger.error("reconciliation sweep failed: %s", e)


async def _consume_loop(consumer: AIOKafkaConsumer, stub: us_pb2_grpc.UserServiceStub) -> None:
    async for msg in consumer:
        await handle_message(msg.value, stub)


async def consume():
    settings = Settings()

    consumer = AIOKafkaConsumer(
        settings.grant_results_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        auto_offset_reset="latest",
    )
    channel = grpc.aio.insecure_channel(settings.users_service_addr)
    stub = us_pb2_grpc.UserServiceStub(channel)

    await consumer.start()
    try:
        await asyncio.gather(
            _consume_loop(consumer, stub),
            reconcile_loop(settings.reconcile_interval_seconds, settings.max_reconcile_attempts),
        )
    finally:
        await channel.close()
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(consume())
