from payment_service.engine import engine
from payment_service.models import payments_table


async def create_payment(
    payment_id: str, username: str, appids: list[int], idempotency_key: str
) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            payments_table.insert().values(
                payment_id=payment_id,
                username=username,
                appids=appids,
                idempotency_key=idempotency_key,
            )
        )


async def mark_grant_requested(payment_id: str) -> bool:
    """Flip a payment from `pending` to `grant_requested`.

    Returns False (and changes nothing) if the payment is unknown or already
    past `pending` - the caller uses that to skip re-publishing a grant
    request for a webhook YooKassa redelivered.
    """
    async with engine.begin() as conn:
        result = await conn.execute(
            payments_table.update()
            .where(
                payments_table.c.payment_id == payment_id,
                payments_table.c.status == "pending",
            )
            .values(status="grant_requested")
        )
    return result.rowcount > 0
