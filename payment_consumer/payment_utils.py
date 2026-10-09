from async_yookassa import YooKassaClient

from payment_consumer.settings import Settings

_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


async def capture_payment(payment_id: str):
    """Confirm a `waiting_for_capture` payment (money moves to the seller)."""
    settings = get_settings()
    async with YooKassaClient(
        account_id=settings.shopid, secret_key=settings.ukass_api_key
    ) as client:
        return await client.payment.capture(payment_id)


async def cancel_payment(payment_id: str):
    """Release a `waiting_for_capture` payment (money never moves)."""
    settings = get_settings()
    async with YooKassaClient(
        account_id=settings.shopid, secret_key=settings.ukass_api_key
    ) as client:
        return await client.payment.cancel(payment_id)
