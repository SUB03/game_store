import grpc
from fastapi import HTTPException

from store_service.engine import engine
from store_service.models import games_table
import users_proto.users_service_pb2_grpc as us_pb2_grpc
import users_proto.users_service_pb2 as us_pb2

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

async def get_price(appid: int):
    async with engine.begin() as conn:
        result = await conn.execute(games_table.select().where(games_table.c.appid==appid))
        result = result.fetchone()
    return result