from sqlalchemy import select

from payment_consumer.engine import engine
from payment_consumer.models import payments_table

RECONCILABLE_STATUSES = ("granted_pending_capture", "cancel_failed")


async def set_status(payment_id: str, status: str, increment_attempts: bool = False) -> None:
    async with engine.begin() as conn:
        stmt = payments_table.update().where(payments_table.c.payment_id == payment_id)
        if increment_attempts:
            stmt = stmt.values(status=status, attempts=payments_table.c.attempts + 1)
        else:
            stmt = stmt.values(status=status)
        await conn.execute(stmt)


async def fetch_reconcilable(max_attempts: int) -> list:
    """Payments stuck on a failed capture/cancel, still under the retry cap."""
    async with engine.begin() as conn:
        result = await conn.execute(
            select(
                payments_table.c.payment_id,
                payments_table.c.status,
                payments_table.c.attempts,
            ).where(
                payments_table.c.status.in_(RECONCILABLE_STATUSES),
                payments_table.c.attempts < max_attempts,
            )
        )
        return result.fetchall()
