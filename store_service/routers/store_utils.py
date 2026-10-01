import grpc
from fastapi import HTTPException

from store_service.engine import engine
from store_service.models import games_table
import payment_proto.payment_service_pb2_grpc as ps_pb2_grpc
import payment_proto.payment_service_pb2 as ps_pb2
import users_proto.users_service_pb2_grpc as us_pb2_grpc
import users_proto.users_service_pb2 as us_pb2

async def make_payment(username: str, appid: int, price: str) -> ps_pb2.MakePaymentResponse:
    channel = grpc.aio.insecure_channel("payment_service:8002")
    stub = ps_pb2_grpc.PaymentServiceStub(channel)

    request = ps_pb2.MakePaymentRequest(
        username=username,
        appid=appid,
        price=price
    )

    try:
        response: ps_pb2.MakePaymentResponse = await stub.MakePayment(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Payment service error: {e.code()} - {e.details()}",
        )
    finally:
        await channel.close()

    return response

async def has_game(username: str, appid: int) -> us_pb2.HasGameResponse:
    channel = grpc.aio.insecure_channel("users_service:8003")
    stub = us_pb2_grpc.UserServiceStub(channel)

    request = us_pb2.HasGameRequest(
        username=username,
        appid=appid
    )

    try:
        response: us_pb2.HasGameResponse = await stub.HasGame(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Users service error: {e.code()} - {e.details()}",
        )
    finally:
        await channel.close()

    return response.result

async def add_game(username: str, appid: int) -> us_pb2.AddGameToUserResponse:
    channel = grpc.aio.insecure_channel("users_service:8003")
    stub = us_pb2_grpc.UserServiceStub(channel)

    request = us_pb2.AddGameToUserRequest(
        username=username,
        appid=appid
    )

    try:
        response: us_pb2.AddGameToUserResponse = await stub.AddGameToUser(request)
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
        response: us_pb2.GetOwnedGamesResponse = await stub.GetOwnedGames(request)
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
        response: us_pb2.AddGameToCartResponse = await stub.AddGameToCart(request)
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
        response: us_pb2.RemoveGameFromCartResponse = await stub.RemoveGameFromCart(request)
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
        response: us_pb2.GetCartResponse = await stub.GetCart(request)
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
        response: us_pb2.ClearCartResponse = await stub.ClearCart(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Users service error: {e.code()} - {e.details()}",
        )
    finally:
        await channel.close()

    return response.removed

async def make_payment_cart(
    username: str, appids: list[int], price: str, checkout_key: str = ""
) -> ps_pb2.MakePaymentResponse:
    channel = grpc.aio.insecure_channel("payment_service:8002")
    stub = ps_pb2_grpc.PaymentServiceStub(channel)

    request = ps_pb2.MakePaymentRequest(
        username=username,
        appid=appids[0] if appids else 0,
        price=price,
        appids=appids,
        idempotency_key=checkout_key,
    )

    try:
        response: ps_pb2.MakePaymentResponse = await stub.MakePayment(request)
    except grpc.aio.AioRpcError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Payment service error: {e.code()} - {e.details()}",
        )
    finally:
        await channel.close()

    return response

async def get_price(appid: int):
    async with engine.begin() as conn:
        result = await conn.execute(games_table.select().where(games_table.c.appid==appid))
        result = result.fetchone()
    return result