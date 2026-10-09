import uuid

import grpc
from fastapi import HTTPException

from payment_service.main_settings import Settings as PaymentSettings
import users_proto.users_service_pb2_grpc as us_pb2_grpc
import users_proto.users_service_pb2 as us_pb2

from async_yookassa import YooKassaClient
from async_yookassa.models.payment import PaymentRequest, Amount, RedirectConfirmationRequest

_payment_settings: PaymentSettings | None = None
_channel: grpc.aio.Channel | None = None


def get_payment_settings() -> PaymentSettings:
    global _payment_settings
    if _payment_settings is None:
        _payment_settings = PaymentSettings()
    return _payment_settings


def _get_stub() -> us_pb2_grpc.UserServiceStub:
    global _channel
    if _channel is None:
        _channel = grpc.aio.insecure_channel(get_payment_settings().users_service_addr)
    return us_pb2_grpc.UserServiceStub(_channel)


async def _yookassa_payment(
    username: str, appids: list[int], price: str, idempotency_key: uuid.UUID
):
    settings = get_payment_settings()
    description = f"Purchase of {len(appids)} games by {username}"
    return_url = f"{settings.frontend_url}/profile"

    # The webhook reads these to grant ownership of every paid game.
    metadata = {
        "username": username,
        "appids": ",".join(str(appid) for appid in appids),
    }

    # Two-step flow: the money moves only when the capture consumer confirms
    # the grant succeeded. YooKassa notifies `payment.waiting_for_capture`,
    # which the notifications endpoint publishes to Kafka.
    async with YooKassaClient(
        account_id=settings.shopid,
        secret_key=settings.ukass_api_key
    ) as client:
        yookassa_request = PaymentRequest(
            amount=Amount(value=price, currency="RUB"),
            description=description,
            capture=False,
            metadata=metadata,
            confirmation=RedirectConfirmationRequest(
                type="redirect",
                return_url=return_url
            )
        )

        payment = await client.payment.create(
            yookassa_request, idempotency_key=idempotency_key
        )

    return payment


async def make_payment_cart(
    username: str, appids: list[int], price: str, idempotency_key: uuid.UUID
):
    payment = await _yookassa_payment(username, appids, price, idempotency_key)
    return {"payment_id": payment.id, "confirmation_url": payment.confirmation.confirmation_url}


async def has_game(username: str, appid: int):
    stub = _get_stub()
    request = us_pb2.HasGameRequest(username=username, appid=appid)
    try:
        response = await stub.HasGame(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Users service error: {e.code()} - {e.details()}",
        )
    return response.result


async def add_game(username: str, appid: int):
    stub = _get_stub()
    request = us_pb2.AddGameToUserRequest(username=username, appid=appid)
    try:
        response = await stub.AddGameToUser(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Users service error: {e.code()} - {e.details()}",
        )
    return {"message": "added the game", "appid": response.appid}


async def get_owned_games(username: str) -> list[int]:
    stub = _get_stub()
    request = us_pb2.GetOwnedGamesRequest(username=username)
    try:
        response = await stub.GetOwnedGames(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Users service error: {e.code()} - {e.details()}",
        )
    return list(response.appids)


async def add_game_to_cart(username: str, appid: int) -> dict:
    stub = _get_stub()
    request = us_pb2.AddGameToCartRequest(username=username, appid=appid)
    try:
        response = await stub.AddGameToCart(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Users service error: {e.code()} - {e.details()}",
        )
    return {"appid": response.appid, "added": response.added}


async def remove_game_from_cart(username: str, appid: int) -> dict:
    stub = _get_stub()
    request = us_pb2.RemoveGameFromCartRequest(username=username, appid=appid)
    try:
        response = await stub.RemoveGameFromCart(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Users service error: {e.code()} - {e.details()}",
        )
    return {"appid": response.appid, "removed": response.removed}


async def get_user_cart(username: str) -> list[int]:
    stub = _get_stub()
    request = us_pb2.GetCartRequest(username=username)
    try:
        response = await stub.GetCart(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Users service error: {e.code()} - {e.details()}",
        )
    return list(response.appids)


async def clear_user_cart(username: str) -> int:
    stub = _get_stub()
    request = us_pb2.ClearCartRequest(username=username)
    try:
        response = await stub.ClearCart(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Users service error: {e.code()} - {e.details()}",
        )
    return response.removed


async def get_price(appid: int):
    # Local import to avoid a hard engine dependency at module import time
    # (unit tests patch payment_utils.get_price before any DB is touched).
    from payment_service.engine import engine
    from payment_service.models import games_table

    async with engine.begin() as conn:
        result = await conn.execute(games_table.select().where(games_table.c.appid == appid))
        result = result.fetchone()
    return result
