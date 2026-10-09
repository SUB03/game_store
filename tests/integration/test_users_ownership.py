"""Integration tests for the users_service gRPC servicer against real PostgreSQL."""

import pytest
from sqlalchemy.exc import IntegrityError
from users_proto.users_service_pb2 import AddGameToUserRequest, HasGameRequest

from users_service.main import Settings, UsersServiceServicer


@pytest.fixture
def servicer(db):
    return UsersServiceServicer(Settings())


@pytest.fixture
def context():
    return None  # the servicer never uses the ServicerContext


async def test_has_game_is_false_for_missing_ownership(
    servicer, context, seed_user, seed_game
):
    username = await seed_user(username="alice")
    appid = await seed_game(name="Not owned")
    response = await servicer.HasGame(
        HasGameRequest(username=username, appid=appid), context
    )
    assert response.result is False


async def test_add_game_then_has_game(servicer, context, seed_user, seed_game):
    username = await seed_user(username="alice")
    appid = await seed_game(name="Owned Game")

    added = await servicer.AddGameToUser(
        AddGameToUserRequest(username=username, appid=appid), context
    )
    assert added.appid == appid

    response = await servicer.HasGame(
        HasGameRequest(username=username, appid=appid), context
    )
    assert response.result is True


async def test_has_game_is_false_for_other_game(servicer, context, seed_user, seed_game):
    username = await seed_user(username="alice")
    owned = await seed_game(name="Owned")
    await seed_game(name="Not owned")

    await servicer.AddGameToUser(
        AddGameToUserRequest(username=username, appid=owned), context
    )

    games = await _all_appids()
    others = [appid for appid in games if appid != owned]
    response = await servicer.HasGame(
        HasGameRequest(username=username, appid=others[0]), context
    )
    assert response.result is False


async def test_duplicate_ownership_is_idempotent(servicer, context, seed_user, seed_game):
    username = await seed_user(username="alice")
    appid = await seed_game(name="Owned Game")

    first = await servicer.AddGameToUser(
        AddGameToUserRequest(username=username, appid=appid), context
    )
    second = await servicer.AddGameToUser(
        AddGameToUserRequest(username=username, appid=appid), context
    )

    assert first.appid == appid
    assert second.appid == appid
    response = await servicer.HasGame(
        HasGameRequest(username=username, appid=appid), context
    )
    assert response.result is True


async def test_ownership_requires_existing_user_and_game(servicer, context, seed_user, seed_game):
    username = await seed_user(username="alice")
    appid = await seed_game(name="Owned Game")

    with pytest.raises(IntegrityError):
        await servicer.AddGameToUser(
            AddGameToUserRequest(username="ghost", appid=appid), context
        )
    with pytest.raises(IntegrityError):
        await servicer.AddGameToUser(
            AddGameToUserRequest(username=username, appid=999_999), context
        )


# --- local helpers ----------------------------------------------------------

async def _all_appids():
    from sqlalchemy import text
    import store_service.routers.store_utils as store_utils

    engine = store_utils.engine
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT appid FROM store_games"))
        return [row[0] for row in result]