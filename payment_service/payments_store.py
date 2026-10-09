from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from payment_service.engine import engine
from payment_service.models import payments_table

STUCK_STATUSES = ("pending", "grant_requested")


async def create_payment(
    payment_id: str, username: str, appids: list[int], idempotency_key: str
) -> None:
    # A retried checkout with the same idempotency key gets the same
    # YooKassa payment_id back, so this insert must be a no-op the second
    # time instead of a duplicate-primary-key crash.
    async with engine.begin() as conn:
        await conn.execute(
            pg_insert(payments_table)
            .values(
                payment_id=payment_id,
                username=username,
                appids=appids,
                idempotency_key=idempotency_key,
            )
            .on_conflict_do_nothing()
        )


async def mark_grant_requested(payment_id: str):
    """Flip a payment from `pending` to `grant_requested`.

    Returns the payment's own trusted (username, appids) row on success, or
    None if the payment is unknown or already past `pending` - the caller
    uses None to skip re-publishing a grant request for a webhook YooKassa
    redelivered. The caller must build the grant request from this returned
    row, never from the webhook request body, since the body is attacker
    controlled and the row is not.
    """
    async with engine.begin() as conn:
        result = await conn.execute(
            payments_table.update()
            .where(
                payments_table.c.payment_id == payment_id,
                payments_table.c.status == "pending",
            )
            .values(status="grant_requested")
            .returning(payments_table.c.username, payments_table.c.appids)
        )
        return result.fetchone()


async def fetch_stuck(grace_seconds: float, max_attempts: int) -> list:
    """Payments that never progressed past `pending`/`grant_requested`.

    Kafka-level durability (consumer group + manual commit) stops *new*
    message loss, but something still needs to re-drive payments stuck from
    before that fix, or lost for any other reason.
    """
    async with engine.begin() as conn:
        result = await conn.execute(
            select(
                payments_table.c.payment_id,
                payments_table.c.username,
                payments_table.c.appids,
                payments_table.c.status,
                payments_table.c.attempts,
            ).where(
                payments_table.c.status.in_(STUCK_STATUSES),
                payments_table.c.updated_at < func.now() - timedelta(seconds=grace_seconds),
                payments_table.c.attempts < max_attempts,
            )
        )
        return result.fetchall()


async def bump_attempts(payment_id: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            payments_table.update()
            .where(payments_table.c.payment_id == payment_id)
            .values(attempts=payments_table.c.attempts + 1)
        )


async def mark_granted_pending_capture(payment_id: str) -> None:
    """The grant already succeeded (appids are owned); only the grant_game_consumer
    result message was lost. Skip straight to the capture retry payment_consumer
    already does, instead of re-running AddGamesIfNoneOwned."""
    async with engine.begin() as conn:
        await conn.execute(
            payments_table.update()
            .where(payments_table.c.payment_id == payment_id)
            .values(status="granted_pending_capture")
        )
