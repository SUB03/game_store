import json
import logging

from aiokafka import AIOKafkaProducer

from payment_service.payment_utils import get_owned_games
from payment_service.payments_store import (
    bump_attempts,
    fetch_stuck,
    mark_granted_pending_capture,
)

logger = logging.getLogger("payment_service")


async def sweep_once(
    producer: AIOKafkaProducer,
    grant_requests_topic: str,
    grace_seconds: float,
    max_attempts: int,
) -> None:
    for row in await fetch_stuck(grace_seconds, max_attempts):
        if row.status == "grant_requested":
            await _redrive_grant_requested(row, producer, grant_requests_topic)
        else:
            # `pending` - the webhook itself never arrived. Nothing to
            # automatically retry (we can't fake a YooKassa callback); just
            # make it visible instead of leaving it silently stuck forever.
            logger.warning(
                "payment %s stuck in pending for over %ds (attempt %d)",
                row.payment_id, grace_seconds, row.attempts + 1,
            )
            await bump_attempts(row.payment_id)


async def _redrive_grant_requested(
    row, producer: AIOKafkaProducer, grant_requests_topic: str
) -> None:
    appids = list(row.appids)
    owned = set(await get_owned_games(username=row.username))
    if all(appid in owned for appid in appids):
        # The grant already succeeded; only grant_game_consumer's result
        # message was lost. Skip straight to the capture retry
        # payment_consumer's reconciliation already does.
        logger.info(
            "payment %s already fully granted, skipping to capture retry",
            row.payment_id,
        )
        await mark_granted_pending_capture(row.payment_id)
        return

    logger.warning(
        "payment %s stuck in grant_requested, re-publishing (attempt %d)",
        row.payment_id, row.attempts + 1,
    )
    message = {
        "payment_id": row.payment_id,
        "username": row.username,
        "appids": appids,
    }
    await producer.send_and_wait(grant_requests_topic, json.dumps(message).encode("utf-8"))
    await bump_attempts(row.payment_id)
