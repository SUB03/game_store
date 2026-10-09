import grpc, asyncio
from grpc.aio import ServicerContext
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models import games_ownership, users_cart

import users_proto.users_service_pb2_grpc as users_service_pb2_grpc
from users_proto.users_service_pb2 import (
    AddGameToCartRequest,
    AddGameToCartResponse,
    AddGameToUserRequest,
    AddGameToUserResponse,
    AddGamesIfNoneOwnedRequest,
    AddGamesIfNoneOwnedResponse,
    ClearCartRequest,
    ClearCartResponse,
    GetCartRequest,
    GetCartResponse,
    GetOwnedGamesRequest,
    GetOwnedGamesResponse,
    HasGameRequest,
    HasGameResponse,
    RemoveGameFromCartRequest,
    RemoveGameFromCartResponse,
)

class Settings(BaseSettings):
    db_url: str = Field(alias="SQLALCHEMY_URL")
    model_config = SettingsConfigDict(extra="ignore", env_file=".env")

class UsersServiceServicer(users_service_pb2_grpc.UserServiceServicer):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine = create_async_engine(settings.db_url)

    async def AddGameToUser(
        self,
        request: AddGameToUserRequest,
        context: ServicerContext
    ) -> AddGameToUserResponse:
        async with self.engine.begin() as conn:
            await conn.execute(
                pg_insert(games_ownership)
                .values(username=request.username, appid=request.appid)
                .on_conflict_do_nothing()
            )
        return AddGameToUserResponse(appid=request.appid)

    async def AddGamesIfNoneOwned(
        self,
        request: AddGamesIfNoneOwnedRequest,
        context: ServicerContext
    ) -> AddGamesIfNoneOwnedResponse:
        appids = sorted(set(request.appids))
        async with self.engine.begin() as conn:
            result = await conn.execute(
                select(games_ownership.c.appid).where(
                    games_ownership.c.username == request.username,
                    games_ownership.c.appid.in_(appids),
                )
            )
            owned = sorted(row.appid for row in result.fetchall())
            if not owned:
                await conn.execute(
                    pg_insert(games_ownership),
                    [
                        {"username": request.username, "appid": appid}
                        for appid in appids
                    ],
                )
        return AddGamesIfNoneOwnedResponse(already_owned=owned)

    async def HasGame(
        self,
        request: HasGameRequest,
        context: ServicerContext
    ) -> HasGameResponse:
        async with self.engine.begin() as conn:
            result = await conn.execute(games_ownership.select().where(
                games_ownership.c.username == request.username,
                games_ownership.c.appid == request.appid
            ))

            result = result.fetchone()
            print(result)

            return HasGameResponse(
                result = True if result else False
            )

    async def GetOwnedGames(
        self,
        request: GetOwnedGamesRequest,
        context: ServicerContext
    ) -> GetOwnedGamesResponse:
        async with self.engine.begin() as conn:
            result = await conn.execute(
                games_ownership.select().where(
                    games_ownership.c.username == request.username
                )
            )
            rows = result.fetchall()

        return GetOwnedGamesResponse(appids=[row.appid for row in rows])

    async def AddGameToCart(
        self,
        request: AddGameToCartRequest,
        context: ServicerContext
    ) -> AddGameToCartResponse:
        async with self.engine.begin() as conn:
            # (username, appid) is the primary key and adding is idempotent:
            # ON CONFLICT DO NOTHING turns a repeat add into a harmless no-op.
            # Generic Table.insert() has no on_conflict_* methods - they live
            # on the postgresql dialect's insert().
            #
            # RETURNING is what tells the two cases apart: psycopg reports
            # rowcount == -1 for INSERT ... ON CONFLICT DO NOTHING (whether a
            # row was written is unknown to the driver), so a returned row is
            # the only reliable "we really inserted it" signal.
            result = await conn.execute(
                pg_insert(users_cart)
                .values(
                    username=request.username,
                    appid=request.appid,
                )
                .on_conflict_do_nothing()
                .returning(users_cart.c.appid)
            )
            added = result.fetchone() is not None

        return AddGameToCartResponse(appid=request.appid, added=added)

    async def RemoveGameFromCart(
        self,
        request: RemoveGameFromCartRequest,
        context: ServicerContext
    ) -> RemoveGameFromCartResponse:
        async with self.engine.begin() as conn:
            result = await conn.execute(
                users_cart.delete().where(
                    users_cart.c.username == request.username,
                    users_cart.c.appid == request.appid,
                )
            )
            removed = bool(result.rowcount)

        return RemoveGameFromCartResponse(appid=request.appid, removed=removed)

    async def GetCart(
        self,
        request: GetCartRequest,
        context: ServicerContext
    ) -> GetCartResponse:
        async with self.engine.begin() as conn:
            result = await conn.execute(
                users_cart.select().where(users_cart.c.username == request.username)
            )
            rows = result.fetchall()

        appids = [row.appid for row in rows]
        return GetCartResponse(appids=appids)

    async def ClearCart(
        self,
        request: ClearCartRequest,
        context: ServicerContext
    ) -> ClearCartResponse:
        async with self.engine.begin() as conn:
            result = await conn.execute(
                users_cart.delete().where(users_cart.c.username == request.username)
            )
            removed = max(result.rowcount, 0)

        return ClearCartResponse(removed=removed)


async def serve():
    settings = Settings()
    server = grpc.aio.server()
    users_service_pb2_grpc.add_UserServiceServicer_to_server(UsersServiceServicer(settings), server)
    server.add_insecure_port('[::]:8003')

    await server.start()
    await server.wait_for_termination()

if __name__ == "__main__":
    asyncio.run(serve())