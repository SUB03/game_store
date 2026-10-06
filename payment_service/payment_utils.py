import uuid

import grpc
from fastapi import HTTPException

from payment_service.main_settings import Settings as PaymentSettings
import users_proto.users_service_pb2_grpc as us_pb2_grpc
import users_proto.users_service_pb2 as us_pb2

from async_yookassa import YooKassaClient
from async_yookassa.models.payment import PaymentRequest, Amount, RedirectConfirmationRequest

_payment_settings: PaymentSettings | None = None


def get_payment_settings() -> PaymentSettings:
    global _payment_settings
    if _payment_settings is None:
        _payment_settings = PaymentSettings()
    return _payment_settings


async def _yookassa_payment(
    username: str, appids: list[int], price: str, checkout_key: str = ""
):
    """Create one YooKassa payment covering every appid (moved from the old gRPC servicer)."""
    settings = get_payment_settings()
    if len(appids) > 1:
        description = f"Purchase of {len(appids)} games by {username}"
        return_url = f"{settings.frontend_url}/profile"
    else:
        description = f"Purchase of app {appids[0]} by {username}"
        return_url = f"{settings.frontend_url}/app/{appids[0]}"

    # The webhook reads these to grant ownership of every paid game.
    metadata = {
        "username": username,
        "appid": str(appids[0]),
        "appids": ",".join(str(appid) for appid in appids),
    }

    idempotency_key = None
    if checkout_key:
        try:
            idempotency_key = uuid.UUID(checkout_key)
        except ValueError:
            # Never fail a payment over a malformed key; the library
            # generates a fresh random one when None is passed.
            idempotency_key = None

    async with YooKassaClient(
        account_id=settings.shopid,
        secret_key=settings.ukass_api_key
    ) as client:
        yookassa_request = PaymentRequest(
            amount=Amount(value=price, currency="RUB"),
            description=description,
            capture=True,
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


async def make_payment(username: str, appid: int, price: str):
    payment = await _yookassa_payment(username, [appid], price)
    return {"payment_id": payment.id, "confirmation_url": payment.confirmation.confirmation_url}


async def make_payment_cart(
    username: str, appids: list[int], price: str, checkout_key: str = ""
):
    payment = await _yookassa_payment(username, appids, price, checkout_key)
    return {"payment_id": payment.id, "confirmation_url": payment.confirmation.confirmation_url}


async def has_game(username: str, appid: int):
    channel = grpc.aio.insecure_channel("users_service:8003")
    stub = us_pb2_grpc.UserServiceStub(channel)

    request = us_pb2.HasGameRequest(
        username=username,
        appid=appid
    )

    try:
        response = await stub.HasGame(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Users service error: {e.code()} - {e.details()}",
        )
    finally:
        await channel.close()

    return response.result


async def add_game(username: str, appid: int):
    channel = grpc.aio.insecure_channel("users_service:8003")
    stub = us_pb2_grpc.UserServiceStub(channel)

    request = us_pb2.AddGameToUserRequest(
        username=username,
        appid=appid
    )

    try:
        response = await stub.AddGameToUser(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Users service error: {e.code()} - {e.details()}",
        )
    finally:
        await channel.close()

    return {"message": "added the game", "appid": response.appid}


async def get_owned_games(username: str) -> list[int]:
    channel = grpc.aio.insecure_channel("users_service:8003")
    stub = us_pb2_grpc.UserServiceStub(channel)

    request = us_pb2.GetOwnedGamesRequest(username=username)

    try:
        response = await stub.GetOwnedGames(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Users service error: {e.code()} - {e.details()}",
        )
    finally:
        await channel.close()

    return list(response.appids)


async def add_game_to_cart(username: str, appid: int) -> dict:
    channel = grpc.aio.insecure_channel("users_service:8003")
    stub = us_pb2_grpc.UserServiceStub(channel)

    request = us_pb2.AddGameToCartRequest(username=username, appid=appid)

    try:
        response = await stub.AddGameToCart(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Users service error: {e.code()} - {e.details()}",
        )
    finally:
        await channel.close()

    return {"appid": response.appid, "added": response.added}


async def remove_game_from_cart(username: str, appid: int) -> dict:
    channel = grpc.aio.insecure_channel("users_service:8003")
    stub = us_pb2_grpc.UserServiceStub(channel)

    request = us_pb2.RemoveGameFromCartRequest(username=username, appid=appid)

    try:
        response = await stub.RemoveGameFromCart(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Users service error: {e.code()} - {e.details()}",
        )
    finally:
        await channel.close()

    return {"appid": response.appid, "removed": response.removed}


async def get_user_cart(username: str) -> tuple[list[int], str]:
    channel = grpc.aio.insecure_channel("users_service:8003")
    stub = us_pb2_grpc.UserServiceStub(channel)

    request = us_pb2.GetCartRequest(username=username)

    try:
        response = await stub.GetCart(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Users service error: {e.code()} - {e.details()}",
        )
    finally:
        await channel.close()

    return list(response.appids), response.checkout_key


async def clear_user_cart(username: str) -> int:
    channel = grpc.aio.insecure_channel("users_service:8003")
    stub = us_pb2_grpc.UserServiceStub(channel)

    request = us_pb2.ClearCartRequest(username=username)

    try:
        response = await stub.ClearCart(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Users service error: {e.code()} - {e.details()}",
        )
    finally:
        await channel.close()

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
